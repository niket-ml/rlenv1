"""Deterministic analysis and reporting for the RC1.1 Case-2 sentinel."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np

from uc_bench.mmmvp_open_rc11_freeze import read_rc11_release_freeze

ANALYSIS_PATH = Path("artifacts/mmmvp_open_rc11/sentinel_analysis.json")
SPEND_PATH = Path("artifacts/mmmvp_open_rc11/spend_ledger.json")
REPORT_PATH = Path("reports/generated/mmmvp_open_rc11_case2_sentinel.md")
FIGURE_ROOT = Path("reports/generated/mmmvp_open_rc11_case2_sentinel_figures")


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected object: {path}")
    return value


def _token_totals(summary: dict[str, Any]) -> dict[str, int]:
    prompt = completion = reasoning = cached = 0
    for request in summary.get("provider_requests") or []:
        usage = request.get("usage") or {}
        prompt += int(usage.get("prompt_tokens") or 0)
        completion += int(usage.get("completion_tokens") or 0)
        reasoning += int(
            (usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0
        )
        cached += int((request.get("cache") or {}).get("cached_prompt_tokens") or 0)
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "reasoning_tokens": reasoning,
        "cached_prompt_tokens": cached,
        "total_tokens": prompt + completion,
    }


def _failure_kind(summary: dict[str, Any]) -> str:
    classification = str(summary.get("classification"))
    grade = summary.get("diagnostic_grade") or {}
    if classification == "grader_failure":
        return "grader_failure"
    if classification == "infrastructure_failure":
        return "infrastructure_failure"
    if classification in {"provider_adapter_failure", "provider_policy_refusal"}:
        return "provider_failure"
    if classification in {
        "agent_task_failure",
        "agent_refusal",
        "context_budget_exhaustion",
        "cost_cap_reached",
    }:
        return "model_completion_failure"
    if classification == "protected_evidence_tampering":
        return "contract_failure"
    if grade and not grade.get("complete_mission_success"):
        return "scientific_failure"
    return "none"


def _model_row(root: Path, summary_path: str) -> dict[str, Any]:
    summary = _read(root / summary_path)
    grade = summary.get("diagnostic_grade") or {}
    submission = summary.get("submission") or {}
    followup = submission.get("followup_plan") or {}
    final = submission.get("final_submission") or {}
    requirements = {
        str(row["requirement_id"]): bool(row["passed"])
        for row in grade.get("requirements") or []
        if row.get("requirement_class") == "mission_critical_science"
    }
    first = grade.get("first_decision_critical_failure")
    events = submission.get("event_log") or []
    rejected = Counter(
        str(event.get("event"))
        for event in events
        if str(event.get("event", "")).endswith("_rejected")
    )
    latest = Path(summary_path).parent / "host_trajectory/latest.json"
    decision = final.get("decision") or {}
    return {
        "model_id": summary["model_id"],
        "classification": summary["classification"],
        "failure_type": _failure_kind(summary),
        "complete_mission_success": summary.get("complete_mission_success"),
        "partial_scientific_quality": summary.get("partial_scientific_quality"),
        "reliability_score": summary.get("reliability_score"),
        "requirements": requirements or None,
        "first_decision_critical_failure": first,
        "downstream_consequences": (
            first.get("downstream") or first.get("downstream_requirements") or [] if first else []
        ),
        "selected_resource": followup.get("chosen_resource"),
        "resource_rationale": followup.get("why_this_resource"),
        "belief_updates": final.get("belief_updates") or [],
        "final_decision": decision,
        "recoverable_contract_violation_count": summary.get(
            "recoverable_contract_violation_count", 0
        ),
        "protected_evidence_mutation_attempted": summary.get(
            "protected_evidence_mutation_attempted", False
        ),
        "completion_status": summary.get("stop_condition"),
        "assistant_turns": summary.get("assistant_turns", 0),
        "tool_actions": (summary.get("trajectory_persistence") or {}).get(
            "tool_action_count", 0
        ),
        "tokens": _token_totals(summary),
        "wall_time_seconds": round(
            sum(
                float(row.get("latency_seconds") or 0.0)
                for row in summary.get("provider_requests") or []
            ),
            3,
        ),
        "cost_usd": float(summary.get("cumulative_reported_cost_usd") or 0.0),
        "provider": (summary.get("provider_adapter") or {}).get("provider_order", [None])[0],
        "provider_request_count": summary.get("provider_request_count", 0),
        "tool_or_schema_rejections": dict(rejected),
        "provider_health": not any(
            row.get("error") or row.get("identity_violations")
            for row in summary.get("provider_requests") or []
        ),
        "infrastructure_health": summary["classification"] != "infrastructure_failure",
        "grader_health": bool((summary.get("grader_consistency") or {}).get("passed")),
        "trajectory_replay_health": bool(
            (summary.get("trajectory_persistence") or {}).get("passed")
        ),
        "summary_path": summary_path,
        "trajectory_path": latest.as_posix(),
        "request_body_hashes": sorted(
            {
                str((request.get("request_contract") or {}).get("request_body_contract_digest"))
                for request in summary.get("provider_requests") or []
                if (request.get("request_contract") or {}).get("request_body_contract_digest")
            }
        ),
    }


def _render_heatmap(root: Path, models: list[dict[str, Any]], requirements: list[str]) -> str:
    output = root / FIGURE_ROOT / "model_by_requirement_heatmap.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    values = np.full((len(models), len(requirements)), np.nan)
    for row_index, row in enumerate(models):
        for column_index, requirement in enumerate(requirements):
            if row["requirements"] is not None and requirement in row["requirements"]:
                values[row_index, column_index] = float(row["requirements"][requirement])
    figure_width = max(9.0, 0.75 * len(requirements))
    figure_height = max(4.0, 0.55 * len(models))
    fig, ax = plt.subplots(figsize=(figure_width, figure_height))
    masked = np.ma.masked_invalid(values)
    image = ax.imshow(masked, cmap="RdYlGn", vmin=0, vmax=1, aspect="auto")
    image.cmap.set_bad("#d9d9d9")
    ax.set_xticks(range(len(requirements)), requirements, rotation=50, ha="right")
    ax.set_yticks(range(len(models)), [row["model_id"] for row in models])
    ax.set_title("Case 2: mission-critical requirement results")
    for row_index in range(len(models)):
        for column_index in range(len(requirements)):
            value = values[row_index, column_index]
            label = "—" if np.isnan(value) else ("✓" if value else "×")
            ax.text(column_index, row_index, label, ha="center", va="center", fontsize=9)
    fig.colorbar(image, ax=ax, label="requirement pass")
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)
    return output.relative_to(root).as_posix()


def build_rc11_sentinel_analysis(project_root: Path) -> dict[str, Any]:
    """Build the complete deterministic sentinel audit and decision."""

    root = project_root.resolve()
    analysis_target = root / ANALYSIS_PATH
    if analysis_target.exists():
        raise ValueError("RC1.1 sentinel analysis already exists")
    state = _read(root / "artifacts/mmmvp_open_rc11/sentinel_state.json")
    compatibility = _read(root / "artifacts/mmmvp_open_rc11/compatibility_results.json")
    release = read_rc11_release_freeze(root)
    models = [_model_row(root, path) for path in state.get("summary_paths") or []]
    requirements = sorted(
        {
            requirement
            for row in models
            for requirement in (row.get("requirements") or {})
        }
    )
    heatmap = _render_heatmap(root, models, requirements)
    infrastructure_faults = [
        row["model_id"]
        for row in models
        if not row["infrastructure_health"]
        or not row["trajectory_replay_health"]
        or not row["grader_health"]
    ]
    provider_faults = [row["model_id"] for row in models if not row["provider_health"]]
    route_hashes = sorted(
        {hash_ for row in models for hash_ in row.get("request_body_hashes") or []}
    )
    schema_terminal = [
        row["model_id"]
        for row in models
        if row["failure_type"] == "model_completion_failure"
        and row["tool_or_schema_rejections"]
    ]
    systematic_submission_format_problem = len(schema_terminal) >= max(2, len(models) // 2)
    if state.get("status") != "completed_mandatory_review" or infrastructure_faults:
        recommendation = "NO_GO"
    elif provider_faults or systematic_submission_format_problem or len(models) < 10:
        recommendation = "GO_WITH_DISCLOSED_LIMITATION"
    else:
        recommendation = "GO_FULL_MATRIX"
    representative: list[dict[str, Any]] = []
    for label, predicate in (
        ("complete_mission", lambda row: row["complete_mission_success"] is True),
        ("scientific_failure", lambda row: row["failure_type"] == "scientific_failure"),
        (
            "recoverable_path_correction",
            lambda row: row["recoverable_contract_violation_count"] > 0,
        ),
        ("completion_failure", lambda row: row["failure_type"] == "model_completion_failure"),
    ):
        selected = next((row for row in models if predicate(row)), None)
        if selected is not None:
            representative.append(
                {
                    "label": label,
                    "model_id": selected["model_id"],
                    "summary_path": selected["summary_path"],
                    "trajectory_path": selected["trajectory_path"],
                }
            )
    funding = state.get("funding_after") or state.get("funding_stop") or state.get(
        "funding_before"
    )
    value = {
        "schema_version": "uc-bench-open-mmmvp-rc1-1-sentinel-analysis-1",
        "status": "complete" if state.get("status") == "completed_mandatory_review" else "stopped",
        "interpretation": "one-condition, one-attempt-per-model MMMVP pilot; not a ranking",
        "recommendation": recommendation,
        "scientific_freeze_digest": release["scientific_freeze_digest"],
        "rc1_release_digest": release["rc1_release_digest"],
        "rc11_infrastructure_digest": release["infrastructure_digest"],
        "serialized_request_sha256": _read(
            root / "artifacts/mmmvp_open_rc11/inherited_compatibility.json"
        )["identity"]["serialized_request_sha256"],
        "tool_schema_sha256": _read(
            root / "artifacts/mmmvp_open_rc11/inherited_compatibility.json"
        )["identity"]["tool_schema_sha256"],
        "request_body_contract_hashes": route_hashes,
        "compatibility": {
            "compatible_model_count": compatibility["compatible_model_count"],
            "qwen_original_failure_preserved": compatibility[
                "qwen_original_failure_preserved"
            ],
            "qwen_retry": next(
                row for row in compatibility["results"] if row["model_id"].startswith("qwen/")
            ),
        },
        "condition_id": "case_02",
        "order_seed": state["order_seed"],
        "execution_order": state["execution_order"],
        "models": models,
        "requirement_ids": requirements,
        "model_by_requirement_heatmap": heatmap,
        "representative_trajectories": representative,
        "failure_type_counts": dict(Counter(row["failure_type"] for row in models)),
        "recoverable_contract_violation_total": sum(
            row["recoverable_contract_violation_count"] for row in models
        ),
        "infrastructure_fault_models": infrastructure_faults,
        "provider_fault_models": provider_faults,
        "systematic_submission_format_problem": systematic_submission_format_problem,
        "schema_terminal_models": schema_terminal,
        "scientific_total_usd": round(sum(row["cost_usd"] for row in models), 8),
        "compatibility_retry_cost_usd": compatibility["cost_usd"],
        "remaining_account_headroom": funding,
        "remaining_matrix_launched": False,
        "ranking_claim_allowed": False,
    }
    spend = {
        "schema_version": "uc-bench-open-mmmvp-rc1-1-spend-ledger-1",
        "compatibility_retry_usd": compatibility["cost_usd"],
        "scientific": [
            {
                "model_id": row["model_id"],
                "cost_usd": row["cost_usd"],
                "summary_path": row["summary_path"],
            }
            for row in models
        ],
        "scientific_total_usd": value["scientific_total_usd"],
    }
    analysis_target.parent.mkdir(parents=True, exist_ok=True)
    analysis_target.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (root / SPEND_PATH).write_text(
        json.dumps(spend, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return value


def render_rc11_report(analysis: dict[str, Any]) -> str:
    lines = [
        "# UC-Bench open MMMVP RC1.1 Case-2 sentinel",
        "",
        (
            "This is a one-condition, one-attempt-per-model development pilot. "
            "It is not a stable model ranking."
        ),
        "",
        f"Recommendation: **{analysis['recommendation']}**.",
        "",
        (
            "| Model | Mission | Partial | Reliability | Failure type | Resource | "
            "Path errors | Turns | Tools | Tokens | Cost |"
        ),
        "|---|---:|---:|---:|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in analysis["models"]:
        lines.append(
            f"| `{row['model_id']}` | {row['complete_mission_success']} | "
            f"{row['partial_scientific_quality']} | {row['reliability_score']} | "
            f"{row['failure_type']} | {row['selected_resource'] or '—'} | "
            f"{row['recoverable_contract_violation_count']} | {row['assistant_turns']} | "
            f"{row['tool_actions']} | {row['tokens']['total_tokens']} | ${row['cost_usd']:.4f} |"
        )
    lines.extend(
        [
            "",
            "## Requirement evidence",
            "",
            f"![Model by requirement heatmap]({analysis['model_by_requirement_heatmap']})",
            "",
        ]
    )
    for row in analysis["models"]:
        first = row["first_decision_critical_failure"]
        lines.extend([f"### {row['model_id']}", ""])
        if first:
            lines.append(
                f"First decision-critical failure: `{first.get('requirement_id')}` — "
                f"{first.get('consequence')}. Downstream: "
                f"{json.dumps(row['downstream_consequences'], sort_keys=True)}."
            )
        else:
            lines.append("No decision-critical scientific failure was recorded.")
        lines.extend(
            [
                "",
                f"Decision: `{json.dumps(row['final_decision'], sort_keys=True)}`",
                "",
                f"Belief revision: `{json.dumps(row['belief_updates'], sort_keys=True)}`",
                "",
                f"Replay: `{row['trajectory_path']}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Integrity and scope",
            "",
            f"Scientific freeze: `{analysis['scientific_freeze_digest']}`.",
            "",
            f"RC1.1 infrastructure freeze: `{analysis['rc11_infrastructure_digest']}`.",
            "",
            (
                f"Serialized request: `{analysis['serialized_request_sha256']}`; "
                f"tool schema: `{analysis['tool_schema_sha256']}`."
            ),
            "",
            (
                f"Scientific spend: ${analysis['scientific_total_usd']:.4f}; "
                f"Qwen retry: ${analysis['compatibility_retry_cost_usd']:.4f}."
            ),
            "",
            (
                "Contract mistakes, scientific failures, completion failures, provider "
                "failures, infrastructure failures, and grader failures are reported "
                "separately. The remaining four conditions, held-out cases, excluded "
                "frontier models, and Astra were not run."
            ),
            "",
        ]
    )
    return "\n".join(lines)


__all__ = [
    "ANALYSIS_PATH",
    "REPORT_PATH",
    "build_rc11_sentinel_analysis",
    "render_rc11_report",
]

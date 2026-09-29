"""Deterministic analysis and reporting for the RC1.2 Case-2 sentinel."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np

from uc_bench.mmmvp_open_rc12_freeze import read_rc12_release_freeze
from uc_bench.mmmvp_open_verifier import SCORE_SOURCE_TABLE

ANALYSIS_PATH = Path("artifacts/mmmvp_open_rc12/sentinel_analysis.json")
SPEND_PATH = Path("artifacts/mmmvp_open_rc12/spend_ledger.json")
REPORT_PATH = Path("reports/generated/mmmvp_open_rc12_case2_sentinel.md")
FIGURE_ROOT = Path("reports/generated/mmmvp_open_rc12_case2_sentinel_figures")


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected object: {path}")
    return value


def _token_totals(summary: dict[str, Any]) -> dict[str, int]:
    totals = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "reasoning_tokens": 0,
        "cached_prompt_tokens": 0,
    }
    for request in summary.get("provider_requests") or []:
        usage = request.get("usage") or {}
        totals["prompt_tokens"] += int(usage.get("prompt_tokens") or 0)
        totals["completion_tokens"] += int(usage.get("completion_tokens") or 0)
        totals["reasoning_tokens"] += int(
            (usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0
        )
        totals["cached_prompt_tokens"] += int(
            (request.get("cache") or {}).get("cached_prompt_tokens") or 0
        )
    totals["total_tokens"] = totals["prompt_tokens"] + totals["completion_tokens"]
    return totals


def _failure_kind(summary: dict[str, Any]) -> str:
    classification = str(summary.get("classification"))
    grade = summary.get("diagnostic_grade") or {}
    if classification == "grader_failure":
        return "grader_failure"
    if classification in {"infrastructure_failure", "unknown_harness_failure"}:
        return "infrastructure_failure"
    if classification in {
        "provider_adapter_failure",
        "provider_policy_refusal",
    } and not summary.get("usable_provider_response_count"):
        return "provider_failure"
    if classification == "protected_evidence_tampering":
        return "contract_failure"
    if grade and not grade.get("complete_mission_success"):
        return "scientific_failure"
    if classification != "success" or grade is None:
        return "model_completion_failure"
    return "none"


def _model_row(root: Path, summary_path: str) -> dict[str, Any]:
    summary = _read(root / summary_path)
    grade = summary.get("diagnostic_grade") or {}
    submission = summary.get("submission") or {}
    final = submission.get("final_submission") or {}
    events = submission.get("event_log") or []
    requirements = {
        str(row["requirement_id"]): bool(row["passed"])
        for row in grade.get("requirements") or []
        if row.get("requirement_class") == "mission_critical_science"
    }
    accepted = sum(event.get("event") == "submit" for event in events)
    rejected = sum(event.get("event") == "submit_rejected" for event in events)
    first = grade.get("first_decision_critical_failure")
    replay = summary.get("trajectory_persistence") or {}
    adapter = summary.get("provider_adapter") or {}
    return {
        "model_id": summary["model_id"],
        "classification": summary["classification"],
        "failure_type": _failure_kind(summary),
        "complete_mission_success": summary.get("complete_mission_success"),
        "partial_scientific_quality": summary.get("partial_scientific_quality"),
        "reliability_score": summary.get("reliability_score"),
        "requirements": requirements or None,
        "accepted_submission_count": accepted,
        "rejected_submission_count": rejected,
        "first_decision_critical_failure": first,
        "downstream_consequences": (
            (first.get("downstream") or first.get("downstream_requirements") or []) if first else []
        ),
        "selected_resource": (submission.get("followup_plan") or {}).get("chosen_resource"),
        "belief_updates": final.get("belief_updates") or [],
        "final_decision": final.get("decision") or {},
        "recoverable_contract_violation_count": summary.get(
            "recoverable_contract_violation_count", 0
        ),
        "horizon_boundary": summary.get("horizon_boundary") or {},
        "completion_status": summary.get("stop_condition"),
        "turns": int(summary.get("turn_count") or summary.get("assistant_turns") or 0),
        "tool_actions": int(replay.get("tool_action_count") or 0),
        "tokens": _token_totals(summary),
        "wall_time_seconds": round(
            sum(
                float(request.get("latency_seconds") or 0.0)
                for request in summary.get("provider_requests") or []
            ),
            3,
        ),
        "cost_usd": float(summary.get("cumulative_reported_cost_usd") or 0.0),
        "provider": (adapter.get("provider_order") or [None])[0],
        "provider_request_count": int(summary.get("provider_request_count") or 0),
        "provider_health": not any(
            request.get("error") or request.get("identity_violations")
            for request in summary.get("provider_requests") or []
        ),
        "infrastructure_health": summary["classification"] != "infrastructure_failure",
        "grader_health": bool((summary.get("grader_consistency") or {}).get("passed")),
        "trajectory_replay_health": bool(replay.get("passed")),
        "summary_path": summary_path,
        "trajectory_path": (Path(summary_path).parent / "host_trajectory/latest.json").as_posix(),
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
    fig, ax = plt.subplots(
        figsize=(max(10.0, 0.8 * len(requirements)), max(4.0, 0.6 * len(models)))
    )
    masked = np.ma.masked_invalid(values)
    image = ax.imshow(masked, cmap="RdYlGn", vmin=0, vmax=1, aspect="auto")
    image.cmap.set_bad("#d9d9d9")
    ax.set_xticks(range(len(requirements)), requirements, rotation=50, ha="right")
    labels = [
        row["model_id"]
        if row["requirements"] is not None
        else f"{row['model_id']} [{row['failure_type']}]"
        for row in models
    ]
    ax.set_yticks(range(len(models)), labels)
    ax.set_title("Case 2 mission-critical requirements (grey = not gradeable)")
    for row_index in range(len(models)):
        for column_index in range(len(requirements)):
            value = values[row_index, column_index]
            label = "—" if np.isnan(value) else ("✓" if value else "×")
            ax.text(column_index, row_index, label, ha="center", va="center", fontsize=8)
    fig.colorbar(image, ax=ax, label="requirement pass")
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)
    return output.relative_to(root).as_posix()


def build_rc12_sentinel_analysis(project_root: Path) -> dict[str, Any]:
    """Build the full deterministic sentinel audit without model calls."""

    root = project_root.resolve()
    if (root / ANALYSIS_PATH).exists():
        raise ValueError("RC1.2 sentinel analysis already exists")
    state = _read(root / "artifacts/mmmvp_open_rc12/sentinel_state.json")
    compatibility = _read(root / "artifacts/mmmvp_open_rc12/inherited_compatibility.json")
    release = read_rc12_release_freeze(root)
    models = [_model_row(root, path) for path in state.get("summary_paths") or []]
    requirements = [str(row["requirement_id"]) for row in SCORE_SOURCE_TABLE][1:]
    heatmap = _render_heatmap(root, models, requirements)
    infrastructure_faults = [
        row["model_id"]
        for row in models
        if not row["infrastructure_health"]
        or not row["trajectory_replay_health"]
        or not row["grader_health"]
    ]
    provider_faults = [row["model_id"] for row in models if not row["provider_health"]]
    complete = state.get("status") == "completed_mandatory_review" and len(models) == 10
    gradeable_count = sum(row["requirements"] is not None for row in models)
    widespread_submission_failure = complete and gradeable_count < 3
    if not complete or infrastructure_faults or provider_faults:
        recommendation = "NO_GO"
    elif widespread_submission_failure:
        recommendation = "GO_WITH_DISCLOSED_LIMITATION"
    else:
        recommendation = "GO_FULL_MATRIX"
    request_hashes = sorted(
        {digest for row in models for digest in row.get("request_body_hashes") or []}
    )
    value = {
        "schema_version": "uc-bench-open-mmmvp-rc1-2-sentinel-analysis-1",
        "status": "complete" if complete else "stopped",
        "interpretation": "one-condition, one-attempt-per-model MMMVP pilot; not a ranking",
        "recommendation": recommendation,
        "scientific_freeze_digest": release["scientific_freeze_digest"],
        "rc11_infrastructure_digest": release["rc11_infrastructure_digest"],
        "rc12_infrastructure_digest": release["infrastructure_digest"],
        "serialized_request_sha256": release["serialized_request_sha256"],
        "tool_schema_sha256": release["tool_schema_sha256"],
        "request_body_contract_hashes": request_hashes,
        "compatibility": {
            "status": compatibility["status"],
            "inherited_model_count": compatibility["inherited_model_count"],
            "new_paid_canaries": compatibility["paid_compatibility_requests"],
        },
        "condition_id": "case_02",
        "order_seed": state["order_seed"],
        "execution_order": state["execution_order"],
        "models": models,
        "requirement_ids": requirements,
        "model_by_requirement_heatmap": heatmap,
        "failure_type_counts": dict(Counter(row["failure_type"] for row in models)),
        "gradeable_submission_count": gradeable_count,
        "widespread_submission_failure": widespread_submission_failure,
        "infrastructure_fault_models": infrastructure_faults,
        "provider_fault_models": provider_faults,
        "scientific_total_usd": round(sum(row["cost_usd"] for row in models), 8),
        "remaining_account_headroom": state.get("funding_after")
        or state.get("funding_stop")
        or state.get("funding_before"),
        "remaining_matrix_launched": False,
        "ranking_claim_allowed": False,
    }
    spend = {
        "schema_version": "uc-bench-open-mmmvp-rc1-2-spend-ledger-1",
        "compatibility_usd": 0.0,
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
    (root / ANALYSIS_PATH).write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (root / SPEND_PATH).write_text(
        json.dumps(spend, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return value


def render_rc12_report(analysis: dict[str, Any]) -> str:
    lines = [
        "# UC-Bench open MMMVP RC1.2 Case-2 sentinel",
        "",
        "This is a one-condition, one-attempt-per-model development pilot, not a stable ranking.",
        "",
        f"Recommendation: **{analysis['recommendation']}**.",
        "",
        (
            "| Model | Mission | Partial | Reliability | Failure | Accepted/rejected | "
            "Path errors | Horizon call | Turns | Tools | Tokens | Cost |"
        ),
        "|---|---:|---:|---:|---|---:|---:|---|---:|---:|---:|---:|",
    ]
    for row in analysis["models"]:
        horizon = row["horizon_boundary"]
        horizon_label = (
            f"{horizon.get('terminal_tool_name')} ({horizon.get('terminal_boundary_reason')})"
            if horizon.get("unexecuted_terminal_tool_count")
            else "—"
        )
        lines.append(
            f"| `{row['model_id']}` | {row['complete_mission_success']} | "
            f"{row['partial_scientific_quality']} | {row['reliability_score']} | "
            f"{row['failure_type']} | {row['accepted_submission_count']}/"
            f"{row['rejected_submission_count']} | "
            f"{row['recoverable_contract_violation_count']} | {horizon_label} | "
            f"{row['turns']} | {row['tool_actions']} | {row['tokens']['total_tokens']} | "
            f"${row['cost_usd']:.6f} |"
        )
    lines.extend(
        [
            "",
            "## Model × requirement",
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
        elif row["requirements"] is None:
            lines.append(
                f"No scientific grade: `{row['failure_type']}` with stop "
                f"`{row['completion_status']}`."
            )
        else:
            lines.append("No decision-critical scientific failure was recorded.")
        lines.extend(
            [
                "",
                f"Resource: `{row['selected_resource']}`.",
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
            f"RC1.2 infrastructure freeze: `{analysis['rc12_infrastructure_digest']}`.",
            "",
            (
                f"Serialized request: `{analysis['serialized_request_sha256']}`; "
                f"tool schema: `{analysis['tool_schema_sha256']}`."
            ),
            "",
            (
                f"Scientific spend: ${analysis['scientific_total_usd']:.6f}; "
                "paid RC1.2 compatibility spend: $0."
            ),
            "",
            (
                "Contract, scientific, model-completion, provider, infrastructure, and "
                "grader failures remain separate. The remaining four conditions, held-out "
                "cases, Sol, Astra, GPT-5.2+, and Claude 4.5+ were not run."
            ),
            "",
        ]
    )
    return "\n".join(lines)


__all__ = [
    "ANALYSIS_PATH",
    "REPORT_PATH",
    "build_rc12_sentinel_analysis",
    "render_rc12_report",
]

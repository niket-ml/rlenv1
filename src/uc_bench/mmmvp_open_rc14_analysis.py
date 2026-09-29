"""Separated scientific, completion, contract and infrastructure analysis for RC1.4."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from uc_bench.mmmvp_open_rc13_analysis import submission_friction as rc13_submission_friction
from uc_bench.mmmvp_open_rc14_audit import issue_is_disclosed
from uc_bench.mmmvp_open_rc14_sentinel import rc14_global_stop_faults
from uc_bench.model_runner import _write_json

ANALYSIS_PATH = Path("artifacts/mmmvp_open_rc14/sentinel_analysis.json")
REPORT_PATH = Path("reports/generated/mmmvp_open_rc14_case2_sentinel.md")


def rc14_submission_friction(summary: dict[str, Any]) -> dict[str, Any]:
    base = rc13_submission_friction(summary)
    rejections = [
        row
        for row in (summary.get("submission", {}).get("event_log") or [])
        if row.get("event") == "submit_rejected"
    ]
    issues = [issue for row in rejections for issue in row.get("schema_issues") or []]
    undisclosed = sorted(
        {
            f"{issue.get('code')}:{issue.get('path')}"
            for issue in issues
            if not issue_is_disclosed(issue)
        }
    )
    return {
        **base,
        "machine_rule_disclosed_to_agent": all(
            issue_is_disclosed(issue) for issue in issues
        )
        if issues
        else None,
        "first_rejected_rule_disclosed": issue_is_disclosed(issues[0]) if issues else None,
        "undisclosed_machine_requirements": undisclosed,
    }


def _first_failure(grade: dict[str, Any]) -> dict[str, Any] | None:
    return grade.get("first_decision_critical_failure")


def analyze_rc14_sentinel(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    state = json.loads(
        (root / "artifacts/mmmvp_open_rc14/sentinel_state.json").read_text()
    )
    models: list[dict[str, Any]] = []
    for relative in state.get("summary_paths") or []:
        summary = json.loads((root / relative).read_text())
        grade = summary.get("diagnostic_grade") or {}
        friction = rc14_submission_friction(summary)
        classification = str(summary.get("classification"))
        infrastructure_excluded = classification in {
            "provider_adapter_failure",
            "provider_policy_refusal",
            "infrastructure_failure",
            "unknown_harness_failure",
            "grader_failure",
            "protected_evidence_tampering",
        }
        scientific_failure = (
            _first_failure(grade)
            if grade and not grade.get("complete_mission_success")
            else None
        )
        model_completion_failure = classification in {
            "agent_task_failure",
            "agent_refusal",
            "context_budget_exhaustion",
            "cost_cap_reached",
        }
        submission_contract_failure = bool(
            friction["rejected_submission_count"]
            or friction["final_failure_class"]
            == "completion_with_contract_friction"
        )
        recoverable_tool_use_failure = bool(
            summary.get("framework_tool_error_count")
            or summary.get("wrapper_tool_error_count")
        )
        provider_specific_failure = classification in {
            "provider_adapter_failure",
            "provider_policy_refusal",
            "infrastructure_failure",
        } and not rc14_global_stop_faults(summary)
        shared_infrastructure_failure = bool(rc14_global_stop_faults(summary))
        models.append(
            {
                "model_id": summary["model_id"],
                "classification": classification,
                "strict_mission_success": summary.get("complete_mission_success"),
                "partial_scientific_quality": summary.get("partial_scientific_quality"),
                "reliability_score": summary.get("reliability_score"),
                "first_scientific_failure": scientific_failure,
                "failure_taxonomy": {
                    "scientific_failure": scientific_failure is not None,
                    "model_completion_failure": model_completion_failure,
                    "submission_or_contract_failure": submission_contract_failure,
                    "recoverable_tool_use_failure": recoverable_tool_use_failure,
                    "provider_specific_failure": provider_specific_failure,
                    "shared_infrastructure_failure": shared_infrastructure_failure,
                },
                "submission_friction": friction,
                "turns": summary.get("turn_count"),
                "tool_calls": (summary.get("submission", {}).get("state") or {}).get(
                    "tool_calls"
                ),
                "cost_usd": summary.get("cumulative_reported_cost_usd"),
                "framework_tool_error_count": summary.get("framework_tool_error_count"),
                "wrapper_tool_error_count": summary.get("wrapper_tool_error_count"),
                "infrastructure_excluded": infrastructure_excluded,
                "provider_request_count": summary.get("provider_request_count"),
                "completion_status": (summary.get("submission", {}).get("state") or {}).get(
                    "terminal_reason"
                ),
            }
        )
    graded = [row for row in models if row["strict_mission_success"] is not None]
    scientific_signatures = Counter(
        str((row["first_scientific_failure"] or {}).get("requirement_id"))
        for row in graded
        if not row["strict_mission_success"]
    )
    contract_only = [
        row
        for row in models
        if row["submission_friction"]["final_failure_class"]
        == "completion_with_contract_friction"
    ]
    undisclosed = [
        row
        for row in models
        if row["submission_friction"]["undisclosed_machine_requirements"]
    ]
    substantive = [
        row
        for row in models
        if row["submission_friction"][
            "substantive_scientific_work_complete_before_first_rejection"
        ]
    ]
    artificial_floor = bool(
        undisclosed or (substantive and len(contract_only) >= len(substantive) / 2)
    )
    observed_pairs = {
        (row["strict_mission_success"], row["partial_scientific_quality"])
        for row in graded
    }
    genuine_differences = bool(
        len(graded) >= 2
        and len(observed_pairs) >= 2
        and not artificial_floor
        and len(scientific_signatures) >= 1
    )
    if state.get("status") != "completed_mandatory_review":
        decision = "INSUFFICIENT_EVIDENCE_EARLY_STOP"
    elif artificial_floor:
        decision = "NO_GO_ARTIFICIAL_CONTRACT_OR_COMPLETION_FLOOR"
    elif genuine_differences:
        decision = "CASE2_SHOWS_GENUINE_SINGLE_ATTEMPT_WORKFLOW_DIFFERENCES"
    else:
        decision = "CASE2_DIFFERENCE_NOT_ESTABLISHED"
    value = {
        "schema_version": "uc-bench-open-mmmvp-rc1-4-sentinel-analysis-1",
        "status": state.get("status"),
        "decision": decision,
        "execution_order": state.get("execution_order") or [],
        "completed_model_count": len(models),
        "graded_model_count": len(graded),
        "strict_mission_success_count": sum(
            row["strict_mission_success"] is True for row in graded
        ),
        "models": models,
        "scientific_failure_signatures": dict(sorted(scientific_signatures.items())),
        "contract_only_completion_count": len(contract_only),
        "undisclosed_contract_failure_count": len(undisclosed),
        "artificial_contract_or_completion_floor": artificial_floor,
        "genuine_scientific_workflow_differences_observed": genuine_differences,
        "combined_spend_usd": float(state.get("compatibility_cost_usd") or 0)
        + float(state.get("scientific_spend_usd") or 0),
        "scientific_spend_usd": state.get("scientific_spend_usd"),
        "compatibility_spend_usd": state.get("compatibility_cost_usd"),
        "provider_or_infrastructure_exclusion_count": sum(
            row["infrastructure_excluded"] for row in models
        ),
        "failure_class_counts": {
            name: sum(row["failure_taxonomy"][name] for row in models)
            for name in (
                "scientific_failure",
                "model_completion_failure",
                "submission_or_contract_failure",
                "recoverable_tool_use_failure",
                "provider_specific_failure",
                "shared_infrastructure_failure",
            )
        },
        "remaining_matrix_launched": False,
        "ranking_claim_allowed": False,
    }
    target = root / ANALYSIS_PATH
    _write_json(target, value, secret="")
    return value


def write_rc14_report(project_root: Path, analysis: dict[str, Any]) -> Path:
    root = project_root.resolve()
    lines = [
        "# UC-Bench open MMMVP RC1.4 Case-2 sentinel",
        "",
        f"Decision: **{analysis['decision']}**.",
        "",
        (
            "| Model | Mission | Partial | Reliability | Rejects | Tool errors | "
            "Turns | Cost | Class |"
        ),
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in analysis["models"]:
        friction = row["submission_friction"]
        tool_errors = int(row["framework_tool_error_count"] or 0) + int(
            row["wrapper_tool_error_count"] or 0
        )
        lines.append(
            f"| `{row['model_id']}` | {row['strict_mission_success']} | "
            f"{row['partial_scientific_quality']} | {row['reliability_score']} | "
            f"{friction['rejected_submission_count']} | {tool_errors} | "
            f"{row['turns']} | ${float(row['cost_usd'] or 0):.4f} | "
            f"{row['classification']} |"
        )
    lines.extend(
        [
            "",
            f"- Completed cells: {analysis['completed_model_count']}/10",
            f"- Strict missions: {analysis['strict_mission_success_count']}",
            f"- Undisclosed-contract failures: {analysis['undisclosed_contract_failure_count']}",
            (
                "- Provider/infrastructure exclusions: "
                f"{analysis['provider_or_infrastructure_exclusion_count']}"
            ),
            f"- Compatibility spend: ${float(analysis['compatibility_spend_usd'] or 0):.4f}",
            f"- Scientific spend: ${float(analysis['scientific_spend_usd'] or 0):.4f}",
            f"- Combined spend: ${float(analysis['combined_spend_usd'] or 0):.4f}",
            "",
            (
                "This is one attempt per model on one development condition; it is not "
                "a stable ranking."
            ),
        ]
    )
    target = root / REPORT_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


__all__ = [
    "ANALYSIS_PATH",
    "REPORT_PATH",
    "analyze_rc14_sentinel",
    "rc14_submission_friction",
    "write_rc14_report",
]

"""Model-separated Case-2 analysis for RC1.5."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from uc_bench.mmmvp_open_rc14_analysis import rc14_submission_friction
from uc_bench.mmmvp_open_rc15_sentinel import STATE_PATH, rc15_global_stop_faults
from uc_bench.model_runner import _write_json

ANALYSIS_PATH = Path("artifacts/mmmvp_open_rc15/sentinel_analysis.json")
REPORT_PATH = Path("reports/generated/mmmvp_open_rc15_case2_sentinel.md")


def _submission_counts(summary: dict[str, Any]) -> tuple[int, int]:
    events = (summary.get("submission") or {}).get("event_log") or []
    accepted = sum(row.get("event") == "submit" for row in events)
    rejected = sum(row.get("event") == "submit_rejected" for row in events)
    return accepted, rejected


def _decision_details(summary: dict[str, Any]) -> dict[str, Any]:
    final = (summary.get("submission") or {}).get("final_submission") or {}
    beliefs = final.get("belief_updates") or []
    return {
        "decision": final.get("decision"),
        "belief_updates": [
            {
                "hypothesis_id": row.get("hypothesis_id"),
                "before": row.get("before"),
                "after": row.get("after"),
            }
            for row in beliefs
        ],
        "selected_resource": (summary.get("submission") or {})
        .get("state", {})
        .get("selected_resource"),
    }


def analyze_rc15_sentinel(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    state = json.loads((root / STATE_PATH).read_text(encoding="utf-8"))
    models: list[dict[str, Any]] = []
    for relative in state.get("summary_paths") or []:
        summary = json.loads((root / relative).read_text(encoding="utf-8"))
        grade = summary.get("diagnostic_grade") or {}
        friction = rc14_submission_friction(summary)
        accepted, rejected = _submission_counts(summary)
        classification = str(summary.get("classification"))
        first_failure = grade.get("first_decision_critical_failure")
        provider_excluded = classification in {
            "provider_adapter_failure",
            "provider_policy_refusal",
            "infrastructure_failure",
        } and not rc15_global_stop_faults(summary)
        shared_infrastructure = bool(rc15_global_stop_faults(summary))
        completion_failure = classification in {
            "agent_task_failure",
            "agent_refusal",
            "context_budget_exhaustion",
            "cost_cap_reached",
        }
        contract_failure = bool(rejected and not accepted)
        tool_errors = int(summary.get("framework_tool_error_count") or 0) + int(
            summary.get("wrapper_tool_error_count") or 0
        )
        models.append(
            {
                "model_id": summary["model_id"],
                "classification": classification,
                "strict_mission_success": summary.get("complete_mission_success"),
                "partial_scientific_quality": summary.get(
                    "partial_scientific_quality"
                ),
                "reliability_score": summary.get("reliability_score"),
                "accepted_submission_count": accepted,
                "rejected_submission_count": rejected,
                "first_decision_critical_scientific_failure": first_failure,
                "completion_failure": completion_failure,
                "contract_failure": contract_failure,
                "submission_friction": friction,
                "recoverable_tool_use_error_count": tool_errors,
                "framework_tool_error_count": summary.get(
                    "framework_tool_error_count"
                ),
                "wrapper_tool_error_count": summary.get("wrapper_tool_error_count"),
                "turns": summary.get("turn_count"),
                "requests": summary.get("provider_request_count"),
                "cost_usd": summary.get("cumulative_reported_cost_usd"),
                "provider_or_infrastructure_exclusion": provider_excluded,
                "shared_infrastructure_failure": shared_infrastructure,
                **_decision_details(summary),
            }
        )

    graded = [row for row in models if row["strict_mission_success"] is not None]
    successes = [row for row in graded if row["strict_mission_success"]]
    failures = [row for row in graded if not row["strict_mission_success"]]
    scientific_failures = [
        row for row in failures if row["first_decision_critical_scientific_failure"]
    ]
    undisclosed = [
        row
        for row in models
        if row["submission_friction"]["undisclosed_machine_requirements"]
    ]
    completion_or_contract = [
        row for row in models if row["completion_failure"] or row["contract_failure"]
    ]
    artificial_floor = bool(
        undisclosed
        or graded
        and len(completion_or_contract) > len(graded) / 2
        and len(scientific_failures) < len(completion_or_contract)
    )
    observed_outcomes = {
        (row["strict_mission_success"], row["partial_scientific_quality"])
        for row in graded
    }
    genuine_separation = bool(
        len(graded) >= 3
        and len(observed_outcomes) >= 2
        and scientific_failures
        and not artificial_floor
    )
    scientific_floor = bool(
        failures
        and scientific_failures
        and any((row["partial_scientific_quality"] or 0) > 0 for row in failures)
        and not artificial_floor
    )
    ceiling = bool(len(graded) >= 3 and len(successes) == len(graded))
    if state.get("status") != "completed_mandatory_review":
        conclusion = "INSUFFICIENT_EVIDENCE_EARLY_STOP"
    elif artificial_floor:
        conclusion = "ARTIFICIAL_CONTRACT_OR_COMPLETION_FLOOR"
    elif ceiling:
        conclusion = "SINGLE_ATTEMPT_CASE2_CEILING_WARNING"
    elif genuine_separation:
        conclusion = "GENUINE_SINGLE_ATTEMPT_CAPABILITY_SEPARATION"
    elif scientific_floor:
        conclusion = "CREDIBLE_SCIENTIFIC_FLOOR_WITHOUT_CLEAR_SEPARATION"
    else:
        conclusion = "INSUFFICIENT_EVIDENCE"
    failure_signatures = Counter(
        str(
            (row["first_decision_critical_scientific_failure"] or {}).get(
                "requirement_id"
            )
        )
        for row in scientific_failures
    )
    value = {
        "schema_version": "uc-bench-open-mmmvp-rc1-5-sentinel-analysis-1",
        "status": state.get("status"),
        "conclusion": conclusion,
        "model_count": len(models),
        "graded_model_count": len(graded),
        "strict_mission_success_count": len(successes),
        "models": models,
        "case2_assessment": {
            "genuine_capability_separation": genuine_separation,
            "credible_scientific_floor": scientific_floor,
            "ceiling": ceiling,
            "artificial_contract_or_completion_floor": artificial_floor,
            "insufficient_evidence": conclusion.startswith("INSUFFICIENT"),
        },
        "first_failure_signatures": dict(sorted(failure_signatures.items())),
        "scientific_spend_usd": state.get("scientific_spend_usd"),
        "provider_or_infrastructure_exclusion_count": sum(
            row["provider_or_infrastructure_exclusion"] for row in models
        ),
        "shared_infrastructure_failure_count": sum(
            row["shared_infrastructure_failure"] for row in models
        ),
        "remaining_matrix_launched": False,
        "ranking_claim_allowed": False,
        "interpretation_limit": (
            "One attempt per model on one development condition is not a stable ranking."
        ),
    }
    _write_json(root / ANALYSIS_PATH, value, secret="")
    return value


def write_rc15_report(project_root: Path, analysis: dict[str, Any]) -> Path:
    root = project_root.resolve()
    lines = [
        "# UC-Bench open MMMVP RC1.5 Case-2 sentinel",
        "",
        f"Conclusion: **{analysis['conclusion']}**.",
        "",
        (
            "| Model | Mission | Partial | Reliability | Accepted/rejected | "
            "Tool errors | Turns | Requests | Cost | Class |"
        ),
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in analysis["models"]:
        lines.append(
            f"| `{row['model_id']}` | {row['strict_mission_success']} | "
            f"{row['partial_scientific_quality']} | {row['reliability_score']} | "
            f"{row['accepted_submission_count']}/{row['rejected_submission_count']} | "
            f"{row['recoverable_tool_use_error_count']} | {row['turns']} | "
            f"{row['requests']} | ${float(row['cost_usd'] or 0):.4f} | "
            f"{row['classification']} |"
        )
        if row["first_decision_critical_scientific_failure"]:
            lines.extend(
                [
                    "",
                    (
                        f"First scientific failure for `{row['model_id']}`: "
                        "`"
                        + json.dumps(
                            row["first_decision_critical_scientific_failure"],
                            sort_keys=True,
                        )
                        + "`"
                    ),
                ]
            )
    assessment = analysis["case2_assessment"]
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            f"- Genuine capability separation: {assessment['genuine_capability_separation']}",
            f"- Credible scientific floor: {assessment['credible_scientific_floor']}",
            f"- Ceiling: {assessment['ceiling']}",
            (
                "- Artificial contract/completion floor: "
                f"{assessment['artificial_contract_or_completion_floor']}"
            ),
            f"- Insufficient evidence: {assessment['insufficient_evidence']}",
            f"- Scientific spend: ${float(analysis['scientific_spend_usd'] or 0):.4f}",
            "",
            analysis["interpretation_limit"],
            "No other condition was run.",
        ]
    )
    target = root / REPORT_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


__all__ = [
    "ANALYSIS_PATH",
    "REPORT_PATH",
    "analyze_rc15_sentinel",
    "write_rc15_report",
]

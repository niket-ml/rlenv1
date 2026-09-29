"""Separated scientific and infrastructure analysis for RC1.6 Case 2."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from uc_bench.mmmvp_open_rc14_analysis import rc14_submission_friction
from uc_bench.mmmvp_open_rc16_sentinel import STATE_PATH, rc16_global_stop_faults
from uc_bench.model_runner import _write_json

ANALYSIS_PATH = Path("artifacts/mmmvp_open_rc16/sentinel_analysis.json")
REPORT_PATH = Path("reports/generated/mmmvp_open_rc16_case2_sentinel.md")


def _requirement(grade: dict[str, Any], requirement_id: str) -> dict[str, Any] | None:
    return next(
        (
            row
            for row in grade.get("requirements") or []
            if row.get("requirement_id") == requirement_id
        ),
        None,
    )


def _submission_counts(summary: dict[str, Any]) -> tuple[int, int]:
    events = (summary.get("submission") or {}).get("event_log") or []
    return (
        sum(row.get("event") == "submit" for row in events),
        sum(row.get("event") == "submit_rejected" for row in events),
    )


def analyze_rc16_sentinel(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    state = json.loads((root / STATE_PATH).read_text(encoding="utf-8"))
    models: list[dict[str, Any]] = []
    for relative in state.get("summary_paths") or []:
        summary = json.loads((root / relative).read_text(encoding="utf-8"))
        grade = summary.get("diagnostic_grade") or {}
        diagnostics = grade.get("diagnostics") or {}
        accepted, rejected = _submission_counts(summary)
        classification = str(summary.get("classification"))
        first = grade.get("first_decision_critical_failure")
        artifact_failures = [
            row for row in diagnostics.get("artifact_validation") or [] if not row.get("valid")
        ]
        final = (summary.get("submission") or {}).get("final_submission") or {}
        beliefs = final.get("belief_updates") or []
        requirements = {
            name: _requirement(grade, name)
            for name in (
                "prospective_plan_implemented",
                "relevant_entity_reconstruction",
                "decision_relevant_quantitative_work",
                "decision_relevant_followup",
                "purchased_evidence_analyzed",
                "belief_commitment_and_revision",
                "evidence_supported_decision",
            )
        }
        tool_errors = int(summary.get("framework_tool_error_count") or 0) + int(
            summary.get("wrapper_tool_error_count") or 0
        )
        global_faults = rc16_global_stop_faults(summary)
        provider_excluded = (
            classification
            in {
                "provider_adapter_failure",
                "provider_policy_refusal",
                "infrastructure_failure",
            }
            and not global_faults
        )
        models.append(
            {
                "model_id": summary["model_id"],
                "classification": classification,
                "strict_mission_success": summary.get("complete_mission_success"),
                "partial_scientific_quality": summary.get("partial_scientific_quality"),
                "reliability_score": summary.get("reliability_score"),
                "first_decision_critical_scientific_failure": first,
                "artifact_validation_failures": artifact_failures,
                "plan_implementation": requirements["prospective_plan_implemented"],
                "patient_dependence_analysis": requirements["relevant_entity_reconstruction"],
                "site_analysis": requirements["decision_relevant_quantitative_work"],
                "resource_selection": requirements["decision_relevant_followup"],
                "resource_use": requirements["purchased_evidence_analyzed"],
                "belief_revision": {
                    "requirement": requirements["belief_commitment_and_revision"],
                    "updates": beliefs,
                },
                "decision_support": requirements["evidence_supported_decision"],
                "final_decision": final.get("decision"),
                "selected_resource": (summary.get("submission") or {})
                .get("state", {})
                .get("selected_resource"),
                "submission_friction": rc14_submission_friction(summary),
                "accepted_submission_count": accepted,
                "rejected_submission_count": rejected,
                "recoverable_tool_error_count": tool_errors,
                "framework_tool_error_count": summary.get("framework_tool_error_count"),
                "wrapper_tool_error_count": summary.get("wrapper_tool_error_count"),
                "turns": summary.get("turn_count"),
                "requests": summary.get("provider_request_count"),
                "cost_usd": summary.get("cumulative_reported_cost_usd"),
                "provider_or_infrastructure_exclusion": provider_excluded,
                "shared_infrastructure_failure": bool(global_faults),
                "shared_infrastructure_faults": global_faults,
            }
        )

    graded = [row for row in models if row["strict_mission_success"] is not None]
    successful = [row for row in graded if row["strict_mission_success"]]
    failed = [row for row in graded if not row["strict_mission_success"]]
    scientific_failures = [
        row for row in failed if row["first_decision_critical_scientific_failure"]
    ]
    artificial = [
        row
        for row in models
        if row["submission_friction"]["undisclosed_machine_requirements"]
        or (row["rejected_submission_count"] and not row["accepted_submission_count"])
    ]
    outcomes = {
        (row["strict_mission_success"], row["partial_scientific_quality"]) for row in graded
    }
    gradient = bool(
        len(graded) >= 3 and len(outcomes) >= 3 and scientific_failures and not artificial
    )
    floor = bool(
        scientific_failures
        and any(float(row["partial_scientific_quality"] or 0) > 0 for row in failed)
        and not artificial
    )
    ceiling = bool(len(graded) >= 3 and len(successful) == len(graded))
    completion_floor = bool(artificial)
    if state.get("status") != "completed_mandatory_review":
        conclusion = "INSUFFICIENT_EVIDENCE_EARLY_STOP"
    elif ceiling:
        conclusion = "SINGLE_ATTEMPT_CASE2_CEILING_WARNING"
    elif completion_floor:
        conclusion = "ARTIFICIAL_CONTRACT_OR_COMPLETION_FLOOR"
    elif gradient:
        conclusion = "GENUINE_SINGLE_ATTEMPT_CAPABILITY_GRADIENT"
    elif floor:
        conclusion = "CREDIBLE_SCIENTIFIC_FLOOR_WITHOUT_CLEAR_GRADIENT"
    else:
        conclusion = "INSUFFICIENT_EVIDENCE"
    signatures = Counter(
        str(row["first_decision_critical_scientific_failure"]["requirement_id"])
        for row in scientific_failures
    )
    value = {
        "schema_version": "uc-bench-open-mmmvp-rc1-6-sentinel-analysis-1",
        "status": state.get("status"),
        "conclusion": conclusion,
        "models": models,
        "model_count": len(models),
        "graded_model_count": len(graded),
        "strict_mission_success_count": len(successful),
        "case2_assessment": {
            "genuine_capability_gradient": gradient,
            "credible_scientific_floor": floor,
            "ceiling": ceiling,
            "artificial_contract_or_completion_floor": completion_floor,
            "insufficient_evidence": conclusion.startswith("INSUFFICIENT"),
        },
        "first_failure_signatures": dict(sorted(signatures.items())),
        "scientific_spend_usd": state.get("scientific_spend_usd"),
        "ranking_claim_allowed": False,
        "other_conditions_launched": False,
        "interpretation_limit": (
            "One attempt per model on one development condition is not a stable ranking."
        ),
    }
    _write_json(root / ANALYSIS_PATH, value, secret="")
    return value


def write_rc16_report(project_root: Path, analysis: dict[str, Any]) -> Path:
    root = project_root.resolve()
    lines = [
        "# UC-Bench open MMMVP RC1.6 Case-2 sentinel",
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
            f"{row['recoverable_tool_error_count']} | {row['turns']} | {row['requests']} | "
            f"${float(row['cost_usd'] or 0):.4f} | {row['classification']} |"
        )
        if row["first_decision_critical_scientific_failure"]:
            lines.extend(
                [
                    "",
                    f"First failure for `{row['model_id']}`: `"
                    + json.dumps(row["first_decision_critical_scientific_failure"], sort_keys=True)
                    + "`",
                ]
            )
    assessment = analysis["case2_assessment"]
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            f"- Genuine capability gradient: {assessment['genuine_capability_gradient']}",
            f"- Credible scientific floor: {assessment['credible_scientific_floor']}",
            f"- Ceiling: {assessment['ceiling']}",
            "- Artificial contract/completion floor: "
            f"{assessment['artificial_contract_or_completion_floor']}",
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


__all__ = ["analyze_rc16_sentinel", "write_rc16_report"]

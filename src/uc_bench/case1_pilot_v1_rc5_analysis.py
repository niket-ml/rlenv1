"""Evidence-citing RC5 Case-1 pilot report."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from uc_bench.case1_pilot_v1_rc5_execution import STATE_PATH
from uc_bench.case1_pilot_v1_rc5_release import read_rc5_freeze
from uc_bench.errors import ConfigurationError
from uc_bench.model_runner import _write_json

REPORT_PATH = Path("artifacts/uc_bench_case1_pilot_v1_rc5/science/pilot_report.json")
MANUAL_ADJUDICATIONS_PATH = Path(
    "artifacts/uc_bench_case1_pilot_v1_rc5/science/manual_adjudications.json"
)

_MODEL_COMPLETION_CLASSES = frozenset(
    {"agent_task_failure", "agent_refusal", "context_budget_exhaustion", "cost_cap_reached"}
)
_PROVIDER_CLASSES = frozenset({"provider_adapter_failure", "provider_policy_refusal"})
_INFRASTRUCTURE_CLASSES = frozenset(
    {
        "grader_failure",
        "infrastructure_failure",
        "provider_identity_failure",
        "unknown_harness_failure",
    }
)
_EXECUTION_INTEGRITY_CLASSES = frozenset({"protected_evidence_tampering"})


def execution_taxonomy_bucket(
    execution_classification: Any,
    verifier_failure_class: Any,
    mission_success: Any,
) -> str:
    """Assign each completed cell one exhaustive, non-overlapping report bucket."""

    if execution_classification in _PROVIDER_CLASSES:
        return "provider"
    if execution_classification in _INFRASTRUCTURE_CLASSES:
        return "infrastructure"
    if execution_classification in _MODEL_COMPLETION_CLASSES:
        return "model_completion"
    if execution_classification in _EXECUTION_INTEGRITY_CLASSES:
        return "integrity"
    if verifier_failure_class == "scientific_failure":
        return "scientific"
    if verifier_failure_class == "integrity_failure":
        return "integrity"
    if verifier_failure_class == "contract_failure":
        return "contract"
    if mission_success is True:
        return "success"
    return "unclassified"


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError(f"JSON object required: {path}")
    return value


def _property_rows(grade: dict[str, Any]) -> dict[str, Any]:
    points = (grade.get("diagnostics") or {}).get("property_points") or {}
    return {
        str(row["requirement_id"]): {
            "passed": bool(row["passed"]),
            "points": points.get(str(row["requirement_id"])),
            "stage": row.get("stage"),
            "observed": row.get("observed"),
            "consequence": row.get("consequence"),
            "remedy": row.get("remedy"),
            "authoritative_evidence": row.get("evidence") or [],
        }
        for row in grade.get("requirements") or []
        if isinstance(row, dict) and row.get("requirement_id")
    }


def _model_row(root: Path, summary_path: str, manual: dict[str, Any] | None) -> dict[str, Any]:
    summary = _read(root / summary_path)
    grade = summary.get("diagnostic_grade") or {}
    lifecycle = summary.get("authoritative_lifecycle") or {}
    submitted = bool(lifecycle.get("submission_accepted"))
    submission = summary.get("submission") or {}
    followup = submission.get("followup_plan") or {}
    final = submission.get("final_submission") or {}
    properties = _property_rows(grade) if submitted else {}
    first = grade.get("first_decision_critical_failure") if submitted else None
    execution_classification = summary.get("classification")
    verifier_failure_class = grade.get("failure_class") if submitted else None
    taxonomy_bucket = execution_taxonomy_bucket(
        execution_classification,
        verifier_failure_class,
        grade.get("complete_mission_success") if submitted else None,
    )
    return {
        "model_id": summary.get("model_id"),
        "technical_reliability": {
            "identity_passed": bool((summary.get("provider_identity") or {}).get("compatible")),
            "replay_status": (summary.get("trajectory_replay") or {}).get("status"),
            "grader_status": (summary.get("grader_assessment") or {}).get("status"),
            "reliability_score": summary.get("reliability_score"),
        },
        "strict_mission_success": grade.get("complete_mission_success") if submitted else None,
        "partial_scientific_quality": grade.get("partial_scientific_quality")
        if submitted
        else None,
        "scientific_properties": properties,
        "first_decision_critical_failure": first,
        "downstream_consequences": [
            row.get("consequence") for row in properties.values() if not row.get("passed")
        ],
        "purchased_resource": lifecycle.get("resource_purchased")
        or followup.get("chosen_resource"),
        "resource_use": (grade.get("diagnostics") or {}).get("resource") if submitted else None,
        "belief_change": final.get("belief_updates"),
        "final_decision": lifecycle.get("final_decision") or final.get("decision"),
        "claim_scope": final.get("claims"),
        "turns": lifecycle.get("turn_count"),
        "requests": lifecycle.get("provider_request_count"),
        "checkpointed_cost_usd": lifecycle.get("checkpointed_spend_usd"),
        "provider_ledger_cost_usd": lifecycle.get("final_provider_ledger_spend_usd"),
        "budget_enforcement_cost_usd": lifecycle.get("budget_enforcement_spend_usd"),
        "completion_state": lifecycle.get("completion_state"),
        "execution_classification": execution_classification,
        "verifier_failure_class": verifier_failure_class,
        "taxonomy_bucket": taxonomy_bucket,
        "manual_forensic_adjudication": manual,
        "summary_path": summary_path,
    }


def build_report(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    release = read_rc5_freeze(root)
    state = _read(root / STATE_PATH)
    manual_path = root / MANUAL_ADJUDICATIONS_PATH
    manual = _read(manual_path).get("models", {}) if manual_path.is_file() else {}
    rows = [
        _model_row(
            root,
            path,
            manual.get(str(_read(root / path).get("model_id"))),
        )
        for path in state.get("summary_paths") or []
    ]
    submitted = [row for row in rows if row["strict_mission_success"] is not None]
    scores = [float(row["partial_scientific_quality"]) for row in submitted]
    failures = [
        (row.get("first_decision_critical_failure") or {}).get("requirement_id")
        for row in submitted
        if row.get("strict_mission_success") is False
    ]
    concentration = max(
        (failures.count(item) / len(failures) for item in set(failures)), default=None
    )
    clean_rows = [
        row
        for row in rows
        if row["execution_classification"]
        not in {"provider_adapter_failure", "provider_identity_failure", "infrastructure_failure"}
    ]
    return {
        "schema_version": "uc-bench-case1-pilot-v1-rc5-report-1",
        "scope": "single-attempt five-model Case 1 pilot; not a stable ranking",
        "release_digest": release["closure"]["aggregate_digest"],
        "rc4_official_score_preserved": 22.0,
        "rc4_score_interpretation": "archived verifier diagnostic, not model performance",
        "state_status": state.get("status"),
        "models": rows,
        "descriptive_summary": {
            "mission_pass_count": sum(row["strict_mission_success"] is True for row in submitted),
            "submitted_scientific_cell_count": len(submitted),
            "excluded_or_unsubmitted_cell_count": len(rows) - len(submitted),
            "mean_partial_scientific_quality": sum(scores) / len(scores) if scores else None,
            "scientific_spend_usd": state.get("scientific_spend_usd"),
            "first_failure_concentration": concentration,
        },
        "construct_interpretation": {
            "ceiling_warning": len(clean_rows) == 5
            and all(row["strict_mission_success"] is True for row in clean_rows),
            "genuine_scientific_separation": len(set(scores)) > 1 if len(scores) > 1 else False,
            "concentrated_failure_on_one_step": concentration is not None and concentration > 0.5,
            "artificial_contract_floor": any(
                (row.get("manual_forensic_adjudication") or {}).get("artificial_contract_failure")
                for row in rows
            ),
            "insufficient_evidence": len(rows) < 5,
        },
        "failure_taxonomy": {
            bucket: [row["model_id"] for row in rows if row["taxonomy_bucket"] == bucket]
            for bucket in (
                "success",
                "scientific",
                "integrity",
                "contract",
                "model_completion",
                "provider",
                "infrastructure",
                "unclassified",
            )
        },
        "excluded_models": state.get("excluded_models") or [],
        "global_stop_faults": state.get("global_stop_faults") or [],
        "case2_requests": state.get("case2_requests"),
        "other_case_requests": state.get("other_case_requests"),
        "sol_requests": state.get("sol_requests"),
        "astra_requests": state.get("astra_requests"),
        "stable_ranking_claim_allowed": False,
    }


def write_report(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    value = build_report(root)
    _write_json(root / REPORT_PATH, value, secret="")
    return value


__all__ = [
    "MANUAL_ADJUDICATIONS_PATH",
    "REPORT_PATH",
    "build_report",
    "execution_taxonomy_bucket",
    "write_report",
]

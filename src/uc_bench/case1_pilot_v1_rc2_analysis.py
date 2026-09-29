"""Deterministic reporting for the five-cell RC2 Case 1 pilot."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from uc_bench.case1_pilot_v1_rc2_execution import STATE_PATH
from uc_bench.errors import ConfigurationError
from uc_bench.model_runner import _write_json

REPORT_PATH = Path("artifacts/uc_bench_case1_pilot_v1_rc2/science/pilot_report.json")


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError(f"Expected JSON object: {path}")
    return value


def _event_resource(summary: dict[str, Any]) -> str | None:
    events = ((summary.get("submission") or {}).get("event_log") or [])
    for row in events:
        if isinstance(row, dict) and row.get("event") == "purchase_resource":
            return str(row.get("resource_id"))
    final = ((summary.get("submission") or {}).get("checkpoints") or {}).get("C5") or {}
    assessment = final.get("resource_assessment") or {}
    return str(assessment.get("resource_id")) if assessment.get("resource_id") else None


def _model_row(root: Path, summary_path: str, attestation_path: str) -> dict[str, Any]:
    summary = _read(root / summary_path)
    attestation = _read(root / attestation_path)
    grade = summary.get("diagnostic_grade") or {}
    requirements = {
        str(row.get("requirement_id")): bool(row.get("passed"))
        for row in grade.get("requirements") or []
        if isinstance(row, dict) and row.get("requirement_id")
    }
    submission = summary.get("submission") or {}
    checkpoints = submission.get("checkpoints") or {}
    followup = checkpoints.get("C4") or {}
    final = checkpoints.get("C5") or {}
    belief_updates = final.get("belief_updates") or []
    return {
        "model_id": summary.get("model_id"),
        "technical_reliability": {
            "identity_passed": bool((attestation.get("identity") or {}).get("compatible")),
            "trajectory_replay_passed": bool(
                (summary.get("trajectory_persistence") or {}).get("passed")
            ),
            "usable_provider_response_count": summary.get("usable_provider_response_count"),
            "reliability_score": summary.get("reliability_score"),
        },
        "mission_success": summary.get("complete_mission_success"),
        "partial_scientific_quality": summary.get("partial_scientific_quality"),
        "scientific_properties": requirements,
        "first_decision_critical_failure": grade.get("first_decision_critical_failure"),
        "downstream_consequences": grade.get("downstream_consequences") or [],
        "purchased_resource": _event_resource(summary),
        "resource_question": followup.get("decision_question_type"),
        "resource_useful": ((grade.get("diagnostics") or {}).get("resource") or {}).get("used"),
        "belief_before": final.get("beliefs_before"),
        "belief_updates": belief_updates,
        "final_decision": final.get("decision"),
        "supported_claim_ids": final.get("supported_claim_ids"),
        "prohibited_claim_ids": final.get("prohibited_claim_ids"),
        "turns": summary.get("turn_count"),
        "requests": summary.get("provider_request_count"),
        "cost_usd": summary.get("cumulative_reported_cost_usd"),
        "completion_status": summary.get("stop_condition"),
        "failure_classification": summary.get("classification"),
        "summary_path": summary_path,
        "identity_attestation_path": attestation_path,
    }


def build_report(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    state = _read(root / STATE_PATH)
    if len(state.get("summary_paths") or []) != len(state.get("attestation_paths") or []):
        raise ConfigurationError("Summary and identity-attestation counts differ")
    rows = [
        _model_row(root, summary, attestation)
        for summary, attestation in zip(
            state.get("summary_paths") or [],
            state.get("attestation_paths") or [],
            strict=True,
        )
    ]
    passes = [row for row in rows if row["mission_success"] is True]
    scores = [
        float(row["partial_scientific_quality"])
        for row in rows
        if row["partial_scientific_quality"] is not None
    ]
    return {
        "schema_version": "uc-bench-case1-pilot-v1-rc2-report-1",
        "release_id": "uc-bench-case1-pilot-v1-rc2",
        "scope": "single-attempt five-model Case 1 pilot; not a stable ranking",
        "state_status": state.get("status"),
        "models": rows,
        "aggregate_descriptive_only": {
            "mission_pass_count": len(passes),
            "scientifically_scored_count": len(scores),
            "mean_partial_scientific_quality": sum(scores) / len(scores) if scores else None,
            "scientific_spend_usd": state.get("scientific_spend_usd"),
        },
        "excluded_models": state.get("excluded_models") or [],
        "global_stop_faults": state.get("global_stop_faults") or [],
        "manual_adjudication_required_before_capability_claims": True,
        "stable_ranking_claim_allowed": False,
        "case2_requests": state.get("case2_requests"),
        "other_case_requests": state.get("other_case_requests"),
        "sol_requests": state.get("sol_requests"),
        "astra_requests": state.get("astra_requests"),
    }


def write_report(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    value = build_report(root)
    _write_json(root / REPORT_PATH, value, secret="")
    return value


__all__ = ["REPORT_PATH", "build_report", "write_report"]

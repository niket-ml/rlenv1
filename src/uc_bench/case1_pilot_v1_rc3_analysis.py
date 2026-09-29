"""Deterministic and manually adjudicated reporting for the RC3 Case 1 pilot."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from uc_bench.case1_pilot_v1_rc3_execution import STATE_PATH
from uc_bench.errors import ConfigurationError
from uc_bench.model_runner import _write_json

REPORT_PATH = Path("artifacts/uc_bench_case1_pilot_v1_rc3/science/pilot_report.json")
MANUAL_ADJUDICATIONS_PATH = Path(
    "artifacts/uc_bench_case1_pilot_v1_rc3/science/manual_adjudications.json"
)


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError(f"Expected JSON object: {path}")
    return value


def _first_failure(grade: dict[str, Any]) -> tuple[Any, list[Any]]:
    name = grade.get("first_decision_critical_failure")
    if not name:
        return None, []
    for row in grade.get("requirements") or []:
        if row.get("requirement_id") == name:
            return name, [row.get("consequence")]
    return name, []


def _model_row(
    root: Path,
    summary_path: str,
    attestation_path: str,
    manual: dict[str, Any] | None,
) -> dict[str, Any]:
    summary = _read(root / summary_path)
    attestation = _read(root / attestation_path)
    grade = summary.get("diagnostic_grade") or {}
    properties = {
        str(row.get("requirement_id")): {
            "passed": bool(row.get("passed")),
            "stage": row.get("stage"),
            "consequence": row.get("consequence"),
            "remedy": row.get("remedy"),
            "evidence": row.get("evidence") or [],
        }
        for row in grade.get("requirements") or []
        if isinstance(row, dict) and row.get("requirement_id")
    }
    first, consequences = _first_failure(grade)
    checkpoints = (summary.get("submission") or {}).get("checkpoints") or {}
    followup = checkpoints.get("followup_plan") or {}
    final = checkpoints.get("final_submission") or {}
    if not followup:
        followup = checkpoints.get("C4") or {}
    if not final:
        final = checkpoints.get("C5") or {}
    resource = final.get("resource_assessment") or {}
    return {
        "model_id": summary.get("model_id"),
        "technical_reliability": {
            "identity_passed": bool((attestation.get("identity") or {}).get("compatible")),
            "replay_status": (summary.get("trajectory_replay") or {}).get("status"),
            "grader_status": (summary.get("grader_assessment") or {}).get("status"),
            "reliability_score": summary.get("reliability_score"),
        },
        "mission_success": summary.get("complete_mission_success"),
        "partial_scientific_quality": summary.get("partial_scientific_quality"),
        "scientific_properties": properties,
        "first_decision_critical_failure": first,
        "downstream_consequences": consequences,
        "evidence_purchase": resource.get("resource_id") or followup.get("chosen_resource"),
        "evidence_use": (grade.get("diagnostics") or {}).get("resource"),
        "belief_revision": final.get("belief_updates"),
        "final_decision": final.get("decision"),
        "claim_scope": final.get("claims"),
        "turns": summary.get("turn_count"),
        "requests": summary.get("provider_request_count"),
        "cost_usd": summary.get("cumulative_reported_cost_usd"),
        "completion_state": summary.get("stop_condition"),
        "failure_classification": summary.get("classification"),
        "scientific_base_release_id": summary.get("scientific_base_release_id"),
        "scientific_base_digest": summary.get("scientific_base_digest"),
        "execution_release_id": summary.get("execution_release_id"),
        "execution_release_digest": summary.get("execution_release_digest"),
        "manual_construct_validity_adjudication": manual,
        "summary_path": summary_path,
        "identity_attestation_path": attestation_path,
    }


def build_report(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    state = _read(root / STATE_PATH)
    manual_file = root / MANUAL_ADJUDICATIONS_PATH
    manual = _read(manual_file).get("models", {}) if manual_file.is_file() else {}
    summaries = state.get("summary_paths") or []
    attestations = state.get("attestation_paths") or []
    if len(summaries) != len(attestations):
        raise ConfigurationError("Summary and identity-attestation counts differ")
    rows = []
    for summary_path, attestation_path in zip(summaries, attestations, strict=True):
        model_id = _read(root / summary_path).get("model_id")
        rows.append(
            _model_row(
                root,
                summary_path,
                attestation_path,
                manual.get(str(model_id)),
            )
        )
    scores = [
        float(row["partial_scientific_quality"])
        for row in rows
        if row["partial_scientific_quality"] is not None
    ]
    passes = sum(row["mission_success"] is True for row in rows)
    return {
        "schema_version": "uc-bench-case1-pilot-v1-rc3-report-1",
        "scope": "single-attempt five-model Case 1 pilot; not a stable ranking",
        "state_status": state.get("status"),
        "models": rows,
        "descriptive_summary": {
            "mission_pass_count": passes,
            "scientific_cell_count": len(scores),
            "mean_partial_scientific_quality": sum(scores) / len(scores) if scores else None,
            "scientific_spend_usd": state.get("scientific_spend_usd"),
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
    "write_report",
]

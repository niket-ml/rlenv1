"""Deterministic RC4 Case-1 pilot reporting with explicit diagnostic separation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from uc_bench.case1_pilot_v1_rc4_execution import STATE_PATH
from uc_bench.errors import ConfigurationError
from uc_bench.model_runner import _write_json

REPORT_PATH = Path("artifacts/uc_bench_case1_pilot_v1_rc4/science/pilot_report.json")
MANUAL_ADJUDICATIONS_PATH = Path(
    "artifacts/uc_bench_case1_pilot_v1_rc4/science/manual_adjudications.json"
)


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError(f"Expected JSON object: {path}")
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


def _diagnostic_saved_work(run_root: Path, summary: dict[str, Any]) -> dict[str, Any]:
    latest_path = run_root / "host_trajectory/latest.json"
    latest = _read(latest_path) if latest_path.is_file() else {}
    state = (latest.get("environment") or {}).get("state") or {}
    files = sorted(
        path.relative_to(run_root / "workspace").as_posix()
        for path in (run_root / "workspace/work").rglob("*")
        if path.is_file()
    ) if (run_root / "workspace/work").is_dir() else []
    return {
        "headline_scientific_score_eligible": bool(
            summary.get("submission", {}).get("state", {}).get("completion_accepted")
        ),
        "phase_reached": state.get("phase"),
        "validation_committed": bool(state.get("validation_plan_hash")),
        "validation_revealed": state.get("phase")
        in {"revealed", "followup_committed", "purchased", "submitted"},
        "followup_committed": bool(state.get("followup_plan_hash")),
        "resource_purchased": state.get("selected_resource"),
        "saved_work_files": files,
        "first_completion_failure": summary.get("stop_condition") or summary.get("rollout_error"),
        "note": "Diagnostic lifecycle evidence only; it is not mixed into the official score.",
    }


def _model_row(
    root: Path, summary_path: str, manual: dict[str, Any] | None
) -> dict[str, Any]:
    summary = _read(root / summary_path)
    grade = summary.get("diagnostic_grade") or {}
    submitted = bool(
        (summary.get("submission") or {}).get("state", {}).get("completion_accepted")
    )
    checkpoints = (summary.get("submission") or {}).get("checkpoints") or {}
    followup = checkpoints.get("followup_plan") or checkpoints.get("C4") or {}
    final = checkpoints.get("final_submission") or checkpoints.get("C5") or {}
    resource = final.get("resource_assessment") or {}
    calculations = (grade.get("diagnostics") or {}).get("calculation_results") or {}
    run_root = (root / summary_path).parent
    return {
        "model_id": summary.get("model_id"),
        "technical_reliability": {
            "identity_passed": bool(
                (summary.get("provider_identity") or {}).get("compatible")
            ),
            "replay_status": (summary.get("trajectory_replay") or {}).get("status"),
            "grader_status": (summary.get("grader_assessment") or {}).get("status"),
            "reliability_score": summary.get("reliability_score"),
        },
        "submitted": submitted,
        "strict_mission_success": (
            summary.get("complete_mission_success") if submitted else None
        ),
        "official_partial_scientific_quality": (
            summary.get("partial_scientific_quality") if submitted else None
        ),
        "scientific_properties": _property_rows(grade) if submitted else {},
        "first_decision_critical_failure": (
            grade.get("first_decision_critical_failure") if submitted else None
        ),
        "downstream_consequences": [
            row["consequence"]
            for row in _property_rows(grade).values()
            if not row["passed"]
        ] if submitted else [],
        "verified_calculations": calculations if submitted else {},
        "evidence_purchase": resource.get("resource_id") or followup.get("chosen_resource"),
        "evidence_use": (grade.get("diagnostics") or {}).get("resource") if submitted else None,
        "belief_revision": final.get("belief_updates"),
        "final_action": final.get("decision"),
        "claim_scope": final.get("claims"),
        "turns": summary.get("turn_count"),
        "requests": summary.get("provider_request_count"),
        "cost_usd": summary.get("cumulative_reported_cost_usd"),
        "completion_state": summary.get("stop_condition"),
        "failure_classification": summary.get("classification"),
        "manual_construct_validity_adjudication": manual,
        "diagnostic_saved_work": _diagnostic_saved_work(run_root, summary),
        "summary_path": summary_path,
    }


def build_report(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    state = _read(root / STATE_PATH)
    manual_file = root / MANUAL_ADJUDICATIONS_PATH
    manual = _read(manual_file).get("models", {}) if manual_file.is_file() else {}
    rows = [
        _model_row(
            root,
            summary_path,
            manual.get(str(_read(root / summary_path).get("model_id"))),
        )
        for summary_path in state.get("summary_paths") or []
    ]
    submitted = [row for row in rows if row["submitted"]]
    scores = [float(row["official_partial_scientific_quality"]) for row in submitted]
    failures = {
        str(row["model_id"]): row["first_decision_critical_failure"] for row in submitted
    }
    first_steps = [
        (failure or {}).get("requirement_id")
        for failure in failures.values()
        if isinstance(failure, dict)
    ]
    concentration = max(
        (first_steps.count(step) / len(first_steps) for step in set(first_steps)),
        default=None,
    )
    return {
        "schema_version": "uc-bench-case1-pilot-v1-rc4-report-1",
        "scope": "single-attempt five-model Case 1 pilot; not a stable ranking",
        "state_status": state.get("status"),
        "models": rows,
        "descriptive_summary": {
            "mission_pass_count": sum(row["strict_mission_success"] is True for row in submitted),
            "submitted_scientific_cell_count": len(submitted),
            "unsubmitted_cell_count": len(rows) - len(submitted),
            "mean_partial_scientific_quality": sum(scores) / len(scores) if scores else None,
            "scientific_spend_usd": state.get("scientific_spend_usd"),
            "first_failure_concentration": concentration,
        },
        "construct_interpretation": {
            "ceiling_warning": bool(rows) and all(
                row["strict_mission_success"] is True for row in rows
            ),
            "genuine_scientific_separation": len(set(scores)) > 1 if scores else False,
            "concentrated_failure_on_one_step": concentration is not None and concentration > 0.5,
            "artificial_contract_floor": any(
                (row.get("manual_construct_validity_adjudication") or {}).get(
                    "artificial_contract_failure"
                )
                for row in rows
            ),
            "insufficient_evidence": len(rows) < 5,
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


__all__ = ["MANUAL_ADJUDICATIONS_PATH", "REPORT_PATH", "build_report", "write_report"]

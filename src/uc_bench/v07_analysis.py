"""Frozen, deterministic analysis for the bounded v0.7 development calibration."""

from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Any

CAPABILITY_BY_CHECKPOINT = {
    "C1": "data_integrity_and_analysis_unit",
    "C2": "prospective_validation_design",
    "C3": "quantitative_validity_and_leakage_containment",
    "C4": "diagnosis_and_value_of_information",
    "C5": "belief_revision_decision_and_claim_scope",
}


def _nested_first(value: Any, keys: set[str]) -> Any:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in keys and not isinstance(child, (dict, list)):
                return child
        for child in value.values():
            result = _nested_first(child, keys)
            if result is not None:
                return result
    elif isinstance(value, list):
        for child in value:
            result = _nested_first(child, keys)
            if result is not None:
                return result
    return None


def _valid(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if row.get("classification") == "valid_episode"]


def _model_rows(rows: list[dict[str, Any]], model_id: str) -> list[dict[str, Any]]:
    return [row for row in rows if row.get("model_id") == model_id]


def _scientific_failures(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for row in rows:
        grade = row.get("diagnostic_grade") or {}
        for checkpoint, properties in (grade.get("property_scores") or {}).items():
            for prop in properties or []:
                score = float(prop.get("score") or 0.0)
                if score >= 75:
                    continue
                failures.append(
                    {
                        "model_id": row.get("model_id"),
                        "condition_id": row.get("condition_id"),
                        "checkpoint": checkpoint,
                        "capability": CAPABILITY_BY_CHECKPOINT.get(checkpoint, checkpoint),
                        "property_id": prop.get("property_id"),
                        "score": score,
                        "trace_evidence": prop.get("observed"),
                        "professional_consequence": prop.get("consequence"),
                        "actionable_remedy": prop.get("remedy"),
                    }
                )
    return failures


def _meaningful_partial(model_rows: list[dict[str, Any]]) -> bool:
    scores = [
        float(row["diagnostic_grade"]["work_quality_score"])
        for row in model_rows
        if row.get("diagnostic_grade")
    ]
    checkpoint_scores = [
        float(value)
        for row in model_rows
        for value in (row.get("diagnostic_grade", {}).get("checkpoint_scores") or {}).values()
    ]
    return bool(scores) and any(10 < score < 95 for score in scores + checkpoint_scores)


def _sol_gate(rows: list[dict[str, Any]], manual_grader_wording_failure: bool) -> dict[str, Any]:
    model_id = "openai/gpt-5.6-sol"
    model_rows = _model_rows(rows, model_id)
    valid = _valid(model_rows)
    scores = [float(row["diagnostic_grade"]["work_quality_score"]) for row in valid]
    score_mean = mean(scores) if len(scores) == 5 else None
    missions = sum(bool(row["diagnostic_grade"]["full_mission_success"]) for row in valid)
    case1 = next((row for row in valid if row.get("condition_id") == "case_01"), None)
    harder = [row for row in valid if row.get("condition_id") != "case_01"]
    failures = _scientific_failures(valid)
    distinct = sorted({str(row["property_id"]) for row in failures})
    checks = {
        "five_valid_cells": len(valid) == 5,
        "mean_55_to_75": score_mean is not None and 55 <= score_mean <= 75,
        "mission_count_2_to_3": 2 <= missions <= 3,
        "easier_case_passed": bool(
            case1 and case1["diagnostic_grade"]["full_mission_success"]
        ),
        "harder_case_failed": any(
            not row["diagnostic_grade"]["full_mission_success"] for row in harder
        ),
        "three_distinct_scientific_failures": len(distinct) >= 3,
        "meaningful_partial_credit": _meaningful_partial(valid),
        "no_grader_wording_failure": not manual_grader_wording_failure,
        "no_provider_identity_or_integrity_failure": all(
            not any(
                request.get("identity_violations")
                for request in row.get("provider_requests") or []
            )
            and row.get("integrity", {}).get("start_state_untampered") is True
            and row.get("integrity", {}).get("commitment_immutable") is True
            for row in valid
        ),
    }
    hard_no_go_reasons: list[str] = []
    if score_mean is not None and score_mean > 75:
        hard_no_go_reasons.append("ceiling_failure_mean_above_75")
    if score_mean is not None and score_mean < 45:
        hard_no_go_reasons.append("floor_failure_mean_below_45")
    if missions >= 4:
        hard_no_go_reasons.append("ceiling_failure_four_or_five_missions")
    if len(valid) == 5 and missions <= 1:
        hard_no_go_reasons.append("floor_failure_zero_or_one_mission")
    failed = [name for name, passed in checks.items() if not passed]
    decision = "continue_to_gpt_5_2" if not failed else "no_go"
    return {
        "decision": decision,
        "checks": checks,
        "failed_checks": failed,
        "hard_no_go_reasons": hard_no_go_reasons,
        "valid_cell_count": len(valid),
        "mean_work_quality": score_mean,
        "full_missions": missions,
        "distinct_failure_properties": distinct,
        "manual_grader_wording_failure": manual_grader_wording_failure,
    }


def analyze_v07(
    rows: list[dict[str, Any]], *, manual_grader_wording_failure: bool = False
) -> dict[str, Any]:
    """Create all predeclared matrices without changing or reinterpreting scores."""

    model_ids = [
        model
        for model in ("openai/gpt-5.6-sol", "openai/gpt-5.2")
        if _model_rows(rows, model)
    ]
    valid = _valid(rows)
    milestone_matrix: dict[str, dict[str, float | None]] = {}
    capability_matrix: dict[str, dict[str, float | None]] = {}
    state_matrix: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    decision_rows: list[dict[str, Any]] = []
    resource_rows: list[dict[str, Any]] = []
    process_rows: list[dict[str, Any]] = []
    for model in model_ids:
        cells = _valid(_model_rows(rows, model))
        milestone_matrix[model] = {
            checkpoint: (
                round(
                    mean(
                        float(row["diagnostic_grade"]["checkpoint_scores"][checkpoint])
                        for row in cells
                    ),
                    6,
                )
                if cells
                else None
            )
            for checkpoint in CAPABILITY_BY_CHECKPOINT
        }
        capability_matrix[model] = {
            CAPABILITY_BY_CHECKPOINT[checkpoint]: value
            for checkpoint, value in milestone_matrix[model].items()
        }
    for row in rows:
        grade = row.get("diagnostic_grade") or {}
        model = str(row.get("model_id"))
        condition = str(row.get("condition_id"))
        state_matrix[model][condition] = {
            "work_quality_score": grade.get("work_quality_score"),
            "reliability_score": row.get("reliability_score"),
            "full_mission_success": grade.get("full_mission_success"),
            "first_substantive_divergence": grade.get("first_substantive_divergence"),
            "classification": row.get("classification"),
        }
        c5 = (row.get("submission", {}).get("checkpoints") or {}).get("C5") or {}
        decision_rows.append(
            {
                "model_id": model,
                "condition_id": condition,
                "initial_decision": _nested_first(
                    c5, {"initial_decision", "pre_followup_decision"}
                ),
                "final_decision": _nested_first(
                    c5, {"final_decision", "decision", "investment_decision"}
                ),
                "belief_direction": _nested_first(
                    c5, {"belief_direction", "belief_update", "posterior_direction"}
                ),
                "belief_revision_correct": "belief_revision_incorrect"
                not in (grade.get("mission_failures") or []),
            }
        )
        resource_rows.append(
            {
                "model_id": model,
                "condition_id": condition,
                "selected_resource": row.get("submission", {}).get("selected_resource"),
                "spent_units": row.get("submission", {}).get("spent_units"),
                "C4_score": (grade.get("checkpoint_scores") or {}).get("C4"),
                "C5_score": (grade.get("checkpoint_scores") or {}).get("C5"),
            }
        )
        process_rows.append(
            {
                "model_id": model,
                "condition_id": condition,
                "classification": row.get("classification"),
                "rollout_error": row.get("rollout_error"),
                "stop_condition": row.get("stop_condition"),
                "provider_request_count": row.get("provider_request_count"),
                "turn_count": row.get("turn_count"),
                "token_usage": row.get("token_usage"),
                "cost_usd": row.get("cumulative_reported_cost_usd"),
                "trace_paths": row.get("complete_tool_history_paths"),
            }
        )
    sol_gate = _sol_gate(rows, manual_grader_wording_failure)
    failures = _scientific_failures(valid)
    failure_by_model_capability: dict[str, dict[str, int]] = {}
    for model in model_ids:
        counts: dict[str, int] = defaultdict(int)
        for failure in failures:
            if failure["model_id"] == model:
                counts[str(failure["capability"])] += 1
        failure_by_model_capability[model] = dict(sorted(counts.items()))

    gap_diagnostics: dict[str, Any] = {"available": False}
    two_model_checks: dict[str, bool] = {}
    if set(model_ids) == {"openai/gpt-5.6-sol", "openai/gpt-5.2"}:
        sol = "openai/gpt-5.6-sol"
        older = "openai/gpt-5.2"
        checkpoint_gaps = {
            checkpoint: abs(
                float(milestone_matrix[sol][checkpoint])
                - float(milestone_matrix[older][checkpoint])
            )
            for checkpoint in CAPABILITY_BY_CHECKPOINT
        }
        total_gap = sum(checkpoint_gaps.values())
        shares = {
            key: (value / total_gap if total_gap else 0.0)
            for key, value in checkpoint_gaps.items()
        }
        scenario_gaps = {}
        for condition in state_matrix[sol]:
            if condition in state_matrix[older]:
                scenario_gaps[condition] = abs(
                    float(state_matrix[sol][condition]["work_quality_score"])
                    - float(state_matrix[older][condition]["work_quality_score"])
                )
        scenario_total = sum(scenario_gaps.values())
        scenario_shares = {
            key: (value / scenario_total if scenario_total else 0.0)
            for key, value in scenario_gaps.items()
        }
        mission_counts = {
            model: sum(
                bool(row["diagnostic_grade"]["full_mission_success"])
                for row in _valid(_model_rows(rows, model))
            )
            for model in model_ids
        }
        mission_patterns = {
            model: {
                row["condition_id"]: bool(row["diagnostic_grade"]["full_mission_success"])
                for row in _valid(_model_rows(rows, model))
            }
            for model in model_ids
        }
        meaningful_difference = mission_patterns[sol] != mission_patterns[older] or any(
            value >= 5 for value in checkpoint_gaps.values()
        )
        two_model_checks = {
            "ten_valid_cells": len(valid) == 10,
            "no_universal_mission_failure": all(value >= 1 for value in mission_counts.values()),
            "meaningful_model_difference": meaningful_difference,
            "checkpoint_gap_concentration_at_most_30_percent": (
                bool(shares) and max(shares.values()) <= 0.30
            ),
            "meaningful_partial_credit": all(
                _meaningful_partial(_valid(_model_rows(rows, model))) for model in model_ids
            ),
            "no_process_failure_scored_as_science": all(
                row.get("classification") == "valid_episode" for row in rows
            ),
        }
        gap_diagnostics = {
            "available": True,
            "checkpoint_absolute_gaps": checkpoint_gaps,
            "checkpoint_gap_shares": shares,
            "maximum_checkpoint_gap_share": max(shares.values()) if shares else None,
            "scenario_absolute_gaps": scenario_gaps,
            "scenario_gap_shares": scenario_shares,
            "maximum_scenario_gap_share": (
                max(scenario_shares.values()) if scenario_shares else None
            ),
            "mission_counts": mission_counts,
        }

    complete = len(rows) == 10
    if not complete:
        overall = sol_gate["decision"]
    elif sol_gate["decision"] != "continue_to_gpt_5_2":
        overall = "no_go"
    else:
        overall = "go_internal_calibration_only" if all(two_model_checks.values()) else "no_go"
    score_cost = {
        model: {
            "mean_work_quality": (
                round(
                    mean(
                        float(row["diagnostic_grade"]["work_quality_score"])
                        for row in _valid(_model_rows(rows, model))
                    ),
                    6,
                )
                if _valid(_model_rows(rows, model))
                else None
            ),
            "total_cost_usd": round(
                sum(
                    float(row.get("cumulative_reported_cost_usd") or 0.0)
                    for row in _model_rows(rows, model)
                ),
                8,
            ),
        }
        for model in model_ids
    }
    return {
        "schema_version": "0.7-analysis-1",
        "scope": "controlled internal development calibration; one seed; not a stable ranking",
        "episode_count": len(rows),
        "valid_episode_count": len(valid),
        "model_by_milestone": milestone_matrix,
        "model_by_capability": capability_matrix,
        "model_by_controlled_failure_state": dict(state_matrix),
        "initial_vs_final_decisions": decision_rows,
        "resource_choices_and_intervention_effects": resource_rows,
        "belief_revision_failures": [
            row for row in decision_rows if not row["belief_revision_correct"]
        ],
        "scientific_failure_evidence": failures,
        "model_by_failure_capability": failure_by_model_capability,
        "process_tool_timeout_infrastructure": process_rows,
        "ceiling_floor_and_family_concentration": gap_diagnostics,
        "sol_gate": sol_gate,
        "two_model_gate": {
            "checks": two_model_checks,
            "failed_checks": [name for name, passed in two_model_checks.items() if not passed],
        },
        "score_cost_frontier": score_cost,
        "representative_replay_traces": [
            {
                "model_id": row.get("model_id"),
                "condition_id": row.get("condition_id"),
                "paths": row.get("complete_tool_history_paths"),
            }
            for row in rows
        ],
        "go_no_go": overall,
        "claim_limits": [
            "One seed does not establish a stable model ranking.",
            "Internally authored controls are not independent external expert validation.",
            "Observed repeated behaviour can support capability diagnosis; "
            "training-cause claims require paired intervention evidence.",
            "The authentic GEO anchor is separate from these controlled states.",
            "No held-out state or Astra model was exposed.",
        ],
    }

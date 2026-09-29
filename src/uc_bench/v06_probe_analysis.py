"""Deterministic, predeclared analysis for the v0.6 development ceiling probe.

The ceiling construct is scientific artifact quality among accepted submissions.
Completion reliability is reported separately and can never manufacture headroom.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from pathlib import Path
from statistics import mean
from typing import Any

from uc_bench.hard_suite_v06 import V06_CAPABILITY_MAP

VALID_EPISODE = "valid_episode"
EXCLUDED_INFRASTRUCTURE = "infrastructure_failure"


def _average(values: Iterable[float]) -> float | None:
    rows = list(values)
    return None if not rows else round(mean(rows), 6)


def _loss_share(losses: Mapping[str, float]) -> dict[str, float]:
    total = sum(max(0.0, value) for value in losses.values())
    if total <= 0:
        return {name: 0.0 for name in losses}
    return {
        name: round(max(0.0, value) / total, 6)
        for name, value in losses.items()
    }


def ceiling_band(score: float | None, gates: Mapping[str, Any]) -> str:
    """Classify a strongest-model scientific mean without changing a score."""

    if score is None:
        return "not_interpretable"
    desired_low, desired_high = gates["strongest_model_desired_range_inclusive"]
    acceptable = gates["strongest_model_acceptable_range"]
    insufficient = gates["strongest_model_insufficient_headroom_range"]
    if score < float(desired_low):
        return "overhard_no_go"
    if score <= float(desired_high):
        return "desired_60_to_70"
    if score <= float(acceptable["upper_inclusive"]):
        return "acceptable_70_to_75"
    if score <= float(insufficient["upper_inclusive"]):
        return "insufficient_headroom_75_to_80"
    return "ceiling_no_go_above_80"


def _latest_cells(
    rows: Iterable[Mapping[str, Any]],
    *,
    model_ids: list[str],
    scenario_ids: list[str],
) -> dict[tuple[str, str], dict[str, Any]]:
    expected = {(model, scenario) for model in model_ids for scenario in scenario_ids}
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in rows:
        row = dict(raw)
        key = (str(row.get("model_id")), str(row.get("scenario_id")))
        if key not in expected:
            continue
        prior = result.get(key)
        if prior is None or int(row.get("execution_attempt", 0)) >= int(
            prior.get("execution_attempt", 0)
        ):
            result[key] = row
    return result


def _accepted(row: Mapping[str, Any]) -> bool:
    diagnostic = row.get("diagnostic_grade") or {}
    return (
        row.get("classification") == VALID_EPISODE
        and diagnostic.get("completion_accepted") is True
    )


def _scientific_score(row: Mapping[str, Any]) -> float | None:
    if not _accepted(row):
        return None
    value = (row.get("diagnostic_grade") or {}).get(
        "coverage_adjusted_scientific_score"
    )
    return float(value) if isinstance(value, int | float) else None


def _trace_evidence(
    row: Mapping[str, Any],
    annotation: Mapping[str, Any],
    *,
    project_root: Path | None,
) -> dict[str, Any]:
    workspace = str(row.get("workspace_directory") or "")
    artifact = str(annotation.get("artifact_path") or "")
    relative = f"{workspace}/{artifact}" if workspace and artifact else ""
    exists = None
    if project_root is not None and relative:
        exists = (project_root.resolve() / relative).is_file()
    return {
        "model_id": str(row.get("model_id")),
        "scenario_id": str(row.get("scenario_id")),
        "run_id": row.get("run_id"),
        "artifact_id": annotation.get("artifact"),
        "artifact_path": artifact,
        "workspace_artifact_path": relative,
        "workspace_artifact_exists": exists,
        "artifact_score": annotation.get("artifact_score"),
        "artifact_state": annotation.get("artifact_state"),
        "properties_evaluated": annotation.get("properties_evaluated") or [],
        "professional_consequence": annotation.get("professional_consequence"),
        "paired_remedy": annotation.get("paired_remedy"),
        "remedy_intervention_class": annotation.get(
            "remedy_intervention_class"
        ),
        "run_summary_path": (
            f"{row.get('run_directory')}/run_summary.json"
            if row.get("run_directory")
            else ""
        ),
    }


def analyze_v06_probe(
    rows: Iterable[Mapping[str, Any]],
    *,
    config: Mapping[str, Any],
    model_ids: list[str],
    scenario_ids: list[str],
    project_root: Path | None = None,
) -> dict[str, Any]:
    """Apply the frozen ceiling and concentration rules to development rows."""

    gates = config["development_acceptance_gates"]
    deduction_contract = config["deduction_validity_contract"]
    cells = _latest_cells(rows, model_ids=model_ids, scenario_ids=scenario_ids)
    expected = {(model, scenario) for model in model_ids for scenario in scenario_ids}
    missing = sorted(f"{model}::{scenario}" for model, scenario in expected - set(cells))

    model_results: dict[str, Any] = {}
    for model in model_ids:
        model_rows = [
            cells[(model, scenario)]
            for scenario in scenario_ids
            if (model, scenario) in cells
        ]
        accepted_rows = [row for row in model_rows if _accepted(row)]
        science = [
            score
            for score in (_scientific_score(row) for row in accepted_rows)
            if score is not None
        ]
        reliability = [
            float(row.get("score") or 0.0)
            for row in model_rows
            if row.get("classification") != EXCLUDED_INFRASTRUCTURE
        ]
        input_tokens = sum(
            int(
                (row.get("token_usage") or {}).get("input_tokens")
                or (row.get("token_usage") or {}).get("prompt_tokens")
                or 0
            )
            for row in model_rows
        )
        output_tokens = sum(
            int(
                (row.get("token_usage") or {}).get("output_tokens")
                or (row.get("token_usage") or {}).get("completion_tokens")
                or 0
            )
            for row in model_rows
        )
        model_results[model] = {
            "expected_episode_count": len(scenario_ids),
            "observed_episode_count": len(model_rows),
            "accepted_submission_count": len(accepted_rows),
            "excluded_infrastructure_count": sum(
                row.get("classification") == EXCLUDED_INFRASTRUCTURE
                for row in model_rows
            ),
            "classification_counts": dict(
                sorted(Counter(str(row.get("classification")) for row in model_rows).items())
            ),
            "mean_scientific_score_accepted_submissions": _average(science),
            "mean_reliability_score_non_infrastructure_attempts": _average(reliability),
            "scientific_episode_scores": science,
            "reported_cost_usd": round(
                sum(float(row.get("reported_cost_usd") or 0.0) for row in model_rows),
                8,
            ),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "turns": sum(int(row.get("turn_count") or 0) for row in model_rows),
        }

    all_valid = not missing and all(
        _accepted(cells[cell]) and _scientific_score(cells[cell]) is not None
        for cell in expected
    )
    scored_models = [
        (model, result["mean_scientific_score_accepted_submissions"])
        for model, result in model_results.items()
        if result["mean_scientific_score_accepted_submissions"] is not None
    ]
    strongest_model, strongest_score = (
        max(scored_models, key=lambda item: (float(item[1]), item[0]))
        if scored_models
        else (None, None)
    )
    strongest_rows = (
        [
            cells[(str(strongest_model), scenario)]
            for scenario in scenario_ids
            if (str(strongest_model), scenario) in cells
            and _accepted(cells[(str(strongest_model), scenario)])
        ]
        if strongest_model is not None
        else []
    )

    capability_values: dict[str, list[float]] = defaultdict(list)
    family_values: dict[str, list[float]] = defaultdict(list)
    artifact_values: dict[str, list[float]] = defaultdict(list)
    trace_evidence: list[dict[str, Any]] = []
    evidence_violations: list[str] = []
    required_evidence = list(deduction_contract["required_deterministic_evidence"])
    threshold = float(deduction_contract["material_artifact_threshold_below"])
    material_artifact_ids: set[str] = set()
    for row in strongest_rows:
        diagnostic = row["diagnostic_grade"]
        for name, value in (diagnostic.get("capability_scores") or {}).items():
            capability_values[str(name)].append(float(value))
        for name, value in (diagnostic.get("family_scores") or {}).items():
            family_values[str(name)].append(float(value))
        for name, value in (diagnostic.get("artifact_scores") or {}).items():
            artifact_values[str(name)].append(float(value))
        for raw_annotation in diagnostic.get("scientific_failure_annotations") or []:
            annotation = dict(raw_annotation)
            score = annotation.get("artifact_score")
            if not isinstance(score, int | float) or float(score) >= threshold:
                continue
            evidence = _trace_evidence(row, annotation, project_root=project_root)
            trace_evidence.append(evidence)
            artifact_id = str(annotation.get("artifact"))
            material_artifact_ids.add(artifact_id)
            absent = [
                name
                for name in required_evidence
                if name not in annotation
                or annotation[name] is None
                or annotation[name] == ""
            ]
            if absent:
                evidence_violations.append(
                    f"{row.get('model_id')}::{row.get('scenario_id')}::{artifact_id}:"
                    f"missing_{','.join(absent)}"
                )
            if evidence["workspace_artifact_exists"] is False:
                evidence_violations.append(
                    f"{row.get('model_id')}::{row.get('scenario_id')}::{artifact_id}:"
                    "artifact_trace_missing"
                )

    capability_means = {
        name: float(_average(capability_values.get(name, [])) or 0.0)
        for name in V06_CAPABILITY_MAP
    }
    capability_losses = {
        name: round(100.0 - score, 6) for name, score in capability_means.items()
    }
    minimum_capability_loss = float(gates["minimum_material_capability_loss_points"])
    material_capabilities = [
        name
        for name, loss in capability_losses.items()
        if loss >= minimum_capability_loss
        and material_artifact_ids.intersection(V06_CAPABILITY_MAP[name])
    ]

    family_means = {
        name: float(_average(values) or 0.0) for name, values in family_values.items()
    }
    family_losses = {name: round(100.0 - value, 6) for name, value in family_means.items()}
    family_shares = _loss_share(family_losses)
    max_family = max(family_shares, key=family_shares.get) if family_shares else None
    max_family_share = family_shares.get(max_family, 0.0) if max_family else 0.0

    scenario_losses: dict[str, float] = {}
    for scenario in scenario_ids:
        row = cells.get((str(strongest_model), scenario)) if strongest_model else None
        score = _scientific_score(row) if row else None
        if score is not None:
            scenario_losses[scenario] = round(100.0 - score, 6)
    scenario_shares = _loss_share(scenario_losses)
    max_scenario = max(scenario_shares, key=scenario_shares.get) if scenario_shares else None
    max_scenario_share = scenario_shares.get(max_scenario, 0.0) if max_scenario else 0.0
    scenario_evaluable = len(scenario_ids) >= 6 and len(scenario_losses) == len(scenario_ids)

    strongest_episode_scores = [
        score
        for score in (_scientific_score(row) for row in strongest_rows)
        if score is not None
    ]
    partial_episode_fraction = (
        sum(0.0 < score < 95.0 for score in strongest_episode_scores)
        / len(strongest_episode_scores)
        if strongest_episode_scores
        else 0.0
    )
    partial_artifacts = sorted(
        artifact
        for artifact, values in artifact_values.items()
        if any(0.0 < score < 90.0 for score in values)
    )
    partial_rules = gates["meaningful_partial_credit"]
    partial_pass = (
        partial_episode_fraction
        >= float(partial_rules["minimum_fraction_of_episodes_strictly_between_zero_and_95"])
        and len(partial_artifacts)
        >= int(partial_rules["minimum_material_artifacts_strictly_between_zero_and_90"])
    )
    ceiling_fraction = (
        sum(score >= 95.0 for score in strongest_episode_scores)
        / len(strongest_episode_scores)
        if strongest_episode_scores
        else 0.0
    )
    band = ceiling_band(strongest_score if all_valid else None, gates)

    gate_results = {
        "valid_submission_in_every_cell": all_valid,
        "strongest_model_ceiling_band": band,
        "ceiling_band_allows_continuation": band
        in {"desired_60_to_70", "acceptable_70_to_75"},
        "maximum_ceiling_fraction": ceiling_fraction
        <= float(gates["maximum_ceiling_fraction"]),
        "minimum_three_scientific_capabilities_with_material_loss": len(
            material_capabilities
        )
        >= int(gates["minimum_scientific_capabilities_with_material_loss"]),
        "maximum_single_artifact_family_gap_share": max_family_share
        <= float(gates["maximum_single_family_gap_share"]),
        "maximum_single_scenario_gap_share": (
            max_scenario_share <= float(gates["maximum_single_scenario_gap_share"])
            if scenario_evaluable
            else None
        ),
        "meaningful_partial_credit": partial_pass,
        "material_deductions_have_trace_and_actionable_remedy": not evidence_violations,
    }
    sentinel_gate_names = [
        "valid_submission_in_every_cell",
        "ceiling_band_allows_continuation",
        "maximum_ceiling_fraction",
        "minimum_three_scientific_capabilities_with_material_loss",
        "maximum_single_artifact_family_gap_share",
        "meaningful_partial_credit",
        "material_deductions_have_trace_and_actionable_remedy",
    ]
    failures = [name for name in sentinel_gate_names if gate_results[name] is not True]
    decision = "continue" if not failures else "stop"
    if missing:
        decision = "incomplete"

    return {
        "schema_version": "0.6-probe-analysis-1",
        "status": "controlled_internal_development_not_ranking",
        "ranking_claim_allowed": False,
        "scientific_ceiling_metric": gates["scientific_ceiling_metric"],
        "completion_reliability_reported_separately": True,
        "expected_cell_count": len(expected),
        "observed_cell_count": len(cells),
        "missing_cells": missing,
        "models": model_results,
        "strongest_model": strongest_model,
        "strongest_model_scientific_mean": strongest_score,
        "strongest_model_ceiling_band": band,
        "strongest_model_ceiling_fraction": round(ceiling_fraction, 6),
        "capability_diagnostics": {
            "mean_scores": capability_means,
            "loss_points": capability_losses,
            "material_loss_threshold_points": minimum_capability_loss,
            "material_capabilities": material_capabilities,
            "material_capability_count": len(material_capabilities),
            "passes_minimum_three": gate_results[
                "minimum_three_scientific_capabilities_with_material_loss"
            ],
        },
        "artifact_family_concentration": {
            "mean_scores": family_means,
            "loss_points": family_losses,
            "gap_shares": family_shares,
            "largest_contributor": max_family,
            "largest_gap_share": round(max_family_share, 6),
            "maximum_allowed": gates["maximum_single_family_gap_share"],
            "passes": gate_results["maximum_single_artifact_family_gap_share"],
        },
        "scenario_concentration": {
            "loss_points": scenario_losses,
            "observed_gap_shares": scenario_shares,
            "largest_contributor": max_scenario,
            "largest_observed_gap_share": round(max_scenario_share, 6),
            "maximum_allowed": gates["maximum_single_scenario_gap_share"],
            "evaluable": scenario_evaluable,
            "passes": gate_results["maximum_single_scenario_gap_share"],
            "interpretation": (
                "evaluated_across_all_six_development_states"
                if scenario_evaluable
                else "not_a_sentinel_gate; two states cannot satisfy a 30_percent_loss_share_cap"
            ),
        },
        "meaningful_partial_credit": {
            "episode_fraction_strictly_between_zero_and_95": round(
                partial_episode_fraction, 6
            ),
            "artifacts_strictly_between_zero_and_90": partial_artifacts,
            "artifact_count": len(partial_artifacts),
            "passes": partial_pass,
        },
        "material_deduction_evidence": trace_evidence,
        "deduction_evidence_violations": sorted(evidence_violations),
        "gate_results": gate_results,
        "sentinel_decision": {
            "decision": decision,
            "reasons": failures or ["all_predeclared_sentinel_gates_passed"],
            "scenario_concentration_deferred_to_full_six_state_matrix": not scenario_evaluable,
            "ranking_claim_allowed": False,
        },
    }

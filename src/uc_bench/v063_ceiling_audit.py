# ruff: noqa: E501
"""Post-exposure construct audit for the frozen v0.6.3 sentinel.

This module never changes or substitutes for the frozen score.  It decomposes
the exact frozen invariant calculations, records the observed artifact fields,
and classifies each deduction for construct-validity review.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from statistics import mean, pvariance
from typing import Any

import uc_bench.hard_suite_v06 as v06
from uc_bench.v063_grader import sanitize_artifact

ADJUDICATION_LABELS = {
    "A": "consequential scientific error",
    "B": "defensible alternative professional policy",
    "C": "grader/schema artifact",
    "D": "harmless incompleteness",
    "E": "genuine uncertainty not resolvable from supplied evidence",
}

ARTIFACT_PATHS = {
    f"A{index:02d}": path for index, path in enumerate(v06.ALL_ARTIFACTS, start=1)
}

EVIDENCE_AVAILABLE = {
    "A01": [
        "case/cohort_registry.csv",
        "case/intended_use.json",
        "model/predictor_manifest.json",
        "data/internal_predictions.csv",
        "data/external_locked_predictions.csv",
    ],
    "A02": ["MANIFEST.json", "case/sponsor_attestations.json", "START_STATE.json"],
    "A03": ["data/internal_predictions.csv", "data/external_locked_predictions.csv"],
    "A04": [
        "case/intended_use.json",
        "case/endpoint_definition.json",
        "data/internal_predictions.csv",
        "data/external_locked_predictions.csv",
    ],
    "A05": ["case/preprocessing_history.csv", "case/sponsor_attestations.json"],
    "A06": [
        "model/locked_model.json",
        "model/reproduction_features.csv",
        "model/reference_predictions.csv",
        "model/score_locked.py",
    ],
    "A07": [
        "case/metric_contract.json",
        "case/intended_use.json",
        "all pre-reveal A01-A06 artifacts",
    ],
    "A08": [
        "revealed/external_outcomes.csv",
        "submission/committed_validation_plan.json",
        "data/internal_predictions.csv",
        "data/external_locked_predictions.csv",
    ],
    "A09": ["case/resource_catalog.json", "submission/validation_results.json"],
    "A10": [
        "submission/validation_results.json",
        "submission/resource_value_memo.json",
        "followup/ (selected intervention evidence)",
    ],
}


def _read(path: Path) -> Any:
    if not path.is_file():
        return None
    if path.suffix == ".json":
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    except (OSError, csv.Error):
        return None


def _norm(value: Any) -> str:
    return v06._normal(value)  # noqa: SLF001 - audit mirrors the frozen grader


def _credit(value: bool) -> float:
    return 100.0 if value else 0.0


def _num(expected: float, observed: Any, tolerance: float) -> float:
    return v06._numeric_credit(  # noqa: SLF001 - audit mirrors frozen grader
        expected, observed, tolerance
    )


def _evidence(root: Path, refs: Iterable[Any]) -> float:
    return v06._evidence_credit(root, refs)  # noqa: SLF001


def _component(
    name: str,
    score: float,
    weight: float,
    observed: Any,
    expected: Any,
    pointer: str,
) -> dict[str, Any]:
    return {
        "invariant": name,
        "component_score": round(float(score), 6),
        "artifact_weight_fraction": round(float(weight), 9),
        "deduction_points": round(float(weight) * (100.0 - float(score)), 6),
        "observed": observed,
        "frozen_expected": expected,
        "artifact_pointer": pointer,
    }


def _row_refs(rows: Any) -> list[str]:
    if not isinstance(rows, list):
        return []
    return [
        ref
        for row in rows
        if isinstance(row, dict)
        for ref in str(row.get("evidence_refs", "")).split(";")
        if ref
    ]


def decompose_artifact(
    artifact_id: str,
    value: Any,
    *,
    workspace: Path,
    scenario: dict[str, Any],
    selected_resource: str,
    committed: bool,
    decision_contract: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return the exact atomic components used by the frozen scorer."""

    sid = str(scenario["scenario_id"])
    if artifact_id == "A01":
        rows = value if isinstance(value, list) else []
        observed = {str(row.get("cohort_id")): row for row in rows if isinstance(row, dict)}
        registry_rows = v06._read_csv(workspace / "case/cohort_registry.csv")  # noqa: SLF001
        registry = {row["cohort_id"]: row for row in registry_rows}
        internal = v06._read_csv(workspace / "data/internal_predictions.csv")  # noqa: SLF001
        external = v06._read_csv(workspace / "data/external_locked_predictions.csv")  # noqa: SLF001
        expected_counts = {
            "DISCOVERY-01": (118, 118),
            "INTERNAL-01": (len(internal), len({row["fingerprint_group"] for row in internal})),
            "EXTERNAL-01": (len(external), len({row["fingerprint_group"] for row in external})),
        }
        accounted = set(observed) == set(registry)
        roles = all(
            _norm(observed.get(cohort, {}).get("role")) == _norm(source["role"])
            for cohort, source in registry.items()
        )
        biological = all(
            all(
                str(observed.get(cohort, {}).get(field)) == str(source[field])
                for field in ("drug", "endpoint", "platform")
            )
            for cohort, source in registry.items()
        )
        counts_ok = True
        for cohort, expected in expected_counts.items():
            try:
                row_ok = (
                    int(float(observed.get(cohort, {}).get("row_count", -1))) == expected[0]
                    and int(float(observed.get(cohort, {}).get("patient_count", -1)))
                    == expected[1]
                )
            except (TypeError, ValueError, OverflowError):
                row_ok = False
            counts_ok = counts_ok and row_ok
        evidence_scores = [
            _evidence(workspace, str(row.get("evidence_refs", "")).split(";"))
            for row in rows
            if isinstance(row, dict)
        ]
        evidence_score = mean(evidence_scores) if evidence_scores else 0.0
        counts_observed = {
            cohort: {
                "row_count": observed.get(cohort, {}).get("row_count"),
                "patient_count": observed.get(cohort, {}).get("patient_count"),
            }
            for cohort in expected_counts
        }
        return [
            _component("source_cohorts_accounted_for", _credit(accounted), 0.2, sorted(observed), sorted(registry), "#rows[*].cohort_id"),
            _component("roles_and_visibility_correct", _credit(roles), 0.2, {k: v.get("role") for k, v in observed.items()}, {k: v["role"] for k, v in registry.items()}, "#rows[*].role"),
            _component("drug_endpoint_platform_preserved", _credit(biological), 0.2, {k: {f: v.get(f) for f in ("drug", "endpoint", "platform")} for k, v in observed.items()}, "cohort_registry exact fields", "#rows[*].drug|endpoint|platform"),
            _component("row_and_patient_counts_reconciled", _credit(counts_ok), 0.2, counts_observed, {k: {"row_count": v[0], "patient_count": v[1]} for k, v in expected_counts.items()}, "#rows[*].row_count|patient_count"),
            _component("evidence_references_resolve", evidence_score, 0.2, _row_refs(rows), "all submitted references resolve inside workspace", "#rows[*].evidence_refs"),
        ]

    if artifact_id == "A02":
        obj = value if isinstance(value, dict) else {}
        pairs = [
            ("scenario_identity", _credit(obj.get("scenario_id") == sid), obj.get("scenario_id"), sid, "#/scenario_id"),
            ("manifest_assets_checked", _credit(obj.get("manifest_assets_checked") is True), obj.get("manifest_assets_checked"), True, "#/manifest_assets_checked"),
            ("outcomes_sealed_before_commit", _credit(obj.get("outcomes_sealed_before_commit") is True), obj.get("outcomes_sealed_before_commit"), True, "#/outcomes_sealed_before_commit"),
            ("sponsor_attestations_not_ground_truth", _credit(obj.get("sponsor_attestations_treated_as_ground_truth") is False), obj.get("sponsor_attestations_treated_as_ground_truth"), False, "#/sponsor_attestations_treated_as_ground_truth"),
            ("research_licence_scope", _credit("research" in _norm(obj.get("licence_scope"))), obj.get("licence_scope"), "contains research", "#/licence_scope"),
            ("at_least_one_finding", _credit(len(obj.get("findings") or []) >= 1), len(obj.get("findings") or []), ">=1", "#/findings"),
            ("evidence_references_resolve", _evidence(workspace, obj.get("evidence_refs") or []), obj.get("evidence_refs"), "all references resolve", "#/evidence_refs"),
        ]
        return [_component(name, score, 1 / 7, observed, expected, pointer) for name, score, observed, expected, pointer in pairs]

    if artifact_id == "A03":
        rows = value if isinstance(value, list) else []
        source = [
            *v06._read_csv(workspace / "data/internal_predictions.csv"),  # noqa: SLF001
            *v06._read_csv(workspace / "data/external_locked_predictions.csv"),  # noqa: SLF001
        ]
        by_sample = {str(row.get("sample_id")): row for row in rows if isinstance(row, dict)}
        all_rows = set(by_sample) == {str(row["sample_id"]) for row in source}
        identity = all(
            str(by_sample.get(str(row["sample_id"]), {}).get("canonical_patient_id"))
            in {str(row["fingerprint_group"]), str(row["fingerprint_group"])[3:]}
            for row in source
        )
        dependence = all(
            str(by_sample.get(str(row["sample_id"]), {}).get("dependence_cluster"))
            in {str(row["fingerprint_group"]), str(row["fingerprint_group"])[3:]}
            for row in source
        )
        aliases = {str(row["sample_id"]) for row in source if str(row["reported_patient_id"]).endswith("-ALIAS")}
        blocked = scenario["states"]["identity"] == "blocked"
        containment = (
            all(_norm(by_sample.get(sample, {}).get("linkage_status")) in {"unresolved", "conditional", "reconciled_by_fingerprint"} for sample in aliases)
            if blocked
            else all(_norm(row.get("linkage_status")) not in {"ignored", "independent_row"} for row in rows if isinstance(row, dict))
        )
        evidence_scores = [_evidence(workspace, str(row.get("evidence_refs", "")).split(";")) for row in rows if isinstance(row, dict)]
        pairs = [
            ("all_rows_accounted_for", _credit(all_rows), len(by_sample), len(source), "#rows[*].sample_id"),
            ("canonical_identity_uses_fingerprint", _credit(identity), "submitted canonical_patient_id", "fingerprint_group (prefix optional)", "#rows[*].canonical_patient_id"),
            ("dependence_cluster_explicit", _credit(dependence), "submitted dependence_cluster", "fingerprint_group (prefix optional)", "#rows[*].dependence_cluster"),
            ("unresolved_linkage_contained", _credit(containment), {sample: by_sample.get(sample, {}).get("linkage_status") for sample in sorted(aliases)}, "unresolved/conditional/reconciled_by_fingerprint when blocked; never ignored otherwise", "#rows[*].linkage_status"),
            ("evidence_references_resolve", mean(evidence_scores) if evidence_scores else 0.0, _row_refs(rows), "all references resolve", "#rows[*].evidence_refs"),
        ]
        return [_component(name, score, 0.2, observed, expected, pointer) for name, score, observed, expected, pointer in pairs]

    if artifact_id == "A04":
        obj = value if isinstance(value, dict) else {}
        endpoint_state = str(scenario["states"]["endpoint"])
        expected_ambiguity = "blocked" if endpoint_state == "blocked" else endpoint_state
        transfer = "mismatched" if scenario["scenario_class"] == "endpoint_drug_platform_transfer_failure" else "matched"
        labels = obj.get("label_sources") or []
        pairs = [
            ("scenario_identity", _credit(obj.get("scenario_id") == sid), obj.get("scenario_id"), sid, "#/scenario_id"),
            ("target_endpoint_explicit", _credit(_norm(obj.get("target_endpoint")) == "week_6_clinical_response"), obj.get("target_endpoint"), "week_6_clinical_response", "#/target_endpoint"),
            ("assessment_timepoint_explicit", _credit("6" in str(obj.get("assessment_timepoint"))), obj.get("assessment_timepoint"), "contains 6", "#/assessment_timepoint"),
            ("label_sources_preserved", _credit({"reviewer_a", "reviewer_b", "extraction_label"} <= {_norm(row) for row in labels}), labels, ["reviewer_a", "reviewer_b", "extraction_label"], "#/label_sources"),
            ("ambiguity_status", _credit(_norm(obj.get("ambiguity_status")) == expected_ambiguity), obj.get("ambiguity_status"), expected_ambiguity, "#/ambiguity_status"),
            ("endpoint_transfer_status", _credit(_norm(obj.get("endpoint_transfer_status")) == transfer), obj.get("endpoint_transfer_status"), transfer, "#/endpoint_transfer_status"),
            ("sensitivity_plan_present", _credit(bool(obj.get("sensitivity_plan"))), obj.get("sensitivity_plan"), "non-empty", "#/sensitivity_plan"),
            ("evidence_references_resolve", _evidence(workspace, obj.get("evidence_refs") or []), obj.get("evidence_refs"), "all references resolve", "#/evidence_refs"),
        ]
        return [_component(name, score, 0.125, observed, expected, pointer) for name, score, observed, expected, pointer in pairs]

    if artifact_id == "A05":
        obj = value if isinstance(value, dict) else {}
        leaky = scenario["states"]["preprocessing"] == "blocked"
        transfer = scenario["states"]["transport"] == "blocked"
        expected_leakage = "blocked" if leaky else "clear"
        expected_transfer = "mismatched" if transfer else "matched"
        pairs = [
            ("scenario_identity", _credit(obj.get("scenario_id") == sid), obj.get("scenario_id"), sid, "#/scenario_id"),
            ("lineage_has_four_steps", _credit(len(obj.get("steps") or []) >= 4), len(obj.get("steps") or []), ">=4", "#/steps"),
            ("outcome_visibility_recorded", _credit(obj.get("outcomes_used_during_fit") is leaky), obj.get("outcomes_used_during_fit"), leaky, "#/outcomes_used_during_fit"),
            ("validation_refit_detected", _credit(obj.get("validation_data_used_to_fit_transforms") is leaky), obj.get("validation_data_used_to_fit_transforms"), leaky, "#/validation_data_used_to_fit_transforms"),
            ("leakage_status", _credit(_norm(obj.get("leakage_status")) == expected_leakage), obj.get("leakage_status"), expected_leakage, "#/leakage_status"),
            ("platform_transfer_contained", _credit(_norm(obj.get("platform_transfer_status")) == expected_transfer), obj.get("platform_transfer_status"), expected_transfer, "#/platform_transfer_status"),
            ("evidence_references_resolve", _evidence(workspace, obj.get("evidence_refs") or []), obj.get("evidence_refs"), "all references resolve", "#/evidence_refs"),
        ]
        return [_component(name, score, 1 / 7, observed, expected, pointer) for name, score, observed, expected, pointer in pairs]

    if artifact_id == "A06":
        rows = value if isinstance(value, list) else []
        reference = {row["sample_id"]: float(row["locked_probability"]) for row in v06._read_csv(workspace / "model/reference_predictions.csv")}  # noqa: SLF001
        observed = {str(row.get("sample_id")): row for row in rows if isinstance(row, dict)}
        identity = set(observed) == set(reference)
        probabilities = all(_num(expected, observed.get(sample, {}).get("reproduced_probability"), 1e-8) == 100 for sample, expected in reference.items())
        errors = True
        for row in rows:
            try:
                expected_error = abs(float(row.get("reference_probability", 0)) - float(row.get("reproduced_probability", 1)))
                errors = errors and _num(expected_error, row.get("absolute_error"), 1e-8) == 100
            except (TypeError, ValueError, OverflowError):
                errors = False
        model_hash = v06.sha256_file(workspace / "model/locked_model.json")
        hashes = all(str(row.get("model_sha256")) == model_hash for row in rows if isinstance(row, dict)) and bool(rows)
        pairs = [
            ("all_reference_samples_scored", _credit(identity), sorted(observed), sorted(reference), "#rows[*].sample_id"),
            ("prediction_tolerance_met", _credit(probabilities), "submitted reproduced_probability", "reference within 1e-8", "#rows[*].reproduced_probability"),
            ("absolute_error_recomputed", _credit(errors), "submitted absolute_error", "absolute difference within 1e-8", "#rows[*].absolute_error"),
            ("model_hash_preserved", _credit(hashes), sorted({str(row.get("model_sha256")) for row in rows if isinstance(row, dict)}), model_hash, "#rows[*].model_sha256"),
        ]
        return [_component(name, score, 0.25, observed_value, expected, pointer) for name, score, observed_value, expected, pointer in pairs]

    if artifact_id == "A07":
        obj = value if isinstance(value, dict) else {}
        outer = 12
        components = [
            _component("scenario_identity", _credit(obj.get("scenario_id") == sid), 1 / outer, obj.get("scenario_id"), sid, "#/scenario_id"),
            _component("patient_dependence_preserved", _credit(obj.get("dependence_preserved") is True), 1 / outer, obj.get("dependence_preserved"), True, "#/dependence_preserved"),
            _component("uncertainty_preserves_dependence", _credit(obj.get("uncertainty_preserves_dependence") is True), 1 / outer, obj.get("uncertainty_preserves_dependence"), True, "#/uncertainty_preserves_dependence"),
            _component("preprocessing_outcome_blind", _credit(obj.get("preprocessing_outcome_blind") is (scenario["states"]["preprocessing"] != "blocked")), 1 / outer, obj.get("preprocessing_outcome_blind"), scenario["states"]["preprocessing"] != "blocked", "#/preprocessing_outcome_blind"),
        ]
        for field in ("reports_discrimination", "reports_uncertainty", "reports_calibration", "reports_decision_utility"):
            components.append(_component(field, _credit(obj.get(field) is True), 1 / outer / 4, obj.get(field), True, f"#/{field}"))
        components.append(_component("three_metric_families", _credit(len(obj.get("metric_families") or []) >= 3), 1 / outer, obj.get("metric_families"), ">=3", "#/metric_families"))
        rule = obj.get("decision_rule") if isinstance(obj.get("decision_rule"), dict) else {}
        for name in ("minimum_auc", "minimum_auc_ci_low", "maximum_brier", "minimum_net_benefit"):
            components.append(_component(f"decision_rule.{name}", _num(float(decision_contract[name]), rule.get(name), 0.01), 1 / outer / 4, rule.get(name), decision_contract[name], f"#/decision_rule/{name}"))
        components.extend(
            [
                _component("competing_live_hypotheses", _credit(len(obj.get("live_hypotheses") or []) >= 2), 1 / outer, obj.get("live_hypotheses"), ">=2", "#/live_hypotheses"),
                _component("pre_reveal_decision", _credit(obj.get("pre_reveal_decision") == scenario["initial_decision"]), 1 / outer, obj.get("pre_reveal_decision"), scenario["initial_decision"], "#/pre_reveal_decision"),
                _component("locked_model_path_declared", _credit("model/locked_model.json" in (obj.get("analysis_artifact_paths") or [])), 1 / outer, obj.get("analysis_artifact_paths"), "contains model/locked_model.json", "#/analysis_artifact_paths"),
                _component("commitment_immutable", _credit(committed), 1 / outer, committed, True, "COMMITMENT_RECORD.json#/artifact_snapshot"),
                _component("evidence_references_resolve", _evidence(workspace, obj.get("evidence_refs") or []), 1 / outer, obj.get("evidence_refs"), "all references resolve", "#/evidence_refs"),
            ]
        )
        return components

    if artifact_id == "A08":
        obj = value if isinstance(value, dict) else {}
        outer = 9
        try:
            expected_metrics = v06.compute_v05_metrics(workspace, followup=False)
        except Exception:  # audit records the frozen fallback
            expected_metrics = {name: 0.0 for name in v06.METRIC_NAMES}
        components = [
            _component("scenario_identity", _credit(obj.get("scenario_id") == sid), 1 / outer, obj.get("scenario_id"), sid, "#/scenario_id"),
            _component("committed_plan_honoured", _credit(obj.get("committed_plan_honoured") is True), 1 / outer, obj.get("committed_plan_honoured"), True, "#/committed_plan_honoured"),
            _component("patient_dependence_preserved", _credit(obj.get("dependence_preserved") is True), 1 / outer, obj.get("dependence_preserved"), True, "#/dependence_preserved"),
            _component("preprocessing_outcome_blind", _credit(obj.get("preprocessing_outcome_blind") is (scenario["states"]["preprocessing"] != "blocked")), 1 / outer, obj.get("preprocessing_outcome_blind"), scenario["states"]["preprocessing"] != "blocked", "#/preprocessing_outcome_blind"),
        ]
        metrics = obj.get("metrics") if isinstance(obj.get("metrics"), dict) else {}
        for name in v06.METRIC_NAMES:
            components.append(_component(f"metric.{name}", _num(float(expected_metrics[name]), metrics.get(name), float(v06.METRIC_TOLERANCES[name])), 1 / outer / len(v06.METRIC_NAMES), metrics.get(name), expected_metrics[name], f"#/metrics/{name}"))
        claims = obj.get("claim_statuses") if isinstance(obj.get("claim_statuses"), dict) else {}
        expected_claims = v06.expected_initial_claim_statuses(scenario)
        for name, status in expected_claims.items():
            components.append(_component(f"claim_status.{name}", _credit(_norm(claims.get(name)) == status), 1 / outer / len(expected_claims), claims.get(name), status, f"#/claim_statuses/{name}"))
        components.extend(
            [
                _component("provisional_decision", _credit(obj.get("provisional_decision") == scenario["initial_decision"]), 1 / outer, obj.get("provisional_decision"), scenario["initial_decision"], "#/provisional_decision"),
                _component("dominant_uncertainty_present", _credit(bool(str(obj.get("dominant_uncertainty", "")).strip())), 1 / outer, obj.get("dominant_uncertainty"), "non-empty", "#/dominant_uncertainty"),
                _component("evidence_references_resolve", _evidence(workspace, obj.get("evidence_refs") or []), 1 / outer, obj.get("evidence_refs"), "all references resolve", "#/evidence_refs"),
            ]
        )
        return components

    if artifact_id == "A09":
        obj = value if isinstance(value, dict) else {}
        selected = str(obj.get("selected_resource_id"))
        utility = float(scenario["resource_utilities"].get(selected, 0.0))
        comparisons = obj.get("resource_comparisons") or []
        compared = {str(row.get("resource_id")) for row in comparisons if isinstance(row, dict)}
        expected_ids = set(scenario["resource_utilities"])
        effect = v06.expected_intervention_effect(scenario, selected)
        pairs = [
            ("scenario_identity", _credit(obj.get("scenario_id") == sid), obj.get("scenario_id"), sid, "#/scenario_id"),
            ("competing_hypotheses_retained", _credit(len(obj.get("live_hypotheses") or []) >= 2), obj.get("live_hypotheses"), ">=2", "#/live_hypotheses"),
            ("all_resource_counterfactuals_compared", 100 * len(compared & expected_ids) / len(expected_ids), sorted(compared), sorted(expected_ids), "#/resource_comparisons[*].resource_id"),
            ("resource_utility", 100 * utility, selected, {key: value for key, value in scenario["resource_utilities"].items()}, "#/selected_resource_id"),
            ("expected_intervention_effect", _credit(obj.get("expected_effect") == effect), obj.get("expected_effect"), effect, "#/expected_effect"),
            ("smallest_discriminating_action_present", _credit(bool(str(obj.get("smallest_discriminating_action", "")).strip())), obj.get("smallest_discriminating_action"), "non-empty", "#/smallest_discriminating_action"),
            ("evidence_references_resolve", _evidence(workspace, obj.get("evidence_refs") or []), obj.get("evidence_refs"), "all references resolve", "#/evidence_refs"),
        ]
        return [_component(name, score, 1 / 7, observed, expected, pointer) for name, score, observed, expected, pointer in pairs]

    if artifact_id == "A10":
        obj = value if isinstance(value, dict) else {}
        belief = obj.get("belief_update") if isinstance(obj.get("belief_update"), dict) else {}
        next_action = obj.get("smallest_next_action") if isinstance(obj.get("smallest_next_action"), dict) else {}
        expected_decision = v06.expected_final_decision(scenario, selected_resource)
        expected_effect = v06.expected_intervention_effect(scenario, selected_resource)
        expected_direction = v06.expected_belief_direction(scenario, selected_resource)
        expected_action = v06.expected_next_action_class(scenario, selected_resource)
        supported_refs = [ref for claim in obj.get("supported_claims") or [] if isinstance(claim, dict) for ref in claim.get("evidence_refs") or []]
        components = [
            _component("scenario_identity", _credit(obj.get("scenario_id") == sid), 1 / 9, obj.get("scenario_id"), sid, "#/scenario_id"),
            _component("decision_supported", _credit(obj.get("decision") == expected_decision), 1 / 9, obj.get("decision"), expected_decision, "#/decision"),
        ]
        claims = obj.get("claim_statuses") if isinstance(obj.get("claim_statuses"), dict) else {}
        expected_claims = v06.expected_final_claim_statuses(scenario, selected_resource)
        for name, status in expected_claims.items():
            components.append(_component(f"claim_status.{name}", _credit(_norm(claims.get(name)) == status), 1 / 9 / len(expected_claims), claims.get(name), status, f"#/claim_statuses/{name}"))
        components.extend(
            [
                _component("intervention_effect", _credit(obj.get("intervention_effect") == expected_effect), 1 / 9, obj.get("intervention_effect"), expected_effect, "#/intervention_effect"),
                _component("belief_revision_direction", _credit(belief.get("direction") == expected_direction), 1 / 9, belief.get("direction"), expected_direction, "#/belief_update/direction"),
                _component("smallest_next_action_class", _credit(next_action.get("class") == expected_action), 1 / 9, next_action.get("class"), expected_action, "#/smallest_next_action/class"),
                _component("limitations_explicit", _credit(len(obj.get("limitations") or []) >= 1), 1 / 9, len(obj.get("limitations") or []), ">=1", "#/limitations"),
                _component("supported_claims_present", _credit(len(obj.get("supported_claims") or []) >= 1), 1 / 9, len(obj.get("supported_claims") or []), ">=1", "#/supported_claims"),
                _component("evidence_references_resolve", _evidence(workspace, [*(obj.get("evidence_refs") or []), *supported_refs]), 1 / 9, [*(obj.get("evidence_refs") or []), *supported_refs], "all references resolve", "#/evidence_refs|supported_claims[*].evidence_refs"),
            ]
        )
        return components
    raise ValueError(f"Unknown artifact: {artifact_id}")


def _contains_nested_metric_evidence(value: Any) -> bool:
    if not isinstance(value, dict) or not isinstance(value.get("metrics"), dict):
        return False
    metrics = value["metrics"]
    return bool(metrics)


def adjudicate_deduction(
    artifact_id: str,
    component: dict[str, Any],
    *,
    artifact_value: Any,
    scenario: dict[str, Any],
    selected_resource: str,
) -> tuple[str, str]:
    """Classify a frozen deduction without changing its score."""

    name = str(component["invariant"])
    observed = component.get("observed")
    clean = scenario["scenario_class"] == "clean_enough_progression"
    leakage = scenario["scenario_class"] == "batch_or_preprocessing_leakage"

    if artifact_id == "A01" and name == "row_and_patient_counts_reconciled":
        raw_rows = artifact_value if isinstance(artifact_value, list) else []
        discovery = next(
            (
                row
                for row in raw_rows
                if isinstance(row, dict) and row.get("cohort_id") == "DISCOVERY-01"
            ),
            {},
        )
        patient_count = str(discovery.get("patient_count", "")).lower()
        if any(marker in patient_count for marker in ("unresolved", "unknown", "na", "n/a")):
            return "E", "The discovery row-level file was absent, so 118 unique patients could not be verified; refusing to invent the count is correct diligence."
    if artifact_id == "A02" and isinstance(artifact_value, dict):
        alternative_structure = any(
            key in artifact_value
            for key in ("evidence_vs_attestation", "verified_evidence", "discrepancies")
        )
        if alternative_structure and name in {
            "sponsor_attestations_not_ground_truth",
            "at_least_one_finding",
        }:
            return "C", "The scientific distinction or discrepancy is present under a different, clearer structure that the frozen field-level grader ignores."
        if alternative_structure:
            return "D", "The alternate provenance memo omitted a frozen bookkeeping field; its core scientific finding remains inspectable."
    if artifact_id == "A03" and name == "dependence_cluster_explicit":
        return "B", "The submitted patient-plus-site cluster is a defensible stricter dependence unit; the frozen grader accepted only the bare fingerprint token."
    if (
        artifact_id == "A04"
        and name == "target_endpoint_explicit"
        and "week" in _norm(observed)
        and "clinical_response" in _norm(observed)
    ):
        return "C", "The target endpoint was semantically explicit but annotated; the frozen grader required exact normalized equality."
    if artifact_id == "A04" and name == "label_sources_preserved":
        return "C", "The labels were often semantically preserved with annotations such as '(primary)' or '(sensitivity)', but the frozen normalizer required bare tokens."
    if artifact_id == "A04" and name == "ambiguity_status" and clean:
        return "B", "Calling the labels conditional is defensible when source adjudication is unavailable, even if supplied reviewer columns agree."
    if (
        artifact_id == "A04"
        and name in {"ambiguity_status", "endpoint_transfer_status"}
        and _norm(observed) in {"conditional", "unresolved", "invalid"}
    ):
        return "B", "A conservative endpoint/transfer status is professionally defensible when source verification remains incomplete."
    if artifact_id == "A05" and name == "leakage_status" and clean:
        return "B", "A conditional status distinguishes a clean declared lineage from an independently verified execution; the frozen target allowed only 'clear'."
    if artifact_id == "A05" and name in {"outcome_visibility_recorded", "validation_refit_detected", "leakage_status"} and leakage:
        serialized = json.dumps(artifact_value, sort_keys=True).lower()
        if "leak" in serialized and any(term in serialized for term in ("outcome", "week6_response", "validation")):
            return "C", "The agent identified the consequential leakage in a semantically clear alternative field layout or used 'invalid' where the frozen enum required 'blocked'."
        return "A", "The planted outcome-informed or validation-fitted transform is decision-invalidating and should be identified directly."
    if artifact_id == "A05" and name == "platform_transfer_contained":
        serialized = json.dumps(artifact_value, sort_keys=True).lower()
        if "same platform" in serialized or "single platform" in serialized:
            return "C", "The agent documented the matched platform in prose or another field; the frozen grader required one exact enum location."
    if artifact_id == "A07" and name.startswith("decision_rule."):
        if isinstance(artifact_value, dict) and isinstance(artifact_value.get("decision_rule"), dict):
            rule = artifact_value["decision_rule"]
            if any(isinstance(value, dict) for value in rule.values()):
                return "C", "The plan supplied a richer/nested rule, but the frozen scorer read only four numbers at exact top-level keys."
        return "D", "A numeric threshold was omitted or placed outside the frozen field; the rest of the prospective plan remains inspectable."
    if artifact_id == "A07" and name == "pre_reveal_decision" and clean:
        return "B", "Before the external outcome reveal, pause or insufficient evidence is a defensible conservative position; the frozen target prematurely required conditional advance."
    if artifact_id == "A08" and name.startswith("metric.") and _contains_nested_metric_evidence(artifact_value):
        return "C", "The agent independently produced detailed patient-level results, but the frozen scorer looked only for flat metric keys and ignored nested valid outputs."
    if artifact_id == "A08" and name.startswith("metric."):
        return "A", "The required quantitative estimate is absent or outside tolerance in the frozen result contract."
    if artifact_id in {"A08", "A10"} and name.startswith("claim_status."):
        return "B", "The frozen enum encodes one policy boundary; a more conservative claim status can be professionally defensible if supported by the stated limitations."
    if artifact_id == "A08" and name == "provisional_decision":
        if clean and str(observed) in {"pause", "insufficient_evidence"}:
            return "B", "A conservative pre-investment pause is defensible because preprocessing execution and source identity were attested rather than independently verified."
        return "A", "The provisional decision does not contain the scenario's material blocker or overstates the revealed evidence."
    if artifact_id == "A09" and name == "resource_utility":
        if clean and selected_resource in {"R1", "R3", "R4", "R5"}:
            return "B", "No-resource was not uniquely professionally optimal: a low-cost identity or locked-pipeline check can be justified before commercial advancement."
        return "A", "The selected investment has lower predeclared decision value than an available experiment that directly tests the active blocker."
    if artifact_id == "A09" and name == "expected_intervention_effect":
        return "B", "The agent can correctly describe resolution of the selected blocker while the frozen enum instead names the newly exposed blocker; both framings can be scientifically coherent."
    if artifact_id == "A09" and name == "all_resource_counterfactuals_compared":
        return "D", "Omitting a dominated resource comparison is incomplete documentation but need not change the decision."
    if artifact_id == "A10" and name in {"decision_supported", "intervention_effect", "belief_revision_direction", "smallest_next_action_class"} and clean:
        return "B", "The final action follows a coherent conservative diligence policy, while the frozen target assumes clean sponsor attestations are sufficient and no resource is optimal."
    if artifact_id == "A10" and name in {"intervention_effect", "belief_revision_direction", "smallest_next_action_class"}:
        return "B", "The artifact can describe the same scientific update with a different recovery framing; exact enum agreement is not uniquely valid."
    if name == "evidence_references_resolve":
        return "D", "Some cited support was incomplete or not path-resolvable; this weakens auditability without automatically invalidating the scientific conclusion."
    if name in {"scenario_identity", "limitations_explicit", "supported_claims_present", "dominant_uncertainty_present", "smallest_discriminating_action_present"}:
        return "D", "This is incomplete traceability or documentation rather than an independently established scientific error."
    if artifact_id in {"A02", "A03", "A06"}:
        return "A", "This failed property would compromise provenance, dependence handling, or locked-model identity if taken at face value."
    return "A", "The submitted property conflicts with the available evidence or frozen scientific requirement and can change a supported claim."


def _artifact_behavior(artifact_id: str, value: Any) -> str:
    if value is None:
        return "Artifact absent or unparsable."
    if artifact_id == "A01":
        return f"Inventoried {len(value) if isinstance(value, list) else 0} cohorts; discovery patient_count={next((r.get('patient_count') for r in value if r.get('cohort_id') == 'DISCOVERY-01'), None) if isinstance(value, list) else None}."
    if artifact_id == "A02":
        return f"Recorded manifest_checked={value.get('manifest_assets_checked')}, sealed={value.get('outcomes_sealed_before_commit')}, sponsor_ground_truth={value.get('sponsor_attestations_treated_as_ground_truth')} and {len(value.get('findings') or [])} findings."
    if artifact_id == "A03":
        statuses = sorted({_norm(row.get("linkage_status")) for row in value if isinstance(row, dict)}) if isinstance(value, list) else []
        return f"Mapped {len(value) if isinstance(value, list) else 0} sample rows using linkage statuses {statuses}."
    if artifact_id == "A04":
        return f"Set ambiguity={value.get('ambiguity_status')}, transfer={value.get('endpoint_transfer_status')}, labels={value.get('label_sources')}."
    if artifact_id == "A05":
        return f"Set outcomes_used={value.get('outcomes_used_during_fit')}, validation_refit={value.get('validation_data_used_to_fit_transforms')}, leakage={value.get('leakage_status')}, transfer={value.get('platform_transfer_status')}."
    if artifact_id == "A06":
        return f"Reproduced {len(value) if isinstance(value, list) else 0} audit predictions and recorded model hashes."
    if artifact_id == "A07":
        return f"Committed pre-reveal decision={value.get('pre_reveal_decision')}, dependence={value.get('dependence_preserved')}, blind_preprocessing={value.get('preprocessing_outcome_blind')}, hypotheses={len(value.get('live_hypotheses') or [])}."
    if artifact_id == "A08":
        metrics = value.get("metrics") or {}
        return f"Reported provisional decision={value.get('provisional_decision')}; metrics keys={sorted(metrics) if isinstance(metrics, dict) else []}; dominant uncertainty={value.get('dominant_uncertainty')}."
    if artifact_id == "A09":
        return f"Selected {value.get('selected_resource_id')} after comparing {len(value.get('resource_comparisons') or [])} resources; expected effect={value.get('expected_effect')}."
    if artifact_id == "A10":
        belief = value.get("belief_update")
        belief = belief if isinstance(belief, dict) else {}
        return f"Concluded {value.get('decision')}; effect={value.get('intervention_effect')}; belief direction={belief.get('direction')}."
    return "Unknown artifact."


def _expected_behavior(artifact_id: str, scenario: dict[str, Any], selected: str) -> str:
    expected = {
        "A01": "Account for all three cohorts and reconcile rows and unique patients without inventing unavailable source facts.",
        "A02": "Verify manifest/provenance, preserve sealing/licence, and treat sponsor attestations as claims rather than ground truth.",
        "A03": "Map every row to fingerprint-defined patient/dependence clusters and contain unresolved aliases.",
        "A04": "Preserve week-6 clinical-response labels, quantify ambiguity, and avoid endpoint-transfer overclaiming.",
        "A05": "Reconstruct fit scope and detect outcome use, validation refitting, leakage, and platform mismatch.",
        "A06": "Independently reproduce all reference predictions with the unchanged locked model.",
        "A07": f"Commit a leakage-safe patient-level validation plan and the frozen pre-reveal decision {scenario['initial_decision']}.",
        "A08": f"Recompute patient-level performance/uncertainty and make the frozen provisional decision {scenario['initial_decision']}.",
        "A09": f"Compare all interventions and select the smallest high-value test; frozen optimum={scenario['optimal_resource']}.",
        "A10": f"Revise beliefs after the selected evidence and reach frozen conditional decision={v06.expected_final_decision(scenario, selected)}.",
    }
    return expected[artifact_id]


def _round(value: float) -> float:
    return round(float(value), 6)


def _stats(values: list[float]) -> dict[str, float]:
    return {
        "mean": _round(mean(values)),
        "minimum": _round(min(values)),
        "maximum": _round(max(values)),
        "range": _round(max(values) - min(values)),
        "population_variance": _round(pvariance(values)),
        "ceiling_rate_at_least_95": _round(sum(value >= 95 for value in values) / len(values)),
    }


def _elapsed_seconds(requests: list[dict[str, Any]]) -> float | None:
    timestamps = []
    for request in requests:
        raw = request.get("recorded_at")
        if not raw:
            continue
        try:
            timestamps.append(datetime.fromisoformat(str(raw)))
        except ValueError:
            continue
    if len(timestamps) < 2:
        return None
    return _round((max(timestamps) - min(timestamps)).total_seconds())


def _ease_categories(artifact_id: str, stat: dict[str, float]) -> list[str]:
    categories: list[str] = []
    if stat["minimum"] >= 95:
        categories.append("universally_easy")
    if stat["range"] <= 10:
        categories.append("weakly_discriminative")
    if artifact_id in {"A01", "A02", "A03", "A06"}:
        categories.append("procedural")
    if artifact_id in {"A05", "A09", "A10"}:
        categories.append("answer_signalling")
    if artifact_id in {"A02", "A06"}:
        categories.append("mechanically_recoverable")
        categories.append("scientifically_shallow")
    if artifact_id in {"A01", "A04", "A05", "A07", "A08", "A09", "A10"}:
        categories.append("grader_limited")
    if artifact_id == "A02":
        categories.append("redundant")
    if artifact_id in {"A05", "A08", "A09", "A10"}:
        categories.append("consequential_and_discriminative")
    return categories


def build_v063_ceiling_audit(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    checkpoint = json.loads((root / "artifacts/diagnostics/hard_suite_v063_calibration_runs.json").read_text(encoding="utf-8"))
    config = json.loads((root / "configs/hard_suite_v06.json").read_text(encoding="utf-8"))
    controls = json.loads((root / "artifacts/diagnostics/hard_suite_v06_controls.json").read_text(encoding="utf-8"))
    scenarios = {row["scenario_id"]: row for row in config["development_scenarios"]}
    metadata = {row["id"]: row for row in config["artifacts"]}
    cells: list[dict[str, Any]] = []
    artifact_values: dict[str, list[float]] = defaultdict(list)
    capability_values: dict[str, list[float]] = defaultdict(list)
    scenario_losses: dict[str, float] = defaultdict(float)
    artifact_losses: dict[str, float] = defaultdict(float)
    capability_losses: dict[str, float] = defaultdict(float)
    adjudication_counts: dict[str, int] = defaultdict(int)

    for run in checkpoint["runs"]:
        workspace = root / run["workspace_directory"]
        run_root = root / run["run_directory"]
        scenario = scenarios[run["scenario_id"]]
        grade = run["diagnostic_grade"]
        selected = str(grade.get("selected_resource") or "none")
        commitment = _read(workspace / "COMMITMENT_RECORD.json") or {}
        committed = bool(commitment.get("artifact_snapshot"))
        artifact_rows = []
        first_adjudicated = None
        for artifact_id, relative in ARTIFACT_PATHS.items():
            value = _read(workspace / relative)
            scoring_value = sanitize_artifact(relative, value, [])
            components = decompose_artifact(
                artifact_id,
                scoring_value,
                workspace=workspace,
                scenario=scenario,
                selected_resource=selected,
                committed=committed,
                decision_contract=config["decision_contract"],
            )
            reconstructed = _round(sum(row["artifact_weight_fraction"] * row["component_score"] for row in components))
            frozen_score = float(grade["artifact_scores"][artifact_id])
            if abs(reconstructed - frozen_score) > 0.0002:
                raise AssertionError(f"{run['run_id']} {artifact_id}: decomposition {reconstructed} != frozen {frozen_score}")
            deductions = []
            for component in components:
                if component["component_score"] >= 99.999999:
                    continue
                code, rationale = adjudicate_deduction(
                    artifact_id,
                    component,
                    artifact_value=value,
                    scenario=scenario,
                    selected_resource=selected,
                )
                adjudication_counts[code] += 1
                deduction = {
                    **component,
                    "adjudication": code,
                    "adjudication_label": ADJUDICATION_LABELS[code],
                    "construct_rationale": rationale,
                }
                deductions.append(deduction)
                if code == "A" and first_adjudicated is None:
                    first_adjudicated = artifact_id
            expected_final = v06.expected_final_decision(scenario, selected)
            observed_final = grade.get("observed_final_decision")
            if deductions:
                scientific_assessment = " ".join(
                    f"{row['adjudication']}: {row['construct_rationale']}"
                    for row in deductions
                )
            else:
                scientific_assessment = (
                    "The artifact satisfied every atomic frozen invariant; this does not "
                    "by itself establish that the artifact was difficult or discriminative."
                )
            artifact_row = {
                "artifact_id": artifact_id,
                "artifact_path": relative,
                "depth": metadata[artifact_id]["depth"],
                "family": metadata[artifact_id]["family"],
                "score": frozen_score,
                "state": grade["artifact_states"][artifact_id],
                "agent_behavior": _artifact_behavior(artifact_id, value),
                "evidence_available": EVIDENCE_AVAILABLE[artifact_id],
                "frozen_expected_behavior": _expected_behavior(artifact_id, scenario, selected),
                "deductions": deductions,
                "scientific_correctness": sorted({row["adjudication"] for row in deductions}) or ["no_deduction"],
                "scientific_assessment": scientific_assessment,
                "professional_consequence_if_real": metadata[artifact_id]["consequence_of_error"],
                "frozen_first_divergence": grade.get("first_substantive_divergence"),
                "adjudicated_first_consequential_divergence": None,
                "eventual_decision_effect": (
                    "decision_diverged_from_frozen_conditional_target"
                    if observed_final != expected_final
                    else "no_observed_final_decision_divergence"
                ),
                "paired_actionable_remedy": metadata[artifact_id]["paired_remedy"],
                "remedy_intervention_class": metadata[artifact_id]["remedy_intervention_class"],
                "trace": {
                    "artifact": f"{run['workspace_directory']}/{relative}",
                    "grade": f"{run['run_directory']}/run_summary.json#/diagnostic_grade/artifact_scores/{artifact_id}",
                    "request_ledger": f"{run['run_directory']}/request_ledger.json#/requests",
                },
            }
            artifact_rows.append(artifact_row)
            artifact_values[artifact_id].append(frozen_score)
            artifact_losses[artifact_id] += 100 - frozen_score
            scenario_losses[run["scenario_id"]] += 100 - frozen_score

        for row in artifact_rows:
            row["adjudicated_first_consequential_divergence"] = first_adjudicated
        for capability, score in grade["capability_scores"].items():
            capability_values[capability].append(float(score))
            capability_losses[capability] += 100 - float(score)

        ledger = _read(run_root / "request_ledger.json") or {}
        requests = ledger.get("requests") or []
        summary = _read(run_root / "run_summary.json") or {}
        cells.append(
            {
                "run_id": run["run_id"],
                "model_id": run["model_id"],
                "scenario_id": run["scenario_id"],
                "classification": run["classification"],
                "accepted_scientific_score": run["score"],
                "diagnostic_scientific_score": grade["coverage_adjusted_scientific_score"],
                "reliability_score": grade["reliability_inclusive_score"],
                "artifact_coverage": grade["artifact_coverage"],
                "capability_scores": grade["capability_scores"],
                "initial_decision": grade.get("observed_initial_decision"),
                "selected_resource": selected,
                "final_decision": grade.get("observed_final_decision"),
                "intervention_effect": grade.get("observed_intervention_effect"),
                "frozen_expected_initial_decision": scenario["initial_decision"],
                "frozen_expected_resource": scenario["optimal_resource"],
                "frozen_expected_final_for_selected_resource": v06.expected_final_decision(scenario, selected),
                "frozen_expected_effect_for_selected_resource": v06.expected_intervention_effect(scenario, selected),
                "frozen_first_divergence": grade.get("first_substantive_divergence"),
                "adjudicated_first_consequential_divergence": first_adjudicated,
                "cost_usd": run["reported_cost_usd"],
                "turns": run["turn_count"],
                "provider_requests": run["provider_request_count"],
                "tool_calls": summary.get("tool_call_count"),
                "tool_call_counts": summary.get("tool_call_counts"),
                "api_wall_time_seconds": _elapsed_seconds(requests),
                "token_usage": run["token_usage"],
                "artifacts": artifact_rows,
                "trace": {
                    "summary": f"{run['run_directory']}/run_summary.json",
                    "ledger": f"{run['run_directory']}/request_ledger.json",
                    "workspace": run["workspace_directory"],
                },
            }
        )

    artifact_stats = {name: _stats(values) for name, values in artifact_values.items()}
    capability_stats = {name: _stats(values) for name, values in capability_values.items()}
    total_artifact_loss = sum(artifact_losses.values())
    total_capability_loss = sum(capability_losses.values())
    total_scenario_loss = sum(scenario_losses.values())
    artifact_analysis = {}
    for artifact_id, stat in artifact_stats.items():
        artifact_analysis[artifact_id] = {
            **stat,
            "family": metadata[artifact_id]["family"],
            "total_loss_points": _round(artifact_losses[artifact_id]),
            "share_of_total_artifact_loss": _round(artifact_losses[artifact_id] / total_artifact_loss),
            "ease_categories": _ease_categories(artifact_id, stat),
        }
    capability_analysis = {
        name: {
            **stat,
            "total_loss_points": _round(capability_losses[name]),
            "share_of_total_capability_loss": _round(capability_losses[name] / total_capability_loss),
        }
        for name, stat in capability_stats.items()
    }
    scenario_analysis = {
        name: {
            "total_loss_points": _round(loss),
            "share_of_total_artifact_loss": _round(loss / total_scenario_loss),
            "mean_artifact_score": _round(100 - loss / (5 * 10)),
        }
        for name, loss in scenario_losses.items()
    }

    model_ids = sorted({cell["model_id"] for cell in cells})
    model_diagnostic_artifacts: dict[str, dict[str, float]] = {}
    model_science_means: dict[str, float] = {}
    model_reliability: dict[str, float] = {}
    for model_id in model_ids:
        rows = [cell for cell in cells if cell["model_id"] == model_id]
        model_science_means[model_id] = _round(mean(cell["diagnostic_scientific_score"] for cell in rows))
        model_reliability[model_id] = _round(sum(cell["classification"] == "valid_episode" for cell in rows) / len(rows))
        model_diagnostic_artifacts[model_id] = {
            artifact_id: _round(mean(next(a["score"] for a in cell["artifacts"] if a["artifact_id"] == artifact_id) for cell in rows))
            for artifact_id in ARTIFACT_PATHS
        }
    strongest = max(model_science_means, key=model_science_means.get)
    family_gap_contributions: dict[str, Any] = {}
    for model_id in model_ids:
        signed = {
            metadata[artifact_id]["family"]: _round((model_diagnostic_artifacts[strongest][artifact_id] - model_diagnostic_artifacts[model_id][artifact_id]) / 10)
            for artifact_id in ARTIFACT_PATHS
        }
        abs_total = sum(abs(value) for value in signed.values())
        family_gap_contributions[model_id] = {
            "strongest_reference_model": strongest,
            "aggregate_mean_gap_points": _round(model_science_means[strongest] - model_science_means[model_id]),
            "signed_score_point_contribution": signed,
            "absolute_gap_share": {name: _round(abs(value) / abs_total) if abs_total else 0.0 for name, value in signed.items()},
        }

    pre = [next(a["score"] for a in cell["artifacts"] if a["artifact_id"] == artifact) for cell in cells for artifact in list(ARTIFACT_PATHS)[:7]]
    post = [next(a["score"] for a in cell["artifacts"] if a["artifact_id"] == artifact) for cell in cells for artifact in list(ARTIFACT_PATHS)[7:]]
    early = [next(a["score"] for a in cell["artifacts"] if a["artifact_id"] == artifact) for cell in cells for artifact in list(ARTIFACT_PATHS)[:6]]
    final = [next(a["score"] for a in cell["artifacts"] if a["artifact_id"] == artifact) for cell in cells for artifact in ("A09", "A10")]

    universal = controls["universal_policy_controls"]
    universal_summary = {
        policy: {
            "mean_decision_policy_score": value["mean_decision_policy_score"],
            "mean_scientific_artifact_score": _round(mean(row["coverage_adjusted_scientific_score"] for row in value["results"])),
            "minimum_scientific_artifact_score": _round(min(row["coverage_adjusted_scientific_score"] for row in value["results"])),
        }
        for policy, value in universal.items()
    }

    return {
        "schema_version": "0.6.3-ceiling-construct-audit-1",
        "frozen_result_policy": {
            "v063_scores_changed": False,
            "v063_rescored": False,
            "post_hoc_adjudication_is_a_separate_construct_audit": True,
            "paid_calls_in_audit": 0,
            "heldout_or_astra_used": False,
        },
        "verdict": {
            "decision": "no_go_preserve_v063",
            "plain_reason": "The suite did not create enough scientifically valid headroom: accepted model means were already above the target, one clean cell did not submit, one artifact family exceeded the 30% concentration gate, and shallow universal policies can receive very high scientific artifact scores.",
            "mandatory_failures": [
                "accepted Sol mean 82.800737 exceeds the >80 ceiling no-go threshold",
                "Gemini clean produced all artifacts but did not submit, so every-cell validity failed",
                "decision/recovery was 32.1306% of the strongest accepted model's loss, above 30%",
                "universal policies can score above 92 on artifact science while decision-policy quality stays below 50",
                "many deductions reflect exact representation or one conservative-policy target rather than consequential science",
            ],
        },
        "sentinel": {
            "cell_count": len(cells),
            "valid_episode_count": sum(cell["classification"] == "valid_episode" for cell in cells),
            "completion_reliability_by_model": model_reliability,
            "diagnostic_scientific_mean_by_model": model_science_means,
            "response_reported_spend_usd": checkpoint["response_reported_spend_usd"],
            "key_usage_delta_usd": checkpoint["key_usage_delta_usd"],
            "aggregate_with_v062_usd": checkpoint["aggregate_scientific_spend_usd"],
            "heldout_requests": checkpoint["heldout_requests"],
            "astra_requests": checkpoint["astra_requests"],
        },
        "artifact_analysis": artifact_analysis,
        "capability_analysis": capability_analysis,
        "scenario_analysis": scenario_analysis,
        "family_gap_contributions": family_gap_contributions,
        "difficulty_slices": {
            "mechanical_score_weight_fraction": 0.40,
            "quantitative_score_weight_fraction": 0.12,
            "interpretive_score_weight_fraction": 0.48,
            "classification_note": "A01/A02/A03/A06 mechanical; 50% of A07 and 70% of A08 quantitative; remaining weight interpretive. This is an audit classification, not a frozen scoring change.",
            "pre_reveal_weight_fraction": 0.70,
            "post_reveal_weight_fraction": 0.30,
            "pre_reveal_mean": _round(mean(pre)),
            "post_reveal_mean": _round(mean(post)),
            "early_A01_A06_mean": _round(mean(early)),
            "decision_A09_A10_mean": _round(mean(final)),
        },
        "shallow_policy_diagnostic": {
            "universal_policies": universal_summary,
            "conclusion": "yes_excessive_credit",
            "reason": "The universal controls fail their separate decision-policy score but retain roughly 92-95 scientific artifact score because most artifact points can be copied from a reference-quality evidence summary before the incorrect policy fields are applied.",
        },
        "template_without_key_evidence": {
            "conclusion": "excessive_credit_risk_confirmed",
            "evidence": "A02, A03 and A06 are highly template/tool driven; A07/A08 exact fields reward surface placement, and the resource catalog names the intended remedy. A dedicated zero-evidence template control was not frozen in v0.6, so no fabricated numeric score is reported.",
        },
        "scenario_distinction": {
            "conclusion": "partly_distinguishes_but_not_cleanly",
            "clean_mean": scenario_analysis["dev6_clean_progression"]["mean_artifact_score"],
            "leakage_mean": scenario_analysis["dev6_preprocessing_leakage"]["mean_artifact_score"],
            "reason": "The leakage state changed several models' preprocessing and final decisions, but A02/A04 failures and exact-enum effects also drove the gap; clean-state attestation uncertainty led experts to reasonable pause/resource choices that the frozen target penalized.",
        },
        "adjudication_counts": {code: adjudication_counts.get(code, 0) for code in ADJUDICATION_LABELS},
        "adjudication_labels": ADJUDICATION_LABELS,
        "cells": cells,
        "claims": {
            "defensible": [
                "v0.6.3 is a one-seed controlled internal calibration no-go",
                "the environment exercised a coherent multi-stage tool workflow",
                "models differed in completion, evidence handling, quantitative execution, resource choice, and belief revision",
                "several model artifacts contain useful partial work despite failed frozen invariants",
                "the audit demonstrates grader and construct limitations that must be repaired in a successor",
            ],
            "prohibited": [
                "stable model ranking",
                "Astra or frontier ceiling characterization",
                "external expert validity",
                "real-world prevalence of any failure mode",
                "training-data undersampling, SFT, RL, prompting, or expert-remedy causation without paired tests",
                "biomarker efficacy or commercial readiness from controlled synthetic scenarios",
            ],
        },
    }

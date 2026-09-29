"""Consequence-based deterministic grading for the v0.7 vertical environment."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from typing import Any

from uc_bench.v07_cases import PUBLIC_ROOT, RESOURCE_CATALOG, load_truth

CHECKPOINT_WEIGHTS = {"C1": 15, "C2": 20, "C3": 25, "C4": 20, "C5": 20}

CONCEPT_ALIASES = {
    "signal_supported": {"signal_supported", "credible_prognostic_signal", "criteria_met"},
    "minor_execution_uncertainty": {
        "minor_execution_uncertainty",
        "unverified_execution_detail",
        "residual_provenance_uncertainty",
    },
    "patient_dependence": {
        "patient_dependence",
        "repeated_measures",
        "pseudoreplication",
        "biopsy_dependence",
    },
    "site_confounding": {
        "site_confounding",
        "site_mix",
        "site_dependent_performance",
        "site_shift",
    },
    "preprocessing_fit_scope": {
        "preprocessing_fit_scope",
        "reference_fit_scope",
        "fit_membership_error",
    },
    "validation_information_leakage": {
        "validation_information_leakage",
        "preprocessing_leakage",
        "outcome_informed_preprocessing",
        "data_leakage",
    },
    "miscalibration": {"miscalibration", "calibration_failure", "probability_miscalibration"},
    "negative_threshold_utility": {
        "negative_threshold_utility",
        "threshold_harm",
        "negative_net_benefit",
        "poor_decision_value",
    },
}

METHOD_ALIASES = {
    "cluster_bootstrap",
    "patient_bootstrap",
    "site_stratified_cluster_bootstrap",
    "cluster_robust",
    "bayesian_hierarchical",
    "site_stratified_bayesian",
    "delong_patient_level",
}

METRIC_ALIASES = {
    "auc": {"auc", "roc_auc", "patient_auc"},
    "auc_ci_low": {"auc_ci_low", "auc_lower", "ci_lower", "lower_95"},
    "brier": {"brier", "brier_score"},
    "ece": {"ece", "expected_calibration_error", "calibration_error"},
    "net_benefit": {"net_benefit", "decision_net_benefit", "threshold_utility"},
    "naive_row_auc": {"naive_row_auc", "biopsy_auc", "row_auc"},
    "site_weighted_auc": {"site_weighted_auc", "within_site_auc", "stratified_auc"},
    "worst_site_auc": {"worst_site_auc", "minimum_site_auc"},
}


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def _walk(value: Any) -> Iterable[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield _norm(key), child
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _first(payload: Any, aliases: Iterable[str], default: Any = None) -> Any:
    wanted = {_norm(alias) for alias in aliases}
    for key, value in _walk(payload):
        if key in wanted and not isinstance(value, (dict, list)):
            return value
    return default


def _list(payload: Any, aliases: Iterable[str]) -> list[Any]:
    wanted = {_norm(alias) for alias in aliases}
    for key, value in _walk(payload):
        if key in wanted:
            if isinstance(value, list):
                return value
            if value is None:
                return []
            return [value]
    return []


def _bool(payload: Any, aliases: Iterable[str]) -> bool | None:
    value = _first(payload, aliases)
    if isinstance(value, bool):
        return value
    normalized = _norm(value)
    if normalized in {"true", "yes", "1"}:
        return True
    if normalized in {"false", "no", "0"}:
        return False
    return None


def _float(payload: Any, aliases: Iterable[str]) -> float | None:
    value = _first(payload, aliases)
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _close(observed: float | None, expected: float, tolerance: float) -> float:
    if observed is None:
        return 0.0
    delta = abs(observed - expected)
    if delta <= tolerance:
        return 100.0
    if delta <= tolerance * 2:
        return 50.0
    return 0.0


def _concepts(payload: Any) -> set[str]:
    raw = {
        _norm(value)
        for value in _list(
            payload, {"diagnosed_concepts", "material_findings", "findings", "mechanisms"}
        )
    }
    resolved: set[str] = set()
    for concept, aliases in CONCEPT_ALIASES.items():
        if any(alias in value or value in alias for value in raw for alias in aliases):
            resolved.add(concept)
    for value in raw:
        if (
            "pseudorep" in value
            or "repeated_measure" in value
            or (
                "patient" in value
                and any(token in value for token in ("depend", "repeat", "cluster"))
            )
        ):
            resolved.add("patient_dependence")
        if "site" in value and any(
            token in value for token in ("confound", "mix", "shift", "heterogen", "depend")
        ):
            resolved.add("site_confounding")
        if any(token in value for token in ("preprocess", "normaliz", "reference")) and any(
            token in value for token in ("fit", "scope", "membership")
        ):
            resolved.add("preprocessing_fit_scope")
        if "leak" in value or (
            "validation" in value
            and any(token in value for token in ("fit", "reference", "outcome_inform"))
        ):
            resolved.add("validation_information_leakage")
        if "calibrat" in value and any(
            token in value for token in ("poor", "fail", "mis", "shift", "error")
        ):
            resolved.add("miscalibration")
        if "net_benefit" in value or (
            "threshold" in value and any(token in value for token in ("harm", "utility", "value"))
        ):
            resolved.add("negative_threshold_utility")
        if "signal" in value and any(token in value for token in ("support", "credible", "valid")):
            resolved.add("signal_supported")
        if any(token in value for token in ("execution", "provenance")) and any(
            token in value for token in ("minor", "residual", "uncertain", "unverified")
        ):
            resolved.add("minor_execution_uncertainty")
    return resolved


def _decisions(payload: Any, aliases: Iterable[str]) -> set[str]:
    value = _first(payload, aliases)
    if value is None:
        return set()
    normalized = _norm(value)
    if "conditional" in normalized and "advance" in normalized:
        return {"conditional_advance"}
    if "insufficient" in normalized or "abstain" in normalized:
        return {"insufficient_evidence"}
    for decision in ("advance", "pause", "stop"):
        if decision in normalized:
            return {decision}
    return {normalized}


def _belief_matches(observed: str, expected: str) -> bool:
    if observed == expected:
        return True
    if expected == "unchanged_supported":
        return any(token in observed for token in ("unchanged", "stable")) and "support" in observed
    if expected == "modest_increase":
        return any(token in observed for token in ("increase", "strengthen"))
    if expected == "decrease_site_blocker_remains":
        return (
            any(token in observed for token in ("decrease", "weaken"))
            and "site" in observed
            and any(token in observed for token in ("remain", "unresolved", "block"))
        )
    if expected == "large_decrease":
        return any(token in observed for token in ("decrease", "collapse", "weaken", "downgrade"))
    if expected == "increase_after_valid_replay":
        return any(token in observed for token in ("increase", "strengthen", "recover")) and any(
            token in observed for token in ("replay", "clean", "valid")
        )
    if expected == "decrease_utility_concern_confirmed":
        return any(token in observed for token in ("decrease", "weaken", "downgrade")) and any(
            token in observed for token in ("utility", "calibrat", "harm", "net_benefit")
        )
    return False


def _claim_concepts(values: Iterable[Any]) -> set[str]:
    resolved: set[str] = set()
    for raw in values:
        value = _norm(raw)
        if value in {
            "research_use_prognostic_validation",
            "naive_row_performance_not_decision_valid",
            "original_validation_invalid",
            "ranking_signal_only",
            "treatment_effect",
            "clinical_utility_proven",
            "all_platforms",
            "independent_validation_passed",
            "safe_threshold_use",
        }:
            resolved.add(value)
        if (
            "research" in value
            and "prognostic" in value
            and any(token in value for token in ("valid", "support"))
        ):
            resolved.add("research_use_prognostic_validation")
        if any(token in value for token in ("row", "biopsy")) and any(
            token in value for token in ("invalid", "mislead", "not_decision")
        ):
            resolved.add("naive_row_performance_not_decision_valid")
        if (
            "original" in value
            and "validation" in value
            and any(token in value for token in ("invalid", "ineligible", "contaminat"))
        ):
            resolved.add("original_validation_invalid")
        if "ranking" in value and any(token in value for token in ("only", "signal")):
            resolved.add("ranking_signal_only")
        if "treatment_effect" in value or ("causal" in value and "treatment" in value):
            resolved.add("treatment_effect")
        if "clinical_utility" in value and any(
            token in value for token in ("proven", "establish", "validated")
        ):
            resolved.add("clinical_utility_proven")
        if "all_platform" in value or "platform_invariant" in value:
            resolved.add("all_platforms")
        if "independent_validation" in value and any(
            token in value for token in ("pass", "valid", "establish")
        ):
            resolved.add("independent_validation_passed")
        if "threshold" in value and any(token in value for token in ("safe", "deploy", "use")):
            resolved.add("safe_threshold_use")
    return resolved


def _citations(payload: Any) -> set[str]:
    return {str(value) for value in _list(payload, {"evidence_refs", "evidence_paths", "sources"})}


def _citation_score(payload: Any, expected_fragments: Iterable[str]) -> float:
    citations = _citations(payload)
    expected = list(expected_fragments)
    if not expected:
        return 100.0
    hits = sum(any(fragment in citation for citation in citations) for fragment in expected)
    return 100 * hits / len(expected)


@dataclass(frozen=True, slots=True)
class PropertyScore:
    property_id: str
    score: float
    observed: Any
    expected: Any
    consequence: str
    remedy: str


@dataclass(frozen=True, slots=True)
class V07Grade:
    work_quality_score: float
    checkpoint_scores: dict[str, float]
    full_mission_success: bool
    mission_failures: list[str]
    reliability_score: float
    completion_accepted: bool
    first_substantive_divergence: str | None
    property_scores: dict[str, list[dict[str, Any]]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _score_checkpoint(
    checkpoint_id: str,
    rows: list[tuple[str, float, float, Any, Any, str, str]],
) -> tuple[float, list[PropertyScore]]:
    if abs(sum(weight for _, weight, *_ in rows) - 100) > 1e-9:
        raise ValueError(f"Property weights for {checkpoint_id} do not sum to 100")
    properties = [
        PropertyScore(
            property_id=property_id,
            score=round(score, 6),
            observed=observed,
            expected=expected,
            consequence=consequence,
            remedy=remedy,
        )
        for property_id, _, score, observed, expected, consequence, remedy in rows
    ]
    score = sum(weight * value / 100 for _, weight, value, *_ in rows)
    return round(score, 6), properties


def _event_order(submission: dict[str, Any], first: str, second: str) -> bool:
    events = [
        str(row.get("event")) for row in submission.get("event_log", []) if isinstance(row, dict)
    ]
    try:
        return events.index(first) < events.index(second)
    except ValueError:
        return False


def _resource_selected(submission: dict[str, Any], c4: dict[str, Any]) -> str:
    selected = submission.get("selected_resource") or _first(
        c4, {"selected_resource", "resource_id", "purchase"}
    )
    if selected is None:
        return ""
    match = re.search(r"\bX(?:17|24|31|46|58|63)\b", str(selected), flags=re.IGNORECASE)
    if match:
        return match.group(0).upper()
    return "none" if "none" in _norm(selected) or "nothing" in _norm(selected) else str(selected)


def _metric_score(
    c3: dict[str, Any], truth: dict[str, Any]
) -> tuple[float, dict[str, float | None]]:
    tolerances = {
        "auc": 0.025,
        "auc_ci_low": 0.05,
        "brier": 0.025,
        "ece": 0.035,
        "net_benefit": 0.035,
    }
    observed = {
        metric: _float(c3, aliases)
        for metric, aliases in METRIC_ALIASES.items()
        if metric in tolerances
    }
    scores = [
        _close(observed[metric], float(truth["metrics"][metric]), tolerance)
        for metric, tolerance in tolerances.items()
    ]
    return mean(scores), observed


def _replay_metric_score(c5: dict[str, Any], truth: dict[str, Any], mechanism: str) -> float:
    if "replay_metrics" not in truth:
        return 100.0
    expected = truth["replay_metrics"][mechanism]
    observed_auc = _float(c5, {"replay_auc", "clean_auc", "followup_auc"})
    observed_brier = _float(c5, {"replay_brier", "clean_brier", "followup_brier"})
    return mean(
        (
            _close(observed_auc, expected["auc"], 0.03),
            _close(observed_brier, expected["brier"], 0.03),
        )
    )


def grade_submission(
    project_root: Path,
    case_id: str,
    submission: dict[str, Any],
    *,
    mechanism: str = "default",
) -> V07Grade:
    """Grade scientific properties while keeping submission reliability separate."""

    if case_id == "case_03" and mechanism == "default":
        mechanism = "signal_collapses"
    truth = load_truth(project_root, case_id)
    checkpoints = (
        submission.get("checkpoints") if isinstance(submission.get("checkpoints"), dict) else {}
    )
    c1 = checkpoints.get("C1") if isinstance(checkpoints.get("C1"), dict) else {}
    c2 = checkpoints.get("C2") if isinstance(checkpoints.get("C2"), dict) else {}
    c3 = checkpoints.get("C3") if isinstance(checkpoints.get("C3"), dict) else {}
    c4 = checkpoints.get("C4") if isinstance(checkpoints.get("C4"), dict) else {}
    c5 = checkpoints.get("C5") if isinstance(checkpoints.get("C5"), dict) else {}

    concepts = _concepts(c1) | _concepts(c3) | _concepts(c4)
    required = set(truth["required_concepts"])
    analysis_unit = _norm(_first(c1, {"analysis_unit", "unit_of_analysis"}))
    n_patients = _float(c1, {"n_patients", "patient_count", "unique_patients"})
    n_samples = _float(c1, {"n_samples", "sample_count", "eligible_biopsies"})
    harmless = {_norm(value) for value in _list(c1, {"harmless_anomalies", "nonmaterial_findings"})}
    c1_score, c1_properties = _score_checkpoint(
        "C1",
        [
            (
                "patient_analysis_unit",
                20,
                100.0
                if analysis_unit in {"patient", "fingerprint_patient", "source_reconciled_patient"}
                else 0.0,
                analysis_unit,
                "patient",
                "Biopsy rows are treated as independent people.",
                "Patient/visit reconciliation or an analysis-unit checklist.",
            ),
            (
                "patient_count",
                20,
                _close(n_patients, truth["n_patients"], 1),
                n_patients,
                truth["n_patients"],
                "The evidence population is miscounted.",
                "Reconcile patient, biopsy and visit identifiers.",
            ),
            (
                "sample_count",
                10,
                _close(n_samples, truth["n_samples"], 1),
                n_samples,
                truth["n_samples"],
                "Repeated biopsies and eligibility cannot be audited.",
                "Compute row counts from the supplied cohort records.",
            ),
            (
                "dependence_and_site_inspected",
                15,
                100.0
                if _bool(c1, {"dependence_inspected", "repeated_measures_checked"})
                and _bool(c1, {"site_distribution_inspected", "site_checked"})
                else 0.0,
                {
                    "dependence": _bool(c1, {"dependence_inspected", "repeated_measures_checked"}),
                    "site": _bool(c1, {"site_distribution_inspected", "site_checked"}),
                },
                True,
                "Dependence or site imbalance can masquerade as precision or transportability.",
                "Patient-level and site-aware diagnostics.",
            ),
            (
                "endpoint_timing_checked",
                10,
                100.0 if _bool(c1, {"baseline_timing_checked", "endpoint_timing_checked"}) else 0.0,
                _bool(c1, {"baseline_timing_checked", "endpoint_timing_checked"}),
                True,
                "Post-treatment input or mistimed outcomes answer the wrong question.",
                "Patient/visit chronology and endpoint-source review.",
            ),
            (
                "material_concepts_recovered",
                15,
                100 * len(required & concepts) / len(required),
                sorted(concepts),
                sorted(required),
                "The live scientific problem is not contained.",
                "Targeted metadata, statistical, pipeline, or calibration review.",
            ),
            (
                "harmless_anomaly_not_escalated",
                5,
                100.0
                if harmless & set(truth["harmless_anomalies"])
                and not _bool(c1, {"harmless_anomaly_is_blocker"})
                else 0.0,
                sorted(harmless),
                truth["harmless_anomalies"],
                "A harmless imperfection triggers unnecessary delay or spend.",
                "Materiality checklist tied to the intended-use contract.",
            ),
            (
                "traceable_evidence",
                5,
                _citation_score(c1, truth["evidence_path"]["analysis_unit"]),
                sorted(_citations(c1)),
                truth["evidence_path"]["analysis_unit"],
                "The conclusion cannot be replayed from packet evidence.",
                "Cite the specific inspected records.",
            ),
        ],
    )

    method = _norm(_first(c2, {"uncertainty_method", "interval_method", "uncertainty"}))
    planned_metrics = {
        _norm(value) for value in _list(c2, {"metrics", "metric_families", "planned_metrics"})
    }
    required_metrics = {"auc", "brier", "calibration", "net_benefit"}
    planned_hypotheses = _list(c2, {"live_hypotheses", "competing_hypotheses"})
    thresholds = _list(c2, {"decision_thresholds", "advance_criteria", "decision_rules"})
    fit_scope = _norm(_first(c2, {"fit_scope", "preprocessing_fit_scope", "transform_fit_scope"}))
    method_valid = any(accepted in method or method in accepted for accepted in METHOD_ALIASES)
    fit_scope_valid = fit_scope in {
        "training_only",
        "outcome_blind_training_only",
        "locked_replay_training_only",
    } or ("training" in fit_scope and "only" in fit_scope and "outcome" in fit_scope)
    commit_valid = _event_order(submission, "commit_validation_plan", "reveal_validation")
    c2_score, c2_properties = _score_checkpoint(
        "C2",
        [
            (
                "irreversible_pre_reveal_commitment",
                20,
                100.0 if commit_valid else 0.0,
                commit_valid,
                True,
                "Post-reveal flexibility invalidates the validation claim.",
                "Cryptographically lock the analysis before outcome reveal.",
            ),
            (
                "patient_unit_prespecified",
                15,
                100.0
                if _norm(_first(c2, {"analysis_unit", "unit_of_analysis"}))
                in {"patient", "fingerprint_patient", "source_reconciled_patient"}
                else 0.0,
                _first(c2, {"analysis_unit", "unit_of_analysis"}),
                "patient",
                "The committed estimand permits pseudoreplication.",
                "Prespecify patient-level aggregation or a defensible repeated-measures model.",
            ),
            (
                "fit_scope_prespecified",
                15,
                100.0 if fit_scope_valid else 0.0,
                fit_scope,
                "outcome-blind training-only",
                "Validation information can enter preprocessing.",
                "Prespecify fit membership and an outcome-blind replay.",
            ),
            (
                "uncertainty_method_valid",
                15,
                100.0 if method_valid else 0.0,
                method,
                sorted(METHOD_ALIASES),
                "Uncertainty ignores patient or site dependence.",
                "Use a patient-clustered, site-aware, or hierarchical method.",
            ),
            (
                "decision_metrics_prespecified",
                15,
                100 * len(planned_metrics & required_metrics) / len(required_metrics),
                sorted(planned_metrics),
                sorted(required_metrics),
                "AUC can dominate calibration and utility after results are seen.",
                "Prespecify discrimination, calibration and decision utility.",
            ),
            (
                "decision_rule_prespecified",
                10,
                100.0 if thresholds or _bool(c2, {"contract_thresholds_adopted"}) else 0.0,
                thresholds or _bool(c2, {"contract_thresholds_adopted"}),
                "thresholds or explicit contract adoption",
                "The decision rule is selected after viewing results.",
                "Commit threshold and advance/pause/stop rules.",
            ),
            (
                "competing_hypotheses_prespecified",
                10,
                100.0 if len(planned_hypotheses) >= 2 else 0.0,
                planned_hypotheses,
                "at least two live explanations",
                "The first plausible explanation becomes an untested narrative.",
                "Predeclare competing explanations and differentiating results.",
            ),
        ],
    )

    metric_accuracy, observed_metrics = _metric_score(c3, truth)
    dependence_handling = (
        _bool(c3, {"patient_dependence_preserved", "patient_level_analysis"}) is True
    )
    site_handling = _bool(c3, {"site_aware_analysis", "site_sensitivity_performed"}) is True
    if case_id == "case_02":
        naive = _float(c3, METRIC_ALIASES["naive_row_auc"])
        site_auc = _float(c3, METRIC_ALIASES["site_weighted_auc"])
        dependence_specific = (
            mean(
                (
                    _close(naive, truth["metrics"]["naive_row_auc"], 0.03),
                    _close(site_auc, truth["metrics"]["site_weighted_auc"], 0.06),
                )
            )
            if dependence_handling and site_handling
            else 0.0
        )
    else:
        dependence_specific = 100.0 if dependence_handling and site_handling else 0.0
    contaminated_as_valid = _bool(
        c3, {"contaminated_metrics_used_for_decision", "contaminated_evidence_treated_as_valid"}
    )
    contamination_score = 100.0
    if case_id == "case_03":
        contamination_score = 100.0 if contaminated_as_valid is False else 0.0
    integrated = _bool(
        c3, {"discrimination_calibration_utility_integrated", "all_metric_families_interpreted"}
    )
    c3_score, c3_properties = _score_checkpoint(
        "C3",
        [
            (
                "independent_numeric_reproduction",
                50,
                metric_accuracy,
                observed_metrics,
                {key: truth["metrics"][key] for key in observed_metrics},
                "The investment decision rests on unreproduced or wrong numbers.",
                "Independent patient-level calculation with declared tolerances.",
            ),
            (
                "patient_and_site_structure_preserved",
                20,
                dependence_specific,
                {"patient": dependence_handling, "site": site_handling},
                True,
                "Repeated biopsies or site mix inflate performance and precision.",
                "Patient-clustered and site-aware reanalysis.",
            ),
            (
                "uncertainty_matches_plan",
                10,
                100.0 if _bool(c3, {"uncertainty_matches_commitment", "plan_honoured"}) else 0.0,
                _bool(c3, {"uncertainty_matches_commitment", "plan_honoured"}),
                True,
                "The executed analysis silently diverges from the locked plan.",
                "Automated plan-versus-execution comparison.",
            ),
            (
                "contaminated_evidence_contained",
                10,
                contamination_score,
                contaminated_as_valid,
                False if case_id == "case_03" else "not applicable",
                "Contaminated validation evidence is used to advance the asset.",
                "Outcome-blind replay with fit-input provenance.",
            ),
            (
                "metrics_interpreted_together",
                10,
                100.0 if integrated else 0.0,
                integrated,
                True,
                "High discrimination masks miscalibration or harmful threshold behavior.",
                "Joint discrimination, calibration and decision-curve review.",
            ),
        ],
    )

    selected = _resource_selected(submission, c4)
    resource_values = truth["resource_decision_values"]
    best_value = max(resource_values.values())
    selected_value = float(resource_values.get(selected, 0.0))
    value_score = (
        100.0
        if best_value - selected_value <= 0.08
        else max(0.0, 100 * selected_value / best_value - 25)
    )
    observed_action_consistent = selected == _resource_selected(
        {"selected_resource": submission.get("selected_resource")}, {}
    )
    outcomes_mapped = _list(c4, {"possible_results", "decision_changing_outcomes", "outcome_map"})
    alternatives = _list(c4, {"alternatives_compared", "resources_compared"})
    diagnosed = _concepts(c4) | _concepts(c3) | _concepts(c1)
    resource_meta = {row["resource_id"]: row for row in RESOURCE_CATALOG}.get(selected, {})
    spent = submission.get("spent_units")
    budget_ok = (
        isinstance(spent, (int, float)) and spent <= 3 and spent == resource_meta.get("cost_units")
    )
    c4_score, c4_properties = _score_checkpoint(
        "C4",
        [
            (
                "material_diagnosis_supported",
                30,
                100 * len(required & diagnosed) / len(required),
                sorted(diagnosed),
                sorted(required),
                "The follow-up targets the wrong live problem.",
                "Tie each diagnosis to calculations and source evidence.",
            ),
            (
                "competing_explanations_retained",
                15,
                100.0
                if len(_list(c4, {"live_explanations", "competing_explanations"})) >= 2
                else 0.0,
                _list(c4, {"live_explanations", "competing_explanations"}),
                "at least two",
                "Plausible alternatives are collapsed prematurely.",
                "Maintain a hypothesis ledger until distinguishing evidence arrives.",
            ),
            (
                "diagnosis_evidence_trace",
                10,
                _citation_score(
                    c4,
                    truth["evidence_path"]["pipeline_scope"]
                    if case_id == "case_03"
                    else truth["evidence_path"]["quantitative"],
                ),
                sorted(_citations(c4)),
                "case-relevant records",
                "The diagnosis is asserted without replayable evidence.",
                "Cite the calculation and records supporting the mechanism.",
            ),
            (
                "prepurchase_outcome_map",
                15,
                100.0 if len(outcomes_mapped) >= 2 else 0.0,
                outcomes_mapped,
                "at least two result-contingent actions",
                "A resource is bought without knowing how its result changes the decision.",
                "Predeclare result-contingent belief and action updates.",
            ),
            (
                "resource_decision_value",
                20,
                value_score if observed_action_consistent else 0.0,
                {"resource": selected, "decision_value": selected_value},
                {"within": 0.08, "best": best_value},
                "Budget buys reassurance rather than decision-relevant evidence.",
                "Compare resources by the hypotheses and decisions they can change.",
            ),
            (
                "alternatives_and_limits",
                5,
                100.0
                if len(alternatives) >= 3
                and _bool(c4, {"resource_limitations_considered", "limitations_considered"})
                else 0.0,
                alternatives,
                "three comparisons plus limitations",
                "The apparent best option ignores cheaper or more informative alternatives.",
                "Explicit cost, delay and cannot-answer comparison.",
            ),
            (
                "budget_respected",
                5,
                100.0 if budget_ok else 0.0,
                {"spent": spent, "selected": selected},
                "one purchase within 3 units",
                "The episode purchases evidence outside the constrained decision.",
                "Enforce one-purchase budget accounting.",
            ),
        ],
    )
    if selected not in resource_values or not budget_ok:
        # Correct prose about the case cannot compensate for an impossible or
        # over-budget action: the checkpoint is specifically about selecting
        # and committing scarce follow-up resources.
        c4_score = min(c4_score, 40.0)

    expected_final = set(
        truth.get("variant_final_decisions", {}).get(mechanism, truth["final_decisions"])
    )
    final_decision = _decisions(c5, {"final_decision", "decision", "investment_decision"})
    selected_followup = _norm(
        _first(c5, {"resource_interpretation", "observed_effect", "followup_conclusion"})
    )
    if case_id == "case_03":
        expected_direction = truth["variant_belief_directions"][mechanism]
    elif case_id == "case_01":
        expected_direction = "unchanged_supported" if selected == "none" else "modest_increase"
    elif case_id == "case_02":
        expected_direction = "decrease_site_blocker_remains"
    else:
        expected_direction = "decrease_utility_concern_confirmed"
    belief = _norm(_first(c5, {"belief_direction", "belief_update", "posterior_direction"}))
    supported = _claim_concepts(_list(c5, {"supported_claims", "claims_supported"}))
    unsupported = _claim_concepts(_list(c5, {"unsupported_claims", "claims_not_supported"}))
    made = _claim_concepts(_list(c5, {"claims_made", "asserted_claims"}))
    prohibited = set(truth["prohibited_claims"])
    claim_score = mean(
        (
            100.0 if supported & set(truth["supported_claims"]) else 0.0,
            100.0 if prohibited <= unsupported else 0.0,
            100.0 if not (made & prohibited) else 0.0,
        )
    )
    if case_id == "case_01":
        if selected == "none":
            final_metric_score = (
                100.0
                if _bool(c5, {"new_evidence_received", "followup_evidence_received"}) is False
                else 0.0
            )
        else:
            final_metric_score = _close(
                _float(c5, {"followup_auc", "replay_auc"}),
                truth["metrics"]["auc"],
                0.03,
            )
    elif case_id == "case_02":
        final_metric_score = mean(
            (
                _close(
                    _float(c5, {"resolved_patient_count", "reconciled_patient_count"}),
                    truth["n_patients"],
                    1,
                ),
                100.0 if _bool(c5, {"site_blocker_remaining", "site_concern_remaining"}) else 0.0,
            )
        )
    else:
        final_metric_score = _replay_metric_score(c5, truth, mechanism)
    if case_id == "case_04":
        expected_followup = truth["followup_metrics"]
        follow_auc = _float(c5, {"followup_auc", "external_auc"})
        follow_nb = _float(c5, {"followup_net_benefit", "external_net_benefit"})
        final_metric_score = mean(
            (
                _close(follow_auc, expected_followup["auc"], 0.04),
                _close(follow_nb, expected_followup["net_benefit"], 0.04),
            )
        )
    initial = _decisions(c5, {"initial_decision", "pre_followup_decision"})
    c5_score, c5_properties = _score_checkpoint(
        "C5",
        [
            (
                "followup_evidence_analysed",
                15,
                final_metric_score,
                selected_followup or "quantitative values",
                "resource-specific evidence",
                "The purchased result is not independently analysed.",
                "Recalculate the returned evidence using the committed estimand.",
            ),
            (
                "belief_revision_direction",
                20,
                100.0 if _belief_matches(belief, expected_direction) else 0.0,
                belief,
                expected_direction,
                "New evidence is ignored or moves belief in the wrong direction.",
                "Explicit pre/post hypothesis probabilities or ordered beliefs.",
            ),
            (
                "initial_and_final_decisions",
                25,
                mean(
                    (
                        100.0 if initial & set(truth["initial_decisions"]) else 0.0,
                        100.0 if final_decision & expected_final else 0.0,
                    )
                ),
                {"initial": sorted(initial), "final": sorted(final_decision)},
                {"initial": truth["initial_decisions"], "final": sorted(expected_final)},
                "The investment action is unsafe under the complete evidence chain.",
                "Decision review against the committed contract and follow-up result.",
            ),
            (
                "claim_scope",
                25,
                claim_score,
                {
                    "supported": sorted(supported),
                    "unsupported": sorted(unsupported),
                    "made": sorted(made),
                },
                {"supported": truth["supported_claims"], "prohibited": truth["prohibited_claims"]},
                "Commercial or causal claims exceed the validated evidence.",
                "Claim-to-evidence ledger and bounded intended-use language.",
            ),
            (
                "remaining_uncertainty",
                10,
                100.0
                if len(_list(c5, {"remaining_uncertainties", "unresolved_questions"})) >= 1
                else 0.0,
                _list(c5, {"remaining_uncertainties", "unresolved_questions"}),
                "at least one bounded uncertainty",
                "Residual uncertainty is erased by one favorable result.",
                "State what the selected resource could not answer.",
            ),
            (
                "contaminated_evidence_not_revived",
                5,
                100.0
                if not (
                    case_id == "case_03"
                    and _bool(c5, {"original_contaminated_result_used_as_validation"})
                )
                else 0.0,
                _bool(c5, {"original_contaminated_result_used_as_validation"}),
                False,
                "Invalid original evidence re-enters the final claim.",
                "Maintain provenance eligibility through final synthesis.",
            ),
        ],
    )

    checkpoint_scores = {
        "C1": c1_score,
        "C2": c2_score,
        "C3": c3_score,
        "C4": c4_score,
        "C5": c5_score,
    }
    work_quality = sum(
        CHECKPOINT_WEIGHTS[key] * checkpoint_scores[key] / 100 for key in CHECKPOINT_WEIGHTS
    )
    data_grounded = (
        n_patients is not None
        and n_samples is not None
        and sum(value is not None for value in observed_metrics.values()) >= 3
    )
    if not data_grounded:
        # A polished generic memo is not an investigation.  The cap is a
        # consequence of missing patient enumeration and independent numbers,
        # not a formatting or vocabulary penalty.
        work_quality = min(work_quality, 15.0)
    completion = submission.get("completion_accepted") is True
    failures: list[str] = []
    if not commit_valid:
        failures.append("commitment_not_preserved")
    if _bool(c3, {"uncertainty_matches_commitment", "plan_honoured"}) is not True:
        failures.append("execution_diverged_from_commitment")
    if not dependence_handling or not site_handling:
        failures.append("analysis_structure_invalid")
    if c3_score < 65:
        failures.append("decision_relevant_analysis_invalid")
    if case_id == "case_03" and contaminated_as_valid is not False:
        failures.append("contaminated_evidence_used")
    if best_value - selected_value > 0.08:
        failures.append("followup_not_decision_efficient")
    if not final_decision & expected_final:
        failures.append("unsupported_final_decision")
    if made & prohibited or not prohibited <= unsupported:
        failures.append("claim_scope_overstated")
    if min(c1_score, c2_score, c3_score, c4_score) < 65 and (made or supported):
        failures.append("claim_exceeds_weakest_decision_critical_evidence")
    if not _belief_matches(belief, expected_direction):
        failures.append("belief_revision_incorrect")
    if not completion:
        failures.append("submission_not_accepted")
    full_mission = not failures

    property_groups = {
        "C1": [asdict(row) for row in c1_properties],
        "C2": [asdict(row) for row in c2_properties],
        "C3": [asdict(row) for row in c3_properties],
        "C4": [asdict(row) for row in c4_properties],
        "C5": [asdict(row) for row in c5_properties],
    }
    first = next((key for key in CHECKPOINT_WEIGHTS if checkpoint_scores[key] < 90), None)
    return V07Grade(
        work_quality_score=round(work_quality, 6),
        checkpoint_scores=checkpoint_scores,
        full_mission_success=full_mission,
        mission_failures=failures,
        reliability_score=round(work_quality if completion else 0.0, 6),
        completion_accepted=completion,
        first_substantive_divergence=first,
        property_scores=property_groups,
    )


def validate_public_packet_has_no_truth_labels(project_root: Path, case_id: str) -> list[str]:
    root = project_root.resolve() / PUBLIC_ROOT / case_id
    forbidden = {
        "leakage_status",
        "identity_blocked",
        "optimal_resource",
        "scenario_class",
        "expected_decision",
        "planted_truth",
        "preferred_resource",
    }
    violations: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8").lower()
        for token in forbidden:
            if token in text:
                violations.append(f"{path.relative_to(root)}:{token}")
    return violations

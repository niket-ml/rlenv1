"""Deterministic explicit-field grader for the v0.7.2 interface repair."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from typing import Any

from uc_bench.hashing import canonical_sha256
from uc_bench.v07_cases import RESOURCE_CATALOG, load_truth
from uc_bench.v07_grader import CHECKPOINT_WEIGHTS
from uc_bench.v072_artifacts import (
    ArtifactVerification,
    recompute_followup_artifact,
    verify_v072_artifacts,
)
from uc_bench.v072_schema import SchemaIssue, normalize_submission

_TOLERANCES = {
    "auc": 0.025,
    "auc_ci_low": 0.05,
    "brier": 0.025,
    "ece": 0.035,
    "net_benefit": 0.035,
}
_INFRASTRUCTURE_CLASSES = {
    "infrastructure_failure",
    "provider_adapter_failure",
    "provider_policy_refusal",
    "unknown_harness_failure",
}


def _event_payload_digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class PropertyScore:
    property_id: str
    score: float
    observed: Any
    expected: Any
    consequence: str
    remedy: str


@dataclass(frozen=True, slots=True)
class V072Grade:
    scientific_work_quality_score: float | None
    work_quality_score: float | None
    checkpoint_scores: dict[str, float] | None
    strict_full_mission_success: bool | None
    full_mission_success: bool | None
    mission_failures: list[str]
    environment_reliability_status: dict[str, Any]
    reliability_score: float | None
    completion_accepted: bool
    first_substantive_divergence: str | None
    first_decision_critical_failure: dict[str, Any] | None
    downstream_consequences: list[str]
    failure_taxonomy: dict[str, Any]
    property_scores: dict[str, list[dict[str, Any]]]
    schema_issues: list[dict[str, str]]
    scientific_errors: list[str]
    event_facts: dict[str, Any]
    event_action_disagreements: list[str]
    evidence_support: dict[str, dict[str, Any]]
    artifact_verification: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _close(observed: float | None, expected: float, tolerance: float) -> float:
    if observed is None:
        return 0.0
    delta = abs(observed - expected)
    if delta <= tolerance:
        return 100.0
    if delta <= tolerance * 2:
        return 50.0
    return 0.0


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
    result = sum(weight * score / 100 for _, weight, score, *_ in rows)
    return round(result, 6), properties


def _validated_events(submission: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    raw = submission.get("event_log")
    if not isinstance(raw, list):
        return [], ["event_log_missing_or_not_array"]
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    previous = 0
    for index, row in enumerate(raw):
        if not isinstance(row, dict) or not isinstance(row.get("event"), str):
            errors.append(f"event_{index + 1}_invalid")
            continue
        sequence = row.get("sequence")
        if not isinstance(sequence, int) or sequence <= previous:
            errors.append(f"event_{index + 1}_sequence_invalid")
            continue
        previous = sequence
        rows.append(row)
    return rows, errors


def _event_facts(submission: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    events, errors = _validated_events(submission)
    by_name: dict[str, list[dict[str, Any]]] = {}
    for row in events:
        by_name.setdefault(str(row["event"]), []).append(row)

    def position(name: str) -> int | None:
        rows = by_name.get(name) or []
        return int(rows[0]["sequence"]) if rows else None

    commits = by_name.get("commit_validation_plan") or []
    reveals = by_name.get("reveal_validation") or []
    purchases = by_name.get("purchase_resource") or []
    submits = by_name.get("submit") or []
    commit_sequence = position("commit_validation_plan")
    reveal_sequence = position("reveal_validation")
    purchase_sequence = position("purchase_resource")
    submit_sequence = position("submit")
    commit_before_reveal = (
        len(commits) == 1
        and len(reveals) == 1
        and commit_sequence is not None
        and reveal_sequence is not None
        and commit_sequence < reveal_sequence
    )
    c4_saves = [
        row for row in by_name.get("save_checkpoint", []) if str(row.get("checkpoint")) == "C4"
    ]
    c4_before_purchase = bool(
        c4_saves
        and purchase_sequence is not None
        and int(c4_saves[-1]["sequence"]) < purchase_sequence
    )
    purchase = purchases[0] if len(purchases) == 1 else {}
    selected = purchase.get("resource_id") if isinstance(purchase.get("resource_id"), str) else None
    cost = purchase.get("cost_units")
    if len(commits) != 1:
        errors.append("commit_event_count_not_one")
    if len(reveals) != 1:
        errors.append("reveal_event_count_not_one")
    if len(purchases) != 1:
        errors.append("purchase_event_count_not_one")
    if len(submits) > 1:
        errors.append("submit_event_count_above_one")
    checkpoints = submission.get("checkpoints")
    checkpoints = checkpoints if isinstance(checkpoints, dict) else {}
    digest_mismatches: list[str] = []
    for row in by_name.get("save_checkpoint", []):
        checkpoint = row.get("checkpoint")
        payload = checkpoints.get(checkpoint) if isinstance(checkpoint, str) else None
        if not isinstance(payload, dict) or row.get("digest") != _event_payload_digest(payload):
            digest_mismatches.append(str(checkpoint))
    if len(commits) == 1:
        payload = checkpoints.get("C2")
        if not isinstance(payload, dict) or commits[0].get("digest") != _event_payload_digest(
            payload
        ):
            digest_mismatches.append("C2")
        if len(reveals) == 1 and reveals[0].get("committed_plan_hash") != commits[0].get("digest"):
            errors.append("reveal_commit_hash_mismatch")
        if len(submits) == 1 and submits[0].get("committed_plan_hash") != commits[0].get("digest"):
            errors.append("submit_commit_hash_mismatch")
    if digest_mismatches:
        errors.append("checkpoint_event_digest_mismatch:" + ",".join(sorted(digest_mismatches)))
    return {
        "event_count": len(events),
        "commit_before_reveal": commit_before_reveal,
        "commit_sequence": commit_sequence,
        "reveal_sequence": reveal_sequence,
        "c4_saved_before_purchase": c4_before_purchase,
        "purchase_sequence": purchase_sequence,
        "selected_resource": selected,
        "spent_units": cost,
        "submission_sequence": submit_sequence,
        "completion_accepted": len(submits) == 1,
        "checkpoint_event_digests_match": not digest_mismatches,
        "tool_events": [row for row in events if str(row["event"]).startswith("tool_")],
    }, errors


def _evidence_score(
    checkpoint: dict[str, Any], conclusion_id: str, expected_fragments: list[str]
) -> tuple[float, dict[str, Any]]:
    references = checkpoint.get("evidence_refs", {}).get(conclusion_id, [])
    if not isinstance(references, list):
        references = []
    hits = [
        fragment for fragment in expected_fragments if any(fragment in ref for ref in references)
    ]
    score = 100.0 if not expected_fragments else 100 * len(hits) / len(expected_fragments)
    return score, {
        "references": references,
        "expected_fragments": expected_fragments,
        "supported_fragments": hits,
        "supported": score == 100.0,
    }


def _metric_accuracy(
    c2: dict[str, Any], c3: dict[str, Any], truth: dict[str, Any], artifacts: ArtifactVerification
) -> tuple[float, dict[str, float | None]]:
    declared = set(c2["validation_plan"]["primary_metric_ids"])
    submitted = c3["primary_metrics"]
    observed: dict[str, float | None] = {}
    scores: list[float] = []
    for metric, tolerance in _TOLERANCES.items():
        controlling_metric = "auc" if metric == "auc_ci_low" else metric
        value = submitted.get(metric) if controlling_metric in declared else None
        observed[metric] = value
        recomputed = artifacts.recomputed_primary_metrics.get(metric)
        supported = (
            artifacts.usable
            and artifacts.reported_metric_matches.get(metric) is True
            and artifacts.calculated_output_matches.get(metric) is True
        )
        scores.append(
            _close(recomputed, float(truth["metrics"][metric]), tolerance)
            if controlling_metric in declared and supported
            else 0.0
        )
    return mean(scores), observed


def _resource_score(selected: str | None, truth: dict[str, Any]) -> tuple[float, float, float]:
    values = truth["resource_decision_values"]
    best = max(float(value) for value in values.values())
    selected_value = float(values.get(selected, 0.0))
    score = 100.0 if best - selected_value <= 0.08 else max(0.0, 100 * selected_value / best - 25)
    return score, selected_value, best


def _followup_score(
    case_id: str,
    mechanism: str,
    selected: str | None,
    c5: dict[str, Any],
    truth: dict[str, Any],
    independently_recomputed: dict[str, Any],
) -> float:
    analysis = c5["investigation_analysis"]
    if independently_recomputed.get("usable") is not True:
        return 0.0
    values = independently_recomputed.get("calculated_values") or {}
    for metric, value in values.items():
        submitted = analysis["calculated_values"].get(metric)
        if submitted is None or abs(float(submitted) - float(value)) > 0.001:
            return 0.0
    if case_id == "case_01":
        if selected == "none":
            return (
                100.0
                if analysis["new_evidence_received"] is False
                and independently_recomputed.get("new_evidence_received") is False
                else 0.0
            )
        return _close(values.get("auc"), float(truth["metrics"]["auc"]), 0.03)
    if case_id == "case_02":
        return mean(
            (
                _close(
                    independently_recomputed.get("resolved_patient_count"),
                    float(truth["n_patients"]),
                    1,
                )
                if analysis["resolved_patient_count"]
                == independently_recomputed.get("resolved_patient_count")
                else 0.0,
                100.0 if analysis["site_blocker_remaining"] is True else 0.0,
            )
        )
    if case_id == "case_03":
        expected = truth["replay_metrics"][mechanism]
        return mean(
            (
                _close(values.get("auc"), float(expected["auc"]), 0.03),
                _close(values.get("brier"), float(expected["brier"]), 0.03),
            )
        )
    expected = truth["followup_metrics"]
    return mean(
        (
            _close(values.get("auc"), float(expected["auc"]), 0.04),
            _close(values.get("net_benefit"), float(expected["net_benefit"]), 0.04),
        )
    )


def _reliability(
    *,
    classification: str,
    completion: bool,
    schema_issues: list[SchemaIssue],
    event_errors: list[str],
    parsing_errors: list[str],
    score: float,
) -> tuple[dict[str, Any], float | None]:
    if classification in _INFRASTRUCTURE_CLASSES:
        return {
            "status": classification,
            "scientific_score_reportable": False,
            "schema_valid": not schema_issues,
            "parsing_valid": not parsing_errors,
            "event_record_valid": not event_errors,
            "provider_failure": classification
            in {"provider_adapter_failure", "provider_policy_refusal"},
            "infrastructure_failure": classification
            in {"infrastructure_failure", "unknown_harness_failure"},
            "errors": [*parsing_errors, *event_errors],
        }, None
    if not completion:
        status = "usable_unsubmitted_attempt"
        reliability_score = 0.0
    elif parsing_errors:
        status = "parsing_failure"
        reliability_score = 0.0
    elif event_errors:
        status = "event_record_failure"
        reliability_score = 0.0
    elif schema_issues:
        status = "schema_nonconformant_usable"
        reliability_score = score
    else:
        status = "valid_episode"
        reliability_score = score
    return {
        "status": status,
        "scientific_score_reportable": True,
        "schema_valid": not schema_issues,
        "parsing_valid": not parsing_errors,
        "event_record_valid": not event_errors,
        "provider_failure": False,
        "infrastructure_failure": False,
        "errors": [*parsing_errors, *event_errors],
    }, reliability_score


_DECISION_CRITICAL_PROPERTIES = {
    "C1": {
        "patient_analysis_unit",
        "patient_count",
        "dependence_and_site_inspected",
        "endpoint_timing_checked",
        "material_concepts_recovered",
    },
    "C2": {
        "irreversible_pre_reveal_commitment",
        "patient_unit_prespecified",
        "fit_scope_prespecified",
        "uncertainty_method_valid",
        "decision_metrics_prespecified",
        "decision_rule_prespecified",
        "competing_hypotheses_prespecified",
    },
    "C3": {
        "independent_numeric_reproduction",
        "patient_and_site_structure_preserved",
        "uncertainty_matches_plan",
        "contaminated_evidence_contained",
        "metrics_interpreted_together",
    },
    "C4": {
        "material_diagnosis_supported",
        "competing_explanations_retained",
        "prepurchase_outcome_map",
        "resource_decision_value",
        "budget_respected",
    },
    "C5": {
        "followup_evidence_analysed",
        "belief_revision_direction",
        "initial_and_final_decisions",
        "claim_scope",
        "contaminated_evidence_not_revived",
    },
}

_DOWNSTREAM_BY_CHECKPOINT = {
    "C1": [
        "The validation estimand and dependence structure may be wrong.",
        "Later performance and transportability claims require conditional review.",
    ],
    "C2": [
        "Confirmatory validation cannot support the intended decision without a valid locked plan.",
        "Later metric, resource, and final-decision claims remain diagnostic only.",
    ],
    "C3": [
        "The selected follow-up may target an invalid performance diagnosis.",
        "The final diligence decision cannot rely on the affected validation evidence.",
    ],
    "C4": [
        "The purchased evidence may not distinguish the live hypotheses or justify its cost.",
        "Final belief revision must be interpreted conditional on an inefficient investigation.",
    ],
    "C5": [
        "The final claim or investment action is not supported by the completed evidence chain.",
    ],
}


def _first_decision_failure(
    property_groups: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, Any] | None, list[str]]:
    for checkpoint in CHECKPOINT_WEIGHTS:
        for row in property_groups[checkpoint]:
            if (
                row["property_id"] in _DECISION_CRITICAL_PROPERTIES[checkpoint]
                and float(row["score"]) < 100
            ):
                return {
                    "checkpoint": checkpoint,
                    "property_id": row["property_id"],
                    "score": row["score"],
                    "observed": row["observed"],
                    "expected": row["expected"],
                    "trace_evidence": {
                        "property_score": (f"property_scores.{checkpoint}.{row['property_id']}"),
                        "consequence": row["consequence"],
                        "remedy": row["remedy"],
                    },
                }, list(_DOWNSTREAM_BY_CHECKPOINT[checkpoint])
    return None, []


def grade_v072_submission(
    project_root: Path,
    case_id: str,
    submission: dict[str, Any],
    *,
    mechanism: str = "default",
    execution_classification: str = "valid_episode",
    parsing_errors: list[str] | None = None,
    workspace_root: Path | None = None,
) -> V072Grade:
    """Grade exact fields and event facts without reading explanatory prose."""

    parsing_errors = list(parsing_errors or [])
    if case_id == "case_03" and mechanism == "default":
        mechanism = "signal_collapses"
    truth = load_truth(project_root, case_id)
    checkpoints, schema_issues = normalize_submission(submission)
    c1, c2, c3, c4, c5 = (checkpoints[key] for key in CHECKPOINT_WEIGHTS)
    events, event_errors = _event_facts(submission)
    evidence_support: dict[str, dict[str, Any]] = {}
    artifacts = verify_v072_artifacts(
        workspace_root,
        c2,
        c3,
    )

    required = set(truth["required_concepts"])
    diagnosed = (
        set(c1["findings"]["diagnosed_concepts"])
        | set(c3["diagnosed_concepts"])
        | set(c4["diagnosed_concepts"])
    )
    evidence_score, evidence_support["C1.analysis_unit"] = _evidence_score(
        c1, "analysis_unit", list(truth["evidence_path"]["analysis_unit"])
    )
    c1_score, c1_properties = _score_checkpoint(
        "C1",
        [
            (
                "patient_analysis_unit",
                20,
                100.0 if c1["analysis_unit"]["level"] == "PATIENT" else 0.0,
                c1["analysis_unit"],
                "PATIENT",
                "Biopsy rows are treated as independent people.",
                "Patient/visit reconciliation or an analysis-unit checklist.",
            ),
            (
                "patient_count",
                20,
                _close(c1["cohort_counts"]["patient_count"], truth["n_patients"], 1),
                c1["cohort_counts"]["patient_count"],
                truth["n_patients"],
                "The evidence population is miscounted.",
                "Reconcile patient, biopsy and visit identifiers.",
            ),
            (
                "sample_count",
                10,
                _close(c1["cohort_counts"]["sample_count"], truth["n_samples"], 1),
                c1["cohort_counts"]["sample_count"],
                truth["n_samples"],
                "Repeated biopsies and eligibility cannot be audited.",
                "Compute row counts from the supplied cohort records.",
            ),
            (
                "dependence_and_site_inspected",
                15,
                100.0
                if c1["checks"]["dependence_inspected"] is True
                and c1["checks"]["site_distribution_inspected"] is True
                else 0.0,
                c1["checks"],
                True,
                "Dependence or site imbalance can masquerade as precision or transportability.",
                "Patient-level and site-aware diagnostics.",
            ),
            (
                "endpoint_timing_checked",
                10,
                100.0 if c1["checks"]["endpoint_timing_checked"] is True else 0.0,
                c1["checks"]["endpoint_timing_checked"],
                True,
                "Post-treatment input or mistimed outcomes answer the wrong question.",
                "Patient/visit chronology and endpoint-source review.",
            ),
            (
                "material_concepts_recovered",
                15,
                100 * len(required & diagnosed) / len(required),
                sorted(diagnosed),
                sorted(required),
                "The live scientific problem is not contained.",
                "Targeted metadata, statistical, pipeline, or calibration review.",
            ),
            (
                "harmless_anomaly_not_escalated",
                5,
                100.0
                if set(c1["findings"]["nonmaterial_findings"]) & set(truth["harmless_anomalies"])
                and c1["findings"]["nonmaterial_finding_is_blocker"] is False
                else 0.0,
                c1["findings"],
                truth["harmless_anomalies"],
                "A harmless imperfection triggers unnecessary delay or spend.",
                "Materiality checklist tied to the intended-use contract.",
            ),
            (
                "traceable_evidence",
                5,
                evidence_score,
                evidence_support["C1.analysis_unit"]["references"],
                truth["evidence_path"]["analysis_unit"],
                "The conclusion cannot be replayed from packet evidence.",
                "Cite the specific inspected records.",
            ),
        ],
    )

    plan = c2["validation_plan"]
    primary_ids = set(plan["primary_metric_ids"])
    fit_valid = (
        plan["preprocessing"]["fit_scope"] in {"TRAINING_ONLY", "LOCKED_TRAINING_ONLY"}
        and plan["preprocessing"]["outcome_blind"] is True
    )
    uncertainty_valid = (
        isinstance(plan["uncertainty"]["method"], str)
        and bool(plan["uncertainty"]["method"].strip())
        and plan["uncertainty"]["preserves_patient_dependence"] is True
        and plan["uncertainty"]["site_aware"] is True
        and isinstance(plan["uncertainty"]["random_seed"], int)
        and isinstance(plan["uncertainty"]["bootstrap_replicates"], int)
    )
    commit_valid = events["commit_before_reveal"]
    c2_score, c2_properties = _score_checkpoint(
        "C2",
        [
            (
                "irreversible_pre_reveal_commitment",
                20,
                100.0 if commit_valid else 0.0,
                events,
                True,
                "Post-reveal flexibility invalidates the validation claim.",
                "Cryptographically lock the analysis before outcome reveal.",
            ),
            (
                "patient_unit_prespecified",
                15,
                100.0 if plan["analysis_unit"]["level"] == "PATIENT" else 0.0,
                plan["analysis_unit"],
                "PATIENT",
                "The committed estimand permits pseudoreplication.",
                "Prespecify patient aggregation or a defensible repeated-measures model.",
            ),
            (
                "fit_scope_prespecified",
                15,
                100.0 if fit_valid else 0.0,
                plan["preprocessing"],
                "outcome-blind training-only",
                "Validation information can enter preprocessing.",
                "Prespecify fit membership and an outcome-blind replay.",
            ),
            (
                "uncertainty_method_valid",
                15,
                100.0 if uncertainty_valid else 0.0,
                plan["uncertainty"],
                "patient-dependent and site-aware method",
                "Uncertainty ignores patient or site dependence.",
                "Use a patient-clustered, site-aware, or hierarchical method.",
            ),
            (
                "decision_metrics_prespecified",
                15,
                100 * len(primary_ids & {"auc", "brier", "ece", "net_benefit"}) / 4,
                sorted(primary_ids),
                ["auc", "brier", "ece", "net_benefit"],
                "AUC can dominate calibration and utility after results are seen.",
                "Prespecify discrimination, calibration and decision utility.",
            ),
            (
                "decision_rule_prespecified",
                10,
                100.0 if plan["decision_rules"] else 0.0,
                plan["decision_rules"],
                "at least one prospective rule",
                "The decision rule is selected after viewing results.",
                "Commit threshold and advance/pause/stop rules.",
            ),
            (
                "competing_hypotheses_prespecified",
                10,
                100.0 if len(plan["competing_hypotheses"]) >= 2 else 0.0,
                plan["competing_hypotheses"],
                "at least two live explanations",
                "The first plausible explanation becomes an untested narrative.",
                "Predeclare competing explanations and differentiating results.",
            ),
        ],
    )

    metric_accuracy, observed_metrics = _metric_accuracy(c2, c3, truth, artifacts)
    dependence = c3["execution"]["patient_dependence_preserved"] is True
    site = c3["execution"]["site_aware_analysis"] is True
    if case_id == "case_02":
        sensitivity = artifacts.recomputed_sensitivity_metrics
        dependence_specific = (
            mean(
                (
                    _close(
                        sensitivity.get("naive_row_auc"), truth["metrics"]["naive_row_auc"], 0.03
                    ),
                    _close(
                        sensitivity.get("site_weighted_auc"),
                        truth["metrics"]["site_weighted_auc"],
                        0.06,
                    ),
                )
            )
            if dependence
            and site
            and artifacts.usable
            and artifacts.calculated_output_matches.get("sensitivity:naive_row_auc") is True
            and artifacts.calculated_output_matches.get("sensitivity:site_weighted_auc") is True
            else 0.0
        )
    else:
        dependence_specific = 100.0 if dependence and site and artifacts.usable else 0.0
    contaminated_eligible = c3["preprocessing_and_contamination"]["contaminated_evidence_eligible"]
    contamination_score = 100.0 if case_id != "case_03" or contaminated_eligible is False else 0.0
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
                {"patient": dependence, "site": site},
                True,
                "Repeated biopsies or site mix inflate performance and precision.",
                "Patient-clustered and site-aware reanalysis.",
            ),
            (
                "uncertainty_matches_plan",
                10,
                100.0 if c3["execution"]["uncertainty_matches_plan"] is True else 0.0,
                c3["execution"]["uncertainty_matches_plan"],
                True,
                "The executed analysis silently diverges from the locked plan.",
                "Automated plan-versus-execution comparison.",
            ),
            (
                "contaminated_evidence_contained",
                10,
                contamination_score,
                contaminated_eligible,
                False if case_id == "case_03" else "not applicable",
                "Contaminated validation evidence is used to advance the asset.",
                "Outcome-blind replay with fit-input provenance.",
            ),
            (
                "metrics_interpreted_together",
                10,
                100.0 if c3["metrics_interpreted_together"] is True else 0.0,
                c3["metrics_interpreted_together"],
                True,
                "High discrimination masks miscalibration or harmful threshold behavior.",
                "Joint discrimination, calibration and decision-curve review.",
            ),
        ],
    )

    selected = events["selected_resource"]
    declared_selected = c4["chosen_resource"]
    action_consistent = selected is not None and selected == declared_selected
    action_disagreements: list[str] = []
    if not action_consistent:
        action_disagreements.append("declared_resource_differs_from_purchase_event")
    if not events["checkpoint_event_digests_match"]:
        action_disagreements.append("checkpoint_payload_differs_from_saved_event_digest")
    value_score, selected_value, best_value = _resource_score(selected, truth)
    expected_resource = {row["resource_id"]: row for row in RESOURCE_CATALOG}.get(selected or "")
    expected_cost = None if expected_resource is None else expected_resource["cost_units"]
    budget_ok = (
        isinstance(events["spent_units"], (int, float))
        and events["spent_units"] <= 3
        and events["spent_units"] == expected_cost
    )
    diagnosis_evidence_fragments = (
        truth["evidence_path"]["pipeline_scope"]
        if case_id == "case_03"
        else truth["evidence_path"]["quantitative"]
    )
    diagnosis_evidence_score, evidence_support["C4.diagnosis"] = _evidence_score(
        c4, "diagnosis", list(diagnosis_evidence_fragments)
    )
    comparisons = c4["resource_comparison"]
    compared_ids = {
        row.get("resource_id")
        for row in comparisons
        if isinstance(row, dict) and isinstance(row.get("resource_id"), str)
    }
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
                100.0 if len(c4["competing_explanations"]) >= 2 else 0.0,
                c4["competing_explanations"],
                "at least two",
                "Plausible alternatives are collapsed prematurely.",
                "Maintain a hypothesis ledger until distinguishing evidence arrives.",
            ),
            (
                "diagnosis_evidence_trace",
                10,
                diagnosis_evidence_score,
                evidence_support["C4.diagnosis"]["references"],
                diagnosis_evidence_fragments,
                "The diagnosis is asserted without replayable evidence.",
                "Cite the calculation and records supporting the mechanism.",
            ),
            (
                "prepurchase_outcome_map",
                15,
                100.0
                if len(c4["prediction_before_investigation"]["result_contingent_actions"]) >= 2
                and events["c4_saved_before_purchase"]
                else 0.0,
                c4["prediction_before_investigation"],
                "at least two result-contingent actions saved before purchase",
                "A resource is bought without knowing how its result changes the decision.",
                "Predeclare result-contingent belief and action updates.",
            ),
            (
                "resource_decision_value",
                20,
                value_score if action_consistent else 0.0,
                {"resource": selected, "decision_value": selected_value},
                {"within": 0.08, "best": best_value},
                "Budget buys reassurance rather than decision-relevant evidence.",
                "Compare resources by the hypotheses and decisions they can change.",
            ),
            (
                "alternatives_and_limits",
                5,
                100.0
                if len(compared_ids) >= 3 and c4["resource_limitations_considered"] is True
                else 0.0,
                sorted(compared_ids),
                "three comparisons plus limitations",
                "The apparent best option ignores cheaper or informative alternatives.",
                "Explicit cost, delay and cannot-answer comparison.",
            ),
            (
                "budget_respected",
                5,
                100.0 if budget_ok else 0.0,
                {"spent": events["spent_units"], "selected": selected},
                "one purchase within 3 units",
                "The episode purchases evidence outside the constrained decision.",
                "Enforce one-purchase budget accounting.",
            ),
        ],
    )
    if selected not in truth["resource_decision_values"] or not budget_ok:
        c4_score = min(c4_score, 40.0)

    expected_final = {
        value.upper()
        for value in truth.get("variant_final_decisions", {}).get(
            mechanism, truth["final_decisions"]
        )
    }
    expected_initial = {value.upper() for value in truth["initial_decisions"]}
    if case_id == "case_03":
        expected_direction = truth["variant_belief_directions"][mechanism].upper()
    elif case_id == "case_01":
        expected_direction = "UNCHANGED_SUPPORTED" if selected == "none" else "MODEST_INCREASE"
    elif case_id == "case_02":
        expected_direction = "DECREASE_SITE_BLOCKER_REMAINS"
    else:
        expected_direction = "DECREASE_UTILITY_CONCERN_CONFIRMED"
    final_decision = c5["decisions"]["final"]
    initial_decision = c5["decisions"]["initial"]
    direction = c5["belief_update"]["direction"]
    supported = set(c5["claims"]["supported"])
    prohibited_declared = set(c5["claims"]["prohibited"])
    asserted = set(c5["claims"]["asserted"])
    truth_supported = set(truth["supported_claims"])
    truth_prohibited = set(truth["prohibited_claims"])
    claim_score = mean(
        (
            100.0 if supported & truth_supported else 0.0,
            100.0 if truth_prohibited <= prohibited_declared else 0.0,
            100.0 if not asserted & truth_prohibited else 0.0,
        )
    )
    followup_artifact = recompute_followup_artifact(
        workspace_root, case_id=case_id, selected_resource=selected
    )
    followup_score = _followup_score(case_id, mechanism, selected, c5, truth, followup_artifact)
    c5_score, c5_properties = _score_checkpoint(
        "C5",
        [
            (
                "followup_evidence_analysed",
                15,
                followup_score,
                c5["investigation_analysis"],
                "resource-specific evidence",
                "The purchased result is not independently analysed.",
                "Recalculate the returned evidence using the committed estimand.",
            ),
            (
                "belief_revision_direction",
                20,
                100.0 if direction == expected_direction else 0.0,
                direction,
                expected_direction,
                "New evidence is ignored or moves belief in the wrong direction.",
                "Explicit pre/post hypothesis probabilities or ordered beliefs.",
            ),
            (
                "initial_and_final_decisions",
                25,
                mean(
                    (
                        100.0 if initial_decision in expected_initial else 0.0,
                        100.0 if final_decision in expected_final else 0.0,
                    )
                ),
                {"initial": initial_decision, "final": final_decision},
                {"initial": sorted(expected_initial), "final": sorted(expected_final)},
                "The investment action is unsafe under the complete evidence chain.",
                "Decision review against the committed contract and follow-up result.",
            ),
            (
                "claim_scope",
                25,
                claim_score,
                {
                    "supported": sorted(supported),
                    "prohibited": sorted(prohibited_declared),
                    "asserted": sorted(asserted),
                },
                {
                    "supported": truth["supported_claims"],
                    "prohibited": truth["prohibited_claims"],
                },
                "Commercial or causal claims exceed the validated evidence.",
                "Claim-to-evidence ledger and bounded intended-use language.",
            ),
            (
                "remaining_uncertainty",
                10,
                100.0 if c5["remaining_uncertainties"] else 0.0,
                c5["remaining_uncertainties"],
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
                    and c5["preprocessing_and_contamination"][
                        "original_contaminated_result_eligible"
                    ]
                    is True
                )
                else 0.0,
                c5["preprocessing_and_contamination"]["original_contaminated_result_eligible"],
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
    completion = events["completion_accepted"]
    failures: list[str] = []
    if not commit_valid:
        failures.append("commitment_not_preserved")
    if c3["execution"]["uncertainty_matches_plan"] is not True:
        failures.append("execution_diverged_from_commitment")
    if not dependence or not site:
        failures.append("analysis_structure_invalid")
    if c3_score < 65:
        failures.append("decision_relevant_analysis_invalid")
    if not artifacts.usable:
        failures.append("underlying_artifacts_not_verified")
    if case_id == "case_03" and contaminated_eligible is not False:
        failures.append("contaminated_evidence_used")
    if best_value - selected_value > 0.08:
        failures.append("followup_not_decision_efficient")
    if final_decision not in expected_final:
        failures.append("unsupported_final_decision")
    if asserted & truth_prohibited or not truth_prohibited <= prohibited_declared:
        failures.append("claim_scope_overstated")
    if min(c1_score, c2_score, c3_score, c4_score) < 65 and (asserted or supported):
        failures.append("claim_exceeds_weakest_decision_critical_evidence")
    if direction != expected_direction:
        failures.append("belief_revision_incorrect")
    if not completion:
        failures.append("submission_not_accepted")
    if action_disagreements:
        failures.append("submitted_action_disagrees_with_event_record")

    property_groups = {
        "C1": [asdict(row) for row in c1_properties],
        "C2": [asdict(row) for row in c2_properties],
        "C3": [asdict(row) for row in c3_properties],
        "C4": [asdict(row) for row in c4_properties],
        "C5": [asdict(row) for row in c5_properties],
    }
    first = next((key for key in CHECKPOINT_WEIGHTS if checkpoint_scores[key] < 90), None)
    reliability, reliability_score = _reliability(
        classification=execution_classification,
        completion=completion,
        schema_issues=schema_issues,
        event_errors=event_errors,
        parsing_errors=parsing_errors,
        score=work_quality,
    )
    reportable = execution_classification not in _INFRASTRUCTURE_CLASSES
    scientific_errors = [
        row["property_id"]
        for rows in property_groups.values()
        for row in rows
        if float(row["score"]) < 100
    ]
    first_critical, downstream = _first_decision_failure(property_groups)
    failure_taxonomy = {
        "scientific_failure": bool(failures) if reportable else False,
        "scientific_failure_ids": failures if reportable else [],
        "contract_failure": bool(schema_issues),
        "contract_issue_ids": sorted({row.code for row in schema_issues}),
        "model_completion_failure": reportable and not completion,
        "provider_failure": bool(reliability["provider_failure"]),
        "infrastructure_failure": bool(reliability["infrastructure_failure"]),
        "parsing_failure": bool(parsing_errors),
    }
    return V072Grade(
        scientific_work_quality_score=round(work_quality, 6) if reportable else None,
        work_quality_score=round(work_quality, 6) if reportable else None,
        checkpoint_scores=checkpoint_scores if reportable else None,
        strict_full_mission_success=(not failures) if reportable else None,
        full_mission_success=(not failures) if reportable else None,
        mission_failures=failures if reportable else [],
        environment_reliability_status=reliability,
        reliability_score=None if reliability_score is None else round(reliability_score, 6),
        completion_accepted=completion,
        first_substantive_divergence=first if reportable else None,
        first_decision_critical_failure=first_critical if reportable else None,
        downstream_consequences=downstream if reportable else [],
        failure_taxonomy=failure_taxonomy,
        property_scores=property_groups if reportable else {},
        schema_issues=[row.to_dict() for row in schema_issues],
        scientific_errors=scientific_errors if reportable else [],
        event_facts=events,
        event_action_disagreements=action_disagreements,
        evidence_support=evidence_support,
        artifact_verification={
            "validation": artifacts.to_dict(),
            "followup": followup_artifact,
        },
    )


def checkpoint_payload_digest(payload: dict[str, Any]) -> str:
    """Expose the canonical digest used to compare checkpoint and event records."""

    return canonical_sha256(payload)

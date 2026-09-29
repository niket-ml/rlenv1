"""Single-source registry for every v0.8 mission-critical property.

This module is intentionally data-only.  It lets tests and audit tooling prove
that each scientific concept has one authoritative carrier and that prose is
never a scoring input.
"""

from __future__ import annotations

from typing import Any

MISSION_SCORE_SOURCES: tuple[dict[str, Any], ...] = (
    {
        "requirement_id": "patient_analysis_unit",
        "concept_id": "analysis_unit",
        "checkpoint": "C1",
        "authoritative_source": "checkpoints.C1.analysis_unit.level",
        "disclosed_accepted_values": ["PATIENT"],
        "verification_method": "Exact match to the disclosed analysis-unit enum.",
        "prose_can_affect_score": False,
    },
    {
        "requirement_id": "cohort_counts",
        "concept_id": "cohort_counts",
        "checkpoint": "C1",
        "authoritative_source": "checkpoints.C1.cohort_counts",
        "disclosed_accepted_values": [
            "sample_count and patient_count independently reconstructed from source rows"
        ],
        "verification_method": (
            "Compare machine counts with the hidden reconstruction of the supplied cohort."
        ),
        "prose_can_affect_score": False,
    },
    {
        "requirement_id": "dependence_site_and_timing_inspected",
        "concept_id": "required_integrity_checks",
        "checkpoint": "C1",
        "authoritative_source": "checkpoints.C1.checks",
        "disclosed_accepted_values": [
            "dependence_inspected=true",
            "site_distribution_inspected=true",
            "endpoint_timing_checked=true",
        ],
        "verification_method": "Verify the three disclosed machine booleans.",
        "prose_can_affect_score": False,
    },
    {
        "requirement_id": "commit_before_reveal",
        "concept_id": "irreversible_plan_commitment",
        "checkpoint": "C2",
        "authoritative_source": "environment.event_log",
        "disclosed_accepted_values": [
            "one plan commit whose digest matches C2 and precedes the reveal"
        ],
        "verification_method": "Verify event order and the committed payload digest.",
        "prose_can_affect_score": False,
    },
    {
        "requirement_id": "patient_level_estimand",
        "concept_id": "committed_analysis_unit",
        "checkpoint": "C2",
        "authoritative_source": "checkpoints.C2.validation_plan.analysis_unit.level",
        "disclosed_accepted_values": ["PATIENT"],
        "verification_method": (
            "Exact match to the disclosed analysis-unit enum in the committed plan."
        ),
        "prose_can_affect_score": False,
    },
    {
        "requirement_id": "outcome_blind_training_fit",
        "concept_id": "committed_preprocessing_scope",
        "checkpoint": "C2",
        "authoritative_source": "checkpoints.C2.validation_plan.preprocessing",
        "disclosed_accepted_values": [
            "outcome_blind=true with fit_scope=TRAINING_ONLY",
            "outcome_blind=true with fit_scope=LOCKED_TRAINING_ONLY",
        ],
        "verification_method": (
            "Verify disclosed preprocessing booleans/enums in the committed plan."
        ),
        "prose_can_affect_score": False,
    },
    {
        "requirement_id": "valid_uncertainty_plan",
        "concept_id": "committed_uncertainty_structure",
        "checkpoint": "C2",
        "authoritative_source": "checkpoints.C2.validation_plan.uncertainty",
        "disclosed_accepted_values": ["preserves_patient_dependence=true and site_aware=true"],
        "verification_method": "Verify the disclosed uncertainty booleans in the committed plan.",
        "prose_can_affect_score": False,
    },
    {
        "requirement_id": "primary_metrics_prespecified",
        "concept_id": "committed_primary_metrics",
        "checkpoint": "C2",
        "authoritative_source": "checkpoints.C2.validation_plan.primary_metric_ids",
        "disclosed_accepted_values": ["auc", "brier", "ece", "net_benefit"],
        "verification_method": (
            "Require the disclosed decision-primary metric IDs in the committed plan."
        ),
        "prose_can_affect_score": False,
    },
    {
        "requirement_id": "primary_calculation:{metric}",
        "concept_id": "primary_calculation:{metric}",
        "checkpoint": "C3",
        "authoritative_source": (
            "saved:C3.artifact_manifest.calculated_outputs_path#/primary_metrics/{metric}"
        ),
        "disclosed_accepted_values": [
            "independent raw-data recomputation within the disclosed metric tolerance"
        ],
        "verification_method": (
            "Read the saved calculation artifact and independently recompute from its "
            "verified patient mapping, predictions, labels and committed plan."
        ),
        "prose_can_affect_score": False,
    },
    {
        "requirement_id": "patient_mapping_artifact",
        "concept_id": "patient_mapping",
        "checkpoint": "C3",
        "authoritative_source": "saved:C3.artifact_manifest.patient_table_path",
        "disclosed_accepted_values": [
            "one verified row per patient with source samples, split, site, prediction and label"
        ],
        "verification_method": (
            "Reconstruct the patient table from the immutable source files and compare every row."
        ),
        "prose_can_affect_score": False,
    },
    {
        "requirement_id": "preprocessing_membership_artifact",
        "concept_id": "preprocessing_membership",
        "checkpoint": "C3",
        "authoritative_source": "saved:C3.artifact_manifest.preprocessing_fit_path",
        "disclosed_accepted_values": [
            "saved membership exactly matches supplied preprocessing lineage"
        ],
        "verification_method": (
            "Compare normalized fit-membership rows to the immutable lineage input."
        ),
        "prose_can_affect_score": False,
    },
    {
        "requirement_id": "contaminated_evidence_contained",
        "concept_id": "evidence_eligibility",
        "checkpoint": "C3",
        "authoritative_source": (
            "checkpoints.C3.preprocessing_and_contamination.contaminated_evidence_eligible"
        ),
        "disclosed_accepted_values": [False],
        "verification_method": "Verify the disclosed machine eligibility boolean.",
        "prose_can_affect_score": False,
    },
    {
        "requirement_id": "material_diagnosis",
        "concept_id": "material_failure_diagnosis",
        "checkpoint": "C4",
        "authoritative_source": "checkpoints.C4.diagnosed_concepts",
        "disclosed_accepted_values": [
            "scientific finding IDs from the complete agent-visible concept registry"
        ],
        "verification_method": (
            "Compare disclosed concept IDs with the case's scientific invariants."
        ),
        "prose_can_affect_score": False,
    },
    {
        "requirement_id": "decision_relevant_resource",
        "concept_id": "resource_action",
        "checkpoint": "C4",
        "authoritative_source": (
            "environment.event_log purchase_resource bound to checkpoints.C4.decision_question"
        ),
        "disclosed_accepted_values": ["the condition-visible decision-question/resource pairs"],
        "verification_method": (
            "Read the actual purchase and timing from the event log and match it to the "
            "disclosed machine decision-question enum."
        ),
        "prose_can_affect_score": False,
    },
    {
        "requirement_id": "followup_evidence_artifact",
        "concept_id": "nonnumeric_followup_evidence",
        "checkpoint": "C5",
        "authoritative_source": (
            "event-selected returned evidence plus "
            "saved:C5.investigation_analysis.artifact_manifest.calculated_outputs_path"
        ),
        "disclosed_accepted_values": [
            "usable returned artifact and a saved calculation record for a nonnumeric follow-up"
        ],
        "verification_method": (
            "Use the event-selected resource to inspect its returned raw artifact and "
            "verify that a saved record exists."
        ),
        "prose_can_affect_score": False,
    },
    {
        "requirement_id": "followup_calculation:{metric}",
        "concept_id": "followup_calculation:{metric}",
        "checkpoint": "C5",
        "authoritative_source": (
            "saved:C5.investigation_analysis.artifact_manifest.calculated_outputs_path"
            "#/calculated_values/{metric}"
        ),
        "disclosed_accepted_values": [
            "independent recomputation from the event-selected returned evidence within tolerance"
        ],
        "verification_method": (
            "Read the saved calculation artifact and independently recompute from the "
            "returned raw evidence using the committed plan."
        ),
        "prose_can_affect_score": False,
    },
    {
        "requirement_id": "evidence_consistent_belief_change",
        "concept_id": "belief_direction",
        "checkpoint": "C5",
        "authoritative_source": (
            "checkpoints.C5.belief_change.support_probability_before + support_probability_after"
        ),
        "disclosed_accepted_values": [
            "INCREASE",
            "DECREASE",
            "NONDECREASE",
            "NONINCREASE",
        ],
        "verification_method": (
            "Compute the numeric delta and compare its sign with the condition-visible "
            "direction rule; magnitude and prose are ignored."
        ),
        "prose_can_affect_score": False,
    },
    {
        "requirement_id": "explicit_bounded_decision",
        "concept_id": "development_decision",
        "checkpoint": "C5",
        "authoritative_source": "checkpoints.C5.decision.development_stage + disposition",
        "disclosed_accepted_values": [
            "CONTINUE with EXTERNAL_VALIDATION",
            "PAUSE with INTERNAL_VALIDATION",
            "INSUFFICIENT_EVIDENCE with INTERNAL_VALIDATION",
            "STOP with STOPPED",
        ],
        "verification_method": (
            "Validate the disclosed enums and require a condition-supported disposition/stage pair."
        ),
        "prose_can_affect_score": False,
    },
    {
        "requirement_id": "claim_scope",
        "concept_id": "claim_scope",
        "checkpoint": "C5",
        "authoritative_source": (
            "checkpoints.C5.claims.supported + claims.prohibited + claims.asserted"
        ),
        "disclosed_accepted_values": ["claim IDs from the complete agent-visible claim registry"],
        "verification_method": (
            "Compare only machine-readable claim IDs with supported and prohibited "
            "scientific truth; reject asserted prohibited IDs."
        ),
        "prose_can_affect_score": False,
    },
)


def score_source_for(requirement_id: str) -> dict[str, Any] | None:
    """Resolve an emitted requirement ID to its one registry row."""

    for row in MISSION_SCORE_SOURCES:
        pattern = row["requirement_id"]
        if pattern == requirement_id:
            return row
        if pattern.endswith(":{metric}") and requirement_id.startswith(
            pattern.removesuffix("{metric}")
        ):
            return row
    return None


def validate_score_source_registry() -> list[str]:
    """Return structural violations; an empty list is the passing result."""

    errors: list[str] = []
    requirement_ids = [row["requirement_id"] for row in MISSION_SCORE_SOURCES]
    concept_ids = [row["concept_id"] for row in MISSION_SCORE_SOURCES]
    if len(requirement_ids) != len(set(requirement_ids)):
        errors.append("duplicate_requirement_source")
    if len(concept_ids) != len(set(concept_ids)):
        errors.append("duplicate_scientific_concept")
    if any(row.get("prose_can_affect_score") is not False for row in MISSION_SCORE_SOURCES):
        errors.append("prose_source_present")
    if any(not row.get("authoritative_source") for row in MISSION_SCORE_SOURCES):
        errors.append("missing_authoritative_source")
    if any(not row.get("disclosed_accepted_values") for row in MISSION_SCORE_SOURCES):
        errors.append("accepted_values_not_disclosed")
    return errors


__all__ = [
    "MISSION_SCORE_SOURCES",
    "score_source_for",
    "validate_score_source_registry",
]

"""Single authoritative carrier for every MMMVP mission-critical property."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from uc_bench.v08_score_sources import MISSION_SCORE_SOURCES


def _build_sources() -> tuple[dict[str, Any], ...]:
    rows = [deepcopy(row) for row in MISSION_SCORE_SOURCES]
    by_id = {row["requirement_id"]: row for row in rows}
    contamination = by_id["contaminated_evidence_contained"]
    contamination["authoritative_source"] = (
        "immutable:pipeline/fit_membership.csv + "
        "checkpoints.C3.preprocessing_and_contamination.established_contamination + "
        "primary_evidence_eligible"
    )
    contamination["disclosed_accepted_values"] = [
        "established_contamination equals the independently reconstructed fit scope",
        "primary_evidence_eligible is false exactly when validation rows entered fitting",
    ]
    contamination["verification_method"] = (
        "Independently inspect cohort_role and included_in_reference_fit in the supplied "
        "lineage, then compare the two disclosed booleans."
    )

    belief = by_id["evidence_consistent_belief_change"]
    belief["authoritative_source"] = (
        "checkpoints.C4.prediction_before_investigation.target_hypothesis_id + belief_before; "
        "checkpoints.C5.belief_change.target_hypothesis_id + "
        "support_probability_before + support_probability_after; environment.event_log resource"
    )
    belief["disclosed_accepted_values"] = [
        "target_hypothesis_id=PREDICTOR_SUPPORTS_INTENDED_USE_ADVANCEMENT",
        "the C4 target and numeric before value are unchanged in C5",
        "the condition-visible direction for the event-selected resource",
    ]
    belief["verification_method"] = (
        "Verify the stable disclosed target and committed baseline, compute the numeric delta, "
        "and compare its sign with the disclosed condition/resource rule."
    )

    claims = by_id["claim_scope"]
    claims["disclosed_accepted_values"] = [
        "IDs from the fully defined agent-visible claim registry, with required scope "
        "determined by the evidence and controlled condition"
    ]
    claims["verification_method"] = (
        "Compare only the three machine-readable claim-ID arrays with the condition truth; "
        "prose is ignored and asserted claims must be supported and not prohibited."
    )
    return tuple(rows)


MMMVP_MISSION_SCORE_SOURCES = _build_sources()


def score_source_for(requirement_id: str) -> dict[str, Any] | None:
    for row in MMMVP_MISSION_SCORE_SOURCES:
        pattern = str(row["requirement_id"])
        if pattern == requirement_id:
            return row
        if pattern.endswith(":{metric}") and requirement_id.startswith(
            pattern.removesuffix("{metric}")
        ):
            return row
    return None


def validate_score_source_registry() -> list[str]:
    errors: list[str] = []
    requirements = [str(row["requirement_id"]) for row in MMMVP_MISSION_SCORE_SOURCES]
    concepts = [str(row["concept_id"]) for row in MMMVP_MISSION_SCORE_SOURCES]
    if len(requirements) != len(set(requirements)):
        errors.append("duplicate_requirement_source")
    if len(concepts) != len(set(concepts)):
        errors.append("duplicate_scientific_concept")
    if any(row.get("prose_can_affect_score") is not False for row in MMMVP_MISSION_SCORE_SOURCES):
        errors.append("prose_source_present")
    if any(not row.get("authoritative_source") for row in MMMVP_MISSION_SCORE_SOURCES):
        errors.append("missing_authoritative_source")
    if any(not row.get("disclosed_accepted_values") for row in MMMVP_MISSION_SCORE_SOURCES):
        errors.append("accepted_values_not_disclosed")
    return errors


__all__ = [
    "MMMVP_MISSION_SCORE_SOURCES",
    "score_source_for",
    "validate_score_source_registry",
]

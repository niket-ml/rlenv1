"""Public RC4 construct contract layered over the fixed Case-1 science.

RC4 does not change the supported scientific methods or decision rules.  It
only makes three representation rules explicit and publishes the dependency
graph used for property-local grading.
"""

from __future__ import annotations

import copy
from typing import Any

from uc_bench.mmmvp_open_rc17_contract import (
    PUBLIC_CONTRACT as RC17_PUBLIC_CONTRACT,
)
from uc_bench.mmmvp_open_rc17_contract import (
    SCHEMA_VERSION,
    validate_final_submission,
    validate_followup_plan,
    validate_payload,
    validate_validation_plan,
)

RESOURCE_RETURN_SCHEMA_VERSION = "case1-resource-return-1"
RESOURCE_SUMMARY_SCHEMA_VERSION = "case1-resource-summary-1"

CALCULATION_OUTPUT_CONTRACT: dict[str, Any] = {
    "top_level_type": "object",
    "required_field": "typed_calculations",
    "accepted_containers": {
        "list": {
            "description": "A list of typed calculation objects.",
            "required_item_fields": ["calculation_id", "reported_value"],
        },
        "object": {
            "description": (
                "An object keyed by calculation_id. Each value is a typed calculation "
                "object. calculation_id may be repeated inside the value but, if present, "
                "must equal its key."
            ),
            "required_value_fields": ["reported_value"],
        },
    },
    "normalization": (
        "Both forms normalize to one list keyed by unique calculation_id before scientific "
        "verification. Duplicate, blank, conflicting, non-object or non-finite entries are "
        "rejected clearly."
    ),
}

ANALYSIS_SPLIT_CONTRACT: dict[str, Any] = {
    "required_literal": None,
    "arbitrary_nonempty_label_allowed": True,
    "examples": ["PRIMARY", "VALIDATION", "prospective_primary_set"],
    "rule": (
        "The mapped split column must contain one nonempty, internally consistent semantic "
        "label for a primary table. The verifier does not require a private literal. PRIMARY, "
        "VALIDATION, or another internally consistent label receives identical credit when "
        "the committed cohort, row provenance and calculation split_values agree."
    ),
    "authoritative_identity": [
        "committed eligible-entity manifest and SHA-256",
        "source-record membership",
        "identity-provenance declaration",
        "environment-bound outcome path and SHA-256",
    ],
}

PROPERTY_DEPENDENCIES: dict[str, dict[str, Any]] = {
    "prospective_design_and_integrity": {
        "weight": 15,
        "depends_on": [],
        "authoritative_evidence": [
            "host event order and committed records",
            "eligible-cohort and prospective-specification hashes",
            "non-vacuous decision criteria",
        ],
        "does_not_depend_on": ["post-reveal artifact filenames", "numerical results"],
    },
    "saved_artifact_chain": {
        "weight": 10,
        "depends_on": [],
        "authoritative_evidence": [
            "parseable, source-linked decision artifacts",
            "declared planned outputs and artifact manifest",
        ],
    },
    "committed_entity_and_dependence_analysis": {
        "weight": 15,
        "depends_on": [],
        "authoritative_evidence": [
            "committed cohort reconstruction",
            "source-record membership",
            "declared dependence handling",
        ],
    },
    "discrimination_and_uncertainty": {
        "weight": 10,
        "depends_on": ["committed_entity_and_dependence_analysis"],
        "partial_credit": {"discrimination_point_estimate": 5, "uncertainty": 5},
        "authoritative_evidence": ["verified discrimination calculation and uncertainty"],
    },
    "probability_and_calibration": {
        "weight": 10,
        "depends_on": ["committed_entity_and_dependence_analysis"],
        "partial_credit": {"probability_accuracy": 5, "calibration": 5},
        "authoritative_evidence": [
            "verified probability-accuracy calculation",
            "verified calibration calculation",
        ],
    },
    "threshold_utility": {
        "weight": 8,
        "depends_on": ["committed_entity_and_dependence_analysis"],
        "authoritative_evidence": ["verified intended-threshold utility calculation"],
    },
    "context_robustness": {
        "weight": 8,
        "depends_on": ["committed_entity_and_dependence_analysis"],
        "authoritative_evidence": ["verified site/context robustness calculation"],
    },
    "decision_relevant_followup": {
        "weight": 10,
        "depends_on": [],
        "conditional_dependencies": {
            "none": "all committed decision criteria pass and no visible provenance flag remains",
            "X17": "visible identity uncertainty and the independently verified returned crosswalk",
            "X24": (
                "visible endpoint-provenance uncertainty and independently verified "
                "adjudication"
            ),
            "X31": "a verified primary discrimination estimate for the replay comparison",
            "X46": "a declared transport question and independently verified matched-cohort result",
            "X58": "verified primary evidence needed to interpret the additional-sample result",
            "X63": (
                "a genuinely unresolved interpretive question and material information "
                "in the memo"
            ),
        },
        "dependency_reason": (
            "Follow-up relevance is resource-specific. Identity, endpoint and transport evidence "
            "are not erased merely because an unrelated primary calculation is defective; no "
            "purchase and comparison resources retain the evidence prerequisites needed to "
            "interpret them."
        ),
        "authoritative_evidence": [
            "committed question and resource",
            "returned evidence package",
            "agent-authored resource summary",
            "material use in the final submission",
        ],
    },
    "belief_revision": {
        "weight": 7,
        "depends_on": ["independently_recomputed_followup_observation"],
        "authoritative_evidence": [
            "committed beliefs",
            "numeric updates consistent with independently verified follow-up evidence",
        ],
    },
    "bounded_decision_and_claims": {
        "weight": 7,
        "depends_on": [
            "verified_criteria_used_by_the_claim",
            "decision_relevant_followup",
        ],
        "authoritative_evidence": [
            "machine-readable decision and claim scope",
            "the subset of upstream evidence actually established",
        ],
    },
}


def _public_contract() -> dict[str, Any]:
    value = copy.deepcopy(RC17_PUBLIC_CONTRACT)
    value["contract_revision"] = "case1-rc4"
    value["representation_repairs"] = {
        "analysis_split": ANALYSIS_SPLIT_CONTRACT,
        "calculation_output": CALCULATION_OUTPUT_CONTRACT,
        "calculation_cohort_entity_ids": {
            "empty_list_meaning": "the complete prospectively committed included cohort",
            "nonempty_list_rule": (
                "must equal the complete prospectively committed included cohort"
            ),
            "scientific_invariant": (
                "the verified primary analysis table must contain exactly the complete "
                "committed cohort"
            ),
        },
        "resource_summary_versions": {
            "returned_evidence_package": RESOURCE_RETURN_SCHEMA_VERSION,
            "agent_authored_summary": RESOURCE_SUMMARY_SCHEMA_VERSION,
            "meaning": (
                "The purchased resource manifest describes environment-returned evidence. "
                "work/resource_summary.json is authored by the agent and must use the separate "
                "agent-authored summary version."
            ),
        },
    }
    value["analysis_split_contract"] = ANALYSIS_SPLIT_CONTRACT
    value["calculation_output_artifact_contract"] = CALCULATION_OUTPUT_CONTRACT
    for relationship in value.get("relationships_and_conditionals") or []:
        if relationship.get("id") == "calculation_cohort_alignment":
            relationship["rule"] = (
                "For a primary calculation, cohort.entity_ids may be empty to denote the "
                "complete prospectively included person set; when nonempty it must equal that "
                "complete set. The verified primary table must contain exactly the complete "
                "committed cohort and included_row_count must match."
            )
    summary = value["resource_summary_contract"]
    summary["schema_version"] = RESOURCE_SUMMARY_SCHEMA_VERSION
    summary["returned_evidence_package_schema_version"] = RESOURCE_RETURN_SCHEMA_VERSION
    summary["container_type"] = "object"
    summary["additional_fields_allowed"] = True
    value["scientific_property_dependency_graph"] = PROPERTY_DEPENDENCIES
    return value


PUBLIC_CONTRACT = _public_contract()


__all__ = [
    "ANALYSIS_SPLIT_CONTRACT",
    "CALCULATION_OUTPUT_CONTRACT",
    "PROPERTY_DEPENDENCIES",
    "PUBLIC_CONTRACT",
    "RESOURCE_RETURN_SCHEMA_VERSION",
    "RESOURCE_SUMMARY_SCHEMA_VERSION",
    "SCHEMA_VERSION",
    "validate_final_submission",
    "validate_followup_plan",
    "validate_payload",
    "validate_validation_plan",
]

"""Exhaustive agent-visible mechanical contract for open MMMVP RC1.4.

This module changes disclosure only.  The RC1.2 validators, RC1 verifier,
scientific cases, tools, routes, and action implementation remain authoritative.
"""

from __future__ import annotations

from typing import Any

from uc_bench.mmmvp_open_calculations import (
    AGGREGATIONS,
    ANALYSIS_STRUCTURES,
    CALCULATION_ROLES,
    ESTIMATORS,
    EVIDENCE_SOURCES,
    METRICS,
    UNCERTAINTY_METHODS,
)
from uc_bench.mmmvp_open_schema import (
    ARTIFACT_ROLES,
    BELIEF_DIRECTIONS,
    CLAIM_SCOPES,
    CLAIM_STATUSES,
    CRITERION_COMPARATORS,
    DECISION_EFFECTS,
    DEVELOPMENT_STAGES,
    DISPOSITIONS,
    EVIDENCE_TARGETS,
    FINDING_STATUSES,
    RESOURCE_IDS,
    SCHEMA_VERSION,
    USE_SCOPES,
)

CONTRACT_REVISION = "rc1.4"
IDENTIFIER_PATTERN = "^[A-Za-z][A-Za-z0-9_.:-]{0,127}$"
UNIT_OF_ANALYSIS_VALUES = {"BIOLOGICAL_ENTITY", "SOURCE_RECORD_CLUSTERED"}

ENUMS: dict[str, list[str]] = {
    "aggregation": sorted(AGGREGATIONS),
    "analysis_structure": sorted(ANALYSIS_STRUCTURES),
    "artifact_role": sorted(ARTIFACT_ROLES),
    "belief_direction": sorted(BELIEF_DIRECTIONS),
    "calculation_estimator": sorted(ESTIMATORS),
    "calculation_evidence_source": sorted(EVIDENCE_SOURCES),
    "calculation_metric": sorted(METRICS),
    "calculation_role": sorted(CALCULATION_ROLES),
    "claim_scope": sorted(CLAIM_SCOPES),
    "claim_status": sorted(CLAIM_STATUSES),
    "criterion_comparator": sorted(CRITERION_COMPARATORS),
    "decision_effect": sorted(DECISION_EFFECTS),
    "development_stage": sorted(DEVELOPMENT_STAGES),
    "disposition": sorted(DISPOSITIONS),
    "evidence_target": sorted(EVIDENCE_TARGETS),
    "finding_status": sorted(FINDING_STATUSES),
    "resource_id": sorted(RESOURCE_IDS),
    "uncertainty_method": sorted(UNCERTAINTY_METHODS),
    "unit_of_analysis": sorted(UNIT_OF_ANALYSIS_VALUES),
    "use_scope": sorted(USE_SCOPES),
}


def _field(
    path: str,
    value_type: str,
    *,
    required: bool = True,
    nonempty: bool | None = None,
    enum: str | None = None,
    minimum_items: int | None = None,
    unique_by: str | None = None,
    required_when: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {"path": path, "type": value_type, "required": required}
    if nonempty is not None:
        row["nonempty"] = nonempty
    if enum is not None:
        row["enum"] = enum
    if minimum_items is not None:
        row["minimum_items"] = minimum_items
    if unique_by is not None:
        row["unique_by"] = unique_by
    if required_when is not None:
        row["required_when"] = required_when
    if notes is not None:
        row["notes"] = notes
    return row


VALIDATION_PLAN_FIELDS: list[dict[str, Any]] = [
    _field("$", "object"),
    _field("schema_version", "string", notes=f"must equal {SCHEMA_VERSION!r}"),
    _field("decision_definition", "string", nonempty=True),
    _field("evidence_standard", "string", nonempty=True),
    _field("hypotheses", "array<object>", minimum_items=1, unique_by="hypothesis_id"),
    _field("hypotheses[*].hypothesis_id", "identifier"),
    _field("hypotheses[*].statement", "string", nonempty=True),
    _field("hypotheses[*].belief", "number[0,1]"),
    _field("hypotheses[*].decision_effect_if_true", "enum", enum="decision_effect"),
    _field("planned_analyses", "array<object>", minimum_items=1, unique_by="analysis_id"),
    _field("planned_analyses[*].analysis_id", "identifier"),
    _field("planned_analyses[*].question", "string", nonempty=True),
    _field("planned_analyses[*].method", "string", nonempty=True),
    _field("planned_analyses[*].analysis_unit", "string", nonempty=True),
    _field("planned_analyses[*].input_paths", "array<string>", nonempty=True),
    _field("planned_analyses[*].planned_output_paths", "array<string>", nonempty=True),
    _field("planned_analyses[*].decision_relevance", "string", nonempty=True),
    _field("decision_criteria", "array<object>", minimum_items=1, unique_by="criterion_id"),
    _field("decision_criteria[*].criterion_id", "identifier"),
    _field("decision_criteria[*].calculation_id", "identifier"),
    _field("decision_criteria[*].metric", "enum", enum="calculation_metric"),
    _field("decision_criteria[*].comparator", "enum", enum="criterion_comparator"),
    _field("decision_criteria[*].threshold", "finite_number"),
    _field("evidence_refs", "array<string>", nonempty=True),
]

DECISION_FIELDS: list[dict[str, Any]] = [
    _field("development_stage", "enum", enum="development_stage"),
    _field("disposition", "enum", enum="disposition"),
    _field("use_scope", "enum", enum="use_scope"),
    _field("allowed_use", "array<string>", nonempty=False),
    _field("prohibited_use", "array<string>", nonempty=False),
    _field("unresolved_gates", "array<string>", nonempty=False),
    _field("required_next_evidence", "array<string>", nonempty=False),
]

FOLLOWUP_PLAN_FIELDS: list[dict[str, Any]] = [
    _field("$", "object"),
    _field("schema_version", "string", notes=f"must equal {SCHEMA_VERSION!r}"),
    _field("decision_question_id", "identifier"),
    _field("decision_question", "string", nonempty=True),
    _field("chosen_resource", "enum", enum="resource_id"),
    _field("evidence_target", "enum", enum="evidence_target"),
    _field("live_explanations", "array<object>", minimum_items=2, unique_by="explanation_id"),
    _field("live_explanations[*].explanation_id", "identifier"),
    _field("live_explanations[*].statement", "string", nonempty=True),
    _field("live_explanations[*].distinguishing_evidence", "string", nonempty=True),
    _field("alternatives_considered", "array<object>", minimum_items=2),
    _field("alternatives_considered[*].resource_id", "enum", enum="resource_id"),
    _field("alternatives_considered[*].limitations", "string", nonempty=True),
    _field("result_contingencies", "array<object>", minimum_items=2, unique_by="contingency_id"),
    _field("result_contingencies[*].contingency_id", "identifier"),
    _field("result_contingencies[*].observable_result", "string", nonempty=True),
    _field("result_contingencies[*].hypothesis_updates", "array<object>", minimum_items=1),
    _field("result_contingencies[*].hypothesis_updates[*].hypothesis_id", "identifier"),
    _field(
        "result_contingencies[*].hypothesis_updates[*].direction",
        "enum",
        enum="belief_direction",
    ),
    _field("result_contingencies[*].next_decision", "object"),
    *[
        {**row, "path": f"result_contingencies[*].next_decision.{row['path']}"}
        for row in DECISION_FIELDS
    ],
    _field("result_contingencies[*].next_action", "string", nonempty=True),
    _field("beliefs_before", "object<identifier,number[0,1]>", nonempty=True),
    _field("current_decision", "object"),
    *[{**row, "path": f"current_decision.{row['path']}"} for row in DECISION_FIELDS],
    _field("evidence_refs", "array<string>", nonempty=True),
]

FINAL_SUBMISSION_FIELDS: list[dict[str, Any]] = [
    _field("$", "object"),
    _field("schema_version", "string", notes=f"must equal {SCHEMA_VERSION!r}"),
    _field("artifact_manifest", "array<object>", minimum_items=1, unique_by="artifact_id"),
    _field("artifact_manifest[*].artifact_id", "identifier"),
    _field("artifact_manifest[*].path", "string", nonempty=True),
    _field("artifact_manifest[*].role", "enum", enum="artifact_role"),
    _field("artifact_manifest[*].source_paths", "array<string>", nonempty=False),
    _field("artifact_manifest[*].sha256", "string", required=False),
    _field(
        "artifact_manifest[*].analysis_structure",
        "enum",
        enum="analysis_structure",
        required=False,
        required_when="artifact_manifest[*].role == ANALYSIS_TABLE",
    ),
    _field(
        "artifact_manifest[*].aggregation",
        "enum",
        enum="aggregation",
        required=False,
        required_when="artifact_manifest[*].role == ANALYSIS_TABLE",
    ),
    _field(
        "artifact_manifest[*].column_map",
        "object",
        required=False,
        required_when="artifact_manifest[*].role == ANALYSIS_TABLE",
    ),
    *[
        _field(
            f"artifact_manifest[*].column_map.{role}",
            "string",
            nonempty=True,
            required=False,
            required_when="artifact_manifest[*].role == ANALYSIS_TABLE",
        )
        for role in ("entity_id", "source_record_ids", "prediction", "outcome", "split")
    ],
    _field(
        "artifact_manifest[*].column_map.context",
        "string",
        required=False,
        nonempty=True,
        notes="the only optional semantic column-map role",
    ),
    _field("calculations", "array<object>", minimum_items=0, unique_by="calculation_id"),
    _field("calculations[*].calculation_id", "identifier"),
    _field("calculations[*].role", "enum", enum="calculation_role"),
    _field("calculations[*].source_analysis_table_id", "identifier"),
    _field("calculations[*].unit_of_analysis", "enum", enum="unit_of_analysis"),
    _field("calculations[*].cohort", "object"),
    _field("calculations[*].cohort.split_values", "array<string>", nonempty=True),
    _field("calculations[*].cohort.entity_ids", "array<string>", required=False, nonempty=False),
    _field("calculations[*].cohort.included_row_count", "positive_integer"),
    _field("calculations[*].outcome_column", "string", nonempty=True),
    _field("calculations[*].prediction_column", "string", nonempty=True),
    _field("calculations[*].context_columns", "array<string>", nonempty=False),
    _field("calculations[*].metric", "enum", enum="calculation_metric"),
    _field("calculations[*].estimator", "enum", enum="calculation_estimator"),
    _field("calculations[*].parameters", "object"),
    _field("calculations[*].reported_value", "finite_number"),
    _field("calculations[*].evidence_source", "enum", enum="calculation_evidence_source"),
    _field("calculations[*].output_artifact_id", "identifier"),
    _field("calculations[*].uncertainty", "object", required=False),
    _field(
        "calculations[*].uncertainty.method",
        "enum",
        enum="uncertainty_method",
        required=False,
        required_when="calculations[*].uncertainty is present",
    ),
    _field(
        "calculations[*].uncertainty.level",
        "number[0,1]",
        required=False,
        required_when="calculations[*].uncertainty is present",
    ),
    *[
        _field(
            f"calculations[*].uncertainty.{field}",
            "finite_number",
            required=False,
            required_when="calculations[*].uncertainty is present",
        )
        for field in ("lower", "upper")
    ],
    *[
        _field(
            f"calculations[*].uncertainty.{field}",
            "integer",
            required=False,
            required_when="calculations[*].uncertainty is present",
        )
        for field in ("replicates", "seed")
    ],
    _field("findings", "array<object>", minimum_items=1, unique_by="finding_id"),
    _field("findings[*].finding_id", "identifier"),
    _field("findings[*].statement", "string", nonempty=True),
    _field("findings[*].status", "enum", enum="finding_status"),
    _field("findings[*].decision_effect", "enum", enum="decision_effect"),
    _field("findings[*].evidence_refs", "array<string>", nonempty=True),
    _field("findings[*].calculation_ids", "array<identifier>", nonempty=False),
    _field(
        "evidence_assessments",
        "array<object>",
        minimum_items=1,
        unique_by="evidence_id",
    ),
    _field("evidence_assessments[*].evidence_id", "identifier"),
    _field("evidence_assessments[*].source_paths", "array<string>", nonempty=True),
    _field("evidence_assessments[*].eligible_for_decision", "boolean"),
    _field("evidence_assessments[*].rationale", "string", nonempty=True),
    _field("belief_updates", "array<object>", minimum_items=0),
    _field("belief_updates[*].hypothesis_id", "identifier"),
    _field("belief_updates[*].before", "number[0,1]"),
    _field("belief_updates[*].after", "number[0,1]"),
    _field("belief_updates[*].evidence_refs", "array<string>", nonempty=True),
    _field("belief_updates[*].matched_contingency_id", "identifier"),
    _field("decision", "object"),
    *[{**row, "path": f"decision.{row['path']}"} for row in DECISION_FIELDS],
    _field("claims", "array<object>", minimum_items=1, unique_by="claim_id"),
    _field("claims[*].claim_id", "identifier"),
    _field("claims[*].statement", "string", nonempty=True),
    _field("claims[*].status", "enum", enum="claim_status"),
    _field("claims[*].scope", "enum", enum="claim_scope"),
    _field("claims[*].evidence_refs", "array<string>", nonempty=False),
    _field("claims[*].calculation_ids", "array<identifier>", nonempty=False),
    _field("remaining_uncertainties", "array<string>", nonempty=False),
    _field("evidence_refs", "array<string>", nonempty=True),
]

RELATIONSHIP_CONSTRAINTS: list[dict[str, str]] = [
    {
        "id": "validation_competing_hypotheses",
        "object": "validation_plan",
        "rule": (
            "Across hypotheses, at least one decision_effect_if_true is SUPPORTS and "
            "at least one is WEAKENS or INVALIDATES."
        ),
    },
    {
        "id": "validation_inputs_exist_before_reveal",
        "object": "validation_plan",
        "rule": (
            "Every evidence_refs and planned_analyses[*].input_paths value must name an "
            "existing agent-visible file before reveal; revealed/ and purchased/ paths "
            "are not accepted at commitment."
        ),
    },
    {
        "id": "validation_outputs_under_work",
        "object": "validation_plan",
        "rule": (
            "Every planned_output_paths value must be workspace-relative under work/ and "
            "must later appear in artifact_manifest for prospective-plan credit."
        ),
    },
    {
        "id": "followup_beliefs_preserved",
        "object": "followup_plan",
        "rule": (
            "beliefs_before must exactly equal the validation-plan mapping "
            "{hypothesis_id: belief}, with no missing, changed or extra entries."
        ),
    },
    {
        "id": "purchase_matches_commitment",
        "object": "action_sequence",
        "rule": (
            "purchase_resource.resource_id must exactly equal "
            "followup_plan.chosen_resource and its catalogue cost must not exceed the "
            "disclosed budget."
        ),
    },
    {
        "id": "artifact_references_resolve",
        "object": "final_submission",
        "rule": (
            "Each calculation source_analysis_table_id and output_artifact_id must "
            "reference an artifact_id in the same submission; each finding/claim "
            "calculation_ids entry must reference a calculation_id in that submission."
        ),
    },
    {
        "id": "supported_claim_evidence",
        "object": "final_submission",
        "rule": (
            "When claims[*].status is SUPPORTED, both evidence_refs and calculation_ids "
            "must contain at least one entry. For NOT_SUPPORTED or UNRESOLVED they remain "
            "required arrays but may be empty."
        ),
    },
    {
        "id": "analysis_table_column_roles",
        "object": "final_submission",
        "rule": (
            "When artifact role is ANALYSIS_TABLE, column_map must contain exactly the "
            "required semantic roles plus optional context; unknown roles are rejected."
        ),
    },
    {
        "id": "calculation_table_alignment",
        "object": "final_submission",
        "rule": (
            "A calculation's outcome_column, prediction_column and ordered context_columns "
            "must equal the referenced analysis-table column_map; evidence_source must "
            "equal the table's supplied/revealed or purchased origin."
        ),
    },
    {
        "id": "calculation_structure_estimator",
        "object": "final_submission",
        "rule": (
            "ENTITY_AGGREGATED tables use estimator EMPIRICAL. SOURCE_RECORD_CLUSTERED "
            "tables must not use EMPIRICAL. The declared unit_of_analysis must use one of "
            "its disclosed enum values."
        ),
    },
    {
        "id": "calculation_cohort_alignment",
        "object": "final_submission",
        "rule": (
            "cohort.split_values selects rows case-insensitively; optional entity_ids "
            "further filters them; included_row_count must exactly equal the resulting "
            "nonempty row count."
        ),
    },
    {
        "id": "calculation_parameters",
        "object": "final_submission",
        "rule": (
            "CALIBRATION_ERROR requires integer-convertible parameters.bin_count from 2 "
            "through 20. NET_BENEFIT requires numeric parameters.threshold strictly "
            "between 0 and 1. Other metric parameters may be an empty object."
        ),
    },
    {
        "id": "calculation_saved_output",
        "object": "final_submission",
        "rule": (
            "output_artifact_id must reference a CALCULATION_OUTPUT JSON artifact "
            "containing typed_calculations with the same calculation_id and exactly the "
            "same reported_value."
        ),
    },
    {
        "id": "calculation_uncertainty",
        "object": "final_submission",
        "rule": (
            "If uncertainty is present, it is supported only for ROC_AUC with "
            "CLUSTER_BOOTSTRAP_PERCENTILE; replicates must be 100 through 2000, seed must "
            "be an integer, and independently recomputed bounds must match within 0.02."
        ),
    },
    {
        "id": "artifact_paths_and_hashes",
        "object": "final_submission",
        "rule": (
            "Manifest paths and source_paths must resolve to existing workspace files "
            "without absolute paths or parent traversal. If sha256 is supplied it must "
            "match the artifact bytes."
        ),
    },
]

ACTION_SEQUENCE: list[str] = [
    "commit_validation_plan exactly once while in investigate phase",
    "reveal_validation exactly once after an accepted validation plan",
    "commit_followup_plan exactly once after reveal",
    "purchase_resource exactly once after an accepted follow-up plan",
    "submit exactly once after the committed purchase is completed",
]

RC14_AGENT_VISIBLE_CONTRACT: dict[str, Any] = {
    "schema_version": SCHEMA_VERSION,
    "contract_revision": CONTRACT_REVISION,
    "scope": (
        "This file discloses interface mechanics only. Enum availability does not imply that "
        "a value is scientifically appropriate. The evidence, not this contract, determines "
        "the analysis, resource and decision."
    ),
    "policy": {
        "additional_fields_allowed": True,
        "exact_matching": (
            "Only schema_version, disclosed enums, resource IDs, identifiers/references, "
            "column roles and other machine-readable values below use exact matching."
        ),
        "prose_scoring": (
            "Free text must be nonempty where stated but is not matched to private words or "
            "phrases and cannot independently pass or fail a scientific requirement."
        ),
        "paths": (
            "All paths are workspace-relative; supplied evidence is immutable; write "
            "derived files under work/."
        ),
        "schema_feedback": (
            "Invalid submissions return recoverable issues with path, code and message."
        ),
        "identifier_pattern": IDENTIFIER_PATTERN,
        "identifier_rule": (
            "Identifiers begin with a letter, contain only letters, digits, dot, colon, "
            "underscore or hyphen, have at most 128 characters, and are unique where "
            "unique_by is declared."
        ),
        "array_rule": (
            "Every array<string> entry must be nonempty text, including arrays allowed "
            "to be empty."
        ),
        "finite_number_rule": "Finite numbers exclude booleans, NaN and infinities.",
        "tool_call_limit": 80,
    },
    "enums": ENUMS,
    "objects": {
        "validation_plan": {"fields": VALIDATION_PLAN_FIELDS},
        "followup_plan": {"fields": FOLLOWUP_PLAN_FIELDS},
        "final_submission": {"fields": FINAL_SUBMISSION_FIELDS},
    },
    "relationships_and_conditionals": RELATIONSHIP_CONSTRAINTS,
    "action_sequence": ACTION_SEQUENCE,
}


__all__ = [
    "ACTION_SEQUENCE",
    "CONTRACT_REVISION",
    "DECISION_FIELDS",
    "ENUMS",
    "FINAL_SUBMISSION_FIELDS",
    "FOLLOWUP_PLAN_FIELDS",
    "IDENTIFIER_PATTERN",
    "RC14_AGENT_VISIBLE_CONTRACT",
    "RELATIONSHIP_CONSTRAINTS",
    "UNIT_OF_ANALYSIS_VALUES",
    "VALIDATION_PLAN_FIELDS",
]

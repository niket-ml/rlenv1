"""Mechanical-only schema for the open-ended MMMVP interface."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
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

SCHEMA_VERSION = "mmmvp-open-rc1-2"
RESOURCE_IDS = {"none", "X17", "X24", "X31", "X46", "X58", "X63"}
EVIDENCE_TARGETS = {
    "RECORD_LINKAGE",
    "ENDPOINT_REVIEW",
    "PIPELINE_REPLAY",
    "EXTERNAL_COHORT",
    "ADDITIONAL_SAMPLE",
    "EXPERT_REVIEW",
    "NO_NEW_EVIDENCE",
}
DEVELOPMENT_STAGES = {
    "DISCOVERY",
    "INTERNAL_VALIDATION",
    "EXTERNAL_VALIDATION",
    "PROSPECTIVE_EVALUATION",
    "STOPPED",
}
DISPOSITIONS = {"CONTINUE", "PAUSE", "STOP", "INSUFFICIENT_EVIDENCE"}
USE_SCOPES = {
    "NO_USE",
    "RETROSPECTIVE_AUDIT",
    "RESEARCH_RANKING",
    "RESEARCH_PROBABILITY",
    "CLINICAL_DECISION_SUPPORT",
    "TREATMENT_SELECTION",
}
ARTIFACT_ROLES = {"ANALYSIS_TABLE", "CALCULATION_OUTPUT", "CODE", "PROVENANCE", "OTHER"}
FINDING_STATUSES = {"SUPPORTED", "REFUTED", "UNRESOLVED"}
DECISION_EFFECTS = {"SUPPORTS", "WEAKENS", "INVALIDATES", "NONE"}
CLAIM_STATUSES = {"SUPPORTED", "NOT_SUPPORTED", "UNRESOLVED"}
CLAIM_SCOPES = {
    "PROGNOSTIC_RANKING",
    "PROGNOSTIC_PROBABILITY",
    "INDEPENDENT_VALIDATION",
    "CLINICAL_UTILITY",
    "TREATMENT_EFFECT",
    "CROSS_CONTEXT_TRANSPORT",
}
BELIEF_DIRECTIONS = {"INCREASE", "DECREASE", "UNCHANGED"}
CRITERION_COMPARATORS = {"AT_LEAST", "AT_MOST"}
_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")

AGENT_VISIBLE_CONTRACT: dict[str, Any] = {
    "schema_version": SCHEMA_VERSION,
    "policy": {
        "additional_fields_allowed": True,
        "prose_scoring": "presence only; scientific meaning is not exact-matched",
        "paths": "workspace-relative",
    },
    "mechanical_constraints": [
        "All required text fields are nonempty.",
        (
            "All identifier fields begin with a letter, contain only letters, digits, dot, "
            "colon, underscore or hyphen, and are unique within their array."
        ),
        (
            "Committed hypotheses include at least one that would support the declared "
            "development action if true and at least one that would weaken or invalidate it."
        ),
        "All belief, before and after values are numeric and lie in [0,1].",
        (
            "Validation-plan evidence_refs, planned input_paths and planned_output_paths are "
            "nonempty arrays."
        ),
        "Every result contingency has at least one hypothesis update.",
        "Follow-up evidence_refs are a nonempty array and beliefs_before is a nonempty object.",
        (
            "Every scored calculation names one analysis-table artifact, its cohort and "
            "columns, a disclosed metric and estimator, parameters, reported value, evidence "
            "source and saved calculation-output artifact. Agent code is diagnostic-only."
        ),
        (
            "Validation plans commit machine-readable decision criteria before outcomes are "
            "revealed. Final actions are checked against those unchanged criteria."
        ),
        "Artifact and calculation references must name IDs declared in the same final submission.",
        "Finding evidence_refs and evidence-assessment source_paths are nonempty arrays.",
        "Belief-update evidence_refs and final evidence_refs are nonempty arrays.",
        "A claim marked SUPPORTED has nonempty evidence_refs and calculation_ids.",
        (
            "Decision audit fields allowed_use, prohibited_use, unresolved_gates and "
            "required_next_evidence are text arrays and may be empty."
        ),
    ],
    "enums": {
        "resource_id": sorted(RESOURCE_IDS),
        "evidence_target": sorted(EVIDENCE_TARGETS),
        "development_stage": sorted(DEVELOPMENT_STAGES),
        "disposition": sorted(DISPOSITIONS),
        "use_scope": sorted(USE_SCOPES),
        "artifact_role": sorted(ARTIFACT_ROLES),
        "finding_status": sorted(FINDING_STATUSES),
        "decision_effect": sorted(DECISION_EFFECTS),
        "claim_status": sorted(CLAIM_STATUSES),
        "claim_scope": sorted(CLAIM_SCOPES),
        "belief_direction": sorted(BELIEF_DIRECTIONS),
        "calculation_metric": sorted(METRICS),
        "calculation_estimator": sorted(ESTIMATORS),
        "calculation_role": sorted(CALCULATION_ROLES),
        "calculation_evidence_source": sorted(EVIDENCE_SOURCES),
        "analysis_structure": sorted(ANALYSIS_STRUCTURES),
        "aggregation": sorted(AGGREGATIONS),
        "uncertainty_method": sorted(UNCERTAINTY_METHODS),
        "criterion_comparator": sorted(CRITERION_COMPARATORS),
    },
    "objects": {
        "validation_plan": {
            "required": [
                "schema_version",
                "decision_definition",
                "evidence_standard",
                "hypotheses",
                "planned_analyses",
                "decision_criteria",
                "evidence_refs",
            ],
            "minimum_hypotheses": 1,
            "minimum_planned_analyses": 1,
            "hypotheses_item": [
                "hypothesis_id",
                "statement",
                "belief",
                "decision_effect_if_true",
            ],
            "planned_analyses_item": [
                "analysis_id",
                "question",
                "method",
                "analysis_unit",
                "input_paths",
                "planned_output_paths",
                "decision_relevance",
            ],
            "decision_criteria_item": [
                "criterion_id",
                "calculation_id",
                "metric",
                "comparator",
                "threshold",
            ],
        },
        "followup_plan": {
            "required": [
                "schema_version",
                "decision_question_id",
                "decision_question",
                "chosen_resource",
                "evidence_target",
                "live_explanations",
                "alternatives_considered",
                "result_contingencies",
                "beliefs_before",
                "current_decision",
                "evidence_refs",
            ],
            "minimum_live_explanations": 2,
            "live_explanations_item": [
                "explanation_id",
                "statement",
                "distinguishing_evidence",
            ],
            "alternatives_considered_item": ["resource_id", "limitations"],
            "minimum_alternatives_considered": 2,
            "minimum_result_contingencies": 2,
            "result_contingencies_item": [
                "contingency_id",
                "observable_result",
                "hypothesis_updates",
                "next_decision",
                "next_action",
            ],
            "hypothesis_updates_item": ["hypothesis_id", "direction"],
        },
        "final_submission": {
            "required": [
                "schema_version",
                "artifact_manifest",
                "calculations",
                "findings",
                "evidence_assessments",
                "belief_updates",
                "decision",
                "claims",
                "remaining_uncertainties",
                "evidence_refs",
            ],
            "minimum_artifacts": 1,
            "minimum_findings": 1,
            "minimum_evidence_assessments": 1,
            "minimum_claims": 1,
            "artifact_manifest_item": {
                "required": ["artifact_id", "path", "role", "source_paths"],
                "optional": ["sha256"],
                "when_role_is_analysis_table": [
                    "column_map",
                    "analysis_structure",
                    "aggregation",
                ],
            },
            "analysis_table_column_map": {
                "required": [
                    "entity_id",
                    "source_record_ids",
                    "prediction",
                    "outcome",
                    "split",
                ],
                "optional": ["context"],
            },
            "typed_calculations_item": [
                "calculation_id",
                "role",
                "source_analysis_table_id",
                "unit_of_analysis",
                "cohort",
                "outcome_column",
                "prediction_column",
                "context_columns",
                "metric",
                "estimator",
                "parameters",
                "reported_value",
                "evidence_source",
                "output_artifact_id",
                "optional uncertainty object",
            ],
            "findings_item": [
                "finding_id",
                "statement",
                "status",
                "decision_effect",
                "evidence_refs",
                "calculation_ids",
            ],
            "evidence_assessments_item": [
                "evidence_id",
                "source_paths",
                "eligible_for_decision",
                "rationale",
            ],
            "belief_updates_item": [
                "hypothesis_id",
                "before",
                "after",
                "evidence_refs",
                "matched_contingency_id",
            ],
            "claims_item": [
                "claim_id",
                "statement",
                "status",
                "scope",
                "evidence_refs",
                "calculation_ids",
            ],
            "decision_object": [
                "development_stage",
                "disposition",
                "use_scope",
                "allowed_use",
                "prohibited_use",
                "unresolved_gates",
                "required_next_evidence",
            ],
        },
    },
}


@dataclass(frozen=True, slots=True)
class OpenSchemaIssue:
    path: str
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"path": self.path, "code": self.code, "message": self.message}


@dataclass(frozen=True, slots=True)
class OpenSchemaResult:
    object_type: str
    issues: tuple[OpenSchemaIssue, ...]

    @property
    def valid(self) -> bool:
        return not self.issues


def _issue(issues: list[OpenSchemaIssue], path: str, code: str, message: str) -> None:
    issues.append(OpenSchemaIssue(path, code, message))


def _object(value: Any, path: str, issues: list[OpenSchemaIssue]) -> dict[str, Any]:
    if not isinstance(value, dict):
        _issue(issues, path, "object_required", "Expected a JSON object")
        return {}
    return value


def _text(value: Any, path: str, issues: list[OpenSchemaIssue]) -> None:
    if not isinstance(value, str) or not value.strip():
        _issue(issues, path, "text_required", "Expected nonempty text")


def _identifier(value: Any, path: str, issues: list[OpenSchemaIssue]) -> None:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        _issue(issues, path, "identifier_required", "Expected an agent-defined identifier")


def _probability(value: Any, path: str, issues: list[OpenSchemaIssue]) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= float(value) <= 1:
        _issue(issues, path, "probability_required", "Expected a number in [0,1]")


def _finite_number(value: Any, path: str, issues: list[OpenSchemaIssue]) -> None:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
    ):
        _issue(issues, path, "finite_number_required", "Expected a finite number")


def _string_array(
    value: Any,
    path: str,
    issues: list[OpenSchemaIssue],
    *,
    nonempty: bool = False,
) -> list[str]:
    if not isinstance(value, list) or (nonempty and not value):
        _issue(
            issues,
            path,
            "array_required",
            "Expected an array" + (" with entries" if nonempty else ""),
        )
        return []
    if not all(isinstance(item, str) and item.strip() for item in value):
        _issue(issues, path, "text_array_required", "Every entry must be nonempty text")
        return []
    return value


def _unique_objects(
    value: Any,
    path: str,
    id_field: str,
    issues: list[OpenSchemaIssue],
    *,
    minimum: int = 0,
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) < minimum:
        _issue(issues, path, "object_array_required", f"Expected at least {minimum} object(s)")
        return []
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        row = _object(item, f"{path}[{index}]", issues)
        identifier = row.get(id_field)
        _identifier(identifier, f"{path}[{index}].{id_field}", issues)
        if isinstance(identifier, str):
            if identifier in seen:
                _issue(
                    issues,
                    f"{path}[{index}].{id_field}",
                    "duplicate_identifier",
                    "Identifier must be unique",
                )
            seen.add(identifier)
        rows.append(row)
    return rows


def _version(payload: Any, object_type: str, issues: list[OpenSchemaIssue]) -> dict[str, Any]:
    value = _object(payload, "$", issues)
    if value.get("schema_version") != SCHEMA_VERSION:
        _issue(issues, "schema_version", "invalid_schema_version", f"Expected {SCHEMA_VERSION}")
    return value


def _decision(value: Any, path: str, issues: list[OpenSchemaIssue]) -> None:
    row = _object(value, path, issues)
    for field, accepted in (
        ("development_stage", DEVELOPMENT_STAGES),
        ("disposition", DISPOSITIONS),
        ("use_scope", USE_SCOPES),
    ):
        if row.get(field) not in accepted:
            _issue(issues, f"{path}.{field}", "invalid_enum", f"Expected one of {sorted(accepted)}")
    for field in ("allowed_use", "prohibited_use", "unresolved_gates", "required_next_evidence"):
        _string_array(row.get(field), f"{path}.{field}", issues)


def validate_validation_plan(payload: Any) -> OpenSchemaResult:
    issues: list[OpenSchemaIssue] = []
    value = _version(payload, "validation_plan", issues)
    _text(value.get("decision_definition"), "decision_definition", issues)
    _text(value.get("evidence_standard"), "evidence_standard", issues)
    hypotheses = _unique_objects(
        value.get("hypotheses"), "hypotheses", "hypothesis_id", issues, minimum=1
    )
    for index, row in enumerate(hypotheses):
        _text(row.get("statement"), f"hypotheses[{index}].statement", issues)
        _probability(row.get("belief"), f"hypotheses[{index}].belief", issues)
        if row.get("decision_effect_if_true") not in DECISION_EFFECTS:
            _issue(
                issues,
                f"hypotheses[{index}].decision_effect_if_true",
                "invalid_enum",
                f"Expected one of {sorted(DECISION_EFFECTS)}",
            )
    hypothesis_effects = {row.get("decision_effect_if_true") for row in hypotheses}
    if "SUPPORTS" not in hypothesis_effects or not hypothesis_effects.intersection(
        {"WEAKENS", "INVALIDATES"}
    ):
        _issue(
            issues,
            "hypotheses",
            "competing_decision_effects_required",
            "Expected supporting and weakening or invalidating hypotheses",
        )
    analyses = _unique_objects(
        value.get("planned_analyses"), "planned_analyses", "analysis_id", issues, minimum=1
    )
    for index, row in enumerate(analyses):
        base = f"planned_analyses[{index}]"
        for field in ("question", "method", "analysis_unit", "decision_relevance"):
            _text(row.get(field), f"{base}.{field}", issues)
        _string_array(row.get("input_paths"), f"{base}.input_paths", issues, nonempty=True)
        _string_array(
            row.get("planned_output_paths"), f"{base}.planned_output_paths", issues, nonempty=True
        )
    criteria = _unique_objects(
        value.get("decision_criteria"),
        "decision_criteria",
        "criterion_id",
        issues,
        minimum=1,
    )
    for index, row in enumerate(criteria):
        base = f"decision_criteria[{index}]"
        _identifier(row.get("calculation_id"), f"{base}.calculation_id", issues)
        if row.get("metric") not in METRICS:
            _issue(issues, f"{base}.metric", "invalid_enum", "Unknown calculation metric")
        if row.get("comparator") not in CRITERION_COMPARATORS:
            _issue(issues, f"{base}.comparator", "invalid_enum", "Unknown comparator")
        _finite_number(row.get("threshold"), f"{base}.threshold", issues)
    _string_array(value.get("evidence_refs"), "evidence_refs", issues, nonempty=True)
    return OpenSchemaResult("validation_plan", tuple(issues))


def validate_followup_plan(payload: Any) -> OpenSchemaResult:
    issues: list[OpenSchemaIssue] = []
    value = _version(payload, "followup_plan", issues)
    _identifier(value.get("decision_question_id"), "decision_question_id", issues)
    _text(value.get("decision_question"), "decision_question", issues)
    if value.get("chosen_resource") not in RESOURCE_IDS:
        _issue(issues, "chosen_resource", "invalid_enum", f"Expected one of {sorted(RESOURCE_IDS)}")
    if value.get("evidence_target") not in EVIDENCE_TARGETS:
        _issue(
            issues, "evidence_target", "invalid_enum", f"Expected one of {sorted(EVIDENCE_TARGETS)}"
        )
    explanations = _unique_objects(
        value.get("live_explanations"), "live_explanations", "explanation_id", issues, minimum=2
    )
    for index, row in enumerate(explanations):
        _text(row.get("statement"), f"live_explanations[{index}].statement", issues)
        _text(
            row.get("distinguishing_evidence"),
            f"live_explanations[{index}].distinguishing_evidence",
            issues,
        )
    alternatives = value.get("alternatives_considered")
    if not isinstance(alternatives, list) or len(alternatives) < 2:
        _issue(
            issues,
            "alternatives_considered",
            "object_array_required",
            "Expected at least two compared resources",
        )
    else:
        for index, row_value in enumerate(alternatives):
            row = _object(row_value, f"alternatives_considered[{index}]", issues)
            if row.get("resource_id") not in RESOURCE_IDS:
                _issue(
                    issues,
                    f"alternatives_considered[{index}].resource_id",
                    "invalid_enum",
                    "Unknown resource ID",
                )
            _text(row.get("limitations"), f"alternatives_considered[{index}].limitations", issues)
    contingencies = _unique_objects(
        value.get("result_contingencies"),
        "result_contingencies",
        "contingency_id",
        issues,
        minimum=2,
    )
    for index, row in enumerate(contingencies):
        base = f"result_contingencies[{index}]"
        _text(row.get("observable_result"), f"{base}.observable_result", issues)
        _text(row.get("next_action"), f"{base}.next_action", issues)
        _decision(row.get("next_decision"), f"{base}.next_decision", issues)
        updates = row.get("hypothesis_updates")
        if not isinstance(updates, list) or not updates:
            _issue(
                issues,
                f"{base}.hypothesis_updates",
                "object_array_required",
                "Expected at least one update",
            )
        else:
            for update_index, update_value in enumerate(updates):
                update = _object(update_value, f"{base}.hypothesis_updates[{update_index}]", issues)
                _identifier(
                    update.get("hypothesis_id"),
                    f"{base}.hypothesis_updates[{update_index}].hypothesis_id",
                    issues,
                )
                if update.get("direction") not in BELIEF_DIRECTIONS:
                    _issue(
                        issues,
                        f"{base}.hypothesis_updates[{update_index}].direction",
                        "invalid_enum",
                        "Unknown direction",
                    )
    beliefs = value.get("beliefs_before")
    if not isinstance(beliefs, dict) or not beliefs:
        _issue(issues, "beliefs_before", "object_required", "Expected hypothesis probabilities")
    else:
        for hypothesis_id, belief in beliefs.items():
            _identifier(hypothesis_id, f"beliefs_before.{hypothesis_id}", issues)
            _probability(belief, f"beliefs_before.{hypothesis_id}", issues)
    _decision(value.get("current_decision"), "current_decision", issues)
    _string_array(value.get("evidence_refs"), "evidence_refs", issues, nonempty=True)
    return OpenSchemaResult("followup_plan", tuple(issues))


def validate_final_submission(payload: Any) -> OpenSchemaResult:
    issues: list[OpenSchemaIssue] = []
    value = _version(payload, "final_submission", issues)
    artifacts = _unique_objects(
        value.get("artifact_manifest"), "artifact_manifest", "artifact_id", issues, minimum=1
    )
    artifact_ids = {
        row.get("artifact_id") for row in artifacts if isinstance(row.get("artifact_id"), str)
    }
    for index, row in enumerate(artifacts):
        base = f"artifact_manifest[{index}]"
        _text(row.get("path"), f"{base}.path", issues)
        if row.get("role") not in ARTIFACT_ROLES:
            _issue(
                issues, f"{base}.role", "invalid_enum", f"Expected one of {sorted(ARTIFACT_ROLES)}"
            )
        _string_array(row.get("source_paths"), f"{base}.source_paths", issues)
        if row.get("role") == "ANALYSIS_TABLE":
            if row.get("analysis_structure") not in ANALYSIS_STRUCTURES:
                _issue(
                    issues,
                    f"{base}.analysis_structure",
                    "invalid_enum",
                    "Unknown analysis structure",
                )
            if row.get("aggregation") not in AGGREGATIONS:
                _issue(
                    issues,
                    f"{base}.aggregation",
                    "invalid_enum",
                    "Unknown aggregation",
                )
            column_map = row.get("column_map")
            if not isinstance(column_map, dict):
                _issue(
                    issues,
                    f"{base}.column_map",
                    "object_required",
                    "ANALYSIS_TABLE requires a semantic column map",
                )
            else:
                required_roles = {
                    "entity_id",
                    "source_record_ids",
                    "prediction",
                    "outcome",
                    "split",
                }
                if not required_roles <= set(column_map):
                    _issue(
                        issues,
                        f"{base}.column_map",
                        "missing_column_role",
                        f"Expected roles {sorted(required_roles)}",
                    )
                for role, column in column_map.items():
                    if role not in required_roles | {"context"}:
                        _issue(
                            issues,
                            f"{base}.column_map.{role}",
                            "unknown_column_role",
                            "Unknown semantic column role",
                        )
                    _text(column, f"{base}.column_map.{role}", issues)
    calculations = _unique_objects(
        value.get("calculations"), "calculations", "calculation_id", issues
    )
    calculation_ids = {
        row.get("calculation_id")
        for row in calculations
        if isinstance(row.get("calculation_id"), str)
    }
    for index, row in enumerate(calculations):
        base = f"calculations[{index}]"
        if row.get("role") not in CALCULATION_ROLES:
            _issue(issues, f"{base}.role", "invalid_enum", "Unknown calculation role")
        source_table = row.get("source_analysis_table_id")
        _identifier(source_table, f"{base}.source_analysis_table_id", issues)
        if source_table not in artifact_ids:
            _issue(
                issues,
                f"{base}.source_analysis_table_id",
                "unknown_reference",
                "Unknown analysis-table artifact ID",
            )
        if row.get("unit_of_analysis") not in {
            "BIOLOGICAL_ENTITY",
            "SOURCE_RECORD_CLUSTERED",
        }:
            _issue(issues, f"{base}.unit_of_analysis", "invalid_enum", "Unknown analysis unit")
        cohort = _object(row.get("cohort"), f"{base}.cohort", issues)
        _string_array(
            cohort.get("split_values"), f"{base}.cohort.split_values", issues, nonempty=True
        )
        _string_array(cohort.get("entity_ids", []), f"{base}.cohort.entity_ids", issues)
        count = cohort.get("included_row_count")
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            _issue(
                issues,
                f"{base}.cohort.included_row_count",
                "positive_integer_required",
                "Expected a positive row count",
            )
        for field in ("outcome_column", "prediction_column"):
            _text(row.get(field), f"{base}.{field}", issues)
        _string_array(row.get("context_columns"), f"{base}.context_columns", issues)
        if row.get("metric") not in METRICS:
            _issue(issues, f"{base}.metric", "invalid_enum", "Unknown calculation metric")
        if row.get("estimator") not in ESTIMATORS:
            _issue(issues, f"{base}.estimator", "invalid_enum", "Unknown estimator")
        if not isinstance(row.get("parameters"), dict):
            _issue(issues, f"{base}.parameters", "object_required", "Expected an object")
        _finite_number(row.get("reported_value"), f"{base}.reported_value", issues)
        if row.get("evidence_source") not in EVIDENCE_SOURCES:
            _issue(issues, f"{base}.evidence_source", "invalid_enum", "Unknown evidence source")
        _identifier(row.get("output_artifact_id"), f"{base}.output_artifact_id", issues)
        if row.get("output_artifact_id") not in artifact_ids:
            _issue(issues, f"{base}.output_artifact_id", "unknown_reference", "Unknown artifact ID")
        uncertainty = row.get("uncertainty")
        if uncertainty is not None:
            uncertainty_row = _object(uncertainty, f"{base}.uncertainty", issues)
            if uncertainty_row.get("method") not in UNCERTAINTY_METHODS:
                _issue(
                    issues,
                    f"{base}.uncertainty.method",
                    "invalid_enum",
                    "Unknown uncertainty method",
                )
            _probability(uncertainty_row.get("level"), f"{base}.uncertainty.level", issues)
            for field in ("lower", "upper"):
                _finite_number(uncertainty_row.get(field), f"{base}.uncertainty.{field}", issues)
            for field in ("replicates", "seed"):
                item = uncertainty_row.get(field)
                if not isinstance(item, int) or isinstance(item, bool):
                    _issue(
                        issues,
                        f"{base}.uncertainty.{field}",
                        "integer_required",
                        "Expected an integer",
                    )
    findings = _unique_objects(value.get("findings"), "findings", "finding_id", issues, minimum=1)
    for index, row in enumerate(findings):
        base = f"findings[{index}]"
        _text(row.get("statement"), f"{base}.statement", issues)
        if row.get("status") not in FINDING_STATUSES:
            _issue(issues, f"{base}.status", "invalid_enum", "Unknown finding status")
        if row.get("decision_effect") not in DECISION_EFFECTS:
            _issue(issues, f"{base}.decision_effect", "invalid_enum", "Unknown decision effect")
        _string_array(row.get("evidence_refs"), f"{base}.evidence_refs", issues, nonempty=True)
        refs = _string_array(row.get("calculation_ids"), f"{base}.calculation_ids", issues)
        if not set(refs) <= calculation_ids:
            _issue(issues, f"{base}.calculation_ids", "unknown_reference", "Unknown calculation ID")
    assessments = _unique_objects(
        value.get("evidence_assessments"), "evidence_assessments", "evidence_id", issues, minimum=1
    )
    for index, row in enumerate(assessments):
        base = f"evidence_assessments[{index}]"
        _string_array(row.get("source_paths"), f"{base}.source_paths", issues, nonempty=True)
        if not isinstance(row.get("eligible_for_decision"), bool):
            _issue(
                issues,
                f"{base}.eligible_for_decision",
                "boolean_required",
                "Expected true or false",
            )
        _text(row.get("rationale"), f"{base}.rationale", issues)
    beliefs = value.get("belief_updates")
    if not isinstance(beliefs, list):
        _issue(issues, "belief_updates", "object_array_required", "Expected an array")
    else:
        for index, row_value in enumerate(beliefs):
            row = _object(row_value, f"belief_updates[{index}]", issues)
            _identifier(row.get("hypothesis_id"), f"belief_updates[{index}].hypothesis_id", issues)
            _probability(row.get("before"), f"belief_updates[{index}].before", issues)
            _probability(row.get("after"), f"belief_updates[{index}].after", issues)
            _string_array(
                row.get("evidence_refs"),
                f"belief_updates[{index}].evidence_refs",
                issues,
                nonempty=True,
            )
            _identifier(
                row.get("matched_contingency_id"),
                f"belief_updates[{index}].matched_contingency_id",
                issues,
            )
    _decision(value.get("decision"), "decision", issues)
    claims = _unique_objects(value.get("claims"), "claims", "claim_id", issues, minimum=1)
    for index, row in enumerate(claims):
        base = f"claims[{index}]"
        _text(row.get("statement"), f"{base}.statement", issues)
        if row.get("status") not in CLAIM_STATUSES:
            _issue(issues, f"{base}.status", "invalid_enum", "Unknown claim status")
        if row.get("scope") not in CLAIM_SCOPES:
            _issue(issues, f"{base}.scope", "invalid_enum", "Unknown claim scope")
        supported = row.get("status") == "SUPPORTED"
        _string_array(
            row.get("evidence_refs"),
            f"{base}.evidence_refs",
            issues,
            nonempty=supported,
        )
        refs = _string_array(
            row.get("calculation_ids"),
            f"{base}.calculation_ids",
            issues,
            nonempty=supported,
        )
        if not set(refs) <= calculation_ids:
            _issue(issues, f"{base}.calculation_ids", "unknown_reference", "Unknown calculation ID")
    _string_array(value.get("remaining_uncertainties"), "remaining_uncertainties", issues)
    _string_array(value.get("evidence_refs"), "evidence_refs", issues, nonempty=True)
    return OpenSchemaResult("final_submission", tuple(issues))


__all__ = [
    "BELIEF_DIRECTIONS",
    "EVIDENCE_TARGETS",
    "RESOURCE_IDS",
    "SCHEMA_VERSION",
    "OpenSchemaIssue",
    "OpenSchemaResult",
    "validate_final_submission",
    "validate_followup_plan",
    "validate_validation_plan",
]

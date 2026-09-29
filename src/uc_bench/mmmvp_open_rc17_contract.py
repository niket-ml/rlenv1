"""Public Case-1 RC1.7 contract and single-source mechanical validation.

RC1.7 deliberately keeps scientific choices in machine fields only where the
hidden verifier must reproduce them. Prose is retained for audit and never
determines mission credit.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from uc_bench.mmmvp_open_rc14_contract import (
    ENUMS as LEGACY_ENUMS,
)
from uc_bench.mmmvp_open_rc14_contract import (
    FINAL_SUBMISSION_FIELDS,
    FOLLOWUP_PLAN_FIELDS,
    RELATIONSHIP_CONSTRAINTS,
    VALIDATION_PLAN_FIELDS,
)
from uc_bench.mmmvp_open_schema import (
    SCHEMA_VERSION as LEGACY_SCHEMA_VERSION,
)
from uc_bench.mmmvp_open_schema import (
    OpenSchemaIssue,
    OpenSchemaResult,
)
from uc_bench.mmmvp_open_schema import (
    validate_final_submission as validate_legacy_final,
)
from uc_bench.mmmvp_open_schema import (
    validate_followup_plan as validate_legacy_followup,
)
from uc_bench.mmmvp_open_schema import (
    validate_validation_plan as validate_legacy_validation,
)

SCHEMA_VERSION = "mmmvp-open-case1-rc1-7"

BIOLOGICAL_UNITS = {"PERSON"}
DEPENDENCE_RULES = {"PERSON_LEVEL_AGGREGATION", "SOURCE_RECORD_CLUSTERING"}
AGGREGATIONS = {"MEAN", "MEDIAN", "FIRST", "NONE"}
OUTCOME_ROLES = {"SEALED_VALIDATION_OUTCOMES"}
PRIMARY_METRICS = {
    "ROC_AUC",
    "BINARY_CONCORDANCE",
    "BRIER_SCORE",
    "LOG_LOSS",
    "CALIBRATION_ERROR",
    "NET_BENEFIT",
    "THRESHOLD_EXPECTED_UTILITY",
    "SITE_WEIGHTED_ROC_AUC",
    "WORST_SITE_ROC_AUC",
    "ENTITY_COUNT",
}
UNCERTAINTY_METHODS = {
    "ENTITY_BOOTSTRAP_PERCENTILE",
    "CLUSTER_BOOTSTRAP_PERCENTILE",
}
CRITERION_PROPERTIES = {
    "DISCRIMINATION",
    "PROBABILITY_ACCURACY",
    "CALIBRATION",
    "THRESHOLD_UTILITY",
    "CONTEXT_ROBUSTNESS",
}
QUESTION_RESOURCE = {
    "IDENTITY_LINKAGE": "X17",
    "ENDPOINT_VALIDITY": "X24",
    "PIPELINE_REPRODUCIBILITY": "X31",
    "CROSS_CONTEXT_TRANSPORT": "X46",
    "PRECISION_WITH_SAME_PROCESS": "X58",
    "EXPERT_INTERPRETATION": "X63",
    "CURRENT_DECISION_ALREADY_RESOLVED": "none",
}
EVIDENCE_TARGET = {
    "IDENTITY_LINKAGE": "RECORD_LINKAGE",
    "ENDPOINT_VALIDITY": "ENDPOINT_REVIEW",
    "PIPELINE_REPRODUCIBILITY": "PIPELINE_REPLAY",
    "CROSS_CONTEXT_TRANSPORT": "EXTERNAL_COHORT",
    "PRECISION_WITH_SAME_PROCESS": "ADDITIONAL_SAMPLE",
    "EXPERT_INTERPRETATION": "EXPERT_REVIEW",
    "CURRENT_DECISION_ALREADY_RESOLVED": "NO_NEW_EVIDENCE",
}
RESOURCE_EFFECTS = {
    "RESOLVES",
    "REDUCES_UNCERTAINTY",
    "EXPOSES_BLOCKER",
    "INEFFECTIVE",
    "MISLEADING_REASSURANCE",
    "NO_NEW_EVIDENCE",
}
EXCLUSION_REASONS = {
    "PREOUTCOME_ENDPOINT_AMBIGUITY",
    "PREOUTCOME_MISSING_PREDICTION",
}

METRIC_ALIASES = {
    "BINARY_CONCORDANCE": "ROC_AUC",
    "THRESHOLD_EXPECTED_UTILITY": "NET_BENEFIT",
}
UNCERTAINTY_ALIASES = {
    "ENTITY_BOOTSTRAP_PERCENTILE": "CLUSTER_BOOTSTRAP_PERCENTILE",
}

NON_VACUITY = {
    "DISCRIMINATION": {
        "comparator": "AT_LEAST",
        "threshold_bound": {"at_least": 0.7},
        "uncertainty_lower_bound": 0.58,
        "reason": "must meet or exceed the public intended-use discrimination gate",
    },
    "PROBABILITY_ACCURACY": {
        "comparator": "AT_MOST",
        "metric_bounds": {
            "BRIER_SCORE": {"at_most": 0.23},
            "LOG_LOSS": {"less_than": 0.6931471805599453},
        },
        "reason": (
            "Brier must meet the public intended-use gate; log loss must beat the "
            "uninformative 0.5-probability forecast"
        ),
    },
    "CALIBRATION": {
        "comparator": "AT_MOST",
        "threshold_bound": {"at_most": 0.12},
        "reason": "must meet or improve on the public intended-use calibration gate",
    },
    "THRESHOLD_UTILITY": {
        "comparator": "AT_LEAST",
        "strict_threshold_bound": {"greater_than": 0.0},
        "reason": "must require positive utility over treat-none at the stated threshold",
    },
    "CONTEXT_ROBUSTNESS": {
        "comparator": "AT_LEAST",
        "strict_threshold_bound": {"greater_than": 0.5},
        "reason": "must exclude a below-chance worst/context-weighted result",
    },
}

RESOURCE_MATERIALITY_RULES = {
    "none": (
        "Valid only when the verified primary evidence resolves the bounded immediate decision "
        "and no visible outcome-provenance flag requires adjudication. It adds no evidence and "
        "material must be false."
    ),
    "X17": (
        "Material only if the returned crosswalk leaves unresolved records or changes the "
        "person/source-record membership implied by the visible authoritative identity "
        "declaration."
    ),
    "X24": (
        "Material when visible provenance makes endpoint adjudication an unresolved gate and "
        "the blinded adjudication resolves that gate, whether or not labels change. A changed "
        "label set or harmful corrected result must change the decision."
    ),
    "X31": (
        "Receives decision-relevant credit only when the absolute replay-versus-primary "
        "discrimination difference exceeds the prospectively committed materiality threshold."
    ),
    "X46": (
        "Material when transport is the declared unresolved decision question and the returned "
        "matched-context result is used to bound or block the final claim."
    ),
    "X58": (
        "Material when the additional same-process sample crosses a committed performance gate, "
        "exposes harm, or changes a performance estimate by more than the committed threshold."
    ),
    "X63": (
        "Material only when the declared uncertainty is interpretive and the returned memo adds "
        "decision-relevant information not already present in the packet; recommendations alone "
        "do not create empirical evidence."
    ),
}
RESOURCE_MINIMUM_MATERIALITY = {
    "X31": 0.02,
    "X46": 0.02,
    "X58": 0.02,
}

SUPPORTED_METHODS = {
    "dependence": [
        "one row per person using predeclared MEAN, MEDIAN or FIRST aggregation",
        "all source rows with ENTITY_WEIGHTED estimation and cluster bootstrap",
    ],
    "discrimination": ["ROC_AUC", "BINARY_CONCORDANCE"],
    "probability_accuracy": ["BRIER_SCORE", "LOG_LOSS"],
    "calibration": ["CALIBRATION_ERROR with 2-20 predeclared bins"],
    "threshold_utility": ["NET_BENEFIT", "THRESHOLD_EXPECTED_UTILITY"],
    "uncertainty": [
        "ENTITY_BOOTSTRAP_PERCENTILE for one-row-per-person tables",
        "CLUSTER_BOOTSTRAP_PERCENTILE for dependence-preserving source-row tables",
    ],
    "context_robustness": ["WORST_SITE_ROC_AUC", "SITE_WEIGHTED_ROC_AUC"],
    "outside_release": [
        "Bayesian intervals, DeLong intervals and model-refitting workflows are not "
        "machine-recomputed in RC1.7",
    ],
}

METHOD_DEFINITIONS = {
    "person_level_aggregation": {
        "MEAN": "arithmetic mean of all eligible source-record probabilities per person",
        "MEDIAN": "median of all eligible source-record probabilities per person",
        "FIRST": "probability from the lexicographically first source_record_id per person",
    },
    "ENTITY_WEIGHTED": (
        "retain source rows and assign each row weight 1 divided by that person's included "
        "source-row count, so every person has total weight one"
    ),
    "ROC_AUC_and_BINARY_CONCORDANCE": (
        "weighted binary concordance: the probability a randomly weighted positive scores "
        "above a randomly weighted negative, with ties contributing one half"
    ),
    "BRIER_SCORE": "weighted mean of (predicted_probability - binary_outcome)^2",
    "LOG_LOSS": "weighted binary cross-entropy using finite probabilities in [0,1]",
    "CALIBRATION_ERROR": (
        "weighted expected calibration error over predeclared equal-width probability bins; "
        "empty bins contribute zero and probability 1 belongs to the last bin"
    ),
    "NET_BENEFIT_and_THRESHOLD_EXPECTED_UTILITY": (
        "weighted TP/N - weighted FP/N * threshold/(1-threshold); the expected-utility "
        "alias uses true-positive value 1 and false-positive cost threshold/(1-threshold)"
    ),
    "SITE_WEIGHTED_ROC_AUC": (
        "weighted mean of site-specific ROC AUC, weighted by site total analysis weight; "
        "sites with only one observed class are omitted"
    ),
    "WORST_SITE_ROC_AUC": (
        "minimum site-specific ROC AUC among sites containing both observed classes"
    ),
    "bootstrap": (
        "sample persons with replacement using Python random.Random(seed), retain all rows of "
        "each sampled person, omit one-class replicates, require at least 90% valid replicates, "
        "sort estimates, and use floor/ceil empirical percentile indices at the declared level"
    ),
    "rounding_tolerance": "reported metrics are accepted within absolute tolerance 0.002",
}


def _successor_fields(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    value = copy.deepcopy(rows)
    for row in value:
        if row["path"] == "schema_version":
            row["notes"] = f"must equal {SCHEMA_VERSION!r}"
        if row.get("enum") == "calculation_metric":
            row["enum"] = "primary_metric"
        if row.get("enum") == "uncertainty_method":
            row["enum"] = "uncertainty_method"
    return value


def _successor_relationships() -> list[dict[str, str]]:
    result = copy.deepcopy(RELATIONSHIP_CONSTRAINTS)
    for row in result:
        if row["id"] == "calculation_structure_estimator":
            row["rule"] = (
                "ENTITY_AGGREGATED tables use EMPIRICAL. Primary SOURCE_RECORD_CLUSTERED "
                "tables use ENTITY_WEIGHTED. ROW_EMPIRICAL is diagnostic-only and cannot "
                "support a decision or claim."
            )
        if row["id"] == "calculation_uncertainty":
            row["rule"] = (
                "Discrimination uncertainty uses ENTITY_BOOTSTRAP_PERCENTILE for one row per "
                "person or CLUSTER_BOOTSTRAP_PERCENTILE for retained source rows. Both invoke "
                "the patient-resampling definition in method_definitions.json; replicates are "
                "100-2000 and independently recomputed bounds match within 0.02."
            )
        if row["id"] == "calculation_cohort_alignment":
            row["rule"] = (
                "Primary calculation cohort.entity_ids must equal the complete prospectively "
                "included person set; post-reveal primary filtering is forbidden. "
                "included_row_count must equal the resulting nonempty row count. Entity filters "
                "are permitted only for clearly diagnostic or follow-up calculations."
            )
        if row["id"] == "calculation_parameters":
            row["rule"] = (
                "CALIBRATION_ERROR uses the precommitted 2-20 bin_count and threshold utility "
                "uses the precommitted intended-use threshold. Final primary parameters must "
                "exactly match the validation plan; other supported metric parameters may be "
                "an empty object."
            )
        if row["id"] == "artifact_paths_and_hashes":
            row["rule"] = (
                "Every decision-linked manifest path and source_path must resolve to an "
                "existing workspace file without absolute paths or parent traversal. If "
                "sha256 is supplied it must match. An unlinked optional artifact is diagnostic "
                "only and cannot invalidate an otherwise correct primary chain."
            )
    return result


def _field(path: str, required: bool, description: str, enum: str | None = None) -> dict[str, Any]:
    row: dict[str, Any] = {"path": path, "required": required, "description": description}
    if enum:
        row["enum"] = enum
    return row


PUBLIC_CONTRACT: dict[str, Any] = {
    "contract_revision": "case1-rc1.7",
    "payload_schema_version": SCHEMA_VERSION,
    "principles": [
        "The agent chooses the scientific workflow within the supported families below.",
        "Prose is never exact-matched and cannot independently pass or fail science.",
        "Every decision-driving result must be saved and independently reproducible.",
        "The primary cohort, dependence rule, estimands and criteria are bound before reveal.",
    ],
    "action_sequence": [
        "commit_validation_plan",
        "reveal_validation",
        "commit_followup_plan",
        "purchase_resource",
        "submit",
    ],
    "enums": {
        **LEGACY_ENUMS,
        "calculation_metric": sorted(PRIMARY_METRICS),
        "uncertainty_method": sorted(UNCERTAINTY_METHODS),
        "biological_unit": sorted(BIOLOGICAL_UNITS),
        "dependence_handling": sorted(DEPENDENCE_RULES),
        "aggregation": sorted(AGGREGATIONS),
        "outcome_role": sorted(OUTCOME_ROLES),
        "primary_metric": sorted(PRIMARY_METRICS),
        "criterion_property": sorted(CRITERION_PROPERTIES),
        "decision_question_type": sorted(QUESTION_RESOURCE),
        "resource_effect": sorted(RESOURCE_EFFECTS),
        "preoutcome_exclusion_reason": sorted(EXCLUSION_REASONS),
    },
    "supported_methods": SUPPORTED_METHODS,
    "non_vacuity": NON_VACUITY,
    "resource_question_mapping": QUESTION_RESOURCE,
    "resource_evidence_target_mapping": EVIDENCE_TARGET,
    "resource_materiality_rules": RESOURCE_MATERIALITY_RULES,
    "resource_minimum_materiality_thresholds": RESOURCE_MINIMUM_MATERIALITY,
    "prospective_binding": {
        "eligible_manifest_columns": [
            "entity_id",
            "source_record_ids",
            "included",
            "preoutcome_exclusion_reason",
        ],
        "rules": [
            "The manifest must contain every baseline-eligible person visible before reveal.",
            "Excluded people remain listed with included=false and a pre-outcome reason.",
            "The manifest path and SHA-256 are committed before reveal.",
            "The primary analysis must use exactly the included manifest entities and "
            "source records.",
            "SEALED_VALIDATION_OUTCOMES is a symbolic role; the environment binds its path "
            "and hash after reveal.",
        ],
    },
    "objects": {
        "validation_plan": {
            "fields": _successor_fields(VALIDATION_PLAN_FIELDS),
            "additional_required": [
                _field(
                    "prospective_specification.biological_unit",
                    True,
                    "Decision unit",
                    "biological_unit",
                ),
                _field(
                    "prospective_specification.dependence_handling",
                    True,
                    "Dependence rule",
                    "dependence_handling",
                ),
                _field(
                    "prospective_specification.aggregation",
                    True,
                    "Aggregation; NONE only for clustered rows",
                    "aggregation",
                ),
                _field(
                    "prospective_specification.eligible_entity_manifest_path",
                    True,
                    "Existing work/ CSV path",
                ),
                _field(
                    "prospective_specification.eligible_entity_manifest_sha256",
                    True,
                    "Lower-case SHA-256",
                ),
                _field(
                    "prospective_specification.identity_provenance_path",
                    True,
                    "Visible authoritative identifier declaration",
                ),
                _field(
                    "prospective_specification.outcome_role",
                    True,
                    "Symbolic future outcome role",
                    "outcome_role",
                ),
                _field("prospective_specification.estimator", True, "EMPIRICAL or ENTITY_WEIGHTED"),
                _field(
                    "prospective_specification.discrimination_metric",
                    True,
                    "Supported discrimination metric",
                    "primary_metric",
                ),
                _field(
                    "prospective_specification.probability_metric",
                    True,
                    "BRIER_SCORE or LOG_LOSS",
                    "primary_metric",
                ),
                _field(
                    "prospective_specification.calibration_metric",
                    True,
                    "CALIBRATION_ERROR",
                    "primary_metric",
                ),
                _field("prospective_specification.calibration_bin_count", True, "Integer 2-20"),
                _field(
                    "prospective_specification.utility_metric",
                    True,
                    "Supported threshold utility",
                    "primary_metric",
                ),
                _field(
                    "prospective_specification.utility_threshold",
                    True,
                    "Must equal intended-use threshold",
                ),
                _field(
                    "prospective_specification.context_metric",
                    True,
                    "Supported site robustness metric",
                    "primary_metric",
                ),
                _field(
                    "prospective_specification.uncertainty_method",
                    True,
                    "Patient-respecting method",
                    "uncertainty_method",
                ),
                _field(
                    "prospective_specification.uncertainty_replicates", True, "Integer 100-2000"
                ),
                _field("prospective_specification.uncertainty_seed", True, "Integer"),
                _field("prospective_specification.uncertainty_level", True, "Number in [0.8,0.99]"),
                _field("prospective_specification.exclusions", True, "Array; may be empty"),
                _field(
                    "decision_criteria[*].property",
                    True,
                    "Exactly one of each required property",
                    "criterion_property",
                ),
            ],
        },
        "followup_plan": {
            "fields": _successor_fields(FOLLOWUP_PLAN_FIELDS),
            "additional_required": [
                _field(
                    "decision_question_type",
                    True,
                    "Machine-readable unresolved question",
                    "decision_question_type",
                ),
                _field(
                    "materiality_threshold",
                    True,
                    "Finite non-negative threshold for a quantitative comparison",
                ),
            ],
        },
        "final_submission": {
            "fields": _successor_fields(FINAL_SUBMISSION_FIELDS),
            "additional_required": [
                _field("resource_assessment.resource_id", True, "Must match event record"),
                _field(
                    "resource_assessment.question_type",
                    True,
                    "Must match follow-up commitment",
                    "decision_question_type",
                ),
                _field(
                    "resource_assessment.summary_artifact_path",
                    True,
                    "Saved standardized resource summary",
                ),
                _field("resource_assessment.source_paths", True, "Returned evidence paths"),
                _field(
                    "resource_assessment.calculation_ids",
                    True,
                    "Relevant typed calculation IDs when the returned package supports the "
                    "typed-table decoder; otherwise the standardized summary results are "
                    "the saved calculations and this array may be empty",
                ),
                _field(
                    "resource_assessment.observed_effect",
                    True,
                    "Evidence effect",
                    "resource_effect",
                ),
                _field(
                    "resource_assessment.material",
                    True,
                    "Boolean result under the committed materiality rule",
                ),
                _field(
                    "narrative_summary", True, "Professional-language audit field; diagnostic only"
                ),
            ],
        },
    },
    "resource_summary_contract": {
        "common_required": ["schema_version", "resource_id", "source_hashes", "results"],
        "result_keys": {
            "none": ["new_evidence"],
            "X17": ["canonical_entity_count", "unresolved_record_count"],
            "X24": [
                "changed_label_count",
                "reviewer_disagreement_count",
                "roc_auc",
                "binary_concordance",
                "brier_score",
                "log_loss",
                "calibration_error",
                "net_benefit",
                "threshold_expected_utility",
                "worst_site_roc_auc",
                "site_weighted_roc_auc",
            ],
            "X31": ["roc_auc", "brier_score", "net_benefit", "primary_auc_absolute_delta"],
            "X46": ["entity_count", "roc_auc", "brier_score", "net_benefit"],
            "X58": ["entity_count", "roc_auc", "brier_score", "net_benefit"],
            "X63": ["new_empirical_evidence", "recommendation_count"],
        },
    },
    "relationships_and_conditionals": [
        *_successor_relationships(),
        {
            "id": "prospective_primary_binding",
            "rule": (
                "All primary decision calculations use exactly the included entities and "
                "source records in the committed manifest and match every committed method "
                "and parameter field."
            ),
        },
        {
            "id": "symbolic_outcome_binding",
            "rule": (
                "SEALED_VALIDATION_OUTCOMES is bound by the environment to an immutable path "
                "and SHA-256 after reveal."
            ),
        },
        {
            "id": "intended_use_parameter_binding",
            "rule": (
                "prospective_specification.utility_threshold must equal the action_threshold "
                "in intended_use.json; decision criteria may be stricter than, but never weaker "
                "than, the public non-vacuity rules."
            ),
        },
        {
            "id": "identity_provenance_binding",
            "rule": (
                "prospective_specification.identity_provenance_path must be "
                "identity_provenance.json, whose committed hash and declared identifier "
                "relationship are independently verified."
            ),
        },
        {
            "id": "resource_question_and_use",
            "rule": (
                "decision_question_type determines both the resource ID and evidence_target. "
                "The returned manifest, standardized summary, actual calculations and final "
                "response must satisfy the disclosed resource_materiality_rules entry and "
                "establish that the evidence answered the declared material question."
            ),
        },
        {
            "id": "criterion_property_metric_binding",
            "rule": (
                "DISCRIMINATION uses ROC_AUC or BINARY_CONCORDANCE; PROBABILITY_ACCURACY uses "
                "BRIER_SCORE or LOG_LOSS; CALIBRATION uses CALIBRATION_ERROR; "
                "THRESHOLD_UTILITY uses NET_BENEFIT or THRESHOLD_EXPECTED_UTILITY; and "
                "CONTEXT_ROBUSTNESS uses SITE_WEIGHTED_ROC_AUC or WORST_SITE_ROC_AUC."
            ),
        },
        {
            "id": "resource_assessment_binding",
            "rule": (
                "resource_assessment resource_id and question_type must match the event record "
                "and follow-up commitment; source_paths, calculation_ids, observed_effect and "
                "material must match independently recomputed returned evidence."
            ),
        },
        {
            "id": "decision_from_criteria_and_followup",
            "rule": (
                "CONTINUE is valid only when every precommitted criterion passes and no "
                "material purchased result exposes a blocker. A valid failure may support "
                "PAUSE, STOP or INSUFFICIENT_EVIDENCE depending on the bounded action."
            ),
        },
        {
            "id": "decision_tuple_consistency",
            "rule": (
                "CONTINUE cannot use NO_USE or a clinical use scope and cannot have stage "
                "STOPPED. STOP requires stage STOPPED and use_scope NO_USE. PAUSE and "
                "INSUFFICIENT_EVIDENCE use NO_USE or RETROSPECTIVE_AUDIT. A continued path "
                "needs a supported SUPPORTS finding; a contained path needs a supported "
                "WEAKENS or INVALIDATES finding. One claim scope cannot have conflicting "
                "machine statuses."
            ),
        },
        {
            "id": "claim_scope_evidence",
            "rule": (
                "RESEARCH_PROBABILITY requires supported prognostic-probability claims backed "
                "by valid primary discrimination, probability and calibration calculations; "
                "RESEARCH_RANKING requires valid primary discrimination. Clinical decision "
                "support, treatment selection/effect, clinical utility, independent validation "
                "and cross-context transport cannot be supported by the internal Case-1 result."
            ),
        },
    ],
    "method_definitions_file": "method_definitions.json",
}


def contract_sha256() -> str:
    raw = json.dumps(PUBLIC_CONTRACT, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def _append(issues: list[OpenSchemaIssue], path: str, code: str, message: str) -> None:
    issues.append(OpenSchemaIssue(path, code, message))


def _legacy_payload(payload: Any) -> Any:
    value = copy.deepcopy(payload)
    if not isinstance(value, dict):
        return value
    value["schema_version"] = LEGACY_SCHEMA_VERSION
    for criterion in value.get("decision_criteria") or []:
        metric = criterion.get("metric")
        criterion["metric"] = METRIC_ALIASES.get(metric, metric)
    for calculation in value.get("calculations") or []:
        metric = calculation.get("metric")
        calculation["metric"] = METRIC_ALIASES.get(metric, metric)
        uncertainty = calculation.get("uncertainty")
        if isinstance(uncertainty, dict):
            method = uncertainty.get("method")
            uncertainty["method"] = UNCERTAINTY_ALIASES.get(method, method)
    return value


def _version(payload: Any, issues: list[OpenSchemaIssue]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        _append(issues, "$", "object_required", "Expected a JSON object")
        return {}
    if payload.get("schema_version") != SCHEMA_VERSION:
        _append(issues, "schema_version", "invalid_schema_version", f"Expected {SCHEMA_VERSION}")
    return payload


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _sha256_text(value: Any) -> bool:
    return (
        isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)
    )


def _criterion_is_nonvacuous(row: dict[str, Any], metric_by_property: dict[str, str]) -> bool:
    prop = row.get("property")
    threshold = row.get("threshold")
    if prop not in NON_VACUITY or not _finite(threshold):
        return False
    rule = NON_VACUITY[prop]
    if row.get("comparator") != rule["comparator"]:
        return False
    if prop == "PROBABILITY_ACCURACY":
        metric = metric_by_property.get(prop)
        bound = rule["metric_bounds"].get(metric or "")
        if not bound:
            return False
        if "at_most" in bound:
            return float(threshold) <= float(bound["at_most"])
        return float(threshold) < float(bound["less_than"])
    bound = rule.get("threshold_bound") or rule.get("strict_threshold_bound")
    if "at_least" in bound:
        return float(threshold) >= float(bound["at_least"])
    if "at_most" in bound:
        return float(threshold) <= float(bound["at_most"])
    if "greater_than" in bound:
        return float(threshold) > float(bound["greater_than"])
    return float(threshold) < float(bound["less_than"])


def validate_validation_plan(payload: Any) -> OpenSchemaResult:
    issues = list(validate_legacy_validation(_legacy_payload(payload)).issues)
    value = _version(payload, issues)
    spec = value.get("prospective_specification")
    if not isinstance(spec, dict):
        _append(issues, "prospective_specification", "object_required", "Expected an object")
        spec = {}
    enum_checks = {
        "biological_unit": BIOLOGICAL_UNITS,
        "dependence_handling": DEPENDENCE_RULES,
        "aggregation": AGGREGATIONS,
        "outcome_role": OUTCOME_ROLES,
        "discrimination_metric": {"ROC_AUC", "BINARY_CONCORDANCE"},
        "probability_metric": {"BRIER_SCORE", "LOG_LOSS"},
        "calibration_metric": {"CALIBRATION_ERROR"},
        "utility_metric": {"NET_BENEFIT", "THRESHOLD_EXPECTED_UTILITY"},
        "context_metric": {"SITE_WEIGHTED_ROC_AUC", "WORST_SITE_ROC_AUC"},
        "uncertainty_method": UNCERTAINTY_METHODS,
        "estimator": {"EMPIRICAL", "ENTITY_WEIGHTED"},
    }
    for field, accepted in enum_checks.items():
        if spec.get(field) not in accepted:
            _append(
                issues,
                f"prospective_specification.{field}",
                "invalid_enum",
                f"Expected one of {sorted(accepted)}",
            )
    for field in ("eligible_entity_manifest_path", "identity_provenance_path"):
        if not isinstance(spec.get(field), str) or not spec[field].strip():
            _append(
                issues,
                f"prospective_specification.{field}",
                "text_required",
                "Expected nonempty text",
            )
    if not _sha256_text(spec.get("eligible_entity_manifest_sha256")):
        _append(
            issues,
            "prospective_specification.eligible_entity_manifest_sha256",
            "sha256_required",
            "Expected a lower-case SHA-256",
        )
    if (
        spec.get("dependence_handling") == "SOURCE_RECORD_CLUSTERING"
        and spec.get("aggregation") != "NONE"
    ):
        _append(
            issues,
            "prospective_specification.aggregation",
            "relationship_error",
            "Clustered source rows require NONE",
        )
    if spec.get("dependence_handling") == "PERSON_LEVEL_AGGREGATION" and spec.get(
        "aggregation"
    ) not in {"MEAN", "MEDIAN", "FIRST"}:
        _append(
            issues,
            "prospective_specification.aggregation",
            "relationship_error",
            "Person-level aggregation requires MEAN, MEDIAN or FIRST",
        )
    if (
        spec.get("dependence_handling") == "PERSON_LEVEL_AGGREGATION"
        and spec.get("estimator") != "EMPIRICAL"
    ):
        _append(
            issues,
            "prospective_specification.estimator",
            "relationship_error",
            "One-row-per-person tables require EMPIRICAL",
        )
    if (
        spec.get("dependence_handling") == "SOURCE_RECORD_CLUSTERING"
        and spec.get("estimator") != "ENTITY_WEIGHTED"
    ):
        _append(
            issues,
            "prospective_specification.estimator",
            "relationship_error",
            "Clustered source rows require ENTITY_WEIGHTED",
        )
    for field, lower, upper in (
        ("calibration_bin_count", 2, 20),
        ("uncertainty_replicates", 100, 2000),
    ):
        item = spec.get(field)
        if not isinstance(item, int) or isinstance(item, bool) or not lower <= item <= upper:
            _append(
                issues,
                f"prospective_specification.{field}",
                "bounded_integer_required",
                f"Expected integer in [{lower},{upper}]",
            )
    if not isinstance(spec.get("uncertainty_seed"), int) or isinstance(
        spec.get("uncertainty_seed"), bool
    ):
        _append(
            issues,
            "prospective_specification.uncertainty_seed",
            "integer_required",
            "Expected an integer",
        )
    if (
        not _finite(spec.get("uncertainty_level"))
        or not 0.8 <= float(spec.get("uncertainty_level", 0)) <= 0.99
    ):
        _append(
            issues,
            "prospective_specification.uncertainty_level",
            "bounded_number_required",
            "Expected a number in [0.8,0.99]",
        )
    if (
        not _finite(spec.get("utility_threshold"))
        or not 0 < float(spec.get("utility_threshold", 0)) < 1
    ):
        _append(
            issues,
            "prospective_specification.utility_threshold",
            "probability_required",
            "Expected a number in (0,1)",
        )
    exclusions = spec.get("exclusions")
    if not isinstance(exclusions, list):
        _append(
            issues, "prospective_specification.exclusions", "array_required", "Expected an array"
        )
    else:
        seen: set[str] = set()
        for index, row in enumerate(exclusions):
            if not isinstance(row, dict):
                _append(
                    issues,
                    f"prospective_specification.exclusions[{index}]",
                    "object_required",
                    "Expected an object",
                )
                continue
            entity = row.get("entity_id")
            if not isinstance(entity, str) or not entity:
                _append(
                    issues,
                    f"prospective_specification.exclusions[{index}].entity_id",
                    "text_required",
                    "Expected an entity ID",
                )
            elif entity in seen:
                _append(
                    issues,
                    f"prospective_specification.exclusions[{index}].entity_id",
                    "duplicate_identifier",
                    "Entity exclusion must be unique",
                )
            else:
                seen.add(entity)
            if row.get("reason") not in EXCLUSION_REASONS:
                _append(
                    issues,
                    f"prospective_specification.exclusions[{index}].reason",
                    "invalid_enum",
                    f"Expected one of {sorted(EXCLUSION_REASONS)}",
                )
            if not isinstance(row.get("evidence_refs"), list) or not row["evidence_refs"]:
                _append(
                    issues,
                    f"prospective_specification.exclusions[{index}].evidence_refs",
                    "nonempty_array_required",
                    "Expected evidence paths",
                )

    criteria = value.get("decision_criteria") or []
    properties = [row.get("property") for row in criteria if isinstance(row, dict)]
    if set(properties) != CRITERION_PROPERTIES or len(properties) != len(CRITERION_PROPERTIES):
        _append(
            issues,
            "decision_criteria",
            "criterion_family_coverage",
            f"Expected exactly one criterion for each {sorted(CRITERION_PROPERTIES)}",
        )
    metric_by_property = {
        "DISCRIMINATION": spec.get("discrimination_metric"),
        "PROBABILITY_ACCURACY": spec.get("probability_metric"),
        "CALIBRATION": spec.get("calibration_metric"),
        "THRESHOLD_UTILITY": spec.get("utility_metric"),
        "CONTEXT_ROBUSTNESS": spec.get("context_metric"),
    }
    for index, row in enumerate(criteria):
        if not isinstance(row, dict):
            continue
        prop = row.get("property")
        if prop not in CRITERION_PROPERTIES:
            _append(
                issues,
                f"decision_criteria[{index}].property",
                "invalid_enum",
                f"Expected one of {sorted(CRITERION_PROPERTIES)}",
            )
            continue
        if row.get("metric") != metric_by_property[prop]:
            _append(
                issues,
                f"decision_criteria[{index}].metric",
                "metric_plan_mismatch",
                "Criterion metric must match the committed method family",
            )
        if not _criterion_is_nonvacuous(row, metric_by_property):
            _append(
                issues,
                f"decision_criteria[{index}]",
                "vacuous_decision_criterion",
                NON_VACUITY[prop]["reason"],
            )
    return OpenSchemaResult("validation_plan", tuple(issues))


def validate_followup_plan(payload: Any) -> OpenSchemaResult:
    issues = list(validate_legacy_followup(_legacy_payload(payload)).issues)
    value = _version(payload, issues)
    question = value.get("decision_question_type")
    if question not in QUESTION_RESOURCE:
        _append(
            issues,
            "decision_question_type",
            "invalid_enum",
            f"Expected one of {sorted(QUESTION_RESOURCE)}",
        )
    elif value.get("chosen_resource") != QUESTION_RESOURCE[question]:
        _append(
            issues,
            "chosen_resource",
            "question_resource_mismatch",
            f"{question} is answered by {QUESTION_RESOURCE[question]}",
        )
    if question in EVIDENCE_TARGET and value.get("evidence_target") != EVIDENCE_TARGET[question]:
        _append(
            issues,
            "evidence_target",
            "question_evidence_target_mismatch",
            f"{question} requires evidence_target {EVIDENCE_TARGET[question]}",
        )
    threshold = value.get("materiality_threshold")
    if not _finite(threshold) or float(threshold) < 0:
        _append(
            issues,
            "materiality_threshold",
            "nonnegative_number_required",
            "Expected a finite non-negative number",
        )
    elif (
        question
        in {
            "CURRENT_DECISION_ALREADY_RESOLVED",
            "IDENTITY_LINKAGE",
            "EXPERT_INTERPRETATION",
        }
        and float(threshold) != 0
    ):
        _append(
            issues,
            "materiality_threshold",
            "nonquantitative_threshold_must_be_zero",
            "Use 0 for none or a non-quantitative resource; returned evidence still "
            "determines materiality",
        )
    elif question in QUESTION_RESOURCE:
        resource = QUESTION_RESOURCE[question]
        minimum = RESOURCE_MINIMUM_MATERIALITY.get(resource)
        if minimum is not None and float(threshold) < minimum:
            _append(
                issues,
                "materiality_threshold",
                "materiality_threshold_below_public_floor",
                f"{resource} requires a threshold of at least {minimum}",
            )
    return OpenSchemaResult("followup_plan", tuple(issues))


def validate_final_submission(payload: Any) -> OpenSchemaResult:
    issues = list(validate_legacy_final(_legacy_payload(payload)).issues)
    value = _version(payload, issues)
    assessment = value.get("resource_assessment")
    if not isinstance(assessment, dict):
        _append(issues, "resource_assessment", "object_required", "Expected an object")
        assessment = {}
    resource = assessment.get("resource_id")
    if resource not in set(QUESTION_RESOURCE.values()):
        _append(issues, "resource_assessment.resource_id", "invalid_enum", "Unknown resource ID")
    if assessment.get("question_type") not in QUESTION_RESOURCE:
        _append(
            issues,
            "resource_assessment.question_type",
            "invalid_enum",
            f"Expected one of {sorted(QUESTION_RESOURCE)}",
        )
    if not isinstance(assessment.get("summary_artifact_path"), str) or not assessment.get(
        "summary_artifact_path"
    ):
        _append(
            issues,
            "resource_assessment.summary_artifact_path",
            "text_required",
            "Expected a saved summary path",
        )
    for field in ("source_paths", "calculation_ids"):
        if not isinstance(assessment.get(field), list):
            _append(issues, f"resource_assessment.{field}", "array_required", "Expected an array")
    if assessment.get("observed_effect") not in RESOURCE_EFFECTS:
        _append(
            issues,
            "resource_assessment.observed_effect",
            "invalid_enum",
            f"Expected one of {sorted(RESOURCE_EFFECTS)}",
        )
    if not isinstance(assessment.get("material"), bool):
        _append(
            issues, "resource_assessment.material", "boolean_required", "Expected true or false"
        )
    if (
        not isinstance(value.get("narrative_summary"), str)
        or not value.get("narrative_summary", "").strip()
    ):
        _append(
            issues,
            "narrative_summary",
            "text_required",
            "Expected nonempty professional-language summary",
        )
    return OpenSchemaResult("final_submission", tuple(issues))


def validate_payload(kind: str, payload: Any) -> OpenSchemaResult:
    validators = {
        "validation": validate_validation_plan,
        "followup": validate_followup_plan,
        "final": validate_final_submission,
    }
    if kind not in validators:
        return OpenSchemaResult(
            kind,
            (
                OpenSchemaIssue(
                    "$", "unknown_payload_kind", "Expected validation, followup or final"
                ),
            ),
        )
    return validators[kind](payload)


def validate_file(kind: str, path: Path) -> OpenSchemaResult:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return OpenSchemaResult(kind, (OpenSchemaIssue("$", "json_required", str(exc)),))
    return validate_payload(kind, payload)


__all__ = [
    "NON_VACUITY",
    "PUBLIC_CONTRACT",
    "QUESTION_RESOURCE",
    "RESOURCE_EFFECTS",
    "SCHEMA_VERSION",
    "SUPPORTED_METHODS",
    "METHOD_DEFINITIONS",
    "contract_sha256",
    "validate_file",
    "validate_final_submission",
    "validate_followup_plan",
    "validate_payload",
    "validate_validation_plan",
]

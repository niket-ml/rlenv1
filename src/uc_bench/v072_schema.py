"""Strict, prose-independent checkpoint interface for UC-Bench v0.7.2.

The interface deliberately accepts only documented field names.  A checkpoint may
place those fields directly at its root (the flat form) or inside ``facts`` (the
nested form).  Explanatory text and annotations are retained but never inspected
by the normalizer or grader.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from typing import Any

SCHEMA_VERSION = "0.7.2-submission-1"
CHECKPOINT_IDS = ("C1", "C2", "C3", "C4", "C5")
DECISION_ENUM = {
    "ADVANCE",
    "CONDITIONAL_ADVANCE",
    "PAUSE",
    "STOP",
    "INSUFFICIENT_EVIDENCE",
}
ANALYSIS_UNIT_ENUM = {"PATIENT", "BIOPSY", "SITE"}
RESOURCE_ENUM = {"none", "X17", "X24", "X31", "X46", "X58", "X63"}
BELIEF_DIRECTION_ENUM = {
    "UNCHANGED_SUPPORTED",
    "MODEST_INCREASE",
    "DECREASE_SITE_BLOCKER_REMAINS",
    "LARGE_DECREASE",
    "INCREASE_AFTER_VALID_REPLAY",
    "DECREASE_UTILITY_CONCERN_CONFIRMED",
}
PRIMARY_METRIC_IDS = {"auc", "brier", "ece", "net_benefit"}
AGGREGATION_METHOD_ENUM = {"MEAN", "MEDIAN", "FIRST_LOCKED"}
CALCULATED_METRIC_IDS = {
    "auc",
    "auc_ci_low",
    "brier",
    "ece",
    "net_benefit",
    "naive_row_auc",
    "site_weighted_auc",
    "worst_site_auc",
}


@dataclass(frozen=True, slots=True)
class SchemaIssue:
    checkpoint: str
    path: str
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class NormalizedCheckpoint:
    checkpoint: str
    facts: dict[str, Any]
    issues: tuple[SchemaIssue, ...]


def _same(left: Any, right: Any) -> bool:
    return json.dumps(left, sort_keys=True, separators=(",", ":"), default=str) == json.dumps(
        right, sort_keys=True, separators=(",", ":"), default=str
    )


def _field(
    checkpoint: str,
    payload: dict[str, Any],
    name: str,
    issues: list[SchemaIssue],
) -> Any:
    """Read one exact field from either documented carrier, rejecting conflicts."""

    direct_present = name in payload
    nested = payload.get("facts")
    nested_present = isinstance(nested, dict) and name in nested
    if direct_present and nested_present and not _same(payload[name], nested[name]):
        issues.append(
            SchemaIssue(
                checkpoint,
                name,
                "conflicting_field",
                f"{name} differs between the flat and nested carriers",
            )
        )
        return None
    if direct_present:
        return payload[name]
    if nested_present:
        return nested[name]
    issues.append(SchemaIssue(checkpoint, name, "missing_field", f"Missing required field: {name}"))
    return None


def _object(
    checkpoint: str,
    path: str,
    value: Any,
    issues: list[SchemaIssue],
) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if value is not None:
        issues.append(SchemaIssue(checkpoint, path, "invalid_type", "Expected an object"))
    return {}


def _require_keys(
    checkpoint: str,
    path: str,
    value: dict[str, Any],
    required: tuple[str, ...],
    issues: list[SchemaIssue],
) -> None:
    for key in required:
        if key not in value:
            issues.append(
                SchemaIssue(
                    checkpoint,
                    f"{path}.{key}",
                    "missing_field",
                    f"Missing required field: {path}.{key}",
                )
            )


def _list(
    checkpoint: str,
    path: str,
    value: Any,
    issues: list[SchemaIssue],
) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is not None:
        issues.append(SchemaIssue(checkpoint, path, "invalid_type", "Expected an array"))
    return []


def _bool(
    checkpoint: str,
    path: str,
    value: Any,
    issues: list[SchemaIssue],
) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is not None:
        issues.append(SchemaIssue(checkpoint, path, "invalid_type", "Expected a boolean"))
    return None


def _number(
    checkpoint: str,
    path: str,
    value: Any,
    issues: list[SchemaIssue],
) -> float | None:
    if isinstance(value, bool):
        value = None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        number = math.nan
    if math.isfinite(number):
        return number
    if value is not None:
        issues.append(SchemaIssue(checkpoint, path, "invalid_type", "Expected a finite number"))
    return None


def _string_list(
    checkpoint: str,
    path: str,
    value: Any,
    issues: list[SchemaIssue],
) -> list[str]:
    rows = _list(checkpoint, path, value, issues)
    if not all(isinstance(row, str) for row in rows):
        issues.append(
            SchemaIssue(checkpoint, path, "invalid_item_type", "Every item must be a string")
        )
        return [row for row in rows if isinstance(row, str)]
    return rows


def _enum(
    checkpoint: str,
    path: str,
    value: Any,
    allowed: set[str],
    issues: list[SchemaIssue],
) -> str | None:
    if isinstance(value, str) and value in allowed:
        return value
    if value is not None:
        issues.append(
            SchemaIssue(
                checkpoint,
                path,
                "invalid_enum",
                f"Expected one of {sorted(allowed)}",
            )
        )
    return None


def _analysis_unit(checkpoint: str, value: Any, issues: list[SchemaIssue]) -> dict[str, Any]:
    if isinstance(value, str):
        level = value
        patient_key = None
    else:
        row = _object(checkpoint, "analysis_unit", value, issues)
        level = row.get("level")
        patient_key = row.get("patient_key")
    return {
        "level": _enum(checkpoint, "analysis_unit.level", level, ANALYSIS_UNIT_ENUM, issues),
        "patient_key": patient_key if isinstance(patient_key, str) else None,
    }


def _evidence(checkpoint: str, value: Any, issues: list[SchemaIssue]) -> dict[str, list[str]]:
    row = _object(checkpoint, "evidence_refs", value, issues)
    result: dict[str, list[str]] = {}
    for conclusion_id, references in row.items():
        if not isinstance(conclusion_id, str):
            issues.append(
                SchemaIssue(checkpoint, "evidence_refs", "invalid_key", "Keys must be strings")
            )
            continue
        result[conclusion_id] = _string_list(
            checkpoint, f"evidence_refs.{conclusion_id}", references, issues
        )
    return result


def _normalize_c1(payload: dict[str, Any], issues: list[SchemaIssue]) -> dict[str, Any]:
    checkpoint = "C1"
    counts = _object(
        checkpoint, "cohort_counts", _field(checkpoint, payload, "cohort_counts", issues), issues
    )
    checks = _object(checkpoint, "checks", _field(checkpoint, payload, "checks", issues), issues)
    findings = _object(
        checkpoint, "findings", _field(checkpoint, payload, "findings", issues), issues
    )
    _require_keys(
        checkpoint,
        "cohort_counts",
        counts,
        ("sample_count", "patient_count", "site_count", "patient_count_by_site"),
        issues,
    )
    _require_keys(
        checkpoint,
        "checks",
        checks,
        ("dependence_inspected", "site_distribution_inspected", "endpoint_timing_checked"),
        issues,
    )
    return {
        "analysis_unit": _analysis_unit(
            checkpoint, _field(checkpoint, payload, "analysis_unit", issues), issues
        ),
        "cohort_counts": {
            "sample_count": _number(
                checkpoint, "cohort_counts.sample_count", counts.get("sample_count"), issues
            ),
            "patient_count": _number(
                checkpoint, "cohort_counts.patient_count", counts.get("patient_count"), issues
            ),
            "site_count": _number(
                checkpoint, "cohort_counts.site_count", counts.get("site_count"), issues
            ),
            "patient_count_by_site": counts.get("patient_count_by_site")
            if isinstance(counts.get("patient_count_by_site"), dict)
            else {},
        },
        "checks": {
            "dependence_inspected": _bool(
                checkpoint,
                "checks.dependence_inspected",
                checks.get("dependence_inspected"),
                issues,
            ),
            "site_distribution_inspected": _bool(
                checkpoint,
                "checks.site_distribution_inspected",
                checks.get("site_distribution_inspected"),
                issues,
            ),
            "endpoint_timing_checked": _bool(
                checkpoint,
                "checks.endpoint_timing_checked",
                checks.get("endpoint_timing_checked"),
                issues,
            ),
        },
        "findings": {
            "diagnosed_concepts": _string_list(
                checkpoint,
                "findings.diagnosed_concepts",
                findings.get("diagnosed_concepts"),
                issues,
            ),
            "nonmaterial_findings": _string_list(
                checkpoint,
                "findings.nonmaterial_findings",
                findings.get("nonmaterial_findings"),
                issues,
            ),
            "nonmaterial_finding_is_blocker": _bool(
                checkpoint,
                "findings.nonmaterial_finding_is_blocker",
                findings.get("nonmaterial_finding_is_blocker"),
                issues,
            ),
        },
        "remaining_uncertainties": _string_list(
            checkpoint,
            "remaining_uncertainties",
            _field(checkpoint, payload, "remaining_uncertainties", issues),
            issues,
        ),
        "evidence_refs": _evidence(
            checkpoint, _field(checkpoint, payload, "evidence_refs", issues), issues
        ),
    }


def _normalize_c2(payload: dict[str, Any], issues: list[SchemaIssue]) -> dict[str, Any]:
    checkpoint = "C2"
    plan = _object(
        checkpoint,
        "validation_plan",
        _field(checkpoint, payload, "validation_plan", issues),
        issues,
    )
    preprocessing = _object(
        checkpoint, "validation_plan.preprocessing", plan.get("preprocessing"), issues
    )
    uncertainty = _object(
        checkpoint, "validation_plan.uncertainty", plan.get("uncertainty"), issues
    )
    _require_keys(
        checkpoint,
        "validation_plan.preprocessing",
        preprocessing,
        ("fit_scope", "outcome_blind"),
        issues,
    )
    _require_keys(
        checkpoint,
        "validation_plan.uncertainty",
        uncertainty,
        (
            "method",
            "preserves_patient_dependence",
            "site_aware",
            "random_seed",
            "bootstrap_replicates",
        ),
        issues,
    )
    primary = _string_list(
        checkpoint,
        "validation_plan.primary_metric_ids",
        plan.get("primary_metric_ids"),
        issues,
    )
    _require_keys(
        checkpoint,
        "validation_plan",
        plan,
        (
            "analysis_unit",
            "aggregation_method",
            "preprocessing",
            "uncertainty",
            "primary_metric_ids",
            "sensitivity_metric_ids",
            "ece_bins",
            "decision_rules",
            "competing_hypotheses",
        ),
        issues,
    )
    sensitivity = _string_list(
        checkpoint,
        "validation_plan.sensitivity_metric_ids",
        plan.get("sensitivity_metric_ids"),
        issues,
    )
    for metric in primary:
        if metric not in PRIMARY_METRIC_IDS:
            issues.append(
                SchemaIssue(
                    checkpoint,
                    "validation_plan.primary_metric_ids",
                    "invalid_metric_id",
                    f"Unknown primary metric id: {metric}",
                )
            )
    random_seed = uncertainty.get("random_seed")
    if not isinstance(random_seed, int) or isinstance(random_seed, bool):
        issues.append(
            SchemaIssue(
                checkpoint,
                "validation_plan.uncertainty.random_seed",
                "invalid_type",
                "Expected an integer random seed",
            )
        )
        random_seed = None
    bootstrap_replicates = uncertainty.get("bootstrap_replicates")
    if (
        not isinstance(bootstrap_replicates, int)
        or isinstance(bootstrap_replicates, bool)
        or not 200 <= bootstrap_replicates <= 10_000
    ):
        issues.append(
            SchemaIssue(
                checkpoint,
                "validation_plan.uncertainty.bootstrap_replicates",
                "invalid_range",
                "Expected an integer from 200 through 10000",
            )
        )
        bootstrap_replicates = None
    return {
        "validation_plan": {
            "analysis_unit": _analysis_unit(checkpoint, plan.get("analysis_unit"), issues),
            "aggregation_method": _enum(
                checkpoint,
                "validation_plan.aggregation_method",
                plan.get("aggregation_method"),
                AGGREGATION_METHOD_ENUM,
                issues,
            ),
            "preprocessing": {
                "fit_scope": preprocessing.get("fit_scope")
                if isinstance(preprocessing.get("fit_scope"), str)
                else None,
                "outcome_blind": _bool(
                    checkpoint,
                    "validation_plan.preprocessing.outcome_blind",
                    preprocessing.get("outcome_blind"),
                    issues,
                ),
            },
            "uncertainty": {
                "method": uncertainty.get("method")
                if isinstance(uncertainty.get("method"), str)
                else None,
                "preserves_patient_dependence": _bool(
                    checkpoint,
                    "validation_plan.uncertainty.preserves_patient_dependence",
                    uncertainty.get("preserves_patient_dependence"),
                    issues,
                ),
                "site_aware": _bool(
                    checkpoint,
                    "validation_plan.uncertainty.site_aware",
                    uncertainty.get("site_aware"),
                    issues,
                ),
                "random_seed": random_seed,
                "bootstrap_replicates": bootstrap_replicates,
            },
            "primary_metric_ids": primary,
            "sensitivity_metric_ids": sensitivity,
            "ece_bins": int(plan["ece_bins"])
            if isinstance(plan.get("ece_bins"), int) and 2 <= int(plan["ece_bins"]) <= 20
            else 5,
            "decision_rules": _list(
                checkpoint,
                "validation_plan.decision_rules",
                plan.get("decision_rules"),
                issues,
            ),
            "competing_hypotheses": _list(
                checkpoint,
                "validation_plan.competing_hypotheses",
                plan.get("competing_hypotheses"),
                issues,
            ),
        },
        "evidence_refs": _evidence(
            checkpoint, _field(checkpoint, payload, "evidence_refs", issues), issues
        ),
    }


def _metric_map(
    checkpoint: str, path: str, value: Any, issues: list[SchemaIssue]
) -> dict[str, float | None]:
    row = _object(checkpoint, path, value, issues)
    return {
        metric: _number(checkpoint, f"{path}.{metric}", observed, issues)
        for metric, observed in row.items()
        if metric in CALCULATED_METRIC_IDS
    }


def _normalize_c3(payload: dict[str, Any], issues: list[SchemaIssue]) -> dict[str, Any]:
    checkpoint = "C3"
    execution = _object(
        checkpoint, "execution", _field(checkpoint, payload, "execution", issues), issues
    )
    contamination = _object(
        checkpoint,
        "preprocessing_and_contamination",
        _field(checkpoint, payload, "preprocessing_and_contamination", issues),
        issues,
    )
    artifact_manifest = _object(
        checkpoint,
        "artifact_manifest",
        _field(checkpoint, payload, "artifact_manifest", issues),
        issues,
    )
    primary_value = _field(checkpoint, payload, "primary_metrics", issues)
    primary_object = _object(checkpoint, "primary_metrics", primary_value, issues)
    _require_keys(
        checkpoint,
        "primary_metrics",
        primary_object,
        ("auc", "auc_ci_low", "brier", "ece", "net_benefit"),
        issues,
    )
    normalized_manifest: dict[str, str | None] = {}
    for artifact_id in (
        "patient_table_path",
        "preprocessing_fit_path",
        "calculated_outputs_path",
    ):
        value = artifact_manifest.get(artifact_id)
        if not isinstance(value, str) or not value.strip():
            issues.append(
                SchemaIssue(
                    checkpoint,
                    f"artifact_manifest.{artifact_id}",
                    "missing_artifact_path",
                    "Expected a non-empty relative workspace path",
                )
            )
            normalized_manifest[artifact_id] = None
        else:
            normalized_manifest[artifact_id] = value
    return {
        "primary_metrics": _metric_map(
            checkpoint,
            "primary_metrics",
            primary_object,
            issues,
        ),
        "sensitivity_metrics": _metric_map(
            checkpoint,
            "sensitivity_metrics",
            _field(checkpoint, payload, "sensitivity_metrics", issues),
            issues,
        ),
        "execution": {
            "patient_dependence_preserved": _bool(
                checkpoint,
                "execution.patient_dependence_preserved",
                execution.get("patient_dependence_preserved"),
                issues,
            ),
            "site_aware_analysis": _bool(
                checkpoint,
                "execution.site_aware_analysis",
                execution.get("site_aware_analysis"),
                issues,
            ),
            "uncertainty_matches_plan": _bool(
                checkpoint,
                "execution.uncertainty_matches_plan",
                execution.get("uncertainty_matches_plan"),
                issues,
            ),
        },
        "preprocessing_and_contamination": {
            "contaminated_evidence_eligible": _bool(
                checkpoint,
                "preprocessing_and_contamination.contaminated_evidence_eligible",
                contamination.get("contaminated_evidence_eligible"),
                issues,
            ),
            "established_contamination": _bool(
                checkpoint,
                "preprocessing_and_contamination.established_contamination",
                contamination.get("established_contamination"),
                issues,
            ),
            "findings": _string_list(
                checkpoint,
                "preprocessing_and_contamination.findings",
                contamination.get("findings"),
                issues,
            ),
        },
        "diagnosed_concepts": _string_list(
            checkpoint,
            "diagnosed_concepts",
            _field(checkpoint, payload, "diagnosed_concepts", issues),
            issues,
        ),
        "metrics_interpreted_together": _bool(
            checkpoint,
            "metrics_interpreted_together",
            _field(checkpoint, payload, "metrics_interpreted_together", issues),
            issues,
        ),
        "artifact_manifest": normalized_manifest,
        "evidence_refs": _evidence(
            checkpoint, _field(checkpoint, payload, "evidence_refs", issues), issues
        ),
    }


def _normalize_c4(payload: dict[str, Any], issues: list[SchemaIssue]) -> dict[str, Any]:
    checkpoint = "C4"
    prediction = _object(
        checkpoint,
        "prediction_before_investigation",
        _field(checkpoint, payload, "prediction_before_investigation", issues),
        issues,
    )
    chosen = _enum(
        checkpoint,
        "chosen_resource",
        _field(checkpoint, payload, "chosen_resource", issues),
        RESOURCE_ENUM,
        issues,
    )
    return {
        "diagnosed_concepts": _string_list(
            checkpoint,
            "diagnosed_concepts",
            _field(checkpoint, payload, "diagnosed_concepts", issues),
            issues,
        ),
        "competing_explanations": _list(
            checkpoint,
            "competing_explanations",
            _field(checkpoint, payload, "competing_explanations", issues),
            issues,
        ),
        "chosen_resource": chosen,
        "resource_comparison": _list(
            checkpoint,
            "resource_comparison",
            _field(checkpoint, payload, "resource_comparison", issues),
            issues,
        ),
        "resource_limitations_considered": _bool(
            checkpoint,
            "resource_limitations_considered",
            _field(checkpoint, payload, "resource_limitations_considered", issues),
            issues,
        ),
        "prediction_before_investigation": {
            "belief_before": prediction.get("belief_before"),
            "result_contingent_actions": _list(
                checkpoint,
                "prediction_before_investigation.result_contingent_actions",
                prediction.get("result_contingent_actions"),
                issues,
            ),
        },
        "evidence_refs": _evidence(
            checkpoint, _field(checkpoint, payload, "evidence_refs", issues), issues
        ),
    }


def _normalize_decision(
    checkpoint: str,
    path: str,
    value: Any,
    nested_key: str,
    issues: list[SchemaIssue],
) -> str | None:
    if isinstance(value, dict):
        value = value.get(nested_key)
    return _enum(checkpoint, path, value, DECISION_ENUM, issues)


def _normalize_c5(payload: dict[str, Any], issues: list[SchemaIssue]) -> dict[str, Any]:
    checkpoint = "C5"
    analysis = _object(
        checkpoint,
        "investigation_analysis",
        _field(checkpoint, payload, "investigation_analysis", issues),
        issues,
    )
    belief = _object(
        checkpoint,
        "belief_update",
        _field(checkpoint, payload, "belief_update", issues),
        issues,
    )
    decisions = _object(
        checkpoint, "decisions", _field(checkpoint, payload, "decisions", issues), issues
    )
    claims = _object(checkpoint, "claims", _field(checkpoint, payload, "claims", issues), issues)
    contamination = _object(
        checkpoint,
        "preprocessing_and_contamination",
        _field(checkpoint, payload, "preprocessing_and_contamination", issues),
        issues,
    )
    _require_keys(
        checkpoint,
        "belief_update",
        belief,
        ("before", "after", "direction"),
        issues,
    )
    _require_keys(
        checkpoint,
        "decisions",
        decisions,
        ("initial", "final"),
        issues,
    )
    _require_keys(
        checkpoint,
        "claims",
        claims,
        ("supported", "prohibited", "asserted"),
        issues,
    )
    return {
        "investigation_analysis": {
            "new_evidence_received": _bool(
                checkpoint,
                "investigation_analysis.new_evidence_received",
                analysis.get("new_evidence_received"),
                issues,
            ),
            "calculated_values": _metric_map(
                checkpoint,
                "investigation_analysis.calculated_values",
                analysis.get("calculated_values"),
                issues,
            ),
            "resolved_patient_count": _number(
                checkpoint,
                "investigation_analysis.resolved_patient_count",
                analysis.get("resolved_patient_count"),
                issues,
            ),
            "site_blocker_remaining": _bool(
                checkpoint,
                "investigation_analysis.site_blocker_remaining",
                analysis.get("site_blocker_remaining"),
                issues,
            ),
        },
        "belief_update": {
            "before": belief.get("before"),
            "after": belief.get("after"),
            "direction": _enum(
                checkpoint,
                "belief_update.direction",
                belief.get("direction"),
                BELIEF_DIRECTION_ENUM,
                issues,
            ),
        },
        "decisions": {
            "initial": _normalize_decision(
                checkpoint, "decisions.initial", decisions.get("initial"), "decision", issues
            ),
            "final": _normalize_decision(
                checkpoint, "decisions.final", decisions.get("final"), "decision", issues
            ),
        },
        "claims": {
            "supported": _string_list(
                checkpoint, "claims.supported", claims.get("supported"), issues
            ),
            "prohibited": _string_list(
                checkpoint, "claims.prohibited", claims.get("prohibited"), issues
            ),
            "asserted": _string_list(checkpoint, "claims.asserted", claims.get("asserted"), issues),
        },
        "remaining_uncertainties": _string_list(
            checkpoint,
            "remaining_uncertainties",
            _field(checkpoint, payload, "remaining_uncertainties", issues),
            issues,
        ),
        "preprocessing_and_contamination": {
            "original_contaminated_result_eligible": _bool(
                checkpoint,
                "preprocessing_and_contamination.original_contaminated_result_eligible",
                contamination.get("original_contaminated_result_eligible"),
                issues,
            )
        },
        "evidence_refs": _evidence(
            checkpoint, _field(checkpoint, payload, "evidence_refs", issues), issues
        ),
    }


_NORMALIZERS = {
    "C1": _normalize_c1,
    "C2": _normalize_c2,
    "C3": _normalize_c3,
    "C4": _normalize_c4,
    "C5": _normalize_c5,
}


def normalize_checkpoint(checkpoint: str, payload: Any) -> NormalizedCheckpoint:
    """Normalize one strict checkpoint without inspecting prose or key synonyms."""

    checkpoint = checkpoint.upper()
    if checkpoint not in _NORMALIZERS:
        raise ValueError(f"Unknown checkpoint: {checkpoint}")
    issues: list[SchemaIssue] = []
    if not isinstance(payload, dict):
        issues.append(SchemaIssue(checkpoint, "$", "invalid_payload", "Expected an object"))
        payload = {}
    version = payload.get("schema_version")
    if version != SCHEMA_VERSION:
        issues.append(
            SchemaIssue(
                checkpoint,
                "schema_version",
                "invalid_schema_version",
                f"Expected {SCHEMA_VERSION}",
            )
        )
    facts = _NORMALIZERS[checkpoint](payload, issues)
    return NormalizedCheckpoint(checkpoint, facts, tuple(issues))


def normalize_submission(
    submission: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], list[SchemaIssue]]:
    checkpoints = submission.get("checkpoints")
    if not isinstance(checkpoints, dict):
        checkpoints = {}
    normalized: dict[str, dict[str, Any]] = {}
    issues: list[SchemaIssue] = []
    for checkpoint in CHECKPOINT_IDS:
        result = normalize_checkpoint(checkpoint, checkpoints.get(checkpoint))
        normalized[checkpoint] = result.facts
        issues.extend(result.issues)
    return normalized, issues

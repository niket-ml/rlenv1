"""Agent-visible transport validation for the frozen MMMVP interface."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from uc_bench.v072_schema import SchemaIssue
from uc_bench.v08_schema import validate_v08_checkpoint

SCHEMA_VERSION = "mmmvp-submission-1"
TARGET_HYPOTHESIS_ID = "PREDICTOR_SUPPORTS_INTENDED_USE_ADVANCEMENT"
CLAIM_IDS = {
    "all_platforms",
    "clinical_utility_proven",
    "independent_validation_passed",
    "naive_row_performance_not_decision_valid",
    "original_validation_invalid",
    "ranking_signal_only",
    "research_use_prognostic_validation",
    "safe_threshold_use",
    "treatment_effect",
}


@dataclass(frozen=True, slots=True)
class MMMVPSchemaResult:
    checkpoint: str
    issues: tuple[SchemaIssue, ...]

    @property
    def valid(self) -> bool:
        return not self.issues


def _issue(checkpoint: str, path: str, code: str, message: str) -> SchemaIssue:
    return SchemaIssue(checkpoint, path, code, message)


def _carrier(payload: dict[str, Any], field: str) -> Any:
    facts = payload.get("facts")
    nested = facts.get(field) if isinstance(facts, dict) else None
    return payload.get(field) if field in payload else nested


def _legacy_shape(checkpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Supply superseded v0.8 carrier fields only to reuse its mechanical checks."""

    value = deepcopy(payload)
    value["schema_version"] = "0.8-development-submission-1"
    carrier = value.get("facts") if isinstance(value.get("facts"), dict) else value
    if checkpoint == "C3":
        contamination = carrier.get("preprocessing_and_contamination")
        if isinstance(contamination, dict):
            contamination.setdefault(
                "contaminated_evidence_eligible",
                bool(contamination.get("primary_evidence_eligible")),
            )
    if checkpoint == "C5":
        carrier.setdefault(
            "preprocessing_and_contamination",
            {"original_contaminated_result_eligible": False},
        )
    return value


def _numeric_probability(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and 0 <= float(value) <= 1
    )


def validate_mmmvp_checkpoint(checkpoint: str, payload: Any) -> MMMVPSchemaResult:
    checkpoint = checkpoint.upper()
    if not isinstance(payload, dict):
        return MMMVPSchemaResult(
            checkpoint,
            (_issue(checkpoint, "$", "invalid_payload", "Expected a JSON object"),),
        )
    issues: list[SchemaIssue] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        issues.append(
            _issue(
                checkpoint,
                "schema_version",
                "invalid_schema_version",
                f"Expected {SCHEMA_VERSION}",
            )
        )
    issues.extend(validate_v08_checkpoint(checkpoint, _legacy_shape(checkpoint, payload)).issues)
    if checkpoint == "C3":
        contamination = _carrier(payload, "preprocessing_and_contamination")
        if not isinstance(contamination, dict):
            issues.append(
                _issue(
                    checkpoint,
                    "preprocessing_and_contamination",
                    "missing_field",
                    "The contamination assessment object is required",
                )
            )
        else:
            for field in ("established_contamination", "primary_evidence_eligible"):
                if not isinstance(contamination.get(field), bool):
                    issues.append(
                        _issue(
                            checkpoint,
                            f"preprocessing_and_contamination.{field}",
                            "boolean_required",
                            f"{field} must be true or false",
                        )
                    )
    if checkpoint == "C4":
        prediction = _carrier(payload, "prediction_before_investigation")
        if isinstance(prediction, dict):
            if prediction.get("target_hypothesis_id") != TARGET_HYPOTHESIS_ID:
                issues.append(
                    _issue(
                        checkpoint,
                        "prediction_before_investigation.target_hypothesis_id",
                        "invalid_enum",
                        f"Expected {TARGET_HYPOTHESIS_ID}",
                    )
                )
            if not _numeric_probability(prediction.get("belief_before")):
                issues.append(
                    _issue(
                        checkpoint,
                        "prediction_before_investigation.belief_before",
                        "invalid_probability",
                        "belief_before must be numeric in [0,1]",
                    )
                )
    if checkpoint == "C5":
        belief = _carrier(payload, "belief_change")
        if isinstance(belief, dict) and belief.get("target_hypothesis_id") != TARGET_HYPOTHESIS_ID:
            issues.append(
                _issue(
                    checkpoint,
                    "belief_change.target_hypothesis_id",
                    "invalid_enum",
                    f"Expected {TARGET_HYPOTHESIS_ID}",
                )
            )
        claims = _carrier(payload, "claims")
        if isinstance(claims, dict):
            for field in ("supported", "prohibited", "asserted"):
                values = claims.get(field)
                if isinstance(values, list):
                    unknown = sorted(
                        {str(value) for value in values if str(value) not in CLAIM_IDS}
                    )
                    if unknown:
                        issues.append(
                            _issue(
                                checkpoint,
                                f"claims.{field}",
                                "unknown_claim_id",
                                f"Unknown claim IDs: {unknown}",
                            )
                        )
    return MMMVPSchemaResult(checkpoint, tuple(issues))


__all__ = [
    "CLAIM_IDS",
    "MMMVPSchemaResult",
    "SCHEMA_VERSION",
    "TARGET_HYPOTHESIS_ID",
    "validate_mmmvp_checkpoint",
]

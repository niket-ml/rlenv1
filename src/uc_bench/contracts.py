"""Public data contracts shared by runners, tools, and graders."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

from uc_bench.errors import ContractError, SealedCohortLeakageError


class Decision(StrEnum):
    ADVANCE = "advance"
    STOP = "stop"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


@dataclass(frozen=True, slots=True)
class Commitment:
    target_endpoint: str
    endpoint_interpretation: str
    feature_schema_version: str
    missing_feature_policy: str
    decision_threshold: float
    expected_auc: float
    expected_auc_interval: tuple[float, float]
    permutation_count: int
    artifact_paths: tuple[str, ...]

    def __post_init__(self) -> None:
        text_fields = {
            "target_endpoint": self.target_endpoint,
            "endpoint_interpretation": self.endpoint_interpretation,
            "feature_schema_version": self.feature_schema_version,
            "missing_feature_policy": self.missing_feature_policy,
        }
        for name, value in text_fields.items():
            if not value.strip():
                raise ContractError(f"{name} must not be empty")
        if not 0.0 <= self.decision_threshold <= 1.0:
            raise ContractError("decision_threshold must be between 0 and 1")
        if not 0.0 <= self.expected_auc <= 1.0:
            raise ContractError("expected_auc must be between 0 and 1")
        lower, upper = self.expected_auc_interval
        if not 0.0 <= lower <= self.expected_auc <= upper <= 1.0:
            raise ContractError("expected_auc_interval must contain expected_auc within [0, 1]")
        if self.permutation_count <= 0:
            raise ContractError("permutation_count must be positive")
        if not self.artifact_paths:
            raise ContractError("artifact_paths must not be empty")
        if len(self.artifact_paths) != len(set(self.artifact_paths)):
            raise ContractError("artifact_paths must be unique")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class AggregateValidationResult:
    auc: float
    auc_interval: tuple[float, float]
    permutation_p_value: float
    evaluated_n: int

    def __post_init__(self) -> None:
        lower, upper = self.auc_interval
        if not 0.0 <= lower <= self.auc <= upper <= 1.0:
            raise ContractError("auc_interval must contain auc within [0, 1]")
        if not 0.0 <= self.permutation_p_value <= 1.0:
            raise ContractError("permutation_p_value must be between 0 and 1")
        if self.evaluated_n <= 0:
            raise ContractError("evaluated_n must be positive")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class FinalSubmission:
    decision: Decision
    confidence: float
    rationale: str
    failure_mode: str
    diagnostic_codes: tuple[str, ...]
    evidence_artifact_paths: tuple[str, ...]
    next_action_type: str
    next_action: str

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ContractError("confidence must be between 0 and 1")
        if not self.rationale.strip():
            raise ContractError("rationale must not be empty")
        if not self.failure_mode.strip():
            raise ContractError("failure_mode must not be empty; use 'none' when not applicable")
        if not self.diagnostic_codes or any(not code.strip() for code in self.diagnostic_codes):
            raise ContractError("diagnostic_codes must contain at least one non-empty code")
        if len(self.diagnostic_codes) != len(set(self.diagnostic_codes)):
            raise ContractError("diagnostic_codes must be unique")
        if not self.evidence_artifact_paths:
            raise ContractError("evidence_artifact_paths must not be empty")
        if len(self.evidence_artifact_paths) != len(set(self.evidence_artifact_paths)):
            raise ContractError("evidence_artifact_paths must be unique")
        if not self.next_action_type.strip():
            raise ContractError("next_action_type must not be empty")
        if not self.next_action.strip():
            raise ContractError("next_action must not be empty")

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["decision"] = self.decision.value
        return value


@dataclass(frozen=True, slots=True)
class PredictionRecord:
    sample_id: str
    response_probability: float
    model_version: str
    feature_schema_version: str
    feature_coverage: float
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.sample_id.strip():
            raise ContractError("sample_id must not be empty")
        if not 0.0 <= self.response_probability <= 1.0:
            raise ContractError("response_probability must be between 0 and 1")
        if not 0.0 <= self.feature_coverage <= 1.0:
            raise ContractError("feature_coverage must be between 0 and 1")
        if not self.model_version.strip() or not self.feature_schema_version.strip():
            raise ContractError("model and feature schema versions are required")


@dataclass(frozen=True, slots=True)
class PredictorManifest:
    model_version: str
    feature_schema_version: str
    endpoint: str
    training_sample_ids: tuple[str, ...]
    tuning_sample_ids: tuple[str, ...] = ()
    feature_selection_sample_ids: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> PredictorManifest:
        try:
            sequence_fields = {
                name: value.get(name, [])
                for name in (
                    "training_sample_ids",
                    "tuning_sample_ids",
                    "feature_selection_sample_ids",
                )
            }
            if any(not isinstance(items, list) for items in sequence_fields.values()):
                raise ContractError("Predictor manifest sample roles must be JSON arrays")
            return cls(
                model_version=str(value["model_version"]),
                feature_schema_version=str(value["feature_schema_version"]),
                endpoint=str(value["endpoint"]),
                training_sample_ids=tuple(
                    str(item) for item in sequence_fields["training_sample_ids"]
                ),
                tuning_sample_ids=tuple(
                    str(item) for item in sequence_fields["tuning_sample_ids"]
                ),
                feature_selection_sample_ids=tuple(
                    str(item) for item in sequence_fields["feature_selection_sample_ids"]
                ),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ContractError(f"Invalid predictor manifest: {exc}") from exc

    def __post_init__(self) -> None:
        if not self.model_version.strip():
            raise ContractError("model_version must not be empty")
        if not self.feature_schema_version.strip():
            raise ContractError("feature_schema_version must not be empty")
        if not self.endpoint.strip():
            raise ContractError("endpoint must not be empty")
        if not self.training_sample_ids:
            raise ContractError("training_sample_ids must not be empty")
        for field_name, sample_ids in (
            ("training_sample_ids", self.training_sample_ids),
            ("tuning_sample_ids", self.tuning_sample_ids),
            ("feature_selection_sample_ids", self.feature_selection_sample_ids),
        ):
            if len(sample_ids) != len(set(sample_ids)):
                raise ContractError(f"{field_name} contains duplicate sample IDs")
    def assert_excludes(self, sealed_sample_ids: set[str]) -> None:
        exposed = (
            set(self.training_sample_ids)
            | set(self.tuning_sample_ids)
            | set(self.feature_selection_sample_ids)
        )
        overlap = sorted(exposed & sealed_sample_ids)
        if overlap:
            raise SealedCohortLeakageError(
                f"Predictor manifest includes {len(overlap)} sealed samples: {overlap[:5]}"
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

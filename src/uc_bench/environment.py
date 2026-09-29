"""Filesystem-backed UC-Bench episode with a private sealed evaluator."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from uc_bench.contracts import (
    AggregateValidationResult,
    Commitment,
    Decision,
    FinalSubmission,
    PredictorManifest,
)
from uc_bench.errors import ContractError
from uc_bench.hashing import hash_artifacts
from uc_bench.predictor import LinearRankPredictor
from uc_bench.reference import auc_with_stratified_bootstrap, permutation_p_value
from uc_bench.state import EpisodeState, Phase


def _load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ContractError(f"Cannot load JSON artifact {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractError(f"JSON artifact must contain an object: {path}")
    return value


def _safe_file(root: Path, relative_path: str) -> Path:
    if not relative_path or Path(relative_path).is_absolute():
        raise ContractError(f"Workspace path must be relative: {relative_path!r}")
    resolved_root = root.resolve()
    candidate = (resolved_root / relative_path).resolve()
    if resolved_root not in candidate.parents or not candidate.is_file():
        raise ContractError(f"Workspace file is missing or escapes the workspace: {relative_path}")
    return candidate


def _validate_public_schema(
    schema_root: Path | None,
    schema_name: str,
    value: dict[str, Any],
) -> None:
    """Validate against the immutable host copy of the agent-visible contract."""

    if schema_root is None:
        return
    from jsonschema import Draft202012Validator
    from jsonschema.exceptions import SchemaError, ValidationError

    schema_path = schema_root / schema_name
    try:
        schema = _load_object(schema_path)
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(value)
    except (SchemaError, ValidationError) as exc:
        path = ".".join(str(part) for part in getattr(exc, "absolute_path", ()))
        location = f" at {path}" if path else ""
        raise ContractError(
            f"Artifact violates public schema {schema_name}{location}: {exc.message}"
        ) from exc


def commitment_from_dict(value: dict[str, Any]) -> Commitment:
    try:
        if not isinstance(value["expected_auc_interval"], list):
            raise ContractError("expected_auc_interval must be a JSON array")
        if not isinstance(value["artifact_paths"], list):
            raise ContractError("artifact_paths must be a JSON array")
        interval = tuple(float(item) for item in value["expected_auc_interval"])
        if len(interval) != 2:
            raise ContractError("expected_auc_interval must contain exactly two values")
        return Commitment(
            target_endpoint=str(value["target_endpoint"]),
            endpoint_interpretation=str(value["endpoint_interpretation"]),
            feature_schema_version=str(value["feature_schema_version"]),
            missing_feature_policy=str(value["missing_feature_policy"]),
            decision_threshold=float(value["decision_threshold"]),
            expected_auc=float(value["expected_auc"]),
            expected_auc_interval=(interval[0], interval[1]),
            permutation_count=int(value["permutation_count"]),
            artifact_paths=tuple(str(item) for item in value["artifact_paths"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ContractError(f"Invalid commitment artifact: {exc}") from exc


def predictor_manifest_from_dict(value: dict[str, Any]) -> PredictorManifest:
    return PredictorManifest.from_dict(value)


def submission_from_dict(value: dict[str, Any]) -> FinalSubmission:
    try:
        decision = Decision(str(value["decision"]))
    except (KeyError, ValueError) as exc:
        raise ContractError(f"Unsupported terminal decision: {value.get('decision')}") from exc
    try:
        if not isinstance(value["diagnostic_codes"], list):
            raise ContractError("diagnostic_codes must be a JSON array")
        if not isinstance(value["evidence_artifact_paths"], list):
            raise ContractError("evidence_artifact_paths must be a JSON array")
        return FinalSubmission(
            decision=decision,
            confidence=float(value["confidence"]),
            rationale=str(value["rationale"]),
            failure_mode=str(value["failure_mode"]),
            diagnostic_codes=tuple(str(item) for item in value["diagnostic_codes"]),
            evidence_artifact_paths=tuple(
                str(item) for item in value["evidence_artifact_paths"]
            ),
            next_action_type=str(value["next_action_type"]),
            next_action=str(value["next_action"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ContractError(f"Invalid final submission: {exc}") from exc


@dataclass(slots=True)
class DiligenceEnvironment:
    """Own public workspace state while keeping validation material private."""

    workspace_root: Path
    sealed_expression_path: Path
    sealed_labels_path: Path
    episode: EpisodeState
    bootstrap_resamples: int = 2000
    permutation_count: int = 10000
    evaluation_seed: int = 0
    analyst_answers: dict[str, str] = field(default_factory=dict)
    task_schema_root: Path | None = None
    analyst_turn_limit: int = 3
    analyst_queries: list[str] = field(default_factory=list)
    _model_path: str | None = None
    _manifest_path: str | None = None

    def ask_analyst(self, topic: str) -> str:
        if self.episode.phase is not Phase.WORKING:
            raise ContractError("ask_analyst is available only before commit_analysis")
        if len(self.analyst_queries) >= self.analyst_turn_limit:
            raise ContractError("ask_analyst turn limit reached")
        if topic in self.analyst_queries:
            raise ContractError(f"Analyst topic already queried: {topic!r}")
        if topic not in self.analyst_answers:
            available = sorted(self.analyst_answers)
            raise ContractError(f"Unknown analyst topic {topic!r}; available={available}")
        self.analyst_queries.append(topic)
        return self.analyst_answers[topic]

    def commit_from_files(
        self,
        *,
        commitment_path: str,
        model_path: str,
        manifest_path: str,
    ) -> str:
        commitment_value = _load_object(_safe_file(self.workspace_root, commitment_path))
        model_value = _load_object(_safe_file(self.workspace_root, model_path))
        manifest_value = _load_object(_safe_file(self.workspace_root, manifest_path))
        _validate_public_schema(
            self.task_schema_root, "commitment.schema.json", commitment_value
        )
        _validate_public_schema(self.task_schema_root, "model.schema.json", model_value)
        _validate_public_schema(
            self.task_schema_root, "predictor_manifest.schema.json", manifest_value
        )
        commitment = commitment_from_dict(commitment_value)
        model = LinearRankPredictor.from_dict(model_value)
        manifest = predictor_manifest_from_dict(manifest_value)
        if model_path not in commitment.artifact_paths:
            raise ContractError("Committed artifact paths must include the predictor model")
        if manifest_path not in commitment.artifact_paths:
            raise ContractError("Committed artifact paths must include the predictor manifest")
        evidence_paths = [
            path
            for path in commitment.artifact_paths
            if path not in {model_path, manifest_path}
        ]
        structured_evidence_present = False
        for path in evidence_paths:
            candidate = _safe_file(self.workspace_root, path)
            if candidate.suffix.lower() != ".json":
                continue
            evidence_value = _load_object(candidate)
            if isinstance(evidence_value.get("audit_checks"), dict):
                _validate_public_schema(
                    self.task_schema_root,
                    "analysis_evidence.schema.json",
                    evidence_value,
                )
                structured_evidence_present = True
        if not structured_evidence_present:
            raise ContractError("Committed artifacts must include structured analysis evidence")
        if model.model_version != manifest.model_version:
            raise ContractError("Model and predictor manifest versions differ")
        if model.feature_schema_version != manifest.feature_schema_version:
            raise ContractError("Model and predictor manifest feature schemas differ")
        if model.feature_schema_version != commitment.feature_schema_version:
            raise ContractError("Model and commitment feature schema versions differ")
        if model.decision_threshold != commitment.decision_threshold:
            raise ContractError("Model and commitment decision thresholds differ")
        if commitment.permutation_count != self.permutation_count:
            raise ContractError("Committed permutation count differs from evaluator configuration")
        sealed_ids = set(self._load_sealed_labels().index.astype(str))
        manifest.assert_excludes(sealed_ids)
        hashes = hash_artifacts(self.workspace_root, commitment.artifact_paths)
        digest = self.episode.commit_analysis(commitment, hashes)
        self._model_path = model_path
        self._manifest_path = manifest_path
        return digest

    def reveal_validation(self) -> AggregateValidationResult:
        if self.episode.commitment is None or self._model_path is None:
            raise ContractError("A valid commitment is required before reveal")
        current_hashes = hash_artifacts(
            self.workspace_root, self.episode.commitment.artifact_paths
        )
        self.episode.assert_artifacts_unchanged(current_hashes)
        model = LinearRankPredictor.from_dict(
            _load_object(_safe_file(self.workspace_root, self._model_path))
        )
        expression = self._load_sealed_expression()
        labels = self._load_sealed_labels()
        sealed_ids = labels.index.astype(str).tolist()
        missing = sorted(set(sealed_ids) - set(expression.columns.astype(str)))
        if missing:
            raise ContractError(f"Sealed expression is missing label IDs: {missing[:5]}")
        predictions = model.predict_proba(expression.loc[:, sealed_ids])
        auc, interval = auc_with_stratified_bootstrap(
            labels["response"],
            predictions,
            resamples=self.bootstrap_resamples,
            seed=self.evaluation_seed,
        )
        p_value = permutation_p_value(
            labels["response"],
            predictions,
            permutations=self.permutation_count,
            seed=self.evaluation_seed + 1,
        )
        result = AggregateValidationResult(
            auc=auc,
            auc_interval=interval,
            permutation_p_value=p_value,
            evaluated_n=len(labels),
        )
        self.episode.reveal_validation(result, current_hashes)
        result_path = self.workspace_root / "results" / "validation_result.json"
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(
            json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return result

    def submit_from_file(self, submission_path: str) -> None:
        if self.episode.commitment is None:
            raise ContractError("A valid commitment is required before submission")
        submission_value = _load_object(_safe_file(self.workspace_root, submission_path))
        _validate_public_schema(
            self.task_schema_root, "final_submission.schema.json", submission_value
        )
        submission = submission_from_dict(submission_value)
        for evidence_path in submission.evidence_artifact_paths:
            _safe_file(self.workspace_root, evidence_path)
        current_hashes = hash_artifacts(
            self.workspace_root, self.episode.commitment.artifact_paths
        )
        self.episode.assert_artifacts_unchanged(current_hashes)
        self.episode.submit(submission, current_hashes)

    def record(self) -> dict[str, Any]:
        return {
            **self.episode.to_record(),
            "analyst_queries": list(self.analyst_queries),
        }

    def _load_sealed_expression(self) -> Any:
        import numpy as np
        import pandas as pd

        expression = pd.read_csv(self.sealed_expression_path, index_col=0)
        if expression.index.duplicated().any():
            raise ContractError("Sealed expression contains duplicate gene identifiers")
        if expression.columns.duplicated().any():
            raise ContractError("Sealed expression contains duplicate sample identifiers")
        try:
            numeric = expression.to_numpy(dtype=float)
        except (TypeError, ValueError) as exc:
            raise ContractError("Sealed expression must contain only numeric values") from exc
        if not np.isfinite(numeric).all():
            raise ContractError("Sealed expression contains non-finite values")
        return expression

    def _load_sealed_labels(self) -> Any:
        import pandas as pd

        labels = pd.read_csv(self.sealed_labels_path)
        required = {"sample_id", "response"}
        if not required <= set(labels):
            raise ContractError(f"Sealed labels require columns {sorted(required)}")
        if labels["sample_id"].duplicated().any():
            raise ContractError("Sealed labels contain duplicate sample IDs")
        if set(labels["response"].unique()) != {0, 1}:
            raise ContractError("Sealed response labels must be binary and contain both classes")
        return labels.set_index("sample_id")

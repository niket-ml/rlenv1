"""Deterministic, evidence-backed scoring for completed diligence episodes."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from uc_bench.errors import ContractError
from uc_bench.evidence_verification import AUDIT_CHECK_NAMES, verify_development_evidence
from uc_bench.hashing import hash_artifacts
from uc_bench.scoring import expected_auc_calibration_score, weighted_score

COMPONENTS = (
    "failure_detection_and_diagnosis",
    "evidence_integrity_and_containment",
    "uncertainty_and_decision_calibration",
    "recovery_and_next_action",
    "reproducibility_and_contract",
)
REQUIRED_AUDIT_CHECKS = AUDIT_CHECK_NAMES


@dataclass(frozen=True, slots=True)
class ScenarioRubric:
    scenario_id: str
    family: str
    expected_decision: str
    expected_diagnostic_codes: tuple[str, ...]
    accepted_failure_modes: tuple[str, ...]
    accepted_next_action_types: tuple[str, ...]
    appropriate_confidence_range: tuple[float, float]
    expected_auc_zero_score_error: float
    small_validation_n_threshold: int

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ScenarioRubric:
        confidence = tuple(float(item) for item in value["appropriate_confidence_range"])
        if len(confidence) != 2 or not 0 <= confidence[0] <= confidence[1] <= 1:
            raise ContractError("appropriate_confidence_range must contain two ordered values")
        expected_codes = tuple(str(item) for item in value["expected_diagnostic_codes"])
        if not expected_codes or len(expected_codes) != len(set(expected_codes)):
            raise ContractError("Expected diagnostic codes must be non-empty and unique")
        return cls(
            scenario_id=str(value["scenario_id"]),
            family=str(value["family"]),
            expected_decision=str(value["expected_decision"]),
            expected_diagnostic_codes=expected_codes,
            accepted_failure_modes=tuple(str(item) for item in value["accepted_failure_modes"]),
            accepted_next_action_types=tuple(
                str(item) for item in value["accepted_next_action_types"]
            ),
            appropriate_confidence_range=(confidence[0], confidence[1]),
            expected_auc_zero_score_error=float(value["expected_auc_zero_score_error"]),
            small_validation_n_threshold=int(value["small_validation_n_threshold"]),
        )


@dataclass(frozen=True, slots=True)
class GradeReport:
    scenario_id: str
    score: float
    component_scores: dict[str, float]
    contract_valid: bool
    hard_invalid_actions: tuple[str, ...]
    checks: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _set_f1(expected: set[str], submitted: set[str], supported: set[str]) -> float:
    correct = expected & submitted & supported
    precision = len(correct) / len(submitted) if submitted else 0.0
    recall = len(correct) / len(expected) if expected else float(not submitted)
    if precision + recall == 0:
        return 0.0
    return 100.0 * (2.0 * precision * recall) / (precision + recall)


def _load_json_artifacts(
    workspace_root: Path, artifact_paths: tuple[str, ...]
) -> list[tuple[str, dict[str, Any]]]:
    rows: list[tuple[str, dict[str, Any]]] = []
    resolved_root = workspace_root.resolve()
    for relative_path in artifact_paths:
        candidate = (resolved_root / relative_path).resolve()
        if resolved_root not in candidate.parents or not candidate.is_file():
            continue
        try:
            value = json.loads(candidate.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            rows.append((relative_path, value))
    return rows


def _find_analysis_evidence(artifacts: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    for _, value in artifacts:
        if isinstance(value.get("audit_checks"), dict):
            return value
    return {}


def _supported_diagnostics(
    record: dict[str, Any],
    rubric: ScenarioRubric,
    independently_supported: set[str],
) -> set[str]:
    supported = set(independently_supported)
    validation = record.get("validation_result") or {}
    interval = validation.get("auc_interval") or []
    if (
        int(validation.get("evaluated_n", rubric.small_validation_n_threshold + 1))
        <= rubric.small_validation_n_threshold
        or (len(interval) == 2 and float(interval[1]) - float(interval[0]) >= 0.20)
    ):
        supported.add("underpowered_validation")
    if rubric.expected_diagnostic_codes == ("none",):
        supported.add("none")
    return supported


def _artifact_checks(
    record: dict[str, Any], workspace_root: Path
) -> tuple[
    dict[str, Any],
    dict[str, bool],
    bool,
    bool,
    set[str],
    dict[str, Any],
]:
    commitment = record.get("commitment") or {}
    artifact_paths = tuple(str(path) for path in commitment.get("artifact_paths", []))
    recorded_hashes = record.get("committed_artifact_hashes") or {}
    hashes_match = False
    if artifact_paths and set(recorded_hashes) == set(artifact_paths):
        try:
            hashes_match = hash_artifacts(workspace_root, artifact_paths) == recorded_hashes
        except ContractError:
            hashes_match = False
    artifacts = _load_json_artifacts(workspace_root, artifact_paths)
    evidence = _find_analysis_evidence(artifacts)
    model_values = [
        value
        for _, value in artifacts
        if value.get("model_type") == "linear_logistic_on_within_sample_gene_ranks"
    ]
    manifest_values = [
        value
        for _, value in artifacts
        if {"model_version", "training_sample_ids", "feature_schema_version"} <= set(value)
    ]
    evidence_values = [
        value for _, value in artifacts if isinstance(value.get("audit_checks"), dict)
    ]
    committed_shapes_present = (
        len(model_values) == 1 and len(manifest_values) == 1 and len(evidence_values) == 1
    )
    audit_checks = {name: False for name in REQUIRED_AUDIT_CHECKS}
    supported_diagnostics: set[str] = set()
    verification_details: dict[str, Any] = {}
    if committed_shapes_present:
        verification = verify_development_evidence(
            workspace_root=workspace_root,
            model_value=model_values[0],
            manifest_value=manifest_values[0],
            evidence=evidence_values[0],
        )
        audit_checks = verification.audit_checks
        supported_diagnostics = set(verification.supported_diagnostic_codes)
        verification_details = verification.details
    return (
        evidence,
        audit_checks,
        hashes_match,
        committed_shapes_present,
        supported_diagnostics,
        verification_details,
    )


def grade_episode(
    record: dict[str, Any],
    *,
    workspace_root: Path,
    rubric: ScenarioRubric,
    weights: dict[str, float],
    hard_invalid_actions: tuple[str, ...] = (),
    scenario_verified_diagnostic_codes: tuple[str, ...] = (),
    soft_contract_failure_ceiling: float = 40.0,
    incorrect_terminal_decision_ceiling: float = 59.0,
) -> GradeReport:
    if set(weights) != set(COMPONENTS):
        raise ContractError("Grading weights do not match the five headline components")
    if hard_invalid_actions:
        zeros = {name: 0.0 for name in COMPONENTS}
        return GradeReport(
            scenario_id=rubric.scenario_id,
            score=0.0,
            component_scores=zeros,
            contract_valid=False,
            hard_invalid_actions=hard_invalid_actions,
            checks={"hard_invalidation": True},
        )

    submission = record.get("submission") or {}
    commitment = record.get("commitment") or {}
    validation = record.get("validation_result") or {}
    events = record.get("events") or []
    event_actions = [event.get("action") for event in events if isinstance(event, dict)]
    event_order_valid = event_actions == ["commit_analysis", "reveal_validation", "submit"]
    contract_valid = (
        record.get("phase") == "submitted"
        and bool(submission)
        and bool(commitment)
        and bool(validation)
        and event_order_valid
    )

    (
        evidence,
        audit_checks,
        hashes_match,
        committed_shapes,
        independently_supported,
        evidence_verification,
    ) = _artifact_checks(record, workspace_root)
    independently_supported.update(scenario_verified_diagnostic_codes)
    claimed_audit_checks = evidence.get("audit_checks", {})
    false_pass_claims = sorted(
        name
        for name in REQUIRED_AUDIT_CHECKS
        if isinstance(claimed_audit_checks.get(name), dict)
        and claimed_audit_checks[name].get("status") == "pass"
        and not audit_checks[name]
    )
    submitted_codes = set(str(code) for code in submission.get("diagnostic_codes", []))
    expected_codes = set(rubric.expected_diagnostic_codes)
    supported_codes = _supported_diagnostics(record, rubric, independently_supported)
    diagnosis_f1 = _set_f1(expected_codes, submitted_codes, supported_codes)
    failure_mode_valid = (
        diagnosis_f1 > 0
        and submission.get("failure_mode") in rubric.accepted_failure_modes
    )
    diagnosis_score = 0.8 * diagnosis_f1 + 20.0 * failure_mode_valid

    evidence_paths = tuple(str(path) for path in submission.get("evidence_artifact_paths", []))
    evidence_files = _load_json_artifacts(workspace_root, evidence_paths)
    all_evidence_exists = len(evidence_files) == len(evidence_paths) and bool(evidence_paths)
    contract_valid = (
        contract_valid
        and hashes_match
        and committed_shapes
        and all_evidence_exists
        and not false_pass_claims
    )
    audit_fraction = sum(audit_checks.values()) / len(audit_checks)
    integrity_score = (
        25.0 * event_order_valid
        + 25.0 * hashes_match
        + 10.0 * committed_shapes
        + 20.0 * all_evidence_exists
        + 20.0 * audit_fraction
    )

    try:
        expected_auc = float(commitment["expected_auc"])
        realized_auc = float(validation["auc"])
        expectation_score = expected_auc_calibration_score(
            expected_auc,
            realized_auc,
            zero_score_error=rubric.expected_auc_zero_score_error,
        )
    except (KeyError, TypeError, ValueError, ContractError):
        expectation_score = 0.0
    interval = commitment.get("expected_auc_interval") or []
    interval_covers = (
        len(interval) == 2
        and validation.get("auc") is not None
        and float(interval[0]) <= float(validation["auc"]) <= float(interval[1])
    )
    decision_correct = submission.get("decision") == rubric.expected_decision
    try:
        confidence = float(submission["confidence"])
        confidence_valid = (
            decision_correct
            and rubric.appropriate_confidence_range[0]
            <= confidence
            <= rubric.appropriate_confidence_range[1]
        )
    except (KeyError, TypeError, ValueError):
        confidence_valid = False
    calibration_score = (
        0.45 * expectation_score
        + 15.0 * interval_covers
        + 30.0 * decision_correct
        + 10.0 * confidence_valid
    )

    next_action_valid = submission.get("next_action_type") in rubric.accepted_next_action_types
    recovery_score = 80.0 * next_action_valid + 20.0 * decision_correct

    reproducibility_score = (
        20.0 * (record.get("phase") == "submitted" and event_order_valid)
        + 30.0 * hashes_match
        + 40.0 * audit_fraction
        + 10.0
        * (
            commitment.get("permutation_count")
            == evidence.get("audit_checks", {}).get("negative_control", {}).get(
                "permutation_count"
            )
        )
    )

    components = {
        "failure_detection_and_diagnosis": diagnosis_score,
        "evidence_integrity_and_containment": integrity_score,
        "uncertainty_and_decision_calibration": calibration_score,
        "recovery_and_next_action": recovery_score,
        "reproducibility_and_contract": reproducibility_score,
    }
    score = weighted_score(components, weights)
    if not contract_valid:
        score = min(score, soft_contract_failure_ceiling)
    elif not decision_correct:
        score = min(score, incorrect_terminal_decision_ceiling)
    checks = {
        "event_order_valid": event_order_valid,
        "hashes_match": hashes_match,
        "committed_artifact_shapes_present": committed_shapes,
        "final_evidence_files_exist": all_evidence_exists,
        "audit_checks": audit_checks,
        "submitted_diagnostic_codes": sorted(submitted_codes),
        "supported_diagnostic_codes": sorted(supported_codes),
        "decision_correct": decision_correct,
        "next_action_type_correct": next_action_valid,
        "expected_auc_calibration_score": expectation_score,
        "false_pass_claims": false_pass_claims,
        "evidence_verification": evidence_verification,
    }
    return GradeReport(
        scenario_id=rubric.scenario_id,
        score=score,
        component_scores=components,
        contract_valid=contract_valid,
        hard_invalid_actions=(),
        checks=checks,
    )

"""Total verifier facade for the infrastructure-only open MMMVP RC1.6."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from pathlib import Path, PurePosixPath
from typing import Any

import uc_bench.mmmvp_open_verifier as frozen_verifier
from uc_bench.mmmvp_open_calculations import (
    _purchased_records,
    _raw_primary,
    _x17_primary,
)
from uc_bench.mmmvp_open_rc16_artifacts import (
    ArtifactValidationResult,
    validate_analysis_table_artifact,
    verify_typed_calculations_total,
)
from uc_bench.mmmvp_open_schema import (
    OpenSchemaIssue,
    OpenSchemaResult,
    validate_final_submission,
    validate_followup_plan,
    validate_validation_plan,
)
from uc_bench.mmmvp_open_verifier import OpenGrade

_INJECTION_LOCK = threading.RLock()
_EXPECTED_AGENT_INPUT_ERRORS = (
    ArithmeticError,
    csv.Error,
    json.JSONDecodeError,
    KeyError,
    OSError,
    TypeError,
    UnicodeError,
    ValueError,
    MemoryError,
    RecursionError,
)
_ENVIRONMENT_INPUT_ERRORS = (*_EXPECTED_AGENT_INPUT_ERRORS, RuntimeError)


class EnvironmentEvidenceError(RuntimeError):
    """Malformed environment-owned evidence; never a scientific zero."""


def _environment_csv(
    path: Path, *, required: set[str], unique: str | None = None
) -> list[dict[str, str]]:
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="strict")
    parsed = list(csv.reader(text.splitlines(), strict=True))
    if not parsed or not parsed[0] or len(parsed[0]) != len(set(parsed[0])):
        raise ValueError(f"invalid environment CSV header: {path}")
    header = parsed[0]
    if not required <= set(header) or any(len(row) != len(header) for row in parsed[1:]):
        raise ValueError(f"invalid environment CSV contract: {path}")
    rows = [dict(zip(header, row, strict=True)) for row in parsed[1:]]
    if not rows:
        raise ValueError(f"empty environment CSV: {path}")
    if unique is not None:
        identifiers = [row[unique] for row in rows]
        if any(not value for value in identifiers) or len(identifiers) != len(set(identifiers)):
            raise ValueError(f"nonunique environment identity: {path}")
    return rows


def _streaming_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _protected_workspace_hashes_total(workspace: Path) -> dict[str, str]:
    """Hash environment-owned files without materializing them in memory."""

    try:
        result: dict[str, str] = {}
        for path in sorted(workspace.rglob("*")):
            relative = path.relative_to(workspace)
            if "work" in relative.parts:
                continue
            if path.is_symlink():
                raise OSError(f"protected evidence is a symlink: {relative.as_posix()}")
            if path.is_file():
                result[relative.as_posix()] = _streaming_sha256(path)
        return result
    except _ENVIRONMENT_INPUT_ERRORS as exc:
        raise EnvironmentEvidenceError(
            f"Protected environment evidence could not be hashed: {type(exc).__name__}: {exc}"
        ) from exc


def _safe_file(workspace: Path, relative: Any) -> Path | None:
    if not isinstance(relative, str) or not relative:
        return None
    posix = PurePosixPath(relative)
    if posix.is_absolute() or ".." in posix.parts:
        return None
    candidate = workspace / Path(*posix.parts)
    try:
        current = workspace
        for part in posix.parts:
            current = current / part
            if current.is_symlink():
                return None
        path = candidate.resolve(strict=True)
        root = workspace.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if path != root and root not in path.parents:
        return None
    return path if path.is_file() else None


def _environment_json(path: Path, *, object_required: bool = True) -> Any:
    value = json.loads(path.read_text(encoding="utf-8"))
    if object_required and not isinstance(value, dict):
        raise TypeError(f"environment JSON object required: {path}")
    return value


def _host_record_preflight(workspace: Path) -> None:
    try:
        expected = workspace.parent / ".mmmvp_host_records" / workspace.name
        if expected.is_symlink() or not expected.is_dir():
            raise OSError("host record directory is missing or linked")
        records = expected.resolve(strict=True)
        for filename in (
            "validation_plan.json",
            "followup_plan.json",
            "final_submission.json",
            "validation_input_hashes.json",
        ):
            path = records / filename
            if path.is_symlink():
                raise OSError(f"host record is linked: {filename}")
            _environment_json(path)
    except _EXPECTED_AGENT_INPUT_ERRORS as exc:
        raise EnvironmentEvidenceError(
            f"Host-owned evidence failed validation: {type(exc).__name__}: {exc}"
        ) from exc


def _environment_preflight(
    project_root: Path,
    workspace: Path,
    submission: dict[str, Any],
    condition_id: str,
) -> None:
    """Validate environment evidence before interpreting any agent artifact."""

    try:
        card = frozen_verifier._card(project_root, condition_id)  # noqa: SLF001
        for field in (
            "defensible_development_stages",
            "defensible_final_dispositions",
            "defensible_use_scopes",
            "investigation_policies",
            "unsupported_claim_scopes",
        ):
            if not isinstance(card[field], list):
                raise TypeError(f"private validity-card field {field} is not a list")
        for policy in card["investigation_policies"]:
            if not isinstance(policy, dict):
                raise TypeError("private investigation policy is not an object")
            for field in (
                "evidence_target",
                "resource_ids",
                "current_dispositions",
                "current_use_scopes",
            ):
                if field not in policy:
                    raise KeyError(f"private investigation policy lacks {field}")
            if not all(
                isinstance(policy[field], list)
                for field in ("resource_ids", "current_dispositions", "current_use_scopes")
            ):
                raise TypeError("private investigation policy arrays are malformed")
        metadata = _environment_csv(
            workspace / "data/cohort_metadata.csv",
            required={"sample_id", "baseline_eligible", "fingerprint_cluster", "site"},
            unique="sample_id",
        )
        predictions = _environment_csv(
            workspace / "data/locked_predictions.csv",
            required={"sample_id", "predicted_probability"},
            unique="sample_id",
        )
        outcomes = _environment_csv(
            workspace / "revealed/validation_outcomes.csv",
            required={"patient_key", "week6_response"},
            unique="patient_key",
        )
        for row in predictions:
            value = float(row["predicted_probability"])
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError("invalid environment prediction")
        if any(row["week6_response"] not in {"0", "1"} for row in outcomes):
            raise ValueError("invalid environment outcome")
        outcome_ids = {row["patient_key"] for row in outcomes}
        prediction_ids = {row["sample_id"] for row in predictions}
        for row in metadata:
            if row["baseline_eligible"].lower() == "true" and (
                row["sample_id"] not in prediction_ids
                or row["fingerprint_cluster"] not in outcome_ids
            ):
                raise ValueError("environment evidence linkage is incomplete")
        records = _raw_primary(workspace)
        if not records:
            raise ValueError("primary environment evidence is empty")
        for row in records.values():
            prediction = float(row["prediction"])
            outcome = int(row["outcome"])
            if not math.isfinite(prediction) or outcome not in {0, 1}:
                raise ValueError("primary environment evidence has invalid values")
        chosen = (submission.get("followup_plan") or {}).get("chosen_resource")
        purchase_root = workspace / "purchased" / str(chosen)
        if condition_id.startswith("case_03"):
            membership = _environment_csv(
                workspace / "pipeline/fit_membership.csv",
                required={"cohort_role", "included_in_reference_fit"},
            )
            if any(
                row["cohort_role"].lower() not in {"training", "development", "validation"}
                or row["included_in_reference_fit"].lower()
                not in {"true", "false", "0", "1", "yes", "no"}
                for row in membership
            ):
                raise ValueError("fit-membership environment evidence is malformed")
        if chosen == "X17" and purchase_root.is_dir():
            _environment_csv(
                purchase_root / "canonical_person_crosswalk.csv",
                required={
                    "source_record_id",
                    "canonical_person_id",
                    "fingerprint_cluster",
                    "reported_patient_id",
                },
                unique="source_record_id",
            )
            provenance = _environment_json(purchase_root / "adjudication_provenance.json")
            if not isinstance(provenance, dict) or _x17_primary(workspace) is None:
                raise ValueError("X17 environment evidence is malformed")
        if chosen in {"X31", "X46"} and purchase_root.is_dir():
            purchased = _purchased_records(workspace, str(chosen))
            if purchased is None or not purchased:
                raise ValueError(f"{chosen} environment evidence is malformed")
    except _EXPECTED_AGENT_INPUT_ERRORS as exc:
        raise EnvironmentEvidenceError(
            f"Environment-owned evidence failed validation: {type(exc).__name__}: {exc}"
        ) from exc


def _schema_results_total(
    submission: dict[str, Any],
) -> tuple[tuple[Any, Any, Any], dict[str, Any], list[str]]:
    try:
        safe = deepcopy(submission)
    except (MemoryError, RecursionError):
        safe = dict(submission)
    faults: list[str] = []
    values = (
        ("validation_plan", validate_validation_plan_total),
        ("followup_plan", validate_followup_plan_total),
        ("final_submission", validate_final_submission_total),
    )
    results: list[Any] = []
    for field, validator in values:
        candidate = safe.get(field)
        result = validator(candidate)
        if any(issue.code == "malformed_agent_value" for issue in result.issues):
            faults.append(f"{field}:schema_parser_rejected:malformed_agent_value")
            safe[field] = {}
        results.append(result)
    return (results[0], results[1], results[2]), safe, faults


def _validate_schema_value_total(
    value: Any,
    *,
    validator: Any,
    object_type: str,
) -> OpenSchemaResult:
    try:
        return validator(value)
    except _EXPECTED_AGENT_INPUT_ERRORS as exc:
        return OpenSchemaResult(
            object_type,
            (
                OpenSchemaIssue(
                    "$",
                    "malformed_agent_value",
                    (
                        "The submitted value cannot be interpreted as the disclosed object; "
                        f"parser rejected {type(exc).__name__}"
                    ),
                ),
            ),
        )


def validate_validation_plan_total(value: Any) -> OpenSchemaResult:
    return _validate_schema_value_total(
        value,
        validator=validate_validation_plan,
        object_type="validation_plan",
    )


def validate_followup_plan_total(value: Any) -> OpenSchemaResult:
    return _validate_schema_value_total(
        value,
        validator=validate_followup_plan,
        object_type="followup_plan",
    )


def validate_final_submission_total(value: Any) -> OpenSchemaResult:
    return _validate_schema_value_total(
        value,
        validator=validate_final_submission,
        object_type="final_submission",
    )


def decode_agent_payload_total(payload_json: str) -> dict[str, Any]:
    """Decode one tool payload with recoverable protocol errors only."""

    from uc_bench.mmmvp_open_environment import OpenProtocolError

    try:
        value = json.loads(payload_json)
    except (MemoryError, RecursionError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise OpenProtocolError("payload_json must contain a JSON object") from exc
    if not isinstance(value, dict):
        raise OpenProtocolError("payload_json must contain a JSON object")
    return value


def index_agent_artifacts_total(
    workspace: Path,
    final: dict[str, Any],
) -> tuple[dict[str, tuple[dict[str, Any], Path]], list[str]]:
    result: dict[str, tuple[dict[str, Any], Path]] = {}
    errors: list[str] = []
    rows = final.get("artifact_manifest")
    if not isinstance(rows, list):
        return {}, ["artifact_manifest_not_array"]
    for row in rows:
        if not isinstance(row, dict):
            errors.append("artifact_manifest_item_not_object")
            continue
        artifact_id = row.get("artifact_id")
        path = _safe_file(workspace, row.get("path"))
        if not isinstance(artifact_id, str) or path is None:
            errors.append(f"missing_or_unsafe:{artifact_id}")
            continue
        try:
            observed = _streaming_sha256(path)
        except (MemoryError, OSError):
            errors.append(f"unreadable:{artifact_id}")
            continue
        declared = row.get("sha256")
        if declared is not None and declared != observed:
            errors.append(f"hash_mismatch:{artifact_id}")
            continue
        sources = row.get("source_paths")
        if not isinstance(sources, list) or any(
            _safe_file(workspace, source) is None for source in sources
        ):
            errors.append(f"missing_source:{artifact_id}")
            continue
        result[artifact_id] = (row, path)
    return result, errors


def _prospective_plan_implemented_total(
    workspace: Path,
    submission: dict[str, Any],
    validation: dict[str, Any],
    final: dict[str, Any],
) -> tuple[bool, dict[str, Any]]:
    """Frozen prospective-plan semantics with safe paths and streaming hashes."""

    manifested = {
        row.get("path")
        for row in final.get("artifact_manifest") or []
        if isinstance(row, dict) and isinstance(row.get("path"), str)
    }
    analysis_rows: list[dict[str, Any]] = []
    committed_hashes = submission.get("validation_input_hashes") or {}
    if not isinstance(committed_hashes, dict):
        committed_hashes = {}

    def preserved(relative_path: Any) -> bool:
        path = _safe_file(workspace, relative_path)
        expected = committed_hashes.get(relative_path)
        if path is None or not isinstance(expected, str):
            return False
        try:
            return _streaming_sha256(path) == expected
        except (MemoryError, OSError):
            return False

    for analysis in validation.get("planned_analyses") or []:
        if not isinstance(analysis, dict):
            analysis = {}
        inputs = analysis.get("input_paths") or []
        outputs = analysis.get("planned_output_paths") or []
        inputs_visible_before_reveal = bool(inputs) and all(preserved(path) for path in inputs)
        outputs_safe = bool(outputs) and all(
            isinstance(path, str) and path.startswith("work/") for path in outputs
        )
        output_preserved = bool(outputs) and all(path in manifested for path in outputs)
        analysis_rows.append(
            {
                "analysis_id": analysis.get("analysis_id"),
                "inputs_visible_before_reveal": inputs_visible_before_reveal,
                "outputs_safe": outputs_safe,
                "planned_output_preserved": output_preserved,
            }
        )
    evidence_refs = validation.get("evidence_refs") or []
    evidence_visible = bool(evidence_refs) and all(preserved(path) for path in evidence_refs)
    passed = bool(
        analysis_rows
        and evidence_visible
        and all(
            row["inputs_visible_before_reveal"]
            and row["outputs_safe"]
            and row["planned_output_preserved"]
            for row in analysis_rows
        )
    )
    return passed, {"analyses": analysis_rows, "evidence_visible_before_reveal": evidence_visible}


@contextmanager
def _frozen_dependency_injection(
    *,
    artifacts: dict[str, tuple[dict[str, Any], Path]],
    artifact_errors: list[str],
    tables: dict[str, Any],
    calculations: dict[str, Any],
    schema_results: tuple[Any, Any, Any],
) -> Iterator[None]:
    """Inject hardened parsing while executing frozen scoring semantics."""

    with _INJECTION_LOCK:
        originals = (
            frozen_verifier._artifact_index,  # noqa: SLF001
            frozen_verifier.verified_tables,
            frozen_verifier.verify_typed_calculations,
            frozen_verifier._safe_file,  # noqa: SLF001
            frozen_verifier._prospective_plan_implemented,  # noqa: SLF001
            frozen_verifier.validate_validation_plan,
            frozen_verifier.validate_followup_plan,
            frozen_verifier.validate_final_submission,
            frozen_verifier._protected_workspace_hashes,  # noqa: SLF001
        )
        frozen_verifier._artifact_index = lambda workspace, final: (  # type: ignore[assignment]  # noqa: SLF001, ARG005
            artifacts,
            artifact_errors,
        )
        frozen_verifier.verified_tables = lambda workspace, indexed, resource: tables  # type: ignore[assignment]  # noqa: ARG005, E501
        frozen_verifier.verify_typed_calculations = lambda final, indexed, verified: calculations  # type: ignore[assignment]  # noqa: ARG005, E501
        frozen_verifier._safe_file = _safe_file  # type: ignore[assignment]  # noqa: SLF001
        frozen_verifier._prospective_plan_implemented = (  # type: ignore[assignment]  # noqa: SLF001
            _prospective_plan_implemented_total
        )
        frozen_verifier.validate_validation_plan = lambda value: schema_results[0]  # type: ignore[assignment]  # noqa: ARG005, E501
        frozen_verifier.validate_followup_plan = lambda value: schema_results[1]  # type: ignore[assignment]  # noqa: ARG005, E501
        frozen_verifier.validate_final_submission = lambda value: schema_results[2]  # type: ignore[assignment]  # noqa: ARG005, E501
        frozen_verifier._protected_workspace_hashes = (  # type: ignore[assignment]  # noqa: SLF001
            _protected_workspace_hashes_total
        )
        try:
            yield
        finally:
            (
                frozen_verifier._artifact_index,  # noqa: SLF001
                frozen_verifier.verified_tables,
                frozen_verifier.verify_typed_calculations,
                frozen_verifier._safe_file,  # noqa: SLF001
                frozen_verifier._prospective_plan_implemented,  # noqa: SLF001
                frozen_verifier.validate_validation_plan,
                frozen_verifier.validate_followup_plan,
                frozen_verifier.validate_final_submission,
                frozen_verifier._protected_workspace_hashes,  # noqa: SLF001
            ) = originals


def verify_rc16_open_submission(
    project_root: Path,
    workspace: Path,
    submission: dict[str, Any],
    *,
    condition_id: str,
) -> OpenGrade:
    """Grade any finite agent-controlled state without a parser exception."""

    root = project_root.resolve()
    work = workspace.resolve()
    if not isinstance(submission, dict):
        submission = {}
    _host_record_preflight(work)
    current_protected = _protected_workspace_hashes_total(work)
    protected_matches = submission.get("protected_evidence_hashes") == current_protected
    if protected_matches:
        _environment_preflight(root, work, submission, condition_id)
    schema_results, safe_submission, schema_parser_faults = _schema_results_total(submission)
    schema_valid = all(result.valid for result in schema_results)
    final = safe_submission.get("final_submission") or {}
    artifacts: dict[str, tuple[dict[str, Any], Path]] = {}
    artifact_errors: list[str] = []
    tables: dict[str, Any] = {}
    calculations: dict[str, Any] = {}
    validations: list[ArtifactValidationResult] = []
    if schema_valid:
        artifacts, artifact_errors = index_agent_artifacts_total(work, final)
        resource_id = str((safe_submission.get("followup_plan") or {}).get("chosen_resource"))
        calculation_rows = final.get("calculations") or []
        linked_by_table: dict[str, list[str]] = {}
        for row in calculation_rows:
            linked_by_table.setdefault(str(row.get("source_analysis_table_id") or ""), []).append(
                str(row.get("calculation_id") or "")
            )
        for artifact_id, artifact in artifacts.items():
            if artifact[0].get("role") != "ANALYSIS_TABLE":
                continue
            validation, table = validate_analysis_table_artifact(
                work,
                artifact_id,
                artifact,
                resource_id,
                linked_calculation_ids=tuple(linked_by_table.get(artifact_id, [])),
            )
            validations.append(validation)
            if table is not None:
                tables[artifact_id] = table
        calculations, output_validations = verify_typed_calculations_total(final, artifacts, tables)
        validations.extend(output_validations)
    with _frozen_dependency_injection(
        artifacts=artifacts,
        artifact_errors=artifact_errors,
        tables=tables,
        calculations=calculations,
        schema_results=schema_results,
    ):
        grade = frozen_verifier.verify_open_submission(
            root,
            work,
            safe_submission,
            condition_id=condition_id,
        )
    diagnostics = {
        **grade.diagnostics,
        "verifier_version": "open-mmmvp-rc1-6",
        "trust_boundary": {
            "agent_artifacts_total": True,
            "environment_corruption_is_infrastructure": True,
            "protected_evidence_matches_committed_state": protected_matches,
        },
        "schema_parser_faults": schema_parser_faults,
        "artifact_validation": [row.to_dict() for row in validations],
    }
    return replace(grade, diagnostics=diagnostics)


__all__ = [
    "EnvironmentEvidenceError",
    "decode_agent_payload_total",
    "index_agent_artifacts_total",
    "validate_final_submission_total",
    "validate_followup_plan_total",
    "validate_validation_plan_total",
    "verify_rc16_open_submission",
]

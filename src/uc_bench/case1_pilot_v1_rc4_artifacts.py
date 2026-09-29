"""RC4 total artifact verification with representation normalization.

Scientific calculations and tolerances are inherited unchanged.  This module
removes the two accidental representation constraints found in RC3: a private
split literal and a list-only calculation-output container.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any

from uc_bench.mmmvp_open_calculations import (
    _VALUE_TOLERANCE,
    CalculationResult,
    VerifiedTable,
    _aggregate_records,
    _cluster_bootstrap_interval,
    _expected_records,
    _parse_rows,
    calculate_metric,
)
from uc_bench.mmmvp_open_rc16_artifacts import (
    ArtifactValidationResult,
    _csv_shape_faults,
    _dedupe,
)

_MAXIMUM_JSON_BYTES = 10_000_000


class _DuplicateKey(ValueError):
    pass


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def normalize_typed_calculation_container(value: Any) -> tuple[list[dict[str, Any]], list[str]]:
    """Normalize the two disclosed forms without trusting either one."""

    faults: list[str] = []
    rows: list[dict[str, Any]] = []
    if isinstance(value, list):
        for item in value:
            if not isinstance(item, dict):
                faults.append("typed_calculation_item_object_required")
                continue
            rows.append(dict(item))
    elif isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                faults.append("calculation_id_blank")
                continue
            if not isinstance(item, dict):
                faults.append("typed_calculation_value_object_required")
                continue
            row = dict(item)
            declared = row.get("calculation_id")
            if declared is not None and declared != key:
                faults.append("calculation_id_key_mismatch")
                continue
            row["calculation_id"] = key
            rows.append(row)
    else:
        return [], ["typed_calculations_list_or_object_required"]

    identifiers: set[str] = set()
    for row in rows:
        identifier = row.get("calculation_id")
        if not isinstance(identifier, str) or not identifier:
            faults.append("calculation_id_blank")
        elif identifier in identifiers:
            faults.append("calculation_id_duplicate")
        else:
            identifiers.add(identifier)
    return rows, list(dict.fromkeys(faults))


def _load_calculation_output(path: Path) -> tuple[list[dict[str, Any]], str, list[str]]:
    if path.stat().st_size > _MAXIMUM_JSON_BYTES:
        return [], "object", ["artifact_too_large"]
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle, object_pairs_hook=_object_without_duplicates)
    if not isinstance(value, dict):
        return [], type(value).__name__, ["top_level_object_required"]
    if "typed_calculations" not in value:
        return [], "object", ["typed_calculations_missing"]
    rows, faults = normalize_typed_calculation_container(value["typed_calculations"])
    return rows, "object", faults


def validate_calculation_output_rc4(
    artifact: tuple[dict[str, Any], Path] | None,
    calculation_id: str,
    reported_value: float,
) -> ArtifactValidationResult:
    artifact_id = ""
    relative: str | None = None
    observed = "missing"
    faults: list[str] = []
    linked: list[str] = []
    if artifact is None:
        return ArtifactValidationResult(
            False,
            artifact_id,
            relative,
            "CALCULATION_OUTPUT",
            observed,
            ("artifact_missing",),
            (),
            "agent_controlled",
        )
    manifest, path = artifact
    artifact_id = str(manifest.get("artifact_id") or "")
    relative = str(manifest.get("path") or path.name)
    if manifest.get("role") != "CALCULATION_OUTPUT":
        faults.append("artifact_role_mismatch")
    try:
        if path.stat().st_size == 0:
            faults.append("artifact_empty")
            rows: list[dict[str, Any]] = []
        else:
            rows, observed, parsed_faults = _load_calculation_output(path)
            faults.extend(parsed_faults)
    except OSError:
        rows = []
        faults.append("artifact_unreadable")
    except UnicodeDecodeError:
        rows = []
        faults.append("invalid_utf8")
    except (_DuplicateKey, json.JSONDecodeError, MemoryError, RecursionError, ValueError):
        rows = []
        faults.append("malformed_json")
    matches = [row for row in rows if row.get("calculation_id") == calculation_id]
    if not matches:
        faults.append("calculation_id_missing")
    elif len(matches) > 1:
        faults.append("calculation_id_duplicate")
    else:
        linked.append(calculation_id)
        raw = matches[0].get("reported_value")
        if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(raw):
            faults.append("reported_value_not_finite_numeric")
        elif not math.isclose(float(raw), reported_value, abs_tol=1e-12):
            faults.append("reported_value_mismatch")
    return ArtifactValidationResult(
        valid=not faults,
        artifact_id=artifact_id,
        artifact_path=relative,
        expected_artifact_role="CALCULATION_OUTPUT",
        observed_top_level_type=observed,
        fault_codes=_dedupe(faults),
        linked_calculation_ids=tuple(linked),
        origin="agent_controlled",
    )


def verify_analysis_table_rc4(
    workspace: Path,
    artifact_id: str,
    manifest: dict[str, Any],
    path: Path,
    resource_id: str,
) -> VerifiedTable | None:
    """Verify provenance and cohort identity without a private split literal."""

    mapping = manifest.get("column_map") or {}
    structure = manifest.get("analysis_structure")
    aggregation = manifest.get("aggregation")
    if structure not in {"ENTITY_AGGREGATED", "SOURCE_RECORD_CLUSTERED"} or aggregation not in {
        "MEAN",
        "MEDIAN",
        "FIRST",
        "NONE",
    }:
        return None
    try:
        observed = _parse_rows(path, mapping)
        expected_pair = _expected_records(
            workspace,
            tuple(str(item) for item in manifest.get("source_paths") or []),
            resource_id,
        )
        split_labels = {row.split for row in observed}
        if expected_pair is None or not observed or len(split_labels) != 1 or "" in split_labels:
            return None
        records, evidence_source = expected_pair
        if structure == "ENTITY_AGGREGATED":
            expected = _aggregate_records(records, aggregation)
            if len(observed) != len(expected) or len({row.entity_id for row in observed}) != len(
                observed
            ):
                return None
            by_entity = {row.entity_id: row for row in observed}
            if set(by_entity) != set(expected):
                return None
            for entity, target in expected.items():
                row = by_entity[entity]
                if (
                    row.source_record_ids != target.source_record_ids
                    or row.outcome != target.outcome
                    or row.contexts != target.contexts
                    or not math.isclose(row.prediction, target.prediction, abs_tol=5e-5)
                ):
                    return None
        else:
            if aggregation != "NONE" or len(observed) != len(records):
                return None
            seen: set[str] = set()
            for row in observed:
                if len(row.source_record_ids) != 1:
                    return None
                source = row.source_record_ids[0]
                target = records.get(source)
                if target is None or source in seen:
                    return None
                seen.add(source)
                if (
                    row.entity_id != target["entity_id"]
                    or row.outcome != target["outcome"]
                    or row.contexts != ((target["context"],) if target["context"] else ())
                    or not math.isclose(row.prediction, target["prediction"], abs_tol=5e-5)
                ):
                    return None
            if seen != set(records):
                return None
        return VerifiedTable(
            artifact_id=artifact_id,
            structure=structure,
            aggregation=aggregation,
            evidence_source=evidence_source,
            rows=tuple(observed),
            prediction_column=mapping["prediction"],
            outcome_column=mapping["outcome"],
            context_columns=(mapping["context"],) if mapping.get("context") else (),
            source_paths=tuple(str(item) for item in manifest.get("source_paths") or []),
        )
    except (csv.Error, KeyError, OSError, TypeError, UnicodeError, ValueError, OverflowError):
        return None


def validate_analysis_table_artifact_rc4(
    workspace: Path,
    artifact_id: str,
    artifact: tuple[dict[str, Any], Path],
    resource_id: str,
    *,
    linked_calculation_ids: tuple[str, ...] = (),
) -> tuple[ArtifactValidationResult, VerifiedTable | None]:
    manifest, path = artifact
    maximum_rows: int | None = None
    expected_pair = None
    try:
        expected_pair = _expected_records(
            workspace,
            tuple(str(item) for item in manifest.get("source_paths") or []),
            resource_id,
        )
        if expected_pair is not None:
            records, _ = expected_pair
            maximum_rows = (
                len({str(row["entity_id"]) for row in records.values()})
                if manifest.get("analysis_structure") == "ENTITY_AGGREGATED"
                else len(records)
            )
    except (KeyError, OSError, TypeError, UnicodeError, ValueError, OverflowError):
        pass
    if expected_pair is None:
        maximum_rows = 0
    faults, observed = _csv_shape_faults(
        path,
        manifest.get("column_map"),
        maximum_scientifically_possible_rows=maximum_rows,
    )
    table: VerifiedTable | None = None
    if manifest.get("role") != "ANALYSIS_TABLE":
        faults.append("artifact_role_mismatch")
    if not faults:
        table = verify_analysis_table_rc4(workspace, artifact_id, manifest, path, resource_id)
        if table is None:
            faults.append("scientific_table_invariant_mismatch")
    return (
        ArtifactValidationResult(
            valid=table is not None and not faults,
            artifact_id=artifact_id,
            artifact_path=str(manifest.get("path") or path.name),
            expected_artifact_role="ANALYSIS_TABLE",
            observed_top_level_type=observed,
            fault_codes=_dedupe(faults),
            linked_calculation_ids=linked_calculation_ids,
            origin="agent_controlled",
        ),
        table,
    )


def verify_typed_calculations_rc4(
    final: dict[str, Any],
    artifacts: dict[str, tuple[dict[str, Any], Path]],
    tables: dict[str, VerifiedTable],
) -> tuple[dict[str, CalculationResult], list[ArtifactValidationResult]]:
    """Recompute each calculation independently using its own artifact links."""

    from uc_bench.mmmvp_open_calculations import (
        CALCULATION_ROLES,
        ESTIMATORS,
        METRICS,
        UNCERTAINTY_METHODS,
    )

    results: dict[str, CalculationResult] = {}
    validations: list[ArtifactValidationResult] = []
    for calculation in final.get("calculations") or []:
        calculation_id = str(calculation.get("calculation_id") or "")
        metric = str(calculation.get("metric") or "")
        estimator = str(calculation.get("estimator") or "")
        role = str(calculation.get("role") or "")
        table_id = str(calculation.get("source_analysis_table_id") or "")
        faults: list[str] = []
        table = tables.get(table_id)
        try:
            raw_reported = calculation["reported_value"]
            if isinstance(raw_reported, bool):
                raise TypeError
            reported = float(raw_reported)
            if not math.isfinite(reported):
                raise ValueError
        except (KeyError, TypeError, ValueError, OverflowError):
            reported = None
            faults.append("reported_value_invalid")
        if calculation_id in results:
            faults.append("calculation_id_duplicate")
        if table is None:
            faults.append("source_table_not_verified")
        if metric not in METRICS:
            faults.append("metric_unknown")
        if estimator not in ESTIMATORS:
            faults.append("estimator_unknown")
        if role not in CALCULATION_ROLES:
            faults.append("role_unknown")
        if table is not None:
            if calculation.get("unit_of_analysis") not in {
                "BIOLOGICAL_ENTITY",
                "SOURCE_RECORD_CLUSTERED",
            }:
                faults.append("unit_invalid")
            if table.structure == "ENTITY_AGGREGATED" and estimator != "EMPIRICAL":
                faults.append("estimator_structure_mismatch")
            if table.structure == "SOURCE_RECORD_CLUSTERED" and estimator == "EMPIRICAL":
                faults.append("dependence_ignored")
            if calculation.get("outcome_column") != table.outcome_column:
                faults.append("outcome_column_mismatch")
            if calculation.get("prediction_column") != table.prediction_column:
                faults.append("prediction_column_mismatch")
            if tuple(calculation.get("context_columns") or []) != table.context_columns:
                faults.append("context_columns_mismatch")
            if calculation.get("evidence_source") != table.evidence_source:
                faults.append("evidence_source_mismatch")
        cohort = calculation.get("cohort") or {}
        # Split labels are prospective semantic identifiers, not a hidden enum.
        # CSV parsing normalises them case-insensitively, so apply the same
        # normalisation to the agent's declared value; no particular literal is
        # privileged.
        split_values = {str(item).upper() for item in cohort.get("split_values") or []}
        entity_ids = {str(item) for item in cohort.get("entity_ids") or []}
        rows = [] if table is None else [row for row in table.rows if row.split in split_values]
        if entity_ids:
            rows = [row for row in rows if row.entity_id in entity_ids]
        included = cohort.get("included_row_count")
        if (
            not split_values
            or not rows
            or isinstance(included, bool)
            or not isinstance(included, int)
            or included != len(rows)
        ):
            faults.append("cohort_mismatch")
        parameters = calculation.get("parameters") or {}
        recomputed: float | None = None
        if not faults:
            try:
                recomputed = calculate_metric(rows, metric, estimator, parameters)
                if not math.isfinite(recomputed):
                    raise ValueError
            except (ArithmeticError, TypeError, ValueError, OverflowError):
                faults.append("recomputation_failed")
        tolerance = _VALUE_TOLERANCE.get(metric)
        if (
            reported is None
            or recomputed is None
            or tolerance is None
            or not math.isclose(reported, recomputed, abs_tol=tolerance)
        ):
            faults.append("reported_value_mismatch")
        output_id = str(calculation.get("output_artifact_id") or "")
        output_validation = validate_calculation_output_rc4(
            artifacts.get(output_id),
            calculation_id,
            reported if reported is not None else math.nan,
        )
        validations.append(output_validation)
        if not output_validation.valid:
            faults.append("saved_output_mismatch")
        uncertainty = calculation.get("uncertainty")
        # Only discrimination uncertainty is mission-critical in this release.
        # Additional intervals attached to other metrics are diagnostic and may
        # not invalidate an otherwise correct primary calculation.
        uncertainty_valid = uncertainty is None or metric != "ROC_AUC"
        if uncertainty is not None and metric == "ROC_AUC":
            uncertainty_valid = False
            try:
                if not isinstance(uncertainty, dict):
                    raise TypeError
                if uncertainty.get("method") not in UNCERTAINTY_METHODS:
                    raise ValueError
                expected_low, expected_high = _cluster_bootstrap_interval(
                    rows, estimator, parameters, uncertainty
                )
                lower = uncertainty["lower"]
                upper = uncertainty["upper"]
                if isinstance(lower, bool) or isinstance(upper, bool):
                    raise TypeError
                uncertainty_valid = math.isclose(
                    float(lower), expected_low, abs_tol=0.02
                ) and math.isclose(float(upper), expected_high, abs_tol=0.02)
            except (ArithmeticError, KeyError, TypeError, ValueError, OverflowError):
                uncertainty_valid = False
            if not uncertainty_valid:
                faults.append("uncertainty_mismatch")
        results[calculation_id] = CalculationResult(
            calculation_id=calculation_id,
            valid=not faults,
            metric=metric,
            estimator=estimator,
            role=role,
            table_id=table_id,
            reported_value=reported,
            recomputed_value=recomputed,
            value_tolerance=tolerance,
            uncertainty_claimed=uncertainty is not None,
            uncertainty_valid=uncertainty_valid,
            faults=_dedupe(faults),
        )
    return results, validations


__all__ = [
    "normalize_typed_calculation_container",
    "validate_analysis_table_artifact_rc4",
    "validate_calculation_output_rc4",
    "verify_analysis_table_rc4",
    "verify_typed_calculations_rc4",
]

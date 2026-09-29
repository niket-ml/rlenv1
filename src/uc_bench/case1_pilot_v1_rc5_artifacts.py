"""Cohort-aware artifact and calculation verification for Case-1 RC5."""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any

from uc_bench.case1_pilot_v1_rc4_artifacts import (
    normalize_typed_calculation_container,
    validate_calculation_output_rc4,
    verify_typed_calculations_rc4,
)
from uc_bench.case1_pilot_v1_rc5_cohort import CommittedCohort
from uc_bench.mmmvp_open_calculations import (
    VerifiedTable,
    _aggregate_records,
    _parse_rows,
    _purchased_records,
    _raw_primary,
    _x17_primary,
)
from uc_bench.mmmvp_open_rc16_artifacts import (
    ArtifactValidationResult,
    _csv_shape_faults,
    _dedupe,
)


def expected_records_rc5(
    workspace: Path,
    source_paths: tuple[str, ...],
    resource_id: str,
    cohort: CommittedCohort,
) -> tuple[dict[str, dict[str, Any]], str] | None:
    """Resolve source records while applying committed primary membership once."""

    if any(path.startswith("purchased/X17/") for path in source_paths):
        records = _x17_primary(workspace)
        if records is None:
            return None
        return (
            {key: value for key, value in records.items() if key in cohort.included_source_records},
            "PURCHASED",
        )
    if any(path.startswith(f"purchased/{resource_id}/") for path in source_paths):
        records = _purchased_records(workspace, resource_id)
        if records is None:
            return None
        if resource_id == "X31":
            records = {
                key: value
                for key, value in records.items()
                if value.get("entity_id") in cohort.included_entities
            }
            if {str(value.get("entity_id")) for value in records.values()} != set(
                cohort.included_entities
            ):
                return None
        return records, "PURCHASED"
    if not cohort.valid:
        return None
    raw = _raw_primary(workspace)
    records = {
        key: value
        for key, value in raw.items()
        if key in cohort.included_source_records and value["entity_id"] in cohort.included_entities
    }
    if set(records) != set(cohort.included_source_records):
        return None
    return records, "SUPPLIED_AND_REVEALED"


def verify_analysis_table_rc5(
    workspace: Path,
    artifact_id: str,
    manifest: dict[str, Any],
    path: Path,
    resource_id: str,
    cohort: CommittedCohort,
) -> VerifiedTable | None:
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
        expected_pair = expected_records_rc5(
            workspace,
            tuple(str(item) for item in manifest.get("source_paths") or []),
            resource_id,
            cohort,
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


def validate_analysis_table_artifact_rc5(
    workspace: Path,
    artifact_id: str,
    artifact: tuple[dict[str, Any], Path],
    resource_id: str,
    cohort: CommittedCohort,
    *,
    linked_calculation_ids: tuple[str, ...] = (),
) -> tuple[ArtifactValidationResult, VerifiedTable | None]:
    manifest, path = artifact
    expected_pair = None
    maximum_rows: int | None = None
    try:
        expected_pair = expected_records_rc5(
            workspace,
            tuple(str(item) for item in manifest.get("source_paths") or []),
            resource_id,
            cohort,
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
        table = verify_analysis_table_rc5(
            workspace, artifact_id, manifest, path, resource_id, cohort
        )
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


__all__ = [
    "expected_records_rc5",
    "normalize_typed_calculation_container",
    "validate_analysis_table_artifact_rc5",
    "validate_calculation_output_rc4",
    "verify_analysis_table_rc5",
    "verify_typed_calculations_rc4",
]

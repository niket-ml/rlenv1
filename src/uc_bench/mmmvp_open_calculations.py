"""Canonical table and typed-calculation verification for the open MMMVP RC."""

from __future__ import annotations

import csv
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, median
from typing import Any

from sklearn.metrics import log_loss, roc_auc_score

METRICS = {
    "ROC_AUC",
    "BRIER_SCORE",
    "LOG_LOSS",
    "CALIBRATION_ERROR",
    "NET_BENEFIT",
    "SITE_WEIGHTED_ROC_AUC",
    "WORST_SITE_ROC_AUC",
    "ENTITY_COUNT",
}
ESTIMATORS = {"EMPIRICAL", "ENTITY_WEIGHTED", "ROW_EMPIRICAL"}
CALCULATION_ROLES = {"PRIMARY", "FOLLOWUP", "SENSITIVITY", "DIAGNOSTIC"}
EVIDENCE_SOURCES = {"SUPPLIED_AND_REVEALED", "PURCHASED"}
ANALYSIS_STRUCTURES = {"ENTITY_AGGREGATED", "SOURCE_RECORD_CLUSTERED"}
AGGREGATIONS = {"MEAN", "MEDIAN", "FIRST", "NONE"}
UNCERTAINTY_METHODS = {"CLUSTER_BOOTSTRAP_PERCENTILE"}

_VALUE_TOLERANCE = {
    "ROC_AUC": 0.002,
    "BRIER_SCORE": 0.002,
    "LOG_LOSS": 0.002,
    "CALIBRATION_ERROR": 0.002,
    "NET_BENEFIT": 0.002,
    "SITE_WEIGHTED_ROC_AUC": 0.002,
    "WORST_SITE_ROC_AUC": 0.002,
    "ENTITY_COUNT": 0.1,
}


@dataclass(frozen=True, slots=True)
class CanonicalRow:
    entity_id: str
    source_record_ids: tuple[str, ...]
    prediction: float
    outcome: int
    split: str
    contexts: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class VerifiedTable:
    artifact_id: str
    structure: str
    aggregation: str
    evidence_source: str
    rows: tuple[CanonicalRow, ...]
    prediction_column: str
    outcome_column: str
    context_columns: tuple[str, ...]
    source_paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CalculationResult:
    calculation_id: str
    valid: bool
    metric: str
    estimator: str
    role: str
    table_id: str
    reported_value: float | None
    recomputed_value: float | None
    value_tolerance: float | None
    uncertainty_claimed: bool
    uncertainty_valid: bool
    faults: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "calculation_id": self.calculation_id,
            "valid": self.valid,
            "metric": self.metric,
            "estimator": self.estimator,
            "role": self.role,
            "table_id": self.table_id,
            "reported_value": self.reported_value,
            "recomputed_value": self.recomputed_value,
            "value_tolerance": self.value_tolerance,
            "uncertainty_claimed": self.uncertainty_claimed,
            "uncertainty_valid": self.uncertainty_valid,
            "faults": list(self.faults),
        }


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _parts(value: str) -> tuple[str, ...]:
    return tuple(
        sorted({part.strip() for part in value.replace(",", "|").split("|") if part.strip()})
    )


def _safe_file(workspace: Path, relative: Any) -> Path | None:
    if not isinstance(relative, str) or not relative:
        return None
    path = (workspace / relative).resolve()
    if path != workspace and workspace not in path.parents:
        return None
    return path if path.is_file() else None


def _raw_primary(workspace: Path) -> dict[str, Any]:
    metadata = _read_csv(workspace / "data/cohort_metadata.csv")
    predictions = {
        row["sample_id"]: float(row["predicted_probability"])
        for row in _read_csv(workspace / "data/locked_predictions.csv")
    }
    outcomes = {
        row["patient_key"]: int(row["week6_response"])
        for row in _read_csv(workspace / "revealed/validation_outcomes.csv")
    }
    records: dict[str, dict[str, Any]] = {}
    for row in metadata:
        sample = row["sample_id"]
        if str(row.get("baseline_eligible", "")).lower() != "true" or sample not in predictions:
            continue
        entity = row["fingerprint_cluster"]
        records[sample] = {
            "source_record_id": sample,
            "entity_id": entity,
            "prediction": predictions[sample],
            "outcome": outcomes[entity],
            "context": str(row.get("site", "")),
        }
    return records


def _x17_primary(workspace: Path) -> dict[str, dict[str, Any]] | None:
    path = workspace / "purchased/X17/canonical_person_crosswalk.csv"
    if not path.is_file():
        return None
    base = _raw_primary(workspace)
    rows = _read_csv(path)
    if not rows or {row.get("source_record_id") for row in rows} != set(base):
        return None
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        source = str(row["source_record_id"])
        canonical = str(row["canonical_person_id"])
        item = base[source]
        if row.get("fingerprint_cluster") != item["entity_id"]:
            return None
        result[source] = {**item, "entity_id": canonical}
    return result


def _purchased_records(workspace: Path, resource_id: str) -> dict[str, dict[str, Any]] | None:
    if resource_id == "X31":
        prediction_path = workspace / "purchased/X31/replay_predictions.csv"
        outcome_path = workspace / "revealed/validation_outcomes.csv"
    elif resource_id == "X46":
        prediction_path = workspace / "purchased/X46/matched_predictions.csv"
        outcome_path = workspace / "purchased/X46/matched_outcomes.csv"
    else:
        return None
    if not prediction_path.is_file() or not outcome_path.is_file():
        return None
    outcomes = {row["patient_key"]: int(row["week6_response"]) for row in _read_csv(outcome_path)}
    result: dict[str, dict[str, Any]] = {}
    for row in _read_csv(prediction_path):
        entity = row["patient_key"]
        if entity not in outcomes:
            return None
        result[entity] = {
            "source_record_id": entity,
            "entity_id": entity,
            "prediction": float(row["predicted_probability"]),
            "outcome": outcomes[entity],
            "context": str(row.get("site", "")),
        }
    return result


def _expected_records(
    workspace: Path,
    source_paths: tuple[str, ...],
    resource_id: str,
) -> tuple[dict[str, dict[str, Any]], str] | None:
    if any(path.startswith("purchased/X17/") for path in source_paths):
        records = _x17_primary(workspace)
        return (records, "PURCHASED") if records is not None else None
    if any(path.startswith(f"purchased/{resource_id}/") for path in source_paths):
        records = _purchased_records(workspace, resource_id)
        return (records, "PURCHASED") if records is not None else None
    return _raw_primary(workspace), "SUPPLIED_AND_REVEALED"


def _aggregate_records(
    records: dict[str, dict[str, Any]], aggregation: str
) -> dict[str, CanonicalRow]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in records.values():
        grouped.setdefault(item["entity_id"], []).append(item)
    result: dict[str, CanonicalRow] = {}
    for entity, values in grouped.items():
        ordered = sorted(values, key=lambda row: row["source_record_id"])
        probabilities = [float(row["prediction"]) for row in ordered]
        if aggregation == "MEAN":
            prediction = mean(probabilities)
        elif aggregation == "MEDIAN":
            prediction = median(probabilities)
        elif aggregation == "FIRST" or aggregation == "NONE" and len(probabilities) == 1:
            prediction = probabilities[0]
        else:
            raise ValueError("Aggregation is inconsistent with source-record multiplicity")
        outcomes = {int(row["outcome"]) for row in ordered}
        if len(outcomes) != 1:
            raise ValueError("Canonical entity has conflicting outcomes")
        result[entity] = CanonicalRow(
            entity_id=entity,
            source_record_ids=tuple(row["source_record_id"] for row in ordered),
            prediction=prediction,
            outcome=next(iter(outcomes)),
            split="VALIDATION",
            contexts=tuple(sorted({str(row["context"]) for row in ordered if row["context"]})),
        )
    return result


def _parse_rows(path: Path, mapping: dict[str, str]) -> list[CanonicalRow]:
    rows: list[CanonicalRow] = []
    context_column = mapping.get("context")
    for row in _read_csv(path):
        rows.append(
            CanonicalRow(
                entity_id=str(row[mapping["entity_id"]]),
                source_record_ids=_parts(str(row[mapping["source_record_ids"]])),
                prediction=float(row[mapping["prediction"]]),
                outcome=int(row[mapping["outcome"]]),
                split=str(row[mapping["split"]]).upper(),
                contexts=_parts(str(row.get(context_column, ""))) if context_column else (),
            )
        )
    return rows


def verify_analysis_table(
    workspace: Path,
    artifact_id: str,
    manifest: dict[str, Any],
    path: Path,
    resource_id: str,
) -> VerifiedTable | None:
    """Normalize an agent table and verify source/entity/alignment invariants."""

    mapping = manifest.get("column_map") or {}
    structure = manifest.get("analysis_structure")
    aggregation = manifest.get("aggregation")
    if structure not in ANALYSIS_STRUCTURES or aggregation not in AGGREGATIONS:
        return None
    try:
        observed = _parse_rows(path, mapping)
        expected_pair = _expected_records(
            workspace,
            tuple(str(item) for item in manifest.get("source_paths") or []),
            resource_id,
        )
        if expected_pair is None or not observed:
            return None
        records, evidence_source = expected_pair
        if structure == "ENTITY_AGGREGATED":
            expected = _aggregate_records(records, aggregation)
            unique_entity_count = len({row.entity_id for row in observed})
            if len(observed) != len(expected) or unique_entity_count != len(observed):
                return None
            by_entity = {row.entity_id: row for row in observed}
            if set(by_entity) != set(expected):
                return None
            for entity, target in expected.items():
                row = by_entity[entity]
                if (
                    row.source_record_ids != target.source_record_ids
                    or row.outcome != target.outcome
                    or row.split != "VALIDATION"
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
                    or row.split != "VALIDATION"
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
    except (KeyError, OSError, TypeError, ValueError):
        return None


def verified_tables(
    workspace: Path,
    artifacts: dict[str, tuple[dict[str, Any], Path]],
    resource_id: str,
) -> dict[str, VerifiedTable]:
    result: dict[str, VerifiedTable] = {}
    for artifact_id, (manifest, path) in artifacts.items():
        if manifest.get("role") != "ANALYSIS_TABLE":
            continue
        table = verify_analysis_table(workspace, artifact_id, manifest, path, resource_id)
        if table is not None:
            result[artifact_id] = table
    return result


def _weights(rows: list[CanonicalRow], estimator: str) -> list[float]:
    if estimator == "ROW_EMPIRICAL":
        return [1.0] * len(rows)
    if estimator == "ENTITY_WEIGHTED":
        counts: dict[str, int] = {}
        for row in rows:
            counts[row.entity_id] = counts.get(row.entity_id, 0) + 1
        return [1.0 / counts[row.entity_id] for row in rows]
    if len({row.entity_id for row in rows}) != len(rows):
        raise ValueError("EMPIRICAL requires one row per biological entity")
    return [1.0] * len(rows)


def _weighted_mean(values: list[float], weights: list[float]) -> float:
    return sum(value * weight for value, weight in zip(values, weights, strict=True)) / sum(weights)


def _calibration_error(
    labels: list[int], probabilities: list[float], weights: list[float], bins: int
) -> float:
    total = sum(weights)
    result = 0.0
    for index in range(bins):
        low = index / bins
        high = (index + 1) / bins
        selected = [
            i
            for i, probability in enumerate(probabilities)
            if low <= probability < high or (index == bins - 1 and probability == 1)
        ]
        if not selected:
            continue
        bin_weights = [weights[i] for i in selected]
        observed = _weighted_mean([float(labels[i]) for i in selected], bin_weights)
        predicted = _weighted_mean([probabilities[i] for i in selected], bin_weights)
        result += sum(bin_weights) / total * abs(observed - predicted)
    return result


def _site_auc(rows: list[CanonicalRow], weights: list[float]) -> tuple[float, float]:
    grouped: dict[str, list[int]] = {}
    for index, row in enumerate(rows):
        if len(row.contexts) != 1:
            continue
        grouped.setdefault(row.contexts[0], []).append(index)
    values: list[tuple[float, float]] = []
    for indexes in grouped.values():
        labels = [rows[i].outcome for i in indexes]
        if len(set(labels)) < 2:
            continue
        group_weights = [weights[i] for i in indexes]
        auc = float(
            roc_auc_score(
                labels,
                [rows[i].prediction for i in indexes],
                sample_weight=group_weights,
            )
        )
        values.append((auc, sum(group_weights)))
    if not values:
        raise ValueError("No context contains both outcome classes")
    return (
        sum(auc * weight for auc, weight in values) / sum(weight for _, weight in values),
        min(auc for auc, _ in values),
    )


def calculate_metric(
    rows: list[CanonicalRow], metric: str, estimator: str, parameters: dict[str, Any]
) -> float:
    if metric not in METRICS or estimator not in ESTIMATORS or not rows:
        raise ValueError("Unsupported typed calculation")
    weights = _weights(rows, estimator)
    labels = [row.outcome for row in rows]
    predictions = [row.prediction for row in rows]
    if metric == "ROC_AUC":
        return float(roc_auc_score(labels, predictions, sample_weight=weights))
    if metric == "BRIER_SCORE":
        squared_errors = [
            (prediction - outcome) ** 2
            for prediction, outcome in zip(predictions, labels, strict=True)
        ]
        return _weighted_mean(
            squared_errors,
            weights,
        )
    if metric == "LOG_LOSS":
        return float(log_loss(labels, predictions, sample_weight=weights, labels=[0, 1]))
    if metric == "CALIBRATION_ERROR":
        bins = int(parameters.get("bin_count", 0))
        if not 2 <= bins <= 20:
            raise ValueError("Calibration error requires bin_count in [2,20]")
        return _calibration_error(labels, predictions, weights, bins)
    if metric == "NET_BENEFIT":
        threshold = float(parameters.get("threshold"))
        if not 0 < threshold < 1:
            raise ValueError("Net benefit requires threshold in (0,1)")
        total = sum(weights)
        true_positive = sum(
            weight
            for outcome, prediction, weight in zip(labels, predictions, weights, strict=True)
            if prediction >= threshold and outcome == 1
        )
        false_positive = sum(
            weight
            for outcome, prediction, weight in zip(labels, predictions, weights, strict=True)
            if prediction >= threshold and outcome == 0
        )
        return true_positive / total - false_positive / total * threshold / (1 - threshold)
    if metric in {"SITE_WEIGHTED_ROC_AUC", "WORST_SITE_ROC_AUC"}:
        site_weighted, worst = _site_auc(rows, weights)
        return site_weighted if metric == "SITE_WEIGHTED_ROC_AUC" else worst
    if metric == "ENTITY_COUNT":
        return float(len({row.entity_id for row in rows}))
    raise ValueError("Unsupported metric")


def _cluster_bootstrap_interval(
    rows: list[CanonicalRow],
    estimator: str,
    parameters: dict[str, Any],
    uncertainty: dict[str, Any],
) -> tuple[float, float]:
    replicates = int(uncertainty["replicates"])
    seed = int(uncertainty["seed"])
    if not 100 <= replicates <= 2000:
        raise ValueError("Bootstrap replicates outside disclosed bounds")
    by_entity: dict[str, list[CanonicalRow]] = {}
    for row in rows:
        by_entity.setdefault(row.entity_id, []).append(row)
    entities = sorted(by_entity)
    generator = random.Random(seed)
    values: list[float] = []
    for _ in range(replicates):
        sampled: list[CanonicalRow] = []
        for draw_index in range(len(entities)):
            entity = generator.choice(entities)
            for row in by_entity[entity]:
                sampled.append(
                    CanonicalRow(
                        entity_id=f"B{draw_index}:{entity}",
                        source_record_ids=row.source_record_ids,
                        prediction=row.prediction,
                        outcome=row.outcome,
                        split=row.split,
                        contexts=row.contexts,
                    )
                )
        if len({row.outcome for row in sampled}) < 2:
            continue
        values.append(calculate_metric(sampled, "ROC_AUC", estimator, parameters))
    if len(values) < replicates * 0.9:
        raise ValueError("Too few valid bootstrap replicates")
    values.sort()
    alpha = 1 - float(uncertainty["level"])
    low_index = max(0, int(math.floor((alpha / 2) * (len(values) - 1))))
    high_index = min(len(values) - 1, int(math.ceil((1 - alpha / 2) * (len(values) - 1))))
    return values[low_index], values[high_index]


def cluster_bootstrap_interval(
    rows: list[CanonicalRow],
    estimator: str,
    *,
    replicates: int,
    seed: int,
    level: float = 0.95,
) -> tuple[float, float]:
    """Public deterministic implementation used by valid local fixtures."""

    return _cluster_bootstrap_interval(
        rows,
        estimator,
        {},
        {
            "method": "CLUSTER_BOOTSTRAP_PERCENTILE",
            "replicates": replicates,
            "seed": seed,
            "level": level,
        },
    )


def _output_confirms(
    artifact: tuple[dict[str, Any], Path] | None,
    calculation_id: str,
    reported_value: float,
) -> bool:
    if artifact is None or artifact[0].get("role") != "CALCULATION_OUTPUT":
        return False
    try:
        payload = json.loads(artifact[1].read_text(encoding="utf-8"))
        rows = payload.get("typed_calculations") or []
        match = next(row for row in rows if row.get("calculation_id") == calculation_id)
        return math.isclose(float(match["reported_value"]), reported_value, abs_tol=1e-12)
    except (KeyError, StopIteration, TypeError, ValueError, OSError, json.JSONDecodeError):
        return False


def verify_typed_calculations(
    final: dict[str, Any],
    artifacts: dict[str, tuple[dict[str, Any], Path]],
    tables: dict[str, VerifiedTable],
) -> dict[str, CalculationResult]:
    """Recompute each declared value; unrelated numbers are never inspected."""

    results: dict[str, CalculationResult] = {}
    for calculation in final.get("calculations") or []:
        calculation_id = str(calculation.get("calculation_id") or "")
        metric = str(calculation.get("metric") or "")
        estimator = str(calculation.get("estimator") or "")
        role = str(calculation.get("role") or "")
        table_id = str(calculation.get("source_analysis_table_id") or "")
        faults: list[str] = []
        table = tables.get(table_id)
        try:
            reported = float(calculation["reported_value"])
        except (KeyError, TypeError, ValueError):
            reported = None
            faults.append("reported_value_invalid")
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
            declared_context = tuple(calculation.get("context_columns") or [])
            if declared_context != table.context_columns:
                faults.append("context_columns_mismatch")
            if calculation.get("evidence_source") != table.evidence_source:
                faults.append("evidence_source_mismatch")
        cohort = calculation.get("cohort") or {}
        split_values = {str(item).upper() for item in cohort.get("split_values") or []}
        entity_ids = set(str(item) for item in cohort.get("entity_ids") or [])
        rows = [] if table is None else [row for row in table.rows if row.split in split_values]
        if entity_ids:
            rows = [row for row in rows if row.entity_id in entity_ids]
        if not split_values or not rows or int(cohort.get("included_row_count") or -1) != len(rows):
            faults.append("cohort_mismatch")
        parameters = calculation.get("parameters") or {}
        recomputed: float | None = None
        if not faults:
            try:
                recomputed = calculate_metric(rows, metric, estimator, parameters)
            except (TypeError, ValueError):
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
        if reported is not None and not _output_confirms(
            artifacts.get(output_id), calculation_id, reported
        ):
            faults.append("saved_output_mismatch")
        uncertainty = calculation.get("uncertainty")
        uncertainty_valid = uncertainty is None
        if uncertainty is not None:
            uncertainty_valid = False
            try:
                if metric != "ROC_AUC" or uncertainty.get("method") not in UNCERTAINTY_METHODS:
                    raise ValueError("unsupported uncertainty")
                expected_low, expected_high = _cluster_bootstrap_interval(
                    rows, estimator, parameters, uncertainty
                )
                uncertainty_valid = math.isclose(
                    float(uncertainty["lower"]), expected_low, abs_tol=0.02
                ) and math.isclose(float(uncertainty["upper"]), expected_high, abs_tol=0.02)
            except (KeyError, TypeError, ValueError):
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
            faults=tuple(dict.fromkeys(faults)),
        )
    return results


__all__ = [
    "AGGREGATIONS",
    "ANALYSIS_STRUCTURES",
    "CALCULATION_ROLES",
    "ESTIMATORS",
    "EVIDENCE_SOURCES",
    "METRICS",
    "UNCERTAINTY_METHODS",
    "CalculationResult",
    "CanonicalRow",
    "VerifiedTable",
    "calculate_metric",
    "cluster_bootstrap_interval",
    "verified_tables",
    "verify_typed_calculations",
]

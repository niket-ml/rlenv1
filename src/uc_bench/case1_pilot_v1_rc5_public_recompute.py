"""Public, no-answer recomputation used by the RC5 local dry-run validator."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import random
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from statistics import mean, median
from typing import Any

METRIC_ALIASES = {
    "BINARY_CONCORDANCE": "ROC_AUC",
    "THRESHOLD_EXPECTED_UTILITY": "NET_BENEFIT",
}


def _strict_zip(*values: Any) -> Any:
    """Python-3.9-compatible strict zip for this standalone validator."""

    materialized = [list(value) for value in values]
    if len({len(value) for value in materialized}) > 1:
        raise ValueError("paired vectors have different lengths")
    return zip(*materialized)  # noqa: B905 - explicit length check above supports Python 3.9


def _numeric_direction(before: Any, after: Any) -> str | None:
    if (
        isinstance(before, bool)
        or isinstance(after, bool)
        or not isinstance(before, (int, float))
        or not isinstance(after, (int, float))
        or not math.isfinite(float(before))
        or not math.isfinite(float(after))
    ):
        return None
    if math.isclose(float(before), float(after), abs_tol=1e-12):
        return "UNCHANGED"
    return "INCREASE" if float(after) > float(before) else "DECREASE"


def belief_revision_errors(
    validation: dict[str, Any],
    followup: dict[str, Any],
    final: dict[str, Any],
    observed_effect: str | None,
) -> list[str]:
    """Apply the disclosed evidence-direction rule without interpreting prose."""

    errors: list[str] = []
    try:
        hypotheses = validation.get("hypotheses") or []
        before = {row["hypothesis_id"]: row["belief"] for row in hypotheses}
        effects = {row["hypothesis_id"]: row["decision_effect_if_true"] for row in hypotheses}
        if len(before) != len(hypotheses) or set(effects) != set(before):
            return ["validation hypotheses are not uniquely identified"]
        if followup.get("beliefs_before") != before:
            errors.append("follow-up beliefs differ from committed hypotheses")
        contingencies = {
            row["contingency_id"]: row for row in followup.get("result_contingencies") or []
        }
        updates = final.get("belief_updates") or []
        selected_ids = {row.get("matched_contingency_id") for row in updates}
        if len(selected_ids) != 1 or next(iter(selected_ids), None) not in contingencies:
            return [*errors, "belief updates do not select one committed contingency"]
        selected = contingencies[next(iter(selected_ids))]
        committed_directions = {
            row["hypothesis_id"]: row["direction"]
            for row in selected.get("hypothesis_updates") or []
        }
        observed = {row["hypothesis_id"]: row for row in updates}
        if (
            len(observed) != len(updates)
            or set(observed) != set(before)
            or set(committed_directions) != set(before)
        ):
            return [*errors, "belief update identifiers differ from committed hypotheses"]
        directions: dict[str, str | None] = {}
        for identifier, row in observed.items():
            if not math.isclose(float(row.get("before")), float(before[identifier]), abs_tol=1e-12):
                errors.append("belief update before-value differs from commitment")
            direction = _numeric_direction(row.get("before"), row.get("after"))
            directions[identifier] = direction
            if direction != committed_directions[identifier]:
                errors.append("belief direction differs from selected contingency")

        if observed_effect in {"NO_NEW_EVIDENCE", "INEFFECTIVE"}:
            if set(directions.values()) != {"UNCHANGED"}:
                errors.append("no-new-evidence result requires unchanged beliefs")
        else:
            blocker = observed_effect in {"EXPOSES_BLOCKER", "MISLEADING_REASSURANCE"}
            changed = False
            for identifier, direction in directions.items():
                effect = effects[identifier]
                if effect == "NONE":
                    allowed = {"UNCHANGED"}
                elif (effect == "SUPPORTS") != blocker:
                    allowed = {"UNCHANGED", "INCREASE"}
                else:
                    allowed = {"UNCHANGED", "DECREASE"}
                if direction not in allowed:
                    errors.append("belief revision direction contradicts verified evidence")
                changed = changed or direction in {"INCREASE", "DECREASE"}
            if not changed:
                errors.append("material evidence requires at least one belief change")
    except (ArithmeticError, KeyError, StopIteration, TypeError, ValueError, RecursionError):
        errors.append("belief revision cannot be interpreted")
    return list(dict.fromkeys(errors))


def _weighted_auc(labels: list[int], predictions: list[float], weights: list[float]) -> float:
    positives = [
        (prediction, weight)
        for label, prediction, weight in _strict_zip(labels, predictions, weights)
        if label == 1
    ]
    negatives = [
        (prediction, weight)
        for label, prediction, weight in _strict_zip(labels, predictions, weights)
        if label == 0
    ]
    denominator = sum(weight for _value, weight in positives) * sum(
        weight for _value, weight in negatives
    )
    if denominator <= 0:
        raise ValueError("AUC requires both outcome classes")
    concordance = 0.0
    for positive, positive_weight in positives:
        for negative, negative_weight in negatives:
            comparison = 1.0 if positive > negative else 0.5 if positive == negative else 0.0
            concordance += comparison * positive_weight * negative_weight
    return concordance / denominator


@dataclass(frozen=True)
class Row:
    entity_id: str
    source_record_ids: tuple[str, ...]
    prediction: float
    outcome: int
    split: str
    contexts: tuple[str, ...]


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _parts(value: str) -> tuple[str, ...]:
    return tuple(
        sorted({part.strip() for part in value.replace(",", "|").split("|") if part.strip()})
    )


def _safe(workspace: Path, relative: Any) -> Path | None:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        return None
    path = (workspace / relative).resolve()
    return path if workspace in path.parents and path.is_file() else None


def _source_hashes(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        pairs = list(value.items())
    elif isinstance(value, list):
        pairs = []
        for row in value:
            if not isinstance(row, dict) or set(row) != {"path", "sha256"}:
                raise ValueError("source hash list item")
            pairs.append((row["path"], row["sha256"]))
    else:
        raise ValueError("source hash container")
    result: dict[str, str] = {}
    for path, digest in pairs:
        if (
            not isinstance(path, str)
            or not path
            or path in result
            or not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ValueError("source hash entry")
        result[path] = digest
    return dict(sorted(result.items()))


def _resource_hashes_valid(workspace: Path, resource: str, summary: dict[str, Any]) -> bool:
    manifest_relative = f"purchased/{resource}/resource_manifest.json"
    manifest_path = _safe(workspace, manifest_relative)
    if manifest_path is None:
        return False
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected: dict[str, str] = {}
    for row in manifest.get("files") or []:
        if not isinstance(row, dict) or set(row) < {"path", "sha256"}:
            return False
        relative = f"purchased/{resource}/{row['path']}"
        if relative in expected:
            return False
        expected[relative] = str(row["sha256"])
    permitted = {
        **expected,
        manifest_relative: hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    }
    observed = _source_hashes(summary.get("source_hashes"))
    if not set(expected).issubset(observed) or not set(observed).issubset(permitted):
        return False
    return all(
        (path := _safe(workspace, relative)) is not None
        and permitted[relative] == digest
        and hashlib.sha256(path.read_bytes()).hexdigest() == digest
        for relative, digest in observed.items()
    )


def _parse_table(path: Path, mapping: dict[str, str]) -> list[Row]:
    values: list[Row] = []
    for item in _read_csv(path):
        prediction = float(item[mapping["prediction"]])
        outcome = int(item[mapping["outcome"]])
        if not 0 <= prediction <= 1 or outcome not in {0, 1}:
            raise ValueError("prediction/outcome domain")
        context = item.get(mapping.get("context", ""), "").strip()
        values.append(
            Row(
                entity_id=item[mapping["entity_id"]],
                source_record_ids=_parts(item[mapping["source_record_ids"]]),
                prediction=prediction,
                outcome=outcome,
                split=item[mapping["split"]],
                contexts=_parts(context),
            )
        )
    return values


def _weights(rows: list[Row], estimator: str) -> list[float]:
    if estimator == "ROW_EMPIRICAL":
        return [1.0] * len(rows)
    if estimator == "ENTITY_WEIGHTED":
        counts: dict[str, int] = {}
        for row in rows:
            counts[row.entity_id] = counts.get(row.entity_id, 0) + 1
        return [1.0 / counts[row.entity_id] for row in rows]
    if estimator != "EMPIRICAL" or len({row.entity_id for row in rows}) != len(rows):
        raise ValueError("unsupported estimator/dependence combination")
    return [1.0] * len(rows)


def _weighted_mean(values: list[float], weights: list[float]) -> float:
    return sum(value * weight for value, weight in _strict_zip(values, weights)) / sum(weights)


def _site_auc(rows: list[Row], weights: list[float]) -> tuple[float, float]:
    grouped: dict[str, list[int]] = {}
    for index, row in enumerate(rows):
        if len(row.contexts) == 1:
            grouped.setdefault(row.contexts[0], []).append(index)
    values: list[tuple[float, float]] = []
    for indexes in grouped.values():
        labels = [rows[index].outcome for index in indexes]
        if len(set(labels)) < 2:
            continue
        group_weights = [weights[index] for index in indexes]
        value = _weighted_auc(
            labels,
            [rows[index].prediction for index in indexes],
            group_weights,
        )
        values.append((value, sum(group_weights)))
    if not values:
        raise ValueError("no context has both outcome classes")
    return (
        sum(value * weight for value, weight in values) / sum(weight for _, weight in values),
        min(value for value, _ in values),
    )


def calculate_metric(
    rows: list[Row], metric: str, estimator: str, parameters: dict[str, Any]
) -> float:
    metric = METRIC_ALIASES.get(metric, metric)
    if not rows:
        raise ValueError("empty calculation cohort")
    weights = _weights(rows, estimator)
    labels = [row.outcome for row in rows]
    predictions = [row.prediction for row in rows]
    if metric == "ROC_AUC":
        return _weighted_auc(labels, predictions, weights)
    if metric == "BRIER_SCORE":
        return _weighted_mean(
            [
                (prediction - outcome) ** 2
                for prediction, outcome in _strict_zip(predictions, labels)
            ],
            weights,
        )
    if metric == "LOG_LOSS":
        epsilon = sys.float_info.epsilon
        losses = []
        for label, prediction in _strict_zip(labels, predictions):
            probability = min(1 - epsilon, max(epsilon, prediction))
            losses.append(
                -(label * math.log(probability) + (1 - label) * math.log(1 - probability))
            )
        return _weighted_mean(losses, weights)
    if metric == "CALIBRATION_ERROR":
        bins = int(parameters.get("bin_count", 0))
        if not 2 <= bins <= 20:
            raise ValueError("calibration bin_count outside [2,20]")
        total = sum(weights)
        error = 0.0
        for index in range(bins):
            low, high = index / bins, (index + 1) / bins
            selected = [
                row
                for row, probability in enumerate(predictions)
                if low <= probability < high or (index == bins - 1 and probability == 1)
            ]
            if selected:
                selected_weights = [weights[row] for row in selected]
                observed = _weighted_mean(
                    [float(labels[row]) for row in selected], selected_weights
                )
                predicted = _weighted_mean([predictions[row] for row in selected], selected_weights)
                error += sum(selected_weights) / total * abs(observed - predicted)
        return error
    if metric == "NET_BENEFIT":
        threshold = float(parameters.get("threshold"))
        if not 0 < threshold < 1:
            raise ValueError("utility threshold outside (0,1)")
        total = sum(weights)
        true_positive = sum(
            weight
            for outcome, prediction, weight in _strict_zip(labels, predictions, weights)
            if prediction >= threshold and outcome == 1
        )
        false_positive = sum(
            weight
            for outcome, prediction, weight in _strict_zip(labels, predictions, weights)
            if prediction >= threshold and outcome == 0
        )
        return true_positive / total - false_positive / total * threshold / (1 - threshold)
    if metric in {"SITE_WEIGHTED_ROC_AUC", "WORST_SITE_ROC_AUC"}:
        site_weighted, worst = _site_auc(rows, weights)
        return site_weighted if metric == "SITE_WEIGHTED_ROC_AUC" else worst
    if metric == "ENTITY_COUNT":
        return float(len({row.entity_id for row in rows}))
    raise ValueError("unsupported calculation metric")


def bootstrap_interval(
    rows: list[Row], estimator: str, uncertainty: dict[str, Any]
) -> tuple[float, float]:
    replicates = int(uncertainty["replicates"])
    seed = int(uncertainty["seed"])
    if not 100 <= replicates <= 2000:
        raise ValueError("bootstrap replicates outside [100,2000]")
    by_entity: dict[str, list[Row]] = {}
    for row in rows:
        by_entity.setdefault(row.entity_id, []).append(row)
    entities = sorted(by_entity)
    generator = random.Random(seed)
    values: list[float] = []
    for _ in range(replicates):
        sampled: list[Row] = []
        for draw_index in range(len(entities)):
            entity = generator.choice(entities)
            sampled.extend(
                replace(row, entity_id=f"B{draw_index}:{entity}") for row in by_entity[entity]
            )
        if len({row.outcome for row in sampled}) >= 2:
            values.append(calculate_metric(sampled, "ROC_AUC", estimator, {}))
    if len(values) < replicates * 0.9:
        raise ValueError("too few valid bootstrap replicates")
    values.sort()
    alpha = 1 - float(uncertainty["level"])
    low = max(0, int(math.floor((alpha / 2) * (len(values) - 1))))
    high = min(len(values) - 1, int(math.ceil((1 - alpha / 2) * (len(values) - 1))))
    return values[low], values[high]


def _visible_outcomes(workspace: Path) -> dict[str, int]:
    binding_path = workspace / "revealed/evidence_binding.json"
    binding = json.loads(binding_path.read_text(encoding="utf-8"))
    if binding.get("schema_version") != "case1-visible-outcome-binding-1":
        raise ValueError("visible outcome binding version")
    path = _safe(workspace, binding.get("path"))
    if path is None or not str(binding.get("path")).startswith("revealed/"):
        raise ValueError("visible outcome binding path")
    if hashlib.sha256(path.read_bytes()).hexdigest() != binding.get("sha256"):
        raise ValueError("visible outcome binding hash")
    entity_column = str(binding.get("entity_id_column") or "")
    outcome_column = str(binding.get("outcome_column") or "")
    values: dict[str, int] = {}
    for row in _read_csv(path):
        entity = row[entity_column]
        outcome = int(row[outcome_column])
        if not entity or entity in values or outcome not in {0, 1}:
            raise ValueError("visible outcome binding contents")
        values[entity] = outcome
    return values


def _committed_manifest(
    workspace: Path, validation: dict[str, Any]
) -> tuple[set[str], list[dict[str, str]]]:
    relative = (validation.get("prospective_specification") or {}).get(
        "eligible_entity_manifest_path"
    )
    path = _safe(workspace, relative)
    if path is None or not str(relative).startswith("work/"):
        raise ValueError("committed manifest path")
    rows = _read_csv(path)
    included = {
        row["entity_id"] for row in rows if row.get("included", "").strip().lower() == "true"
    }
    if not included:
        raise ValueError("committed cohort is empty")
    return included, rows


def _primary_source_records(
    workspace: Path,
    validation: dict[str, Any],
    *,
    outcomes_override: dict[str, int] | None = None,
) -> dict[str, dict[str, Any]]:
    metadata = {row["sample_id"]: row for row in _read_csv(workspace / "data/cohort_metadata.csv")}
    predictions = {
        row["sample_id"]: float(row["predicted_probability"])
        for row in _read_csv(workspace / "data/locked_predictions.csv")
    }
    outcomes = outcomes_override or _visible_outcomes(workspace)
    included, _manifest = _committed_manifest(workspace, validation)
    return {
        source: {
            "entity_id": row["fingerprint_cluster"],
            "prediction": predictions[source],
            "outcome": outcomes[row["fingerprint_cluster"]],
            "context": row["site"],
        }
        for source, row in metadata.items()
        if row.get("baseline_eligible", "").lower() == "true"
        and row["fingerprint_cluster"] in included
    }


def _purchased_source_records(
    workspace: Path,
    validation: dict[str, Any],
    resource: str,
    source_paths: list[Any],
) -> dict[str, dict[str, Any]] | None:
    """Reconstruct the three resources that can support FOLLOWUP calculations."""

    paths = [str(path) for path in source_paths]
    if resource == "X17" and any(path.startswith("purchased/X17/") for path in paths):
        metadata = {
            row["sample_id"]: row for row in _read_csv(workspace / "data/cohort_metadata.csv")
        }
        predictions = {
            row["sample_id"]: float(row["predicted_probability"])
            for row in _read_csv(workspace / "data/locked_predictions.csv")
        }
        outcomes = _visible_outcomes(workspace)
        raw = {
            source: {
                "entity_id": row["fingerprint_cluster"],
                "prediction": predictions[source],
                "outcome": outcomes[row["fingerprint_cluster"]],
                "context": row["site"],
            }
            for source, row in metadata.items()
            if row.get("baseline_eligible", "").lower() == "true" and source in predictions
        }
        crosswalk = _read_csv(workspace / "purchased/X17/canonical_person_crosswalk.csv")
        if {row.get("source_record_id") for row in crosswalk} != set(raw):
            return None
        mapped: dict[str, dict[str, Any]] = {}
        for row in crosswalk:
            source = row["source_record_id"]
            if row.get("fingerprint_cluster") != raw[source]["entity_id"]:
                return None
            mapped[source] = {**raw[source], "entity_id": row["canonical_person_id"]}
        _included, manifest = _committed_manifest(workspace, validation)
        included_sources = {
            source
            for row in manifest
            if row.get("included", "").strip().lower() == "true"
            for source in _parts(row.get("source_record_ids", ""))
        }
        return {key: value for key, value in mapped.items() if key in included_sources}
    if resource == "X31" and any(path.startswith("purchased/X31/") for path in paths):
        predictions_path = workspace / "purchased/X31/replay_predictions.csv"
        outcomes = _visible_outcomes(workspace)
    elif resource == "X46" and any(path.startswith("purchased/X46/") for path in paths):
        predictions_path = workspace / "purchased/X46/matched_predictions.csv"
        outcomes = {
            row["patient_key"]: int(row["week6_response"])
            for row in _read_csv(workspace / "purchased/X46/matched_outcomes.csv")
        }
    else:
        return None
    records: dict[str, dict[str, Any]] = {}
    included, _manifest = _committed_manifest(workspace, validation)
    for row in _read_csv(predictions_path):
        entity = row["patient_key"]
        if resource == "X31" and entity not in included:
            continue
        if entity not in outcomes or entity in records:
            return None
        records[entity] = {
            "entity_id": entity,
            "prediction": float(row["predicted_probability"]),
            "outcome": outcomes[entity],
            "context": row.get("site", ""),
        }
    if resource == "X31" and set(records) != included:
        return None
    return records


def _analysis_rows_from_primary_records(
    workspace: Path,
    validation: dict[str, Any],
    *,
    outcomes_override: dict[str, int] | None = None,
) -> tuple[list[Row], str]:
    records = _primary_source_records(workspace, validation, outcomes_override=outcomes_override)
    spec = validation["prospective_specification"]
    estimator = str(spec["estimator"])
    if spec["dependence_handling"] == "SOURCE_RECORD_CLUSTERING":
        return (
            [
                Row(
                    entity_id=str(record["entity_id"]),
                    source_record_ids=(source,),
                    prediction=float(record["prediction"]),
                    outcome=int(record["outcome"]),
                    split="PRIMARY",
                    contexts=(str(record["context"]),) if record.get("context") else (),
                )
                for source, record in sorted(records.items())
            ],
            estimator,
        )
    aggregation = str(spec["aggregation"])
    grouped: dict[str, list[str]] = {}
    for source, record in records.items():
        grouped.setdefault(str(record["entity_id"]), []).append(source)
    rows: list[Row] = []
    for entity, sources in sorted(grouped.items()):
        sources.sort()
        predictions = [float(records[source]["prediction"]) for source in sources]
        probability = {"MEAN": mean, "MEDIAN": median, "FIRST": lambda value: value[0]}[
            aggregation
        ](predictions)
        contexts = tuple(
            sorted(
                {
                    str(records[source]["context"])
                    for source in sources
                    if records[source].get("context")
                }
            )
        )
        rows.append(
            Row(
                entity_id=entity,
                source_record_ids=tuple(sources),
                prediction=float(probability),
                outcome=int(records[sources[0]]["outcome"]),
                split="PRIMARY",
                contexts=contexts,
            )
        )
    return rows, estimator


def _binary_metrics(
    predictions: list[float], outcomes: list[int], *, threshold: float = 0.5
) -> dict[str, float]:
    rows = [
        Row(str(index), (str(index),), prediction, outcome, "FOLLOWUP", ())
        for index, (prediction, outcome) in enumerate(_strict_zip(predictions, outcomes))
    ]
    return {
        "roc_auc": calculate_metric(rows, "ROC_AUC", "EMPIRICAL", {}),
        "brier_score": calculate_metric(rows, "BRIER_SCORE", "EMPIRICAL", {}),
        "net_benefit": calculate_metric(rows, "NET_BENEFIT", "EMPIRICAL", {"threshold": threshold}),
    }


def expected_resource_results(
    workspace: Path,
    validation: dict[str, Any],
    resource: str,
    *,
    primary_auc: float,
) -> dict[str, Any]:
    """Recompute a purchased package from the files revealed by that package."""

    purchased = workspace / "purchased" / resource
    if resource == "none":
        return {"new_evidence": False}
    if resource == "X17":
        rows = _read_csv(purchased / "canonical_person_crosswalk.csv")
        limitations = json.loads(
            (purchased / "package_limitations.json").read_text(encoding="utf-8")
        )
        return {
            "canonical_entity_count": len({row["canonical_person_id"] for row in rows}),
            "unresolved_record_count": len(limitations.get("unresolved_fields") or []),
        }
    if resource == "X24":
        adjudicated = _read_csv(purchased / "adjudicated_endpoints.csv")
        labels = {row["patient_key"]: int(row["week6_response"]) for row in adjudicated}
        original = _visible_outcomes(workspace)
        rows, estimator = _analysis_rows_from_primary_records(
            workspace, validation, outcomes_override=labels
        )
        spec = validation["prospective_specification"]
        result: dict[str, Any] = {
            "changed_label_count": sum(
                labels[key] != original.get(key) for key in {row.entity_id for row in rows}
            ),
            "reviewer_disagreement_count": sum(
                row.get("reviewer_agreement") != "concordant" for row in adjudicated
            ),
            "roc_auc": calculate_metric(rows, "ROC_AUC", estimator, {}),
            "binary_concordance": calculate_metric(rows, "ROC_AUC", estimator, {}),
            "brier_score": calculate_metric(rows, "BRIER_SCORE", estimator, {}),
            "log_loss": calculate_metric(rows, "LOG_LOSS", estimator, {}),
            "calibration_error": calculate_metric(
                rows,
                "CALIBRATION_ERROR",
                estimator,
                {"bin_count": int(spec["calibration_bin_count"])},
            ),
            "net_benefit": calculate_metric(
                rows,
                "NET_BENEFIT",
                estimator,
                {"threshold": float(spec["utility_threshold"])},
            ),
            "threshold_expected_utility": calculate_metric(
                rows,
                "NET_BENEFIT",
                estimator,
                {"threshold": float(spec["utility_threshold"])},
            ),
            "worst_site_roc_auc": calculate_metric(rows, "WORST_SITE_ROC_AUC", estimator, {}),
            "site_weighted_roc_auc": calculate_metric(rows, "SITE_WEIGHTED_ROC_AUC", estimator, {}),
        }
        return result
    if resource == "X31":
        included, _manifest = _committed_manifest(workspace, validation)
        predictions_by_entity = {
            row["patient_key"]: row for row in _read_csv(purchased / "replay_predictions.csv")
        }
        outcomes = _visible_outcomes(workspace)
        if not included.issubset(predictions_by_entity) or not included.issubset(outcomes):
            raise ValueError("X31 does not cover the committed cohort")
        predictions = [predictions_by_entity[entity] for entity in sorted(included)]
        result = _binary_metrics(
            [float(row["predicted_probability"]) for row in predictions],
            [outcomes[row["patient_key"]] for row in predictions],
        )
        result["primary_auc_absolute_delta"] = abs(result["roc_auc"] - primary_auc)
        return result
    if resource in {"X46", "X58"}:
        stem = "matched" if resource == "X46" else "additional"
        predictions = _read_csv(purchased / f"{stem}_predictions.csv")
        outcomes = {
            row["patient_key"]: int(row["week6_response"])
            for row in _read_csv(purchased / f"{stem}_outcomes.csv")
        }
        result = {"entity_count": len(predictions)}
        result.update(
            _binary_metrics(
                [float(row["predicted_probability"]) for row in predictions],
                [outcomes[row["patient_key"]] for row in predictions],
            )
        )
        return result
    if resource == "X63":
        memo = json.loads((purchased / "review_memo.json").read_text(encoding="utf-8"))
        return {
            "new_empirical_evidence": bool(memo.get("new_empirical_evidence")),
            "recommendation_count": len(memo.get("recommendations") or []),
        }
    raise ValueError("unknown resource")


def _primary_table_matches(
    workspace: Path,
    validation: dict[str, Any],
    artifact: dict[str, Any],
    rows: list[Row],
) -> bool:
    records = _primary_source_records(workspace, validation)
    return _table_matches_records(artifact, rows, records)


def _table_matches_records(
    artifact: dict[str, Any], rows: list[Row], records: dict[str, dict[str, Any]]
) -> bool:
    structure = artifact.get("analysis_structure")
    aggregation = artifact.get("aggregation")
    if structure == "SOURCE_RECORD_CLUSTERED":
        if aggregation != "NONE" or len(rows) != len(records):
            return False
        observed = {
            row.source_record_ids[0]: row for row in rows if len(row.source_record_ids) == 1
        }
        if set(observed) != set(records):
            return False
        return all(
            row.entity_id == records[source]["entity_id"]
            and row.outcome == records[source]["outcome"]
            and row.contexts
            == ((records[source]["context"],) if records[source]["context"] else ())
            and math.isclose(row.prediction, records[source]["prediction"], abs_tol=5e-5)
            for source, row in observed.items()
        )
    if structure != "ENTITY_AGGREGATED" or aggregation not in {
        "MEAN",
        "MEDIAN",
        "FIRST",
        "NONE",
    }:
        return False
    grouped: dict[str, list[str]] = {}
    for source, record in records.items():
        grouped.setdefault(record["entity_id"], []).append(source)
    observed = {row.entity_id: row for row in rows}
    if len(observed) != len(rows) or set(observed) != set(grouped):
        return False
    if aggregation == "NONE" and any(len(sources) != 1 for sources in grouped.values()):
        return False
    for entity, sources in grouped.items():
        sources.sort()
        values = [records[source]["prediction"] for source in sources]
        outcomes = {records[source]["outcome"] for source in sources}
        if len(outcomes) != 1:
            return False
        expected = {
            "MEAN": mean,
            "MEDIAN": median,
            "FIRST": lambda item: item[0],
            "NONE": lambda item: item[0],
        }[aggregation](values)
        row = observed[entity]
        contexts = tuple(
            sorted({records[source]["context"] for source in sources if records[source]["context"]})
        )
        if (
            row.source_record_ids != tuple(sources)
            or row.outcome != next(iter(outcomes))
            or row.contexts != contexts
            or not math.isclose(row.prediction, expected, abs_tol=5e-5)
        ):
            return False
    return True


def verify_final_calculations(
    workspace: Path, validation: dict[str, Any], final: dict[str, Any]
) -> list[str]:
    """Check the complete public scientific chain using only visible evidence."""

    errors: list[str] = []
    spec = validation.get("prospective_specification") or {}
    try:
        included, _manifest = _committed_manifest(workspace, validation)
        _visible_outcomes(workspace)
        followup = json.loads((workspace / "work/followup_plan.json").read_text(encoding="utf-8"))
        if not isinstance(followup, dict):
            raise ValueError("follow-up plan must be an object")
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return [
            "committed cohort, follow-up plan or revealed outcome binding is invalid: "
            f"{type(exc).__name__}"
        ]
    resource = str(followup.get("chosen_resource") or "")
    artifacts = {
        row.get("artifact_id"): row
        for row in final.get("artifact_manifest") or []
        if isinstance(row, dict) and row.get("artifact_id")
    }
    manifested_paths = {
        str(row.get("path"))
        for row in final.get("artifact_manifest") or []
        if isinstance(row, dict)
    }
    planned_paths = {
        str(path)
        for analysis in validation.get("planned_analyses") or []
        if isinstance(analysis, dict)
        for path in analysis.get("planned_output_paths") or []
    }
    if not planned_paths.issubset(manifested_paths):
        errors.append("every prospectively planned output must appear in artifact_manifest")
    criteria = {
        str(row.get("calculation_id")): row
        for row in validation.get("decision_criteria") or []
        if isinstance(row, dict)
    }
    assessment = final.get("resource_assessment") or {}
    decision_calculation_ids = set(criteria) | set(assessment.get("calculation_ids") or [])
    decision_calculation_ids |= {
        str(identifier)
        for claim in final.get("claims") or []
        if isinstance(claim, dict) and claim.get("status") == "SUPPORTED"
        for identifier in claim.get("calculation_ids") or []
    }
    decision_calculation_ids |= {
        str(identifier)
        for finding in final.get("findings") or []
        if isinstance(finding, dict) and finding.get("status") == "SUPPORTED"
        for identifier in finding.get("calculation_ids") or []
    }
    calculation_rows = {
        str(row.get("calculation_id") or ""): row
        for row in final.get("calculations") or []
        if isinstance(row, dict)
    }
    decision_table_ids = {
        str(calculation_rows[identifier].get("source_analysis_table_id") or "")
        for identifier in decision_calculation_ids
        if identifier in calculation_rows
    }
    tables: dict[str, list[Row]] = {}
    table_evidence_sources: dict[str, str] = {}
    for artifact_id, artifact in artifacts.items():
        decision_linked = str(artifact_id) in decision_table_ids
        # Optional work is diagnostic until a decision-critical calculation or
        # supported claim cites it. A malformed optional table cannot invalidate
        # an otherwise sound primary evidence chain.
        if artifact.get("role") != "ANALYSIS_TABLE" or not decision_linked:
            continue
        path = _safe(workspace, artifact.get("path"))
        try:
            rows = _parse_table(path, artifact.get("column_map") or {}) if path else []
        except (KeyError, OSError, TypeError, ValueError):
            rows = []
        if not rows:
            errors.append(f"analysis table cannot be parsed: {artifact_id}")
            continue
        source_paths = artifact.get("source_paths") or []
        purchased = any(str(path).startswith("purchased/") for path in source_paths)
        expected_records = (
            _purchased_source_records(workspace, validation, resource, source_paths)
            if purchased
            else _primary_source_records(workspace, validation)
        )
        if expected_records is None or not _table_matches_records(artifact, rows, expected_records):
            errors.append(f"analysis table differs from committed source evidence: {artifact_id}")
            continue
        table_evidence_sources[str(artifact_id)] = (
            "PURCHASED" if purchased else "SUPPLIED_AND_REVEALED"
        )
        if len({row.split for row in rows}) != 1:
            errors.append(f"analysis table must use one consistent split value: {artifact_id}")
            continue
        tables[str(artifact_id)] = rows

    property_metric = {
        "DISCRIMINATION": spec.get("discrimination_metric"),
        "PROBABILITY_ACCURACY": spec.get("probability_metric"),
        "CALIBRATION": spec.get("calibration_metric"),
        "THRESHOLD_UTILITY": spec.get("utility_metric"),
        "CONTEXT_ROBUSTNESS": spec.get("context_metric"),
    }
    recomputed_by_id: dict[str, float] = {}
    primary_valid: set[str] = set()
    followup_valid: set[str] = set()
    generally_valid: set[str] = set()
    for calculation in final.get("calculations") or []:
        if not isinstance(calculation, dict):
            continue
        identifier = str(calculation.get("calculation_id") or "")
        if identifier not in decision_calculation_ids:
            continue
        table_id = str(calculation.get("source_analysis_table_id") or "")
        table_artifact = artifacts.get(table_id) or {}
        rows = tables.get(table_id)
        if rows is None:
            errors.append(f"calculation source table is invalid: {identifier}")
            continue
        split_values = set((calculation.get("cohort") or {}).get("split_values") or [])
        selected = [row for row in rows if row.split in split_values]
        calculation_valid = bool(selected and len(selected) == len(rows))
        if calculation.get("evidence_source") != table_evidence_sources.get(table_id):
            errors.append(f"calculation evidence source differs from its table: {identifier}")
            calculation_valid = False
        column_map = table_artifact.get("column_map") or {}
        if (
            calculation.get("prediction_column") != column_map.get("prediction")
            or calculation.get("outcome_column") != column_map.get("outcome")
            or calculation.get("context_columns")
            != ([column_map["context"]] if column_map.get("context") else [])
        ):
            errors.append(f"calculation columns differ from its analysis table: {identifier}")
            calculation_valid = False
        try:
            recomputed = calculate_metric(
                selected,
                str(calculation.get("metric") or ""),
                str(calculation.get("estimator") or ""),
                calculation.get("parameters") or {},
            )
            if not math.isclose(
                recomputed, float(calculation.get("reported_value")), abs_tol=0.002
            ):
                errors.append(f"reported calculation does not recompute: {identifier}")
                calculation_valid = False
            recomputed_by_id[identifier] = recomputed
            uncertainty = calculation.get("uncertainty")
            if uncertainty is not None:
                lower, upper = bootstrap_interval(
                    selected, str(calculation["estimator"]), uncertainty
                )
                if not math.isclose(
                    lower, float(uncertainty.get("lower")), abs_tol=0.002
                ) or not math.isclose(upper, float(uncertainty.get("upper")), abs_tol=0.002):
                    errors.append(f"reported uncertainty does not recompute: {identifier}")
                    calculation_valid = False
        except (ArithmeticError, KeyError, TypeError, ValueError):
            errors.append(f"calculation cannot be recomputed: {identifier}")
            calculation_valid = False
        output = artifacts.get(calculation.get("output_artifact_id"))
        output_path = _safe(workspace, (output or {}).get("path"))
        try:
            if (output or {}).get("role") != "CALCULATION_OUTPUT":
                raise ValueError("output role")
            payload = json.loads(output_path.read_text(encoding="utf-8")) if output_path else {}
            typed = payload.get("typed_calculations") or []
            if isinstance(typed, dict):
                saved = typed.get(identifier) or {}
            else:
                saved = next(row for row in typed if row.get("calculation_id") == identifier)
            if not math.isclose(
                float(saved.get("reported_value")),
                float(calculation.get("reported_value")),
                abs_tol=1e-12,
            ):
                raise ValueError("saved value mismatch")
        except (AttributeError, KeyError, OSError, StopIteration, TypeError, ValueError):
            errors.append(f"saved calculation output does not confirm value: {identifier}")
            calculation_valid = False

        criterion = criteria.get(identifier)
        if criterion is not None:
            prop = str(criterion.get("property") or "")
            expected_structure = (
                "ENTITY_AGGREGATED"
                if spec.get("dependence_handling") == "PERSON_LEVEL_AGGREGATION"
                else "SOURCE_RECORD_CLUSTERED"
            )
            expected_aggregation = (
                spec.get("aggregation") if expected_structure == "ENTITY_AGGREGATED" else "NONE"
            )
            cohort = calculation.get("cohort") or {}
            entity_ids = set(cohort.get("entity_ids") or [])
            expected_count = (
                len(included) if expected_structure == "ENTITY_AGGREGATED" else len(rows)
            )
            if any(
                (
                    calculation.get("role") != "PRIMARY",
                    calculation.get("metric") != property_metric.get(prop),
                    calculation.get("estimator") != spec.get("estimator"),
                    calculation.get("evidence_source") != "SUPPLIED_AND_REVEALED",
                    table_artifact.get("analysis_structure") != expected_structure,
                    table_artifact.get("aggregation") != expected_aggregation,
                    bool(entity_ids) and entity_ids != included,
                    cohort.get("included_row_count") != expected_count,
                )
            ):
                errors.append(f"primary calculation differs from prospective plan: {identifier}")
                calculation_valid = False
            parameters = calculation.get("parameters") or {}
            if prop == "CALIBRATION" and parameters.get("bin_count") != spec.get(
                "calibration_bin_count"
            ):
                errors.append(f"calibration bins differ from commitment: {identifier}")
                calculation_valid = False
            if prop == "THRESHOLD_UTILITY":
                threshold = parameters.get("threshold")
                if not isinstance(threshold, (int, float)) or not math.isclose(
                    float(threshold), float(spec.get("utility_threshold", -1)), abs_tol=1e-12
                ):
                    errors.append(f"utility threshold differs from commitment: {identifier}")
                    calculation_valid = False
                if calculation.get("metric") == "THRESHOLD_EXPECTED_UTILITY" and (
                    not math.isclose(
                        float(parameters.get("true_positive_value", -1)), 1.0, abs_tol=1e-12
                    )
                    or not math.isclose(
                        float(parameters.get("false_positive_cost", -1)),
                        float(spec["utility_threshold"]) / (1 - float(spec["utility_threshold"])),
                        abs_tol=1e-12,
                    )
                ):
                    errors.append(f"expected-utility values differ from commitment: {identifier}")
                    calculation_valid = False
            if prop == "DISCRIMINATION":
                uncertainty = calculation.get("uncertainty") or {}
                if any(
                    (
                        uncertainty.get("method") != spec.get("uncertainty_method"),
                        uncertainty.get("replicates") != spec.get("uncertainty_replicates"),
                        uncertainty.get("seed") != spec.get("uncertainty_seed"),
                        not isinstance(uncertainty.get("level"), (int, float)),
                        not math.isclose(
                            float(uncertainty.get("level", -1)),
                            float(spec.get("uncertainty_level", -2)),
                            abs_tol=1e-12,
                        ),
                    )
                ):
                    errors.append(
                        f"discrimination uncertainty differs from commitment: {identifier}"
                    )
                    calculation_valid = False
            if calculation_valid:
                primary_valid.add(identifier)
        elif calculation.get("role") == "FOLLOWUP" and calculation_valid:
            followup_valid.add(identifier)
        if calculation_valid and calculation.get("estimator") != "ROW_EMPIRICAL":
            generally_valid.add(identifier)

    if set(criteria) != primary_valid:
        errors.append("not every committed primary calculation is valid")
    criterion_results: dict[str, bool] = {}
    for identifier, criterion in criteria.items():
        if identifier not in recomputed_by_id:
            continue
        value = recomputed_by_id[identifier]
        threshold = float(criterion["threshold"])
        passed = (
            value >= threshold if criterion.get("comparator") == "AT_LEAST" else value <= threshold
        )
        if criterion.get("property") == "DISCRIMINATION":
            calculation = next(
                (
                    row
                    for row in final.get("calculations") or []
                    if isinstance(row, dict) and row.get("calculation_id") == identifier
                ),
                {},
            )
            passed = passed and float(
                (calculation.get("uncertainty") or {}).get("lower", -1)
            ) >= float((validation.get("non_vacuity") or {}).get("uncertainty_lower_bound", 0.58))
        criterion_results[str(criterion.get("property"))] = passed

    assessment = final.get("resource_assessment") or {}
    resource = str(assessment.get("resource_id") or "")
    summary_path = _safe(workspace, assessment.get("summary_artifact_path"))
    resource_relevant = False
    expected_effect: str | None = None
    expected_material: bool | None = None
    expected_results: dict[str, Any] = {}
    if summary_path is None:
        errors.append("resource summary artifact is missing")
    else:
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            if (
                summary.get("schema_version") != "case1-resource-summary-1"
                or summary.get("resource_id") != resource
                or not _resource_hashes_valid(workspace, resource, summary)
            ):
                errors.append("resource summary identity or transitive source hashes are invalid")
            discrimination_id = next(
                identifier
                for identifier, criterion in criteria.items()
                if criterion.get("property") == "DISCRIMINATION"
            )
            expected_results = expected_resource_results(
                workspace,
                validation,
                resource,
                primary_auc=recomputed_by_id[discrimination_id],
            )
            observed_results = summary.get("results") or {}
            if set(observed_results) != set(expected_results):
                errors.append("resource summary result keys differ from recomputation")
            else:
                for key, wanted in expected_results.items():
                    got = observed_results[key]
                    if isinstance(wanted, bool):
                        matches = got is wanted
                    else:
                        matches = (
                            isinstance(got, (int, float))
                            and not isinstance(got, bool)
                            and math.isclose(float(got), float(wanted), abs_tol=0.002)
                        )
                    if not matches:
                        errors.append(f"resource result does not recompute: {key}")
            endpoint_rows = _read_csv(workspace / "data/endpoint_source_ledger.csv")
            unresolved = {
                row["patient_key"]
                for row in endpoint_rows
                if row.get("patient_key") in included
                and any(
                    marker in row.get("review_status", "").lower()
                    for marker in ("discordant", "pending", "ambiguous")
                )
            }
            threshold = float(
                json.loads((workspace / "work/followup_plan.json").read_text(encoding="utf-8"))[
                    "materiality_threshold"
                ]
            )
            if resource == "none":
                resource_relevant = (
                    bool(criteria)
                    and set(criteria) == primary_valid
                    and len(criterion_results) == 5
                    and not unresolved
                )
                expected_effect, expected_material = "NO_NEW_EVIDENCE", False
            elif resource == "X17":
                expected_material = bool(
                    expected_results["unresolved_record_count"]
                    or expected_results["canonical_entity_count"] != len(included)
                )
                provenance = json.loads(
                    (workspace / "identity_provenance.json").read_text(encoding="utf-8")
                )
                authoritative = (provenance.get("authoritative_relationship") or {}).get(
                    "relationship"
                ) == "same_privacy_preserving_person_identifier"
                resource_relevant = bool(expected_material and not authoritative)
                expected_effect = "RESOLVES" if expected_material else "INEFFECTIVE"
            elif resource == "X24":
                expected_material = bool(unresolved)
                resource_relevant = expected_material
                expected_effect = (
                    "EXPOSES_BLOCKER"
                    if expected_results["roc_auc"] <= 0.5 or expected_results["net_benefit"] < 0
                    else "RESOLVES"
                )
            elif resource == "X31":
                expected_material = expected_results["primary_auc_absolute_delta"] > threshold
                resource_relevant = expected_material
                expected_effect = "EXPOSES_BLOCKER" if expected_material else "RESOLVES"
            elif resource == "X46":
                expected_material = True
                resource_relevant = True
                expected_effect = (
                    "EXPOSES_BLOCKER"
                    if expected_results["roc_auc"] <= 0.5 or expected_results["net_benefit"] < 0
                    else "REDUCES_UNCERTAINTY"
                )
            elif resource == "X58":
                expected_material = (
                    abs(expected_results["roc_auc"] - recomputed_by_id[discrimination_id])
                    > threshold
                    or expected_results["net_benefit"] < 0
                )
                resource_relevant = expected_material
                expected_effect = "EXPOSES_BLOCKER" if expected_material else "REDUCES_UNCERTAINTY"
            elif resource == "X63":
                expected_material = bool(expected_results["new_empirical_evidence"])
                resource_relevant = expected_material
                expected_effect = "RESOLVES" if expected_material else "REDUCES_UNCERTAINTY"
            if not resource_relevant:
                errors.append("selected resource is not relevant to the bounded current decision")
            if assessment.get("observed_effect") != expected_effect:
                errors.append("resource observed_effect differs from recomputation")
            if assessment.get("material") is not expected_material:
                errors.append("resource material flag differs from recomputation")
            calculation_ids = set(assessment.get("calculation_ids") or [])
            if resource in {"X17", "X31", "X46"} and (
                not calculation_ids or not calculation_ids.issubset(followup_valid)
            ):
                errors.append("empirical resource needs valid FOLLOWUP calculations")
            summary_relative = str(assessment.get("summary_artifact_path") or "")
            if any(
                summary_relative not in set(row.get("evidence_refs") or [])
                for row in final.get("belief_updates") or []
                if isinstance(row, dict)
            ):
                errors.append("belief updates do not cite the resource summary")
            errors.extend(belief_revision_errors(validation, followup, final, expected_effect))
        except (
            ArithmeticError,
            KeyError,
            MemoryError,
            OSError,
            RecursionError,
            StopIteration,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            errors.append(f"resource results cannot be recomputed: {type(exc).__name__}")

    all_primary_pass = len(criterion_results) == 5 and all(criterion_results.values())
    if resource == "X24" and expected_results.get("changed_label_count", 0):
        result_key = {
            "ROC_AUC": "roc_auc",
            "BINARY_CONCORDANCE": "binary_concordance",
            "BRIER_SCORE": "brier_score",
            "LOG_LOSS": "log_loss",
            "CALIBRATION_ERROR": "calibration_error",
            "NET_BENEFIT": "net_benefit",
            "THRESHOLD_EXPECTED_UTILITY": "threshold_expected_utility",
            "WORST_SITE_ROC_AUC": "worst_site_roc_auc",
            "SITE_WEIGHTED_ROC_AUC": "site_weighted_roc_auc",
        }
        corrected: list[bool] = []
        for criterion in criteria.values():
            value = expected_results[result_key[str(criterion["metric"])]]
            corrected.append(
                value >= float(criterion["threshold"])
                if criterion["comparator"] == "AT_LEAST"
                else value <= float(criterion["threshold"])
            )
        all_primary_pass = len(corrected) == 5 and all(corrected)
    supports_continue = all_primary_pass and not (
        expected_effect == "EXPOSES_BLOCKER" and expected_material is True
    )
    decision = final.get("decision") or {}
    if supports_continue != (decision.get("disposition") == "CONTINUE"):
        errors.append("final disposition does not follow verified criteria and resource evidence")
    if decision.get("use_scope") in {"CLINICAL_DECISION_SUPPORT", "TREATMENT_SELECTION"}:
        errors.append("internal Case-1 evidence cannot support clinical use")
    claims = [row for row in final.get("claims") or [] if isinstance(row, dict)]
    findings = [row for row in final.get("findings") or [] if isinstance(row, dict)]
    supported_effects = {
        row.get("decision_effect") for row in findings if row.get("status") == "SUPPORTED"
    }
    if any(
        row.get("status") == "SUPPORTED"
        and (
            not row.get("evidence_refs")
            or not row.get("calculation_ids")
            or not set(row.get("calculation_ids") or []).issubset(generally_valid)
        )
        for row in findings
    ):
        errors.append("supported finding lacks independently valid cited evidence")
    if decision.get("disposition") == "CONTINUE" and (
        "SUPPORTS" not in supported_effects or "INVALIDATES" in supported_effects
    ):
        errors.append("continued path lacks a supported SUPPORTS finding or retains a blocker")
    if decision.get("disposition") in {"PAUSE", "STOP", "INSUFFICIENT_EVIDENCE"} and not (
        {"WEAKENS", "INVALIDATES"} & supported_effects
    ):
        errors.append("contained path lacks a supported WEAKENS or INVALIDATES finding")
    forbidden = {
        "INDEPENDENT_VALIDATION",
        "CLINICAL_UTILITY",
        "TREATMENT_EFFECT",
        "CROSS_CONTEXT_TRANSPORT",
    }
    if any(row.get("status") == "SUPPORTED" and row.get("scope") in forbidden for row in claims):
        errors.append("a supported claim exceeds the Case-1 evidence scope")
    status_by_scope: dict[str, set[str]] = {}
    for row in claims:
        status_by_scope.setdefault(str(row.get("scope")), set()).add(str(row.get("status")))
    if any(len(statuses) > 1 for statuses in status_by_scope.values()):
        errors.append("one claim scope cannot be both supported and unsupported")
    supported = {row.get("scope") for row in claims if row.get("status") == "SUPPORTED"}
    if decision.get("use_scope") == "RESEARCH_PROBABILITY" and (
        "PROGNOSTIC_PROBABILITY" not in supported
    ):
        errors.append("research probability use lacks its supported bounded claim")
    if decision.get("use_scope") == "RESEARCH_RANKING" and ("PROGNOSTIC_RANKING" not in supported):
        errors.append("research ranking use lacks its supported bounded claim")
    criterion_ids = {
        str(row.get("property")): str(row.get("calculation_id"))
        for row in validation.get("decision_criteria") or []
        if isinstance(row, dict)
    }
    required_by_scope = {
        "PROGNOSTIC_PROBABILITY": {
            criterion_ids.get("DISCRIMINATION"),
            criterion_ids.get("PROBABILITY_ACCURACY"),
            criterion_ids.get("CALIBRATION"),
        },
        "PROGNOSTIC_RANKING": {criterion_ids.get("DISCRIMINATION")},
    }
    for claim in claims:
        if claim.get("status") != "SUPPORTED":
            continue
        calculation_ids = set(claim.get("calculation_ids") or [])
        if not claim.get("evidence_refs") or not calculation_ids.issubset(generally_valid):
            errors.append("supported claim lacks independently valid cited evidence")
        required = required_by_scope.get(str(claim.get("scope")))
        if required is not None and (None in required or not required.issubset(calculation_ids)):
            errors.append("supported bounded claim lacks its required primary metric families")
    return list(dict.fromkeys(errors))


__all__ = [
    "belief_revision_errors",
    "bootstrap_interval",
    "calculate_metric",
    "verify_final_calculations",
]

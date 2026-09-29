"""Small, dependency-free metrics used by the v0.7 diligence environment.

The benchmark intentionally exposes row-level CSV files rather than precomputed
diagnoses.  These helpers are shared by packet construction, the reference
solver, and deterministic grading.  They are not mounted in the agent workspace.
"""

from __future__ import annotations

import csv
import math
import random
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from statistics import mean, median
from typing import Any


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def roc_auc(labels: Iterable[int], scores: Iterable[float]) -> float:
    """Return the Mann-Whitney ROC AUC, with ties receiving half credit."""

    pairs = sorted(zip(scores, labels, strict=True), key=lambda row: row[0])
    positives = sum(label for _, label in pairs)
    negatives = len(pairs) - positives
    if positives == 0 or negatives == 0:
        raise ValueError("ROC AUC requires both outcome classes")

    rank_sum = 0.0
    index = 0
    while index < len(pairs):
        end = index + 1
        while end < len(pairs) and pairs[end][0] == pairs[index][0]:
            end += 1
        average_rank = ((index + 1) + end) / 2
        rank_sum += average_rank * sum(label for _, label in pairs[index:end])
        index = end
    return (rank_sum - positives * (positives + 1) / 2) / (positives * negatives)


def brier_score(labels: Iterable[int], probabilities: Iterable[float]) -> float:
    values = [
        (float(probability) - int(label)) ** 2
        for label, probability in zip(labels, probabilities, strict=True)
    ]
    if not values:
        raise ValueError("Brier score requires observations")
    return mean(values)


def calibration_error(
    labels: Iterable[int], probabilities: Iterable[float], *, bins: int = 5
) -> float:
    """Expected absolute calibration error using fixed-width probability bins."""

    grouped: dict[int, list[tuple[int, float]]] = defaultdict(list)
    for label, probability in zip(labels, probabilities, strict=True):
        probability = min(max(float(probability), 0.0), 1.0)
        grouped[min(int(probability * bins), bins - 1)].append((int(label), probability))
    total = sum(len(rows) for rows in grouped.values())
    if total == 0:
        raise ValueError("Calibration error requires observations")
    return sum(
        len(rows)
        / total
        * abs(mean(label for label, _ in rows) - mean(probability for _, probability in rows))
        for rows in grouped.values()
    )


def net_benefit(
    labels: Iterable[int], probabilities: Iterable[float], *, threshold: float
) -> float:
    if not 0 < threshold < 1:
        raise ValueError("Threshold must lie strictly between zero and one")
    pairs = list(zip(labels, probabilities, strict=True))
    if not pairs:
        raise ValueError("Net benefit requires observations")
    true_positive = sum(
        int(probability >= threshold and label == 1) for label, probability in pairs
    )
    false_positive = sum(
        int(probability >= threshold and label == 0) for label, probability in pairs
    )
    odds = threshold / (1 - threshold)
    return true_positive / len(pairs) - false_positive / len(pairs) * odds


def collapse_to_patient(
    metadata: list[dict[str, str]],
    predictions: list[dict[str, str]],
    outcomes: list[dict[str, str]],
    *,
    identity_field: str = "fingerprint_cluster",
) -> list[dict[str, Any]]:
    """Collapse baseline biopsies to patients using the median prediction."""

    meta_by_sample = {row["sample_id"]: row for row in metadata}
    outcome_by_patient = {row["patient_key"]: int(row["week6_response"]) for row in outcomes}
    grouped: dict[str, list[float]] = defaultdict(list)
    sites: dict[str, str] = {}
    for row in predictions:
        meta = meta_by_sample[row["sample_id"]]
        if meta["baseline_eligible"].lower() != "true":
            continue
        patient = meta[identity_field]
        grouped[patient].append(float(row["predicted_probability"]))
        sites.setdefault(patient, meta["site"])
    missing = sorted(set(grouped) - set(outcome_by_patient))
    if missing:
        raise ValueError(f"Missing patient outcomes for: {missing[:3]}")
    return [
        {
            "patient_key": patient,
            "site": sites[patient],
            "probability": median(probabilities),
            "outcome": outcome_by_patient[patient],
        }
        for patient, probabilities in sorted(grouped.items())
    ]


def metric_bundle(rows: list[dict[str, Any]], *, threshold: float = 0.5) -> dict[str, float]:
    labels = [int(row["outcome"]) for row in rows]
    probabilities = [float(row["probability"]) for row in rows]
    return {
        "auc": roc_auc(labels, probabilities),
        "brier": brier_score(labels, probabilities),
        "ece": calibration_error(labels, probabilities),
        "net_benefit": net_benefit(labels, probabilities, threshold=threshold),
    }


def site_metric_bundle(rows: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["site"])].append(row)
    site_auc: dict[str, float | None] = {}
    weighted_sum = 0.0
    weighted_n = 0
    for site, site_rows in sorted(grouped.items()):
        labels = {int(row["outcome"]) for row in site_rows}
        value = (
            roc_auc(
                [int(row["outcome"]) for row in site_rows],
                [float(row["probability"]) for row in site_rows],
            )
            if len(labels) == 2
            else None
        )
        site_auc[site] = value
        if value is not None:
            weighted_sum += value * len(site_rows)
            weighted_n += len(site_rows)
    return {
        "site_auc": site_auc,
        "site_weighted_auc": weighted_sum / weighted_n if weighted_n else None,
        "worst_site_auc": min(value for value in site_auc.values() if value is not None),
    }


def cluster_bootstrap_auc(
    rows: list[dict[str, Any]], *, seed: int, replicates: int = 600
) -> tuple[float, float]:
    """Patient bootstrap interval. Rows must already contain one row per patient."""

    generator = random.Random(seed)
    values: list[float] = []
    for _ in range(replicates):
        sample = [rows[generator.randrange(len(rows))] for _ in rows]
        labels = [int(row["outcome"]) for row in sample]
        if len(set(labels)) != 2:
            continue
        values.append(roc_auc(labels, [float(row["probability"]) for row in sample]))
    if len(values) < replicates * 0.9:
        raise ValueError("Too few valid bootstrap replicates")
    values.sort()
    return values[math.floor(0.025 * len(values))], values[math.floor(0.975 * len(values))]


def naive_row_auc(
    metadata: list[dict[str, str]],
    predictions: list[dict[str, str]],
    outcomes: list[dict[str, str]],
) -> float:
    outcome_by_patient = {row["patient_key"]: int(row["week6_response"]) for row in outcomes}
    meta_by_sample = {row["sample_id"]: row for row in metadata}
    labels: list[int] = []
    scores: list[float] = []
    for prediction in predictions:
        meta = meta_by_sample[prediction["sample_id"]]
        if meta["baseline_eligible"].lower() != "true":
            continue
        labels.append(outcome_by_patient[meta["fingerprint_cluster"]])
        scores.append(float(prediction["predicted_probability"]))
    return roc_auc(labels, scores)

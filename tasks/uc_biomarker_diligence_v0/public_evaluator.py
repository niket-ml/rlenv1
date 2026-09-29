#!/usr/bin/env python3
"""Public, sealed-data-free development evaluator for UC-Bench v0.

This file defines the exact predictor, AUC, bootstrap, and permutation
mathematics used to verify development claims. It never reads the sealed cohort.
Run it on the final written model artifact before committing.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score


def read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def predict_proba(model: dict[str, Any], expression: pd.DataFrame) -> pd.Series:
    if model.get("model_type") != "linear_logistic_on_within_sample_gene_ranks":
        raise ValueError("Unsupported model_type")
    genes = [str(gene) for gene in model["genes"]]
    coefficients = np.asarray(model["coefficients"], dtype=float)
    if len(genes) != len(coefficients):
        raise ValueError("genes and coefficients must align one-to-one")
    missing = sorted(set(genes) - set(expression.index.astype(str)))
    if missing:
        raise ValueError(f"Expression is missing predictor genes: {missing}")
    if expression.shape[0] < 1000:
        raise ValueError("Within-sample ranks require at least 1,000 background genes")
    ranks = expression.rank(axis=0, method="average", pct=True).loc[genes]
    linear = float(model["intercept"]) + coefficients @ ranks.to_numpy(dtype=float)
    probabilities = 1.0 / (1.0 + np.exp(-np.clip(linear, -700.0, 700.0)))
    return pd.Series(probabilities, index=expression.columns, name="response_probability")


def auc_with_stratified_bootstrap(
    outcomes: pd.Series,
    predictions: pd.Series,
    *,
    resamples: int,
    seed: int,
) -> tuple[float, tuple[float, float]]:
    labels = outcomes.loc[predictions.index].astype(int).to_numpy()
    probabilities = predictions.to_numpy(dtype=float)
    positive = np.flatnonzero(labels == 1)
    negative = np.flatnonzero(labels == 0)
    if not len(positive) or not len(negative):
        raise ValueError("AUC requires both outcome classes")
    rng = np.random.default_rng(seed)
    bootstrap = np.empty(resamples, dtype=float)
    for index in range(resamples):
        sample = np.concatenate(
            (
                rng.choice(positive, size=len(positive), replace=True),
                rng.choice(negative, size=len(negative), replace=True),
            )
        )
        bootstrap[index] = roc_auc_score(labels[sample], probabilities[sample])
    auc = float(roc_auc_score(labels, probabilities))
    lower, upper = (float(value) for value in np.quantile(bootstrap, (0.025, 0.975)))
    return auc, (lower, upper)


def permutation_p_value(
    outcomes: pd.Series,
    predictions: pd.Series,
    *,
    permutations: int,
    seed: int,
) -> float:
    labels = outcomes.loc[predictions.index].astype(int).to_numpy()
    probabilities = predictions.to_numpy(dtype=float)
    observed = roc_auc_score(labels, probabilities)
    rng = np.random.default_rng(seed)
    exceedances = sum(
        roc_auc_score(rng.permutation(labels), probabilities) >= observed
        for _ in range(permutations)
    )
    return float((exceedances + 1) / (permutations + 1))


def evaluate_development(
    *,
    model: dict[str, Any],
    metadata: pd.DataFrame,
    discovery_expression: pd.DataFrame,
    replication_expression: pd.DataFrame,
    resamples: int,
    discovery_seed: int,
    replication_seed: int,
    permutations: int,
    permutation_seed: int,
) -> dict[str, Any]:
    outcomes = metadata.set_index("sample_id")["response"].astype(int)
    matrices = {
        "discovery": ("GSE16879", discovery_expression),
        "replication": ("GSE73661", replication_expression),
    }
    results: dict[str, Any] = {}
    predictions: dict[str, pd.Series] = {}
    for role, (cohort, matrix) in matrices.items():
        sample_ids = metadata.loc[metadata["cohort"] == cohort, "sample_id"].tolist()
        prediction = predict_proba(model, matrix.loc[:, sample_ids])
        predictions[role] = prediction
        seed = discovery_seed if role == "discovery" else replication_seed
        auc, interval = auc_with_stratified_bootstrap(
            outcomes,
            prediction,
            resamples=resamples,
            seed=seed,
        )
        results[role] = {
            "cohort": cohort,
            "n": len(sample_ids),
            "auc": auc,
            "auc_interval": list(interval),
        }
    p_value = permutation_p_value(
        outcomes,
        predictions["replication"],
        permutations=permutations,
        seed=permutation_seed,
    )
    results["replication"]["permutation_p_value"] = p_value
    common_gene_count = len(
        set(discovery_expression.index.astype(str))
        & set(replication_expression.index.astype(str))
    )
    cohort_counts = {}
    for cohort, frame in metadata.groupby("cohort"):
        cohort_counts[str(cohort)] = {
            "n": int(len(frame)),
            "responders": int((frame["response"] == 1).sum()),
            "nonresponders": int((frame["response"] == 0).sum()),
        }
    return {
        "cohort_counts": cohort_counts,
        "common_gene_count": common_gene_count,
        "development_results": results,
        "audit_parameters": {
            "rank_strategy": "within_sample_percentile_rank",
            "bootstrap_method": "stratified_bootstrap",
            "resamples": resamples,
            "discovery_seed": discovery_seed,
            "replication_seed": replication_seed,
            "permutation_test": "replication_label_permutation",
            "permutation_count": permutations,
            "permutation_seed": permutation_seed,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, default=Path("data/metadata.csv"))
    parser.add_argument(
        "--discovery-expression",
        type=Path,
        default=Path("data/GSE16879_gene_expression.csv.gz"),
    )
    parser.add_argument(
        "--replication-expression",
        type=Path,
        default=Path("data/GSE73661_gene_expression.csv.gz"),
    )
    parser.add_argument("--resamples", type=int, default=2000)
    parser.add_argument("--discovery-seed", type=int, default=20260906)
    parser.add_argument("--replication-seed", type=int, default=20260907)
    parser.add_argument("--permutations", type=int, default=10000)
    parser.add_argument("--permutation-seed", type=int, default=20260908)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = evaluate_development(
        model=read_object(args.model),
        metadata=pd.read_csv(args.metadata),
        discovery_expression=pd.read_csv(args.discovery_expression, index_col=0),
        replication_expression=pd.read_csv(args.replication_expression, index_col=0),
        resamples=args.resamples,
        discovery_seed=args.discovery_seed,
        replication_seed=args.replication_seed,
        permutations=args.permutations,
        permutation_seed=args.permutation_seed,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

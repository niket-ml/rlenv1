"""Prespecified low-dimensional reference analysis for UC-Bench v0."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from uc_bench.errors import ContractError


@dataclass(frozen=True, slots=True)
class RankCompositeModel:
    model_version: str
    feature_schema_version: str
    genes: tuple[str, ...]
    coefficient: float
    intercept: float
    decision_threshold: float

    def __post_init__(self) -> None:
        if not self.genes or len(self.genes) != len(set(self.genes)):
            raise ContractError("Reference genes must be non-empty and unique")
        if not 0.0 <= self.decision_threshold <= 1.0:
            raise ContractError("Reference decision threshold must be within [0, 1]")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def as_linear_rank_predictor(self) -> Any:
        """Return the algebraically equivalent public predictor artifact.

        The reference feature is ``1 - mean(gene ranks)``. Expanding that
        expression yields a linear model over the individual ranks, which is
        the only executable model shape accepted by the private evaluator.
        """

        from uc_bench.predictor import LinearRankPredictor

        gene_coefficient = -self.coefficient / len(self.genes)
        return LinearRankPredictor(
            model_version=self.model_version,
            feature_schema_version=self.feature_schema_version,
            genes=self.genes,
            coefficients=tuple(gene_coefficient for _ in self.genes),
            intercept=self.intercept + self.coefficient,
            decision_threshold=self.decision_threshold,
        )

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> RankCompositeModel:
        return cls(
            model_version=value["model_version"],
            feature_schema_version=value["feature_schema_version"],
            genes=tuple(value["genes"]),
            coefficient=float(value["coefficient"]),
            intercept=float(value["intercept"]),
            decision_threshold=float(value["decision_threshold"]),
        )


def load_reference_spec(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if len(value.get("candidate_genes", [])) != 5:
        raise ContractError("Reference specification must contain exactly five genes")
    return value


def response_feature(expression: Any, genes: tuple[str, ...]) -> Any:
    """Return a cross-platform response score using within-sample gene ranks."""

    missing = sorted(set(genes) - set(expression.index))
    if missing:
        raise ContractError(f"Expression matrix is missing reference genes: {missing}")
    if expression.shape[0] < 1000:
        raise ContractError("Within-sample ranks require at least 1,000 background genes")
    percentile_ranks = expression.rank(axis=0, method="average", pct=True)
    nonresponse_score = percentile_ranks.loc[list(genes)].mean(axis=0)
    feature = 1.0 - nonresponse_score
    feature.name = "response_rank_composite"
    return feature


def fit_reference_model(
    expression: Any,
    outcomes: Any,
    *,
    sample_ids: list[str],
    spec: dict[str, Any],
) -> RankCompositeModel:
    from sklearn.linear_model import LogisticRegression

    genes = tuple(spec["candidate_genes"])
    feature = response_feature(expression.loc[:, sample_ids], genes)
    labels = outcomes.loc[sample_ids].astype(int)
    if set(labels.unique()) != {0, 1}:
        raise ContractError("Reference fitting requires both outcome classes")
    fit = spec["fit"]
    estimator = LogisticRegression(
        C=float(fit["C"]),
        class_weight=fit["class_weight"],
        solver=fit["solver"],
        random_state=int(fit["random_state"]),
    )
    estimator.fit(feature.to_numpy().reshape(-1, 1), labels.to_numpy())
    return RankCompositeModel(
        model_version=spec["model_version"],
        feature_schema_version=spec["feature_schema_version"],
        genes=genes,
        coefficient=float(estimator.coef_[0, 0]),
        intercept=float(estimator.intercept_[0]),
        decision_threshold=0.5,
    )


def predict_reference(model: RankCompositeModel, expression: Any) -> Any:
    import numpy as np
    import pandas as pd

    feature = response_feature(expression, model.genes)
    linear = model.intercept + model.coefficient * feature.to_numpy()
    probability = 1.0 / (1.0 + np.exp(-linear))
    return pd.Series(probability, index=expression.columns, name="response_probability")


def auc_with_stratified_bootstrap(
    outcomes: Any,
    predictions: Any,
    *,
    resamples: int,
    seed: int,
) -> tuple[float, tuple[float, float]]:
    import numpy as np
    from sklearn.metrics import roc_auc_score

    labels = outcomes.loc[predictions.index].astype(int).to_numpy()
    probabilities = predictions.to_numpy(dtype=float)
    positive = np.flatnonzero(labels == 1)
    negative = np.flatnonzero(labels == 0)
    if not len(positive) or not len(negative):
        raise ContractError("AUC requires both outcome classes")
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
    interval = tuple(float(value) for value in np.quantile(bootstrap, (0.025, 0.975)))
    return auc, (interval[0], interval[1])


def permutation_p_value(
    outcomes: Any,
    predictions: Any,
    *,
    permutations: int,
    seed: int,
) -> float:
    import numpy as np
    from sklearn.metrics import roc_auc_score

    labels = outcomes.loc[predictions.index].astype(int).to_numpy()
    probabilities = predictions.to_numpy(dtype=float)
    observed = roc_auc_score(labels, probabilities)
    rng = np.random.default_rng(seed)
    exceedances = 0
    for _ in range(permutations):
        exceedances += roc_auc_score(rng.permutation(labels), probabilities) >= observed
    return float((exceedances + 1) / (permutations + 1))


def expected_transfer_auc(
    replication_auc: float, spec: dict[str, Any]
) -> tuple[float, tuple[float, float]]:
    policy = spec["transport_expectation"]
    expected = max(
        float(policy["minimum_expected_auc"]),
        replication_auc - float(policy["replication_auc_penalty"]),
    )
    half_width = float(policy["interval_half_width"])
    return expected, (max(0.5, expected - half_width), min(1.0, expected + half_width))

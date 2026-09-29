"""Safe, inspectable predictor artifact supported by the v0 private grader."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

from uc_bench.errors import ContractError


@dataclass(frozen=True, slots=True)
class LinearRankPredictor:
    """Logistic model over within-sample percentile ranks of named genes."""

    model_version: str
    feature_schema_version: str
    genes: tuple[str, ...]
    coefficients: tuple[float, ...]
    intercept: float
    decision_threshold: float = 0.5

    def __post_init__(self) -> None:
        if not self.model_version.strip() or not self.feature_schema_version.strip():
            raise ContractError("Model and feature schema versions are required")
        if not 1 <= len(self.genes) <= 50:
            raise ContractError("Linear rank predictors require between 1 and 50 genes")
        if len(self.genes) != len(set(self.genes)):
            raise ContractError("Predictor genes must be unique")
        if len(self.coefficients) != len(self.genes):
            raise ContractError("Predictor coefficients must align one-to-one with genes")
        if any(not gene.strip() for gene in self.genes):
            raise ContractError("Predictor gene names must not be empty")
        numeric = (*self.coefficients, self.intercept, self.decision_threshold)
        if any(not math.isfinite(value) for value in numeric):
            raise ContractError("Predictor numeric values must be finite")
        if any(abs(value) > 1_000.0 for value in (*self.coefficients, self.intercept)):
            raise ContractError("Predictor coefficients and intercept must have magnitude <= 1,000")
        if not 0.0 <= self.decision_threshold <= 1.0:
            raise ContractError("Predictor threshold must be within [0, 1]")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> LinearRankPredictor:
        if value.get("model_type") != "linear_logistic_on_within_sample_gene_ranks":
            raise ContractError("Unsupported model_type")
        try:
            if not isinstance(value["genes"], list) or not isinstance(
                value["coefficients"], list
            ):
                raise ContractError("Predictor genes and coefficients must be JSON arrays")
            if any(isinstance(item, bool) for item in value["coefficients"]):
                raise ContractError("Predictor coefficients must be numeric, not boolean")
            return cls(
                model_version=str(value["model_version"]),
                feature_schema_version=str(value["feature_schema_version"]),
                genes=tuple(str(gene) for gene in value["genes"]),
                coefficients=tuple(float(coefficient) for coefficient in value["coefficients"]),
                intercept=float(value["intercept"]),
                decision_threshold=float(value["decision_threshold"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ContractError(f"Invalid predictor artifact: {exc}") from exc

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_type": "linear_logistic_on_within_sample_gene_ranks",
            **asdict(self),
        }

    def predict_proba(self, expression: Any) -> Any:
        """Apply the frozen model without fitting any target-cohort parameters."""

        import numpy as np
        import pandas as pd

        missing = sorted(set(self.genes) - set(expression.index))
        if missing:
            raise ContractError(f"Sealed expression is missing predictor genes: {missing}")
        if expression.shape[0] < 1000:
            raise ContractError("Within-sample ranks require at least 1,000 background genes")
        ranks = expression.rank(axis=0, method="average", pct=True).loc[list(self.genes)]
        linear = self.intercept + np.asarray(self.coefficients) @ ranks.to_numpy(dtype=float)
        linear = np.clip(linear, -700.0, 700.0)
        probabilities = 1.0 / (1.0 + np.exp(-linear))
        return pd.Series(
            probabilities,
            index=expression.columns,
            name="response_probability",
        )

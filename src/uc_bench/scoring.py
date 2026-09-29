"""Small, deterministic scoring primitives used by public tests and reports."""

from __future__ import annotations

from collections.abc import Mapping

from uc_bench.errors import ContractError


def weighted_score(scores: Mapping[str, float], weights: Mapping[str, float]) -> float:
    if set(scores) != set(weights):
        missing = sorted(set(weights) - set(scores))
        added = sorted(set(scores) - set(weights))
        raise ContractError(
            f"Score components differ from weights: missing={missing}, added={added}"
        )
    if abs(sum(weights.values()) - 1.0) > 1e-9:
        raise ContractError("Weights must sum to 1")
    if any(not 0.0 <= value <= 100.0 for value in scores.values()):
        raise ContractError("Component scores must be between 0 and 100")
    return sum(scores[name] * weight for name, weight in weights.items())


def expected_auc_calibration_score(
    expected_auc: float, realized_auc: float, *, zero_score_error: float = 0.25
) -> float:
    """Convert absolute AUC expectation error into a bounded 0–100 score."""

    if not 0.0 <= expected_auc <= 1.0 or not 0.0 <= realized_auc <= 1.0:
        raise ContractError("AUC values must be between 0 and 1")
    if zero_score_error <= 0.0:
        raise ContractError("zero_score_error must be positive")
    error = abs(expected_auc - realized_auc)
    return max(0.0, 100.0 * (1.0 - error / zero_score_error))


def data_use_lift(full_data_score: float, data_withheld_score: float) -> tuple[float, float]:
    """Return absolute lift and the withheld/full retention ratio."""

    if not 0.0 <= full_data_score <= 100.0:
        raise ContractError("full_data_score must be between 0 and 100")
    if not 0.0 <= data_withheld_score <= 100.0:
        raise ContractError("data_withheld_score must be between 0 and 100")
    retention = data_withheld_score / full_data_score if full_data_score else 1.0
    return full_data_score - data_withheld_score, retention

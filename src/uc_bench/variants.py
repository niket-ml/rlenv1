"""Deterministic controlled variants used to measure graceful failure."""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import NormalDist
from typing import Any

from uc_bench.contracts import AggregateValidationResult
from uc_bench.errors import ContractError
from uc_bench.reference import auc_with_stratified_bootstrap, permutation_p_value


def inject_label_noise(labels: Any, fraction: float, *, seed: int) -> tuple[Any, tuple[str, ...]]:
    import numpy as np

    if not 0.0 <= fraction <= 1.0:
        raise ContractError("Label-noise fraction must be within [0, 1]")
    changed_n = min(len(labels), round(len(labels) * fraction))
    rng = np.random.default_rng(seed)
    positions = sorted(rng.choice(len(labels), size=changed_n, replace=False).tolist())
    changed = labels.copy()
    changed.iloc[positions] = 1 - changed.iloc[positions].astype(int)
    return changed, tuple(str(labels.index[position]) for position in positions)


def inject_sample_swaps(
    labels: Any, count: int, *, seed: int
) -> tuple[Any, tuple[tuple[str, str], ...]]:
    import numpy as np

    positive = np.flatnonzero(labels.to_numpy(dtype=int) == 1)
    negative = np.flatnonzero(labels.to_numpy(dtype=int) == 0)
    if count < 0 or count > min(len(positive), len(negative)):
        raise ContractError("Swap count exceeds the available opposite-class pairs")
    rng = np.random.default_rng(seed)
    selected_positive = rng.choice(positive, size=count, replace=False)
    selected_negative = rng.choice(negative, size=count, replace=False)
    swapped = labels.copy()
    pairs = []
    for positive_position, negative_position in zip(
        selected_positive, selected_negative, strict=True
    ):
        positive_id = str(labels.index[positive_position])
        negative_id = str(labels.index[negative_position])
        swapped.iloc[positive_position], swapped.iloc[negative_position] = (
            swapped.iloc[negative_position],
            swapped.iloc[positive_position],
        )
        pairs.append((positive_id, negative_id))
    return swapped, tuple(pairs)


def inject_duplicate_samples(
    expression: Any, labels: Any, fraction: float, *, seed: int
) -> tuple[Any, Any, dict[str, str]]:
    import numpy as np
    import pandas as pd

    if not 0.0 <= fraction <= 1.0:
        raise ContractError("Duplicate fraction must be within [0, 1]")
    duplicate_n = min(len(labels), round(len(labels) * fraction))
    rng = np.random.default_rng(seed)
    positions = rng.choice(len(labels), size=duplicate_n, replace=False)
    mapping: dict[str, str] = {}
    columns = []
    duplicate_labels = []
    for counter, position in enumerate(positions):
        source_id = str(labels.index[position])
        duplicate_id = f"CONTROL_DUPLICATE_{counter:04d}"
        mapping[duplicate_id] = source_id
        column = expression.loc[:, source_id].rename(duplicate_id)
        columns.append(column)
        duplicate_labels.append((duplicate_id, int(labels.iloc[position])))
    if columns:
        expression = pd.concat([expression, *columns], axis=1)
        labels = pd.concat(
            [
                labels,
                pd.Series(
                    dict(duplicate_labels),
                    name=labels.name,
                    dtype=labels.dtype,
                ),
            ]
        )
    return expression, labels, mapping


def drop_features(
    expression: Any, genes: tuple[str, ...], fraction: float, *, seed: int
) -> tuple[Any, tuple[str, ...]]:
    import numpy as np

    if not 0.0 <= fraction <= 1.0:
        raise ContractError("Feature-dropout fraction must be within [0, 1]")
    available = tuple(gene for gene in genes if gene in expression.index)
    drop_n = min(len(available), math.ceil(len(available) * fraction))
    rng = np.random.default_rng(seed)
    dropped = tuple(
        sorted(rng.choice(available, size=drop_n, replace=False).tolist())
    )
    return expression.drop(index=list(dropped)), dropped


def inject_confounding_feature(labels: Any, correlation: float, *, seed: int) -> Any:
    """Create a standardized private control feature with target label correlation."""

    import numpy as np
    import pandas as pd

    if not 0.0 <= correlation < 1.0:
        raise ContractError("Confounding correlation must be within [0, 1)")
    label_vector = labels.to_numpy(dtype=float)
    standardized_labels = (label_vector - label_vector.mean()) / label_vector.std()
    rng = np.random.default_rng(seed)
    noise = rng.normal(size=len(labels))
    noise -= noise.mean()
    noise -= standardized_labels * (
        np.dot(noise, standardized_labels) / np.dot(standardized_labels, standardized_labels)
    )
    noise /= noise.std()
    feature = correlation * standardized_labels + math.sqrt(1 - correlation**2) * noise
    return pd.Series(feature, index=labels.index, name="private_control_feature")


def simulate_sufficient_validation(
    *, target_auc: float, n: int, seed: int, bootstrap_resamples: int, permutations: int
) -> AggregateValidationResult:
    """Generate an explicitly synthetic positive control for power/decision logic."""

    import numpy as np
    import pandas as pd

    if not 0.5 < target_auc < 1.0 or n < 20:
        raise ContractError("Positive control requires target AUC in (0.5, 1) and n >= 20")
    rng = np.random.default_rng(seed)
    negative_n = n // 2
    positive_n = n - negative_n
    separation = math.sqrt(2.0) * NormalDist().inv_cdf(target_auc)
    latent = np.concatenate(
        [rng.normal(0.0, 1.0, negative_n), rng.normal(separation, 1.0, positive_n)]
    )
    labels = pd.Series([0] * negative_n + [1] * positive_n)
    predictions = pd.Series(1.0 / (1.0 + np.exp(-latent)))
    auc, interval = auc_with_stratified_bootstrap(
        labels, predictions, resamples=bootstrap_resamples, seed=seed + 1
    )
    p_value = permutation_p_value(
        labels, predictions, permutations=permutations, seed=seed + 2
    )
    return AggregateValidationResult(auc, interval, p_value, n)


@dataclass(frozen=True, slots=True)
class PolicyAction:
    decision: str
    diagnostic_codes: tuple[str, ...]
    next_action_type: str


def policy_control_score(
    expected: list[PolicyAction], submitted: list[PolicyAction]
) -> float:
    """Score policy controls without using prose: 60% decision, 20% each diagnosis/action."""

    if len(expected) != len(submitted) or not expected:
        raise ContractError("Policy-control action lists must be non-empty and aligned")
    total = 0.0
    for expected_action, submitted_action in zip(expected, submitted, strict=True):
        total += 60.0 * (submitted_action.decision == expected_action.decision)
        total += 20.0 * (
            set(submitted_action.diagnostic_codes) == set(expected_action.diagnostic_codes)
        )
        total += 20.0 * (
            submitted_action.next_action_type == expected_action.next_action_type
        )
    return total / len(expected)

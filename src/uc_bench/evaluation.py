"""Repeated-evaluation validation, uncertainty, and rank-stability analysis."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from uc_bench.errors import ContractError
from uc_bench.grading import COMPONENTS


@dataclass(frozen=True, slots=True)
class EpisodeScoreRow:
    run_id: str
    model_id: str
    condition: str
    scenario_id: str
    scenario_family: str
    seed: int
    score: float
    component_scores: dict[str, float]
    contract_valid: bool
    infrastructure_failure: bool
    decision_correct: bool

    def __post_init__(self) -> None:
        for name in ("run_id", "model_id", "condition", "scenario_id", "scenario_family"):
            if not str(getattr(self, name)).strip():
                raise ContractError(f"{name} must not be empty")
        if not 0.0 <= self.score <= 100.0:
            raise ContractError("Episode score must be within [0, 100]")
        if set(self.component_scores) != set(COMPONENTS):
            raise ContractError("Episode component scores must match the benchmark taxonomy")
        if any(not 0.0 <= value <= 100.0 for value in self.component_scores.values()):
            raise ContractError("Episode component scores must be within [0, 100]")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> EpisodeScoreRow:
        return cls(
            run_id=str(value["run_id"]),
            model_id=str(value["model_id"]),
            condition=str(value["condition"]),
            scenario_id=str(value["scenario_id"]),
            scenario_family=str(value["scenario_family"]),
            seed=int(value["seed"]),
            score=float(value["score"]),
            component_scores={
                str(name): float(score)
                for name, score in value["component_scores"].items()
            },
            contract_valid=bool(value["contract_valid"]),
            infrastructure_failure=bool(value["infrastructure_failure"]),
            decision_correct=bool(value["decision_correct"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _cluster_bootstrap_interval(
    rows: list[EpisodeScoreRow], *, resamples: int, seed: int
) -> tuple[float, float]:
    import numpy as np

    if resamples <= 0 or not rows:
        raise ContractError("Cluster bootstrap requires rows and positive resamples")
    clusters: dict[int, list[float]] = {}
    for row in rows:
        clusters.setdefault(row.seed, []).append(row.score)
    cluster_ids = sorted(clusters)
    cluster_means = np.asarray(
        [sum(clusters[cluster]) / len(clusters[cluster]) for cluster in cluster_ids]
    )
    rng = np.random.default_rng(seed)
    bootstrap = np.empty(resamples)
    for index in range(resamples):
        draw = rng.choice(cluster_means, size=len(cluster_means), replace=True)
        bootstrap[index] = draw.mean()
    lower, upper = np.quantile(bootstrap, (0.025, 0.975))
    return float(lower), float(upper)


def summarize_groups(
    rows: list[EpisodeScoreRow],
    *,
    bootstrap_resamples: int,
    seed: int,
    floor_threshold: float,
    ceiling_threshold: float,
) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[EpisodeScoreRow]] = {}
    for row in rows:
        if row.infrastructure_failure:
            continue
        groups.setdefault((row.model_id, row.condition, row.scenario_family), []).append(row)
    summaries = []
    for group_index, (key, group) in enumerate(sorted(groups.items())):
        model_id, condition, scenario_family = key
        score_mean = sum(row.score for row in group) / len(group)
        interval = _cluster_bootstrap_interval(
            group,
            resamples=bootstrap_resamples,
            seed=seed + group_index,
        )
        summaries.append(
            {
                "model_id": model_id,
                "condition": condition,
                "scenario_family": scenario_family,
                "n": len(group),
                "unique_seeds": len({row.seed for row in group}),
                "score_mean": score_mean,
                "score_interval": interval,
                "contract_valid_rate": sum(row.contract_valid for row in group) / len(group),
                "decision_accuracy": sum(row.decision_correct for row in group) / len(group),
                "floor_rate": sum(row.score <= floor_threshold for row in group) / len(group),
                "ceiling_rate": sum(row.score >= ceiling_threshold for row in group) / len(group),
                "component_means": {
                    component: sum(row.component_scores[component] for row in group)
                    / len(group)
                    for component in COMPONENTS
                },
            }
        )
    return summaries


def paired_condition_lift(
    rows: list[EpisodeScoreRow], *, full_condition: str = "full_data"
) -> list[dict[str, Any]]:
    by_key = {
        (row.model_id, row.scenario_id, row.seed, row.condition): row
        for row in rows
        if not row.infrastructure_failure
    }
    pairs: dict[str, list[tuple[float, float]]] = {}
    for model_id, scenario_id, seed, condition in sorted(by_key):
        if condition != full_condition:
            continue
        full = by_key[(model_id, scenario_id, seed, full_condition)]
        withheld = by_key.get((model_id, scenario_id, seed, "data_withheld"))
        if withheld is not None:
            pairs.setdefault(model_id, []).append((full.score, withheld.score))
    summaries = []
    for model_id, model_pairs in sorted(pairs.items()):
        full_mean = sum(full for full, _ in model_pairs) / len(model_pairs)
        withheld_mean = sum(withheld for _, withheld in model_pairs) / len(model_pairs)
        summaries.append(
            {
                "model_id": model_id,
                "paired_n": len(model_pairs),
                "full_minus_withheld_mean": full_mean - withheld_mean,
                "withheld_retention": (
                    withheld_mean / full_mean if full_mean > 0.0 else None
                ),
            }
        )
    return summaries


def rank_first_probabilities(
    rows: list[EpisodeScoreRow],
    *,
    condition: str,
    scenario_family: str,
    resamples: int,
    seed: int,
) -> dict[str, float]:
    import numpy as np

    if resamples <= 0:
        raise ContractError("Rank bootstrap requires positive resamples")

    grouped: dict[str, dict[int, list[float]]] = {}
    for row in rows:
        if (
            row.condition == condition
            and row.scenario_family == scenario_family
            and not row.infrastructure_failure
        ):
            grouped.setdefault(row.model_id, {}).setdefault(row.seed, []).append(row.score)
    if len(grouped) < 2:
        return {model: 1.0 for model in grouped}
    models = sorted(grouped)
    rng = np.random.default_rng(seed)
    wins = dict.fromkeys(models, 0.0)
    for _ in range(resamples):
        means = {}
        for model in models:
            cluster_means = np.asarray(
                [sum(values) / len(values) for values in grouped[model].values()]
            )
            means[model] = float(
                rng.choice(cluster_means, size=len(cluster_means), replace=True).mean()
            )
        best = max(means.values())
        tied = [model for model, value in means.items() if abs(value - best) <= 1e-12]
        for model in tied:
            wins[model] += 1.0 / len(tied)
    return {model: wins[model] / resamples for model in models}

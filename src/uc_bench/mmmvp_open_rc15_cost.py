"""Canonical, independently cross-checked RC1.5 Case-2 cost gate."""

from __future__ import annotations

import json
import math
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np

from uc_bench.errors import ConfigurationError
from uc_bench.mmmvp_open_rc15_adapter import (
    CanonicalLaunchRoute,
    load_rc15_all_routes,
    load_rc15_launch_routes,
)
from uc_bench.model_runner import _write_json
from uc_bench.openrouter import fetch_credit_balance, fetch_key_status

COST_PLAN_PATH = Path("artifacts/mmmvp_open_rc15/cost_plan.json")
SOURCE_RUN_ROOT = Path("build/uc_bench_mmmvp_open_rc12_runs")
SCIENTIFIC_HARD_CAP_USD = 52.0
TARGET_CELL_COUNT = 9
QUANTILES = (0.5, 0.9, 0.95)


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError(f"Expected JSON object: {path}")
    return value


def _token_count(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ConfigurationError(f"{field} must be a non-negative integer")
    return value


def _summary_no_cache_cost(summary: dict[str, Any]) -> dict[str, Any]:
    """Reconstruct one archived cell through the canonical adapter boundary."""

    raw_adapter = summary.get("provider_adapter")
    if not isinstance(raw_adapter, dict):
        raise ConfigurationError("Archived summary has no provider_adapter object")
    route = CanonicalLaunchRoute.from_serialized_adapter(raw_adapter)
    prompt_tokens = 0
    completion_tokens = 0
    for index, request in enumerate(summary.get("provider_requests") or []):
        if not isinstance(request, dict):
            raise ConfigurationError("Archived provider request must be an object")
        usage = request.get("usage") or {}
        if not isinstance(usage, dict):
            raise ConfigurationError("Archived request usage must be an object")
        prompt_tokens += _token_count(
            usage.get("prompt_tokens") or 0,
            field=f"provider_requests[{index}].usage.prompt_tokens",
        )
        completion_tokens += _token_count(
            usage.get("completion_tokens") or 0,
            field=f"provider_requests[{index}].usage.completion_tokens",
        )
    cost = (
        prompt_tokens * route.prompt_price_usd_per_million
        + completion_tokens * route.completion_price_usd_per_million
    ) / 1_000_000
    return {
        "model_id": route.model_id,
        "route": route.to_record(),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "price_source_fields": list(route.price_source_fields),
        "observed_reported_cost_usd": float(
            summary.get("cumulative_reported_cost_usd") or 0.0
        ),
        "reconstructed_no_cache_cost_usd": cost,
    }


def _expanded_quantiles(values: list[float]) -> dict[str, float]:
    """Method A: explicitly expand all ordered nine-draw combinations."""

    totals = np.asarray([0.0], dtype=np.float64)
    source = np.asarray(values, dtype=np.float64)
    for _ in range(TARGET_CELL_COUNT):
        totals = (totals[:, None] + source[None, :]).reshape(-1)
    return {
        str(probability): float(
            np.quantile(totals, probability, method="inverted_cdf")
        )
        for probability in QUANTILES
    }


def _compositions(total: int, parts: int) -> list[tuple[int, ...]]:
    if parts == 1:
        return [(total,)]
    rows: list[tuple[int, ...]] = []
    for head in range(total + 1):
        rows.extend(
            (head, *tail) for tail in _compositions(total - head, parts - 1)
        )
    return rows


def _multinomial_quantiles(values: list[float]) -> dict[str, float]:
    """Method B: exact multinomial weights over unordered compositions."""

    decimals = [Decimal(str(value)) for value in values]
    distribution: Counter[Decimal] = Counter()
    numerator = math.factorial(TARGET_CELL_COUNT)
    for counts in _compositions(TARGET_CELL_COUNT, len(decimals)):
        weight = numerator
        total = Decimal("0")
        for count, value in zip(counts, decimals, strict=True):
            weight //= math.factorial(count)
            total += count * value
        distribution[total] += weight
    expected_weight = len(values) ** TARGET_CELL_COUNT
    if sum(distribution.values()) != expected_weight:
        raise ConfigurationError("Exact cost distribution lost multinomial mass")
    ordered = sorted(distribution.items())
    result: dict[str, float] = {}
    for probability in QUANTILES:
        target_rank = math.ceil(probability * expected_weight)
        cumulative = 0
        for total, weight in ordered:
            cumulative += weight
            if cumulative >= target_rank:
                result[str(probability)] = float(total)
                break
    return result


def _funding(key: str) -> dict[str, float]:
    status = fetch_key_status(key)
    credits = fetch_credit_balance(key) or {}
    account = float(credits.get("remaining_usd", 0.0))
    return {
        "key_usage_usd": float(status.usage_usd),
        "key_limit_usd": float(status.limit_usd),
        "key_limit_remaining_usd": float(status.limit_remaining_usd),
        "account_remaining_usd": account,
        "effective_remaining_usd": min(float(status.limit_remaining_usd), account),
    }


def calculate_rc15_cost_plan(
    project_root: Path,
    *,
    key: str | None = None,
) -> dict[str, Any]:
    root = project_root.resolve()
    summaries = sorted((root / SOURCE_RUN_ROOT).glob("*/run_summary.json"))
    if len(summaries) != 5:
        raise ConfigurationError("RC1.5 requires five immutable RC1.2 cost observations")
    observations = [
        _summary_no_cache_cost(_read_object(path)) for path in summaries
    ]
    values = [row["reconstructed_no_cache_cost_usd"] for row in observations]
    expanded = _expanded_quantiles(values)
    multinomial = _multinomial_quantiles(values)
    disagreements = {
        name: abs(expanded[name] - multinomial[name])
        for name in expanded
        if abs(expanded[name] - multinomial[name]) > 1e-10
    }
    if disagreements:
        raise ConfigurationError(
            f"Independent RC1.5 cost calculations disagree: {disagreements}"
        )
    all_routes = load_rc15_all_routes(root)
    compatible_routes = load_rc15_launch_routes(root)
    funding = _funding(key) if key is not None else None
    p90 = expanded["0.9"]
    paid_execution_allowed = bool(
        funding is not None
        and p90 <= SCIENTIFIC_HARD_CAP_USD
        and funding["effective_remaining_usd"] >= SCIENTIFIC_HARD_CAP_USD
    )
    return {
        "schema_version": "uc-bench-open-mmmvp-rc1-5-cost-plan-1",
        "status": "passed" if paid_execution_allowed else "rehearsal_only",
        "method": {
            "source": "five immutable RC1.2 Case-2 summaries",
            "target_cell_count": TARGET_CELL_COUNT,
            "compatible_models_only": True,
            "primary": "explicit_ordered_distribution_numpy_inverted_cdf",
            "independent_cross_check": "exact_multinomial_composition_distribution",
            "distribution_size": len(values) ** TARGET_CELL_COUNT,
            "agreement_tolerance_usd": 1e-10,
            "price_accessor": (
                "CanonicalLaunchRoute.from_serialized_adapter using "
                "maximum_route_price_usd_per_million.prompt and .completion"
            ),
            "silent_price_defaults": False,
        },
        "source_cell_count": len(observations),
        "observations": observations,
        "all_panel_routes": [route.to_record() for route in all_routes.values()],
        "compatible_routes": [
            route.to_record() for route in compatible_routes.values()
        ],
        "excluded_routes": sorted(set(all_routes) - set(compatible_routes)),
        "independent_quantiles_usd": {
            "expanded": expanded,
            "multinomial": multinomial,
        },
        "independent_calculations_agree": True,
        "sentinel_no_cache_median_usd": expanded["0.5"],
        "sentinel_no_cache_p90_usd": p90,
        "sentinel_no_cache_p95_usd": expanded["0.95"],
        "scientific_hard_cap_usd": SCIENTIFIC_HARD_CAP_USD,
        "funding": funding,
        "paid_execution_allowed": paid_execution_allowed,
        "minimum_account_top_up_required_usd": (
            None
            if funding is None
            else max(
                0.0,
                SCIENTIFIC_HARD_CAP_USD
                - funding["effective_remaining_usd"],
            )
        ),
        "minimum_cap_increase_required_usd": (
            None
            if funding is None
            else max(
                0.0,
                SCIENTIFIC_HARD_CAP_USD
                - funding["key_limit_remaining_usd"],
            )
        ),
        "api_requests": 0,
        "scientific_requests": 0,
        "heldout_requests": 0,
        "astra_requests": 0,
    }


def write_rc15_cost_plan(project_root: Path, *, key: str) -> dict[str, Any]:
    root = project_root.resolve()
    target = root / COST_PLAN_PATH
    if target.exists():
        raise ConfigurationError("RC1.5 cost plan already exists")
    value = calculate_rc15_cost_plan(root, key=key)
    _write_json(target, value, secret=key)
    return value


__all__ = [
    "COST_PLAN_PATH",
    "SCIENTIFIC_HARD_CAP_USD",
    "TARGET_CELL_COUNT",
    "calculate_rc15_cost_plan",
    "write_rc15_cost_plan",
]

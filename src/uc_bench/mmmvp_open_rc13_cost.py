"""Predeclared no-cache sentinel cost gate for RC1.3."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from uc_bench.errors import ConfigurationError
from uc_bench.model_runner import _write_json
from uc_bench.openrouter import fetch_credit_balance, fetch_key_status

RC12_RUN_ROOT = Path("build/uc_bench_mmmvp_open_rc12_runs")
COST_PLAN_PATH = Path("artifacts/mmmvp_open_rc13/cost_plan.json")
BOOTSTRAP_SEED = 2026090913
BOOTSTRAP_DRAWS = 1_000_000
TARGET_CELL_COUNT = 10
AUTHORIZED_CAP_USD = 40.0


def _summary_no_cache_cost(summary: dict[str, Any]) -> dict[str, Any]:
    adapter = summary.get("provider_adapter") or {}
    prices = adapter.get("maximum_route_price_usd_per_million") or {}
    prompt_tokens = 0
    completion_tokens = 0
    for request in summary.get("provider_requests") or []:
        usage = request.get("usage") or {}
        prompt_tokens += int(usage.get("prompt_tokens") or 0)
        completion_tokens += int(usage.get("completion_tokens") or 0)
    prompt_price = float(prices.get("prompt") or 0.0)
    completion_price = float(prices.get("completion") or 0.0)
    no_cache = (
        prompt_tokens * prompt_price + completion_tokens * completion_price
    ) / 1_000_000
    return {
        "model_id": summary["model_id"],
        "observed_reported_cost_usd": float(
            summary.get("cumulative_reported_cost_usd") or 0.0
        ),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "maximum_prompt_price_usd_per_million": prompt_price,
        "maximum_completion_price_usd_per_million": completion_price,
        "reconstructed_no_cache_cost_usd": no_cache,
    }


def calculate_rc13_cost_plan(
    project_root: Path,
    *,
    key: str | None = None,
) -> dict[str, Any]:
    """Bootstrap a ten-cell no-cache total from five observed RC1.2 cells."""

    root = project_root.resolve()
    paths = sorted((root / RC12_RUN_ROOT).glob("*/run_summary.json"))
    if len(paths) != 5:
        raise ConfigurationError("RC1.3 cost gate requires the five RC1.2 summaries")
    observations = [
        _summary_no_cache_cost(json.loads(path.read_text(encoding="utf-8")))
        for path in paths
    ]
    costs = np.asarray(
        [row["reconstructed_no_cache_cost_usd"] for row in observations],
        dtype=float,
    )
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    totals = rng.choice(
        costs,
        size=(BOOTSTRAP_DRAWS, TARGET_CELL_COUNT),
        replace=True,
    ).sum(axis=1)
    median = float(np.quantile(totals, 0.5, method="linear"))
    p90 = float(np.quantile(totals, 0.9, method="linear"))
    p95 = float(np.quantile(totals, 0.95, method="linear"))

    funding: dict[str, float] | None = None
    effective_headroom: float | None = None
    if key is not None:
        status = fetch_key_status(key)
        credits = fetch_credit_balance(key) or {}
        account = float(credits.get("remaining_usd", 0.0))
        effective_headroom = min(float(status.limit_remaining_usd), account)
        funding = {
            "key_usage_usd": float(status.usage_usd),
            "key_limit_usd": float(status.limit_usd),
            "key_limit_remaining_usd": float(status.limit_remaining_usd),
            "account_remaining_usd": account,
            "effective_remaining_usd": effective_headroom,
        }

    cap_shortfall = max(0.0, p90 - AUTHORIZED_CAP_USD)
    top_up = (
        None
        if effective_headroom is None
        else max(0.0, p90 - effective_headroom)
    )
    value = {
        "schema_version": "uc-bench-open-mmmvp-rc1-3-cost-plan-1",
        "method": {
            "name": "nonparametric_bootstrap_of_observed_no_cache_cell_costs",
            "source": "five immutable RC1.2 Case-2 sentinel summaries",
            "no_cache_reconstruction": (
                "sum prompt and completion tokens at each frozen adapter's "
                "maximum pinned-route prices"
            ),
            "target_cell_count": TARGET_CELL_COUNT,
            "bootstrap_draws": BOOTSTRAP_DRAWS,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "assumption": (
                "The five observed RC1.2 cell workloads are exchangeable draws "
                "for completion-cost planning; this does not model provider-specific "
                "behaviour for the five unobserved models."
            ),
        },
        "observations": observations,
        "observed_reported_total_usd": float(
            sum(row["observed_reported_cost_usd"] for row in observations)
        ),
        "observed_reconstructed_no_cache_total_usd": float(costs.sum()),
        "ten_cell_no_cache_median_usd": median,
        "ten_cell_no_cache_p90_usd": p90,
        "ten_cell_no_cache_p95_usd": p95,
        "authorized_cap_usd": AUTHORIZED_CAP_USD,
        "p90_exceeds_authorized_cap": p90 > AUTHORIZED_CAP_USD,
        "minimum_cap_increase_required_usd": cap_shortfall,
        "minimum_total_cap_required_usd": p90,
        "funding": funding,
        "exact_account_top_up_required_usd": top_up,
        "paid_execution_allowed": bool(
            p90 <= AUTHORIZED_CAP_USD
            and effective_headroom is not None
            and effective_headroom >= p90
        ),
        "scientific_api_requests": 0,
    }
    return value


def write_rc13_cost_plan(project_root: Path, *, key: str) -> dict[str, Any]:
    root = project_root.resolve()
    value = calculate_rc13_cost_plan(root, key=key)
    target = root / COST_PLAN_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    _write_json(target, value, secret=key)
    return value


__all__ = [
    "AUTHORIZED_CAP_USD",
    "BOOTSTRAP_DRAWS",
    "BOOTSTRAP_SEED",
    "COST_PLAN_PATH",
    "calculate_rc13_cost_plan",
    "write_rc13_cost_plan",
]

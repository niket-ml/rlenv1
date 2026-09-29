"""Conservative post-compatibility cost gate for the RC1.4 sentinel."""

from __future__ import annotations

import json
import random
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.mmmvp_open_provider import load_open_route_contract_adapters
from uc_bench.openrouter import fetch_credit_balance, fetch_key_status

COST_PLAN_PATH = Path("artifacts/mmmvp_open_rc14/cost_plan.json")
COMPATIBILITY_PATH = Path(
    "artifacts/mmmvp_open_rc14/compatibility_convergence_results.json"
)
SCIENTIFIC_HARD_CAP_USD = 52.0
BOOTSTRAP_DRAWS = 1_000_000
BOOTSTRAP_SEED = 2026090914


def _summary_no_cache_cost(summary: dict[str, Any]) -> dict[str, Any]:
    adapter = summary["provider_adapter"]
    prompt_price = float(adapter["maximum_prompt_price_usd_per_million"])
    completion_price = float(adapter["maximum_completion_price_usd_per_million"])
    prompt_tokens = 0
    completion_tokens = 0
    for request in summary.get("provider_requests") or []:
        usage = request.get("usage") or {}
        prompt_tokens += int(usage.get("prompt_tokens") or 0)
        completion_tokens += int(usage.get("completion_tokens") or 0)
    no_cache = (
        prompt_tokens * prompt_price + completion_tokens * completion_price
    ) / 1_000_000
    return {
        "model_id": summary["model_id"],
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "maximum_prompt_price_usd_per_million": prompt_price,
        "maximum_completion_price_usd_per_million": completion_price,
        "observed_reported_cost_usd": float(summary["cumulative_reported_cost_usd"]),
        "reconstructed_no_cache_cost_usd": no_cache,
    }


def _quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    index = int(probability * (len(ordered) - 1))
    return ordered[index]


def _funding(key: str) -> dict[str, float]:
    status = fetch_key_status(key)
    credits = fetch_credit_balance(key) or {}
    account = float(credits.get("remaining_usd", 0.0))
    return {
        "key_usage_usd": status.usage_usd,
        "key_limit_usd": status.limit_usd,
        "key_limit_remaining_usd": status.limit_remaining_usd,
        "account_remaining_usd": account,
        "effective_remaining_usd": min(status.limit_remaining_usd, account),
    }


def calculate_rc14_cost_plan(project_root: Path, *, key: str) -> dict[str, Any]:
    root = project_root.resolve()
    compatibility = json.loads((root / COMPATIBILITY_PATH).read_text(encoding="utf-8"))
    if compatibility.get("status") != "passed":
        raise ConfigurationError("RC1.4 compatibility did not pass")
    summaries = sorted(
        (root / "build/uc_bench_mmmvp_open_rc12_runs").glob("*/run_summary.json")
    )
    if len(summaries) != 5:
        raise ConfigurationError("Expected exactly five immutable RC1.2 cost observations")
    observations = [
        _summary_no_cache_cost(json.loads(path.read_text(encoding="utf-8")))
        for path in summaries
    ]
    values = [row["reconstructed_no_cache_cost_usd"] for row in observations]
    generator = random.Random(BOOTSTRAP_SEED)
    totals = [
        sum(generator.choice(values) for _ in range(10))
        for _ in range(BOOTSTRAP_DRAWS)
    ]
    compatibility_cost = float(compatibility["total_rc14_compatibility_cost_usd"])
    sentinel_median = _quantile(totals, 0.5)
    sentinel_p90 = _quantile(totals, 0.9)
    sentinel_p95 = _quantile(totals, 0.95)
    combined_median = compatibility_cost + sentinel_median
    combined_p90 = compatibility_cost + sentinel_p90
    combined_p95 = compatibility_cost + sentinel_p95
    funding_after = _funding(key)
    funding_before = compatibility["funding_before"]
    adapters = load_open_route_contract_adapters(root)
    if len(adapters) != 10:
        raise ConfigurationError("RC1.4 cost plan requires the frozen ten-model panel")
    paid_execution_allowed = bool(
        sentinel_p90 <= SCIENTIFIC_HARD_CAP_USD
        and funding_after["effective_remaining_usd"] >= SCIENTIFIC_HARD_CAP_USD
    )
    return {
        "schema_version": "uc-bench-open-mmmvp-rc1-4-cost-plan-1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "passed" if paid_execution_allowed else "blocked",
        "method": {
            "name": "nonparametric_bootstrap_of_observed_no_cache_cell_costs",
            "source": "five immutable RC1.2 Case-2 sentinel summaries",
            "target_cell_count": 10,
            "bootstrap_draws": BOOTSTRAP_DRAWS,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "no_cache_reconstruction": (
                "sum prompt and completion tokens at each frozen adapter's maximum "
                "pinned-route prices"
            ),
            "compatibility_cost_treatment": (
                "add exact reported RC1.4 compatibility spend to every sentinel draw"
            ),
            "assumption": (
                "The five RC1.2 workloads are exchangeable planning draws; this is "
                "conservative because they include the observed submission friction."
            ),
        },
        "source_cell_count": len(observations),
        "observations": observations,
        "compatibility_request_count": int(
            json.loads((root / "artifacts/mmmvp_open_rc14/compatibility_results.json").read_text())[
                "request_count"
            ]
        )
        + int(compatibility["round02_request_count"]),
        "compatibility_cost_usd": compatibility_cost,
        "sentinel_no_cache_median_usd": sentinel_median,
        "sentinel_no_cache_p90_usd": sentinel_p90,
        "sentinel_no_cache_p95_usd": sentinel_p95,
        "combined_compatibility_and_sentinel_median_usd": combined_median,
        "combined_compatibility_and_sentinel_p90_usd": combined_p90,
        "combined_compatibility_and_sentinel_p95_usd": combined_p95,
        "scientific_hard_cap_usd": SCIENTIFIC_HARD_CAP_USD,
        "funding_before_compatibility": funding_before,
        "funding_after_compatibility": funding_after,
        "paid_execution_allowed": paid_execution_allowed,
        "minimum_account_top_up_required_usd": max(
            0.0, SCIENTIFIC_HARD_CAP_USD - funding_after["effective_remaining_usd"]
        ),
        "minimum_cap_increase_required_usd": max(
            0.0, SCIENTIFIC_HARD_CAP_USD - funding_after["key_limit_remaining_usd"]
        ),
        "scientific_api_requests": 0,
        "heldout_requests": 0,
        "astra_requests": 0,
    }


def write_rc14_cost_plan(project_root: Path, *, key: str) -> dict[str, Any]:
    value = calculate_rc14_cost_plan(project_root, key=key)
    target = project_root.resolve() / COST_PLAN_PATH
    if target.exists():
        raise ConfigurationError("RC1.4 cost plan already exists")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(target)
    return value


__all__ = [
    "BOOTSTRAP_DRAWS",
    "BOOTSTRAP_SEED",
    "COST_PLAN_PATH",
    "SCIENTIFIC_HARD_CAP_USD",
    "calculate_rc14_cost_plan",
    "write_rc14_cost_plan",
]

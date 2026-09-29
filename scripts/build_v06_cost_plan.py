#!/usr/bin/env python3
"""Build the post-adapter v0.6 cost gate using read-only OpenRouter metadata."""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.model_runner import load_openrouter_key
from uc_bench.openrouter import fetch_credit_balance, fetch_key_status
from uc_bench.openrouter_catalog import fetch_model_endpoints, fetch_user_catalog

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PANEL_PATH = PROJECT_ROOT / "configs/hard_suite_v06_model_panel.json"
EXECUTION_PATH = PROJECT_ROOT / "configs/hard_suite_v06_execution.json"
V05_RUNS_PATH = PROJECT_ROOT / "artifacts/diagnostics/hard_suite_v05_calibration_runs.json"
COMPATIBILITY_PATH = PROJECT_ROOT / "artifacts/diagnostics/hard_suite_v06_compatibility.json"
OUTPUT_PATH = PROJECT_ROOT / "artifacts/diagnostics/hard_suite_v06_cost_plan.json"
REPORT_PATH = PROJECT_ROOT / "reports/generated/hard_suite_v06_cost_plan.md"

WORKLOAD_UPLIFT = 1.20
CACHE_HIT_CASE = 0.60
CONTINGENCY_FRACTION = 0.20
INTER_EPISODE_COOLDOWN_SECONDS = 20


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError(f"Expected object: {path}")
    return value


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ConfigurationError("Cannot take a quantile of an empty workload")
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def _ceil_cents(value: float) -> float:
    return math.ceil(max(0.0, value) * 100) / 100


def v05_workload_profile(project_root: Path = PROJECT_ROOT) -> dict[str, Any]:
    root = project_root.resolve()
    rows = _read(root / V05_RUNS_PATH.relative_to(PROJECT_ROOT)).get("runs") or []
    inputs = [float(row["token_usage"]["input_tokens"]) for row in rows]
    outputs = [float(row["token_usage"]["output_tokens"]) for row in rows]
    turns = [float(row["turn_count"]) for row in rows]
    runtimes: list[float] = []
    for row in rows:
        result = _read(root / row["run_directory"] / "verifiers_output.json")
        runtimes.append(float(result["metadata"]["time"]))
    if not inputs or len(inputs) != len(runtimes):
        raise ConfigurationError("v0.5 workload profile is incomplete")
    return {
        "source": V05_RUNS_PATH.relative_to(PROJECT_ROOT).as_posix(),
        "episode_count": len(rows),
        "input_tokens": {
            "median": median(inputs),
            "p90": _quantile(inputs, 0.90),
            "maximum": max(inputs),
        },
        "output_tokens": {
            "median": median(outputs),
            "p90": _quantile(outputs, 0.90),
            "maximum": max(outputs),
        },
        "turns": {
            "median": median(turns),
            "p90": _quantile(turns, 0.90),
            "maximum": max(turns),
        },
        "wall_time_seconds": {
            "median": median(runtimes),
            "p90": _quantile(runtimes, 0.90),
            "maximum": max(runtimes),
        },
    }


def _observed_rates(result: dict[str, Any]) -> dict[str, Any]:
    prompt_rates: list[float] = []
    completion_rates: list[float] = []
    cached_tokens = 0
    cache_write_tokens = 0
    requests = result.get("requests") or []
    for request in requests:
        usage = request.get("usage") or {}
        details = usage.get("cost_details") or {}
        prompt_tokens = float(usage.get("prompt_tokens") or 0)
        completion_tokens = float(usage.get("completion_tokens") or 0)
        if prompt_tokens and details.get("upstream_inference_prompt_cost") is not None:
            prompt_rates.append(
                1_000_000
                * float(details["upstream_inference_prompt_cost"])
                / prompt_tokens
            )
        if completion_tokens and details.get("upstream_inference_completions_cost") is not None:
            completion_rates.append(
                1_000_000
                * float(details["upstream_inference_completions_cost"])
                / completion_tokens
            )
        prompt_details = usage.get("prompt_tokens_details") or {}
        cached_tokens += int(prompt_details.get("cached_tokens") or 0)
        cache_write_tokens += int(prompt_details.get("cache_write_tokens") or 0)
    return {
        "prompt_usd_per_million": median(prompt_rates) if prompt_rates else None,
        "completion_usd_per_million": (
            median(completion_rates) if completion_rates else None
        ),
        "compatible_request_count": len(requests),
        "mean_latency_seconds_per_request": (
            float(result["total_latency_seconds"]) / len(requests) if requests else None
        ),
        "cached_prompt_tokens_observed": cached_tokens,
        "cache_write_tokens_observed": cache_write_tokens,
        "reported_cost_usd": float(result.get("total_reported_cost_usd") or 0.0),
    }


def _episode_cost(
    *,
    input_tokens: float,
    output_tokens: float,
    prompt_price: float,
    completion_price: float,
    cache_read_price: float | None,
    cache_fraction: float,
) -> float:
    uncached = input_tokens * (1 - cache_fraction) * prompt_price / 1_000_000
    cached_rate = prompt_price if cache_read_price is None else cache_read_price
    cached = input_tokens * cache_fraction * cached_rate / 1_000_000
    output = output_tokens * completion_price / 1_000_000
    return uncached + cached + output


def build_cost_plan(key: str) -> dict[str, Any]:
    panel = _read(PANEL_PATH)
    execution = _read(EXECUTION_PATH)
    compatibility = _read(COMPATIBILITY_PATH)
    if compatibility.get("status") != "passed":
        raise ConfigurationError("Compatibility must pass before post-adapter costing")
    workload = v05_workload_profile()
    catalog = fetch_user_catalog(key)
    key_status = fetch_key_status(key)
    credits = fetch_credit_balance(key) or {}
    compatible = {str(row["model_id"]): row for row in compatibility["results"]}
    input_median = WORKLOAD_UPLIFT * float(workload["input_tokens"]["median"])
    input_p90 = WORKLOAD_UPLIFT * float(workload["input_tokens"]["p90"])
    output_median = WORKLOAD_UPLIFT * float(workload["output_tokens"]["median"])
    output_p90 = WORKLOAD_UPLIFT * float(workload["output_tokens"]["p90"])
    openai_latency_baseline = median(
        _observed_rates(compatible[model_id])["mean_latency_seconds_per_request"]
        for model_id in ("openai/gpt-5.6-sol", "openai/gpt-5.2")
    )
    models: list[dict[str, Any]] = []
    for proposed in panel["models"]:
        model_id = str(proposed["model_id"])
        observed = _observed_rates(compatible[model_id])
        model = catalog.get(model_id)
        if model is None or model.canonical_slug != proposed["expected_canonical_slug"]:
            raise ConfigurationError(f"Model availability or canonical pin changed: {model_id}")
        endpoints = fetch_model_endpoints(key, model_id)
        matching = [
            row
            for row in endpoints
            if str(row.get("provider_name")) in set(proposed["provider_order"])
        ]
        if not matching:
            raise ConfigurationError(f"Pinned provider route disappeared: {model_id}")
        ceiling = proposed["maximum_route_price_usd_per_million"]
        prompt_price = float(ceiling["prompt"])
        completion_price = float(ceiling["completion"])
        if observed["prompt_usd_per_million"] is not None and not math.isclose(
            float(observed["prompt_usd_per_million"]), prompt_price, rel_tol=1e-6
        ):
            raise ConfigurationError(f"Observed prompt price no longer matches pin: {model_id}")
        if observed["completion_usd_per_million"] is not None and not math.isclose(
            float(observed["completion_usd_per_million"]),
            completion_price,
            rel_tol=1e-6,
        ):
            raise ConfigurationError(f"Observed completion price no longer matches pin: {model_id}")
        cache_read = model.pricing.get("input_cache_read")
        cache_read_per_million = (
            None if cache_read is None else float(cache_read) * 1_000_000
        )
        median_no_cache = _episode_cost(
            input_tokens=input_median,
            output_tokens=output_median,
            prompt_price=prompt_price,
            completion_price=completion_price,
            cache_read_price=cache_read_per_million,
            cache_fraction=0.0,
        )
        p90_no_cache = _episode_cost(
            input_tokens=input_p90,
            output_tokens=output_p90,
            prompt_price=prompt_price,
            completion_price=completion_price,
            cache_read_price=cache_read_per_million,
            cache_fraction=0.0,
        )
        median_cache = _episode_cost(
            input_tokens=input_median,
            output_tokens=output_median,
            prompt_price=prompt_price,
            completion_price=completion_price,
            cache_read_price=cache_read_per_million,
            cache_fraction=CACHE_HIT_CASE,
        )
        p90_cache = _episode_cost(
            input_tokens=input_p90,
            output_tokens=output_p90,
            prompt_price=prompt_price,
            completion_price=completion_price,
            cache_read_price=cache_read_per_million,
            cache_fraction=CACHE_HIT_CASE,
        )
        latency_factor = max(
            1.0,
            float(observed["mean_latency_seconds_per_request"])
            / openai_latency_baseline,
        )
        models.append(
            {
                "model_id": model_id,
                "expected_canonical_slug": proposed["expected_canonical_slug"],
                "provider_order": proposed["provider_order"],
                "allow_fallbacks": False,
                "price_ceiling_usd_per_million": ceiling,
                "catalog_cache_read_usd_per_million": cache_read_per_million,
                "compatibility_measurement": observed,
                "median_episode_cost_usd": round(median_no_cache, 6),
                "p90_episode_cost_usd": round(p90_no_cache, 6),
                "cache_case_median_episode_cost_usd": round(median_cache, 6),
                "cache_case_p90_episode_cost_usd": round(p90_cache, 6),
                "projected_episode_wall_time_seconds": {
                    "median": round(
                        WORKLOAD_UPLIFT
                        * float(workload["wall_time_seconds"]["median"])
                        * latency_factor,
                        1,
                    ),
                    "p90": round(
                        WORKLOAD_UPLIFT
                        * float(workload["wall_time_seconds"]["p90"])
                        * latency_factor,
                        1,
                    ),
                },
            }
        )
    full_median = 6 * sum(row["median_episode_cost_usd"] for row in models)
    full_p90 = 6 * sum(row["p90_episode_cost_usd"] for row in models)
    full_cache_median = 6 * sum(
        row["cache_case_median_episode_cost_usd"] for row in models
    )
    full_cache_p90 = 6 * sum(
        row["cache_case_p90_episode_cost_usd"] for row in models
    )
    sentinel_median = 2 * sum(row["median_episode_cost_usd"] for row in models)
    sentinel_p90 = 2 * sum(row["p90_episode_cost_usd"] for row in models)
    sentinel_cache_median = 2 * sum(
        row["cache_case_median_episode_cost_usd"] for row in models
    )
    sentinel_cache_p90 = 2 * sum(
        row["cache_case_p90_episode_cost_usd"] for row in models
    )
    full_cap = math.ceil(full_p90 * (1 + CONTINGENCY_FRACTION))
    sentinel_cap = math.ceil(sentinel_p90 * (1 + CONTINGENCY_FRACTION))
    account_remaining = float(credits.get("remaining_usd") or 0.0)
    key_remaining = float(key_status.limit_remaining_usd or 0.0)
    full_wall_median = 6 * sum(
        row["projected_episode_wall_time_seconds"]["median"] for row in models
    ) + 29 * INTER_EPISODE_COOLDOWN_SECONDS
    full_wall_p90 = 6 * sum(
        row["projected_episode_wall_time_seconds"]["p90"] for row in models
    ) + 29 * INTER_EPISODE_COOLDOWN_SECONDS
    sentinel_wall_median = 2 * sum(
        row["projected_episode_wall_time_seconds"]["median"] for row in models
    ) + 9 * INTER_EPISODE_COOLDOWN_SECONDS
    sentinel_wall_p90 = 2 * sum(
        row["projected_episode_wall_time_seconds"]["p90"] for row in models
    ) + 9 * INTER_EPISODE_COOLDOWN_SECONDS
    return {
        "schema_version": "0.6-cost-plan-1",
        "status": "ready_for_explicit_freeze_decision",
        "generated_at": datetime.now(UTC).isoformat(),
        "network_actions": [
            "authenticated_GET_models_user",
            "authenticated_GET_model_endpoints",
            "authenticated_GET_key",
            "authenticated_GET_credits",
        ],
        "inference_requests_made": 0,
        "scientific_requests_made": 0,
        "heldout_requests_made": 0,
        "astra_requests_made": 0,
        "compatibility_spend_already_incurred_usd": float(
            compatibility["cumulative_reported_cost_usd"]
        ),
        "workload": {
            "v05_observed": workload,
            "v06_workload_uplift": WORKLOAD_UPLIFT,
            "uplift_basis": (
                "The v0.6 envelope raises total completion opportunity from 75k to "
                "90k tokens (1.20x) and splits three combined submissions into ten "
                "independently graded artifacts. The same 1.20x uplift is applied to "
                "both cumulative input and output workload."
            ),
            "projected_v06_tokens": {
                "median_input": input_median,
                "p90_input": input_p90,
                "median_output": output_median,
                "p90_output": output_p90,
            },
            "cache_case_fraction": CACHE_HIT_CASE,
            "cache_case_status": (
                "illustrative_only; compatibility calls observed no reusable cache "
                "hits, so no-cache values govern funding and caps"
            ),
        },
        "models": models,
        "full_matrix": {
            "episode_count": 30,
            "no_cache_median_usd": round(full_median, 2),
            "no_cache_p90_usd": round(full_p90, 2),
            "cache_case_median_usd": round(full_cache_median, 2),
            "cache_case_p90_usd": round(full_cache_p90, 2),
            "contingency_fraction": CONTINGENCY_FRACTION,
            "conservative_maximum_cap_usd": full_cap,
            "recommended_account_top_up_usd": round(
                _ceil_cents(full_cap - account_remaining), 2
            ),
            "required_key_limit_increase_usd": round(
                _ceil_cents(full_cap - key_remaining), 2
            ),
            "likely_wall_time_hours": {
                "median": round(full_wall_median / 3600, 2),
                "p90": round(full_wall_p90 / 3600, 2),
            },
        },
        "sentinel": {
            "episode_count": 10,
            "scenario_ids": execution["sentinel"]["scenario_ids"],
            "no_cache_median_usd": round(sentinel_median, 2),
            "no_cache_p90_usd": round(sentinel_p90, 2),
            "cache_case_median_usd": round(sentinel_cache_median, 2),
            "cache_case_p90_usd": round(sentinel_cache_p90, 2),
            "contingency_fraction": CONTINGENCY_FRACTION,
            "conservative_maximum_cap_usd": sentinel_cap,
            "recommended_account_top_up_usd": round(
                _ceil_cents(sentinel_cap - account_remaining), 2
            ),
            "required_key_limit_increase_usd": round(
                _ceil_cents(sentinel_cap - key_remaining), 2
            ),
            "likely_wall_time_hours": {
                "median": round(sentinel_wall_median / 3600, 2),
                "p90": round(sentinel_wall_p90 / 3600, 2),
            },
        },
        "account": {
            "total_credits_usd": credits.get("total_credits_usd"),
            "total_usage_usd": credits.get("total_usage_usd"),
            "account_remaining_usd": credits.get("remaining_usd"),
            "key_usage_usd": key_status.usage_usd,
            "key_limit_usd": key_status.limit_usd,
            "key_limit_remaining_usd": key_status.limit_remaining_usd,
        },
        "recommendation": (
            "Freeze the complete 30-cell configuration, then run the balanced "
            "10-episode sentinel. Continue without task or grader changes only if "
            "the predeclared sentinel rules pass."
        ),
        "limitations": [
            (
                "v0.6 has no scientific trajectories yet; the 1.20x workload "
                "uplift is a planning assumption."
            ),
            "Compatibility latency is a small-request proxy, not an episode benchmark.",
            (
                "The cache case is not a funding assumption because the canaries "
                "observed no reusable hits."
            ),
            "One seed cannot support a stable ranking or uncertainty claim.",
        ],
    }


def _money(value: Any) -> str:
    return f"${float(value):.2f}"


def render_report(plan: dict[str, Any]) -> str:
    lines = [
        "# UC-Bench v0.6 post-adapter cost gate",
        "",
        f"Generated: `{plan['generated_at']}`",
        "",
        "Status: **ready for an explicit freeze decision; scientific execution remains closed.**",
        "",
        "| Model | Native route | Median episode | P90 episode | 60% cache median |",
        "|---|---|---:|---:|---:|",
    ]
    for row in plan["models"]:
        lines.append(
            "| {model} | {provider} | {median} | {p90} | {cache} |".format(
                model=row["model_id"],
                provider=", ".join(row["provider_order"]),
                median=_money(row["median_episode_cost_usd"]),
                p90=_money(row["p90_episode_cost_usd"]),
                cache=_money(row["cache_case_median_episode_cost_usd"]),
            )
        )
    full = plan["full_matrix"]
    sentinel = plan["sentinel"]
    account = plan["account"]
    lines.extend(
        [
            "",
            "## Full 30-episode matrix",
            "",
            f"- Expected no-cache spend: {_money(full['no_cache_median_usd'])}.",
            f"- P90 no-cache spend: {_money(full['no_cache_p90_usd'])}.",
            f"- Conservative cap: {_money(full['conservative_maximum_cap_usd'])}.",
            (
                f"- Top-up / key-limit increase: "
                f"{_money(full['recommended_account_top_up_usd'])} / "
                f"{_money(full['required_key_limit_increase_usd'])}."
            ),
            (
                f"- Likely sequential wall time: {full['likely_wall_time_hours']['median']:.2f} "
                f"hours median, {full['likely_wall_time_hours']['p90']:.2f} hours P90."
            ),
            "",
            "## Balanced 10-episode sentinel",
            "",
            f"- Expected no-cache spend: {_money(sentinel['no_cache_median_usd'])}.",
            f"- P90 no-cache spend: {_money(sentinel['no_cache_p90_usd'])}.",
            f"- Conservative cap: {_money(sentinel['conservative_maximum_cap_usd'])}.",
            (
                f"- Top-up / key-limit increase: "
                f"{_money(sentinel['recommended_account_top_up_usd'])} / "
                f"{_money(sentinel['required_key_limit_increase_usd'])}."
            ),
            (
                f"- Likely sequential wall time: "
                f"{sentinel['likely_wall_time_hours']['median']:.2f} hours median, "
                f"{sentinel['likely_wall_time_hours']['p90']:.2f} hours P90."
            ),
            "",
            "The cache scenario is shown for sensitivity only. No-cache projections set the cap.",
            "",
            "## Current funds",
            "",
            f"- Account remaining: {_money(account['account_remaining_usd'])}.",
            f"- Key-limit remaining: {_money(account['key_limit_remaining_usd'])}.",
            (
                f"- Compatibility spend already incurred: "
                f"{_money(plan['compatibility_spend_already_incurred_usd'])}."
            ),
            "",
            "## Recommendation",
            "",
            plan["recommendation"],
            "",
            "The sentinel is not a leaderboard and cannot justify task or grader changes.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    key = load_openrouter_key(PROJECT_ROOT)
    plan = build_cost_plan(key)
    _write(OUTPUT_PATH, plan)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = REPORT_PATH.with_suffix(".md.tmp")
    temporary.write_text(render_report(plan), encoding="utf-8")
    temporary.replace(REPORT_PATH)
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

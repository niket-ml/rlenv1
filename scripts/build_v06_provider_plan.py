#!/usr/bin/env python3
"""Build the read-only v0.6 availability and cost plan; make no model calls."""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any

from uc_bench.model_runner import load_openrouter_key
from uc_bench.openrouter import fetch_credit_balance, fetch_key_status
from uc_bench.openrouter_catalog import fetch_model_endpoints, fetch_user_catalog

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PANEL_PATH = PROJECT_ROOT / "configs" / "hard_suite_v06_model_panel.json"
PROFILE_PATH = PROJECT_ROOT / "artifacts" / "diagnostics" / "hard_suite_v05_calibration_runs.json"
OUTPUT_PATH = PROJECT_ROOT / "artifacts" / "diagnostics" / "hard_suite_v06_provider_plan.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "generated" / "hard_suite_v06_provider_plan.md"


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected JSON object: {path}")
    return value


def _quantile(values: list[int], probability: float) -> float:
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def _token_profile() -> dict[str, float]:
    rows = _read(PROFILE_PATH).get("runs") or []
    inputs = [int(row["token_usage"]["input_tokens"]) for row in rows]
    outputs = [int(row["token_usage"]["output_tokens"]) for row in rows]
    if not inputs or not outputs:
        raise ValueError("v0.5 calibration has no token workload profile")
    return {
        "source": PROFILE_PATH.relative_to(PROJECT_ROOT).as_posix(),
        "episode_count": len(inputs),
        "median_input_tokens": median(inputs),
        "median_output_tokens": median(outputs),
        "p90_input_tokens": _quantile(inputs, 0.9),
        "p90_output_tokens": _quantile(outputs, 0.9),
        "maximum_input_tokens": max(inputs),
        "maximum_output_tokens": max(outputs),
    }


def _cost(prompt_tokens: float, output_tokens: float, pricing: dict[str, Any]) -> float:
    prompt = float(pricing.get("prompt") or 0.0)
    completion = float(pricing.get("completion") or 0.0)
    return prompt_tokens * prompt + output_tokens * completion


def _supports(parameters: set[str], *alternatives: str) -> bool:
    return any(item in parameters for item in alternatives)


def build_plan(key: str) -> dict[str, Any]:
    panel = _read(PANEL_PATH)
    catalog = fetch_user_catalog(key)
    key_status = fetch_key_status(key)
    credits = fetch_credit_balance(key)
    profile = _token_profile()
    models: list[dict[str, Any]] = []
    for proposed in panel["models"]:
        model_id = str(proposed["model_id"])
        model = catalog.get(model_id)
        endpoints = fetch_model_endpoints(key, model_id) if model else []
        requested_providers = set(proposed["provider_order"])
        matching_endpoints = [
            item
            for item in endpoints
            if str(item.get("provider_name") or item.get("name")) in requested_providers
        ]
        native_parameters = {
            parameter
            for endpoint in matching_endpoints
            for parameter in endpoint["supported_parameters"]
        }
        pricing = model.pricing if model else {}
        median_cost = _cost(
            profile["median_input_tokens"], profile["median_output_tokens"], pricing
        )
        p90_cost = _cost(profile["p90_input_tokens"], profile["p90_output_tokens"], pricing)
        canonical = model.canonical_slug if model else None
        models.append(
            {
                "model_id": model_id,
                "authenticated_available": model is not None,
                "expected_canonical_slug": proposed["expected_canonical_slug"],
                "observed_canonical_slug": canonical,
                "canonical_pin_matches": canonical == proposed["expected_canonical_slug"],
                "requested_provider_order": proposed["provider_order"],
                "allow_fallbacks": False,
                "matching_native_endpoint_count": len(matching_endpoints),
                "matching_native_endpoints": matching_endpoints,
                "tool_calling_supported": _supports(native_parameters, "tools"),
                "tool_choice_supported": _supports(native_parameters, "tool_choice"),
                "structured_output_supported": _supports(
                    native_parameters, "structured_outputs", "response_format"
                ),
                "reasoning_effort_supported": _supports(native_parameters, "reasoning_effort"),
                "maximum_token_parameter": (
                    "max_completion_tokens"
                    if "max_completion_tokens" in native_parameters
                    else "max_tokens"
                    if "max_tokens" in native_parameters
                    else None
                ),
                "context_length": model.context_length if model else None,
                "maximum_completion_tokens": (model.maximum_completion_tokens if model else None),
                "catalog_pricing_usd_per_token": pricing,
                "projected_no_cache_cost_per_episode_usd": {
                    "median_v05_workload": round(median_cost, 6),
                    "p90_v05_workload": round(p90_cost, 6),
                },
                "actual_serving_provider": "not_observed_until_canary",
                "resolved_reasoning_effort": "not_reported_until_canary",
                "cache_accounting": "not_observed_until_canary",
                "compatibility_status": "not_run",
            }
        )
    median_full = sum(
        6 * row["projected_no_cache_cost_per_episode_usd"]["median_v05_workload"] for row in models
    )
    p90_full = sum(
        6 * row["projected_no_cache_cost_per_episode_usd"]["p90_v05_workload"] for row in models
    )
    canary_cap = float(panel["compatibility_protocol"]["maximum_incremental_spend_usd"])
    account_remaining = float((credits or {}).get("remaining_usd") or 0.0)
    key_remaining = float(key_status.limit_remaining_usd or 0.0)
    recommended_reserve = round(max(10.0, 0.2 * p90_full), 2)
    scientific_funding_target = p90_full + recommended_reserve
    return {
        "schema_version": "0.6-provider-plan-1",
        "generated_at": datetime.now(UTC).isoformat(),
        "network_actions": [
            "authenticated_GET_models_user",
            "authenticated_GET_model_endpoints",
            "authenticated_GET_key",
            "authenticated_GET_credits",
        ],
        "inference_requests_made": 0,
        "panel_status": "proposed_unfrozen_compatibility_not_run",
        "astra_requested_or_configured": False,
        "token_workload_proxy": profile,
        "models": models,
        "compatibility_stage": {
            "maximum_incremental_spend_usd": canary_cap,
            "current_funds_sufficient": min(account_remaining, key_remaining) >= canary_cap,
            "top_up_required_now_usd": round(
                max(0.0, canary_cap - min(account_remaining, key_remaining)), 2
            ),
        },
        "scientific_stage_projection": {
            "episode_count": 6 * len(models),
            "attempts_per_cell": 1,
            "no_cache_median_workload_usd": round(median_full, 2),
            "no_cache_p90_workload_usd": round(p90_full, 2),
            "recommended_contingency_usd": recommended_reserve,
            "funding_target_after_canaries_usd": round(scientific_funding_target, 2),
            "account_top_up_to_p90_target_usd": round(
                max(0.0, scientific_funding_target - account_remaining), 2
            ),
            "key_limit_increase_to_p90_target_usd": round(
                max(
                    0.0,
                    key_status.usage_usd
                    + scientific_funding_target
                    - float(key_status.limit_usd or 0.0),
                ),
                2,
            ),
            "authorization": "not_authorized_before_compatibility_results_and_new_cap",
        },
        "account": {
            "key_usage_usd": key_status.usage_usd,
            "key_limit_usd": key_status.limit_usd,
            "key_limit_remaining_usd": key_status.limit_remaining_usd,
            "account_total_credits_usd": (credits or {}).get("total_credits_usd"),
            "account_total_usage_usd": (credits or {}).get("total_usage_usd"),
            "account_remaining_usd": (credits or {}).get("remaining_usd"),
        },
        "limitations": [
            (
                "Costs use the observed v0.5 token workload and current catalog prices; "
                "live canaries are required to measure provider-specific tool-loop "
                "overhead and caching."
            ),
            "Availability metadata does not prove end-to-end compatibility.",
            (
                "Actual provider, resolved reasoning effort, latency, retries, and cache "
                "use are observable only during the bounded canaries."
            ),
            "No scientific or ordering claim is implied by this plan.",
        ],
    }


def _money(value: Any) -> str:
    return "unknown" if value is None else f"${float(value):.2f}"


def render_markdown(plan: dict[str, Any]) -> str:
    lines = [
        "# UC-Bench v0.6 cross-provider readiness",
        "",
        f"Generated: `{plan['generated_at']}`",
        "",
        "Status: **unfrozen; no compatibility or scientific model calls have run.**",
        "",
        "## Authenticated availability",
        "",
        (
            "| Requested model | Canonical pin | Native route | Tools | Structured output "
            "| Max-token field | Median episode | P90 episode |"
        ),
        "|---|---|---|---:|---:|---|---:|---:|",
    ]
    for row in plan["models"]:
        lines.append(
            (
                "| {model_id} | {pin} | {route} | {tools} | {structured} | {token} "
                "| {median} | {p90} |"
            ).format(
                model_id=row["model_id"],
                pin=("match" if row["canonical_pin_matches"] else "MISMATCH"),
                route=", ".join(row["requested_provider_order"]),
                tools="yes" if row["tool_calling_supported"] else "no",
                structured="yes" if row["structured_output_supported"] else "no",
                token=row["maximum_token_parameter"] or "missing",
                median=_money(
                    row["projected_no_cache_cost_per_episode_usd"]["median_v05_workload"]
                ),
                p90=_money(row["projected_no_cache_cost_per_episode_usd"]["p90_v05_workload"]),
            )
        )
    account = plan["account"]
    scientific = plan["scientific_stage_projection"]
    compatibility = plan["compatibility_stage"]
    funds_status = "sufficient" if compatibility["current_funds_sufficient"] else "insufficient"
    compatibility_cap = _money(compatibility["maximum_incremental_spend_usd"])
    median_panel = _money(scientific["no_cache_median_workload_usd"])
    p90_panel = _money(scientific["no_cache_p90_workload_usd"])
    funding_target = _money(scientific["funding_target_after_canaries_usd"])
    account_top_up = _money(scientific["account_top_up_to_p90_target_usd"])
    key_increase = _money(scientific["key_limit_increase_to_p90_target_usd"])
    lines.extend(
        [
            "",
            "All routes use `allow_fallbacks: false`. A canonical-pin mismatch is a hard stop.",
            "",
            "## Budget decision",
            "",
            f"- Account remaining: {_money(account['account_remaining_usd'])}.",
            f"- Key-limit remaining: {_money(account['key_limit_remaining_usd'])}.",
            (f"- Compatibility canary cap: {compatibility_cap}; current funds are {funds_status}."),
            f"- Thirty-episode panel projection, no-cache median workload: {median_panel}.",
            f"- Thirty-episode panel projection, no-cache P90 workload: {p90_panel}.",
            (f"- Recommended post-canary funding target including contingency: {funding_target}."),
            (
                f"- Indicative account top-up to that target: {account_top_up}; "
                f"indicative key-limit increase: {key_increase}."
            ),
            "",
            (
                "Do not top up for the scientific pilot yet: the canaries should replace "
                "these proxy estimates with measured provider costs first."
            ),
            "",
            "## Freeze gate",
            "",
            (
                "The panel remains unfrozen until every exact model passes the non-scored "
                "provider canary and a new scientific cost cap is explicitly approved. "
                "Adapter failures are reliability findings, never scientific failures."
            ),
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    key = load_openrouter_key(PROJECT_ROOT)
    plan = build_plan(key)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    REPORT_PATH.write_text(render_markdown(plan), encoding="utf-8")
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

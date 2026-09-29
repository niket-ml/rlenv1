#!/usr/bin/env python3
"""Plan or execute the bounded, non-scored v0.6 provider compatibility canaries."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.model_runner import load_openrouter_key
from uc_bench.openrouter import fetch_key_status
from uc_bench.openrouter_catalog import fetch_model_endpoints, fetch_user_catalog
from uc_bench.v06_compatibility import CanaryRequest, run_provider_canary

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PANEL_PATH = PROJECT_ROOT / "configs" / "hard_suite_v06_model_panel.json"
PLAN_PATH = PROJECT_ROOT / "artifacts" / "diagnostics" / "hard_suite_v06_provider_plan.json"
OUTPUT_PATH = PROJECT_ROOT / "artifacts" / "diagnostics" / "hard_suite_v06_compatibility.json"
PLAN_OUTPUT_PATH = (
    PROJECT_ROOT / "artifacts" / "diagnostics" / "hard_suite_v06_compatibility_plan.json"
)
ATTEMPT_ROOT = PROJECT_ROOT / "artifacts" / "diagnostics" / "hard_suite_v06_compatibility_attempts"


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError(f"Expected JSON object: {path}")
    return value


def _write(value: dict[str, Any], path: Path = OUTPUT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _archive_existing_output() -> Path | None:
    if not OUTPUT_PATH.is_file():
        return None
    previous = _read(OUTPUT_PATH)
    stamp = str(previous.get("generated_at") or "unknown").replace(":", "-")
    target = ATTEMPT_ROOT / f"attempt-{stamp}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.read_bytes() == OUTPUT_PATH.read_bytes():
            return target
        raise ConfigurationError(f"Compatibility attempt archive collision: {target}")
    shutil.copy2(OUTPUT_PATH, target)
    return target


def _requests(panel: dict[str, Any], catalog: dict[str, Any], key: str) -> list[CanaryRequest]:
    requests: list[CanaryRequest] = []
    for model in panel["models"]:
        model_id = str(model["model_id"])
        observed = catalog.get(model_id)
        if observed is None:
            raise ConfigurationError(f"Model is no longer available to this key: {model_id}")
        if observed.canonical_slug != model["expected_canonical_slug"]:
            raise ConfigurationError(
                f"Canonical model changed for {model_id}: {observed.canonical_slug!r}"
            )
        endpoints = fetch_model_endpoints(key, model_id)
        provider_order = tuple(str(item) for item in model["provider_order"])
        parameters = {
            parameter
            for endpoint in endpoints
            if str(endpoint.get("provider_name") or endpoint.get("name")) in set(provider_order)
            for parameter in endpoint["supported_parameters"]
        }
        if not parameters:
            raise ConfigurationError(f"No pinned native provider endpoint remains for {model_id}")
        required = {"tools", "tool_choice", "reasoning_effort"}
        if not required <= parameters:
            raise ConfigurationError(
                f"{model_id} lost required parameters: {sorted(required - parameters)}"
            )
        if not ({"structured_outputs", "response_format"} & parameters):
            raise ConfigurationError(f"{model_id} has no structured-output interface")
        maximum_field = (
            "max_completion_tokens"
            if "max_completion_tokens" in parameters
            else "max_tokens"
            if "max_tokens" in parameters
            else None
        )
        if maximum_field is None:
            raise ConfigurationError(f"{model_id} has no supported maximum-token field")
        requests.append(
            CanaryRequest(
                model_id=model_id,
                expected_canonical_slug=str(model["expected_canonical_slug"]),
                provider_order=provider_order,
                reasoning_effort=str(model["requested_reasoning_effort"]),
                maximum_token_parameter=maximum_field,
                maximum_completion_tokens=int(
                    model.get(
                        "canary_maximum_completion_tokens_override",
                        panel["compatibility_protocol"][
                            "maximum_completion_tokens_per_request"
                        ],
                    )
                ),
                tool_choice_mode=(
                    "auto" if model["provider_family"] in {"anthropic", "moonshot"} else "specified"
                ),
            )
        )
    return requests


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--resume-failures", action="store_true")
    parser.add_argument("--maximum-incremental-cost-usd", type=float)
    args = parser.parse_args()
    panel = _read(PANEL_PATH)
    provider_plan = _read(PLAN_PATH)
    configured_cap = float(panel["compatibility_protocol"]["maximum_incremental_spend_usd"])
    if not args.execute:
        output = {
            "schema_version": "0.6-compatibility-1",
            "generated_at": datetime.now(UTC).isoformat(),
            "status": "planned_not_executed",
            "non_scored": True,
            "scientific_score": None,
            "model_count": len(panel["models"]),
            "maximum_request_count": 3 * len(panel["models"]),
            "maximum_incremental_spend_usd": configured_cap,
            "provider_plan_generated_at": provider_plan["generated_at"],
            "results": [],
            "astra_requests": 0,
        }
        _write(output, PLAN_OUTPUT_PATH)
        print(json.dumps(output, indent=2, sort_keys=True))
        return 0
    if args.maximum_incremental_cost_usd is None:
        raise ConfigurationError("Execution requires an explicit incremental cost cap")
    if abs(args.maximum_incremental_cost_usd - configured_cap) > 1e-9:
        raise ConfigurationError(
            f"Compatibility execution requires the predeclared ${configured_cap:.2f} cap"
        )
    prior: dict[str, Any] | None = None
    if args.resume_failures:
        if not OUTPUT_PATH.is_file():
            raise ConfigurationError("No compatibility result exists to resume")
        prior = _read(OUTPUT_PATH)
        if prior.get("status") == "passed":
            raise ConfigurationError("Compatibility already passed; refusing a repeat run")
    elif OUTPUT_PATH.is_file():
        raise ConfigurationError(
            "Compatibility result already exists; use --resume-failures to preserve "
            "and retry failures"
        )
    archived = _archive_existing_output() if prior else None
    key = load_openrouter_key(PROJECT_ROOT)
    catalog = fetch_user_catalog(key)
    requests = _requests(panel, catalog, key)
    prior_results = {str(row["model_id"]): row for row in (prior or {}).get("results") or []}
    pending = [
        request
        for request in requests
        if prior_results.get(request.model_id, {}).get("classification") != "compatible"
    ]
    usage_before = float(
        (prior or {}).get("key_usage_before_usd") or fetch_key_status(key).usage_usd
    )
    cumulative_reported_cost = float(
        (prior or {}).get("cumulative_reported_cost_usd")
        or sum(float(row.get("total_reported_cost_usd") or 0.0) for row in prior_results.values())
    )
    new_results: list[dict[str, Any]] = []
    stop_reason = "completed"
    for request in pending:
        usage_now = fetch_key_status(key).usage_usd
        spent_guard = max(usage_now - usage_before, cumulative_reported_cost)
        if spent_guard >= configured_cap:
            stop_reason = "cost_cap_reached_before_next_canary"
            break
        nonce = hashlib.sha256(f"uc-bench-v06-canary:{request.model_id}".encode()).hexdigest()[:16]
        result = run_provider_canary(request, key=key, nonce=nonce)
        new_results.append(result)
        cumulative_reported_cost += float(result.get("total_reported_cost_usd") or 0.0)
    usage_after = fetch_key_status(key).usage_usd
    incremental = usage_after - usage_before
    combined = {**prior_results, **{str(row["model_id"]): row for row in new_results}}
    results = [combined[request.model_id] for request in requests if request.model_id in combined]
    within_cap = max(incremental, cumulative_reported_cost) <= configured_cap
    output = {
        "schema_version": "0.6-compatibility-1",
        "generated_at": datetime.now(UTC).isoformat(),
        "status": (
            "passed"
            if len(results) == len(requests)
            and all(row["classification"] == "compatible" for row in results)
            and within_cap
            else "failed_or_incomplete"
        ),
        "stop_reason": stop_reason,
        "non_scored": True,
        "scientific_score": None,
        "maximum_incremental_spend_usd": configured_cap,
        "observed_incremental_spend_usd": round(incremental, 8),
        "cumulative_reported_cost_usd": round(cumulative_reported_cost, 8),
        "spend_guard_value_usd": round(max(incremental, cumulative_reported_cost), 8),
        "key_usage_before_usd": usage_before,
        "key_usage_after_usd": usage_after,
        "result_count": len(results),
        "new_result_count": len(new_results),
        "compatibility_attempt_count": int(
            (prior or {}).get("compatibility_attempt_count") or (1 if prior else 0)
        )
        + 1,
        "archived_prior_result": (
            archived.relative_to(PROJECT_ROOT).as_posix() if archived else None
        ),
        "results": results,
        "astra_requests": 0,
        "scientific_execution_authorized": False,
    }
    _write(output)
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if output["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

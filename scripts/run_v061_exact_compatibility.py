#!/usr/bin/env python3
"""Run the non-scientific v0.6.1 exact-parameter-envelope canary."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.model_runner import load_openrouter_key
from uc_bench.openrouter import fetch_key_status
from uc_bench.v061_provider import (
    EXACT_COMPATIBILITY_CAP_USD,
    MAXIMUM_COMPLETION_TOKENS,
    V061AuditedOpenRouterClient,
    V061ProviderAdapter,
    V061RequestLedger,
    build_v061_client,
    discover_v061_adapters,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = (
    PROJECT_ROOT
    / "artifacts/diagnostics/hard_suite_v061_exact_payload_compatibility_v2.json"
)
ATTEMPT_ROOT = (
    PROJECT_ROOT
    / "artifacts/diagnostics/hard_suite_v061_exact_payload_compatibility_v2_attempts"
)

TOOL = {
    "type": "function",
    "function": {
        "name": "record_workspace_ready",
        "description": "Record that the ordinary research workspace is ready.",
        "parameters": {
            "type": "object",
            "properties": {"status": {"type": "string", "enum": ["ready"]}},
            "required": ["status"],
            "additionalProperties": False,
        },
    },
}
PROMPT = [
    {
        "role": "system",
        "content": (
            "You are preparing an ordinary biomedical research workspace. "
            "This contains no scientific case or benchmark answer."
        ),
    },
    {
        "role": "user",
        "content": "Record that the workspace is ready using the available tool.",
    },
]


def _write(value: dict[str, Any]) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(OUTPUT_PATH)


def _slug(model_id: str) -> str:
    return "".join(char if char.isalnum() else "-" for char in model_id).strip("-")


async def _one_request(
    *, key: str, adapter: V061ProviderAdapter, ledger: V061RequestLedger
) -> None:
    client: V061AuditedOpenRouterClient = build_v061_client(
        key=key, adapter=adapter, ledger=ledger
    )
    try:
        await client.get_native_response(
            PROMPT,
            adapter.model_id,
            adapter.sampling_args(
                maximum_completion_tokens=MAXIMUM_COMPLETION_TOKENS
            ),
            [TOOL],
        )
    finally:
        await client.close()


def _result(
    adapter: V061ProviderAdapter,
    ledger: V061RequestLedger,
    route_contract: dict[str, Any],
) -> dict[str, Any]:
    row = ledger.records[-1] if ledger.records else {}
    error = row.get("error") or {}
    contract = row.get("request_contract") or {}
    response_contract = row.get("response_contract") or {}
    passed = (
        len(ledger.records) == 1
        and not error
        and not row.get("identity_violations")
        and contract.get("maximum_token_field") == "max_tokens"
        and contract.get("maximum_tokens") == MAXIMUM_COMPLETION_TOKENS
        and contract.get("parallel_tool_calls_present")
        == ("parallel_tool_calls" in adapter.supported_parameters)
        and set(contract.get("endpoint_visible_parameters") or [])
        <= set(adapter.supported_parameters)
        and contract.get("require_parameters") is True
        and contract.get("allow_fallbacks") is False
        and contract.get("provider_order") == list(adapter.provider_order)
        and contract.get("provider_only") == list(adapter.provider_order)
        and response_contract.get("tool_call_count") == 1
        and response_contract.get("finish_reason") == "tool_calls"
    )
    return {
        "model_id": adapter.model_id,
        "classification": (
            "compatible_exact_payload"
            if passed
            else str(error.get("classification") or "provider_adapter_failure")
        ),
        "route_contract": route_contract,
        "request_contract": contract,
        "response_contract": response_contract,
        "actual_provider": row.get("actual_provider"),
        "returned_model": row.get("returned_model"),
        "reported_cost_usd": ledger.cumulative_reported_cost_usd,
        "token_usage": row.get("usage") or {},
        "error": error or None,
        "scientific_content_present": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--maximum-incremental-cost-usd", type=float)
    args = parser.parse_args()
    if not args.execute:
        print(
            json.dumps(
                {
                    "mode": "planning_only",
                    "model_count": 5,
                    "request_count": 5,
                    "scientific_requests": 0,
                    "maximum_incremental_cost_usd": EXACT_COMPATIBILITY_CAP_USD,
                },
                indent=2,
            )
        )
        return 0
    if args.maximum_incremental_cost_usd != EXACT_COMPATIBILITY_CAP_USD:
        raise ConfigurationError(
            f"Exact compatibility requires the ${EXACT_COMPATIBILITY_CAP_USD:.2f} cap"
        )
    if OUTPUT_PATH.exists():
        raise ConfigurationError("v0.6.1 exact compatibility result already exists")
    if (
        PROJECT_ROOT / "artifacts/diagnostics/hard_suite_v061_calibration_runs.json"
    ).exists():
        raise ConfigurationError("v0.6.1 scientific checkpoint predates compatibility")
    key = load_openrouter_key(PROJECT_ROOT)
    adapters, _catalog, contracts = discover_v061_adapters(PROJECT_ROOT, key)
    usage_before = fetch_key_status(key).usage_usd
    results: list[dict[str, Any]] = []
    checkpoint = {
        "schema_version": "0.6.1-exact-compatibility-2",
        "status": "running",
        "started_at": datetime.now(UTC).isoformat(),
        "non_scored": True,
        "scientific_requests": 0,
        "heldout_requests": 0,
        "astra_requests": 0,
        "maximum_incremental_cost_usd": EXACT_COMPATIBILITY_CAP_USD,
        "key_usage_before_usd": usage_before,
        "results": results,
    }
    _write(checkpoint)
    for index, (model_id, adapter) in enumerate(adapters.items()):
        status = fetch_key_status(key)
        reported = sum(float(row["reported_cost_usd"]) for row in results)
        observed = max(reported, status.usage_usd - usage_before)
        if observed >= EXACT_COMPATIBILITY_CAP_USD:
            checkpoint["status"] = "stopped_cost_cap"
            break
        if index:
            time.sleep(4)
        ledger = V061RequestLedger(
            ATTEMPT_ROOT / f"{_slug(model_id)}.json", adapter
        )
        with suppress(Exception):
            asyncio.run(_one_request(key=key, adapter=adapter, ledger=ledger))
        results.append(_result(adapter, ledger, contracts[model_id]))
        checkpoint["results"] = results
        checkpoint["status"] = "running"
        checkpoint["updated_at"] = datetime.now(UTC).isoformat()
        checkpoint["response_reported_spend_usd"] = round(
            sum(float(row["reported_cost_usd"]) for row in results), 8
        )
        _write(checkpoint)
    usage_after = fetch_key_status(key).usage_usd
    checkpoint["key_usage_after_usd"] = usage_after
    checkpoint["key_usage_delta_usd"] = usage_after - usage_before
    checkpoint["response_reported_spend_usd"] = round(
        sum(float(row["reported_cost_usd"]) for row in results), 8
    )
    checkpoint["status"] = (
        "passed"
        if len(results) == len(adapters)
        and all(row["classification"] == "compatible_exact_payload" for row in results)
        and max(
            float(checkpoint["response_reported_spend_usd"]),
            float(checkpoint["key_usage_delta_usd"]),
        )
        <= EXACT_COMPATIBILITY_CAP_USD
        else "failed"
    )
    checkpoint["completed_at"] = datetime.now(UTC).isoformat()
    checkpoint["model_response_count"] = sum(
        row["classification"] == "compatible_exact_payload" for row in results
    )
    _write(checkpoint)
    print(json.dumps(checkpoint, indent=2, sort_keys=True))
    return 0 if checkpoint["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

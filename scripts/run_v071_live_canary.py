#!/usr/bin/env python3
"""Run one minimal, non-scientific request through the production client path."""

from __future__ import annotations

import argparse
import asyncio
import json
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.model_runner import _resolve_generated, _write_json, load_openrouter_key
from uc_bench.openrouter import OPENROUTER_BASE_URL, fetch_key_status
from uc_bench.v07_provider import load_v07_provider_adapters, verify_live_v07_identity
from uc_bench.v071_auth import (
    V071RequestLedger,
    build_v071_scientific_client,
    credential_locations,
    mapping_contains_credential,
    redact_exception_message,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts/diagnostics/hard_suite_v071_live_canary.json"
ATTEMPT_ROOT = ROOT / "artifacts/diagnostics/hard_suite_v071_live_canary_attempt"
LEDGER = ATTEMPT_ROOT / "request_ledger.json"
CAP_USD = 0.25
COMBINED_AUTHORIZED_MAXIMUM_USD = 45.25
MODEL_ID = "openai/gpt-5.6-sol"


async def _one_request(client: Any, adapter: Any) -> Any:
    prompt = [
        {
            "role": "system",
            "content": "This is a non-scientific authentication and tool transport check.",
        },
        {
            "role": "user",
            "content": "Call infrastructure_ready once with status 'ready'.",
        },
    ]
    tools = [
        {
            "type": "function",
            "function": {
                "name": "infrastructure_ready",
                "description": "Record that the non-scientific transport is ready.",
                "parameters": {
                    "type": "object",
                    "properties": {"status": {"type": "string", "enum": ["ready"]}},
                    "required": ["status"],
                    "additionalProperties": False,
                },
            },
        }
    ]
    sampling = adapter.sampling_args(maximum_completion_tokens=128)
    sampling["n"] = 1
    return await client.get_native_response(
        prompt,
        adapter.model_id,
        sampling,
        tools,
        state={"non_scientific_canary": True},
    )


def _write(value: dict[str, Any], key: str) -> None:
    _write_json(OUTPUT, value, secret=key)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--maximum-incremental-spend-usd", type=float)
    args = parser.parse_args()
    if not args.execute:
        print(
            json.dumps(
                {
                    "mode": "planning_only",
                    "model_id": MODEL_ID,
                    "request_count": 1,
                    "non_scientific": True,
                    "maximum_incremental_spend_usd": CAP_USD,
                },
                indent=2,
            )
        )
        return 0
    if args.maximum_incremental_spend_usd != CAP_USD:
        raise ConfigurationError("The v0.7.1 canary requires the exact $0.25 cap")
    if OUTPUT.exists() or ATTEMPT_ROOT.exists():
        raise ConfigurationError("A v0.7.1 live canary attempt already exists")
    key = load_openrouter_key(ROOT)
    adapters = load_v07_provider_adapters(ROOT)
    adapter = adapters[MODEL_ID]
    live_identity = verify_live_v07_identity(key, adapters)
    before = fetch_key_status(key)
    if (
        before.limit_remaining_usd is None
        or before.limit_remaining_usd < COMBINED_AUTHORIZED_MAXIMUM_USD
    ):
        raise ConfigurationError("OpenRouter headroom is below the authorized $45.25 maximum")
    ATTEMPT_ROOT.mkdir(parents=True)
    ledger = V071RequestLedger(LEDGER, adapter, secret=key)
    client: Any = None
    error: dict[str, Any] | None = None
    response: Any = None
    try:
        client = build_v071_scientific_client(
            key=key,
            base_url=OPENROUTER_BASE_URL,
            adapter=adapter,
            ledger=ledger,
        )
        response = asyncio.run(_one_request(client, adapter))
    except Exception as exc:
        error = {
            "type": type(exc).__name__,
            "message": redact_exception_message(exc, secret=key),
        }
    finally:
        if client is not None:
            with suppress(Exception):
                _resolve_generated(client.close())
    after = fetch_key_status(key)
    row = ledger.records[-1] if ledger.records else {}
    response_contract = row.get("response_contract") or {}
    message = None if response is None else response.choices[0].message
    calls = [] if message is None else list(message.tool_calls or [])
    tool_names = [call.function.name for call in calls]
    tool_arguments = [call.function.arguments for call in calls]
    key_delta = max(0.0, float(after.usage_usd) - float(before.usage_usd))
    reported = ledger.cumulative_reported_cost_usd
    spend_guard = max(key_delta, reported)
    prompt_contract = row.get("prompt_state_contract") or {}
    request_contract = row.get("request_contract") or {}
    result = {
        "schema_version": "0.7.1-live-production-path-canary-1",
        "completed_at": datetime.now(UTC).isoformat(),
        "status": "pending_leak_scan",
        "non_scientific": True,
        "scientific_requests": 0,
        "heldout_requests": 0,
        "astra_requests": 0,
        "requested_model": MODEL_ID,
        "returned_model": row.get("returned_model"),
        "provider_identity": row.get("actual_provider"),
        "authentication_success": bool(row) and not row.get("error"),
        "tool_call_handling": {
            "tool_call_count": len(calls),
            "tool_names": tool_names,
            "tool_arguments": tool_arguments,
            "expected_call_observed": tool_names == ["infrastructure_ready"],
        },
        "finish_reason": row.get("finish_reason"),
        "token_usage": row.get("usage") or {},
        "reported_cost_usd": round(reported, 8),
        "key_usage_before_usd": before.usage_usd,
        "key_usage_after_usd": after.usage_usd,
        "key_usage_delta_usd": key_delta,
        "spend_guard_value_usd": round(spend_guard, 8),
        "maximum_incremental_spend_usd": CAP_USD,
        "request_count": len(ledger.records),
        "request_contract": request_contract,
        "prompt_state_contract": prompt_contract,
        "route_verification": live_identity,
        "error": error,
        "exact_production_client_factory": "uc_bench.v071_auth.build_v071_scientific_client",
        "explicit_key_constructor_argument": True,
        "explicit_base_url_constructor_argument": OPENROUTER_BASE_URL,
        "case_data_used": False,
        "credential_leakage_detected": None,
        "credential_leakage_locations": [],
    }
    _write(result, key)
    locations = credential_locations(ATTEMPT_ROOT, key)
    if key.encode("utf-8") in OUTPUT.read_bytes():
        locations.append(OUTPUT.relative_to(ROOT).as_posix())
    in_memory_leak = mapping_contains_credential(result, key)
    result["credential_leakage_locations"] = sorted(set(locations))
    result["credential_leakage_detected"] = bool(locations or in_memory_leak)
    passed = (
        error is None
        and len(ledger.records) == 1
        and result["authentication_success"]
        and not row.get("identity_violations")
        and result["tool_call_handling"]["expected_call_observed"]
        and response_contract.get("tool_call_count") == 1
        and response_contract.get("finish_reason") == "tool_calls"
        and (row.get("runner_normalization") or {}).get(
            "removed_redundant_n_equals_one"
        )
        is True
        and spend_guard <= CAP_USD
        and not result["credential_leakage_detected"]
    )
    result["status"] = "passed" if passed else "failed"
    _write(result, key)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

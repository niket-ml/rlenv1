"""Capped, non-scientific compatibility canaries for open MMMVP routes."""

from __future__ import annotations

import asyncio
import inspect
import json
import math
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.mmmvp_open_freeze import read_open_mmmvp_freeze
from uc_bench.mmmvp_open_provider import (
    COMPATIBILITY_PATH,
    load_open_route_contract_adapters,
)
from uc_bench.model_runner import _write_json
from uc_bench.v06_provider import _as_dict
from uc_bench.v071_auth import (
    V071RequestLedger,
    build_v071_scientific_client,
    credential_locations,
    redact_exception_message,
)

CANARY_CAP_USD = 0.50
CANARY_MAX_TOKENS = 1200


@dataclass(slots=True)
class CompatibilityBudget:
    hard_cap_usd: float = CANARY_CAP_USD
    reported_spend_usd: float = 0.0

    def authorize(self, adapter: Any, messages: list[dict[str, Any]], tools: list[Any]) -> None:
        # One UTF-8 character per input token is deliberately conservative.
        characters = len(json.dumps({"messages": messages, "tools": tools}))
        input_tokens_upper = characters + 512
        upper = (
            input_tokens_upper * adapter.maximum_prompt_price_usd_per_million
            + CANARY_MAX_TOKENS * adapter.maximum_completion_price_usd_per_million
        ) / 1_000_000
        if self.reported_spend_usd + upper > self.hard_cap_usd + 1e-12:
            raise ConfigurationError("Compatibility hard-cap guard refused the next request")

    def observe(self, ledger: V071RequestLedger, before: float) -> None:
        increment = ledger.cumulative_reported_cost_usd - before
        if increment < -1e-12 or not math.isfinite(increment):
            raise ConfigurationError("Compatibility cost accounting is invalid")
        self.reported_spend_usd += max(0.0, increment)
        if self.reported_spend_usd > self.hard_cap_usd + 1e-9:
            raise ConfigurationError("Compatibility hard cap was exceeded")


def canary_tools() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "record_lab_handoff",
                "description": "Record a harmless handoff nonce before a client restart.",
                "parameters": {
                    "type": "object",
                    "properties": {"nonce": {"type": "string"}},
                    "required": ["nonce"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "submit_lab_handoff",
                "description": "Submit the exact resume token returned by the handoff tool.",
                "parameters": {
                    "type": "object",
                    "properties": {"resume_token": {"type": "string"}},
                    "required": ["resume_token"],
                    "additionalProperties": False,
                },
            },
        },
    ]


def _first_message(response: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = _as_dict(response)
    choices = raw.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        raise ConfigurationError("Canary response has no first choice")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise ConfigurationError("Canary response has no assistant message")
    return raw, message


def _tool_call(message: dict[str, Any], expected: str) -> tuple[dict[str, Any], dict[str, Any]]:
    calls = message.get("tool_calls") or []
    if len(calls) != 1 or not isinstance(calls[0], dict):
        raise ConfigurationError(f"Expected exactly one {expected} tool call")
    call = calls[0]
    function = call.get("function") or {}
    if function.get("name") != expected:
        raise ConfigurationError(f"Expected {expected}, received {function.get('name')}")
    raw_arguments = function.get("arguments")
    try:
        arguments = (
            json.loads(raw_arguments)
            if isinstance(raw_arguments, str)
            else dict(raw_arguments or {})
        )
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ConfigurationError("Canary tool arguments are not valid JSON") from exc
    return call, arguments


async def _close(client: Any) -> None:
    result = client.close()
    if inspect.isawaitable(result):
        await result


async def run_one_open_canary(
    project_root: Path,
    *,
    key: str,
    model_id: str,
    output_root: Path,
    budget: CompatibilityBudget,
    attempt_index: int = 0,
) -> dict[str, Any]:
    root = project_root.resolve()
    adapter = load_open_route_contract_adapters(root)[model_id]
    model_root = output_root / model_id.replace("/", "--") / f"attempt-{attempt_index}"
    model_root.mkdir(parents=True, exist_ok=False)
    ledger = V071RequestLedger(model_root / "request_ledger.json", adapter, secret=key)
    nonce = f"handoff-{abs(hash((model_id, attempt_index))) % 10_000_000:07d}"
    resume_token = f"resume::{nonce}"
    tools = canary_tools()
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                "Maintain a harmless lab-notebook handoff. Use the requested tool and "
                "do not discuss API testing or software conformance."
            ),
        },
        {"role": "user", "content": f"Call record_lab_handoff once with nonce {nonce}."},
    ]
    first_client: Any = None
    second_client: Any = None
    raw_responses: list[dict[str, Any]] = []
    try:
        budget.authorize(adapter, messages, tools)
        first_client = build_v071_scientific_client(
            key=key,
            base_url="https://openrouter.ai/api/v1",
            adapter=adapter,
            ledger=ledger,
        )
        before = ledger.cumulative_reported_cost_usd
        first_response = await first_client.get_native_response(
            messages,
            model_id,
            adapter.sampling_args(maximum_completion_tokens=CANARY_MAX_TOKENS),
            tools,
        )
        budget.observe(ledger, before)
        first_raw, first_message = _first_message(first_response)
        raw_responses.append(first_raw)
        first_call, first_arguments = _tool_call(first_message, "record_lab_handoff")
        if first_arguments.get("nonce") != nonce:
            raise ConfigurationError("First tool call did not preserve the requested nonce")
        messages.extend(
            [
                first_message,
                {
                    "role": "tool",
                    "tool_call_id": first_call["id"],
                    "content": json.dumps(
                        {"accepted": True, "resume_token": resume_token}, sort_keys=True
                    ),
                },
            ]
        )
        persisted = {
            "messages": messages,
            "completed_actions": ["record_lab_handoff"],
            "pending_action": "submit_lab_handoff",
        }
        _write_json(model_root / "restart_checkpoint.json", persisted, secret=key)
        await _close(first_client)
        first_client = None

        restored = json.loads(
            (model_root / "restart_checkpoint.json").read_text(encoding="utf-8")
        )
        if restored != persisted:
            raise ConfigurationError("Restart checkpoint did not round-trip exactly")
        messages = list(restored["messages"])
        messages.append(
            {
                "role": "user",
                "content": (
                    "Read the resume_token from the preceding tool result and call "
                    "submit_lab_handoff once with that exact value."
                ),
            }
        )
        budget.authorize(adapter, messages, tools)
        second_client = build_v071_scientific_client(
            key=key,
            base_url="https://openrouter.ai/api/v1",
            adapter=adapter,
            ledger=ledger,
        )
        before = ledger.cumulative_reported_cost_usd
        second_response = await second_client.get_native_response(
            messages,
            model_id,
            adapter.sampling_args(maximum_completion_tokens=CANARY_MAX_TOKENS),
            tools,
        )
        budget.observe(ledger, before)
        second_raw, second_message = _first_message(second_response)
        raw_responses.append(second_raw)
        second_call, second_arguments = _tool_call(second_message, "submit_lab_handoff")
        if second_arguments.get("resume_token") != resume_token:
            raise ConfigurationError("Tool-result ingestion failed across the restart")

        reasoning_fields = ("reasoning", "reasoning_content", "reasoning_details")
        first_reasoning = [name for name in reasoning_fields if first_message.get(name) is not None]
        result = {
            "model_id": model_id,
            "attempt_index": attempt_index,
            "classification": "compatible",
            "requested_model": model_id,
            "returned_models": sorted(
                {str(row["returned_model"]) for row in ledger.records if row.get("returned_model")}
            ),
            "requested_provider": adapter.provider_order[0],
            "actual_providers": sorted(
                {
                    str(row["actual_provider"])
                    for row in ledger.records
                    if row.get("actual_provider")
                }
            ),
            "fallback_disabled": True,
            "tool_calling": True,
            "tool_result_ingestion": True,
            "structured_submission": bool(second_call.get("id")),
            "restart_safe": True,
            "no_action_repeated_or_omitted": True,
            "reasoning_state_returned": bool(first_reasoning),
            "reasoning_state_fields": first_reasoning,
            "reasoning_state_preserved_when_returned": all(
                first_message.get(name) == messages[2].get(name) for name in first_reasoning
            ),
            "finish_reasons": [
                first_raw["choices"][0].get("finish_reason"),
                second_raw["choices"][0].get("finish_reason"),
            ],
            "usage_accounting": all(bool(row.get("usage")) for row in ledger.records),
            "request_count": len(ledger.records),
            "cost_usd": round(ledger.cumulative_reported_cost_usd, 8),
            "adapter": adapter.to_dict(),
            "private_state_in_request": False,
            "error": None,
        }
        _write_json(
            model_root / "provider_responses.json",
            {"responses": raw_responses},
            secret=key,
        )
        _write_json(model_root / "result.json", result, secret=key)
        if credential_locations(model_root, key):
            raise ConfigurationError("Credential appeared in canary artifacts")
        return result
    except Exception as exc:
        result = {
            "model_id": model_id,
            "attempt_index": attempt_index,
            "classification": "incompatible",
            "requested_provider": adapter.provider_order[0],
            "request_count": len(ledger.records),
            "cost_usd": round(ledger.cumulative_reported_cost_usd, 8),
            "error": {
                "type": type(exc).__name__,
                "message": redact_exception_message(exc, secret=key),
            },
            "adapter": adapter.to_dict(),
        }
        _write_json(
            model_root / "provider_responses.json",
            {"responses": raw_responses},
            secret=key,
        )
        _write_json(model_root / "result.json", result, secret=key)
        return result
    finally:
        for client in (first_client, second_client):
            if client is not None:
                with suppress(Exception):
                    await _close(client)


def run_all_open_canaries(
    project_root: Path,
    *,
    key: str,
    authorization_digest: str,
    funding_baseline: dict[str, float],
) -> dict[str, Any]:
    root = project_root.resolve()
    freeze = read_open_mmmvp_freeze(root)
    if authorization_digest != freeze["hash_set_digest"]:
        raise ConfigurationError("Compatibility authorization differs from the RC1 freeze")
    target = root / COMPATIBILITY_PATH
    if target.exists():
        raise ConfigurationError("Compatibility result already exists and is immutable")
    output_root = root / "artifacts/mmmvp_open_release/compatibility_attempts"
    output_root.mkdir(parents=True, exist_ok=False)
    budget = CompatibilityBudget()
    results = [
        asyncio.run(
            run_one_open_canary(
                root,
                key=key,
                model_id=model_id,
                output_root=output_root,
                budget=budget,
            )
        )
        for model_id in freeze["model_ids"]
    ]
    compatible = [row for row in results if row["classification"] == "compatible"]
    value = {
        "schema_version": "uc-bench-open-mmmvp-compatibility-1",
        "executed_at": datetime.now(UTC).isoformat(),
        "status": "passed" if len(compatible) >= 8 else "stopped_insufficient_compatibility",
        "scientific_freeze_digest": freeze["hash_set_digest"],
        "model_count": len(results),
        "compatible_model_count": len(compatible),
        "incompatible_model_count": len(results) - len(compatible),
        "minimum_compatible_models": 8,
        "scientific_requests": 0,
        "heldout_requests": 0,
        "astra_requests": 0,
        "hard_cap_usd": CANARY_CAP_USD,
        "cost_usd": round(budget.reported_spend_usd, 8),
        "funding_baseline": funding_baseline,
        "results": results,
    }
    _write_json(target, value, secret=key)
    if credential_locations(root / "artifacts/mmmvp_open_release", key):
        raise ConfigurationError("Credential appeared in compatibility artifacts")
    return value


__all__ = [
    "CANARY_CAP_USD",
    "CompatibilityBudget",
    "canary_tools",
    "run_all_open_canaries",
    "run_one_open_canary",
]

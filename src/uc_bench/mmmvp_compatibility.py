"""Two-request, non-scientific compatibility and restart canary for each provider."""

from __future__ import annotations

import asyncio
import inspect
import json
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.mmmvp_freeze import read_mmmvp_freeze
from uc_bench.mmmvp_provider import (
    COMPATIBILITY_PATH,
    load_route_contract_adapters,
)
from uc_bench.model_runner import _write_json
from uc_bench.v06_provider import _as_dict
from uc_bench.v071_auth import (
    V071RequestLedger,
    build_v071_scientific_client,
    credential_locations,
    redact_exception_message,
)


def _tools() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "record_lab_handoff",
                "description": "Record the harmless handoff nonce before a client restart.",
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
    arguments = function.get("arguments")
    try:
        parsed = json.loads(arguments) if isinstance(arguments, str) else dict(arguments or {})
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ConfigurationError("Canary tool arguments are not valid JSON") from exc
    return call, parsed


async def _close(client: Any) -> None:
    result = client.close()
    if inspect.isawaitable(result):
        await result


async def run_one_canary(
    project_root: Path,
    *,
    key: str,
    model_id: str,
    output_root: Path,
) -> dict[str, Any]:
    root = project_root.resolve()
    adapter = load_route_contract_adapters(root)[model_id]
    model_root = output_root / model_id.replace("/", "--")
    model_root.mkdir(parents=True, exist_ok=False)
    ledger = V071RequestLedger(model_root / "request_ledger.json", adapter, secret=key)
    nonce = f"handoff-{abs(hash(model_id)) % 10_000_000:07d}"
    resume_token = f"resume::{nonce}"
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                "You are maintaining a harmless lab notebook handoff. Use the requested "
                "tool; do not discuss API conformance or software testing."
            ),
        },
        {
            "role": "user",
            "content": f"Call record_lab_handoff once with nonce {nonce}.",
        },
    ]
    first_client: Any = None
    second_client: Any = None
    try:
        first_client = build_v071_scientific_client(
            key=key,
            base_url="https://openrouter.ai/api/v1",
            adapter=adapter,
            ledger=ledger,
        )
        first_response = await first_client.get_native_response(
            messages,
            model_id,
            adapter.sampling_args(maximum_completion_tokens=1200),
            _tools(),
        )
        first_raw, first_message = _first_message(first_response)
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
        second_client = build_v071_scientific_client(
            key=key,
            base_url="https://openrouter.ai/api/v1",
            adapter=adapter,
            ledger=ledger,
        )
        second_response = await second_client.get_native_response(
            messages,
            model_id,
            adapter.sampling_args(maximum_completion_tokens=1200),
            _tools(),
        )
        second_raw, second_message = _first_message(second_response)
        second_call, second_arguments = _tool_call(second_message, "submit_lab_handoff")
        if second_arguments.get("resume_token") != resume_token:
            raise ConfigurationError("Tool-result ingestion failed across the restart")
        reasoning_fields = ("reasoning", "reasoning_content", "reasoning_details")
        first_reasoning = [name for name in reasoning_fields if first_message.get(name) is not None]
        preserved = all(
            first_message.get(name) == messages[2].get(name) for name in first_reasoning
        )
        result = {
            "model_id": model_id,
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
            "tool_calling": True,
            "tool_result_ingestion": True,
            "submission_behaviour": second_call.get("id") is not None,
            "restart_safe": True,
            "no_action_repeated_or_omitted": True,
            "reasoning_state_returned": bool(first_reasoning),
            "reasoning_state_fields": first_reasoning,
            "reasoning_state_preserved_when_returned": preserved,
            "reasoning_state_requirement": (
                "not_applicable"
                if adapter.reasoning_mode == "not_supported"
                else "preserve_if_returned"
            ),
            "finish_reasons": [
                first_raw["choices"][0].get("finish_reason"),
                second_raw["choices"][0].get("finish_reason"),
            ],
            "usage_accounting": all(bool(row.get("usage")) for row in ledger.records),
            "request_count": len(ledger.records),
            "cost_usd": round(ledger.cumulative_reported_cost_usd, 8),
            "adapter": adapter.to_dict(),
            "error": None,
        }
        _write_json(model_root / "result.json", result, secret=key)
        if credential_locations(model_root, key):
            raise ConfigurationError("Credential appeared in canary artifacts")
        return result
    except Exception as exc:
        result = {
            "model_id": model_id,
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
        _write_json(model_root / "result.json", result, secret=key)
        return result
    finally:
        for client in (first_client, second_client):
            if client is not None:
                with suppress(Exception):
                    await _close(client)


def run_all_canaries(
    project_root: Path,
    *,
    key: str,
    authorization_digest: str,
    funding_baseline: dict[str, float],
) -> dict[str, Any]:
    root = project_root.resolve()
    freeze = read_mmmvp_freeze(root)
    if authorization_digest != freeze["hash_set_digest"]:
        raise ConfigurationError("Compatibility authorization differs from the freeze")
    target = root / COMPATIBILITY_PATH
    if target.exists():
        raise ConfigurationError("Compatibility result already exists and will not be overwritten")
    attempt_root = root / "artifacts/mmmvp/compatibility_attempts"
    attempt_root.mkdir(parents=True, exist_ok=False)
    results: list[dict[str, Any]] = []
    for model_id in freeze["model_ids"]:
        results.append(
            asyncio.run(
                run_one_canary(
                    root,
                    key=key,
                    model_id=model_id,
                    output_root=attempt_root,
                )
            )
        )
    failures = [row for row in results if row["classification"] != "compatible"]
    widespread = len(failures) >= 3
    value = {
        "schema_version": "uc-bench-mmmvp-compatibility-1",
        "executed_at": datetime.now(UTC).isoformat(),
        "status": "stopped_widespread_incompatibility" if widespread else "completed",
        "freeze_digest": freeze["hash_set_digest"],
        "model_count": len(results),
        "compatible_model_count": len(results) - len(failures),
        "incompatible_model_count": len(failures),
        "widespread_incompatibility": widespread,
        "scientific_requests": 0,
        "heldout_requests": 0,
        "astra_requests": 0,
        "cost_usd": round(sum(float(row["cost_usd"]) for row in results), 8),
        "funding_baseline": funding_baseline,
        "results": results,
    }
    _write_json(target, value, secret=key)
    if credential_locations(root / "artifacts/mmmvp", key):
        raise ConfigurationError("Credential appeared in compatibility artifacts")
    return value


__all__ = ["run_all_canaries", "run_one_canary"]

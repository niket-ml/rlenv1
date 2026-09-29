"""Non-scored cross-provider compatibility canaries for UC-Bench v0.6."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from uc_bench.openrouter import OPENROUTER_BASE_URL

CANARY_TOOL = {
    "type": "function",
    "function": {
        "name": "record_project_status",
        "description": "Record the current stage for a project.",
        "parameters": {
            "type": "object",
            "required": ["project_id", "stage"],
            "properties": {
                "project_id": {"type": "string"},
                "stage": {"type": "string"},
            },
            "additionalProperties": False,
        },
    },
}

CANARY_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "uc_bench_provider_canary",
        "strict": True,
        "schema": {
            "type": "object",
            "required": ["project_id", "recorded_stage", "state_preserved", "outcome"],
            "properties": {
                "project_id": {"type": "string"},
                "recorded_stage": {"type": "string"},
                "state_preserved": {"type": "boolean"},
                "outcome": {"type": "string"},
            },
            "additionalProperties": False,
        },
    },
}


@dataclass(frozen=True, slots=True)
class CanaryRequest:
    model_id: str
    expected_canonical_slug: str
    provider_order: tuple[str, ...]
    reasoning_effort: str
    maximum_token_parameter: str
    maximum_completion_tokens: int = 700
    tool_choice_mode: str = "specified"


def classify_transport_error(status: int | None, message: str) -> str:
    """Classify adapter failures without assigning a scientific score."""

    lowered = message.lower()
    if status in {408, 409, 429} or (status is not None and status >= 500):
        return "infrastructure_failure"
    if any(token in lowered for token in ("timeout", "connection reset", "temporarily")):
        return "infrastructure_failure"
    return "provider_adapter_failure"


def is_refusal(message: dict[str, Any]) -> bool:
    refusal = message.get("refusal")
    if isinstance(refusal, str) and refusal.strip():
        return True
    content = str(message.get("content") or "").lower()
    return any(
        marker in content
        for marker in (
            "i can't assist",
            "i cannot assist",
            "i’m unable to",
            "i am unable to",
        )
    )


def _post(payload: dict[str, Any], key: str) -> tuple[int, dict[str, Any], float]:
    request = urllib.request.Request(
        f"{OPENROUTER_BASE_URL}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "UC-Bench/0.6 non-scored compatibility canary",
        },
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            status = int(response.status)
            value = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        try:
            value = json.loads(exc.read().decode("utf-8"))
        except json.JSONDecodeError:
            value = {"error": {"message": "non-json HTTP error"}}
    elapsed = time.monotonic() - started
    return status, value if isinstance(value, dict) else {}, elapsed


def _base_payload(request: CanaryRequest) -> dict[str, Any]:
    return {
        "model": request.model_id,
        "provider": {
            "order": list(request.provider_order),
            "allow_fallbacks": False,
        },
        "reasoning": {"effort": request.reasoning_effort},
        request.maximum_token_parameter: request.maximum_completion_tokens,
    }


def _choice(response: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return {}, None
    message = choices[0].get("message")
    return (message if isinstance(message, dict) else {}), choices[0].get("finish_reason")


def _tool_call(message: dict[str, Any]) -> dict[str, Any] | None:
    calls = message.get("tool_calls")
    if not isinstance(calls, list) or len(calls) != 1 or not isinstance(calls[0], dict):
        return None
    return calls[0]


def _arguments(call: dict[str, Any]) -> dict[str, Any]:
    function = call.get("function")
    if not isinstance(function, dict):
        return {}
    raw = function.get("arguments")
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(str(raw))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _content_object(message: dict[str, Any]) -> dict[str, Any]:
    raw = message.get("content")
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(str(raw))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _usage(response: dict[str, Any]) -> dict[str, Any]:
    value = response.get("usage")
    return value if isinstance(value, dict) else {}


def run_provider_canary(
    request: CanaryRequest,
    *,
    key: str,
    nonce: str,
) -> dict[str, Any]:
    """Run three tiny requests that test the adapter, not scientific ability."""

    records: list[dict[str, Any]] = []
    first_messages = [
        {
            "role": "system",
            "content": "You help maintain a project log using the available function.",
        },
        {
            "role": "user",
            "content": (
                f"Project ID: {nonce}. Record its current stage as 'review_ready' "
                "using the function rather than a prose reply."
            ),
        },
    ]
    tool_choice: object = (
        "auto"
        if request.tool_choice_mode == "auto"
        else {"type": "function", "function": {"name": "record_project_status"}}
    )
    payload1 = {
        **_base_payload(request),
        "messages": first_messages,
        "tools": [CANARY_TOOL],
        "tool_choice": tool_choice,
    }
    status1, response1, elapsed1 = _post(payload1, key)
    message1, finish1 = _choice(response1)
    call = _tool_call(message1)
    arguments = _arguments(call or {})
    records.append(_request_record(status1, response1, elapsed1, finish1))
    if status1 != 200:
        return _failed_result(request, records, status1, response1)
    if is_refusal(message1):
        return _result(request, records, "refusal", {}, response1)
    if not call or arguments != {"project_id": nonce, "stage": "review_ready"}:
        return _result(request, records, "provider_adapter_failure", {}, response1)

    tool_result = "review_ready"
    messages2 = [
        *first_messages,
        message1,
        {
            "role": "tool",
            "tool_call_id": call.get("id"),
            "name": "record_project_status",
            "content": tool_result,
        },
        {
            "role": "user",
            "content": (
                "Return the requested project-status JSON. Use the project ID and "
                "recorded stage already visible, set state_preserved true, and set "
                "outcome to complete."
            ),
        },
    ]
    payload2 = {
        **_base_payload(request),
        "messages": messages2,
        "response_format": CANARY_RESPONSE_FORMAT,
    }
    status2, response2, elapsed2 = _post(payload2, key)
    message2, finish2 = _choice(response2)
    structured = _content_object(message2)
    records.append(_request_record(status2, response2, elapsed2, finish2))
    if status2 != 200:
        return _failed_result(request, records, status2, response2)
    if is_refusal(message2):
        return _result(request, records, "refusal", {}, response2)
    structured_ok = structured == {
        "project_id": nonce,
        "recorded_stage": tool_result,
        "state_preserved": True,
        "outcome": "complete",
    }

    compacted_state = (
        f"Project summary: project_id={nonce}; recorded_stage={tool_result}; "
        "the project-log update succeeded."
    )
    payload3 = {
        **_base_payload(request),
        "messages": [
            {"role": "system", "content": compacted_state},
            {
                "role": "user",
                "content": (
                    "Using the project summary, return the requested project-status JSON. "
                    "Set state_preserved true and outcome to complete."
                ),
            },
        ],
        "response_format": CANARY_RESPONSE_FORMAT,
    }
    status3, response3, elapsed3 = _post(payload3, key)
    message3, finish3 = _choice(response3)
    compacted = _content_object(message3)
    records.append(_request_record(status3, response3, elapsed3, finish3))
    if status3 != 200:
        return _failed_result(request, records, status3, response3)
    if is_refusal(message3):
        return _result(request, records, "refusal", {}, response3)
    compacted_ok = compacted == {
        "project_id": nonce,
        "recorded_stage": tool_result,
        "state_preserved": True,
        "outcome": "complete",
    }
    resolved_models = {str(row.get("response_model")) for row in records}
    providers = {str(row.get("provider")) for row in records}
    checks = {
        "function_tool_calling": True,
        "visible_state_across_turns": structured_ok,
        "structured_output": structured_ok and compacted_ok,
        "maximum_completion_token_semantics": all(
            int(row["usage"].get("completion_tokens") or 0) <= request.maximum_completion_tokens
            for row in records
        ),
        "compacted_state_ingestion": compacted_ok,
        "tool_result_ingestion": structured_ok,
        "stop_finish_behaviour": all(row.get("finish_reason") is not None for row in records),
        "provider_routing_identity": providers == set(request.provider_order),
        "canonical_model_identity": resolved_models
        <= {request.expected_canonical_slug, request.model_id}
        and "None" not in resolved_models,
        "cache_accounting": all(
            isinstance(row.get("usage"), dict)
            and "prompt_tokens" in row["usage"]
            and "completion_tokens" in row["usage"]
            for row in records
        ),
        "harmless_request_not_refused": True,
    }
    classification = "compatible" if all(checks.values()) else "provider_adapter_failure"
    return _result(request, records, classification, checks, response3)


def _request_record(
    status: int,
    response: dict[str, Any],
    elapsed: float,
    finish_reason: str | None,
) -> dict[str, Any]:
    message, _ = _choice(response)
    refusal = message.get("refusal")
    content = message.get("content")
    return {
        "http_status": status,
        "response_model": response.get("model"),
        "provider": response.get("provider"),
        "finish_reason": finish_reason,
        "latency_seconds": round(elapsed, 6),
        "usage": _usage(response),
        "message_diagnostics": {
            "refusal": str(refusal)[:500] if refusal else None,
            "content_prefix": str(content)[:500] if content else None,
            "tool_call_count": len(message.get("tool_calls") or []),
            "reasoning_present": bool(
                message.get("reasoning") or message.get("reasoning_details")
            ),
        },
        "retry_count": 0,
        "error": response.get("error") if status != 200 else None,
    }


def _failed_result(
    request: CanaryRequest,
    records: list[dict[str, Any]],
    status: int,
    response: dict[str, Any],
) -> dict[str, Any]:
    error = response.get("error")
    message = json.dumps(error, sort_keys=True) if error is not None else "unknown error"
    return _result(request, records, classify_transport_error(status, message), {}, response)


def _result(
    request: CanaryRequest,
    records: list[dict[str, Any]],
    classification: str,
    checks: dict[str, bool],
    response: dict[str, Any],
) -> dict[str, Any]:
    return {
        "model_id": request.model_id,
        "expected_canonical_slug": request.expected_canonical_slug,
        "requested_provider_order": list(request.provider_order),
        "requested_reasoning_effort": request.reasoning_effort,
        "resolved_reasoning_effort": response.get("reasoning_effort", "not_reported"),
        "maximum_token_parameter": request.maximum_token_parameter,
        "tool_choice_mode": request.tool_choice_mode,
        "prompt_profile": "natural_project_workflow",
        "classification": classification,
        "scientific_score": None,
        "checks": checks,
        "requests": records,
        "request_count": len(records),
        "total_latency_seconds": round(sum(float(row["latency_seconds"]) for row in records), 6),
        "total_reported_cost_usd": round(
            sum(float(row["usage"].get("cost") or 0.0) for row in records), 8
        ),
    }

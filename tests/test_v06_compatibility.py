from __future__ import annotations

import json
from unittest.mock import patch

from uc_bench.v06_compatibility import (
    CanaryRequest,
    classify_transport_error,
    is_refusal,
    run_provider_canary,
)


def _response(content: object, *, tool_call: bool = False) -> dict[str, object]:
    if tool_call:
        message = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {
                        "name": "record_project_status",
                        "arguments": json.dumps(
                            {"project_id": "abc123", "stage": "review_ready"}
                        ),
                    },
                }
            ],
        }
        finish = "tool_calls"
    else:
        message = {"role": "assistant", "content": json.dumps(content)}
        finish = "stop"
    return {
        "model": "openai/example-20260101",
        "provider": "OpenAI",
        "choices": [{"message": message, "finish_reason": finish}],
        "usage": {"prompt_tokens": 20, "completion_tokens": 10, "cost": 0.0001},
    }


def test_compatibility_canary_verifies_tool_result_and_compacted_state() -> None:
    structured = {
        "project_id": "abc123",
        "recorded_stage": "review_ready",
        "state_preserved": True,
        "outcome": "complete",
    }
    side_effect = [
        (200, _response({}, tool_call=True), 0.1),
        (200, _response(structured), 0.2),
        (200, _response(structured), 0.3),
    ]
    request = CanaryRequest(
        model_id="openai/example",
        expected_canonical_slug="openai/example-20260101",
        provider_order=("OpenAI",),
        reasoning_effort="medium",
        maximum_token_parameter="max_completion_tokens",
    )
    with patch("uc_bench.v06_compatibility._post", side_effect=side_effect):
        result = run_provider_canary(request, key="secret", nonce="abc123")
    assert result["classification"] == "compatible"
    assert result["scientific_score"] is None
    assert all(result["checks"].values())
    assert result["request_count"] == 3


def test_provider_errors_and_refusals_are_not_scientific_failures() -> None:
    assert classify_transport_error(429, "rate limited") == "infrastructure_failure"
    assert classify_transport_error(400, "tools unsupported") == "provider_adapter_failure"
    assert is_refusal({"refusal": "cannot comply"})

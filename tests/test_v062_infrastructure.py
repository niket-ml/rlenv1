from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import verifiers as vf
from datasets import Dataset
from openai.types.chat import ChatCompletion

from uc_bench.errors import ConfigurationError
from uc_bench.model_runner import _resolve_generated
from uc_bench.v061_freeze import read_v061_freeze_manifest
from uc_bench.v061_provider import V061ProviderAdapter, V061RequestLedger
from uc_bench.v062_provider import V062AuditedOpenRouterClient, build_v062_client
from uc_bench.v062_runner import V062RunConfig, run_v062_episode

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PARENT_V061_DIGEST = (
    "04e5394a729a3ac6e985b544f9d668688a04a38a727eb46a6e715f3b610d0cf4"
)


def _adapter() -> V061ProviderAdapter:
    return V061ProviderAdapter(
        model_id="vendor/model",
        expected_canonical_slug="vendor/model-pinned",
        provider_order=("Native Provider",),
        allow_fallbacks=False,
        requested_reasoning_effort="medium",
        tool_choice="auto",
        preserve_reasoning_state=True,
        maximum_prompt_price_usd_per_million=2.0,
        maximum_completion_price_usd_per_million=10.0,
        supported_parameters=("max_tokens", "reasoning", "tool_choice", "tools"),
        endpoint_contract_digest="route-contract",
    )


def _response(*, tool_call: bool) -> ChatCompletion:
    message: dict[str, Any] = {
        "role": "assistant",
        "content": None if tool_call else "done",
    }
    if tool_call:
        message.update(
            {
                "reasoning_details": [
                    {"type": "reasoning.encrypted", "data": "signed-state"}
                ],
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "record_workspace_ready",
                            "arguments": '{"status":"ready"}',
                        },
                    }
                ],
            }
        )
    return ChatCompletion.model_validate(
        {
            "id": "response-tool" if tool_call else "response-final",
            "created": 1,
            "model": "vendor/model",
            "provider": "Native Provider",
            "object": "chat.completion",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "tool_calls" if tool_call else "stop",
                    "message": message,
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
                "cost": 0.001,
            },
        }
    )


def record_workspace_ready(status: str) -> dict[str, str]:
    return {"recorded_status": status}


def test_v061_freeze_and_zero_response_failure_are_preserved() -> None:
    manifest = read_v061_freeze_manifest(PROJECT_ROOT)
    assert manifest["hash_set_digest"] == PARENT_V061_DIGEST
    checkpoint = json.loads(
        (
            PROJECT_ROOT
            / "artifacts/diagnostics/hard_suite_v061_calibration_runs.json"
        ).read_text()
    )
    assert checkpoint["response_reported_spend_usd"] == 0
    assert checkpoint["key_usage_delta_usd"] == 0
    assert len(checkpoint["runs"]) == 1
    assert checkpoint["runs"][0]["provider_request_count"] == 0


def test_v062_scientific_contract_is_still_byte_equivalent() -> None:
    parent = json.loads(
        (PROJECT_ROOT / "configs/hard_suite_v06_execution.json").read_text()
    )
    successor = json.loads(
        (PROJECT_ROOT / "configs/hard_suite_v062_execution.json").read_text()
    )
    for field in (
        "episode_budget",
        "submission_policy",
        "full_matrix",
        "sentinel",
        "checkpoint_policy",
    ):
        assert successor[field] == parent[field]


def test_full_stack_live_gate_contains_two_request_tool_loops_for_all_models() -> None:
    result = json.loads(
        (
            PROJECT_ROOT
            / "artifacts/diagnostics/hard_suite_v062_full_stack_compatibility.json"
        ).read_text()
    )
    assert result["status"] == "passed"
    assert result["model_adapter_pass_count"] == 5
    assert result["scientific_requests"] == 0
    assert result["heldout_requests"] == 0
    assert result["astra_requests"] == 0
    for row in result["results"]:
        assert row["classification"] == "compatible_full_stack"
        assert row["attempt_count"] == 1
        attempt = row["attempts"][0]
        assert attempt["request_count"] == 2
        assert attempt["redundant_n_normalized"] is True
        assert attempt["tool_call_observed"] is True
        assert attempt["tool_result_ingested"] is True
        assert attempt["normal_stop_observed"] is True
        assert all(
            "n" not in contract["endpoint_visible_parameters"]
            for contract in attempt["request_contracts"]
        )


def test_only_redundant_unit_n_is_normalized(tmp_path: Path) -> None:
    adapter = _adapter()
    ledger = V061RequestLedger(tmp_path / "ledger.json", adapter)
    captured: list[dict[str, Any]] = []

    async def fake_post(*_args: Any, body: dict[str, Any], **_kwargs: Any) -> Any:
        captured.append(body)
        return _response(tool_call=True)

    async def exercise() -> None:
        client = build_v062_client(key="not-live", adapter=adapter, ledger=ledger)
        try:
            with patch(
                "uc_bench.v061_provider.post_chat_completion_with_routed_experts_sidecar",
                new=AsyncMock(side_effect=fake_post),
            ):
                sampling = adapter.sampling_args(maximum_completion_tokens=5_000)
                sampling["n"] = 1
                await client.get_native_response(
                    [{"role": "user", "content": "local"}],
                    adapter.model_id,
                    sampling,
                    [{"type": "function", "function": {"name": "one"}}],
                )
        finally:
            await client.close()

    asyncio.run(exercise())
    assert "n" not in captured[0]
    assert ledger.records[0]["runner_normalization"] == {
        "input_n": 1,
        "removed_redundant_n_equals_one": True,
        "removed_nontransport_state_object": False,
        "semantic_rollout_count_unchanged": True,
    }

    async def reject_nonunit() -> None:
        client = V062AuditedOpenRouterClient(
            object(),
            adapter,
            V061RequestLedger(tmp_path / "reject.json", adapter),
        )
        with pytest.raises(ConfigurationError, match="redundant n=1"):
            await client.get_native_response([], adapter.model_id, {"n": 2})

    asyncio.run(reject_nonunit())


def test_literal_environment_evaluate_path_preserves_tool_result_and_reasoning(
    tmp_path: Path,
) -> None:
    adapter = _adapter()
    ledger = V061RequestLedger(tmp_path / "full-stack.json", adapter)
    captured: list[dict[str, Any]] = []

    async def fake_post(*_args: Any, body: dict[str, Any], **_kwargs: Any) -> Any:
        captured.append(body)
        has_tool_result = any(row.get("role") == "tool" for row in body["messages"])
        return _response(tool_call=not has_tool_result)

    environment = vf.ToolEnv(
        dataset=Dataset.from_list(
            [
                {
                    "prompt": [
                        {
                            "role": "user",
                            "content": "Call the tool, then finish after its result.",
                        }
                    ],
                    "answer": "",
                }
            ]
        ),
        tools=[record_workspace_ready],
        system_prompt="Harmless local integration test.",
        max_turns=3,
        timeout_seconds=30,
        score_rollouts=False,
    )
    client = build_v062_client(key="not-live", adapter=adapter, ledger=ledger)
    try:
        with patch(
            "uc_bench.v061_provider.post_chat_completion_with_routed_experts_sidecar",
            new=AsyncMock(side_effect=fake_post),
        ):
            generated = _resolve_generated(
                environment.evaluate(
                    client=client,
                    model=adapter.model_id,
                    sampling_args=adapter.sampling_args(
                        maximum_completion_tokens=5_000
                    ),
                    num_examples=1,
                    rollouts_per_example=1,
                    max_concurrent=1,
                    save_results=False,
                    independent_scoring=True,
                    max_retries=0,
                )
            )
    finally:
        _resolve_generated(client.close())
    assert not (generated.get("outputs") or [{}])[0].get("error")
    assert len(captured) == 2
    assert all("n" not in body for body in captured)
    assert all(
        row["runner_normalization"]["removed_nontransport_state_object"]
        for row in ledger.records
    )
    assert any(row.get("role") == "tool" for row in captured[1]["messages"])
    assistants = [
        row for row in captured[1]["messages"] if row.get("role") == "assistant"
    ]
    assert assistants[0]["reasoning_details"] == [
        {"type": "reasoning.encrypted", "data": "signed-state"}
    ]
    assert ledger.records[1]["prompt_state_contract"]["tool_result_message_count"] == 1
    assert (
        ledger.records[1]["prompt_state_contract"][
            "assistant_reasoning_state_message_count"
        ]
        == 1
    )


def test_v062_rejects_forbidden_models_and_unfrozen_execution() -> None:
    with pytest.raises(ConfigurationError, match="Astra"):
        V062RunConfig(
            model_id="openai/gpt-6-astra",
            run_id="forbidden",
            scenario_id="dev6_clean_progression",
            seed=6101,
        )
    with pytest.raises(ConfigurationError):
        run_v062_episode(
            PROJECT_ROOT,
            V062RunConfig(
                model_id="openai/gpt-5.6-sol",
                run_id="must-not-build",
                scenario_id="dev6_clean_progression",
                seed=6101,
            ),
            openrouter_key="not-live",
            authorization_digest="wrong",
        )
    assert not (
        PROJECT_ROOT / "build/hard_suite_v06_runs/hard62-must-not-build"
    ).exists()

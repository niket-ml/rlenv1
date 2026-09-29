from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from scripts.adjudicate_v061_exact_compatibility import adjudicate
from uc_bench.errors import ConfigurationError
from uc_bench.hard_suite_v06 import ALL_ARTIFACTS, run_reference_v06_episode
from uc_bench.v06_freeze import read_v06_freeze_manifest
from uc_bench.v06_provider import classify_execution, reliability_score
from uc_bench.v061_provider import (
    V061ProviderAdapter,
    V061RequestLedger,
    build_v061_client,
    eligible_route_contract,
    exact_request_contract,
)
from uc_bench.v061_runner import V061RunConfig, run_v061_episode

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PARENT_FREEZE_DIGEST = (
    "f96e3c725700a0f696a0ad44e7d08a0cff5a8024fb09710d88605b760078eb6e"
)


def _panel() -> dict[str, Any]:
    return json.loads(
        (PROJECT_ROOT / "configs/hard_suite_v06_model_panel.json").read_text(
            encoding="utf-8"
        )
    )


def _adapter(*, supported: tuple[str, ...] | None = None) -> V061ProviderAdapter:
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
        supported_parameters=supported
        or ("max_tokens", "reasoning", "tool_choice", "tools"),
        endpoint_contract_digest="route-contract",
    )


def _endpoint(
    provider: str = "Native Provider",
    *,
    supported: list[str] | None = None,
    prompt_price: float = 0.000001,
    completion_price: float = 0.000005,
) -> dict[str, Any]:
    return {
        "name": f"{provider}/model",
        "provider_name": provider,
        "model_name": "model",
        "context_length": 100_000,
        "max_completion_tokens": 8_000,
        "supported_parameters": supported
        or ["max_tokens", "reasoning", "tool_choice", "tools"],
        "pricing_usd_per_token": {
            "prompt": prompt_price,
            "completion": completion_price,
        },
    }


def test_parent_v06_is_preserved_byte_for_byte() -> None:
    manifest = read_v06_freeze_manifest(PROJECT_ROOT)
    assert manifest["hash_set_digest"] == PARENT_FREEZE_DIGEST


def test_v061_scientific_execution_contract_is_unchanged() -> None:
    parent = json.loads(
        (PROJECT_ROOT / "configs/hard_suite_v06_execution.json").read_text()
    )
    successor = json.loads(
        (PROJECT_ROOT / "configs/hard_suite_v061_execution.json").read_text()
    )
    for field in (
        "episode_budget",
        "submission_policy",
        "full_matrix",
        "sentinel",
        "checkpoint_policy",
    ):
        assert successor[field] == parent[field]


def test_compatibility_adjudication_preserves_auto_tool_variability() -> None:
    first = json.loads(
        (
            PROJECT_ROOT
            / "artifacts/diagnostics/hard_suite_v061_exact_payload_compatibility.json"
        ).read_text()
    )
    second = json.loads(
        (
            PROJECT_ROOT
            / "artifacts/diagnostics/hard_suite_v061_exact_payload_compatibility_v2.json"
        ).read_text()
    )
    result = adjudicate(first, second)
    rows = {row["model_id"]: row for row in result["results"]}
    kimi = rows["moonshotai/kimi-k3"]
    assert result["status"] == "passed"
    assert result["automatic_tool_selection_variability_models"] == [
        "moonshotai/kimi-k3"
    ]
    assert kimi["same_envelope_tool_call_observations"] == [True, False]
    assert kimi["automatic_tool_selection_rate"] == 0.5
    assert kimi["classification"] == "compatible_exact_payload"


def test_route_contract_uses_only_eligible_native_routes_and_intersection() -> None:
    proposed = {
        "model_id": "vendor/model",
        "provider_order": ["Native Provider"],
        "scientific_tool_choice": "auto",
        "maximum_route_price_usd_per_million": {
            "prompt": 2.0,
            "completion": 10.0,
        },
    }
    first = _endpoint(supported=[
        "max_tokens",
        "parallel_tool_calls",
        "reasoning",
        "tool_choice",
        "tools",
    ])
    second = _endpoint()
    wrong_provider = _endpoint("Fallback Provider")
    too_expensive = _endpoint(prompt_price=0.000003)
    contract = eligible_route_contract(
        proposed, [first, second, wrong_provider, too_expensive]
    )
    assert contract["eligible_endpoint_count"] == 2
    assert contract["supported_parameter_intersection"] == [
        "max_tokens",
        "reasoning",
        "tool_choice",
        "tools",
    ]


def test_route_contract_fails_closed_when_required_parameter_is_absent() -> None:
    proposed = {
        "model_id": "vendor/model",
        "provider_order": ["Native Provider"],
        "scientific_tool_choice": "auto",
        "maximum_route_price_usd_per_million": {
            "prompt": 2.0,
            "completion": 10.0,
        },
    }
    with pytest.raises(ConfigurationError, match="lost required parameters"):
        eligible_route_contract(
            proposed,
            [_endpoint(supported=["max_tokens", "reasoning", "tools"])],
        )


def test_scientific_sampling_uses_supported_parameters_only() -> None:
    adapter = _adapter()
    sampling = adapter.sampling_args(maximum_completion_tokens=5_000)
    assert sampling["max_tokens"] == 5_000
    assert "max_completion_tokens" not in sampling
    assert "parallel_tool_calls" not in sampling["extra_body"]
    assert sampling["extra_body"]["tool_choice"] == "auto"
    route = sampling["extra_body"]["provider"]
    assert route == {
        "order": ["Native Provider"],
        "only": ["Native Provider"],
        "allow_fallbacks": False,
        "require_parameters": True,
        "max_price": {"prompt": 2.0, "completion": 10.0},
    }


def test_optional_parallel_setting_is_emitted_only_when_supported() -> None:
    adapter = _adapter(
        supported=(
            "max_tokens",
            "parallel_tool_calls",
            "reasoning",
            "tool_choice",
            "tools",
        )
    )
    sampling = adapter.sampling_args(maximum_completion_tokens=5_000)
    assert sampling["extra_body"]["parallel_tool_calls"] is False


def test_literal_scientific_request_body_matches_the_audited_contract(
    tmp_path: Path,
) -> None:
    adapter = _adapter()
    ledger = V061RequestLedger(tmp_path / "ledger.json", adapter)
    response = {
        "id": "response-1",
        "model": "vendor/model",
        "provider": "Native Provider",
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {"name": "one", "arguments": "{}"},
                        }
                    ],
                },
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.001},
    }
    captured: list[dict[str, Any]] = []

    async def fake_post(*_args: Any, body: dict[str, Any], **_kwargs: Any) -> Any:
        captured.append(body)
        return response

    async def exercise() -> None:
        client = build_v061_client(key="not-a-live-key", adapter=adapter, ledger=ledger)
        try:
            with patch(
                "uc_bench.v061_provider.post_chat_completion_with_routed_experts_sidecar",
                new=AsyncMock(side_effect=fake_post),
            ):
                await client.get_native_response(
                    [{"role": "user", "content": "ordinary local canary"}],
                    adapter.model_id,
                    adapter.sampling_args(maximum_completion_tokens=5_000),
                    [
                        {"type": "function", "function": {"name": "one"}},
                        {"type": "function", "function": {"name": "two"}},
                    ],
                )
        finally:
            await client.close()

    asyncio.run(exercise())
    assert len(captured) == 1
    body = captured[0]
    assert body["max_tokens"] == 5_000
    assert "max_completion_tokens" not in body
    assert "parallel_tool_calls" not in body
    assert body["provider"]["only"] == ["Native Provider"]
    assert exact_request_contract(body) == ledger.records[0]["request_contract"]
    assert ledger.records[0]["response_contract"]["tool_call_count"] == 1
    assert ledger.records[0]["response_contract"]["finish_reason"] == "tool_calls"
    assert ledger.write_count == 2


def test_client_is_constructed_while_credential_is_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed: dict[str, str | None] = {}

    class FakeClient:
        def __init__(self, *_args: Any) -> None:
            observed["key"] = os.environ.get("OPENROUTER_API_KEY")

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(
        "uc_bench.v061_provider.V061AuditedOpenRouterClient", FakeClient
    )
    result = build_v061_client(
        key="temporary-secret",
        adapter=_adapter(),
        ledger=V061RequestLedger(tmp_path / "ledger.json", _adapter()),
    )
    assert isinstance(result, FakeClient)
    assert observed["key"] == "temporary-secret"
    assert "OPENROUTER_API_KEY" not in os.environ


def test_parameter_routing_404_is_an_adapter_failure(tmp_path: Path) -> None:
    class ParameterRouteError(RuntimeError):
        status_code = 404

    ledger = V061RequestLedger(tmp_path / "ledger.json", _adapter())
    row = ledger.record_error(
        ParameterRouteError(
            "No endpoints found that can handle requested parameters; "
            "filtered by parameters"
        ),
        latency_seconds=0.1,
    )
    assert row["error"]["classification"] == "provider_adapter_failure"
    assert (
        classify_execution(
            rollout_error=None,
            completion=[],
            submitted=False,
            request_records=ledger.records,
        )
        == "provider_adapter_failure"
    )
    assert reliability_score("provider_adapter_failure", 70) is None


def test_all_artifacts_remain_writable_and_gradable_without_method_lock_in(
    tmp_path: Path,
) -> None:
    package, environment, grade = run_reference_v06_episode(
        PROJECT_ROOT,
        "dev6_clean_progression",
        output_root=tmp_path,
    )
    assert all((package.workspace_root / path).is_file() for path in ALL_ARTIFACTS)
    assert environment.submitted is True
    assert grade.coverage_adjusted_scientific_score >= 90


def test_v061_rejects_astra_and_heldout_before_building() -> None:
    with pytest.raises(ConfigurationError, match="Astra"):
        V061RunConfig(
            model_id="openai/gpt-6-astra",
            run_id="forbidden",
            scenario_id="dev6_clean_progression",
            seed=6101,
        )
    with pytest.raises(ConfigurationError, match="held-out"):
        V061RunConfig(
            model_id="openai/gpt-5.6-sol",
            run_id="forbidden",
            scenario_id="dev6_clean_progression",
            seed=6101,
            partition="heldout",
        )


def test_v061_direct_execution_requires_its_own_freeze_authorization() -> None:
    with pytest.raises(ConfigurationError):
        run_v061_episode(
            PROJECT_ROOT,
            V061RunConfig(
                model_id="openai/gpt-5.6-sol",
                run_id="must-not-build",
                scenario_id="dev6_clean_progression",
                seed=6101,
            ),
            openrouter_key="not-a-live-key",
            authorization_digest="wrong",
        )
    assert not (
        PROJECT_ROOT / "build/hard_suite_v06_runs/hard61-must-not-build"
    ).exists()

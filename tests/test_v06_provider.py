from __future__ import annotations

import json
from pathlib import Path

import pytest

from uc_bench.errors import ConfigurationError
from uc_bench.hard_suite_v06 import ALL_ARTIFACTS, run_reference_v06_episode
from uc_bench.hard_suite_v06_runner import (
    V06RunConfig,
    _ordinary_scientific_prompt,
    run_v06_episode,
)
from uc_bench.openrouter_catalog import CatalogModel
from uc_bench.v06_provider import (
    RequestLedger,
    classify_execution,
    load_provider_adapters,
    preserve_reasoning_fields,
    reliability_score,
    validate_live_adapter_identity,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _response(model: str, provider: str, *, cost: float = 0.01) -> dict[str, object]:
    return {
        "model": model,
        "provider": provider,
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "content": None,
                    "reasoning_details": [{"type": "summary", "summary": "visible"}],
                    "tool_calls": [{"id": "call-1"}],
                },
            }
        ],
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "cost": cost,
            "prompt_tokens_details": {"cached_tokens": 40, "cache_write_tokens": 0},
            "completion_tokens_details": {"reasoning_tokens": 8},
        },
    }


def test_all_exact_adapters_build_the_same_scientific_opportunity() -> None:
    adapters = load_provider_adapters(PROJECT_ROOT)
    assert set(adapters) == {
        "openai/gpt-5.6-sol",
        "anthropic/claude-opus-5",
        "google/gemini-3.1-pro-preview",
        "moonshotai/kimi-k3",
        "openai/gpt-5.2",
    }
    for model_id, adapter in adapters.items():
        sampling = adapter.sampling_args(maximum_completion_tokens=5000)
        route = sampling["extra_body"]["provider"]
        assert route["order"] == list(adapter.provider_order)
        assert route["only"] == list(adapter.provider_order)
        assert route["allow_fallbacks"] is False
        assert route["require_parameters"] is True
        assert route["max_price"] == {
            "prompt": adapter.maximum_prompt_price_usd_per_million,
            "completion": adapter.maximum_completion_price_usd_per_million,
        }
        assert sampling["extra_body"]["reasoning"] == {"effort": "medium"}
        if model_id in {"anthropic/claude-opus-5", "moonshotai/kimi-k3"}:
            assert sampling["extra_body"]["tool_choice"] == "auto"
        else:
            assert "tool_choice" not in sampling["extra_body"]


def test_every_adapter_can_share_the_ten_artifact_state_machine(tmp_path: Path) -> None:
    adapters = load_provider_adapters(PROJECT_ROOT)
    for index, adapter in enumerate(adapters.values()):
        adapter.sampling_args(maximum_completion_tokens=5000)
        package, environment, grade = run_reference_v06_episode(
            PROJECT_ROOT,
            "dev6_clean_progression",
            output_root=tmp_path / str(index),
        )
        assert environment.submitted is True
        assert grade.reliability_inclusive_score >= 90
        assert all((package.workspace_root / path).is_file() for path in ALL_ARTIFACTS)


def test_reasoning_and_tool_state_are_preserved_without_rewriting() -> None:
    details = [{"type": "reasoning.encrypted", "data": "signed-provider-state"}]
    source = [
        {"role": "assistant", "content": None, "reasoning_details": details},
        {"role": "tool", "tool_call_id": "call-1", "content": "tool-result-47"},
    ]
    native = [
        {"role": "assistant", "content": None},
        {"role": "tool", "tool_call_id": "call-1", "content": "tool-result-47"},
    ]
    preserved = preserve_reasoning_fields(source, native)
    assert preserved[0]["reasoning_details"] == details
    assert preserved[1]["content"] == "tool-result-47"


def test_request_ledger_checkpoints_cost_route_and_cache_after_each_request(
    tmp_path: Path,
) -> None:
    adapter = load_provider_adapters(PROJECT_ROOT)["openai/gpt-5.6-sol"]
    path = tmp_path / "request_ledger.json"
    ledger = RequestLedger(path, adapter)
    assert ledger.write_count == 1
    ledger.record_response(
        _response(adapter.model_id, adapter.provider_order[0]), latency_seconds=0.2
    )
    ledger.record_response(
        _response(adapter.model_id, adapter.provider_order[0], cost=0.02),
        latency_seconds=0.3,
    )
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert ledger.write_count == 3
    assert saved["request_count"] == 2
    assert saved["cumulative_reported_cost_usd"] == 0.03
    assert saved["requests"][0]["cache"]["cached_prompt_tokens"] == 40
    assert saved["requests"][0]["retry_count"] == 0


def test_model_or_provider_change_is_a_recorded_adapter_violation(tmp_path: Path) -> None:
    adapter = load_provider_adapters(PROJECT_ROOT)["openai/gpt-5.6-sol"]
    ledger = RequestLedger(tmp_path / "ledger.json", adapter)
    row = ledger.record_response(
        _response("openai/different-model", "Different Provider"),
        latency_seconds=0.1,
    )
    assert row["identity_violations"] == [
        "returned_model_mismatch",
        "serving_provider_mismatch",
    ]
    assert (
        classify_execution(
            rollout_error=None,
            completion=[],
            submitted=False,
            request_records=ledger.records,
        )
        == "provider_adapter_failure"
    )


def test_live_catalog_pin_change_or_route_loss_fails_before_execution() -> None:
    adapters = load_provider_adapters(PROJECT_ROOT)
    catalog = {
        model_id: CatalogModel(
            model_id=model_id,
            canonical_slug=adapter.expected_canonical_slug,
            context_length=400_000,
            maximum_completion_tokens=128_000,
            supported_parameters=("reasoning", "structured_outputs", "tools"),
            pricing={},
        )
        for model_id, adapter in adapters.items()
    }
    endpoints = {
        model_id: [
            {
                "provider_name": adapter.provider_order[0],
                "supported_parameters": ["reasoning", "structured_outputs", "tools"],
            }
        ]
        for model_id, adapter in adapters.items()
    }
    result = validate_live_adapter_identity(adapters, catalog, endpoints)
    assert result["status"] == "passed"
    changed = dict(catalog)
    sol = changed["openai/gpt-5.6-sol"]
    changed["openai/gpt-5.6-sol"] = CatalogModel(
        model_id=sol.model_id,
        canonical_slug="openai/gpt-5.6-sol-different",
        context_length=sol.context_length,
        maximum_completion_tokens=sol.maximum_completion_tokens,
        supported_parameters=sol.supported_parameters,
        pricing=sol.pricing,
    )
    with pytest.raises(ConfigurationError, match="canonical model changed"):
        validate_live_adapter_identity(adapters, changed, endpoints)
    missing_route = dict(endpoints)
    missing_route["moonshotai/kimi-k3"] = []
    with pytest.raises(ConfigurationError, match="tool route disappeared"):
        validate_live_adapter_identity(adapters, catalog, missing_route)


def test_provider_failures_are_excluded_but_usable_non_submission_is_zero() -> None:
    assert reliability_score("infrastructure_failure", 70) is None
    assert reliability_score("provider_adapter_failure", 70) is None
    assert reliability_score("provider_policy_refusal", 70) is None
    assert reliability_score("agent_task_failure", 70) == 0
    assert reliability_score("agent_refusal", 70) == 0


def test_response_refusal_is_model_reliability_but_provider_block_is_excluded(
    tmp_path: Path,
) -> None:
    adapter = load_provider_adapters(PROJECT_ROOT)["openai/gpt-5.6-sol"]
    refused = _response(adapter.model_id, adapter.provider_order[0])
    refused["choices"][0]["message"]["refusal"] = "I cannot assist"
    ledger = RequestLedger(tmp_path / "response_refusal.json", adapter)
    ledger.record_response(refused, latency_seconds=0.1)
    assert classify_execution(
        rollout_error=None,
        completion=[],
        submitted=False,
        request_records=ledger.records,
    ) == "agent_refusal"
    assert reliability_score("agent_refusal", 70) == 0

    class ProviderPolicyBlock(RuntimeError):
        status_code = 403

    blocked = RequestLedger(tmp_path / "provider_block.json", adapter)
    blocked.record_error(ProviderPolicyBlock("policy block"), latency_seconds=0.1)
    assert classify_execution(
        rollout_error={"error": "blocked"},
        completion=[],
        submitted=False,
        request_records=blocked.records,
    ) == "provider_policy_refusal"
    assert reliability_score("provider_policy_refusal", 70) is None


def test_transport_failure_is_excluded_from_scientific_scoring(tmp_path: Path) -> None:
    adapter = load_provider_adapters(PROJECT_ROOT)["openai/gpt-5.6-sol"]

    class RateLimit(RuntimeError):
        status_code = 429

    ledger = RequestLedger(tmp_path / "rate_limit.json", adapter)
    ledger.record_error(RateLimit("temporary rate limit"), latency_seconds=0.1)
    classification = classify_execution(
        rollout_error={"error": "rate limit"},
        completion=[],
        submitted=False,
        request_records=ledger.records,
    )
    assert classification == "infrastructure_failure"
    assert reliability_score(classification, 70) is None


def test_usable_partial_work_with_rollout_error_still_scores_zero_reliability() -> None:
    classification = classify_execution(
        rollout_error={"type": "TimeoutError", "message": "episode time limit"},
        completion=[{"role": "assistant", "content": "partial audit"}],
        submitted=False,
        request_records=[],
    )
    assert classification == "agent_task_failure"
    assert reliability_score(classification, 72) == 0


def test_docker_failure_before_any_model_work_is_infrastructure() -> None:
    classification = classify_execution(
        rollout_error={"type": "DockerRuntimeError", "message": "image unavailable"},
        completion=[],
        submitted=False,
        request_records=[],
    )
    assert classification == "infrastructure_failure"
    assert reliability_score(classification, 0) is None


def test_context_and_wall_clock_exhaustion_are_not_exclusion_loopholes(
    tmp_path: Path,
) -> None:
    adapter = load_provider_adapters(PROJECT_ROOT)["openai/gpt-5.6-sol"]

    class OverlongPromptError(RuntimeError):
        pass

    ledger = RequestLedger(tmp_path / "overlong.json", adapter)
    ledger.record_error(OverlongPromptError("context length"), latency_seconds=0.1)
    classification = classify_execution(
        rollout_error={"type": "OverlongPromptError"},
        completion=[],
        submitted=False,
        request_records=ledger.records,
    )
    assert classification == "context_budget_exhaustion"
    assert reliability_score(classification, 60) == 0
    wall_clock = classify_execution(
        rollout_error={"type": "TimeoutError", "message": "episode time limit"},
        completion=[],
        submitted=False,
        request_records=[],
    )
    assert wall_clock == "agent_task_failure"
    assert reliability_score(wall_clock, 0) == 0


def test_runner_rejects_heldout_and_astra_before_building() -> None:
    with pytest.raises(ConfigurationError, match="held-out"):
        V06RunConfig(
            model_id="openai/gpt-5.6-sol",
            run_id="heldout",
            scenario_id="held6_clean_progression",
            seed=1,
            partition="heldout",
        )
    with pytest.raises(ConfigurationError, match="forbidden"):
        V06RunConfig(
            model_id="openai/gpt-6-astra",
            run_id="astra",
            scenario_id="dev6_clean_progression",
            seed=1,
        )


def test_direct_scientific_runner_cannot_bypass_freeze_validation(monkeypatch) -> None:
    def reject_invalid_freeze(_root: Path) -> None:
        raise ConfigurationError("v0.6 freeze manifest is absent")

    monkeypatch.setattr(
        "uc_bench.hard_suite_v06_runner.read_v06_freeze_manifest",
        reject_invalid_freeze,
    )
    with pytest.raises(ConfigurationError, match="freeze manifest"):
        run_v06_episode(
            PROJECT_ROOT,
            V06RunConfig(
                model_id="openai/gpt-5.6-sol",
                run_id="must-not-build",
                scenario_id="dev6_clean_progression",
                seed=61107,
            ),
            openrouter_key="not-used",
        )
    assert not (PROJECT_ROOT / "build/hard_suite_v06_runs/must-not-build").exists()


def test_scientific_prompt_uses_ordinary_workflow_framing() -> None:
    prompt = _ordinary_scientific_prompt(
        "Task evidence contract.",
        V06RunConfig(
            model_id="anthropic/claude-opus-5",
            run_id="prompt",
            scenario_id="dev6_clean_progression",
            seed=1,
        ),
    ).lower()
    assert "technical diligence" in prompt
    assert "sdk" not in prompt
    assert "conformance" not in prompt
    assert "duplicate model outputs" not in prompt


def test_anthropic_reasoning_minimum_is_enforced() -> None:
    adapter = load_provider_adapters(PROJECT_ROOT)["anthropic/claude-opus-5"]
    with pytest.raises(ConfigurationError, match="reasoning minimum"):
        adapter.sampling_args(maximum_completion_tokens=1024)

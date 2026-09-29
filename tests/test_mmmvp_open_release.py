from __future__ import annotations

import asyncio
import json
from pathlib import Path

from uc_bench.mmmvp_open_compatibility import CompatibilityBudget, run_one_open_canary
from uc_bench.mmmvp_open_freeze import read_open_mmmvp_freeze
from uc_bench.mmmvp_open_provider import _adapter, _normalized
from uc_bench.mmmvp_open_sentinel import _integrity_stop, _max_request_cost
from uc_bench.mmmvp_provider import MMMVPProviderAdapter, route_contract

ROOT = Path(__file__).resolve().parents[1]


def _fake_adapter() -> MMMVPProviderAdapter:
    return MMMVPProviderAdapter(
        model_id="lab/fake",
        expected_canonical_slug="lab/fake-pinned",
        provider_order=("Lab Provider",),
        allow_fallbacks=False,
        requested_reasoning_effort="medium",
        reasoning_mode="effort",
        tool_choice="auto",
        preserve_reasoning_state=True,
        maximum_prompt_price_usd_per_million=1.0,
        maximum_completion_price_usd_per_million=2.0,
        supported_parameters=("max_tokens", "reasoning", "tool_choice", "tools"),
        endpoint_contract_digest="digest",
        context_length=10_000,
        maximum_completion_tokens=5_000,
    )


def test_release_panel_is_exactly_the_frozen_older_model_panel() -> None:
    panel = json.loads((ROOT / "configs/uc_bench_mmmvp_open_model_panel.json").read_text())
    assert [row["model_id"] for row in panel["models"]] == [
        "openai/gpt-5.1",
        "anthropic/claude-opus-4.1",
        "google/gemini-3.1-pro-preview",
        "anthropic/claude-sonnet-4",
        "moonshotai/kimi-k3",
        "z-ai/glm-5.2",
        "openai/gpt-5",
        "qwen/qwen3.5-397b-a17b",
        "deepseek/deepseek-v3.2",
        "mistralai/mistral-large-2512",
    ]
    assert not set(panel["explicitly_out_of_scope"]) & {
        row["model_id"] for row in panel["models"]
    }


def test_open_panel_normalizes_without_changing_route_semantics() -> None:
    row = {
        "model_id": "lab/fake",
        "canonical_slug": "lab/fake-pinned",
        "provider": "Lab Provider",
        "reasoning_mode": "effort",
        "requested_reasoning_effort": "medium",
        "maximum_route_price_usd_per_million": {"prompt": 1.0, "completion": 2.0},
    }
    endpoint = {
        "provider_name": "Lab Provider",
        "name": "exact",
        "context_length": 10_000,
        "max_completion_tokens": 5_000,
        "supported_parameters": [
            "max_tokens",
            "reasoning",
            "reasoning_effort",
            "tools",
            "tool_choice",
        ],
        "pricing_usd_per_token": {"prompt": 1e-6, "completion": 2e-6},
    }
    contract = route_contract(_normalized(row), [endpoint])
    adapter = _adapter(row, contract)
    assert adapter.expected_canonical_slug == "lab/fake-pinned"
    assert adapter.provider_order == ("Lab Provider",)
    assert adapter.allow_fallbacks is False


def test_fake_canary_exercises_restart_and_tool_ingestion(monkeypatch, tmp_path: Path) -> None:
    adapter = _fake_adapter()

    class FakeClient:
        def __init__(self, ledger):
            self.ledger = ledger

        async def get_native_response(self, messages, model, sampling, tools):
            second = any(message.get("role") == "tool" for message in messages)
            if second:
                token = json.loads(next(m["content"] for m in messages if m["role"] == "tool"))[
                    "resume_token"
                ]
                name, arguments = "submit_lab_handoff", {"resume_token": token}
            else:
                nonce = messages[-1]["content"].rsplit(" ", 1)[-1].rstrip(".")
                name, arguments = "record_lab_handoff", {"nonce": nonce}
            response = {
                "model": "lab/fake",
                "provider": "Lab Provider",
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "reasoning": "opaque-state",
                            "tool_calls": [
                                {
                                    "id": f"call-{name}",
                                    "type": "function",
                                    "function": {
                                        "name": name,
                                        "arguments": json.dumps(arguments),
                                    },
                                }
                            ],
                        },
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10, "cost": 0.001},
            }
            self.ledger.record_response(response, latency_seconds=0.01)
            return response

        async def close(self):
            return None

    monkeypatch.setattr(
        "uc_bench.mmmvp_open_compatibility.load_open_route_contract_adapters",
        lambda root: {"lab/fake": adapter},
    )
    monkeypatch.setattr(
        "uc_bench.mmmvp_open_compatibility.build_v071_scientific_client",
        lambda **kwargs: FakeClient(kwargs["ledger"]),
    )
    result = asyncio.run(
        run_one_open_canary(
            ROOT,
            key="sk-or-v1-test-secret",
            model_id="lab/fake",
            output_root=tmp_path,
            budget=CompatibilityBudget(),
        )
    )
    assert result["classification"] == "compatible"
    assert result["restart_safe"]
    assert result["tool_result_ingestion"]
    assert result["request_count"] == 2
    assert "sk-or-v1-test-secret" not in json.dumps(result)


def test_sentinel_request_guard_uses_context_and_output_price_ceiling() -> None:
    assert _max_request_cost(_fake_adapter()) == 0.02


def test_sentinel_integrity_faults_fail_closed() -> None:
    summary = {
        "grader_consistency": {"passed": True},
        "integrity": {
            "start_state_untampered": True,
            "protected_evidence_untampered": True,
        },
        "trajectory_persistence": {"passed": True},
        "provider_requests": [],
    }
    assert _integrity_stop(summary) == []
    summary["trajectory_persistence"]["passed"] = False
    assert _integrity_stop(summary) == ["trajectory_not_restorable"]


def test_release_infrastructure_does_not_change_scientific_freeze() -> None:
    freeze = read_open_mmmvp_freeze(ROOT)
    expected = "466441682b04175432329b41adcfd735cdea66f860d66f046dfae195c91e701c"
    assert freeze["hash_set_digest"] == expected

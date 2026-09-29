from __future__ import annotations

import json
from pathlib import Path

import pytest

from uc_bench.errors import ConfigurationError
from uc_bench.mmmvp_provider import MMMVPProviderAdapter, route_contract

ROOT = Path(__file__).resolve().parents[1]


def _panel_row(model_id: str) -> dict:
    panel = json.loads((ROOT / "configs/uc_bench_mmmvp_model_panel.json").read_text())
    return next(row for row in panel["models"] if row["model_id"] == model_id)


def test_provider_panel_has_exact_requested_ten_models() -> None:
    panel = json.loads((ROOT / "configs/uc_bench_mmmvp_model_panel.json").read_text())
    assert [row["model_id"] for row in panel["models"]] == [
        "openai/gpt-5.4",
        "anthropic/claude-opus-4.8",
        "google/gemini-3.1-pro-preview",
        "anthropic/claude-sonnet-4.6",
        "moonshotai/kimi-k3",
        "z-ai/glm-5.2",
        "openai/gpt-5.2",
        "qwen/qwen3.5-397b-a17b",
        "deepseek/deepseek-v3.2",
        "mistralai/mistral-large-2512",
    ]


def test_route_contract_requires_exact_provider_tools_and_price() -> None:
    row = _panel_row("qwen/qwen3.5-397b-a17b")
    endpoint = {
        "provider_name": "Alibaba",
        "name": "Alibaba exact",
        "context_length": 262144,
        "max_completion_tokens": 65536,
        "supported_parameters": ["max_tokens", "reasoning", "tools", "tool_choice"],
        "pricing_usd_per_token": {"prompt": 3.9e-7, "completion": 2.34e-6},
    }
    contract = route_contract(row, [endpoint])
    assert contract["provider"] == "Alibaba"
    with pytest.raises(ConfigurationError):
        route_contract(row, [{**endpoint, "provider_name": "Another"}])


def test_non_reasoning_adapter_omits_reasoning_without_changing_tools() -> None:
    adapter = MMMVPProviderAdapter(
        model_id="m",
        expected_canonical_slug="m-pinned",
        provider_order=("P",),
        allow_fallbacks=False,
        requested_reasoning_effort="not_supported",
        reasoning_mode="not_supported",
        tool_choice="auto",
        preserve_reasoning_state=True,
        maximum_prompt_price_usd_per_million=1,
        maximum_completion_price_usd_per_million=2,
        supported_parameters=("max_tokens", "tools", "tool_choice"),
        endpoint_contract_digest="digest",
        context_length=10000,
        maximum_completion_tokens=5000,
    )
    sampling = adapter.sampling_args(maximum_completion_tokens=1200)
    assert "reasoning" not in sampling["extra_body"]
    assert sampling["extra_body"]["tool_choice"] == "auto"
    assert sampling["extra_body"]["provider"]["allow_fallbacks"] is False

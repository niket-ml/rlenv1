from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import verifiers as vf
from datasets import Dataset

import uc_bench.v071_runner as production_runner
from uc_bench.errors import ConfigurationError
from uc_bench.model_runner import _resolve_generated
from uc_bench.openrouter import OPENROUTER_BASE_URL
from uc_bench.v06_provider import classify_execution
from uc_bench.v07_freeze import read_v07_freeze_manifest
from uc_bench.v07_provider import load_v07_provider_adapters
from uc_bench.v071_auth import (
    V071RequestLedger,
    credential_locations,
    redact_exception_message,
)
from uc_bench.v071_freeze import FREEZE_PATH, v071_scientific_hashes
from uc_bench.v071_runner import v071_reported_scores

ROOT = Path(__file__).resolve().parents[1]
TEST_KEY = "sk-or-v1-regression-secret-123456"


class _FakeNativeClient:
    def __init__(self, **kwargs: Any) -> None:
        self.constructor_kwargs = kwargs
        self.base_url = kwargs["base_url"]
        self._http_client = kwargs["http_client"]
        self.request_count = 0

    async def post(
        self,
        path: str,
        *,
        body: dict[str, Any],
        cast_to: Any,
        options: dict[str, Any],
    ) -> httpx.Response:
        del cast_to, options
        assert path == "/chat/completions"
        assert self.constructor_kwargs["api_key"] == TEST_KEY
        self.request_count += 1
        has_tool_result = any(row.get("role") == "tool" for row in body["messages"])
        if has_tool_result:
            message: dict[str, Any] = {"role": "assistant", "content": "done"}
            finish_reason = "stop"
        else:
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_ready",
                        "type": "function",
                        "function": {
                            "name": "record_ready",
                            "arguments": '{"status":"ready"}',
                        },
                    }
                ],
            }
            finish_reason = "tool_calls"
        payload = {
            "id": f"fake-{self.request_count}",
            "object": "chat.completion",
            "created": 1,
            "model": "openai/gpt-5.6-sol",
            "provider": "OpenAI",
            "choices": [
                {
                    "index": 0,
                    "message": message,
                    "finish_reason": finish_reason,
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
                "cost": 0.0,
            },
        }
        return httpx.Response(
            200,
            content=json.dumps(payload).encode(),
            request=httpx.Request("POST", OPENROUTER_BASE_URL + path),
        )

    async def close(self) -> None:
        await self._http_client.aclose()


def _adapter() -> Any:
    return load_v07_provider_adapters(ROOT)["openai/gpt-5.6-sol"]


def test_real_constructor_receives_explicit_existing_key(tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    def factory(**kwargs: Any) -> _FakeNativeClient:
        captured.update(kwargs)
        return _FakeNativeClient(**kwargs)

    ledger = V071RequestLedger(tmp_path / "ledger.json", _adapter(), secret=TEST_KEY)
    client = production_runner.build_v071_scientific_client(
        key=TEST_KEY,
        base_url=OPENROUTER_BASE_URL,
        adapter=_adapter(),
        ledger=ledger,
        native_client_factory=factory,
    )
    assert captured["api_key"] == TEST_KEY
    _resolve_generated(client.close())


def test_real_constructor_receives_exact_openrouter_base_url(tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    def factory(**kwargs: Any) -> _FakeNativeClient:
        captured.update(kwargs)
        return _FakeNativeClient(**kwargs)

    ledger = V071RequestLedger(tmp_path / "ledger.json", _adapter(), secret=TEST_KEY)
    client = production_runner.build_v071_scientific_client(
        key=TEST_KEY,
        base_url=OPENROUTER_BASE_URL,
        adapter=_adapter(),
        ledger=ledger,
        native_client_factory=factory,
    )
    assert captured["base_url"] == "https://openrouter.ai/api/v1"
    _resolve_generated(client.close())


def test_client_construction_without_key_fails_before_transport(tmp_path: Path) -> None:
    calls = 0

    def factory(**kwargs: Any) -> _FakeNativeClient:
        nonlocal calls
        calls += 1
        return _FakeNativeClient(**kwargs)

    ledger = V071RequestLedger(tmp_path / "ledger.json", _adapter(), secret=TEST_KEY)
    with pytest.raises(ConfigurationError, match="explicit OpenRouter API key"):
        production_runner.build_v071_scientific_client(
            key="",
            base_url=OPENROUTER_BASE_URL,
            adapter=_adapter(),
            ledger=ledger,
            native_client_factory=factory,
        )
    assert calls == 0
    assert ledger.records == []


def test_production_runner_uses_exact_factory_not_compatibility_helper() -> None:
    source = inspect.getsource(production_runner.run_v071_episode)
    assert "build_v071_scientific_client(" in source
    assert "build_v062_client" not in source
    assert "ClientConfig" not in source
    assert "_temporary_environment" not in source


def test_credentials_never_appear_in_prompts_workspaces_ledgers_or_errors(
    tmp_path: Path,
) -> None:
    ledger = V071RequestLedger(tmp_path / "ledger.json", _adapter(), secret=TEST_KEY)

    class SecretError(RuntimeError):
        status_code = 401

    row = ledger.record_error(
        SecretError(f"Authorization: Bearer {TEST_KEY}"), latency_seconds=0.01
    )
    (tmp_path / "workspace" / "README.md").parent.mkdir()
    (tmp_path / "workspace" / "README.md").write_text(
        production_runner.v07_scientific_system_prompt(
            "public task",
            production_runner.V071RunConfig(
                "openai/gpt-5.6-sol", "run", "case_01", "default", 70701
            ),
        ),
        encoding="utf-8",
    )
    assert TEST_KEY not in json.dumps(row)
    assert TEST_KEY not in redact_exception_message(
        SecretError(TEST_KEY), secret=TEST_KEY
    )
    assert credential_locations(tmp_path, TEST_KEY) == []


def record_ready(status: str) -> dict[str, str]:
    """Return a harmless result for the simulated production transport turn."""

    return {"status": status}


def test_simulated_authenticated_response_completes_first_full_runner_turn(
    tmp_path: Path,
) -> None:
    adapter = _adapter()
    native_instances: list[_FakeNativeClient] = []

    def factory(**kwargs: Any) -> _FakeNativeClient:
        instance = _FakeNativeClient(**kwargs)
        native_instances.append(instance)
        return instance

    ledger = V071RequestLedger(tmp_path / "ledger.json", adapter, secret=TEST_KEY)
    client = production_runner.build_v071_scientific_client(
        key=TEST_KEY,
        base_url=OPENROUTER_BASE_URL,
        adapter=adapter,
        ledger=ledger,
        native_client_factory=factory,
    )
    environment = vf.ToolEnv(
        dataset=Dataset.from_list(
            [
                {
                    "prompt": [
                        {
                            "role": "user",
                            "content": "Call record_ready with status ready, then say done.",
                        }
                    ],
                    "answer": "",
                }
            ]
        ),
        tools=[record_ready],
        system_prompt="Non-scientific simulated runner transport test.",
        max_turns=3,
        timeout_seconds=30,
        score_rollouts=False,
        env_id="uc-bench-v071-simulated-full-turn",
    )
    generated = _resolve_generated(
        environment.evaluate(
            client=client,
            model=adapter.model_id,
            sampling_args=adapter.sampling_args(maximum_completion_tokens=512),
            num_examples=1,
            rollouts_per_example=1,
            max_concurrent=1,
            save_results=False,
            independent_scoring=True,
            max_retries=0,
        )
    )
    _resolve_generated(client.close())
    assert not (generated.get("outputs") or [{}])[0].get("error")
    assert native_instances[0].request_count == 2
    assert ledger.records[0]["response_contract"]["tool_call_count"] == 1
    assert ledger.records[1]["prompt_state_contract"]["tool_result_message_count"] == 1
    assert ledger.records[1]["finish_reason"] == "stop"


def test_simulated_401_is_authentication_infrastructure_failure(tmp_path: Path) -> None:
    ledger = V071RequestLedger(tmp_path / "ledger.json", _adapter(), secret=TEST_KEY)

    class AuthenticationFailure(RuntimeError):
        status_code = 401

    row = ledger.record_error(AuthenticationFailure("unauthorized"), latency_seconds=0.1)
    classification = classify_execution(
        rollout_error={"type": "AuthenticationFailure", "message": "unauthorized"},
        completion=[],
        submitted=False,
        request_records=ledger.records,
    )
    assert row["error"]["infrastructure_subtype"] == "authentication_failure"
    assert classification == "infrastructure_failure"


def test_authentication_failure_produces_no_scientific_or_reliability_score() -> None:
    assert v071_reported_scores(
        "infrastructure_failure", {"work_quality_score": 100.0}
    ) == (None, None)


def test_v071_scientific_hashes_are_identical_to_v07() -> None:
    parent = read_v07_freeze_manifest(ROOT)
    assert v071_scientific_hashes(ROOT) == parent["hashes"]
    assert len(parent["hashes"]) == 169


def test_v071_uses_new_freeze_checkpoint_and_run_paths() -> None:
    config = json.loads(
        (ROOT / "configs/hard_suite_v071_infrastructure.json").read_text(encoding="utf-8")
    )
    assert FREEZE_PATH.as_posix() == "artifacts/diagnostics/hard_suite_v071_freeze.json"
    assert config["freeze_path"] != "artifacts/diagnostics/hard_suite_v07_freeze.json"
    assert config["checkpoint_path"] != (
        "artifacts/diagnostics/hard_suite_v07_calibration_runs.json"
    )
    assert config["run_root"] == "build/hard_suite_v071_runs"

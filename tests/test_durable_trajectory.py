from __future__ import annotations

import asyncio
import inspect
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from verifiers.legacy.utils.tool_utils import convert_func_to_tool_def

import uc_bench.v07_environment as v07_environment_module
from uc_bench.durable_runner import DurableAuditedOpenRouterClient
from uc_bench.durable_trajectory import (
    DurableTrajectoryStore,
    durable_tool_functions,
    redact_host_record,
    restore_v08_environment,
    transcript_for_resume,
)
from uc_bench.v08_controls import build_reference_solution
from uc_bench.v08_environment import V08Environment, v08_tool_functions
from uc_bench.v08_repair_snapshot import read_v08_repair_snapshot
from uc_bench.v08_verifier import verify_v08_submission

ROOT = Path(__file__).resolve().parents[1]
TEST_KEY = "sk-or-v1-durable-regression-secret"


class _FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz: Any = None) -> _FrozenDateTime:
        fixed = cls(2026, 9, 9, 12, 0, 0, tzinfo=UTC)
        return fixed if tz is not None else fixed.replace(tzinfo=None)


class _FakeDocker:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace

    def inspect_workspace(self, relative_path: str = ".") -> str:
        return json.dumps({"relative_path": relative_path}, sort_keys=True)

    def read_file(self, relative_path: str) -> str:
        return (self.workspace / relative_path).read_text(encoding="utf-8")

    def write_file(self, relative_path: str, content: str) -> str:
        path = self.workspace / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return json.dumps({"path": relative_path, "bytes": path.stat().st_size}, sort_keys=True)

    def run_command(self, command: str) -> str:
        return json.dumps({"exit_code": 0, "stdout": command, "stderr": ""}, sort_keys=True)


class _FakeLedger:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    @property
    def cumulative_reported_cost_usd(self) -> float:
        return sum(float(row["reported_cost_usd"]) for row in self.records)


class _FakeProvider:
    """Deterministic no-network provider that emits one tool call per response."""

    def __init__(self, store: DurableTrajectoryStore, ledger: _FakeLedger) -> None:
        self.store = store
        self.ledger = ledger

    def call_tool(
        self,
        tool: Any,
        arguments: dict[str, Any],
        *,
        prompt: list[dict[str, Any]],
    ) -> tuple[Any, list[dict[str, Any]]]:
        index = len(self.ledger.records)
        call_id = f"fake-call-{index:03d}"
        response = {
            "id": f"fake-response-{index:03d}",
            "model": "openai/gpt-5.6-sol",
            "provider": "OpenAI",
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "reasoning_details": [{"type": "summary", "text": f"step {index}"}],
                        "tool_calls": [
                            {
                                "id": call_id,
                                "type": "function",
                                "function": {
                                    "name": tool.__name__,
                                    "arguments": json.dumps(arguments, sort_keys=True),
                                },
                            }
                        ],
                    },
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
                "cost": 0.0,
            },
        }
        self.ledger.records.append(
            {
                "request_index": index,
                "reported_cost_usd": 0.0,
                "returned_model": "openai/gpt-5.6-sol",
                "actual_provider": "OpenAI",
            }
        )
        self.store.record_model_response(
            prompt=prompt,
            response=response,
            ledger=self.ledger,
        )
        result = tool(**arguments)
        return result, self.store.latest()["messages"]


def _tool_map(tools: list[Any]) -> dict[str, Any]:
    return {tool.__name__: tool for tool in tools}


def _actions(
    reference: dict[str, Any], reference_workspace: Path
) -> list[tuple[str, str, dict[str, Any]]]:
    checkpoints = reference["checkpoints"]
    actions: list[tuple[str, str, dict[str, Any]]] = [
        (
            "C1",
            "save_checkpoint",
            {"checkpoint": "C1", "payload_json": json.dumps(checkpoints["C1"])},
        ),
        (
            "C2",
            "commit_validation_plan",
            {"payload_json": json.dumps(checkpoints["C2"])},
        ),
        ("reveal", "reveal_validation", {}),
    ]
    for path in sorted((reference_workspace / "work").rglob("*")):
        if path.is_file():
            relative = path.relative_to(reference_workspace).as_posix()
            actions.append(
                (
                    f"work:{relative}",
                    "write_file",
                    {"relative_path": relative, "content": path.read_text(encoding="utf-8")},
                )
            )
    actions.extend(
        [
            (
                "C3",
                "save_checkpoint",
                {"checkpoint": "C3", "payload_json": json.dumps(checkpoints["C3"])},
            ),
            (
                "C4",
                "save_checkpoint",
                {"checkpoint": "C4", "payload_json": json.dumps(checkpoints["C4"])},
            ),
            ("purchase", "purchase_resource", {"resource_id": reference["selected_resource"]}),
            (
                "C5",
                "save_checkpoint",
                {"checkpoint": "C5", "payload_json": json.dumps(checkpoints["C5"])},
            ),
            ("submit", "submit", {}),
        ]
    )
    return actions


def _run_fake_episode(
    tmp_path: Path,
    *,
    name: str,
    interrupt_after: str | None,
) -> tuple[dict[str, Any], dict[str, Any], DurableTrajectoryStore]:
    reference, reference_workspace = build_reference_solution(
        ROOT,
        "case_04",
        tmp_path / f"{name}-reference",
        alternative=False,
    )
    workspace = tmp_path / name / "workspace"
    core = V08Environment(ROOT, "case_04", workspace)
    ledger = _FakeLedger()
    store = DurableTrajectoryStore(
        tmp_path / name / "host_trajectory",
        workspace=workspace,
        core=core,
        secret=TEST_KEY,
        run_metadata={"provider": "fake", "api_key": TEST_KEY},
    )
    tools = _tool_map(durable_tool_functions(_FakeDocker(workspace), core, store, ledger))
    provider = _FakeProvider(store, ledger)
    prompt: list[dict[str, Any]] = [
        {"role": "system", "content": "unchanged scientific prompt"},
        {"role": "user", "content": "begin"},
    ]
    interrupted = False
    for label, tool_name, arguments in _actions(reference, reference_workspace):
        _, prompt = provider.call_tool(tools[tool_name], arguments, prompt=prompt)
        if label == interrupt_after and not interrupted:
            latest = store.latest()
            core = restore_v08_environment(ROOT, workspace, latest)
            store = DurableTrajectoryStore.reopen(
                tmp_path / name / "host_trajectory",
                workspace=workspace,
                core=core,
                secret=TEST_KEY,
            )
            prompt = transcript_for_resume(store.latest())
            tools = _tool_map(
                durable_tool_functions(_FakeDocker(workspace), core, store, ledger)
            )
            provider = _FakeProvider(store, ledger)
            interrupted = True
    submission = core.export_submission()
    grade = verify_v08_submission(
        ROOT,
        workspace,
        submission,
        condition_id="case_04",
    ).to_dict()
    return core.state_dict(), grade, store


@pytest.mark.parametrize("interrupt_after", ["reveal", "C4"])
def test_fake_provider_interruption_resumes_without_repeat_or_omission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    interrupt_after: str,
) -> None:
    monkeypatch.setattr(v07_environment_module, "datetime", _FrozenDateTime)
    uninterrupted_state, uninterrupted_grade, uninterrupted_store = _run_fake_episode(
        tmp_path,
        name=f"uninterrupted-{interrupt_after}",
        interrupt_after=None,
    )
    resumed_state, resumed_grade, resumed_store = _run_fake_episode(
        tmp_path,
        name=f"resumed-{interrupt_after}",
        interrupt_after=interrupt_after,
    )
    assert resumed_state == uninterrupted_state
    assert resumed_grade == uninterrupted_grade
    assert resumed_grade["complete_mission_success"] is True
    expected_events = [row["event"] for row in uninterrupted_state["event_log"]]
    assert [row["event"] for row in resumed_state["event_log"]] == expected_events
    assert uninterrupted_store.verify()["passed"] is True
    resumed_verification = resumed_store.verify()
    assert resumed_verification["passed"] is True
    assert resumed_verification["tool_action_count"] == len(
        resumed_store.latest()["tool_actions"]
    )
    assert resumed_verification["model_response_count"] == len(
        resumed_store.latest()["provider_exchanges"]
    )


def test_host_records_are_outside_workspace_atomic_and_credential_free(tmp_path: Path) -> None:
    workspace = tmp_path / "run" / "workspace"
    core = V08Environment(ROOT, "case_01", workspace)
    ledger = _FakeLedger()
    store = DurableTrajectoryStore(
        tmp_path / "run" / "host_trajectory",
        workspace=workspace,
        core=core,
        secret=TEST_KEY,
        run_metadata={"authorization": f"Bearer {TEST_KEY}", "secret": TEST_KEY},
    )
    tools = _tool_map(durable_tool_functions(_FakeDocker(workspace), core, store, ledger))
    provider = _FakeProvider(store, ledger)
    provider.call_tool(
        tools["inspect_workspace"],
        {"relative_path": "."},
        prompt=[{"role": "user", "content": f"secret should redact: {TEST_KEY}"}],
    )
    journal = sorted(store.journal_root.glob("*.json"))
    assert len(journal) == 2
    assert all(path.stat().st_mode & 0o077 == 0 for path in journal)
    assert workspace not in store.host_root.parents
    assert not (workspace / "host_trajectory").exists()
    assert TEST_KEY not in "".join(path.read_text(encoding="utf-8") for path in journal)
    assert store.verify()["credential_leak_found"] is False


def test_redaction_removes_header_and_mapping_credentials() -> None:
    value = redact_host_record(
        {
            "api_key": TEST_KEY,
            "Authorization": f"Bearer {TEST_KEY}",
            "nested": f"Authorization: Bearer {TEST_KEY}",
        },
        secret=TEST_KEY,
    )
    rendered = json.dumps(value)
    assert TEST_KEY not in rendered
    assert "Bearer sk-or-v1-" not in rendered


def test_persistence_wrapper_preserves_exact_agent_tool_contract(tmp_path: Path) -> None:
    plain_core = V08Environment(ROOT, "case_01", tmp_path / "plain")
    durable_core = V08Environment(ROOT, "case_01", tmp_path / "durable" / "workspace")
    ledger = _FakeLedger()
    store = DurableTrajectoryStore(
        tmp_path / "durable" / "host_trajectory",
        workspace=durable_core.run_root,
        core=durable_core,
        secret=TEST_KEY,
        run_metadata={},
    )
    plain = [
        convert_func_to_tool_def(tool)
        for tool in v08_tool_functions(_FakeDocker(plain_core.run_root), plain_core)
    ]
    observed = [
        convert_func_to_tool_def(tool)
        for tool in durable_tool_functions(
            _FakeDocker(durable_core.run_root), durable_core, store, ledger
        )
    ]
    assert observed == plain


def test_client_observer_forwards_identical_live_arguments_and_orders_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    forwarded: dict[str, Any] = {}
    order: list[str] = []
    response = {
        "choices": [{"message": {"role": "assistant", "content": "ok"}}]
    }

    async def fake_super(
        self: Any,
        prompt: Any,
        model: str,
        sampling_args: Any,
        tools: Any = None,
        **kwargs: Any,
    ) -> Any:
        forwarded.update(
            {
                "prompt": prompt,
                "model": model,
                "sampling_args": sampling_args,
                "tools": tools,
                "kwargs": kwargs,
            }
        )
        return response

    monkeypatch.setattr(
        "uc_bench.v062_provider.V062AuditedOpenRouterClient.get_native_response",
        fake_super,
    )

    class Store:
        def record_model_response(self, **kwargs: Any) -> None:
            assert kwargs["response"] is response
            order.append("persist")

    class Ledger:
        def enforce_cap(self) -> None:
            order.append("cap")

    client = object.__new__(DurableAuditedOpenRouterClient)
    client.store = Store()
    client.ledger = Ledger()
    prompt = [{"role": "user", "content": "same"}]
    sampling = {"max_tokens": 7}
    tools = [{"type": "function"}]
    returned = asyncio.run(
        client.get_native_response(
            prompt,
            "openai/gpt-5.6-sol",
            sampling,
            tools,
            state="discarded-by-existing-adapter",
        )
    )
    assert returned is response
    assert forwarded == {
        "prompt": prompt,
        "model": "openai/gpt-5.6-sol",
        "sampling_args": sampling,
        "tools": tools,
        "kwargs": {"state": "discarded-by-existing-adapter"},
    }
    assert order == ["persist", "cap"]


def test_snapshot_02_remains_byte_valid_after_infrastructure_addition() -> None:
    snapshot = read_v08_repair_snapshot(ROOT)
    assert snapshot["hash_set_digest"] == (
        "937bc7d08e74e7f7fd8b718761e96ca1b1989ff7a1aa5caaa9cf9ce66fbc5730"
    )
    assert snapshot["file_count"] == 228


def test_durable_runner_is_observer_only() -> None:
    source = inspect.getsource(DurableAuditedOpenRouterClient.get_native_response)
    assert "super().get_native_response" in source
    assert "record_model_response" in source
    assert "enforce_cap" in source

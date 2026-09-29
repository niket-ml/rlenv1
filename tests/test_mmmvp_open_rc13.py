from __future__ import annotations

import asyncio
import inspect
import json
from pathlib import Path
from typing import Any

import pytest
import verifiers as vf
from datasets import Dataset
from verifiers.legacy.types import AssistantMessage, ToolCall

from uc_bench.durable_trajectory import TrajectoryPersistenceError, workspace_manifest
from uc_bench.mmmvp_blind_interface import serialized_open_request
from uc_bench.mmmvp_open_controls import build_open_reference
from uc_bench.mmmvp_open_freeze import read_open_mmmvp_freeze
from uc_bench.mmmvp_open_rc11_compatibility import compatibility_identity
from uc_bench.mmmvp_open_rc12_environment import RC12OpenMMMVPEnvironment
from uc_bench.mmmvp_open_rc12_freeze import read_rc12_release_freeze
from uc_bench.mmmvp_open_rc12_trajectory import restore_rc12_environment
from uc_bench.mmmvp_open_rc13_compatibility import load_rc13_compatible_adapters
from uc_bench.mmmvp_open_rc13_cost import calculate_rc13_cost_plan
from uc_bench.mmmvp_open_rc13_runner import (
    RC13DurableAuditedOpenRouterClient,
    _rc13_paced_environment,
)
from uc_bench.mmmvp_open_rc13_trajectory import (
    RC13DurableTrajectoryStore,
    rc13_durable_tool_functions,
    rc13_tool_call_context,
    rc13_trajectory_replay_check,
)

ROOT = Path(__file__).resolve().parents[1]
TEST_KEY = "sk-or-v1-rc13-test-secret"
FIXTURE = ROOT / "artifacts/mmmvp_open_rc13/deepseek_framework_error_fixture.json"
KNOWN_TOOLS = frozenset(
    {
        "inspect_workspace",
        "read_file",
        "write_file",
        "run_command",
        "commit_validation_plan",
        "reveal_validation",
        "commit_followup_plan",
        "purchase_resource",
        "submit",
    }
)


class _Ledger:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    @property
    def cumulative_reported_cost_usd(self) -> float:
        return 0.0


class _FakeDocker:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace

    def functions(self) -> list[Any]:
        return [self.inspect_workspace, self.read_file, self.write_file, self.run_command]

    def inspect_workspace(self, relative_path: str = ".") -> str:
        if not isinstance(relative_path, str):
            raise TypeError("relative_path must be text")
        return json.dumps({"relative_path": relative_path})

    def read_file(self, relative_path: str) -> str:
        if not isinstance(relative_path, str):
            raise TypeError("relative_path must be text")
        return (self.workspace / relative_path).read_text(encoding="utf-8")

    def write_file(self, relative_path: str, content: str) -> str:
        if not isinstance(relative_path, str) or not isinstance(content, str):
            raise TypeError("relative_path and content must be text")
        path = self.workspace / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return json.dumps({"path": relative_path, "bytes": path.stat().st_size})

    def run_command(self, command: str) -> str:
        if not isinstance(command, str):
            raise TypeError("command must be text")
        return json.dumps({"exit_code": 0, "stdout": command, "stderr": ""})


def _new_store(
    tmp_path: Path, name: str
) -> tuple[RC12OpenMMMVPEnvironment, _Ledger, RC13DurableTrajectoryStore, dict[str, Any]]:
    workspace = tmp_path / name / "workspace"
    core = RC12OpenMMMVPEnvironment(ROOT, "case_02", workspace)
    core.mark_workspace_boundary_enforced(True)
    ledger = _Ledger()
    store = RC13DurableTrajectoryStore(
        tmp_path / name / "host",
        workspace=workspace,
        core=core,  # type: ignore[arg-type]
        secret=TEST_KEY,
        run_metadata={"fixture": name},
    )
    prompt = serialized_open_request()["messages"]
    return core, ledger, store, prompt


def _response(calls: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "model": "fake/model",
        "provider": "fake",
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": calls,
                },
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "cost": 0.0},
    }


def _call(call_id: str, name: str, raw_arguments: Any) -> dict[str, Any]:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": raw_arguments},
    }


def _framework_prompt(
    store: RC13DurableTrajectoryStore,
    results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    latest = store.latest()
    assistant = next(
        row for row in reversed(latest["messages"]) if row.get("role") == "assistant"
    )
    prefix = latest["messages"][: latest["messages"].index(assistant) + 1]
    return [*prefix, *results]


def _execute(
    tools: dict[str, Any], call_id: str, name: str, arguments: dict[str, Any]
) -> Any:
    with rc13_tool_call_context(call_id):
        return tools[name](**arguments)


def test_exact_deepseek_failure_is_preserved_and_recovers(tmp_path: Path) -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    source = json.loads((ROOT / fixture["source_rc12_latest_path"]).read_text())
    archived = next(
        call
        for message in source["messages"]
        if message.get("role") == "assistant"
        for call in message.get("tool_calls") or []
        if str(call.get("id")) == fixture["tool_call_id"]
    )
    assert archived["function"]["arguments"] == fixture["raw_arguments"]
    assert fixture["rc12_persisted_status"] == "pending_recoverable"

    core, ledger, store, prompt = _new_store(tmp_path, "exact")
    before_state = core.state_dict()
    before_workspace = workspace_manifest(core.run_root)
    store.record_model_response(
        prompt=prompt,
        response=_response(
            [
                _call(
                    fixture["tool_call_id"],
                    fixture["tool_name"],
                    fixture["raw_arguments"],
                )
            ]
        ),
        ledger=ledger,
    )
    next_prompt = _framework_prompt(store, [fixture["framework_result"]])
    store.reconcile_framework_tool_results(
        next_prompt, ledger=ledger, known_tool_names=KNOWN_TOOLS
    )
    store.assert_provider_request_lifecycle(next_prompt)
    latest = store.latest()
    call = latest["pending_tool_calls"][0]
    assert call["status"] == "errored"
    assert call["error_class"] == "tool_argument_parse_error"
    assert call["wrapper_entered"] is False
    assert len(latest["tool_actions"]) == 1
    assert latest["tool_actions"][0]["tool_result_content"] == fixture[
        "framework_result"
    ]["content"]
    assert core.state_dict() == before_state
    assert workspace_manifest(core.run_root) == before_workspace

    corrected_id = "deepseek-corrected-call"
    store.record_model_response(
        prompt=next_prompt,
        response=_response(
            [
                _call(
                    corrected_id,
                    "write_file",
                    json.dumps(
                        {"relative_path": "work/corrected.txt", "content": "ok"}
                    ),
                )
            ]
        ),
        ledger=ledger,
    )
    tools = {
        tool.__name__: tool
        for tool in rc13_durable_tool_functions(
            _FakeDocker(core.run_root), core, store, ledger
        )
    }
    _execute(
        tools,
        corrected_id,
        "write_file",
        {"relative_path": "work/corrected.txt", "content": "ok"},
    )
    assert (core.run_root / "work/corrected.txt").read_text() == "ok"
    replay = rc13_trajectory_replay_check(
        ROOT,
        core.run_root,
        store,
        condition_id="case_02",
        grade=None,
        stop_condition=None,
    )
    assert replay["passed"], replay["faults"]
    assert replay["framework_tool_error_count"] == 1


def test_exact_runner_environment_generates_and_captures_framework_error(
    tmp_path: Path,
) -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    core, ledger, store, prompt = _new_store(tmp_path, "exact-environment")
    wrapper_entered = False

    def should_not_run(relative_path: str, content: str) -> str:
        nonlocal wrapper_entered
        wrapper_entered = True
        raise AssertionError((relative_path, content))

    tools = rc13_durable_tool_functions(_FakeDocker(core.run_root), core, store, ledger)
    tools = [should_not_run if tool.__name__ == "write_file" else tool for tool in tools]
    environment = _rc13_paced_environment(
        vf,
        minimum_interval_seconds=0.0,
        tools=tools,
        dataset=Dataset.from_list([{"prompt": [{"role": "user", "content": "x"}]}]),
        max_turns=2,
        score_rollouts=False,
    )
    call = ToolCall(
        id=fixture["tool_call_id"],
        name="write_file",
        arguments=fixture["raw_arguments"],
    )
    assistant = AssistantMessage(tool_calls=[call])
    store.record_model_response(
        prompt=prompt,
        response=_response(
            [
                _call(
                    fixture["tool_call_id"],
                    "write_file",
                    fixture["raw_arguments"],
                )
            ]
        ),
        ledger=ledger,
    )
    messages = asyncio.run(environment.env_response([assistant], state={}))
    assert wrapper_entered is False
    result_rows = [message.model_dump(mode="json") for message in messages]
    assert result_rows == [fixture["framework_result"]]
    next_prompt = _framework_prompt(store, result_rows)
    store.reconcile_framework_tool_results(
        next_prompt, ledger=ledger, known_tool_names=KNOWN_TOOLS
    )
    store.assert_provider_request_lifecycle(next_prompt)
    assert store.latest()["pending_tool_calls"][0]["status"] == "errored"


@pytest.mark.parametrize(
    "raw",
    [
        '{"content":"unterminated}',
        '{"path":"bad\\q"}',
        '{"relative_path":"work/a",}',
        '["not", "an", "object"]',
        "42",
    ],
)
def test_framework_argument_parse_variants_are_recoverable(
    tmp_path: Path, raw: str
) -> None:
    core, ledger, store, prompt = _new_store(tmp_path, f"parse-{abs(hash(raw))}")
    call_id = "parse-call"
    store.record_model_response(
        prompt=prompt,
        response=_response([_call(call_id, "write_file", raw)]),
        ledger=ledger,
    )
    result = {"role": "tool", "tool_call_id": call_id, "content": "invalid arguments"}
    next_prompt = _framework_prompt(store, [result])
    store.reconcile_framework_tool_results(
        next_prompt, ledger=ledger, known_tool_names=KNOWN_TOOLS
    )
    store.assert_provider_request_lifecycle(next_prompt)
    latest = store.latest()
    assert latest["pending_tool_calls"][0]["status"] == "errored"
    assert latest["pending_tool_calls"][0]["error_class"] == "tool_argument_parse_error"
    assert not (core.run_root / "work/a").exists()


def test_unknown_tool_is_dispatch_error_and_unknown_result_id_fails(
    tmp_path: Path,
) -> None:
    _, ledger, store, prompt = _new_store(tmp_path, "unknown-tool")
    call_id = "unknown-call"
    store.record_model_response(
        prompt=prompt,
        response=_response([_call(call_id, "not_a_tool", "{}")]),
        ledger=ledger,
    )
    result = {"role": "tool", "tool_call_id": call_id, "content": "unknown tool"}
    next_prompt = _framework_prompt(store, [result])
    store.reconcile_framework_tool_results(
        next_prompt, ledger=ledger, known_tool_names=KNOWN_TOOLS
    )
    assert store.latest()["pending_tool_calls"][0]["error_class"] == "tool_dispatch_error"

    _, ledger2, store2, prompt2 = _new_store(tmp_path, "unknown-result")
    store2.record_model_response(
        prompt=prompt2,
        response=_response([_call("known-call", "write_file", "{")]),
        ledger=ledger2,
    )
    bad = _framework_prompt(
        store2,
        [{"role": "tool", "tool_call_id": "different-call", "content": "bad"}],
    )
    with pytest.raises(TrajectoryPersistenceError, match="matched 0 provider calls"):
        store2.reconcile_framework_tool_results(
            bad, ledger=ledger2, known_tool_names=KNOWN_TOOLS
        )


def test_duplicate_call_and_result_ids_fail_closed(tmp_path: Path) -> None:
    _, ledger, store, prompt = _new_store(tmp_path, "duplicate-call")
    duplicate = _call("same-id", "write_file", "{")
    with pytest.raises(TrajectoryPersistenceError, match="Duplicate provider"):
        store.record_model_response(
            prompt=prompt,
            response=_response([duplicate, duplicate]),
            ledger=ledger,
        )
    assert not store.latest_path.exists()

    _, ledger2, store2, prompt2 = _new_store(tmp_path, "duplicate-result")
    store2.record_model_response(
        prompt=prompt2,
        response=_response([_call("call-1", "write_file", "{")]),
        ledger=ledger2,
    )
    result = {"role": "tool", "tool_call_id": "call-1", "content": "bad"}
    next_prompt = _framework_prompt(store2, [result, result])
    with pytest.raises(TrajectoryPersistenceError, match="Duplicate tool-result"):
        store2.reconcile_framework_tool_results(
            next_prompt, ledger=ledger2, known_tool_names=KNOWN_TOOLS
        )


def test_parallel_mixture_matches_by_call_id_not_tool_name(tmp_path: Path) -> None:
    core, ledger, store, prompt = _new_store(tmp_path, "parallel")
    malformed_id = "parallel-malformed"
    valid_id = "parallel-valid"
    store.record_model_response(
        prompt=prompt,
        response=_response(
            [
                _call(malformed_id, "write_file", "{"),
                _call(
                    valid_id,
                    "write_file",
                    json.dumps({"relative_path": "work/valid.txt", "content": "valid"}),
                ),
            ]
        ),
        ledger=ledger,
    )
    tools = {
        tool.__name__: tool
        for tool in rc13_durable_tool_functions(
            _FakeDocker(core.run_root), core, store, ledger
        )
    }
    valid_content = _execute(
        tools,
        valid_id,
        "write_file",
        {"relative_path": "work/valid.txt", "content": "valid"},
    )
    assistant = next(
        row for row in reversed(store.latest()["messages"]) if row.get("role") == "assistant"
    )
    prefix = store.latest()["messages"][: store.latest()["messages"].index(assistant) + 1]
    next_prompt = [
        *prefix,
        {"role": "tool", "tool_call_id": malformed_id, "content": "invalid JSON"},
        {"role": "tool", "tool_call_id": valid_id, "content": valid_content},
    ]
    store.reconcile_framework_tool_results(
        next_prompt, ledger=ledger, known_tool_names=KNOWN_TOOLS
    )
    store.assert_provider_request_lifecycle(next_prompt)
    calls = {
        call["tool_call_id"]: call for call in store.latest()["pending_tool_calls"]
    }
    assert calls[malformed_id]["status"] == "errored"
    assert calls[valid_id]["status"] == "executed"
    assert (core.run_root / "work/valid.txt").read_text() == "valid"
    assert len(store.latest()["tool_actions"]) == 2


@pytest.mark.parametrize(
    ("arguments", "match"),
    [
        ({"relative_path": "work/missing-content.txt"}, "required positional"),
        ({"relative_path": 7, "content": "bad"}, "must be text"),
    ],
)
def test_missing_and_wrong_typed_arguments_use_wrapper_error_path(
    tmp_path: Path, arguments: dict[str, Any], match: str
) -> None:
    core, ledger, store, prompt = _new_store(tmp_path, f"wrapper-{match}")
    call_id = "wrapper-call"
    store.record_model_response(
        prompt=prompt,
        response=_response(
            [_call(call_id, "write_file", json.dumps(arguments))]
        ),
        ledger=ledger,
    )
    tools = {
        tool.__name__: tool
        for tool in rc13_durable_tool_functions(
            _FakeDocker(core.run_root), core, store, ledger
        )
    }
    with pytest.raises((TypeError, ValueError), match=match):
        _execute(tools, call_id, "write_file", arguments)
    action = store.latest()["tool_actions"][0]
    assert action["error_class"] == "tool_wrapper_error"
    assert action["wrapper_entered"] is True
    assert store.latest()["pending_tool_calls"][0]["status"] == "errored"


@pytest.mark.parametrize("phase", ["revealed", "purchased"])
def test_framework_failure_after_irreversible_actions_changes_no_state(
    tmp_path: Path, phase: str
) -> None:
    core, ledger, store, prompt = _new_store(tmp_path, f"phase-{phase}")
    reference, _ = build_open_reference(
        ROOT, "case_02", tmp_path / f"reference-{phase}", alternative=False
    )
    assert core.commit_validation_plan(json.dumps(reference["validation_plan"]))[
        "accepted"
    ]
    core.reveal_validation()
    if phase == "purchased":
        assert core.commit_followup_plan(json.dumps(reference["followup_plan"]))[
            "accepted"
        ]
        core.purchase_resource(reference["followup_plan"]["chosen_resource"])
    before_state = core.state_dict()
    before_workspace = workspace_manifest(core.run_root)
    call_id = f"{phase}-bad-call"
    store.record_model_response(
        prompt=prompt,
        response=_response([_call(call_id, "write_file", "{")]),
        ledger=ledger,
    )
    result = {"role": "tool", "tool_call_id": call_id, "content": "bad JSON"}
    next_prompt = _framework_prompt(store, [result])
    store.reconcile_framework_tool_results(
        next_prompt, ledger=ledger, known_tool_names=KNOWN_TOOLS
    )
    assert core.state_dict() == before_state
    assert workspace_manifest(core.run_root) == before_workspace


def test_interruption_before_error_persist_recovers_once_and_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    core, ledger, store, prompt = _new_store(tmp_path, "interrupt")
    call_id = "interrupted-call"
    store.record_model_response(
        prompt=prompt,
        response=_response([_call(call_id, "write_file", "{")]),
        ledger=ledger,
    )
    result = {"role": "tool", "tool_call_id": call_id, "content": "bad JSON"}
    next_prompt = _framework_prompt(store, [result])
    original_persist = store._persist  # noqa: SLF001

    def interrupt(event_type: str, event: Any, ledger_value: Any) -> Any:
        if event_type == "framework_tool_errors_reconciled":
            raise TrajectoryPersistenceError("simulated interruption")
        return original_persist(event_type, event, ledger_value)

    monkeypatch.setattr(store, "_persist", interrupt)
    with pytest.raises(TrajectoryPersistenceError, match="simulated interruption"):
        store.reconcile_framework_tool_results(
            next_prompt, ledger=ledger, known_tool_names=KNOWN_TOOLS
        )

    restored = restore_rc12_environment(ROOT, core.run_root, store.latest())
    reopened = RC13DurableTrajectoryStore.reopen(
        store.host_root,
        workspace=core.run_root,
        core=restored,  # type: ignore[arg-type]
        secret=TEST_KEY,
    )
    reopened.reconcile_framework_tool_results(
        next_prompt, ledger=ledger, known_tool_names=KNOWN_TOOLS
    )
    sequence = reopened.latest()["sequence"]
    assert len(reopened.latest()["tool_actions"]) == 1

    restored2 = restore_rc12_environment(ROOT, core.run_root, reopened.latest())
    reopened2 = RC13DurableTrajectoryStore.reopen(
        store.host_root,
        workspace=core.run_root,
        core=restored2,  # type: ignore[arg-type]
        secret=TEST_KEY,
    )
    assert (
        reopened2.reconcile_framework_tool_results(
            next_prompt, ledger=ledger, known_tool_names=KNOWN_TOOLS
        )
        is None
    )
    assert reopened2.latest()["sequence"] == sequence
    assert len(reopened2.latest()["tool_actions"]) == 1


def test_horizon_closure_stays_unexecuted_not_errored(tmp_path: Path) -> None:
    core, ledger, store, prompt = _new_store(tmp_path, "horizon")
    store.record_model_response(
        prompt=prompt,
        response=_response([_call("final-call", "submit", "{}")]),
        ledger=ledger,
    )
    store.close_terminal_tool_calls(
        status="unexecuted_horizon",
        boundary_reason="max_turns_reached",
        ledger=ledger,
    )
    call = store.latest()["pending_tool_calls"][0]
    assert call["status"] == "unexecuted_horizon"
    replay = rc13_trajectory_replay_check(
        ROOT,
        core.run_root,
        store,
        condition_id="case_02",
        grade=None,
        stop_condition="max_turns_reached",
    )
    assert replay["passed"], replay["faults"]
    assert replay["framework_tool_error_count"] == 0


def test_pre_request_client_contains_reconciliation_and_invariant_gate() -> None:
    source = inspect.getsource(RC13DurableAuditedOpenRouterClient.get_native_response)
    assert source.index("reconcile_framework_tool_results") < source.index(
        "assert_provider_request_lifecycle"
    )
    assert source.index("assert_provider_request_lifecycle") < source.index(
        "super().get_native_response"
    )


def test_rc13_provider_facing_identity_and_science_are_unchanged() -> None:
    scientific = read_open_mmmvp_freeze(ROOT)
    rc12 = read_rc12_release_freeze(ROOT)
    identity = compatibility_identity(ROOT)
    adapters = load_rc13_compatible_adapters(ROOT)
    rc12_config = json.loads(
        (ROOT / "configs/uc_bench_mmmvp_open_rc12_release.json").read_text()
    )
    rc13_config = json.loads(
        (ROOT / "configs/uc_bench_mmmvp_open_rc13_release.json").read_text()
    )
    assert scientific["hash_set_digest"] == (
        "466441682b04175432329b41adcfd735cdea66f860d66f046dfae195c91e701c"
    )
    assert identity["serialized_request_sha256"] == (
        "d50747a564877dea31329cd71e9a8a1e3b4ed8f913b802d059cc3c053d0d9523"
    )
    assert identity["tool_schema_sha256"] == (
        "a29133462152f7c78452a5e13c76efc2991142b8703ce418cdf4a78d10f842d7"
    )
    assert rc12["infrastructure_digest"] == (
        "cac7b11ef7dc1c0604f07b050256352ae06d285d453ec1f3001a889ccfab5f3a"
    )
    assert rc12_config["scientific_episode"] == rc13_config["scientific_episode"]
    assert len(adapters) == 10
    assert serialized_open_request()["tools"]


def test_no_cache_cost_gate_uses_only_five_preserved_rc12_cells() -> None:
    plan = calculate_rc13_cost_plan(ROOT)
    assert len(plan["observations"]) == 5
    assert plan["method"]["target_cell_count"] == 10
    assert plan["method"]["bootstrap_draws"] == 1_000_000
    assert plan["ten_cell_no_cache_p90_usd"] > 40.0
    assert plan["p90_exceeds_authorized_cap"] is True
    assert plan["scientific_api_requests"] == 0


def test_rc12_submission_friction_is_separate_and_flags_undisclosed_rule() -> None:
    value = json.loads(
        (
            ROOT
            / "artifacts/mmmvp_open_rc13/rc12_submission_friction_diagnostic.json"
        ).read_text()
    )
    assert value["source_trajectories_reused_for_rc13_scoring"] is False
    assert value["source_scores_reinterpreted"] is False
    assert value["key_evidence"]["accepted_values_present_in_agent_visible_enums"] is False
    assert set(value["key_evidence"]["affected_models"]) == {
        "mistralai/mistral-large-2512",
        "anthropic/claude-sonnet-4",
        "google/gemini-3.1-pro-preview",
    }
    assert "machine_enforced_rule_not_disclosed_to_agent" in value["warnings"]

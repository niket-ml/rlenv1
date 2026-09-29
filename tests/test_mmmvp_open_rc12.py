from __future__ import annotations

import inspect
import json
import random
from pathlib import Path
from typing import Any

import pytest

from uc_bench.hashing import canonical_sha256
from uc_bench.mmmvp_blind_interface import serialized_open_request
from uc_bench.mmmvp_open_freeze import read_open_mmmvp_freeze
from uc_bench.mmmvp_open_rc11_compatibility import compatibility_identity
from uc_bench.mmmvp_open_rc11_freeze import read_rc11_release_freeze
from uc_bench.mmmvp_open_rc12_compatibility import (
    load_rc12_compatible_adapters,
)
from uc_bench.mmmvp_open_rc12_environment import (
    RC12DockerWorkspace,
    RC12OpenMMMVPEnvironment,
    RecoverableWorkspacePathError,
    rc12_isolation_passed,
)
from uc_bench.mmmvp_open_rc12_runner import (
    rc12_reported_values,
    rc12_runtime_factory,
    terminal_tool_status,
)
from uc_bench.mmmvp_open_rc12_trajectory import (
    ACTIVE_TOOL_STATUS,
    RC12DurableTrajectoryStore,
    archived_rc11_adjudication,
    rc12_durable_tool_functions,
    rc12_trajectory_replay_check,
    restore_rc12_environment,
)

ROOT = Path(__file__).resolve().parents[1]
TEST_KEY = "sk-or-v1-rc12-test-secret"
FIXTURE = ROOT / "artifacts/mmmvp_open_rc12/mistral_false_positive_commands.json"
RC11_RUNS = ROOT / "build/uc_bench_mmmvp_open_rc11_runs"
MISTRAL_RUN = RC11_RUNS / "open-mmmvp-rc11-sentinel-01-mistralai-mistral-large-2512-case-02"
GLM_RUN = RC11_RUNS / "open-mmmvp-rc11-sentinel-00-z-ai-glm-5.2-case-02"


class _Ledger:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = [
            {
                "request_index": 0,
                "reported_cost_usd": 0.0,
                "returned_model": "fake/model",
                "actual_provider": "fake",
            }
        ]

    @property
    def cumulative_reported_cost_usd(self) -> float:
        return 0.0


def _core_runtime(
    tmp_path: Path, name: str
) -> tuple[RC12OpenMMMVPEnvironment, RC12DockerWorkspace]:
    core = RC12OpenMMMVPEnvironment(ROOT, "case_02", tmp_path / name / "workspace")
    core.mark_workspace_boundary_enforced(True)
    runtime = rc12_runtime_factory(
        core.run_root,
        container_name=f"uc-rc12-unit-{name}",
        image="uc-bench-agent:0.1",
        core=core,
    )
    runtime.docker_binary = Path("/bin/echo")
    runtime._started = True  # noqa: SLF001
    return core, runtime


def _tool_response(name: str, arguments: dict[str, Any], call_id: str = "call-1") -> dict[str, Any]:
    return {
        "model": "fake/model",
        "provider": "fake",
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {"name": name, "arguments": json.dumps(arguments)},
                        }
                    ],
                },
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "cost": 0.0},
    }


def _new_store(tmp_path: Path, name: str = "trajectory") -> tuple[Any, Any, Any, Any]:
    core, runtime = _core_runtime(tmp_path, name)
    ledger = _Ledger()
    store = RC12DurableTrajectoryStore(
        tmp_path / name / "host",
        workspace=core.run_root,
        core=core,  # type: ignore[arg-type]
        secret=TEST_KEY,
        run_metadata={"fixture": name},
    )
    return core, runtime, ledger, store


def test_rc12_run_command_contains_no_text_authorization_parser() -> None:
    source = inspect.getsource(RC12DockerWorkspace.run_command)
    for forbidden in ("command_mutation_targets", "_REDIRECTION", "_PYTHON_WRITE", "shlex", "re."):
        assert forbidden not in source


def test_all_four_complete_mistral_commands_are_exact_fixtures() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    latest = json.loads((MISTRAL_RUN / "host_trajectory/latest.json").read_text(encoding="utf-8"))
    assert fixture["complete_command_count"] == 4
    assert [row["action_index"] for row in fixture["commands"]] == [20, 21, 23, 24]
    for row in fixture["commands"]:
        archived = next(
            action
            for action in latest["tool_actions"]
            if action["action_index"] == row["action_index"]
        )["invocation_arguments"]["command"]
        assert row["complete_command"] == archived
        assert row["command_sha256"] == canonical_sha256(archived)


def test_quoted_comparison_property_never_changes_command_classification(tmp_path: Path) -> None:
    core, runtime = _core_runtime(tmp_path, "fuzz")
    rng = random.Random(2026090912)
    operators = [">", ">=", "<", "<=", ">>"]
    wrappers = [
        'python3 -c "print({payload!r})"',
        "printf '%s\\n' {payload!r}",
        "awk 'BEGIN {{print {payload!r}}}'",
    ]
    for _ in range(200):
        payload = f"left{rng.choice(operators)}right-{rng.randrange(1_000_000)}"
        command = rng.choice(wrappers).format(payload=payload)
        result = json.loads(runtime.run_command(command))
        assert result["exit_code"] == 0
    assert core.recoverable_contract_violation_count == 0
    assert core.integrity_status()["protected_evidence_untampered"]


def test_write_file_retains_structured_destination_boundary(tmp_path: Path) -> None:
    core, runtime = _core_runtime(tmp_path, "write")
    with pytest.raises(RecoverableWorkspacePathError):
        runtime.write_file("derived.json", "{}")
    result = json.loads(runtime.write_file("work/derived.json", "{}"))
    assert result["path"] == "work/derived.json"
    assert core.recoverable_contract_violation_count == 1
    assert core.state.phase == "investigate"


@pytest.mark.parametrize(
    ("stop_condition", "cap_reached", "error", "expected"),
    [
        ("max_turns_reached", False, None, ("unexecuted_horizon", "max_turns_reached")),
        (
            "max_total_completion_tokens_reached",
            False,
            None,
            ("unexecuted_horizon", "max_total_completion_tokens_reached"),
        ),
        ("anything", True, None, ("unexecuted_cost_boundary", "cost_cap_reached")),
        ("timeout", False, None, ("unexecuted_timeout", "timeout")),
        ("no_tools_called", False, None, None),
    ],
)
def test_terminal_boundary_mapping(
    stop_condition: str,
    cap_reached: bool,
    error: Any,
    expected: tuple[str, str] | None,
) -> None:
    assert (
        terminal_tool_status(
            stop_condition=stop_condition, cap_reached=cap_reached, rollout_error=error
        )
        == expected
    )


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        ("unexecuted_horizon", "max_turns_reached"),
        ("unexecuted_horizon", "max_total_completion_tokens_reached"),
        ("unexecuted_cost_boundary", "cost_cap_reached"),
        ("unexecuted_timeout", "timeout"),
    ],
)
def test_terminal_tool_closes_without_execution_and_replays(
    tmp_path: Path, status: str, reason: str
) -> None:
    core, _, ledger, store = _new_store(tmp_path, f"terminal-{status}-{reason}")
    before_state = core.state_dict()
    before_files = sorted(
        path.relative_to(core.run_root) for path in core.run_root.rglob("*") if path.is_file()
    )
    response = _tool_response("submit", {"payload_json": "{}"})
    store.record_model_response(
        prompt=serialized_open_request()["messages"], response=response, ledger=ledger
    )
    store.close_terminal_tool_calls(status=status, boundary_reason=reason, ledger=ledger)
    latest = store.latest()
    call = latest["pending_tool_calls"][0]
    assert call["status"] == status
    assert latest["event_type"] == "terminal_tool_closure"
    assert latest["event"]["tool_executed"] is False
    assert core.state_dict() == before_state
    assert (
        sorted(
            path.relative_to(core.run_root) for path in core.run_root.rglob("*") if path.is_file()
        )
        == before_files
    )
    replay = rc12_trajectory_replay_check(
        ROOT,
        core.run_root,
        store,
        condition_id="case_02",
        grade=None,
        stop_condition=reason,
    )
    assert replay["passed"], replay["faults"]
    assert replay["resume_boundary_available"] is False
    assert replay["terminal_replay_available"] is True
    assert replay["unexecuted_terminal_tool_count"] == 1
    assert replay["terminal_tool_name"] == "submit"
    assert replay["terminal_boundary_reason"] == reason


def test_mid_episode_pending_call_still_fails_closed(tmp_path: Path) -> None:
    core, _, ledger, store = _new_store(tmp_path, "pending")
    store.record_model_response(
        prompt=serialized_open_request()["messages"],
        response=_tool_response("inspect_workspace", {"relative_path": "."}),
        ledger=ledger,
    )
    assert store.latest()["pending_tool_calls"][0]["status"] == ACTIVE_TOOL_STATUS
    replay = rc12_trajectory_replay_check(
        ROOT,
        core.run_root,
        store,
        condition_id="case_02",
        grade=None,
        stop_condition=None,
    )
    assert not replay["passed"]
    assert "unexplained_mid_episode_pending_tool_call" in replay["faults"]


def test_executed_and_errored_calls_have_explicit_statuses(tmp_path: Path) -> None:
    core, runtime, ledger, store = _new_store(tmp_path, "statuses")
    tools = {
        tool.__name__: tool for tool in rc12_durable_tool_functions(runtime, core, store, ledger)
    }
    store.record_model_response(
        prompt=serialized_open_request()["messages"],
        response=_tool_response("inspect_workspace", {"relative_path": "."}),
        ledger=ledger,
    )
    tools["inspect_workspace"](".")
    assert store.latest()["pending_tool_calls"][0]["status"] == "executed"
    store.record_model_response(
        prompt=store.latest()["messages"],
        response=_tool_response(
            "write_file", {"relative_path": "bad.json", "content": "{}"}, "call-2"
        ),
        ledger=ledger,
    )
    with pytest.raises(RecoverableWorkspacePathError):
        tools["write_file"]("bad.json", "{}")
    assert store.latest()["pending_tool_calls"][0]["status"] == "errored"


def test_interruption_reopen_executes_pending_once(tmp_path: Path) -> None:
    core, runtime, ledger, store = _new_store(tmp_path, "restart")
    store.record_model_response(
        prompt=serialized_open_request()["messages"],
        response=_tool_response("write_file", {"relative_path": "work/a.txt", "content": "a"}),
        ledger=ledger,
    )
    latest = store.latest()
    restored = restore_rc12_environment(ROOT, core.run_root, latest)
    reopened = RC12DurableTrajectoryStore.reopen(
        store.host_root,
        workspace=core.run_root,
        core=restored,  # type: ignore[arg-type]
        secret=TEST_KEY,
    )
    runtime.boundary_handler = restored.boundary_event
    runtime.integrity_guard = restored._assert_untampered  # noqa: SLF001
    tools = {
        tool.__name__: tool
        for tool in rc12_durable_tool_functions(runtime, restored, reopened, ledger)
    }
    tools["write_file"]("work/a.txt", "a")
    assert (core.run_root / "work/a.txt").read_text(encoding="utf-8") == "a"
    assert reopened.latest()["pending_tool_calls"][0]["status"] == "executed"
    assert len(reopened.latest()["tool_actions"]) == 1
    assert reopened.verify(require_no_pending_tools=False)["passed"]
    replay = rc12_trajectory_replay_check(
        ROOT,
        core.run_root,
        reopened,
        condition_id="case_02",
        grade=None,
        stop_condition=None,
    )
    assert replay["passed"], replay["faults"]


def test_reliability_rules_cover_all_terminal_categories() -> None:
    for classification in (
        "agent_task_failure",
        "agent_refusal",
        "context_budget_exhaustion",
        "cost_cap_reached",
    ):
        assert rc12_reported_values(classification, None, usable_responses=1) == (None, 0.0)
    assert rc12_reported_values("provider_adapter_failure", None, usable_responses=0) == (
        None,
        None,
    )
    assert rc12_reported_values("infrastructure_failure", None, usable_responses=0) == (
        None,
        None,
    )
    assert rc12_reported_values(
        "agent_task_failure", None, usable_responses=2, grader_or_replay_fault=True
    ) == (None, None)


def test_archived_rc11_replay_classification_is_nonretroactive() -> None:
    glm = archived_rc11_adjudication(GLM_RUN)
    mistral = archived_rc11_adjudication(MISTRAL_RUN)
    assert glm["trajectory_replay_health"]
    assert glm["counterfactual_rc12_reliability"] == 0.0
    assert glm["scientific_interpretation"] == "usable_opportunity_completion_failure"
    assert mistral["trajectory_replay_health"]
    assert mistral["terminal_tool_status"] == "unexecuted_horizon"
    assert mistral["terminal_tool_name"] == "submit"
    assert mistral["resume_boundary_available"] is False
    assert mistral["terminal_replay_available"] is True
    assert mistral["counterfactual_rc12_reliability"] == 0.0
    assert mistral["scientific_interpretation"] == "environment_contaminated_by_rc11_path_errors"
    assert json.loads((MISTRAL_RUN / "run_summary.json").read_text())["reliability_score"] is None


def test_rc12_science_request_tools_providers_and_budgets_are_unchanged() -> None:
    scientific = read_open_mmmvp_freeze(ROOT)
    rc11 = read_rc11_release_freeze(ROOT)
    identity = compatibility_identity(ROOT)
    adapters = load_rc12_compatible_adapters(ROOT)
    rc11_config = json.loads((ROOT / "configs/uc_bench_mmmvp_open_rc11_release.json").read_text())
    rc12_config = json.loads((ROOT / "configs/uc_bench_mmmvp_open_rc12_release.json").read_text())
    assert (
        scientific["hash_set_digest"]
        == "466441682b04175432329b41adcfd735cdea66f860d66f046dfae195c91e701c"
    )
    assert (
        scientific["serialized_request_sha256"]
        == "d50747a564877dea31329cd71e9a8a1e3b4ed8f913b802d059cc3c053d0d9523"
    )
    assert (
        identity["tool_schema_sha256"]
        == "a29133462152f7c78452a5e13c76efc2991142b8703ce418cdf4a78d10f842d7"
    )
    assert (
        rc11["infrastructure_digest"]
        == "f626396695fa31e8eb2764d2dc62366c345a1f64285922c3ae3af78b681ad068"
    )
    assert rc11_config["scientific_episode"] == rc12_config["scientific_episode"]
    assert len(adapters) == 10
    assert serialized_open_request()["tools"]


def test_rc12_isolation_requires_unchanged_two_mount_boundary() -> None:
    snapshot = {
        "network_mode": "none",
        "read_only_rootfs": True,
        "privileged": False,
        "credential_environment_present": False,
        "workspace_parent_read_only": True,
        "work_nested_writable": True,
        "only_workspace_and_work_bind_mounted": True,
        "workspace_boundary_enforced": True,
    }
    assert rc12_isolation_passed(snapshot)
    for key in (
        "workspace_parent_read_only",
        "work_nested_writable",
        "workspace_boundary_enforced",
    ):
        broken = dict(snapshot)
        broken[key] = False
        assert not rc12_isolation_passed(broken)

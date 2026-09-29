from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from uc_bench.durable_trajectory import DurableTrajectoryStore
from uc_bench.mmmvp_blind_interface import serialized_open_request
from uc_bench.mmmvp_open_controls import build_open_reference
from uc_bench.mmmvp_open_environment import mmmvp_open_tool_functions
from uc_bench.mmmvp_open_freeze import read_open_mmmvp_freeze
from uc_bench.mmmvp_open_rc11_compatibility import compatibility_identity
from uc_bench.mmmvp_open_rc11_environment import (
    ProtectedEvidenceTampering,
    RC11DockerWorkspace,
    RC11OpenMMMVPEnvironment,
    RecoverableWorkspacePathError,
    command_mutation_targets,
    rc11_isolation_passed,
)
from uc_bench.mmmvp_open_rc11_runner import (
    rc11_reported_values,
    rc11_runtime_factory,
)
from uc_bench.mmmvp_open_rc11_trajectory import (
    rc11_durable_tool_functions,
    restore_rc11_environment,
)
from uc_bench.mmmvp_open_release_freeze import read_open_release_freeze
from uc_bench.mmmvp_open_verifier import verify_open_submission

ROOT = Path(__file__).resolve().parents[1]
TEST_KEY = "sk-or-v1-rc11-test-secret"
FIXTURE = ROOT / "artifacts/mmmvp_open_rc11/gemini_root_write_fixture.json"
ARCHIVED_TRAJECTORY = ROOT / (
    "build/uc_bench_mmmvp_open_runs/"
    "open-mmmvp-sentinel-00-google-gemini-3.1-pro-preview-case-02/"
    "host_trajectory/latest.json"
)


class _Ledger:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    @property
    def cumulative_reported_cost_usd(self) -> float:
        return 0.0


def _core_and_runtime(tmp_path: Path, name: str = "case") -> tuple[Any, Any]:
    core = RC11OpenMMMVPEnvironment(ROOT, "case_02", tmp_path / name / "workspace")
    core.mark_workspace_boundary_enforced(True)
    runtime = rc11_runtime_factory(
        core.run_root,
        container_name=f"uc-rc11-unit-{name}",
        image="uc-bench-agent:0.1",
        core=core,
    )
    runtime.docker_binary = Path("/bin/echo")
    runtime._started = True  # noqa: SLF001 - no-network boundary unit fixture
    return core, runtime


def _fixture_command() -> str:
    return str(json.loads(FIXTURE.read_text(encoding="utf-8"))["arguments"]["command"])


def _archived_command() -> str:
    latest = json.loads(ARCHIVED_TRAJECTORY.read_text(encoding="utf-8"))
    for message in latest["messages"]:
        for call in message.get("tool_calls") or []:
            function = call.get("function") or {}
            arguments = json.loads(function.get("arguments") or "{}")
            if function.get("name") == "run_command" and "commit_vp.json" in arguments.get(
                "command", ""
            ):
                return str(arguments["command"])
    raise AssertionError("The preserved Gemini command is missing")


def _complete_reference(core: RC11OpenMMMVPEnvironment, tmp_path: Path) -> dict[str, Any]:
    reference, reference_workspace = build_open_reference(
        ROOT,
        "case_02",
        tmp_path / "reference",
        alternative=False,
    )
    assert core.commit_validation_plan(json.dumps(reference["validation_plan"]))["accepted"]
    core.reveal_validation()
    for path in (reference_workspace / "work").rglob("*"):
        if path.is_file():
            target = core.run_root / path.relative_to(reference_workspace)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    assert core.commit_followup_plan(json.dumps(reference["followup_plan"]))["accepted"]
    core.purchase_resource(reference["followup_plan"]["chosen_resource"])
    assert core.submit(json.dumps(reference["final_submission"]))["accepted"]
    return verify_open_submission(
        ROOT,
        core.run_root,
        core.export_submission(),
        condition_id="case_02",
    ).to_dict()


def test_exact_gemini_command_is_preserved_as_regression_fixture() -> None:
    assert _fixture_command() == _archived_command()
    assert command_mutation_targets(_fixture_command())[0] == "commit_vp.json"


def test_exact_root_write_is_recoverable_and_creates_no_file(tmp_path: Path) -> None:
    core, runtime = _core_and_runtime(tmp_path)
    with pytest.raises(RecoverableWorkspacePathError, match="under work/"):
        runtime.run_command(_fixture_command())
    assert not (core.run_root / "commit_vp.json").exists()
    assert core.state.phase == "investigate"
    assert core.recoverable_contract_violation_count == 1
    integrity = core.integrity_status()
    assert integrity["start_state_untampered"]
    assert integrity["protected_evidence_untampered"]
    assert not integrity["protected_evidence_mutation_attempted"]
    assert integrity["workspace_boundary_enforced"]


@pytest.mark.parametrize(
    "path",
    [
        "helper.json",
        "../helper.json",
        "work/../helper.json",
        "/workspace/helper.json",
        "/tmp/helper.json",
    ],
)
def test_write_file_rejects_every_non_work_target_recoverably(
    tmp_path: Path, path: str
) -> None:
    core, runtime = _core_and_runtime(tmp_path, path.replace("/", "-").replace("..", "up"))
    with pytest.raises(RecoverableWorkspacePathError):
        runtime.write_file(path, "derived")
    assert core.state.phase == "investigate"
    assert core.recoverable_contract_violation_count == 1


def test_work_write_succeeds_without_damaging_integrity(tmp_path: Path) -> None:
    core, runtime = _core_and_runtime(tmp_path)
    result = json.loads(runtime.write_file("work/helper.json", "{}\n"))
    assert result["path"] == "work/helper.json"
    (core.run_root / "work/helper.json").unlink()
    assert core.integrity_status()["protected_evidence_untampered"]


@pytest.mark.parametrize(
    "command",
    [
        "rm data/locked_predictions.csv",
        "mv data/locked_predictions.csv work/predictions.csv",
        "cp work/helper.json data/locked_predictions.csv",
        "touch data/locked_predictions.csv",
        "ln data/locked_predictions.csv work/hard-link.csv",
        "ln -s data/locked_predictions.csv work/symbolic-link.csv",
        "sed -i 's/a/b/' data/locked_predictions.csv",
        "python -c \"open('data/locked_predictions.csv','w').write('x')\"",
        "printf x > /workspace/data/locked_predictions.csv",
        "printf x > work/../data/locked_predictions.csv",
    ],
)
def test_protected_modify_delete_replace_rename_and_link_attempts_are_terminal(
    tmp_path: Path, command: str
) -> None:
    core, runtime = _core_and_runtime(tmp_path, str(abs(hash(command))))
    with pytest.raises(ProtectedEvidenceTampering):
        runtime.run_command(command)
    assert core.state.phase == "terminal"
    assert core.state.terminal_reason == "protected_evidence_tampering"
    assert core.protected_evidence_mutation_attempted
    assert core.integrity_status()["protected_evidence_untampered"]


def test_write_file_cannot_follow_symlink_or_hardlink_to_protected_data(
    tmp_path: Path,
) -> None:
    core, runtime = _core_and_runtime(tmp_path, "symlink")
    link = core.run_root / "work/link.csv"
    link.symlink_to(core.run_root / "data/locked_predictions.csv")
    with pytest.raises(ProtectedEvidenceTampering):
        runtime.write_file("work/link.csv", "x")
    assert (core.run_root / "data/locked_predictions.csv").read_text(encoding="utf-8")

    core2, runtime2 = _core_and_runtime(tmp_path, "hardlink")
    hardlink = core2.run_root / "work/link.csv"
    hardlink.hardlink_to(core2.run_root / "data/locked_predictions.csv")
    with pytest.raises(ProtectedEvidenceTampering):
        runtime2.write_file("work/link.csv", "x")
    assert core2.integrity_status()["protected_evidence_untampered"]


def test_host_hash_guard_detects_changed_deleted_and_unsafe_file_types(tmp_path: Path) -> None:
    for index, operation in enumerate(("change", "delete", "symlink")):
        core, _ = _core_and_runtime(tmp_path, f"hash-{index}")
        protected = core.run_root / "data/locked_predictions.csv"
        if operation == "change":
            protected.write_text("changed", encoding="utf-8")
        elif operation == "delete":
            protected.unlink()
        else:
            external = tmp_path / f"same-{index}.csv"
            shutil.copy2(protected, external)
            protected.unlink()
            protected.symlink_to(external)
        with pytest.raises(ProtectedEvidenceTampering):
            core._assert_untampered()  # noqa: SLF001
        assert core.state.phase == "terminal"
        assert not core.integrity_status()["protected_evidence_untampered"]


def test_reveal_and_purchase_files_become_protected(tmp_path: Path) -> None:
    reference, _ = build_open_reference(
        ROOT, "case_02", tmp_path / "reference", alternative=False
    )
    core, runtime = _core_and_runtime(tmp_path, "revealed")
    assert core.commit_validation_plan(json.dumps(reference["validation_plan"]))["accepted"]
    core.reveal_validation()
    revealed = next(path for path in (core.run_root / "revealed").rglob("*") if path.is_file())
    with pytest.raises(ProtectedEvidenceTampering):
        runtime.run_command(f"rm {revealed.relative_to(core.run_root).as_posix()}")

    core2, runtime2 = _core_and_runtime(tmp_path, "purchased")
    assert core2.commit_validation_plan(json.dumps(reference["validation_plan"]))["accepted"]
    core2.reveal_validation()
    assert core2.commit_followup_plan(json.dumps(reference["followup_plan"]))["accepted"]
    core2.purchase_resource(reference["followup_plan"]["chosen_resource"])
    purchased = next((core2.run_root / "purchased").rglob("*.csv"))
    with pytest.raises(ProtectedEvidenceTampering):
        runtime2.run_command(f"rm {purchased.relative_to(core2.run_root).as_posix()}")


def test_recoverable_error_does_not_reduce_scientific_mission_credit(tmp_path: Path) -> None:
    core, runtime = _core_and_runtime(tmp_path)
    with pytest.raises(RecoverableWorkspacePathError):
        runtime.run_command(_fixture_command())
    runtime.write_file("work/commit_vp.json", "{}\n")
    grade = _complete_reference(core, tmp_path)
    assert grade["complete_mission_success"]
    assert grade["partial_scientific_quality"] >= 90
    assert core.recoverable_contract_violation_count == 1
    assert core.integrity_status()["protected_evidence_untampered"]


def test_rejected_write_persists_and_restores_exactly(tmp_path: Path) -> None:
    core, runtime = _core_and_runtime(tmp_path)
    ledger = _Ledger()
    store = DurableTrajectoryStore(
        tmp_path / "host-trajectory",
        workspace=core.run_root,
        core=core,  # type: ignore[arg-type]
        secret=TEST_KEY,
        run_metadata={"fixture": "exact-gemini-root-write"},
    )
    tools = {
        tool.__name__: tool
        for tool in rc11_durable_tool_functions(runtime, core, store, ledger)
    }
    response = {
        "model": "fake/model",
        "provider": "fake",
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call-root-write",
                            "type": "function",
                            "function": {
                                "name": "run_command",
                                "arguments": json.dumps({"command": _fixture_command()}),
                            },
                        }
                    ],
                },
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "cost": 0.0},
    }
    ledger.records.append(
        {
            "request_index": 0,
            "reported_cost_usd": 0.0,
            "returned_model": "fake/model",
            "actual_provider": "fake",
        }
    )
    store.record_model_response(
        prompt=serialized_open_request()["messages"], response=response, ledger=ledger
    )
    with pytest.raises(RecoverableWorkspacePathError):
        tools["run_command"](_fixture_command())
    latest = store.latest()
    assert latest["tool_actions"][-1]["error"]["type"] == "RecoverableWorkspacePathError"
    assert latest["pending_tool_calls"][-1]["status"] == "errored"
    restored = restore_rc11_environment(ROOT, core.run_root, latest)
    assert restored.state.phase == "investigate"
    assert restored.recoverable_contract_violation_count == 1
    reopened = DurableTrajectoryStore.reopen(
        tmp_path / "host-trajectory",
        workspace=core.run_root,
        core=restored,  # type: ignore[arg-type]
        secret=TEST_KEY,
    )
    assert reopened.verify()["passed"]
    assert reopened.latest() == latest


def test_reliability_distinguishes_usable_and_excluded_attempts() -> None:
    assert rc11_reported_values("agent_task_failure", None, usable_responses=2) == (None, 0.0)
    assert rc11_reported_values("agent_refusal", None, usable_responses=1) == (None, 0.0)
    assert rc11_reported_values("cost_cap_reached", None, usable_responses=1) == (None, 0.0)
    assert rc11_reported_values("infrastructure_failure", None, usable_responses=0) == (
        None,
        None,
    )
    assert rc11_reported_values("provider_adapter_failure", None, usable_responses=0) == (
        None,
        None,
    )
    assert rc11_reported_values(
        "agent_task_failure",
        None,
        usable_responses=3,
        grader_or_replay_fault=True,
    ) == (None, None)


def test_rc11_tools_and_request_are_identical_to_rc1(tmp_path: Path) -> None:
    core, runtime = _core_and_runtime(tmp_path)
    tools = mmmvp_open_tool_functions(runtime, core)
    from uc_bench.mmmvp_open_runner import _tool_contract

    assert _tool_contract(tools) == serialized_open_request()["tools"]
    assert compatibility_identity(ROOT)["serialized_request_sha256"] == read_open_mmmvp_freeze(
        ROOT
    )["serialized_request_sha256"]


def test_runtime_factory_is_the_nested_mount_implementation(tmp_path: Path) -> None:
    core = RC11OpenMMMVPEnvironment(ROOT, "case_02", tmp_path / "workspace")
    runtime = rc11_runtime_factory(
        core.run_root,
        container_name="uc-rc11-factory-test",
        image="uc-bench-agent:0.1",
        core=core,
    )
    assert isinstance(runtime, RC11DockerWorkspace)
    assert runtime.boundary_handler is not None
    assert runtime.integrity_guard is not None


def test_isolation_requires_both_mount_modes() -> None:
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
    assert rc11_isolation_passed(snapshot)
    for key in (
        "workspace_parent_read_only",
        "work_nested_writable",
        "only_workspace_and_work_bind_mounted",
        "workspace_boundary_enforced",
    ):
        changed = dict(snapshot)
        changed[key] = False
        assert not rc11_isolation_passed(changed)


def test_old_scientific_and_release_freezes_remain_exact() -> None:
    assert (
        read_open_mmmvp_freeze(ROOT)["hash_set_digest"]
        == "466441682b04175432329b41adcfd735cdea66f860d66f046dfae195c91e701c"
    )
    assert (
        read_open_release_freeze(ROOT)["category_digest_set"]
        == "0c620a5db9b75fc5454d5e013866fc37d4bb71095266721c158aa8efd00c1dba"
    )


def test_archived_gemini_summary_is_unchanged_and_sidecar_is_nonretroactive() -> None:
    summary = json.loads((ARCHIVED_TRAJECTORY.parents[1] / "run_summary.json").read_text())
    sidecar = json.loads(
        (ROOT / "artifacts/mmmvp_open_rc11/rc1_gemini_reliability_adjudication.json").read_text()
    )
    assert summary["reliability_score"] is None
    assert summary["classification"] == "agent_task_failure"
    assert sidecar["historical_reliability_score"] is None
    assert sidecar["retroactive_score_change"] is False

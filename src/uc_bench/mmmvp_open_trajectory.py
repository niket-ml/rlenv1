"""Restoration and replay checks for the open MMMVP production trajectory."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from uc_bench.durable_trajectory import (
    DurableTrajectoryStore,
    TrajectoryPersistenceError,
    durable_wrapped_tools,
    workspace_manifest,
)
from uc_bench.mmmvp_open_environment import (
    OpenEpisodeState,
    OpenMMMVPEnvironment,
    mmmvp_open_tool_functions,
)
from uc_bench.mmmvp_open_verifier import verify_open_submission


def restore_open_environment(
    project_root: Path,
    workspace: Path,
    latest: Mapping[str, Any],
) -> OpenMMMVPEnvironment:
    """Reconstruct the open core without repeating an irreversible action."""

    environment = latest.get("environment")
    if not isinstance(environment, Mapping):
        raise TrajectoryPersistenceError("Durable record lacks environment state")
    if environment.get("workspace_manifest") != workspace_manifest(workspace):
        raise TrajectoryPersistenceError("Workspace changed since the durable boundary")
    state_raw = environment.get("state")
    submission = environment.get("submission")
    if not isinstance(state_raw, Mapping) or not isinstance(submission, Mapping):
        raise TrajectoryPersistenceError("Durable record lacks open episode state")

    restored_state = dict(state_raw)
    case_id = str(restored_state.pop("case_id"))
    mechanism = str(restored_state.pop("mechanism"))
    core = object.__new__(OpenMMMVPEnvironment)
    core.project_root = project_root.resolve()
    core.case_id = case_id
    core.mechanism = mechanism
    core.run_root = workspace.resolve()
    core.records_root = Path(str(submission["host_record_locator"])).resolve()
    core.maximum_tool_calls = int(environment["maximum_tool_calls"])
    core.state = OpenEpisodeState(**restored_state)
    core._start_hashes = dict(environment["start_hashes"])  # noqa: SLF001
    core._protected_evidence_hashes = dict(  # noqa: SLF001
        submission.get("protected_evidence_hashes") or {}
    )
    core._validation_input_hashes = dict(  # noqa: SLF001
        submission.get("validation_input_hashes") or {}
    )
    if core.export_submission() != dict(submission):
        raise TrajectoryPersistenceError("Restored open submission differs from durable state")
    return core


def open_durable_tool_functions(
    docker: Any,
    core: OpenMMMVPEnvironment,
    store: DurableTrajectoryStore,
    ledger: Any,
) -> list[Any]:
    """Persist every action from the open environment's exact tool surface."""

    return durable_wrapped_tools(mmmvp_open_tool_functions(docker, core), store, ledger)


def open_trajectory_replay_check(
    project_root: Path,
    workspace: Path,
    store: DurableTrajectoryStore,
    *,
    condition_id: str,
    grade: dict[str, Any] | None,
) -> dict[str, Any]:
    """Verify the journal, reconstruct state, and independently regrade terminal work."""

    verification = store.verify()
    if not verification["passed"]:
        return {**verification, "reconstructed": False, "recomputed_grade_matches": False}
    latest = store.latest()
    restored = restore_open_environment(project_root, workspace, latest)
    submission = restored.export_submission()
    restored_grade: dict[str, Any] | None = None
    if restored.state.completion_accepted:
        restored_grade = verify_open_submission(
            project_root,
            workspace,
            submission,
            condition_id=condition_id,
        ).to_dict()
    pending = any(
        call.get("status") == "pending" for call in latest.get("pending_tool_calls") or []
    )
    return {
        **verification,
        "reconstructed": submission == latest["environment"]["submission"],
        "recomputed_grade_matches": restored_grade == grade,
        "resume_boundary_available": (
            restored.state.phase != "terminal" and bool(latest.get("messages")) and not pending
        ),
        "terminal_replay_available": restored.state.phase == "terminal",
    }


__all__ = [
    "open_durable_tool_functions",
    "open_trajectory_replay_check",
    "restore_open_environment",
]

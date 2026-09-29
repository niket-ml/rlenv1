"""MMMVP restoration and replay checks for durable host-only trajectories."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from uc_bench.durable_trajectory import (
    DurableTrajectoryStore,
    TrajectoryPersistenceError,
    durable_tool_functions,
    workspace_manifest,
)
from uc_bench.mmmvp_environment import MMMVPEnvironment
from uc_bench.mmmvp_verifier import verify_mmmvp_submission
from uc_bench.v07_environment import V07EpisodeState


def restore_mmmvp_environment(
    project_root: Path,
    workspace: Path,
    latest: Mapping[str, Any],
) -> MMMVPEnvironment:
    environment = latest.get("environment")
    if not isinstance(environment, Mapping):
        raise TrajectoryPersistenceError("Durable record lacks environment state")
    if environment.get("workspace_manifest") != workspace_manifest(workspace):
        raise TrajectoryPersistenceError("Workspace changed since the durable boundary")
    state_raw = environment.get("state")
    if not isinstance(state_raw, Mapping):
        raise TrajectoryPersistenceError("Durable record lacks episode state")
    core = object.__new__(MMMVPEnvironment)
    core.project_root = project_root.resolve()
    core.case_id = str(state_raw["case_id"])
    core.run_root = workspace.resolve()
    core.maximum_tool_calls = int(environment["maximum_tool_calls"])
    core.state = V07EpisodeState(**dict(state_raw))
    core._start_hashes = dict(environment["start_hashes"])  # noqa: SLF001
    if core.export_submission() != environment.get("submission"):
        raise TrajectoryPersistenceError("Restored submission differs from durable state")
    return core


def mmmvp_durable_tool_functions(
    docker: Any,
    core: MMMVPEnvironment,
    store: DurableTrajectoryStore,
    ledger: Any,
) -> list[Any]:
    return durable_tool_functions(docker, core, store, ledger)  # type: ignore[arg-type]


def trajectory_replay_check(
    project_root: Path,
    workspace: Path,
    store: DurableTrajectoryStore,
    *,
    condition_id: str,
    grade: dict[str, Any] | None,
) -> dict[str, Any]:
    verification = store.verify()
    if not verification["passed"]:
        return {**verification, "reconstructed": False, "recomputed_grade_matches": False}
    latest = store.latest()
    restored = restore_mmmvp_environment(project_root, workspace, latest)
    restored_grade: dict[str, Any] | None = None
    submission = restored.export_submission()
    if len(submission.get("checkpoints") or {}) == 5:
        restored_grade = verify_mmmvp_submission(
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
    "mmmvp_durable_tool_functions",
    "restore_mmmvp_environment",
    "trajectory_replay_check",
]

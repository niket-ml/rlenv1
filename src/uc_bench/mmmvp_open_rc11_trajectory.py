"""Durable reconstruction for the RC1.1 infrastructure successor."""

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
from uc_bench.mmmvp_open_environment import OpenEpisodeState, mmmvp_open_tool_functions
from uc_bench.mmmvp_open_rc11_environment import RC11OpenMMMVPEnvironment
from uc_bench.mmmvp_open_verifier import verify_open_submission


def restore_rc11_environment(
    project_root: Path,
    workspace: Path,
    latest: Mapping[str, Any],
) -> RC11OpenMMMVPEnvironment:
    """Reconstruct RC1.1 without replaying a tool or irreversible action."""

    environment = latest.get("environment")
    if not isinstance(environment, Mapping):
        raise TrajectoryPersistenceError("Durable record lacks environment state")
    if environment.get("workspace_manifest") != workspace_manifest(workspace):
        raise TrajectoryPersistenceError("Workspace changed since the durable boundary")
    state_raw = environment.get("state")
    submission = environment.get("submission")
    if not isinstance(state_raw, Mapping) or not isinstance(submission, Mapping):
        raise TrajectoryPersistenceError("Durable record lacks RC1.1 episode state")

    restored = dict(state_raw)
    case_id = str(restored.pop("case_id"))
    mechanism = str(restored.pop("mechanism"))
    recoverable = int(restored.pop("recoverable_contract_violation_count", 0))
    mutation_attempted = bool(restored.pop("protected_evidence_mutation_attempted", False))
    boundary_enforced = bool(restored.pop("workspace_boundary_enforced", False))

    core = object.__new__(RC11OpenMMMVPEnvironment)
    core.project_root = project_root.resolve()
    core.case_id = case_id
    core.mechanism = mechanism
    core.run_root = workspace.resolve()
    core.records_root = Path(str(submission["host_record_locator"])).resolve()
    core.maximum_tool_calls = int(environment["maximum_tool_calls"])
    core.state = OpenEpisodeState(**restored)
    core._start_hashes = dict(environment["start_hashes"])  # noqa: SLF001
    core._protected_evidence_hashes = dict(  # noqa: SLF001
        submission.get("protected_evidence_hashes") or {}
    )
    core._validation_input_hashes = dict(  # noqa: SLF001
        submission.get("validation_input_hashes") or {}
    )
    core.recoverable_contract_violation_count = recoverable
    core.protected_evidence_mutation_attempted = mutation_attempted
    core.workspace_boundary_enforced = boundary_enforced
    if core.export_submission() != dict(submission):
        raise TrajectoryPersistenceError("Restored RC1.1 submission differs from durable state")
    return core


def rc11_durable_tool_functions(
    docker: Any,
    core: RC11OpenMMMVPEnvironment,
    store: DurableTrajectoryStore,
    ledger: Any,
) -> list[Any]:
    """Persist every action from the unchanged RC1 public tool surface."""

    return durable_wrapped_tools(mmmvp_open_tool_functions(docker, core), store, ledger)


def rc11_trajectory_replay_check(
    project_root: Path,
    workspace: Path,
    store: DurableTrajectoryStore,
    *,
    condition_id: str,
    grade: dict[str, Any] | None,
) -> dict[str, Any]:
    """Verify the journal, reconstruct state, and independently regrade."""

    verification = store.verify()
    if not verification["passed"]:
        return {**verification, "reconstructed": False, "recomputed_grade_matches": False}
    latest = store.latest()
    restored = restore_rc11_environment(project_root, workspace, latest)
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
        "recoverable_contract_violation_count": (
            restored.recoverable_contract_violation_count
        ),
        "protected_evidence_mutation_attempted": (
            restored.protected_evidence_mutation_attempted
        ),
    }


__all__ = [
    "rc11_durable_tool_functions",
    "rc11_trajectory_replay_check",
    "restore_rc11_environment",
]

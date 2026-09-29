"""Durable reconstruction and replay checks for the isolated Case-1 RC1.7 core."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from uc_bench.durable_trajectory import TrajectoryPersistenceError, workspace_manifest
from uc_bench.mmmvp_open_environment import OpenEpisodeState
from uc_bench.mmmvp_open_rc12_trajectory import _tool_lifecycle_faults
from uc_bench.mmmvp_open_rc13_trajectory import FRAMEWORK_ERROR_CLASSES
from uc_bench.mmmvp_open_rc17_environment import RC17OpenMMMVPEnvironment
from uc_bench.mmmvp_open_rc17_verifier import verify_rc17_case1_submission


def restore_rc17_environment(
    project_root: Path,
    workspace: Path,
    latest: Mapping[str, Any],
) -> RC17OpenMMMVPEnvironment:
    """Restore authentic Case 1 at a durable boundary without replaying an action."""

    environment = latest.get("environment")
    if not isinstance(environment, Mapping):
        raise TrajectoryPersistenceError("Durable record lacks environment state")
    if environment.get("workspace_manifest") != workspace_manifest(workspace):
        raise TrajectoryPersistenceError("Workspace changed since the durable boundary")
    state_raw = environment.get("state")
    submission = environment.get("submission")
    if not isinstance(state_raw, Mapping) or not isinstance(submission, Mapping):
        raise TrajectoryPersistenceError("Durable record lacks RC1.7 episode state")

    restored = dict(state_raw)
    case_id = str(restored.pop("case_id"))
    mechanism = str(restored.pop("mechanism"))
    if case_id != "case_01" or mechanism != "default":
        raise TrajectoryPersistenceError("RC1.7 restore accepts authentic Case 1 only")
    recoverable = int(restored.pop("recoverable_contract_violation_count", 0))
    mutation_attempted = bool(restored.pop("protected_evidence_mutation_attempted", False))
    boundary_enforced = bool(restored.pop("workspace_boundary_enforced", False))

    core = object.__new__(RC17OpenMMMVPEnvironment)
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
    # Production Case 1 uses the immutable authentic returns. Control injection is
    # deliberately unavailable after a persisted boundary.
    core._control_outcomes = None  # noqa: SLF001
    core._control_outcome_provenance = None  # noqa: SLF001
    core._control_resource_overrides = {}  # noqa: SLF001
    if core.export_submission() != dict(submission):
        raise TrajectoryPersistenceError("Restored RC1.7 submission differs from durable state")
    return core


def rc17_trajectory_replay_check(
    project_root: Path,
    workspace: Path,
    store: Any,
    *,
    grade: dict[str, Any] | None,
    stop_condition: str | None,
    grader: Callable[..., Any] = verify_rc17_case1_submission,
) -> dict[str, Any]:
    """Independently verify lifecycle continuity and scientific replay."""

    verification = store.verify(require_no_pending_tools=False)
    latest = store.latest()
    lifecycle_faults, boundary = _tool_lifecycle_faults(latest, stop_condition=stop_condition)
    faults = [*verification["faults"], *lifecycle_faults]
    framework_actions = [
        action for action in latest.get("tool_actions") or [] if action.get("framework_generated")
    ]
    for action in framework_actions:
        call_id = str(action.get("tool_call_id"))
        if action.get("wrapper_entered") is not False:
            faults.append(f"framework_error_entered_wrapper:{call_id}")
        if action.get("error_class") not in FRAMEWORK_ERROR_CLASSES:
            faults.append(f"invalid_framework_error_class:{call_id}")
        if not action.get("error") or action.get("result") is not None:
            faults.append(f"invalid_framework_error_action:{call_id}")

    restored: RC17OpenMMMVPEnvironment | None = None
    try:
        restored = restore_rc17_environment(project_root, workspace, latest)
    except Exception as exc:  # host journal/state is not agent artifact data
        faults.append(f"reconstruction:{type(exc).__name__}")

    if boundary["terminal_replay_available"]:
        previous_path = store.journal_root / f"{int(latest['sequence']) - 1:06d}.json"
        if not previous_path.is_file():
            faults.append("terminal_closure_missing_previous_record")
        else:
            previous = json.loads(previous_path.read_text(encoding="utf-8"))
            for field in ("state", "submission", "workspace_manifest"):
                if previous["environment"].get(field) != latest["environment"].get(field):
                    faults.append(f"terminal_closure_mutated:{field}")

    reconstructed = bool(
        restored is not None and restored.export_submission() == latest["environment"]["submission"]
    )
    lifecycle = {
        **verification,
        "passed": not faults,
        "faults": list(dict.fromkeys(faults)),
        "reconstructed": reconstructed,
        **boundary,
        "recoverable_contract_violation_count": (
            restored.recoverable_contract_violation_count if restored else None
        ),
        "protected_evidence_mutation_attempted": (
            restored.protected_evidence_mutation_attempted if restored else None
        ),
        "framework_tool_error_count": len(framework_actions),
        "framework_tool_error_classes": dict(
            Counter(str(action.get("error_class")) for action in framework_actions)
        ),
        "wrapper_tool_error_count": sum(
            bool(action.get("error")) and not action.get("framework_generated")
            for action in latest.get("tool_actions") or []
        ),
    }

    grader_fault: dict[str, str] | None = None
    replayed_grade: dict[str, Any] | None = None
    if restored is not None and restored.state.completion_accepted:
        try:
            replayed_grade = grader(
                project_root,
                workspace,
                restored.export_submission(),
            ).to_dict()
        except Exception as exc:  # grading remains separate from lifecycle health
            grader_fault = {"type": type(exc).__name__, "message": str(exc)}
    grader_replay = {
        "passed": grader_fault is None and replayed_grade == grade,
        "faults": (
            [f"verifier_exception:{grader_fault['type']}"]
            if grader_fault
            else ([] if replayed_grade == grade else ["recomputed_grade_mismatch"])
        ),
        "exception": grader_fault,
        "recomputed_grade_matches": grader_fault is None and replayed_grade == grade,
    }
    return {
        **lifecycle,
        "lifecycle": lifecycle,
        "grader_replay": grader_replay,
        "recomputed_grade_matches": grader_replay["recomputed_grade_matches"],
    }


__all__ = ["rc17_trajectory_replay_check", "restore_rc17_environment"]

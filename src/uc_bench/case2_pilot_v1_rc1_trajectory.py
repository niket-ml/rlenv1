"""Exact Case 2 reconstruction and scientific replay."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from uc_bench.case2_pilot_v1_rc1_environment import Case2PilotRC1Environment
from uc_bench.case2_pilot_v1_rc1_verifier import verify_case2_rc1_submission
from uc_bench.durable_trajectory import TrajectoryPersistenceError, workspace_manifest
from uc_bench.mmmvp_open_environment import OpenEpisodeState
from uc_bench.mmmvp_open_rc12_trajectory import _tool_lifecycle_faults
from uc_bench.mmmvp_open_rc13_trajectory import FRAMEWORK_ERROR_CLASSES


def restore_case2_environment(
    project_root: Path,
    workspace: Path,
    latest: Mapping[str, Any],
) -> Case2PilotRC1Environment:
    environment = latest.get("environment")
    if not isinstance(environment, Mapping):
        raise TrajectoryPersistenceError("Durable record lacks environment state")
    if environment.get("workspace_manifest") != workspace_manifest(workspace):
        raise TrajectoryPersistenceError("Workspace changed since the durable boundary")
    state_raw = environment.get("state")
    submission = environment.get("submission")
    if not isinstance(state_raw, Mapping) or not isinstance(submission, Mapping):
        raise TrajectoryPersistenceError("Durable record lacks Case 2 episode state")
    restored = dict(state_raw)
    case_id = str(restored.pop("case_id"))
    mechanism = str(restored.pop("mechanism"))
    if case_id != "case_02" or mechanism != "default":
        raise TrajectoryPersistenceError("Case 2 restore accepts the authentic case only")
    recoverable = int(restored.pop("recoverable_contract_violation_count", 0))
    mutation = bool(restored.pop("protected_evidence_mutation_attempted", False))
    boundary = bool(restored.pop("workspace_boundary_enforced", False))
    core = object.__new__(Case2PilotRC1Environment)
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
    core.protected_evidence_mutation_attempted = mutation
    core.workspace_boundary_enforced = boundary
    if core.export_submission() != dict(submission):
        raise TrajectoryPersistenceError("Restored Case 2 submission differs from durable state")
    return core


def case2_trajectory_replay_check(
    project_root: Path,
    workspace: Path,
    store: Any,
    *,
    grade: dict[str, Any] | None,
    stop_condition: str | None,
) -> dict[str, Any]:
    verification = store.verify(require_no_pending_tools=False)
    latest = store.latest()
    lifecycle_faults, boundary = _tool_lifecycle_faults(latest, stop_condition=stop_condition)
    faults = [*verification["faults"], *lifecycle_faults]
    framework_actions = [
        row for row in latest.get("tool_actions") or [] if row.get("framework_generated")
    ]
    for action in framework_actions:
        call_id = str(action.get("tool_call_id"))
        if action.get("wrapper_entered") is not False:
            faults.append(f"framework_error_entered_wrapper:{call_id}")
        if action.get("error_class") not in FRAMEWORK_ERROR_CLASSES:
            faults.append(f"invalid_framework_error_class:{call_id}")
        if not action.get("error") or action.get("result") is not None:
            faults.append(f"invalid_framework_error_action:{call_id}")
    restored: Case2PilotRC1Environment | None = None
    try:
        restored = restore_case2_environment(project_root, workspace, latest)
    except Exception as exc:
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
    replayed_grade: dict[str, Any] | None = None
    grader_fault: str | None = None
    if restored is not None and restored.state.completion_accepted:
        try:
            replayed_grade = verify_case2_rc1_submission(
                workspace, restored.export_submission()
            ).to_dict()
        except Exception as exc:
            grader_fault = type(exc).__name__
            faults.append(f"verifier_exception:{grader_fault}")
    reconstructed = bool(
        restored is not None and restored.export_submission() == latest["environment"]["submission"]
    )
    return {
        **verification,
        "passed": not faults,
        "faults": list(dict.fromkeys(faults)),
        "reconstructed": reconstructed,
        "recomputed_grade_matches": grader_fault is None and replayed_grade == grade,
        **boundary,
        "recoverable_contract_violation_count": recoverable_count(restored),
        "protected_evidence_mutation_attempted": (
            restored.protected_evidence_mutation_attempted if restored else None
        ),
        "framework_tool_error_count": len(framework_actions),
        "framework_tool_error_classes": dict(
            Counter(str(row.get("error_class")) for row in framework_actions)
        ),
    }


def recoverable_count(restored: Case2PilotRC1Environment | None) -> int | None:
    return restored.recoverable_contract_violation_count if restored else None


__all__ = ["case2_trajectory_replay_check", "restore_case2_environment"]

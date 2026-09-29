"""RC1.6 trajectory replay with lifecycle and grading independently adjudicated."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

from uc_bench.mmmvp_open_rc12_trajectory import (
    _tool_lifecycle_faults,
    restore_rc12_environment,
)
from uc_bench.mmmvp_open_rc13_trajectory import FRAMEWORK_ERROR_CLASSES
from uc_bench.mmmvp_open_rc16_verifier import verify_rc16_open_submission


def rc16_trajectory_replay_check(
    project_root: Path,
    workspace: Path,
    store: Any,
    *,
    condition_id: str,
    grade: dict[str, Any] | None,
    stop_condition: str | None,
    grader: Callable[..., Any] = verify_rc16_open_submission,
) -> dict[str, Any]:
    """Check durable continuity first and replay science in a separate result."""

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

    restored = None
    try:
        restored = restore_rc12_environment(project_root, workspace, latest)
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
            replayed = grader(
                project_root,
                workspace,
                restored.export_submission(),
                condition_id=condition_id,
            )
            replayed_grade = replayed.to_dict()
        except Exception as exc:  # deliberately separate from lifecycle adjudication
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


__all__ = ["rc16_trajectory_replay_check"]

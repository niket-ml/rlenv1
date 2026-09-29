"""RC5 trajectory reconstruction with the cohort-aware verifier."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from uc_bench.case1_pilot_v1_rc5_verifier import verify_case1_rc5_submission
from uc_bench.mmmvp_open_rc17_trajectory import rc17_trajectory_replay_check


def rc5_trajectory_replay_check(
    project_root: Path,
    workspace: Path,
    store: Any,
    *,
    grade: dict[str, Any] | None,
    stop_condition: str | None,
) -> dict[str, Any]:
    return rc17_trajectory_replay_check(
        project_root,
        workspace,
        store,
        grade=grade,
        stop_condition=stop_condition,
        grader=verify_case1_rc5_submission,
    )


__all__ = ["rc5_trajectory_replay_check"]

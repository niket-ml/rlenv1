"""RC4 reconstruction and replay using the property-local verifier."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from uc_bench.case1_pilot_v1_rc4_verifier import verify_case1_rc4_submission
from uc_bench.mmmvp_open_rc17_trajectory import rc17_trajectory_replay_check


def rc4_trajectory_replay_check(
    project_root: Path,
    workspace: Path,
    store: Any,
    *,
    grade: dict[str, Any] | None,
    stop_condition: str | None,
) -> dict[str, Any]:
    """Replay the inherited lifecycle and recompute the RC4 grade exactly."""

    return rc17_trajectory_replay_check(
        project_root,
        workspace,
        store,
        grade=grade,
        stop_condition=stop_condition,
        grader=verify_case1_rc4_submission,
    )


__all__ = ["rc4_trajectory_replay_check"]

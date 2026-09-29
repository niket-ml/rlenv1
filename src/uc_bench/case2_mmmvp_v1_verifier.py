"""Canonical production verifier for the final Case 2 MMMVP release.

Only the two separately locked and validated general corrections are composed:
non-failing numerical representation warnings and causal containment of optional
diagnostics. All scientific reconstruction remains owned by the predecessor
verifier chain.
"""

from __future__ import annotations

from typing import Any

from development.case2_optionality_repair.scorer import (
    evaluate_case2_submission as _validated_optionality_verifier,
)


def grade_case2_submission(
    workspace: Any,
    submission: Any,
    *,
    require_host_process: bool = True,
):
    """Grade one Case 2 submission through the sole release authority."""

    return _validated_optionality_verifier(
        workspace,
        submission,
        require_host_process=require_host_process,
    )


# One public grading entry point; the alias is intentionally not exported.
__all__ = ["grade_case2_submission"]

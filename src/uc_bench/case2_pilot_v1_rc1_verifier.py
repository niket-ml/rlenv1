"""Thin hidden verifier for the unfrozen Case 2 RC1 candidate.

All scientific predicates are evaluated by the public semantic engine.  This
wrapper adds no disposition, resource, identity, threshold, or prose rule.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from uc_bench.case2_pilot_v1_rc1_semantics import OpenGrade, evaluate_case2_submission


def verify_case2_rc1_submission(workspace: Path, submission: Any) -> OpenGrade:
    return evaluate_case2_submission(workspace, submission)


__all__ = ["verify_case2_rc1_submission"]

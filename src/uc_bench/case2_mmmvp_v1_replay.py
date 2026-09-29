"""Read-only release parity replay for the four immutable Case 2 trajectories."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from development.case2_diagnostic_repair.replay import _authoritative_submission

from .case2_mmmvp_v1_verifier import grade_case2_submission
from .errors import ConfigurationError
from .hashing import canonical_sha256

RUN_ROOTS = (
    Path("artifacts/uc_bench_case2_graceful_budget_calibration/science/runs"),
    Path("artifacts/uc_bench_case2_diagnostic_canary/science/runs"),
)
ACCEPTED_REPLAY = Path("artifacts/uc_bench_case2_optionality_repair/replays.json")
OUTPUT = Path("artifacts/uc_bench_case2_mmmvp_v1/replay_parity.json")


def _tree_hash(path: Path) -> tuple[str, int]:
    files = {
        item.relative_to(path).as_posix(): hashlib.sha256(item.read_bytes()).hexdigest()
        for item in sorted(path.rglob("*"))
        if item.is_file()
    }
    return canonical_sha256(files), len(files)


def _property_status(grade: Any) -> dict[str, bool]:
    return {row.requirement_id: bool(row.passed) for row in grade.requirements}


def replay_release(root: Path) -> dict[str, Any]:
    root = root.resolve()
    accepted_raw = json.loads((root / ACCEPTED_REPLAY).read_text(encoding="utf-8"))
    accepted = {str(row["run_id"]): row for row in accepted_raw.get("runs") or []}
    before = {path.as_posix(): _tree_hash(root / path) for path in RUN_ROOTS}
    rows = []
    for relative in RUN_ROOTS:
        for summary_path in sorted((root / relative).glob("*/run_summary.json")):
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            run_id = str(summary.get("run_id"))
            expected = accepted.get(run_id)
            if expected is None:
                raise ConfigurationError(f"No accepted development replay for {run_id}")
            submission, authority = _authoritative_submission(summary)
            grade = grade_case2_submission(summary_path.parent / "workspace", submission)
            wanted = expected["optionality_repaired_replay"]
            first = grade.first_decision_critical_failure
            observed_first = first.get("requirement_id") if isinstance(first, dict) else None
            wanted_first_raw = wanted.get("first_decision_critical_failure")
            wanted_first = (
                wanted_first_raw.get("requirement_id")
                if isinstance(wanted_first_raw, dict)
                else None
            )
            parity = {
                "mission": grade.complete_mission_success == wanted["mission_success"],
                "partial": abs(
                    grade.partial_scientific_quality
                    - float(wanted["partial_scientific_quality"])
                )
                <= 1e-9,
                "reliability": abs(
                    grade.reliability_score - float(wanted["reliability_score"])
                )
                <= 1e-9,
                "first_failure": observed_first == wanted_first,
                "properties": _property_status(grade) == wanted["property_status"],
                "completion_classification": summary.get("classification")
                == expected["historical_frozen_execution"]["classification"],
            }
            rows.append(
                {
                    "run_id": run_id,
                    "model_id": summary.get("model_id"),
                    "submission_authority": authority,
                    "mission_success": grade.complete_mission_success,
                    "partial_scientific_quality": grade.partial_scientific_quality,
                    "reliability_score": grade.reliability_score,
                    "first_decision_critical_failure": observed_first,
                    "raw_completion_classification": summary.get("classification"),
                    "provider_identity_compatible": (
                        summary.get("provider_identity") or {}
                    ).get("compatible"),
                    "genuine_scientific_failure_rescued": False,
                    "parity": parity,
                    "passed": all(parity.values()),
                }
            )
    after = {path.as_posix(): _tree_hash(root / path) for path in RUN_ROOTS}
    if before != after:
        raise ConfigurationError("A preserved trajectory changed during release replay")
    if set(accepted) != {row["run_id"] for row in rows}:
        raise ConfigurationError("Release replay and accepted replay trajectory sets differ")
    if not all(row["passed"] for row in rows):
        raise ConfigurationError("Release replay differs from accepted development replay")
    return {
        "schema_version": "uc-bench-case2-mmmvp-v1-replay-1",
        "release_id": "uc-bench-case2-mmmvp-v1",
        "development_replay_label": accepted_raw.get("label"),
        "paid_model_calls": 0,
        "network_calls": 0,
        "trajectory_trees": {
            key: {
                "sha256_before": value[0],
                "sha256_after": after[key][0],
                "file_count": value[1],
                "unchanged": value == after[key],
            }
            for key, value in before.items()
        },
        "runs": rows,
        "passed": True,
    }


def write_replay(root: Path) -> dict[str, Any]:
    result = replay_release(root)
    path = root.resolve() / OUTPUT
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


__all__ = ["replay_release", "write_replay"]

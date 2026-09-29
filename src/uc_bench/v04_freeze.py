"""Immutable file manifest for the v0.4 development calibration."""

from __future__ import annotations

from pathlib import Path

from uc_bench.hashing import sha256_file

V04_FROZEN_FILES = {
    "calibration_config": Path("configs/hard_suite_v04_calibration.json"),
    "suite": Path("configs/hard_suite_v04.json"),
    "heldout": Path("grader_private/hard_suite_v04_heldout.json"),
    "ladder_spec": Path("grader_private/hard_suite_v04_ladders.json"),
    "controls": Path("artifacts/diagnostics/hard_suite_v04_controls.json"),
    "ladder_results": Path("artifacts/diagnostics/hard_suite_v04_ladders.json"),
    "task": Path("tasks/hard_suite_v04/TASK.md"),
    "commitment_schema": Path(
        "tasks/hard_suite_v04/schemas/commitment.schema.json"
    ),
    "submission_schema": Path(
        "tasks/hard_suite_v04/schemas/final_submission.schema.json"
    ),
    "generator_grader": Path("src/uc_bench/hard_suite_v04.py"),
    "ladder_generator": Path("src/uc_bench/v04_ladders.py"),
    "isolated_runner": Path("src/uc_bench/hard_suite_v04_runner.py"),
    "freeze_contract": Path("src/uc_bench/v04_freeze.py"),
    "calibration_orchestrator": Path("scripts/run_v04_calibration.py"),
}


def v04_frozen_hashes(project_root: Path) -> dict[str, str]:
    root = project_root.resolve()
    return {
        name: sha256_file(root / relative)
        for name, relative in V04_FROZEN_FILES.items()
    }

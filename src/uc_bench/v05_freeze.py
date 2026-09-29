"""Immutable file manifest for the v0.5 bounded development pilot."""

from __future__ import annotations

from pathlib import Path

from uc_bench.hashing import sha256_file

V05_FROZEN_FILES = {
    "suite": Path("configs/hard_suite_v05.json"),
    "calibration": Path("configs/hard_suite_v05_calibration.json"),
    "heldout": Path("grader_private/hard_suite_v05_heldout.json"),
    "development_ladders": Path("configs/hard_suite_v05_ladders.json"),
    "heldout_ladders": Path("grader_private/hard_suite_v05_ladders.json"),
    "controls": Path("artifacts/diagnostics/hard_suite_v05_controls.json"),
    "task": Path("tasks/hard_suite_v05/TASK.md"),
    "commitment_schema": Path("tasks/hard_suite_v05/schemas/commitment.schema.json"),
    "assessment_schema": Path("tasks/hard_suite_v05/schemas/validation_assessment.schema.json"),
    "submission_schema": Path("tasks/hard_suite_v05/schemas/final_submission.schema.json"),
    "generator_grader": Path("src/uc_bench/hard_suite_v05.py"),
    "isolated_runner": Path("src/uc_bench/hard_suite_v05_runner.py"),
    "freeze_contract": Path("src/uc_bench/v05_freeze.py"),
    "freeze_script": Path("scripts/freeze_v05.py"),
    "calibration_orchestrator": Path("scripts/run_v05_calibration.py"),
    "construct_audit": Path("audit/evidence/stage_08_HARD_SUITE_V05.md"),
    "suite_specification": Path("docs/HARD_SUITE_V05_SPEC.md"),
}


def v05_frozen_hashes(project_root: Path) -> dict[str, str]:
    root = project_root.resolve()
    return {name: sha256_file(root / relative) for name, relative in V05_FROZEN_FILES.items()}

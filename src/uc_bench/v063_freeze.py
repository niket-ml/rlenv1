"""Freeze contract for the total-grader, checkpoint-safe v0.6.3 successor."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.hashing import sha256_file
from uc_bench.v06_freeze import v06_runtime_versions
from uc_bench.v062_freeze import V062_FROZEN_PATHS, read_v062_freeze_manifest

V063_FREEZE_PATH = Path("artifacts/diagnostics/hard_suite_v063_freeze.json")
V062_SCIENCE_RUN = Path(
    "build/hard_suite_v06_runs/"
    "hard62-gpt-5.6-sol-dev6_clean_progression-0-20260908T194210Z"
)
V063_STATIC_FROZEN_PATHS = (
    *V062_FROZEN_PATHS,
    "artifacts/diagnostics/hard_suite_v062_freeze.json",
    "artifacts/diagnostics/hard_suite_v062_calibration_runs.json",
    "artifacts/diagnostics/hard_suite_v062_grader_no_go.json",
    "reports/generated/hard_suite_v062_grader_no_go.md",
    "configs/hard_suite_v063_execution.json",
    "artifacts/diagnostics/hard_suite_v063_cost_plan.json",
    "artifacts/diagnostics/hard_suite_v063_grader_controls.json",
    "src/uc_bench/v063_grader.py",
    "src/uc_bench/v063_runner.py",
    "src/uc_bench/v063_freeze.py",
    "scripts/build_v063_cost_plan.py",
    "scripts/build_v063_grader_controls.py",
    "scripts/freeze_v063.py",
    "scripts/run_v063_pilot.py",
    "scripts/analyze_v063_probe.py",
    "tests/test_v063_grader.py",
    "tests/test_v063_infrastructure.py",
)


def _captured_v062_paths(root: Path) -> tuple[str, ...]:
    captured = root / V062_SCIENCE_RUN
    if not captured.is_dir():
        raise ConfigurationError("The paid v0.6.2 trajectory is missing")
    rows = tuple(
        path.relative_to(root).as_posix()
        for path in sorted(captured.rglob("*"))
        if path.is_file()
    )
    if not rows:
        raise ConfigurationError("The paid v0.6.2 trajectory is empty")
    return rows


def v063_frozen_paths(project_root: Path) -> tuple[str, ...]:
    root = project_root.resolve()
    return tuple(dict.fromkeys((*V063_STATIC_FROZEN_PATHS, *_captured_v062_paths(root))))


def v063_frozen_hashes(project_root: Path) -> dict[str, str]:
    root = project_root.resolve()
    read_v062_freeze_manifest(root)
    result = {}
    for relative in v063_frozen_paths(root):
        path = root / relative
        if not path.is_file():
            raise ConfigurationError(f"Required v0.6.3 freeze input is missing: {relative}")
        result[relative] = sha256_file(path)
    return result


def validate_v063_freeze_manifest(
    project_root: Path,
    manifest: dict[str, Any],
) -> None:
    root = project_root.resolve()
    parent = read_v062_freeze_manifest(root)
    if manifest.get("schema_version") != "0.6.3-freeze-1":
        raise ConfigurationError("Unknown v0.6.3 freeze schema")
    if manifest.get("status") != "frozen":
        raise ConfigurationError("v0.6.3 is not frozen")
    if manifest.get("parent_v062_hash_set_digest") != parent["hash_set_digest"]:
        raise ConfigurationError("v0.6.3 parent v0.6.2 freeze changed")
    for field in (
        "scientific_tasks_changed_from_v06",
        "scientific_prompts_changed_from_v06",
        "scientific_thresholds_changed_from_v06",
        "scientific_scoring_invariants_changed_from_v06",
    ):
        if manifest.get(field) is not False:
            raise ConfigurationError(f"v0.6.3 invalid change marker: {field}")
    if manifest.get("grader_implementation_changed_from_v06") is not True:
        raise ConfigurationError("v0.6.3 did not disclose its grader repair")
    if manifest.get("v063_scientific_model_responses_before_freeze") != 0:
        raise ConfigurationError("v0.6.3 records a pre-freeze response")
    if manifest.get("predecessor_scientific_model_response_count") != 1:
        raise ConfigurationError("v0.6.3 lost the v0.6.2 development exposure")
    if manifest.get("heldout_exposure_count") != 0:
        raise ConfigurationError("v0.6.3 records held-out exposure")
    if manifest.get("astra_exposure_count") != 0:
        raise ConfigurationError("v0.6.3 records Astra exposure")
    if manifest.get("hashes") != v063_frozen_hashes(root):
        raise ConfigurationError("A frozen v0.6.3 input changed")
    if manifest.get("runtime_versions") != v06_runtime_versions():
        raise ConfigurationError("The frozen v0.6.3 runtime versions changed")


def read_v063_freeze_manifest(project_root: Path) -> dict[str, Any]:
    path = project_root.resolve() / V063_FREEZE_PATH
    if not path.is_file():
        raise ConfigurationError("v0.6.3 freeze manifest is absent")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError("v0.6.3 freeze manifest is not an object")
    validate_v063_freeze_manifest(project_root, value)
    return value

"""Freeze contract for the full-stack-validated infrastructure-only v0.6.2."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.hashing import sha256_file
from uc_bench.v06_freeze import v06_runtime_versions
from uc_bench.v061_freeze import V061_FROZEN_PATHS, read_v061_freeze_manifest

V062_FREEZE_PATH = Path("artifacts/diagnostics/hard_suite_v062_freeze.json")
V061_FAILED_RUN = (
    "build/hard_suite_v06_runs/"
    "hard61-gpt-5.6-sol-dev6_clean_progression-0-20260908T190304Z"
)
V062_FROZEN_PATHS = (
    *V061_FROZEN_PATHS,
    "artifacts/diagnostics/hard_suite_v061_freeze.json",
    "artifacts/diagnostics/hard_suite_v061_calibration_runs.json",
    f"{V061_FAILED_RUN}/request_ledger.json",
    f"{V061_FAILED_RUN}/run_summary.json",
    f"{V061_FAILED_RUN}/verifiers_output.json",
    "configs/hard_suite_v062_execution.json",
    "src/uc_bench/v062_provider.py",
    "src/uc_bench/v062_runner.py",
    "src/uc_bench/v062_freeze.py",
    "scripts/run_v062_full_stack_compatibility.py",
    "scripts/run_v062_pilot.py",
    "scripts/freeze_v062.py",
    "scripts/analyze_v062_probe.py",
    "tests/test_v062_infrastructure.py",
    "artifacts/diagnostics/hard_suite_v062_full_stack_compatibility.json",
    "artifacts/diagnostics/hard_suite_v062_full_stack_compatibility_attempts/openai-gpt-5-6-sol-0.json",
    "artifacts/diagnostics/hard_suite_v062_full_stack_compatibility_attempts/anthropic-claude-opus-5-0.json",
    "artifacts/diagnostics/hard_suite_v062_full_stack_compatibility_attempts/google-gemini-3-1-pro-preview-0.json",
    "artifacts/diagnostics/hard_suite_v062_full_stack_compatibility_attempts/moonshotai-kimi-k3-0.json",
    "artifacts/diagnostics/hard_suite_v062_full_stack_compatibility_attempts/openai-gpt-5-2-0.json",
)


def v062_frozen_hashes(project_root: Path) -> dict[str, str]:
    root = project_root.resolve()
    read_v061_freeze_manifest(root)
    result = {}
    for relative in V062_FROZEN_PATHS:
        path = root / relative
        if not path.is_file():
            raise ConfigurationError(f"Required v0.6.2 freeze input is missing: {relative}")
        result[relative] = sha256_file(path)
    return result


def validate_v062_freeze_manifest(
    project_root: Path, manifest: dict[str, Any]
) -> None:
    root = project_root.resolve()
    parent = read_v061_freeze_manifest(root)
    if manifest.get("schema_version") != "0.6.2-freeze-1":
        raise ConfigurationError("Unknown v0.6.2 freeze schema")
    if manifest.get("status") != "frozen":
        raise ConfigurationError("v0.6.2 is not frozen")
    if manifest.get("parent_v061_hash_set_digest") != parent["hash_set_digest"]:
        raise ConfigurationError("v0.6.2 parent v0.6.1 freeze changed")
    for field in (
        "scientific_tasks_changed_from_v06",
        "scientific_grader_changed_from_v06",
        "scientific_thresholds_changed_from_v06",
    ):
        if manifest.get(field) is not False:
            raise ConfigurationError(f"v0.6.2 invalid change marker: {field}")
    if manifest.get("scientific_model_responses_before_freeze") != 0:
        raise ConfigurationError("v0.6.2 records a pre-freeze scientific response")
    if manifest.get("heldout_exposure_count") != 0:
        raise ConfigurationError("v0.6.2 records held-out exposure")
    if manifest.get("astra_exposure_count") != 0:
        raise ConfigurationError("v0.6.2 records Astra exposure")
    if manifest.get("hashes") != v062_frozen_hashes(root):
        raise ConfigurationError("A frozen v0.6.2 input changed")
    if manifest.get("runtime_versions") != v06_runtime_versions():
        raise ConfigurationError("The frozen v0.6.2 runtime versions changed")


def read_v062_freeze_manifest(project_root: Path) -> dict[str, Any]:
    path = project_root.resolve() / V062_FREEZE_PATH
    if not path.is_file():
        raise ConfigurationError("v0.6.2 freeze manifest is absent")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError("v0.6.2 freeze manifest is not an object")
    validate_v062_freeze_manifest(project_root, value)
    return value

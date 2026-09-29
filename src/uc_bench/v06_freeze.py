"""Hash contract for the one-time v0.6 pre-scientific-exposure freeze."""

from __future__ import annotations

import json
import platform
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.hashing import sha256_file

V06_FROZEN_PATHS = (
    "configs/hard_suite_v06.json",
    "configs/hard_suite_v06_model_panel.json",
    "configs/hard_suite_v06_execution.json",
    "grader_private/hard_suite_v06_heldout.json",
    "tasks/hard_suite_v06/TASK.md",
    "tasks/hard_suite_v06/schemas/committed_validation_plan.schema.json",
    "tasks/hard_suite_v06/schemas/endpoint_audit.schema.json",
    "tasks/hard_suite_v06/schemas/final_diligence_report.schema.json",
    "tasks/hard_suite_v06/schemas/preprocessing_lineage.schema.json",
    "tasks/hard_suite_v06/schemas/provenance_audit.schema.json",
    "tasks/hard_suite_v06/schemas/resource_value_memo.schema.json",
    "tasks/hard_suite_v06/schemas/validation_results.schema.json",
    "src/uc_bench/hard_suite_v05.py",
    "src/uc_bench/hard_suite_v06.py",
    "src/uc_bench/hard_suite_v06_runner.py",
    "src/uc_bench/v06_provider.py",
    "src/uc_bench/v06_probe_analysis.py",
    "src/uc_bench/v06_freeze.py",
    "src/uc_bench/errors.py",
    "src/uc_bench/hashing.py",
    "src/uc_bench/openrouter.py",
    "src/uc_bench/openrouter_catalog.py",
    "src/uc_bench/docker_runtime.py",
    "src/uc_bench/model_runner.py",
    "scripts/run_v06_pilot.py",
    "scripts/analyze_v06_probe.py",
    "scripts/freeze_v06.py",
    "scripts/build_v06_cost_plan.py",
    "artifacts/diagnostics/hard_suite_v06_controls.json",
    "artifacts/diagnostics/hard_suite_v06_compatibility.json",
    "artifacts/diagnostics/hard_suite_v06_cost_plan.json",
    "docker/agent.Dockerfile",
    "pyproject.toml",
)

V06_RUNTIME_PACKAGES = (
    "datasets",
    "jsonschema",
    "numpy",
    "openai",
    "pandas",
    "pydantic",
    "scikit-learn",
    "verifiers",
)


def v06_runtime_versions() -> dict[str, str]:
    result = {"python": platform.python_version()}
    for package in V06_RUNTIME_PACKAGES:
        try:
            result[package] = version(package)
        except PackageNotFoundError as exc:
            raise ConfigurationError(
                f"Required v0.6 runtime package is absent: {package}"
            ) from exc
    return result


def v06_frozen_hashes(project_root: Path) -> dict[str, str]:
    root = project_root.resolve()
    result: dict[str, str] = {}
    for relative in V06_FROZEN_PATHS:
        path = root / relative
        if not path.is_file():
            raise ConfigurationError(f"Required v0.6 freeze input is missing: {relative}")
        result[relative] = sha256_file(path)
    return result


def validate_v06_freeze_manifest(project_root: Path, manifest: dict[str, Any]) -> None:
    if manifest.get("schema_version") != "0.6-freeze-1":
        raise ConfigurationError("Unknown v0.6 freeze schema")
    if manifest.get("frozen_before_scientific_model_calls") is not True:
        raise ConfigurationError("v0.6 was not frozen before scientific model calls")
    if manifest.get("astra_exposure_count") != 0:
        raise ConfigurationError("v0.6 freeze records an Astra exposure")
    if manifest.get("heldout_exposure_count") != 0:
        raise ConfigurationError("v0.6 freeze records held-out exposure")
    expected = v06_frozen_hashes(project_root)
    if manifest.get("hashes") != expected:
        raise ConfigurationError("A frozen v0.6 input changed")
    if manifest.get("runtime_versions") != v06_runtime_versions():
        raise ConfigurationError("The frozen v0.6 runtime versions changed")


def read_v06_freeze_manifest(project_root: Path) -> dict[str, Any]:
    path = project_root.resolve() / "artifacts/diagnostics/hard_suite_v06_freeze.json"
    if not path.is_file():
        raise ConfigurationError("v0.6 freeze manifest is absent")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError("v0.6 freeze manifest is not an object")
    validate_v06_freeze_manifest(project_root, value)
    return value

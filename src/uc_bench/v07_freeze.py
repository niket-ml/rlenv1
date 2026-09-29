"""Immutable one-time freeze contract for the bounded v0.7 development pilot."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256, sha256_file
from uc_bench.v06_freeze import v06_runtime_versions

FREEZE_PATH = Path("artifacts/diagnostics/hard_suite_v07_freeze.json")

STATIC_PATHS = (
    "configs/hard_suite_v07.json",
    "configs/hard_suite_v07_model_panel.json",
    "configs/hard_suite_v07_execution.json",
    "src/uc_bench/hard_suite_v07.py",
    "src/uc_bench/v07_cases.py",
    "src/uc_bench/v07_environment.py",
    "src/uc_bench/v07_grader.py",
    "src/uc_bench/v07_metrics.py",
    "src/uc_bench/v07_provider.py",
    "src/uc_bench/v07_runner.py",
    "src/uc_bench/v07_analysis.py",
    "src/uc_bench/v07_freeze.py",
    "src/uc_bench/v06_provider.py",
    "src/uc_bench/v061_provider.py",
    "src/uc_bench/v062_provider.py",
    "src/uc_bench/docker_runtime.py",
    "src/uc_bench/model_runner.py",
    "scripts/build_v07_controls.py",
    "scripts/build_v07_dependency_gate.py",
    "scripts/check_v07_exact_payload.py",
    "scripts/check_v07_live_gate.py",
    "scripts/freeze_v07.py",
    "scripts/run_v07_pilot.py",
    "scripts/analyze_v07.py",
    "tests/test_hard_suite_v07.py",
    "tests/test_v07_dependency_contract.py",
    "tests/test_v07_infrastructure.py",
    "artifacts/diagnostics/hard_suite_v07_controls.json",
    "artifacts/diagnostics/hard_suite_v07_dependency_gate.json",
    "artifacts/diagnostics/hard_suite_v07_exact_payload_compatibility.json",
    "artifacts/diagnostics/hard_suite_v07_pre_freeze_live_gate.json",
    "artifacts/diagnostics/hard_suite_v07_cost_plan.json",
    "artifacts/diagnostics/hard_suite_v07_case_validity_cards.json",
    "artifacts/diagnostics/hard_suite_v07_failure_remedy_map.json",
    "artifacts/diagnostics/hard_suite_v07_intervention_design.json",
    "artifacts/diagnostics/hard_suite_v07_reset_traceability.json",
    "artifacts/diagnostics/hard_suite_v061_exact_payload_compatibility_adjudication.json",
    "artifacts/diagnostics/hard_suite_v062_full_stack_compatibility.json",
    "docs/HARD_SUITE_V07_SPEC.md",
    "reports/generated/hard_suite_v07_preapproval.md",
    "docker/agent.Dockerfile",
    "pyproject.toml",
)


def _dynamic_paths(root: Path, relative_root: str) -> list[str]:
    directory = root / relative_root
    if not directory.is_dir():
        raise ConfigurationError(f"Freeze directory is missing: {relative_root}")
    return [
        path.relative_to(root).as_posix()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    ]


def v07_frozen_paths(project_root: Path) -> tuple[str, ...]:
    root = project_root.resolve()
    values = [
        *STATIC_PATHS,
        *_dynamic_paths(root, "tasks/hard_suite_v07/development"),
        *_dynamic_paths(root, "grader_private/hard_suite_v07"),
    ]
    return tuple(dict.fromkeys(values))


def v07_frozen_hashes(project_root: Path) -> dict[str, str]:
    root = project_root.resolve()
    result: dict[str, str] = {}
    for relative in v07_frozen_paths(root):
        path = root / relative
        if not path.is_file():
            raise ConfigurationError(f"Required v0.7 freeze input is missing: {relative}")
        result[relative] = sha256_file(path)
    return result


def validate_v07_freeze_manifest(project_root: Path, manifest: dict[str, Any]) -> None:
    root = project_root.resolve()
    if manifest.get("schema_version") != "0.7-freeze-1" or manifest.get("status") != "frozen":
        raise ConfigurationError("v0.7 freeze status or schema is invalid")
    if manifest.get("immutable") is not True:
        raise ConfigurationError("v0.7 freeze is not immutable")
    if manifest.get("scientific_model_responses_before_freeze") != 0:
        raise ConfigurationError("v0.7 records pre-freeze scientific exposure")
    if manifest.get("heldout_exposure_count") != 0 or manifest.get("astra_exposure_count") != 0:
        raise ConfigurationError("v0.7 freeze records forbidden exposure")
    if manifest.get("condition_count") != 5 or manifest.get("episode_count") != 10:
        raise ConfigurationError("v0.7 frozen matrix is not the approved ten cells")
    if manifest.get("dependency_invariant_count") != 10:
        raise ConfigurationError("v0.7 dependency gate is incomplete")
    hashes = v07_frozen_hashes(root)
    if manifest.get("hashes") != hashes:
        raise ConfigurationError("A frozen v0.7 input changed")
    if manifest.get("hash_set_digest") != canonical_sha256(hashes):
        raise ConfigurationError("v0.7 freeze digest is inconsistent")
    if manifest.get("runtime_versions") != v06_runtime_versions():
        raise ConfigurationError("The frozen v0.7 runtime changed")


def read_v07_freeze_manifest(project_root: Path) -> dict[str, Any]:
    path = project_root.resolve() / FREEZE_PATH
    if not path.is_file():
        raise ConfigurationError("v0.7 freeze manifest is absent")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError("v0.7 freeze manifest must be an object")
    validate_v07_freeze_manifest(project_root, value)
    return value

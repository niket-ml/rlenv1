"""Freeze contract for the infrastructure-only v0.6.1 successor."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.hashing import sha256_file
from uc_bench.v06_freeze import (
    V06_FROZEN_PATHS,
    read_v06_freeze_manifest,
    v06_runtime_versions,
)

V061_FREEZE_PATH = Path("artifacts/diagnostics/hard_suite_v061_freeze.json")
V061_FROZEN_PATHS = (
    *V06_FROZEN_PATHS,
    "artifacts/diagnostics/hard_suite_v06_freeze.json",
    "configs/hard_suite_v061_execution.json",
    "src/uc_bench/v061_provider.py",
    "src/uc_bench/v061_runner.py",
    "src/uc_bench/v061_freeze.py",
    "scripts/run_v061_exact_compatibility.py",
    "scripts/adjudicate_v061_exact_compatibility.py",
    "scripts/run_v061_pilot.py",
    "scripts/freeze_v061.py",
    "scripts/analyze_v061_probe.py",
    "tests/test_v061_infrastructure.py",
    "artifacts/diagnostics/hard_suite_v061_exact_payload_compatibility.json",
    "artifacts/diagnostics/hard_suite_v061_exact_payload_compatibility_v2.json",
    "artifacts/diagnostics/hard_suite_v061_exact_payload_compatibility_adjudication.json",
    "artifacts/diagnostics/hard_suite_v061_exact_payload_compatibility_attempts/openai-gpt-5-6-sol.json",
    "artifacts/diagnostics/hard_suite_v061_exact_payload_compatibility_attempts/anthropic-claude-opus-5.json",
    "artifacts/diagnostics/hard_suite_v061_exact_payload_compatibility_attempts/google-gemini-3-1-pro-preview.json",
    "artifacts/diagnostics/hard_suite_v061_exact_payload_compatibility_attempts/moonshotai-kimi-k3.json",
    "artifacts/diagnostics/hard_suite_v061_exact_payload_compatibility_attempts/openai-gpt-5-2.json",
    "artifacts/diagnostics/hard_suite_v061_exact_payload_compatibility_v2_attempts/openai-gpt-5-6-sol.json",
    "artifacts/diagnostics/hard_suite_v061_exact_payload_compatibility_v2_attempts/anthropic-claude-opus-5.json",
    "artifacts/diagnostics/hard_suite_v061_exact_payload_compatibility_v2_attempts/google-gemini-3-1-pro-preview.json",
    "artifacts/diagnostics/hard_suite_v061_exact_payload_compatibility_v2_attempts/moonshotai-kimi-k3.json",
    "artifacts/diagnostics/hard_suite_v061_exact_payload_compatibility_v2_attempts/openai-gpt-5-2.json",
)


def v061_frozen_hashes(project_root: Path) -> dict[str, str]:
    root = project_root.resolve()
    read_v06_freeze_manifest(root)
    result = {}
    for relative in V061_FROZEN_PATHS:
        path = root / relative
        if not path.is_file():
            raise ConfigurationError(f"Required v0.6.1 freeze input is missing: {relative}")
        result[relative] = sha256_file(path)
    return result


def validate_v061_freeze_manifest(
    project_root: Path, manifest: dict[str, Any]
) -> None:
    root = project_root.resolve()
    parent = read_v06_freeze_manifest(root)
    if manifest.get("schema_version") != "0.6.1-freeze-1":
        raise ConfigurationError("Unknown v0.6.1 freeze schema")
    if manifest.get("status") != "frozen":
        raise ConfigurationError("v0.6.1 is not frozen")
    if manifest.get("parent_v06_hash_set_digest") != parent["hash_set_digest"]:
        raise ConfigurationError("v0.6.1 parent v0.6 freeze changed")
    if manifest.get("scientific_tasks_changed_from_v06") is not False:
        raise ConfigurationError("v0.6.1 changed the frozen scientific tasks")
    if manifest.get("scientific_model_responses_before_freeze") != 0:
        raise ConfigurationError("v0.6.1 records pre-freeze scientific responses")
    if manifest.get("heldout_exposure_count") != 0:
        raise ConfigurationError("v0.6.1 records held-out exposure")
    if manifest.get("astra_exposure_count") != 0:
        raise ConfigurationError("v0.6.1 records Astra exposure")
    if manifest.get("hashes") != v061_frozen_hashes(root):
        raise ConfigurationError("A frozen v0.6.1 input changed")
    if manifest.get("runtime_versions") != v06_runtime_versions():
        raise ConfigurationError("The frozen v0.6.1 runtime versions changed")


def read_v061_freeze_manifest(project_root: Path) -> dict[str, Any]:
    path = project_root.resolve() / V061_FREEZE_PATH
    if not path.is_file():
        raise ConfigurationError("v0.6.1 freeze manifest is absent")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError("v0.6.1 freeze manifest is not an object")
    validate_v061_freeze_manifest(project_root, value)
    return value

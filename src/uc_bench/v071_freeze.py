"""Immutable infrastructure-successor freeze layered over v0.7 science."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256, sha256_file
from uc_bench.v06_freeze import v06_runtime_versions
from uc_bench.v07_freeze import read_v07_freeze_manifest

FREEZE_PATH = Path("artifacts/diagnostics/hard_suite_v071_freeze.json")
LOCAL_GATE_PATH = Path("artifacts/diagnostics/hard_suite_v071_local_gate.json")
LIVE_CANARY_PATH = Path("artifacts/diagnostics/hard_suite_v071_live_canary.json")

INFRASTRUCTURE_PATHS = (
    "configs/hard_suite_v071_infrastructure.json",
    "src/uc_bench/v071_auth.py",
    "src/uc_bench/v071_runner.py",
    "src/uc_bench/v071_freeze.py",
    "scripts/check_v071_local_gate.py",
    "scripts/run_v071_live_canary.py",
    "scripts/freeze_v071.py",
    "scripts/run_v071_pilot.py",
    "tests/test_v071_infrastructure.py",
    "artifacts/diagnostics/hard_suite_v07_infrastructure_no_go.json",
    LOCAL_GATE_PATH.as_posix(),
    LIVE_CANARY_PATH.as_posix(),
)


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError(f"Expected object: {path}")
    return value


def v071_scientific_hashes(project_root: Path) -> dict[str, str]:
    """Return the exact validated v0.7 scientific freeze hash mapping."""

    return dict(read_v07_freeze_manifest(project_root.resolve())["hashes"])


def v071_infrastructure_hashes(project_root: Path) -> dict[str, str]:
    root = project_root.resolve()
    values: dict[str, str] = {}
    for relative in INFRASTRUCTURE_PATHS:
        path = root / relative
        if not path.is_file():
            raise ConfigurationError(f"Required v0.7.1 infrastructure file is missing: {relative}")
        values[relative] = sha256_file(path)
    return values


def v071_frozen_hashes(project_root: Path) -> dict[str, str]:
    values = v071_scientific_hashes(project_root)
    overlap = set(values) & set(INFRASTRUCTURE_PATHS)
    if overlap:
        raise ConfigurationError(
            f"v0.7.1 infrastructure overlaps frozen science: {sorted(overlap)}"
        )
    values.update(v071_infrastructure_hashes(project_root))
    return values


def validate_v071_pre_freeze_gates(project_root: Path) -> None:
    root = project_root.resolve()
    parent = read_v07_freeze_manifest(root)
    no_go = _read_object(root / "artifacts/diagnostics/hard_suite_v07_infrastructure_no_go.json")
    if (
        no_go.get("status") != "frozen_no_go"
        or no_go.get("freeze_hash_set_digest") != parent["hash_set_digest"]
        or no_go.get("model_responses") != 0
        or no_go.get("response_reported_spend_usd") != 0.0
    ):
        raise ConfigurationError("The permanent v0.7 zero-spend no-go record is invalid")
    local = _read_object(root / LOCAL_GATE_PATH)
    if (
        local.get("status") != "passed"
        or local.get("parent_scientific_hash_set_digest") != parent["hash_set_digest"]
        or local.get("scientific_hash_mismatch_count") != 0
        or local.get("failed_command_count") != 0
    ):
        raise ConfigurationError("The v0.7.1 local engineering gate is not passed")
    live = _read_object(root / LIVE_CANARY_PATH)
    if (
        live.get("status") != "passed"
        or live.get("scientific_requests") != 0
        or live.get("request_count") != 1
        or live.get("authentication_success") is not True
        or live.get("credential_leakage_detected") is not False
        or float(live.get("spend_guard_value_usd") or 0.0) > 0.25
    ):
        raise ConfigurationError("The v0.7.1 live production-path canary is not passed")


def validate_v071_freeze_manifest(project_root: Path, manifest: dict[str, Any]) -> None:
    root = project_root.resolve()
    parent = read_v07_freeze_manifest(root)
    if manifest.get("schema_version") != "0.7.1-freeze-1":
        raise ConfigurationError("Unknown v0.7.1 freeze schema")
    if manifest.get("status") != "frozen" or manifest.get("immutable") is not True:
        raise ConfigurationError("v0.7.1 is not immutable and frozen")
    if manifest.get("parent_v07_hash_set_digest") != parent["hash_set_digest"]:
        raise ConfigurationError("The v0.7 parent freeze changed")
    if manifest.get("scientific_hashes") != parent["hashes"]:
        raise ConfigurationError("v0.7.1 scientific hashes differ from v0.7")
    if manifest.get("scientific_content_changed_from_v07") is not False:
        raise ConfigurationError("v0.7.1 discloses a forbidden scientific change")
    if manifest.get("permitted_change") != "authentication_client_lifecycle_only":
        raise ConfigurationError("v0.7.1 has an unauthorized change scope")
    if manifest.get("v071_scientific_model_responses_before_freeze") != 0:
        raise ConfigurationError("v0.7.1 records scientific exposure before freeze")
    if manifest.get("heldout_exposure_count") != 0 or manifest.get("astra_exposure_count") != 0:
        raise ConfigurationError("v0.7.1 records forbidden exposure")
    if manifest.get("scientific_cap_usd") != 45.0:
        raise ConfigurationError("v0.7.1 scientific cap differs from v0.7")
    if manifest.get("combined_new_maximum_spend_usd") != 45.25:
        raise ConfigurationError("v0.7.1 combined cap is not $45.25")
    if manifest.get("hashes") != v071_frozen_hashes(root):
        raise ConfigurationError("A frozen v0.7.1 input changed")
    if manifest.get("hash_set_digest") != canonical_sha256(manifest["hashes"]):
        raise ConfigurationError("The v0.7.1 freeze digest is inconsistent")
    if manifest.get("runtime_versions") != v06_runtime_versions():
        raise ConfigurationError("The v0.7.1 runtime changed")
    validate_v071_pre_freeze_gates(root)


def read_v071_freeze_manifest(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    path = root / FREEZE_PATH
    if not path.is_file():
        raise ConfigurationError("v0.7.1 freeze manifest is absent")
    value = _read_object(path)
    validate_v071_freeze_manifest(root, value)
    return value

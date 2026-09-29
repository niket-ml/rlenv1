"""Immutable interface-and-grader successor freeze layered over v0.7 science."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256, sha256_file
from uc_bench.v06_freeze import v06_runtime_versions
from uc_bench.v071_freeze import read_v071_freeze_manifest

FREEZE_PATH = Path("artifacts/diagnostics/hard_suite_v072_freeze.json")
LOCAL_GATE_PATH = Path("artifacts/diagnostics/hard_suite_v072_local_gate.json")
EXACT_PAYLOAD_PATH = Path("artifacts/diagnostics/hard_suite_v072_exact_payload_compatibility.json")
CONTROLS_PATH = Path("artifacts/diagnostics/hard_suite_v072_controls.json")
REPLAY_ROOT = Path("artifacts/diagnostics/hard_suite_v072_replay_fixtures")
COST_PATH = Path("artifacts/diagnostics/hard_suite_v072_cost_plan.json")

INTERFACE_PATHS = (
    "configs/hard_suite_v072_interface.json",
    "docs/HARD_SUITE_V072_SUBMISSION.md",
    "src/uc_bench/v072_schema.py",
    "src/uc_bench/v072_artifacts.py",
    "src/uc_bench/v072_grader.py",
    "src/uc_bench/v072_environment.py",
    "src/uc_bench/v072_interface.py",
    "src/uc_bench/hard_suite_v072.py",
    "src/uc_bench/v072_replay.py",
    "src/uc_bench/v072_runner.py",
    "src/uc_bench/v072_freeze.py",
    "scripts/check_v072_exact_payload.py",
    "scripts/build_v072_controls.py",
    "scripts/replay_v072_grader_validation.py",
    "scripts/build_v072_cost_plan.py",
    "scripts/check_v072_local_gate.py",
    "scripts/freeze_v072.py",
    "scripts/run_v072_pilot.py",
    "tests/test_v072_grader.py",
    "tests/test_v072_interface.py",
    EXACT_PAYLOAD_PATH.as_posix(),
    CONTROLS_PATH.as_posix(),
    COST_PATH.as_posix(),
    LOCAL_GATE_PATH.as_posix(),
)


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError(f"Expected object: {path}")
    return value


def v072_scientific_hashes(project_root: Path) -> dict[str, str]:
    """Return the exact v0.7 scientific hash mapping carried through v0.7.1."""

    return dict(read_v071_freeze_manifest(project_root.resolve())["scientific_hashes"])


def _replay_paths(project_root: Path) -> list[str]:
    root = project_root.resolve()
    replay = root / REPLAY_ROOT
    if not replay.is_dir():
        raise ConfigurationError("The five-trajectory v0.7.2 replay fixture is absent")
    return [
        path.relative_to(root).as_posix() for path in sorted(replay.rglob("*")) if path.is_file()
    ]


def v072_interface_hashes(project_root: Path) -> dict[str, str]:
    root = project_root.resolve()
    values: dict[str, str] = {}
    for relative in [*INTERFACE_PATHS, *_replay_paths(root)]:
        path = root / relative
        if not path.is_file():
            raise ConfigurationError(f"Required v0.7.2 interface file is missing: {relative}")
        values[relative] = sha256_file(path)
    return values


def v072_frozen_hashes(project_root: Path) -> dict[str, str]:
    science = v072_scientific_hashes(project_root)
    interface = v072_interface_hashes(project_root)
    overlap = set(science) & set(interface)
    if overlap:
        raise ConfigurationError(f"v0.7.2 interface overlaps frozen science: {sorted(overlap)}")
    return {**science, **interface}


def validate_v072_pre_freeze_gates(project_root: Path) -> None:
    root = project_root.resolve()
    parent = read_v071_freeze_manifest(root)
    exact = _read_object(root / EXACT_PAYLOAD_PATH)
    controls = _read_object(root / CONTROLS_PATH)
    replay = _read_object(root / REPLAY_ROOT / "replay_summary.json")
    cost = _read_object(root / COST_PATH)
    local = _read_object(root / LOCAL_GATE_PATH)
    interface = _read_object(root / "configs/hard_suite_v072_interface.json")
    if exact.get("status") != "passed" or exact.get("new_provider_requests") != 0:
        raise ConfigurationError("The exact v0.7.2 provider payload gate is not passed")
    if controls.get("status") != "passed" or controls.get("new_api_requests") != 0:
        raise ConfigurationError("The v0.7.2 separation and anti-gaming controls failed")
    if (
        replay.get("status") != "passed"
        or replay.get("episode_count") != 5
        or replay.get("uniformly_capped") is not False
        or replay.get("new_api_requests") != 0
    ):
        raise ConfigurationError("The five-trajectory zero-cost replay gate failed")
    if cost.get("status") != "predeclared_no_paid_execution":
        raise ConfigurationError("The staged v0.7.2 cost plan is absent")
    stage_caps = [float(row["hard_cumulative_cap_usd"]) for row in cost["stages"]]
    if stage_caps != [5.0, 12.0, 45.0]:
        raise ConfigurationError("The staged spend caps changed")
    if (
        local.get("status") != "passed"
        or local.get("parent_scientific_hash_set_digest") != parent["parent_v07_hash_set_digest"]
        or local.get("scientific_hash_mismatch_count") != 0
        or local.get("failed_command_count") != 0
        or local.get("credential_leakage_detected") is not False
    ):
        raise ConfigurationError("The complete v0.7.2 local gate is not passed")
    if interface.get("scientific_global_cap_usd") != 45.0:
        raise ConfigurationError("The v0.7.2 interface changed the scientific cap")
    if (
        interface.get("heldout_requests_allowed") != 0
        or interface.get("astra_requests_allowed") != 0
    ):
        raise ConfigurationError("The v0.7.2 plan permits forbidden exposure")


def validate_v072_freeze_manifest(project_root: Path, manifest: dict[str, Any]) -> None:
    root = project_root.resolve()
    parent = read_v071_freeze_manifest(root)
    if manifest.get("schema_version") != "0.7.2-freeze-1":
        raise ConfigurationError("Unknown v0.7.2 freeze schema")
    if manifest.get("status") != "frozen" or manifest.get("immutable") is not True:
        raise ConfigurationError("v0.7.2 is not immutable and frozen")
    if manifest.get("parent_v071_hash_set_digest") != parent["hash_set_digest"]:
        raise ConfigurationError("The v0.7.1 parent freeze changed")
    if manifest.get("scientific_hashes") != parent["scientific_hashes"]:
        raise ConfigurationError("v0.7.2 scientific hashes differ from v0.7/v0.7.1")
    if manifest.get("scientific_content_changed_from_v07") is not False:
        raise ConfigurationError("v0.7.2 discloses a forbidden scientific change")
    if manifest.get("permitted_change") != "explicit_interface_and_grader_only":
        raise ConfigurationError("v0.7.2 has an unauthorized change scope")
    if manifest.get("scientific_model_responses_before_freeze") != 0:
        raise ConfigurationError("v0.7.2 records scientific exposure before freeze")
    if manifest.get("heldout_exposure_count") != 0 or manifest.get("astra_exposure_count") != 0:
        raise ConfigurationError("v0.7.2 records forbidden exposure")
    if manifest.get("scientific_cap_usd") != 45.0:
        raise ConfigurationError("v0.7.2 scientific cap differs from v0.7")
    if (
        manifest.get("checkpoint_weights") != parent["checkpoint_weights"]
        or manifest.get("sol_gate") != parent["sol_gate"]
        or manifest.get("two_model_gate") != parent["two_model_gate"]
        or manifest.get("failure_handling") != parent["failure_handling"]
    ):
        raise ConfigurationError("v0.7.2 changed a frozen scientific or stopping rule")
    if manifest.get("first_stage_cap_usd") != 5.0:
        raise ConfigurationError("v0.7.2 first-stage cap differs from the staged plan")
    if manifest.get("hashes") != v072_frozen_hashes(root):
        raise ConfigurationError("A frozen v0.7.2 input changed")
    if manifest.get("hash_set_digest") != canonical_sha256(manifest["hashes"]):
        raise ConfigurationError("The v0.7.2 freeze digest is inconsistent")
    if manifest.get("runtime_versions") != v06_runtime_versions():
        raise ConfigurationError("The v0.7.2 runtime changed")
    validate_v072_pre_freeze_gates(root)


def read_v072_freeze_manifest(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    path = root / FREEZE_PATH
    if not path.is_file():
        raise ConfigurationError("v0.7.2 freeze manifest is absent")
    value = _read_object(path)
    validate_v072_freeze_manifest(root, value)
    return value

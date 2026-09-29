"""Immutable release-candidate freeze for the audited open MMMVP."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256, sha256_file
from uc_bench.mmmvp_blind_interface import serialized_open_request

FREEZE_PATH = Path("artifacts/mmmvp_open_rc1/freeze.json")
LOCAL_GATE_PATH = Path("artifacts/mmmvp_open_rc1/local_gate.json")
AUDIT_PATH = Path("artifacts/mmmvp_open_rc1/open_endedness_audit.json")

_FIXED_FILES = (
    "configs/uc_bench_mmmvp_open_suite.json",
    "configs/uc_bench_mmmvp_open_model_panel.json",
    "src/uc_bench/mmmvp_blind_interface.py",
    "src/uc_bench/mmmvp_open_schema.py",
    "src/uc_bench/mmmvp_open_calculations.py",
    "src/uc_bench/mmmvp_open_interventions.py",
    "src/uc_bench/mmmvp_open_environment.py",
    "src/uc_bench/mmmvp_open_verifier.py",
    "src/uc_bench/mmmvp_open_controls.py",
    "src/uc_bench/mmmvp_open_trajectory.py",
    "src/uc_bench/mmmvp_open_runner.py",
    "src/uc_bench/mmmvp_open_audit.py",
    "src/uc_bench/durable_trajectory.py",
    "src/uc_bench/durable_runner.py",
    "src/uc_bench/v071_auth.py",
    "src/uc_bench/v062_provider.py",
    "src/uc_bench/v061_provider.py",
    "src/uc_bench/v06_provider.py",
    "src/uc_bench/docker_runtime.py",
    "scripts/build_mmmvp_open_rc_assets.py",
    "scripts/audit_mmmvp_open_successor.py",
    "scripts/check_mmmvp_open_rc1_local_gate.py",
    "scripts/create_mmmvp_open_freeze.py",
    "tests/test_mmmvp_blind_interface.py",
    "tests/test_mmmvp_open_repairs.py",
    "artifacts/mmmvp_open_rc1/local_gate.json",
    "artifacts/mmmvp_open_rc1/open_endedness_audit.json",
    "docs/mmmvp_open_endedness_contract.md",
    "reports/generated/mmmvp_open_rc1_overview.md",
    "reports/generated/mmmvp_open_rc1_schematics_and_release_audit.md",
)


def open_freeze_paths(project_root: Path) -> list[Path]:
    root = project_root.resolve()
    paths = [root / relative for relative in _FIXED_FILES]
    for relative_root in (
        "tasks/hard_suite_v07/development",
        "grader_private/hard_suite_v07",
        "grader_private/mmmvp_open",
        "grader_private/mmmvp_open_rc1",
    ):
        paths.extend(path for path in (root / relative_root).rglob("*") if path.is_file())
    missing = [path.relative_to(root).as_posix() for path in paths if not path.is_file()]
    if missing:
        raise ConfigurationError(f"Open MMMVP freeze files missing: {missing}")
    return sorted(set(paths))


def open_freeze_hashes(project_root: Path) -> dict[str, str]:
    root = project_root.resolve()
    return {
        path.relative_to(root).as_posix(): sha256_file(path) for path in open_freeze_paths(root)
    }


def create_open_mmmvp_freeze(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    target = root / FREEZE_PATH
    if target.exists():
        raise ConfigurationError("The immutable open MMMVP RC freeze already exists")
    gate = json.loads((root / LOCAL_GATE_PATH).read_text(encoding="utf-8"))
    audit = json.loads((root / AUDIT_PATH).read_text(encoding="utf-8"))
    if gate.get("status") != "passed" or gate.get("api_requests") != 0:
        raise ConfigurationError("The zero-cost open MMMVP local gate has not passed")
    if audit.get("status") != "passed" or audit.get("api_requests") != 0:
        raise ConfigurationError("The open-endedness audit has not passed")
    panel = json.loads(
        (root / "configs/uc_bench_mmmvp_open_model_panel.json").read_text(encoding="utf-8")
    )
    models = [row["model_id"] for row in panel["models"]]
    if len(models) != 10 or len(models) != len(set(models)):
        raise ConfigurationError("The open MMMVP panel must contain ten unique models")
    forbidden = set(panel["explicitly_out_of_scope"])
    if forbidden & set(models):
        raise ConfigurationError("An explicitly excluded model entered the open panel")
    hashes = open_freeze_hashes(root)
    request_hash = canonical_sha256(serialized_open_request())
    value = {
        "schema_version": "uc-bench-open-mmmvp-freeze-1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "immutable_release_candidate",
        "description": "five-condition open-ended MMMVP calibrated pilot environment",
        "source_scientific_version": "v0.8",
        "condition_ids": list(gate["condition_ids"]),
        "model_ids": models,
        "model_count": len(models),
        "condition_count": len(gate["condition_ids"]),
        "scientific_episode_count": 50,
        "attempts_per_cell": 1,
        "serialized_request_sha256": request_hash,
        "file_count": len(hashes),
        "hashes": hashes,
        "hash_set_digest": canonical_sha256(hashes),
        "api_requests_during_repair": 0,
        "compatibility_complete": False,
        "scientific_execution_authorized": False,
        "heldout_included": False,
        "astra_included": False,
        "ranking_claim_allowed": False,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(target)
    return value


def read_open_mmmvp_freeze(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    path = root / FREEZE_PATH
    if not path.is_file():
        raise ConfigurationError("The open MMMVP release candidate is not frozen")
    value = json.loads(path.read_text(encoding="utf-8"))
    expected = open_freeze_hashes(root)
    if value.get("hashes") != expected or value.get("hash_set_digest") != canonical_sha256(
        expected
    ):
        raise ConfigurationError("The open MMMVP frozen content changed")
    if value.get("heldout_included") or value.get("astra_included"):
        raise ConfigurationError("Held-out or Astra content entered the open MMMVP freeze")
    return value


__all__ = [
    "AUDIT_PATH",
    "FREEZE_PATH",
    "LOCAL_GATE_PATH",
    "create_open_mmmvp_freeze",
    "open_freeze_hashes",
    "read_open_mmmvp_freeze",
]

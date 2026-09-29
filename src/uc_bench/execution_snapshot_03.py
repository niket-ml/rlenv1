"""Third v0.8 development execution snapshot: persistence infrastructure only."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256, sha256_file
from uc_bench.v08_repair_snapshot import SNAPSHOT_02_PATH, read_v08_repair_snapshot

SNAPSHOT_03_PATH = Path("artifacts/diagnostics/hard_suite_v08_execution_snapshot_03.json")
INFRASTRUCTURE_GATE_PATH = Path("artifacts/diagnostics/final_sol_infrastructure_gate.json")

_INFRASTRUCTURE_FILES = (
    "configs/final_sol_check.json",
    "src/uc_bench/durable_trajectory.py",
    "src/uc_bench/durable_runner.py",
    "src/uc_bench/execution_snapshot_03.py",
    "scripts/check_final_sol_infrastructure.py",
    "scripts/create_final_sol_snapshot.py",
    "scripts/run_final_sol_check.py",
    "tests/test_durable_trajectory.py",
    INFRASTRUCTURE_GATE_PATH.as_posix(),
)


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError(f"Expected JSON object: {path}")
    return value


def infrastructure_hashes(project_root: Path) -> dict[str, str]:
    root = project_root.resolve()
    missing = [relative for relative in _INFRASTRUCTURE_FILES if not (root / relative).is_file()]
    if missing:
        raise ConfigurationError(f"Snapshot-03 infrastructure files missing: {missing}")
    return {relative: sha256_file(root / relative) for relative in _INFRASTRUCTURE_FILES}


def _parent_files_unchanged(project_root: Path, parent: dict[str, Any]) -> bool:
    root = project_root.resolve()
    return all(
        (root / relative).is_file() and sha256_file(root / relative) == digest
        for relative, digest in parent["hashes"].items()
    )


def create_execution_snapshot_03(project_root: Path) -> dict[str, Any]:
    """Create one immutable development snapshot after the zero-cost gate."""

    root = project_root.resolve()
    target = root / SNAPSHOT_03_PATH
    if target.exists():
        raise ConfigurationError("Snapshot 03 already exists and will not be overwritten")
    parent = read_v08_repair_snapshot(root)
    gate = _read(root / INFRASTRUCTURE_GATE_PATH)
    if gate.get("status") != "passed" or gate.get("api_requests") != 0:
        raise ConfigurationError("The zero-cost persistence gate has not passed")
    if not _parent_files_unchanged(root, parent):
        raise ConfigurationError("Snapshot-02 scientific or verifier content changed")
    new_hashes = infrastructure_hashes(root)
    hash_basis = {
        SNAPSHOT_02_PATH.as_posix(): sha256_file(root / SNAPSHOT_02_PATH),
        **new_hashes,
    }
    value = {
        "schema_version": "0.8-development-execution-snapshot-3",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "immutable_two_condition_persistence_execution_snapshot",
        "interpretation": "third_development_snapshot_not_release_freeze",
        "scientific_version": "v0.8",
        "scientific_version_created": False,
        "scientific_cases_changed": False,
        "verifier_rules_changed": False,
        "prompts_changed": False,
        "tools_or_action_rules_changed": False,
        "accepted_alternatives_changed": False,
        "parent_snapshot_02": {
            "path": SNAPSHOT_02_PATH.as_posix(),
            "manifest_sha256": sha256_file(root / SNAPSHOT_02_PATH),
            "hash_set_digest": parent["hash_set_digest"],
            "file_count": parent["file_count"],
            "all_parent_files_byte_identical": True,
            "matched_parent_file_count": len(parent["hashes"]),
        },
        "permitted_difference_scope": "new_runner_trajectory_persistence_and_reporting_only",
        "infrastructure_files": new_hashes,
        "hashes": hash_basis,
        "hash_set_digest": canonical_sha256(hash_basis),
        "model_id": "openai/gpt-5.6-sol",
        "condition_ids": ["case_03_signal_remains", "case_04"],
        "maximum_incremental_spend_usd": 4.78,
        "api_requests_before_snapshot": 0,
        "api_spend_before_snapshot_usd": 0.0,
        "heldout_included": False,
        "astra_included": False,
        "release_freeze": False,
        "ranking_claim_allowed": False,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(target)
    return value


def read_execution_snapshot_03(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    path = root / SNAPSHOT_03_PATH
    if not path.is_file():
        raise ConfigurationError("v0.8 development snapshot 03 does not exist")
    value = _read(path)
    parent = read_v08_repair_snapshot(root)
    if value.get("parent_snapshot_02", {}).get("hash_set_digest") != parent["hash_set_digest"]:
        raise ConfigurationError("Snapshot 03 has the wrong parent digest")
    if not _parent_files_unchanged(root, parent):
        raise ConfigurationError("Snapshot-02 content changed after snapshot 03")
    expected = {
        SNAPSHOT_02_PATH.as_posix(): sha256_file(root / SNAPSHOT_02_PATH),
        **infrastructure_hashes(root),
    }
    if value.get("hashes") != expected:
        raise ConfigurationError("Snapshot-03 infrastructure hash mismatch")
    if value.get("hash_set_digest") != canonical_sha256(expected):
        raise ConfigurationError("Snapshot-03 digest mismatch")
    if value.get("release_freeze") is not False:
        raise ConfigurationError("Snapshot 03 must not be labelled a release freeze")
    return value


__all__ = [
    "INFRASTRUCTURE_GATE_PATH",
    "SNAPSHOT_03_PATH",
    "create_execution_snapshot_03",
    "infrastructure_hashes",
    "read_execution_snapshot_03",
]

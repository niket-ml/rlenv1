"""Hashed v0.8 development-execution snapshot (not a release freeze)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256, sha256_file

SNAPSHOT_PATH = Path("artifacts/diagnostics/hard_suite_v08_execution_snapshot.json")

_FIXED_FILES = (
    "configs/hard_suite_v08_mvp.json",
    "configs/hard_suite_v08_execution.json",
    "configs/hard_suite_v07_model_panel.json",
    "src/uc_bench/v08_schema.py",
    "src/uc_bench/v08_interface.py",
    "src/uc_bench/v08_environment.py",
    "src/uc_bench/v08_verifier.py",
    "src/uc_bench/v08_runner.py",
    "src/uc_bench/v08_snapshot.py",
    "src/uc_bench/v07_environment.py",
    "src/uc_bench/v07_metrics.py",
    "src/uc_bench/v072_artifacts.py",
    "src/uc_bench/v071_auth.py",
    "src/uc_bench/v07_provider.py",
    "src/uc_bench/docker_runtime.py",
    "artifacts/diagnostics/hard_suite_v08_local_gate.json",
    "scripts/check_v08_local_gate.py",
    "scripts/run_v08_development.py",
)


def v08_snapshot_paths(project_root: Path) -> list[Path]:
    """Return all code, contracts and unchanged scientific evidence in scope."""

    root = project_root.resolve()
    paths = [root / relative for relative in _FIXED_FILES]
    for relative_root in (
        "tasks/hard_suite_v07/development",
        "grader_private/hard_suite_v07",
    ):
        paths.extend(
            path for path in (root / relative_root).rglob("*") if path.is_file()
        )
    missing = [path.relative_to(root).as_posix() for path in paths if not path.is_file()]
    if missing:
        raise ConfigurationError(f"v0.8 snapshot inputs missing: {missing}")
    return sorted(set(paths))


def v08_snapshot_hashes(project_root: Path) -> dict[str, str]:
    root = project_root.resolve()
    return {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in v08_snapshot_paths(root)
    }


def create_v08_execution_snapshot(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    hashes = v08_snapshot_hashes(root)
    value = {
        "schema_version": "0.8-development-execution-snapshot-1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "immutable_for_authorized_three_condition_tranche",
        "interpretation": "execution_snapshot_not_final_mvp_release_freeze",
        "partition": "development",
        "model_id": "openai/gpt-5.6-sol",
        "condition_ids": ["case_02", "case_03_signal_remains", "case_04"],
        "maximum_incremental_spend_usd": 8.0,
        "file_count": len(hashes),
        "hashes": hashes,
        "hash_set_digest": canonical_sha256(hashes),
        "heldout_included": False,
        "astra_included": False,
        "release_freeze": False,
    }
    path = root / SNAPSHOT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
    return value


def read_v08_execution_snapshot(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    path = root / SNAPSHOT_PATH
    if not path.is_file():
        raise ConfigurationError("v0.8 execution snapshot does not exist")
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("hashes") != v08_snapshot_hashes(root):
        raise ConfigurationError("v0.8 execution snapshot hash mismatch")
    if value.get("hash_set_digest") != canonical_sha256(value["hashes"]):
        raise ConfigurationError("v0.8 execution snapshot digest mismatch")
    if value.get("release_freeze") is not False:
        raise ConfigurationError("v0.8 development snapshot was mislabelled as a release freeze")
    return value


__all__ = [
    "SNAPSHOT_PATH",
    "create_v08_execution_snapshot",
    "read_v08_execution_snapshot",
    "v08_snapshot_hashes",
    "v08_snapshot_paths",
]

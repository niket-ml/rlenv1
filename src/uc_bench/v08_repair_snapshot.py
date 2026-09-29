"""Second v0.8 development snapshot after the zero-cost verifier repair."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256, sha256_file

SNAPSHOT_02_PATH = Path("artifacts/diagnostics/hard_suite_v08_execution_snapshot_02.json")
FIRST_SNAPSHOT_PATH = Path("artifacts/diagnostics/hard_suite_v08_execution_snapshot.json")

_REPAIR_ARTIFACTS = (
    "artifacts/diagnostics/hard_suite_v08_execution_snapshot.json",
    "artifacts/diagnostics/hard_suite_v08_execution_snapshot_01_sources.tar.gz",
    "artifacts/diagnostics/hard_suite_v08_mandatory_stop.json",
    "artifacts/diagnostics/hard_suite_v08_repair_controls.json",
    "artifacts/diagnostics/hard_suite_v08_case2_development_replay.json",
    "artifacts/diagnostics/hard_suite_v08_case3_resume_assessment.json",
    "artifacts/diagnostics/hard_suite_v08_score_source_table.json",
    "artifacts/diagnostics/hard_suite_v08_verifier_architecture_audit.json",
    "artifacts/diagnostics/hard_suite_v08_verifier_repair_gate.json",
    "reports/generated/hard_suite_v08_mandatory_stop.md",
    "reports/generated/hard_suite_v08_verifier_repair.md",
)

_RAW_RUN_ROOTS = (
    "build/hard_suite_v08_runs/v08-gpt-5.6-sol-case_02-20260909T061848Z",
    ("build/hard_suite_v08_runs/v08-gpt-5.6-sol-case_03_signal_remains-20260909T062304Z"),
)


def _tree_files(root: Path, relative: str) -> list[Path]:
    path = root / relative
    return [item for item in path.rglob("*") if item.is_file()]


def v08_repair_snapshot_paths(project_root: Path) -> list[Path]:
    """Return repaired code, contracts, evidence, tests and preserved run inputs."""

    root = project_root.resolve()
    paths: list[Path] = [root / relative for relative in _REPAIR_ARTIFACTS]
    for pattern in (
        "configs/hard_suite_v08*.json",
        "src/uc_bench/v08*.py",
        "scripts/*v08*.py",
        "tests/test_v08*.py",
        "tests/fixtures/v08*.json",
    ):
        paths.extend(root.glob(pattern))
    for relative in (
        "tasks/hard_suite_v07/development",
        "grader_private/hard_suite_v07",
        *_RAW_RUN_ROOTS,
    ):
        paths.extend(_tree_files(root, relative))
    paths = [path for path in paths if path != root / SNAPSHOT_02_PATH]
    missing = [path.relative_to(root).as_posix() for path in paths if not path.is_file()]
    if missing:
        raise ConfigurationError(f"v0.8 repair snapshot inputs missing: {missing}")
    return sorted(set(paths))


def v08_repair_snapshot_hashes(project_root: Path) -> dict[str, str]:
    root = project_root.resolve()
    return {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in v08_repair_snapshot_paths(root)
    }


def _scientific_hashes_unchanged(project_root: Path) -> bool:
    root = project_root.resolve()
    first = json.loads((root / FIRST_SNAPSHOT_PATH).read_text(encoding="utf-8"))
    first_science = {
        path: digest
        for path, digest in first["hashes"].items()
        if path.startswith("tasks/hard_suite_v07/development/")
        or path.startswith("grader_private/hard_suite_v07/")
    }
    current = {path: sha256_file(root / path) for path in first_science}
    return current == first_science


def create_v08_repair_snapshot(project_root: Path) -> dict[str, Any]:
    """Create snapshot 02 only after the offline repair gate has passed."""

    root = project_root.resolve()
    gate = json.loads(
        (root / "artifacts/diagnostics/hard_suite_v08_verifier_repair_gate.json").read_text(
            encoding="utf-8"
        )
    )
    if gate.get("status") != "passed" or gate.get("api_requests") != 0:
        raise ConfigurationError("v0.8 repair gate has not passed at zero API cost")
    if not _scientific_hashes_unchanged(root):
        raise ConfigurationError("v0.8 scientific case or truth hash changed")
    first = json.loads((root / FIRST_SNAPSHOT_PATH).read_text(encoding="utf-8"))
    hashes = v08_repair_snapshot_hashes(root)
    value = {
        "schema_version": "0.8-development-execution-snapshot-2",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "immutable_development_verifier_architecture_snapshot",
        "interpretation": "second_development_snapshot_not_release_freeze",
        "scientific_version": "v0.8",
        "scientific_version_created": False,
        "scientific_cases_changed": False,
        "parent_execution_snapshot": {
            "path": FIRST_SNAPSHOT_PATH.as_posix(),
            "manifest_sha256": sha256_file(root / FIRST_SNAPSHOT_PATH),
            "hash_set_digest": first["hash_set_digest"],
            "preserved_immutable": True,
        },
        "repair_scope": "verifier_architecture_and_infrastructure_reporting_only",
        "api_requests_during_repair": 0,
        "api_spend_usd": 0.0,
        "case2_raw_historical_result_preserved": True,
        "case2_replay_is_retroactive_frozen_score": False,
        "case3_resumption_authorized": False,
        "scientific_execution_authorized": False,
        "file_count": len(hashes),
        "hashes": hashes,
        "hash_set_digest": canonical_sha256(hashes),
        "heldout_included": False,
        "astra_included": False,
        "release_freeze": False,
    }
    path = root / SNAPSHOT_02_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return value


def read_v08_repair_snapshot(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    path = root / SNAPSHOT_02_PATH
    if not path.is_file():
        raise ConfigurationError("v0.8 repair snapshot does not exist")
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("hashes") != v08_repair_snapshot_hashes(root):
        raise ConfigurationError("v0.8 repair snapshot hash mismatch")
    if value.get("hash_set_digest") != canonical_sha256(value["hashes"]):
        raise ConfigurationError("v0.8 repair snapshot digest mismatch")
    if value.get("release_freeze") is not False:
        raise ConfigurationError("v0.8 repair snapshot is not a release freeze")
    return value


__all__ = [
    "SNAPSHOT_02_PATH",
    "create_v08_repair_snapshot",
    "read_v08_repair_snapshot",
    "v08_repair_snapshot_hashes",
    "v08_repair_snapshot_paths",
]

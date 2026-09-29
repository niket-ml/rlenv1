"""Immutable release/infrastructure digest for RC1.1 over frozen RC1 science."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256, sha256_file
from uc_bench.mmmvp_open_freeze import read_open_mmmvp_freeze
from uc_bench.mmmvp_open_release_freeze import read_open_release_freeze

SCIENTIFIC_FREEZE_DIGEST = "466441682b04175432329b41adcfd735cdea66f860d66f046dfae195c91e701c"
RC1_RELEASE_DIGEST = "0c620a5db9b75fc5454d5e013866fc37d4bb71095266721c158aa8efd00c1dba"
RC11_FREEZE_PATH = Path("artifacts/mmmvp_open_rc11/release_freeze.json")
RC11_GATE_PATH = Path("artifacts/mmmvp_open_rc11/pre_exposure_gate.json")

_INFRASTRUCTURE_FILES = (
    "configs/uc_bench_mmmvp_open_rc11_release.json",
    "src/uc_bench/mmmvp_open_rc11_environment.py",
    "src/uc_bench/mmmvp_open_rc11_trajectory.py",
    "src/uc_bench/mmmvp_open_rc11_runner.py",
    "src/uc_bench/mmmvp_open_rc11_compatibility.py",
    "src/uc_bench/mmmvp_open_rc11_freeze.py",
    "src/uc_bench/mmmvp_open_rc11_sentinel.py",
    "src/uc_bench/mmmvp_open_rc11_analysis.py",
    "scripts/prepare_mmmvp_open_rc11.py",
    "scripts/check_mmmvp_open_rc11_gate.py",
    "scripts/create_mmmvp_open_rc11_freeze.py",
    "scripts/run_mmmvp_open_rc11_docker_preflight.py",
    "scripts/run_mmmvp_open_rc11_compatibility.py",
    "scripts/run_mmmvp_open_rc11_sentinel.py",
    "scripts/analyze_mmmvp_open_rc11_sentinel.py",
    "tests/test_mmmvp_open_rc11.py",
    "artifacts/mmmvp_open_rc11/gemini_root_write_fixture.json",
    "artifacts/mmmvp_open_rc11/rc1_gemini_reliability_adjudication.json",
    "artifacts/mmmvp_open_rc11/inherited_compatibility.json",
    "artifacts/mmmvp_open_rc11/pre_exposure_gate.json",
)

_PRESERVED_ROOTS = (
    "artifacts/mmmvp_open_rc1",
    "artifacts/mmmvp_open_release",
    "build/uc_bench_mmmvp_open_runs/open-mmmvp-sentinel-00-google-gemini-3.1-pro-preview-case-02",
)
_PRESERVED_FILES = (
    "reports/generated/mmmvp_open_case2_sentinel_incident.md",
)


def _files_beneath(root: Path, relatives: tuple[str, ...]) -> list[Path]:
    paths: list[Path] = []
    for relative in relatives:
        base = root / relative
        if not base.is_dir():
            raise ConfigurationError(f"Preserved RC1 directory is missing: {relative}")
        paths.extend(path for path in base.rglob("*") if path.is_file())
    return paths


def rc1_archive_hashes(project_root: Path) -> dict[str, str]:
    """Hash the complete pre-RC1.1 evidence that must remain immutable."""

    root = project_root.resolve()
    paths = _files_beneath(root, _PRESERVED_ROOTS)
    paths.extend(root / relative for relative in _PRESERVED_FILES)
    missing = [path.relative_to(root).as_posix() for path in paths if not path.is_file()]
    if missing:
        raise ConfigurationError(f"Preserved RC1 evidence is missing: {missing}")
    return {
        path.relative_to(root).as_posix(): sha256_file(path) for path in sorted(set(paths))
    }


def rc11_infrastructure_hashes(project_root: Path) -> dict[str, str]:
    root = project_root.resolve()
    paths = [root / relative for relative in _INFRASTRUCTURE_FILES]
    missing = [path.relative_to(root).as_posix() for path in paths if not path.is_file()]
    if missing:
        raise ConfigurationError(f"RC1.1 infrastructure files are missing: {missing}")
    return {path.relative_to(root).as_posix(): sha256_file(path) for path in sorted(paths)}


def _validate_inheritance(project_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    root = project_root.resolve()
    scientific = read_open_mmmvp_freeze(root)
    rc1_release = read_open_release_freeze(root)
    if scientific["hash_set_digest"] != SCIENTIFIC_FREEZE_DIGEST:
        raise ConfigurationError("The RC1 scientific digest changed")
    if rc1_release["category_digest_set"] != RC1_RELEASE_DIGEST:
        raise ConfigurationError("The RC1 release digest changed")
    old_config = json.loads(
        (root / "configs/uc_bench_mmmvp_open_release.json").read_text(encoding="utf-8")
    )
    new_config = json.loads(
        (root / "configs/uc_bench_mmmvp_open_rc11_release.json").read_text(encoding="utf-8")
    )
    if old_config["scientific_episode"] != new_config["scientific_episode"]:
        raise ConfigurationError("RC1.1 changed the frozen episode limits")
    if old_config["sentinel"]["hard_cumulative_cap_usd"] != new_config["sentinel"][
        "hard_cumulative_cap_usd"
    ]:
        raise ConfigurationError("RC1.1 changed the sentinel scientific cap")
    return scientific, rc1_release


def create_rc11_release_freeze(project_root: Path) -> dict[str, Any]:
    """Freeze the infrastructure repair while referencing byte-identical RC1 science."""

    root = project_root.resolve()
    target = root / RC11_FREEZE_PATH
    if target.exists():
        raise ConfigurationError("The RC1.1 release is already frozen")
    scientific, rc1_release = _validate_inheritance(root)
    gate = json.loads((root / RC11_GATE_PATH).read_text(encoding="utf-8"))
    if gate.get("status") != "passed" or gate.get("api_requests") != 0:
        raise ConfigurationError("The zero-cost RC1.1 gate did not pass")
    infrastructure = rc11_infrastructure_hashes(root)
    archives = rc1_archive_hashes(root)
    value = {
        "schema_version": "uc-bench-open-mmmvp-rc1-1-release-freeze-1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "immutable_infrastructure_successor",
        "scientific_freeze_digest": scientific["hash_set_digest"],
        "scientific_file_count": scientific["file_count"],
        "scientific_hashes": scientific["hashes"],
        "rc1_release_digest": rc1_release["category_digest_set"],
        "rc1_category_digests": {
            name: row["digest"] for name, row in rc1_release["categories"].items()
        },
        "rc1_archive_hashes": archives,
        "rc1_archive_digest": canonical_sha256(archives),
        "infrastructure_hashes": infrastructure,
        "infrastructure_digest": canonical_sha256(infrastructure),
        "scientific_content_byte_identical": True,
        "scientific_changes_permitted": False,
        "provider_fallbacks_allowed": False,
        "sentinel_condition": "case_02",
        "sentinel_hard_cap_usd": 25.0,
        "remaining_matrix_authorized": False,
        "heldout_included": False,
        "astra_included": False,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(target)
    return value


def read_rc11_release_freeze(project_root: Path) -> dict[str, Any]:
    """Fail closed on any scientific, RC1 archive, or RC1.1 infrastructure drift."""

    root = project_root.resolve()
    target = root / RC11_FREEZE_PATH
    if not target.is_file():
        raise ConfigurationError("The RC1.1 infrastructure successor is not frozen")
    value = json.loads(target.read_text(encoding="utf-8"))
    scientific, rc1_release = _validate_inheritance(root)
    if value.get("scientific_freeze_digest") != scientific["hash_set_digest"]:
        raise ConfigurationError("RC1.1 no longer references the exact RC1 science")
    if value.get("scientific_hashes") != scientific["hashes"]:
        raise ConfigurationError("RC1.1 scientific file hashes changed")
    if value.get("rc1_release_digest") != rc1_release["category_digest_set"]:
        raise ConfigurationError("RC1 release digest changed after RC1.1")
    archives = rc1_archive_hashes(root)
    if (
        value.get("rc1_archive_hashes") != archives
        or value.get("rc1_archive_digest") != canonical_sha256(archives)
    ):
        raise ConfigurationError("Preserved RC1 evidence changed after RC1.1")
    infrastructure = rc11_infrastructure_hashes(root)
    if (
        value.get("infrastructure_hashes") != infrastructure
        or value.get("infrastructure_digest") != canonical_sha256(infrastructure)
    ):
        raise ConfigurationError("Frozen RC1.1 infrastructure changed")
    if value.get("heldout_included") or value.get("astra_included"):
        raise ConfigurationError("Held-out or Astra content entered RC1.1")
    return value


__all__ = [
    "RC11_FREEZE_PATH",
    "RC11_GATE_PATH",
    "RC1_RELEASE_DIGEST",
    "SCIENTIFIC_FREEZE_DIGEST",
    "create_rc11_release_freeze",
    "rc1_archive_hashes",
    "rc11_infrastructure_hashes",
    "read_rc11_release_freeze",
]

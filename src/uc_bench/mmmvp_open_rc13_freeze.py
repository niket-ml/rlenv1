"""Immutable RC1.3 infrastructure freeze over preserved RC1.2."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256, sha256_file
from uc_bench.mmmvp_open_freeze import read_open_mmmvp_freeze
from uc_bench.mmmvp_open_rc11_compatibility import compatibility_identity
from uc_bench.mmmvp_open_rc12_freeze import read_rc12_release_freeze

SCIENTIFIC_FREEZE_DIGEST = "466441682b04175432329b41adcfd735cdea66f860d66f046dfae195c91e701c"
SERIALIZED_REQUEST_DIGEST = "d50747a564877dea31329cd71e9a8a1e3b4ed8f913b802d059cc3c053d0d9523"
TOOL_SCHEMA_DIGEST = "a29133462152f7c78452a5e13c76efc2991142b8703ce418cdf4a78d10f842d7"
RC12_INFRASTRUCTURE_DIGEST = "cac7b11ef7dc1c0604f07b050256352ae06d285d453ec1f3001a889ccfab5f3a"
RC13_FREEZE_PATH = Path("artifacts/mmmvp_open_rc13/release_freeze.json")
RC13_GATE_PATH = Path("artifacts/mmmvp_open_rc13/pre_exposure_gate.json")

_INFRASTRUCTURE_FILES = (
    "configs/uc_bench_mmmvp_open_rc13_release.json",
    "src/uc_bench/mmmvp_open_rc13_trajectory.py",
    "src/uc_bench/mmmvp_open_rc13_runner.py",
    "src/uc_bench/mmmvp_open_rc13_compatibility.py",
    "src/uc_bench/mmmvp_open_rc13_cost.py",
    "src/uc_bench/mmmvp_open_rc13_freeze.py",
    "src/uc_bench/mmmvp_open_rc13_sentinel.py",
    "src/uc_bench/mmmvp_open_rc13_analysis.py",
    "scripts/prepare_mmmvp_open_rc13.py",
    "scripts/audit_mmmvp_open_rc13_submission_friction.py",
    "scripts/check_mmmvp_open_rc13_gate.py",
    "scripts/create_mmmvp_open_rc13_freeze.py",
    "scripts/run_mmmvp_open_rc13_sentinel.py",
    "scripts/analyze_mmmvp_open_rc13_sentinel.py",
    "tests/test_mmmvp_open_rc13.py",
    "artifacts/mmmvp_open_rc13/deepseek_framework_error_fixture.json",
    "artifacts/mmmvp_open_rc13/inherited_compatibility.json",
    "artifacts/mmmvp_open_rc13/cost_plan.json",
    "artifacts/mmmvp_open_rc13/rc12_submission_friction_diagnostic.json",
    "artifacts/mmmvp_open_rc13/pre_exposure_gate.json",
    "artifacts/mmmvp_open_rc13/pre_exposure_gate_attempt_01_sandbox_denied.json",
)


def _rc12_archive_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    for relative in (
        "artifacts/mmmvp_open_rc12",
        "build/uc_bench_mmmvp_open_rc12_runs",
    ):
        base = root / relative
        if not base.is_dir():
            raise ConfigurationError(f"Preserved RC1.2 directory is missing: {relative}")
        paths.extend(path for path in base.rglob("*") if path.is_file())
    paths.extend(
        path
        for path in (root / "reports/generated").glob("mmmvp_open_rc12*")
        if path.is_file()
    )
    figure_roots = [
        path
        for path in (root / "reports/generated").glob("mmmvp_open_rc12*")
        if path.is_dir()
    ]
    for base in figure_roots:
        paths.extend(path for path in base.rglob("*") if path.is_file())
    if not paths:
        raise ConfigurationError("No RC1.2 archive files were found")
    return sorted(set(paths))


def rc12_complete_archive_hashes(project_root: Path) -> dict[str, str]:
    root = project_root.resolve()
    return {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in _rc12_archive_paths(root)
    }


def rc13_infrastructure_hashes(project_root: Path) -> dict[str, str]:
    root = project_root.resolve()
    paths = [root / relative for relative in _INFRASTRUCTURE_FILES]
    missing = [path.relative_to(root).as_posix() for path in paths if not path.is_file()]
    if missing:
        raise ConfigurationError(f"RC1.3 infrastructure files are missing: {missing}")
    return {path.relative_to(root).as_posix(): sha256_file(path) for path in sorted(paths)}


def _validate_inheritance(project_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    root = project_root.resolve()
    scientific = read_open_mmmvp_freeze(root)
    rc12 = read_rc12_release_freeze(root)
    identity = compatibility_identity(root)
    observed = {
        "scientific": scientific["hash_set_digest"],
        "request": identity["serialized_request_sha256"],
        "tools": identity["tool_schema_sha256"],
        "rc12": rc12["infrastructure_digest"],
    }
    expected = {
        "scientific": SCIENTIFIC_FREEZE_DIGEST,
        "request": SERIALIZED_REQUEST_DIGEST,
        "tools": TOOL_SCHEMA_DIGEST,
        "rc12": RC12_INFRASTRUCTURE_DIGEST,
    }
    if observed != expected:
        raise ConfigurationError(f"RC1.3 inheritance drift: {observed}")
    rc12_config = json.loads(
        (root / "configs/uc_bench_mmmvp_open_rc12_release.json").read_text()
    )
    rc13_config = json.loads(
        (root / "configs/uc_bench_mmmvp_open_rc13_release.json").read_text()
    )
    if rc12_config["scientific_episode"] != rc13_config["scientific_episode"]:
        raise ConfigurationError("RC1.3 changed the frozen episode budget")
    return scientific, rc12


def create_rc13_release_freeze(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    target = root / RC13_FREEZE_PATH
    if target.exists():
        raise ConfigurationError("RC1.3 is already frozen")
    scientific, rc12 = _validate_inheritance(root)
    gate = json.loads((root / RC13_GATE_PATH).read_text(encoding="utf-8"))
    if gate.get("status") != "passed" or gate.get("api_requests") != 0:
        raise ConfigurationError("The zero-cost RC1.3 gate did not pass")
    compatibility = json.loads(
        (root / "artifacts/mmmvp_open_rc13/inherited_compatibility.json").read_text()
    )
    if compatibility.get("status") != "passed" or compatibility.get("api_requests") != 0:
        raise ConfigurationError("RC1.3 compatibility inheritance is not clean")
    cost = json.loads(
        (root / "artifacts/mmmvp_open_rc13/cost_plan.json").read_text()
    )
    if cost.get("scientific_api_requests") != 0:
        raise ConfigurationError("RC1.3 cost planning contacted a scientific model")
    infrastructure = rc13_infrastructure_hashes(root)
    archive = rc12_complete_archive_hashes(root)
    value = {
        "schema_version": "uc-bench-open-mmmvp-rc1-3-release-freeze-1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "immutable_infrastructure_successor",
        "scientific_freeze_digest": scientific["hash_set_digest"],
        "scientific_hashes": scientific["hashes"],
        "serialized_request_sha256": SERIALIZED_REQUEST_DIGEST,
        "tool_schema_sha256": TOOL_SCHEMA_DIGEST,
        "rc12_infrastructure_digest": rc12["infrastructure_digest"],
        "rc12_complete_archive_hashes": archive,
        "rc12_complete_archive_digest": canonical_sha256(archive),
        "infrastructure_hashes": infrastructure,
        "infrastructure_digest": canonical_sha256(infrastructure),
        "scientific_content_byte_identical": True,
        "provider_facing_content_byte_identical": True,
        "scientific_changes_permitted": False,
        "provider_fallbacks_allowed": False,
        "sentinel_condition": "case_02",
        "sentinel_hard_cap_usd": 40.0,
        "remaining_matrix_authorized": False,
        "heldout_included": False,
        "astra_included": False,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(target)
    return value


def read_rc13_release_freeze(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    target = root / RC13_FREEZE_PATH
    if not target.is_file():
        raise ConfigurationError("RC1.3 is not frozen")
    value = json.loads(target.read_text(encoding="utf-8"))
    scientific, rc12 = _validate_inheritance(root)
    expected = {
        "scientific_freeze_digest": scientific["hash_set_digest"],
        "serialized_request_sha256": SERIALIZED_REQUEST_DIGEST,
        "tool_schema_sha256": TOOL_SCHEMA_DIGEST,
        "rc12_infrastructure_digest": rc12["infrastructure_digest"],
    }
    if any(value.get(key) != wanted for key, wanted in expected.items()):
        raise ConfigurationError("RC1.3 frozen identities changed")
    archive = rc12_complete_archive_hashes(root)
    if value.get("rc12_complete_archive_hashes") != archive or value.get(
        "rc12_complete_archive_digest"
    ) != canonical_sha256(archive):
        raise ConfigurationError("Preserved RC1.2 evidence changed after RC1.3")
    infrastructure = rc13_infrastructure_hashes(root)
    if value.get("infrastructure_hashes") != infrastructure or value.get(
        "infrastructure_digest"
    ) != canonical_sha256(infrastructure):
        raise ConfigurationError("Frozen RC1.3 infrastructure changed")
    if value.get("heldout_included") or value.get("astra_included"):
        raise ConfigurationError("Held-out or Astra content entered RC1.3")
    return value


__all__ = [
    "RC13_FREEZE_PATH",
    "RC13_GATE_PATH",
    "RC12_INFRASTRUCTURE_DIGEST",
    "SCIENTIFIC_FREEZE_DIGEST",
    "SERIALIZED_REQUEST_DIGEST",
    "TOOL_SCHEMA_DIGEST",
    "create_rc13_release_freeze",
    "rc12_complete_archive_hashes",
    "rc13_infrastructure_hashes",
    "read_rc13_release_freeze",
]

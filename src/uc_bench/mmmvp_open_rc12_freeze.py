"""Immutable RC1.2 infrastructure freeze over preserved RC1 and RC1.1."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256, sha256_file
from uc_bench.mmmvp_open_freeze import read_open_mmmvp_freeze
from uc_bench.mmmvp_open_rc11_compatibility import compatibility_identity
from uc_bench.mmmvp_open_rc11_freeze import read_rc11_release_freeze
from uc_bench.mmmvp_open_release_freeze import read_open_release_freeze

SCIENTIFIC_FREEZE_DIGEST = "466441682b04175432329b41adcfd735cdea66f860d66f046dfae195c91e701c"
SERIALIZED_REQUEST_DIGEST = "d50747a564877dea31329cd71e9a8a1e3b4ed8f913b802d059cc3c053d0d9523"
TOOL_SCHEMA_DIGEST = "a29133462152f7c78452a5e13c76efc2991142b8703ce418cdf4a78d10f842d7"
RC1_RELEASE_DIGEST = "0c620a5db9b75fc5454d5e013866fc37d4bb71095266721c158aa8efd00c1dba"
RC11_INFRASTRUCTURE_DIGEST = "f626396695fa31e8eb2764d2dc62366c345a1f64285922c3ae3af78b681ad068"
RC12_FREEZE_PATH = Path("artifacts/mmmvp_open_rc12/release_freeze.json")
RC12_GATE_PATH = Path("artifacts/mmmvp_open_rc12/pre_exposure_gate.json")

_INFRASTRUCTURE_FILES = (
    "configs/uc_bench_mmmvp_open_rc12_release.json",
    "src/uc_bench/mmmvp_open_rc12_environment.py",
    "src/uc_bench/mmmvp_open_rc12_trajectory.py",
    "src/uc_bench/mmmvp_open_rc12_runner.py",
    "src/uc_bench/mmmvp_open_rc12_compatibility.py",
    "src/uc_bench/mmmvp_open_rc12_freeze.py",
    "src/uc_bench/mmmvp_open_rc12_sentinel.py",
    "src/uc_bench/mmmvp_open_rc12_analysis.py",
    "scripts/prepare_mmmvp_open_rc12.py",
    "scripts/check_mmmvp_open_rc12_gate.py",
    "scripts/create_mmmvp_open_rc12_freeze.py",
    "scripts/run_mmmvp_open_rc12_docker_preflight.py",
    "scripts/run_mmmvp_open_rc12_sentinel.py",
    "scripts/analyze_mmmvp_open_rc12_sentinel.py",
    "tests/test_mmmvp_open_rc12.py",
    "artifacts/mmmvp_open_rc12/mistral_false_positive_commands.json",
    "artifacts/mmmvp_open_rc12/archived_rc11_replay_adjudication.json",
    "artifacts/mmmvp_open_rc12/inherited_compatibility.json",
    "artifacts/mmmvp_open_rc12/pre_exposure_gate.json",
)

_RC11_PRESERVED_ROOTS = (
    "artifacts/mmmvp_open_rc11",
    "build/uc_bench_mmmvp_open_rc11_runs",
)
_RC11_PRESERVED_FILES = (
    "reports/generated/mmmvp_open_rc11_case2_sentinel_stopped.md",
    "reports/generated/mmmvp_open_rc11_case2_sentinel_figures/model_by_requirement_heatmap.svg",
)


def _files_beneath(root: Path, relatives: tuple[str, ...]) -> list[Path]:
    paths: list[Path] = []
    for relative in relatives:
        base = root / relative
        if not base.is_dir():
            raise ConfigurationError(f"Preserved directory is missing: {relative}")
        paths.extend(path for path in base.rglob("*") if path.is_file())
    return paths


def rc11_complete_archive_hashes(project_root: Path) -> dict[str, str]:
    """Hash every RC1.1 report, result, compatibility record, and trajectory."""

    root = project_root.resolve()
    paths = _files_beneath(root, _RC11_PRESERVED_ROOTS)
    paths.extend(root / relative for relative in _RC11_PRESERVED_FILES)
    missing = [path.relative_to(root).as_posix() for path in paths if not path.is_file()]
    if missing:
        raise ConfigurationError(f"Preserved RC1.1 evidence is missing: {missing}")
    return {path.relative_to(root).as_posix(): sha256_file(path) for path in sorted(set(paths))}


def rc12_infrastructure_hashes(project_root: Path) -> dict[str, str]:
    root = project_root.resolve()
    paths = [root / relative for relative in _INFRASTRUCTURE_FILES]
    missing = [path.relative_to(root).as_posix() for path in paths if not path.is_file()]
    if missing:
        raise ConfigurationError(f"RC1.2 infrastructure files are missing: {missing}")
    return {path.relative_to(root).as_posix(): sha256_file(path) for path in sorted(paths)}


def _validate_inheritance(
    project_root: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    root = project_root.resolve()
    scientific = read_open_mmmvp_freeze(root)
    rc1_release = read_open_release_freeze(root)
    rc11_release = read_rc11_release_freeze(root)
    identity = compatibility_identity(root)
    expected = {
        "scientific": scientific["hash_set_digest"],
        "request": identity["serialized_request_sha256"],
        "tools": identity["tool_schema_sha256"],
        "rc1": rc1_release["category_digest_set"],
        "rc11": rc11_release["infrastructure_digest"],
    }
    required = {
        "scientific": SCIENTIFIC_FREEZE_DIGEST,
        "request": SERIALIZED_REQUEST_DIGEST,
        "tools": TOOL_SCHEMA_DIGEST,
        "rc1": RC1_RELEASE_DIGEST,
        "rc11": RC11_INFRASTRUCTURE_DIGEST,
    }
    if expected != required:
        raise ConfigurationError(f"RC1.2 inheritance drift: {expected}")
    rc11_config = json.loads(
        (root / "configs/uc_bench_mmmvp_open_rc11_release.json").read_text(encoding="utf-8")
    )
    rc12_config = json.loads(
        (root / "configs/uc_bench_mmmvp_open_rc12_release.json").read_text(encoding="utf-8")
    )
    if rc11_config["scientific_episode"] != rc12_config["scientific_episode"]:
        raise ConfigurationError("RC1.2 changed the frozen episode budgets")
    if (
        rc11_config["sentinel"]["hard_cumulative_cap_usd"]
        != rc12_config["sentinel"]["hard_cumulative_cap_usd"]
    ):
        raise ConfigurationError("RC1.2 changed the sentinel cap")
    return scientific, rc1_release, rc11_release


def create_rc12_release_freeze(project_root: Path) -> dict[str, Any]:
    """Freeze only the second infrastructure repair."""

    root = project_root.resolve()
    target = root / RC12_FREEZE_PATH
    if target.exists():
        raise ConfigurationError("The RC1.2 infrastructure successor is already frozen")
    scientific, rc1_release, rc11_release = _validate_inheritance(root)
    gate = json.loads((root / RC12_GATE_PATH).read_text(encoding="utf-8"))
    if gate.get("status") != "passed" or gate.get("api_requests") != 0:
        raise ConfigurationError("The zero-cost RC1.2 gate did not pass")
    infrastructure = rc12_infrastructure_hashes(root)
    rc11_archive = rc11_complete_archive_hashes(root)
    value = {
        "schema_version": "uc-bench-open-mmmvp-rc1-2-release-freeze-1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "immutable_infrastructure_successor",
        "scientific_freeze_digest": scientific["hash_set_digest"],
        "scientific_file_count": scientific["file_count"],
        "scientific_hashes": scientific["hashes"],
        "serialized_request_sha256": SERIALIZED_REQUEST_DIGEST,
        "tool_schema_sha256": TOOL_SCHEMA_DIGEST,
        "rc1_release_digest": rc1_release["category_digest_set"],
        "rc11_infrastructure_digest": rc11_release["infrastructure_digest"],
        "rc11_complete_archive_hashes": rc11_archive,
        "rc11_complete_archive_digest": canonical_sha256(rc11_archive),
        "infrastructure_hashes": infrastructure,
        "infrastructure_digest": canonical_sha256(infrastructure),
        "scientific_content_byte_identical": True,
        "provider_facing_content_byte_identical": True,
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


def read_rc12_release_freeze(project_root: Path) -> dict[str, Any]:
    """Fail closed on scientific, provider-facing, archived, or RC1.2 drift."""

    root = project_root.resolve()
    target = root / RC12_FREEZE_PATH
    if not target.is_file():
        raise ConfigurationError("The RC1.2 infrastructure successor is not frozen")
    value = json.loads(target.read_text(encoding="utf-8"))
    scientific, rc1_release, rc11_release = _validate_inheritance(root)
    required = {
        "scientific_freeze_digest": scientific["hash_set_digest"],
        "serialized_request_sha256": SERIALIZED_REQUEST_DIGEST,
        "tool_schema_sha256": TOOL_SCHEMA_DIGEST,
        "rc1_release_digest": rc1_release["category_digest_set"],
        "rc11_infrastructure_digest": rc11_release["infrastructure_digest"],
    }
    if any(value.get(key) != expected for key, expected in required.items()):
        raise ConfigurationError("RC1.2 frozen identities changed")
    rc11_archive = rc11_complete_archive_hashes(root)
    if value.get("rc11_complete_archive_hashes") != rc11_archive or value.get(
        "rc11_complete_archive_digest"
    ) != canonical_sha256(rc11_archive):
        raise ConfigurationError("Preserved RC1.1 evidence changed after RC1.2")
    infrastructure = rc12_infrastructure_hashes(root)
    if value.get("infrastructure_hashes") != infrastructure or value.get(
        "infrastructure_digest"
    ) != canonical_sha256(infrastructure):
        raise ConfigurationError("Frozen RC1.2 infrastructure changed")
    if value.get("heldout_included") or value.get("astra_included"):
        raise ConfigurationError("Held-out or Astra content entered RC1.2")
    return value


__all__ = [
    "RC12_FREEZE_PATH",
    "RC12_GATE_PATH",
    "RC11_INFRASTRUCTURE_DIGEST",
    "SCIENTIFIC_FREEZE_DIGEST",
    "SERIALIZED_REQUEST_DIGEST",
    "TOOL_SCHEMA_DIGEST",
    "create_rc12_release_freeze",
    "rc11_complete_archive_hashes",
    "rc12_infrastructure_hashes",
    "read_rc12_release_freeze",
]

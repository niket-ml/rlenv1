"""Category-level immutable digests for RC1 release execution."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256, sha256_file
from uc_bench.mmmvp_open_freeze import read_open_mmmvp_freeze

RELEASE_FREEZE_PATH = Path("artifacts/mmmvp_open_release/release_freeze.json")

_PUBLIC_PROMPT_TOOLS = (
    "src/uc_bench/mmmvp_blind_interface.py",
    "src/uc_bench/mmmvp_open_environment.py",
)
_SUBMISSION_CONTRACT = ("src/uc_bench/mmmvp_open_schema.py",)
_VERIFIER_SCORING = (
    "src/uc_bench/mmmvp_open_calculations.py",
    "src/uc_bench/mmmvp_open_verifier.py",
    "src/uc_bench/mmmvp_open_controls.py",
    "grader_private/mmmvp_open_rc1/validity_cards.json",
)
_PROVIDER_EXECUTION = (
    "configs/uc_bench_mmmvp_open_model_panel.json",
    "configs/uc_bench_mmmvp_open_release.json",
    "artifacts/mmmvp_open_release/route_contracts.json",
    "src/uc_bench/mmmvp_open_provider.py",
    "src/uc_bench/mmmvp_open_compatibility.py",
    "src/uc_bench/mmmvp_open_sentinel.py",
    "src/uc_bench/mmmvp_open_sentinel_analysis.py",
    "src/uc_bench/mmmvp_open_runner.py",
    "src/uc_bench/mmmvp_open_trajectory.py",
    "src/uc_bench/durable_runner.py",
    "src/uc_bench/durable_trajectory.py",
    "src/uc_bench/mmmvp_provider.py",
    "src/uc_bench/v071_auth.py",
    "src/uc_bench/v062_provider.py",
    "src/uc_bench/v061_provider.py",
    "src/uc_bench/v06_provider.py",
    "src/uc_bench/docker_runtime.py",
    "scripts/build_mmmvp_open_route_contracts.py",
    "scripts/run_mmmvp_open_compatibility.py",
    "scripts/run_mmmvp_open_sentinel.py",
    "scripts/analyze_mmmvp_open_sentinel.py",
    "scripts/check_mmmvp_open_release_gate.py",
    "tests/test_mmmvp_open_release.py",
    "artifacts/mmmvp_open_release/pre_exposure_gate.json",
)


def _scientific_case_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    for relative in (
        "tasks/hard_suite_v07/development",
        "grader_private/hard_suite_v07",
        "grader_private/mmmvp_open_rc1/case_02",
        "grader_private/mmmvp_open_rc1/case_03",
    ):
        paths.extend(path for path in (root / relative).rglob("*") if path.is_file())
    paths.extend(
        [
            root / "grader_private/mmmvp_open_rc1/validity_cards.json",
            root / "src/uc_bench/mmmvp_open_interventions.py",
            root / "configs/uc_bench_mmmvp_open_suite.json",
        ]
    )
    return sorted(set(paths))


def _paths(root: Path, relatives: tuple[str, ...]) -> list[Path]:
    paths = [root / relative for relative in relatives]
    missing = [path.relative_to(root).as_posix() for path in paths if not path.is_file()]
    if missing:
        raise ConfigurationError(f"Release freeze files are missing: {missing}")
    return paths


def release_category_paths(project_root: Path) -> dict[str, list[Path]]:
    root = project_root.resolve()
    return {
        "scientific_cases_and_private_truths": _scientific_case_paths(root),
        "public_prompt_and_tools": _paths(root, _PUBLIC_PROMPT_TOOLS),
        "submission_contract": _paths(root, _SUBMISSION_CONTRACT),
        "verifier_and_scoring": _paths(root, _VERIFIER_SCORING),
        "provider_adapters_and_execution_limits": _paths(root, _PROVIDER_EXECUTION),
    }


def release_category_hashes(project_root: Path) -> dict[str, dict[str, str]]:
    root = project_root.resolve()
    return {
        category: {
            path.relative_to(root).as_posix(): sha256_file(path) for path in sorted(paths)
        }
        for category, paths in release_category_paths(root).items()
    }


def create_open_release_freeze(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    target = root / RELEASE_FREEZE_PATH
    if target.exists():
        raise ConfigurationError("The open MMMVP release freeze already exists")
    scientific = read_open_mmmvp_freeze(root)
    categories = release_category_hashes(root)
    value = {
        "schema_version": "uc-bench-open-mmmvp-category-freeze-1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "immutable_release_execution_candidate",
        "scientific_freeze_digest": scientific["hash_set_digest"],
        "categories": {
            name: {
                "file_count": len(hashes),
                "digest": canonical_sha256(hashes),
                "hashes": hashes,
            }
            for name, hashes in categories.items()
        },
        "category_digest_set": canonical_sha256(
            {name: canonical_sha256(hashes) for name, hashes in categories.items()}
        ),
        "scientific_files_mutable_after_exposure": False,
        "provider_fallbacks_allowed": False,
        "heldout_included": False,
        "astra_included": False,
        "remaining_matrix_authorized": False,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(target)
    return value


def read_open_release_freeze(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    target = root / RELEASE_FREEZE_PATH
    if not target.is_file():
        raise ConfigurationError("The open MMMVP release execution is not frozen")
    value = json.loads(target.read_text(encoding="utf-8"))
    scientific = read_open_mmmvp_freeze(root)
    if value.get("scientific_freeze_digest") != scientific["hash_set_digest"]:
        raise ConfigurationError("Scientific and release freezes differ")
    expected = release_category_hashes(root)
    observed = value.get("categories") or {}
    for name, hashes in expected.items():
        row = observed.get(name) or {}
        if row.get("hashes") != hashes or row.get("digest") != canonical_sha256(hashes):
            raise ConfigurationError(f"Frozen release category changed: {name}")
    return value


__all__ = [
    "RELEASE_FREEZE_PATH",
    "create_open_release_freeze",
    "read_open_release_freeze",
    "release_category_hashes",
    "release_category_paths",
]

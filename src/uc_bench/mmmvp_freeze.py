"""Immutable release freeze for the five-condition, ten-model MMMVP pilot."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256, sha256_file

FREEZE_PATH = Path("artifacts/mmmvp/freeze.json")
LOCAL_GATE_PATH = Path("artifacts/mmmvp/local_gate.json")

_FIXED_FILES = (
    "configs/uc_bench_mmmvp_suite.json",
    "configs/uc_bench_mmmvp_model_panel.json",
    "configs/uc_bench_mmmvp_execution.json",
    "artifacts/mmmvp/route_contracts.json",
    "src/uc_bench/mmmvp_schema.py",
    "src/uc_bench/mmmvp_interface.py",
    "src/uc_bench/mmmvp_environment.py",
    "src/uc_bench/mmmvp_verifier.py",
    "src/uc_bench/mmmvp_score_sources.py",
    "src/uc_bench/mmmvp_provider.py",
    "src/uc_bench/mmmvp_controls.py",
    "src/uc_bench/mmmvp_trajectory.py",
    "src/uc_bench/mmmvp_runner.py",
    "src/uc_bench/mmmvp_compatibility.py",
    "src/uc_bench/mmmvp_analysis.py",
    "src/uc_bench/v08_verifier.py",
    "src/uc_bench/v08_environment.py",
    "src/uc_bench/v072_artifacts.py",
    "src/uc_bench/v072_environment.py",
    "src/uc_bench/v07_environment.py",
    "src/uc_bench/v07_cases.py",
    "src/uc_bench/v07_metrics.py",
    "src/uc_bench/durable_trajectory.py",
    "src/uc_bench/durable_runner.py",
    "src/uc_bench/v071_auth.py",
    "src/uc_bench/v062_provider.py",
    "src/uc_bench/v061_provider.py",
    "src/uc_bench/v06_provider.py",
    "src/uc_bench/docker_runtime.py",
    "scripts/build_mmmvp_route_contracts.py",
    "scripts/check_mmmvp_local_gate.py",
    "scripts/create_mmmvp_freeze.py",
    "scripts/run_mmmvp_compatibility.py",
    "scripts/run_mmmvp_matrix.py",
    "tests/test_mmmvp_verifier.py",
    "tests/test_mmmvp_provider.py",
    "tests/test_mmmvp_runner.py",
    "artifacts/mmmvp/local_gate.json"
)


def freeze_paths(project_root: Path) -> list[Path]:
    root = project_root.resolve()
    paths = [root / relative for relative in _FIXED_FILES]
    for relative_root in (
        "tasks/hard_suite_v07/development",
        "grader_private/hard_suite_v07",
    ):
        paths.extend(path for path in (root / relative_root).rglob("*") if path.is_file())
    missing = [path.relative_to(root).as_posix() for path in paths if not path.is_file()]
    if missing:
        raise ConfigurationError(f"MMMVP freeze files missing: {missing}")
    return sorted(set(paths))


def freeze_hashes(project_root: Path) -> dict[str, str]:
    root = project_root.resolve()
    return {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in freeze_paths(root)
    }


def create_mmmvp_freeze(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    target = root / FREEZE_PATH
    if target.exists():
        raise ConfigurationError("The immutable MMMVP freeze already exists")
    gate = json.loads((root / LOCAL_GATE_PATH).read_text(encoding="utf-8"))
    if gate.get("status") != "passed" or gate.get("api_requests") != 0:
        raise ConfigurationError("The zero-cost MMMVP local gate has not passed")
    panel = json.loads(
        (root / "configs/uc_bench_mmmvp_model_panel.json").read_text(encoding="utf-8")
    )
    models = [row["model_id"] for row in panel["models"]]
    if len(models) != 10 or len(models) != len(set(models)):
        raise ConfigurationError("The MMMVP panel must contain ten unique models")
    forbidden = {
        "openai/gpt-5.6-sol",
        "anthropic/claude-opus-5",
        "openai/gpt-5.5",
        "openai/gpt-6-astra",
    }
    if forbidden & set(models):
        raise ConfigurationError("A forbidden development model entered the panel")
    hashes = freeze_hashes(root)
    value = {
        "schema_version": "uc-bench-mmmvp-freeze-1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "immutable_release_candidate",
        "description": "five-condition ten-model MMMVP multi-model pilot",
        "source_scientific_version": "v0.8",
        "scientific_case_or_truth_changes": False,
        "condition_count": 5,
        "model_count": 10,
        "model_ids": models,
        "representative_sentinel_condition": "case_02",
        "scientific_episode_count": 50,
        "attempts_per_cell": 1,
        "hard_cumulative_compatibility_and_science_cap_usd": 68.0,
        "file_count": len(hashes),
        "hashes": hashes,
        "hash_set_digest": canonical_sha256(hashes),
        "heldout_included": False,
        "astra_included": False,
        "ranking_claim_allowed": False,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(target)
    return value


def read_mmmvp_freeze(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    path = root / FREEZE_PATH
    if not path.is_file():
        raise ConfigurationError("MMMVP is not frozen")
    value = json.loads(path.read_text(encoding="utf-8"))
    expected = freeze_hashes(root)
    if value.get("hashes") != expected or value.get(
        "hash_set_digest"
    ) != canonical_sha256(expected):
        raise ConfigurationError("MMMVP frozen content changed")
    if value.get("heldout_included") or value.get("astra_included"):
        raise ConfigurationError("Held-out or Astra content entered the MMMVP freeze")
    return value


__all__ = ["FREEZE_PATH", "create_mmmvp_freeze", "freeze_hashes", "read_mmmvp_freeze"]

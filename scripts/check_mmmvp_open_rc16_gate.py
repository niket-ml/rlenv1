#!/usr/bin/env python3
"""Run the complete zero-cost RC1.6 pre-freeze gate."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from uc_bench.hashing import sha256_file
from uc_bench.mmmvp_open_rc14_freeze import read_rc14_release_freeze
from uc_bench.mmmvp_open_rc15_freeze import read_rc15_release_freeze
from uc_bench.mmmvp_open_rc15_guard import FrozenByteSnapshot, run_preserving_frozen_files
from uc_bench.mmmvp_open_rc16_cost import calculate_rc16_cost_plan
from uc_bench.model_runner import _write_json

TARGET = Path("artifacts/mmmvp_open_rc16/pre_exposure_gate.json")


def _frozen_predecessor_hashes(root: Path) -> dict[str, str]:
    """Return every inherited frozen byte that mutation-prone legacy tests may touch."""
    rc14 = read_rc14_release_freeze(root)
    rc15 = read_rc15_release_freeze(root)
    protected = dict(rc15["scientific_hashes"])
    protected.update(rc14["infrastructure_hashes"])
    protected.update(rc15["infrastructure_hashes"])
    for relative in (
        "artifacts/mmmvp_open_rc14/release_freeze.json",
        "artifacts/mmmvp_open_rc15/release_freeze.json",
        "artifacts/mmmvp_open_rc15/sentinel_state.json",
        "reports/UC_BENCH_MMMVP_OPEN_RC15_CASE2_SENTINEL_STOP.md",
    ):
        protected[relative] = sha256_file(root / relative)
    gemini_root = root / (
        "build/uc_bench_mmmvp_open_rc14_runs/"
        "open-mmmvp-rc15-sentinel-00-google-gemini-3.1-pro-preview-case-02-atte"
    )
    for path in gemini_root.rglob("*"):
        if path.is_file():
            protected[path.relative_to(root).as_posix()] = sha256_file(path)
    return protected


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    rc15 = read_rc15_release_freeze(root)
    protected = _frozen_predecessor_hashes(root)
    snapshot = FrozenByteSnapshot.capture(root, protected)
    commands = [
        ["./.venv/bin/python", "-m", "pytest", "-q", "tests/test_mmmvp_open_rc16.py"],
        ["./.venv/bin/ruff", "check", "src", "tests", "scripts"],
        [
            "./.venv/bin/python",
            "-m",
            "pytest",
            "-q",
            "--ignore=tests/test_mmmvp_open_rc14.py",
        ],
        ["./.venv/bin/python", "-m", "pytest", "-q", "tests/test_mmmvp_open_rc14.py"],
        ["./.venv/bin/python", "-m", "uc_bench", "doctor"],
        ["./.venv/bin/python", "scripts/project_status.py", "--check"],
        ["./.venv/bin/python", "scripts/run_docker_preflight.py"],
        ["./.venv/bin/python", "scripts/run_mmmvp_open_rc12_docker_preflight.py"],
    ]
    results = [run_preserving_frozen_files(root, command, snapshot) for command in commands]
    evidence = {
        Path(name).stem: json.loads(
            (root / "artifacts/mmmvp_open_rc16" / name).read_text()
        )
        for name in (
            "compatibility_inheritance.json",
            "parser_trust_boundary_audit.json",
            "gemini_regression.json",
            "crash_corpus.json",
            "red_team_parser_review.json",
            "pre_freeze_rehearsal.json",
        )
    }
    cost = calculate_rc16_cost_plan(root)
    invariants = {
        "rc15_preserved": read_rc15_release_freeze(root)["infrastructure_digest"]
        == rc15["infrastructure_digest"],
        "all_zero_cost_evidence_passed": all(
            row.get("status") == "passed" and int(row.get("api_requests") or 0) == 0
            for row in evidence.values()
        ),
        "gemini_exact_regression": evidence["gemini_regression"]["partial_scientific_quality"]
        == 40.0
        and evidence["gemini_regression"]["trajectory_reconstruction"]["passed"],
        "crash_corpus_total": not evidence["crash_corpus"]["verifier_exceptions"]
        and not evidence["crash_corpus"]["hangs"],
        "previous_scores_unchanged": not evidence["crash_corpus"]["previously_gradeable_changes"],
        "reference_alternative_controls_unchanged": evidence["crash_corpus"][
            "reference_and_alternative_passes_unchanged"
        ],
        "anti_gaming_unchanged": evidence["crash_corpus"]["anti_gaming_failures_unchanged"],
        "independent_red_team_resolved": not evidence["red_team_parser_review"].get(
            "unresolved_concrete_paths"
        ),
        "rehearsal_all_paths": all(
            evidence["pre_freeze_rehearsal"][field]
            for field in (
                "valid_typed_artifact_passes",
                "gemini_scalar_is_normal_40_failure",
                "malformed_agent_artifact_fails_gracefully",
                "corrupt_environment_is_global_stop",
            )
        ),
        "nine_compatibility_passes_inherited": len(
            evidence["compatibility_inheritance"]["technically_compatible_models"]
        )
        == 9,
        "glm_excluded": evidence["compatibility_inheritance"]["provider_specific_exclusions"]
        == ["z-ai/glm-5.2"],
        "no_compatibility_calls": evidence["compatibility_inheritance"][
            "new_compatibility_requests"
        ]
        == 0,
        "p90_within_50_cap": cost["sentinel_no_cache_p90_usd"] <= 50.0,
        "all_commands_preserved_predecessor": all(
            row["frozen_predecessor_restored_and_verified"] for row in results
        ),
    }
    passed = all(row["passed"] for row in results) and all(invariants.values())
    value = {
        "schema_version": "uc-bench-open-mmmvp-rc1-6-pre-exposure-gate-1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "passed" if passed else "failed",
        "api_requests": 0,
        "scientific_requests": 0,
        "compatibility_requests": 0,
        "commands": results,
        "invariants": invariants,
        "offline_cost": {
            "median_usd": cost["sentinel_no_cache_median_usd"],
            "p90_usd": cost["sentinel_no_cache_p90_usd"],
            "p95_usd": cost["sentinel_no_cache_p95_usd"],
            "hard_cap_usd": 50.0,
        },
    }
    _write_json(root / TARGET, value, secret="")
    print(json.dumps({"status": value["status"], "api_requests": 0}, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

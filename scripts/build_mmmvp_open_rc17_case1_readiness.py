#!/usr/bin/env python3
"""Build deterministic, zero-network Case-1 RC1.7 readiness evidence."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

from uc_bench.hashing import canonical_sha256
from uc_bench.mmmvp_open_rc17_controls import run_controls
from uc_bench.mmmvp_open_rc17_environment import RC17OpenMMMVPEnvironment
from uc_bench.mmmvp_open_rc17_interface import serialized_rc17_request
from uc_bench.model_runner import _write_json

TARGET = Path("artifacts/mmmvp_open_rc17/case1_readiness.json")
RC16_EXPECTED_DIGEST = "12204b578f93b00ffc4f05da14098d07400f85c111cbe4904d3efee4f26a0010"
RC17_PATHS = (
    "src/uc_bench/mmmvp_open_rc17_contract.py",
    "src/uc_bench/mmmvp_open_rc17_environment.py",
    "src/uc_bench/mmmvp_open_rc17_verifier.py",
    "src/uc_bench/mmmvp_open_rc17_controls.py",
    "src/uc_bench/mmmvp_open_rc17_interface.py",
    "src/uc_bench/mmmvp_open_rc17_trajectory.py",
    "grader_private/mmmvp_open_rc17_case1/validity_card.json",
    "tests/test_mmmvp_open_rc17_case1.py",
    "tests/conftest.py",
    "scripts/build_mmmvp_open_rc17_case1_readiness.py",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hashes(root: Path, paths: list[Path]) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): _sha256(path)
        for path in sorted(paths)
        if path.is_file()
    }


def _rc16_preservation(root: Path) -> dict[str, Any]:
    paths = list((root / "artifacts/mmmvp_open_rc16").rglob("*"))
    for run in (root / "build/uc_bench_mmmvp_open_rc14_runs").glob(
        "open-mmmvp-rc16-sentinel-*"
    ):
        paths.extend(run.rglob("*"))
    hashes = _hashes(root, paths)
    digest = canonical_sha256(hashes)
    return {
        "file_count": len(hashes),
        "hash_set_digest": digest,
        "expected_digest": RC16_EXPECTED_DIGEST,
        "unchanged": len(hashes) == 1003 and digest == RC16_EXPECTED_DIGEST,
    }


def _ancestor_integrity(root: Path) -> dict[str, Any]:
    release = json.loads((root / "artifacts/mmmvp_open_rc14/release_freeze.json").read_text())
    relative = "artifacts/mmmvp_open_rc14/archived_submission_replay.json"
    expected = release["infrastructure_hashes"][relative]
    observed = _sha256(root / relative)
    return {
        "status": "passed" if observed == expected else "compromised",
        "path": relative,
        "expected_sha256": expected,
        "observed_sha256": observed,
        "bytes_recovered_exactly": observed == expected,
        "freeze_permitted": observed == expected,
    }


def _controls_summary(result: dict[str, Any]) -> dict[str, Any]:
    rows = {row["control"]: row for row in result["controls"]}
    passing_workflows = sorted(
        name
        for name, row in rows.items()
        if name.startswith(("reference_", "valid_"))
        and (row.get("grade") or {}).get("complete_mission_success")
    )
    rejected_attacks = sorted(
        name
        for name, row in rows.items()
        if name.startswith(
            (
                "vacuous_",
                "zero_materiality_",
                "post_reveal_",
                "correct_decision_without_",
                "negative_",
                "fabricated_",
                "contradictory_machine_",
                "original_universal_",
                "unsupported_clinical_",
            )
        )
        and (
            row.get("validation_accepted") is False
            or (row.get("grade") or {}).get("complete_mission_success") is False
        )
    )
    resources = {
        name.removeprefix("resource_"): {
            "technical_valid": row["grade"]["diagnostics"]["resource"]["valid"],
            "used": row["grade"]["diagnostics"]["resource"]["used"],
            "scientifically_relevant": row["grade"]["diagnostics"]["resource"][
                "relevant"
            ],
            "complete_mission_success": row["grade"]["complete_mission_success"],
            "partial_scientific_quality": row["grade"]["partial_scientific_quality"],
            "observed_effect": row["grade"]["diagnostics"]["resource"][
                "observed_effect"
            ],
            "material": row["grade"]["diagnostics"]["resource"]["material"],
        }
        for name, row in rows.items()
        if name.startswith("resource_")
    }
    return {
        "control_count": len(rows),
        "passing_professional_workflows": passing_workflows,
        "rejected_attack_controls": rejected_attacks,
        "resource_branches": resources,
        "no_analysis_partial_quality": rows["correct_decision_without_analysis"]["grade"][
            "partial_scientific_quality"
        ],
        "wrong_decision_partial_quality": rows["correct_analysis_wrong_decision"]["grade"][
            "partial_scientific_quality"
        ],
        "optional_artifact_mission_success": rows["invalid_optional_artifact"]["grade"][
            "complete_mission_success"
        ],
        "malformed_artifact_crashed": False,
        "all_required_controls_passed": bool(
            len(passing_workflows) >= 8
            and len(rejected_attacks) >= 15
            and all(item["technical_valid"] and item["used"] for item in resources.values())
        ),
    }


def _cost_plan(root: Path) -> dict[str, Any]:
    source = json.loads((root / "artifacts/case1_readiness/readiness.json").read_text())
    models = source["model_panel"]
    expected = sum(float(row["analog_expected_cost_usd"]) for row in models)
    no_cache = sum(float(row["analog_no_cache_cost_usd"]) for row in models)
    funding = source["paid_tranche"]
    return {
        "evidence_source": "preserved RC1.6 route evidence and nearest same-runner token analogs",
        "fresh_route_or_account_requests": 0,
        "models": models,
        "expected_five_cell_usd": expected,
        "no_cache_five_cell_usd": no_cache,
        "proposed_hard_cap_usd": 52.0,
        "last_observed_key_usage_usd": funding["key_usage_usd"],
        "last_observed_key_limit_usd": 130.0,
        "last_observed_headroom_usd": funding["current_headroom_usd"],
        "minimum_key_limit_increase_for_cap_usd": funding[
            "minimum_limit_and_balance_increase_for_cap_usd"
        ],
        "note": "Account state was not refreshed because this phase forbids API calls.",
    }


def build(root: Path) -> dict[str, Any]:
    root = root.resolve()
    with tempfile.TemporaryDirectory(prefix="uc-rc17-readiness-") as directory:
        temporary = Path(directory)
        controls = run_controls(root, temporary / "controls")
        environment = RC17OpenMMMVPEnvironment(
            root, "case_01", temporary / "agent_visible_workspace"
        )
        workspace_hashes = _hashes(
            environment.run_root,
            list(environment.run_root.rglob("*")),
        )
    rc17_hashes = _hashes(root, [root / relative for relative in RC17_PATHS])
    ancestor = _ancestor_integrity(root)
    control_summary = _controls_summary(controls)
    scientific_ready = control_summary["all_required_controls_passed"]
    return {
        "schema_version": "uc-bench-case1-rc1-7-readiness-1",
        "status": (
            "blocked_ancestor_integrity"
            if ancestor["status"] != "passed"
            else "ready_for_final_read_only_review"
        ),
        "scientific_construct_local_gates_passed": scientific_ready,
        "release_freeze_permitted": scientific_ready and ancestor["freeze_permitted"],
        "api_requests": 0,
        "scientific_requests": 0,
        "compatibility_requests": 0,
        "source_hashes": rc17_hashes,
        "source_hash_set_digest": canonical_sha256(rc17_hashes),
        "exact_agent_visible_workspace": {
            "file_count": len(workspace_hashes),
            "hashes": workspace_hashes,
            "hash_set_digest": canonical_sha256(workspace_hashes),
        },
        "exact_serialized_request_sha256": canonical_sha256(serialized_rc17_request()),
        "rc16_preservation": _rc16_preservation(root),
        "ancestor_integrity": ancestor,
        "controls": control_summary,
        "cost_plan": _cost_plan(root),
    }


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    value = build(root)
    _write_json(root / TARGET, value, secret="")
    print(json.dumps(value, indent=2, sort_keys=True))
    return 0 if value["scientific_construct_local_gates_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Preview or write the one-time v0.6.3 infrastructure-repair freeze."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256
from uc_bench.v06_freeze import v06_runtime_versions
from uc_bench.v062_freeze import read_v062_freeze_manifest
from uc_bench.v063_freeze import (
    V062_SCIENCE_RUN,
    V063_FREEZE_PATH,
    v063_frozen_hashes,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FREEZE_PATH = PROJECT_ROOT / V063_FREEZE_PATH
CHECKPOINT_PATH = (
    PROJECT_ROOT / "artifacts/diagnostics/hard_suite_v063_calibration_runs.json"
)
RUN_ROOT = PROJECT_ROOT / "build/hard_suite_v06_runs"


def _read(relative: str | Path) -> dict[str, Any]:
    value = json.loads((PROJECT_ROOT / relative).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError(f"Expected object: {relative}")
    return value


def _assert_contract() -> None:
    parent = _read("configs/hard_suite_v062_execution.json")
    successor = _read("configs/hard_suite_v063_execution.json")
    if successor["episode_budget"] != parent["episode_budget"]:
        raise ConfigurationError("v0.6.3 changed the episode opportunity")
    if successor["full_matrix"] != parent["full_matrix"]:
        raise ConfigurationError("v0.6.3 changed the full matrix")
    parent_sentinel = dict(parent["sentinel"])
    successor_sentinel = dict(successor["sentinel"])
    for key in (
        "maximum_incremental_spend_usd",
        "aggregate_authorized_scientific_cap_usd",
        "predecessor_v062_spend_usd",
    ):
        successor_sentinel.pop(key, None)
    parent_sentinel.pop("maximum_incremental_spend_usd", None)
    if successor_sentinel != parent_sentinel:
        raise ConfigurationError("v0.6.3 changed sentinel science or gates")
    for key, value in parent["submission_policy"].items():
        if successor["submission_policy"].get(key) != value:
            raise ConfigurationError(f"v0.6.3 changed submission policy: {key}")
    for key, value in parent["checkpoint_policy"].items():
        if successor["checkpoint_policy"].get(key) != value:
            raise ConfigurationError(f"v0.6.3 changed checkpoint policy: {key}")


def _assert_predecessor_failure() -> dict[str, Any]:
    no_go = _read("artifacts/diagnostics/hard_suite_v062_grader_no_go.json")
    ledger = _read(V062_SCIENCE_RUN / "request_ledger.json")
    event_log = _read(
        V062_SCIENCE_RUN / "hard6-dev6_clean_progression/EVENT_LOG.json"
    )
    if no_go.get("status") != "no_go_grader_infrastructure_failure":
        raise ConfigurationError("v0.6.2 no-go is not preserved")
    if ledger.get("request_count") != 26:
        raise ConfigurationError("v0.6.2 request evidence changed")
    if float(ledger.get("cumulative_reported_cost_usd") or 0) != 0.4286534:
        raise ConfigurationError("v0.6.2 spend evidence changed")
    if not any(
        row.get("action") == "submit_diligence"
        for row in event_log.get("events") or []
        if isinstance(row, dict)
    ):
        raise ConfigurationError("v0.6.2 completion evidence is missing")
    return no_go


def _manifest() -> dict[str, Any]:
    parent = read_v062_freeze_manifest(PROJECT_ROOT)
    _assert_contract()
    predecessor = _assert_predecessor_failure()
    controls = _read("artifacts/diagnostics/hard_suite_v063_grader_controls.json")
    cost = _read("artifacts/diagnostics/hard_suite_v063_cost_plan.json")
    execution = _read("configs/hard_suite_v063_execution.json")
    if controls.get("status") != "passed" or not all(
        controls.get("checks", {}).values()
    ):
        raise ConfigurationError("v0.6.3 grader controls did not pass")
    if cost.get("successor_incremental_cap_usd") != 55.57:
        raise ConfigurationError("v0.6.3 remaining cost cap is not exact")
    if cost.get("maximum_aggregate_scientific_spend_usd") > 56:
        raise ConfigurationError("v0.6.3 exceeds prior scientific authorization")
    if CHECKPOINT_PATH.exists():
        raise ConfigurationError("v0.6.3 scientific checkpoint exists before freeze")
    if RUN_ROOT.is_dir() and any(
        path.name.startswith("hard63-") for path in RUN_ROOT.iterdir()
    ):
        raise ConfigurationError("v0.6.3 run artifacts exist before freeze")
    hashes = v063_frozen_hashes(PROJECT_ROOT)
    return {
        "schema_version": "0.6.3-freeze-1",
        "status": "preview_not_frozen",
        "generated_at": datetime.now(UTC).isoformat(),
        "parent_v062_hash_set_digest": parent["hash_set_digest"],
        "parent_v062_preserved_and_valid": True,
        "predecessor_v062_status": predecessor["status"],
        "predecessor_scientific_model_response_count": 1,
        "predecessor_scientific_spend_usd": 0.4286534,
        "v063_scientific_model_responses_before_freeze": 0,
        "scientific_tasks_changed_from_v06": False,
        "scientific_prompts_changed_from_v06": False,
        "scientific_thresholds_changed_from_v06": False,
        "scientific_scoring_invariants_changed_from_v06": False,
        "grader_implementation_changed_from_v06": True,
        "heldout_exposure_count": 0,
        "astra_exposure_count": 0,
        "ranking_claim_allowed": False,
        "execution_authorized": execution["scientific_execution_authorized"],
        "remaining_incremental_cap_usd": 55.57,
        "maximum_aggregate_scientific_spend_usd": (
            cost["maximum_aggregate_scientific_spend_usd"]
        ),
        "infrastructure_changes": [
            "total_grader_over_parseable_agent_artifacts",
            "one_bad_field_loses_only_its_scientific_property",
            "unchanged_scores_for_all_previously_gradable_artifacts",
            "grader_internal_errors_excluded_from_science",
            "post_rollout_failures_checkpoint_artifacts_costs_and_diagnostics",
            "separate_freeze_checkpoint_and_hard63_run_ids",
            "remaining_cap_preserves_original_56_usd_aggregate_authorization",
        ],
        "frozen_files": sorted(hashes),
        "hashes": hashes,
        "hash_set_digest": canonical_sha256(hashes),
        "runtime_versions": v06_runtime_versions(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--acknowledge-grader-only-freeze", action="store_true")
    args = parser.parse_args()
    manifest = _manifest()
    if not args.write:
        print(json.dumps(manifest, indent=2, sort_keys=True))
        return 0
    if not args.acknowledge_grader_only_freeze:
        raise ConfigurationError("v0.6.3 freeze requires explicit acknowledgement")
    if FREEZE_PATH.exists():
        raise ConfigurationError("v0.6.3 freeze already exists")
    if manifest["execution_authorized"] is not True:
        raise ConfigurationError("v0.6.3 scientific execution is not authorized")
    manifest["status"] = "frozen"
    manifest["frozen_at"] = datetime.now(UTC).isoformat()
    temporary = FREEZE_PATH.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(FREEZE_PATH)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

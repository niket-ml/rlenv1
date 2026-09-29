#!/usr/bin/env python3
"""Create the immutable v0.7.2 interface-and-grader successor freeze."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from uc_bench.hashing import canonical_sha256
from uc_bench.v06_freeze import v06_runtime_versions
from uc_bench.v071_freeze import read_v071_freeze_manifest
from uc_bench.v072_freeze import (
    FREEZE_PATH,
    v072_frozen_hashes,
    v072_interface_hashes,
    v072_scientific_hashes,
    validate_v072_pre_freeze_gates,
)

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    output = ROOT / FREEZE_PATH
    if output.exists():
        raise RuntimeError("The immutable v0.7.2 freeze already exists")
    parent = read_v071_freeze_manifest(ROOT)
    validate_v072_pre_freeze_gates(ROOT)
    science = v072_scientific_hashes(ROOT)
    if science != parent["scientific_hashes"]:
        raise RuntimeError("v0.7.2 scientific content differs from v0.7/v0.7.1")
    interface = v072_interface_hashes(ROOT)
    hashes = v072_frozen_hashes(ROOT)
    manifest = {
        "schema_version": "0.7.2-freeze-1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "frozen",
        "immutable": True,
        "parent_version": "0.7.1",
        "parent_v071_hash_set_digest": parent["hash_set_digest"],
        "parent_v07_hash_set_digest": parent["parent_v07_hash_set_digest"],
        "preserved_parent_statuses": {
            "v07": "permanent_zero_spend_infrastructure_no_go",
            "v071": "infrastructure_success_scientific_construct_no_go",
        },
        "permitted_change": "explicit_interface_and_grader_only",
        "scientific_content_changed_from_v07": False,
        "scientific_hashes": science,
        "scientific_hash_count": len(science),
        "interface_and_grader_hashes": interface,
        "hashes": hashes,
        "hash_set_digest": canonical_sha256(hashes),
        "scientific_model_responses_before_freeze": 0,
        "grader_validation_replay_requests": 0,
        "grader_validation_replay_spend_usd": 0.0,
        "scientific_cap_usd": 45.0,
        "first_stage_cap_usd": 5.0,
        "later_stage_caps_usd": [12.0, 45.0],
        "model_ids_in_order": parent["model_ids_in_order"],
        "conditions_in_order": parent["conditions_in_order"],
        "checkpoint_weights": parent["checkpoint_weights"],
        "sol_gate": parent["sol_gate"],
        "two_model_gate": parent["two_model_gate"],
        "failure_handling": parent["failure_handling"],
        "headline_metric": "strict_full_mission_success",
        "diagnostic_metric": "scientific_work_quality_score",
        "reliability_reported_separately": True,
        "first_two_sol_runs_are_infrastructure_and_grader_checks_only": True,
        "ranking_claim_allowed": False,
        "pilot_description": "calibrated pilot environment or case study",
        "new_checkpoint_path": ("artifacts/diagnostics/hard_suite_v072_calibration_runs.json"),
        "new_run_root": "build/hard_suite_v072_runs",
        "heldout_exposure_count": 0,
        "astra_exposure_count": 0,
        "runtime_versions": v06_runtime_versions(),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(output)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Create the one-time immutable v0.7.1 infrastructure-successor freeze."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from uc_bench.hashing import canonical_sha256
from uc_bench.v06_freeze import v06_runtime_versions
from uc_bench.v07_freeze import read_v07_freeze_manifest
from uc_bench.v071_freeze import (
    FREEZE_PATH,
    v071_frozen_hashes,
    v071_infrastructure_hashes,
    v071_scientific_hashes,
    validate_v071_pre_freeze_gates,
)

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    output = ROOT / FREEZE_PATH
    if output.exists():
        raise RuntimeError("The immutable v0.7.1 freeze already exists")
    parent = read_v07_freeze_manifest(ROOT)
    validate_v071_pre_freeze_gates(ROOT)
    science = v071_scientific_hashes(ROOT)
    if science != parent["hashes"]:
        raise RuntimeError("v0.7.1 scientific content differs from frozen v0.7")
    infrastructure = v071_infrastructure_hashes(ROOT)
    hashes = v071_frozen_hashes(ROOT)
    manifest = {
        "schema_version": "0.7.1-freeze-1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "frozen",
        "immutable": True,
        "parent_version": "0.7",
        "parent_v07_hash_set_digest": parent["hash_set_digest"],
        "parent_v07_status": "permanent_zero_spend_infrastructure_no_go",
        "permitted_change": "authentication_client_lifecycle_only",
        "scientific_content_changed_from_v07": False,
        "scientific_hashes": science,
        "scientific_hash_count": len(science),
        "infrastructure_hashes": infrastructure,
        "hashes": hashes,
        "hash_set_digest": canonical_sha256(hashes),
        "v071_scientific_model_responses_before_freeze": 0,
        "compatibility_request_count_before_freeze": 1,
        "compatibility_request_cap_usd": 0.25,
        "scientific_cap_usd": 45.0,
        "combined_new_maximum_spend_usd": 45.25,
        "model_ids_in_order": parent["model_ids_in_order"],
        "conditions_in_order": parent["conditions_in_order"],
        "checkpoint_weights": parent["checkpoint_weights"],
        "sol_gate": parent["sol_gate"],
        "two_model_gate": parent["two_model_gate"],
        "failure_handling": parent["failure_handling"],
        "new_checkpoint_path": (
            "artifacts/diagnostics/hard_suite_v071_calibration_runs.json"
        ),
        "new_run_root": "build/hard_suite_v071_runs",
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

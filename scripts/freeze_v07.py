#!/usr/bin/env python3
"""Create the one-time v0.7 freeze after every zero-cost gate passes."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from uc_bench.hashing import canonical_sha256, sha256_file
from uc_bench.v06_freeze import v06_runtime_versions
from uc_bench.v07_freeze import FREEZE_PATH, read_v07_freeze_manifest, v07_frozen_hashes

ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> dict:
    value = json.loads((ROOT / relative).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected object: {relative}")
    return value


def main() -> int:
    target = ROOT / FREEZE_PATH
    if target.exists():
        manifest = read_v07_freeze_manifest(ROOT)
        print(json.dumps(manifest, indent=2, sort_keys=True))
        return 0
    controls = _read("artifacts/diagnostics/hard_suite_v07_controls.json")
    dependencies = _read("artifacts/diagnostics/hard_suite_v07_dependency_gate.json")
    payload = _read("artifacts/diagnostics/hard_suite_v07_exact_payload_compatibility.json")
    live = _read("artifacts/diagnostics/hard_suite_v07_pre_freeze_live_gate.json")
    cost = _read("artifacts/diagnostics/hard_suite_v07_cost_plan.json")
    execution = _read("configs/hard_suite_v07_execution.json")
    panel = _read("configs/hard_suite_v07_model_panel.json")
    if not controls.get("all_gates_pass"):
        raise ValueError("v0.7 local scientific/environment controls failed")
    if dependencies.get("status") != "passed" or dependencies.get("invariant_count") != 10:
        raise ValueError("v0.7 dependency controls failed")
    if payload.get("status") != "passed" or payload.get("new_provider_requests") != 0:
        raise ValueError("v0.7 exact payload gate failed or spent unexpectedly")
    if live.get("status") != "passed" or live.get("inference_requests") != 0:
        raise ValueError("v0.7 live route/account gate failed or spent unexpectedly")
    cap = float(execution["maximum_incremental_spend_usd"])
    if cap > 50 or cap != float(cost["proposed_hard_cap_usd"]):
        raise ValueError("v0.7 cost cap is not the authorized <=$50 exact cap")
    public_case3 = ROOT / "tasks/hard_suite_v07/development/case_03"
    public_case3_hashes = {
        path.relative_to(public_case3).as_posix(): sha256_file(path)
        for path in sorted(public_case3.rglob("*"))
        if path.is_file()
    }
    hashes = v07_frozen_hashes(ROOT)
    manifest = {
        "schema_version": "0.7-freeze-1",
        "status": "frozen",
        "immutable": True,
        "created_at": datetime.now(UTC).isoformat(),
        "suite_id": "uc_anti_tnf_predictor_diligence_v0_7",
        "model_ids_in_order": execution["model_order"],
        "model_routes": panel["models"],
        "conditions_in_order": execution["conditions_in_order"],
        "condition_count": 5,
        "episode_count": 10,
        "attempts_per_cell": 1,
        "case_03_visible_packet_hashes": public_case3_hashes,
        "case_03_only_sealed_x31_return_differs": True,
        "checkpoint_weights": _read("configs/hard_suite_v07.json")["checkpoint_weights"],
        "tool_order": [
            "inspect_workspace",
            "read_file",
            "write_file",
            "run_command",
            "save_checkpoint",
            "commit_validation_plan",
            "reveal_validation",
            "purchase_resource",
            "submit",
        ],
        "dependency_invariant_count": 10,
        "dependency_gate_status": dependencies["status"],
        "scientific_model_responses_before_freeze": 0,
        "heldout_cases_created": False,
        "heldout_exposure_count": 0,
        "astra_exposure_count": 0,
        "maximum_incremental_spend_usd": cap,
        "failure_handling": execution["failure_handling"],
        "sol_gate": execution["sol_gate"],
        "two_model_gate": execution["two_model_gate"],
        "accepted_alternatives_path": (
            "artifacts/diagnostics/hard_suite_v07_case_validity_cards.json"
        ),
        "scoring_invariants_path": "src/uc_bench/v07_grader.py",
        "cost_plan_path": "artifacts/diagnostics/hard_suite_v07_cost_plan.json",
        "exact_payload_path": (
            "artifacts/diagnostics/hard_suite_v07_exact_payload_compatibility.json"
        ),
        "pre_freeze_live_gate_path": (
            "artifacts/diagnostics/hard_suite_v07_pre_freeze_live_gate.json"
        ),
        "runtime_versions": v06_runtime_versions(),
        "hashes": hashes,
        "hash_set_digest": canonical_sha256(hashes),
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(target)
    validated = read_v07_freeze_manifest(ROOT)
    print(json.dumps(validated, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

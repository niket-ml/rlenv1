#!/usr/bin/env python3
"""Preview or write the one-time full-stack-validated v0.6.2 freeze."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256
from uc_bench.v06_freeze import v06_runtime_versions
from uc_bench.v061_freeze import read_v061_freeze_manifest
from uc_bench.v062_freeze import (
    V062_FREEZE_PATH,
    V062_FROZEN_PATHS,
    v062_frozen_hashes,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FREEZE_PATH = PROJECT_ROOT / V062_FREEZE_PATH
CHECKPOINT_PATH = (
    PROJECT_ROOT / "artifacts/diagnostics/hard_suite_v062_calibration_runs.json"
)
RUN_ROOT = PROJECT_ROOT / "build/hard_suite_v06_runs"


def _read(relative: str) -> dict[str, Any]:
    value = json.loads((PROJECT_ROOT / relative).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError(f"Expected object: {relative}")
    return value


def _assert_scientific_contract_unchanged() -> None:
    parent = _read("configs/hard_suite_v06_execution.json")
    successor = _read("configs/hard_suite_v062_execution.json")
    for name in (
        "episode_budget",
        "submission_policy",
        "full_matrix",
        "sentinel",
        "checkpoint_policy",
    ):
        if successor[name] != parent[name]:
            raise ConfigurationError(f"v0.6.2 changed scientific execution field: {name}")


def _assert_prior_failure_is_zero_response() -> dict[str, Any]:
    prior = _read("artifacts/diagnostics/hard_suite_v061_calibration_runs.json")
    runs = prior.get("runs") or []
    if (
        len(runs) != 1
        or runs[0].get("classification") != "unknown_harness_failure"
        or runs[0].get("provider_request_count") != 0
        or prior.get("response_reported_spend_usd") != 0
        or prior.get("key_usage_delta_usd") != 0
    ):
        raise ConfigurationError("v0.6.1 predecessor failure is not zero-response")
    return prior


def _manifest() -> dict[str, Any]:
    parent = read_v061_freeze_manifest(PROJECT_ROOT)
    _assert_scientific_contract_unchanged()
    prior = _assert_prior_failure_is_zero_response()
    compatibility = _read(
        "artifacts/diagnostics/hard_suite_v062_full_stack_compatibility.json"
    )
    execution = _read("configs/hard_suite_v062_execution.json")
    if (
        compatibility.get("status") != "passed"
        or compatibility.get("model_adapter_pass_count") != 5
    ):
        raise ConfigurationError("v0.6.2 full-stack compatibility did not pass 5/5")
    if compatibility.get("scientific_requests") != 0:
        raise ConfigurationError("Scientific content entered full-stack compatibility")
    if (
        compatibility.get("heldout_requests") != 0
        or compatibility.get("astra_requests") != 0
    ):
        raise ConfigurationError("Forbidden exposure entered full-stack compatibility")
    if CHECKPOINT_PATH.exists():
        raise ConfigurationError("v0.6.2 scientific checkpoint exists before freeze")
    if RUN_ROOT.is_dir() and any(
        path.name.startswith("hard62-") for path in RUN_ROOT.iterdir()
    ):
        raise ConfigurationError("v0.6.2 run artifacts exist before freeze")
    hashes = v062_frozen_hashes(PROJECT_ROOT)
    return {
        "schema_version": "0.6.2-freeze-1",
        "status": "preview_not_frozen",
        "generated_at": datetime.now(UTC).isoformat(),
        "parent_v061_hash_set_digest": parent["hash_set_digest"],
        "parent_v061_preserved_and_valid": True,
        "prior_scientific_launch_attempt_count": len(prior["runs"]),
        "prior_scientific_model_response_count": 0,
        "prior_scientific_spend_usd": 0.0,
        "scientific_tasks_changed_from_v06": False,
        "scientific_grader_changed_from_v06": False,
        "scientific_thresholds_changed_from_v06": False,
        "scientific_model_responses_before_freeze": 0,
        "heldout_exposure_count": 0,
        "astra_exposure_count": 0,
        "ranking_claim_allowed": False,
        "execution_authorized": execution["scientific_execution_authorized"],
        "infrastructure_changes": [
            "drop_only_redundant_verifiers_n_equals_one",
            "reject_any_nonunit_n_instead_of_normalizing",
            "compatibility_traverses_environment_evaluate_and_tool_loop",
            "tool_result_ingestion_recorded_on_second_provider_request",
            "request_normalization_recorded_in_every_ledger_entry",
            "separate_freeze_checkpoint_and_hard62_run_ids",
        ],
        "frozen_files": list(V062_FROZEN_PATHS),
        "hashes": hashes,
        "hash_set_digest": canonical_sha256(hashes),
        "runtime_versions": v06_runtime_versions(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--acknowledge-infrastructure-only-freeze", action="store_true")
    args = parser.parse_args()
    manifest = _manifest()
    if not args.write:
        print(json.dumps(manifest, indent=2, sort_keys=True))
        return 0
    if not args.acknowledge_infrastructure_only_freeze:
        raise ConfigurationError("v0.6.2 freeze requires explicit acknowledgement")
    if FREEZE_PATH.exists():
        raise ConfigurationError("v0.6.2 freeze already exists")
    if manifest["execution_authorized"] is not True:
        raise ConfigurationError("v0.6.2 scientific execution is not authorized")
    manifest["status"] = "frozen"
    manifest["frozen_at"] = datetime.now(UTC).isoformat()
    temporary = FREEZE_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(FREEZE_PATH)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

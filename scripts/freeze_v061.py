#!/usr/bin/env python3
"""Preview or write the one-time v0.6.1 infrastructure-only freeze."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256
from uc_bench.v06_freeze import read_v06_freeze_manifest, v06_runtime_versions
from uc_bench.v061_freeze import (
    V061_FREEZE_PATH,
    V061_FROZEN_PATHS,
    v061_frozen_hashes,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FREEZE_PATH = PROJECT_ROOT / V061_FREEZE_PATH
CHECKPOINT_PATH = (
    PROJECT_ROOT / "artifacts/diagnostics/hard_suite_v061_calibration_runs.json"
)
RUN_ROOT = PROJECT_ROOT / "build/hard_suite_v06_runs"


def _read(relative: str) -> dict[str, Any]:
    value = json.loads((PROJECT_ROOT / relative).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError(f"Expected object: {relative}")
    return value


def _assert_scientific_contract_unchanged() -> None:
    parent = _read("configs/hard_suite_v06_execution.json")
    successor = _read("configs/hard_suite_v061_execution.json")
    for name in (
        "episode_budget",
        "submission_policy",
        "full_matrix",
        "sentinel",
        "checkpoint_policy",
    ):
        if successor[name] != parent[name]:
            raise ConfigurationError(f"v0.6.1 changed scientific execution field: {name}")


def _manifest() -> dict[str, Any]:
    parent = read_v06_freeze_manifest(PROJECT_ROOT)
    _assert_scientific_contract_unchanged()
    exact = _read(
        "artifacts/diagnostics/hard_suite_v061_exact_payload_compatibility_adjudication.json"
    )
    execution = _read("configs/hard_suite_v061_execution.json")
    if exact.get("status") != "passed" or exact.get("model_response_count") != 5:
        raise ConfigurationError("v0.6.1 exact-payload compatibility did not pass 5/5")
    if exact.get("scientific_requests") != 0:
        raise ConfigurationError("Scientific content entered v0.6.1 compatibility")
    if exact.get("heldout_requests") != 0 or exact.get("astra_requests") != 0:
        raise ConfigurationError("Forbidden exposure entered v0.6.1 compatibility")
    if CHECKPOINT_PATH.exists():
        raise ConfigurationError("v0.6.1 scientific checkpoint exists before freeze")
    if RUN_ROOT.is_dir() and any(
        path.name.startswith("hard61-") for path in RUN_ROOT.iterdir()
    ):
        raise ConfigurationError("v0.6.1 run artifacts exist before freeze")
    hashes = v061_frozen_hashes(PROJECT_ROOT)
    return {
        "schema_version": "0.6.1-freeze-1",
        "status": "preview_not_frozen",
        "generated_at": datetime.now(UTC).isoformat(),
        "parent_v06_hash_set_digest": parent["hash_set_digest"],
        "parent_v06_preserved_and_valid": True,
        "scientific_tasks_changed_from_v06": False,
        "scientific_grader_changed_from_v06": False,
        "scientific_thresholds_changed_from_v06": False,
        "scientific_model_responses_before_freeze": 0,
        "non_scientific_exact_compatibility_responses": 5,
        "heldout_exposure_count": 0,
        "astra_exposure_count": 0,
        "ranking_claim_allowed": False,
        "execution_authorized": execution["scientific_execution_authorized"],
        "infrastructure_changes": [
            "credential_available_before_client_construction",
            "exact_shared_compatibility_and_scientific_request_builder",
            "max_tokens_preserved_without_sdk_rewrite",
            "optional_parameters_filtered_by_route_support",
            "provider_default_auto_normalized_to_explicit_auto",
            "actual_tool_call_required_by_exact_payload_canary",
            "auto_tool_nonselection_recorded_as_model_behavior_not_adapter_failure",
            "parameter_filter_errors_classified_as_provider_adapter_failure",
            "separate_freeze_checkpoint_and_run_ids",
        ],
        "frozen_files": list(V061_FROZEN_PATHS),
        "hashes": hashes,
        "hash_set_digest": canonical_sha256(hashes),
        "runtime_versions": v06_runtime_versions(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--preview-output", type=Path)
    parser.add_argument("--acknowledge-infrastructure-only-freeze", action="store_true")
    args = parser.parse_args()
    manifest = _manifest()
    if not args.write:
        if args.preview_output is not None:
            output = args.preview_output.resolve()
            output.relative_to(PROJECT_ROOT)
            output.parent.mkdir(parents=True, exist_ok=True)
            temporary = output.with_suffix(output.suffix + ".tmp")
            temporary.write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            temporary.replace(output)
        print(json.dumps(manifest, indent=2, sort_keys=True))
        return 0
    if not args.acknowledge_infrastructure_only_freeze:
        raise ConfigurationError("v0.6.1 freeze requires explicit acknowledgement")
    if FREEZE_PATH.exists():
        raise ConfigurationError("v0.6.1 freeze already exists")
    if manifest["execution_authorized"] is not True:
        raise ConfigurationError("v0.6.1 scientific execution is not authorized")
    manifest["status"] = "frozen"
    manifest["frozen_at"] = datetime.now(UTC).isoformat()
    temporary = FREEZE_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(FREEZE_PATH)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

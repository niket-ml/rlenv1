#!/usr/bin/env python3
"""Run v0.6.3 with total grading and checkpoint-safe post-processing."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import run_v06_pilot as v06_pilot

from uc_bench.v061_provider import verify_live_v061_identity
from uc_bench.v062_provider import load_v062_provider_adapters
from uc_bench.v063_freeze import read_v063_freeze_manifest, v063_frozen_hashes
from uc_bench.v063_runner import run_v063_episode

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "artifacts/diagnostics/hard_suite_v063_calibration_runs.json"
EXECUTION_PATH = PROJECT_ROOT / "configs/hard_suite_v063_execution.json"
COST_PATH = PROJECT_ROOT / "artifacts/diagnostics/hard_suite_v063_cost_plan.json"


def _write_checkpoint(value: dict[str, Any]) -> None:
    temporary = OUTPUT_PATH.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(OUTPUT_PATH)


def main() -> int:
    originals = {
        "EXECUTION_PATH": v06_pilot.EXECUTION_PATH,
        "COST_PATH": v06_pilot.COST_PATH,
        "OUTPUT_PATH": v06_pilot.OUTPUT_PATH,
        "read_v06_freeze_manifest": v06_pilot.read_v06_freeze_manifest,
        "v06_frozen_hashes": v06_pilot.v06_frozen_hashes,
        "load_provider_adapters": v06_pilot.load_provider_adapters,
        "verify_live_adapter_identity": v06_pilot.verify_live_adapter_identity,
        "run_v06_episode": v06_pilot.run_v06_episode,
        "attempt_control": v06_pilot.attempt_control,
        "_checkpoint": v06_pilot._checkpoint,
    }
    original_checkpoint = v06_pilot._checkpoint
    original_attempt_control = v06_pilot.attempt_control

    def authorized_episode(project_root: Path, config: Any, *, openrouter_key: str) -> Any:
        manifest = read_v063_freeze_manifest(project_root)
        return run_v063_episode(
            project_root,
            config,
            openrouter_key=openrouter_key,
            authorization_digest=str(manifest["hash_set_digest"]),
        )

    def attempt_control(
        classification: str,
        *,
        execution_attempt: int,
        retry_limit: int,
    ) -> tuple[str, str | None]:
        if classification in {
            "grader_infrastructure_failure",
            "post_rollout_infrastructure_failure",
        }:
            return "stop", classification
        return original_attempt_control(
            classification,
            execution_attempt=execution_attempt,
            retry_limit=retry_limit,
        )

    def checkpoint(**kwargs: Any) -> dict[str, Any]:
        value = original_checkpoint(**kwargs)
        value["schema_version"] = "0.6.3-pilot-1"
        value["runner_revision"] = "0.6.3"
        value[
            "scientific_contract_revision"
        ] = "0.6-tasks-prompts-thresholds-and-scoring-invariants"
        value["parent_v062_checkpoint_used"] = False
        value["predecessor_v062_scientific_spend_usd"] = 0.4286534
        value["aggregate_scientific_spend_usd"] = round(
            0.4286534 + float(value.get("response_reported_spend_usd") or 0),
            8,
        )
        value["aggregate_authorized_scientific_cap_usd"] = 56.0
        _write_checkpoint(value)
        return value

    try:
        v06_pilot.EXECUTION_PATH = EXECUTION_PATH
        v06_pilot.COST_PATH = COST_PATH
        v06_pilot.OUTPUT_PATH = OUTPUT_PATH
        v06_pilot.read_v06_freeze_manifest = read_v063_freeze_manifest
        v06_pilot.v06_frozen_hashes = v063_frozen_hashes
        v06_pilot.load_provider_adapters = load_v062_provider_adapters
        v06_pilot.verify_live_adapter_identity = verify_live_v061_identity
        v06_pilot.run_v06_episode = authorized_episode
        v06_pilot.attempt_control = attempt_control
        v06_pilot._checkpoint = checkpoint
        return v06_pilot.main()
    finally:
        for name, value in originals.items():
            setattr(v06_pilot, name, value)


if __name__ == "__main__":
    raise SystemExit(main())

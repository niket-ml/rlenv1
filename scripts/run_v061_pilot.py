#!/usr/bin/env python3
"""Run v0.6.1 through the frozen v0.6 pilot logic with new infrastructure."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import run_v06_pilot as v06_pilot

from uc_bench.v061_freeze import read_v061_freeze_manifest, v061_frozen_hashes
from uc_bench.v061_provider import (
    load_v061_provider_adapters,
    verify_live_v061_identity,
)
from uc_bench.v061_runner import run_v061_episode

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "artifacts/diagnostics/hard_suite_v061_calibration_runs.json"
EXECUTION_PATH = PROJECT_ROOT / "configs/hard_suite_v061_execution.json"


def _write_checkpoint(value: dict[str, Any]) -> None:
    temporary = OUTPUT_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(OUTPUT_PATH)


def main() -> int:
    """Install versioned infrastructure bindings, then use the audited loop."""

    originals = {
        "EXECUTION_PATH": v06_pilot.EXECUTION_PATH,
        "OUTPUT_PATH": v06_pilot.OUTPUT_PATH,
        "read_v06_freeze_manifest": v06_pilot.read_v06_freeze_manifest,
        "v06_frozen_hashes": v06_pilot.v06_frozen_hashes,
        "load_provider_adapters": v06_pilot.load_provider_adapters,
        "verify_live_adapter_identity": v06_pilot.verify_live_adapter_identity,
        "run_v06_episode": v06_pilot.run_v06_episode,
        "_checkpoint": v06_pilot._checkpoint,
    }
    original_checkpoint = v06_pilot._checkpoint

    def authorized_episode(project_root: Path, config: Any, *, openrouter_key: str) -> Any:
        manifest = read_v061_freeze_manifest(project_root)
        return run_v061_episode(
            project_root,
            config,
            openrouter_key=openrouter_key,
            authorization_digest=str(manifest["hash_set_digest"]),
        )

    def checkpoint(**kwargs: Any) -> dict[str, Any]:
        value = original_checkpoint(**kwargs)
        value["schema_version"] = "0.6.1-pilot-1"
        value["runner_revision"] = "0.6.1"
        value["scientific_contract_revision"] = "0.6-byte-identical"
        value["parent_v06_checkpoint_used"] = False
        _write_checkpoint(value)
        return value

    try:
        v06_pilot.EXECUTION_PATH = EXECUTION_PATH
        v06_pilot.OUTPUT_PATH = OUTPUT_PATH
        v06_pilot.read_v06_freeze_manifest = read_v061_freeze_manifest
        v06_pilot.v06_frozen_hashes = v061_frozen_hashes
        v06_pilot.load_provider_adapters = load_v061_provider_adapters
        v06_pilot.verify_live_adapter_identity = verify_live_v061_identity
        v06_pilot.run_v06_episode = authorized_episode
        v06_pilot._checkpoint = checkpoint
        return v06_pilot.main()
    finally:
        for name, value in originals.items():
            setattr(v06_pilot, name, value)


if __name__ == "__main__":
    raise SystemExit(main())

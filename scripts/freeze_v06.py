#!/usr/bin/env python3
"""Preview or explicitly write the v0.6 pre-exposure freeze manifest."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256
from uc_bench.v06_freeze import (
    V06_FROZEN_PATHS,
    v06_frozen_hashes,
    v06_runtime_versions,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FREEZE_PATH = PROJECT_ROOT / "artifacts/diagnostics/hard_suite_v06_freeze.json"
SCIENTIFIC_CHECKPOINT_PATH = (
    PROJECT_ROOT / "artifacts/diagnostics/hard_suite_v06_calibration_runs.json"
)
SCIENTIFIC_RUN_ROOT = PROJECT_ROOT / "build/hard_suite_v06_runs"


def _read(relative: str) -> dict[str, Any]:
    value = json.loads((PROJECT_ROOT / relative).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError(f"Expected object: {relative}")
    return value


def _manifest() -> dict[str, Any]:
    panel = _read("configs/hard_suite_v06_model_panel.json")
    execution = _read("configs/hard_suite_v06_execution.json")
    controls = _read("artifacts/diagnostics/hard_suite_v06_controls.json")
    compatibility = _read("artifacts/diagnostics/hard_suite_v06_compatibility.json")
    cost = _read("artifacts/diagnostics/hard_suite_v06_cost_plan.json")
    if SCIENTIFIC_CHECKPOINT_PATH.exists():
        raise ConfigurationError("v0.6 scientific checkpoint exists before freeze")
    if SCIENTIFIC_RUN_ROOT.is_dir() and any(SCIENTIFIC_RUN_ROOT.iterdir()):
        raise ConfigurationError("v0.6 scientific run artifacts exist before freeze")
    if controls.get("all_local_gates_pass") is not True:
        raise ConfigurationError("v0.6 local controls do not pass")
    if compatibility.get("status") != "passed" or compatibility.get("astra_requests") != 0:
        raise ConfigurationError("v0.6 compatibility does not pass cleanly")
    if cost.get("status") != "ready_for_explicit_freeze_decision":
        raise ConfigurationError("v0.6 cost gate is incomplete")
    if panel.get("heldout_ceiling_probe_configured") is not False:
        raise ConfigurationError("A held-out ceiling probe entered the development panel")
    hashes = v06_frozen_hashes(PROJECT_ROOT)
    return {
        "schema_version": "0.6-freeze-1",
        "status": "preview_not_frozen",
        "generated_at": datetime.now(UTC).isoformat(),
        "frozen_before_scientific_model_calls": False,
        "would_freeze_before_scientific_model_calls": True,
        "scientific_model_calls_before_freeze": 0,
        "compatibility_calls_are_non_scientific": True,
        "heldout_exposure_count": 0,
        "astra_exposure_count": 0,
        "ranking_claim_allowed": False,
        "model_ids": [str(row["model_id"]) for row in panel["models"]],
        "provider_routes": {
            str(row["model_id"]): list(row["provider_order"])
            for row in panel["models"]
        },
        "development_scenario_ids": [
            str(row["scenario_id"])
            for row in _read("configs/hard_suite_v06.json")["development_scenarios"]
        ],
        "episode_budget": execution["episode_budget"],
        "sentinel": execution["sentinel"],
        "full_matrix": execution["full_matrix"],
        "acceptance_gates": _read("configs/hard_suite_v06.json")[
            "development_acceptance_gates"
        ],
        "frozen_files": list(V06_FROZEN_PATHS),
        "hashes": hashes,
        "hash_set_digest": canonical_sha256(hashes),
        "runtime_versions": v06_runtime_versions(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--preview-output", type=Path)
    parser.add_argument("--acknowledge-final-pre-exposure-freeze", action="store_true")
    args = parser.parse_args()
    manifest = _manifest()
    if not args.write:
        if args.preview_output is not None:
            output = args.preview_output.resolve()
            try:
                output.relative_to(PROJECT_ROOT)
            except ValueError as exc:
                raise ConfigurationError(
                    "Freeze preview output must remain inside the project"
                ) from exc
            output.parent.mkdir(parents=True, exist_ok=True)
            temporary = output.with_suffix(output.suffix + ".tmp")
            temporary.write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            temporary.replace(output)
        print(json.dumps(manifest, indent=2, sort_keys=True))
        return 0
    if not args.acknowledge_final_pre_exposure_freeze:
        raise ConfigurationError("Freeze write requires the explicit acknowledgement flag")
    if FREEZE_PATH.exists():
        raise ConfigurationError("v0.6 freeze already exists and cannot be overwritten")
    panel = _read("configs/hard_suite_v06_model_panel.json")
    execution = _read("configs/hard_suite_v06_execution.json")
    if panel.get("freeze_authorized") is not True:
        raise ConfigurationError("Panel freeze is not authorized")
    if execution.get("scientific_execution_authorized") is not True:
        raise ConfigurationError("Scientific execution is not authorized")
    manifest["status"] = "frozen"
    manifest["frozen_before_scientific_model_calls"] = True
    manifest["frozen_at"] = datetime.now(UTC).isoformat()
    temporary = FREEZE_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(FREEZE_PATH)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Create or verify the v0.4 pre-model-call freeze manifest."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.hashing import sha256_file
from uc_bench.v04_freeze import V04_FROZEN_FILES, v04_frozen_hashes

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FREEZE_PATH = PROJECT_ROOT / "artifacts" / "diagnostics" / "hard_suite_v04_freeze.json"
AMENDMENT_PATH = (
    PROJECT_ROOT
    / "artifacts"
    / "diagnostics"
    / "hard_suite_v04_freeze_amendment_01.json"
)
RUNS_PATH = PROJECT_ROOT / "artifacts" / "diagnostics" / "hard_suite_v04_calibration_runs.json"


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected JSON object: {path}")
    return value


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _pre_freeze_model_calls() -> int:
    if not RUNS_PATH.exists():
        return 0
    return int(_read(RUNS_PATH).get("executed_request_count") or 0)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--amend-cost-field", action="store_true")
    args = parser.parse_args()
    hashes = v04_frozen_hashes(PROJECT_ROOT)
    if args.write and args.amend_cost_field:
        raise SystemExit("Choose either --write or --amend-cost-field")
    if args.amend_cost_field:
        if not FREEZE_PATH.exists():
            raise SystemExit("Cannot amend an absent base freeze manifest")
        if AMENDMENT_PATH.exists():
            raise SystemExit("Freeze amendment already exists; do not overwrite it")
        calls = _pre_freeze_model_calls()
        if calls:
            raise SystemExit(f"Refusing post-exposure amendment: {calls} requests exist")
        artifact = {
            "schema_version": "0.4",
            "amendment_id": "freeze_amendment_01",
            "amended_at": datetime.now(UTC).isoformat(),
            "reason": (
                "Pre-exposure cost guard referenced remaining_usd instead of the actual "
                "OpenRouterKeyStatus field limit_remaining_usd. No task, evidence, grader, "
                "prompt, model, seed, or budget changed."
            ),
            "parent_freeze_path": FREEZE_PATH.relative_to(PROJECT_ROOT).as_posix(),
            "parent_freeze_sha256": sha256_file(FREEZE_PATH),
            "frozen_before_model_calls": True,
            "v04_model_calls_before_amendment": 0,
            "astra_exposure_count": 0,
            "ranking_claim_allowed": False,
            "files": {
                name: path.as_posix() for name, path in V04_FROZEN_FILES.items()
            },
            "hashes": hashes,
        }
        _write(AMENDMENT_PATH, artifact)
        print(json.dumps(artifact, indent=2))
        return 0
    if args.write:
        if FREEZE_PATH.exists():
            raise SystemExit("Freeze manifest already exists; do not overwrite it")
        calls = _pre_freeze_model_calls()
        if calls:
            raise SystemExit(f"Refusing post-exposure freeze: {calls} v0.4 requests exist")
        controls = _read(
            PROJECT_ROOT / "artifacts" / "diagnostics" / "hard_suite_v04_controls.json"
        )
        if not controls.get("all_gates_pass"):
            raise SystemExit("Cannot freeze: v0.4 local gates do not all pass")
        artifact = {
            "schema_version": "0.4",
            "frozen_at": datetime.now(UTC).isoformat(),
            "frozen_before_model_calls": True,
            "v04_model_calls_before_freeze": 0,
            "astra_exposure_count": 0,
            "ranking_claim_allowed": False,
            "files": {
                name: path.as_posix() for name, path in V04_FROZEN_FILES.items()
            },
            "hashes": hashes,
        }
        _write(FREEZE_PATH, artifact)
        print(json.dumps(artifact, indent=2))
        return 0
    active_path = AMENDMENT_PATH if AMENDMENT_PATH.exists() else FREEZE_PATH
    if not active_path.exists():
        print(json.dumps({"frozen": False, "reason": "manifest absent"}, indent=2))
        return 1
    manifest = _read(active_path)
    valid = manifest.get("hashes") == hashes
    print(
        json.dumps(
            {
                "frozen": True,
                "active_manifest": active_path.relative_to(PROJECT_ROOT).as_posix(),
                "hashes_match": valid,
            },
            indent=2,
        )
    )
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Create or verify the one-time v0.5 pre-model-call freeze manifest."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.v05_freeze import V05_FROZEN_FILES, v05_frozen_hashes

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FREEZE_PATH = PROJECT_ROOT / "artifacts" / "diagnostics" / "hard_suite_v05_freeze.json"
RUNS_PATH = PROJECT_ROOT / "artifacts" / "diagnostics" / "hard_suite_v05_calibration_runs.json"
CONTROLS_PATH = PROJECT_ROOT / "artifacts" / "diagnostics" / "hard_suite_v05_controls.json"


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


def _request_count() -> int:
    if not RUNS_PATH.exists():
        return 0
    return int(_read(RUNS_PATH).get("executed_request_count") or 0)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    hashes = v05_frozen_hashes(PROJECT_ROOT)
    if args.write:
        if FREEZE_PATH.exists():
            raise SystemExit("v0.5 freeze already exists; never overwrite it")
        requests = _request_count()
        if requests:
            raise SystemExit(f"Refusing post-exposure freeze: {requests} requests exist")
        controls = _read(CONTROLS_PATH)
        if not controls.get("all_local_gates_passed"):
            raise SystemExit("Cannot freeze: v0.5 local gates do not all pass")
        artifact = {
            "schema_version": "0.5",
            "frozen_at": datetime.now(UTC).isoformat(),
            "frozen_before_model_calls": True,
            "v05_model_calls_before_freeze": 0,
            "astra_exposure_count": 0,
            "ranking_claim_allowed": False,
            "files": {name: path.as_posix() for name, path in V05_FROZEN_FILES.items()},
            "hashes": hashes,
        }
        _write(FREEZE_PATH, artifact)
        print(json.dumps(artifact, indent=2))
        return 0
    if not FREEZE_PATH.exists():
        print(json.dumps({"frozen": False, "reason": "manifest absent"}, indent=2))
        return 1
    manifest = _read(FREEZE_PATH)
    valid = manifest.get("hashes") == hashes
    print(
        json.dumps(
            {
                "frozen": True,
                "hashes_match": valid,
                "v05_model_calls_before_freeze": manifest.get("v05_model_calls_before_freeze"),
                "astra_exposure_count": manifest.get("astra_exposure_count"),
            },
            indent=2,
        )
    )
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())

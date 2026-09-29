#!/usr/bin/env python3
"""Validate and record the diagnostic-suite design gate."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from uc_bench.diagnostic_suite import validate_diagnostic_suite

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "configs" / "diagnostic_suite.json"
OUTPUT_PATH = PROJECT_ROOT / "artifacts" / "diagnostics" / "suite_validation.json"


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def main() -> int:
    validation = validate_diagnostic_suite(read_json(CONFIG_PATH)).to_dict()
    output = {
        "schema_version": "0.1",
        "suite_config": CONFIG_PATH.relative_to(PROJECT_ROOT).as_posix(),
        **validation,
        "status": "pass" if validation["calibration_ready"] else "implementation_incomplete",
        "ranking_claim_allowed": False,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

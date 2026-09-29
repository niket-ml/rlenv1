#!/usr/bin/env python3
"""Run and persist the automated UC-Bench pre-release audit."""

from __future__ import annotations

import json
from pathlib import Path

from uc_bench.release_audit import run_pre_release_audit

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    result = run_pre_release_audit(PROJECT_ROOT)
    output = PROJECT_ROOT / "artifacts" / "release" / "pre_release_audit.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

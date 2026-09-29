#!/usr/bin/env python3
"""Audit RC1.2 submission friction separately at zero API cost."""

from __future__ import annotations

import json
from pathlib import Path

from uc_bench.mmmvp_open_rc13_analysis import analyze_rc12_submission_friction


def main() -> int:
    value = analyze_rc12_submission_friction(Path(__file__).resolve().parents[1])
    print(
        json.dumps(
            {
                "status": value["status"],
                "models": value["model_count"],
                "warnings": value["warnings"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

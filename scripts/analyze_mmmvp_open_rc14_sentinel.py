#!/usr/bin/env python3
"""Analyze the completed or stopped RC1.4 sentinel without model calls."""

from __future__ import annotations

import json
from pathlib import Path

from uc_bench.mmmvp_open_rc14_analysis import (
    analyze_rc14_sentinel,
    write_rc14_report,
)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    analysis = analyze_rc14_sentinel(root)
    report = write_rc14_report(root, analysis)
    print(
        json.dumps(
            {
                "status": analysis["status"],
                "decision": analysis["decision"],
                "completed_model_count": analysis["completed_model_count"],
                "report": report.relative_to(root).as_posix(),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

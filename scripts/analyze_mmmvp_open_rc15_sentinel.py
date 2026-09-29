#!/usr/bin/env python3
"""Analyze and report the RC1.5 Case-2 sentinel."""

from __future__ import annotations

import json
from pathlib import Path

from uc_bench.mmmvp_open_rc15_analysis import (
    analyze_rc15_sentinel,
    write_rc15_report,
)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    analysis = analyze_rc15_sentinel(root)
    report = write_rc15_report(root, analysis)
    print(
        json.dumps(
            {
                "conclusion": analysis["conclusion"],
                "model_count": analysis["model_count"],
                "report": report.relative_to(root).as_posix(),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

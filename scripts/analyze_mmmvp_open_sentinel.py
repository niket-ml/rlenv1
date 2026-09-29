#!/usr/bin/env python3
"""Render the deterministic open-MMMVP Case-2 sentinel report."""

from __future__ import annotations

import json
from pathlib import Path

from uc_bench.mmmvp_open_sentinel_analysis import (
    ANALYSIS_PATH,
    REPORT_PATH,
    build_open_sentinel_analysis,
    render_open_sentinel_report,
)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    analysis = build_open_sentinel_analysis(root)
    report = root / REPORT_PATH
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(render_open_sentinel_report(analysis), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": analysis["status"],
                "recommendation": analysis["recommendation"],
                "models": analysis["sentinel_models_completed"],
                "analysis": ANALYSIS_PATH.as_posix(),
                "report": REPORT_PATH.as_posix(),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

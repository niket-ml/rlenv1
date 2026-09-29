#!/usr/bin/env python3
"""Analyze the completed-or-stopped RC1.2 sentinel without model calls."""

from __future__ import annotations

import json
from pathlib import Path

from uc_bench.mmmvp_open_rc12_analysis import (
    REPORT_PATH,
    build_rc12_sentinel_analysis,
    render_rc12_report,
)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    analysis = build_rc12_sentinel_analysis(root)
    report = root / REPORT_PATH
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(render_rc12_report(analysis), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": analysis["status"],
                "recommendation": analysis["recommendation"],
                "model_count": len(analysis["models"]),
                "scientific_total_usd": analysis["scientific_total_usd"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

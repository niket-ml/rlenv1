#!/usr/bin/env python3
"""Analyze a completed, stopped or cost-blocked RC1.3 sentinel without calls."""

from __future__ import annotations

import json
from pathlib import Path

from uc_bench.mmmvp_open_rc13_analysis import REPORT_PATH, analyze_rc13_sentinel


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    analysis = analyze_rc13_sentinel(root)
    report = root / REPORT_PATH
    report.parent.mkdir(parents=True, exist_ok=True)
    if analysis["status"] == "not_executed":
        cost = analysis["cost_plan"]
        text = f"""# UC-Bench open MMMVP RC1.3 Case-2 sentinel

**NO_GO — predeclared cost gate.** No RC1.3 model call was made.

- Ten-cell no-cache median: ${cost['ten_cell_no_cache_median_usd']:.2f}
- Ten-cell no-cache P90: ${cost['ten_cell_no_cache_p90_usd']:.2f}
- Authorized hard cap: ${cost['authorized_cap_usd']:.2f}
- Minimum total cap required: ${cost['minimum_total_cap_required_usd']:.2f}
- Exact account top-up required: ${cost['exact_account_top_up_required_usd']:.2f}

RC1.3 passed its infrastructure gate and remains a frozen, zero-science-spend
successor. The Case-2 capability gradient and submission-friction floor remain
unassessed in RC1.3.
"""
    else:
        lines = [
            "# UC-Bench open MMMVP RC1.3 Case-2 sentinel",
            "",
            f"Status: **{analysis['status']}**.",
            "",
            "| Model | Mission | Partial | Reliability | Rejections | Framework errors | Cost |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
        for row in analysis["models"]:
            friction = row["submission_friction"]
            lines.append(
                f"| `{row['model_id']}` | {row['complete_mission_success']} | "
                f"{row['partial_scientific_quality']} | {row['reliability_score']} | "
                f"{friction['rejected_submission_count']} | "
                f"{row['framework_tool_error_count']} | ${float(row['cost_usd'] or 0):.4f} |"
            )
        text = "\n".join(lines) + "\n"
    report.write_text(text, encoding="utf-8")
    print(
        json.dumps(
            {
                "status": analysis["status"],
                "recommendation": analysis["recommendation"],
                "model_count": len(analysis["models"]),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

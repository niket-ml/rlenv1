#!/usr/bin/env python3
"""Write the frozen v0.7 development analysis and compact report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from uc_bench.v07_analysis import analyze_v07

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "artifacts/diagnostics/hard_suite_v07_calibration_runs.json"
OUTPUT = ROOT / "artifacts/diagnostics/hard_suite_v07_analysis.json"
REPORT = ROOT / "reports/generated/hard_suite_v07_calibration.md"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--grader-wording-failure", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    checkpoint = json.loads(RUNS.read_text(encoding="utf-8"))
    analysis = analyze_v07(
        list(checkpoint.get("runs") or []),
        manual_grader_wording_failure=args.grader_wording_failure,
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(analysis, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(OUTPUT)
    lines = [
        "# UC-Bench v0.7 bounded development calibration",
        "",
        f"**Decision:** {analysis['go_no_go']}",
        "",
        (
            "This is controlled, one-seed internal calibration—not a stable ranking "
            "or external validation."
        ),
        "",
        "## Sol gate",
        "",
        f"```json\n{json.dumps(analysis['sol_gate'], indent=2, sort_keys=True)}\n```",
        "",
        "## Model × milestone",
        "",
        f"```json\n{json.dumps(analysis['model_by_milestone'], indent=2, sort_keys=True)}\n```",
        "",
        "## Model × controlled failure state",
        "",
        "```json\n"
        + json.dumps(
            analysis["model_by_controlled_failure_state"], indent=2, sort_keys=True
        )
        + "\n```",
        "",
        "## Failure evidence and remedies",
        "",
        "```json\n"
        + json.dumps(analysis["scientific_failure_evidence"], indent=2, sort_keys=True)
        + "\n```",
        "",
        "## Claim limits",
        "",
        *[f"- {value}" for value in analysis["claim_limits"]],
        "",
    ]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    report_temp = REPORT.with_suffix(".md.tmp")
    report_temp.write_text("\n".join(lines), encoding="utf-8")
    report_temp.replace(REPORT)
    print(json.dumps(analysis, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

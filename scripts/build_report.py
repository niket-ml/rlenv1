#!/usr/bin/env python3
"""Build the self-contained UC-Bench report without inventing model results."""

from __future__ import annotations

from pathlib import Path

from uc_bench.reporting import load_json, render_report

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    output = render_report(
        evaluation=load_json(
            PROJECT_ROOT / "reports" / "generated" / "evaluation_summary.json"
        ),
        reference_separation=load_json(
            PROJECT_ROOT / "artifacts" / "grading" / "reference_separation.json"
        ),
        variant_controls=load_json(
            PROJECT_ROOT / "artifacts" / "variants" / "scenario_controls.json"
        ),
        runtime_smoke=load_json(
            PROJECT_ROOT / "artifacts" / "runtime" / "infrastructure_smoke.json"
        ),
    )
    output_path = PROJECT_ROOT / "reports" / "generated" / "index.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(output, encoding="utf-8")
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Build the staged v0.7.2 cost plan from preserved v0.7.1 usage."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "artifacts/diagnostics/hard_suite_v071_calibration_runs.json"
PARENT = ROOT / "artifacts/diagnostics/hard_suite_v07_cost_plan.json"
OUTPUT = ROOT / "artifacts/diagnostics/hard_suite_v072_cost_plan.json"


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected object: {path}")
    return value


def main() -> int:
    source = _read(SOURCE)
    parent = _read(PARENT)
    sol_rows = [row for row in source["runs"] if row["model_id"] == "openai/gpt-5.6-sol"]
    if len(sol_rows) != 5:
        raise RuntimeError("Expected five preserved v0.7.1 Sol costs")
    costs = [float(row["cumulative_reported_cost_usd"]) for row in sol_rows]
    by_condition = {
        str(row["condition_id"]): float(row["cumulative_reported_cost_usd"]) for row in sol_rows
    }
    exact_two_case_baseline = by_condition["case_01"] + by_condition["case_03_signal_collapses"]
    interface_multiplier = 1.25
    no_cache_multiplier = 1.10
    sol_parent = parent["per_model"]["openai/gpt-5.6-sol"]
    gpt52_parent = parent["per_model"]["openai/gpt-5.2"]
    result = {
        "schema_version": "0.7.2-staged-cost-1",
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "predeclared_no_paid_execution",
        "basis": {
            "preserved_v071_sol_episode_costs_usd": costs,
            "preserved_v071_sol_median_usd": round(median(costs), 8),
            "preserved_v071_sol_total_usd": round(sum(costs), 8),
            "exact_case_01_plus_case_03_collapse_baseline_usd": round(exact_two_case_baseline, 8),
            "interface_and_artifact_overhead_multiplier": interface_multiplier,
            "no_cache_safety_multiplier": no_cache_multiplier,
            "parent_v07_gpt52_estimates_retained_because_no_v071_gpt52_run": True,
        },
        "stages": [
            {
                "stage_id": "sol_two_case_grader_check",
                "episodes": 2,
                "expected_usd": round(exact_two_case_baseline * interface_multiplier, 2),
                "no_cache_p90_usd": round(
                    2 * float(sol_parent["v07_no_cache_p90_per_episode"]) * no_cache_multiplier,
                    2,
                ),
                "hard_cumulative_cap_usd": 5.0,
                "mandatory_manual_stop_after_stage": True,
            },
            {
                "stage_id": "all_five_sol",
                "episodes": 5,
                "expected_usd": round(sum(costs) * interface_multiplier, 2),
                "no_cache_p90_usd": round(
                    5 * float(sol_parent["v07_no_cache_p90_per_episode"]) * no_cache_multiplier,
                    2,
                ),
                "hard_cumulative_cap_usd": 12.0,
                "requires_separate_approval": True,
            },
            {
                "stage_id": "ten_episode_two_model_matrix",
                "episodes": 10,
                "expected_cached_usd": round(
                    sum(costs) * interface_multiplier
                    + 5
                    * float(gpt52_parent["v07_cached_median_per_episode"])
                    * interface_multiplier,
                    2,
                ),
                "parent_no_cache_p90_usd": float(parent["no_cache_p90_total_usd"]),
                "hard_cumulative_cap_usd": 45.0,
                "requires_separate_approval": True,
                "warning": (
                    "The $45 inherited cap is a hard stop, not permission to exceed it; "
                    "a no-cache tail may truncate the matrix."
                ),
            },
        ],
        "likely_wall_clock_hours": {
            "two_case_check": [0.3, 1.4],
            "five_sol": [0.8, 3.0],
            "full_ten_if_later_authorized": [1.5, 6.0],
        },
        "compatibility_spend_already_incurred_usd": 0.0,
        "v072_new_api_requests_at_plan_time": 0,
        "v072_new_api_spend_at_plan_time_usd": 0.0,
        "first_paid_command": (
            "PYTHONPATH=src ./.venv/bin/python scripts/run_v072_pilot.py "
            "--stage sol_two_case_grader_check --execute "
            "--maximum-incremental-spend-usd 5.00"
        ),
        "heldout_requests": 0,
        "astra_requests": 0,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(OUTPUT)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

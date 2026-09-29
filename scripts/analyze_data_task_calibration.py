#!/usr/bin/env python3
"""Analyze the frozen data-task calibration without mutating its raw runs."""

from __future__ import annotations

import json
from collections import Counter
from itertools import pairwise
from pathlib import Path
from statistics import mean
from typing import Any

from jsonschema import Draft202012Validator

from uc_bench.data_diagnostics import grade_data_diagnostic, solve_data_diagnostic
from uc_bench.hashing import sha256_file

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_PATH = PROJECT_ROOT / "artifacts" / "diagnostics" / "data_task_calibration_runs.json"
CONFIG_PATH = PROJECT_ROOT / "configs" / "data_task_calibration.json"
OUTPUT_PATH = PROJECT_ROOT / "artifacts" / "diagnostics" / "data_task_calibration_analysis.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "generated" / "data_task_calibration.md"
COMPONENTS = ("decision", "metrics", "diagnosis", "affected_ids", "method_and_action")


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected JSON object: {path}")
    return value


def selected_scored_rows(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Keep the one non-infrastructure result for every frozen matrix cell."""

    rows = [row for row in raw["runs"] if row["classification"] != "infrastructure_failure"]
    keys = [
        (
            str(row["model_id"]),
            str(row["task_id"]),
            str(row["scenario_id"]),
            int(row["attempt_index"]),
        )
        for row in rows
    ]
    if len(keys) != len(set(keys)):
        raise ValueError("Multiple non-infrastructure results exist for a calibration cell")
    return rows


def _schema_errors(value: Any, schema: dict[str, Any]) -> list[str]:
    return [
        f"{error.validator}:{'.'.join(str(part) for part in error.absolute_path) or '<root>'}"
        for error in sorted(
            Draft202012Validator(schema).iter_errors(value),
            key=lambda error: (list(error.absolute_path), error.validator),
        )
    ]


def artifact_diagnostic(row: dict[str, Any]) -> dict[str, Any]:
    """Inspect unsubmitted artifacts post hoc; never use this as the official score."""

    run_root = PROJECT_ROOT / str(row["run_directory"])
    summary = read_json(run_root / "run_summary.json")
    workspace = run_root / f"{row['task_id']}-{row['scenario_id']}"
    submission_path = workspace / "submission" / "final_submission.json"
    result = {
        "stop_condition": summary.get("stop_condition"),
        "tool_call_counts": summary.get("tool_call_counts") or {},
        "artifact_exists": submission_path.is_file(),
        "artifact_json_valid": False,
        "artifact_schema_valid": False,
        "artifact_official_grade_if_submitted": None,
        "schema_error_codes": [],
        "provided_metric_count": 0,
        "correct_provided_metric_count": 0,
    }
    if not submission_path.is_file():
        return result
    try:
        value = json.loads(submission_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        result["schema_error_codes"] = ["invalid_json"]
        return result
    result["artifact_json_valid"] = True
    schema = read_json(workspace / "schemas" / "final_submission.schema.json")
    errors = _schema_errors(value, schema)
    result["schema_error_codes"] = errors
    result["artifact_schema_valid"] = not errors
    expected = solve_data_diagnostic(workspace)
    task = read_json(workspace / "task.json")
    supplied_metrics = value.get("metrics") if isinstance(value, dict) else None
    if isinstance(supplied_metrics, dict):
        for name, supplied in supplied_metrics.items():
            if name not in expected["metrics"] or not isinstance(supplied, int | float):
                continue
            result["provided_metric_count"] += 1
            tolerance = float(task["metric_contract"][name]["absolute_tolerance"])
            if abs(float(supplied) - float(expected["metrics"][name])) <= tolerance + 1e-12:
                result["correct_provided_metric_count"] += 1
    if not errors:
        result["artifact_official_grade_if_submitted"] = grade_data_diagnostic(
            workspace, value
        ).score
    return result


def augment_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for row in rows:
        diagnostic = artifact_diagnostic(row)
        if row["classification"] == "valid_episode":
            signature = "completed_valid_episode"
        elif (
            diagnostic["artifact_schema_valid"]
            and diagnostic["artifact_official_grade_if_submitted"] is not None
        ):
            signature = "submission_omission_after_valid_artifact"
        elif int(diagnostic["tool_call_counts"].get("submit_data_audit", 0)) > 0:
            signature = "contract_repair_exhaustion"
        elif diagnostic["artifact_exists"]:
            signature = "unsubmitted_incomplete_artifact"
        else:
            signature = "no_submission_artifact"
        output.append({**row, "artifact_diagnostic": diagnostic, "failure_signature": signature})
    return output


def model_summaries(rows: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    summaries = []
    for model in config["models"]:
        model_id = str(model["model_id"])
        selected = [row for row in rows if row["model_id"] == model_id]
        scores = [float(row["score"]) for row in selected]
        valid = [row for row in selected if row["classification"] == "valid_episode"]
        signatures = Counter(str(row["failure_signature"]) for row in selected)
        component_means = {
            component: mean(
                float((row.get("component_scores") or {}).get(component, 0.0)) for row in selected
            )
            for component in COMPONENTS
        }
        summaries.append(
            {
                "model_id": model_id,
                "tier": model["tier"],
                "attempt_count": len(selected),
                "valid_episode_count": len(valid),
                "agent_task_failure_count": len(selected) - len(valid),
                "valid_episode_rate": len(valid) / len(selected),
                "mean_attempt_score": mean(scores),
                "valid_episode_mean_score": (
                    mean(float(row["score"]) for row in valid) if valid else None
                ),
                "floor_rate": sum(score <= 20.0 for score in scores) / len(scores),
                "ceiling_rate": sum(score >= 95.0 for score in scores) / len(scores),
                "mean_turn_count": mean(float(row["turn_count"]) for row in selected),
                "component_means_including_task_failures": component_means,
                "failure_signatures": dict(sorted(signatures.items())),
            }
        )
    return summaries


def scenario_summaries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys = sorted({(str(row["task_id"]), str(row["scenario_id"])) for row in rows})
    return [
        {
            "task_id": task_id,
            "scenario_id": scenario_id,
            "model_scores": {
                str(row["model_id"]): float(row["score"])
                for row in rows
                if row["task_id"] == task_id and row["scenario_id"] == scenario_id
            },
        }
        for task_id, scenario_id in keys
    ]


def render_report(output: dict[str, Any]) -> str:
    lines = [
        "# Executable data-task calibration",
        "",
        "This is a one-attempt-per-cell calibration, not leaderboard evidence. Agent task "
        "failures score zero; provider failures are excluded.",
        "",
        "| model | mean attempt score | valid episodes | floor | ceiling | mean turns |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in output["model_summaries"]:
        lines.append(
            f"| {row['model_id']} | {row['mean_attempt_score']:.2f} | "
            f"{row['valid_episode_count']}/{row['attempt_count']} | "
            f"{row['floor_rate']:.2f} | {row['ceiling_rate']:.2f} | "
            f"{row['mean_turn_count']:.2f} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            f"- Strict temporal ordering: `{str(output['strict_temporal_order']).lower()}`.",
            f"- Non-increasing temporal ordering: "
            f"`{str(output['nonincreasing_temporal_order']).lower()}`.",
            f"- Floor/ceiling gate: `{str(output['floor_ceiling_gate_passed']).lower()}`.",
            f"- Calibration accepted: `{str(output['calibration_accepted']).lower()}`.",
            "- Successful submissions were at ceiling; observed separation is primarily "
            "workflow-completion reliability, not a measured difference in biological "
            "model quality.",
            "- Post-hoc artifact diagnostics are explanatory only and never replace the zero "
            "assigned to an unsubmitted attempt.",
            "",
            "## Failure signatures",
            "",
        ]
    )
    for row in output["model_summaries"]:
        lines.append(f"- `{row['model_id']}`: {row['failure_signatures']}")
    return "\n".join(lines) + "\n"


def main() -> int:
    raw = read_json(RAW_PATH)
    config = read_json(CONFIG_PATH)
    rows = augment_rows(selected_scored_rows(raw))
    expected_count = int(raw["planned_trajectory_count"])
    if len(rows) != expected_count:
        raise SystemExit(f"Expected {expected_count} scored cells; found {len(rows)}")
    summaries = model_summaries(rows, config)
    means = [float(row["mean_attempt_score"]) for row in summaries]
    strict_order = all(left > right for left, right in pairwise(means))
    nonincreasing_order = all(left >= right for left, right in pairwise(means))
    acceptance = config["acceptance"]
    floor_ceiling = all(
        row["floor_rate"] <= float(acceptance["maximum_model_floor_rate"])
        and row["ceiling_rate"] <= float(acceptance["maximum_model_ceiling_rate"])
        for row in summaries
    )
    distinct_means = len({round(value, 8) for value in means})
    output = {
        "schema_version": "0.1",
        "raw_artifact": RAW_PATH.relative_to(PROJECT_ROOT).as_posix(),
        "raw_artifact_sha256": sha256_file(RAW_PATH),
        "leaderboard_evidence": False,
        "ranking_claim_allowed": False,
        "planned_cell_count": expected_count,
        "scored_cell_count": len(rows),
        "infrastructure_failure_count": int(raw["infrastructure_failure_count"]),
        "estimated_cost_usd": float(raw["estimated_cost_usd"]),
        "openrouter_usage_delta_usd": (
            float(raw["openrouter_key_usage_after_usd"])
            - float(raw["openrouter_key_usage_before_usd"])
        ),
        "strict_temporal_order": strict_order,
        "nonincreasing_temporal_order": nonincreasing_order,
        "distinct_model_means": distinct_means,
        "floor_ceiling_gate_passed": floor_ceiling,
        "calibration_accepted": (
            floor_ceiling and distinct_means >= int(acceptance["minimum_distinct_model_means"])
        ),
        "model_summaries": summaries,
        "scenario_summaries": scenario_summaries(rows),
        "rows_with_posthoc_artifact_diagnostics": rows,
    }
    OUTPUT_PATH.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(render_report(output), encoding="utf-8")
    print(
        json.dumps(
            {
                "calibration_accepted": output["calibration_accepted"],
                "strict_temporal_order": strict_order,
                "floor_ceiling_gate_passed": floor_ceiling,
                "model_means": {row["model_id"]: row["mean_attempt_score"] for row in summaries},
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

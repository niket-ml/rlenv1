#!/usr/bin/env python3
"""Regrade and diagnose the short-task calibration without mutating raw runs."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any

from uc_bench.diagnostic_packets import grade_diagnostic_packet, load_packet_scenario
from uc_bench.hashing import sha256_file

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNS_PATH = PROJECT_ROOT / "artifacts" / "diagnostics" / "packet_calibration_runs.json"
CONFIG_PATH = PROJECT_ROOT / "configs" / "packet_calibration.json"
OUTPUT_PATH = PROJECT_ROOT / "artifacts" / "diagnostics" / "packet_calibration_analysis.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "generated" / "packet_calibration.md"
FLOOR_THRESHOLD = 20.0
CEILING_THRESHOLD = 95.0


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def regrade_rows(raw_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    run_roots = {}
    for summary_path in (PROJECT_ROOT / "build" / "packet_runs").glob(
        "*/run_summary.json"
    ):
        summary = read_json(summary_path)
        run_roots[str(summary["run_id"])] = summary_path.parent
    rows = []
    for raw in raw_rows:
        row = dict(raw)
        if row["classification"] == "infrastructure_failure":
            row["regraded_score"] = None
            row["regraded_components"] = None
            rows.append(row)
            continue
        recorded_directory = row.get("run_directory")
        run_root = (
            PROJECT_ROOT / str(recorded_directory)
            if recorded_directory
            else run_roots[str(row["run_id"])]
        )
        record_path = run_root / "packet_record.json"
        record = read_json(record_path)
        scenario = load_packet_scenario(
            PROJECT_ROOT, str(row["task_id"]), str(row["scenario_id"])
        )
        grade = grade_diagnostic_packet(
            record.get("submission"), scenario["rubric"]
        ).to_dict()
        row["regraded_score"] = grade["score"]
        row["regraded_components"] = grade["component_scores"]
        row["decision_correct"] = grade["decision_correct"]
        row["contract_valid"] = grade["contract_valid"]
        row["diagnostic_checks"] = grade["checks"]
        submission = record.get("submission") or {}
        row["submitted_confidence"] = submission.get("confidence")
        rows.append(row)
    return rows


def model_summaries(
    rows: list[dict[str, Any]], config: dict[str, Any]
) -> list[dict[str, Any]]:
    summaries = []
    for model in config["models"]:
        model_rows = [
            row
            for row in rows
            if row["model_id"] == model["model_id"]
            and row["classification"] != "infrastructure_failure"
        ]
        scores = [float(row["regraded_score"]) for row in model_rows]
        component_names = sorted(
            {
                name
                for row in model_rows
                for name in (row.get("regraded_components") or {})
            }
        )
        submitted_confidences = [
            float(row["submitted_confidence"])
            for row in model_rows
            if isinstance(row.get("submitted_confidence"), int | float)
        ]
        failure_signatures: Counter[str] = Counter()
        for row in model_rows:
            components = row.get("regraded_components") or {}
            if row["classification"] == "agent_task_failure":
                failure_signatures["did_not_submit"] += 1
            if not row.get("decision_correct"):
                failure_signatures["incorrect_or_missing_decision"] += 1
            if float(components.get("diagnosis", 0.0)) < 100.0:
                failure_signatures["incomplete_diagnosis"] += 1
            if float(components.get("next_action", 0.0)) < 100.0:
                failure_signatures["incorrect_or_missing_next_action"] += 1
            if float(components.get("required_evidence_recall", 0.0)) < 100.0:
                failure_signatures["missing_required_evidence"] += 1
        summaries.append(
            {
                "model_id": model["model_id"],
                "tier": model["tier"],
                "released": model["released"],
                "n": len(model_rows),
                "score_mean": mean(scores),
                "score_minimum": min(scores),
                "score_maximum": max(scores),
                "contract_valid_rate": mean(
                    float(bool(row.get("contract_valid"))) for row in model_rows
                ),
                "decision_accuracy": mean(
                    float(bool(row.get("decision_correct"))) for row in model_rows
                ),
                "floor_rate": mean(score <= FLOOR_THRESHOLD for score in scores),
                "ceiling_rate": mean(score >= CEILING_THRESHOLD for score in scores),
                "component_means": {
                    name: mean(
                        float((row.get("regraded_components") or {}).get(name, 0.0))
                        for row in model_rows
                    )
                    for name in component_names
                },
                "submitted_confidence_mean": (
                    mean(submitted_confidences) if submitted_confidences else None
                ),
                "failure_signatures": dict(sorted(failure_signatures.items())),
            }
        )
    return summaries


def scenario_summaries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys = sorted(
        {
            (str(row["task_id"]), str(row["scenario_id"]))
            for row in rows
            if row["classification"] != "infrastructure_failure"
        }
    )
    summaries = []
    for task_id, scenario_id in keys:
        scenario_rows = [
            row
            for row in rows
            if row["task_id"] == task_id
            and row["scenario_id"] == scenario_id
            and row["classification"] != "infrastructure_failure"
        ]
        scores = [float(row["regraded_score"]) for row in scenario_rows]
        summaries.append(
            {
                "task_id": task_id,
                "scenario_id": scenario_id,
                "score_mean": mean(scores),
                "score_range": [min(scores), max(scores)],
                "model_scores": {
                    str(row["model_id"]): row["regraded_score"]
                    for row in scenario_rows
                },
            }
        )
    return summaries


def render_markdown(output: dict[str, Any]) -> str:
    lines = [
        "# Diagnostic packet calibration",
        "",
        "> CALIBRATION ONLY — one attempt per cell; no ranking claim.",
        "",
        "## Model summary",
        "",
        "| Model | Mean | Valid | Decision accuracy | Floor | Ceiling |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in output["model_summaries"]:
        lines.append(
            f"| {row['model_id']} | {row['score_mean']:.2f} | "
            f"{row['contract_valid_rate']:.0%} | {row['decision_accuracy']:.0%} | "
            f"{row['floor_rate']:.0%} | {row['ceiling_rate']:.0%} |"
        )
    lines.extend(
        [
            "",
            "## Gate",
            "",
            f"- Strict temporal ordering: `{str(output['strict_temporal_order']).lower()}`",
            f"- Floor/ceiling gate: `{str(output['floor_ceiling_gate_passed']).lower()}`",
            f"- Calibration accepted: `{str(output['calibration_accepted']).lower()}`",
            "",
            "The raw paid-run artifact is preserved. Scores here are recomputed under "
            "public packet scoring policy v0.2, which does not use hidden confidence "
            "bands or penalize additional valid evidence citations.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    raw = read_json(RUNS_PATH)
    config = read_json(CONFIG_PATH)
    rows = regrade_rows(raw["runs"])
    summaries = model_summaries(rows, config)
    score_means = [float(row["score_mean"]) for row in summaries]
    strict_temporal_order = all(
        newer > older for newer, older in zip(score_means, score_means[1:], strict=True)
    )
    maximum_floor = float(config["acceptance"]["maximum_model_floor_rate"])
    maximum_ceiling = float(config["acceptance"]["maximum_model_ceiling_rate"])
    floor_ceiling_passed = all(
        row["floor_rate"] <= maximum_floor
        and row["ceiling_rate"] <= maximum_ceiling
        for row in summaries
    )
    distinct_means = len({round(value, 8) for value in score_means})
    output = {
        "schema_version": "0.1",
        "status": "calibration_not_ranking",
        "leaderboard_evidence": False,
        "raw_runs_path": RUNS_PATH.relative_to(PROJECT_ROOT).as_posix(),
        "raw_runs_sha256": sha256_file(RUNS_PATH),
        "scoring_policy_version": "0.2",
        "infrastructure_failure_count": sum(
            row["classification"] == "infrastructure_failure" for row in rows
        ),
        "completed_trajectory_count": sum(
            row["classification"] != "infrastructure_failure" for row in rows
        ),
        "model_summaries": summaries,
        "scenario_summaries": scenario_summaries(rows),
        "strict_temporal_order": strict_temporal_order,
        "distinct_model_mean_count": distinct_means,
        "floor_ceiling_gate_passed": floor_ceiling_passed,
        "calibration_accepted": (
            strict_temporal_order
            and floor_ceiling_passed
            and distinct_means
            >= int(config["acceptance"]["minimum_distinct_model_means"])
        ),
        "interpretation_limits": [
            "one_attempt_per_cell",
            "calibration_scenarios_not_held_out",
            "release_date_not_a_grading_feature",
            "model_order_not_statistically_estimated",
        ],
        "regraded_rows": rows,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(render_markdown(output), encoding="utf-8")
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

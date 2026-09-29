#!/usr/bin/env python3
"""Build the intervention matrix, recovery table, and breaking-point report."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

from uc_bench.hard_suite import iter_hard_suite_ladder_variants, iter_hard_suite_variants

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNS_PATH = PROJECT_ROOT / "artifacts" / "diagnostics" / "hard_suite_calibration_runs.json"
LADDER_RUNS_PATH = PROJECT_ROOT / "artifacts" / "diagnostics" / "hard_suite_ladder_runs.json"
CONTROLS_PATH = PROJECT_ROOT / "artifacts" / "diagnostics" / "hard_suite_controls.json"
LADDER_CONTROLS_PATH = PROJECT_ROOT / "artifacts" / "diagnostics" / "hard_suite_ladders.json"
OUTPUT_PATH = PROJECT_ROOT / "artifacts" / "diagnostics" / "hard_suite_analysis.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "generated" / "hard_suite_report.md"


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected JSON object: {path}")
    return value


def _variant_index() -> dict[str, dict[str, Any]]:
    variants = iter_hard_suite_variants(PROJECT_ROOT, partition="development")
    variants += iter_hard_suite_ladder_variants(PROJECT_ROOT)
    return {str(row["variant_id"]): row for row in variants}


def _matrix_rows(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    variants = _variant_index()
    output = []
    for row in runs:
        if row["classification"] == "infrastructure_failure":
            continue
        variant = variants[str(row["variant_id"])]
        grade = row.get("grade") or {}
        output.append(
            {
                "model_id": row["model_id"],
                "family_id": variant["family_id"],
                "variant_id": variant["variant_id"],
                "pair_role": variant["pair_role"],
                "provided_intervention": variant["provided_intervention"],
                "expected_resource_effect": variant["expected_resource_effect"],
                "score": float(row["score"]),
                "decision_correct": bool(grade.get("decision_correct", False)),
                "detection_correct": bool(grade.get("detection_correct", False)),
                "containment_correct": bool(grade.get("containment_correct", False)),
                "smallest_action_correct": bool(grade.get("smallest_action_correct", False)),
                "intervention_assessment_correct": bool(
                    grade.get("intervention_assessment_correct", False)
                ),
                "expected_primary_failure": grade.get("expected_primary_failure"),
                "classification": row["classification"],
            }
        )
    return output


def _model_summaries(matrix: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for model_id in dict.fromkeys(str(row["model_id"]) for row in matrix):
        selected = [row for row in matrix if row["model_id"] == model_id]
        output.append(
            {
                "model_id": model_id,
                "task_count": len(selected),
                "mean_score": mean(float(row["score"]) for row in selected),
                "ceiling_rate": sum(float(row["score"]) >= 95.0 for row in selected)
                / len(selected),
                "zero_rate": sum(float(row["score"]) == 0.0 for row in selected) / len(selected),
                "decision_accuracy": mean(bool(row["decision_correct"]) for row in selected),
                "detection_accuracy": mean(bool(row["detection_correct"]) for row in selected),
                "containment_accuracy": mean(bool(row["containment_correct"]) for row in selected),
                "smallest_action_accuracy": mean(
                    bool(row["smallest_action_correct"]) for row in selected
                ),
            }
        )
    return output


def _recovery_rows(matrix: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in matrix:
        grouped[(str(row["model_id"]), str(row["family_id"]))].append(row)
    output = []
    for (model_id, family_id), rows in grouped.items():
        if len(rows) != 2:
            continue
        control = next(
            (
                row
                for row in rows
                if row["pair_role"]
                in {"ineffective_control", "uncontained_control", "no_current_resolution"}
            ),
            None,
        )
        treated = next((row for row in rows if row is not control), None)
        if control is None or treated is None:
            continue
        output.append(
            {
                "model_id": model_id,
                "family_id": family_id,
                "control_intervention": control["provided_intervention"],
                "provided_intervention": treated["provided_intervention"],
                "expected_resource_effect": treated["expected_resource_effect"],
                "control_score": control["score"],
                "provided_score": treated["score"],
                "paired_score_delta": treated["score"] - control["score"],
                "control_decision_correct": control["decision_correct"],
                "provided_decision_correct": treated["decision_correct"],
                "provided_containment_correct": treated["containment_correct"],
                "provided_action_correct": treated["smallest_action_correct"],
                "provided_intervention_assessment_correct": treated[
                    "intervention_assessment_correct"
                ],
                "observed_recovery": (
                    treated["decision_correct"]
                    and treated["containment_correct"]
                    and treated["intervention_assessment_correct"]
                ),
            }
        )
    return output


def _family_gap_share(matrix: list[dict[str, Any]]) -> dict[str, float]:
    summaries = _model_summaries(matrix)
    if len(summaries) < 2:
        return {}
    ordered = sorted(summaries, key=lambda row: float(row["mean_score"]))
    weakest = str(ordered[0]["model_id"])
    strongest = str(ordered[-1]["model_id"])
    gaps = {}
    for family in sorted({str(row["family_id"]) for row in matrix}):
        strong = [
            float(row["score"])
            for row in matrix
            if row["model_id"] == strongest and row["family_id"] == family
        ]
        weak = [
            float(row["score"])
            for row in matrix
            if row["model_id"] == weakest and row["family_id"] == family
        ]
        if strong and weak:
            gaps[family] = abs(mean(strong) - mean(weak))
    total = sum(gaps.values())
    return {family: value / total for family, value in gaps.items()} if total else {}


def _ladder_rows() -> list[dict[str, Any]]:
    if not LADDER_RUNS_PATH.is_file():
        return []
    runs = list(_read_object(LADDER_RUNS_PATH).get("runs") or [])
    variants = _variant_index()
    output = []
    for row in runs:
        if row["classification"] == "infrastructure_failure":
            continue
        variant = variants[str(row["variant_id"])]
        grade = row.get("grade") or {}
        output.append(
            {
                "model_id": row["model_id"],
                "ladder_id": variant["ladder_id"],
                "level": variant["ladder_level"],
                "score": float(row["score"]),
                "decision_correct": bool(grade.get("decision_correct", False)),
            }
        )
    return output


def _acceptance(matrix: list[dict[str, Any]]) -> dict[str, Any]:
    if not matrix:
        return {"status": "pending_development_calibration", "all_gates_passed": False}
    summaries = _model_summaries(matrix)
    strongest = max(summaries, key=lambda row: float(row["mean_score"]))
    weakest = min(summaries, key=lambda row: float(row["mean_score"]))
    failed_rows = [
        row
        for row in matrix
        if not (
            row["decision_correct"] and row["detection_correct"] and row["smallest_action_correct"]
        )
    ]
    failure_modes = {
        str(row["expected_primary_failure"])
        for row in failed_rows
        if row["expected_primary_failure"]
    }
    gap_share = _family_gap_share(matrix)
    gates = {
        "strongest_mean_below_85": float(strongest["mean_score"]) < 85.0,
        "strongest_ceiling_rate_at_most_25_percent": float(strongest["ceiling_rate"]) <= 0.25,
        "weakest_not_universal_zero": float(weakest["zero_rate"]) < 1.0
        and float(weakest["mean_score"]) > 0.0,
        "at_least_three_interpretable_failure_modes": len(failure_modes) >= 3,
        "single_family_gap_share_at_most_30_percent": bool(gap_share)
        and max(gap_share.values()) <= 0.30,
    }
    return {
        "status": "one_seed_calibration_not_ranking",
        "strongest_development_model": strongest,
        "weakest_development_model": weakest,
        "observed_failure_modes": sorted(failure_modes),
        "family_gap_share": gap_share,
        "gates": gates,
        "all_gates_passed": all(gates.values()),
        "ranking_claim_allowed": False,
    }


def _render_report(output: dict[str, Any]) -> str:
    controls = output["local_controls"]
    lines = [
        "# UC-Bench hard-suite report",
        "",
        "> Primary output: model × failure mode × intervention. Aggregate ranking is "
        "secondary and remains prohibited without repeated seeds.",
        "",
        "## Local gates",
        "",
        f"All local gates passed: **{controls['all_local_gates_passed']}**. "
        f"Reference minimum {controls['reference_minimum_score']:.1f}; universal-policy "
        f"means advance/abstain/stop = "
        f"{controls['universal_policy_mean_scores']['advance']:.1f}/"
        f"{controls['universal_policy_mean_scores']['insufficient_evidence']:.1f}/"
        f"{controls['universal_policy_mean_scores']['stop']:.1f}.",
        "",
        "## Model × failure mode × intervention matrix",
        "",
    ]
    matrix = output["matrix"]
    if not matrix:
        lines.append("Development calibration has not run; model cells are intentionally pending.")
    else:
        lines.extend(
            [
                "| model | family | role | resource | score | decision | detect | "
                "contain | action |",
                "|---|---|---|---|---:|---:|---:|---:|---:|",
            ]
        )
        for row in matrix:
            lines.append(
                f"| {row['model_id']} | {row['family_id']} | {row['pair_role']} | "
                f"{row['provided_intervention']} | {row['score']:.1f} | "
                f"{int(row['decision_correct'])} | {int(row['detection_correct'])} | "
                f"{int(row['containment_correct'])} | "
                f"{int(row['smallest_action_correct'])} |"
            )
    lines.extend(["", "## Intervention recovery", ""])
    recovery = output["recovery"]
    if not recovery:
        lines.append("Paired model recovery is pending development calibration.")
    else:
        lines.extend(
            [
                "| model | family | provided resource | control → treated | delta | recovered |",
                "|---|---|---|---:|---:|---:|",
            ]
        )
        for row in recovery:
            lines.append(
                f"| {row['model_id']} | {row['family_id']} | "
                f"{row['provided_intervention']} | {row['control_score']:.1f} → "
                f"{row['provided_score']:.1f} | {row['paired_score_delta']:+.1f} | "
                f"{int(row['observed_recovery'])} |"
            )
    lines.extend(["", "## Breaking-point curves", ""])
    ladders = output["ladder_results"]
    if not ladders:
        lines.append(
            "Model curves are pending. The frozen local ladder has 20 runnable levels and "
            "all five reference curves contain a decision/diagnosis transition."
        )
    else:
        lines.extend(
            [
                "| model | ladder | level | score | correct decision |",
                "|---|---|---:|---:|---:|",
            ]
        )
        for row in ladders:
            lines.append(
                f"| {row['model_id']} | {row['ladder_id']} | {row['level']} | "
                f"{row['score']:.1f} | {int(row['decision_correct'])} |"
            )
    lines.extend(
        [
            "",
            "## Acceptance",
            "",
            f"Status: `{output['acceptance']['status']}`. A single Astra ceiling canary is "
            "permitted only if development and local gates pass. Astra at 85 or above is "
            "an explicit no-go.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    controls = _read_object(CONTROLS_PATH)
    ladder_controls = _read_object(LADDER_CONTROLS_PATH)
    runs = list(_read_object(RUNS_PATH).get("runs") or []) if RUNS_PATH.is_file() else []
    matrix = _matrix_rows(runs)
    output = {
        "schema_version": "0.2",
        "status": "pre_release_calibration_not_ranking",
        "local_controls": controls,
        "ladder_controls": ladder_controls,
        "matrix": matrix,
        "model_summaries": _model_summaries(matrix),
        "recovery": _recovery_rows(matrix),
        "ladder_results": _ladder_rows(),
        "acceptance": _acceptance(matrix),
        "ranking_claim_allowed": False,
    }
    OUTPUT_PATH.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(_render_report(output), encoding="utf-8")
    print(json.dumps(output["acceptance"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

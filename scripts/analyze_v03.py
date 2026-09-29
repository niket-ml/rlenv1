#!/usr/bin/env python3
"""Analyze v0.3 as a controlled failure/intervention study, never a ranking."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

from jsonschema import Draft202012Validator

from uc_bench.hard_suite_v03 import iter_v03_variants

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNS_PATH = PROJECT_ROOT / "artifacts" / "diagnostics" / "hard_suite_v03_calibration_runs.json"
CONTROLS_PATH = PROJECT_ROOT / "artifacts" / "diagnostics" / "hard_suite_v03_controls.json"
LADDERS_PATH = PROJECT_ROOT / "artifacts" / "diagnostics" / "hard_suite_ladders.json"
CONFIG_PATH = PROJECT_ROOT / "configs" / "hard_suite_v03_calibration.json"
OUTPUT_PATH = PROJECT_ROOT / "artifacts" / "diagnostics" / "hard_suite_v03_analysis.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "generated" / "hard_suite_v03_report.md"

OBSERVABLE_FAILURES = {
    "H01_identity_metadata": (
        "Identical expression fingerprints map to incompatible patient or visit IDs."
    ),
    "H02_transfer_data": (
        "Only the jointly endpoint-, drug-, and platform-matched condition recovers; "
        "no single-factor match does."
    ),
    "H03_process_science": (
        "Outcome is entangled with batch and split provenance is unsafe; after process "
        "repair, endpoint transfer can remain unresolved."
    ),
    "H04_label_expertise": (
        "Observed and blindly adjudicated week-6 endpoint labels disagree materially, "
        "changing locked-model AUC."
    ),
    "H05_evidence_sufficiency": (
        "The available bridge is too small to distinguish transfer failure from model "
        "misspecification."
    ),
}

SMALLEST_ACTIONS = {
    "H01_identity_metadata": "Reconcile patient, biopsy date, and visit from source records.",
    "H02_transfer_data": "Run one adequately sized jointly matched transfer bridge.",
    "H03_process_science": "Regenerate predictions with grouped splits and fit-only preprocessing.",
    "H04_label_expertise": "Blindly adjudicate the prespecified endpoint from source records.",
    "H05_evidence_sufficiency": "Run an adequately sized independent replication.",
}

SUBSTANTIVE_COMPONENTS = {
    "quantitative_analysis": "quantitative_analysis",
    "scientific_diagnosis": "scientific_reasoning",
    "evidence_integration": "evidence_diagnosis",
    "resource_selection": "recovery_design",
    "recovery_design": "recovery_design",
}


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected JSON object: {path}")
    return value


def _variant_index() -> dict[str, dict[str, Any]]:
    variants = iter_v03_variants(PROJECT_ROOT, partition="development")
    return {str(row["variant_id"]): row for row in variants}


def _resource_index(variant: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(row["resource_id"]): row for row in variant["resources"]}


def _schema_primary_failure(row: dict[str, Any]) -> bool:
    if row.get("classification") != "agent_task_failure":
        return False
    run_root = PROJECT_ROOT / str(row["run_directory"])
    matches = list(run_root.glob("hard3-*/submission/final_submission.json"))
    if len(matches) != 1:
        return False
    try:
        submission = _read(matches[0])
        schema = _read(matches[0].parents[1] / "schemas" / "final_submission.schema.json")
    except (OSError, TypeError, json.JSONDecodeError):
        return True
    return not Draft202012Validator(schema).is_valid(submission)


def _failure_domains(row: dict[str, Any]) -> list[str]:
    if row.get("classification") == "agent_task_failure":
        return ["schema_execution" if _schema_primary_failure(row) else "long_horizon_execution"]
    grade = row.get("grade") or {}
    components = grade.get("components") or {}
    domains = {
        domain
        for component, domain in SUBSTANTIVE_COMPONENTS.items()
        if float(components.get(component, 0.0)) < 75.0
    }
    if not grade.get("decision_correct", False):
        domains.add("scientific_reasoning")
    if not grade.get("detection_correct", False):
        domains.add("evidence_diagnosis")
    if not grade.get("containment_correct", False):
        domains.add("recovery_design")
    if not grade.get("smallest_action_correct", False):
        domains.add("recovery_design")
    return sorted(domains)


def _matrix(raw_runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    variants = _variant_index()
    output = []
    for row in raw_runs:
        if row.get("classification") == "infrastructure_failure":
            continue
        variant = variants[str(row["variant_id"])]
        resources = _resource_index(variant)
        expected_id = str(variant["expected_resource_id"])
        selected_id = str(row.get("selected_resource_id") or "none")
        resolving = resources[str(variant["correct_resource_id"])]
        selected = resources.get(selected_id)
        grade = row.get("grade") or {}
        components = grade.get("components") or {}
        output.append(
            {
                "model_id": row["model_id"],
                "attempt_index": row["attempt_index"],
                "family_id": variant["family_id"],
                "variant_id": variant["variant_id"],
                "pair_role": variant["pair_role"],
                "controlled_or_authentic": "controlled",
                "observably_wrong": OBSERVABLE_FAILURES[str(variant["family_id"])],
                "failure_mode": variant["failure_mode"],
                "score": float(row["score"]),
                "classification": row["classification"],
                "failure_domains": _failure_domains(row),
                "detected": bool(grade.get("detection_correct", False)),
                "contained": bool(grade.get("containment_correct", False)),
                "decision_correct": bool(grade.get("decision_correct", False)),
                "smallest_action_correct": bool(grade.get("smallest_action_correct", False)),
                "smallest_correct_action": SMALLEST_ACTIONS[str(variant["family_id"])],
                "resolving_intervention": resolving["intervention"],
                "resolving_intervention_class": resolving["class"],
                "correct_intervention_available": bool(variant["correct_resource_available"]),
                "expected_resource_id": expected_id,
                "selected_resource_id": selected_id,
                "selected_intervention": selected["intervention"] if selected else "none",
                "selected_intervention_class": selected["class"] if selected else "none",
                "resource_selection_correct": bool(
                    grade.get("resource_selection_correct", False)
                ),
                "intervention_assessment_correct": bool(
                    grade.get("intervention_assessment_correct", False)
                ),
                "component_scores": components,
                "turn_count": int(row.get("turn_count") or 0),
                "schema_primary_failure": _schema_primary_failure(row),
                "run_id": row["run_id"],
            }
        )
    return output


def _summaries(matrix: list[dict[str, Any]], model_order: list[str]) -> list[dict[str, Any]]:
    output = []
    for model_id in model_order:
        selected = [row for row in matrix if row["model_id"] == model_id]
        if not selected:
            continue
        output.append(
            {
                "model_id": model_id,
                "task_count": len(selected),
                "mean_score": mean(float(row["score"]) for row in selected),
                "ceiling_rate": mean(float(row["score"]) >= 95.0 for row in selected),
                "zero_rate": mean(float(row["score"]) == 0.0 for row in selected),
                "valid_episode_rate": mean(
                    row["classification"] == "valid_episode" for row in selected
                ),
                "detection_rate": mean(bool(row["detected"]) for row in selected),
                "containment_rate": mean(bool(row["contained"]) for row in selected),
                "correct_resource_rate": mean(
                    bool(row["resource_selection_correct"]) for row in selected
                ),
                "smallest_action_rate": mean(
                    bool(row["smallest_action_correct"]) for row in selected
                ),
            }
        )
    return output


def _paired_recovery(matrix: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in matrix:
        grouped[(str(row["model_id"]), str(row["family_id"]))].append(row)
    output = []
    for (model_id, family_id), rows in sorted(grouped.items()):
        if len(rows) != 2:
            continue
        control = next((row for row in rows if row["pair_role"] == "control"), None)
        treated = next((row for row in rows if row["pair_role"] == "treated"), None)
        if control is None or treated is None:
            continue
        outcome_recovered = all(
            (
                treated["detected"],
                treated["contained"],
                treated["decision_correct"],
                treated["resource_selection_correct"],
                treated["intervention_assessment_correct"],
            )
        )
        output.append(
            {
                "model_id": model_id,
                "family_id": family_id,
                "intervention": treated["resolving_intervention"],
                "intervention_class": treated["resolving_intervention_class"],
                "control_score": control["score"],
                "treated_score": treated["score"],
                "score_delta": treated["score"] - control["score"],
                "control_correctly_declined_ineffective_resources": control[
                    "resource_selection_correct"
                ],
                "treated_selected_resolving_intervention": treated[
                    "resource_selection_correct"
                ],
                "outcome_recovered": outcome_recovered,
            }
        )
    return output


def _gap_share(matrix: list[dict[str, Any]], summaries: list[dict[str, Any]]) -> dict[str, float]:
    if len(summaries) < 2:
        return {}
    strongest = max(summaries, key=lambda row: float(row["mean_score"]))["model_id"]
    weakest = min(summaries, key=lambda row: float(row["mean_score"]))["model_id"]
    gaps = {}
    for family_id in sorted({str(row["family_id"]) for row in matrix}):
        strong = [
            float(row["score"])
            for row in matrix
            if row["model_id"] == strongest and row["family_id"] == family_id
        ]
        weak = [
            float(row["score"])
            for row in matrix
            if row["model_id"] == weakest and row["family_id"] == family_id
        ]
        if len(strong) == 2 and len(weak) == 2:
            gaps[family_id] = abs(mean(strong) - mean(weak))
    total = sum(gaps.values())
    return {family: gap / total for family, gap in gaps.items()} if total else {}


def _acceptance(
    matrix: list[dict[str, Any]],
    summaries: list[dict[str, Any]],
    model_order: list[str],
    expected_cells: int,
) -> dict[str, Any]:
    complete = len(matrix) == expected_cells and all(
        sum(row["model_id"] == model for row in matrix) == expected_cells // len(model_order)
        for model in model_order
    )
    if not complete:
        return {
            "status": "development_calibration_incomplete",
            "all_development_gates_passed": False,
            "astra_canary_permitted": False,
            "completed_cells": len(matrix),
            "expected_cells": expected_cells,
        }
    by_model = {str(row["model_id"]): row for row in summaries}
    frontier = by_model[model_order[0]]
    observed_strongest = max(summaries, key=lambda row: float(row["mean_score"]))
    weakest = min(summaries, key=lambda row: float(row["mean_score"]))
    domains = sorted({domain for row in matrix for domain in row["failure_domains"]})
    substantive = sorted(
        set(domains)
        & {
            "scientific_reasoning",
            "evidence_diagnosis",
            "quantitative_analysis",
            "recovery_design",
            "long_horizon_execution",
        }
    )
    schema_failures = sum(bool(row["schema_primary_failure"]) for row in matrix)
    any_failures = sum(bool(row["failure_domains"]) for row in matrix)
    family_gap_share = _gap_share(matrix, summaries)
    means = [float(by_model[model]["mean_score"]) for model in model_order]
    gates = {
        "frontier_mean_below_85": float(frontier["mean_score"]) < 85.0,
        "frontier_mean_in_ideal_65_to_80": 65.0 <= float(frontier["mean_score"]) <= 80.0,
        "observed_strongest_mean_below_85": float(observed_strongest["mean_score"]) < 85.0,
        "frontier_ceiling_rate_at_most_25_percent": float(frontier["ceiling_rate"]) <= 0.25,
        "weakest_not_universal_failure_or_zero": float(weakest["mean_score"]) > 0.0
        and float(weakest["zero_rate"]) < 1.0,
        "at_least_three_substantive_failure_domains": len(substantive) >= 3,
        "schema_not_primary": schema_failures == 0
        or schema_failures / max(any_failures, 1) < 0.5,
        "single_family_gap_share_at_most_30_percent": bool(family_gap_share)
        and max(family_gap_share.values()) <= 0.30,
        "single_seed_directional_gradient_frontier_to_weakest": all(
            means[index] > means[index + 1] for index in range(len(means) - 1)
        ),
    }
    mandatory = {key: value for key, value in gates.items() if "ideal_65_to_80" not in key}
    return {
        "status": "one_seed_development_calibration_not_ranking",
        "frontier_model": frontier,
        "observed_strongest_model": observed_strongest,
        "weakest_model": weakest,
        "observed_failure_domains": domains,
        "substantive_failure_domains": substantive,
        "schema_primary_failure_count": schema_failures,
        "family_gap_share": family_gap_share,
        "gates": gates,
        "all_development_gates_passed": all(mandatory.values()),
        "astra_canary_permitted": all(mandatory.values()),
        "ranking_claim_allowed": False,
    }


def _render(output: dict[str, Any]) -> str:
    controls = output["local_controls"]
    run = output["run_metadata"]
    lines = [
        "# UC-Bench hard suite v0.3 — controlled calibration",
        "",
        "> Primary output: model × failure mode × intervention. These are one-seed "
        "controlled results, not a stable ranking and not an authentic-cohort result.",
        "",
        "## Status and spend",
        "",
        f"Usable cells: **{run['completed_trajectory_count']}/{run['planned_trajectory_count']}**; "
        f"infrastructure failures excluded: **{run['infrastructure_failure_count']}**; "
        f"Astra requests: **{run['astra_requests']}**.",
        "",
        f"OpenRouter key usage at frozen-run start/end: "
        f"`${run['openrouter_key_usage_before_usd']:.2f}` / "
        + (
            f"`${run['openrouter_key_usage_after_usd']:.2f}`."
            if run.get("openrouter_key_usage_after_usd") is not None
            else "`pending while run is active`."
        ),
        "",
        "## Local integrity gates",
        "",
        f"All local controls: **{controls['all_local_gates_passed']}**; reference minimum "
        f"**{controls['reference_minimum_score']:.1f}**; wrong-resource maximum "
        f"**{controls['wrong_resource_maximum_score']:.1f}**; reward-hack maximum "
        f"**{controls['reward_hacking_maximum_score']:.1f}**.",
        "",
        "## Model × failure mode × intervention",
        "",
    ]
    matrix = output["controlled_results"]["matrix"]
    if not matrix:
        lines.append("No usable controlled model cells are available.")
    else:
        lines.extend(
            [
                "| model | family | role | score | selected intervention | detect | contain | "
                "action | decision | failure domains |",
                "|---|---|---|---:|---|---:|---:|---:|---:|---|",
            ]
        )
        for row in matrix:
            lines.append(
                f"| {row['model_id']} | {row['family_id']} | {row['pair_role']} | "
                f"{row['score']:.1f} | {row['selected_intervention']} | "
                f"{int(row['detected'])} | {int(row['contained'])} | "
                f"{int(row['smallest_action_correct'])} | "
                f"{int(row['decision_correct'])} | "
                f"{', '.join(row['failure_domains']) or 'none'} |"
            )
    lines.extend(["", "## Paired intervention recovery", ""])
    recovery = output["controlled_results"]["paired_recovery"]
    if not recovery:
        lines.append("Complete pairs are pending.")
    else:
        lines.extend(
            [
                "| model | family | resolving intervention | control→treated | selected | "
                "recovered |",
                "|---|---|---|---:|---:|---:|",
            ]
        )
        for row in recovery:
            lines.append(
                f"| {row['model_id']} | {row['family_id']} | {row['intervention']} | "
                f"{row['control_score']:.1f}→{row['treated_score']:.1f} "
                f"({row['score_delta']:+.1f}) | "
                f"{int(row['treated_selected_resolving_intervention'])} | "
                f"{int(row['outcome_recovered'])} |"
            )
    lines.extend(
        [
            "",
            "## Controlled breaking-point curves",
            "",
            "The shared evidence generator has five zero-cost, runnable four-level ladders. "
            "These are reference transitions; paid model curves remain pending and must not "
            "be invented from the ten paired cells.",
            "",
            "| ladder | parameter | levels | reference transition |",
            "|---|---|---|---|",
        ]
    )
    for curve in output["controlled_results"]["breaking_point_curves"]:
        transitions = " → ".join(
            f"{row['level']}:{row['expected_decision']}/{row['expected_primary_failure']}"
            for row in curve["points"]
        )
        lines.append(
            f"| {curve['ladder_id']} | {curve['parameter']} | {len(curve['points'])} | "
            f"{transitions} |"
        )
    lines.extend(
        [
            "",
            "## Authentic results",
            "",
            "No authentic hard-suite model results are claimed. The current v0.3 fixtures are "
            "controlled and biologically motivated; an authentic cohort slice must be packaged "
            "and reported separately before making empirical claims about real-world prevalence.",
            "",
            "## Acceptance and ceiling probe",
            "",
            f"Status: `{output['acceptance']['status']}`. Astra permitted: "
            f"**{output['acceptance'].get('astra_canary_permitted', False)}**. "
            "Even if permitted, a single canary is a ceiling check only; Astra ≥85 is an "
            "explicit no-go, and no ranking is allowed without repeated seeds and uncertainty.",
        ]
    )
    return "\n".join(lines) + "\n"


def _curves() -> list[dict[str, Any]]:
    rows = list(_read(LADDERS_PATH).get("rows") or [])
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["ladder_id"])].append(row)
    return [
        {
            "ladder_id": ladder_id,
            "family_id": points[0]["family_id"],
            "parameter": points[0]["parameter"],
            "points": sorted(points, key=lambda row: float(row["level"])),
        }
        for ladder_id, points in sorted(grouped.items())
    ]


def main() -> int:
    run = _read(RUNS_PATH)
    config = _read(CONFIG_PATH)
    controls = _read(CONTROLS_PATH)
    model_order = [str(row["model_id"]) for row in config["models"]]
    matrix = _matrix(list(run.get("runs") or []))
    summaries = _summaries(matrix, model_order)
    acceptance = _acceptance(
        matrix,
        summaries,
        model_order,
        expected_cells=int(run["planned_trajectory_count"]),
    )
    output = {
        "schema_version": "0.3",
        "status": "controlled_one_seed_calibration_not_ranking",
        "ranking_claim_allowed": False,
        "run_metadata": {key: value for key, value in run.items() if key != "runs"},
        "local_controls": controls,
        "controlled_results": {
            "matrix": matrix,
            "model_summaries": summaries,
            "paired_recovery": _paired_recovery(matrix),
            "breaking_point_curves": _curves(),
        },
        "authentic_results": {
            "status": "not_run_separate_partition",
            "matrix": [],
            "claim_allowed": False,
        },
        "acceptance": acceptance,
    }
    OUTPUT_PATH.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(_render(output), encoding="utf-8")
    print(json.dumps(acceptance, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

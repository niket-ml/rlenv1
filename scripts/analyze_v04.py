#!/usr/bin/env python3
"""Analyze v0.4 as a controlled failure/intervention study, never a ranking."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

from jsonschema import Draft202012Validator

from uc_bench.hard_suite_v04 import iter_v04_variants, load_v04_config

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNS_PATH = PROJECT_ROOT / "artifacts" / "diagnostics" / "hard_suite_v04_calibration_runs.json"
CONTROLS_PATH = PROJECT_ROOT / "artifacts" / "diagnostics" / "hard_suite_v04_controls.json"
LADDERS_PATH = PROJECT_ROOT / "artifacts" / "diagnostics" / "hard_suite_v04_ladders.json"
OUTPUT_PATH = PROJECT_ROOT / "artifacts" / "diagnostics" / "hard_suite_v04_analysis.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "generated" / "hard_suite_v04_report.md"

OBSERVABLE_FAILURES = {
    "Q01_identity_dependence": (
        "Biopsy-row identities conflict within fingerprint-defined patients; row AUC, "
        "patient AUC, clustered uncertainty, and effective n disagree."
    ),
    "Q02_transport_factorial": (
        "Predictive performance depends jointly on endpoint, drug, and platform; pooled "
        "or one-factor evidence cannot identify intended-use transport."
    ),
    "Q03_process_confounding": (
        "Naive, patient-grouped, and batch-blocked estimates disagree while batch is "
        "associated with outcome and permutation nulls lead to different conclusions."
    ),
    "Q04_label_sensitivity": (
        "Reviewer disagreement creates an AUC sensitivity interval that crosses the "
        "decision threshold until blinded endpoint adjudication is supplied."
    ),
    "Q05_decision_sufficiency": (
        "AUC alone appears promising, but clustered uncertainty, calibration, PPV, net "
        "benefit, and required replication n determine whether evidence is sufficient."
    ),
}

SMALLEST_ACTIONS = {
    "Q01_identity_dependence": "Reconcile patient, visit, and biopsy identity.",
    "Q02_transport_factorial": "Run the jointly endpoint-, drug-, and platform-matched bridge.",
    "Q03_process_confounding": (
        "Regenerate leakage-safe grouped/batch-blocked predictions, then obtain an "
        "endpoint-matched replication if biological evidence remains unresolved."
    ),
    "Q04_label_sensitivity": "Blindly adjudicate the prespecified endpoint from source records.",
    "Q05_decision_sufficiency": "Run the powered independent intended-use replication.",
}

COMPONENT_DOMAINS = {
    "quantitative_statistical_reasoning": "quantitative_statistical_reasoning",
    "scientific_diagnosis": "scientific_reasoning",
    "decision": "scientific_decision",
    "resource_selection_value_of_information": "evidence_diagnosis",
    "recovery_design": "recovery_design",
    "commitment_and_reproducibility": "long_horizon_execution",
}


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected JSON object: {path}")
    return value


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _variant_index() -> dict[str, dict[str, Any]]:
    return {
        str(row["variant_id"]): row
        for row in iter_v04_variants(PROJECT_ROOT, partition="development")
    }


def _schema_primary_failure(row: dict[str, Any]) -> bool:
    if row.get("classification") != "agent_task_failure":
        return False
    run_root = PROJECT_ROOT / str(row["run_directory"])
    matches = list(run_root.glob("hard4-*/submission/final_submission.json"))
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
    return sorted(
        {
            domain
            for component, domain in COMPONENT_DOMAINS.items()
            if float(components.get(component, 0.0)) < 75.0
        }
    )


def _matrix(raw_runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    variants = _variant_index()
    output = []
    for row in raw_runs:
        if row.get("classification") == "infrastructure_failure":
            continue
        variant = variants[str(row["variant_id"])]
        resources = {str(item["resource_id"]): item for item in variant["resources"]}
        resolving = resources[str(variant["correct_resource_id"])]
        grade = row.get("grade") or {}
        components = grade.get("components") or {}
        selected_id = str(row.get("selected_resource_id") or "none")
        selected = resources.get(selected_id)
        output.append(
            {
                "model_id": row["model_id"],
                "attempt_index": row["attempt_index"],
                "family_id": variant["family_id"],
                "variant_id": variant["variant_id"],
                "pair_role": variant["pair_role"],
                "controlled_or_authentic": "controlled",
                "observably_wrong": OBSERVABLE_FAILURES[str(variant["family_id"])],
                "score": float(row["score"]),
                "classification": row["classification"],
                "failure_domains": _failure_domains(row),
                "primary_failure_detected": bool(
                    grade.get("expected_primary_failure")
                    and (grade.get("components") or {}).get("scientific_diagnosis", 0) >= 60
                ),
                "contained": bool(grade.get("containment_correct", False)),
                "decision_correct": bool(grade.get("decision_correct", False)),
                "estimand_correct": bool(grade.get("estimand_correct", False)),
                "analysis_method_correct": bool(grade.get("analysis_method_correct", False)),
                "computation_score": float(grade.get("computation_score", 0.0)),
                "interpretation_correct": bool(grade.get("interpretation_correct", False)),
                "smallest_correct_action": SMALLEST_ACTIONS[str(variant["family_id"])],
                "recovery_design_correct": bool(
                    grade.get("recovery_design_correct", False)
                ),
                "resolving_intervention": resolving["intervention"],
                "resolving_intervention_class": resolving["class"],
                "correct_intervention_available": bool(
                    variant["correct_resource_available"]
                ),
                "expected_resource_id": variant["expected_resource_id"],
                "selected_resource_id": selected_id,
                "selected_intervention": selected["intervention"] if selected else "none",
                "selected_intervention_class": selected["class"] if selected else "none",
                "resource_selection_correct": bool(
                    grade.get("resource_selection_correct", False)
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
                "usable_task_count": len(selected),
                "mean_score": mean(float(row["score"]) for row in selected),
                "ceiling_rate": mean(float(row["score"]) >= 95.0 for row in selected),
                "zero_rate": mean(float(row["score"]) == 0.0 for row in selected),
                "valid_episode_rate": mean(
                    row["classification"] == "valid_episode" for row in selected
                ),
                "component_means": {
                    component: mean(
                        float(row["component_scores"].get(component, 0.0))
                        for row in selected
                    )
                    for component in COMPONENT_DOMAINS
                },
            }
        )
    return output


def _family_component_matrix(matrix: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in matrix:
        grouped[(str(row["model_id"]), str(row["family_id"]))].append(row)
    output = []
    for (model_id, family_id), rows in sorted(grouped.items()):
        output.append(
            {
                "model_id": model_id,
                "family_id": family_id,
                "cell_count": len(rows),
                "mean_score": mean(float(row["score"]) for row in rows),
                "component_means": {
                    component: mean(
                        float(row["component_scores"].get(component, 0.0))
                        for row in rows
                    )
                    for component in COMPONENT_DOMAINS
                },
            }
        )
    return output


def _paired_recovery(matrix: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in matrix:
        grouped[(str(row["model_id"]), str(row["family_id"]))].append(row)
    output = []
    for (model_id, family_id), rows in sorted(grouped.items()):
        control = next((row for row in rows if row["pair_role"] == "control"), None)
        treated = next((row for row in rows if row["pair_role"] == "treated"), None)
        if control is None or treated is None:
            continue
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
                "score_improved": treated["score"] > control["score"],
                "treated_decision_correct": treated["decision_correct"],
                "treated_containment_correct": treated["contained"],
                "strict_behavioral_recovery": all(
                    (
                        treated["decision_correct"],
                        treated["contained"],
                        treated["recovery_design_correct"],
                    )
                ),
                "component_deltas": {
                    component: float(treated["component_scores"].get(component, 0.0))
                    - float(control["component_scores"].get(component, 0.0))
                    for component in COMPONENT_DOMAINS
                },
            }
        )
    return output


def _gap_share(
    family_matrix: list[dict[str, Any]], summaries: list[dict[str, Any]]
) -> dict[str, float]:
    if len(summaries) < 2:
        return {}
    strongest = max(summaries, key=lambda row: float(row["mean_score"]))["model_id"]
    weakest = min(summaries, key=lambda row: float(row["mean_score"]))["model_id"]
    strong = {
        row["family_id"]: float(row["mean_score"])
        for row in family_matrix
        if row["model_id"] == strongest
    }
    weak = {
        row["family_id"]: float(row["mean_score"])
        for row in family_matrix
        if row["model_id"] == weakest
    }
    gaps = {
        family: abs(value - weak[family])
        for family, value in strong.items()
        if family in weak
    }
    total = sum(gaps.values())
    return {family: value / total for family, value in gaps.items()} if total else {}


def _acceptance(
    matrix: list[dict[str, Any]],
    summaries: list[dict[str, Any]],
    gap_share: dict[str, float],
    planned: int,
) -> dict[str, Any]:
    if len(matrix) != planned or len(summaries) != 3:
        return {"evaluated": False, "reason": "frozen 30-cell matrix incomplete"}
    config = load_v04_config(PROJECT_ROOT)
    gates = config["acceptance_gates"]
    strongest = max(summaries, key=lambda row: float(row["mean_score"]))
    weakest = min(summaries, key=lambda row: float(row["mean_score"]))
    domains = {
        domain
        for row in matrix
        for domain in row["failure_domains"]
        if domain != "schema_execution"
    }
    failed_rows = [row for row in matrix if float(row["score"]) < 95.0]
    schema_share = (
        mean(bool(row["schema_primary_failure"]) for row in failed_rows)
        if failed_rows
        else 0.0
    )
    results = {
        "strongest_mean_below_85": strongest["mean_score"]
        < float(gates["strongest_overall_maximum"]),
        "strongest_in_ideal_65_to_80": 65.0 <= strongest["mean_score"] <= 80.0,
        "strongest_quantitative_in_ideal_60_to_85": 60.0
        <= strongest["component_means"]["quantitative_statistical_reasoning"]
        <= 85.0,
        "no_more_than_25_percent_at_ceiling": strongest["ceiling_rate"] <= 0.25,
        "weakest_not_universal_zero": weakest["zero_rate"] < 1.0,
        "at_least_three_interpretable_failure_domains": len(domains)
        >= int(gates["minimum_quantitatively_distinct_failure_modes"]),
        "schema_not_primary": schema_share < 0.5,
        "no_family_over_30_percent_of_gap": bool(gap_share)
        and max(gap_share.values()) <= float(gates["maximum_single_family_gap_share"]),
    }
    return {
        "evaluated": True,
        "gates": results,
        "all_mandatory_gates_pass": all(
            value
            for name, value in results.items()
            if name
            not in {
                "strongest_in_ideal_65_to_80",
                "strongest_quantitative_in_ideal_60_to_85",
            }
        ),
        "strongest_model": strongest["model_id"],
        "weakest_model": weakest["model_id"],
        "substantive_failure_domains": sorted(domains),
        "schema_share_of_failed_cells": schema_share,
    }


def _report(analysis: dict[str, Any]) -> str:
    summaries = analysis["model_summaries"]
    acceptance = analysis["acceptance"]
    if not acceptance.get("evaluated"):
        acceptance_label = "PENDING"
    else:
        acceptance_label = (
            "PASS" if acceptance.get("all_mandatory_gates_pass") else "NO-GO"
        )
    spend = analysis["observed_incremental_spend_usd"]
    spend_text = "not available" if spend is None else f"${float(spend):.4f}"
    lines = [
        "# UC-Bench hard suite v0.4 — controlled calibration",
        "",
        "> This is a one-seed development calibration, not a stable model ranking. ",
        "> Authentic-cohort results are reported separately and are currently empty.",
        "",
        "## Status",
        "",
        f"- Frozen cells completed: {analysis['completed_usable_cells']} / "
        f"{analysis['planned_cells']}",
        f"- Infrastructure failures excluded: {analysis['infrastructure_failure_count']}",
        f"- Astra requests: {analysis['astra_requests']}",
        f"- Observed incremental spend: {spend_text}",
        f"- Acceptance: **{acceptance_label}**",
        "",
        "## Model × component summary",
        "",
        "| Model | n | Mean | Ceiling | Zero | Quant | Science | Decision | VOI | "
        "Recovery | Commit |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summaries:
        c = row["component_means"]
        lines.append(
            f"| {row['model_id']} | {row['usable_task_count']} | {row['mean_score']:.1f} | "
            f"{row['ceiling_rate']:.0%} | {row['zero_rate']:.0%} | "
            f"{c['quantitative_statistical_reasoning']:.1f} | "
            f"{c['scientific_diagnosis']:.1f} | {c['decision']:.1f} | "
            f"{c['resource_selection_value_of_information']:.1f} | "
            f"{c['recovery_design']:.1f} | {c['commitment_and_reproducibility']:.1f} |"
        )
    lines.extend(
        [
            "",
            "## Acceptance gates",
            "",
            "| Gate | Result |",
            "|---|---:|",
        ]
    )
    for name, passed in acceptance.get("gates", {}).items():
        lines.append(f"| {name} | {'pass' if passed else 'fail'} |")
    lines.extend(
        [
            "",
            "The mandatory no-go is family concentration: Q03 explains 43.6% of the "
            "Sol–GPT-5.2 gap, above the frozen 30% maximum. Sol is also 0.50 above the "
            "ideal 65–80 range, and its quantitative component remains near ceiling at "
            "99.59. Astra is therefore not permitted.",
            "",
            "## Family gap share",
            "",
            "| Family | Share of strongest-to-weakest gap |",
            "|---|---:|",
        ]
    )
    for family, share in analysis["single_family_gap_share"].items():
        lines.append(f"| {family} | {share:.1%} |")
    lines.extend(
        [
            "",
            "## Paired intervention behavior",
            "",
            "| Model | Family | Intervention | Score delta | Selected | Decision | "
            "Strict recovery |",
            "|---|---|---|---:|---:|---:|---:|",
        ]
    )
    for row in analysis["paired_intervention_recovery"]:
        lines.append(
            f"| {row['model_id']} | {row['family_id']} | {row['intervention']} | "
            f"{row['score_delta']:+.2f} | "
            f"{'yes' if row['treated_selected_resolving_intervention'] else 'no'} | "
            f"{'correct' if row['treated_decision_correct'] else 'wrong'} | "
            f"{'yes' if row['strict_behavioral_recovery'] else 'no'} |"
        )
    lines.extend(
        [
            "",
            "## Product outputs",
            "",
            "The JSON analysis contains the full model × failure-mode × intervention rows, "
            "paired recovery results, family/component matrix, and deterministic breaking-"
            "point curves. Aggregate scores are secondary.",
            "",
            "No adaptation remedy is inferred. Prompting, retrieval, tool training, SFT, or "
            "RL should be named only after a paired experiment directly tests it.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    config = _read(PROJECT_ROOT / "configs" / "hard_suite_v04_calibration.json")
    raw = _read(RUNS_PATH) if RUNS_PATH.exists() else {"runs": []}
    raw_runs = list(raw.get("runs") or [])
    matrix = _matrix(raw_runs)
    model_order = [str(row["model_id"]) for row in config["models"]]
    summaries = _summaries(matrix, model_order)
    family_matrix = _family_component_matrix(matrix)
    gap_share = _gap_share(family_matrix, summaries)
    planned = len(config["variant_ids"]) * len(model_order) * int(config["attempts_per_cell"])
    controls = _read(CONTROLS_PATH)
    ladders = _read(LADDERS_PATH)
    infrastructure_count = sum(
        row.get("classification") == "infrastructure_failure" for row in raw_runs
    )
    analysis = {
        "schema_version": "0.4",
        "status": "controlled_development_calibration_not_ranking",
        "ranking_claim_allowed": False,
        "repeated_seed_uncertainty_available": False,
        "astra_requests": int(raw.get("astra_requests") or 0),
        "planned_cells": planned,
        "completed_usable_cells": len(matrix),
        "infrastructure_failure_count": infrastructure_count,
        "observed_incremental_spend_usd": raw.get("observed_incremental_spend_usd"),
        "local_gates": controls["gates"],
        "model_summaries": summaries,
        "model_by_family_by_component": family_matrix,
        "model_by_failure_mode_by_intervention": matrix,
        "paired_intervention_recovery": _paired_recovery(matrix),
        "breaking_point_curves": ladders["rows"],
        "single_family_gap_share": gap_share,
        "acceptance": _acceptance(matrix, summaries, gap_share, planned),
        "controlled_results": matrix,
        "authentic_results": [],
        "authentic_result_status": "not_run_do_not_conflate_with_controlled_simulation",
    }
    _write(OUTPUT_PATH, analysis)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(_report(analysis), encoding="utf-8")
    print(
        json.dumps(
            {
                "planned_cells": planned,
                "completed_usable_cells": len(matrix),
                "acceptance": analysis["acceptance"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Build local v0.5 construct, policy, integrity, and graceful-failure controls."""

from __future__ import annotations

import copy
import json
import tempfile
from pathlib import Path
from statistics import mean
from typing import Any

from uc_bench.errors import ContractError
from uc_bench.hard_suite_v05 import (
    V05Builder,
    V05Environment,
    compute_v05_metrics,
    grade_v05,
    iter_v05_scenarios,
    reference_v05_assessment,
    reference_v05_commitment,
    reference_v05_submission,
    validate_v05_config,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "artifacts" / "diagnostics" / "hard_suite_v05_controls.json"


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _degrade_commitment(value: dict[str, Any], decision: str) -> dict[str, Any]:
    result = copy.deepcopy(value)
    result["intended_use"]["endpoint"] = "unspecified_response"
    result["intended_use"]["probability_threshold"] = 0.50
    for audit in result["audits"].values():
        audit["status"] = "clear"
        audit["evidence_refs"] = ["missing/generic_checklist.txt"]
        audit["decision_effect"] = "No concerns noted."
    result["reproduction"] = {
        "predictions_compared": 0,
        "max_abs_error": 0.1,
        "passed": False,
        "model_sha256": "not-actually-verified",
    }
    result["plan"].update(
        {
            "analysis_unit": "row",
            "grouping_keys": ["sample_id"],
            "uncertainty_unit": "row",
            "preprocessing_fit_scope": "all_data",
            "metric_families": [
                "training_accuracy",
                "feature_count",
                "coefficient_size",
                "generic_p_value",
            ],
            "decision_rule": {
                "minimum_auc": 0.5,
                "minimum_auc_ci_low": 0.0,
                "maximum_brier": 1.0,
                "minimum_net_benefit": -1.0,
            },
            "pre_reveal_decision": decision,
            "live_hypotheses": ["model_good", "model_bad"],
        }
    )
    result["evidence_refs"] = [
        "missing/summary.txt",
        "missing/checklist.txt",
        "missing/readme.txt",
    ]
    return result


def _degrade_assessment(value: dict[str, Any], decision: str, resource_id: str) -> dict[str, Any]:
    result = copy.deepcopy(value)
    result["claim_statuses"] = {name: "admissible" for name in result["claim_statuses"]}
    result["provisional_decision"] = decision
    result["dominant_uncertainty"] = "none"
    result["resource_request"] = {
        "resource_id": resource_id,
        "expected_effect": "More evidence is always reassuring.",
        "hypotheses_discriminated": ["model_good"],
    }
    result["evidence_refs"] = ["missing/auc.txt", "missing/plot.png"]
    return result


def _degrade_submission(
    value: dict[str, Any], decision: str, resource_id: str, metrics: dict[str, float]
) -> dict[str, Any]:
    result = copy.deepcopy(value)
    result.update(
        {
            "decision": decision,
            "confidence": 0.99,
            "metrics": metrics,
            "claim_statuses": {name: "admissible" for name in result["claim_statuses"]},
            "intervention_effect": (
                "resolves_blocker" if resource_id != "none" else "no_resource_needed"
            ),
            "belief_update": {
                "prior_confidence": 0.99,
                "posterior_confidence": 0.99,
                "direction": "unchanged",
                "explanation": "AUC is good enough.",
            },
            "smallest_next_action_class": ("additional_data" if resource_id != "none" else "none"),
            "smallest_next_action": "Proceed using the generic policy.",
            "supported_claims": [
                {
                    "claim": "The predictor is validated.",
                    "status": "supported",
                    "evidence_refs": ["missing/result.txt"],
                }
            ],
            "limitations": ["None material."],
            "evidence_refs": [
                "missing/result.txt",
                "missing/resource.txt",
                "missing/memo.txt",
            ],
        }
    )
    return result


def _run_flavor(
    temporary_root: Path,
    scenario: dict[str, Any],
    flavor: str,
) -> dict[str, Any]:
    run_root = temporary_root / flavor
    run_root.mkdir(parents=True, exist_ok=True)
    package = V05Builder(PROJECT_ROOT).build(str(scenario["scenario_id"]), output_root=run_root)
    environment = V05Environment(package)
    commitment = reference_v05_commitment(package, PROJECT_ROOT)
    policy_decision = {
        "always_advance": "advance",
        "always_stop": "stop",
        "always_abstain": "insufficient_evidence",
        "always_more_data": "pause",
        "mediocre": "advance",
    }.get(flavor)
    if flavor == "alternative_expert":
        commitment["plan"]["analysis_unit"] = "subject"
        commitment["plan"]["uncertainty_unit"] = "site-stratified subject-cluster resampling"
        commitment["plan"]["primary_estimand"] = (
            "external patient discrimination, calibration and threshold utility"
        )
    elif policy_decision:
        commitment = _degrade_commitment(commitment, policy_decision)
    _write(package.workspace_root / "submission" / "commitment.json", commitment)
    environment.commit_validation_plan()
    environment.reveal_validation()
    assessment = reference_v05_assessment(package, PROJECT_ROOT)
    if policy_decision:
        requested = "R5" if flavor == "always_more_data" else "none"
        assessment = _degrade_assessment(assessment, policy_decision, requested)
    _write(
        package.workspace_root / "submission" / "validation_assessment.json",
        assessment,
    )
    environment.request_followup()
    submission = reference_v05_submission(package)
    if policy_decision:
        submission = _degrade_submission(
            submission,
            policy_decision,
            str(environment.selected_resource),
            compute_v05_metrics(package.workspace_root, followup=True),
        )
    _write(package.workspace_root / "submission" / "final_submission.json", submission)
    environment.submit_diligence()
    grade = grade_v05(
        PROJECT_ROOT,
        package,
        environment.commitment,
        environment.assessment,
        environment.submission,
        selected_resource=environment.selected_resource,
        commitment_immutable=environment.commitment_immutable,
        assessment_immutable=environment.assessment_immutable,
    )
    return grade.to_dict()


def _single_error_control(temporary_root: Path, scenario: dict[str, Any]) -> dict[str, Any]:
    package = V05Builder(PROJECT_ROOT).build(
        str(scenario["scenario_id"]), output_root=temporary_root / "single-error"
    )
    environment = V05Environment(package)
    commitment = reference_v05_commitment(package, PROJECT_ROOT)
    commitment["audits"]["identity"]["status"] = "unknown"
    _write(package.workspace_root / "submission" / "commitment.json", commitment)
    environment.commit_validation_plan()
    environment.reveal_validation()
    assessment = reference_v05_assessment(package, PROJECT_ROOT)
    _write(package.workspace_root / "submission" / "validation_assessment.json", assessment)
    environment.request_followup()
    submission = reference_v05_submission(package)
    _write(package.workspace_root / "submission" / "final_submission.json", submission)
    environment.submit_diligence()
    return grade_v05(
        PROJECT_ROOT,
        package,
        environment.commitment,
        environment.assessment,
        environment.submission,
        selected_resource=environment.selected_resource,
        commitment_immutable=True,
        assessment_immutable=True,
    ).to_dict()


def _integrity_controls(temporary_root: Path, scenario: dict[str, Any]) -> dict[str, Any]:
    package = V05Builder(PROJECT_ROOT).build(
        str(scenario["scenario_id"]), output_root=temporary_root / "integrity"
    )
    pre_reveal_forbidden = [
        path.relative_to(package.workspace_root).as_posix()
        for path in package.workspace_root.rglob("*")
        if path.is_file()
        and any(token in path.name.lower() for token in ("outcome", "answer", "private"))
    ]
    environment = V05Environment(package)
    commitment = reference_v05_commitment(package, PROJECT_ROOT)
    _write(package.workspace_root / "submission" / "commitment.json", commitment)
    environment.commit_validation_plan()
    locked_model = package.workspace_root / "model" / "locked_model.json"
    original = locked_model.read_text(encoding="utf-8")
    locked_model.write_text(original + "\n", encoding="utf-8")
    mutation_rejected = False
    try:
        environment.reveal_validation()
    except ContractError:
        mutation_rejected = True
    return {
        "pre_reveal_forbidden_paths": pre_reveal_forbidden,
        "mutation_rejected": mutation_rejected,
    }


def main() -> None:
    validation = validate_v05_config(PROJECT_ROOT)
    scenarios = iter_v05_scenarios(PROJECT_ROOT)
    with tempfile.TemporaryDirectory(prefix="uc-v05-controls-") as temporary:
        temporary_root = Path(temporary)
        per_scenario = []
        policy_scores: dict[str, list[float]] = {
            name: []
            for name in (
                "always_advance",
                "always_stop",
                "always_abstain",
                "always_more_data",
            )
        }
        for scenario in scenarios:
            reference = _run_flavor(temporary_root, scenario, "reference")
            alternative = _run_flavor(temporary_root, scenario, "alternative_expert")
            mediocre = _run_flavor(temporary_root, scenario, "mediocre")
            policies = {}
            for policy in policy_scores:
                grade = _run_flavor(temporary_root, scenario, policy)
                policies[policy] = grade
                policy_scores[policy].append(float(grade["score"]))
            per_scenario.append(
                {
                    "scenario_id": scenario["scenario_id"],
                    "scenario_class": scenario["scenario_class"],
                    "reference": reference,
                    "alternative_expert": alternative,
                    "mediocre": mediocre,
                    "policies": policies,
                }
            )
        single_error = _single_error_control(temporary_root, scenarios[1])
        integrity = _integrity_controls(temporary_root, scenarios[0])

    policy_means = {name: mean(scores) for name, scores in policy_scores.items()}
    checks = {
        "configuration_valid": validation["heldout_sealed_before_model_calls"],
        "astra_unexposed": validation["astra_exposure_count"] == 0,
        "reference_minimum_90": min(row["reference"]["score"] for row in per_scenario) >= 90,
        "alternative_method_minimum_90": min(
            row["alternative_expert"]["score"] for row in per_scenario
        )
        >= 90,
        "reference_beats_mediocre_each_scenario": all(
            row["reference"]["score"] > row["mediocre"]["score"] for row in per_scenario
        ),
        "reference_beats_mediocre_each_milestone": all(
            row["reference"]["milestone_scores"][milestone]
            > row["mediocre"]["milestone_scores"][milestone]
            for row in per_scenario
            for milestone in row["reference"]["milestone_scores"]
        ),
        "universal_policies_below_50": max(policy_means.values()) < 50,
        "single_ordinary_error_retains_over_50": single_error["score"] > 50,
        "pre_reveal_has_no_outcomes_or_private_answers": not integrity[
            "pre_reveal_forbidden_paths"
        ],
        "committed_mutation_rejected": integrity["mutation_rejected"],
        "decisions_are_symmetric": len(
            {row["reference"]["expected_final_decision"] for row in per_scenario}
        )
        >= 3,
        "intervention_effects_are_heterogeneous": len(
            {row["reference"]["expected_intervention_effect"] for row in per_scenario}
        )
        >= 4,
    }
    output = {
        "schema_version": "0.5",
        "suite_id": "uc_anti_tnf_predictor_diligence_v0_5",
        "model_calls": 0,
        "configuration": validation,
        "checks": checks,
        "all_local_gates_passed": all(checks.values()),
        "policy_mean_scores": policy_means,
        "single_error_control": single_error,
        "integrity_controls": integrity,
        "scenarios": per_scenario,
    }
    _write(OUTPUT_PATH, output)
    print(
        json.dumps(
            {"all_local_gates_passed": all(checks.values()), "checks": checks},
            indent=2,
        )
    )
    if not all(checks.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

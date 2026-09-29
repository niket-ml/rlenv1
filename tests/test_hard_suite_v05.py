from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from uc_bench.errors import ConfigurationError, ContractError, InvalidTransitionError
from uc_bench.hard_suite_v05 import (
    V05Builder,
    V05Environment,
    compute_v05_metrics,
    grade_v05,
    iter_v05_scenarios,
    reference_v05_assessment,
    reference_v05_commitment,
    reference_v05_submission,
    run_reference_v05_episode,
    validate_v05_config,
)
from uc_bench.hard_suite_v05_runner import V05RunConfig

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def test_v05_partitions_are_sealed_disjoint_and_cover_the_same_job_states() -> None:
    result = validate_v05_config(PROJECT_ROOT)
    assert result["milestone_count"] == 10
    assert result["development_scenario_count"] == 6
    assert result["heldout_scenario_count"] == 6
    assert result["heldout_sealed_before_model_calls"] is True
    assert result["astra_exposure_count"] == 0


@pytest.mark.parametrize("partition", ["development", "heldout"])
def test_v05_reference_and_alternative_decisions_cover_every_state(
    tmp_path: Path, partition: str
) -> None:
    decisions = set()
    effects = set()
    for scenario in iter_v05_scenarios(PROJECT_ROOT, partition=partition):
        _, _, grade = run_reference_v05_episode(
            PROJECT_ROOT,
            str(scenario["scenario_id"]),
            output_root=tmp_path / partition,
            partition=partition,
        )
        assert grade.score == 100.0
        assert set(grade.milestone_scores.values()) == {100.0}
        assert set(grade.capability_scores.values()) == {100.0}
        decisions.add(grade.expected_final_decision)
        effects.add(grade.expected_intervention_effect)
    assert len(decisions) >= 3
    assert len(effects) >= 4


def test_v05_start_state_contains_no_outcomes_or_private_answer(tmp_path: Path) -> None:
    scenario = iter_v05_scenarios(PROJECT_ROOT)[2]
    package = V05Builder(PROJECT_ROOT).build(str(scenario["scenario_id"]), output_root=tmp_path)
    assert not (package.workspace_root / "revealed").exists()
    assert not (package.workspace_root / "followup").exists()
    forbidden = (
        '"optimal_resource"',
        '"resource_utilities"',
        '"final_decision"',
        '"designed_effect"',
        '"scenario_class"',
    )
    rendered = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in package.workspace_root.rglob("*")
        if path.is_file()
    )
    assert not any(token in rendered for token in forbidden)


def test_v05_irreversible_sequence_and_mutation_guards(tmp_path: Path) -> None:
    scenario = iter_v05_scenarios(PROJECT_ROOT)[0]
    package = V05Builder(PROJECT_ROOT).build(str(scenario["scenario_id"]), output_root=tmp_path)
    environment = V05Environment(package)
    with pytest.raises(InvalidTransitionError):
        environment.reveal_validation()
    commitment = reference_v05_commitment(package, PROJECT_ROOT)
    _write(package.workspace_root / "submission" / "commitment.json", commitment)
    environment.commit_validation_plan()
    with pytest.raises(InvalidTransitionError):
        environment.commit_validation_plan()
    model_path = package.workspace_root / "model" / "locked_model.json"
    model_path.write_text(model_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ContractError, match="changed"):
        environment.reveal_validation()


def test_v05_assessment_and_resource_choice_are_immutable(tmp_path: Path) -> None:
    scenario = iter_v05_scenarios(PROJECT_ROOT)[1]
    package = V05Builder(PROJECT_ROOT).build(str(scenario["scenario_id"]), output_root=tmp_path)
    environment = V05Environment(package)
    commitment = reference_v05_commitment(package, PROJECT_ROOT)
    _write(package.workspace_root / "submission" / "commitment.json", commitment)
    environment.commit_validation_plan()
    environment.reveal_validation()
    assessment = reference_v05_assessment(package, PROJECT_ROOT)
    assessment_path = package.workspace_root / "submission" / "validation_assessment.json"
    _write(assessment_path, assessment)
    reveal = environment.request_followup()
    assert reveal["selected_resource"] == "R1"
    assessment["resource_request"]["resource_id"] = "R5"
    _write(assessment_path, assessment)
    submission = reference_v05_submission(package)
    _write(package.workspace_root / "submission" / "final_submission.json", submission)
    with pytest.raises(ContractError, match="changed"):
        environment.submit_diligence()


def test_v05_controlled_evidence_has_real_breaking_behavior(tmp_path: Path) -> None:
    by_class = {str(row["scenario_class"]): row for row in iter_v05_scenarios(PROJECT_ROOT)}
    leakage = by_class["batch_or_preprocessing_leakage"]
    package, _, grade = run_reference_v05_episode(
        PROJECT_ROOT,
        str(leakage["scenario_id"]),
        output_root=tmp_path / "leakage",
    )
    assert grade.observed_evidence["initial_metrics"]["auc"] > 0.9
    assert grade.observed_evidence["followup_metrics"]["auc"] < 0.7
    assert grade.expected_final_decision == "stop"

    endpoint = by_class["endpoint_label_ambiguity"]
    _, _, endpoint_grade = run_reference_v05_episode(
        PROJECT_ROOT,
        str(endpoint["scenario_id"]),
        output_root=tmp_path / "endpoint",
    )
    assert endpoint_grade.observed_evidence["initial_metrics"]["reviewer_disagreement_rate"] > 0.1
    assert endpoint_grade.observed_evidence["followup_metrics"]["reviewer_disagreement_rate"] == 0
    assert endpoint_grade.expected_intervention_effect == "exposes_second_blocker"

    irreducible = by_class["underpowered_or_irreducible_external_evidence"]
    _, _, irreducible_grade = run_reference_v05_episode(
        PROJECT_ROOT,
        str(irreducible["scenario_id"]),
        output_root=tmp_path / "irreducible",
    )
    assert irreducible_grade.observed_evidence["followup_metrics"]["auc_ci_low"] < 0.58
    assert irreducible_grade.expected_final_decision == "insufficient_evidence"


def test_v05_different_valid_statistical_workflow_is_not_penalized(tmp_path: Path) -> None:
    scenario = iter_v05_scenarios(PROJECT_ROOT)[4]
    package, environment, reference_grade = run_reference_v05_episode(
        PROJECT_ROOT,
        str(scenario["scenario_id"]),
        output_root=tmp_path,
    )
    alternative = copy.deepcopy(environment.commitment)
    alternative["plan"]["analysis_unit"] = "subject"
    alternative["plan"]["uncertainty_unit"] = "site-stratified subject-cluster bootstrap"
    alternative["plan"]["primary_estimand"] = (
        "subject-level external discrimination, calibration and clinical utility"
    )
    grade = grade_v05(
        PROJECT_ROOT,
        package,
        alternative,
        environment.assessment,
        environment.submission,
        selected_resource=environment.selected_resource,
        commitment_immutable=True,
        assessment_immutable=True,
    )
    assert grade.score == reference_grade.score == 100.0


def test_v05_one_early_error_does_not_zero_valid_recovery(tmp_path: Path) -> None:
    scenario = iter_v05_scenarios(PROJECT_ROOT)[1]
    package, environment, _ = run_reference_v05_episode(
        PROJECT_ROOT,
        str(scenario["scenario_id"]),
        output_root=tmp_path,
    )
    flawed = copy.deepcopy(environment.commitment)
    flawed["audits"]["identity"]["status"] = "unknown"
    grade = grade_v05(
        PROJECT_ROOT,
        package,
        flawed,
        environment.assessment,
        environment.submission,
        selected_resource=environment.selected_resource,
        commitment_immutable=True,
        assessment_immutable=True,
    )
    assert 50 < grade.score < 100
    assert grade.milestone_scores["M03"] < 100
    assert grade.milestone_scores["M08"] == 100
    assert grade.milestone_scores["M10"] == 100


def test_v05_metrics_are_deterministic(tmp_path: Path) -> None:
    scenario = iter_v05_scenarios(PROJECT_ROOT)[0]
    package, _, _ = run_reference_v05_episode(
        PROJECT_ROOT,
        str(scenario["scenario_id"]),
        output_root=tmp_path,
    )
    assert compute_v05_metrics(package.workspace_root) == compute_v05_metrics(
        package.workspace_root
    )
    assert compute_v05_metrics(package.workspace_root, followup=True) == compute_v05_metrics(
        package.workspace_root, followup=True
    )


def test_v05_control_artifact_passes_all_prepaid_gates() -> None:
    controls = json.loads(
        (PROJECT_ROOT / "artifacts" / "diagnostics" / "hard_suite_v05_controls.json").read_text(
            encoding="utf-8"
        )
    )
    assert controls["model_calls"] == 0
    assert controls["all_local_gates_passed"] is True
    assert max(controls["policy_mean_scores"].values()) < 50


def test_v05_runner_budget_and_partition_validation() -> None:
    config = V05RunConfig("model", "run", "scenario", seed=1)
    assert config.maximum_turns == 55
    assert config.partition == "development"
    with pytest.raises(ConfigurationError, match="Unknown v0.5 partition"):
        V05RunConfig("model", "run", "scenario", seed=1, partition="secret")
    with pytest.raises(ConfigurationError, match="budgets"):
        V05RunConfig("model", "run", "scenario", seed=1, maximum_turns=0)


def test_v05_breaking_point_ladders_are_development_heldout_disjoint() -> None:
    development = json.loads(
        (PROJECT_ROOT / "configs" / "hard_suite_v05_ladders.json").read_text(encoding="utf-8")
    )
    heldout = json.loads(
        (PROJECT_ROOT / "grader_private" / "hard_suite_v05_ladders.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(development["ladders"]) == 5
    assert len(heldout["heldout_ladders"]) == 5
    assert heldout["astra_exposure_count"] == 0
    for development_ladder, heldout_ladder in zip(
        development["ladders"], heldout["heldout_ladders"], strict=True
    ):
        assert development_ladder["ladder_id"] == heldout_ladder["ladder_id"]
        development_rungs = {row["value"] for row in development_ladder["rungs"]}
        heldout_rungs = set(heldout_ladder["rungs"])
        if development_ladder["ladder_id"] != "transport_mismatch_count":
            assert development_rungs.isdisjoint(heldout_rungs)

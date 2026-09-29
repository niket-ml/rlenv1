from __future__ import annotations

import json
from pathlib import Path

import pytest

from uc_bench.hard_suite_v07 import (
    CASE_IDS,
    V07Environment,
    V07ProtocolError,
    build_development_cases,
    direct_submission,
    empty_submission,
    generic_submission,
    grade_submission,
    reference_checkpoints,
    replay_reference,
    validate_public_packet_has_no_truth_labels,
    validate_v07_config,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module", autouse=True)
def _packets() -> None:
    build_development_cases(ROOT)


def mechanisms(case_id: str) -> list[str]:
    return ["signal_collapses", "signal_remains"] if case_id == "case_03" else ["default"]


def test_v07_is_four_case_five_checkpoint_freeze_ready_environment() -> None:
    status = validate_v07_config(ROOT)
    assert status == {
        "status": "ready_for_one_time_freeze_and_bounded_execution",
        "case_count": 4,
        "checkpoint_count": 5,
        "checkpoint_weight_sum": 100,
        "paid_runner_created": True,
    }
    assert (ROOT / "scripts/run_v07_pilot.py").exists()


def test_public_packets_are_complete_and_do_not_name_planted_truth() -> None:
    for case_id in CASE_IDS:
        packet = ROOT / "tasks/hard_suite_v07/development" / case_id
        required = {
            "data/cohort_metadata.csv",
            "data/locked_predictions.csv",
            "data/expression_feature_summary.csv",
            "data/endpoint_source_ledger.csv",
            "pipeline/preprocess.py",
            "pipeline/preprocess_config.json",
            "pipeline/fit_membership.csv",
            "logs/execution_log.csv",
            "model/model_manifest.json",
            "model/reproduction_cases.csv",
            "sponsor/assertions.md",
            "followup_catalog.json",
            "intended_use.json",
            "validation_manifest.json",
        }
        assert required <= {
            str(path.relative_to(packet)) for path in packet.rglob("*") if path.is_file()
        }
        assert validate_public_packet_has_no_truth_labels(ROOT, case_id) == []


def test_two_distinct_valid_approaches_score_at_least_90_on_every_case() -> None:
    for case_id in CASE_IDS:
        for mechanism in mechanisms(case_id):
            reference = grade_submission(
                ROOT,
                case_id,
                direct_submission(ROOT, case_id, mechanism=mechanism),
                mechanism=mechanism,
            )
            alternative = grade_submission(
                ROOT,
                case_id,
                direct_submission(ROOT, case_id, mechanism=mechanism, alternative=True),
                mechanism=mechanism,
            )
            assert reference.work_quality_score >= 90
            assert alternative.work_quality_score >= 90
            assert reference.full_mission_success
            assert alternative.full_mission_success


def test_nesting_and_unscored_prose_do_not_change_score() -> None:
    flat = direct_submission(ROOT, "case_04")
    nested = json.loads(json.dumps(flat))
    c3 = nested["checkpoints"]["C3"]
    c3["analysis"] = {"results": c3.pop("metrics")}
    nested["unscored_narrative"] = "Different defensible organization and prose."
    one = grade_submission(ROOT, "case_04", flat)
    two = grade_submission(ROOT, "case_04", nested)
    assert abs(one.work_quality_score - two.work_quality_score) <= 0.01


def test_annotated_professional_language_is_not_an_exact_label_trap() -> None:
    submission = direct_submission(ROOT, "case_02")
    submission["checkpoints"]["C1"]["diagnosed_concepts"] = [
        "Non-independence from repeated patient biopsies",
        "Performance shifts materially with site mix",
    ]
    submission["checkpoints"]["C2"]["fit_scope"] = (
        "Training-only and outcome-blind preprocessing fit"
    )
    submission["checkpoints"]["C2"]["uncertainty_method"] = (
        "Site-stratified cluster bootstrap over patients"
    )
    submission["selected_resource"] = "X17 — source records"
    submission["checkpoints"]["C4"]["selected_resource"] = "X17 — source records"
    submission["checkpoints"]["C5"].update(
        {
            "belief_direction": "Evidence weakens and the site blocker remains unresolved",
            "initial_decision": "Pause pending reconciliation",
            "final_decision": "Pause — site transport remains unresolved",
            "supported_claims": ["Biopsy-row performance is misleading and not decision-valid"],
            "unsupported_claims": [
                "The evidence does not establish independent validation",
                "No causal treatment effect is supported",
            ],
            "claims_made": ["Biopsy-row performance is misleading and not decision-valid"],
        }
    )
    result = grade_submission(ROOT, "case_02", submission)
    assert result.work_quality_score >= 95
    assert result.full_mission_success


def test_empty_generic_and_keyword_controls_are_low() -> None:
    keyword = empty_submission()
    keyword["checkpoints"]["C1"] = {
        "diagnosed_concepts": [
            "patient_dependence",
            "site_confounding",
            "validation_information_leakage",
            "miscalibration",
            "negative_threshold_utility",
        ]
    }
    for case_id in CASE_IDS:
        assert grade_submission(ROOT, case_id, empty_submission()).work_quality_score <= 15
        assert grade_submission(ROOT, case_id, generic_submission()).work_quality_score <= 20
        assert grade_submission(ROOT, case_id, keyword).work_quality_score <= 15


def test_universal_decision_policies_fail_full_mission() -> None:
    for policy in ("advance", "pause", "stop", "abstain"):
        success = 0
        for case_id in CASE_IDS:
            submission = direct_submission(
                ROOT,
                case_id,
                mechanism="signal_collapses" if case_id == "case_03" else "default",
            )
            submission["checkpoints"]["C5"]["final_decision"] = policy
            result = grade_submission(
                ROOT,
                case_id,
                submission,
                mechanism="signal_collapses" if case_id == "case_03" else "default",
            )
            success += int(result.full_mission_success)
        assert success < len(CASE_IDS)


def test_buy_everything_fails_budget_and_value() -> None:
    submission = direct_submission(ROOT, "case_02")
    submission["selected_resource"] = "all"
    submission["spent_units"] = 11
    submission["checkpoints"]["C4"]["selected_resource"] = "all"
    result = grade_submission(ROOT, "case_02", submission)
    assert result.checkpoint_scores["C4"] < 65
    assert not result.full_mission_success


def test_one_ordinary_early_error_retains_substantial_later_credit() -> None:
    submission = direct_submission(ROOT, "case_02")
    submission["checkpoints"]["C1"].update(
        {"analysis_unit": "biopsy", "n_patients": 155, "n_samples": 155}
    )
    result = grade_submission(ROOT, "case_02", submission)
    assert result.checkpoint_scores["C1"] < 70
    assert result.work_quality_score >= 80
    assert result.checkpoint_scores["C5"] == 100


def test_environment_enforces_commit_reveal_purchase_and_submit(tmp_path: Path) -> None:
    checkpoints, selected = reference_checkpoints(ROOT, "case_01")
    environment = V07Environment(ROOT, "case_01", tmp_path / "episode")
    with pytest.raises(V07ProtocolError, match="prior locked commitment"):
        environment.reveal_validation()
    environment.save_checkpoint("C1", checkpoints["C1"])
    environment.commit_validation_plan(checkpoints["C2"])
    with pytest.raises(V07ProtocolError, match="exactly once"):
        environment.commit_validation_plan(checkpoints["C2"])
    environment.reveal_validation()
    environment.save_checkpoint("C3", checkpoints["C3"])
    environment.save_checkpoint("C4", checkpoints["C4"])
    environment.purchase_resource(selected)
    environment.save_checkpoint("C5", checkpoints["C5"])
    submission = environment.submit()
    assert submission["completion_accepted"]
    assert submission["terminal_reason"] == "submitted"


def test_tampering_hidden_access_and_post_reveal_mutation_are_rejected(
    tmp_path: Path,
) -> None:
    checkpoints, _ = reference_checkpoints(ROOT, "case_02")
    hidden = V07Environment(ROOT, "case_02", tmp_path / "hidden")
    with pytest.raises(V07ProtocolError, match="Private grader data"):
        hidden.read_file("grader_private/hard_suite_v07/case_02/truth.json")

    tampered = V07Environment(ROOT, "case_02", tmp_path / "tampered")
    tampered.save_checkpoint("C1", checkpoints["C1"])
    (tampered.run_root / "sponsor/assertions.md").write_text("changed", encoding="utf-8")
    with pytest.raises(V07ProtocolError, match="modified"):
        tampered.commit_validation_plan(checkpoints["C2"])

    mutation = V07Environment(ROOT, "case_02", tmp_path / "mutation")
    mutation.save_checkpoint("C1", checkpoints["C1"])
    mutation.commit_validation_plan(checkpoints["C2"])
    mutation.reveal_validation()
    with pytest.raises(V07ProtocolError, match="Use commit_validation_plan"):
        mutation.save_checkpoint("C2", {"analysis_unit": "biopsy"})


def test_changing_leakage_replay_mechanism_changes_correct_final_decision() -> None:
    collapse = direct_submission(ROOT, "case_03", mechanism="signal_collapses")
    correct = grade_submission(ROOT, "case_03", collapse, mechanism="signal_collapses")
    counterfactual = grade_submission(ROOT, "case_03", collapse, mechanism="signal_remains")
    assert correct.full_mission_success
    assert not counterfactual.full_mission_success
    assert "unsupported_final_decision" in counterfactual.mission_failures
    assert "belief_revision_incorrect" in counterfactual.mission_failures


def test_metadata_followup_analysis_is_not_free_credit() -> None:
    clean = direct_submission(ROOT, "case_01")
    clean["checkpoints"]["C5"].pop("new_evidence_received")
    assert grade_submission(ROOT, "case_01", clean).checkpoint_scores["C5"] < 100

    dependence = direct_submission(ROOT, "case_02")
    dependence["checkpoints"]["C5"].pop("resolved_patient_count")
    dependence["checkpoints"]["C5"].pop("site_blocker_remaining")
    assert grade_submission(ROOT, "case_02", dependence).checkpoint_scores["C5"] < 90


def test_reference_replay_completes_inside_tool_budget(tmp_path: Path) -> None:
    submission, grade = replay_reference(
        ROOT,
        "case_03",
        tmp_path / "reference",
        mechanism="signal_collapses",
    )
    assert grade.work_quality_score >= 90
    assert grade.full_mission_success
    assert submission["tool_calls"] <= 20


def test_unsubmitted_work_keeps_diagnostic_score_but_zeroes_reliability() -> None:
    submission = direct_submission(ROOT, "case_04")
    submission["completion_accepted"] = False
    result = grade_submission(ROOT, "case_04", submission)
    assert result.work_quality_score >= 90
    assert result.reliability_score == 0
    assert not result.full_mission_success

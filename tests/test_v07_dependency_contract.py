"""Pre-freeze dependency tests for the v0.7 scientific decision chain."""

from __future__ import annotations

from pathlib import Path

import pytest

from uc_bench.hard_suite_v07 import (
    V07Environment,
    V07ProtocolError,
    direct_submission,
    grade_submission,
    reference_checkpoints,
)

ROOT = Path(__file__).resolve().parents[1]


def test_01_correct_final_from_contaminated_analysis_cannot_pass_mission() -> None:
    submission = direct_submission(ROOT, "case_03", mechanism="signal_collapses")
    submission["checkpoints"]["C3"]["contaminated_metrics_used_for_decision"] = True
    result = grade_submission(ROOT, "case_03", submission, mechanism="signal_collapses")
    assert not result.full_mission_success
    assert "contaminated_evidence_used" in result.mission_failures
    assert result.work_quality_score > 50


def test_02_post_reveal_analysis_outside_plan_is_partial_but_not_validation() -> None:
    submission = direct_submission(ROOT, "case_01")
    submission["checkpoints"]["C3"]["uncertainty_matches_commitment"] = False
    result = grade_submission(ROOT, "case_01", submission)
    assert 80 < result.work_quality_score < 100
    assert not result.full_mission_success
    assert "execution_diverged_from_commitment" in result.mission_failures


def test_03_only_the_purchased_resource_is_revealed(tmp_path: Path) -> None:
    checkpoints, _ = reference_checkpoints(ROOT, "case_02")
    environment = V07Environment(ROOT, "case_02", tmp_path / "episode")
    environment.save_checkpoint("C1", checkpoints["C1"])
    environment.commit_validation_plan(checkpoints["C2"])
    environment.reveal_validation()
    environment.save_checkpoint("C3", checkpoints["C3"])
    checkpoints["C4"]["selected_resource"] = "X24"
    environment.save_checkpoint("C4", checkpoints["C4"])
    revealed = environment.purchase_resource("X24")
    assert revealed
    assert all(path.startswith("purchased/X24/") for path in revealed)
    assert not (environment.run_root / "purchased/X17").exists()


def test_04_precommit_correction_recovers_but_plan_cannot_change_after_reveal(
    tmp_path: Path,
) -> None:
    checkpoints, selected = reference_checkpoints(ROOT, "case_01")
    environment = V07Environment(ROOT, "case_01", tmp_path / "episode")
    wrong = dict(checkpoints["C1"], analysis_unit="biopsy")
    environment.save_checkpoint("C1", wrong)
    environment.save_checkpoint("C1", checkpoints["C1"])
    environment.commit_validation_plan(checkpoints["C2"])
    environment.reveal_validation()
    with pytest.raises(V07ProtocolError, match="Use commit_validation_plan"):
        environment.save_checkpoint("C2", dict(checkpoints["C2"], analysis_unit="biopsy"))
    environment.save_checkpoint("C3", checkpoints["C3"])
    environment.save_checkpoint("C4", checkpoints["C4"])
    environment.purchase_resource(selected)
    environment.save_checkpoint("C5", checkpoints["C5"])
    result = grade_submission(ROOT, "case_01", environment.submit())
    assert result.full_mission_success


def test_05_one_final_decision_cannot_pass_both_case_03_returns() -> None:
    submission = direct_submission(ROOT, "case_03", mechanism="signal_collapses")
    collapsed = grade_submission(ROOT, "case_03", submission, mechanism="signal_collapses")
    remains = grade_submission(ROOT, "case_03", submission, mechanism="signal_remains")
    assert collapsed.full_mission_success
    assert not remains.full_mission_success


def test_06_correct_numbers_with_wrong_patient_site_structure_fail_quantitative_gate() -> None:
    submission = direct_submission(ROOT, "case_02")
    submission["checkpoints"]["C3"]["patient_dependence_preserved"] = False
    submission["checkpoints"]["C3"]["site_aware_analysis"] = False
    result = grade_submission(ROOT, "case_02", submission)
    assert result.checkpoint_scores["C3"] < 90
    assert result.work_quality_score > 50
    assert not result.full_mission_success
    assert "analysis_structure_invalid" in result.mission_failures


def test_07_claim_strength_is_bounded_by_weakest_critical_evidence() -> None:
    submission = direct_submission(ROOT, "case_01")
    submission["checkpoints"]["C2"] = {}
    result = grade_submission(ROOT, "case_01", submission)
    assert not result.full_mission_success
    assert (
        "claim_exceeds_weakest_decision_critical_evidence" in result.mission_failures
    )


def test_08_no_resource_and_low_cost_confirmation_both_pass_case_01() -> None:
    no_resource = grade_submission(ROOT, "case_01", direct_submission(ROOT, "case_01"))
    confirmation = grade_submission(
        ROOT, "case_01", direct_submission(ROOT, "case_01", alternative=True)
    )
    assert no_resource.full_mission_success
    assert confirmation.full_mission_success


def test_09_guessed_correct_final_without_evidence_chain_gets_partial_only() -> None:
    submission = direct_submission(ROOT, "case_01")
    for checkpoint in ("C1", "C2", "C3", "C4"):
        submission["checkpoints"][checkpoint] = {}
    result = grade_submission(ROOT, "case_01", submission)
    assert not result.full_mission_success
    assert 0 < result.work_quality_score <= 15


def test_10_missing_submission_changes_reliability_not_scientific_work() -> None:
    complete = direct_submission(ROOT, "case_04")
    unsubmitted = direct_submission(ROOT, "case_04")
    unsubmitted["completion_accepted"] = False
    complete_grade = grade_submission(ROOT, "case_04", complete)
    unsubmitted_grade = grade_submission(ROOT, "case_04", unsubmitted)
    assert unsubmitted_grade.work_quality_score == complete_grade.work_quality_score
    assert unsubmitted_grade.reliability_score == 0
    assert complete_grade.reliability_score == complete_grade.work_quality_score

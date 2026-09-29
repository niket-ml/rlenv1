from __future__ import annotations

import copy
from pathlib import Path

from uc_bench.mmmvp_controls import CONDITIONS, build_mmmvp_reference, run_mmmvp_controls
from uc_bench.mmmvp_schema import TARGET_HYPOTHESIS_ID, validate_mmmvp_checkpoint
from uc_bench.mmmvp_score_sources import validate_score_source_registry
from uc_bench.mmmvp_verifier import verify_mmmvp_submission
from uc_bench.v08_controls import sync_event_digests

ROOT = Path(__file__).resolve().parents[1]


def _reference(tmp_path: Path, condition: str = "case_02"):
    return build_mmmvp_reference(ROOT, condition, tmp_path / condition, alternative=False)


def test_all_references_and_valid_alternatives_pass(tmp_path: Path) -> None:
    for index, condition in enumerate(CONDITIONS):
        for alternative in (False, True):
            submission, workspace = build_mmmvp_reference(
                ROOT,
                condition,
                tmp_path / f"{index}-{alternative}",
                alternative=alternative,
            )
            grade = verify_mmmvp_submission(ROOT, workspace, submission, condition_id=condition)
            assert grade.complete_mission_success, grade.mission_failures


def test_all_thirty_five_controls_pass(tmp_path: Path) -> None:
    result = run_mmmvp_controls(ROOT, tmp_path / "controls")
    assert result["status"] == "passed"
    assert result["control_count"] == 35


def test_clean_and_contaminated_fit_scope_are_distinguished(tmp_path: Path) -> None:
    clean, clean_workspace = _reference(tmp_path, "case_04")
    clean_grade = verify_mmmvp_submission(
        ROOT, clean_workspace, clean, condition_id="case_04"
    )
    assert clean_grade.complete_mission_success
    clean["checkpoints"]["C3"]["preprocessing_and_contamination"][
        "established_contamination"
    ] = True
    clean["checkpoints"]["C3"]["preprocessing_and_contamination"][
        "primary_evidence_eligible"
    ] = False
    sync_event_digests(clean)
    wrong = verify_mmmvp_submission(ROOT, clean_workspace, clean, condition_id="case_04")
    assert "contaminated_evidence_contained" in wrong.mission_failures


def test_belief_target_and_committed_baseline_cannot_be_changed_post_hoc(tmp_path: Path) -> None:
    submission, workspace = _reference(tmp_path)
    submission["checkpoints"]["C5"]["belief_change"]["target_hypothesis_id"] = (
        "SOME_OTHER_TARGET"
    )
    sync_event_digests(submission)
    grade = verify_mmmvp_submission(ROOT, workspace, submission, condition_id="case_02")
    assert "evidence_consistent_belief_change" in grade.mission_failures

    submission, workspace = build_mmmvp_reference(
        ROOT, "case_02", tmp_path / "second", alternative=False
    )
    submission["checkpoints"]["C5"]["belief_change"][
        "support_probability_before"
    ] = 0.8
    sync_event_digests(submission)
    grade = verify_mmmvp_submission(ROOT, workspace, submission, condition_id="case_02")
    assert "evidence_consistent_belief_change" in grade.mission_failures


def test_no_purchase_requires_unchanged_belief(tmp_path: Path) -> None:
    submission, workspace = build_mmmvp_reference(
        ROOT, "case_04", tmp_path / "case4", alternative=False
    )
    selected = next(
        event["resource_id"]
        for event in submission["event_log"]
        if event.get("event") == "purchase_resource"
    )
    if selected != "none":
        return
    belief = submission["checkpoints"]["C5"]["belief_change"]
    belief["support_probability_after"] = belief["support_probability_before"] - 0.1
    sync_event_digests(submission)
    grade = verify_mmmvp_submission(ROOT, workspace, submission, condition_id="case_04")
    assert "evidence_consistent_belief_change" in grade.mission_failures


def test_prose_never_changes_claim_or_decision_score(tmp_path: Path) -> None:
    submission, workspace = _reference(tmp_path)
    baseline = verify_mmmvp_submission(ROOT, workspace, submission, condition_id="case_02")
    mutated = copy.deepcopy(submission)
    decision = mutated["checkpoints"]["C5"]["decision"]
    decision["allowed_use"] = ["Natural language written differently by a specialist."]
    decision["prohibited_use"] = ["Do not deploy this result in care."]
    decision["unresolved_gates"] = ["The external question remains open."]
    decision["required_next_evidence"] = ["A suitably designed independent cohort."]
    mutated["checkpoints"]["C4"]["why_decision_resolving"] = "A defensible paraphrase."
    sync_event_digests(mutated)
    changed = verify_mmmvp_submission(ROOT, workspace, mutated, condition_id="case_02")
    assert changed.complete_mission_success == baseline.complete_mission_success
    assert changed.partial_scientific_quality == baseline.partial_scientific_quality


def test_claim_ids_are_authoritative_even_when_prose_disagrees(tmp_path: Path) -> None:
    submission, workspace = _reference(tmp_path)
    submission["checkpoints"]["C5"]["decision"]["prohibited_use"] = [
        "Everything is safe and proved, written only as prose."
    ]
    sync_event_digests(submission)
    assert verify_mmmvp_submission(
        ROOT, workspace, submission, condition_id="case_02"
    ).complete_mission_success
    submission["checkpoints"]["C5"]["claims"]["prohibited"] = []
    sync_event_digests(submission)
    grade = verify_mmmvp_submission(ROOT, workspace, submission, condition_id="case_02")
    assert "claim_scope" in grade.mission_failures


def test_schema_discloses_target_and_claim_enums(tmp_path: Path) -> None:
    submission, _ = _reference(tmp_path)
    for checkpoint, payload in submission["checkpoints"].items():
        assert validate_mmmvp_checkpoint(checkpoint, payload).valid
    assert (
        submission["checkpoints"]["C4"]["prediction_before_investigation"][
            "target_hypothesis_id"
        ]
        == TARGET_HYPOTHESIS_ID
    )


def test_source_registry_has_no_duplicate_or_prose_paths() -> None:
    assert validate_score_source_registry() == []


def test_success_and_first_failure_are_mutually_exclusive(tmp_path: Path) -> None:
    submission, workspace = _reference(tmp_path)
    grade = verify_mmmvp_submission(ROOT, workspace, submission, condition_id="case_02")
    assert grade.complete_mission_success
    assert grade.first_decision_critical_failure is None

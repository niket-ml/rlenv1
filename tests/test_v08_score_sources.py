from __future__ import annotations

import copy
import inspect
import json
from pathlib import Path

import uc_bench.v08_verifier as verifier_module
from uc_bench.v08_controls import build_reference_solution, sync_event_digests
from uc_bench.v08_score_sources import (
    MISSION_SCORE_SOURCES,
    score_source_for,
    validate_score_source_registry,
)
from uc_bench.v08_verifier import verify_v08_submission

ROOT = Path(__file__).resolve().parents[1]
CASE2_RUN = ROOT / "build/hard_suite_v08_runs/v08-gpt-5.6-sol-case_02-20260909T061848Z"


def _live_case2() -> tuple[dict[str, object], Path]:
    submission = json.loads((CASE2_RUN / "submission.json").read_text(encoding="utf-8"))
    return submission, CASE2_RUN / "workspace"


def _grade_case2(submission: dict[str, object], workspace: Path):
    return verify_v08_submission(
        ROOT,
        workspace,
        submission,
        condition_id="case_02",
    )


def test_exact_live_case2_submission_passes_decision_unchanged() -> None:
    submission, workspace = _live_case2()
    grade = _grade_case2(submission, workspace)
    requirement = next(
        row for row in grade.requirements if row.requirement_id == "explicit_bounded_decision"
    )
    assert requirement.passed
    assert grade.complete_mission_success
    assert grade.partial_scientific_quality == 100


def test_paraphrasing_prohibited_use_cannot_change_score() -> None:
    submission, workspace = _live_case2()
    baseline = _grade_case2(submission, workspace)
    paraphrased = copy.deepcopy(submission)
    paraphrased["checkpoints"]["C5"]["decision"]["prohibited_use"] = [
        "These estimates must not guide an individual patient's treatment.",
        "Do not describe this as an externally validated or clinically useful tool.",
    ]
    sync_event_digests(paraphrased)
    observed = _grade_case2(paraphrased, workspace)
    assert observed.complete_mission_success == baseline.complete_mission_success
    assert observed.partial_scientific_quality == baseline.partial_scientific_quality
    assert observed.mission_failures == baseline.mission_failures


def test_correct_claim_ids_and_natural_professional_prose_pass() -> None:
    submission, workspace = _live_case2()
    fixtures = json.loads(
        (ROOT / "tests/fixtures/v08_naturalistic_decision_language.json").read_text(
            encoding="utf-8"
        )
    )["fixtures"]
    for fixture in fixtures:
        candidate = copy.deepcopy(submission)
        decision = candidate["checkpoints"]["C5"]["decision"]
        for field in (
            "allowed_use",
            "prohibited_use",
            "unresolved_gates",
            "required_next_evidence",
        ):
            decision[field] = fixture[field]
        sync_event_digests(candidate)
        grade = _grade_case2(candidate, workspace)
        assert grade.complete_mission_success, fixture["fixture_id"]
        assert grade.partial_scientific_quality == 100


def test_incorrect_or_missing_claim_ids_fail_despite_expected_words() -> None:
    submission, workspace = _live_case2()
    expected_words = [
        "independent_validation_passed treatment_effect clinical_utility_proven",
        "all_platforms safe_threshold_use research_use_prognostic_validation",
    ]
    for claims in ({"supported": [], "prohibited": [], "asserted": []}, None):
        candidate = copy.deepcopy(submission)
        candidate["checkpoints"]["C5"]["decision"]["prohibited_use"] = expected_words
        if claims is None:
            candidate["checkpoints"]["C5"]["claims"]["prohibited"] = []
        else:
            candidate["checkpoints"]["C5"]["claims"] = claims
        sync_event_digests(candidate)
        grade = _grade_case2(candidate, workspace)
        assert not grade.complete_mission_success
        assert "claim_scope" in grade.mission_failures


def test_private_claim_ids_are_never_required_in_prose() -> None:
    submission, workspace = _live_case2()
    candidate = copy.deepcopy(submission)
    decision = candidate["checkpoints"]["C5"]["decision"]
    decision["allowed_use"] = ["Bounded retrospective scientific work is reasonable."]
    decision["prohibited_use"] = ["Do not use the result to make care decisions."]
    decision["unresolved_gates"] = ["Independent transport remains unresolved."]
    decision["required_next_evidence"] = ["Evaluate new patients at more than one site."]
    sync_event_digests(candidate)
    grade = _grade_case2(candidate, workspace)
    assert grade.complete_mission_success
    prose_lists = [decision[field] for field in decision if isinstance(decision[field], list)]
    all_prose = " ".join(item for values in prose_lists for item in values)
    assert not any(
        claim_id in all_prose
        for claim_id in submission["checkpoints"]["C5"]["claims"]["prohibited"]
    )


def test_every_mission_requirement_has_one_unique_nonprose_source(
    tmp_path: Path,
) -> None:
    assert validate_score_source_registry() == []
    emitted: list[str] = []
    for index, condition in enumerate(
        (
            "case_01",
            "case_02",
            "case_03_signal_collapses",
            "case_03_signal_remains",
            "case_04",
        )
    ):
        submission, workspace = build_reference_solution(
            ROOT,
            condition,
            tmp_path / str(index),
            alternative=False,
        )
        grade = verify_v08_submission(ROOT, workspace, submission, condition_id=condition)
        emitted.extend(
            row.requirement_id
            for row in grade.requirements
            if row.requirement_class == "mission_critical_science"
        )
    assert all(score_source_for(requirement_id) is not None for requirement_id in emitted)
    assert all(row["prose_can_affect_score"] is False for row in MISSION_SCORE_SOURCES)
    assert len({row["concept_id"] for row in MISSION_SCORE_SOURCES}) == len(MISSION_SCORE_SOURCES)


def test_mission_verifier_contains_no_regex_or_prose_matching() -> None:
    source = inspect.getsource(verifier_module.verify_v08_submission)
    assert "re.search" not in source
    assert "re.match" not in source
    assert ".lower()" not in source
    assert 'decision["prohibited_use"]' not in source
    assert 'decision["allowed_use"]' not in source
    assert 'belief["target_hypothesis"]' not in source
    assert 'belief["evidence"]' not in source


def test_mission_status_and_first_failure_are_logically_consistent() -> None:
    submission, workspace = _live_case2()
    passing = _grade_case2(submission, workspace)
    assert passing.complete_mission_success
    assert passing.first_decision_critical_failure is None
    failing = copy.deepcopy(submission)
    failing["checkpoints"]["C5"]["claims"]["prohibited"] = []
    sync_event_digests(failing)
    failed_grade = _grade_case2(failing, workspace)
    assert not failed_grade.complete_mission_success
    assert failed_grade.first_decision_critical_failure is not None
    assert failed_grade.first_decision_critical_failure["requirement_id"] in (
        failed_grade.mission_failures
    )

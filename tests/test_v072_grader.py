from __future__ import annotations

import copy
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from uc_bench.hard_suite_v072 import replay_v072_reference
from uc_bench.v07_environment import V07ProtocolError
from uc_bench.v07_runner import V07RunConfig, v07_scientific_system_prompt
from uc_bench.v072_environment import V072Environment
from uc_bench.v072_grader import grade_v072_submission
from uc_bench.v072_interface import V072_AGENT_CONTRACT, v072_scientific_system_prompt
from uc_bench.v072_schema import SCHEMA_VERSION

ROOT = Path(__file__).resolve().parents[1]


def _digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _sync_event_digests(submission: dict[str, Any]) -> None:
    commit = _digest(submission["checkpoints"]["C2"])
    for event in submission["event_log"]:
        if event.get("event") == "save_checkpoint":
            checkpoint = event["checkpoint"]
            event["digest"] = _digest(submission["checkpoints"][checkpoint])
        elif event.get("event") == "commit_validation_plan":
            event["digest"] = commit
        elif event.get("event") in {"reveal_validation", "submit"}:
            event["committed_plan_hash"] = commit


def _reference(
    tmp_path: Path,
    case_id: str = "case_01",
    mechanism: str = "default",
    *,
    alternative: bool = False,
) -> tuple[dict[str, Any], Path]:
    workspace = tmp_path / f"{case_id}-{mechanism}-{alternative}"
    submission, grade = replay_v072_reference(
        ROOT,
        case_id,
        workspace,
        mechanism=mechanism,
        alternative=alternative,
    )
    assert grade.strict_full_mission_success
    return submission, workspace


def _grade(
    submission: dict[str, Any],
    workspace: Path,
    case_id: str = "case_01",
    mechanism: str = "default",
) -> Any:
    return grade_v072_submission(
        ROOT,
        case_id,
        submission,
        mechanism=mechanism,
        workspace_root=workspace,
    )


def test_reference_and_alternative_valid_workflows_are_high(tmp_path: Path) -> None:
    conditions = [
        ("case_01", "default"),
        ("case_02", "default"),
        ("case_03", "signal_collapses"),
        ("case_03", "signal_remains"),
        ("case_04", "default"),
    ]
    for index, (case_id, mechanism) in enumerate(conditions):
        for alternative in (False, True):
            _, grade = replay_v072_reference(
                ROOT,
                case_id,
                tmp_path / f"reference-{index}-{alternative}",
                mechanism=mechanism,
                alternative=alternative,
            )
            assert grade.scientific_work_quality_score is not None
            assert grade.scientific_work_quality_score >= 90
            assert grade.strict_full_mission_success


def test_flat_nested_reordered_annotated_and_paraphrased_are_equivalent(
    tmp_path: Path,
) -> None:
    submission, workspace = _reference(tmp_path)
    variants = [copy.deepcopy(submission)]

    nested = copy.deepcopy(submission)
    for payload in nested["checkpoints"].values():
        facts = {
            key: payload.pop(key)
            for key in list(payload)
            if key not in {"schema_version", "explanation", "annotations"}
        }
        payload["facts"] = facts
    _sync_event_digests(nested)
    variants.append(nested)

    reordered = json.loads(json.dumps(submission, sort_keys=True))
    _sync_event_digests(reordered)
    variants.append(reordered)

    annotated = copy.deepcopy(submission)
    annotated["checkpoints"]["C5"]["explanation"] = (
        "No advancement is claimed in this annotation; the explicit enum controls."
    )
    _sync_event_digests(annotated)
    variants.append(annotated)

    paraphrased = copy.deepcopy(annotated)
    paraphrased["checkpoints"]["C5"]["explanation"] = (
        "Different professional narrative, identical recorded facts."
    )
    _sync_event_digests(paraphrased)
    variants.append(paraphrased)

    grades = [_grade(value, workspace).to_dict() for value in variants]
    signatures = [
        (
            row["scientific_work_quality_score"],
            row["checkpoint_scores"],
            row["strict_full_mission_success"],
        )
        for row in grades
    ]
    assert all(value == signatures[0] for value in signatures)


def test_nested_sample_counts_and_patient_enum_are_read_without_wording(
    tmp_path: Path,
) -> None:
    submission, workspace = _reference(tmp_path)
    c1 = submission["checkpoints"]["C1"]
    c1["facts"] = {
        "analysis_unit": c1.pop("analysis_unit"),
        "cohort_counts": c1.pop("cohort_counts"),
        "checks": c1.pop("checks"),
        "findings": c1.pop("findings"),
        "remaining_uncertainties": c1.pop("remaining_uncertainties"),
        "evidence_refs": c1.pop("evidence_refs"),
    }
    c1["explanation"] = "This prose says biopsy, but it is not a scored fact."
    _sync_event_digests(submission)
    grade = _grade(submission, workspace)
    assert grade.checkpoint_scores["C1"] == 100


def test_sensitivity_metric_never_substitutes_for_missing_primary(
    tmp_path: Path,
) -> None:
    submission, workspace = _reference(tmp_path)
    c3 = submission["checkpoints"]["C3"]
    c3["sensitivity_metrics"]["auc"] = c3["primary_metrics"].pop("auc")
    _sync_event_digests(submission)
    grade = _grade(submission, workspace)
    numeric = next(
        row
        for row in grade.property_scores["C3"]
        if row["property_id"] == "independent_numeric_reproduction"
    )
    assert numeric["score"] < 100
    assert grade.checkpoint_scores["C3"] < 100
    assert grade.scientific_work_quality_score > 15


def test_structured_belief_and_nested_stop_are_explicit(tmp_path: Path) -> None:
    submission, workspace = _reference(tmp_path, "case_03", "signal_collapses")
    c5 = submission["checkpoints"]["C5"]
    c5["decisions"]["final"] = {"decision": "STOP"}
    c5["belief_update"] = {
        "before": {"probability": 0.8},
        "after": {"probability": 0.1},
        "direction": "LARGE_DECREASE",
    }
    _sync_event_digests(submission)
    grade = _grade(submission, workspace, "case_03", "signal_collapses")
    assert grade.strict_full_mission_success


def test_decision_negation_cannot_become_advance(tmp_path: Path) -> None:
    submission, workspace = _reference(tmp_path)
    submission["checkpoints"]["C5"]["decisions"]["final"] = "STOP"
    submission["checkpoints"]["C5"]["explanation"] = (
        "No advancement. The word ADVANCE appears only inside this negation."
    )
    _sync_event_digests(submission)
    grade = _grade(submission, workspace)
    assert "unsupported_final_decision" in grade.mission_failures


def test_resource_and_timing_are_taken_from_event_record(tmp_path: Path) -> None:
    submission, workspace = _reference(tmp_path)
    submission["checkpoints"]["C4"]["chosen_resource"] = "X46"
    _sync_event_digests(submission)
    grade = _grade(submission, workspace)
    assert grade.event_facts["selected_resource"] == "none"
    assert grade.event_action_disagreements == ["declared_resource_differs_from_purchase_event"]
    assert not grade.strict_full_mission_success


def test_one_missing_field_only_penalizes_its_requirement(tmp_path: Path) -> None:
    submission, workspace = _reference(tmp_path)
    del submission["checkpoints"]["C1"]["cohort_counts"]["patient_count"]
    _sync_event_digests(submission)
    grade = _grade(submission, workspace)
    assert 80 < grade.scientific_work_quality_score < 100
    assert grade.checkpoint_scores["C2"] == 100
    assert grade.checkpoint_scores["C3"] == 100
    assert any(row["path"] == "cohort_counts.patient_count" for row in grade.schema_issues)
    assert grade.first_decision_critical_failure is not None
    assert grade.first_decision_critical_failure["property_id"] == "patient_count"
    assert grade.downstream_consequences
    assert grade.failure_taxonomy["contract_failure"] is True
    assert grade.failure_taxonomy["provider_failure"] is False


def test_conflicting_fields_are_rejected_without_global_cap(tmp_path: Path) -> None:
    submission, workspace = _reference(tmp_path)
    c1 = submission["checkpoints"]["C1"]
    c1["facts"] = {"analysis_unit": {"level": "BIOPSY", "patient_key": "sample_id"}}
    _sync_event_digests(submission)
    grade = _grade(submission, workspace)
    assert any(row["code"] == "conflicting_field" for row in grade.schema_issues)
    assert grade.checkpoint_scores["C1"] < 100
    assert grade.scientific_work_quality_score > 15


def test_invalid_decision_enum_is_not_inferred_from_explanation(tmp_path: Path) -> None:
    submission, workspace = _reference(tmp_path)
    c5 = submission["checkpoints"]["C5"]
    c5["decisions"]["final"] = "no advancement"
    c5["explanation"] = "CONDITIONAL_ADVANCE appears here."
    _sync_event_digests(submission)
    grade = _grade(submission, workspace)
    assert any(row["code"] == "invalid_enum" for row in grade.schema_issues)
    assert "unsupported_final_decision" in grade.mission_failures


def test_unsupported_evidence_reference_loses_only_evidence_credit(
    tmp_path: Path,
) -> None:
    submission, workspace = _reference(tmp_path)
    submission["checkpoints"]["C4"]["evidence_refs"]["diagnosis"] = ["sponsor/assertions.md"]
    _sync_event_digests(submission)
    grade = _grade(submission, workspace)
    evidence = next(
        row
        for row in grade.property_scores["C4"]
        if row["property_id"] == "diagnosis_evidence_trace"
    )
    assert evidence["score"] == 0
    assert grade.evidence_support["C4.diagnosis"]["supported"] is False
    assert grade.checkpoint_scores["C4"] == 90


def test_three_episode_outputs_and_infrastructure_exclusion(tmp_path: Path) -> None:
    submission, workspace = _reference(tmp_path)
    valid = _grade(submission, workspace).to_dict()
    assert valid["scientific_work_quality_score"] == 100
    assert valid["strict_full_mission_success"] is True
    assert valid["environment_reliability_status"]["status"] == "valid_episode"

    infrastructure = grade_v072_submission(
        ROOT,
        "case_01",
        submission,
        workspace_root=workspace,
        execution_classification="infrastructure_failure",
    ).to_dict()
    assert infrastructure["scientific_work_quality_score"] is None
    assert infrastructure["strict_full_mission_success"] is None
    assert infrastructure["reliability_score"] is None
    assert infrastructure["environment_reliability_status"]["status"] == ("infrastructure_failure")
    assert infrastructure["failure_taxonomy"]["infrastructure_failure"] is True
    assert infrastructure["failure_taxonomy"]["scientific_failure"] is False


def test_usable_unsubmitted_attempt_keeps_science_and_zeroes_reliability(
    tmp_path: Path,
) -> None:
    submission, workspace = _reference(tmp_path)
    submission["event_log"] = [row for row in submission["event_log"] if row["event"] != "submit"]
    grade = _grade(submission, workspace)
    assert grade.scientific_work_quality_score == 100
    assert grade.reliability_score == 0
    assert grade.environment_reliability_status["status"] == "usable_unsubmitted_attempt"
    assert grade.failure_taxonomy["model_completion_failure"] is True
    assert grade.failure_taxonomy["infrastructure_failure"] is False
    assert not grade.strict_full_mission_success


def test_saved_artifacts_are_required_and_independently_recomputed(tmp_path: Path) -> None:
    submission, workspace = _reference(tmp_path)
    no_artifact = copy.deepcopy(submission)
    no_artifact["checkpoints"]["C3"]["artifact_manifest"]["patient_table_path"] = (
        "work/not-there.csv"
    )
    _sync_event_digests(no_artifact)
    grade = _grade(no_artifact, workspace)
    assert grade.checkpoint_scores["C3"] <= 30
    assert "underlying_artifacts_not_verified" in grade.mission_failures

    altered = copy.deepcopy(submission)
    prediction_path = workspace / "data/locked_predictions.csv"
    rows = list(csv.DictReader(prediction_path.read_text(encoding="utf-8").splitlines()))
    rows[0]["predicted_probability"] = str(1 - float(rows[0]["predicted_probability"]))
    with prediction_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    altered_grade = _grade(altered, workspace)
    assert altered_grade.artifact_verification["validation"]["usable"] is False
    assert not altered_grade.strict_full_mission_success


def test_hard_coded_expected_values_and_fixed_decision_fail_on_altered_input(
    tmp_path: Path,
) -> None:
    submission, workspace = _reference(tmp_path)
    label_path = workspace / "revealed/validation_outcomes.csv"
    rows = list(csv.DictReader(label_path.read_text(encoding="utf-8").splitlines()))
    for row in rows[:20]:
        row["week6_response"] = str(1 - int(row["week6_response"]))
    with label_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    grade = _grade(submission, workspace)
    assert grade.checkpoint_scores["C3"] <= 30
    assert not grade.strict_full_mission_success


def _blank_submission(final: str = "PAUSE") -> dict[str, Any]:
    checkpoints = {
        checkpoint: {"schema_version": SCHEMA_VERSION}
        for checkpoint in ("C1", "C2", "C3", "C4", "C5")
    }
    checkpoints["C5"]["decisions"] = {"initial": final, "final": final}
    return {
        "checkpoints": checkpoints,
        "event_log": [
            {"sequence": 1, "event": "reset"},
            {"sequence": 2, "event": "submit", "committed_plan_hash": "guessed"},
        ],
    }


def test_generic_keyword_and_guessed_final_controls_remain_low() -> None:
    for case_id in ("case_01", "case_02", "case_03", "case_04"):
        mechanism = "signal_collapses" if case_id == "case_03" else "default"
        generic = _blank_submission("STOP")
        generic["checkpoints"]["C1"]["findings"] = {
            "diagnosed_concepts": [
                "patient_dependence",
                "site_confounding",
                "validation_information_leakage",
                "miscalibration",
            ]
        }
        grade = grade_v072_submission(ROOT, case_id, generic, mechanism=mechanism)
        assert grade.scientific_work_quality_score <= 20
        assert not grade.strict_full_mission_success


def test_universal_decision_policies_never_pass_all_cases(tmp_path: Path) -> None:
    conditions = [
        ("case_01", "default"),
        ("case_02", "default"),
        ("case_03", "signal_collapses"),
        ("case_03", "signal_remains"),
        ("case_04", "default"),
    ]
    for decision in ("ADVANCE", "PAUSE", "STOP", "INSUFFICIENT_EVIDENCE"):
        passes = 0
        for index, (case_id, mechanism) in enumerate(conditions):
            submission, workspace = _reference(tmp_path / f"{decision}-{index}", case_id, mechanism)
            submission["checkpoints"]["C5"]["decisions"]["final"] = decision
            _sync_event_digests(submission)
            passes += int(
                _grade(submission, workspace, case_id, mechanism).strict_full_mission_success
            )
        assert passes < len(conditions)


def test_graceful_recovery_keeps_later_artifact_credit(tmp_path: Path) -> None:
    submission, workspace = _reference(tmp_path, "case_02")
    submission["checkpoints"]["C1"]["analysis_unit"] = {
        "level": "BIOPSY",
        "patient_key": "sample_id",
    }
    _sync_event_digests(submission)
    grade = _grade(submission, workspace, "case_02")
    assert grade.checkpoint_scores["C1"] < 90
    assert grade.checkpoint_scores["C3"] == 100
    assert grade.checkpoint_scores["C5"] == 100
    assert grade.scientific_work_quality_score >= 90


def test_hidden_grader_boundary_and_agent_visible_contract(tmp_path: Path) -> None:
    environment = V072Environment(ROOT, "case_01", tmp_path / "boundary")
    with pytest.raises(V07ProtocolError, match="Private grader data"):
        environment.read_file("grader_private/hard_suite_v07/case_01/truth.json")
    assert not (environment.run_root / "grader_private").exists()
    config = V07RunConfig("openai/gpt-5.6-sol", "test", "case_01", "default", 70701)
    task_text = "unchanged task"
    original = v07_scientific_system_prompt(task_text, config)
    repaired = v072_scientific_system_prompt(task_text, config)
    assert repaired.startswith(original)
    assert V072_AGENT_CONTRACT in repaired
    for requirement in (
        "patient_table_path",
        "preprocessing_fit_path",
        "calculated_outputs_path",
        "patient_key, site, probability, outcome, split, sample_ids",
        "validation_information_leakage",
        "research_use_prognostic_validation",
        "data/cohort_metadata.csv and data/endpoint_source_ledger.csv",
        "pipeline/preprocess.py, pipeline/fit_membership.csv",
        "never used to infer",
    ):
        assert requirement in repaired

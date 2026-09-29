from __future__ import annotations

import csv
import hashlib
import json
import shutil
from pathlib import Path

from uc_bench.v08_verifier import (
    replay_archived_v072,
    validate_belief_change,
    validate_decision_object,
)

ROOT = Path(__file__).resolve().parents[1]
RUNS = {
    "case_01": ROOT
    / "build/hard_suite_v072_runs/v072-gpt-5.6-sol-case_01-20260909T043338Z",
    "case_03_signal_collapses": ROOT
    / "build/hard_suite_v072_runs/v072-gpt-5.6-sol-case_03_signal_collapses-20260909T043741Z",
}


def _copy_run(tmp_path: Path, condition: str) -> Path:
    target = tmp_path / condition
    shutil.copytree(RUNS[condition], target)
    return target


def test_two_archived_trajectories_replay_as_complete_missions() -> None:
    for condition, run in RUNS.items():
        grade = replay_archived_v072(ROOT, run, condition_id=condition)
        assert grade.complete_mission_success
        assert grade.partial_scientific_quality == 100
        assert grade.reliability_score == 100
        assert grade.first_decision_critical_failure is None
        assert not grade.mission_failures


def test_every_primary_and_followup_calculation_is_scored_independently() -> None:
    grade = replay_archived_v072(ROOT, RUNS["case_01"], condition_id="case_01")
    assert set(grade.calculation_checks["primary"]) == {
        "auc",
        "auc_ci_low",
        "brier",
        "ece",
        "net_benefit",
    }
    assert all(row["passed"] for row in grade.calculation_checks["primary"].values())
    assert all(row["passed"] for row in grade.calculation_checks["followup"].values())


def test_optional_sensitivity_cannot_invalidate_primary_results(tmp_path: Path) -> None:
    run = _copy_run(tmp_path, "case_01")
    path = run / "workspace/work/calculated_outputs.json"
    calculated = json.loads(path.read_text(encoding="utf-8"))
    calculated["sensitivity_metrics"]["site_weighted_auc"] = 0.0
    path.write_text(json.dumps(calculated, indent=2) + "\n", encoding="utf-8")
    grade = replay_archived_v072(ROOT, run, condition_id="case_01")
    assert grade.complete_mission_success
    assert grade.partial_scientific_quality == 100
    assert all(row["passed"] for row in grade.calculation_checks["primary"].values())
    assert not grade.diagnostic_information["optional_sensitivity_checks"][
        "site_weighted_auc"
    ]["passed"]


def test_wrong_saved_primary_value_fails_only_its_own_calculation(tmp_path: Path) -> None:
    run = _copy_run(tmp_path, "case_01")
    path = run / "workspace/work/calculated_outputs.json"
    calculated = json.loads(path.read_text(encoding="utf-8"))
    calculated["primary_metrics"]["auc"] = 0.5
    path.write_text(json.dumps(calculated, indent=2) + "\n", encoding="utf-8")
    grade = replay_archived_v072(ROOT, run, condition_id="case_01")
    assert not grade.complete_mission_success
    assert grade.first_decision_critical_failure is not None
    assert grade.first_decision_critical_failure["requirement_id"] == (
        "primary_calculation:auc"
    )
    assert not grade.calculation_checks["primary"]["auc"]["passed"]
    assert all(
        row["passed"]
        for metric, row in grade.calculation_checks["primary"].items()
        if metric != "auc"
    )
    assert grade.partial_scientific_quality > 95


def test_altered_outcomes_defeat_saved_values_and_fixed_decision(tmp_path: Path) -> None:
    run = _copy_run(tmp_path, "case_03_signal_collapses")
    path = run / "workspace/revealed/validation_outcomes.csv"
    rows = list(csv.DictReader(path.read_text(encoding="utf-8").splitlines()))
    for row in rows[:20]:
        row["week6_response"] = str(1 - int(row["week6_response"]))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    grade = replay_archived_v072(
        ROOT, run, condition_id="case_03_signal_collapses"
    )
    assert not grade.complete_mission_success
    assert any(
        not row["passed"] for row in grade.calculation_checks["primary"].values()
    )
    assert any(
        not row["passed"] for row in grade.calculation_checks["followup"].values()
    )


def test_saved_followup_calculation_survives_omission_from_summary(tmp_path: Path) -> None:
    run = _copy_run(tmp_path, "case_03_signal_collapses")
    submission_path = run / "submission.json"
    submission = json.loads(submission_path.read_text(encoding="utf-8"))
    del submission["checkpoints"]["C5"]["investigation_analysis"]["calculated_values"][
        "brier"
    ]
    final_c5 = submission["checkpoints"]["C5"]
    for event in submission["event_log"]:
        if event.get("event") == "save_checkpoint" and event.get("checkpoint") == "C5":
            event["digest"] = hashlib.sha256(
                json.dumps(final_c5, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
    submission_path.write_text(json.dumps(submission, indent=2) + "\n", encoding="utf-8")
    grade = replay_archived_v072(
        ROOT, run, condition_id="case_03_signal_collapses"
    )
    assert grade.complete_mission_success
    assert grade.calculation_checks["followup"]["brier"]["passed"]
    assert grade.calculation_checks["followup"]["brier"]["reported_value"] is None
    assert grade.calculation_checks["followup"]["brier"][
        "saved_calculation_value"
    ] is not None
    assert grade.calculation_checks["followup"]["auc"]["passed"]


def test_followup_recomputation_uses_committed_ece_bins() -> None:
    for condition, run in RUNS.items():
        grade = replay_archived_v072(ROOT, run, condition_id=condition)
        assert grade.diagnostic_information["followup_recomputation"][
            "ece_bins_from_committed_plan"
        ] == 10
        assert grade.calculation_checks["followup"]["ece"]["passed"]


def test_latest_schema_valid_save_is_authoritative() -> None:
    grade = replay_archived_v072(ROOT, RUNS["case_01"], condition_id="case_01")
    assert grade.event_facts["rejected_save_count"] == 1
    assert grade.event_facts["rejected_save_sequences"] == [33]
    assert grade.event_facts["latest_schema_valid_saves"]["C5"] == 34
    assert grade.event_facts["latest_valid_payload_digests_match"]
    assert grade.reliability_score == 100


def test_numeric_belief_and_explicit_decision_contracts() -> None:
    belief = {
        "target_hypothesis": "bounded predictor validity",
        "support_probability_before": 0.4,
        "support_probability_after": 0.7,
        "evidence": ["replay_predictions.csv"],
    }
    decision = {
        "development_stage": "EXTERNAL_VALIDATION",
        "disposition": "CONTINUE",
        "allowed_use": ["research validation"],
        "unresolved_gates": ["prospective utility"],
        "prohibited_use": ["clinical deployment"],
        "required_next_evidence": ["independent site"],
    }
    assert validate_belief_change(belief) == []
    assert validate_decision_object(decision) == []
    assert validate_belief_change({})
    assert validate_decision_object({})


def test_success_and_critical_failure_are_mutually_exclusive() -> None:
    for condition, run in RUNS.items():
        grade = replay_archived_v072(ROOT, run, condition_id=condition)
        assert not (
            grade.complete_mission_success
            and grade.first_decision_critical_failure is not None
        )

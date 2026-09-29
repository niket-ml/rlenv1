from __future__ import annotations

from uc_bench.mmmvp_runner import grader_consistency


def test_grader_consistency_rejects_logical_contradiction() -> None:
    grade = {
        "complete_mission_success": True,
        "first_decision_critical_failure": {"requirement_id": "x"},
        "mission_failures": [],
        "requirements": [],
        "explicit_decision_object": {},
        "numeric_belief_change": {},
        "diagnostic_information": {"final_verifier_corrections": {"prose_scored": False}},
    }
    result = grader_consistency({"checkpoints": {"C5": {}}}, grade)
    assert not result["passed"]
    assert "mission_success_coexists_with_critical_failure" in result["faults"]

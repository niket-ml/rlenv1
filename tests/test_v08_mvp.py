from __future__ import annotations

import json
from pathlib import Path

import pytest

from uc_bench.v08_controls import (
    CONDITIONS,
    build_reference_solution,
    run_v08_mvp_controls,
    sync_event_digests,
)
from uc_bench.v08_verifier import (
    load_v08_mvp,
    replay_archived_v071,
    verify_v08_submission,
)

ROOT = Path(__file__).resolve().parents[1]
REPLAYS = ROOT / "artifacts/diagnostics/hard_suite_v072_replay_fixtures"


@pytest.fixture(scope="module")
def controls(tmp_path_factory: pytest.TempPathFactory) -> dict[str, object]:
    return run_v08_mvp_controls(ROOT, tmp_path_factory.mktemp("v08-controls"))


def test_active_mvp_is_exactly_four_packets_and_five_conditions() -> None:
    mvp = load_v08_mvp(ROOT)
    assert mvp["status"] == "unfrozen_local_validation"
    assert mvp["environment_count"] == 1
    assert mvp["case_packet_count"] == 4
    assert [row["condition_id"] for row in mvp["active_conditions"]] == list(CONDITIONS)
    assert mvp["paid_calls_authorized"] is True
    assert mvp["paid_authorization_scope"]["conditions"] == [
        "case_02",
        "case_03_signal_remains",
        "case_04",
    ]
    assert mvp["paid_authorization_scope"]["maximum_incremental_spend_usd"] == 8.0
    assert mvp["release_candidate_freeze_authorized"] is False


def test_eight_case_portfolio_is_roadmap_only() -> None:
    portfolio = json.loads(
        (ROOT / "configs/hard_suite_v08_case_portfolio.json").read_text(encoding="utf-8")
    )
    assert portfolio["active_mvp"] is False
    assert portfolio["status"] == "post_mvp_roadmap_only_implementation_not_authorized"


def test_all_five_legacy_replays_match_manual_scientific_adjudication() -> None:
    manual = json.loads(
        (ROOT / "configs/hard_suite_v08_manual_adjudication.json").read_text(encoding="utf-8")
    )
    expected = {row["condition_id"]: row for row in manual["adjudications"]}
    for condition_id in CONDITIONS:
        grade = replay_archived_v071(ROOT, REPLAYS / condition_id, condition_id=condition_id)
        row = expected[condition_id]
        assert grade.complete_mission_success is row["expected_complete_mission"]
        assert set(grade.mission_failures) == set(row["expected_mission_failures"])
        assert not (
            grade.complete_mission_success and grade.first_decision_critical_failure is not None
        )


def test_every_local_control_has_expected_mission_status(
    controls: dict[str, object],
) -> None:
    assert controls["status"] == "passed"
    checks = controls["checks"]
    assert isinstance(checks, dict)
    assert all(checks.values())
    assert controls["condition_count"] == 5
    assert controls["control_count"] == 35


def test_reported_number_is_diagnostic_when_saved_artifact_is_correct(
    tmp_path: Path,
) -> None:
    submission, workspace = build_reference_solution(
        ROOT, "case_04", tmp_path / "case-04", alternative=False
    )
    submission["checkpoints"]["C3"]["primary_metrics"]["brier"] = 0.10
    sync_event_digests(submission)
    grade = verify_v08_submission(ROOT, workspace, submission, condition_id="case_04")
    assert grade.complete_mission_success
    assert grade.partial_scientific_quality == 100
    assert grade.calculation_checks["primary"]["brier"]["passed"]
    assert not grade.diagnostic_information["reported_primary_matches_saved"]["brier"]


def test_optional_diagnostic_failures_never_reduce_mission_quality(
    controls: dict[str, object],
) -> None:
    rows = controls["rows"]
    assert isinstance(rows, list)
    optional = [row for row in rows if row["control"] == "incorrect_optional_diagnostic"]
    assert len(optional) == 5
    assert all(row["complete_mission_success"] for row in optional)
    assert all(row["partial_scientific_quality"] == 100 for row in optional)


def test_mission_requirements_exclude_arbitrary_contract_checks(
    controls: dict[str, object],
) -> None:
    inventory = controls["mission_requirement_inventory"]
    assert isinstance(inventory, dict)
    assert inventory
    forbidden_fragments = {"filename", "prose", "presentation", "schema_vocabulary"}
    assert not any(
        fragment in requirement_id
        for requirement_id in inventory
        for fragment in forbidden_fragments
    )
    assert all(
        row["professional_consequence"] and row["actionable_remedy"] for row in inventory.values()
    )

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from uc_bench.case1_pilot_v1_rc6_lifecycle import transient_failure
from uc_bench.case1_pilot_v1_rc6_release import read_rc6_freeze
from uc_bench.case2_pilot_v1_infrastructure import adjudicate_archived_provider_cell

ROOT = Path(__file__).resolve().parents[1]
RC16_RUNS = ROOT / "build/uc_bench_mmmvp_open_rc14_runs"


def _json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_case1_rc6_is_still_immutable_and_accepted() -> None:
    freeze = read_rc6_freeze(ROOT)
    assert freeze["release_id"] == "uc-bench-case1-pilot-v1-rc6"
    assert freeze["closure"]["aggregate_digest"] == (
        "a1795f1be20b02bb02d86516a664a3d62aed7d6ca716bdd45cb277b4c1ea6d19"
    )


def test_case2_scientific_sources_match_the_audited_bytes() -> None:
    expected = {
        "tasks/hard_suite_v07/development/case_02/README.md": (
            "0e6d270493e05a63ffb2320c61341f0ac14b45fd6bda39d1d4078bd367dc7ea8"
        ),
        "tasks/hard_suite_v07/development/case_02/intended_use.json": (
            "fc4762e0b57a2c4139fd0854a14cb006499fd2d5d0811dfe64e556ac144f246a"
        ),
        "tasks/hard_suite_v07/development/case_02/data/cohort_metadata.csv": (
            "b6e3188ca371f2a03080d08567639b5798cc906ea840cf13662835e985ff2bf6"
        ),
        "tasks/hard_suite_v07/development/case_02/data/locked_predictions.csv": (
            "03f37d2f25f9ebc9b47738ace40db72e64e0a3012657860cc1f7d909f5a8b829"
        ),
        "grader_private/hard_suite_v07/case_02/truth.json": (
            "5a07ac1383cdbfb2387fa4f184d6d70f282dda7e0fd59b33280de007e0efcfbd"
        ),
        "grader_private/hard_suite_v07/case_02/sealed/validation_outcomes.csv": (
            "e9eecabb30081073b0c33694719f3d4c8639d5b6e7b8bd356f73afa714750cef"
        ),
        "grader_private/mmmvp_open_rc1/case_02/X17/canonical_person_crosswalk.csv": (
            "780812d20698c84fdc423939e7967be3577669cf2687e8212a1f3954305d6a63"
        ),
    }
    assert {relative: _sha(ROOT / relative) for relative in expected} == expected


def test_v08_sol_replay_is_reusable_scientific_tractability_evidence() -> None:
    replay = _json(ROOT / "artifacts/diagnostics/hard_suite_v08_case2_development_replay.json")
    assert replay["api_requests"] == 0
    assert replay["raw_historical_result"]["partial_scientific_quality"] == 95.0
    assert replay["raw_historical_result"]["complete_mission_success"] is False
    repaired = replay["repaired_development_replay"]
    assert repaired["partial_scientific_quality"] == 100.0
    assert repaired["complete_mission_success"] is True
    assert repaired["first_decision_critical_failure"] is None


def test_rc15_scalar_grader_crash_is_not_a_model_score() -> None:
    run = RC16_RUNS / ("open-mmmvp-rc15-sentinel-00-google-gemini-3.1-pro-preview-case-02-atte")
    archived = _json(run / "run_summary.json")
    assert _sha(run / "run_summary.json") == (
        "a88ce2a87e77e0f2222f435c36903540357ae4463c4084bd8306515e4d98231d"
    )
    assert archived["complete_mission_success"] is None
    rc16 = _json(ROOT / "artifacts/mmmvp_open_rc16/gemini_regression.json")
    assert rc16["api_requests"] == 0
    assert rc16["partial_scientific_quality"] == 40.0
    assert rc16["strict_mission_success"] is False


def test_rc16_gradeable_case2_runs_remain_diagnostic_not_a_ranking() -> None:
    result = _json(ROOT / "artifacts/mmmvp_open_rc16/sentinel_analysis.json")
    rows = {
        row["model_id"]: row
        for row in result["models"]
        if row.get("classification") == "valid_episode"
    }
    assert {
        model: (row["partial_scientific_quality"], row["reliability_score"])
        for model, row in rows.items()
    } == {
        "anthropic/claude-sonnet-4": (40.0, 100.0),
        "openai/gpt-5": (20.0, 100.0),
        "anthropic/claude-opus-4.1": (30.0, 100.0),
        "google/gemini-3.1-pro-preview": (20.0, 100.0),
        "mistralai/mistral-large-2512": (20.0, 100.0),
    }
    assert all(row["strict_mission_success"] is False for row in rows.values())


def test_exact_rc16_provider_failures_are_cell_local_and_unscored() -> None:
    cases = (
        (
            "open-mmmvp-rc16-sentinel-05-qwen-qwen3.5-397b-a17b-case-02-attempt-0",
            "qwen/qwen3.5-397b-a17b",
            "qwen/qwen3.5-397b-a17b",
            "DeepInfra",
        ),
        (
            "open-mmmvp-rc16-sentinel-06-deepseek-deepseek-v3.2-case-02-attempt-0",
            "deepseek/deepseek-v3.2",
            "deepseek/deepseek-v3.2-20251201",
            "StreamLake",
        ),
    )
    for directory, model, alias, provider in cases:
        ledger = _json(RC16_RUNS / directory / "request_ledger.json")
        result = adjudicate_archived_provider_cell(
            ledger=ledger,
            requested_model=model,
            canonical_alias=alias,
            pinned_provider=provider,
        )
        assert result["classification"] == "isolated_provider_failure"
        assert result["matrix_stop_level"] == "cell_exclusion_continue_panel"
        assert result["scientific_score"] is None
        assert result["reliability"] is None
        assert result["identity_compatible"] is True
        assert result["exception_subtype_evidence"] == "legacy_incomplete"


def test_new_lifecycle_recognizes_the_documented_deepseek_exception_chain() -> None:
    class APIConnectionError(RuntimeError):
        pass

    class ReadError(RuntimeError):
        pass

    outer = APIConnectionError("Connection error.")
    inner = ReadError("peer closed")
    outer.__cause__ = inner
    assert transient_failure(outer)


def test_original_false_tamper_incident_is_not_scientific_evidence() -> None:
    incident = _json(ROOT / "artifacts/mmmvp_open_release/sentinel_incident.json")
    assert incident["sentinel"]["condition_id"] == "case_02"
    assert incident["sentinel"]["scientific_grade_produced"] is False
    assert incident["first_failure"]["actual_files_added"] == ["commit_vp.json"]
    assert incident["first_failure"]["supplied_files_modified"] == []
    assert incident["failure_separation"]["scientific_failure"] == []


def test_case2_controls_show_alternatives_antigaming_and_partial_credit() -> None:
    audit = _json(ROOT / "artifacts/mmmvp_open_rc1/open_endedness_audit.json")
    rows = {
        row["control"]: row
        for row in audit["controls"]["results"]
        if row["condition_id"] == "case_02"
    }
    for name in (
        "correct_reference",
        "different_valid_workflow",
        "justified_abstention",
        "accepted_transport_question",
    ):
        assert rows[name]["complete_mission_success"] is True
    for name in (
        "unsupported_confident_action",
        "hard_coded_values_on_altered_input",
        "correct_number_wrong_source_table",
        "row_independent_analysis",
        "method_label_without_grouping",
    ):
        assert rows[name]["complete_mission_success"] is False
    partial = rows["recoverable_partial_credit"]
    assert partial["complete_mission_success"] is False
    assert 0 < partial["partial_scientific_quality"] < 100


def test_case2_context_decision_rule_is_not_yet_publicly_determined() -> None:
    intended = _json(ROOT / "tasks/hard_suite_v07/development/case_02/intended_use.json")
    truth = _json(ROOT / "grader_private/hard_suite_v07/case_02/truth.json")
    public_gates = set(intended["advance_criteria"])
    assert not {"site_auc_minimum", "site_weighted_auc_minimum", "worst_site_auc_minimum"} & (
        public_gates
    )
    assert "site_confounding" in truth["required_concepts"]
    assert set(truth["final_decisions"]) == {"pause", "insufficient_evidence"}


def test_case1_identity_declaration_cannot_be_copied_into_case2() -> None:
    metadata_path = ROOT / "tasks/hard_suite_v07/development/case_02/data/cohort_metadata.csv"
    metadata = metadata_path.read_text(encoding="utf-8")
    rows = [line.split(",") for line in metadata.splitlines()]
    header = rows[0]
    patient = header.index("reported_patient_id")
    fingerprint = header.index("fingerprint_cluster")
    pairs = {(row[patient], row[fingerprint]) for row in rows[1:]}
    assert ("P0017", "F0017") in pairs
    assert ("P0017", "F0018") in pairs
    assert len({row[fingerprint] for row in rows[1:]}) == 96
    assert len({row[patient] for row in rows[1:]}) == 95

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from uc_bench.case1_pilot_v1_rc5_controls import (
    _copy_episode,
    _replace_final,
    build_reference,
)
from uc_bench.case1_pilot_v1_rc5_verifier import verify_case1_rc5_submission
from uc_bench.case1_pilot_v1_rc6_lifecycle import (
    RequestLifecycleMachine,
    forensic_legacy_request_adjudication,
    lifecycle_identity,
    matrix_stop_level,
    transient_failure,
)
from uc_bench.case1_pilot_v1_rc6_runner import finalize_rc6_run_summary
from uc_bench.case1_pilot_v1_rc6_verifier import verify_case1_rc6_submission
from uc_bench.hashing import canonical_sha256

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "artifacts/uc_bench_case1_pilot_v1_rc5/science/runs"
GPT = RUNS / "case1-rc5-00-openai-gpt-5-attempt-0"
SONNET = RUNS / "case1-rc5-01-anthropic-claude-sonnet-4-attempt-0"
OPUS = RUNS / "case1-rc5-02-anthropic-claude-opus-4.1-attempt-0"


def _submission(run: Path) -> dict[str, object]:
    return json.loads((run / "submission.json").read_text(encoding="utf-8"))


def test_archived_gpt_and_sonnet_regrade_fairly_without_mutation() -> None:
    before = {
        path.relative_to(SONNET).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in SONNET.rglob("*")
        if path.is_file()
    }
    gpt = verify_case1_rc6_submission(ROOT, GPT / "workspace", _submission(GPT)).to_dict()
    sonnet = verify_case1_rc6_submission(
        ROOT, SONNET / "workspace", _submission(SONNET)
    ).to_dict()
    after = {
        path.relative_to(SONNET).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in SONNET.rglob("*")
        if path.is_file()
    }
    assert (gpt["partial_scientific_quality"], gpt["complete_mission_success"]) == (
        100.0,
        True,
    )
    assert (
        sonnet["partial_scientific_quality"],
        sonnet["complete_mission_success"],
    ) == (37.0, False)
    assert sonnet["diagnostics"]["resource_semantics"]["question_relevant"] is True
    assert sonnet["diagnostics"]["resource_semantics"]["declared_material_correct"] is False
    assert sonnet["diagnostics"]["public_hidden_resource_semantics_equal"] is True
    assert before == after


def test_score_inert_relevance_repair_and_score_bearing_material_repair(tmp_path: Path) -> None:
    submission = _submission(SONNET)
    rc5 = verify_case1_rc5_submission(
        ROOT, SONNET / "workspace", submission
    ).to_dict()
    rc6 = verify_case1_rc6_submission(
        ROOT, SONNET / "workspace", submission
    ).to_dict()
    assert rc5["diagnostics"]["resource"]["relevant"] is False
    assert rc6["diagnostics"]["resource"]["relevant"] is True
    assert rc5["partial_scientific_quality"] == rc6["partial_scientific_quality"] == 37.0

    copied, workspace = _copy_episode(submission, SONNET / "workspace", tmp_path / "material")
    final = copy.deepcopy(copied["final_submission"])
    final["resource_assessment"]["material"] = True
    _replace_final(copied, workspace, final)
    repaired = verify_case1_rc6_submission(ROOT, workspace, copied).to_dict()
    assert repaired["partial_scientific_quality"] == 47.0
    changed = {
        key
        for key, points in repaired["diagnostics"]["property_points"].items()
        if points != rc6["diagnostics"]["property_points"][key]
    }
    assert changed == {"decision_relevant_followup"}
    assert repaired["complete_mission_success"] is False


@pytest.mark.parametrize("resource", ["none", "X17", "X24", "X31", "X46", "X58", "X63"])
def test_public_and_hidden_resource_semantics_are_identical(
    tmp_path: Path, resource: str
) -> None:
    submission, workspace = build_reference(ROOT, tmp_path / resource, resource=resource)
    grade = verify_case1_rc6_submission(ROOT, workspace, submission).to_dict()
    facts = grade["diagnostics"]["resource_semantics"]
    hidden = grade["diagnostics"]["resource"]
    assert grade["diagnostics"]["public_hidden_resource_semantics_equal"] is True
    assert hidden["relevant"] == facts["question_relevant"]
    assert hidden["material"] == facts["expected_material"]
    assert hidden["observed_effect"] == facts["expected_effect"]


def test_x24_relevance_does_not_depend_on_broken_primary_output_links() -> None:
    submission = _submission(SONNET)
    facts = verify_case1_rc6_submission(
        ROOT, SONNET / "workspace", submission
    ).to_dict()["diagnostics"]["resource_semantics"]
    assert facts["question_relevant"] is True
    assert facts["expected_material"] is True
    assert facts["returned_result_correct"] is True


def test_archived_opus_is_timeout_not_identity_failure() -> None:
    ledger = json.loads((OPUS / "request_ledger.json").read_text(encoding="utf-8"))
    result = forensic_legacy_request_adjudication(
        ledger_rows=ledger["requests"],
        requested_model="anthropic/claude-opus-4.1",
        canonical_alias="anthropic/claude-4.1-opus-20250805",
        pinned_provider="Amazon Bedrock",
    )
    assert result == {
        "attempted_request_count": 48,
        "completed_response_count": 47,
        "identity_evidence_count": 47,
        "identity_compatible": True,
        "identity_faults": [],
        "terminal_state": "transient_transport_failure",
        "classification": "isolated_provider_timeout",
        "scientific_score": None,
        "reliability": None,
    }
    before = json.loads((OPUS / "host_trajectory/journal/000141.json").read_text())
    after = json.loads((OPUS / "host_trajectory/journal/000142.json").read_text())
    assert before["environment"] == after["environment"]
    assert before["tool_actions"] == after["tool_actions"]
    assert before["pending_tool_calls"] == after["pending_tool_calls"]


def test_full_exception_chain_recognizes_observed_timeout() -> None:
    class ModelError(RuntimeError):
        pass

    class APITimeoutError(RuntimeError):
        pass

    outer = ModelError("ModelError")
    timeout = APITimeoutError("Request timed out.")
    timeout.__cause__ = TimeoutError()
    outer.__cause__ = timeout
    assert transient_failure(outer)


def test_lifecycle_retry_and_restart_are_exact(tmp_path: Path) -> None:
    machine = RequestLifecycleMachine(tmp_path / "lifecycle.json", secret="fixture-secret")
    body = {"model": "m", "messages": [{"role": "user", "content": "x"}]}
    first = machine.begin(body=body)
    machine.transition(first, "transient_transport_failure", error=TimeoutError())
    second = machine.begin(body=body)
    machine.mark_response_received(second, raw_body_sha256="0" * 64)
    machine.transition(second, "completed_response", ledger_request_index=1)
    loaded = RequestLifecycleMachine.load(tmp_path / "lifecycle.json", secret="fixture-secret")
    assert loaded.verify() == {
        "passed": True,
        "faults": [],
        "attempt_count": 2,
        "completed_response_count": 1,
        "pending_count": 0,
    }
    assert loaded.attempts[0]["request_body_sha256"] == loaded.attempts[1][
        "request_body_sha256"
    ]
    assert loaded.attempts[1]["retry_index"] == 1


def test_lifecycle_identity_ignores_no_response_attempts(tmp_path: Path) -> None:
    machine = RequestLifecycleMachine(tmp_path / "lifecycle.json", secret="fixture-secret")
    attempt = machine.begin(body={"model": "m", "messages": []})
    machine.transition(attempt, "transient_transport_failure", error=TimeoutError())

    class Ledger:
        records: list[dict[str, object]] = []

    result = lifecycle_identity(
        requested_model="m",
        canonical_alias="m-dated",
        pinned_provider="P",
        fallback_disabled=True,
        ledger=Ledger(),
        lifecycle=machine,
    )
    assert result["compatible"] is True
    assert result["expected_identity_evidence_count"] == 0
    assert result["observed_identity_evidence_count"] == 0


def test_lifecycle_identity_fails_completed_wrong_or_missing_identity(tmp_path: Path) -> None:
    for name, record in {
        "wrong": {
            "returned_model": "nearby",
            "actual_provider": "P",
            "allow_fallbacks": False,
        },
        "missing": {
            "returned_model": None,
            "actual_provider": None,
            "allow_fallbacks": False,
        },
    }.items():
        machine = RequestLifecycleMachine(tmp_path / f"{name}.json", secret="fixture-secret")
        attempt = machine.begin(body={"model": "m", "messages": []})
        machine.mark_response_received(attempt, raw_body_sha256="0" * 64)
        machine.transition(attempt, "completed_response", ledger_request_index=0)

        class Ledger:
            records = [record]

        result = lifecycle_identity(
            requested_model="m",
            canonical_alias="m-dated",
            pinned_provider="P",
            fallback_disabled=True,
            ledger=Ledger(),
            lifecycle=machine,
        )
        assert result["compatible"] is False


def test_matrix_stopping_policy_contains_provider_cells() -> None:
    assert matrix_stop_level("isolated_provider_timeout") == "cell_exclusion_continue_panel"
    assert matrix_stop_level("provider_adapter_failure") == "cell_exclusion_continue_panel"
    assert matrix_stop_level("model_completion_failure") == "continue_panel"
    assert matrix_stop_level("credential_leakage") == "global_stop"
    assert matrix_stop_level("valid_episode", repeated_identity_drift=True) == "global_stop"


def test_causal_adjudication_precedes_implementation_and_is_self_consistent() -> None:
    path = ROOT / "artifacts/uc_bench_case1_pilot_v1_rc6/causal_rc5_adjudication.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    sonnet = value["models"]["anthropic/claude-sonnet-4"]
    assert sonnet["fair_rc6_replay_expected"]["partial_scientific_quality"] == 37.0
    assert sonnet["counterfactuals"][-1]["score_delta"] == 0.0
    assert value["rc5_records_mutated"] is False
    assert canonical_sha256(value)


def test_completed_responses_without_submission_are_model_completion_failure(
    tmp_path: Path,
) -> None:
    run = tmp_path / "run"
    run.mkdir()
    lifecycle = RequestLifecycleMachine(
        run / "request_lifecycle.json", secret="fixture-secret"
    )
    attempt = lifecycle.begin(body={"model": "m", "messages": []})
    lifecycle.mark_response_received(attempt, raw_body_sha256="0" * 64)
    lifecycle.transition(attempt, "completed_response", ledger_request_index=0)
    ledger = {
        "cumulative_reported_cost_usd": 0.0,
        "requests": [
            {
                "returned_model": "m",
                "actual_provider": "P",
                "allow_fallbacks": False,
            }
        ]
    }
    (run / "request_ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
    summary = {
        "model_id": "m",
        "classification": "agent_task_failure",
        "provider_adapter": {
            "expected_canonical_slug": "m-dated",
            "provider_order": ["P"],
            "allow_fallbacks": False,
        },
        "submission": {"state": {"completion_accepted": False}},
    }
    (run / "run_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    repaired = finalize_rc6_run_summary(run, key="fixture-secret")
    assert repaired["classification"] == "model_completion_failure"
    assert repaired["reliability_score"] == 0.0
    assert repaired["provider_identity"]["compatible"] is True

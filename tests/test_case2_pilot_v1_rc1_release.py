from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import pytest

from uc_bench.case1_pilot_v1_rc3_tools import case1_tool_definitions
from uc_bench.case2_pilot_v1_rc1_environment import Case2PilotRC1Environment
from uc_bench.case2_pilot_v1_rc1_execution import (
    _adopt_cell,
    _completed_request_evidence_faults,
    _durable_trajectory_faults,
    _route_evidence,
    active_cell_recovery_mode,
    forensic_adjudication,
    summary_integrity_faults,
)
from uc_bench.case2_pilot_v1_rc1_interface import production_request
from uc_bench.case2_pilot_v1_rc1_provider import (
    load_case2_adapters,
    load_case2_config,
)
from uc_bench.case2_pilot_v1_rc1_release import (
    CASE1_RC6_DIGEST,
    CASE1_RC6_REQUEST_DIGEST,
    CASE1_RC6_TOOL_DIGEST,
    _frozen_candidate_fields_match,
    candidate_manifest,
    compatibility_adjudication,
)
from uc_bench.case2_pilot_v1_rc1_runner import Case2RunConfig, grader_assessment
from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256
from uc_bench.openrouter_catalog import CatalogModel

ROOT = Path(__file__).resolve().parents[1]


def test_case2_panel_is_exact_and_excludes_every_forbidden_scope() -> None:
    value = load_case2_config(ROOT)
    assert value["execution_order"] == [
        "google/gemini-3.1-pro-preview",
        "openai/gpt-5.1",
        "anthropic/claude-sonnet-4",
    ]
    assert value["forbidden_cases"] == ["case_01", "case_03", "case_04"]
    assert value["budgets_usd"]["scientific_hard_cap"] == 12.0


def test_three_routes_are_singly_pinned_without_fallback() -> None:
    adapters = load_case2_adapters(ROOT)
    assert set(adapters) == set(load_case2_config(ROOT)["execution_order"])
    assert all(len(adapter.provider_order) == 1 for adapter in adapters.values())
    assert all(not adapter.allow_fallbacks for adapter in adapters.values())


def test_provider_facing_request_tools_and_adapters_inherit_rc6_exactly() -> None:
    request = production_request(Case2RunConfig("test", "openai/gpt-5.1"))
    assert len(CASE1_RC6_DIGEST) == 64
    assert canonical_sha256(request) == CASE1_RC6_REQUEST_DIGEST
    assert canonical_sha256(case1_tool_definitions()) == CASE1_RC6_TOOL_DIGEST
    result = compatibility_adjudication(ROOT)
    assert result["passed"]
    assert result["affected_routes_requiring_live_canary"] == []


def test_environment_uses_physical_boundary_without_changing_visible_packet(
    tmp_path: Path,
) -> None:
    environment = Case2PilotRC1Environment(ROOT, tmp_path / "workspace")
    assert hasattr(environment, "mark_workspace_boundary_enforced")
    proposal = json.loads(
        (
            ROOT / "artifacts/uc_bench_case2_pilot_v1_rc1_candidate/freeze_manifest_proposal.json"
        ).read_text(encoding="utf-8")
    )
    observed = {
        path.relative_to(environment.run_root).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in sorted(environment.run_root.rglob("*"))
        if path.is_file()
    }
    assert observed == proposal["required_closure"]["agent_visible_start_state_hashes"]


def test_release_closure_is_category_separated_and_has_no_runtime_monkeypatch() -> None:
    value = candidate_manifest(ROOT)
    expected = {
        "agent_visible_materialized",
        "agent_visible_source",
        "protected_and_sealed",
        "scientific_semantics_and_verifier",
        "runner_persistence_reporting",
        "provider_request_tool_adapters",
        "public_support_and_host_semantic",
        "transitive_runtime_support",
        "tests_controls_reviews",
        "route_and_cost_policy",
    }
    assert set(value["closure"]["groups"]) == expected
    assert value["closure"]["runtime_monkeypatching"] is False
    assert value["closure"]["historical_build_directory_dependency"] is False


def test_freeze_schema_transition_preserves_every_candidate_field() -> None:
    candidate = {
        "schema_version": "uc-bench-case2-pilot-v1-rc1-candidate-2",
        "status": "candidate_unfrozen",
        "release_id": "release",
        "closure": {"x": 1},
    }
    frozen = {
        **candidate,
        "schema_version": "uc-bench-case2-pilot-v1-rc1-freeze-1",
        "status": "frozen_pre_science",
    }
    assert _frozen_candidate_fields_match(frozen, candidate)
    for field, bad_value in (
        ("schema_version", "wrong-freeze-schema"),
        ("status", "candidate_unfrozen"),
        ("closure", {"x": 2}),
    ):
        altered = {**frozen, field: bad_value}
        assert not _frozen_candidate_fields_match(altered, candidate)


def test_grader_contradictions_fail_closed() -> None:
    grade = {
        "complete_mission_success": True,
        "first_decision_critical_failure": {"requirement_id": "x"},
        "mission_failures": [],
        "failure_class": "scientific_failure",
        "partial_scientific_quality": 100,
        "requirements": [],
        "diagnostics": {"property_points": {}, "prose_scored": False},
    }
    assert grader_assessment(grade, None)["status"] == "failed"


def test_nearby_or_forbidden_model_cannot_enter_adapter_map(tmp_path: Path) -> None:
    config = json.loads(
        (ROOT / "configs/uc_bench_case2_pilot_v1_rc1.json").read_text(encoding="utf-8")
    )
    altered = copy.deepcopy(config)
    altered["models"][1]["model_id"] = "openai/gpt-5"
    altered["execution_order"][1] = "openai/gpt-5"
    path = tmp_path / "config.json"
    path.write_text(json.dumps(altered), encoding="utf-8")
    assert "openai/gpt-5" in altered["forbidden_models"]


def test_invalid_release_authorization_is_rejected() -> None:
    from uc_bench.case2_pilot_v1_rc1_runner import _release_record

    with pytest.raises(ConfigurationError):
        _release_record(ROOT, "wrong", preflight=True)


def test_route_gate_requires_exact_catalog_canonical_pin() -> None:
    declared = {
        "provider": "OpenAI",
        "canonical_slug": "openai/gpt-5.1-20251113",
    }
    endpoint = [
        {
            "provider_name": "OpenAI",
            "model_name": "openai/gpt-5.1-20251113",
        }
    ]
    exact = CatalogModel(
        "openai/gpt-5.1",
        "openai/gpt-5.1-20251113",
        400_000,
        128_000,
        (),
        {},
    )
    drifted = CatalogModel(
        "openai/gpt-5.1",
        "openai/gpt-5.1-nearby",
        400_000,
        128_000,
        (),
        {},
    )
    assert _route_evidence("openai/gpt-5.1", declared, exact, endpoint)[
        "route_available"
    ]
    result = _route_evidence("openai/gpt-5.1", declared, drifted, endpoint)
    assert not result["canonical_pin_matches"]
    assert not result["route_available"]


def test_outer_runner_distinguishes_resume_adopt_and_unsafe_boundaries(
    tmp_path: Path,
) -> None:
    model = "openai/gpt-5.1"
    run_id = "case2-rc1-00-openai-gpt-5.1-attempt-0"
    state = {"execution_order": [model], "active_cell": {"model_id": model, "run_id": run_id}}
    state["release_digest"] = "frozen-digest"
    state["active_cell"]["release_digest"] = "frozen-digest"
    output = tmp_path / "runs"
    assert active_cell_recovery_mode(ROOT, state, output_root=output) == "start_unissued"
    run_root = output / run_id
    (run_root / "host_trajectory").mkdir(parents=True)
    assert (
        active_cell_recovery_mode(ROOT, state, output_root=output)
        == "blocked_missing_durable_boundary"
    )
    raw_response = {"model": "returned-model", "provider": "Provider", "choices": []}
    request = {
        "request_index": 0,
        "returned_model": "returned-model",
        "actual_provider": "Provider",
        "reported_cost_usd": 0.1,
        "runner_normalization": {"pending_request_body_sha256": "digest"},
    }
    (run_root / "host_trajectory/latest.json").write_text(
        json.dumps(
            {
                "provider_exchanges": [
                    {
                        "request_index": 0,
                        "request_body_sha256": "digest",
                        "raw_body_sha256": "raw-digest",
                        "raw_response": raw_response,
                        "raw_response_sha256": canonical_sha256(raw_response),
                    }
                ],
                "provider_requests": [request],
            }
        ),
        encoding="utf-8",
    )
    (run_root / "request_ledger.json").write_text(
        json.dumps({"requests": [request]}), encoding="utf-8"
    )
    (run_root / "request_lifecycle.json").write_text(
        json.dumps(
            {
                "schema_version": "uc-bench-case1-pilot-v1-rc6-request-lifecycle-1",
                "attempt_count": 1,
                "completed_response_count": 1,
                "attempts": [
                    {
                        "attempt_id": 0,
                        "logical_request_index": 0,
                        "retry_index": 0,
                        "request_body_sha256": "digest",
                        "state": "completed_response",
                        "response_received": True,
                        "raw_body_sha256": "raw-digest",
                        "ledger_request_index": 0,
                        "transition_history": ["pending", "completed_response"],
                        "started_at": "time",
                        "ended_at": "time",
                        "error_chain": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    assert (
        active_cell_recovery_mode(ROOT, state, output_root=output)
        == "blocked_corrupt_durable_trajectory"
    )
    corrupted = json.loads((run_root / "request_lifecycle.json").read_text())
    corrupted["attempts"][0]["ledger_request_index"] = 999
    (run_root / "request_lifecycle.json").write_text(json.dumps(corrupted))
    assert (
        active_cell_recovery_mode(ROOT, state, output_root=output)
        == "blocked_inconsistent_request_evidence"
    )
    (run_root / "request_lifecycle.json").write_text(
        json.dumps(
            {
                "schema_version": "uc-bench-case1-pilot-v1-rc6-request-lifecycle-1",
                "attempt_count": 1,
                "completed_response_count": 0,
                "attempts": [
                    {
                        "attempt_id": 0,
                        "logical_request_index": 0,
                        "retry_index": 0,
                        "request_body_sha256": "digest",
                        "state": "pending",
                        "response_received": False,
                        "ledger_request_index": None,
                        "transition_history": ["pending"],
                        "started_at": "time",
                        "ended_at": None,
                        "error_chain": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    assert (
        active_cell_recovery_mode(ROOT, state, output_root=output)
        == "blocked_ambiguous_inflight_request"
    )
    (run_root / "run_summary.json").write_text("{}", encoding="utf-8")
    assert (
        active_cell_recovery_mode(ROOT, state, output_root=output)
        == "blocked_corrupt_durable_trajectory"
    )


def test_summary_shape_fails_closed_and_causal_report_uses_real_key() -> None:
    malformed = {
        "schema_version": "wrong",
        "model_id": "openai/gpt-5.1",
        "run_id": "run",
        "case_id": "case_02",
        "classification": "invented",
    }
    faults = summary_integrity_faults(
        malformed,
        expected_model_id="openai/gpt-5.1",
        expected_run_id="run",
        expected_release_id="uc-bench-case2-pilot-v1-rc1",
        expected_release_digest="digest",
        expected_adapter=load_case2_adapters(ROOT)["openai/gpt-5.1"].to_dict(),
    )
    assert "summary_schema_version_mismatch" in faults
    assert "summary_classification_unknown" in faults

    superficially_valid = {
        **malformed,
        "schema_version": "uc-bench-case2-pilot-v1-rc1-run-1",
        "classification": "valid_episode",
        "release_id": "uc-bench-case2-pilot-v1-rc1",
        "release_digest": "DIFFERENT",
        "provider_adapter": load_case2_adapters(ROOT)["openai/gpt-5.1"].to_dict(),
        "run_config": {},
        "provider_fallbacks_allowed": False,
        "agent_received_provider_credentials": False,
        "agent_network_enabled": False,
        "other_case_requests": 0,
        "sol_requests": 0,
        "astra_requests": 0,
        "integrity": {},
        "request_lifecycle": {"passed": True},
        "trajectory_replay": {"passed": True},
        "diagnostic_grade": None,
        "submission": {},
    }
    valid_faults = summary_integrity_faults(
        superficially_valid,
        expected_model_id="openai/gpt-5.1",
        expected_run_id="run",
        expected_release_id="uc-bench-case2-pilot-v1-rc1",
        expected_release_digest="digest",
        expected_adapter=load_case2_adapters(ROOT)["openai/gpt-5.1"].to_dict(),
    )
    assert "summary_release_digest_mismatch" in valid_faults
    assert "summary_valid_episode_missing_grade" in valid_faults
    assert "summary_valid_episode_missing_submission" in valid_faults
    summary = {
        "model_id": "openai/gpt-5.1",
        "diagnostic_grade": {
            "complete_mission_success": False,
            "first_decision_critical_failure": {
                "requirement_id": "x",
                "downstream_dependencies": ["y"],
            },
            "requirements": [{"requirement_id": "x", "passed": False}],
            "diagnostics": {"prose_scored": False},
        },
    }
    assert forensic_adjudication(summary)["downstream_consequences"] == ["y"]


def test_malformed_provider_summary_fails_closed_without_crashing() -> None:
    summary = {
        "schema_version": "uc-bench-case2-pilot-v1-rc1-run-1",
        "model_id": "openai/gpt-5.1",
        "run_id": "run",
        "case_id": "case_02",
        "release_id": "uc-bench-case2-pilot-v1-rc1",
        "release_digest": "digest",
        "classification": "isolated_provider_failure",
        "integrity": {},
        "request_lifecycle": {},
        "trajectory_replay": {},
        "grader_assessment": ["malformed"],
        "provider_identity": ["malformed"],
        "provider_adapter": load_case2_adapters(ROOT)["openai/gpt-5.1"].to_dict(),
        "run_config": asdict(Case2RunConfig("run", "openai/gpt-5.1")),
        "provider_fallbacks_allowed": False,
        "agent_received_provider_credentials": False,
        "agent_network_enabled": False,
        "other_case_requests": 0,
        "sol_requests": 0,
        "astra_requests": 0,
        "diagnostic_grade": None,
        "partial_scientific_quality": None,
        "reliability_score": None,
    }
    faults = summary_integrity_faults(
        summary,
        expected_model_id="openai/gpt-5.1",
        expected_run_id="run",
        expected_release_id="uc-bench-case2-pilot-v1-rc1",
        expected_release_digest="digest",
        expected_adapter=load_case2_adapters(ROOT)["openai/gpt-5.1"].to_dict(),
    )
    assert "summary_grader_assessment_malformed" in faults
    assert "summary_provider_identity_malformed" in faults


@pytest.mark.parametrize(
    ("pending_calls", "expected_fault"),
    [
        (1, "durable_pending_tool_collection_malformed"),
        ([{"status": "pending_recoverable"}], "durable_active_tool_call"),
    ],
)
def test_durable_pending_tool_evidence_is_total_and_fail_closed(
    tmp_path: Path, pending_calls: object, expected_fault: str
) -> None:
    run_root = tmp_path / "run"
    host = run_root / "host_trajectory"
    host.mkdir(parents=True)
    metadata = {
        "run_config": {"run_id": "run", "model_id": "openai/gpt-5.1"},
        "case_id": "case_02",
        "release_id": "uc-bench-case2-pilot-v1-rc1",
        "release_digest": "digest",
        "agent_visible": False,
    }
    (host / "metadata.json").write_text(json.dumps({"run_metadata": metadata}))
    (host / "latest.json").write_text(
        json.dumps({"run_metadata": metadata, "pending_tool_calls": pending_calls})
    )
    faults, _ = _durable_trajectory_faults(
        ROOT,
        run_root,
        expected_model_id="openai/gpt-5.1",
        expected_run_id="run",
        expected_release_id="uc-bench-case2-pilot-v1-rc1",
        expected_release_digest="digest",
        require_no_pending_tools=True,
    )
    assert expected_fault in faults


def test_adoption_rejects_malformed_disk_request_records_without_crashing(
    tmp_path: Path,
) -> None:
    model_id = "openai/gpt-5.1"
    run_id = "run"
    run_root = tmp_path / run_id
    run_root.mkdir()
    summary = {
        "schema_version": "uc-bench-case2-pilot-v1-rc1-run-1",
        "model_id": model_id,
        "run_id": run_id,
        "case_id": "case_02",
        "release_id": "uc-bench-case2-pilot-v1-rc1",
        "release_digest": "digest",
        "classification": "isolated_provider_failure",
        "integrity": {},
        "request_lifecycle": {},
        "trajectory_replay": {},
        "grader_assessment": {},
        "provider_identity": {},
        "provider_adapter": load_case2_adapters(ROOT)[model_id].to_dict(),
        "run_config": asdict(Case2RunConfig(run_id, model_id)),
        "provider_fallbacks_allowed": False,
        "agent_received_provider_credentials": False,
        "agent_network_enabled": False,
        "other_case_requests": 0,
        "sol_requests": 0,
        "astra_requests": 0,
        "diagnostic_grade": None,
        "partial_scientific_quality": None,
        "reliability_score": None,
        "provider_requests": 1,
        "submission": {},
    }
    (run_root / "run_summary.json").write_text(json.dumps(summary))
    (run_root / "submission.json").write_text("{}")
    (run_root / "request_ledger.json").write_text(json.dumps({"requests": 1}))
    (run_root / "request_lifecycle.json").write_text(
        json.dumps({"attempt_count": 0, "attempts": []})
    )
    state = {
        "release_id": "uc-bench-case2-pilot-v1-rc1",
        "release_digest": "digest",
        "execution_order": [model_id],
        "global_stop_faults": [],
        "active_cell": {"model_id": model_id, "run_id": run_id},
    }
    _adopt_cell(
        ROOT,
        key="",
        state=state,
        summary_path=run_root / "run_summary.json",
        adapter=load_case2_adapters(ROOT)[model_id],
        state_path=tmp_path / "state.json",
    )
    assert state["status"] == "global_stop"
    assert "disk_request_ledger_malformed" in state["global_stop_faults"]


@pytest.mark.parametrize(
    ("state", "response_received"),
    [
        ("completed_response", True),
        ("provider_response_parse_failure", True),
        ("transient_transport_failure", False),
        ("terminal_provider_failure", False),
    ],
)
def test_request_evidence_binding_accepts_every_terminal_production_shape(
    state: str, response_received: bool
) -> None:
    request_digest = "request-digest"
    error = {"classification": "provider_adapter_failure", "type": "FixtureError"}
    attempt = {
        "attempt_id": 0,
        "state": state,
        "response_received": response_received,
        "request_body_sha256": request_digest,
        "ledger_request_index": 0,
    }
    record = {
        "request_index": 0,
        "returned_model": "model" if state == "completed_response" else None,
        "actual_provider": "provider" if state == "completed_response" else None,
        "runner_normalization": {"pending_request_body_sha256": request_digest},
        "error": None if state == "completed_response" else error,
    }
    exchange: dict[str, object] = {
        "request_index": 0,
        "request_body_sha256": request_digest,
    }
    if response_received:
        raw_response = {"model": "model", "provider": "provider"}
        exchange.update(
            {
                "raw_body_sha256": "raw-digest",
                "raw_response": raw_response,
                "raw_response_sha256": canonical_sha256(raw_response),
            }
        )
        attempt["raw_body_sha256"] = "raw-digest"
    if state != "completed_response":
        exchange.update(
            {
                "attempt_state": state,
                "error_record_sha256": canonical_sha256(error),
            }
        )
    assert not _completed_request_evidence_faults([attempt], [record], [exchange])
    exchange["request_body_sha256"] = "altered"
    assert "request_0:request_digest_mismatch" in _completed_request_evidence_faults(
        [attempt], [record], [exchange]
    )


def test_request_evidence_binding_rejects_falsy_malformed_collections() -> None:
    for malformed in (None, False, 0, "", {}):
        assert _completed_request_evidence_faults(malformed, [], []) == [
            "request_evidence_collections_malformed"
        ]

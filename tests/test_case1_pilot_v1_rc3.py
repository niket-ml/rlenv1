from __future__ import annotations

import copy
import json
import os
import tempfile
from pathlib import Path

import pytest

import uc_bench.case1_pilot_v1_rc3_execution as rc3_execution
from uc_bench.case1_pilot_v1_interface import production_request as rc1_request
from uc_bench.case1_pilot_v1_rc3_compatibility import replay_rc3_compatibility
from uc_bench.case1_pilot_v1_rc3_execution import (
    isolated_provider_cell,
    rc3_global_stop_faults,
)
from uc_bench.case1_pilot_v1_rc3_interface import production_request
from uc_bench.case1_pilot_v1_rc3_release import PREFLIGHT_PATH, scientific_parity
from uc_bench.case1_pilot_v1_rc3_runner import (
    grader_assessment,
    pre_provider_failure_assessment,
    raw_received_event_count,
    replay_not_applicable,
)
from uc_bench.case1_pilot_v1_rc3_runtime import rc3_durable_tool_functions
from uc_bench.case1_pilot_v1_rc3_tools import (
    CASE1_TOOL_CONTRACT_REGISTRY,
    assert_three_surfaces,
    case1_tool_definitions,
)
from uc_bench.case1_pilot_v1_release import read_release_freeze
from uc_bench.case1_pilot_v1_runner import (
    Case1PilotRunConfig,
)
from uc_bench.case1_pilot_v1_runner import (
    assert_tool_surface as rc2_assert_tool_surface,
)
from uc_bench.case1_pilot_v1_runtime import Case1PilotTrajectoryStore
from uc_bench.mmmvp_open_rc13_trajectory import rc13_durable_tool_functions
from uc_bench.mmmvp_open_rc17_environment import RC17OpenMMMVPEnvironment
from uc_bench.mmmvp_open_rc17_verifier import WEIGHTS

ROOT = Path(os.environ.get("UC_BENCH_CLEAN_ROOT", Path(__file__).resolve().parents[1])).resolve()


class FakeDocker:
    def inspect_workspace(self, relative_path: str = ".") -> str:
        return relative_path

    def read_file(self, relative_path: str) -> str:
        return relative_path

    def write_file(self, relative_path: str, content: str) -> str:
        return relative_path + content

    def run_command(self, command: str) -> str:
        return command


class Observer:
    def __getattr__(self, _name: str):
        return lambda *args, **kwargs: None


def test_registry_is_complete_ordered_strict_and_defensive() -> None:
    rows = case1_tool_definitions()
    assert len(rows) == 9
    assert len({row["function"]["name"] for row in rows}) == 9
    assert all(row["type"] == "function" for row in rows)
    assert all(row["function"]["description"] for row in rows)
    assert all(row["function"]["strict"] is True for row in rows)
    assert all(row["function"]["parameters"]["additionalProperties"] is False for row in rows)
    assert all(isinstance(row["function"]["parameters"]["required"], list) for row in rows)
    mutated = case1_tool_definitions()
    mutated[0]["function"]["description"] = "changed"
    assert case1_tool_definitions() == list(CASE1_TOOL_CONTRACT_REGISTRY)


def test_rc3_request_is_byte_identical_to_rc1_and_uses_registry() -> None:
    config = Case1PilotRunConfig("parity", "google/gemini-3.1-pro-preview")
    assert production_request(config) == rc1_request(config)
    assert production_request(config)["tools"] == case1_tool_definitions()
    assert scientific_parity(ROOT)["passed"]


def test_runtime_binding_is_exact_and_does_not_mutate_class_methods() -> None:
    directory = tempfile.TemporaryDirectory()
    try:
        core = RC17OpenMMMVPEnvironment(ROOT, "case_01", Path(directory.name) / "workspace")
        names = (
            "commit_validation_plan",
            "reveal_validation",
            "commit_followup_plan",
            "purchase_resource",
            "submit",
        )
        before = {name: getattr(RC17OpenMMMVPEnvironment, name).__doc__ for name in names}
        first = rc3_durable_tool_functions(FakeDocker(), core, Observer(), Observer())
        assert_three_surfaces(request_tools=case1_tool_definitions(), runtime_tools=first)
        second = rc3_durable_tool_functions(FakeDocker(), core, Observer(), Observer())
        assert_three_surfaces(request_tools=case1_tool_definitions(), runtime_tools=second)
        after = {name: getattr(RC17OpenMMMVPEnvironment, name).__doc__ for name in names}
        assert before == after
    finally:
        directory.cleanup()


def test_rc2_exact_failure_is_preserved_and_rc3_repairs_it() -> None:
    summary_path = ROOT / (
        "artifacts/uc_bench_case1_pilot_v1_rc2/science/runs/"
        "case1-rc2-00-google-gemini-3.1-pro-preview-attempt-0/run_summary.json"
    )
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["provider_request_count"] == 0
    assert summary["rollout_error"]["message"] == (
        "Production tool surface differs from the frozen request"
    )
    with tempfile.TemporaryDirectory() as directory:
        core = RC17OpenMMMVPEnvironment(ROOT, "case_01", Path(directory) / "workspace")
        rc2_tools = rc13_durable_tool_functions(FakeDocker(), core, Observer(), Observer())
        with pytest.raises(Exception, match="tool surface differs"):
            request = rc1_request(Case1PilotRunConfig("x", "openai/gpt-5"))
            rc2_assert_tool_surface(request, rc2_tools)
        rc3_tools = rc3_durable_tool_functions(FakeDocker(), core, Observer(), Observer())
        assert_three_surfaces(request_tools=case1_tool_definitions(), runtime_tools=rc3_tools)


def test_exact_production_path_preflight_passed() -> None:
    value = json.loads((ROOT / PREFLIGHT_PATH).read_text(encoding="utf-8"))
    assert value["passed"]
    assert value["api_requests"] == value["scientific_model_requests"] == 0
    assert value["fake_provider_requests"] == 2
    assert value["replay_status"] == "passed"
    assert value["grader_status"] == "not_applicable"
    assert value["summary_identity"] == {
        "scientific_base_release_id": "uc-bench-case1-pilot-v1-rc1",
        "scientific_base_digest": (
            "efcd42455279ae6601a7c11493e7c7b194478a6cad5e633a76785b25c48c31ec"
        ),
        "execution_release_id": "uc-bench-case1-pilot-v1-rc3-preflight",
        "execution_release_digest": "rc3-unfrozen-fake-provider-preflight",
    }
    assert all(value["checks"].values())


@pytest.mark.parametrize(
    ("stage", "subtype"),
    (
        ("tool_surface_verified", "pre_client_configuration_failure"),
        ("client_constructed", "pre_first_request_failure"),
    ),
)
def test_pre_provider_failures_are_infrastructure_not_replay_or_grader(
    stage: str, subtype: str
) -> None:
    result = pre_provider_failure_assessment(
        request_count=0,
        raw_response_count=0,
        rollout_error={"type": "ConfigurationError"},
        execution_stage=stage,
    )
    assert result["classification_override"] == "infrastructure_failure"
    assert result["failure_subtype"] == subtype
    assert replay_not_applicable("no_durable_provider_response")["status"] == "not_applicable"
    assert grader_assessment(None, None)["status"] == "not_applicable"


def test_failure_after_durable_response_is_not_pre_provider_failure() -> None:
    result = pre_provider_failure_assessment(
        request_count=1,
        raw_response_count=1,
        rollout_error={"type": "ProviderIdentityError"},
        execution_stage="client_constructed",
    )
    assert result["provider_boundary_status"] == "durable_response_persisted"
    assert result["classification_override"] is None


def test_raw_response_persistence_is_counted_before_parsed_exchange(tmp_path: Path) -> None:
    core = RC17OpenMMMVPEnvironment(ROOT, "case_01", tmp_path / "workspace")

    class Ledger:
        records: list[dict] = []
        cumulative_reported_cost_usd = 0.0

    store = Case1PilotTrajectoryStore(
        tmp_path / "host",
        workspace=tmp_path / "workspace",
        core=core,  # type: ignore[arg-type]
        secret="fixture-secret",
        run_metadata={"fixture": "pre-parse-raw-persistence"},
    )
    response = {
        "model": "fixture/model",
        "provider": "fixture",
        "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "x"}}],
        "usage": {"cost": 0},
    }
    store.record_received_response(
        prompt=[{"role": "user", "content": "x"}],
        response=response,
        ledger=Ledger(),
    )
    latest = store.latest()
    assert raw_received_event_count(store) == 1
    assert latest["event_type"] == "raw_model_response_received"
    assert latest["provider_exchanges"] == []


def test_only_real_replay_or_grader_failure_creates_those_stop_labels() -> None:
    base = {
        "integrity": {
            "start_state_untampered": True,
            "protected_evidence_untampered": True,
            "workspace_boundary_enforced": True,
        },
        "trajectory_replay": {"status": "not_applicable"},
        "grader_assessment": {"status": "not_applicable"},
        "provider_requests": [],
        "classification": "infrastructure_failure",
    }
    assert rc3_global_stop_faults(base) == []
    replay = copy.deepcopy(base)
    replay["trajectory_replay"] = {"status": "failed"}
    assert rc3_global_stop_faults(replay) == ["persistence_or_replay_failure"]
    grader = copy.deepcopy(base)
    grader["grader_assessment"] = {"status": "failed"}
    assert rc3_global_stop_faults(grader) == ["verifier_contradiction_or_failure"]


def test_two_transient_provider_failures_are_cell_scoped_and_do_not_stop_panel() -> None:
    summary = {
        "classification": "infrastructure_failure",
        "raw_response_persisted_count": 0,
        "provider_requests": [
            {
                "error": {
                    "http_status": 503,
                    "classification": "infrastructure_failure",
                    "message": "temporarily unavailable",
                }
            }
        ],
        "trajectory_replay": {"status": "not_applicable"},
        "grader_assessment": {"status": "not_applicable"},
        "integrity": {
            "start_state_untampered": True,
            "protected_evidence_untampered": True,
            "workspace_boundary_enforced": True,
        },
    }
    assert isolated_provider_cell(summary)
    assert rc3_global_stop_faults(summary) == []


def test_route_specific_exclusion_does_not_stop_later_cells(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    order = ["model/a", "model/b", "model/c", "model/d"]
    state = {
        "status": "ready_for_remaining_four",
        "global_stop_faults": [],
        "remaining_four_randomization": {"order": order},
    }
    visited: list[str] = []

    monkeypatch.setattr(rc3_execution, "_read", lambda _path: state)
    monkeypatch.setattr(rc3_execution, "_write_json", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        rc3_execution,
        "funding_snapshot",
        lambda _key: {
            "account_balance_remaining_usd": 100.0,
            "key_limit_usd": 100.0,
            "key_usage_usd": 0.0,
            "key_remaining_usd": 100.0,
            "effective_remaining_usd": 100.0,
        },
    )

    def fake_cell(
        _root: Path,
        *,
        key: str,
        state: dict,
        model_id: str,
        order_index: int,
    ) -> dict:
        del key, order_index
        visited.append(model_id)
        if model_id == order[0]:
            state.setdefault("excluded_models", []).append(
                {"model_id": model_id, "reason": "isolated provider failure"}
            )
        return {}

    monkeypatch.setattr(rc3_execution, "_run_cell", fake_cell)
    result = rc3_execution.run_remaining_four(tmp_path, key="fixture-secret")
    assert visited == order
    assert result["status"] == "completed_mandatory_review"
    assert result["global_stop_faults"] == []


def test_contract_failure_is_a_valid_grader_result_not_a_contradiction() -> None:
    grade = {
        "complete_mission_success": False,
        "first_decision_critical_failure": None,
        "mission_failures": [],
        "failure_class": "contract_failure",
        "requirements": [],
        "diagnostics": {},
    }
    assert grader_assessment(grade, None)["status"] == "passed"


def test_actual_verifier_contradiction_is_detected() -> None:
    grade = {
        "complete_mission_success": True,
        "first_decision_critical_failure": "threshold_utility",
        "mission_failures": ["threshold_utility"],
        "failure_class": "scientific_failure",
        "requirements": [
            {"requirement_id": name, "passed": True} for name in WEIGHTS
        ],
        "partial_scientific_quality": 100,
        "diagnostics": {},
    }
    result = grader_assessment(grade, None)
    assert result["status"] == "failed"
    assert "mission_success_coexists_with_critical_failure" in result["faults"]


def test_compatibility_is_inherited_without_calls_and_schema_is_unchanged() -> None:
    result = replay_rc3_compatibility(ROOT)
    assert result["status"] == "passed"
    assert result["new_api_requests"] == 0
    assert result["compatible_count"] == 5
    assert result["provider_visible_schema_unchanged"]


def test_rc3_does_not_use_simplified_legacy_tool_specs() -> None:
    for path in (
        ROOT / "src/uc_bench/case1_pilot_v1_rc3_tools.py",
        ROOT / "src/uc_bench/case1_pilot_v1_rc3_interface.py",
        ROOT / "src/uc_bench/case1_pilot_v1_rc3_runtime.py",
    ):
        assert "OPEN_TOOL_SPECS" not in path.read_text(encoding="utf-8")


def test_rc1_remains_frozen() -> None:
    assert read_release_freeze(ROOT)["closure"]["file_count"] == 111

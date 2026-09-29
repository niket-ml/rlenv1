from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any

import pytest
from verifiers.legacy.utils.tool_utils import convert_func_to_tool_def

import scripts.run_v08_development as pilot
import uc_bench.v08_runner as production_runner
from uc_bench.errors import ConfigurationError
from uc_bench.openrouter import OPENROUTER_BASE_URL
from uc_bench.v07_provider import load_v07_provider_adapters
from uc_bench.v071_auth import credential_locations
from uc_bench.v08_controls import build_reference_solution, sync_event_digests
from uc_bench.v08_environment import V08Environment, v08_tool_functions
from uc_bench.v08_interface import V08_AGENT_CONTRACT, v08_condition_rule
from uc_bench.v08_schema import SCHEMA_VERSION, validate_v08_checkpoint
from uc_bench.v08_verifier import verify_v08_submission

ROOT = Path(__file__).resolve().parents[1]
TEST_KEY = "sk-or-v1-v08-regression-secret"


class _FakeDocker:
    def inspect_workspace(self, relative_path: str = ".") -> str:
        return relative_path

    def read_file(self, relative_path: str) -> str:
        return relative_path

    def write_file(self, relative_path: str, content: str) -> str:
        return f"{relative_path}:{len(content)}"

    def run_command(self, command: str) -> str:
        return str(len(command))


class _FakeClient:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


def _adapter() -> Any:
    return load_v07_provider_adapters(ROOT)["openai/gpt-5.6-sol"]


def test_v08_agent_contract_discloses_every_new_machine_requirement() -> None:
    for fragment in (
        SCHEMA_VERSION,
        "decision_question",
        "CURRENT_PROBABILITY_USE",
        "PATIENT_IDENTITY",
        "TRANSPORT",
        "CLEAN_PIPELINE_SIGNAL",
        "initial_decision",
        "support_probability_before",
        "support_probability_after",
        "development_stage",
        "allowed_use",
        "prohibited_use",
        "unresolved_gates",
        "required_next_evidence",
        "artifact_manifest.calculated_outputs_path",
        "evidence_paths",
    ):
        assert fragment in V08_AGENT_CONTRACT
    assert "All machine-enforced names" in V08_AGENT_CONTRACT


def test_condition_specific_resource_rules_are_explicit() -> None:
    case2 = v08_condition_rule("case_02")
    assert all(resource in case2 for resource in ("X17", "X46", "none"))
    case3 = v08_condition_rule("case_03_signal_remains")
    assert "must increase" in case3 and "No exact probability" in case3
    case4 = v08_condition_rule("case_04")
    assert "immediate aim" in case4 and "Unnecessary purchasing" in case4


def test_native_reference_submissions_satisfy_v08_schema(tmp_path: Path) -> None:
    conditions = (
        "case_01",
        "case_02",
        "case_03_signal_collapses",
        "case_03_signal_remains",
        "case_04",
    )
    for index, condition_id in enumerate(conditions):
        submission, _ = build_reference_solution(
            ROOT, condition_id, tmp_path / str(index), alternative=False
        )
        for checkpoint, payload in submission["checkpoints"].items():
            result = validate_v08_checkpoint(checkpoint, payload)
            assert result.valid, (condition_id, checkpoint, result.issues)


def test_corrected_schema_resubmission_keeps_latest_valid_payload(tmp_path: Path) -> None:
    submission, _ = build_reference_solution(
        ROOT, "case_01", tmp_path / "reference", alternative=False
    )
    environment = V08Environment(ROOT, "case_01", tmp_path / "episode")
    rejected = environment.save_checkpoint(
        "C1", json.dumps({"schema_version": SCHEMA_VERSION})
    )
    accepted = environment.save_checkpoint(
        "C1", json.dumps(submission["checkpoints"]["C1"])
    )
    assert rejected["accepted"] is False
    assert accepted["accepted"] is True
    assert environment.state.event_log[-2]["schema_valid"] is False
    assert environment.state.event_log[-1]["schema_valid"] is True
    saved = json.loads((environment.run_root / "checkpoints/C1.json").read_text())
    assert saved == submission["checkpoints"]["C1"]


def test_tool_surface_and_order_are_unchanged(tmp_path: Path) -> None:
    environment = V08Environment(ROOT, "case_01", tmp_path / "episode")
    tools = v08_tool_functions(_FakeDocker(), environment)  # type: ignore[arg-type]
    definitions = [convert_func_to_tool_def(tool) for tool in tools]
    names = [getattr(row, "name", None) or row["name"] for row in definitions]
    assert names == [
        "inspect_workspace",
        "read_file",
        "write_file",
        "run_command",
        "save_checkpoint",
        "commit_validation_plan",
        "reveal_validation",
        "purchase_resource",
        "submit",
    ]


def test_verifier_reads_native_fields_and_has_consistent_mission(tmp_path: Path) -> None:
    submission, workspace = build_reference_solution(
        ROOT, "case_03_signal_remains", tmp_path / "reference", alternative=False
    )
    grade = verify_v08_submission(
        ROOT, workspace, submission, condition_id="case_03_signal_remains"
    ).to_dict()
    assert grade["complete_mission_success"] is True
    assert grade["first_decision_critical_failure"] is None
    assert grade["explicit_initial_decision_object"] == submission["checkpoints"]["C4"][
        "initial_decision"
    ]
    assert grade["explicit_decision_object"] == submission["checkpoints"]["C5"][
        "decision"
    ]
    assert grade["numeric_belief_change"] == submission["checkpoints"]["C5"][
        "belief_change"
    ]


def test_case2_no_purchase_is_accepted_only_for_current_use_question(
    tmp_path: Path,
) -> None:
    submission, workspace = build_reference_solution(
        ROOT, "case_02", tmp_path / "case2", alternative=False
    )
    c4 = submission["checkpoints"]["C4"]
    c5 = submission["checkpoints"]["C5"]
    c4["chosen_resource"] = "none"
    c4["decision_question"] = "CURRENT_PROBABILITY_USE"
    for event in submission["event_log"]:
        if event.get("event") == "purchase_resource":
            event["resource_id"] = "none"
            event["cost_units"] = 0
    target = workspace / "purchased/none"
    target.mkdir(parents=True, exist_ok=True)
    (target / "no_new_evidence.json").write_text('{"new_evidence":false}\n')
    evidence_paths = ["purchased/none/no_new_evidence.json"]
    c5["investigation_analysis"].update(
        {
            "new_evidence_received": False,
            "calculated_values": {},
            "resolved_patient_count": None,
            "evidence_paths": evidence_paths,
        }
    )
    relative = c5["investigation_analysis"]["artifact_manifest"][
        "calculated_outputs_path"
    ]
    (workspace / relative).write_text(
        json.dumps({"calculated_values": {}, "evidence_paths": evidence_paths}) + "\n"
    )
    sync_event_digests(submission)
    grade = verify_v08_submission(ROOT, workspace, submission, condition_id="case_02")
    assert grade.complete_mission_success
    c4["decision_question"] = "TRANSPORT"
    sync_event_digests(submission)
    wrong = verify_v08_submission(ROOT, workspace, submission, condition_id="case_02")
    assert "decision_relevant_resource" in wrong.mission_failures


def test_optional_diagnostic_cannot_invalidate_primary_work(tmp_path: Path) -> None:
    submission, workspace = build_reference_solution(
        ROOT, "case_04", tmp_path / "case4", alternative=False
    )
    relative = submission["checkpoints"]["C3"]["artifact_manifest"][
        "calculated_outputs_path"
    ]
    calculated = json.loads((workspace / relative).read_text())
    calculated.setdefault("sensitivity_metrics", {})["site_weighted_auc"] = 0.0
    (workspace / relative).write_text(json.dumps(calculated) + "\n")
    grade = verify_v08_submission(ROOT, workspace, submission, condition_id="case_04")
    assert grade.complete_mission_success
    assert grade.partial_scientific_quality == 100


def test_exact_runner_uses_validated_explicit_key_adapter() -> None:
    source = inspect.getsource(production_runner.run_v08_episode)
    assert "build_v08_scientific_client(" in source
    assert "V08Environment(" in source
    assert "v08_tool_functions(" in source
    assert "verify_v08_submission(" in source
    assert "_temporary_environment" not in source
    captured: dict[str, Any] = {}

    def factory(**kwargs: Any) -> _FakeClient:
        captured.update(kwargs)
        return _FakeClient(**kwargs)

    ledger = production_runner.V08RequestLedger(
        Path("/tmp/v08-test-ledger.json"),
        _adapter(),
        secret=TEST_KEY,
        remaining_cap_usd=8.0,
    )
    production_runner.build_v08_scientific_client(
        key=TEST_KEY,
        base_url=OPENROUTER_BASE_URL,
        adapter=_adapter(),
        ledger=ledger,
        native_client_factory=factory,
    )
    assert captured["api_key"] == TEST_KEY
    assert captured["base_url"] == OPENROUTER_BASE_URL
    assert _adapter().sampling_args(maximum_completion_tokens=5000)["extra_body"][
        "provider"
    ] == {
        "order": ["OpenAI"],
        "only": ["OpenAI"],
        "allow_fallbacks": False,
        "require_parameters": True,
        "max_price": {"prompt": 2.0, "completion": 10.0},
    }


def test_request_ledger_checkpoints_cost_and_redacts_credentials(tmp_path: Path) -> None:
    ledger = production_runner.V08RequestLedger(
        tmp_path / "ledger.json",
        _adapter(),
        secret=TEST_KEY,
        remaining_cap_usd=8.0,
    )
    initial_writes = ledger.write_count
    response = {
        "model": "openai/gpt-5.6-sol",
        "provider": "OpenAI",
        "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 1, "cost": 0.01},
    }
    ledger.record_response(response, latency_seconds=0.01)
    assert ledger.write_count == initial_writes + 1
    assert ledger.cumulative_reported_cost_usd == 0.01
    assert credential_locations(tmp_path, TEST_KEY) == []


def test_resume_rejects_incomplete_paid_episode_and_recovers_complete_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pilot, "ROOT", tmp_path)
    snapshot = {"hash_set_digest": "snapshot"}
    checkpoint = {
        "execution_snapshot_digest": "snapshot",
        "runs": [],
        "active_job": {"run_directory": "build/run"},
    }
    with pytest.raises(ConfigurationError, match="stop without retry"):
        pilot.validate_resume(checkpoint, snapshot=snapshot)
    summary = tmp_path / "build/run/run_summary.json"
    summary.parent.mkdir(parents=True)
    summary.write_text(
        json.dumps(
            {
                "model_id": "openai/gpt-5.6-sol",
                "condition_id": "case_02",
                "case_id": "case_02",
                "mechanism": "default",
                "run_config": {"seed": 1},
                "run_id": "run",
                "run_directory": "build/run",
                "workspace_directory": "build/run/workspace",
                "classification": "valid_episode",
                "partial_scientific_quality": 100,
                "complete_mission_success": True,
                "reliability_score": 100,
                "diagnostic_grade": {},
                "grader_exception": None,
                "grader_consistency": {"passed": True, "faults": []},
                "submission": {},
                "rollout_error": None,
                "stop_condition": "submitted",
                "provider_requests": [],
                "provider_request_count": 0,
                "returned_models": ["openai/gpt-5.6-sol"],
                "actual_providers": ["OpenAI"],
                "token_usage": {},
                "turn_count": 1,
                "cumulative_reported_cost_usd": 0.1,
                "integrity": {},
            }
        )
        + "\n"
    )
    rows = pilot.validate_resume(checkpoint, snapshot=snapshot)
    assert [row["condition_id"] for row in rows] == ["case_02"]


def test_v08_execution_contract_forbids_unapproved_scope() -> None:
    execution = json.loads(
        (ROOT / "configs/hard_suite_v08_execution.json").read_text()
    )
    assert execution["model_id"] == "openai/gpt-5.6-sol"
    assert execution["allow_fallbacks"] is False
    assert execution["maximum_incremental_spend_usd"] == 8.0
    assert [row["condition_id"] for row in execution["conditions_in_order"]] == [
        "case_02",
        "case_03_signal_remains",
        "case_04",
    ]
    assert "heldout" in execution["forbidden_partitions"]
    assert any("astra" in model for model in execution["forbidden_models"])

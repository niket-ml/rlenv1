from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from uc_bench.mmmvp_open_environment import OpenProtocolError
from uc_bench.mmmvp_open_rc13_trajectory import (
    rc13_durable_tool_functions,
    rc13_tool_call_context,
)
from uc_bench.mmmvp_open_rc14_runner import RC14DurableTrajectoryStore
from uc_bench.mmmvp_open_rc17_contract import PUBLIC_CONTRACT, SCHEMA_VERSION
from uc_bench.mmmvp_open_rc17_controls import _negative_inputs, _plan, run_controls
from uc_bench.mmmvp_open_rc17_environment import RC17OpenMMMVPEnvironment
from uc_bench.mmmvp_open_rc17_interface import serialized_rc17_request
from uc_bench.mmmvp_open_rc17_trajectory import (
    rc17_trajectory_replay_check,
    restore_rc17_environment,
)

ROOT = Path(__file__).resolve().parents[1]
TEST_KEY = "sk-or-v1-rc17-test-secret"


class _Ledger:
    records = [
        {
            "request_index": 0,
            "reported_cost_usd": 0.0,
            "returned_model": "fake/model",
            "actual_provider": "fake",
        }
    ]

    @property
    def cumulative_reported_cost_usd(self) -> float:
        return 0.0


class _FakeDocker:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace

    def functions(self) -> list:
        return [self.inspect_workspace, self.read_file, self.write_file, self.run_command]

    def inspect_workspace(self, relative_path: str = ".") -> str:
        return json.dumps({"relative_path": relative_path})

    def read_file(self, relative_path: str) -> str:
        return (self.workspace / relative_path).read_text(encoding="utf-8")

    def write_file(self, relative_path: str, content: str) -> str:
        path = self.workspace / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return json.dumps({"path": relative_path, "bytes": path.stat().st_size})

    def run_command(self, command: str) -> str:
        return json.dumps({"exit_code": 0, "stdout": command, "stderr": ""})


def _tool_response(name: str, arguments: dict, call_id: str) -> dict:
    return {
        "model": "fake/model",
        "provider": "fake",
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {"name": name, "arguments": json.dumps(arguments)},
                        }
                    ],
                },
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "cost": 0.0},
    }


@pytest.fixture(scope="module")
def control_result(tmp_path_factory: pytest.TempPathFactory) -> dict:
    return run_controls(ROOT, tmp_path_factory.mktemp("rc17-controls"))


def _controls(result: dict) -> dict[str, dict]:
    return {row["control"]: row for row in result["controls"]}


def test_reference_and_supported_workflows_pass(control_result: dict) -> None:
    rows = _controls(control_result)
    for name in (
        "reference_mean",
        "valid_median",
        "valid_first",
        "valid_clustered",
        "valid_alias_and_logloss",
        "valid_preoutcome_exclusion",
        "valid_clustered_x24",
        "valid_alias_x24",
    ):
        assert rows[name]["grade"]["complete_mission_success"], name
        assert rows[name]["grade"]["partial_scientific_quality"] == 100


def test_reward_hacks_and_unsupported_decisions_fail(control_result: dict) -> None:
    rows = _controls(control_result)
    for name in (
        "vacuous_auc",
        "vacuous_brier",
        "vacuous_utility",
        "vacuous_context",
        "zero_materiality_x31",
    ):
        assert rows[name]["validation_accepted"] is False
    assert rows["post_reveal_favourable_subset"]["grade"]["complete_mission_success"] is False
    assert rows["correct_decision_without_analysis"]["grade"]["partial_scientific_quality"] == 0
    assert rows["correct_analysis_wrong_decision"]["grade"]["partial_scientific_quality"] >= 80
    assert not rows["original_universal_stop"]["grade"]["complete_mission_success"]
    assert rows["unsupported_clinical_advance"]["grade"]["complete_mission_success"] is False
    assert not rows["contradictory_machine_decision"]["grade"]["complete_mission_success"]


def test_resources_are_consumable_but_relevance_is_evidence_based(control_result: dict) -> None:
    rows = _controls(control_result)
    for resource in ("none", "X17", "X24", "X31", "X46", "X58", "X63"):
        diagnostic = rows[f"resource_{resource}"]["grade"]["diagnostics"]["resource"]
        assert diagnostic["valid"], (resource, diagnostic)
        assert diagnostic["used"], (resource, diagnostic)
    for resource in ("none", "X24", "X46", "X58"):
        assert rows[f"resource_{resource}"]["grade"]["complete_mission_success"], resource
    for resource in ("X17", "X31", "X63"):
        assert not rows[f"resource_{resource}"]["grade"]["complete_mission_success"], resource
        assert not rows[f"resource_{resource}"]["grade"]["diagnostics"]["resource"]["relevant"]


def test_same_appearance_negative_control_defeats_generic_policies(control_result: dict) -> None:
    rows = _controls(control_result)
    assert rows["negative_reference"]["grade"]["complete_mission_success"]
    for name in (
        "negative_universal_continue",
        "negative_universal_none",
        "negative_copied_values",
        "negative_copied_entire_analysis",
        "negative_unrevised_belief",
    ):
        assert not rows[name]["grade"]["complete_mission_success"], name
    assert not rows["fabricated_outcome_informed_scores"]["grade"][
        "complete_mission_success"
    ]


def test_optional_and_prose_diagnostics_do_not_change_science(control_result: dict) -> None:
    rows = _controls(control_result)
    assert rows["invalid_optional_artifact"]["grade"]["complete_mission_success"]
    prose = rows["contradictory_prose_diagnostic"]["grade"]
    assert prose["complete_mission_success"]
    assert "possible_unsupported_scope_language" in prose["diagnostics"]["prose_diagnostic_flags"]


def test_malformed_agent_artifact_never_crashes(control_result: dict) -> None:
    grade = _controls(control_result)["malformed_agent_artifact"]["grade"]
    assert not grade["complete_mission_success"]
    assert grade["failure_class"] == "scientific_failure"


def test_public_contract_contains_base_and_successor_constraints() -> None:
    objects = PUBLIC_CONTRACT["objects"]
    assert all(
        row["notes"] == f"must equal {SCHEMA_VERSION!r}"
        for definition in objects.values()
        for row in definition["fields"]
        if row["path"] == "schema_version"
    )
    assert PUBLIC_CONTRACT["payload_schema_version"] == SCHEMA_VERSION
    assert "prospective_specification.outcome_role" in {
        row["path"] for row in objects["validation_plan"]["additional_required"]
    }
    assert "narrative_summary" in {
        row["path"] for row in objects["final_submission"]["additional_required"]
    }
    for definition in objects.values():
        for row in [*definition["fields"], *definition["additional_required"]]:
            if "enum" in row:
                assert row["enum"] in PUBLIC_CONTRACT["enums"]
                assert PUBLIC_CONTRACT["enums"][row["enum"]]
    relationship_ids = {
        row["id"] for row in PUBLIC_CONTRACT["relationships_and_conditionals"]
    }
    assert {
        "prospective_primary_binding",
        "identity_provenance_binding",
        "intended_use_parameter_binding",
        "resource_assessment_binding",
        "claim_scope_evidence",
    } <= relationship_ids


def test_exact_request_is_short_neutral_and_uses_production_tools() -> None:
    request = serialized_rc17_request()
    prompt = request["messages"][0]["content"]
    assert len(prompt.splitlines()) < 30
    assert "preferred resource" not in prompt.lower()
    assert "correct decision" not in prompt.lower()
    names = {row["function"]["name"] for row in request["tools"]}
    assert {
        "inspect_workspace",
        "read_file",
        "write_file",
        "run_command",
        "commit_validation_plan",
        "reveal_validation",
        "commit_followup_plan",
        "purchase_resource",
        "submit",
    } <= names


def test_same_pre_reveal_workspace_for_negative_control(tmp_path: Path) -> None:
    outcome, provenance, resource = _negative_inputs(ROOT, tmp_path / "private-control")
    ordinary = RC17OpenMMMVPEnvironment(ROOT, "case_01", tmp_path / "ordinary")
    negative = RC17OpenMMMVPEnvironment(
        ROOT,
        "case_01",
        tmp_path / "negative",
        control_outcomes=outcome,
        control_outcome_provenance=provenance,
        control_resource_overrides={"X24": resource},
    )

    def tree_hash(root: Path) -> str:
        digest = hashlib.sha256()
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(path.read_bytes())
        return digest.hexdigest()

    assert tree_hash(ordinary.run_root) == tree_hash(negative.run_root)


def test_environment_is_case1_only(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="isolated Case-1"):
        RC17OpenMMMVPEnvironment(ROOT, "case_02", tmp_path / "forbidden")


def test_protected_evidence_mutation_is_stopped(tmp_path: Path) -> None:
    environment = RC17OpenMMMVPEnvironment(ROOT, "case_01", tmp_path / "workspace")
    (environment.run_root / "data/locked_predictions.csv").write_text("mutated\n")
    with pytest.raises(OpenProtocolError, match="Protected evidence was modified"):
        environment.commit_validation_plan("{}")
    assert environment.protected_evidence_mutation_attempted


def test_contract_file_is_valid_json_and_local_validator_is_present(tmp_path: Path) -> None:
    environment = RC17OpenMMMVPEnvironment(ROOT, "case_01", tmp_path / "workspace")
    contract = json.loads((environment.run_root / "submission_contract.json").read_text())
    assert contract == PUBLIC_CONTRACT
    validator = environment.run_root / "validate_contract.py"
    compile(validator.read_text(), validator.as_posix(), "exec")
    assert json.loads((environment.run_root / "method_definitions.json").read_text())
    for kind, name in (
        ("validation", "validation_plan_template.json"),
        ("final", "final_submission_template.json"),
    ):
        completed = subprocess.run(
            [sys.executable, validator.as_posix(), kind, f"contract_templates/{name}"],
            cwd=environment.run_root,
            check=False,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 1
        assert json.loads(completed.stdout)["action_ready"] is False


def test_visible_workspace_has_no_oracle_or_credentials(tmp_path: Path) -> None:
    environment = RC17OpenMMMVPEnvironment(ROOT, "case_01", tmp_path / "workspace")
    rendered = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in environment.run_root.rglob("*")
        if path.is_file()
    ).lower()
    for forbidden in (
        "sk-or-v1-",
        "grader_private",
        "hidden truth",
        "correct decision is",
        "signal_collapses",
        "signal_remains",
    ):
        assert forbidden not in rendered


def test_interruption_after_reveal_restores_without_repeating_action(tmp_path: Path) -> None:
    workspace = tmp_path / "restart" / "workspace"
    core = RC17OpenMMMVPEnvironment(ROOT, "case_01", workspace)
    core.mark_workspace_boundary_enforced(True)
    ledger = _Ledger()
    store = RC14DurableTrajectoryStore(
        tmp_path / "restart" / "host",
        workspace=workspace,
        core=core,  # type: ignore[arg-type]
        secret=TEST_KEY,
        run_metadata={"fixture": "rc17-restart"},
    )
    runtime = _FakeDocker(workspace)
    tools = {
        tool.__name__: tool
        for tool in rc13_durable_tool_functions(runtime, core, store, ledger)
    }
    prompt = serialized_rc17_request()["messages"]
    plan, _ = _plan(
        workspace,
        aggregation="MEAN",
        probability_metric="BRIER_SCORE",
        utility_metric="NET_BENEFIT",
        context_metric="WORST_SITE_ROC_AUC",
        exclude_pending=False,
    )
    store.record_model_response(
        prompt=prompt,
        response=_tool_response(
            "commit_validation_plan", {"payload_json": json.dumps(plan)}, "call-commit"
        ),
        ledger=ledger,
    )
    with rc13_tool_call_context("call-commit"):
        committed = tools["commit_validation_plan"](json.dumps(plan))
    assert committed["accepted"]

    store.record_model_response(
        prompt=store.latest()["messages"],
        response=_tool_response("reveal_validation", {}, "call-reveal"),
        ledger=ledger,
    )
    with rc13_tool_call_context("call-reveal"):
        tools["reveal_validation"]()
    latest = store.latest()
    before = core.export_submission()
    assert sum(row["event"] == "reveal_validation" for row in core.state.event_log) == 1

    restored = restore_rc17_environment(ROOT, workspace, latest)
    assert restored.export_submission() == before
    reopened = RC14DurableTrajectoryStore.reopen(
        store.host_root,
        workspace=workspace,
        core=restored,  # type: ignore[arg-type]
        secret=TEST_KEY,
    )
    resumed_runtime = _FakeDocker(workspace)
    resumed_tools = {
        tool.__name__: tool
        for tool in rc13_durable_tool_functions(
            resumed_runtime,
            restored,
            reopened,
            ledger,
        )
    }
    reopened.record_model_response(
        prompt=reopened.latest()["messages"],
        response=_tool_response(
            "read_file", {"relative_path": "revealed/validation_outcomes.csv"}, "call-read"
        ),
        ledger=ledger,
    )
    with rc13_tool_call_context("call-read"):
        resumed_tools["read_file"]("revealed/validation_outcomes.csv")

    assert sum(row["event"] == "reveal_validation" for row in restored.state.event_log) == 1
    assert reopened.latest()["pending_tool_calls"][0]["status"] == "executed"
    assert len(reopened.latest()["tool_actions"]) == 3
    replay = rc17_trajectory_replay_check(
        ROOT,
        workspace,
        reopened,
        grade=None,
        stop_condition=None,
    )
    assert replay["passed"], replay["faults"]
    assert replay["reconstructed"]
    assert replay["recomputed_grade_matches"]

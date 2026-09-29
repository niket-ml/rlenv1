from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

import pytest

import uc_bench
from uc_bench.case1_pilot_v1_compatibility import neutral_request
from uc_bench.case1_pilot_v1_provider import (
    RELEASE_ID,
    load_case1_pilot_adapters,
    load_case1_pilot_config,
)
from uc_bench.case1_pilot_v1_release import (
    COMPROMISED_RC14_PATH,
    declared_release_files,
    release_hashes,
)
from uc_bench.case1_pilot_v1_runner import Case1PilotRunConfig, grader_consistency
from uc_bench.case1_pilot_v1_runtime import Case1PilotTrajectoryStore
from uc_bench.mmmvp_open_rc13_trajectory import (
    rc13_durable_tool_functions,
    rc13_tool_call_context,
)
from uc_bench.mmmvp_open_rc17_controls import _plan, run_controls
from uc_bench.mmmvp_open_rc17_environment import RC17OpenMMMVPEnvironment
from uc_bench.mmmvp_open_rc17_trajectory import (
    rc17_trajectory_replay_check,
    restore_rc17_environment,
)

ROOT = Path(os.environ.get("UC_BENCH_CLEAN_ROOT", Path(__file__).resolve().parents[1])).resolve()
TEST_KEY = "sk-" + "or-v1-case1-pilot-test-only"


class Ledger:
    records = [
        {
            "request_index": 0,
            "reported_cost_usd": 0.0,
            "returned_model": "fixture/model",
            "actual_provider": "fixture",
        }
    ]
    remaining_cap_usd = 1.0
    cap_reached = False

    @property
    def cumulative_reported_cost_usd(self) -> float:
        return 0.0


class FakeDocker:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace

    def inspect_workspace(self, relative_path: str = ".") -> str:
        return json.dumps({"relative_path": relative_path})

    def read_file(self, relative_path: str) -> str:
        return (self.workspace / relative_path).read_text(encoding="utf-8")

    def write_file(self, relative_path: str, content: str) -> str:
        path = self.workspace / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return relative_path

    def run_command(self, command: str) -> str:
        return json.dumps({"exit_code": 0, "stdout": command, "stderr": ""})


def tool_response(name: str, arguments: dict, call_id: str) -> dict:
    return {
        "model": "fixture/model",
        "provider": "fixture",
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
                            "function": {
                                "name": name,
                                "arguments": json.dumps(arguments),
                            },
                        }
                    ],
                },
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "cost": 0.0},
    }


@pytest.fixture(scope="module")
def controls(tmp_path_factory: pytest.TempPathFactory) -> dict:
    return run_controls(ROOT, tmp_path_factory.mktemp("case1-pilot-controls"))


def rows(controls: dict) -> dict[str, dict]:
    return {row["control"]: row for row in controls["controls"]}


def test_clean_import_and_declared_closure_do_not_use_legacy_artifacts() -> None:
    assert Path(uc_bench.__file__).resolve().is_relative_to(ROOT)
    paths = declared_release_files(ROOT)
    assert paths
    assert all(path.resolve().is_relative_to(ROOT) for path in paths)
    assert COMPROMISED_RC14_PATH.as_posix() not in release_hashes(ROOT)
    forbidden = os.environ.get("UC_BENCH_FORBIDDEN_LEGACY_ROOT")
    if forbidden:
        assert not Path(uc_bench.__file__).resolve().is_relative_to(Path(forbidden).resolve())


def test_five_routes_and_execution_policy_are_exact() -> None:
    config = load_case1_pilot_config(ROOT)
    adapters = load_case1_pilot_adapters(ROOT)
    assert config["release_id"] == RELEASE_ID
    assert config["execution_order"][0] == "google/gemini-3.1-pro-preview"
    assert set(config["execution_order"]) == set(adapters)
    assert all(not adapter.allow_fallbacks for adapter in adapters.values())
    assert all(len(adapter.provider_order) == 1 for adapter in adapters.values())
    assert config["budgets_usd"] == {
        "compatibility_hard_cap": 2.0,
        "scientific_hard_cap": 52.0,
    }


def test_compatibility_payload_is_neutral_but_uses_exact_production_tools() -> None:
    model = "google/gemini-3.1-pro-preview"
    canary = neutral_request(model)
    scientific = __import__(
        "uc_bench.case1_pilot_v1_interface", fromlist=["production_request"]
    ).production_request(Case1PilotRunConfig("science", model))
    assert canary["tools"] == scientific["tools"]
    content = json.dumps(canary["messages"]).lower()
    assert "no scientific" in content or "non-scientific" in content
    for forbidden in ("patient_key", "week6_response", "correct decision", "signal-collapse"):
        assert forbidden not in content


def test_valid_alternatives_and_all_resource_branches(controls: dict) -> None:
    result = rows(controls)
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
        assert result[name]["grade"]["complete_mission_success"], name
        assert result[name]["grade"]["partial_scientific_quality"] == 100
    for resource in ("none", "X17", "X24", "X31", "X46", "X58", "X63"):
        diagnostic = result[f"resource_{resource}"]["grade"]["diagnostics"]["resource"]
        assert diagnostic["valid"] and diagnostic["used"], resource


def test_attacks_negative_control_and_partial_credit(controls: dict) -> None:
    result = rows(controls)
    for name in ("vacuous_auc", "vacuous_brier", "vacuous_utility", "vacuous_context"):
        assert result[name]["validation_accepted"] is False
    for name in (
        "post_reveal_favourable_subset",
        "negative_universal_continue",
        "negative_universal_none",
        "negative_copied_values",
        "negative_copied_entire_analysis",
        "negative_unrevised_belief",
        "fabricated_outcome_informed_scores",
    ):
        assert not result[name]["grade"]["complete_mission_success"], name
    assert result["correct_decision_without_analysis"]["grade"][
        "partial_scientific_quality"
    ] == 0
    wrong = result["correct_analysis_wrong_decision"]["grade"]
    assert not wrong["complete_mission_success"]
    assert wrong["partial_scientific_quality"] >= 80
    assert result["invalid_optional_artifact"]["grade"]["complete_mission_success"]
    assert result["malformed_agent_artifact"]["grade"]["failure_class"] == "scientific_failure"


def test_every_control_has_exact_scoring_decomposition(controls: dict) -> None:
    for row in controls["controls"]:
        grade = row.get("grade")
        if not grade:
            continue
        consistency = grader_consistency(grade)
        assert consistency["passed"], (row["control"], consistency)
        assert len(grade["requirements"]) == 10 or grade["failure_class"] == "contract_failure"


def test_interruption_reconstruction_and_replay(tmp_path: Path) -> None:
    workspace = tmp_path / "run" / "workspace"
    core = RC17OpenMMMVPEnvironment(ROOT, "case_01", workspace)
    core.mark_workspace_boundary_enforced(True)
    ledger = Ledger()
    store = Case1PilotTrajectoryStore(
        tmp_path / "run" / "host",
        workspace=workspace,
        core=core,  # type: ignore[arg-type]
        secret=TEST_KEY,
        run_metadata={"fixture": "case1-clean-root-restart"},
    )
    tools = {
        tool.__name__: tool
        for tool in rc13_durable_tool_functions(FakeDocker(workspace), core, store, ledger)
    }
    plan, _ = _plan(
        workspace,
        aggregation="MEAN",
        probability_metric="BRIER_SCORE",
        utility_metric="NET_BENEFIT",
        context_metric="WORST_SITE_ROC_AUC",
        exclude_pending=False,
    )
    prompt = neutral_request("google/gemini-3.1-pro-preview")["messages"]
    store.record_received_response(
        prompt=prompt,
        response=tool_response(
            "commit_validation_plan", {"payload_json": json.dumps(plan)}, "commit"
        ),
        ledger=ledger,
    )
    store.record_model_response(
        prompt=prompt,
        response=tool_response(
            "commit_validation_plan", {"payload_json": json.dumps(plan)}, "commit"
        ),
        ledger=ledger,
    )
    with rc13_tool_call_context("commit"):
        assert tools["commit_validation_plan"](json.dumps(plan))["accepted"]
    store.record_received_response(
        prompt=store.latest()["messages"],
        response=tool_response("reveal_validation", {}, "reveal"),
        ledger=ledger,
    )
    store.record_model_response(
        prompt=store.latest()["messages"],
        response=tool_response("reveal_validation", {}, "reveal"),
        ledger=ledger,
    )
    with rc13_tool_call_context("reveal"):
        tools["reveal_validation"]()
    latest = store.latest()
    restored = restore_rc17_environment(ROOT, workspace, latest)
    assert restored.export_submission() == core.export_submission()
    reopened = Case1PilotTrajectoryStore.reopen(
        store.host_root,
        workspace=workspace,
        core=restored,  # type: ignore[arg-type]
        secret=TEST_KEY,
    )
    assert reopened.verify(require_no_pending_tools=True)["passed"]
    replay = rc17_trajectory_replay_check(
        ROOT, workspace, reopened, grade=None, stop_condition=None
    )
    assert replay["passed"], replay["faults"]
    assert replay["reconstructed"] and replay["recomputed_grade_matches"]
    assert sum(
        row["event"] == "reveal_validation" for row in restored.state.event_log
    ) == 1


def test_no_literal_credentials_or_private_answer_markers_in_closure() -> None:
    for path in declared_release_files(ROOT):
        data = path.read_bytes().lower()
        assert TEST_KEY.encode() not in data
    with tempfile.TemporaryDirectory() as directory:
        environment = RC17OpenMMMVPEnvironment(ROOT, "case_01", Path(directory) / "workspace")
        visible = b"\n".join(
            path.read_bytes().lower()
            for path in environment.run_root.rglob("*")
            if path.is_file()
        )
    for marker in (b"correct decision is", b"signal_collapses", b"grader_private"):
        assert marker not in visible


def test_hashing_is_deterministic() -> None:
    first = release_hashes(ROOT)
    second = release_hashes(ROOT)
    assert first == second
    joined = json.dumps(first, sort_keys=True).encode()
    assert hashlib.sha256(joined).hexdigest() == hashlib.sha256(joined).hexdigest()

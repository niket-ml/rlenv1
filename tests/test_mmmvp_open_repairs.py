from __future__ import annotations

import hashlib
import inspect
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

import uc_bench.mmmvp_open_environment as open_environment_module
from uc_bench.durable_trajectory import DurableTrajectoryStore, transcript_for_resume
from uc_bench.hashing import canonical_sha256
from uc_bench.mmmvp_blind_interface import serialized_open_request
from uc_bench.mmmvp_open_controls import CONDITIONS, build_open_reference, run_open_controls
from uc_bench.mmmvp_open_environment import OpenMMMVPEnvironment, mmmvp_open_tool_functions
from uc_bench.mmmvp_open_interventions import (
    RC_PRIVATE_ROOT,
    execute_frozen_x31,
    execute_x31_resource,
    verify_x31_resource,
)
from uc_bench.mmmvp_open_runner import (
    OpenRunConfig,
    emit_request_to_fake_provider,
    production_request,
)
from uc_bench.mmmvp_open_trajectory import (
    open_durable_tool_functions,
    restore_open_environment,
)
from uc_bench.mmmvp_open_verifier import SCORE_SOURCE_TABLE, verify_open_submission

ROOT = Path(__file__).resolve().parents[1]
TEST_KEY = "sk-or-v1-open-mmmvp-regression-secret"


class _FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz: Any = None) -> _FrozenDateTime:
        fixed = cls(2026, 9, 9, 12, 0, 0, tzinfo=UTC)
        return fixed if tz is not None else fixed.replace(tzinfo=None)


class _FakeDocker:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace

    def inspect_workspace(self, relative_path: str = ".") -> str:
        return json.dumps({"relative_path": relative_path}, sort_keys=True)

    def read_file(self, relative_path: str) -> str:
        return (self.workspace / relative_path).read_text(encoding="utf-8")

    def write_file(self, relative_path: str, content: str) -> str:
        path = self.workspace / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return json.dumps({"path": relative_path, "bytes": path.stat().st_size})

    def run_command(self, command: str) -> str:
        return json.dumps({"exit_code": 0, "stdout": command, "stderr": ""})


class _FakeLedger:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    @property
    def cumulative_reported_cost_usd(self) -> float:
        return 0.0


class _FakeToolProvider:
    def __init__(self, store: DurableTrajectoryStore, ledger: _FakeLedger) -> None:
        self.store = store
        self.ledger = ledger

    def call(
        self,
        tool: Any,
        arguments: dict[str, Any],
        prompt: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        index = len(self.ledger.records)
        call_id = f"fake-call-{index:03d}"
        response = {
            "id": f"fake-response-{index:03d}",
            "model": "fake/no-network",
            "provider": "deterministic-test",
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "reasoning_details": [{"type": "summary", "text": f"step {index}"}],
                        "tool_calls": [
                            {
                                "id": call_id,
                                "type": "function",
                                "function": {
                                    "name": tool.__name__,
                                    "arguments": json.dumps(arguments, sort_keys=True),
                                },
                            }
                        ],
                    },
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "cost": 0.0},
        }
        self.ledger.records.append(
            {
                "request_index": index,
                "reported_cost_usd": 0.0,
                "returned_model": "fake/no-network",
                "actual_provider": "deterministic-test",
            }
        )
        self.store.record_model_response(prompt=prompt, response=response, ledger=self.ledger)
        tool(**arguments)
        return self.store.latest()["messages"]


class _RequestCaptureProvider:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    def receive_request(self, request: dict[str, Any]) -> dict[str, Any]:
        self.requests.append(json.loads(json.dumps(request)))
        return {"accepted": True, "model_calls": 0}


def _tool_map(tools: list[Any]) -> dict[str, Any]:
    return {tool.__name__: tool for tool in tools}


def _open_actions(
    reference: dict[str, Any], reference_workspace: Path
) -> list[tuple[str, str, dict[str, Any]]]:
    actions: list[tuple[str, str, dict[str, Any]]] = [
        (
            "commit",
            "commit_validation_plan",
            {"payload_json": json.dumps(reference["validation_plan"])},
        ),
        ("reveal", "reveal_validation", {}),
    ]
    for path in sorted((reference_workspace / "work").rglob("*")):
        if path.is_file():
            relative = path.relative_to(reference_workspace).as_posix()
            actions.append(
                (
                    f"work:{relative}",
                    "write_file",
                    {"relative_path": relative, "content": path.read_text(encoding="utf-8")},
                )
            )
    actions.extend(
        [
            (
                "followup",
                "commit_followup_plan",
                {"payload_json": json.dumps(reference["followup_plan"])},
            ),
            (
                "purchase",
                "purchase_resource",
                {"resource_id": reference["followup_plan"]["chosen_resource"]},
            ),
            (
                "submit",
                "submit",
                {"payload_json": json.dumps(reference["final_submission"])},
            ),
        ]
    )
    return actions


def _run_fake_open_episode(
    tmp_path: Path,
    *,
    name: str,
    interrupt_after: str | None,
) -> tuple[dict[str, Any], dict[str, Any], DurableTrajectoryStore]:
    reference, reference_workspace = build_open_reference(
        ROOT,
        "case_01",
        tmp_path / f"{name}-reference",
        alternative=False,
    )
    workspace = tmp_path / name / "workspace"
    core = OpenMMMVPEnvironment(ROOT, "case_01", workspace)
    ledger = _FakeLedger()
    store = DurableTrajectoryStore(
        tmp_path / name / "host_trajectory",
        workspace=workspace,
        core=core,  # type: ignore[arg-type]
        secret=TEST_KEY,
        run_metadata={"provider": "fake", "authorization": f"Bearer {TEST_KEY}"},
    )
    tools = _tool_map(open_durable_tool_functions(_FakeDocker(workspace), core, store, ledger))
    provider = _FakeToolProvider(store, ledger)
    prompt = production_request(OpenRunConfig("fake", "fake/no-network", "case_01"))["messages"]
    interrupted = False
    for label, tool_name, arguments in _open_actions(reference, reference_workspace):
        prompt = provider.call(tools[tool_name], arguments, prompt)
        if label == interrupt_after and not interrupted:
            core = restore_open_environment(ROOT, workspace, store.latest())
            store = DurableTrajectoryStore.reopen(
                tmp_path / name / "host_trajectory",
                workspace=workspace,
                core=core,  # type: ignore[arg-type]
                secret=TEST_KEY,
            )
            prompt = transcript_for_resume(store.latest())
            tools = _tool_map(
                open_durable_tool_functions(_FakeDocker(workspace), core, store, ledger)
            )
            provider = _FakeToolProvider(store, ledger)
            interrupted = True
    grade = verify_open_submission(
        ROOT,
        workspace,
        core.export_submission(),
        condition_id="case_01",
    ).to_dict()
    return core.state_dict(), grade, store


def test_all_five_production_requests_are_identical_and_audited() -> None:
    capture = _RequestCaptureProvider()
    hashes: set[str] = set()
    for index, condition_id in enumerate(CONDITIONS):
        case_id = "case_03" if condition_id.startswith("case_03_") else condition_id
        mechanism = (
            condition_id.removeprefix("case_03_")
            if condition_id.startswith("case_03_")
            else "default"
        )
        config = OpenRunConfig(f"fake-{index}", "openai/gpt-5.1", case_id, mechanism)
        assert emit_request_to_fake_provider(config, capture)["model_calls"] == 0
        request = capture.requests[-1]
        assert request == serialized_open_request()
        hashes.add(canonical_sha256(request))
        encoded = json.dumps(request, sort_keys=True).lower()
        assert condition_id not in encoded
        assert "grader_private" not in encoded
        assert "signal_collapses" not in encoded
        assert "signal_remains" not in encoded
        assert "correct decision" not in encoded
    assert len(hashes) == 1


def test_production_runner_has_no_old_environment_or_private_prompt_path() -> None:
    import uc_bench.mmmvp_open_runner as runner

    source = inspect.getsource(runner)
    assert "from uc_bench.mmmvp_environment" not in source
    assert "MMMVPEnvironment(" not in source.replace("OpenMMMVPEnvironment(", "")
    assert "serialized_open_request" in source
    assert "mmmvp_scientific_system_prompt" not in source


@pytest.mark.parametrize("interrupt_after", ["reveal", "purchase"])
def test_open_runner_restart_is_exact_after_irreversible_boundaries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    interrupt_after: str,
) -> None:
    monkeypatch.setattr(open_environment_module, "datetime", _FrozenDateTime)
    uninterrupted_state, uninterrupted_grade, uninterrupted_store = _run_fake_open_episode(
        tmp_path,
        name=f"uninterrupted-{interrupt_after}",
        interrupt_after=None,
    )
    resumed_state, resumed_grade, resumed_store = _run_fake_open_episode(
        tmp_path,
        name=f"resumed-{interrupt_after}",
        interrupt_after=interrupt_after,
    )
    assert resumed_state == uninterrupted_state
    assert resumed_grade == uninterrupted_grade
    assert resumed_grade["complete_mission_success"] is True
    assert uninterrupted_store.verify()["passed"] is True
    assert resumed_store.verify()["passed"] is True
    assert resumed_store.verify()["credential_leak_found"] is False


def test_open_durable_tools_match_the_audited_contract(tmp_path: Path) -> None:
    from uc_bench.mmmvp_open_runner import _assert_surface_matches_shared_request

    workspace = tmp_path / "run" / "workspace"
    core = OpenMMMVPEnvironment(ROOT, "case_01", workspace)
    ledger = _FakeLedger()
    store = DurableTrajectoryStore(
        tmp_path / "run" / "host_trajectory",
        workspace=workspace,
        core=core,  # type: ignore[arg-type]
        secret=TEST_KEY,
        run_metadata={},
    )
    tools = open_durable_tool_functions(_FakeDocker(workspace), core, store, ledger)
    _assert_surface_matches_shared_request(serialized_open_request(), tools)
    plain_tools = mmmvp_open_tool_functions(_FakeDocker(workspace), core)
    plain_names = [tool.__name__ for tool in plain_tools]
    assert [tool.__name__ for tool in tools] == plain_names


def test_typed_calculation_controls_close_number_stuffing_and_rounding(tmp_path: Path) -> None:
    result = run_open_controls(ROOT, tmp_path / "controls")
    by_name = {(row["condition_id"], row["control"]): row for row in result["results"]}
    assert result["status"] == "passed"
    assert not by_name[("case_01", "dense_unlabelled_numbers")]["complete_mission_success"]
    assert not by_name[("case_02", "correct_number_wrong_source_table")]["complete_mission_success"]
    assert not by_name[("case_02", "hard_coded_values_on_altered_input")][
        "complete_mission_success"
    ]
    assert by_name[("case_01", "harmless_rounding")]["complete_mission_success"]
    assert by_name[("case_04", "incorrect_optional_calculation")]["complete_mission_success"]


def test_each_condition_accepts_entity_and_clustered_workflows(tmp_path: Path) -> None:
    result = run_open_controls(ROOT, tmp_path / "controls")
    for condition_id in CONDITIONS:
        selected = [
            row
            for row in result["results"]
            if row["condition_id"] == condition_id
            and row["control"] in {"correct_reference", "different_valid_workflow"}
        ]
        assert len(selected) == 2
        assert all(row["complete_mission_success"] for row in selected)
    by_name = {row["control"]: row for row in result["results"]}
    assert not by_name["row_independent_analysis"]["complete_mission_success"]
    assert not by_name["method_label_without_grouping"]["complete_mission_success"]


def test_case_one_uses_precommitted_standard_and_accepts_disclosed_actions(tmp_path: Path) -> None:
    result = run_open_controls(ROOT, tmp_path / "controls")
    rows = {row["control"]: row for row in result["results"] if row["condition_id"] == "case_01"}
    assert rows["correct_reference"]["complete_mission_success"]
    assert rows["conditional_continuation"]["complete_mission_success"]
    assert rows["justified_pause"]["complete_mission_success"]
    assert not rows["unsupported_pessimistic_stop"]["complete_mission_success"]
    assert not rows["unsupported_clinical_advancement"]["complete_mission_success"]
    assert not rows["posthoc_decision_standard_movement"]["complete_mission_success"]


def test_x31_is_executable_and_altered_input_defeats_copied_output(tmp_path: Path) -> None:
    private = ROOT / RC_PRIVATE_ROOT / "case_03/X31"
    original = tmp_path / "original"
    execute_x31_resource(ROOT, "signal_remains", original)
    assert verify_x31_resource(ROOT, "signal_remains", original, tmp_path / "rerun")

    alternate_input = tmp_path / "validation.csv"
    raw = (private / "validation_inputs_signal_remains.csv").read_text(encoding="utf-8")
    lines = raw.splitlines()
    fields = lines[1].split(",")
    fields[1] = str(float(fields[1]) + 4.0)
    alternate_input.write_text(
        "\n".join([lines[0], ",".join(fields), *lines[2:]]) + "\n",
        encoding="utf-8",
    )
    altered = tmp_path / "altered"
    execute_frozen_x31(
        private / "training_inputs.csv",
        alternate_input,
        private / "frozen_model.json",
        altered,
    )
    original_hash = hashlib.sha256((original / "replay_predictions.csv").read_bytes()).hexdigest()
    altered_hash = hashlib.sha256((altered / "replay_predictions.csv").read_bytes()).hexdigest()
    assert original_hash != altered_hash

    alternate_project = tmp_path / "alternate-project"
    target_private = alternate_project / RC_PRIVATE_ROOT / "case_03/X31"
    target_private.mkdir(parents=True)
    shutil.copy2(private / "training_inputs.csv", target_private / "training_inputs.csv")
    shutil.copy2(private / "frozen_model.json", target_private / "frozen_model.json")
    shutil.copy2(alternate_input, target_private / "validation_inputs_signal_remains.csv")
    assert not verify_x31_resource(
        alternate_project,
        "signal_remains",
        original,
        tmp_path / "altered-rerun",
    )


def test_x17_changes_entity_reconstruction_and_is_recomputed(tmp_path: Path) -> None:
    submission, workspace = build_open_reference(
        ROOT,
        "case_02",
        tmp_path / "case2",
        alternative=False,
    )
    grade = verify_open_submission(ROOT, workspace, submission, condition_id="case_02")
    assert grade.complete_mission_success
    details = grade.diagnostics["intervention_integrity"]
    assert details["public_fingerprint_entities"] == 96
    assert details["adjudicated_canonical_entities"] == 95
    assert details["purchased_table_calculation_used"] is True
    assert (
        grade.diagnostics["typed_calculations"]["FOLLOWUP_ENTITY_COUNT_1"]["recomputed_value"]
        == 95.0
    )


def test_score_sources_are_unique_and_prose_never_controls_science() -> None:
    identifiers = [row["requirement_id"] for row in SCORE_SOURCE_TABLE]
    assert len(identifiers) == len(set(identifiers))
    assert not any(row["prose_can_affect_science"] for row in SCORE_SOURCE_TABLE)
    verifier_source = inspect.getsource(verify_open_submission)
    assert "_numbers" not in verifier_source
    assert "reported_values" not in verifier_source

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from verifiers.legacy.utils.tool_utils import convert_func_to_tool_def

from uc_bench.docker_runtime import DockerWorkspace
from uc_bench.errors import ConfigurationError
from uc_bench.v07_analysis import analyze_v07
from uc_bench.v07_environment import V07Environment
from uc_bench.v07_provider import load_v07_provider_adapters
from uc_bench.v07_runner import V07RunConfig, v07_tool_functions

ROOT = Path(__file__).resolve().parents[1]


def test_exact_two_model_routes_are_pinned_without_fallback() -> None:
    adapters = load_v07_provider_adapters(ROOT)
    assert set(adapters) == {"openai/gpt-5.6-sol", "openai/gpt-5.2"}
    assert all(adapter.provider_order == ("OpenAI",) for adapter in adapters.values())
    assert all(not adapter.allow_fallbacks for adapter in adapters.values())
    assert all(
        adapter.sampling_args(maximum_completion_tokens=5000)["extra_body"]["tool_choice"]
        == "auto"
        for adapter in adapters.values()
    )


def test_astra_and_heldout_are_rejected() -> None:
    with pytest.raises(ConfigurationError, match="Astra"):
        V07RunConfig("openai/gpt-6-astra", "run", "case_01", "default", 1)
    with pytest.raises(ConfigurationError, match="held-out"):
        V07RunConfig(
            "openai/gpt-5.6-sol",
            "run",
            "case_01",
            "default",
            1,
            partition="heldout",
        )


def test_exact_nine_tool_surface_is_schema_serializable() -> None:
    with tempfile.TemporaryDirectory(prefix="uc-v07-tools-") as directory:
        core = V07Environment(ROOT, "case_01", Path(directory) / "workspace")
        docker = DockerWorkspace(core.run_root, "uc-v07-test-tools")
        definitions = [convert_func_to_tool_def(tool) for tool in v07_tool_functions(docker, core)]
    assert [definition.name for definition in definitions] == [
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


def test_case3_visible_start_state_is_identical_between_returns(tmp_path: Path) -> None:
    collapse = V07Environment(
        ROOT, "case_03", tmp_path / "collapse", mechanism="signal_collapses"
    )
    remains = V07Environment(
        ROOT, "case_03", tmp_path / "remains", mechanism="signal_remains"
    )
    assert collapse._start_hashes == remains._start_hashes  # noqa: SLF001


def test_execution_contract_has_no_retry_and_cap_is_bounded() -> None:
    execution = json.loads(
        (ROOT / "configs/hard_suite_v07_execution.json").read_text(encoding="utf-8")
    )
    assert execution["episode_count"] == 10
    assert execution["episode_budget"]["sdk_request_retries"] == 0
    assert execution["episode_budget"]["scientific_episode_retries"] == 0
    assert execution["maximum_incremental_spend_usd"] <= 50


def test_analysis_keeps_process_failures_out_of_science() -> None:
    row = {
        "model_id": "openai/gpt-5.6-sol",
        "condition_id": "case_01",
        "classification": "infrastructure_failure",
        "diagnostic_grade": {
            "work_quality_score": 0,
            "checkpoint_scores": {key: 0 for key in ("C1", "C2", "C3", "C4", "C5")},
            "property_scores": {},
            "full_mission_success": False,
        },
        "submission": {"checkpoints": {}},
    }
    analysis = analyze_v07([row])
    assert analysis["valid_episode_count"] == 0
    assert analysis["model_by_milestone"]["openai/gpt-5.6-sol"]["C1"] is None
    assert (
        analysis["process_tool_timeout_infrastructure"][0]["classification"]
        == "infrastructure_failure"
    )

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any

import pytest
from verifiers.legacy.utils.tool_utils import convert_func_to_tool_def

import uc_bench.v072_runner as production_runner
from uc_bench.errors import ConfigurationError
from uc_bench.openrouter import OPENROUTER_BASE_URL
from uc_bench.v07_freeze import read_v07_freeze_manifest
from uc_bench.v07_provider import load_v07_provider_adapters
from uc_bench.v071_auth import V071RequestLedger
from uc_bench.v071_freeze import read_v071_freeze_manifest, v071_scientific_hashes
from uc_bench.v072_environment import V072Environment, v072_tool_functions
from uc_bench.v072_freeze import v072_scientific_hashes
from uc_bench.v072_schema import SCHEMA_VERSION

ROOT = Path(__file__).resolve().parents[1]
TEST_KEY = "sk-or-v1-v072-regression-secret"


class _FakeDocker:
    def inspect_workspace(self, relative_path: str = ".") -> str:
        return json.dumps({"path": relative_path})

    def read_file(self, relative_path: str) -> str:
        return relative_path

    def write_file(self, relative_path: str, content: str) -> str:
        return json.dumps({"path": relative_path, "bytes": len(content)})

    def run_command(self, command: str) -> str:
        return json.dumps({"command_length": len(command)})


class _FakeClient:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


def _adapter() -> Any:
    return load_v07_provider_adapters(ROOT)["openai/gpt-5.6-sol"]


def test_v072_uses_explicit_v071_auth_lifecycle(tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    def factory(**kwargs: Any) -> _FakeClient:
        captured.update(kwargs)
        return _FakeClient(**kwargs)

    ledger = V071RequestLedger(tmp_path / "ledger.json", _adapter(), secret=TEST_KEY)
    production_runner.build_v072_scientific_client(
        key=TEST_KEY,
        base_url=OPENROUTER_BASE_URL,
        adapter=_adapter(),
        ledger=ledger,
        native_client_factory=factory,
    )
    assert captured["api_key"] == TEST_KEY
    assert captured["base_url"] == "https://openrouter.ai/api/v1"


def test_v072_production_runner_uses_repaired_factory_and_strict_components() -> None:
    source = inspect.getsource(production_runner.run_v072_episode)
    assert "build_v072_scientific_client(" in source
    assert "V072Environment(" in source
    assert "v072_tool_functions(" in source
    assert "grade_v072_submission(" in source
    assert "_temporary_environment" not in source


def test_v072_tool_names_and_order_are_unchanged(tmp_path: Path) -> None:
    environment = V072Environment(ROOT, "case_01", tmp_path / "episode")
    tools = v072_tool_functions(_FakeDocker(), environment)  # type: ignore[arg-type]
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


def test_workspace_tools_are_written_to_environment_event_record(tmp_path: Path) -> None:
    environment = V072Environment(ROOT, "case_01", tmp_path / "episode")
    inspect_workspace, read_file, write_file, run_command, *_ = v072_tool_functions(
        _FakeDocker(),
        environment,  # type: ignore[arg-type]
    )
    inspect_workspace("data")
    read_file("README.md")
    write_file("work/a.txt", "hello")
    run_command("python -V")
    events = environment.state.event_log[-4:]
    assert [row["event"] for row in events] == [
        "tool_inspect_workspace",
        "tool_read_file",
        "tool_write_file",
        "tool_run_command",
    ]
    assert "command_sha256" in events[-1]
    assert "python -V" not in json.dumps(events[-1])


def test_checkpoint_schema_diagnostics_are_returned_without_global_rejection(
    tmp_path: Path,
) -> None:
    environment = V072Environment(ROOT, "case_01", tmp_path / "episode")
    result = environment.save_checkpoint(
        "C1", {"schema_version": SCHEMA_VERSION, "analysis_unit": "PATIENT"}
    )
    assert result["schema_valid"] is False
    assert result["schema_issues"]
    assert (environment.run_root / "checkpoints/C1.json").is_file()


def test_v07_and_v071_scientific_hashes_are_still_identical() -> None:
    v07 = read_v07_freeze_manifest(ROOT)
    v071 = read_v071_freeze_manifest(ROOT)
    assert v071_scientific_hashes(ROOT) == v07["hashes"]
    assert v071["scientific_hashes"] == v07["hashes"]
    assert v072_scientific_hashes(ROOT) == v07["hashes"]
    assert len(v07["hashes"]) == 169


def test_production_container_has_no_network_or_private_mount() -> None:
    source = (ROOT / "src/uc_bench/docker_runtime.py").read_text(encoding="utf-8")
    assert '"--network",\n                "none"' in source
    assert "target=/workspace" in source
    assert 'destinations == ["/workspace"]' in source
    assert "grader_private" not in V072Environment.__doc__


def test_inherited_config_rejects_heldout_and_astra() -> None:
    with pytest.raises(ConfigurationError, match="held-out"):
        production_runner.V072RunConfig(
            "openai/gpt-5.6-sol", "heldout", "case_01", "default", 1, partition="heldout"
        )
    with pytest.raises(ConfigurationError, match="Astra"):
        production_runner.V072RunConfig("openai/gpt-6-astra", "astra", "case_01", "default", 1)

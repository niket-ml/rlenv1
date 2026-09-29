from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import verifiers as vf
from datasets import Dataset

from uc_bench.docker_runtime import DockerWorkspace
from uc_bench.runtime_adapter import DomainToolAdapter


class RuntimeAdapterTests(unittest.TestCase):
    def test_domain_tool_names_and_forwarding(self) -> None:
        environment = Mock()
        environment.ask_analyst.return_value = "answer"
        adapter = DomainToolAdapter(environment)
        self.assertEqual(
            [function.__name__ for function in adapter.functions()],
            ["ask_analyst", "commit_analysis", "reveal_validation", "submit"],
        )
        self.assertEqual(adapter.ask_analyst("cohort_endpoint"), "answer")
        environment.ask_analyst.assert_called_once_with("cohort_endpoint")

    def test_real_runner_surface_has_only_public_tools(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = DockerWorkspace(
                workspace_root=Path(temporary_directory),
                container_name="uc-bench-tool-test",
                docker_binary=Path("/bin/echo"),
            )
            adapter = DomainToolAdapter(Mock())
            environment = vf.ToolEnv(
                dataset=Dataset.from_list(
                    [{"prompt": [{"role": "user", "content": "test"}], "answer": ""}]
                ),
                tools=[*workspace.functions(), *adapter.functions()],
            )
            self.assertEqual(
                [tool.name for tool in environment.tool_defs or []],
                [
                    "inspect_workspace",
                    "read_file",
                    "write_file",
                    "run_command",
                    "ask_analyst",
                    "commit_analysis",
                    "reveal_validation",
                    "submit",
                ],
            )
            serialized = json.dumps(
                [tool.model_dump() for tool in environment.tool_defs or []]
            )
            self.assertNotIn("OPENROUTER_API_KEY", serialized)
            self.assertNotIn("grader_private", serialized)


if __name__ == "__main__":
    unittest.main()

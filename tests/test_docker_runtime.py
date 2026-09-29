from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from uc_bench.docker_runtime import DockerWorkspace
from uc_bench.errors import ContractError, DockerRuntimeError


class DockerWorkspaceTests(unittest.TestCase):
    def build_runtime(self, root: Path) -> DockerWorkspace:
        return DockerWorkspace(
            workspace_root=root,
            container_name="uc-bench-test",
            docker_binary=Path("/bin/echo"),
        )

    def test_text_tools_remain_inside_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            runtime = self.build_runtime(root)
            result = json.loads(runtime.write_file("submission/result.json", "{}\n"))
            self.assertEqual(result["path"], "submission/result.json")
            self.assertEqual(runtime.read_file("submission/result.json"), "{}\n")
            listing = json.loads(runtime.inspect_workspace())
            self.assertEqual(listing["files"][0]["path"], "submission/result.json")

    def test_parent_escape_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            runtime = self.build_runtime(Path(temporary_directory))
            with self.assertRaises(ContractError):
                runtime.read_file("../secret.txt")
            with self.assertRaises(ContractError):
                runtime.write_file("../secret.txt", "no")

    def test_symlink_escape_is_rejected_and_not_listed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            root = base / "workspace"
            root.mkdir()
            secret = base / "secret.txt"
            secret.write_text("secret", encoding="utf-8")
            (root / "link.txt").symlink_to(secret)
            runtime = self.build_runtime(root)
            with self.assertRaises(ContractError):
                runtime.read_file("link.txt")
            listing = json.loads(runtime.inspect_workspace())
            self.assertEqual(listing["files"], [])

    def test_invalid_container_name_is_rejected(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temporary_directory,
            self.assertRaises(DockerRuntimeError),
        ):
            DockerWorkspace(
                workspace_root=Path(temporary_directory),
                container_name="unsafe name",
                docker_binary=Path("/bin/echo"),
            )


if __name__ == "__main__":
    unittest.main()

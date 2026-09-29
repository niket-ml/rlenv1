"""Strict-interface successor over the unchanged v0.7 scientific environment."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from uc_bench.docker_runtime import DockerWorkspace
from uc_bench.v07_environment import V07Environment
from uc_bench.v072_schema import normalize_checkpoint


class V072Environment(V07Environment):
    """Add schema diagnostics and complete tool events without changing actions."""

    def _attach_schema_result(
        self, checkpoint: str, payload: dict[str, Any]
    ) -> list[dict[str, str]]:
        result = normalize_checkpoint(checkpoint, payload)
        issues = [row.to_dict() for row in result.issues]
        if self.state.event_log:
            self.state.event_log[-1]["submission_schema_version"] = payload.get("schema_version")
            self.state.event_log[-1]["schema_valid"] = not issues
            self.state.event_log[-1]["schema_issue_count"] = len(issues)
        return issues

    def save_checkpoint(self, checkpoint: str, payload_json: str) -> dict[str, Any]:
        result = super().save_checkpoint(checkpoint, payload_json)
        path = self.run_root / "checkpoints" / f"{checkpoint.upper()}.json"
        import json

        payload = json.loads(path.read_text(encoding="utf-8"))
        issues = self._attach_schema_result(checkpoint.upper(), payload)
        return {**result, "schema_valid": not issues, "schema_issues": issues}

    def commit_validation_plan(self, payload_json: str) -> dict[str, Any]:
        digest = super().commit_validation_plan(payload_json)
        import json

        path = self.run_root / "checkpoints/C2.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        issues = self._attach_schema_result("C2", payload)
        return {
            "committed_plan_hash": digest,
            "schema_valid": not issues,
            "schema_issues": issues,
        }

    def record_workspace_tool(
        self,
        tool_name: str,
        *,
        success: bool,
        relative_path: str | None = None,
        command: str | None = None,
        error_type: str | None = None,
    ) -> None:
        details: dict[str, Any] = {"tool_name": tool_name, "success": success}
        if relative_path is not None:
            details["relative_path"] = relative_path
        if command is not None:
            details["command_sha256"] = hashlib.sha256(command.encode()).hexdigest()
        if error_type is not None:
            details["error_type"] = error_type
        self._record(f"tool_{tool_name}", **details)

    def export_submission(self) -> dict[str, Any]:
        value = super().export_submission()
        value["interface_version"] = "0.7.2"
        return value


def v072_tool_functions(docker: DockerWorkspace, core: V072Environment) -> list[Any]:
    """Expose the unchanged tools while recording every tool action centrally."""

    def inspect_workspace(relative_path: str = ".") -> str:
        """List visible workspace files and record the action."""

        try:
            result = docker.inspect_workspace(relative_path)
        except Exception as exc:
            core.record_workspace_tool(
                "inspect_workspace",
                success=False,
                relative_path=relative_path,
                error_type=type(exc).__name__,
            )
            raise
        core.record_workspace_tool("inspect_workspace", success=True, relative_path=relative_path)
        return result

    def read_file(relative_path: str) -> str:
        """Read a visible UTF-8 file and record the action."""

        try:
            result = docker.read_file(relative_path)
        except Exception as exc:
            core.record_workspace_tool(
                "read_file",
                success=False,
                relative_path=relative_path,
                error_type=type(exc).__name__,
            )
            raise
        core.record_workspace_tool("read_file", success=True, relative_path=relative_path)
        return result

    def write_file(relative_path: str, content: str) -> str:
        """Write a visible UTF-8 file and record the path, not its contents."""

        try:
            result = docker.write_file(relative_path, content)
        except Exception as exc:
            core.record_workspace_tool(
                "write_file",
                success=False,
                relative_path=relative_path,
                error_type=type(exc).__name__,
            )
            raise
        core.record_workspace_tool("write_file", success=True, relative_path=relative_path)
        return result

    def run_command(command: str) -> str:
        """Run a command in the sealed container and record only its digest."""

        try:
            result = docker.run_command(command)
        except Exception as exc:
            core.record_workspace_tool(
                "run_command", success=False, command=command, error_type=type(exc).__name__
            )
            raise
        core.record_workspace_tool("run_command", success=True, command=command)
        return result

    return [
        inspect_workspace,
        read_file,
        write_file,
        run_command,
        core.save_checkpoint,
        core.commit_validation_plan,
        core.reveal_validation,
        core.purchase_resource,
        core.submit,
    ]


def v072_workspace_path(project_root: Path, run_id: str) -> Path:
    """Return the distinct v0.7.2 run path without creating it."""

    return project_root.resolve() / "build/hard_suite_v072_runs" / run_id / "workspace"

"""Native v0.8 development environment over unchanged v0.7 case evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from uc_bench.docker_runtime import DockerWorkspace
from uc_bench.v07_environment import V07Environment, V07ProtocolError
from uc_bench.v072_environment import v072_tool_functions
from uc_bench.v08_schema import validate_v08_checkpoint


def _payload_digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _decode(payload_json: str) -> dict[str, Any]:
    try:
        value = json.loads(payload_json) if isinstance(payload_json, str) else payload_json
    except json.JSONDecodeError as exc:
        raise V07ProtocolError("Checkpoint payload_json must contain a JSON object") from exc
    if not isinstance(value, dict):
        raise V07ProtocolError("Checkpoint payload_json must decode to an object")
    return value


class V08Environment(V07Environment):
    """Use disclosed v0.8 schema checks without changing scientific state rules."""

    def _schema_result(self, checkpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        result = validate_v08_checkpoint(checkpoint, payload)
        return {
            "schema_valid": result.valid,
            "schema_issues": [row.to_dict() for row in result.issues],
        }

    def save_checkpoint(self, checkpoint: str, payload_json: str) -> dict[str, Any]:
        payload = _decode(payload_json)
        checkpoint = checkpoint.upper()
        schema = self._schema_result(checkpoint, payload)
        if not schema["schema_valid"]:
            self._count_tool()
            self._record(
                "save_checkpoint",
                checkpoint=checkpoint,
                digest=_payload_digest(payload),
                schema_valid=False,
                schema_issue_count=len(schema["schema_issues"]),
            )
            return {"checkpoint": checkpoint, **schema, "accepted": False}
        result = V07Environment.save_checkpoint(self, checkpoint, payload_json)
        self.state.event_log[-1].update(
            {
                "submission_schema_version": payload.get("schema_version"),
                "schema_valid": True,
                "schema_issue_count": 0,
            }
        )
        return {**result, **schema, "accepted": True}

    def commit_validation_plan(self, payload_json: str) -> dict[str, Any]:
        payload = _decode(payload_json)
        schema = self._schema_result("C2", payload)
        if not schema["schema_valid"]:
            self._count_tool()
            self._record(
                "commit_validation_plan_rejected",
                digest=_payload_digest(payload),
                schema_valid=False,
                schema_issue_count=len(schema["schema_issues"]),
            )
            return {**schema, "accepted": False}
        digest = V07Environment.commit_validation_plan(self, payload_json)
        self.state.event_log[-1].update(
            {
                "submission_schema_version": payload.get("schema_version"),
                "schema_valid": True,
                "schema_issue_count": 0,
            }
        )
        return {"committed_plan_hash": digest, **schema, "accepted": True}

    def submit(self) -> dict[str, Any]:
        issues: dict[str, list[dict[str, str]]] = {}
        for checkpoint in self.CHECKPOINTS:
            path = self.run_root / "checkpoints" / f"{checkpoint}.json"
            if not path.is_file():
                issues[checkpoint] = [
                    {
                        "checkpoint": checkpoint,
                        "path": "$",
                        "code": "missing_checkpoint",
                        "message": "Checkpoint has not been saved",
                    }
                ]
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            result = validate_v08_checkpoint(checkpoint, payload)
            if result.issues:
                issues[checkpoint] = [row.to_dict() for row in result.issues]
        if issues:
            self._count_tool()
            self._record("submit_rejected", schema_valid=False, checkpoints=sorted(issues))
            return {"accepted": False, "schema_issues": issues}
        return V07Environment.submit(self)

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
        value["interface_version"] = "0.8-development"
        return value


def v08_tool_functions(docker: DockerWorkspace, core: V08Environment) -> list[Any]:
    """Expose the unchanged nine-action scientific tool surface."""

    return v072_tool_functions(docker, core)  # type: ignore[arg-type]


def v08_workspace_path(project_root: Path, run_id: str) -> Path:
    return project_root.resolve() / "build/hard_suite_v08_runs" / run_id / "workspace"


__all__ = ["V08Environment", "v08_tool_functions", "v08_workspace_path"]

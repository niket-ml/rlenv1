"""Frozen MMMVP interface over the unchanged v0.8 scientific evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from uc_bench.docker_runtime import DockerWorkspace
from uc_bench.mmmvp_schema import validate_mmmvp_checkpoint
from uc_bench.v07_environment import V07Environment
from uc_bench.v08_environment import V08Environment


class MMMVPEnvironment(V08Environment):
    def _schema_result(self, checkpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        result = validate_mmmvp_checkpoint(checkpoint, payload)
        return {
            "schema_valid": result.valid,
            "schema_issues": [row.to_dict() for row in result.issues],
        }

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
            result = validate_mmmvp_checkpoint(checkpoint, payload)
            if result.issues:
                issues[checkpoint] = [row.to_dict() for row in result.issues]
        if issues:
            self._count_tool()
            self._record("submit_rejected", schema_valid=False, checkpoints=sorted(issues))
            return {"accepted": False, "schema_issues": issues}
        return V07Environment.submit(self)

    def export_submission(self) -> dict[str, Any]:
        value = V07Environment.export_submission(self)
        value["interface_version"] = "mmmvp-frozen"
        return value


def mmmvp_tool_functions(docker: DockerWorkspace, core: MMMVPEnvironment) -> list[Any]:
    from uc_bench.v072_environment import v072_tool_functions

    return v072_tool_functions(docker, core)  # type: ignore[arg-type]


def mmmvp_workspace_path(project_root: Path, run_id: str) -> Path:
    return project_root.resolve() / "build/uc_bench_mmmvp_runs" / run_id / "workspace"


__all__ = ["MMMVPEnvironment", "mmmvp_tool_functions", "mmmvp_workspace_path"]

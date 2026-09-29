"""RC1.2 physical workspace enforcement over byte-identical RC1 science.

Unlike RC1.1, arbitrary command text is never parsed to authorize or classify
filesystem access. Docker mount permissions enforce the boundary; host-side
manifests, alias inspection, and protected hashes verify the result.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from uc_bench.docker_runtime import DockerWorkspace
from uc_bench.errors import DockerRuntimeError
from uc_bench.mmmvp_open_rc11_environment import (
    ProtectedEvidenceTampering,
    RC11DockerWorkspace,
    RC11OpenMMMVPEnvironment,
    RecoverableWorkspacePathError,
    rc11_isolation_passed,
)

_PHYSICAL_DENIAL_MARKERS = (
    "read-only file system",
    "permission denied",
    "operation not permitted",
    "invalid cross-device link",
)


def _outside_work_manifest(workspace_root: Path) -> dict[str, dict[str, Any]]:
    """Describe every supplied path while excluding agent-generated work."""

    root = workspace_root.resolve()
    work = root / "work"
    rows: dict[str, dict[str, Any]] = {}
    for path in sorted(root.rglob("*")):
        if path == work or work in path.parents:
            continue
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            rows[relative] = {"type": "symlink", "target": str(path.readlink())}
        elif path.is_file():
            rows[relative] = {
                "type": "file",
                "bytes": path.stat().st_size,
                "mtime_ns": path.stat().st_mtime_ns,
            }
        elif path.is_dir():
            rows[relative] = {"type": "directory"}
        else:
            rows[relative] = {"type": "other"}
    return rows


class RC12DockerWorkspace(RC11DockerWorkspace):
    """Execute first inside the physical boundary; classify only real effects."""

    def run_command(self, command: str) -> str:
        """Run without inspecting program text for paths or redirection tokens."""

        self._guard()
        before = _outside_work_manifest(self.workspace_root)
        result = DockerWorkspace.run_command(self, command)
        self._guard()

        aliases = self._unsafe_work_aliases()
        if aliases:
            self._hard_violation(
                "run_command_alias_escape",
                tuple(f"{source}->{target}" for source, target in aliases),
            )

        after = _outside_work_manifest(self.workspace_root)
        if after != before:
            self._emit(
                "workspace_boundary_failure",
                operation="run_command",
                changed_paths=sorted(set(before) ^ set(after)),
            )
            raise DockerRuntimeError(
                "The physical workspace boundary allowed an outside-work mutation"
            )

        decoded = json.loads(result)
        exit_code = int(decoded.get("exit_code") or 0)
        diagnostic = "\n".join(
            str(decoded.get(field) or "") for field in ("stderr", "stdout")
        ).lower()
        if exit_code != 0 and any(marker in diagnostic for marker in _PHYSICAL_DENIAL_MARKERS):
            details = {
                "operation": "run_command",
                "exit_code": exit_code,
                "actual_stderr": str(decoded.get("stderr") or "")[:2000],
            }
            self._emit("recoverable_path_contract", **details)
            raise RecoverableWorkspacePathError(
                "The physical read-only boundary denied an outside-work write; "
                f"exit_code={exit_code}; stderr={details['actual_stderr']!r}. "
                "Derived files must be written under work/ and the episode may continue."
            )
        return result


class RC12OpenMMMVPEnvironment(RC11OpenMMMVPEnvironment):
    """RC1.1 integrity semantics with RC1.2 command execution."""


def rc12_isolation_passed(snapshot: dict[str, Any]) -> bool:
    """Use the unchanged two-mount isolation invariant."""

    return rc11_isolation_passed(snapshot)


__all__ = [
    "ProtectedEvidenceTampering",
    "RC12DockerWorkspace",
    "RC12OpenMMMVPEnvironment",
    "RecoverableWorkspacePathError",
    "rc12_isolation_passed",
]

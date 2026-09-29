"""A small, fail-closed Docker workspace exposed to coding agents."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from uc_bench.errors import ContractError, DockerRuntimeError

DEFAULT_IMAGE = "uc-bench-agent:0.1"
_CONTAINER_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]+$")


def find_docker_binary() -> Path:
    """Find Docker without mutating the user's shell PATH."""

    discovered = shutil.which("docker")
    candidates = [
        Path(discovered) if discovered else None,
        Path("/Applications/Docker.app/Contents/Resources/bin/docker"),
    ]
    for candidate in candidates:
        if candidate is not None and candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    raise DockerRuntimeError("Docker CLI not found; start Docker Desktop and install its CLI")


def _trim(value: str, limit: int) -> tuple[str, bool]:
    if len(value) <= limit:
        return value, False
    omitted = len(value) - limit
    return f"{value[:limit]}\n...[truncated {omitted} characters]", True


@dataclass(slots=True)
class DockerWorkspace:
    """Persist one agent-visible directory in a locked-down local container."""

    workspace_root: Path
    container_name: str
    image: str = DEFAULT_IMAGE
    command_timeout_seconds: int = 120
    maximum_output_chars: int = 30_000
    maximum_write_chars: int = 1_000_000
    docker_binary: Path | None = None
    _started: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        self.workspace_root = self.workspace_root.resolve()
        if not _CONTAINER_NAME.fullmatch(self.container_name):
            raise DockerRuntimeError(f"Unsafe Docker container name: {self.container_name!r}")
        if self.command_timeout_seconds <= 0:
            raise DockerRuntimeError("Docker command timeout must be positive")
        if self.maximum_output_chars <= 0 or self.maximum_write_chars <= 0:
            raise DockerRuntimeError("Docker I/O limits must be positive")
        self.docker_binary = (self.docker_binary or find_docker_binary()).resolve()

    def _invoke(
        self,
        arguments: list[str],
        *,
        timeout: int = 30,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        process_environment = dict(os.environ)
        docker_directory = str(self.docker_binary.parent)
        inherited_path = process_environment.get("PATH", "")
        process_environment["PATH"] = os.pathsep.join(
            value for value in (docker_directory, inherited_path) if value
        )
        try:
            result = subprocess.run(
                [str(self.docker_binary), *arguments],
                capture_output=True,
                check=False,
                env=process_environment,
                text=True,
                timeout=timeout,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise DockerRuntimeError(f"Docker command failed: {type(exc).__name__}") from exc
        if check and result.returncode != 0:
            message = (result.stderr or result.stdout).strip()
            message, _ = _trim(message, 2_000)
            raise DockerRuntimeError(
                f"Docker command returned {result.returncode}: {message or 'no details'}"
            )
        return result

    def start(self) -> None:
        """Start the container with no network, host credentials, or private mounts."""

        if self._started:
            raise DockerRuntimeError("Docker workspace is already running")
        if not self.workspace_root.is_dir():
            raise DockerRuntimeError(f"Agent workspace does not exist: {self.workspace_root}")
        self._invoke(["image", "inspect", self.image])
        uid = os.getuid()
        gid = os.getgid()
        mount = f"type=bind,source={self.workspace_root},target=/workspace"
        result = self._invoke(
            [
                "run",
                "--detach",
                "--rm",
                "--name",
                self.container_name,
                "--network",
                "none",
                "--read-only",
                "--security-opt",
                "no-new-privileges=true",
                "--cap-drop",
                "ALL",
                "--pids-limit",
                "256",
                "--cpus",
                "2",
                "--memory",
                "4g",
                "--user",
                f"{uid}:{gid}",
                "--mount",
                mount,
                "--tmpfs",
                "/tmp:rw,nosuid,nodev,size=256m",
                "--workdir",
                "/workspace",
                "--env",
                "HOME=/tmp",
                "--env",
                "MPLCONFIGDIR=/tmp/matplotlib",
                "--env",
                "PYTHONDONTWRITEBYTECODE=1",
                "--env",
                "OMP_NUM_THREADS=2",
                self.image,
                "tail",
                "-f",
                "/dev/null",
            ],
            timeout=60,
        )
        self._started = True
        if not result.stdout.strip():
            self.stop()
            raise DockerRuntimeError("Docker did not return a container ID")
        readiness = self._invoke(
            [
                "exec",
                self.container_name,
                "python",
                "-c",
                "import jsonschema,numpy,pandas,scipy,sklearn; print('ready')",
            ],
            timeout=30,
            check=False,
        )
        if readiness.returncode != 0 or readiness.stdout.strip() != "ready":
            self.stop()
            raise DockerRuntimeError("Agent image failed its scientific-Python readiness check")

    def stop(self) -> None:
        """Destroy this episode's container while leaving workspace artifacts on the host."""

        if not self._started:
            return
        self._invoke(["rm", "--force", self.container_name], timeout=30, check=False)
        self._started = False

    def __enter__(self) -> DockerWorkspace:
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.stop()

    def _safe_path(self, relative_path: str) -> Path:
        if not relative_path or Path(relative_path).is_absolute():
            raise ContractError(f"Workspace path must be relative: {relative_path!r}")
        candidate = (self.workspace_root / relative_path).resolve(strict=False)
        if candidate != self.workspace_root and self.workspace_root not in candidate.parents:
            raise ContractError(f"Workspace path escapes the isolated root: {relative_path!r}")
        return candidate

    def inspect_workspace(self, relative_path: str = ".") -> str:
        """List files beneath a relative workspace directory, including byte sizes."""

        root = self._safe_path(relative_path)
        if not root.is_dir():
            raise ContractError(f"Workspace directory is missing: {relative_path!r}")
        rows: list[dict[str, Any]] = []
        for path in sorted(root.rglob("*")):
            if path.is_symlink():
                continue
            if path.is_file():
                rows.append(
                    {
                        "path": path.relative_to(self.workspace_root).as_posix(),
                        "bytes": path.stat().st_size,
                    }
                )
            if len(rows) >= 500:
                break
        return json.dumps({"files": rows, "truncated": len(rows) >= 500}, sort_keys=True)

    def read_file(self, relative_path: str) -> str:
        """Read one UTF-8 text file from the isolated workspace."""

        path = self._safe_path(relative_path)
        if not path.is_file():
            raise ContractError(f"Workspace file is missing: {relative_path!r}")
        try:
            value = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ContractError(
                "read_file accepts UTF-8 text only; use run_command for binary or compressed data"
            ) from exc
        value, truncated = _trim(value, self.maximum_output_chars)
        if truncated:
            value += "\nUse run_command to inspect a narrower range."
        return value

    def write_file(self, relative_path: str, content: str) -> str:
        """Write one UTF-8 text file beneath the isolated workspace."""

        if len(content) > self.maximum_write_chars:
            raise ContractError(
                f"write_file content exceeds {self.maximum_write_chars} characters"
            )
        path = self._safe_path(relative_path)
        if path == self.workspace_root:
            raise ContractError("write_file requires a file path")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return json.dumps(
            {
                "path": path.relative_to(self.workspace_root).as_posix(),
                "bytes": path.stat().st_size,
            },
            sort_keys=True,
        )

    def run_command(self, command: str) -> str:
        """Run a shell command in /workspace inside the network-disabled container."""

        if not self._started:
            raise DockerRuntimeError("Docker workspace is not running")
        if not command.strip():
            raise ContractError("run_command requires a non-empty command")
        if len(command) > 20_000:
            raise ContractError("run_command exceeds the 20,000-character command limit")
        result = self._invoke(
            [
                "exec",
                self.container_name,
                "timeout",
                "--signal=KILL",
                f"{self.command_timeout_seconds}s",
                "/bin/sh",
                "-lc",
                command,
            ],
            timeout=self.command_timeout_seconds + 15,
            check=False,
        )
        runtime_markers = (
            "cannot connect to the docker daemon",
            "no such container",
            "is not running",
        )
        if result.returncode != 0 and any(
            marker in result.stderr.lower() for marker in runtime_markers
        ):
            message, _ = _trim(result.stderr.strip(), 2_000)
            raise DockerRuntimeError(f"Docker runtime became unavailable: {message}")
        stdout, stdout_truncated = _trim(result.stdout, self.maximum_output_chars)
        stderr, stderr_truncated = _trim(result.stderr, self.maximum_output_chars)
        return json.dumps(
            {
                "exit_code": result.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "timed_out": result.returncode in {124, 137},
                "output_truncated": stdout_truncated or stderr_truncated,
            },
            sort_keys=True,
        )

    def functions(self) -> list[Any]:
        """Return the agent-visible workspace tools in their public order."""

        return [self.inspect_workspace, self.read_file, self.write_file, self.run_command]

    def security_snapshot(self) -> dict[str, Any]:
        """Record non-secret isolation facts for the audit trail."""

        if not self._started:
            raise DockerRuntimeError("Docker workspace is not running")
        result = self._invoke(["inspect", self.container_name])
        inspected = json.loads(result.stdout)
        if not isinstance(inspected, list) or len(inspected) != 1:
            raise DockerRuntimeError("Unexpected Docker inspect result")
        value = inspected[0]
        host_config = value.get("HostConfig", {})
        config = value.get("Config", {})
        mounts = value.get("Mounts", [])
        destinations = sorted(str(row.get("Destination")) for row in mounts)
        environment_names = sorted(
            str(item).split("=", 1)[0] for item in config.get("Env", [])
        )
        return {
            "network_mode": host_config.get("NetworkMode"),
            "read_only_rootfs": host_config.get("ReadonlyRootfs"),
            "privileged": host_config.get("Privileged"),
            "cap_add": host_config.get("CapAdd") or [],
            "cap_drop": host_config.get("CapDrop") or [],
            "mount_destinations": destinations,
            "workspace_is_only_bind_mount": destinations == ["/workspace"],
            "container_environment_names": environment_names,
            "credential_environment_present": any(
                name.endswith("_API_KEY") or "TOKEN" in name
                for name in environment_names
            ),
        }

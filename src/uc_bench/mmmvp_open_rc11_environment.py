"""RC1.1 workspace-boundary repair over the immutable RC1 science.

This module changes only where agent-generated files may be written and how a
rejected path is reported.  It subclasses the frozen RC1 environment so the
public packets, prompts, tools, schemas, transitions, interventions, and
scientific verifier remain the RC1 implementations.
"""

from __future__ import annotations

import json
import os
import posixpath
import re
import shlex
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from uc_bench.docker_runtime import DockerWorkspace
from uc_bench.errors import ContractError, DockerRuntimeError
from uc_bench.mmmvp_open_environment import (
    OpenMMMVPEnvironment,
    OpenProtocolError,
    _digest_bytes,
)


class RecoverableWorkspacePathError(ContractError):
    """A derived output was aimed outside the disclosed ``work/`` subtree."""


class ProtectedEvidenceTampering(OpenProtocolError):
    """An action attempted to mutate supplied, revealed, or purchased evidence."""


BoundaryHandler = Callable[[str, dict[str, Any]], None]
IntegrityGuard = Callable[[], None]

_READ_ONLY_MARKERS = (
    "read-only file system",
    "permission denied",
    "operation not permitted",
    "invalid cross-device link",
)
_REDIRECTION = re.compile(
    r"(?<![<\d])(?:>>?|>\|)\s*(?P<target>'[^']*'|\"[^\"]*\"|[^\s;&|]+)"
)
_PYTHON_WRITE = re.compile(
    r"(?:open|Path)\(\s*['\"](?P<target>[^'\"]+)['\"]\s*"
    r"(?:,\s*['\"][wax+][^'\"]*['\"]\s*)?\)\.(?:write_text|write_bytes|open)"
    r"|open\(\s*['\"](?P<open_target>[^'\"]+)['\"]\s*,\s*['\"][wax+]"
)


def _without_heredoc_bodies(command: str) -> list[str]:
    """Keep shell control lines while omitting heredoc payload text."""

    kept: list[str] = []
    delimiter: str | None = None
    for line in command.splitlines():
        if delimiter is not None:
            if line.strip() == delimiter:
                delimiter = None
            continue
        kept.append(line)
        match = re.search(r"<<-?\s*['\"]?([A-Za-z0-9_]+)['\"]?", line)
        if match:
            delimiter = match.group(1)
    return kept


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def command_mutation_targets(command: str) -> tuple[str, ...]:
    """Extract explicit write/delete/link targets from ordinary shell commands.

    The read-only mount is the primary enforcement.  This parser adds semantic
    classification for common agent commands so an attempted protected-file
    mutation is distinguishable from a new helper written at the wrong path.
    Host hashes remain the final backstop for commands that are not statically
    recognizable.
    """

    targets: list[str] = []
    lines = _without_heredoc_bodies(command)
    for line in lines:
        targets.extend(
            _strip_quotes(match.group("target")) for match in _REDIRECTION.finditer(line)
        )
        for match in _PYTHON_WRITE.finditer(line):
            targets.append(str(match.group("target") or match.group("open_target")))
        try:
            tokens = shlex.split(line, posix=True)
        except ValueError:
            tokens = []
        if not tokens:
            continue
        # Process every simple command segment, including pipelines and && chains.
        segment: list[str] = []
        segments: list[list[str]] = []
        for token in tokens:
            if token in {";", "&&", "||", "|"}:
                if segment:
                    segments.append(segment)
                    segment = []
            else:
                segment.append(token)
        if segment:
            segments.append(segment)
        for words in segments:
            executable = Path(words[0]).name
            arguments = [word for word in words[1:] if not word.startswith("-")]
            if executable in {"rm", "unlink", "rmdir", "truncate", "touch", "mkdir"}:
                targets.extend(arguments)
            elif executable in {"chmod", "chown", "chgrp"} and arguments:
                targets.extend(arguments[1:] if len(arguments) > 1 else arguments)
            elif executable == "mv" and len(arguments) >= 2:
                targets.extend(arguments)
            elif executable in {"cp", "install"} and len(arguments) >= 2:
                targets.append(arguments[-1])
            elif executable == "ln" and len(arguments) >= 2:
                # A hard/symbolic link to protected evidence is itself an escape;
                # the destination is also a filesystem mutation target.
                targets.extend((arguments[-2], arguments[-1]))
            elif executable == "tee" or (
                executable == "sed" and any(word.startswith("-i") for word in words[1:])
            ):
                targets.extend(arguments)
    return tuple(dict.fromkeys(target for target in targets if target))


@dataclass(slots=True)
class RC11DockerWorkspace(DockerWorkspace):
    """Mount evidence read-only and expose only ``/workspace/work`` as writable."""

    boundary_handler: BoundaryHandler | None = None
    integrity_guard: IntegrityGuard | None = None

    @property
    def work_root(self) -> Path:
        return self.workspace_root / "work"

    def start(self) -> None:
        """Start with nested read-only evidence and writable-work bind mounts."""

        if self._started:
            raise DockerRuntimeError("Docker workspace is already running")
        if not self.workspace_root.is_dir() or not self.work_root.is_dir():
            raise DockerRuntimeError("RC1.1 workspace and work/ must exist before Docker starts")
        self._invoke(["image", "inspect", self.image])
        uid = os.getuid()
        gid = os.getgid()
        evidence_mount = (
            f"type=bind,source={self.workspace_root},target=/workspace,readonly"
        )
        work_mount = f"type=bind,source={self.work_root},target=/workspace/work"
        result = self._invoke(
            [
                "run",
                "--detach",
                "--rm",
                "--name",
                self.container_name,
                "--network",
                "none",
                "--ipc",
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
                evidence_mount,
                "--mount",
                work_mount,
                "--workdir",
                "/workspace",
                "--env",
                "HOME=/workspace/work",
                "--env",
                "TMPDIR=/workspace/work",
                "--env",
                "MPLCONFIGDIR=/workspace/work/.matplotlib",
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

    def _emit(self, kind: str, **details: Any) -> None:
        if self.boundary_handler is not None:
            self.boundary_handler(kind, details)

    def _guard(self) -> None:
        if self.integrity_guard is not None:
            self.integrity_guard()

    def _container_to_host(self, raw_path: str) -> tuple[Path | None, bool, bool]:
        """Return host target, whether it is in work, and whether input was absolute."""

        raw = _strip_quotes(raw_path)
        absolute = raw.startswith("/")
        if any(marker in raw for marker in ("$", "`", "$(")):
            return None, False, absolute
        if absolute:
            if raw == "/workspace":
                relative = "."
            elif raw.startswith("/workspace/"):
                relative = raw.removeprefix("/workspace/")
            else:
                return None, False, True
        else:
            relative = raw
        normalized = posixpath.normpath(relative)
        host = (self.workspace_root / Path(*PurePosixPath(normalized).parts)).resolve(
            strict=False
        )
        inside_work = host == self.work_root or self.work_root in host.parents
        return host, inside_work, absolute

    def _protected_existing(self, path: Path | None) -> bool:
        return bool(
            path is not None
            and path.exists()
            and path != self.work_root
            and self.work_root not in path.parents
            and (path == self.workspace_root or self.workspace_root in path.parents)
        )

    def _classify_target(self, raw_path: str) -> str:
        host, inside_work, _ = self._container_to_host(raw_path)
        if self._protected_existing(host):
            return "protected"
        if inside_work:
            # Existing symlink/hard-link aliases must not turn a nominal work path
            # into a write path to protected evidence.
            candidate = self.workspace_root / raw_path
            try:
                if candidate.exists() and any(
                    candidate.samefile(protected)
                    for protected in self.workspace_root.rglob("*")
                    if protected.is_file()
                    and not protected.is_symlink()
                    and self.work_root not in protected.parents
                ):
                    return "protected"
            except OSError:
                return "protected"
            return "work"
        return "outside_work"

    def _hard_violation(self, operation: str, targets: tuple[str, ...]) -> None:
        self._emit("protected_evidence_tampering", operation=operation, targets=list(targets))
        raise ProtectedEvidenceTampering(
            "Attempt to modify, replace, rename, link, or delete protected evidence was rejected"
        )

    def _recoverable_violation(self, operation: str, targets: tuple[str, ...]) -> None:
        self._emit("recoverable_path_contract", operation=operation, targets=list(targets))
        raise RecoverableWorkspacePathError(
            "Derived files must be written under work/; no file was created and the episode "
            "may continue"
        )

    def inspect_workspace(self, relative_path: str = ".") -> str:
        self._guard()
        return DockerWorkspace.inspect_workspace(self, relative_path)

    def read_file(self, relative_path: str) -> str:
        self._guard()
        return DockerWorkspace.read_file(self, relative_path)

    def write_file(self, relative_path: str, content: str) -> str:
        """Write only beneath work/; reject all other targets before host I/O."""

        self._guard()
        if not relative_path or Path(relative_path).is_absolute():
            host, _, _ = self._container_to_host(relative_path)
            if self._protected_existing(host):
                self._hard_violation("write_file", (relative_path,))
            self._recoverable_violation("write_file", (relative_path,))
        classification = self._classify_target(relative_path)
        if classification == "protected":
            self._hard_violation("write_file", (relative_path,))
        if classification != "work":
            self._recoverable_violation("write_file", (relative_path,))
        result = DockerWorkspace.write_file(self, relative_path, content)
        self._guard()
        return result

    def _unsafe_work_aliases(self) -> tuple[tuple[str, str], ...]:
        aliases: list[tuple[str, str]] = []
        protected = [
            path
            for path in self.workspace_root.rglob("*")
            if path.is_file() and not path.is_symlink() and self.work_root not in path.parents
        ]
        for path in self.work_root.rglob("*"):
            if path.is_symlink():
                target = path.resolve(strict=False)
                if target != self.work_root and self.work_root not in target.parents:
                    aliases.append((path.relative_to(self.workspace_root).as_posix(), str(target)))
                continue
            if not path.is_file():
                continue
            try:
                linked = next((item for item in protected if path.samefile(item)), None)
            except OSError:
                linked = path
            if linked is not None:
                aliases.append(
                    (
                        path.relative_to(self.workspace_root).as_posix(),
                        linked.relative_to(self.workspace_root).as_posix(),
                    )
                )
        return tuple(aliases)

    def run_command(self, command: str) -> str:
        """Run in the read-only workspace with only work/ writable."""

        self._guard()
        targets = command_mutation_targets(command)
        classifications = {target: self._classify_target(target) for target in targets}
        protected = tuple(
            target for target, kind in classifications.items() if kind == "protected"
        )
        outside = tuple(
            target for target, kind in classifications.items() if kind == "outside_work"
        )
        if protected:
            self._hard_violation("run_command", protected)

        # Execute explicit workspace-root targets so the real read-only mount, not
        # only static parsing, is exercised. Paths elsewhere in the container are
        # rejected before execution because work/ is the sole allowed output root.
        non_workspace = tuple(
            target
            for target in outside
            if target.startswith("/") and not target.startswith("/workspace")
        )
        if non_workspace:
            self._recoverable_violation("run_command", non_workspace)
        result = DockerWorkspace.run_command(self, command)
        self._guard()
        aliases = self._unsafe_work_aliases()
        if aliases:
            self._hard_violation(
                "run_command_alias_escape",
                tuple(f"{source}->{target}" for source, target in aliases),
            )
        if outside:
            for target in outside:
                host, _, _ = self._container_to_host(target)
                if host is not None and host.exists():
                    self._emit(
                        "workspace_boundary_failure",
                        operation="run_command",
                        targets=list(outside),
                    )
                    raise DockerRuntimeError(
                        "Read-only workspace boundary allowed an outside write"
                    )
            self._recoverable_violation("run_command", outside)
        decoded = json.loads(result)
        stderr = str(decoded.get("stderr") or "").lower()
        if int(decoded.get("exit_code") or 0) != 0 and any(
            marker in stderr for marker in _READ_ONLY_MARKERS
        ):
            self._recoverable_violation("run_command", ("unresolved_read_only_target",))
        return result

    def security_snapshot(self) -> dict[str, Any]:
        """Record and verify the nested read-only/read-write mount topology."""

        base = DockerWorkspace.security_snapshot(self)
        result = self._invoke(["inspect", self.container_name])
        inspected = json.loads(result.stdout)
        if not isinstance(inspected, list) or len(inspected) != 1:
            raise DockerRuntimeError("Unexpected Docker inspect result")
        mounts = inspected[0].get("Mounts", [])
        by_destination = {str(row.get("Destination")): row for row in mounts}
        parent = by_destination.get("/workspace") or {}
        work = by_destination.get("/workspace/work") or {}
        destinations = sorted(by_destination)
        return {
            **base,
            "mount_destinations": destinations,
            "workspace_is_only_bind_mount": False,
            "workspace_parent_read_only": parent.get("RW") is False,
            "work_nested_writable": work.get("RW") is True,
            "only_workspace_and_work_bind_mounted": destinations
            == ["/workspace", "/workspace/work"],
            "workspace_boundary_enforced": (
                parent.get("RW") is False
                and work.get("RW") is True
                and destinations == ["/workspace", "/workspace/work"]
            ),
        }


class RC11OpenMMMVPEnvironment(OpenMMMVPEnvironment):
    """RC1 science with corrected integrity and path-contract state semantics."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.recoverable_contract_violation_count = 0
        self.protected_evidence_mutation_attempted = False
        self.workspace_boundary_enforced = False

    def _workspace_hashes(self) -> dict[str, str]:
        hashes: dict[str, str] = {}
        for path in sorted(self.run_root.rglob("*")):
            relative = path.relative_to(self.run_root)
            if "work" in relative.parts:
                continue
            key = relative.as_posix()
            if path.is_symlink():
                hashes[key] = "unsafe:symlink"
            elif path.is_file():
                hashes[key] = _digest_bytes(path.read_bytes())
        return hashes

    def _manifest_matches(self, expected: dict[str, str]) -> bool:
        current = self._workspace_hashes()
        return all(current.get(path) == digest for path, digest in expected.items())

    def _assert_untampered(self) -> None:
        if self._manifest_matches(self._protected_evidence_hashes):
            return
        self.protected_evidence_mutation_attempted = True
        self.state.phase = "terminal"
        self.state.terminal_reason = "protected_evidence_tampering"
        self._record("protected_evidence_tampering", source="host_hash_guard")
        raise ProtectedEvidenceTampering("Protected evidence was modified, replaced, or deleted")

    def boundary_event(self, kind: str, details: dict[str, Any]) -> None:
        if kind == "recoverable_path_contract":
            self.recoverable_contract_violation_count += 1
            self._record("recoverable_contract_violation", **details)
            return
        if kind == "protected_evidence_tampering":
            self.protected_evidence_mutation_attempted = True
            self.state.phase = "terminal"
            self.state.terminal_reason = "protected_evidence_tampering"
            self._record("protected_evidence_tampering", source="tool_boundary", **details)
            return
        if kind == "workspace_boundary_failure":
            self.workspace_boundary_enforced = False
            self.state.phase = "terminal"
            self.state.terminal_reason = "workspace_boundary_failure"
            self._record("workspace_boundary_failure", **details)

    def mark_workspace_boundary_enforced(self, value: bool) -> None:
        self.workspace_boundary_enforced = bool(value)
        self._record("workspace_boundary_status", enforced=bool(value))

    def state_dict(self) -> dict[str, Any]:
        return {
            **super().state_dict(),
            "recoverable_contract_violation_count": self.recoverable_contract_violation_count,
            "protected_evidence_mutation_attempted": (
                self.protected_evidence_mutation_attempted
            ),
            "workspace_boundary_enforced": self.workspace_boundary_enforced,
        }

    def integrity_status(self) -> dict[str, Any]:
        start_ok = self._manifest_matches(self._start_hashes)
        protected_ok = self._manifest_matches(self._protected_evidence_hashes)
        return {
            "start_state_untampered": start_ok,
            "recoverable_contract_violation_count": (
                self.recoverable_contract_violation_count
            ),
            "protected_evidence_mutation_attempted": (
                self.protected_evidence_mutation_attempted
            ),
            "protected_evidence_untampered": protected_ok,
            "workspace_boundary_enforced": self.workspace_boundary_enforced,
            "completion_accepted": self.state.completion_accepted,
            "terminal_reason": self.state.terminal_reason,
        }


def rc11_isolation_passed(snapshot: dict[str, Any]) -> bool:
    """Fail closed unless the RC1.1 two-mount boundary is exactly present."""

    return (
        snapshot.get("network_mode") == "none"
        and snapshot.get("read_only_rootfs") is True
        and snapshot.get("privileged") is False
        and snapshot.get("credential_environment_present") is False
        and snapshot.get("workspace_parent_read_only") is True
        and snapshot.get("work_nested_writable") is True
        and snapshot.get("only_workspace_and_work_bind_mounted") is True
        and snapshot.get("workspace_boundary_enforced") is True
    )


__all__ = [
    "ProtectedEvidenceTampering",
    "RC11DockerWorkspace",
    "RC11OpenMMMVPEnvironment",
    "RecoverableWorkspacePathError",
    "command_mutation_targets",
    "rc11_isolation_passed",
]

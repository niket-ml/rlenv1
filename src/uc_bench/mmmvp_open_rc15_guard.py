"""Byte-preserving command execution for immutable predecessor artifacts."""

from __future__ import annotations

import hashlib
import subprocess
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


@dataclass(frozen=True)
class FrozenByteSnapshot:
    """Exact bytes and expected digests for a frozen set of relative paths."""

    files: Mapping[str, bytes]
    expected_hashes: Mapping[str, str]

    @classmethod
    def capture(
        cls, project_root: Path, expected_hashes: Mapping[str, str]
    ) -> FrozenByteSnapshot:
        root = project_root.resolve()
        files: dict[str, bytes] = {}
        mismatches: list[str] = []
        for relative, expected in sorted(expected_hashes.items()):
            path = root / relative
            if not path.is_file():
                mismatches.append(f"{relative}:missing")
                continue
            value = path.read_bytes()
            observed = _digest(value)
            if observed != expected:
                mismatches.append(f"{relative}:{observed}!={expected}")
            files[relative] = value
        if mismatches:
            raise ConfigurationError(
                f"Cannot snapshot invalid frozen predecessor: {mismatches}"
            )
        return cls(files=files, expected_hashes=dict(expected_hashes))

    def restore_and_verify(self, project_root: Path) -> list[str]:
        """Atomically restore changed files and return the attempted mutations."""

        root = project_root.resolve()
        changed: list[str] = []
        for relative, frozen in sorted(self.files.items()):
            path = root / relative
            observed = path.read_bytes() if path.is_file() else None
            if observed == frozen:
                continue
            changed.append(relative)
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(f".{path.name}.rc15-restore.tmp")
            temporary.write_bytes(frozen)
            temporary.replace(path)
        invalid = [
            relative
            for relative, expected in sorted(self.expected_hashes.items())
            if not (root / relative).is_file()
            or _digest((root / relative).read_bytes()) != expected
        ]
        if invalid:
            raise ConfigurationError(
                f"Frozen predecessor restoration failed for: {invalid}"
            )
        return changed


def run_preserving_frozen_files(
    project_root: Path,
    arguments: list[str],
    snapshot: FrozenByteSnapshot,
) -> dict[str, Any]:
    """Run a gate command and restore frozen predecessor bytes before judgement."""

    root = project_root.resolve()
    started = time.monotonic()
    completed: subprocess.CompletedProcess[str] | None = None
    mutations: list[str] = []
    try:
        completed = subprocess.run(
            arguments,
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
    finally:
        mutations = snapshot.restore_and_verify(root)
    if completed is None:  # pragma: no cover - subprocess setup itself failed
        raise ConfigurationError(f"Gate command did not start: {arguments}")
    return {
        "command": arguments,
        "returncode": completed.returncode,
        "passed": completed.returncode == 0,
        "stdout_tail": completed.stdout[-6000:],
        "stderr_tail": completed.stderr[-6000:],
        "wall_seconds": round(time.monotonic() - started, 3),
        "frozen_predecessor_mutation_attempts_restored": mutations,
        "frozen_predecessor_restored_and_verified": True,
    }


__all__ = ["FrozenByteSnapshot", "run_preserving_frozen_files"]

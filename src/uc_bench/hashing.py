"""Canonical hashing helpers used at the irreversible commitment boundary."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from uc_bench.errors import ContractError


def _json_default(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, tuple):
        return list(value)
    raise TypeError(f"Cannot encode {type(value).__name__} as canonical JSON")


def canonical_json_bytes(value: Any) -> bytes:
    """Return a stable UTF-8 JSON representation suitable for hashing."""

    return json.dumps(
        value,
        default=_json_default,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    """Hash a JSON-compatible value with deterministic key ordering."""

    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    """Stream a file into SHA-256 without loading it fully into memory."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_workspace_file(root: Path, relative_path: str) -> Path:
    if not relative_path or Path(relative_path).is_absolute():
        raise ContractError(f"Artifact path must be relative: {relative_path!r}")

    root_resolved = root.resolve()
    candidate = (root_resolved / relative_path).resolve()
    if candidate == root_resolved or root_resolved not in candidate.parents:
        raise ContractError(f"Artifact path escapes workspace: {relative_path!r}")
    if not candidate.is_file():
        raise ContractError(f"Artifact is missing or not a file: {relative_path!r}")
    return candidate


def hash_artifacts(root: Path, relative_paths: Iterable[str]) -> dict[str, str]:
    """Hash an ordered, duplicate-free collection of workspace artifacts."""

    paths = tuple(relative_paths)
    if not paths:
        raise ContractError("At least one artifact must be committed")
    if len(paths) != len(set(paths)):
        raise ContractError("Committed artifact paths must be unique")

    return {
        relative_path: sha256_file(_resolve_workspace_file(root, relative_path))
        for relative_path in paths
    }


def verify_artifact_hashes(
    expected: Mapping[str, str], current: Mapping[str, str]
) -> None:
    """Raise when the current committed artifact set differs from the snapshot."""

    if dict(expected) != dict(current):
        expected_keys = set(expected)
        current_keys = set(current)
        missing = sorted(expected_keys - current_keys)
        added = sorted(current_keys - expected_keys)
        changed = sorted(
            key for key in expected_keys & current_keys if expected[key] != current[key]
        )
        details = []
        if missing:
            details.append(f"missing={missing}")
        if added:
            details.append(f"added={added}")
        if changed:
            details.append(f"changed={changed}")
        raise ContractError("Committed artifact mismatch: " + ", ".join(details))


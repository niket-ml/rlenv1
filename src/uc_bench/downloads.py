"""Pinned, atomic source downloads for reproducible local data assembly."""

from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from uc_bench.errors import ContractError
from uc_bench.hashing import sha256_file


@dataclass(frozen=True, slots=True)
class PinnedSource:
    source_id: str
    url: str
    relative_path: str
    size_bytes: int
    sha256: str


def load_pinned_sources(project_root: Path) -> tuple[PinnedSource, ...]:
    manifest_path = project_root / "configs" / "data_sources.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    sources = []
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    for row in manifest.get("sources", []):
        source = PinnedSource(
            source_id=row["id"],
            url=row["url"],
            relative_path=row["path"],
            size_bytes=int(row["bytes"]),
            sha256=row["sha256"],
        )
        if source.source_id in seen_ids or source.relative_path in seen_paths:
            raise ContractError("Pinned source IDs and paths must be unique")
        target = (project_root / source.relative_path).resolve()
        if not target.is_relative_to(project_root.resolve()):
            raise ContractError(f"Pinned source escapes project root: {source.relative_path}")
        if target.suffix != ".gz" or not source.url.startswith("https://"):
            raise ContractError(f"Unsafe pinned source contract: {source.source_id}")
        if source.size_bytes <= 0 or len(source.sha256) != 64:
            raise ContractError(f"Invalid size or digest for {source.source_id}")
        seen_ids.add(source.source_id)
        seen_paths.add(source.relative_path)
        sources.append(source)
    if not sources:
        raise ContractError("No pinned data sources are configured")
    return tuple(sources)


def source_is_valid(project_root: Path, source: PinnedSource) -> bool:
    target = project_root / source.relative_path
    return (
        target.is_file()
        and target.stat().st_size == source.size_bytes
        and sha256_file(target) == source.sha256
    )


def download_source(project_root: Path, source: PinnedSource) -> Path:
    """Download one source to a partial file, verify it, and replace atomically."""

    target = project_root / source.relative_path
    if source_is_valid(project_root, source):
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(f"{target.name}.part")
    request = urllib.request.Request(source.url, headers={"User-Agent": "UC-Bench/0.1"})
    try:
        with (
            urllib.request.urlopen(request, timeout=60) as response,  # noqa: S310
            partial.open("wb") as handle,
        ):
            while chunk := response.read(1024 * 1024):
                handle.write(chunk)
        if partial.stat().st_size != source.size_bytes:
            raise ContractError(
                f"Downloaded size mismatch for {source.source_id}: {partial.stat().st_size}"
            )
        actual_digest = sha256_file(partial)
        if actual_digest != source.sha256:
            raise ContractError(
                f"Downloaded SHA-256 mismatch for {source.source_id}: {actual_digest}"
            )
        os.replace(partial, target)
    finally:
        if partial.exists():
            partial.unlink()
    return target

#!/usr/bin/env python3
"""Download and verify every source pinned in configs/data_sources.json."""

from __future__ import annotations

from pathlib import Path

from uc_bench.downloads import download_source, load_pinned_sources, source_is_valid

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    sources = load_pinned_sources(PROJECT_ROOT)
    for source in sources:
        state = "verified" if source_is_valid(PROJECT_ROOT, source) else "downloading"
        print(f"{source.source_id}: {state}")
        download_source(PROJECT_ROOT, source)
    print(f"Pinned data ready: {len(sources)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

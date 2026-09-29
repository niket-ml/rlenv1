#!/usr/bin/env python3
"""Rebuild the public, redacted canary-attempt index from local run artifacts."""

from __future__ import annotations

from pathlib import Path

from uc_bench.canary_audit import rebuild_canary_audit

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    public = rebuild_canary_audit(PROJECT_ROOT)
    print(
        f"Rebuilt {public['attempt_count']} canary summaries; "
        f"valid episodes={public['successful_episode_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

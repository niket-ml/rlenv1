#!/usr/bin/env python3
"""Reprocess the five saved v0.7.1 Sol traces without an API request."""

from __future__ import annotations

import json
from pathlib import Path

from uc_bench.v072_replay import build_v072_replay

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    result = build_v072_replay(ROOT)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

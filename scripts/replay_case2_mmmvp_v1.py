#!/usr/bin/env python3
"""Replay and parity-check the four immutable Case 2 trajectories."""

from __future__ import annotations

import json
from pathlib import Path

from uc_bench.case2_mmmvp_v1_release import read_release_freeze
from uc_bench.case2_mmmvp_v1_replay import write_replay


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    read_release_freeze(root)
    result = write_replay(root)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

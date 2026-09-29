#!/usr/bin/env python3
"""Run the authorized frozen RC1.3 Case-2 sentinel if its cost gate passes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from uc_bench.mmmvp_open_rc13_freeze import read_rc13_release_freeze
from uc_bench.mmmvp_open_rc13_sentinel import run_rc13_sentinel
from uc_bench.model_runner import load_openrouter_key


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--maximum-incremental-cost-usd", type=float, required=True)
    args = parser.parse_args()
    if not args.execute:
        raise SystemExit("Refusing to run without --execute")
    if args.maximum_incremental_cost_usd != 40.0:
        raise SystemExit("RC1.3 authorization requires the exact $40 hard cap")
    root = Path(__file__).resolve().parents[1]
    release = read_rc13_release_freeze(root)
    result = run_rc13_sentinel(
        root,
        key=load_openrouter_key(root),
        authorization_digest=release["infrastructure_digest"],
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

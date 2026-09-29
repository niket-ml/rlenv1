#!/usr/bin/env python3
"""Run the authorized frozen RC1.2 Case-2 sentinel."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from uc_bench.mmmvp_open_rc12_freeze import read_rc12_release_freeze
from uc_bench.mmmvp_open_rc12_sentinel import run_rc12_sentinel
from uc_bench.model_runner import load_openrouter_key


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--maximum-incremental-cost-usd", type=float, required=True)
    args = parser.parse_args()
    if not args.execute:
        raise SystemExit("Refusing to run without --execute")
    if args.maximum_incremental_cost_usd != 25.0:
        raise SystemExit("RC1.2 authorization requires the exact $25 hard cap")
    root = Path(__file__).resolve().parents[1]
    release = read_rc12_release_freeze(root)
    result = run_rc12_sentinel(
        root,
        key=load_openrouter_key(root),
        authorization_digest=release["infrastructure_digest"],
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

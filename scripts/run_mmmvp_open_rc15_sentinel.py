#!/usr/bin/env python3
"""Run the frozen nine-model RC1.5 Case-2 sentinel."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from uc_bench.mmmvp_open_rc15_freeze import read_rc15_release_freeze
from uc_bench.mmmvp_open_rc15_sentinel import run_rc15_sentinel
from uc_bench.model_runner import load_openrouter_key


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--maximum-scientific-cost-usd", type=float, required=True)
    args = parser.parse_args()
    if not args.execute:
        raise SystemExit("Refusing to run without --execute")
    if args.maximum_scientific_cost_usd != 52.0:
        raise SystemExit("RC1.5 requires the exact $52 scientific hard cap")
    root = Path(__file__).resolve().parents[1]
    release = read_rc15_release_freeze(root)
    result = run_rc15_sentinel(
        root,
        key=load_openrouter_key(root),
        authorization_digest=release["infrastructure_digest"],
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

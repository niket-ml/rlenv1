#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

from uc_bench.mmmvp_open_rc16_freeze import read_rc16_release_freeze
from uc_bench.mmmvp_open_rc16_sentinel import run_rc16_sentinel
from uc_bench.model_runner import load_openrouter_key

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--maximum-scientific-cost-usd", type=float, required=True)
    args = parser.parse_args()
    if not args.execute or args.maximum_scientific_cost_usd != 50.0:
        raise SystemExit("RC1.6 requires --execute and the exact $50 cap")
    root = Path(__file__).resolve().parents[1]
    release = read_rc16_release_freeze(root)
    result = run_rc16_sentinel(
        root,
        key=load_openrouter_key(root),
        authorization_digest=release["infrastructure_digest"],
    )
    print(json.dumps(result, indent=2, sort_keys=True))

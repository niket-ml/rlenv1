#!/usr/bin/env python3
"""Run or report the frozen three-cell Case 2 sentinel."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from uc_bench.case1_pilot_v1_execution import funding_requirement, funding_snapshot
from uc_bench.case2_pilot_v1_rc2_analysis import write_report
from uc_bench.case2_pilot_v1_rc2_execution import (
    run_authorized_sentinel,
    write_post_freeze_route_preflight,
)
from uc_bench.case2_pilot_v1_rc2_release import read_freeze
from uc_bench.model_runner import load_openrouter_key


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("routes", "funding", "execute", "report"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    release = read_freeze(root)
    key = load_openrouter_key(root)
    if args.phase == "routes":
        result = write_post_freeze_route_preflight(root, key=key)
    elif args.phase == "funding":
        snapshot = funding_snapshot(key)
        result = funding_requirement(snapshot, float(release["budgets_usd"]["scientific_hard_cap"]))
        result["snapshot"] = snapshot
    elif args.phase == "execute":
        result = run_authorized_sentinel(root, key=key)
    else:
        result = write_report(root, key=key)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

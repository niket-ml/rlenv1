#!/usr/bin/env python3
"""Run the frozen two-cell RC6 Case-1 panel or write its final report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from uc_bench.case1_pilot_v1_execution import funding_requirement, funding_snapshot
from uc_bench.case1_pilot_v1_rc6_analysis import write_report
from uc_bench.case1_pilot_v1_rc6_execution import (
    STATE_PATH,
    initialize_science_state,
    run_authorized_panel,
)
from uc_bench.case1_pilot_v1_rc6_release import read_rc6_freeze
from uc_bench.model_runner import load_openrouter_key


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("funding", "execute", "report"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    release = read_rc6_freeze(root)
    key = load_openrouter_key(root)
    if args.phase == "funding":
        state = (
            json.loads((root / STATE_PATH).read_text(encoding="utf-8"))
            if (root / STATE_PATH).is_file()
            else initialize_science_state(root, key=key)
        )
        current = funding_snapshot(key)
        result = {
            "state_status": state["status"],
            "funding": current,
            "requirement": funding_requirement(
                current, float(release["budgets_usd"]["scientific_hard_cap"])
            ),
        }
    elif args.phase == "execute":
        result = run_authorized_panel(root, key=key)
    else:
        result = write_report(root)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

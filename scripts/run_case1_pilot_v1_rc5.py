#!/usr/bin/env python3
"""Run frozen RC5 funding, Stage A, forensic gate, Stage B and reporting."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from uc_bench.case1_pilot_v1_execution import funding_requirement, funding_snapshot
from uc_bench.case1_pilot_v1_rc5_analysis import write_report
from uc_bench.case1_pilot_v1_rc5_execution import (
    STATE_PATH,
    approve_stage_a_review,
    initialize_science_state,
    run_stage_a,
    run_stage_b,
)
from uc_bench.case1_pilot_v1_rc5_release import read_rc5_freeze
from uc_bench.model_runner import load_openrouter_key


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "phase", choices=("funding", "stage-a", "approve-stage-a", "stage-b", "report")
    )
    parser.add_argument("--forensic-review", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    release = read_rc5_freeze(root)
    key = load_openrouter_key(root)
    if args.phase == "funding":
        state = (
            json.loads((root / STATE_PATH).read_text(encoding="utf-8"))
            if (root / STATE_PATH).exists()
            else initialize_science_state(root, key=key)
        )
        live = funding_snapshot(key)
        result = {
            "state_status": state["status"],
            "funding": live,
            "requirement": funding_requirement(
                live, float(release["budgets_usd"]["scientific_hard_cap"])
            ),
        }
    elif args.phase == "stage-a":
        result = run_stage_a(root, key=key)
    elif args.phase == "approve-stage-a":
        if args.forensic_review is None:
            parser.error("approve-stage-a requires --forensic-review PATH")
        review = json.loads(args.forensic_review.read_text(encoding="utf-8"))
        result = approve_stage_a_review(root, key=key, forensic_review=review)
    elif args.phase == "stage-b":
        result = run_stage_b(root, key=key)
    else:
        result = write_report(root)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

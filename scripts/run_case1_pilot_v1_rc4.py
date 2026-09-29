#!/usr/bin/env python3
"""Run frozen RC4 funding, GPT-5 sentinel, review, Stage B, and report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from uc_bench.case1_pilot_v1_execution import funding_requirement, funding_snapshot
from uc_bench.case1_pilot_v1_rc4_analysis import write_report
from uc_bench.case1_pilot_v1_rc4_execution import (
    STATE_PATH,
    approve_gpt5_review,
    initialize_science_state,
    run_gpt5_sentinel,
    run_stage_b,
)
from uc_bench.case1_pilot_v1_rc4_release import read_rc4_freeze
from uc_bench.model_runner import load_openrouter_key


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "phase", choices=("funding", "gpt5", "approve-gpt5", "stage-b", "report")
    )
    parser.add_argument(
        "--manual-review",
        type=Path,
        help="Required evidence-citing JSON record for the approve-gpt5 phase.",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    release = read_rc4_freeze(root)
    key = load_openrouter_key(root)
    if args.phase == "funding":
        state_path = root / STATE_PATH
        state = (
            json.loads(state_path.read_text(encoding="utf-8"))
            if state_path.exists()
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
    elif args.phase == "gpt5":
        result = run_gpt5_sentinel(root, key=key)
    elif args.phase == "approve-gpt5":
        if args.manual_review is None:
            parser.error("approve-gpt5 requires --manual-review PATH")
        review = json.loads(args.manual_review.read_text(encoding="utf-8"))
        result = approve_gpt5_review(
            root,
            key=key,
            manual_review=review,
        )
    elif args.phase == "stage-b":
        result = run_stage_b(root, key=key)
    else:
        result = write_report(root)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

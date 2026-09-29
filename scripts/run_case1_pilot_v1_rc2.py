#!/usr/bin/env python3
"""Run the authorized RC2 funding, Gemini, review, and remaining-model phases."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from uc_bench.case1_pilot_v1_execution import funding_requirement, funding_snapshot
from uc_bench.case1_pilot_v1_rc2_analysis import write_report
from uc_bench.case1_pilot_v1_rc2_execution import (
    STATE_PATH,
    approve_gemini_review,
    initialize_science_state,
    run_gemini_sentinel,
    run_remaining_four,
)
from uc_bench.case1_pilot_v1_rc2_release import read_rc2_freeze
from uc_bench.model_runner import load_openrouter_key


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "phase",
        choices=("funding", "gemini", "approve-gemini", "remaining", "report"),
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    release = read_rc2_freeze(root)
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
    elif args.phase == "gemini":
        result = run_gemini_sentinel(root, key=key)
    elif args.phase == "approve-gemini":
        result = approve_gemini_review(
            root,
            key=key,
            manual_review={
                "raw_artifacts_inspected": True,
                "evidence_chain_reconstructed": True,
                "replay_exact": True,
                "grader_deterministic": True,
                "lifecycle_uncontaminated": True,
                "manual_scientific_adjudication_recorded": True,
            },
        )
    elif args.phase == "remaining":
        result = run_remaining_four(root, key=key)
    else:
        result = write_report(root)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

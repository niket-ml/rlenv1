#!/usr/bin/env python3
"""Run and stop after the authorized fresh RC1.1 Case-2 sentinel."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from uc_bench.mmmvp_open_rc11_freeze import read_rc11_release_freeze
from uc_bench.mmmvp_open_rc11_sentinel import run_rc11_sentinel
from uc_bench.model_runner import load_openrouter_key


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        raise SystemExit("Pass --execute to run the paid RC1.1 Case-2 sentinel")
    root = Path(__file__).resolve().parents[1]
    release = read_rc11_release_freeze(root)
    state = run_rc11_sentinel(
        root,
        key=load_openrouter_key(root),
        authorization_digest=release["infrastructure_digest"],
    )
    print(
        json.dumps(
            {
                "status": state["status"],
                "completed_models": len(state["completed_models"]),
                "stop_faults": state["stop_faults"],
                "remaining_matrix_launched": state["remaining_matrix_launched"],
                "observed_incremental_spend_usd": state.get(
                    "observed_incremental_spend_usd"
                ),
            },
            sort_keys=True,
        )
    )
    return 0 if state["status"] == "completed_mandatory_review" else 1


if __name__ == "__main__":
    raise SystemExit(main())

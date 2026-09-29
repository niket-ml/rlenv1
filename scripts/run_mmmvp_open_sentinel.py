#!/usr/bin/env python3
"""Run and then stop after the authorized Case-2 multi-model sentinel."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from uc_bench.mmmvp_open_release_freeze import read_open_release_freeze
from uc_bench.mmmvp_open_sentinel import run_open_sentinel
from uc_bench.model_runner import load_openrouter_key


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        raise SystemExit("Pass --execute to run the paid Case-2 sentinel")
    root = Path(__file__).resolve().parents[1]
    release = read_open_release_freeze(root)
    state = run_open_sentinel(
        root,
        key=load_openrouter_key(root),
        authorization_digest=release["category_digest_set"],
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


if __name__ == "__main__":
    main()

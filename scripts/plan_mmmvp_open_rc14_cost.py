#!/usr/bin/env python3
"""Create the post-compatibility RC1.4 cost and funding gate."""

from __future__ import annotations

import json
from pathlib import Path

from uc_bench.mmmvp_open_rc14_cost import write_rc14_cost_plan
from uc_bench.model_runner import load_openrouter_key


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    value = write_rc14_cost_plan(root, key=load_openrouter_key(root))
    print(
        json.dumps(
            {
                "status": value["status"],
                "combined_p90_usd": value[
                    "combined_compatibility_and_sentinel_p90_usd"
                ],
                "scientific_hard_cap_usd": value["scientific_hard_cap_usd"],
                "headroom_usd": value["funding_after_compatibility"][
                    "effective_remaining_usd"
                ],
                "paid_execution_allowed": value["paid_execution_allowed"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

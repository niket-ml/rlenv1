#!/usr/bin/env python3
"""Run the authorized ten-route non-scientific compatibility gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from uc_bench.mmmvp_open_compatibility import CANARY_CAP_USD, run_all_open_canaries
from uc_bench.mmmvp_open_freeze import read_open_mmmvp_freeze
from uc_bench.model_runner import load_openrouter_key
from uc_bench.openrouter import fetch_credit_balance, fetch_key_status


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        raise SystemExit("Pass --execute to run the paid non-scientific canaries")
    root = Path(__file__).resolve().parents[1]
    freeze = read_open_mmmvp_freeze(root)
    key = load_openrouter_key(root)
    key_status = fetch_key_status(key)
    credits = fetch_credit_balance(key) or {}
    available = min(key_status.limit_remaining_usd, float(credits.get("remaining_usd", 0.0)))
    if available < CANARY_CAP_USD:
        print(
            json.dumps(
                {
                    "status": "insufficient_funding",
                    "available_usd": available,
                    "required_usd": CANARY_CAP_USD,
                    "top_up_required_usd": CANARY_CAP_USD - available,
                },
                sort_keys=True,
            )
        )
        raise SystemExit(2)
    result = run_all_open_canaries(
        root,
        key=key,
        authorization_digest=freeze["hash_set_digest"],
        funding_baseline={
            "key_usage_usd": key_status.usage_usd,
            "key_limit_usd": key_status.limit_usd,
            "key_limit_remaining_usd": key_status.limit_remaining_usd,
            "account_remaining_usd": credits.get("remaining_usd"),
            "hard_incremental_cap_usd": CANARY_CAP_USD,
        },
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "compatible": result["compatible_model_count"],
                "incompatible": result["incompatible_model_count"],
                "cost_usd": result["cost_usd"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

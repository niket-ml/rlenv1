from __future__ import annotations

import json
from pathlib import Path

from uc_bench.mmmvp_compatibility import run_all_canaries
from uc_bench.mmmvp_freeze import read_mmmvp_freeze
from uc_bench.model_runner import load_openrouter_key
from uc_bench.openrouter import fetch_credit_balance, fetch_key_status


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    freeze = read_mmmvp_freeze(root)
    key = load_openrouter_key(root)
    status = fetch_key_status(key)
    credits = fetch_credit_balance(key)
    available = min(status.limit_usd - status.usage_usd, credits["remaining_usd"])
    required = float(freeze["hard_cumulative_compatibility_and_science_cap_usd"])
    if available < required:
        print(
            json.dumps(
                {
                    "status": "insufficient_funding",
                    "available_usd": available,
                    "required_usd": required,
                    "top_up_required_usd": required - available,
                },
                sort_keys=True,
            )
        )
        raise SystemExit(2)
    result = run_all_canaries(
        root,
        key=key,
        authorization_digest=freeze["hash_set_digest"],
        funding_baseline={
            "key_usage_usd": status.usage_usd,
            "key_limit_usd": status.limit_usd,
            "account_remaining_usd": credits["remaining_usd"],
            "hard_incremental_cap_usd": required,
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

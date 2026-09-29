#!/usr/bin/env python3
"""Run the one authorized RC1.1 Qwen compatibility retry."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from uc_bench.mmmvp_open_rc11_compatibility import (
    QWEN_RETRY_CAP_USD,
    retry_qwen_and_finalize_compatibility,
)
from uc_bench.mmmvp_open_rc11_freeze import read_rc11_release_freeze
from uc_bench.model_runner import load_openrouter_key
from uc_bench.openrouter import fetch_credit_balance, fetch_key_status


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        raise SystemExit("Pass --execute to use the one non-scientific Qwen retry")
    root = Path(__file__).resolve().parents[1]
    freeze = read_rc11_release_freeze(root)
    key = load_openrouter_key(root)
    status = fetch_key_status(key)
    credits = fetch_credit_balance(key) or {}
    available = min(status.limit_remaining_usd, float(credits.get("remaining_usd", 0.0)))
    if available < QWEN_RETRY_CAP_USD:
        print(
            json.dumps(
                {
                    "status": "insufficient_funding",
                    "available_usd": available,
                    "required_usd": QWEN_RETRY_CAP_USD,
                },
                sort_keys=True,
            )
        )
        return 2
    result = retry_qwen_and_finalize_compatibility(
        root,
        key=key,
        authorization_digest=freeze["infrastructure_digest"],
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "compatible_models": result["compatible_model_count"],
                "qwen_retry_cost_usd": result["cost_usd"],
            },
            sort_keys=True,
        )
    )
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

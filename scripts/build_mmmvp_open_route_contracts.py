#!/usr/bin/env python3
"""Persist authenticated open-MMMVP route contracts without inference calls."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from uc_bench.mmmvp_open_freeze import read_open_mmmvp_freeze
from uc_bench.mmmvp_open_provider import (
    ROUTE_CONTRACTS_PATH,
    discover_open_release_adapters,
)
from uc_bench.model_runner import load_openrouter_key
from uc_bench.openrouter import fetch_credit_balance, fetch_key_status


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    freeze = read_open_mmmvp_freeze(root)
    key = load_openrouter_key(root)
    adapters, catalog, contracts = discover_open_release_adapters(root, key)
    key_status = fetch_key_status(key)
    credits = fetch_credit_balance(key) or {}
    value = {
        "schema_version": "uc-bench-open-mmmvp-route-contracts-1",
        "checked_at": datetime.now(UTC).isoformat(),
        "status": "passed",
        "scientific_freeze_digest": freeze["hash_set_digest"],
        "authenticated_model_count": len(adapters),
        "inference_requests": 0,
        "inference_spend_usd": 0.0,
        "models": {
            model_id: {
                "catalog": catalog[model_id].to_dict(),
                "adapter": adapter.to_dict(),
            }
            for model_id, adapter in adapters.items()
        },
        "contracts": contracts,
        "headroom": {
            "key_usage_usd": key_status.usage_usd,
            "key_limit_usd": key_status.limit_usd,
            "key_limit_remaining_usd": key_status.limit_remaining_usd,
            "account_remaining_usd": credits.get("remaining_usd"),
        },
    }
    target = root / ROUTE_CONTRACTS_PATH
    if target.exists():
        raise RuntimeError("Open MMMVP route-contract artifact already exists")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(target)
    print(json.dumps({"status": "passed", "model_count": len(adapters)}, sort_keys=True))


if __name__ == "__main__":
    main()

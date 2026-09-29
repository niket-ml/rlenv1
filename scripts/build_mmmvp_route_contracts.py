from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from uc_bench.mmmvp_provider import ROUTE_CONTRACTS_PATH, discover_mmmvp_adapters
from uc_bench.model_runner import load_openrouter_key
from uc_bench.openrouter import fetch_credit_balance, fetch_key_status


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    key = load_openrouter_key(root)
    adapters, catalog, contracts = discover_mmmvp_adapters(root, key)
    status = fetch_key_status(key)
    credits = fetch_credit_balance(key)
    value = {
        "schema_version": "uc-bench-mmmvp-route-contracts-1",
        "checked_at": datetime.now(UTC).isoformat(),
        "status": "passed",
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
            "key_usage_usd": status.usage_usd,
            "key_limit_usd": status.limit_usd,
            "key_limit_remaining_usd": status.limit_usd - status.usage_usd,
            "account_remaining_usd": credits["remaining_usd"],
        },
    }
    path = root / ROUTE_CONTRACTS_PATH
    if path.exists():
        raise RuntimeError("Route-contract artifact already exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
    print(json.dumps({"status": "passed", "model_count": len(adapters)}, sort_keys=True))


if __name__ == "__main__":
    main()

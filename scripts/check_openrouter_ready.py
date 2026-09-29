#!/usr/bin/env python3
"""Validate the configured OpenRouter key without making a model request."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from uc_bench.model_runner import load_openrouter_key
from uc_bench.openrouter import fetch_credit_balance, fetch_key_status

PROJECT_ROOT = Path(__file__).resolve().parents[1]
def main() -> int:
    key = load_openrouter_key(PROJECT_ROOT)
    status = fetch_key_status(key)
    credits = fetch_credit_balance(key)
    output = {
        "schema_version": "0.1",
        "checked_at": datetime.now(UTC).isoformat(),
        "authenticated": True,
        "model_request_made": False,
        "is_free_tier": status.is_free_tier,
        "key_limit_usd": status.limit_usd,
        "key_limit_remaining_usd": status.limit_remaining_usd,
        "credits": credits,
    }
    output_path = PROJECT_ROOT / "artifacts" / "runtime" / "openrouter_readiness.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

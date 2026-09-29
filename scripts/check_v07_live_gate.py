#!/usr/bin/env python3
"""Persist the authenticated, read-only v0.7 route and account gate."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from uc_bench.model_runner import load_openrouter_key
from uc_bench.openrouter import fetch_key_status
from uc_bench.v07_provider import load_v07_provider_adapters, verify_live_v07_identity

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts/diagnostics/hard_suite_v07_pre_freeze_live_gate.json"


def main() -> int:
    key = load_openrouter_key(ROOT)
    adapters = load_v07_provider_adapters(ROOT)
    identity = verify_live_v07_identity(key, adapters)
    account = fetch_key_status(key)
    cap = 45.0
    headroom = account.limit_remaining_usd
    result = {
        "schema_version": "0.7-pre-freeze-live-gate-1",
        "checked_at": datetime.now(UTC).isoformat(),
        "status": (
            "passed" if headroom is not None and headroom >= cap else "blocked"
        ),
        "authenticated_read_only": True,
        "inference_requests": 0,
        "scientific_requests": 0,
        "heldout_requests": 0,
        "astra_requests": 0,
        "model_identity_and_route": identity,
        "account": {
            "usage_usd": account.usage_usd,
            "key_limit_usd": account.limit_usd,
            "key_limit_remaining_usd": headroom,
        },
        "frozen_cap_usd": cap,
        "headroom_excess_usd": (
            None if headroom is None else round(float(headroom) - cap, 8)
        ),
        "required_top_up_usd": (
            cap if headroom is None else max(0.0, round(cap - float(headroom), 2))
        ),
        "required_key_limit_increase_usd": (
            cap if headroom is None else max(0.0, round(cap - float(headroom), 2))
        ),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(OUTPUT)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

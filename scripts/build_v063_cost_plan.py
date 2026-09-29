#!/usr/bin/env python3
"""Reconcile the remaining v0.6.3 allowance without making model calls."""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.model_runner import load_openrouter_key
from uc_bench.openrouter import fetch_key_status

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE = PROJECT_ROOT / "artifacts/diagnostics/hard_suite_v06_cost_plan.json"
LEDGER = (
    PROJECT_ROOT
    / "build/hard_suite_v06_runs/"
    "hard62-gpt-5.6-sol-dev6_clean_progression-0-20260908T194210Z/"
    "request_ledger.json"
)
OUTPUT = PROJECT_ROOT / "artifacts/diagnostics/hard_suite_v063_cost_plan.json"
AUTHORIZED_SCIENTIFIC_CAP_USD = 56.0
SUCCESSOR_CAP_USD = 55.57


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected object: {path}")
    return value


def main() -> int:
    source = _read(SOURCE)
    ledger = _read(LEDGER)
    prior_spend = float(ledger["cumulative_reported_cost_usd"])
    if prior_spend + SUCCESSOR_CAP_USD > AUTHORIZED_SCIENTIFIC_CAP_USD:
        raise ValueError("Successor cap would exceed the aggregate authorization")
    key_status = fetch_key_status(load_openrouter_key(PROJECT_ROOT))
    result = copy.deepcopy(source)
    result.update(
        {
            "schema_version": "0.6.3-cost-plan-1",
            "status": "ready_for_infrastructure_only_freeze",
            "generated_at": datetime.now(UTC).isoformat(),
            "network_actions": ["authenticated_GET_key"],
            "inference_requests_made": 0,
            "scientific_requests_made": 0,
            "heldout_requests_made": 0,
            "astra_requests_made": 0,
            "predecessor_v062_scientific_spend_usd": prior_spend,
            "aggregate_authorized_scientific_cap_usd": (
                AUTHORIZED_SCIENTIFIC_CAP_USD
            ),
            "successor_incremental_cap_usd": SUCCESSOR_CAP_USD,
            "maximum_aggregate_scientific_spend_usd": round(
                prior_spend + SUCCESSOR_CAP_USD, 8
            ),
            "account": {
                "key_usage_usd": key_status.usage_usd,
                "key_limit_usd": key_status.limit_usd,
                "key_limit_remaining_usd": key_status.limit_remaining_usd,
            },
            "recommendation": (
                "Freeze v0.6.3 only after total-grader and emergency-checkpoint "
                "controls pass, then rerun the complete balanced ten-cell sentinel."
            ),
        }
    )
    result["sentinel"].update(
        {
            "conservative_maximum_cap_usd": SUCCESSOR_CAP_USD,
            "predecessor_v062_spend_usd": prior_spend,
            "aggregate_cap_usd": AUTHORIZED_SCIENTIFIC_CAP_USD,
            "maximum_aggregate_spend_usd": round(
                prior_spend + SUCCESSOR_CAP_USD, 8
            ),
            "recommended_account_top_up_usd": max(
                0.0,
                round(
                    SUCCESSOR_CAP_USD - float(key_status.limit_remaining_usd or 0),
                    2,
                ),
            ),
            "required_key_limit_increase_usd": max(
                0.0,
                round(
                    SUCCESSOR_CAP_USD - float(key_status.limit_remaining_usd or 0),
                    2,
                ),
            ),
        }
    )
    result["limitations"] = [
        *source.get("limitations", []),
        "The v0.6.2 completed trajectory is excluded; v0.6.3 reruns every sentinel cell.",
        "The reduced v0.6.3 cap preserves the original $56 aggregate scientific authorization.",
    ]
    temporary = OUTPUT.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(OUTPUT)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

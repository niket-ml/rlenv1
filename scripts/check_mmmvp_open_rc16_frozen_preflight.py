#!/usr/bin/env python3
"""Post-freeze read-only identity and zero-network production rehearsal."""

import json
from pathlib import Path

from uc_bench.mmmvp_open_rc16_cost import calculate_rc16_cost_plan
from uc_bench.mmmvp_open_rc16_freeze import read_rc16_release_freeze
from uc_bench.mmmvp_open_rc16_rehearsal import (
    POSTFREEZE_PREFLIGHT_PATH,
    run_rc16_prefreeze_rehearsal,
)
from uc_bench.model_runner import _write_json

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    release = read_rc16_release_freeze(root)
    rehearsal = run_rc16_prefreeze_rehearsal(root)
    cost = calculate_rc16_cost_plan(root)
    checks = {
        "freeze_valid": True,
        "production_rehearsal_passed": rehearsal["status"] == "passed",
        "no_network_requests": rehearsal["api_requests"] == 0,
        "p90_within_cap": cost["sentinel_no_cache_p90_usd"] <= 50.0,
        "cost_calculations_agree": cost["independent_calculations_agree"],
    }
    value = {
        "schema_version": "uc-bench-open-mmmvp-rc1-6-post-freeze-preflight-1",
        "status": "passed" if all(checks.values()) else "failed",
        "api_requests": 0,
        "release_infrastructure_digest": release["infrastructure_digest"],
        "checks": checks,
        "rehearsal": rehearsal,
        "cost": {
            "median_usd": cost["sentinel_no_cache_median_usd"],
            "p90_usd": cost["sentinel_no_cache_p90_usd"],
            "hard_cap_usd": 50.0,
        },
    }
    _write_json(root / POSTFREEZE_PREFLIGHT_PATH, value, secret="")
    print(json.dumps({"status": value["status"]}, sort_keys=True))
    raise SystemExit(0 if value["status"] == "passed" else 1)

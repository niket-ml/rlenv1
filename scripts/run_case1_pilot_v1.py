#!/usr/bin/env python3
"""Run authorized post-freeze Case 1 compatibility and scientific phases."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from uc_bench.case1_pilot_v1_compatibility import run_compatibility_panel
from uc_bench.case1_pilot_v1_execution import (
    approve_gemini_review,
    funding_requirement,
    funding_snapshot,
    initialize_science_state,
    run_gemini_sentinel,
    run_remaining_four,
)
from uc_bench.case1_pilot_v1_provider import load_case1_pilot_adapters
from uc_bench.case1_pilot_v1_release import read_release_freeze
from uc_bench.errors import ConfigurationError
from uc_bench.model_runner import load_openrouter_key


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "phase",
        choices=("compatibility", "funding", "gemini", "approve-gemini", "remaining"),
    )
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    release = read_release_freeze(root)
    key = load_openrouter_key(root)
    if arguments.phase == "compatibility":
        before = funding_snapshot(key)
        cap = float(release["budgets_usd"]["compatibility_hard_cap"])
        if before["effective_remaining_usd"] + 1e-9 < cap:
            raise ConfigurationError("Available headroom does not cover compatibility cap")
        result = run_compatibility_panel(
            root, key=key, adapters=load_case1_pilot_adapters(root)
        )
    elif arguments.phase == "funding":
        state_path = root / "artifacts/uc_bench_case1_pilot_v1_rc1/science/pilot_state.json"
        result = (
            json.loads(state_path.read_text())
            if state_path.exists()
            else initialize_science_state(root, key=key)
        )
        result = {
            "state_status": result["status"],
            "funding": funding_snapshot(key),
            "requirement": funding_requirement(
                funding_snapshot(key),
                float(release["budgets_usd"]["scientific_hard_cap"]),
            ),
        }
    elif arguments.phase == "gemini":
        result = run_gemini_sentinel(root, key=key)
    elif arguments.phase == "approve-gemini":
        result = approve_gemini_review(root, key=key)
    else:
        result = run_remaining_four(root, key=key)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Run RC1.4 forensic adjudication and only unresolved production-path canaries."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from uc_bench.mmmvp_open_rc14_harness import run_compatibility_convergence
from uc_bench.model_runner import load_openrouter_key


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        raise SystemExit("Refusing compatibility calls without --execute")
    root = Path(__file__).resolve().parents[1]
    result = run_compatibility_convergence(root, key=load_openrouter_key(root))
    print(
        json.dumps(
            {
                "status": result["status"],
                "compatible_model_count": result[
                    "technically_compatible_model_count"
                ],
                "round02_request_count": result["round02_request_count"],
                "total_cost_usd": result["total_rc14_compatibility_cost_usd"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

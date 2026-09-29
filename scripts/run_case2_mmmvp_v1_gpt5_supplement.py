#!/usr/bin/env python3
"""Run the user-authorized GPT-5 supplemental Case 2 cell."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from development.case2_graceful.preflight import FAKE_KEY, FakeProvider, reference_actions
from uc_bench.case1_pilot_v1_provider import load_case1_pilot_adapters
from uc_bench.case2_mmmvp_v1_supplemental import MODEL_ID, run_gpt5_supplement
from uc_bench.model_runner import load_openrouter_key


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fake", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--run-id")
    parser.add_argument("--maximum-incremental-cost-usd", type=float)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.fake:
        captures = []
        adapter = load_case1_pilot_adapters(root)[MODEL_ID]
        with tempfile.TemporaryDirectory(prefix="case2-gpt5-supplement-") as temporary:
            scratch = Path(temporary)
            actions = reference_actions(scratch / "source")

            def factory(**constructor):
                return FakeProvider(
                    captures,
                    actions=actions,
                    provider=adapter.provider_order[0],
                    **constructor,
                )

            result = run_gpt5_supplement(
                root,
                openrouter_key=FAKE_KEY,
                run_id="case2-gpt5-supplement-fake",
                cost_cap_usd=2.0,
                output_root=scratch / "runs",
                native_client_factory=factory,
            )
    else:
        if args.run_id is None or args.maximum_incremental_cost_usd is None:
            parser.error("real execution requires --run-id and a cost cap")
        result = run_gpt5_supplement(
            root,
            openrouter_key=load_openrouter_key(root),
            run_id=args.run_id,
            cost_cap_usd=args.maximum_incremental_cost_usd,
        )
    print(json.dumps(result.summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

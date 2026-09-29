#!/usr/bin/env python3
"""Run one final Case 2 MMMVP episode, or the zero-cost fake preflight."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from development.case2_graceful.preflight import FAKE_KEY, FakeProvider, reference_actions
from uc_bench.case2_mmmvp_v1_runner import (
    PREFLIGHT_AUTHORIZATION,
    Case2RunConfig,
    run_case2_episode,
)
from uc_bench.case2_pilot_v1_rc1_provider import load_case2_adapters, model_config
from uc_bench.model_runner import load_openrouter_key


def _fake(root: Path) -> dict:
    model_id = "google/gemini-3.1-pro-preview"
    adapter = load_case2_adapters(root)[model_id]
    row = model_config(root, model_id)
    actions = reference_actions(root / "artifacts/uc_bench_case2_mmmvp_v1/fake-source")
    captures = []

    def factory(**constructor):
        return FakeProvider(
            captures,
            actions=actions,
            provider=adapter.provider_order[0],
            **constructor,
        )

    result = run_case2_episode(
        root,
        Case2RunConfig("case2-mmmvp-v1-fake", model_id, minimum_request_interval_seconds=0),
        adapter=adapter,
        openrouter_key=FAKE_KEY,
        authorization_digest=PREFLIGHT_AUTHORIZATION,
        remaining_cost_cap_usd=2,
        output_root=root / "artifacts/uc_bench_case2_mmmvp_v1/fake_runs",
        attempt_seed=int(row["attempt_seed"]),
        provider_seed=row.get("provider_seed"),
        native_client_factory=factory,
        preflight_mode=True,
    )
    return result.summary


def _real(root: Path, args: argparse.Namespace) -> dict:
    from uc_bench.case2_mmmvp_v1_release import read_release_freeze

    release = read_release_freeze(root)
    if args.authorization_digest != release["aggregate_release_digest"]:
        raise ValueError("Authorization digest does not match the frozen release")
    adapters = load_case2_adapters(root)
    if args.model_id not in adapters:
        raise ValueError("Model is outside the frozen Case 2 panel")
    row = model_config(root, args.model_id)
    result = run_case2_episode(
        root,
        Case2RunConfig(args.run_id, args.model_id),
        adapter=adapters[args.model_id],
        openrouter_key=load_openrouter_key(root),
        authorization_digest=args.authorization_digest,
        remaining_cost_cap_usd=args.maximum_incremental_cost_usd,
        output_root=root / "artifacts/uc_bench_case2_mmmvp_v1/science/runs",
        attempt_seed=int(row["attempt_seed"]),
        provider_seed=row.get("provider_seed"),
        scientific_authorization=args.authorization_digest,
    )
    return result.summary


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fake", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--model-id")
    parser.add_argument("--run-id", default="case2-mmmvp-v1-real")
    parser.add_argument("--maximum-incremental-cost-usd", type=float)
    parser.add_argument("--authorization-digest")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.fake:
        result = _fake(root)
    else:
        if not all(
            (args.model_id, args.maximum_incremental_cost_usd, args.authorization_digest)
        ):
            parser.error("real execution requires model, cap and authorization digest")
        result = _real(root, args)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

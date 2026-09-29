#!/usr/bin/env python3
"""Execute one explicitly selected, Docker-isolated OpenRouter canary."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from uc_bench.canary_audit import rebuild_canary_audit
from uc_bench.model_runner import ModelRunConfig, load_openrouter_key, run_model_episode

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CANARY_CONFIG = json.loads(
    (PROJECT_ROOT / "configs" / "canary_model.json").read_text(encoding="utf-8")
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    budget = CANARY_CONFIG["run_budget"]
    parser.add_argument(
        "--model",
        default=CANARY_CONFIG["model_id"],
        help="Pinned OpenRouter model slug",
    )
    parser.add_argument("--seed", type=int, default=20260906)
    parser.add_argument(
        "--temperature",
        type=float,
        default=float(budget["temperature"]),
    )
    parser.add_argument(
        "--maximum-turns",
        type=int,
        default=int(budget["maximum_turns"]),
    )
    parser.add_argument(
        "--maximum-completion-tokens-per-turn",
        type=int,
        default=int(budget["maximum_completion_tokens_per_turn"]),
    )
    parser.add_argument(
        "--maximum-total-completion-tokens",
        type=int,
        default=int(budget["maximum_total_completion_tokens"]),
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Required acknowledgement that this command makes a paid model request",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.execute:
        print("Dry run only: add --execute after reviewing the pinned model and budget.")
        return 0
    key = load_openrouter_key(PROJECT_ROOT)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"canary-{args.model}-{args.seed}-{timestamp}".replace("/", "-")
    artifacts = run_model_episode(
        PROJECT_ROOT,
        ModelRunConfig(
            model_id=args.model,
            run_id=run_id,
            seed=args.seed,
            temperature=args.temperature,
            maximum_turns=args.maximum_turns,
            maximum_completion_tokens_per_turn=(
                args.maximum_completion_tokens_per_turn
            ),
            maximum_total_completion_tokens=args.maximum_total_completion_tokens,
            wall_clock_timeout_seconds=int(
                CANARY_CONFIG["run_budget"]["wall_clock_timeout_seconds"]
            ),
        ),
        openrouter_key=key,
    )
    public_summary = PROJECT_ROOT / "artifacts" / "runtime" / "canary_summary.json"
    public_summary.write_text(
        json.dumps(artifacts.summary, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    rebuild_canary_audit(PROJECT_ROOT)
    print(
        json.dumps(
            {
                "classification": artifacts.summary["classification"],
                "phase": artifacts.summary["phase"],
                "turn_count": artifacts.summary["turn_count"],
                "token_usage": artifacts.summary["token_usage"],
                "cost": artifacts.summary["cost"],
                "openrouter_cost_delta_usd": artifacts.summary[
                    "openrouter_cost_delta_usd"
                ],
                "score": (artifacts.summary.get("grade") or {}).get("score"),
                "summary_path": str(artifacts.summary_path),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

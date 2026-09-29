#!/usr/bin/env python3
"""Plan or run one paid short-packet integration canary."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from uc_bench.model_runner import load_openrouter_key
from uc_bench.packet_runner import (
    DiagnosticPacketRunConfig,
    run_diagnostic_packet_episode,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("--model", default="openai/gpt-5.6-sol")
    value.add_argument("--task-id", default="T08")
    value.add_argument("--scenario-id", default="promising_underpowered")
    value.add_argument("--seed", type=int, default=20260907)
    value.add_argument("--execute", action="store_true")
    return value


def main() -> int:
    args = parser().parse_args()
    plan = {
        "model_id": args.model,
        "task_id": args.task_id,
        "scenario_id": args.scenario_id,
        "maximum_turns": 8,
        "maximum_total_completion_tokens": 8000,
        "paid_request": bool(args.execute),
    }
    if not args.execute:
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_id = (
        f"packet-canary-{args.model}-{args.task_id}-{args.scenario_id}-{timestamp}"
        .replace("/", "-")
        .replace(":", "-")
    )
    artifacts = run_diagnostic_packet_episode(
        PROJECT_ROOT,
        DiagnosticPacketRunConfig(
            model_id=args.model,
            run_id=run_id,
            task_id=args.task_id,
            scenario_id=args.scenario_id,
            seed=args.seed,
        ),
        openrouter_key=load_openrouter_key(PROJECT_ROOT),
    )
    public_path = PROJECT_ROOT / "artifacts" / "diagnostics" / "packet_canary.json"
    public_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.write_text(
        json.dumps(artifacts.summary, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(artifacts.summary, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

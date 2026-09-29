#!/usr/bin/env python3
"""Run one paid flagship canary on an executable data diagnostic."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from uc_bench.data_task_runner import DataTaskRunConfig, run_data_task_episode
from uc_bench.model_runner import load_openrouter_key
from uc_bench.openrouter import fetch_key_status

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("--execute", action="store_true")
    value.add_argument("--model-id", default="openai/gpt-5.6-sol")
    value.add_argument("--task-id", default="T06")
    value.add_argument("--scenario-id", default="noise_n120_20")
    return value


def main() -> int:
    args = parser().parse_args()
    plan = {
        "model_id": args.model_id,
        "task_id": args.task_id,
        "scenario_id": args.scenario_id,
        "trajectory_count": 1,
        "purpose": "runtime_and_difficulty_canary_not_ranking",
    }
    if not args.execute:
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0
    key = load_openrouter_key(PROJECT_ROOT)
    before = fetch_key_status(key)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_id = (
        f"data-canary-{args.model_id}-{args.task_id}-{args.scenario_id}-{timestamp}"
    ).replace("/", "-")
    artifacts = run_data_task_episode(
        PROJECT_ROOT,
        DataTaskRunConfig(
            model_id=args.model_id,
            run_id=run_id,
            task_id=args.task_id,
            scenario_id=args.scenario_id,
            seed=20260907,
        ),
        openrouter_key=key,
    )
    after = fetch_key_status(key)
    output = {
        "schema_version": "0.1",
        "executed_at": datetime.now(UTC).isoformat(),
        "purpose": plan["purpose"],
        "run_directory": artifacts.summary["run_directory"],
        "classification": artifacts.summary["classification"],
        "attempt_score": artifacts.summary["attempt_score"],
        "grade": artifacts.summary["grade"],
        "turn_count": artifacts.summary["turn_count"],
        "tool_call_counts": artifacts.summary["tool_call_counts"],
        "token_usage": artifacts.summary["token_usage"],
        "openrouter_usage_before_usd": before.usage_usd,
        "openrouter_usage_after_usd": after.usage_usd,
        "openrouter_usage_delta_usd": after.usage_usd - before.usage_usd,
    }
    output_path = PROJECT_ROOT / "artifacts" / "diagnostics" / "data_task_canary.json"
    output_path.write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

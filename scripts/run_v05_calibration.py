#!/usr/bin/env python3
"""Run the frozen v0.5 development pilot under a hard incremental spend cap."""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.hard_suite_v05 import validate_v05_config
from uc_bench.hard_suite_v05_runner import V05RunConfig, run_v05_episode
from uc_bench.hashing import canonical_sha256
from uc_bench.model_runner import load_openrouter_key
from uc_bench.openrouter import fetch_key_status
from uc_bench.v05_freeze import v05_frozen_hashes

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "configs" / "hard_suite_v05_calibration.json"
CONTROLS_PATH = PROJECT_ROOT / "artifacts" / "diagnostics" / "hard_suite_v05_controls.json"
FREEZE_PATH = PROJECT_ROOT / "artifacts" / "diagnostics" / "hard_suite_v05_freeze.json"


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected JSON object: {path}")
    return value


def _jobs(config: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "model_id": model["model_id"],
            "scenario_id": scenario_id,
            "attempt_index": attempt,
        }
        for model in config["models"]
        for scenario_id in config["scenario_ids"]
        for attempt in range(int(config["attempts_per_cell"]))
    ]


def _key(row: dict[str, Any]) -> tuple[str, str, int]:
    return (
        str(row["model_id"]),
        str(row["scenario_id"]),
        int(row["attempt_index"]),
    )


def _completed(rows: list[dict[str, Any]]) -> set[tuple[str, str, int]]:
    return {_key(row) for row in rows if row.get("classification") != "infrastructure_failure"}


def _estimate(summary: dict[str, Any], model: dict[str, Any]) -> float | None:
    usage = summary.get("token_usage") or {}
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    if not isinstance(input_tokens, int | float) or not isinstance(output_tokens, int | float):
        return None
    return (
        float(input_tokens) * float(model["input_usd_per_million_tokens"])
        + float(output_tokens) * float(model["output_usd_per_million_tokens"])
    ) / 1_000_000


def _checkpoint(
    path: Path,
    config: dict[str, Any],
    rows: list[dict[str, Any]],
    estimated_cost: float,
    cap: float,
    stop_reason: str | None,
    usage_before: float,
    usage_after: float | None,
) -> dict[str, Any]:
    output = {
        "schema_version": "0.5",
        "executed_at": datetime.now(UTC).isoformat(),
        "status": "bounded_development_pilot_not_ranking",
        "ranking_claim_allowed": False,
        "astra_requests": 0,
        "config_digest": canonical_sha256(config),
        "frozen_hashes": v05_frozen_hashes(PROJECT_ROOT),
        "planned_trajectory_count": len(_jobs(config)),
        "completed_trajectory_count": len(_completed(rows)),
        "executed_request_count": len(rows),
        "infrastructure_failure_count": sum(
            row["classification"] == "infrastructure_failure" for row in rows
        ),
        "estimated_cost_usd": estimated_cost,
        "maximum_incremental_spend_usd": cap,
        "openrouter_key_usage_before_usd": usage_before,
        "openrouter_key_usage_after_usd": usage_after,
        "observed_incremental_spend_usd": (
            None if usage_after is None else usage_after - usage_before
        ),
        "stop_reason": stop_reason,
        "runs": rows,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
    return output


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--maximum-incremental-cost-usd", type=float)
    parser.add_argument(
        "--output-path",
        type=Path,
        default=Path("artifacts/diagnostics/hard_suite_v05_calibration_runs.json"),
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    config = _read(CONFIG_PATH)
    jobs = _jobs(config)
    cap = float(config["cost_planning"]["maximum_incremental_spend_usd"])
    controls = _read(CONTROLS_PATH)
    freeze = _read(FREEZE_PATH) if FREEZE_PATH.exists() else {}
    planning = {
        "mode": "planning_only",
        "models": [row["model_id"] for row in config["models"]],
        "scenario_count": len(config["scenario_ids"]),
        "trajectory_count": len(jobs),
        "maximum_incremental_spend_usd": cap,
        "all_local_gates_passed": controls.get("all_local_gates_passed", False),
        "freeze_manifest_valid": bool(freeze.get("frozen_before_model_calls")),
        "ranking_claim_allowed": False,
        "astra_requests": 0,
    }
    if not args.execute:
        print(json.dumps(planning, indent=2))
        return 0

    validate_v05_config(PROJECT_ROOT)
    if not controls.get("all_local_gates_passed"):
        raise SystemExit("v0.5 local gates failed; paid execution refused")
    if any("astra" in str(row["model_id"]).lower() for row in config["models"]):
        raise SystemExit("Astra is forbidden in v0.5 development calibration")
    if not freeze.get("frozen_before_model_calls"):
        raise SystemExit("v0.5 freeze manifest is absent or invalid")
    if freeze.get("hashes") != v05_frozen_hashes(PROJECT_ROOT):
        raise SystemExit("v0.5 files changed after freeze; paid execution refused")
    if args.maximum_incremental_cost_usd is None or args.maximum_incremental_cost_usd != cap:
        raise SystemExit(f"--maximum-incremental-cost-usd must equal the frozen ${cap:.2f} cap")

    output_path = (PROJECT_ROOT / args.output_path).resolve()
    if PROJECT_ROOT not in output_path.parents:
        raise SystemExit("--output-path must remain inside the project")
    key = load_openrouter_key(PROJECT_ROOT)
    if args.resume:
        existing = _read(output_path)
        if existing.get("config_digest") != canonical_sha256(config):
            raise SystemExit("Unsafe resume: calibration configuration changed")
        if existing.get("frozen_hashes") != v05_frozen_hashes(PROJECT_ROOT):
            raise SystemExit("Unsafe resume: frozen files changed")
        rows = list(existing.get("runs") or [])
        estimated_cost = float(existing.get("estimated_cost_usd", 0.0))
        usage_before = float(existing["openrouter_key_usage_before_usd"])
    else:
        if output_path.exists():
            raise SystemExit("Output exists; use --resume to avoid duplicate requests")
        rows = []
        estimated_cost = 0.0
        usage_before = fetch_key_status(key).usage_usd

    completed = _completed(rows)
    models = {str(row["model_id"]): row for row in config["models"]}
    budget = config["trajectory_budget"]
    cooldown = float(config["cost_planning"]["inter_episode_cooldown_seconds"])
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    stop_reason = None
    usage_after: float | None = None
    for job in jobs:
        if _key(job) in completed:
            continue
        model = models[str(job["model_id"])]
        per_episode_guard = float(model["planning_guard_per_episode_usd"])
        status = fetch_key_status(key)
        usage_after = status.usage_usd
        observed_increment = usage_after - usage_before
        if observed_increment + per_episode_guard > cap:
            stop_reason = "incremental_cost_cap"
            break
        if (
            status.limit_remaining_usd is not None
            and status.limit_remaining_usd < per_episode_guard
        ):
            stop_reason = "openrouter_key_limit_remaining"
            break
        if rows:
            time.sleep(cooldown)
        run_id = (
            f"hard5-{str(job['model_id']).split('/')[-1]}-{job['scenario_id']}-"
            f"{job['attempt_index']}-{timestamp}"
        )
        artifacts = run_v05_episode(
            PROJECT_ROOT,
            V05RunConfig(
                model_id=str(job["model_id"]),
                run_id=run_id,
                scenario_id=str(job["scenario_id"]),
                seed=20260907 + int(job["attempt_index"]),
                maximum_turns=int(budget["maximum_turns"]),
                maximum_completion_tokens_per_turn=int(
                    budget["maximum_completion_tokens_per_turn"]
                ),
                maximum_total_completion_tokens=int(budget["maximum_total_completion_tokens"]),
                wall_clock_timeout_seconds=int(budget["wall_clock_timeout_seconds"]),
                minimum_request_interval_seconds=float(budget["minimum_request_interval_seconds"]),
            ),
            openrouter_key=key,
        )
        summary = artifacts.summary
        estimate = _estimate(summary, model)
        estimated_cost += estimate if estimate is not None else per_episode_guard
        rows.append(
            {
                **job,
                "run_id": summary["run_id"],
                "run_directory": summary["run_directory"],
                "scenario_class": summary["scenario_class"],
                "classification": summary["classification"],
                "score": summary["attempt_score"],
                "grade": summary["grade"],
                "diagnostic_grade": summary["diagnostic_grade"],
                "phase_reached": summary["phase_reached"],
                "selected_resource_id": summary["selected_resource_id"],
                "turn_count": summary["turn_count"],
                "tool_call_counts": summary["tool_call_counts"],
                "token_usage": summary["token_usage"],
                "estimated_cost_usd": estimate,
            }
        )
        try:
            usage_after = fetch_key_status(key).usage_usd
        except ConfigurationError:
            usage_after = None
        _checkpoint(
            output_path,
            config,
            rows,
            estimated_cost,
            cap,
            stop_reason,
            usage_before,
            usage_after,
        )
    _checkpoint(
        output_path,
        config,
        rows,
        estimated_cost,
        cap,
        stop_reason,
        usage_before,
        usage_after,
    )
    print(
        json.dumps(
            {
                "completed": len(_completed(rows)),
                "planned": len(jobs),
                "stop_reason": stop_reason,
                "estimated_cost_usd": estimated_cost,
                "ranking_claim_allowed": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

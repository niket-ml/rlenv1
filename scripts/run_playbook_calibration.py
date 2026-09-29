#!/usr/bin/env python3
"""Run the frozen base-versus-expert-playbook calibration."""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.data_task_runner import DataTaskRunConfig, run_data_task_episode
from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256
from uc_bench.model_runner import load_openrouter_key
from uc_bench.openrouter import fetch_key_status
from uc_bench.packet_runner import (
    DiagnosticPacketRunConfig,
    run_diagnostic_packet_episode,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "configs" / "playbook_calibration.json"
MODEL_INTER_TASK_DELAY_SECONDS = {
    "openai/gpt-5.4": 20.0,
    "openai/gpt-5.2": 20.0,
}


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected JSON object: {path}")
    return value


def build_jobs(config: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "model_id": model["model_id"],
            "task_type": scenario["task_type"],
            "task_id": scenario["task_id"],
            "scenario_id": scenario["scenario_id"],
            "condition": condition,
            "attempt_index": attempt,
        }
        for model in config["models"]
        for scenario in config["scenarios"]
        for condition in config["conditions"]
        for attempt in range(int(config["attempts_per_cell"]))
    ]


def estimate_cost(summary: dict[str, Any], model: dict[str, Any]) -> float | None:
    usage = summary.get("token_usage") or {}
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    if not isinstance(input_tokens, int | float) or not isinstance(output_tokens, int | float):
        return None
    return (
        float(input_tokens) * float(model["input_usd_per_million_tokens"])
        + float(output_tokens) * float(model["output_usd_per_million_tokens"])
    ) / 1_000_000


def job_key(row: dict[str, Any]) -> tuple[str, str, str, str, int]:
    return (
        str(row["model_id"]),
        str(row["task_id"]),
        str(row["scenario_id"]),
        str(row["condition"]),
        int(row["attempt_index"]),
    )


def completed_job_keys(rows: list[dict[str, Any]]) -> set[tuple[str, str, str, str, int]]:
    return {job_key(row) for row in rows if row.get("classification") != "infrastructure_failure"}


def write_checkpoint(
    path: Path,
    *,
    config: dict[str, Any],
    rows: list[dict[str, Any]],
    estimated_cost_usd: float,
    local_cap_usd: float,
    stop_reason: str | None,
    usage_before_usd: float,
    usage_after_usd: float | None,
) -> dict[str, Any]:
    output = {
        "schema_version": "0.1",
        "executed_at": datetime.now(UTC).isoformat(),
        "config_path": CONFIG_PATH.relative_to(PROJECT_ROOT).as_posix(),
        "config_digest": canonical_sha256(config),
        "status": "paired_calibration_not_ranking",
        "leaderboard_evidence": False,
        "planned_trajectory_count": len(build_jobs(config)),
        "completed_trajectory_count": len(completed_job_keys(rows)),
        "executed_request_count": len(rows),
        "infrastructure_failure_count": sum(
            row["classification"] == "infrastructure_failure" for row in rows
        ),
        "estimated_cost_usd": estimated_cost_usd,
        "local_cap_usd": local_cap_usd,
        "openrouter_key_usage_before_usd": usage_before_usd,
        "openrouter_key_usage_after_usd": usage_after_usd,
        "stop_reason": stop_reason,
        "model_inter_task_delay_seconds": MODEL_INTER_TASK_DELAY_SECONDS,
        "runs": rows,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
    return output


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("--execute", action="store_true")
    value.add_argument("--resume", action="store_true")
    value.add_argument("--maximum-estimated-cost-usd", type=float)
    value.add_argument(
        "--output-path",
        type=Path,
        default=Path("artifacts/diagnostics/playbook_calibration_runs.json"),
    )
    return value


def _run_job(
    config: dict[str, Any], job: dict[str, Any], key: str, timestamp: str
) -> dict[str, Any]:
    budget = config["trajectory_budgets"][job["task_type"]]
    model_tag = str(job["model_id"]).split("/")[-1]
    job_digest = canonical_sha256(job)[:8]
    run_id = (
        f"pb-{model_tag}-{job['condition']}-{job['task_id']}-{job_digest}-"
        f"{job['attempt_index']}-{timestamp}"
    )
    shared = {
        "model_id": job["model_id"],
        "run_id": run_id,
        "task_id": job["task_id"],
        "scenario_id": job["scenario_id"],
        "seed": 20260907 + int(job["attempt_index"]),
        "condition": job["condition"],
        "maximum_turns": int(budget["maximum_turns"]),
        "maximum_completion_tokens_per_turn": int(budget["maximum_completion_tokens_per_turn"]),
        "maximum_total_completion_tokens": int(budget["maximum_total_completion_tokens"]),
        "wall_clock_timeout_seconds": int(budget["wall_clock_timeout_seconds"]),
    }
    if job["task_type"] == "packet":
        artifacts = run_diagnostic_packet_episode(
            PROJECT_ROOT, DiagnosticPacketRunConfig(**shared), openrouter_key=key
        )
    elif job["task_type"] == "data":
        artifacts = run_data_task_episode(
            PROJECT_ROOT, DataTaskRunConfig(**shared), openrouter_key=key
        )
    else:
        raise ConfigurationError(f"Unsupported paired task type: {job['task_type']}")
    return artifacts.summary


def main() -> int:
    args = parser().parse_args()
    config = read_json(CONFIG_PATH)
    jobs = build_jobs(config)
    if not args.execute:
        print(
            json.dumps(
                {
                    "mode": "planning_only",
                    "models": [model["model_id"] for model in config["models"]],
                    "scenario_count": len(config["scenarios"]),
                    "conditions": config["conditions"],
                    "trajectory_count": len(jobs),
                    "planning_guard_usd": config["cost_planning"]["planning_guard_usd"],
                    "ranking_claim_allowed": False,
                },
                indent=2,
            )
        )
        return 0
    guard = float(config["cost_planning"]["planning_guard_usd"])
    if args.maximum_estimated_cost_usd is None or args.maximum_estimated_cost_usd < guard:
        raise SystemExit("--maximum-estimated-cost-usd must meet the frozen planning guard")
    output_path = (PROJECT_ROOT / args.output_path).resolve()
    if PROJECT_ROOT.resolve() not in output_path.parents:
        raise SystemExit("--output-path must remain inside the project")
    if args.resume:
        existing = read_json(output_path)
        if existing.get("config_digest") != canonical_sha256(config):
            raise SystemExit("Unsafe resume refused: frozen configuration changed")
        rows = list(existing.get("runs") or [])
        cumulative = float(existing.get("estimated_cost_usd", 0.0))
        usage_before = float(existing["openrouter_key_usage_before_usd"])
    else:
        if output_path.exists():
            raise SystemExit("Output exists; use --resume to avoid duplicate requests")
        rows = []
        cumulative = 0.0
        usage_before = fetch_key_status(load_openrouter_key(PROJECT_ROOT)).usage_usd
    completed = completed_job_keys(rows)
    models = {model["model_id"]: model for model in config["models"]}
    key = load_openrouter_key(PROJECT_ROOT)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    stop_reason = None
    for job in jobs:
        if job_key(job) in completed:
            continue
        model = models[job["model_id"]]
        per_run_guard = float(model["planning_guard_per_task_usd"])
        if cumulative + per_run_guard > args.maximum_estimated_cost_usd:
            stop_reason = "local_planning_cap"
            break
        delay = MODEL_INTER_TASK_DELAY_SECONDS.get(job["model_id"], 0.0)
        if delay and any(row.get("model_id") == job["model_id"] for row in rows):
            time.sleep(delay)
        summary = _run_job(config, job, key, timestamp)
        run_estimate = estimate_cost(summary, model)
        cumulative += run_estimate if run_estimate is not None else per_run_guard
        grade = summary.get("grade") or {}
        rows.append(
            {
                **job,
                "run_id": summary["run_id"],
                "run_directory": summary["run_directory"],
                "package_digest": summary["package_digest"],
                "classification": summary["classification"],
                "score": summary["attempt_score"],
                "decision_correct": grade.get("decision_correct"),
                "component_scores": grade.get("component_scores"),
                "checks": grade.get("checks"),
                "turn_count": summary["turn_count"],
                "tool_call_counts": summary["tool_call_counts"],
                "token_usage": summary["token_usage"],
                "estimated_cost_usd": run_estimate,
            }
        )
        write_checkpoint(
            output_path,
            config=config,
            rows=rows,
            estimated_cost_usd=cumulative,
            local_cap_usd=args.maximum_estimated_cost_usd,
            stop_reason=("infrastructure_failure" if summary["infrastructure_failure"] else None),
            usage_before_usd=usage_before,
            usage_after_usd=None,
        )
        if summary["infrastructure_failure"]:
            stop_reason = "infrastructure_failure"
            break
    try:
        usage_after = fetch_key_status(key).usage_usd
    except ConfigurationError:
        usage_after = None
    output = write_checkpoint(
        output_path,
        config=config,
        rows=rows,
        estimated_cost_usd=cumulative,
        local_cap_usd=args.maximum_estimated_cost_usd,
        stop_reason=stop_reason,
        usage_before_usd=usage_before,
        usage_after_usd=usage_after,
    )
    print(json.dumps({key: value for key, value in output.items() if key != "runs"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Plan or execute the frozen hard-suite development calibration."""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.hard_suite import validate_hard_suite_config
from uc_bench.hard_suite_runner import HardSuiteRunConfig, run_hard_suite_episode
from uc_bench.hashing import canonical_sha256, sha256_file
from uc_bench.model_runner import load_openrouter_key
from uc_bench.openrouter import fetch_key_status

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "configs" / "hard_suite_calibration.json"
CONTROLS_PATH = PROJECT_ROOT / "artifacts" / "diagnostics" / "hard_suite_controls.json"
HARD_CONFIG_PATH = PROJECT_ROOT / "configs" / "hard_suite.json"
HELDOUT_PATH = PROJECT_ROOT / "grader_private" / "hard_suite_heldout.json"
MODEL_INTER_TASK_DELAY_SECONDS = {
    "openai/gpt-5.6-sol": 75.0,
    "openai/gpt-5.4": 75.0,
    "openai/gpt-5.2": 75.0,
}


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected JSON object: {path}")
    return value


def build_jobs(config: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "model_id": model["model_id"],
            "variant_id": variant_id,
            "attempt_index": attempt,
        }
        for model in config["models"]
        for variant_id in config["variant_ids"]
        for attempt in range(int(config["attempts_per_cell"]))
    ]


def _job_key(row: dict[str, Any]) -> tuple[str, str, int]:
    return (
        str(row["model_id"]),
        str(row["variant_id"]),
        int(row["attempt_index"]),
    )


def _completed_keys(rows: list[dict[str, Any]]) -> set[tuple[str, str, int]]:
    return {_job_key(row) for row in rows if row.get("classification") != "infrastructure_failure"}


def _estimate_cost(summary: dict[str, Any], model: dict[str, Any]) -> float | None:
    usage = summary.get("token_usage") or {}
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    if not isinstance(input_tokens, int | float) or not isinstance(output_tokens, int | float):
        return None
    return (
        float(input_tokens) * float(model["input_usd_per_million_tokens"])
        + float(output_tokens) * float(model["output_usd_per_million_tokens"])
    ) / 1_000_000


def _write_checkpoint(
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
        "schema_version": "0.2",
        "executed_at": datetime.now(UTC).isoformat(),
        "config_path": CONFIG_PATH.relative_to(PROJECT_ROOT).as_posix(),
        "config_digest": canonical_sha256(config),
        "hard_suite_config_sha256": sha256_file(HARD_CONFIG_PATH),
        "heldout_spec_sha256": sha256_file(HELDOUT_PATH),
        "status": "one_seed_development_calibration_not_ranking",
        "leaderboard_evidence": False,
        "astra_requests": 0,
        "planned_trajectory_count": len(build_jobs(config)),
        "completed_trajectory_count": len(_completed_keys(rows)),
        "executed_request_count": len(rows),
        "infrastructure_failure_count": sum(
            row["classification"] == "infrastructure_failure" for row in rows
        ),
        "estimated_cost_usd": estimated_cost_usd,
        "local_cap_usd": local_cap_usd,
        "openrouter_key_usage_before_usd": usage_before_usd,
        "openrouter_key_usage_after_usd": usage_after_usd,
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
    parser.add_argument("--maximum-estimated-cost-usd", type=float)
    parser.add_argument(
        "--output-path",
        type=Path,
        default=Path("artifacts/diagnostics/hard_suite_calibration_runs.json"),
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    config = _read_object(CONFIG_PATH)
    jobs = build_jobs(config)
    if not args.execute:
        print(
            json.dumps(
                {
                    "mode": "planning_only",
                    "models": [row["model_id"] for row in config["models"]],
                    "variant_count": len(config["variant_ids"]),
                    "trajectory_count": len(jobs),
                    "planning_guard_usd": config["cost_planning"]["planning_guard_usd"],
                    "astra_requests": 0,
                    "ranking_claim_allowed": False,
                },
                indent=2,
            )
        )
        return 0
    validate_hard_suite_config(PROJECT_ROOT)
    controls = _read_object(CONTROLS_PATH)
    if not controls.get("all_local_gates_passed"):
        raise SystemExit("Hard-suite local gates have not passed; paid calibration refused")
    if any("astra" in str(model["model_id"]).lower() for model in config["models"]):
        raise SystemExit("Astra is forbidden in the development calibration")
    guard = float(config["cost_planning"]["planning_guard_usd"])
    if args.maximum_estimated_cost_usd is None or args.maximum_estimated_cost_usd < guard:
        raise SystemExit("--maximum-estimated-cost-usd must meet the frozen planning guard")
    output_path = (PROJECT_ROOT / args.output_path).resolve()
    if PROJECT_ROOT not in output_path.parents:
        raise SystemExit("--output-path must remain inside the project")
    if args.resume:
        existing = _read_object(output_path)
        if existing.get("config_digest") != canonical_sha256(config):
            raise SystemExit("Unsafe resume refused: frozen configuration changed")
        if existing.get("hard_suite_config_sha256") != sha256_file(HARD_CONFIG_PATH):
            raise SystemExit("Unsafe resume refused: hard-suite configuration changed")
        if existing.get("heldout_spec_sha256") != sha256_file(HELDOUT_PATH):
            raise SystemExit("Unsafe resume refused: held-out specification changed")
        rows = list(existing.get("runs") or [])
        cumulative = float(existing.get("estimated_cost_usd", 0.0))
        usage_before = float(existing["openrouter_key_usage_before_usd"])
    else:
        if output_path.exists():
            raise SystemExit("Output exists; use --resume to avoid duplicate requests")
        rows = []
        cumulative = 0.0
        usage_before = fetch_key_status(load_openrouter_key(PROJECT_ROOT)).usage_usd
    key = load_openrouter_key(PROJECT_ROOT)
    completed = _completed_keys(rows)
    models = {model["model_id"]: model for model in config["models"]}
    budget = config["trajectory_budget"]
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    stop_reason = None
    for job in jobs:
        if _job_key(job) in completed:
            continue
        model = models[job["model_id"]]
        per_run_guard = float(model["planning_guard_per_task_usd"])
        if cumulative + per_run_guard > args.maximum_estimated_cost_usd:
            stop_reason = "local_planning_cap"
            break
        delay = MODEL_INTER_TASK_DELAY_SECONDS.get(str(job["model_id"]), 0.0)
        if delay and any(row.get("model_id") == job["model_id"] for row in rows):
            time.sleep(delay)
        model_tag = str(job["model_id"]).split("/")[-1]
        run_id = f"hard-{model_tag}-{job['variant_id']}-{job['attempt_index']}-{timestamp}"
        artifacts = run_hard_suite_episode(
            PROJECT_ROOT,
            HardSuiteRunConfig(
                model_id=job["model_id"],
                run_id=run_id,
                variant_id=job["variant_id"],
                seed=20260907 + int(job["attempt_index"]),
                maximum_turns=int(budget["maximum_turns"]),
                maximum_completion_tokens_per_turn=int(
                    budget["maximum_completion_tokens_per_turn"]
                ),
                maximum_total_completion_tokens=int(budget["maximum_total_completion_tokens"]),
                wall_clock_timeout_seconds=int(budget["wall_clock_timeout_seconds"]),
            ),
            openrouter_key=key,
        )
        summary = artifacts.summary
        estimate = _estimate_cost(summary, model)
        cumulative += estimate if estimate is not None else per_run_guard
        rows.append(
            {
                **job,
                "run_id": summary["run_id"],
                "run_directory": summary["run_directory"],
                "family_id": summary["family_id"],
                "classification": summary["classification"],
                "score": summary["attempt_score"],
                "grade": summary["grade"],
                "commitment_recorded": summary["commitment_recorded"],
                "evidence_revealed": summary["evidence_revealed"],
                "commitment_immutable": summary["commitment_immutable"],
                "turn_count": summary["turn_count"],
                "tool_call_counts": summary["tool_call_counts"],
                "token_usage": summary["token_usage"],
                "estimated_cost_usd": estimate,
            }
        )
        _write_checkpoint(
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
    output = _write_checkpoint(
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

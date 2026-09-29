#!/usr/bin/env python3
"""Execute the frozen v0.3 development matrix with sequential no-go stops."""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.hard_suite_v03 import validate_v03_config
from uc_bench.hard_suite_v03_runner import V03RunConfig, run_v03_episode
from uc_bench.hashing import canonical_sha256, sha256_file
from uc_bench.model_runner import load_openrouter_key
from uc_bench.openrouter import fetch_key_status

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "configs" / "hard_suite_v03_calibration.json"
SUITE_PATH = PROJECT_ROOT / "configs" / "hard_suite_v03.json"
HELDOUT_PATH = PROJECT_ROOT / "grader_private" / "hard_suite_v03_heldout.json"
CONTROLS_PATH = PROJECT_ROOT / "artifacts" / "diagnostics" / "hard_suite_v03_controls.json"


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected JSON object: {path}")
    return value


def _jobs(config: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"model_id": model["model_id"], "variant_id": variant, "attempt_index": attempt}
        for model in config["models"]
        for variant in config["variant_ids"]
        for attempt in range(int(config["attempts_per_cell"]))
    ]


def _key(row: dict[str, Any]) -> tuple[str, str, int]:
    return str(row["model_id"]), str(row["variant_id"]), int(row["attempt_index"])


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


def _model_stop_reason(
    config: dict[str, Any], rows: list[dict[str, Any]], model_id: str
) -> str | None:
    selected = [
        row
        for row in rows
        if row["model_id"] == model_id and row["classification"] != "infrastructure_failure"
    ]
    if len(selected) != len(config["variant_ids"]):
        return None
    scores = [float(row["score"]) for row in selected]
    rules = config["sequential_stop_rules"]
    if all(score == 0.0 for score in scores) and rules["stop_if_all_scores_zero"]:
        return f"model_floor_failure:{model_id}"
    if mean(scores) >= float(rules["stop_if_mean_at_or_above"]):
        return f"model_ceiling_failure:{model_id}:mean={mean(scores):.3f}"
    ceiling_rate = sum(score >= 95.0 for score in scores) / len(scores)
    if ceiling_rate > float(rules["stop_if_ceiling_rate_above"]):
        return f"model_ceiling_failure:{model_id}:ceiling_rate={ceiling_rate:.3f}"
    return None


def _write_checkpoint(
    path: Path,
    config: dict[str, Any],
    rows: list[dict[str, Any]],
    cumulative: float,
    cap: float,
    stop_reason: str | None,
    usage_before: float,
    usage_after: float | None,
) -> dict[str, Any]:
    output = {
        "schema_version": "0.3",
        "executed_at": datetime.now(UTC).isoformat(),
        "config_path": CONFIG_PATH.relative_to(PROJECT_ROOT).as_posix(),
        "config_digest": canonical_sha256(config),
        "suite_sha256": sha256_file(SUITE_PATH),
        "heldout_sha256": sha256_file(HELDOUT_PATH),
        "status": "one_seed_development_calibration_not_ranking",
        "ranking_claim_allowed": False,
        "astra_requests": 0,
        "planned_trajectory_count": len(_jobs(config)),
        "completed_trajectory_count": len(_completed(rows)),
        "executed_request_count": len(rows),
        "infrastructure_failure_count": sum(
            row["classification"] == "infrastructure_failure" for row in rows
        ),
        "estimated_cost_usd": cumulative,
        "local_cap_usd": cap,
        "openrouter_key_usage_before_usd": usage_before,
        "openrouter_key_usage_after_usd": usage_after,
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
        default=Path("artifacts/diagnostics/hard_suite_v03_calibration_runs.json"),
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    config = _read(CONFIG_PATH)
    jobs = _jobs(config)
    if not args.execute:
        print(
            json.dumps(
                {
                    "mode": "planning_only",
                    "models": [row["model_id"] for row in config["models"]],
                    "variant_count": len(config["variant_ids"]),
                    "trajectory_count": len(jobs),
                    "planning_guard_usd": config["cost_planning"]["planning_guard_usd"],
                    "sequential_stop_rules": config["sequential_stop_rules"],
                    "astra_requests": 0,
                },
                indent=2,
            )
        )
        return 0
    validate_v03_config(PROJECT_ROOT)
    if not _read(CONTROLS_PATH).get("all_local_gates_passed"):
        raise SystemExit("v0.3 local gates failed; paid execution refused")
    if any("astra" in str(row["model_id"]).lower() for row in config["models"]):
        raise SystemExit("Astra is forbidden in v0.3 development calibration")
    guard = float(config["cost_planning"]["planning_guard_usd"])
    if args.maximum_estimated_cost_usd is None or args.maximum_estimated_cost_usd < guard:
        raise SystemExit("--maximum-estimated-cost-usd must meet the frozen planning guard")
    output_path = (PROJECT_ROOT / args.output_path).resolve()
    if PROJECT_ROOT not in output_path.parents:
        raise SystemExit("--output-path must remain inside the project")
    if args.resume:
        existing = _read(output_path)
        if existing.get("config_digest") != canonical_sha256(config):
            raise SystemExit("Unsafe resume: calibration configuration changed")
        if existing.get("suite_sha256") != sha256_file(SUITE_PATH):
            raise SystemExit("Unsafe resume: v0.3 suite changed")
        if existing.get("heldout_sha256") != sha256_file(HELDOUT_PATH):
            raise SystemExit("Unsafe resume: v0.3 held-out suite changed")
        rows = list(existing.get("runs") or [])
        cumulative = float(existing.get("estimated_cost_usd", 0.0))
        usage_before = float(existing["openrouter_key_usage_before_usd"])
    else:
        if output_path.exists():
            raise SystemExit("Output exists; use --resume to avoid duplicate requests")
        rows = []
        cumulative = 0.0
        usage_before = fetch_key_status(load_openrouter_key(PROJECT_ROOT)).usage_usd
    completed = _completed(rows)
    models = {row["model_id"]: row for row in config["models"]}
    key = load_openrouter_key(PROJECT_ROOT)
    budget = config["trajectory_budget"]
    cooldown = float(config["cost_planning"]["inter_task_cooldown_seconds"])
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    stop_reason = None
    previous_model = None
    for job in jobs:
        if _key(job) in completed:
            previous_model = job["model_id"]
            continue
        if previous_model is not None and previous_model != job["model_id"]:
            stop_reason = _model_stop_reason(config, rows, str(previous_model))
            if stop_reason:
                break
        model = models[job["model_id"]]
        per_run_guard = float(model["planning_guard_per_task_usd"])
        if cumulative + per_run_guard > args.maximum_estimated_cost_usd:
            stop_reason = "local_planning_cap"
            break
        if any(row.get("model_id") == job["model_id"] for row in rows):
            time.sleep(cooldown)
        run_id = (
            f"hard3-{str(job['model_id']).split('/')[-1]}-{job['variant_id']}-"
            f"{job['attempt_index']}-{timestamp}"
        )
        artifacts = run_v03_episode(
            PROJECT_ROOT,
            V03RunConfig(
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
        estimate = _estimate(summary, model)
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
                "selected_resource_id": summary["selected_resource_id"],
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
            config,
            rows,
            cumulative,
            args.maximum_estimated_cost_usd,
            "infrastructure_failure" if summary["infrastructure_failure"] else None,
            usage_before,
            None,
        )
        if summary["infrastructure_failure"]:
            stop_reason = "infrastructure_failure"
            break
        previous_model = job["model_id"]
    if not stop_reason and previous_model is not None:
        stop_reason = _model_stop_reason(config, rows, str(previous_model))
    try:
        usage_after = fetch_key_status(key).usage_usd
    except ConfigurationError:
        usage_after = None
    output = _write_checkpoint(
        output_path,
        config,
        rows,
        cumulative,
        args.maximum_estimated_cost_usd,
        stop_reason,
        usage_before,
        usage_after,
    )
    print(json.dumps({key: value for key, value in output.items() if key != "runs"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

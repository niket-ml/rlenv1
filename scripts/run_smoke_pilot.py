#!/usr/bin/env python3
"""Plan or execute the pinned three-model Stage 7 smoke pilot."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.model_runner import ModelRunConfig, load_openrouter_key, run_model_episode

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "configs" / "smoke_models.json"


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def estimate_cost(summary: dict[str, Any], model: dict[str, Any]) -> float | None:
    usage = summary.get("token_usage") or {}
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    if not isinstance(input_tokens, int | float) or not isinstance(
        output_tokens, int | float
    ):
        return None
    return (
        float(input_tokens) * float(model["input_usd_per_million_tokens"])
        + float(output_tokens) * float(model["output_usd_per_million_tokens"])
    ) / 1_000_000


def prepare_resume_rows(
    existing: dict[str, Any],
    *,
    models: list[dict[str, Any]],
    attempts: int,
) -> tuple[list[dict[str, Any]], dict[str, int], float]:
    """Validate a partial smoke artifact and recover completed model attempts."""

    expected_models = [str(model["model_id"]) for model in models]
    plan = existing.get("plan") or {}
    if plan.get("models") != expected_models or plan.get("attempts_per_model") != attempts:
        raise ValueError("Existing smoke artifact does not match the frozen model plan")
    raw_rows = existing.get("runs")
    if not isinstance(raw_rows, list):
        raise ValueError("Existing smoke artifact has no run list")
    counts = dict.fromkeys(expected_models, 0)
    rows: list[dict[str, Any]] = []
    cumulative_estimate = 0.0
    guard_by_model = {
        str(model["model_id"]): float(model["planning_guard_per_run_usd"])
        for model in models
    }
    for raw_row in raw_rows:
        if not isinstance(raw_row, dict):
            raise ValueError("Existing smoke run entries must be objects")
        row = dict(raw_row)
        model_id = str(row.get("model_id"))
        if model_id not in counts or counts[model_id] >= attempts:
            raise ValueError(f"Unexpected or duplicate completed attempt for {model_id}")
        attempt_index = row.get("attempt_index", counts[model_id])
        if attempt_index != counts[model_id]:
            raise ValueError(f"Non-contiguous attempt history for {model_id}")
        row["attempt_index"] = attempt_index
        if row.get("classification") != "infrastructure_failure":
            counts[model_id] += 1
        estimate = row.get("estimated_cost_usd")
        cumulative_estimate += (
            float(estimate) if isinstance(estimate, int | float) else guard_by_model[model_id]
        )
        rows.append(row)
    return rows, counts, cumulative_estimate


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Run paid trajectories; without this flag the command is planning-only",
    )
    parser.add_argument(
        "--maximum-estimated-cost-usd",
        type=float,
        help="Required local planning cap when --execute is used",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume only missing attempts from a validated partial smoke artifact",
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=Path("artifacts/runtime/smoke_pilot_runs.json"),
        help="Project-relative smoke artifact path",
    )
    return parser


def write_smoke_artifact(
    output_path: Path,
    *,
    plan: dict[str, Any],
    maximum_estimated_cost_usd: float,
    cumulative_estimate: float,
    rows: list[dict[str, Any]],
    stop_reason: str | None,
    resumed: bool,
) -> None:
    """Atomically checkpoint the matrix after every completed paid request."""

    output = {
        "schema_version": "0.1",
        "executed_at": datetime.now(UTC).isoformat(),
        "plan": plan,
        "maximum_estimated_cost_usd": maximum_estimated_cost_usd,
        "estimated_cost_usd": cumulative_estimate,
        "runs": rows,
        "executed_run_count": len(rows),
        "completed_trajectory_count": sum(
            row["classification"] != "infrastructure_failure" for row in rows
        ),
        "valid_episode_count": sum(row["contract_valid"] is True for row in rows),
        "infrastructure_failure_count": sum(
            row["classification"] == "infrastructure_failure" for row in rows
        ),
        "stop_reason": stop_reason,
        "resumed": resumed,
        "leaderboard_evidence": False,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(output_path)


def main() -> int:
    args = build_parser().parse_args()
    config = read_json(CONFIG_PATH)
    models = config["models"]
    attempts = int(config["attempts_per_model"])
    point_estimate = float(config["cost_planning"]["nine_run_point_estimate_usd"])
    planning_guard = sum(
        attempts * float(model["planning_guard_per_run_usd"])
        for model in models
    )
    plan = {
        "models": [model["model_id"] for model in models],
        "attempts_per_model": attempts,
        "trajectory_count": attempts * len(models),
        "point_estimate_usd": point_estimate,
        "planning_guard_usd": planning_guard,
        "required_provider_key_limit_usd": config["cost_planning"][
            "required_provider_key_limit_usd"
        ],
    }
    if not args.execute:
        print(json.dumps({"mode": "planning_only", **plan}, indent=2, sort_keys=True))
        return 0
    if args.maximum_estimated_cost_usd is None or args.maximum_estimated_cost_usd <= 0:
        raise SystemExit("--maximum-estimated-cost-usd is required with --execute")
    if args.maximum_estimated_cost_usd < planning_guard:
        raise SystemExit(
            "Local cost cap is below the prespecified planning guard; no request made"
        )

    output_path = (PROJECT_ROOT / args.output_path).resolve()
    if PROJECT_ROOT.resolve() not in output_path.parents:
        raise SystemExit("--output-path must remain inside the project")
    if args.resume:
        if not output_path.is_file():
            raise SystemExit("--resume requires an existing smoke artifact")
        try:
            rows, completed_counts, cumulative_estimate = prepare_resume_rows(
                read_json(output_path), models=models, attempts=attempts
            )
        except ValueError as exc:
            raise SystemExit(f"Unsafe resume refused: {exc}") from exc
    else:
        if output_path.exists():
            raise SystemExit("Smoke artifact already exists; use --resume to avoid duplication")
        rows = []
        completed_counts = {str(model["model_id"]): 0 for model in models}
        cumulative_estimate = 0.0

    key = load_openrouter_key(PROJECT_ROOT)
    budget = config["trajectory_budget"]
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    stop_reason = None
    for model in models:
        model_id = str(model["model_id"])
        per_run_guard = float(model["planning_guard_per_run_usd"])
        for attempt in range(attempts):
            if attempt < completed_counts[model_id]:
                continue
            if cumulative_estimate + per_run_guard > args.maximum_estimated_cost_usd:
                stop_reason = "local_planning_cap"
                break
            run_id = (
                f"smoke-{model['model_id']}-{attempt}-{timestamp}"
                .replace("/", "-")
                .replace(":", "-")
            )
            artifacts = run_model_episode(
                PROJECT_ROOT,
                ModelRunConfig(
                    model_id=str(model["model_id"]),
                    run_id=run_id,
                    seed=20260906 + attempt,
                    temperature=None,
                    maximum_turns=int(budget["maximum_turns"]),
                    maximum_completion_tokens_per_turn=int(
                        budget["maximum_completion_tokens_per_turn"]
                    ),
                    maximum_total_completion_tokens=int(
                        budget["maximum_total_completion_tokens"]
                    ),
                    wall_clock_timeout_seconds=int(
                        budget["wall_clock_timeout_seconds"]
                    ),
                ),
                openrouter_key=key,
            )
            run_estimate = estimate_cost(artifacts.summary, model)
            cumulative_estimate += (
                run_estimate if run_estimate is not None else per_run_guard
            )
            rows.append(
                {
                    "attempt_index": attempt,
                    "run_id": artifacts.summary["run_id"],
                    "model_id": artifacts.summary["model_id"],
                    "classification": artifacts.summary["classification"],
                    "phase": artifacts.summary["phase"],
                    "score": artifacts.summary.get("attempt_score"),
                    "contract_valid": (
                        artifacts.summary.get("grade") or {}
                    ).get("contract_valid"),
                    "estimated_cost_usd": run_estimate,
                    "openrouter_cost_delta_usd": artifacts.summary.get(
                        "openrouter_cost_delta_usd"
                    ),
                    "token_usage": artifacts.summary.get("token_usage"),
                }
            )
            write_smoke_artifact(
                output_path,
                plan=plan,
                maximum_estimated_cost_usd=args.maximum_estimated_cost_usd,
                cumulative_estimate=cumulative_estimate,
                rows=rows,
                stop_reason=(
                    "infrastructure_failure"
                    if artifacts.summary["infrastructure_failure"]
                    else None
                ),
                resumed=args.resume,
            )
            if artifacts.summary["infrastructure_failure"]:
                stop_reason = "infrastructure_failure"
                break
        if stop_reason is not None:
            break

    write_smoke_artifact(
        output_path,
        plan=plan,
        maximum_estimated_cost_usd=args.maximum_estimated_cost_usd,
        cumulative_estimate=cumulative_estimate,
        rows=rows,
        stop_reason=stop_reason,
        resumed=args.resume,
    )
    output = read_json(output_path)
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

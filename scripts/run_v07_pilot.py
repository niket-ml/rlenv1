#!/usr/bin/env python3
"""Run the frozen v0.7 matrix in a five-cell Sol gate then optional GPT-5.2 stage."""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256
from uc_bench.model_runner import load_openrouter_key
from uc_bench.openrouter import fetch_key_status
from uc_bench.v07_analysis import analyze_v07
from uc_bench.v07_freeze import read_v07_freeze_manifest, v07_frozen_hashes
from uc_bench.v07_provider import load_v07_provider_adapters, verify_live_v07_identity
from uc_bench.v07_runner import V07RunConfig, run_v07_episode

ROOT = Path(__file__).resolve().parents[1]
PANEL_PATH = ROOT / "configs/hard_suite_v07_model_panel.json"
EXECUTION_PATH = ROOT / "configs/hard_suite_v07_execution.json"
COST_PATH = ROOT / "artifacts/diagnostics/hard_suite_v07_cost_plan.json"
OUTPUT_PATH = ROOT / "artifacts/diagnostics/hard_suite_v07_calibration_runs.json"
ANALYSIS_PATH = ROOT / "artifacts/diagnostics/hard_suite_v07_analysis.json"


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError(f"Expected object: {path}")
    return value


def all_jobs(execution: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "model_id": model_id,
            "condition_id": condition["condition_id"],
            "case_id": condition["case_id"],
            "mechanism": condition["mechanism"],
            "seed": int(condition["seed"]),
            "attempt_index": 0,
        }
        for model_id in execution["model_order"]
        for condition in execution["conditions_in_order"]
    ]


def select_jobs(jobs: list[dict[str, Any]], stage: str) -> list[dict[str, Any]]:
    model = "openai/gpt-5.6-sol" if stage == "sol" else "openai/gpt-5.2"
    return [job for job in jobs if job["model_id"] == model]


def _job_key(row: dict[str, Any]) -> tuple[str, str]:
    return str(row["model_id"]), str(row["condition_id"])


def validate_resume(
    checkpoint: dict[str, Any],
    *,
    hashes: dict[str, str],
    panel: dict[str, Any],
    execution: dict[str, Any],
    cost: dict[str, Any],
) -> None:
    if checkpoint.get("frozen_hashes") != hashes:
        raise ConfigurationError("Unsafe v0.7 resume: frozen hashes changed")
    if checkpoint.get("panel_digest") != canonical_sha256(panel):
        raise ConfigurationError("Unsafe v0.7 resume: model panel changed")
    if checkpoint.get("execution_digest") != canonical_sha256(execution):
        raise ConfigurationError("Unsafe v0.7 resume: execution contract changed")
    if checkpoint.get("cost_plan_digest") != canonical_sha256(cost):
        raise ConfigurationError("Unsafe v0.7 resume: cost plan changed")
    active = checkpoint.get("active_job")
    if active:
        summary = ROOT / str(active["run_directory"]) / "run_summary.json"
        if not summary.is_file():
            raise ConfigurationError(
                "Resume found an incomplete paid episode; stop for manual recovery, do not retry"
            )


def _checkpoint(
    *,
    stage: str,
    cap: float,
    jobs: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    usage_before: float,
    usage_after: float | None,
    stop_reason: str | None,
    freeze: dict[str, Any],
    panel: dict[str, Any],
    execution: dict[str, Any],
    cost: dict[str, Any],
    live_identity: dict[str, Any],
    active_job: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response_spend = sum(float(row.get("reported_cost_usd") or 0.0) for row in rows)
    key_delta = None if usage_after is None else max(0.0, usage_after - usage_before)
    value = {
        "schema_version": "0.7-pilot-1",
        "updated_at": datetime.now(UTC).isoformat(),
        "status": "controlled_internal_development_not_ranking",
        "current_stage": stage,
        "maximum_incremental_spend_usd": cap,
        "response_reported_spend_usd": round(response_spend, 8),
        "key_usage_before_usd": usage_before,
        "key_usage_after_usd": usage_after,
        "key_usage_delta_usd": key_delta,
        "spend_guard_value_usd": round(max(response_spend, key_delta or 0.0), 8),
        "planned_jobs": all_jobs(execution),
        "planned_job_count": 10,
        "completed_job_count": len(rows),
        "stop_reason": stop_reason,
        "active_job": active_job,
        "ranking_claim_allowed": False,
        "partition": "development",
        "heldout_requests": 0,
        "astra_requests": 0,
        "freeze_hash_set_digest": freeze["hash_set_digest"],
        "frozen_hashes": v07_frozen_hashes(ROOT),
        "panel_digest": canonical_sha256(panel),
        "execution_digest": canonical_sha256(execution),
        "cost_plan_digest": canonical_sha256(cost),
        "live_route_verification": live_identity,
        "runs": rows,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(OUTPUT_PATH)
    return value


def _write_analysis(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result = analyze_v07(rows, manual_grader_wording_failure=False)
    temporary = ANALYSIS_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(ANALYSIS_PATH)
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("sol", "gpt52"), required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--maximum-incremental-spend-usd", type=float)
    return parser


def main() -> int:
    args = _parser().parse_args()
    panel = _read(PANEL_PATH)
    execution = _read(EXECUTION_PATH)
    cost = _read(COST_PATH)
    adapters = load_v07_provider_adapters(ROOT)
    jobs = select_jobs(all_jobs(execution), args.stage)
    cap = float(execution["maximum_incremental_spend_usd"])
    if cap > 50 or cap != float(cost["proposed_hard_cap_usd"]):
        raise ConfigurationError("The frozen v0.7 spend cap is invalid")
    planning = {
        "mode": "planning_only",
        "stage": args.stage,
        "model": jobs[0]["model_id"],
        "stage_episode_count": 5,
        "full_episode_count": 10,
        "maximum_incremental_spend_usd": cap,
        "ranking_claim_allowed": False,
        "heldout_requests": 0,
        "astra_requests": 0,
    }
    if not args.execute:
        print(json.dumps(planning, indent=2, sort_keys=True))
        return 0
    if args.maximum_incremental_spend_usd != cap:
        raise ConfigurationError(f"Execution requires the exact frozen ${cap:.2f} cap")
    freeze = read_v07_freeze_manifest(ROOT)
    key = load_openrouter_key(ROOT)
    live_identity = verify_live_v07_identity(key, adapters)
    current = fetch_key_status(key)
    if current.limit_remaining_usd is None or current.limit_remaining_usd < cap:
        raise ConfigurationError("Current OpenRouter key-limit headroom is below the frozen cap")
    if args.resume:
        checkpoint = _read(OUTPUT_PATH)
        validate_resume(
            checkpoint,
            hashes=v07_frozen_hashes(ROOT),
            panel=panel,
            execution=execution,
            cost=cost,
        )
        rows = list(checkpoint.get("runs") or [])
        usage_before = float(checkpoint["key_usage_before_usd"])
        if checkpoint.get("active_job"):
            recovered = _read(
                ROOT / str(checkpoint["active_job"]["run_directory"]) / "run_summary.json"
            )
            if _job_key(recovered) not in {_job_key(row) for row in rows}:
                rows.append(_summary_row(recovered))
    else:
        if OUTPUT_PATH.exists():
            raise ConfigurationError("A v0.7 checkpoint exists; use --resume")
        if args.stage != "sol":
            raise ConfigurationError("The first v0.7 stage must be Sol")
        rows = []
        usage_before = float(current.usage_usd)
    if args.stage == "gpt52":
        analysis = _write_analysis(rows)
        if analysis["sol_gate"]["decision"] != "continue_to_gpt_5_2":
            raise ConfigurationError("GPT-5.2 is blocked by the frozen Sol gate")
        if len([row for row in rows if row.get("model_id") == "openai/gpt-5.6-sol"]) != 5:
            raise ConfigurationError("GPT-5.2 requires exactly five completed Sol cells")

    model_cost = cost["per_model"]
    completed = {_job_key(row) for row in rows}
    stop_reason: str | None = None
    usage_after: float | None = float(current.usage_usd)
    output = _checkpoint(
        stage=args.stage,
        cap=cap,
        jobs=jobs,
        rows=rows,
        usage_before=usage_before,
        usage_after=usage_after,
        stop_reason=None,
        freeze=freeze,
        panel=panel,
        execution=execution,
        cost=cost,
        live_identity=live_identity,
    )
    for job in jobs:
        if _job_key(job) in completed:
            continue
        status = fetch_key_status(key)
        usage_after = float(status.usage_usd)
        response_spend = sum(float(row.get("reported_cost_usd") or 0.0) for row in rows)
        spent = max(response_spend, usage_after - usage_before)
        guard = float(model_cost[str(job["model_id"])]["v07_no_cache_p90_per_episode"])
        if spent + guard > cap:
            stop_reason = "incremental_cost_cap_before_next_episode"
            break
        if status.limit_remaining_usd is None or status.limit_remaining_usd < guard:
            stop_reason = "openrouter_key_limit_remaining"
            break
        if rows:
            time.sleep(5)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        run_id = (
            f"v07-{str(job['model_id']).split('/')[-1]}-{job['condition_id']}-{timestamp}"
        )
        run_directory = f"build/hard_suite_v07_runs/{run_id}"
        active = {**job, "run_id": run_id, "run_directory": run_directory}
        _checkpoint(
            stage=args.stage,
            cap=cap,
            jobs=jobs,
            rows=rows,
            usage_before=usage_before,
            usage_after=usage_after,
            stop_reason=None,
            freeze=freeze,
            panel=panel,
            execution=execution,
            cost=cost,
            live_identity=live_identity,
            active_job=active,
        )
        budget = execution["episode_budget"]
        artifacts = run_v07_episode(
            ROOT,
            V07RunConfig(
                model_id=str(job["model_id"]),
                run_id=run_id,
                case_id=str(job["case_id"]),
                mechanism=str(job["mechanism"]),
                seed=int(job["seed"]),
                maximum_turns=int(budget["maximum_turns"]),
                maximum_completion_tokens_per_turn=int(
                    budget["maximum_completion_tokens_per_turn"]
                ),
                maximum_total_completion_tokens=int(
                    budget["maximum_total_completion_tokens"]
                ),
                wall_clock_timeout_seconds=int(budget["wall_clock_timeout_seconds"]),
                minimum_request_interval_seconds=float(
                    budget["minimum_request_interval_seconds"]
                ),
            ),
            openrouter_key=key,
            authorization_digest=str(freeze["hash_set_digest"]),
        )
        row = _summary_row(artifacts.summary)
        rows.append(row)
        completed.add(_job_key(row))
        try:
            usage_after = float(fetch_key_status(key).usage_usd)
        except ConfigurationError:
            usage_after = None
        output = _checkpoint(
            stage=args.stage,
            cap=cap,
            jobs=jobs,
            rows=rows,
            usage_before=usage_before,
            usage_after=usage_after,
            stop_reason=None,
            freeze=freeze,
            panel=panel,
            execution=execution,
            cost=cost,
            live_identity=live_identity,
        )
        if row["classification"] in {
            "infrastructure_failure",
            "provider_adapter_failure",
            "provider_policy_refusal",
            "unknown_harness_failure",
        }:
            stop_reason = str(row["classification"])
            break
        if any(row.get("identity_violations") or []):
            stop_reason = "provider_identity_failure"
            break
    analysis = _write_analysis(rows)
    if args.stage == "sol" and not stop_reason:
        if analysis["sol_gate"]["decision"] != "continue_to_gpt_5_2":
            stop_reason = "sol_gate_no_go"
        else:
            stop_reason = "sol_gate_review_complete_continue_authorized"
    if args.stage == "gpt52" and not stop_reason:
        stop_reason = "bounded_ten_episode_matrix_complete"
    output = _checkpoint(
        stage=args.stage,
        cap=cap,
        jobs=jobs,
        rows=rows,
        usage_before=usage_before,
        usage_after=usage_after,
        stop_reason=stop_reason,
        freeze=freeze,
        panel=panel,
        execution=execution,
        cost=cost,
        live_identity=live_identity,
    )
    output["analysis"] = analysis
    temporary = OUTPUT_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(OUTPUT_PATH)
    print(json.dumps({"stop_reason": stop_reason, "analysis": analysis}, indent=2, sort_keys=True))
    return 0


def _summary_row(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "model_id": summary["model_id"],
        "condition_id": summary["condition_id"],
        "case_id": summary["case_id"],
        "mechanism": summary["mechanism"],
        "seed": summary["run_config"]["seed"],
        "attempt_index": 0,
        "run_id": summary["run_id"],
        "run_directory": summary["run_directory"],
        "workspace_directory": summary["workspace_directory"],
        "classification": summary["classification"],
        "scientific_score": summary["scientific_score"],
        "reliability_score": summary["reliability_score"],
        "diagnostic_grade": summary["diagnostic_grade"],
        "submission": summary["submission"],
        "rollout_error": summary["rollout_error"],
        "stop_condition": summary["stop_condition"],
        "provider_requests": summary["provider_requests"],
        "provider_request_count": summary["provider_request_count"],
        "returned_models": summary["returned_models"],
        "actual_providers": summary["actual_providers"],
        "identity_violations": [
            violation
            for request in summary["provider_requests"]
            for violation in request.get("identity_violations") or []
        ],
        "token_usage": summary["token_usage"],
        "turn_count": summary["turn_count"],
        "cumulative_reported_cost_usd": summary["cumulative_reported_cost_usd"],
        "integrity": summary["integrity"],
        "complete_tool_history_paths": summary["complete_tool_history_paths"],
    }


if __name__ == "__main__":
    raise SystemExit(main())

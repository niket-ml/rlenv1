#!/usr/bin/env python3
"""Plan or run the frozen v0.6 development matrix under an exact spend cap."""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.hard_suite_v06 import iter_v06_scenarios, validate_v06_config
from uc_bench.hard_suite_v06_runner import V06RunConfig, run_v06_episode
from uc_bench.hashing import canonical_sha256
from uc_bench.model_runner import load_openrouter_key
from uc_bench.openrouter import fetch_key_status
from uc_bench.v06_freeze import read_v06_freeze_manifest, v06_frozen_hashes
from uc_bench.v06_probe_analysis import analyze_v06_probe
from uc_bench.v06_provider import load_provider_adapters, verify_live_adapter_identity

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PANEL_PATH = PROJECT_ROOT / "configs/hard_suite_v06_model_panel.json"
EXECUTION_PATH = PROJECT_ROOT / "configs/hard_suite_v06_execution.json"
COST_PATH = PROJECT_ROOT / "artifacts/diagnostics/hard_suite_v06_cost_plan.json"
OUTPUT_PATH = PROJECT_ROOT / "artifacts/diagnostics/hard_suite_v06_calibration_runs.json"


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError(f"Expected object: {path}")
    return value


def all_jobs(panel: dict[str, Any]) -> list[dict[str, Any]]:
    scenarios = iter_v06_scenarios(PROJECT_ROOT, partition="development")
    return [
        {
            "model_id": str(model["model_id"]),
            "scenario_id": str(scenario["scenario_id"]),
            "seed": int(scenario["seed"]),
            "attempt_index": 0,
        }
        for model in panel["models"]
        for scenario in scenarios
    ]


def select_jobs(
    jobs: list[dict[str, Any]], execution: dict[str, Any], strategy: str
) -> list[dict[str, Any]]:
    sentinel_ids = set(execution["sentinel"]["scenario_ids"])
    if strategy == "full":
        return list(jobs)
    if strategy == "sentinel":
        return [row for row in jobs if row["scenario_id"] in sentinel_ids]
    if strategy == "remaining":
        return [row for row in jobs if row["scenario_id"] not in sentinel_ids]
    raise ConfigurationError(f"Unknown v0.6 execution strategy: {strategy}")


def _job_key(row: dict[str, Any]) -> tuple[str, str, int]:
    return str(row["model_id"]), str(row["scenario_id"]), int(row["attempt_index"])


def _completed(rows: list[dict[str, Any]]) -> set[tuple[str, str, int]]:
    terminal = {
        "valid_episode",
        "agent_task_failure",
        "agent_refusal",
        "context_budget_exhaustion",
    }
    return {_job_key(row) for row in rows if row.get("classification") in terminal}


def validate_resume_checkpoint(
    existing: dict[str, Any],
    *,
    frozen_hashes: dict[str, str],
    panel: dict[str, Any],
    execution: dict[str, Any],
) -> None:
    """Fail closed if any frozen or execution-defining input changed."""

    if existing.get("frozen_hashes") != frozen_hashes:
        raise ConfigurationError("Unsafe resume: frozen hashes changed")
    if existing.get("panel_digest") != canonical_sha256(panel):
        raise ConfigurationError("Unsafe resume: panel changed")
    if existing.get("execution_digest") != canonical_sha256(execution):
        raise ConfigurationError("Unsafe resume: execution contract changed")


def sentinel_decision(
    rows: list[dict[str, Any]], model_ids: list[str], scenario_ids: list[str]
) -> dict[str, Any]:
    cells = {
        (str(row["model_id"]), str(row["scenario_id"])): row
        for row in rows
        if str(row.get("scenario_id")) in set(scenario_ids)
    }
    expected = {(model, scenario) for model in model_ids for scenario in scenario_ids}
    if set(cells) != expected:
        return {"decision": "incomplete", "reasons": ["sentinel_cells_missing"]}
    if any(row.get("identity_violation") for row in cells.values()):
        return {"decision": "stop", "reasons": ["route_or_model_identity_mismatch"]}
    adapter_failures = {
        "provider_adapter_failure",
        "provider_policy_refusal",
        "unknown_harness_failure",
    }
    if any(row.get("classification") in adapter_failures for row in cells.values()):
        return {"decision": "stop", "reasons": ["unresolved_provider_or_adapter_failure"]}
    analysis = analyze_v06_probe(
        cells.values(),
        config=_read(PROJECT_ROOT / "configs/hard_suite_v06.json"),
        model_ids=model_ids,
        scenario_ids=scenario_ids,
        project_root=PROJECT_ROOT,
    )
    return analysis["sentinel_decision"]


def attempt_control(
    classification: str, *, execution_attempt: int, retry_limit: int
) -> tuple[str, str | None]:
    """Return the next runner action without conflating provider and science."""

    if classification in {
        "provider_adapter_failure",
        "provider_policy_refusal",
        "unknown_harness_failure",
    }:
        return "stop", classification
    if classification == "infrastructure_failure":
        if execution_attempt >= retry_limit:
            return "stop", "infrastructure_retry_limit"
        return "retry_same_cell", None
    return "advance", None


def _checkpoint(
    *,
    strategy: str,
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
    live_route_verification: dict[str, Any],
) -> dict[str, Any]:
    response_cost = sum(float(row.get("reported_cost_usd") or 0.0) for row in rows)
    key_delta = None if usage_after is None else usage_after - usage_before
    spent_guard = max(response_cost, key_delta or 0.0)
    output = {
        "schema_version": "0.6-pilot-1",
        "updated_at": datetime.now(UTC).isoformat(),
        "status": "controlled_internal_development_not_ranking",
        "strategy": strategy,
        "ranking_claim_allowed": False,
        "partition": "development",
        "heldout_requests": 0,
        "astra_requests": 0,
        "maximum_incremental_spend_usd": cap,
        "response_reported_spend_usd": round(response_cost, 8),
        "key_usage_before_usd": usage_before,
        "key_usage_after_usd": usage_after,
        "key_usage_delta_usd": key_delta,
        "spend_guard_value_usd": round(spent_guard, 8),
        "planned_jobs": jobs,
        "planned_job_count": len(jobs),
        "completed_job_count": len(
            _completed(rows) & {_job_key(job) for job in jobs}
        ),
        "attempt_count": len(rows),
        "stop_reason": stop_reason,
        "freeze_hash_set_digest": freeze["hash_set_digest"],
        "frozen_hashes": v06_frozen_hashes(PROJECT_ROOT),
        "panel_digest": canonical_sha256(panel),
        "execution_digest": canonical_sha256(execution),
        "cost_plan_digest": canonical_sha256(cost),
        "live_route_verification": live_route_verification,
        "runs": rows,
    }
    temporary = OUTPUT_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(OUTPUT_PATH)
    return output


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", choices=("sentinel", "full", "remaining"), default="sentinel")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--maximum-incremental-cost-usd", type=float)
    return parser


def main() -> int:
    args = _parser().parse_args()
    panel = _read(PANEL_PATH)
    execution = _read(EXECUTION_PATH)
    cost = _read(COST_PATH)
    validate_v06_config(PROJECT_ROOT)
    adapters = load_provider_adapters(PROJECT_ROOT)
    jobs = select_jobs(all_jobs(panel), execution, args.strategy)
    cap = execution["full_matrix"]["maximum_incremental_spend_usd"]
    planned_cap = cost["full_matrix"]["conservative_maximum_cap_usd"]
    if args.strategy == "sentinel":
        cap = execution["sentinel"]["maximum_incremental_spend_usd"]
        planned_cap = cost["sentinel"]["conservative_maximum_cap_usd"]
    if cap != planned_cap:
        raise ConfigurationError("Execution cap differs from the audited cost plan")
    planning = {
        "mode": "planning_only",
        "strategy": args.strategy,
        "models": list(adapters),
        "episode_count": len(jobs),
        "maximum_incremental_spend_usd": cap,
        "freeze_exists": (
            PROJECT_ROOT / execution["freeze_manifest_path"]
        ).is_file(),
        "scientific_execution_authorized": execution["scientific_execution_authorized"],
        "heldout_requests": 0,
        "astra_requests": 0,
        "ranking_claim_allowed": False,
    }
    if not args.execute:
        print(json.dumps(planning, indent=2, sort_keys=True))
        return 0
    if execution.get("scientific_execution_authorized") is not True:
        raise ConfigurationError("v0.6 scientific execution is not authorized")
    if panel.get("scientific_execution_authorized") is not True:
        raise ConfigurationError("v0.6 panel scientific execution is not authorized")
    freeze = read_v06_freeze_manifest(PROJECT_ROOT)
    if cap is None or args.maximum_incremental_cost_usd != float(cap):
        raise ConfigurationError(f"Execution requires the exact proposed ${float(cap):.2f} cap")
    if any("astra" in model.lower() or "gpt-6" in model.lower() for model in adapters):
        raise ConfigurationError("Astra/GPT-6 entered the v0.6 development panel")
    if args.strategy == "remaining":
        existing = _read(OUTPUT_PATH)
        prior_decision = existing.get("sentinel_decision") or {}
        if prior_decision.get("decision") != "continue":
            raise ConfigurationError("Remaining matrix requires a passing sentinel decision")
    key = load_openrouter_key(PROJECT_ROOT)
    live_route_verification = verify_live_adapter_identity(key, adapters)
    if args.resume:
        existing = _read(OUTPUT_PATH)
        validate_resume_checkpoint(
            existing,
            frozen_hashes=v06_frozen_hashes(PROJECT_ROOT),
            panel=panel,
            execution=execution,
        )
        rows = list(existing.get("runs") or [])
        usage_before = float(existing["key_usage_before_usd"])
    else:
        if OUTPUT_PATH.exists():
            raise ConfigurationError("Pilot checkpoint exists; use --resume")
        rows = []
        usage_before = fetch_key_status(key).usage_usd
    completed = _completed(rows)
    model_costs = {
        str(row["model_id"]): row for row in cost["models"]
    }
    budget = execution["episode_budget"]
    stop_reason: str | None = None
    usage_after: float | None = None
    output = _checkpoint(
        strategy=args.strategy,
        cap=float(cap),
        jobs=jobs,
        rows=rows,
        usage_before=usage_before,
        usage_after=usage_after,
        stop_reason=stop_reason,
        freeze=freeze,
        panel=panel,
        execution=execution,
        cost=cost,
        live_route_verification=live_route_verification,
    )
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    for job in jobs:
        if _job_key(job) in completed:
            continue
        while True:
            status = fetch_key_status(key)
            usage_after = status.usage_usd
            response_spend = sum(
                float(row.get("reported_cost_usd") or 0.0) for row in rows
            )
            spent = max(response_spend, usage_after - usage_before)
            guard = float(model_costs[str(job["model_id"])]["p90_episode_cost_usd"])
            if spent + guard > float(cap):
                stop_reason = "incremental_cost_cap_before_next_episode"
                break
            if (
                status.limit_remaining_usd is not None
                and status.limit_remaining_usd < guard
            ):
                stop_reason = "openrouter_key_limit_remaining"
                break
            if rows:
                time.sleep(20)
            execution_attempt = sum(_job_key(row) == _job_key(job) for row in rows)
            retry_limit = int(budget["verified_infrastructure_episode_retries"])
            if execution_attempt > retry_limit:
                stop_reason = "infrastructure_retry_limit"
                break
            run_id = (
                f"hard6-{str(job['model_id']).split('/')[-1]}-{job['scenario_id']}-"
                f"{execution_attempt}-{timestamp}"
            )
            artifacts = run_v06_episode(
                PROJECT_ROOT,
                V06RunConfig(
                    model_id=str(job["model_id"]),
                    run_id=run_id,
                    scenario_id=str(job["scenario_id"]),
                    seed=int(job["seed"]),
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
                    minimum_request_interval_seconds=float(
                        budget["minimum_request_interval_seconds"]
                    ),
                ),
                openrouter_key=key,
            )
            summary = artifacts.summary
            identity_violation = any(
                request.get("identity_violations")
                for request in summary["provider_requests"]
            )
            rows.append(
                {
                    **job,
                    "execution_attempt": execution_attempt,
                    "run_id": summary["run_id"],
                    "run_directory": summary["run_directory"],
                    "workspace_directory": summary["workspace_directory"],
                    "classification": summary["classification"],
                    "score": summary["attempt_score"],
                    "diagnostic_grade": summary["diagnostic_grade"],
                    "reported_cost_usd": summary["cumulative_reported_cost_usd"],
                    "provider_request_count": summary["provider_request_count"],
                    "returned_models": summary["returned_models"],
                    "actual_providers": summary["actual_providers"],
                    "identity_violation": identity_violation,
                    "token_usage": summary["token_usage"],
                    "turn_count": summary["turn_count"],
                }
            )
            classification = str(summary["classification"])
            action, stop_reason = attempt_control(
                classification,
                execution_attempt=execution_attempt,
                retry_limit=retry_limit,
            )
            try:
                usage_after = fetch_key_status(key).usage_usd
            except ConfigurationError:
                usage_after = None
            output = _checkpoint(
                strategy=args.strategy,
                cap=float(cap),
                jobs=jobs,
                rows=rows,
                usage_before=usage_before,
                usage_after=usage_after,
                stop_reason=stop_reason,
                freeze=freeze,
                panel=panel,
                execution=execution,
                cost=cost,
                live_route_verification=live_route_verification,
            )
            if action != "retry_same_cell":
                break
        if stop_reason:
            output = _checkpoint(
                strategy=args.strategy,
                cap=float(cap),
                jobs=jobs,
                rows=rows,
                usage_before=usage_before,
                usage_after=usage_after,
                stop_reason=stop_reason,
                freeze=freeze,
                panel=panel,
                execution=execution,
                cost=cost,
                live_route_verification=live_route_verification,
            )
            break
    if args.strategy == "sentinel" and not stop_reason:
        decision = sentinel_decision(
            rows,
            list(adapters),
            list(execution["sentinel"]["scenario_ids"]),
        )
        output["sentinel_decision"] = decision
        temporary = OUTPUT_PATH.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(OUTPUT_PATH)
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

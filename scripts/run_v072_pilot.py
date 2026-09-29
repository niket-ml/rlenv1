#!/usr/bin/env python3
"""Run the frozen v0.7.2 calibrated-pilot stages with mandatory review stops."""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from run_v07_pilot import _job_key, _summary_row, all_jobs
from uc_bench.v072_freeze import read_v072_freeze_manifest, v072_frozen_hashes

from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256
from uc_bench.model_runner import load_openrouter_key
from uc_bench.openrouter import fetch_key_status
from uc_bench.v07_provider import load_v07_provider_adapters, verify_live_v07_identity
from uc_bench.v072_runner import V072RunConfig, run_v072_episode

ROOT = Path(__file__).resolve().parents[1]
EXECUTION_PATH = ROOT / "configs/hard_suite_v07_execution.json"
INTERFACE_PATH = ROOT / "configs/hard_suite_v072_interface.json"
COST_PATH = ROOT / "artifacts/diagnostics/hard_suite_v072_cost_plan.json"
OUTPUT_PATH = ROOT / "artifacts/diagnostics/hard_suite_v072_calibration_runs.json"

STAGE_CONDITIONS = {
    "sol_two_case_grader_check": ["case_01", "case_03_signal_collapses"],
    "sol_remaining_three": ["case_02", "case_03_signal_remains", "case_04"],
    "gpt52": [
        "case_01",
        "case_02",
        "case_03_signal_collapses",
        "case_03_signal_remains",
        "case_04",
    ],
}
STAGE_MODEL = {
    "sol_two_case_grader_check": "openai/gpt-5.6-sol",
    "sol_remaining_three": "openai/gpt-5.6-sol",
    "gpt52": "openai/gpt-5.2",
}
STAGE_CAP = {
    "sol_two_case_grader_check": 5.0,
    "sol_remaining_three": 12.0,
    "gpt52": 45.0,
}


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError(f"Expected object: {path}")
    return value


def _write(value: dict[str, Any]) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(OUTPUT_PATH)


def _selected_jobs(execution: dict[str, Any], stage: str) -> list[dict[str, Any]]:
    model = STAGE_MODEL[stage]
    conditions = set(STAGE_CONDITIONS[stage])
    return [
        job
        for job in all_jobs(execution)
        if job["model_id"] == model and job["condition_id"] in conditions
    ]


def _two_case_gate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    expected = set(STAGE_CONDITIONS["sol_two_case_grader_check"])
    selected = [
        row
        for row in rows
        if row["model_id"] == "openai/gpt-5.6-sol" and row["condition_id"] in expected
    ]
    classifications = [row.get("classification") for row in selected]
    representation_caps = [
        row["condition_id"]
        for row in selected
        if float(row.get("scientific_score") or 0.0) <= 15
        or row.get("diagnostic_grade", {}).get("environment_reliability_status", {}).get("status")
        in {"parsing_failure", "event_record_failure"}
    ]
    action_disagreements = [
        row["condition_id"]
        for row in selected
        if row.get("diagnostic_grade", {}).get("event_action_disagreements")
    ]
    unsupported_rewarded = [
        row["condition_id"]
        for row in selected
        if row.get("diagnostic_grade", {}).get("strict_full_mission_success") is True
        and any(
            failure in {"unsupported_final_decision", "claim_scope_overstated"}
            for failure in row.get("diagnostic_grade", {}).get("mission_failures", [])
        )
    ]
    both_near_perfect = len(selected) == 2 and all(
        float(row.get("scientific_score") or 0.0) >= 95 for row in selected
    )
    automatic_failures = {
        "wrong_episode_count": len(selected) != 2,
        "non_valid_episode": classifications != ["valid_episode", "valid_episode"],
        "representation_cap": bool(representation_caps),
        "event_action_disagreement": bool(action_disagreements),
        "unsupported_conclusion_rewarded": bool(unsupported_rewarded),
        "both_near_perfect_requires_procedure_dominance_review": both_near_perfect,
    }
    status = "no_go" if any(automatic_failures.values()) else "manual_construct_review_required"
    result = {
        "status": status,
        "interpretation": "infrastructure_and_grader_check_only_not_model_ranking",
        "conditions": sorted(row["condition_id"] for row in selected),
        "classifications": classifications,
        "scientific_scores": {row["condition_id"]: row.get("scientific_score") for row in selected},
        "strict_missions": {
            row["condition_id"]: row.get("diagnostic_grade", {}).get("strict_full_mission_success")
            for row in selected
        },
        "automatic_failures": automatic_failures,
        "representation_cap_conditions": representation_caps,
        "event_action_disagreement_conditions": action_disagreements,
        "unsupported_rewarded_conditions": unsupported_rewarded,
        "manual_checks_required": [
            "valid scientific content was not missed or misclassified",
            "no score loss is dominated by the explicit representation contract",
            "unsupported conclusions receive no mission success",
            "if both scores are at least 95, success is not mainly procedural",
        ],
        "continuation_allowed_automatically": False,
    }
    result["review_digest"] = canonical_sha256(result)
    return result


def _sol_gate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    selected = [row for row in rows if row["model_id"] == "openai/gpt-5.6-sol"]
    valid = len(selected) == 5 and all(
        row.get("classification") == "valid_episode" for row in selected
    )
    result = {
        "status": "manual_credibility_review_required" if valid else "no_go",
        "valid_five_sol_cells": valid,
        "scores": {row["condition_id"]: row.get("scientific_score") for row in selected},
        "missions": {
            row["condition_id"]: row.get("diagnostic_grade", {}).get("strict_full_mission_success")
            for row in selected
        },
        "continuation_allowed_automatically": False,
        "ranking_claim_allowed": False,
    }
    result["review_digest"] = canonical_sha256(result)
    return result


def _checkpoint(
    *,
    stage: str,
    rows: list[dict[str, Any]],
    usage_before: float,
    usage_after: float | None,
    freeze: dict[str, Any],
    stop_reason: str | None,
    live_identity: dict[str, Any],
    active_job: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response_spend = sum(float(row.get("cumulative_reported_cost_usd") or 0.0) for row in rows)
    key_delta = None if usage_after is None else max(0.0, usage_after - usage_before)
    value = {
        "schema_version": "0.7.2-pilot-1",
        "updated_at": datetime.now(UTC).isoformat(),
        "status": "calibrated_pilot_environment_not_ranking",
        "current_stage": stage,
        "stage_cumulative_spend_cap_usd": STAGE_CAP[stage],
        "global_scientific_spend_cap_usd": 45.0,
        "response_reported_spend_usd": round(response_spend, 8),
        "key_usage_before_usd": usage_before,
        "key_usage_after_usd": usage_after,
        "key_usage_delta_usd": key_delta,
        "spend_guard_value_usd": round(max(response_spend, key_delta or 0.0), 8),
        "completed_job_count": len(rows),
        "active_job": active_job,
        "stop_reason": stop_reason,
        "two_case_gate": _two_case_gate(rows),
        "sol_gate": _sol_gate(rows),
        "ranking_claim_allowed": False,
        "first_two_sol_are_infrastructure_and_grader_checks_only": True,
        "partition": "development",
        "heldout_requests": 0,
        "astra_requests": 0,
        "freeze_hash_set_digest": freeze["hash_set_digest"],
        "frozen_hashes": v072_frozen_hashes(ROOT),
        "live_route_verification": live_identity,
        "runs": rows,
    }
    _write(value)
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=tuple(STAGE_CONDITIONS), required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--maximum-incremental-spend-usd", type=float)
    parser.add_argument("--prior-review-digest")
    return parser


def main() -> int:
    args = _parser().parse_args()
    execution = _read(EXECUTION_PATH)
    interface = _read(INTERFACE_PATH)
    cost = _read(COST_PATH)
    jobs = _selected_jobs(execution, args.stage)
    cap = STAGE_CAP[args.stage]
    planning = {
        "mode": "planning_only",
        "version": "0.7.2",
        "stage": args.stage,
        "model_id": STAGE_MODEL[args.stage],
        "conditions": STAGE_CONDITIONS[args.stage],
        "cumulative_stage_cap_usd": cap,
        "global_scientific_cap_usd": 45.0,
        "ranking_claim_allowed": False,
        "heldout_requests": 0,
        "astra_requests": 0,
    }
    if not args.execute:
        print(json.dumps(planning, indent=2, sort_keys=True))
        return 0
    if args.maximum_incremental_spend_usd != cap:
        raise ConfigurationError(f"Stage requires the exact ${cap:.2f} cumulative cap")
    if interface["scientific_global_cap_usd"] != 45.0:
        raise ConfigurationError("The inherited global science cap changed")
    expected_cost_stage = next(
        row
        for row in cost["stages"]
        if row["stage_id"]
        == ("all_five_sol" if args.stage == "sol_remaining_three" else args.stage)
    )
    if float(expected_cost_stage["hard_cumulative_cap_usd"]) != cap:
        raise ConfigurationError("The requested stage cap differs from the frozen cost plan")
    freeze = read_v072_freeze_manifest(ROOT)
    key = load_openrouter_key(ROOT)
    adapters = load_v07_provider_adapters(ROOT)
    live_identity = verify_live_v07_identity(key, adapters)
    current = fetch_key_status(key)
    if current.limit_remaining_usd is None or current.limit_remaining_usd < cap:
        raise ConfigurationError(f"OpenRouter key headroom is below the ${cap:.2f} stage cap")

    if OUTPUT_PATH.exists():
        if not args.resume:
            raise ConfigurationError("A v0.7.2 checkpoint exists; use --resume")
        checkpoint = _read(OUTPUT_PATH)
        if checkpoint.get("frozen_hashes") != v072_frozen_hashes(ROOT):
            raise ConfigurationError("Unsafe resume: a frozen v0.7.2 input changed")
        if checkpoint.get("active_job"):
            summary = ROOT / checkpoint["active_job"]["run_directory"] / "run_summary.json"
            if not summary.is_file():
                raise ConfigurationError(
                    "Incomplete paid episode detected; stop for diagnosis and do not retry"
                )
        rows = list(checkpoint.get("runs") or [])
        usage_before = float(checkpoint["key_usage_before_usd"])
    else:
        if args.stage != "sol_two_case_grader_check":
            raise ConfigurationError("The first v0.7.2 stage must be the two-case Sol check")
        rows = []
        usage_before = float(current.usage_usd)

    if args.stage == "sol_remaining_three":
        gate = _two_case_gate(rows)
        if gate["status"] != "manual_construct_review_required":
            raise ConfigurationError("The frozen two-case check is a no-go")
        if args.prior_review_digest != gate["review_digest"]:
            raise ConfigurationError("Separate approval of the two-case review is required")
    if args.stage == "gpt52":
        gate = _sol_gate(rows)
        if gate["status"] != "manual_credibility_review_required":
            raise ConfigurationError("Five Sol cells do not support a credible measurement")
        if args.prior_review_digest != gate["review_digest"]:
            raise ConfigurationError("Separate approval of the five-Sol review is required")

    completed = {_job_key(row) for row in rows}
    usage_after: float | None = float(current.usage_usd)
    stop_reason: str | None = None
    _checkpoint(
        stage=args.stage,
        rows=rows,
        usage_before=usage_before,
        usage_after=usage_after,
        freeze=freeze,
        stop_reason=None,
        live_identity=live_identity,
    )
    episode_guard = 2.39 if args.stage != "gpt52" else 7.33
    for job in jobs:
        if _job_key(job) in completed:
            continue
        status = fetch_key_status(key)
        usage_after = float(status.usage_usd)
        response_spend = sum(float(row.get("cumulative_reported_cost_usd") or 0.0) for row in rows)
        spent = max(response_spend, usage_after - usage_before)
        if spent + episode_guard > cap:
            stop_reason = "cumulative_stage_cost_cap_before_next_episode"
            break
        if status.limit_remaining_usd is None or status.limit_remaining_usd < episode_guard:
            stop_reason = "openrouter_key_limit_remaining"
            break
        if rows:
            time.sleep(5)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"v072-{job['model_id'].split('/')[-1]}-{job['condition_id']}-{timestamp}"
        run_directory = f"build/hard_suite_v072_runs/{run_id}"
        active = {**job, "run_id": run_id, "run_directory": run_directory}
        _checkpoint(
            stage=args.stage,
            rows=rows,
            usage_before=usage_before,
            usage_after=usage_after,
            freeze=freeze,
            stop_reason=None,
            live_identity=live_identity,
            active_job=active,
        )
        budget = execution["episode_budget"]
        artifacts = run_v072_episode(
            ROOT,
            V072RunConfig(
                model_id=str(job["model_id"]),
                run_id=run_id,
                case_id=str(job["case_id"]),
                mechanism=str(job["mechanism"]),
                seed=int(job["seed"]),
                maximum_turns=int(budget["maximum_turns"]),
                maximum_completion_tokens_per_turn=int(
                    budget["maximum_completion_tokens_per_turn"]
                ),
                maximum_total_completion_tokens=int(budget["maximum_total_completion_tokens"]),
                wall_clock_timeout_seconds=int(budget["wall_clock_timeout_seconds"]),
                minimum_request_interval_seconds=float(budget["minimum_request_interval_seconds"]),
            ),
            openrouter_key=key,
            authorization_digest=freeze["hash_set_digest"],
        )
        row = _summary_row(artifacts.summary)
        rows.append(row)
        completed.add(_job_key(row))
        try:
            usage_after = float(fetch_key_status(key).usage_usd)
        except ConfigurationError:
            usage_after = None
        _checkpoint(
            stage=args.stage,
            rows=rows,
            usage_before=usage_before,
            usage_after=usage_after,
            freeze=freeze,
            stop_reason=None,
            live_identity=live_identity,
        )
        if row["classification"] != "valid_episode":
            stop_reason = str(row["classification"])
            break
        if row.get("identity_violations"):
            stop_reason = "provider_identity_failure"
            break

    if not stop_reason and args.stage == "sol_two_case_grader_check":
        gate = _two_case_gate(rows)
        stop_reason = (
            "two_case_fail_fast_no_go"
            if gate["status"] == "no_go"
            else "mandatory_two_case_manual_construct_review"
        )
    elif not stop_reason and args.stage == "sol_remaining_three":
        stop_reason = "mandatory_five_sol_manual_credibility_review"
    elif not stop_reason:
        stop_reason = "bounded_ten_episode_calibrated_pilot_complete"
    output = _checkpoint(
        stage=args.stage,
        rows=rows,
        usage_before=usage_before,
        usage_after=usage_after,
        freeze=freeze,
        stop_reason=stop_reason,
        live_identity=live_identity,
    )
    print(
        json.dumps(
            {
                "stop_reason": stop_reason,
                "two_case_gate": output["two_case_gate"],
                "sol_gate": output["sol_gate"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

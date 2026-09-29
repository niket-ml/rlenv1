#!/usr/bin/env python3
"""Run exactly the authorized three-condition v0.8 Sol development tranche."""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.model_runner import load_openrouter_key
from uc_bench.openrouter import fetch_key_status
from uc_bench.v07_provider import load_v07_provider_adapters, verify_live_v07_identity
from uc_bench.v08_runner import V08RunConfig, run_v08_episode
from uc_bench.v08_snapshot import read_v08_execution_snapshot
from uc_bench.v08_verifier import replay_archived_v072

ROOT = Path(__file__).resolve().parents[1]
EXECUTION_PATH = ROOT / "configs/hard_suite_v08_execution.json"
GATE_PATH = ROOT / "artifacts/diagnostics/hard_suite_v08_local_gate.json"
OUTPUT_PATH = ROOT / "artifacts/diagnostics/hard_suite_v08_development_runs.json"
REVIEW_PATH = ROOT / "artifacts/diagnostics/hard_suite_v08_five_condition_review.json"
REPORT_PATH = ROOT / "reports/generated/hard_suite_v08_five_condition_review.md"
CAP = 8.0

EXISTING_REPLAYS = {
    "case_01": ROOT
    / "build/hard_suite_v072_runs/v072-gpt-5.6-sol-case_01-20260909T043338Z",
    "case_03_signal_collapses": ROOT
    / "build/hard_suite_v072_runs/v072-gpt-5.6-sol-case_03_signal_collapses-20260909T043741Z",
}


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError(f"Expected JSON object: {path}")
    return value


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _job_key(row: dict[str, Any]) -> str:
    return str(row["condition_id"])


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
        "partial_scientific_quality": summary["partial_scientific_quality"],
        "complete_mission_success": summary["complete_mission_success"],
        "reliability_score": summary["reliability_score"],
        "diagnostic_grade": summary["diagnostic_grade"],
        "grader_exception": summary["grader_exception"],
        "grader_consistency": summary["grader_consistency"],
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
        "wall_time_seconds": sum(
            float(request.get("latency_seconds") or 0.0)
            for request in summary["provider_requests"]
        ),
        "cumulative_reported_cost_usd": summary["cumulative_reported_cost_usd"],
        "integrity": summary["integrity"],
    }


def validate_resume(
    checkpoint: dict[str, Any], *, snapshot: dict[str, Any]
) -> list[dict[str, Any]]:
    if checkpoint.get("execution_snapshot_digest") != snapshot["hash_set_digest"]:
        raise ConfigurationError("Unsafe v0.8 resume: execution snapshot changed")
    active = checkpoint.get("active_job")
    rows = list(checkpoint.get("runs") or [])
    if active:
        summary_path = ROOT / str(active["run_directory"]) / "run_summary.json"
        if not summary_path.is_file():
            raise ConfigurationError(
                "Interrupted paid episode has no complete summary; stop without retry"
            )
        recovered = _summary_row(_read(summary_path))
        if _job_key(recovered) not in {_job_key(row) for row in rows}:
            rows.append(recovered)
    return rows


def _checkpoint(
    *,
    rows: list[dict[str, Any]],
    usage_before: float,
    usage_after: float | None,
    snapshot: dict[str, Any],
    live_identity: dict[str, Any],
    stop_reason: str | None,
    active_job: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response_spend = sum(float(row["cumulative_reported_cost_usd"]) for row in rows)
    key_delta = None if usage_after is None else max(0.0, usage_after - usage_before)
    value = {
        "schema_version": "0.8-three-condition-development-run-1",
        "updated_at": datetime.now(UTC).isoformat(),
        "status": "development_diagnostic_not_ranking",
        "model_id": "openai/gpt-5.6-sol",
        "conditions": ["case_02", "case_03_signal_remains", "case_04"],
        "maximum_incremental_spend_usd": CAP,
        "response_reported_spend_usd": round(response_spend, 8),
        "key_usage_before_usd": usage_before,
        "key_usage_after_usd": usage_after,
        "key_usage_delta_usd": key_delta,
        "spend_guard_value_usd": round(max(response_spend, key_delta or 0.0), 8),
        "request_cost_checkpointing": "request_ledger_after_every_request",
        "completed_job_count": len(rows),
        "active_job": active_job,
        "stop_reason": stop_reason,
        "execution_snapshot_digest": snapshot["hash_set_digest"],
        "live_route_verification": live_identity,
        "partition": "development",
        "heldout_requests": 0,
        "astra_requests": 0,
        "ranking_claim_allowed": False,
        "runs": rows,
    }
    _write(OUTPUT_PATH, value)
    return value


def _stop_fault(row: dict[str, Any]) -> str | None:
    if row["classification"] in {
        "infrastructure_failure",
        "provider_adapter_failure",
        "unknown_harness_failure",
    }:
        return str(row["classification"])
    if row["classification"] == "cost_cap_reached":
        return "cumulative_cost_cap_reached"
    if row["identity_violations"]:
        return "provider_identity_or_fallback_failure"
    if row["grader_exception"]:
        return "grader_exception"
    if not row["grader_consistency"]["passed"]:
        return "grader_consistency_failure:" + ",".join(
            row["grader_consistency"]["faults"]
        )
    grade = row.get("diagnostic_grade") or {}
    resource = next(
        (
            item
            for item in grade.get("requirements") or []
            if item.get("requirement_id") == "decision_relevant_resource"
        ),
        None,
    )
    if resource and not resource["passed"]:
        observed = resource.get("observed") or {}
        expected = resource.get("expected") or {}
        if observed.get("purchased") in set(
            expected.get(observed.get("decision_question"), [])
        ):
            return "disclosed_valid_resource_alternative_rejected"
    return None


def _review_row(
    condition_id: str,
    grade: dict[str, Any],
    *,
    source: str,
    run: dict[str, Any] | None,
) -> dict[str, Any]:
    submission = (run or {}).get("submission") or {}
    c4 = (submission.get("checkpoints") or {}).get("C4") or {}
    return {
        "condition_id": condition_id,
        "source": source,
        "partial_scientific_quality": grade["partial_scientific_quality"],
        "complete_mission_success": grade["complete_mission_success"],
        "milestone_scores": grade["checkpoint_scores"],
        "first_important_failure": grade["first_decision_critical_failure"],
        "failure_class": (
            "scientific" if grade["first_decision_critical_failure"] else "none"
        ),
        "selected_investigation": grade["event_facts"]["selected_resource"],
        "selected_investigation_reason": c4.get("why_decision_resolving"),
        "decision_question": c4.get("decision_question"),
        "belief_change": grade["numeric_belief_change"],
        "initial_decision": grade["explicit_initial_decision_object"],
        "final_decision": grade["explicit_decision_object"],
        "cost_usd": (run or {}).get("cumulative_reported_cost_usd"),
        "turns": (run or {}).get("turn_count"),
        "completion_status": (run or {}).get("classification", "archived_valid_replay"),
        "reliability_score": grade["reliability_score"],
    }


def write_five_condition_review(rows: list[dict[str, Any]]) -> dict[str, Any]:
    combined: list[dict[str, Any]] = []
    for condition_id, directory in EXISTING_REPLAYS.items():
        grade = replay_archived_v072(
            ROOT, directory, condition_id=condition_id
        ).to_dict()
        combined.append(
            _review_row(
                condition_id,
                grade,
                source="zero_cost_v08_replay_of_trustworthy_v072_trajectory",
                run=None,
            )
        )
    for row in rows:
        grade = row.get("diagnostic_grade")
        if grade is None:
            combined.append(
                {
                    "condition_id": row["condition_id"],
                    "source": "new_v08_native_development_run",
                    "partial_scientific_quality": None,
                    "complete_mission_success": None,
                    "milestone_scores": None,
                    "first_important_failure": None,
                    "failure_class": row["classification"],
                    "selected_investigation": None,
                    "selected_investigation_reason": None,
                    "decision_question": None,
                    "belief_change": None,
                    "initial_decision": None,
                    "final_decision": None,
                    "cost_usd": row["cumulative_reported_cost_usd"],
                    "turns": row["turn_count"],
                    "completion_status": row["classification"],
                    "reliability_score": row["reliability_score"],
                }
            )
        else:
            combined.append(
                _review_row(
                    row["condition_id"],
                    grade,
                    source="new_v08_native_development_run",
                    run=row,
                )
            )
    order = {
        name: index
        for index, name in enumerate(
            [
                "case_01",
                "case_02",
                "case_03_signal_collapses",
                "case_03_signal_remains",
                "case_04",
            ]
        )
    }
    combined.sort(key=lambda item: order[item["condition_id"]])
    trajectories_valid = len(rows) == 3 and all(
        row["diagnostic_grade"] is not None
        and row["grader_consistency"]["passed"]
        and row["classification"] not in {
            "infrastructure_failure",
            "provider_adapter_failure",
            "unknown_harness_failure",
        }
        for row in rows
    )
    result = {
        "schema_version": "0.8-five-condition-development-review-1",
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "valid_development_diagnostic" if trajectories_valid else "invalid_or_incomplete",
        "interpretation": "one_attempt_per_condition_not_a_stable_ranking_or_ceiling_test",
        "conditions": combined,
        "new_trajectory_count": len(rows),
        "new_trajectories_valid_for_diagnosis": trajectories_valid,
        "complete_mission_count": sum(row["complete_mission_success"] is True for row in combined),
        "next_calibration_recommendation": (
            "After provider compatibility is rechecked, run one attempt on all five "
            "conditions for GPT-5.2 and one non-OpenAI frontier model (10 episodes total), "
            "then review before repeated seeds. This is the smallest cross-model comparison "
            "that covers every condition; it is still not a stable ranking."
            if trajectories_valid
            else (
                "No further model calls until the exact invalid or contaminated result "
                "is diagnosed."
            )
        ),
        "ranking_claim_allowed": False,
        "ceiling_claim_allowed": False,
        "heldout_requests": 0,
        "astra_requests": 0,
    }
    _write(REVIEW_PATH, result)
    lines = [
        "# UC-Bench v0.8 five-condition development review",
        "",
        (
            "This is a one-attempt controlled development diagnostic, not a stable "
            "model ranking or ceiling test."
        ),
        "",
        (
            "| Condition | Partial quality | Complete mission | Milestones "
            "C1/C2/C3/C4/C5 | Investigation | Initial → final | Completion | Cost |"
        ),
        "|---|---:|---:|---|---|---|---|---:|",
    ]
    for row in combined:
        scores = row["milestone_scores"] or {}
        milestones = (
            "/".join(
                str(round(float(scores.get(key, 0)), 1))
                for key in ("C1", "C2", "C3", "C4", "C5")
            )
            if scores
            else "n/a"
        )
        initial = (row["initial_decision"] or {}).get("disposition", "n/a")
        final = (row["final_decision"] or {}).get("disposition", "n/a")
        quality = row["partial_scientific_quality"]
        cost = row["cost_usd"]
        lines.append(
            f"| {row['condition_id']} | {quality if quality is not None else 'n/a'} | "
            f"{row['complete_mission_success']} | {milestones} | "
            f"{row['selected_investigation'] or 'n/a'} | {initial} → {final} | "
            f"{row['completion_status']} | {cost if cost is not None else 'historical'} |"
        )
    lines.extend(
        [
            "",
            "## Next calibration",
            "",
            result["next_calibration_recommendation"],
            "",
        ]
    )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--maximum-incremental-spend-usd", type=float)
    return parser


def main() -> int:
    args = _parser().parse_args()
    execution = _read(EXECUTION_PATH)
    planning = {
        "mode": "planning_only",
        "model_id": execution["model_id"],
        "conditions": [row["condition_id"] for row in execution["conditions_in_order"]],
        "episode_count": 3,
        "maximum_incremental_spend_usd": CAP,
        "partition": "development",
        "heldout_requests": 0,
        "astra_requests": 0,
    }
    if not args.execute:
        print(json.dumps(planning, indent=2, sort_keys=True))
        return 0
    if args.maximum_incremental_spend_usd != CAP:
        raise ConfigurationError("Execution requires the exact authorized $8.00 cap")
    gate = _read(GATE_PATH)
    if gate.get("status") != "passed":
        raise ConfigurationError("The complete v0.8 local gate has not passed")
    snapshot = read_v08_execution_snapshot(ROOT)
    key = load_openrouter_key(ROOT)
    adapters = load_v07_provider_adapters(ROOT)
    adapter = adapters["openai/gpt-5.6-sol"]
    live_identity = verify_live_v07_identity(key, {adapter.model_id: adapter})
    current = fetch_key_status(key)
    if current.limit_remaining_usd is None or current.limit_remaining_usd < CAP:
        raise ConfigurationError("OpenRouter key-limit headroom is below the $8 cap")

    if OUTPUT_PATH.exists():
        if not args.resume:
            raise ConfigurationError("A v0.8 development checkpoint exists; use --resume")
        checkpoint = _read(OUTPUT_PATH)
        rows = validate_resume(checkpoint, snapshot=snapshot)
        usage_before = float(checkpoint["key_usage_before_usd"])
    else:
        if args.resume:
            raise ConfigurationError("No v0.8 checkpoint exists to resume")
        rows = []
        usage_before = float(current.usage_usd)

    completed = {_job_key(row) for row in rows}
    usage_after: float | None = float(current.usage_usd)
    stop_reason: str | None = None
    _checkpoint(
        rows=rows,
        usage_before=usage_before,
        usage_after=usage_after,
        snapshot=snapshot,
        live_identity=live_identity,
        stop_reason=None,
    )
    guard = float(execution["per_episode_preflight_guard_usd"])
    for job in execution["conditions_in_order"]:
        if job["condition_id"] in completed:
            continue
        status = fetch_key_status(key)
        usage_after = float(status.usage_usd)
        response_spend = sum(float(row["cumulative_reported_cost_usd"]) for row in rows)
        spent = max(response_spend, usage_after - usage_before)
        if spent + guard > CAP:
            stop_reason = "cumulative_cost_cap_before_next_episode"
            break
        if status.limit_remaining_usd is None or status.limit_remaining_usd < guard:
            stop_reason = "openrouter_key_limit_remaining"
            break
        if rows:
            time.sleep(5)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"v08-gpt-5.6-sol-{job['condition_id']}-{timestamp}"
        run_directory = f"build/hard_suite_v08_runs/{run_id}"
        active = {**job, "run_id": run_id, "run_directory": run_directory}
        _checkpoint(
            rows=rows,
            usage_before=usage_before,
            usage_after=usage_after,
            snapshot=snapshot,
            live_identity=live_identity,
            stop_reason=None,
            active_job=active,
        )
        budget = execution["episode_budget"]
        artifacts = run_v08_episode(
            ROOT,
            V08RunConfig(
                model_id=execution["model_id"],
                run_id=run_id,
                case_id=job["case_id"],
                mechanism=job["mechanism"],
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
            authorization_digest=snapshot["hash_set_digest"],
            remaining_cost_cap_usd=CAP - spent,
        )
        row = _summary_row(artifacts.summary)
        rows.append(row)
        completed.add(row["condition_id"])
        try:
            usage_after = float(fetch_key_status(key).usage_usd)
        except ConfigurationError:
            usage_after = None
        _checkpoint(
            rows=rows,
            usage_before=usage_before,
            usage_after=usage_after,
            snapshot=snapshot,
            live_identity=live_identity,
            stop_reason=None,
        )
        stop_reason = _stop_fault(row)
        if stop_reason:
            break

    if not stop_reason and len(rows) == 3:
        stop_reason = "mandatory_three_condition_review"
    elif not stop_reason:
        stop_reason = "incomplete_three_condition_tranche"
    output = _checkpoint(
        rows=rows,
        usage_before=usage_before,
        usage_after=usage_after,
        snapshot=snapshot,
        live_identity=live_identity,
        stop_reason=stop_reason,
    )
    review = write_five_condition_review(rows)
    print(
        json.dumps(
            {
                "stop_reason": stop_reason,
                "completed_job_count": len(rows),
                "spend_guard_value_usd": output["spend_guard_value_usd"],
                "review_status": review["status"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

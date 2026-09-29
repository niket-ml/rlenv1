#!/usr/bin/env python3
"""Run exactly the final two-condition v0.8 Sol development check."""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.durable_runner import DurableRunConfig, run_durable_v08_episode
from uc_bench.errors import ConfigurationError
from uc_bench.execution_snapshot_03 import read_execution_snapshot_03
from uc_bench.model_runner import load_openrouter_key
from uc_bench.openrouter import fetch_credit_balance, fetch_key_status
from uc_bench.v07_provider import load_v07_provider_adapters, verify_live_v07_identity
from uc_bench.v08_verifier import replay_archived_v072

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs/final_sol_check.json"
GATE_PATH = ROOT / "artifacts/diagnostics/final_sol_infrastructure_gate.json"
OUTPUT_PATH = ROOT / "artifacts/diagnostics/final_sol_development_runs.json"
REVIEW_PATH = ROOT / "artifacts/diagnostics/final_sol_five_condition_review.json"
REPORT_PATH = ROOT / "reports/generated/final_sol_five_condition_review.md"
CASE2_REPLAY_PATH = ROOT / "artifacts/diagnostics/hard_suite_v08_case2_development_replay.json"
CAP = 4.78

EXISTING_RUNS = {
    "case_01": ROOT
    / "build/hard_suite_v072_runs/v072-gpt-5.6-sol-case_01-20260909T043338Z",
    "case_02": ROOT
    / "build/hard_suite_v08_runs/v08-gpt-5.6-sol-case_02-20260909T061848Z",
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
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _summary_row(summary: dict[str, Any]) -> dict[str, Any]:
    grade = summary.get("diagnostic_grade") or {}
    submission = summary.get("submission") or {}
    c4 = (submission.get("checkpoints") or {}).get("C4") or {}
    failure_id = grade.get("first_decision_critical_failure")
    failure_requirement = next(
        (
            row
            for row in grade.get("requirements") or []
            if row.get("requirement_id") == failure_id
        ),
        None,
    )
    return {
        "model_id": summary["model_id"],
        "condition_id": summary["condition_id"],
        "case_id": summary["case_id"],
        "mechanism": summary["mechanism"],
        "seed": summary["run_config"]["seed"],
        "run_id": summary["run_id"],
        "run_directory": summary["run_directory"],
        "classification": summary["classification"],
        "partial_scientific_quality": summary["partial_scientific_quality"],
        "complete_mission_success": summary["complete_mission_success"],
        "milestone_scores": grade.get("checkpoint_scores"),
        "selected_investigation": (grade.get("event_facts") or {}).get(
            "selected_resource"
        ),
        "selected_investigation_reason": c4.get("why_decision_resolving"),
        "belief_change": grade.get("numeric_belief_change"),
        "initial_decision": grade.get("explicit_initial_decision_object"),
        "final_decision": grade.get("explicit_decision_object"),
        "earliest_genuine_scientific_failure": failure_id,
        "failure_remedy": (failure_requirement or {}).get("remedy"),
        "failure_consequence": (failure_requirement or {}).get("consequence"),
        "reliability_score": summary["reliability_score"],
        "turns": summary["turn_count"],
        "tool_calls": summary["tool_call_count"],
        "cost_usd": summary["cumulative_reported_cost_usd"],
        "completion_status": summary["classification"],
        "grader_consistency": summary["grader_consistency"],
        "trajectory_persistence": summary["trajectory_persistence"],
        "provider_requests": summary["provider_requests"],
        "returned_models": summary["returned_models"],
        "actual_providers": summary["actual_providers"],
        "submission": submission,
        "diagnostic_grade": grade or None,
    }


def _schema_unrecovered(row: dict[str, Any]) -> bool:
    submission = row.get("submission") or {}
    if submission.get("completion_accepted"):
        return False
    events = submission.get("event_log") or []
    return any(event.get("schema_valid") is False for event in events)


def _stop_fault(row: dict[str, Any]) -> str | None:
    if row["classification"] in {
        "infrastructure_failure",
        "provider_adapter_failure",
        "provider_policy_refusal",
        "unknown_harness_failure",
    }:
        return str(row["classification"])
    if row["classification"] == "cost_cap_reached":
        return "cumulative_cost_cap_reached"
    if any(
        request.get("identity_violations")
        for request in row.get("provider_requests") or []
    ):
        return "provider_identity_or_fallback_failure"
    if _schema_unrecovered(row):
        return "unrecovered_schema_failure"
    if not row["grader_consistency"]["passed"]:
        return "grader_consistency_failure:" + ",".join(
            row["grader_consistency"]["faults"]
        )
    replay = row.get("trajectory_persistence") or {}
    if not replay.get("passed") or not replay.get("recomputed_grade_matches"):
        return "trajectory_persistence_or_replay_failure"
    return None


def _existing_review_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for condition_id in ("case_01", "case_03_signal_collapses"):
        grade = replay_archived_v072(
            ROOT,
            EXISTING_RUNS[condition_id],
            condition_id=condition_id,
        ).to_dict()
        historical = _read(EXISTING_RUNS[condition_id] / "run_summary.json")
        rows.append(
            {
                "condition_id": condition_id,
                "source": "validated_zero_cost_v08_replay_of_existing_trajectory",
                "partial_scientific_quality": grade["partial_scientific_quality"],
                "complete_mission_success": grade["complete_mission_success"],
                "milestone_scores": grade["checkpoint_scores"],
                "selected_investigation": grade["event_facts"]["selected_resource"],
                "belief_change": grade["numeric_belief_change"],
                "initial_decision": grade["explicit_initial_decision_object"],
                "final_decision": grade["explicit_decision_object"],
                "earliest_genuine_scientific_failure": grade[
                    "first_decision_critical_failure"
                ],
                "failure_remedy": None,
                "reliability_score": grade["reliability_score"],
                "turns": historical.get("turn_count"),
                "cost_usd": historical.get("cumulative_reported_cost_usd"),
                "completion_status": historical.get("classification"),
                "trajectory_persistence": {
                    "historical_trajectory": True,
                    "new_durable_persistence_not_retroactive": True,
                },
            }
        )
    case2 = _read(CASE2_REPLAY_PATH)["repaired_development_replay"]
    historical = _read(EXISTING_RUNS["case_02"] / "run_summary.json")
    rows.append(
        {
            "condition_id": "case_02",
            "source": "validated_zero_cost_development_verifier_replay",
            "partial_scientific_quality": case2["partial_scientific_quality"],
            "complete_mission_success": case2["complete_mission_success"],
            "milestone_scores": case2["checkpoint_scores"],
            "selected_investigation": case2["event_facts"]["selected_resource"],
            "belief_change": case2["numeric_belief_change"],
            "initial_decision": case2["explicit_initial_decision_object"],
            "final_decision": case2["explicit_decision_object"],
            "earliest_genuine_scientific_failure": case2[
                "first_decision_critical_failure"
            ],
            "failure_remedy": None,
            "reliability_score": case2["reliability_score"],
            "turns": historical.get("turn_count"),
            "cost_usd": historical.get("cumulative_reported_cost_usd"),
            "completion_status": "repaired_development_verifier_replay",
            "trajectory_persistence": {
                "historical_trajectory": True,
                "new_durable_persistence_not_retroactive": True,
            },
        }
    )
    return rows


def _write_review(new_rows: list[dict[str, Any]], *, stop_reason: str) -> dict[str, Any]:
    combined = [*_existing_review_rows()]
    for row in new_rows:
        combined.append(
            {
                key: value
                for key, value in row.items()
                if key not in {"provider_requests", "submission", "diagnostic_grade"}
            }
            | {"source": "fresh_snapshot_03_sol_development_run"}
        )
    order = {
        name: index
        for index, name in enumerate(
            (
                "case_01",
                "case_02",
                "case_03_signal_collapses",
                "case_03_signal_remains",
                "case_04",
            )
        )
    }
    combined.sort(key=lambda row: order[row["condition_id"]])
    both_new_valid = len(new_rows) == 2 and all(
        row["classification"] not in {
            "infrastructure_failure",
            "provider_adapter_failure",
            "unknown_harness_failure",
        }
        and row["grader_consistency"]["passed"]
        and row["trajectory_persistence"]["passed"]
        for row in new_rows
    )
    both_new_missions = both_new_valid and all(
        row["complete_mission_success"] is True for row in new_rows
    )
    failures = [
        {
            "condition_id": row["condition_id"],
            "failure": row["earliest_genuine_scientific_failure"],
            "actionable_intervention": row.get("failure_remedy"),
        }
        for row in combined
        if row.get("earliest_genuine_scientific_failure")
    ]
    interpretation = (
        "strong_single_attempt_ceiling_warning_across_mvp_not_saturation_or_ranking"
        if both_new_missions
        else (
            "useful_single_attempt_scientific_failures_require_repetition"
            if failures and both_new_valid
            else "incomplete_or_contaminated_stop_no_automatic_successor"
        )
    )
    value = {
        "schema_version": "0.8-five-condition-sol-development-summary-1",
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "valid_development_diagnostic" if both_new_valid else "invalid_or_incomplete",
        "interpretation": interpretation,
        "explicit_non_claims": [
            "This is not a model ranking.",
            "One success is not saturation.",
            "One attempt per condition does not establish reliable case pass rates.",
        ],
        "conditions": combined,
        "new_run_count": len(new_rows),
        "new_runs_valid_for_diagnosis": both_new_valid,
        "complete_mission_count": sum(
            row["complete_mission_success"] is True for row in combined
        ),
        "scientific_failures_and_interventions": failures,
        "stop_reason": stop_reason,
        "heldout_requests": 0,
        "astra_requests": 0,
        "ranking_claim_allowed": False,
        "saturation_claim_allowed": False,
    }
    _write(REVIEW_PATH, value)
    lines = [
        "# UC-Bench v0.8 five-condition Sol development summary",
        "",
        "This is a one-attempt development diagnostic, not a ranking or saturation claim.",
        "",
        (
            "| Condition | Partial | Mission | C1/C2/C3/C4/C5 | Investigation | "
            "Belief | Decision | Turns | Cost |"
        ),
        "|---|---:|---:|---|---|---|---|---:|---:|",
    ]
    for row in combined:
        scores = row.get("milestone_scores") or {}
        milestones = "/".join(
            str(round(float(scores.get(key, 0.0)), 1))
            for key in ("C1", "C2", "C3", "C4", "C5")
        )
        belief = row.get("belief_change") or {}
        belief_text = (
            f"{belief.get('support_probability_before', 'n/a')}→"
            f"{belief.get('support_probability_after', 'n/a')}"
        )
        decision = (row.get("final_decision") or {}).get("disposition", "n/a")
        lines.append(
            f"| {row['condition_id']} | {row['partial_scientific_quality']} | "
            f"{row['complete_mission_success']} | {milestones} | "
            f"{row.get('selected_investigation') or 'n/a'} | {belief_text} | "
            f"{decision} | {row.get('turns') or 'n/a'} | {row.get('cost_usd') or 0.0} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            interpretation.replace("_", " ") + ".",
            "",
        ]
    )
    if failures:
        lines.extend(["## First scientific failures and remedies", ""])
        for failure in failures:
            lines.append(
                f"- {failure['condition_id']}: {failure['failure']}; "
                f"remedy: {failure['actionable_intervention'] or 'requires targeted review'}."
            )
        lines.append("")
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    return value


def _checkpoint(
    *,
    rows: list[dict[str, Any]],
    usage_before: float,
    usage_after: float | None,
    snapshot: dict[str, Any],
    live_identity: dict[str, Any],
    pre_execution_status: dict[str, Any],
    stop_reason: str | None,
    active_job: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response_spend = sum(float(row["cost_usd"]) for row in rows)
    key_delta = None if usage_after is None else max(0.0, usage_after - usage_before)
    value = {
        "schema_version": "0.8-final-two-condition-sol-check-1",
        "updated_at": datetime.now(UTC).isoformat(),
        "status": "development_diagnostic_not_ranking",
        "model_id": "openai/gpt-5.6-sol",
        "conditions": ["case_03_signal_remains", "case_04"],
        "maximum_incremental_spend_usd": CAP,
        "response_reported_spend_usd": round(response_spend, 8),
        "key_usage_before_usd": usage_before,
        "key_usage_after_usd": usage_after,
        "key_usage_delta_usd": key_delta,
        "spend_guard_value_usd": round(max(response_spend, key_delta or 0.0), 8),
        "pre_execution_key_status": pre_execution_status,
        "completed_job_count": len(rows),
        "active_job": active_job,
        "stop_reason": stop_reason,
        "execution_snapshot_digest": snapshot["hash_set_digest"],
        "parent_snapshot_02_digest": snapshot["parent_snapshot_02"]["hash_set_digest"],
        "live_route_verification": live_identity,
        "partition": "development",
        "heldout_requests": 0,
        "astra_requests": 0,
        "ranking_claim_allowed": False,
        "runs": rows,
    }
    _write(OUTPUT_PATH, value)
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--maximum-incremental-spend-usd", type=float)
    return parser


def main() -> int:
    args = _parser().parse_args()
    config = _read(CONFIG_PATH)
    if not args.execute:
        print(
            json.dumps(
                {
                    "mode": "planning_only",
                    "model_id": config["model_id"],
                    "conditions": [
                        row["condition_id"] for row in config["conditions_in_order"]
                    ],
                    "maximum_incremental_spend_usd": CAP,
                    "heldout_requests": 0,
                    "astra_requests": 0,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.maximum_incremental_spend_usd != CAP:
        raise ConfigurationError("Execution requires the exact authorized $4.78 cap")
    if OUTPUT_PATH.exists():
        raise ConfigurationError(
            "The final Sol check already has a checkpoint; do not duplicate paid calls"
        )
    gate = _read(GATE_PATH)
    if gate.get("status") != "passed" or gate.get("api_requests") != 0:
        raise ConfigurationError("The zero-cost infrastructure gate is not passed")
    snapshot = read_execution_snapshot_03(ROOT)
    key = load_openrouter_key(ROOT)
    adapters = load_v07_provider_adapters(ROOT)
    adapter = adapters["openai/gpt-5.6-sol"]
    live_identity = verify_live_v07_identity(key, {adapter.model_id: adapter})
    current = fetch_key_status(key)
    credit_balance = fetch_credit_balance(key)
    if current.limit_remaining_usd is None or current.limit_remaining_usd < CAP:
        raise ConfigurationError("OpenRouter key-limit headroom is below the $4.78 cap")
    if credit_balance is not None and credit_balance["remaining_usd"] < CAP:
        raise ConfigurationError("OpenRouter account balance is below the $4.78 cap")
    pre_execution_status = {
        "checked_at": datetime.now(UTC).isoformat(),
        "usage_usd": float(current.usage_usd),
        "limit_usd": current.limit_usd,
        "limit_remaining_usd": current.limit_remaining_usd,
        "account_credit_balance": credit_balance,
        "cap_headroom_passed": current.limit_remaining_usd >= CAP,
    }
    usage_before = float(current.usage_usd)
    usage_after: float | None = usage_before
    rows: list[dict[str, Any]] = []
    stop_reason: str | None = None
    _checkpoint(
        rows=rows,
        usage_before=usage_before,
        usage_after=usage_after,
        snapshot=snapshot,
        live_identity=live_identity,
        pre_execution_status=pre_execution_status,
        stop_reason=None,
    )
    scientific_budget = _read(
        ROOT / str(config["episode_budget_source"])
    )["episode_budget"]
    guard = float(config["per_episode_preflight_guard_usd"])
    for job in config["conditions_in_order"]:
        status = fetch_key_status(key)
        usage_after = float(status.usage_usd)
        response_spend = sum(float(row["cost_usd"]) for row in rows)
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
        run_id = f"v08d-gpt-5.6-sol-{job['condition_id']}-{timestamp}"
        run_directory = f"build/hard_suite_v08_runs/{run_id}"
        active = {**job, "run_id": run_id, "run_directory": run_directory}
        _checkpoint(
            rows=rows,
            usage_before=usage_before,
            usage_after=usage_after,
            snapshot=snapshot,
            live_identity=live_identity,
            pre_execution_status=pre_execution_status,
            stop_reason=None,
            active_job=active,
        )
        print(f"START {job['condition_id']} cap_remaining={CAP - spent:.6f}", flush=True)
        artifacts = run_durable_v08_episode(
            ROOT,
            DurableRunConfig(
                model_id=config["model_id"],
                run_id=run_id,
                case_id=job["case_id"],
                mechanism=job["mechanism"],
                seed=int(job["seed"]),
                maximum_turns=int(scientific_budget["maximum_turns"]),
                maximum_completion_tokens_per_turn=int(
                    scientific_budget["maximum_completion_tokens_per_turn"]
                ),
                maximum_total_completion_tokens=int(
                    scientific_budget["maximum_total_completion_tokens"]
                ),
                wall_clock_timeout_seconds=int(
                    scientific_budget["wall_clock_timeout_seconds"]
                ),
                minimum_request_interval_seconds=float(
                    scientific_budget["minimum_request_interval_seconds"]
                ),
            ),
            openrouter_key=key,
            authorization_digest=snapshot["hash_set_digest"],
            remaining_cost_cap_usd=CAP - spent,
        )
        row = _summary_row(artifacts.summary)
        rows.append(row)
        print(
            f"DONE {row['condition_id']} class={row['classification']} "
            f"mission={row['complete_mission_success']} "
            f"quality={row['partial_scientific_quality']} cost={row['cost_usd']}",
            flush=True,
        )
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
            pre_execution_status=pre_execution_status,
            stop_reason=None,
        )
        stop_reason = _stop_fault(row)
        if stop_reason:
            break

    if not stop_reason and len(rows) == 2:
        stop_reason = "mandatory_two_condition_review"
    elif not stop_reason:
        stop_reason = "incomplete_two_condition_check"
    output = _checkpoint(
        rows=rows,
        usage_before=usage_before,
        usage_after=usage_after,
        snapshot=snapshot,
        live_identity=live_identity,
        pre_execution_status=pre_execution_status,
        stop_reason=stop_reason,
    )
    review = _write_review(rows, stop_reason=stop_reason)
    print(
        json.dumps(
            {
                "stop_reason": stop_reason,
                "completed_job_count": len(rows),
                "spend_guard_value_usd": output["spend_guard_value_usd"],
                "review_status": review["status"],
                "interpretation": review["interpretation"],
            },
            indent=2,
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

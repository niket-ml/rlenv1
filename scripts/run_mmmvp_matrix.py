from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.mmmvp_analysis import build_mmmvp_analysis, render_mmmvp_report
from uc_bench.mmmvp_freeze import read_mmmvp_freeze
from uc_bench.mmmvp_runner import MMMVPRunConfig, run_mmmvp_episode
from uc_bench.model_runner import _write_json, load_openrouter_key
from uc_bench.openrouter import fetch_credit_balance, fetch_key_status

STATE_PATH = Path("artifacts/mmmvp/matrix_state.json")
ANALYSIS_PATH = Path("artifacts/mmmvp/analysis.json")
REPORT_PATH = Path("reports/generated/uc_bench_mmmvp_pilot.md")
REQUEST_GUARD_USD = 5.2


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _condition(condition_id: str) -> tuple[str, str]:
    if condition_id == "case_03_signal_collapses":
        return "case_03", "signal_collapses"
    if condition_id == "case_03_signal_remains":
        return "case_03", "signal_remains"
    return condition_id, "default"


def _checkpoint(root: Path, state: dict[str, Any], key: str) -> None:
    _write_json(root / STATE_PATH, state, secret=key)


def _incremental_usage(key: str, baseline: float) -> tuple[float, float]:
    status = fetch_key_status(key)
    credits = fetch_credit_balance(key)
    return max(0.0, status.usage_usd - baseline), min(
        status.limit_usd - status.usage_usd, credits["remaining_usd"]
    )


def _sentinel_audit(root: Path, state: dict[str, Any]) -> dict[str, Any]:
    summaries = [_read(root / path) for path in state["summary_paths"]]
    sentinel = [row for row in summaries if row["condition_id"] == "case_02"]
    grader_faults = [
        {"model_id": row["model_id"], "faults": row["grader_consistency"]["faults"]}
        for row in sentinel
        if not row["grader_consistency"]["passed"]
    ]
    integrity_faults = [
        row["model_id"]
        for row in sentinel
        if not row["integrity"].get("start_state_untampered", False)
        or not row["trajectory_persistence"].get("passed", False)
    ]
    provider_failures = [
        row["model_id"]
        for row in sentinel
        if row["classification"]
        in {"provider_adapter_failure", "provider_policy_refusal", "infrastructure_failure"}
    ]
    unrecovered_schema = [
        row["model_id"]
        for row in sentinel
        if not row["integrity"].get("completion_accepted")
        and any(
            event.get("event") == "submit_rejected"
            for event in row.get("submission", {}).get("event_log", [])
        )
    ]
    faults = []
    if grader_faults:
        faults.append("grader_contamination")
    if integrity_faults:
        faults.append("security_or_integrity_failure")
    if len(provider_failures) >= 3:
        faults.append("widespread_provider_or_infrastructure_failure")
    if len(unrecovered_schema) >= 5:
        faults.append("systematic_submission_format_failure")
    return {
        "passed": not faults,
        "faults": faults,
        "grader_faults": grader_faults,
        "integrity_faults": integrity_faults,
        "provider_or_infrastructure_failures": provider_failures,
        "unrecovered_schema_failures": unrecovered_schema,
        "hidden_wording_requirement_check": "passed_by_frozen_score_source_and_control_gate",
        "sentinel_ranking_claim_allowed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        raise SystemExit("Pass --execute to run the frozen paid matrix")
    root = Path(__file__).resolve().parents[1]
    freeze = read_mmmvp_freeze(root)
    compatibility = _read(root / "artifacts/mmmvp/compatibility_results.json")
    if compatibility.get("widespread_incompatibility"):
        raise SystemExit("Compatibility stopped for widespread incompatibility")
    compatible = [
        row["model_id"]
        for row in compatibility["results"]
        if row["classification"] == "compatible"
    ]
    key = load_openrouter_key(root)
    baseline = float(compatibility["funding_baseline"]["key_usage_usd"])
    hard_cap = float(freeze["hard_cumulative_compatibility_and_science_cap_usd"])
    if (root / STATE_PATH).is_file():
        state = _read(root / STATE_PATH)
        if state["freeze_digest"] != freeze["hash_set_digest"]:
            raise SystemExit("Resume state differs from the frozen suite")
    else:
        state = {
            "schema_version": "uc-bench-mmmvp-matrix-state-1",
            "started_at": datetime.now(UTC).isoformat(),
            "status": "running_sentinel",
            "freeze_digest": freeze["hash_set_digest"],
            "compatible_models": compatible,
            "summary_paths": [],
            "completed_cells": [],
            "sentinel_audit": None,
            "hard_cap_usd": hard_cap,
        }
        _checkpoint(root, state, key)

    conditions = [
        "case_02",
        "case_01",
        "case_03_signal_collapses",
        "case_03_signal_remains",
        "case_04",
    ]
    for condition_index, selected_condition in enumerate(conditions):
        if condition_index == 1:
            audit = _sentinel_audit(root, state)
            state["sentinel_audit"] = audit
            if not audit["passed"]:
                state["status"] = "stopped_after_sentinel"
                _checkpoint(root, state, key)
                print(
                    json.dumps(
                        {"status": state["status"], "audit": audit}, sort_keys=True
                    ),
                    flush=True,
                )
                return
            state["status"] = "running_remaining_matrix"
            _checkpoint(root, state, key)
            print(
                json.dumps(
                    {"status": "sentinel_passed", "audit": audit}, sort_keys=True
                ),
                flush=True,
            )
        case_id, mechanism = _condition(selected_condition)
        for model_index, model_id in enumerate(compatible):
            cell = f"{model_id}::{selected_condition}"
            if cell in state["completed_cells"]:
                continue
            incremental, available = _incremental_usage(key, baseline)
            remaining = hard_cap - incremental
            if remaining < REQUEST_GUARD_USD or available < REQUEST_GUARD_USD:
                state["status"] = "stopped_insufficient_funding_guard"
                state["funding_stop"] = {
                    "incremental_usage_usd": incremental,
                    "remaining_cap_usd": remaining,
                    "available_headroom_usd": available,
                    "request_guard_usd": REQUEST_GUARD_USD,
                }
                _checkpoint(root, state, key)
                print(json.dumps(state["funding_stop"], sort_keys=True), flush=True)
                return
            run_id = (
                f"mmmvp-{model_id.replace('/', '-')}-{selected_condition}-"
                f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
            )
            config = MMMVPRunConfig(
                model_id=model_id,
                run_id=run_id,
                case_id=case_id,
                mechanism=mechanism,
                seed=880000 + condition_index * 100 + model_index,
            )
            result = run_mmmvp_episode(
                root,
                config,
                openrouter_key=key,
                authorization_digest=freeze["hash_set_digest"],
                remaining_cost_cap_usd=remaining,
            )
            relative = result.summary_path.relative_to(root).as_posix()
            state["summary_paths"].append(relative)
            state["completed_cells"].append(cell)
            state["last_completed_cell"] = cell
            state["last_completed_at"] = datetime.now(UTC).isoformat()
            _checkpoint(root, state, key)
            print(
                json.dumps(
                    {
                        "cell": cell,
                        "classification": result.summary["classification"],
                        "mission": result.summary["complete_mission_success"],
                        "partial": result.summary["partial_scientific_quality"],
                        "cost_usd": result.summary["cumulative_reported_cost_usd"],
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
            if not result.summary["grader_consistency"]["passed"]:
                state["status"] = "stopped_grader_contamination"
                _checkpoint(root, state, key)
                return
            recorded = [_read(root / path) for path in state["summary_paths"]]
            failed_provider_models = {
                row["model_id"]
                for row in recorded
                if row["classification"]
                in {
                    "provider_adapter_failure",
                    "provider_policy_refusal",
                    "infrastructure_failure",
                }
            }
            if len(failed_provider_models) >= 3:
                state["status"] = "stopped_widespread_provider_failure"
                state["failed_provider_models"] = sorted(failed_provider_models)
                _checkpoint(root, state, key)
                return
            if not result.summary["integrity"].get("start_state_untampered", False):
                state["status"] = "stopped_security_or_integrity_failure"
                _checkpoint(root, state, key)
                return
    state["status"] = "complete"
    state["completed_at"] = datetime.now(UTC).isoformat()
    _checkpoint(root, state, key)
    analysis = build_mmmvp_analysis(root)
    _write_json(root / ANALYSIS_PATH, analysis, secret=key)
    report_path = root / REPORT_PATH
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_mmmvp_report(analysis), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "complete",
                "scientific_episode_count": analysis["scientific_episode_count"],
                "combined_spend_usd": analysis["combined_spend_usd"],
                "analysis_path": ANALYSIS_PATH.as_posix(),
                "report_path": REPORT_PATH.as_posix(),
            },
            sort_keys=True,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()

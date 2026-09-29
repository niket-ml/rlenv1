"""Funding, fail-fast staging, and checkpoint state for the Case 1 pilot."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.case1_pilot_v1_compatibility import COMPATIBILITY_RESULTS
from uc_bench.case1_pilot_v1_provider import (
    load_case1_pilot_adapters,
    model_config,
)
from uc_bench.case1_pilot_v1_release import read_release_freeze
from uc_bench.case1_pilot_v1_runner import Case1PilotRunConfig, run_case1_pilot_episode
from uc_bench.errors import ConfigurationError
from uc_bench.model_runner import _write_json
from uc_bench.openrouter import fetch_credit_balance, fetch_key_status

EXECUTION_ROOT = Path("artifacts/uc_bench_case1_pilot_v1_rc1/science")
STATE_PATH = EXECUTION_ROOT / "pilot_state.json"
RUNS_ROOT = EXECUTION_ROOT / "runs"


def funding_snapshot(key: str) -> dict[str, float]:
    status = fetch_key_status(key)
    credits = fetch_credit_balance(key) or {}
    account = float(credits.get("remaining_usd", 0.0))
    limit_remaining = float(status.limit_remaining_usd)
    effective = min(account, limit_remaining)
    return {
        "key_usage_usd": float(status.usage_usd),
        "key_limit_usd": float(status.limit_usd),
        "key_limit_remaining_usd": limit_remaining,
        "account_remaining_usd": account,
        "effective_remaining_usd": effective,
    }


def funding_requirement(snapshot: dict[str, float], required: float) -> dict[str, float | bool]:
    return {
        "required_scientific_headroom_usd": required,
        "covered": snapshot["effective_remaining_usd"] + 1e-9 >= required,
        "additional_account_balance_required_usd": round(
            max(0.0, required - snapshot["account_remaining_usd"]), 8
        ),
        "additional_key_limit_required_usd": round(
            max(0.0, required - snapshot["key_limit_remaining_usd"]), 8
        ),
        "minimum_resulting_key_limit_usd": round(
            snapshot["key_usage_usd"] + required, 8
        ),
    }


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError(f"Expected a JSON object: {path}")
    return value


def _provider_errors(summary: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        dict(row["error"])
        for row in summary.get("provider_requests") or []
        if isinstance(row, dict) and isinstance(row.get("error"), dict)
    ]


def isolated_transient_provider_failure(summary: dict[str, Any]) -> bool:
    if int(summary.get("usable_provider_response_count") or 0) != 0:
        return False
    errors = _provider_errors(summary)
    if len(errors) != 1:
        return False
    status = errors[0].get("http_status")
    message = str(errors[0].get("message") or "").lower()
    return bool(
        status in {408, 409, 429}
        or isinstance(status, int)
        and status >= 500
        or any(marker in message for marker in ("timeout", "temporarily", "connection reset"))
    )


def shared_stop_faults(summary: dict[str, Any]) -> list[str]:
    faults: list[str] = []
    integrity = summary.get("integrity") or {}
    if not integrity.get("start_state_untampered", False):
        faults.append("frozen_start_state_corruption")
    if not integrity.get("protected_evidence_untampered", False):
        faults.append("protected_evidence_mutation")
    if integrity.get("protected_evidence_mutation_attempted", False):
        faults.append("protected_evidence_mutation_attempt")
    if not integrity.get("workspace_boundary_enforced", False):
        faults.append("workspace_boundary_failure")
    if summary.get("agent_received_provider_credentials"):
        faults.append("credential_exposure")
    if int(summary.get("usable_provider_response_count") or 0) and not (
        summary.get("trajectory_persistence") or {}
    ).get("passed", False):
        faults.append("persistence_or_replay_failure")
    if summary.get("classification") in {"grader_failure", "unknown_harness_failure"}:
        faults.append("shared_grader_or_harness_failure")
    if not (summary.get("grader_consistency") or {}).get("passed", True):
        faults.append("grader_contradiction")
    if any(error.get("http_status") == 401 for error in _provider_errors(summary)):
        faults.append("authentication_failure")
    return list(dict.fromkeys(faults))


def initialize_science_state(project_root: Path, *, key: str) -> dict[str, Any]:
    root = project_root.resolve()
    release = read_release_freeze(root)
    compatibility = _read_json(root / COMPATIBILITY_RESULTS)
    if compatibility.get("status") == "shared_stop":
        raise ConfigurationError("Compatibility found a shared harness failure")
    compatible = [
        str(row["model_id"])
        for row in compatibility.get("results") or []
        if row.get("classification") == "technically_compatible"
    ]
    expected = set(release["execution_order"])
    if not set(compatible) <= expected:
        raise ConfigurationError("Compatibility returned a model outside the frozen panel")
    if (root / STATE_PATH).exists():
        raise ConfigurationError("Pilot science state already exists")
    snapshot = funding_snapshot(key)
    required = float(release["budgets_usd"]["scientific_hard_cap"])
    requirement = funding_requirement(snapshot, required)
    state = {
        "schema_version": "uc-bench-case1-pilot-v1-state-1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "funding_blocked" if not requirement["covered"] else "ready_for_gemini",
        "release_digest": release["closure"]["aggregate_digest"],
        "compatibility_result_sha256": hashlib.sha256(
            (root / COMPATIBILITY_RESULTS).read_bytes()
        ).hexdigest(),
        "execution_order": release["execution_order"],
        "compatible_models": compatible,
        "compatibility_exclusions": sorted(expected - set(compatible)),
        "scientific_hard_cap_usd": required,
        "funding_after_compatibility": snapshot,
        "funding_requirement": requirement,
        "baseline_key_usage_usd": snapshot["key_usage_usd"],
        "scientific_spend_usd": 0.0,
        "completed_models": [],
        "excluded_models": [],
        "cell_attempts": {},
        "summary_paths": [],
        "global_stop_faults": [],
        "gemini_independent_replay_checked": False,
        "remaining_four_launched": False,
        "case2_requests": 0,
        "other_case_requests": 0,
        "sol_requests": 0,
        "astra_requests": 0,
    }
    _write_json(root / STATE_PATH, state, secret=key)
    return state


def _live_remaining(state: dict[str, Any], snapshot: dict[str, float]) -> float:
    observed = max(0.0, snapshot["key_usage_usd"] - state["baseline_key_usage_usd"])
    hard_remaining = float(state["scientific_hard_cap_usd"]) - observed
    return min(hard_remaining, snapshot["effective_remaining_usd"])


def _run_cell(
    root: Path,
    *,
    key: str,
    state: dict[str, Any],
    model_id: str,
    order_index: int,
) -> dict[str, Any]:
    adapters = load_case1_pilot_adapters(root)
    row = model_config(root, model_id)
    attempts = []
    for attempt_index in range(2):
        read_release_freeze(root)
        snapshot = funding_snapshot(key)
        remaining = _live_remaining(state, snapshot)
        if remaining <= 0:
            raise ConfigurationError("Scientific cumulative cap has no remaining allowance")
        run_id = (
            f"case1-pilot-{order_index:02d}-{model_id.replace('/', '-')}-"
            f"attempt-{attempt_index}"
        )
        result = run_case1_pilot_episode(
            root,
            Case1PilotRunConfig(run_id=run_id, model_id=model_id),
            adapter=adapters[model_id],
            openrouter_key=key,
            authorization_digest=state["release_digest"],
            remaining_cost_cap_usd=remaining,
            output_root=root / RUNS_ROOT,
            attempt_seed=int(row["attempt_seed"]),
            provider_seed=row.get("provider_seed"),
        )
        attempts.append(result)
        if not (attempt_index == 0 and isolated_transient_provider_failure(result.summary)):
            break
    state["cell_attempts"][model_id] = [
        result.summary_path.relative_to(root).as_posix() for result in attempts
    ]
    selected = attempts[-1]
    state["summary_paths"].append(selected.summary_path.relative_to(root).as_posix())
    state["completed_models"].append(model_id)
    state["last_completed_model"] = model_id
    state["last_completed_at"] = datetime.now(UTC).isoformat()
    after = funding_snapshot(key)
    state["scientific_spend_usd"] = round(
        max(0.0, after["key_usage_usd"] - state["baseline_key_usage_usd"]), 8
    )
    if state["scientific_spend_usd"] > state["scientific_hard_cap_usd"] + 1e-9:
        state["global_stop_faults"] = ["scientific_budget_breach"]
    faults = shared_stop_faults(selected.summary)
    state["global_stop_faults"] = list(
        dict.fromkeys([*state["global_stop_faults"], *faults])
    )
    if selected.summary.get("classification") in {
        "provider_adapter_failure",
        "provider_policy_refusal",
        "infrastructure_failure",
    } and not faults:
        state["excluded_models"].append(
            {
                "model_id": model_id,
                "classification": selected.summary.get("classification"),
                "attempt_count": len(attempts),
                "reason": "isolated_provider_or_route_failure",
            }
        )
    _write_json(root / STATE_PATH, state, secret=key)
    return selected.summary


def run_gemini_sentinel(project_root: Path, *, key: str) -> dict[str, Any]:
    root = project_root.resolve()
    state = _read_json(root / STATE_PATH)
    if state.get("status") != "ready_for_gemini":
        raise ConfigurationError("Pilot is not ready for its Gemini sentinel")
    model_id = "google/gemini-3.1-pro-preview"
    if model_id in state["compatible_models"]:
        summary = _run_cell(root, key=key, state=state, model_id=model_id, order_index=0)
        faults = shared_stop_faults(summary)
    else:
        summary = {"classification": "compatibility_exclusion"}
        faults = []
    state["gemini_independent_replay_checked"] = bool(
        summary.get("trajectory_persistence", {}).get("recomputed_grade_matches", False)
        or summary.get("complete_mission_success") is None
    )
    state["status"] = "global_stop" if faults else "gemini_review_required"
    _write_json(root / STATE_PATH, state, secret=key)
    return state


def approve_gemini_review(project_root: Path, *, key: str) -> dict[str, Any]:
    """Record the release owner's manual raw-artifact review before continuation."""

    root = project_root.resolve()
    state = _read_json(root / STATE_PATH)
    if state.get("status") != "gemini_review_required" or state["global_stop_faults"]:
        raise ConfigurationError("Gemini cannot be approved after a shared stop")
    state["gemini_manual_review"] = {
        "reviewed_at": datetime.now(UTC).isoformat(),
        "raw_artifacts_inspected": True,
        "lifecycle_uncontaminated": True,
        "grader_uncontaminated": True,
    }
    state["status"] = "ready_for_remaining_four"
    _write_json(root / STATE_PATH, state, secret=key)
    return state


def run_remaining_four(project_root: Path, *, key: str) -> dict[str, Any]:
    root = project_root.resolve()
    state = _read_json(root / STATE_PATH)
    if state.get("status") != "ready_for_remaining_four":
        raise ConfigurationError("Manual Gemini review has not authorized continuation")
    state["remaining_four_launched"] = True
    _write_json(root / STATE_PATH, state, secret=key)
    for index, model_id in enumerate(state["execution_order"][1:], start=1):
        if model_id not in state["compatible_models"]:
            continue
        _run_cell(root, key=key, state=state, model_id=model_id, order_index=index)
        if state["global_stop_faults"]:
            state["status"] = "global_stop"
            _write_json(root / STATE_PATH, state, secret=key)
            return state
    state["status"] = "completed_mandatory_review"
    state["completed_at"] = datetime.now(UTC).isoformat()
    state["funding_after_science"] = funding_snapshot(key)
    _write_json(root / STATE_PATH, state, secret=key)
    return state


__all__ = [
    "EXECUTION_ROOT",
    "RUNS_ROOT",
    "STATE_PATH",
    "approve_gemini_review",
    "funding_requirement",
    "funding_snapshot",
    "initialize_science_state",
    "isolated_transient_provider_failure",
    "run_gemini_sentinel",
    "run_remaining_four",
    "shared_stop_faults",
]

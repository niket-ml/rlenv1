"""Fresh bounded ten-model Case-2 sentinel for frozen RC1.4."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.mmmvp_open_freeze import read_open_mmmvp_freeze
from uc_bench.mmmvp_open_rc14_audit import issue_is_disclosed
from uc_bench.mmmvp_open_rc14_cost import COST_PLAN_PATH
from uc_bench.mmmvp_open_rc14_freeze import read_rc14_release_freeze
from uc_bench.mmmvp_open_rc14_harness import load_converged_rc14_adapters
from uc_bench.mmmvp_open_rc14_order import ORDER_PATH
from uc_bench.mmmvp_open_rc14_runner import run_rc14_open_mmmvp_episode
from uc_bench.mmmvp_open_runner import OpenRunConfig
from uc_bench.model_runner import _write_json
from uc_bench.openrouter import fetch_credit_balance, fetch_key_status

STATE_PATH = Path("artifacts/mmmvp_open_rc14/sentinel_state.json")
SCIENTIFIC_HARD_CAP_USD = 52.0


def _effective_headroom(key: str) -> tuple[float, dict[str, float]]:
    status = fetch_key_status(key)
    credits = fetch_credit_balance(key) or {}
    account = float(credits.get("remaining_usd", 0.0))
    effective = min(status.limit_remaining_usd, account)
    return effective, {
        "key_usage_usd": status.usage_usd,
        "key_limit_usd": status.limit_usd,
        "key_limit_remaining_usd": status.limit_remaining_usd,
        "account_remaining_usd": account,
        "effective_remaining_usd": effective,
    }


def _maximum_request_cost(adapter: Any) -> float:
    output_tokens = min(5000, int(adapter.maximum_completion_tokens))
    return (
        int(adapter.context_length) * adapter.maximum_prompt_price_usd_per_million
        + output_tokens * adapter.maximum_completion_price_usd_per_million
    ) / 1_000_000


def _transient_provider_failure(summary: dict[str, Any]) -> bool:
    if int(summary.get("usable_provider_response_count") or 0) != 0:
        return False
    requests = summary.get("provider_requests") or []
    errors = [row.get("error") for row in requests if row.get("error")]
    if len(errors) != 1:
        return False
    error = errors[0]
    status = error.get("http_status")
    message = str(error.get("message") or "").lower()
    return bool(
        status in {408, 409, 429}
        or isinstance(status, int)
        and status >= 500
        or any(token in message for token in ("timeout", "temporarily", "connection reset"))
    )


def rc14_global_stop_faults(summary: dict[str, Any]) -> list[str]:
    """Return shared corruption faults; model and isolated route failures continue."""

    faults: list[str] = []
    integrity = summary.get("integrity") or {}
    classification = str(summary.get("classification"))
    if not summary.get("grader_consistency", {}).get("passed", False) and classification not in {
        "provider_adapter_failure",
        "provider_policy_refusal",
        "infrastructure_failure",
    }:
        faults.append("verifier_contradiction")
    if not integrity.get("start_state_untampered", False):
        faults.append("scientific_start_state_changed")
    if not integrity.get("protected_evidence_untampered", False):
        faults.append("protected_evidence_changed")
    if integrity.get("protected_evidence_mutation_attempted", False):
        faults.append("protected_evidence_tampering")
    if not integrity.get("workspace_boundary_enforced", False):
        faults.append("workspace_boundary_failure")
    if not summary.get("trajectory_persistence", {}).get("passed", False):
        faults.append("trajectory_lifecycle_inconsistency")
    if summary.get("agent_received_provider_credentials") or summary.get(
        "agent_network_enabled"
    ):
        faults.append("credential_or_network_leakage")
    if classification in {"unknown_harness_failure", "grader_failure"}:
        faults.append("shared_harness_failure")
    return list(dict.fromkeys(faults))


def run_rc14_sentinel(
    project_root: Path,
    *,
    key: str,
    authorization_digest: str,
) -> dict[str, Any]:
    root = project_root.resolve()
    scientific = read_open_mmmvp_freeze(root)
    release = read_rc14_release_freeze(root)
    if authorization_digest != release["infrastructure_digest"]:
        raise ConfigurationError("Sentinel authorization differs from RC1.4 freeze")
    cost = json.loads((root / COST_PLAN_PATH).read_text(encoding="utf-8"))
    if not cost.get("paid_execution_allowed"):
        raise ConfigurationError("RC1.4 execution is blocked by its combined cost gate")
    adapters = load_converged_rc14_adapters(root)
    order_record = json.loads((root / ORDER_PATH).read_text(encoding="utf-8"))
    if order_record.get("release_infrastructure_digest") != release[
        "infrastructure_digest"
    ]:
        raise ConfigurationError("Sentinel order was not created from this RC1.4 freeze")
    order = list(order_record["execution_order"])
    if set(order) != set(adapters):
        raise ConfigurationError("RC1.4 order differs from the compatible frozen subset")
    target = root / STATE_PATH
    if target.exists():
        raise ConfigurationError("RC1.4 sentinel state already exists; rerun is forbidden")

    available, funding = _effective_headroom(key)
    sentinel_p90 = float(cost["sentinel_no_cache_p90_usd"])
    if available < SCIENTIFIC_HARD_CAP_USD:
        raise ConfigurationError("Live headroom no longer covers the $52 scientific cap")
    baseline_usage = funding["key_usage_usd"]
    state: dict[str, Any] = {
        "schema_version": "uc-bench-open-mmmvp-rc1-4-sentinel-state-1",
        "started_at": datetime.now(UTC).isoformat(),
        "status": "running",
        "scientific_freeze_digest": scientific["hash_set_digest"],
        "release_infrastructure_digest": release["infrastructure_digest"],
        "condition_id": "case_02",
        "execution_order": order,
        "compatible_model_count": len(order),
        "scientific_hard_cap_usd": SCIENTIFIC_HARD_CAP_USD,
        "compatibility_cost_usd": float(cost["compatibility_cost_usd"]),
        "sentinel_no_cache_p90_usd": sentinel_p90,
        "scientific_spend_usd": 0.0,
        "funding_before_science": funding,
        "baseline_key_usage_usd": baseline_usage,
        "completed_models": [],
        "excluded_models": [],
        "cell_attempts": {},
        "summary_paths": [],
        "stop_faults": [],
        "remaining_matrix_launched": False,
    }
    _write_json(target, state, secret=key)

    for index, model_id in enumerate(order):
        read_open_mmmvp_freeze(root)
        read_rc14_release_freeze(root)
        available_now, funding_now = _effective_headroom(key)
        observed_scientific_spend = max(
            0.0, funding_now["key_usage_usd"] - baseline_usage
        )
        global_remaining = min(
            SCIENTIFIC_HARD_CAP_USD - observed_scientific_spend, available_now
        )
        request_guard = _maximum_request_cost(adapters[model_id])
        episode_cap = global_remaining - request_guard
        if episode_cap <= 0:
            state["status"] = "stopped_hard_cap_guard"
            state["stop_faults"] = ["hard_cap_exhaustion_guard"]
            state["funding_stop"] = {
                "scientific_spend_usd": observed_scientific_spend,
                "global_remaining_usd": global_remaining,
                "maximum_single_request_cost_usd": request_guard,
            }
            _write_json(target, state, secret=key)
            return state
        attempts = []
        for attempt_index in range(2):
            run_id = (
                f"open-mmmvp-rc14-sentinel-{index:02d}-"
                f"{model_id.replace('/', '-')}-case-02-attempt-{attempt_index}"
            )
            result = run_rc14_open_mmmvp_episode(
                root,
                OpenRunConfig(run_id=run_id, model_id=model_id, case_id="case_02"),
                adapter=adapters[model_id],
                openrouter_key=key,
                authorization_digest=release["infrastructure_digest"],
                remaining_cost_cap_usd=episode_cap,
            )
            attempts.append(result)
            if not (attempt_index == 0 and _transient_provider_failure(result.summary)):
                break
        state["cell_attempts"][model_id] = [
            item.summary_path.relative_to(root).as_posix() for item in attempts
        ]
        result = attempts[-1]
        relative = result.summary_path.relative_to(root).as_posix()
        state["summary_paths"].append(relative)
        state["completed_models"].append(model_id)
        state["last_completed_at"] = datetime.now(UTC).isoformat()
        state["last_completed_model"] = model_id
        state["last_classification"] = result.summary["classification"]
        state["last_cost_usd"] = result.summary["cumulative_reported_cost_usd"]
        _, observed_funding = _effective_headroom(key)
        state["scientific_spend_usd"] = round(
            max(0.0, observed_funding["key_usage_usd"] - baseline_usage), 8
        )
        if state["scientific_spend_usd"] > SCIENTIFIC_HARD_CAP_USD + 1e-9:
            state["status"] = "stopped_hard_cap_exceeded"
            state["stop_faults"] = ["hard_cap_exceeded"]
            _write_json(target, state, secret=key)
            return state
        classification = str(result.summary.get("classification"))
        if classification in {
            "provider_adapter_failure",
            "provider_policy_refusal",
            "infrastructure_failure",
        } and not rc14_global_stop_faults(result.summary):
            state["excluded_models"].append(
                {
                    "model_id": model_id,
                    "classification": classification,
                    "attempt_count": len(attempts),
                    "reason": "isolated_provider_or_route_failure",
                }
            )
        faults = rc14_global_stop_faults(result.summary)
        rejected_issues = [
            issue
            for event in (
                result.summary.get("submission", {}).get("event_log") or []
            )
            if event.get("event")
            in {"validation_plan_rejected", "followup_plan_rejected", "submit_rejected"}
            for issue in event.get("schema_issues") or []
        ]
        if any(not issue_is_disclosed(issue) for issue in rejected_issues):
            faults.append("undisclosed_contract_requirement")
        if faults:
            state["status"] = "global_stop"
            state["stop_faults"] = faults
            _write_json(target, state, secret=key)
            return state
        _write_json(target, state, secret=key)

    available_after, funding_after = _effective_headroom(key)
    state["completed_at"] = datetime.now(UTC).isoformat()
    state["status"] = "completed_mandatory_review"
    state["funding_after"] = funding_after
    state["effective_headroom_after_usd"] = available_after
    state["remaining_matrix_launched"] = False
    _write_json(target, state, secret=key)
    return state


__all__ = [
    "SCIENTIFIC_HARD_CAP_USD",
    "STATE_PATH",
    "rc14_global_stop_faults",
    "run_rc14_sentinel",
]

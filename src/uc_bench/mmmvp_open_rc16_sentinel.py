"""Nine-model Case-2 sentinel for frozen RC1.6."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.mmmvp_open_rc15_adapter import load_rc15_launch_routes
from uc_bench.mmmvp_open_rc16_cost import COST_PLAN_PATH, SCIENTIFIC_HARD_CAP_USD
from uc_bench.mmmvp_open_rc16_freeze import read_rc16_release_freeze
from uc_bench.mmmvp_open_rc16_order import ORDER_PATH
from uc_bench.mmmvp_open_rc16_rehearsal import POSTFREEZE_PREFLIGHT_PATH
from uc_bench.mmmvp_open_rc16_runner import run_rc16_open_mmmvp_episode
from uc_bench.mmmvp_open_runner import OpenRunConfig
from uc_bench.model_runner import _write_json
from uc_bench.openrouter import fetch_credit_balance, fetch_key_status

STATE_PATH = Path("artifacts/mmmvp_open_rc16/sentinel_state.json")


def _effective_headroom(key: str) -> tuple[float, dict[str, float]]:
    status = fetch_key_status(key)
    credits = fetch_credit_balance(key) or {}
    account = float(credits.get("remaining_usd", 0.0))
    effective = min(float(status.limit_remaining_usd), account)
    return effective, {
        "key_usage_usd": float(status.usage_usd),
        "key_limit_usd": float(status.limit_usd),
        "key_limit_remaining_usd": float(status.limit_remaining_usd),
        "account_remaining_usd": account,
        "effective_remaining_usd": effective,
    }


def _maximum_request_cost(route: Any) -> float:
    completion = min(5_000, route.maximum_completion_tokens)
    return (
        route.context_length * route.prompt_price_usd_per_million
        + completion * route.completion_price_usd_per_million
    ) / 1_000_000


def _errors(summary: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        row["error"]
        for row in summary.get("provider_requests") or []
        if isinstance(row, dict) and isinstance(row.get("error"), dict)
    ]


def _transient_provider_failure(summary: dict[str, Any]) -> bool:
    if int(summary.get("usable_provider_response_count") or 0) != 0:
        return False
    errors = _errors(summary)
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


def rc16_global_stop_faults(summary: dict[str, Any]) -> list[str]:
    """Only shared corruption and genuine lifecycle faults stop the panel."""

    faults: list[str] = []
    integrity = summary.get("integrity") or {}
    if not integrity.get("start_state_untampered", False):
        faults.append("shared_state_corruption:start_state")
    if not integrity.get("protected_evidence_untampered", False):
        faults.append("protected_data_mutation")
    if integrity.get("protected_evidence_mutation_attempted", False):
        faults.append("protected_data_mutation_attempt")
    if not integrity.get("workspace_boundary_enforced", False):
        faults.append("shared_state_corruption:workspace_boundary")
    if summary.get("agent_received_provider_credentials"):
        faults.append("credential_exposure")
    usable = int(summary.get("usable_provider_response_count") or 0)
    lifecycle = summary.get("trajectory_persistence") or {}
    if usable and not lifecycle.get("passed", False):
        faults.append("genuine_inconsistent_tool_lifecycle")
    if summary.get("classification") in {"grader_failure", "unknown_harness_failure"}:
        faults.append("shared_grader_or_harness_failure")
    if not (summary.get("grader_consistency") or {}).get("passed", True):
        faults.append("shared_grader_consistency_failure")
    if any(error.get("http_status") == 401 for error in _errors(summary)):
        faults.append("shared_authentication_failure")
    return list(dict.fromkeys(faults))


def run_rc16_sentinel(
    project_root: Path,
    *,
    key: str,
    authorization_digest: str,
) -> dict[str, Any]:
    root = project_root.resolve()
    release = read_rc16_release_freeze(root)
    if authorization_digest != release["infrastructure_digest"]:
        raise ConfigurationError("Sentinel authorization differs from RC1.6 freeze")
    preflight = json.loads((root / POSTFREEZE_PREFLIGHT_PATH).read_text())
    if (
        preflight.get("status") != "passed"
        or preflight.get("release_infrastructure_digest") != release["infrastructure_digest"]
    ):
        raise ConfigurationError("Frozen RC1.6 launch preflight did not pass")
    cost = json.loads((root / COST_PLAN_PATH).read_text(encoding="utf-8"))
    if not cost.get("paid_execution_allowed") or not cost.get("independent_calculations_agree"):
        raise ConfigurationError("RC1.6 execution is blocked by its cost gate")
    routes = load_rc15_launch_routes(root)
    order_record = json.loads((root / ORDER_PATH).read_text(encoding="utf-8"))
    if order_record.get("release_infrastructure_digest") != release["infrastructure_digest"]:
        raise ConfigurationError("RC1.6 order was not created from this freeze")
    order = list(order_record["execution_order"])
    if len(order) != 9 or set(order) != set(routes):
        raise ConfigurationError("RC1.6 order differs from its compatible panel")
    target = root / STATE_PATH
    if target.exists():
        raise ConfigurationError("RC1.6 sentinel state already exists; rerun is forbidden")

    available, funding = _effective_headroom(key)
    if available < SCIENTIFIC_HARD_CAP_USD:
        raise ConfigurationError("Live headroom does not cover the $50 scientific cap")
    baseline_usage = funding["key_usage_usd"]
    state: dict[str, Any] = {
        "schema_version": "uc-bench-open-mmmvp-rc1-6-sentinel-state-1",
        "started_at": datetime.now(UTC).isoformat(),
        "status": "running",
        "release_infrastructure_digest": release["infrastructure_digest"],
        "condition_id": "case_02",
        "execution_order": order,
        "scientific_hard_cap_usd": SCIENTIFIC_HARD_CAP_USD,
        "scientific_spend_usd": 0.0,
        "funding_before_science": funding,
        "baseline_key_usage_usd": baseline_usage,
        "completed_models": [],
        "excluded_models": [],
        "cell_attempts": {},
        "summary_paths": [],
        "stop_faults": [],
        "other_conditions_launched": False,
    }
    _write_json(target, state, secret=key)

    for index, model_id in enumerate(order):
        read_rc16_release_freeze(root)
        available_now, funding_now = _effective_headroom(key)
        observed_spend = max(0.0, funding_now["key_usage_usd"] - baseline_usage)
        remaining = min(SCIENTIFIC_HARD_CAP_USD - observed_spend, available_now)
        episode_cap = remaining - _maximum_request_cost(routes[model_id])
        if episode_cap <= 0:
            state["status"] = "global_stop"
            state["stop_faults"] = ["budget_breach_guard"]
            _write_json(target, state, secret=key)
            return state

        attempts = []
        for attempt_index in range(2):
            run_id = (
                f"open-mmmvp-rc16-sentinel-{index:02d}-"
                f"{model_id.replace('/', '-')}-case-02-attempt-{attempt_index}"
            )
            result = run_rc16_open_mmmvp_episode(
                root,
                OpenRunConfig(run_id=run_id, model_id=model_id, case_id="case_02"),
                adapter=routes[model_id].adapter,
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
        summary = result.summary
        state["summary_paths"].append(result.summary_path.relative_to(root).as_posix())
        state["completed_models"].append(model_id)
        state["last_completed_at"] = datetime.now(UTC).isoformat()
        state["last_completed_model"] = model_id
        state["last_classification"] = summary["classification"]
        _, observed_funding = _effective_headroom(key)
        state["scientific_spend_usd"] = round(
            max(0.0, observed_funding["key_usage_usd"] - baseline_usage), 8
        )
        if state["scientific_spend_usd"] > SCIENTIFIC_HARD_CAP_USD + 1e-9:
            state["status"] = "global_stop"
            state["stop_faults"] = ["budget_breach"]
            _write_json(target, state, secret=key)
            return state
        faults = rc16_global_stop_faults(summary)
        if faults:
            state["status"] = "global_stop"
            state["stop_faults"] = faults
            _write_json(target, state, secret=key)
            return state
        classification = str(summary.get("classification"))
        if classification in {
            "provider_adapter_failure",
            "provider_policy_refusal",
            "infrastructure_failure",
        }:
            state["excluded_models"].append(
                {
                    "model_id": model_id,
                    "classification": classification,
                    "attempt_count": len(attempts),
                    "reason": "isolated_provider_or_route_failure",
                }
            )
        _write_json(target, state, secret=key)

    available_after, funding_after = _effective_headroom(key)
    state["completed_at"] = datetime.now(UTC).isoformat()
    state["status"] = "completed_mandatory_review"
    state["funding_after"] = funding_after
    state["effective_headroom_after_usd"] = available_after
    _write_json(target, state, secret=key)
    return state


__all__ = ["STATE_PATH", "rc16_global_stop_faults", "run_rc16_sentinel"]

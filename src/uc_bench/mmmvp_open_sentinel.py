"""Bounded Case-2 sentinel orchestration for the frozen open MMMVP RC1."""

from __future__ import annotations

import json
import random
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.mmmvp_open_freeze import read_open_mmmvp_freeze
from uc_bench.mmmvp_open_provider import load_open_compatible_adapters
from uc_bench.mmmvp_open_release_freeze import read_open_release_freeze
from uc_bench.mmmvp_open_runner import OpenRunConfig, run_open_mmmvp_episode
from uc_bench.model_runner import _write_json
from uc_bench.openrouter import fetch_credit_balance, fetch_key_status

STATE_PATH = Path("artifacts/mmmvp_open_release/sentinel_state.json")
HARD_CAP_USD = 25.0
ORDER_SEED = 20260909


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError(f"Expected object: {path}")
    return value


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


def _max_request_cost(adapter: Any) -> float:
    output_tokens = min(5000, int(adapter.maximum_completion_tokens))
    return (
        int(adapter.context_length) * adapter.maximum_prompt_price_usd_per_million
        + output_tokens * adapter.maximum_completion_price_usd_per_million
    ) / 1_000_000


def _integrity_stop(summary: dict[str, Any]) -> list[str]:
    faults: list[str] = []
    if not summary.get("grader_consistency", {}).get("passed", False):
        faults.append("verifier_contradiction")
    integrity = summary.get("integrity") or {}
    if not integrity.get("start_state_untampered", False):
        faults.append("scientific_start_state_changed")
    if not integrity.get("protected_evidence_untampered", False):
        faults.append("protected_evidence_changed")
    if not summary.get("trajectory_persistence", {}).get("passed", False):
        faults.append("trajectory_not_restorable")
    if any(row.get("identity_violations") for row in summary.get("provider_requests") or []):
        faults.append("route_or_model_identity_mismatch")
    return faults


def run_open_sentinel(
    project_root: Path,
    *,
    key: str,
    authorization_digest: str,
) -> dict[str, Any]:
    root = project_root.resolve()
    scientific = read_open_mmmvp_freeze(root)
    release = read_open_release_freeze(root)
    if authorization_digest != release["category_digest_set"]:
        raise ConfigurationError("Sentinel authorization differs from the release freeze")
    compatibility = _read(root / "artifacts/mmmvp_open_release/compatibility_results.json")
    if compatibility.get("status") != "passed":
        raise ConfigurationError("At least eight compatibility canaries have not passed")
    adapters = load_open_compatible_adapters(root)
    if len(adapters) < 8:
        raise ConfigurationError("Fewer than eight compatible models remain")
    target = root / STATE_PATH
    if target.exists():
        raise ConfigurationError("Sentinel state already exists; automatic rerun is forbidden")

    available, funding = _effective_headroom(key)
    if available < HARD_CAP_USD:
        raise ConfigurationError(
            f"Sentinel needs ${HARD_CAP_USD:.2f} headroom; only ${available:.2f} remains"
        )
    baseline_usage = funding["key_usage_usd"]
    order = list(adapters)
    random.Random(ORDER_SEED).shuffle(order)
    state: dict[str, Any] = {
        "schema_version": "uc-bench-open-mmmvp-sentinel-state-1",
        "started_at": datetime.now(UTC).isoformat(),
        "status": "running",
        "scientific_freeze_digest": scientific["hash_set_digest"],
        "release_category_digest_set": release["category_digest_set"],
        "condition_id": "case_02",
        "order_seed": ORDER_SEED,
        "execution_order": order,
        "compatible_model_count": len(order),
        "hard_cap_usd": HARD_CAP_USD,
        "funding_before": funding,
        "baseline_key_usage_usd": baseline_usage,
        "completed_models": [],
        "summary_paths": [],
        "stop_faults": [],
        "remaining_matrix_launched": False,
    }
    _write_json(target, state, secret=key)

    for index, model_id in enumerate(order):
        read_open_mmmvp_freeze(root)
        read_open_release_freeze(root)
        available_now, funding_now = _effective_headroom(key)
        incremental = max(0.0, funding_now["key_usage_usd"] - baseline_usage)
        global_remaining = min(HARD_CAP_USD - incremental, available_now)
        request_guard = _max_request_cost(adapters[model_id])
        episode_cap = global_remaining - request_guard
        if episode_cap <= 0:
            state["status"] = "stopped_hard_cap_guard"
            state["stop_faults"] = ["hard_cap_exhaustion_guard"]
            state["funding_stop"] = {
                "incremental_spend_usd": incremental,
                "global_remaining_usd": global_remaining,
                "maximum_single_request_cost_usd": request_guard,
            }
            _write_json(target, state, secret=key)
            return state
        run_id = f"open-mmmvp-sentinel-{index:02d}-{model_id.replace('/', '-')}-case-02"
        result = run_open_mmmvp_episode(
            root,
            OpenRunConfig(run_id=run_id, model_id=model_id, case_id="case_02"),
            adapter=adapters[model_id],
            openrouter_key=key,
            authorization_digest=scientific["hash_set_digest"],
            remaining_cost_cap_usd=episode_cap,
        )
        relative = result.summary_path.relative_to(root).as_posix()
        state["summary_paths"].append(relative)
        state["completed_models"].append(model_id)
        state["last_completed_at"] = datetime.now(UTC).isoformat()
        state["last_completed_model"] = model_id
        state["last_classification"] = result.summary["classification"]
        state["last_cost_usd"] = result.summary["cumulative_reported_cost_usd"]
        faults = _integrity_stop(result.summary)
        if faults:
            state["status"] = "stopped_fail_fast"
            state["stop_faults"] = faults
            _write_json(target, state, secret=key)
            return state
        _write_json(target, state, secret=key)

    available_after, funding_after = _effective_headroom(key)
    state["completed_at"] = datetime.now(UTC).isoformat()
    state["status"] = "completed_mandatory_review"
    state["funding_after"] = funding_after
    state["observed_incremental_spend_usd"] = max(
        0.0, funding_after["key_usage_usd"] - baseline_usage
    )
    state["effective_headroom_after_usd"] = available_after
    state["remaining_matrix_launched"] = False
    _write_json(target, state, secret=key)
    return state


__all__ = ["HARD_CAP_USD", "ORDER_SEED", "STATE_PATH", "run_open_sentinel"]

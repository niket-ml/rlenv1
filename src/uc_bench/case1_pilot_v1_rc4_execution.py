"""Funding, stage gates, and isolated-cell execution for frozen RC4."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.case1_pilot_v1_execution import funding_requirement, funding_snapshot
from uc_bench.case1_pilot_v1_provider import load_case1_pilot_adapters, model_config
from uc_bench.case1_pilot_v1_rc4_release import read_rc4_freeze
from uc_bench.case1_pilot_v1_rc4_runner import run_case1_pilot_rc4_episode
from uc_bench.case1_pilot_v1_release import read_release_freeze as read_rc1_freeze
from uc_bench.case1_pilot_v1_runner import Case1PilotRunConfig
from uc_bench.errors import ConfigurationError
from uc_bench.model_runner import _write_json
from uc_bench.v071_auth import credential_locations

EXECUTION_ROOT = Path("artifacts/uc_bench_case1_pilot_v1_rc4/science")
STATE_PATH = EXECUTION_ROOT / "pilot_state.json"
RUNS_ROOT = EXECUTION_ROOT / "runs"
GPT5 = "openai/gpt-5"


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError(f"Expected JSON object: {path}")
    return value


def _provider_errors(summary: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        dict(row["error"])
        for row in summary.get("provider_requests") or []
        if isinstance(row, dict) and isinstance(row.get("error"), dict)
    ]


def rc4_global_stop_faults(summary: dict[str, Any]) -> list[str]:
    """Return only shared/integrity faults; scientific and route failures stay local."""

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
    if (summary.get("trajectory_replay") or {}).get("status") == "failed":
        faults.append("persistence_or_replay_failure")
    if (summary.get("grader_assessment") or {}).get("status") == "failed":
        faults.append("verifier_contradiction_or_failure")
    if summary.get("classification") == "grader_failure":
        faults.append("shared_grader_or_harness_failure")
    if summary.get("failure_subtype") in {
        "pre_client_configuration_failure",
        "pre_first_request_failure",
    }:
        faults.append("shared_pre_inference_configuration_failure")
    if any(error.get("http_status") == 401 for error in _provider_errors(summary)):
        faults.append("authentication_failure")
    return list(dict.fromkeys(faults))


def isolated_provider_cell(summary: dict[str, Any]) -> bool:
    return summary.get("classification") in {
        "provider_adapter_failure",
        "provider_identity_failure",
        "provider_policy_refusal",
    } or bool(
        _provider_errors(summary)
        and summary.get("classification") == "infrastructure_failure"
        and summary.get("failure_subtype")
        not in {"pre_client_configuration_failure", "pre_first_request_failure"}
    )


def initialize_science_state(project_root: Path, *, key: str) -> dict[str, Any]:
    root = project_root.resolve()
    release = read_rc4_freeze(root)
    scientific = read_rc1_freeze(root)
    if (root / STATE_PATH).exists():
        raise ConfigurationError("RC4 science state already exists")
    snapshot = funding_snapshot(key)
    required = float(release["budgets_usd"]["scientific_hard_cap"])
    requirement = funding_requirement(snapshot, required)
    state = {
        "schema_version": "uc-bench-case1-pilot-v1-rc4-state-1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "ready_for_gpt5" if requirement["covered"] else "funding_blocked",
        "scientific_base_release_id": scientific["release_id"],
        "scientific_base_digest": scientific["closure"]["aggregate_digest"],
        "execution_release_id": release["release_id"],
        "execution_release_digest": release["closure"]["aggregate_digest"],
        "execution_order": release["execution_order"],
        "stage_b_randomization": release["stage_b_randomization"],
        "compatible_models": list(release["execution_order"]),
        "scientific_hard_cap_usd": required,
        "funding_before_science": snapshot,
        "funding_requirement": requirement,
        "baseline_key_usage_usd": snapshot["key_usage_usd"],
        "scientific_spend_usd": 0.0,
        "completed_models": [],
        "excluded_models": [],
        "summary_paths": [],
        "global_stop_faults": [],
        "gpt5_manual_review": None,
        "case2_requests": 0,
        "other_case_requests": 0,
        "sol_requests": 0,
        "astra_requests": 0,
    }
    _write_json(root / STATE_PATH, state, secret=key)
    return state


def _remaining(state: dict[str, Any], snapshot: dict[str, float]) -> float:
    observed = max(0.0, snapshot["key_usage_usd"] - state["baseline_key_usage_usd"])
    return min(
        float(state["scientific_hard_cap_usd"]) - observed,
        snapshot["effective_remaining_usd"],
    )


def _run_cell(
    root: Path,
    *,
    key: str,
    state: dict[str, Any],
    model_id: str,
    order_index: int,
) -> dict[str, Any]:
    release_before = read_rc4_freeze(root)
    row = model_config(root, model_id)
    remaining = _remaining(state, funding_snapshot(key))
    if remaining <= 0:
        raise ConfigurationError("RC4 cumulative cap has no remaining allowance")
    run_id = f"case1-rc4-{order_index:02d}-{model_id.replace('/', '-')}-attempt-0"
    result = run_case1_pilot_rc4_episode(
        root,
        Case1PilotRunConfig(run_id=run_id, model_id=model_id),
        adapter=load_case1_pilot_adapters(root)[model_id],
        openrouter_key=key,
        authorization_digest=release_before["closure"]["aggregate_digest"],
        remaining_cost_cap_usd=remaining,
        output_root=root / RUNS_ROOT,
        attempt_seed=int(row["attempt_seed"]),
        provider_seed=row.get("provider_seed"),
    )
    if read_rc4_freeze(root)["closure"]["aggregate_digest"] != release_before["closure"][
        "aggregate_digest"
    ]:
        raise ConfigurationError("RC4 freeze mutated during a cell")
    relative = result.summary_path.relative_to(root).as_posix()
    state["summary_paths"].append(relative)
    state["completed_models"].append(model_id)
    state["last_completed_model"] = model_id
    state["last_completed_at"] = datetime.now(UTC).isoformat()
    after = funding_snapshot(key)
    state["scientific_spend_usd"] = round(
        max(0.0, after["key_usage_usd"] - state["baseline_key_usage_usd"]), 8
    )
    faults = rc4_global_stop_faults(result.summary)
    if state["scientific_spend_usd"] > state["scientific_hard_cap_usd"] + 1e-9:
        faults.append("scientific_budget_breach")
    state["global_stop_faults"] = list(
        dict.fromkeys([*state["global_stop_faults"], *faults])
    )
    if isolated_provider_cell(result.summary) and not faults:
        state["excluded_models"].append(
            {
                "model_id": model_id,
                "classification": result.summary.get("classification"),
                "reason": "isolated provider or adapter failure after internal safe retry",
            }
        )
    if credential_locations(result.run_root, key):
        state["global_stop_faults"].append("credential_exposure")
    _write_json(root / STATE_PATH, state, secret=key)
    return result.summary


def run_gpt5_sentinel(project_root: Path, *, key: str) -> dict[str, Any]:
    root = project_root.resolve()
    state = _read(root / STATE_PATH)
    if state.get("status") != "ready_for_gpt5":
        raise ConfigurationError("RC4 is not ready for GPT-5")
    _run_cell(root, key=key, state=state, model_id=GPT5, order_index=0)
    state["status"] = "global_stop" if state["global_stop_faults"] else "gpt5_review_required"
    _write_json(root / STATE_PATH, state, secret=key)
    return state


def approve_gpt5_review(
    project_root: Path, *, key: str, manual_review: dict[str, Any]
) -> dict[str, Any]:
    root = project_root.resolve()
    state = _read(root / STATE_PATH)
    if state.get("status") != "gpt5_review_required" or state["global_stop_faults"]:
        raise ConfigurationError("GPT-5 cannot be approved after a global stop")
    required = {
        "raw_data_and_artifacts_inspected",
        "every_failed_property_manually_adjudicated",
        "evidence_chain_reconstructed",
        "replay_exact",
        "grader_deterministic",
        "no_contract_or_hidden_literal_failure",
        "construct_valid",
    }
    if not required <= set(manual_review) or not all(manual_review[key] for key in required):
        raise ConfigurationError("GPT-5 manual review is incomplete or failed")
    if manual_review.get("reviewed_summary_path") != state["summary_paths"][-1]:
        raise ConfigurationError("GPT-5 manual review does not cite the executed summary")
    summary = _read(root / state["summary_paths"][-1])
    grade = summary.get("diagnostic_grade") or {}
    failed = {
        str(row["requirement_id"])
        for row in grade.get("requirements") or []
        if row.get("passed") is False
    }
    adjudications = manual_review.get("failed_property_adjudications")
    if not isinstance(adjudications, list):
        raise ConfigurationError("GPT-5 review lacks property-level adjudications")
    adjudicated = {
        str(row.get("requirement_id"))
        for row in adjudications
        if isinstance(row, dict)
        and row.get("classification")
        and isinstance(row.get("evidence_refs"), list)
        and row["evidence_refs"]
    }
    if adjudicated != failed:
        raise ConfigurationError("GPT-5 failed-property adjudications are incomplete")
    state["gpt5_manual_review"] = {
        **manual_review,
        "reviewed_at": datetime.now(UTC).isoformat(),
    }
    state["status"] = "ready_for_stage_b"
    _write_json(root / STATE_PATH, state, secret=key)
    return state


def run_stage_b(project_root: Path, *, key: str) -> dict[str, Any]:
    root = project_root.resolve()
    state = _read(root / STATE_PATH)
    if state.get("status") != "ready_for_stage_b":
        raise ConfigurationError("GPT-5 review has not authorized Stage B")
    for index, model_id in enumerate(state["stage_b_randomization"]["order"], start=1):
        _run_cell(
            root, key=key, state=state, model_id=model_id, order_index=index
        )
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
    "approve_gpt5_review",
    "initialize_science_state",
    "isolated_provider_cell",
    "rc4_global_stop_faults",
    "run_gpt5_sentinel",
    "run_stage_b",
]

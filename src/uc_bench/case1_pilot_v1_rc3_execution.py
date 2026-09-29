"""Funding, cell containment, and staged execution for frozen RC3."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.case1_pilot_v1_execution import (
    funding_requirement,
    funding_snapshot,
    isolated_transient_provider_failure,
)
from uc_bench.case1_pilot_v1_provider import load_case1_pilot_adapters, model_config
from uc_bench.case1_pilot_v1_rc2_identity import adjudicate_exact_identity
from uc_bench.case1_pilot_v1_rc2_release import read_rc2_freeze
from uc_bench.case1_pilot_v1_rc3_compatibility import OFFLINE_REPLAY_PATH
from uc_bench.case1_pilot_v1_rc3_release import read_rc3_freeze
from uc_bench.case1_pilot_v1_rc3_runner import run_case1_pilot_rc3_episode
from uc_bench.case1_pilot_v1_release import read_release_freeze as read_rc1_freeze
from uc_bench.case1_pilot_v1_runner import Case1PilotRunConfig
from uc_bench.errors import ConfigurationError
from uc_bench.model_runner import _write_json
from uc_bench.v071_auth import credential_locations

EXECUTION_ROOT = Path("artifacts/uc_bench_case1_pilot_v1_rc3/science")
STATE_PATH = EXECUTION_ROOT / "pilot_state.json"
RUNS_ROOT = EXECUTION_ROOT / "runs"


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


def rc3_global_stop_faults(summary: dict[str, Any]) -> list[str]:
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
    provider_errors = _provider_errors(summary)
    if summary.get("classification") == "unknown_harness_failure" and not provider_errors:
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
    """Identify a route-scoped provider failure after its allowed retry."""

    errors = _provider_errors(summary)
    return bool(
        errors
        and summary.get("raw_response_persisted_count", 0) == 0
        and summary.get("classification")
        in {
            "infrastructure_failure",
            "provider_adapter_failure",
            "provider_policy_refusal",
            "unknown_harness_failure",
        }
    )


def _raw_responses(latest: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        dict(row["raw_response"])
        for row in latest.get("provider_exchanges") or []
        if isinstance(row, dict) and isinstance(row.get("raw_response"), dict)
    ]


def attest_identity(project_root: Path, model_id: str, run_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    adapter = load_case1_pilot_adapters(root)[model_id]
    ledger = _read(run_root / "request_ledger.json")
    latest_path = run_root / "host_trajectory/latest.json"
    latest = _read(latest_path) if latest_path.is_file() else {}
    records = [dict(row) for row in ledger.get("requests") or [] if isinstance(row, dict)]
    identity = adjudicate_exact_identity(
        requested_model=model_id,
        canonical_alias=adapter.expected_canonical_slug,
        pinned_provider=adapter.provider_order[0],
        fallback_disabled=not adapter.allow_fallbacks,
        request_records=records,
        raw_responses=_raw_responses(latest),
    )
    return {
        "schema_version": "uc-bench-case1-pilot-v1-rc3-identity-attestation-1",
        "created_at": datetime.now(UTC).isoformat(),
        "identity": identity,
        "ledger_sha256": hashlib.sha256(
            (run_root / "request_ledger.json").read_bytes()
        ).hexdigest(),
        "trajectory_sha256": (
            hashlib.sha256(latest_path.read_bytes()).hexdigest() if latest_path.is_file() else None
        ),
    }


def initialize_science_state(project_root: Path, *, key: str) -> dict[str, Any]:
    root = project_root.resolve()
    rc3 = read_rc3_freeze(root)
    rc2 = read_rc2_freeze(root)
    rc1 = read_rc1_freeze(root)
    replay = _read(root / OFFLINE_REPLAY_PATH)
    compatible = [
        str(row["model_id"])
        for row in replay.get("results") or []
        if row.get("rc3_classification") == "technically_compatible"
    ]
    if replay.get("status") != "passed" or set(compatible) != set(rc3["execution_order"]):
        raise ConfigurationError("All five routes must inherit technical compatibility")
    if (root / STATE_PATH).exists():
        raise ConfigurationError("RC3 science state already exists")
    snapshot = funding_snapshot(key)
    required = float(rc3["budgets_usd"]["scientific_hard_cap"])
    requirement = funding_requirement(snapshot, required)
    state = {
        "schema_version": "uc-bench-case1-pilot-v1-rc3-state-1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "ready_for_gemini" if requirement["covered"] else "funding_blocked",
        "scientific_base_release_id": rc1["release_id"],
        "scientific_base_digest": rc1["closure"]["aggregate_digest"],
        "source_rc2_execution_release_id": rc2["release_id"],
        "source_rc2_execution_digest": rc2["closure"]["aggregate_digest"],
        "execution_release_id": rc3["release_id"],
        "execution_release_digest": rc3["closure"]["aggregate_digest"],
        "execution_order": rc3["execution_order"],
        "remaining_four_randomization": {
            "source": "unchanged_frozen_rc1_randomization",
            "seed": 2026091001,
            "order": rc3["execution_order"][1:],
        },
        "compatible_models": compatible,
        "scientific_hard_cap_usd": required,
        "funding_before_science": snapshot,
        "funding_requirement": requirement,
        "baseline_key_usage_usd": snapshot["key_usage_usd"],
        "scientific_spend_usd": 0.0,
        "completed_models": [],
        "excluded_models": [],
        "cell_attempts": {},
        "summary_paths": [],
        "attestation_paths": [],
        "global_stop_faults": [],
        "gemini_manual_review": None,
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
    adapters = load_case1_pilot_adapters(root)
    row = model_config(root, model_id)
    attempts: list[Any] = []
    attestations: list[dict[str, Any]] = []
    for attempt_index in range(2):
        rc3_before = read_rc3_freeze(root)
        read_rc2_freeze(root)
        read_rc1_freeze(root)
        remaining = _remaining(state, funding_snapshot(key))
        if remaining <= 0:
            raise ConfigurationError("RC3 cumulative cap has no remaining allowance")
        run_id = (
            f"case1-rc3-{order_index:02d}-{model_id.replace('/', '-')}-"
            f"attempt-{attempt_index}"
        )
        result = run_case1_pilot_rc3_episode(
            root,
            Case1PilotRunConfig(run_id=run_id, model_id=model_id),
            adapter=adapters[model_id],
            openrouter_key=key,
            authorization_digest=rc3_before["closure"]["aggregate_digest"],
            remaining_cost_cap_usd=remaining,
            output_root=root / RUNS_ROOT,
            attempt_seed=int(row["attempt_seed"]),
            provider_seed=row.get("provider_seed"),
        )
        attempts.append(result)
        if result.summary.get("raw_response_persisted_count"):
            attestation = attest_identity(root, model_id, result.run_root)
        else:
            attestation = {
                "schema_version": "uc-bench-case1-pilot-v1-rc3-identity-attestation-1",
                "identity": {
                    "compatible": False,
                    "faults": ["no_response_identity_evidence"],
                    "missing_or_conflicting_identity_fails_closed": True,
                },
            }
        path = result.run_root / "rc3_identity_attestation.json"
        _write_json(path, attestation, secret=key)
        attestations.append(attestation)
        after_digest = read_rc3_freeze(root)["closure"]["aggregate_digest"]
        if after_digest != rc3_before["closure"]["aggregate_digest"]:
            raise ConfigurationError("RC3 freeze mutated during a cell")
        if not (attempt_index == 0 and isolated_transient_provider_failure(result.summary)):
            break

    selected = attempts[-1]
    identity = attestations[-1]["identity"]
    summary_paths = [item.summary_path.relative_to(root).as_posix() for item in attempts]
    state["cell_attempts"][model_id] = summary_paths
    state["summary_paths"].append(summary_paths[-1])
    state["attestation_paths"].append(
        (selected.run_root / "rc3_identity_attestation.json").relative_to(root).as_posix()
    )
    state["completed_models"].append(model_id)
    state["last_completed_model"] = model_id
    state["last_completed_at"] = datetime.now(UTC).isoformat()
    after = funding_snapshot(key)
    state["scientific_spend_usd"] = round(
        max(0.0, after["key_usage_usd"] - state["baseline_key_usage_usd"]), 8
    )
    faults = rc3_global_stop_faults(selected.summary)
    if state["scientific_spend_usd"] > state["scientific_hard_cap_usd"] + 1e-9:
        faults.append("scientific_budget_breach")
    state["global_stop_faults"] = list(dict.fromkeys([*state["global_stop_faults"], *faults]))
    if selected.summary.get("raw_response_persisted_count") and not identity["compatible"]:
        state["excluded_models"].append(
            {
                "model_id": model_id,
                "classification": "provider_identity_failure",
                "faults": identity["faults"],
                "attempt_count": len(attempts),
            }
        )
    elif isolated_provider_cell(selected.summary) and not faults:
        state["excluded_models"].append(
            {
                "model_id": model_id,
                "classification": selected.summary.get("classification"),
                "reason": "isolated provider failure",
                "attempt_count": len(attempts),
            }
        )
    if credential_locations(selected.run_root, key):
        state["global_stop_faults"].append("credential_exposure")
    _write_json(root / STATE_PATH, state, secret=key)
    return selected.summary


def run_gemini_sentinel(project_root: Path, *, key: str) -> dict[str, Any]:
    root = project_root.resolve()
    state = _read(root / STATE_PATH)
    if state.get("status") != "ready_for_gemini":
        raise ConfigurationError("RC3 is not ready for Gemini")
    _run_cell(
        root,
        key=key,
        state=state,
        model_id="google/gemini-3.1-pro-preview",
        order_index=0,
    )
    state["status"] = "global_stop" if state["global_stop_faults"] else "gemini_review_required"
    _write_json(root / STATE_PATH, state, secret=key)
    return state


def approve_gemini_review(
    project_root: Path, *, key: str, manual_review: dict[str, Any]
) -> dict[str, Any]:
    root = project_root.resolve()
    state = _read(root / STATE_PATH)
    if state.get("status") != "gemini_review_required" or state["global_stop_faults"]:
        raise ConfigurationError("Gemini cannot be approved after a global stop")
    required = {
        "raw_artifacts_inspected",
        "evidence_chain_reconstructed",
        "replay_exact",
        "grader_deterministic",
        "lifecycle_uncontaminated",
        "manual_construct_validity_adjudicated",
    }
    if not required <= set(manual_review) or not all(manual_review[field] for field in required):
        raise ConfigurationError("Gemini manual review is incomplete")
    state["gemini_manual_review"] = {
        **manual_review,
        "reviewed_at": datetime.now(UTC).isoformat(),
    }
    state["status"] = "ready_for_remaining_four"
    _write_json(root / STATE_PATH, state, secret=key)
    return state


def run_remaining_four(project_root: Path, *, key: str) -> dict[str, Any]:
    root = project_root.resolve()
    state = _read(root / STATE_PATH)
    if state.get("status") != "ready_for_remaining_four":
        raise ConfigurationError("Gemini manual review has not authorized continuation")
    for index, model_id in enumerate(state["remaining_four_randomization"]["order"], start=1):
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
    "RUNS_ROOT",
    "STATE_PATH",
    "approve_gemini_review",
    "attest_identity",
    "initialize_science_state",
    "isolated_provider_cell",
    "rc3_global_stop_faults",
    "run_gemini_sentinel",
    "run_remaining_four",
]

"""Frozen RC2 orchestration over the byte-identical RC1 scientific runner."""

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
    shared_stop_faults,
)
from uc_bench.case1_pilot_v1_provider import load_case1_pilot_adapters, model_config
from uc_bench.case1_pilot_v1_rc2_compatibility import OFFLINE_REPLAY_PATH
from uc_bench.case1_pilot_v1_rc2_identity import adjudicate_exact_identity
from uc_bench.case1_pilot_v1_rc2_release import read_rc2_freeze
from uc_bench.case1_pilot_v1_release import read_release_freeze as read_rc1_freeze
from uc_bench.case1_pilot_v1_runner import Case1PilotRunConfig, run_case1_pilot_episode
from uc_bench.errors import ConfigurationError
from uc_bench.model_runner import _write_json
from uc_bench.v071_auth import credential_locations

EXECUTION_ROOT = Path("artifacts/uc_bench_case1_pilot_v1_rc2/science")
STATE_PATH = EXECUTION_ROOT / "pilot_state.json"
RUNS_ROOT = EXECUTION_ROOT / "runs"


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError(f"Expected a JSON object: {path}")
    return value


def _raw_responses(latest: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        dict(row["raw_response"])
        for row in latest.get("provider_exchanges") or []
        if isinstance(row, dict) and isinstance(row.get("raw_response"), dict)
    ]


def attest_run_identity(
    project_root: Path, *, model_id: str, run_root: Path
) -> dict[str, Any]:
    root = project_root.resolve()
    adapter = load_case1_pilot_adapters(root)[model_id]
    ledger = _read(run_root / "request_ledger.json")
    latest = _read(run_root / "host_trajectory/latest.json")
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
        "schema_version": "uc-bench-case1-pilot-v1-rc2-run-attestation-1",
        "created_at": datetime.now(UTC).isoformat(),
        "identity": identity,
        "ledger_sha256": hashlib.sha256(
            (run_root / "request_ledger.json").read_bytes()
        ).hexdigest(),
        "trajectory_sha256": hashlib.sha256(
            (run_root / "host_trajectory/latest.json").read_bytes()
        ).hexdigest(),
        "identity_adjudication_is_only_rc2_behavioral_change": True,
    }


def initialize_science_state(project_root: Path, *, key: str) -> dict[str, Any]:
    root = project_root.resolve()
    release = read_rc2_freeze(root)
    rc1 = read_rc1_freeze(root)
    replay = _read(root / OFFLINE_REPLAY_PATH)
    compatible = [
        str(row["model_id"])
        for row in replay.get("results") or []
        if row.get("corrected_rc2_classification") == "technically_compatible"
    ]
    if replay.get("status") != "passed" or set(compatible) != set(release["execution_order"]):
        raise ConfigurationError("All five preserved routes must pass the RC2 offline replay")
    if (root / STATE_PATH).exists():
        raise ConfigurationError("RC2 science state already exists")
    snapshot = funding_snapshot(key)
    required = float(release["budgets_usd"]["scientific_hard_cap"])
    requirement = funding_requirement(snapshot, required)
    order = list(release["execution_order"])
    state = {
        "schema_version": "uc-bench-case1-pilot-v1-rc2-state-1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "ready_for_gemini" if requirement["covered"] else "funding_blocked",
        "rc2_release_digest": release["closure"]["aggregate_digest"],
        "rc1_scientific_release_digest": rc1["closure"]["aggregate_digest"],
        "offline_compatibility_replay_sha256": hashlib.sha256(
            (root / OFFLINE_REPLAY_PATH).read_bytes()
        ).hexdigest(),
        "execution_order": order,
        "gemini_first": order[0],
        "remaining_four_randomization": {
            "source": "byte_identical_rc1_predeclared_randomization",
            "seed": 2026091001,
            "order": order[1:],
            "preserved_before_scientific_exposure": True,
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


def _remaining_cap(state: dict[str, Any], snapshot: dict[str, float]) -> float:
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
        rc2_before = read_rc2_freeze(root)
        rc1 = read_rc1_freeze(root)
        remaining = _remaining_cap(state, funding_snapshot(key))
        if remaining <= 0:
            raise ConfigurationError("RC2 cumulative scientific cap has no allowance")
        run_id = (
            f"case1-rc2-{order_index:02d}-{model_id.replace('/', '-')}-"
            f"attempt-{attempt_index}"
        )
        result = run_case1_pilot_episode(
            root,
            Case1PilotRunConfig(run_id=run_id, model_id=model_id),
            adapter=adapters[model_id],
            openrouter_key=key,
            authorization_digest=rc1["closure"]["aggregate_digest"],
            remaining_cost_cap_usd=remaining,
            output_root=root / RUNS_ROOT,
            attempt_seed=int(row["attempt_seed"]),
            provider_seed=row.get("provider_seed"),
        )
        attempts.append(result)
        usable = int(result.summary.get("usable_provider_response_count") or 0)
        if usable:
            attestation = attest_run_identity(root, model_id=model_id, run_root=result.run_root)
        else:
            attestation = {
                "schema_version": "uc-bench-case1-pilot-v1-rc2-run-attestation-1",
                "created_at": datetime.now(UTC).isoformat(),
                "identity": {
                    "compatible": False,
                    "faults": ["no_usable_response_identity_evidence"],
                    "missing_or_conflicting_identity_fails_closed": True,
                },
                "identity_adjudication_is_only_rc2_behavioral_change": True,
            }
        attestation_path = result.run_root / "rc2_identity_attestation.json"
        _write_json(attestation_path, attestation, secret=key)
        attestations.append(attestation)
        after_digest = read_rc2_freeze(root)["closure"]["aggregate_digest"]
        if after_digest != rc2_before["closure"]["aggregate_digest"]:
            raise ConfigurationError("RC2 frozen files mutated during a model cell")
        if not (attempt_index == 0 and isolated_transient_provider_failure(result.summary)):
            break

    selected = attempts[-1]
    selected_attestation = attestations[-1]
    paths = [item.summary_path.relative_to(root).as_posix() for item in attempts]
    state["cell_attempts"][model_id] = paths
    state["summary_paths"].append(paths[-1])
    state["attestation_paths"].append(
        (selected.run_root / "rc2_identity_attestation.json").relative_to(root).as_posix()
    )
    state["completed_models"].append(model_id)
    state["last_completed_model"] = model_id
    state["last_completed_at"] = datetime.now(UTC).isoformat()
    after = funding_snapshot(key)
    state["scientific_spend_usd"] = round(
        max(0.0, after["key_usage_usd"] - state["baseline_key_usage_usd"]), 8
    )
    faults = shared_stop_faults(selected.summary)
    if state["scientific_spend_usd"] > state["scientific_hard_cap_usd"] + 1e-9:
        faults.append("scientific_budget_breach")
    state["global_stop_faults"] = list(dict.fromkeys([*state["global_stop_faults"], *faults]))

    usable = int(selected.summary.get("usable_provider_response_count") or 0)
    identity_ok = bool((selected_attestation.get("identity") or {}).get("compatible"))
    classification = str(selected.summary.get("classification"))
    if usable and not identity_ok:
        state["excluded_models"].append(
            {
                "model_id": model_id,
                "classification": "provider_identity_failure",
                "reason": "exact identity adjudication failed closed",
                "faults": (selected_attestation.get("identity") or {}).get("faults") or [],
                "attempt_count": len(attempts),
            }
        )
    elif classification in {
        "provider_adapter_failure",
        "provider_policy_refusal",
        "infrastructure_failure",
    } and not faults:
        state["excluded_models"].append(
            {
                "model_id": model_id,
                "classification": classification,
                "reason": "isolated provider or route failure",
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
        raise ConfigurationError("RC2 is not ready for Gemini")
    model_id = "google/gemini-3.1-pro-preview"
    _run_cell(root, key=key, state=state, model_id=model_id, order_index=0)
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
        "manual_scientific_adjudication_recorded",
    }
    if not required <= set(manual_review) or not all(
        bool(manual_review[field]) for field in required
    ):
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
    "EXECUTION_ROOT",
    "RUNS_ROOT",
    "STATE_PATH",
    "approve_gemini_review",
    "attest_run_identity",
    "initialize_science_state",
    "run_gemini_sentinel",
    "run_remaining_four",
]

"""Funding, forensic gate and five-cell Case-1 RC5 execution."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.case1_pilot_v1_execution import funding_requirement, funding_snapshot
from uc_bench.case1_pilot_v1_provider import load_case1_pilot_adapters, model_config
from uc_bench.case1_pilot_v1_rc5_release import read_rc5_freeze
from uc_bench.case1_pilot_v1_rc5_reporting import CorruptTrajectoryError
from uc_bench.case1_pilot_v1_rc5_runner import (
    finalize_rc5_run_summary,
    run_case1_pilot_rc5_episode,
)
from uc_bench.case1_pilot_v1_rc5_verifier import WEIGHTS, verify_case1_rc5_submission
from uc_bench.case1_pilot_v1_runner import Case1PilotRunConfig
from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256
from uc_bench.model_runner import _write_json
from uc_bench.v071_auth import credential_locations

EXECUTION_ROOT = Path("artifacts/uc_bench_case1_pilot_v1_rc5/science")
STATE_PATH = EXECUTION_ROOT / "pilot_state.json"
RUNS_ROOT = EXECUTION_ROOT / "runs"
GPT5 = "openai/gpt-5"
_KNOWN_EXECUTION_CLASSIFICATIONS = frozenset(
    {
        "valid_episode",
        "agent_task_failure",
        "agent_refusal",
        "context_budget_exhaustion",
        "cost_cap_reached",
        "provider_adapter_failure",
        "provider_identity_failure",
        "provider_policy_refusal",
        "infrastructure_failure",
        "grader_failure",
        "protected_evidence_tampering",
        "unknown_harness_failure",
        "shared_harness_failure",
    }
)


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError(f"JSON object required: {path}")
    return value


def _provider_errors(summary: dict[str, Any]) -> list[dict[str, Any]]:
    requests = summary.get("provider_requests")
    if not isinstance(requests, list):
        return []
    return [
        dict(row["error"])
        for row in requests
        if isinstance(row, dict) and isinstance(row.get("error"), dict)
    ]


def rc5_global_stop_faults(summary: dict[str, Any]) -> list[str]:
    faults: list[str] = []
    raw_classification = summary.get("classification")
    classification = raw_classification if isinstance(raw_classification, str) else ""
    if not classification:
        faults.append("malformed_run_summary:classification")
    elif classification not in _KNOWN_EXECUTION_CLASSIFICATIONS:
        faults.append("malformed_run_summary:unknown_classification")
    raw_subtype = summary.get("failure_subtype")
    failure_subtype = raw_subtype if isinstance(raw_subtype, str) else ""
    if raw_subtype is not None and not isinstance(raw_subtype, str):
        faults.append("malformed_run_summary:failure_subtype")
    for field in ("model_id", "run_id"):
        if not isinstance(summary.get(field), str) or not summary.get(field):
            faults.append(f"malformed_run_summary:{field}")
    credentials_exposed = summary.get("agent_received_provider_credentials")
    if not isinstance(credentials_exposed, bool):
        faults.append("malformed_run_summary:agent_received_provider_credentials")
    nested: dict[str, dict[str, Any]] = {}
    for field in (
        "integrity",
        "trajectory_replay",
        "grader_assessment",
        "authoritative_lifecycle",
        "submission",
    ):
        value = summary.get(field)
        if value is None:
            nested[field] = {}
            if field in {"authoritative_lifecycle", "submission"}:
                faults.append(f"malformed_run_summary:{field}")
        elif isinstance(value, dict):
            nested[field] = value
        else:
            nested[field] = {}
            faults.append(f"malformed_run_summary:{field}")
    integrity = nested["integrity"]
    if integrity.get("start_state_untampered") is not True:
        faults.append("frozen_start_state_corruption")
    if integrity.get("protected_evidence_untampered") is not True:
        faults.append("protected_evidence_mutation")
    if integrity.get("protected_evidence_mutation_attempted") is not False:
        faults.append("protected_evidence_mutation_attempt")
    if integrity.get("workspace_boundary_enforced") is not True:
        faults.append("workspace_boundary_failure")
    if credentials_exposed is True:
        faults.append("credential_exposure")
    replay_status = nested["trajectory_replay"].get("status")
    if not isinstance(replay_status, str) or replay_status not in {
        "passed",
        "failed",
        "not_applicable",
    }:
        faults.append("malformed_run_summary:trajectory_replay.status")
    elif replay_status == "failed":
        faults.append("persistence_or_replay_failure")
    grader_status = nested["grader_assessment"].get("status")
    if not isinstance(grader_status, str) or grader_status not in {
        "passed",
        "failed",
        "not_applicable",
    }:
        faults.append("malformed_run_summary:grader_assessment.status")
    elif grader_status == "failed":
        faults.append("verifier_contradiction_or_failure")
    if classification == "grader_failure":
        faults.append("shared_grader_or_harness_failure")
    if classification == "shared_harness_failure":
        faults.append("shared_grader_or_harness_failure")
    if classification == "unknown_harness_failure":
        faults.append("shared_unknown_harness_failure")
    if classification == "protected_evidence_tampering":
        faults.append("protected_evidence_mutation")
    if (
        nested["authoritative_lifecycle"].get("status") == "corrupt"
        or failure_subtype == "durable_trajectory_corruption"
    ):
        faults.append("durable_trajectory_corruption")
    if classification == "provider_identity_failure":
        faults.append("provider_identity_or_fallback_violation")
    if failure_subtype in {
        "pre_client_configuration_failure",
        "pre_first_request_failure",
    }:
        faults.append("shared_pre_inference_configuration_failure")
    if any(error.get("http_status") == 401 for error in _provider_errors(summary)):
        faults.append("authentication_failure")
    provider_requests = summary.get("provider_requests")
    if provider_requests is not None and (
        not isinstance(provider_requests, list)
        or not all(isinstance(row, dict) for row in provider_requests)
    ):
        faults.append("malformed_run_summary:provider_requests")
    lifecycle = nested["authoritative_lifecycle"]
    submission = nested["submission"]
    raw_state = submission.get("state")
    if raw_state is None:
        submission_state: dict[str, Any] = {}
    elif isinstance(raw_state, dict):
        submission_state = raw_state
    else:
        submission_state = {}
        faults.append("malformed_run_summary:submission.state")
    valid_episode_inconsistent = classification == "valid_episode" and (
        lifecycle.get("submission_accepted") is not True
        or submission_state.get("completion_accepted") is not True
    )
    other_lifecycle_inconsistent = classification != "valid_episode" and bool(lifecycle) and (
        not isinstance(lifecycle.get("submission_accepted"), bool)
        or not isinstance(submission_state.get("completion_accepted"), bool)
        or lifecycle.get("submission_accepted") != submission_state.get("completion_accepted")
    )
    if valid_episode_inconsistent or other_lifecycle_inconsistent:
        faults.append("authoritative_lifecycle_inconsistency")
    return list(dict.fromkeys(faults))


def isolated_provider_cell(summary: dict[str, Any]) -> bool:
    classification = summary.get("classification")
    if not isinstance(classification, str):
        return False
    failure_subtype = summary.get("failure_subtype")
    if failure_subtype is not None and not isinstance(failure_subtype, str):
        return False
    return classification in {
        "provider_adapter_failure",
        "provider_policy_refusal",
    } or bool(
        _provider_errors(summary)
        and classification == "infrastructure_failure"
        and failure_subtype
        not in {"pre_client_configuration_failure", "pre_first_request_failure"}
    )


def initialize_science_state(project_root: Path, *, key: str) -> dict[str, Any]:
    root = project_root.resolve()
    release = read_rc5_freeze(root)
    path = root / STATE_PATH
    if path.exists():
        raise ConfigurationError("RC5 science state already exists")
    snapshot = funding_snapshot(key)
    required = float(release["budgets_usd"]["scientific_hard_cap"])
    requirement = funding_requirement(snapshot, required)
    state = {
        "schema_version": "uc-bench-case1-pilot-v1-rc5-state-1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "ready_for_stage_a" if requirement["covered"] else "funding_blocked",
        "execution_release_id": release["release_id"],
        "execution_release_digest": release["closure"]["aggregate_digest"],
        "execution_order": release["execution_order"],
        "stage_a_cap_usd": float(release["budgets_usd"]["stage_a_cap"]),
        "scientific_hard_cap_usd": required,
        "funding_before_science": snapshot,
        "funding_requirement": requirement,
        "baseline_key_usage_usd": snapshot["key_usage_usd"],
        "scientific_spend_usd": 0.0,
        "completed_models": [],
        "excluded_models": [],
        "summary_paths": [],
        "global_stop_faults": [],
        "stage_a_forensic_review": None,
        "active_cell": None,
        "case2_requests": 0,
        "other_case_requests": 0,
        "sol_requests": 0,
        "astra_requests": 0,
    }
    _write_json(path, state, secret=key)
    return state


def _observed_spend(state: dict[str, Any], snapshot: dict[str, float]) -> float:
    return max(0.0, snapshot["key_usage_usd"] - state["baseline_key_usage_usd"])


def _remaining(state: dict[str, Any], snapshot: dict[str, float]) -> float:
    observed = _observed_spend(state, snapshot)
    return min(
        float(state["scientific_hard_cap_usd"]) - observed,
        snapshot["effective_remaining_usd"],
    )


def _cell_run_id(model_id: str, order_index: int) -> str:
    return f"case1-rc5-{order_index:02d}-{model_id.replace('/', '-')}-attempt-0"


def _cell_result_identity_faults(
    root: Path,
    *,
    result: Any,
    model_id: str,
    run_id: str,
) -> list[str]:
    """Fail closed before a returned runner result can be adopted into panel state."""

    expected_root = (root / RUNS_ROOT / run_id).resolve()
    expected_paths = {
        "run_root": expected_root,
        "workspace_root": expected_root / "workspace",
        "summary_path": expected_root / "run_summary.json",
        "request_ledger_path": expected_root / "request_ledger.json",
    }
    faults = [
        f"completed_cell_{field}_mismatch"
        for field, expected in expected_paths.items()
        if not isinstance(getattr(result, field, None), Path)
        or getattr(result, field).resolve() != expected
    ]
    summary = getattr(result, "summary", None)
    if not isinstance(summary, dict):
        faults.append("completed_cell_summary_malformed")
        return faults
    if summary.get("model_id") != model_id or summary.get("run_id") != run_id:
        faults.append("completed_cell_identity_mismatch")
    expected_summary = expected_paths["summary_path"]
    try:
        persisted = _read(expected_summary)
    except (ConfigurationError, OSError, UnicodeError, json.JSONDecodeError):
        faults.append("completed_cell_summary_missing_or_malformed")
    else:
        if persisted.get("model_id") != model_id or persisted.get("run_id") != run_id:
            faults.append("completed_cell_persisted_identity_mismatch")
        if canonical_sha256(persisted) != canonical_sha256(summary):
            faults.append("completed_cell_result_differs_from_persisted_summary")
    return list(dict.fromkeys(faults))


def _finalize_durable_cell(
    root: Path,
    *,
    key: str,
    state: dict[str, Any],
    model_id: str,
    run_id: str,
    summary: dict[str, Any],
) -> None:
    summary_path = root / RUNS_ROOT / run_id / "run_summary.json"
    relative = summary_path.relative_to(root).as_posix()
    if relative not in state["summary_paths"]:
        state["summary_paths"].append(relative)
    if model_id not in state["completed_models"]:
        state["completed_models"].append(model_id)
    state["last_completed_model"] = model_id
    state["last_completed_at"] = datetime.now(UTC).isoformat()
    live_after = funding_snapshot(key)
    state["scientific_spend_usd"] = round(_observed_spend(state, live_after), 8)
    faults = rc5_global_stop_faults(summary)
    if state["scientific_spend_usd"] > state["scientific_hard_cap_usd"] + 1e-9:
        faults.append("scientific_budget_breach")
    state["global_stop_faults"] = list(dict.fromkeys([*state["global_stop_faults"], *faults]))
    if (
        isolated_provider_cell(summary)
        and not faults
        and not any(row.get("model_id") == model_id for row in state["excluded_models"])
    ):
        state["excluded_models"].append(
            {
                "model_id": model_id,
                "classification": summary.get("classification"),
                "reason": "isolated route failure after the runner's one safe retry",
            }
        )
    run_root = summary_path.parent
    if credential_locations(run_root, key):
        state["global_stop_faults"].append("credential_exposure")
    state["global_stop_faults"] = list(dict.fromkeys(state["global_stop_faults"]))
    if state["global_stop_faults"]:
        state["status"] = "global_stop"
    state["active_cell"] = None
    _write_json(root / STATE_PATH, state, secret=key)


def _reconcile_active_cell(root: Path, *, key: str, state: dict[str, Any]) -> bool:
    """Adopt a durable completed run after a host crash without spending twice."""

    active = state.get("active_cell")
    if not isinstance(active, dict):
        return False
    model_id = str(active.get("model_id") or "")
    run_id = str(active.get("run_id") or "")
    try:
        release = read_rc5_freeze(root)
    except ConfigurationError:
        state["global_stop_faults"].append("release_integrity_failure_during_recovery")
        state["status"] = "global_stop"
        _write_json(root / STATE_PATH, state, secret=key)
        return False
    release_digest = release["closure"]["aggregate_digest"]
    if (
        not isinstance(active.get("release_digest"), str)
        or active.get("release_digest") != release_digest
        or state.get("execution_release_digest") != release_digest
    ):
        state["global_stop_faults"].append("recovery_release_digest_mismatch")
        state["status"] = "global_stop"
        _write_json(root / STATE_PATH, state, secret=key)
        return False
    summary_path = root / RUNS_ROOT / run_id / "run_summary.json"
    if summary_path.is_file():
        try:
            summary = finalize_rc5_run_summary(summary_path.parent, key=key)
        except CorruptTrajectoryError:
            state["global_stop_faults"].append("completed_cell_trajectory_corruption")
            state["status"] = "global_stop"
            _write_json(root / STATE_PATH, state, secret=key)
            return False
        if summary.get("model_id") != model_id or summary.get("run_id") != run_id:
            state["global_stop_faults"].append("completed_cell_identity_mismatch")
            state["status"] = "global_stop"
            _write_json(root / STATE_PATH, state, secret=key)
            return False
        _finalize_durable_cell(
            root,
            key=key,
            state=state,
            model_id=model_id,
            run_id=run_id,
            summary=summary,
        )
        return True
    run_root = root / RUNS_ROOT / run_id
    if run_root.exists():
        state["global_stop_faults"].append("incomplete_durable_cell_requires_forensic_review")
        state["status"] = "global_stop"
        _write_json(root / STATE_PATH, state, secret=key)
        return False
    state["global_stop_faults"].append("active_cell_record_without_run_directory")
    state["status"] = "global_stop"
    _write_json(root / STATE_PATH, state, secret=key)
    return False


def _run_cell(
    root: Path,
    *,
    key: str,
    state: dict[str, Any],
    model_id: str,
    order_index: int,
    cell_cap_usd: float | None = None,
) -> dict[str, Any]:
    release_before = read_rc5_freeze(root)
    live_before = funding_snapshot(key)
    remaining = _remaining(state, live_before)
    if cell_cap_usd is not None:
        remaining = min(remaining, cell_cap_usd)
    if remaining <= 0:
        raise ConfigurationError("RC5 cumulative cap has no remaining allowance")
    row = model_config(root, model_id)
    run_id = _cell_run_id(model_id, order_index)
    state["active_cell"] = {
        "model_id": model_id,
        "order_index": order_index,
        "run_id": run_id,
        "status": "running",
        "started_at": datetime.now(UTC).isoformat(),
        "release_digest": release_before["closure"]["aggregate_digest"],
        "maximum_incremental_cost_usd": remaining,
    }
    _write_json(root / STATE_PATH, state, secret=key)
    result = run_case1_pilot_rc5_episode(
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
    if (
        read_rc5_freeze(root)["closure"]["aggregate_digest"]
        != release_before["closure"]["aggregate_digest"]
    ):
        raise ConfigurationError("RC5 freeze mutated during execution")
    identity_faults = _cell_result_identity_faults(
        root,
        result=result,
        model_id=model_id,
        run_id=run_id,
    )
    if identity_faults:
        state["global_stop_faults"] = list(
            dict.fromkeys([*state["global_stop_faults"], *identity_faults])
        )
        state["status"] = "global_stop"
        state["active_cell"] = None
        _write_json(root / STATE_PATH, state, secret=key)
        return result.summary
    _finalize_durable_cell(
        root,
        key=key,
        state=state,
        model_id=model_id,
        run_id=run_id,
        summary=result.summary,
    )
    return result.summary


def run_stage_a(project_root: Path, *, key: str) -> dict[str, Any]:
    root = project_root.resolve()
    state = _read(root / STATE_PATH)
    if state.get("status") != "ready_for_stage_a":
        raise ConfigurationError("RC5 is not ready for Stage A")
    _reconcile_active_cell(root, key=key, state=state)
    if state["global_stop_faults"]:
        return state
    if GPT5 in state["completed_models"]:
        state["status"] = "stage_a_review_required"
        _write_json(root / STATE_PATH, state, secret=key)
        return state
    _run_cell(
        root,
        key=key,
        state=state,
        model_id=GPT5,
        order_index=0,
        cell_cap_usd=float(state["stage_a_cap_usd"]),
    )
    state["status"] = "global_stop" if state["global_stop_faults"] else "stage_a_review_required"
    _write_json(root / STATE_PATH, state, secret=key)
    return state


def approve_stage_a_review(
    project_root: Path, *, key: str, forensic_review: dict[str, Any]
) -> dict[str, Any]:
    root = project_root.resolve()
    state = _read(root / STATE_PATH)
    if state.get("status") != "stage_a_review_required" or state["global_stop_faults"]:
        raise ConfigurationError("RC5 Stage A is not awaiting a clean forensic review")
    required = {
        "raw_data_and_artifacts_inspected",
        "all_ten_properties_adjudicated",
        "evidence_chain_reconstructed",
        "replay_exact",
        "grader_deterministic",
        "no_hidden_contract_or_representation_failure",
        "construct_valid",
    }
    if not required <= set(forensic_review) or not all(
        forensic_review[key] is True for key in required
    ):
        raise ConfigurationError("Stage A forensic review is incomplete or not construct-valid")
    if forensic_review.get("reviewed_summary_path") != state["summary_paths"][-1]:
        raise ConfigurationError("Stage A review does not cite the executed summary")
    summary_path = root / state["summary_paths"][-1]
    summary = finalize_rc5_run_summary(summary_path.parent, key=key)
    if (summary.get("grader_assessment") or {}).get("status") == "failed":
        raise ConfigurationError("Stage A grader assessment is not clean")
    lifecycle = summary.get("authoritative_lifecycle") or {}
    if lifecycle.get("status") == "corrupt":
        raise ConfigurationError("Stage A trajectory is corrupt")
    properties = forensic_review.get("property_adjudications")
    if not isinstance(properties, list) or len(properties) != 10:
        raise ConfigurationError("Stage A review must adjudicate all ten scientific properties")
    by_property = {row.get("requirement_id"): row for row in properties if isinstance(row, dict)}
    if set(by_property) != set(WEIGHTS) or len(by_property) != len(properties):
        raise ConfigurationError("Stage A review must name every unique scientific property")
    if any(
        not isinstance(row, dict)
        or not isinstance(row.get("evidence_refs"), list)
        or not row["evidence_refs"]
        or row.get("classification") not in {"pass", "scientific_failure", "not_evaluable"}
        for row in properties
    ):
        raise ConfigurationError("Stage A property adjudication evidence is incomplete")
    for row in properties:
        for relative in row["evidence_refs"]:
            if not isinstance(relative, str) or not relative:
                raise ConfigurationError("Stage A evidence reference is malformed")
            evidence = (summary_path.parent / relative).resolve()
            if summary_path.parent.resolve() not in evidence.parents or not evidence.is_file():
                raise ConfigurationError("Stage A evidence reference is missing or out of bounds")

    recorded_grade = summary.get("diagnostic_grade")
    if lifecycle.get("submission_accepted"):
        if not isinstance(recorded_grade, dict):
            raise ConfigurationError("Submitted Stage A run lacks a diagnostic grade")
        recomputed = verify_case1_rc5_submission(
            root, summary_path.parent / "workspace", summary.get("submission") or {}
        ).to_dict()
        if canonical_sha256(recomputed) != canonical_sha256(recorded_grade):
            raise ConfigurationError("Stage A grade does not reproduce from saved evidence")
        expected = {
            row["requirement_id"]: "pass" if row["passed"] else "scientific_failure"
            for row in recorded_grade.get("requirements") or []
            if isinstance(row, dict) and row.get("requirement_id") in WEIGHTS
        }
        if set(expected) != set(WEIGHTS) or any(
            by_property[identifier].get("classification") != classification
            for identifier, classification in expected.items()
        ):
            raise ConfigurationError("Stage A manual adjudication contradicts the saved grade")
    else:
        eligible = {
            "agent_task_failure",
            "agent_refusal",
            "context_budget_exhaustion",
            "provider_adapter_failure",
            "provider_policy_refusal",
        }
        if summary.get("classification") not in eligible or any(
            row.get("classification") != "not_evaluable" for row in properties
        ):
            raise ConfigurationError("Unsubmitted Stage A adjudication is not evidence-consistent")
    state["stage_a_forensic_review"] = {
        **forensic_review,
        "reviewed_at": datetime.now(UTC).isoformat(),
    }
    state["status"] = "ready_for_stage_b"
    _write_json(root / STATE_PATH, state, secret=key)
    return state


def run_stage_b(project_root: Path, *, key: str) -> dict[str, Any]:
    root = project_root.resolve()
    state = _read(root / STATE_PATH)
    if state.get("status") != "ready_for_stage_b":
        raise ConfigurationError("RC5 Stage A has not passed forensic adjudication")
    _reconcile_active_cell(root, key=key, state=state)
    if state["global_stop_faults"]:
        return state
    for index, model_id in enumerate(state["execution_order"][1:], start=1):
        if model_id in state["completed_models"]:
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
    "approve_stage_a_review",
    "initialize_science_state",
    "isolated_provider_cell",
    "rc5_global_stop_faults",
    "run_stage_a",
    "run_stage_b",
]

"""Funding gate and bounded two-cell Case-1 RC6 execution."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.case1_pilot_v1_execution import funding_requirement, funding_snapshot
from uc_bench.case1_pilot_v1_provider import load_case1_pilot_adapters, model_config
from uc_bench.case1_pilot_v1_rc6_lifecycle import matrix_stop_level
from uc_bench.case1_pilot_v1_rc6_release import FRESH_MODELS, read_rc6_freeze
from uc_bench.case1_pilot_v1_rc6_runner import (
    finalize_rc6_run_summary,
    run_case1_pilot_rc6_episode,
)
from uc_bench.case1_pilot_v1_runner import Case1PilotRunConfig
from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256
from uc_bench.model_runner import _write_json
from uc_bench.v071_auth import credential_locations

EXECUTION_ROOT = Path("artifacts/uc_bench_case1_pilot_v1_rc6/science")
STATE_PATH = EXECUTION_ROOT / "pilot_state.json"
RUNS_ROOT = EXECUTION_ROOT / "runs"


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError(f"JSON object required: {path}")
    return value


def _observed_spend(state: dict[str, Any], snapshot: dict[str, float]) -> float:
    return max(0.0, snapshot["key_usage_usd"] - state["baseline_key_usage_usd"])


def _remaining(state: dict[str, Any], snapshot: dict[str, float]) -> float:
    return min(
        float(state["scientific_hard_cap_usd"]) - _observed_spend(state, snapshot),
        snapshot["effective_remaining_usd"],
    )


def initialize_science_state(project_root: Path, *, key: str) -> dict[str, Any]:
    root = project_root.resolve()
    release = read_rc6_freeze(root)
    path = root / STATE_PATH
    if path.exists():
        raise ConfigurationError("RC6 science state already exists")
    snapshot = funding_snapshot(key)
    required = float(release["budgets_usd"]["scientific_hard_cap"])
    requirement = funding_requirement(snapshot, required)
    state = {
        "schema_version": "uc-bench-case1-pilot-v1-rc6-state-1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "ready" if requirement["covered"] else "funding_blocked",
        "execution_release_id": release["release_id"],
        "execution_release_digest": release["closure"]["aggregate_digest"],
        "execution_order": list(FRESH_MODELS),
        "scientific_hard_cap_usd": required,
        "funding_immediately_before_science": snapshot,
        "funding_requirement": requirement,
        "baseline_key_usage_usd": snapshot["key_usage_usd"],
        "scientific_spend_usd": 0.0,
        "completed_models": [],
        "excluded_models": [],
        "summary_paths": [],
        "global_stop_faults": [],
        "active_cell": None,
        "case2_requests": 0,
        "other_case_requests": 0,
        "sol_requests": 0,
        "astra_requests": 0,
        "opus_requests": 0,
    }
    _write_json(path, state, secret=key)
    return state


def global_stop_faults(summary: dict[str, Any]) -> list[str]:
    faults: list[str] = []
    integrity = summary.get("integrity") or {}
    replay = summary.get("trajectory_replay") or {}
    grader = summary.get("grader_assessment") or {}
    lifecycle = summary.get("request_lifecycle") or {}
    if integrity.get("start_state_untampered") is not True:
        faults.append("shared_start_state_corruption")
    if integrity.get("protected_evidence_untampered") is not True:
        faults.append("protected_evidence_mutation")
    if integrity.get("protected_evidence_mutation_attempted") is not False:
        faults.append("protected_evidence_mutation_attempt")
    if integrity.get("workspace_boundary_enforced") is not True:
        faults.append("shared_workspace_boundary_failure")
    if summary.get("agent_received_provider_credentials") is not False:
        faults.append("credential_leakage")
    if lifecycle.get("passed") is not True:
        faults.append("shared_request_lifecycle_corruption")
    if replay.get("status") == "failed":
        faults.append("shared_replay_corruption")
    if grader.get("status") == "failed":
        faults.append("shared_grade_affecting_evaluator_defect")
    if summary.get("case_id") != "case_01":
        faults.append("evidence_exposure_outside_case1")
    return list(dict.fromkeys(faults))


def _classification_stop(summary: dict[str, Any]) -> str:
    return matrix_stop_level(str(summary.get("classification") or ""))


def _run_id(model_id: str, index: int) -> str:
    return f"case1-rc6-{index:02d}-{model_id.replace('/', '-')}-attempt-0"


def _adopt_cell(
    root: Path,
    *,
    key: str,
    state: dict[str, Any],
    model_id: str,
    run_id: str,
    summary: dict[str, Any],
) -> None:
    summary_path = root / RUNS_ROOT / run_id / "run_summary.json"
    persisted = _read(summary_path)
    if canonical_sha256(persisted) != canonical_sha256(summary):
        state["global_stop_faults"].append("returned_summary_differs_from_persisted")
    if persisted.get("model_id") != model_id or persisted.get("run_id") != run_id:
        state["global_stop_faults"].append("completed_cell_identity_mismatch")
    relative = summary_path.relative_to(root).as_posix()
    if relative not in state["summary_paths"]:
        state["summary_paths"].append(relative)
    if model_id not in state["completed_models"]:
        state["completed_models"].append(model_id)
    snapshot = funding_snapshot(key)
    state["scientific_spend_usd"] = round(_observed_spend(state, snapshot), 8)
    if state["scientific_spend_usd"] > state["scientific_hard_cap_usd"] + 1e-9:
        state["global_stop_faults"].append("cost_cap_breach")
    state["global_stop_faults"].extend(global_stop_faults(summary))
    stop_level = _classification_stop(summary)
    if stop_level == "global_stop":
        state["global_stop_faults"].append(
            f"global_classification:{summary.get('classification')}"
        )
    elif stop_level == "cell_exclusion_continue_panel":
        state["excluded_models"].append(
            {
                "model_id": model_id,
                "classification": summary.get("classification"),
                "scientific_score": None,
                "reliability": None,
            }
        )
    if credential_locations(summary_path.parent, key):
        state["global_stop_faults"].append("credential_leakage")
    state["global_stop_faults"] = list(dict.fromkeys(state["global_stop_faults"]))
    state["active_cell"] = None
    state["status"] = "global_stop" if state["global_stop_faults"] else "running"
    _write_json(root / STATE_PATH, state, secret=key)


def _reconcile_active(root: Path, *, key: str, state: dict[str, Any]) -> None:
    active = state.get("active_cell")
    if not isinstance(active, dict):
        return
    run_id = str(active.get("run_id") or "")
    model_id = str(active.get("model_id") or "")
    run_root = root / RUNS_ROOT / run_id
    summary_path = run_root / "run_summary.json"
    if summary_path.is_file():
        summary = finalize_rc6_run_summary(run_root, key=key)
        _adopt_cell(
            root,
            key=key,
            state=state,
            model_id=model_id,
            run_id=run_id,
            summary=summary,
        )
        return
    state["global_stop_faults"].append("interrupted_cell_requires_forensic_recovery")
    state["status"] = "global_stop"
    _write_json(root / STATE_PATH, state, secret=key)


def run_authorized_panel(project_root: Path, *, key: str) -> dict[str, Any]:
    root = project_root.resolve()
    state = (
        _read(root / STATE_PATH)
        if (root / STATE_PATH).is_file()
        else initialize_science_state(root, key=key)
    )
    if state.get("status") == "funding_blocked":
        return state
    if state.get("status") not in {"ready", "running"}:
        raise ConfigurationError(f"RC6 state is not executable: {state.get('status')}")
    _reconcile_active(root, key=key, state=state)
    if state["global_stop_faults"]:
        return state
    adapters = load_case1_pilot_adapters(root)
    for index, model_id in enumerate(FRESH_MODELS):
        if model_id in state["completed_models"]:
            continue
        release = read_rc6_freeze(root)
        snapshot = funding_snapshot(key)
        remaining = _remaining(state, snapshot)
        if remaining <= 0:
            state["status"] = "global_stop"
            state["global_stop_faults"].append("cost_cap_reached_before_request")
            _write_json(root / STATE_PATH, state, secret=key)
            return state
        row = model_config(root, model_id)
        run_id = _run_id(model_id, index)
        state["active_cell"] = {
            "model_id": model_id,
            "run_id": run_id,
            "order_index": index,
            "release_digest": release["closure"]["aggregate_digest"],
            "remaining_cost_cap_usd": remaining,
            "started_at": datetime.now(UTC).isoformat(),
        }
        state["status"] = "running"
        _write_json(root / STATE_PATH, state, secret=key)
        result = run_case1_pilot_rc6_episode(
            root,
            Case1PilotRunConfig(run_id=run_id, model_id=model_id),
            adapter=adapters[model_id],
            openrouter_key=key,
            authorization_digest=release["closure"]["aggregate_digest"],
            remaining_cost_cap_usd=remaining,
            output_root=root / RUNS_ROOT,
            attempt_seed=int(row["attempt_seed"]),
            provider_seed=row.get("provider_seed"),
        )
        current_digest = read_rc6_freeze(root)["closure"]["aggregate_digest"]
        if current_digest != release["closure"]["aggregate_digest"]:
            state["global_stop_faults"].append("release_mutation")
            state["status"] = "global_stop"
            _write_json(root / STATE_PATH, state, secret=key)
            return state
        _adopt_cell(
            root,
            key=key,
            state=state,
            model_id=model_id,
            run_id=run_id,
            summary=result.summary,
        )
        if state["global_stop_faults"]:
            return state
    state["status"] = "completed_mandatory_review"
    state["completed_at"] = datetime.now(UTC).isoformat()
    state["funding_after_science"] = funding_snapshot(key)
    state["scientific_spend_usd"] = round(
        _observed_spend(state, state["funding_after_science"]), 8
    )
    _write_json(root / STATE_PATH, state, secret=key)
    return state


__all__ = [
    "EXECUTION_ROOT",
    "RUNS_ROOT",
    "STATE_PATH",
    "global_stop_faults",
    "initialize_science_state",
    "run_authorized_panel",
]

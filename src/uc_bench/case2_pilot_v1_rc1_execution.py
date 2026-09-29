"""Funding, route preflight, containment, and bounded three-cell execution."""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from uc_bench.case1_pilot_v1_execution import funding_requirement, funding_snapshot
from uc_bench.case1_pilot_v1_rc6_lifecycle import (
    RequestLifecycleMachine,
    lifecycle_identity,
    matrix_stop_level,
)
from uc_bench.case2_pilot_v1_rc1_provider import (
    load_case2_adapters,
    model_config,
)
from uc_bench.case2_pilot_v1_rc1_release import read_freeze
from uc_bench.case2_pilot_v1_rc1_runner import (
    Case2RunArtifacts,
    Case2RunConfig,
    grader_assessment,
    run_case2_episode,
)
from uc_bench.case2_pilot_v1_rc1_runtime import Case2TrajectoryStore
from uc_bench.case2_pilot_v1_rc1_semantics import WEIGHTS
from uc_bench.case2_pilot_v1_rc1_trajectory import (
    case2_trajectory_replay_check,
    restore_case2_environment,
)
from uc_bench.case2_pilot_v1_rc1_verifier import verify_case2_rc1_submission
from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256
from uc_bench.mmmvp_open_rc12_trajectory import ACTIVE_TOOL_STATUS
from uc_bench.model_runner import _write_json
from uc_bench.openrouter_catalog import fetch_model_endpoints, fetch_user_catalog
from uc_bench.v071_auth import credential_locations

EXECUTION_ROOT = Path("artifacts/uc_bench_case2_pilot_v1_rc1/science")
STATE_PATH = EXECUTION_ROOT / "sentinel_state.json"
RUNS_ROOT = EXECUTION_ROOT / "runs"
RUN_SUMMARY_SCHEMA = "uc-bench-case2-pilot-v1-rc1-run-1"
ALLOWED_CLASSIFICATIONS = frozenset(
    {
        "cost_cap_reached",
        "grader_failure",
        "infrastructure_failure",
        "isolated_provider_failure",
        "isolated_provider_timeout",
        "model_completion_failure",
        "protected_evidence_tampering",
        "provider_adapter_failure",
        "provider_identity_failure",
        "provider_policy_refusal",
        "valid_episode",
    }
)


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError(f"JSON object required: {path}")
    return value


def _route_evidence(
    model_id: str,
    declared: dict[str, Any],
    visible: Any,
    endpoints: list[dict[str, Any]],
) -> dict[str, Any]:
    matching = [
        row
        for row in endpoints
        if row.get("provider_name") == declared["provider"]
        and row.get("model_name") in {model_id, declared["canonical_slug"]}
    ]
    canonical_pin_matches = bool(
        visible is not None and visible.canonical_slug == declared["canonical_slug"]
    )
    return {
        "model_id": model_id,
        "declared_provider": declared["provider"],
        "declared_canonical_slug": declared["canonical_slug"],
        "visible_to_key": visible is not None,
        "observed_canonical_slug": visible.canonical_slug if visible is not None else None,
        "canonical_pin_matches": canonical_pin_matches,
        "matching_pinned_endpoints": matching,
        "route_available": bool(canonical_pin_matches and matching),
    }


def route_snapshot(project_root: Path, *, key: str) -> dict[str, Any]:
    root = project_root.resolve()
    release = read_freeze(root)
    catalog = fetch_user_catalog(key)
    rows: list[dict[str, Any]] = []
    for model_id in release["execution_order"]:
        declared = model_config(root, model_id)
        endpoints = fetch_model_endpoints(key, model_id)
        visible = catalog.get(model_id)
        rows.append(_route_evidence(model_id, declared, visible, endpoints))
    return {
        "schema_version": "uc-bench-case2-pilot-v1-rc1-route-snapshot-1",
        "checked_at": datetime.now(UTC).isoformat(),
        "passed": all(row["route_available"] for row in rows),
        "routes": rows,
    }


def initialize_state(project_root: Path, *, key: str) -> dict[str, Any]:
    root = project_root.resolve()
    path = root / STATE_PATH
    if path.exists():
        raise ConfigurationError("Case 2 science state already exists")
    release = read_freeze(root)
    funding = funding_snapshot(key)
    required = float(release["budgets_usd"]["scientific_hard_cap"])
    requirement = funding_requirement(funding, required)
    routes = route_snapshot(root, key=key)
    state = {
        "schema_version": "uc-bench-case2-pilot-v1-rc1-state-1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": (
            "ready"
            if requirement["covered"] and routes["passed"]
            else "funding_blocked"
            if not requirement["covered"]
            else "route_blocked"
        ),
        "release_id": release["release_id"],
        "release_digest": release["closure"]["aggregate_digest"],
        "execution_order": list(release["execution_order"]),
        "scientific_hard_cap_usd": required,
        "funding_immediately_before_science": funding,
        "funding_requirement": requirement,
        "route_snapshot": routes,
        "baseline_key_usage_usd": funding["key_usage_usd"],
        "scientific_spend_usd": 0.0,
        "completed_models": [],
        "excluded_models": [],
        "summary_paths": [],
        "forensic_paths": [],
        "global_stop_faults": [],
        "active_cell": None,
        "other_case_requests": 0,
        "sol_requests": 0,
        "astra_requests": 0,
    }
    _write_json(path, state, secret=key)
    return state


def _observed_spend(state: dict[str, Any], snapshot: dict[str, float]) -> float:
    return max(0.0, snapshot["key_usage_usd"] - state["baseline_key_usage_usd"])


def _remaining(state: dict[str, Any], snapshot: dict[str, float]) -> float:
    return min(
        float(state["scientific_hard_cap_usd"]) - _observed_spend(state, snapshot),
        snapshot["effective_remaining_usd"],
    )


def forensic_adjudication(summary: dict[str, Any]) -> dict[str, Any]:
    raw_grade = summary.get("diagnostic_grade")
    grade = raw_grade if isinstance(raw_grade, dict) else None
    raw_requirements = (grade or {}).get("requirements") or []
    requirements = [row for row in raw_requirements if isinstance(row, dict)]
    first = (grade or {}).get("first_decision_critical_failure")
    raw_diagnostics = (grade or {}).get("diagnostics") or {}
    diagnostics = raw_diagnostics if isinstance(raw_diagnostics, dict) else {}
    raw_submission = summary.get("submission") or {}
    submission = raw_submission if isinstance(raw_submission, dict) else {}
    raw_final = submission.get("final_submission") or {}
    final = raw_final if isinstance(raw_final, dict) else {}
    failures = [row for row in requirements if not row.get("passed")]
    faults: list[str] = []
    if grade and grade.get("complete_mission_success") and first:
        faults.append("mission_success_coexists_with_critical_failure")
    if grade and grade.get("complete_mission_success") != (not failures):
        faults.append("mission_result_differs_from_property_conjunction")
    if diagnostics.get("prose_scored"):
        faults.append("undisclosed_prose_scoring")
    prospective = next(
        (
            row
            for row in requirements
            if row.get("requirement_id") == "prospective_design_and_integrity"
        ),
        {},
    )
    committed = ((prospective.get("observed") or {}).get("committed_cohort") or {})
    calculations = diagnostics.get("criteria") or {}
    return {
        "schema_version": "uc-bench-case2-pilot-v1-rc1-forensic-1",
        "model_id": summary.get("model_id"),
        "official_score_unchanged": True,
        "verifier_used_committed_cohort": bool(
            committed.get("hashes_match")
            and committed.get("observed_sha256")
            and committed.get("committed_sha256")
        ),
        "saved_artifact_recomputation": {
            "criteria_seen": sorted(calculations),
            "all_calculations_valid": bool(calculations)
            and all(row.get("calculation_valid") for row in calculations.values()),
        },
        "no_undisclosed_wording_rule": diagnostics.get("prose_scored") is not True,
        "optional_analysis_invalidated_primary": False,
        "first_failure": first,
        "downstream_consequences": (
            first.get("downstream_dependencies") if isinstance(first, dict) else []
        ),
        "identity_strategy": (
            (submission.get("validation_plan") or {}).get("prospective_specification") or {}
        ).get("identity_basis"),
        "selected_resource": (submission.get("followup_plan") or {}).get("chosen_resource"),
        "belief_updates": final.get("belief_updates"),
        "final_decision": final.get("decision"),
        "faults": faults,
        "passed": not faults,
    }


def global_stop_faults(summary: dict[str, Any], forensic: dict[str, Any]) -> list[str]:
    faults: list[str] = []
    integrity = summary.get("integrity") or {}
    replay = summary.get("trajectory_replay") or {}
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
    raw_assessment = summary.get("grader_assessment")
    assessment = raw_assessment if isinstance(raw_assessment, dict) else {}
    if assessment.get("status") == "failed":
        faults.append("shared_grade_affecting_evaluator_defect")
    if not forensic["passed"]:
        faults.append("post_run_forensic_contradiction")
    if summary.get("case_id") != "case_02":
        faults.append("cross_case_evidence_exposure")
    classification = str(summary.get("classification") or "")
    if classification in {"grader_failure", "infrastructure_failure"}:
        faults.append(f"shared_{classification}")
    if classification == "cost_cap_reached":
        faults.append("cost_cap_reached")
    if matrix_stop_level(classification) == "global_stop":
        faults.append(f"global_classification:{classification}")
    return list(dict.fromkeys(faults))


def summary_integrity_faults(
    summary: dict[str, Any],
    *,
    expected_model_id: str,
    expected_run_id: str,
    expected_release_id: str,
    expected_release_digest: str,
    expected_adapter: dict[str, Any],
    expected_run_config: dict[str, Any] | None = None,
) -> list[str]:
    """Validate the trusted host summary shape before any semantic adjudication."""

    faults: list[str] = []
    expected = {
        "schema_version": RUN_SUMMARY_SCHEMA,
        "model_id": expected_model_id,
        "run_id": expected_run_id,
        "case_id": "case_02",
        "release_id": expected_release_id,
        "release_digest": expected_release_digest,
    }
    for field, value in expected.items():
        if summary.get(field) != value:
            faults.append(f"summary_{field}_mismatch")
    if summary.get("classification") not in ALLOWED_CLASSIFICATIONS:
        faults.append("summary_classification_unknown")
    for field in ("integrity", "request_lifecycle", "trajectory_replay"):
        if not isinstance(summary.get(field), dict):
            faults.append(f"summary_{field}_malformed")
    for field in ("grader_assessment", "provider_identity"):
        if not isinstance(summary.get(field), dict):
            faults.append(f"summary_{field}_malformed")
    grade = summary.get("diagnostic_grade")
    if grade is not None and not isinstance(grade, dict):
        faults.append("summary_diagnostic_grade_malformed")
    if summary.get("provider_adapter") != expected_adapter:
        faults.append("summary_provider_adapter_mismatch")
    authoritative_run_config = expected_run_config or asdict(
        Case2RunConfig(expected_run_id, expected_model_id)
    )
    if summary.get("run_config") != authoritative_run_config:
        faults.append("summary_run_config_mismatch")
    if summary.get("provider_fallbacks_allowed") is not False:
        faults.append("summary_provider_fallback_policy_mismatch")
    if summary.get("agent_received_provider_credentials") is not False:
        faults.append("summary_credential_boundary_mismatch")
    if summary.get("agent_network_enabled") is not False:
        faults.append("summary_agent_network_boundary_mismatch")
    for field in ("other_case_requests", "sol_requests", "astra_requests"):
        if summary.get(field) != 0:
            faults.append(f"summary_{field}_nonzero")

    classification = summary.get("classification")
    lifecycle = summary.get("request_lifecycle")
    replay = summary.get("trajectory_replay")
    integrity = summary.get("integrity")
    if classification in {"valid_episode", "model_completion_failure"}:
        if not isinstance(lifecycle, dict) or lifecycle.get("passed") is not True:
            faults.append("summary_completed_cell_lifecycle_invalid")
        if not isinstance(integrity, dict) or any(
            (
                integrity.get("start_state_untampered") is not True,
                integrity.get("protected_evidence_untampered") is not True,
                integrity.get("protected_evidence_mutation_attempted") is not False,
                integrity.get("workspace_boundary_enforced") is not True,
            )
        ):
            faults.append("summary_completed_cell_integrity_invalid")
        records = summary.get("provider_requests")
        if not isinstance(records, list):
            faults.append("summary_provider_requests_malformed")
        else:
            if summary.get("provider_request_count") != len(records):
                faults.append("summary_provider_request_count_mismatch")
            if isinstance(lifecycle, dict):
                if lifecycle.get("attempt_count") != len(records):
                    faults.append("summary_request_lifecycle_count_mismatch")
                states = lifecycle.get("states")
                if not isinstance(states, list) or len(states) != len(records):
                    faults.append("summary_request_lifecycle_states_mismatch")
    if classification == "valid_episode":
        submission = summary.get("submission")
        final = submission.get("final_submission") if isinstance(submission, dict) else None
        assessment = summary.get("grader_assessment")
        identity = summary.get("provider_identity")
        if not isinstance(grade, dict):
            faults.append("summary_valid_episode_missing_grade")
        state = submission.get("state") if isinstance(submission, dict) else None
        if (
            not isinstance(final, dict)
            or not final
            or not isinstance(state, dict)
            or state.get("completion_accepted") is not True
            or not isinstance(submission.get("validation_plan"), dict)
            or not isinstance(submission.get("followup_plan"), dict)
        ):
            faults.append("summary_valid_episode_missing_submission")
        if (
            not isinstance(assessment, dict)
            or assessment.get("status") != "passed"
            or assessment.get("passed") is not True
            or assessment.get("faults") != []
        ):
            faults.append("summary_valid_episode_grader_assessment_invalid")
        if not isinstance(replay, dict) or replay.get("passed") is not True:
            faults.append("summary_valid_episode_replay_invalid")
        if (
            not isinstance(identity, dict)
            or identity.get("compatible") is not True
            or identity.get("requested_model") != expected_model_id
            or identity.get("pinned_provider") != expected_adapter["provider_order"][0]
            or identity.get("fallback_disabled") is not True
            or not isinstance(identity.get("completed_response_count"), int)
            or identity.get("completed_response_count", 0) < 1
            or identity.get("faults") != []
        ):
            faults.append("summary_valid_episode_identity_invalid")
        if isinstance(grade, dict):
            raw_requirements = grade.get("requirements")
            requirements = (
                raw_requirements
                if isinstance(raw_requirements, list)
                and all(isinstance(row, dict) for row in raw_requirements)
                else []
            )
            by_id = {row.get("requirement_id"): row for row in requirements}
            diagnostics = grade.get("diagnostics")
            points = diagnostics.get("property_points") if isinstance(diagnostics, dict) else None
            if len(requirements) != len(WEIGHTS) or set(by_id) != set(WEIGHTS) or any(
                not isinstance(row.get("passed"), bool) for row in requirements
            ):
                faults.append("summary_scientific_requirements_malformed")
            if not isinstance(points, dict) or set(points) != set(WEIGHTS) or any(
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(float(value))
                for value in (points or {}).values()
            ):
                faults.append("summary_property_points_malformed")
            grade_partial = grade.get("partial_scientific_quality")
            grade_reliability = grade.get("reliability_score")
            if (
                not isinstance(grade_partial, (int, float))
                or isinstance(grade_partial, bool)
                or not math.isfinite(float(grade_partial))
                or not isinstance(grade_reliability, (int, float))
                or isinstance(grade_reliability, bool)
                or not math.isfinite(float(grade_reliability))
            ):
                faults.append("summary_scientific_scores_non_numeric")
            elif (
                isinstance(points, dict)
                and set(points) == set(WEIGHTS)
                and abs(
                    float(grade_partial)
                    - sum(float(value) for value in points.values())
                )
                > 1e-9
            ):
                faults.append("summary_partial_not_recomputed_from_properties")
            if set(by_id) == set(WEIGHTS) and grade.get("complete_mission_success") != all(
                row["passed"] for row in by_id.values()
            ):
                faults.append("summary_mission_not_property_conjunction")
            try:
                independently_assessed = grader_assessment(grade, None)
            except (AttributeError, KeyError, TypeError, ValueError):
                faults.append("summary_grader_assessment_not_total")
            else:
                if independently_assessed != assessment:
                    faults.append("summary_grader_assessment_not_reproducible")
            for summary_field, grade_field in (
                ("complete_mission_success", "complete_mission_success"),
                ("partial_scientific_quality", "partial_scientific_quality"),
                ("reliability_score", "reliability_score"),
            ):
                if summary.get(summary_field) != grade.get(grade_field):
                    faults.append(f"summary_{summary_field}_differs_from_grade")
        for field in (
            "provider_request_count",
            "raw_response_persisted_count",
            "parsed_provider_exchange_count",
            "usable_provider_response_count",
        ):
            if not isinstance(summary.get(field), int) or summary.get(field, 0) < 1:
                faults.append(f"summary_valid_episode_{field}_invalid")
    elif classification == "model_completion_failure":
        if grade is not None:
            faults.append("summary_completion_failure_has_grade")
        if summary.get("complete_mission_success") is not None:
            faults.append("summary_completion_failure_has_mission_result")
        if summary.get("reliability_score") != 0.0:
            faults.append("summary_completion_failure_reliability_not_zero")
    elif classification in {
        "isolated_provider_failure",
        "isolated_provider_timeout",
        "provider_adapter_failure",
        "provider_identity_failure",
        "provider_policy_refusal",
    }:
        if summary.get("partial_scientific_quality") is not None or summary.get(
            "reliability_score"
        ) is not None:
            faults.append("summary_provider_exclusion_has_scientific_score")
    return faults


def _run_id(model_id: str, index: int) -> str:
    return f"case2-rc1-{index:02d}-{model_id.replace('/', '-')}-attempt-0"


def _completed_request_evidence_faults(
    attempts: Any,
    records: Any,
    exchanges: Any,
) -> list[str]:
    """Bind every terminal attempt across lifecycle, ledger, and trajectory."""

    if not all(isinstance(rows, list) for rows in (attempts, records, exchanges)):
        return ["request_evidence_collections_malformed"]
    if len(attempts) != len(records) or len(exchanges) != len(attempts):
        return ["request_evidence_count_mismatch"]
    faults: list[str] = []
    response_states = frozenset({"completed_response", "provider_response_parse_failure"})
    no_response_states = frozenset(
        {"transient_transport_failure", "terminal_provider_failure"}
    )
    allowed_states = response_states | no_response_states
    for index, (attempt, record, exchange) in enumerate(
        zip(attempts, records, exchanges, strict=True)
    ):
        if not all(isinstance(row, dict) for row in (attempt, record, exchange)):
            faults.append(f"request_{index}:record_malformed")
            continue
        state = attempt.get("state")
        if state not in allowed_states:
            faults.append(f"request_{index}:attempt_state_not_adoptable")
        if attempt.get("attempt_id") != index:
            faults.append(f"request_{index}:attempt_id_mismatch")
        if attempt.get("ledger_request_index") != index:
            faults.append(f"request_{index}:ledger_index_mismatch")
        if record.get("request_index") != index:
            faults.append(f"request_{index}:ledger_sequence_mismatch")
        if exchange.get("request_index") != index:
            faults.append(f"request_{index}:exchange_sequence_mismatch")
        normalization = record.get("runner_normalization")
        ledger_request_digest = (
            normalization.get("pending_request_body_sha256")
            if isinstance(normalization, dict)
            else None
        )
        request_digest = attempt.get("request_body_sha256")
        if (
            not isinstance(request_digest, str)
            or ledger_request_digest != request_digest
            or exchange.get("request_body_sha256") != request_digest
        ):
            faults.append(f"request_{index}:request_digest_mismatch")
        if state in response_states:
            if attempt.get("response_received") is not True:
                faults.append(f"request_{index}:response_receipt_missing")
            raw_digest = attempt.get("raw_body_sha256")
            if (
                not isinstance(raw_digest, str)
                or exchange.get("raw_body_sha256") != raw_digest
            ):
                faults.append(f"request_{index}:raw_body_digest_mismatch")
            raw_response = exchange.get("raw_response")
            if not isinstance(raw_response, dict) or exchange.get(
                "raw_response_sha256"
            ) != canonical_sha256(raw_response):
                faults.append(f"request_{index}:raw_response_digest_mismatch")
            if state == "completed_response":
                if isinstance(record.get("error"), dict):
                    faults.append(f"request_{index}:completed_record_has_error")
                if exchange.get("attempt_state") is not None:
                    faults.append(f"request_{index}:completed_exchange_marked_failed")
                if isinstance(raw_response, dict):
                    if record.get("returned_model") != raw_response.get("model"):
                        faults.append(f"request_{index}:returned_model_mismatch")
                    if record.get("actual_provider") != raw_response.get("provider"):
                        faults.append(f"request_{index}:returned_provider_mismatch")
            else:
                error = record.get("error")
                if not isinstance(error, dict):
                    faults.append(f"request_{index}:failed_record_error_missing")
                elif exchange.get("error_record_sha256") != canonical_sha256(error):
                    faults.append(f"request_{index}:error_record_digest_mismatch")
                if exchange.get("attempt_state") != state:
                    faults.append(f"request_{index}:failed_exchange_state_mismatch")
        elif state in no_response_states:
            if attempt.get("response_received") is not False:
                faults.append(f"request_{index}:unexpected_response_receipt")
            if attempt.get("raw_body_sha256") is not None:
                faults.append(f"request_{index}:unexpected_raw_body_digest")
            if exchange.get("raw_response") is not None:
                faults.append(f"request_{index}:unexpected_raw_response")
            error = record.get("error")
            if not isinstance(error, dict):
                faults.append(f"request_{index}:failed_record_error_missing")
            elif exchange.get("error_record_sha256") != canonical_sha256(error):
                faults.append(f"request_{index}:error_record_digest_mismatch")
            if exchange.get("attempt_state") != state:
                faults.append(f"request_{index}:failed_exchange_state_mismatch")
    return faults


def _durable_trajectory_faults(
    project_root: Path,
    run_root: Path,
    *,
    expected_model_id: str,
    expected_run_id: str,
    expected_release_id: str,
    expected_release_digest: str,
    require_no_pending_tools: bool,
) -> tuple[list[str], Case2TrajectoryStore | None]:
    """Reconstruct and verify the complete journal before resume or adoption."""

    faults: list[str] = []
    host_root = run_root / "host_trajectory"
    workspace = run_root / "workspace"
    try:
        latest = _read(host_root / "latest.json")
        metadata = _read(host_root / "metadata.json")
    except (ConfigurationError, OSError, json.JSONDecodeError):
        return ["durable_trajectory_metadata_missing_or_malformed"], None
    run_metadata = metadata.get("run_metadata")
    latest_metadata = latest.get("run_metadata")
    if not isinstance(run_metadata, dict) or latest_metadata != run_metadata:
        faults.append("durable_run_metadata_mismatch")
        run_metadata = run_metadata if isinstance(run_metadata, dict) else {}
    run_config = run_metadata.get("run_config")
    if not isinstance(run_config, dict):
        faults.append("durable_run_config_malformed")
        run_config = {}
    expected = {
        "run_id": expected_run_id,
        "model_id": expected_model_id,
        "case_id": "case_02",
    }
    for field, value in expected.items():
        observed = (
            run_config.get(field)
            if field in {"run_id", "model_id"}
            else run_metadata.get(field)
        )
        if observed != value:
            faults.append(f"durable_{field}_mismatch")
    if run_metadata.get("release_id") != expected_release_id:
        faults.append("durable_release_id_mismatch")
    if run_metadata.get("release_digest") != expected_release_digest:
        faults.append("durable_release_digest_mismatch")
    if run_metadata.get("agent_visible") is not False:
        faults.append("durable_host_boundary_mismatch")
    pending_calls = latest.get("pending_tool_calls")
    if not isinstance(pending_calls, list) or not all(
        isinstance(call, dict) for call in pending_calls
    ):
        faults.append("durable_pending_tool_collection_malformed")
    elif require_no_pending_tools and any(
        call.get("status") == ACTIVE_TOOL_STATUS for call in pending_calls
    ):
        faults.append("durable_active_tool_call")
    store: Case2TrajectoryStore | None = None
    try:
        core = restore_case2_environment(project_root, workspace, latest)
        store = Case2TrajectoryStore.reopen(
            host_root,
            workspace=workspace,
            core=core,
            secret="",
        )
        verification = store.verify(require_no_pending_tools=require_no_pending_tools)
    except Exception as exc:
        faults.append(f"durable_reconstruction_exception:{type(exc).__name__}")
    else:
        if verification.get("passed") is not True:
            faults.extend(
                f"durable_trajectory:{fault}" for fault in verification.get("faults") or []
            )
    return list(dict.fromkeys(faults)), store


def active_cell_recovery_mode(
    project_root: Path,
    state: dict[str, Any],
    *,
    output_root: Path | None = None,
) -> str:
    """Return the only safe action for an outer-runner checkpoint."""

    active = state.get("active_cell")
    if not isinstance(active, dict):
        return "none"
    model_id = str(active.get("model_id") or "")
    run_id = str(active.get("run_id") or "")
    order = list(state.get("execution_order") or [])
    if model_id not in order or run_id != _run_id(model_id, order.index(model_id)):
        return "blocked_active_identity"
    if active.get("release_digest") != state.get("release_digest"):
        return "blocked_active_release_mismatch"
    base = output_root.resolve() if output_root is not None else project_root.resolve() / RUNS_ROOT
    run_root = base / run_id
    release_id = str(state.get("release_id") or "uc-bench-case2-pilot-v1-rc1")
    release_digest = str(state.get("release_digest") or "")
    if (run_root / "run_summary.json").is_file():
        trajectory_faults, _ = _durable_trajectory_faults(
            project_root.resolve(),
            run_root,
            expected_model_id=model_id,
            expected_run_id=run_id,
            expected_release_id=release_id,
            expected_release_digest=release_digest,
            require_no_pending_tools=False,
        )
        if trajectory_faults:
            return "blocked_corrupt_durable_trajectory"
        return "adopt_completed"
    if not run_root.exists():
        return "start_unissued"
    latest = run_root / "host_trajectory/latest.json"
    lifecycle = run_root / "request_lifecycle.json"
    if latest.is_file():
        ledger_path = run_root / "request_ledger.json"
        if not lifecycle.is_file() or not ledger_path.is_file():
            return "blocked_missing_request_evidence"
        try:
            lifecycle_machine = RequestLifecycleMachine.load(lifecycle, secret="")
            lifecycle_value = _read(lifecycle)
            ledger_value = _read(ledger_path)
            latest_value = _read(latest)
        except (ConfigurationError, OSError, json.JSONDecodeError):
            return "blocked_malformed_lifecycle"
        attempts = lifecycle_value.get("attempts")
        records = ledger_value.get("requests")
        exchanges = latest_value.get("provider_exchanges")
        if not all(
            isinstance(rows, list) and all(isinstance(row, dict) for row in rows)
            for rows in (attempts, records, exchanges)
        ):
            return "blocked_malformed_request_evidence"
        if lifecycle_machine.active() is not None:
            return "blocked_ambiguous_inflight_request"
        if latest_value.get("provider_requests") != records or _completed_request_evidence_faults(
            attempts, records, exchanges
        ):
            return "blocked_inconsistent_request_evidence"
        trajectory_faults, _ = _durable_trajectory_faults(
            project_root.resolve(),
            run_root,
            expected_model_id=model_id,
            expected_run_id=run_id,
            expected_release_id=release_id,
            expected_release_digest=release_digest,
            require_no_pending_tools=True,
        )
        if trajectory_faults:
            return "blocked_corrupt_durable_trajectory"
        return "resume_durable_boundary"
    return "blocked_missing_durable_boundary"


def _adopt_cell(
    root: Path,
    *,
    key: str,
    state: dict[str, Any],
    summary_path: Path,
    adapter: Any,
    returned_summary: dict[str, Any] | None = None,
    funding_snapshot_fn: Callable[[str], dict[str, float]] = funding_snapshot,
    state_path: Path | None = None,
    expected_run_config: dict[str, Any] | None = None,
) -> None:
    target_state_path = state_path or root / STATE_PATH
    active = state.get("active_cell") or {}
    model_id = str(active.get("model_id") or "")
    run_id = str(active.get("run_id") or "")
    try:
        persisted = _read(summary_path)
    except (ConfigurationError, OSError, json.JSONDecodeError):
        state["global_stop_faults"].append("malformed_or_missing_persisted_summary")
        state["status"] = "global_stop"
        _write_json(target_state_path, state, secret=key)
        return
    faults = summary_integrity_faults(
        persisted,
        expected_model_id=model_id,
        expected_run_id=run_id,
        expected_release_id=str(state.get("release_id") or ""),
        expected_release_digest=str(state.get("release_digest") or ""),
        expected_adapter=adapter.to_dict(),
        expected_run_config=expected_run_config,
    )
    trajectory_faults, store = _durable_trajectory_faults(
        root,
        summary_path.parent,
        expected_model_id=model_id,
        expected_run_id=run_id,
        expected_release_id=str(state.get("release_id") or ""),
        expected_release_digest=str(state.get("release_digest") or ""),
        require_no_pending_tools=False,
    )
    faults.extend(trajectory_faults)
    try:
        disk_submission = _read(summary_path.parent / "submission.json")
        disk_ledger = _read(summary_path.parent / "request_ledger.json")
        disk_lifecycle = _read(summary_path.parent / "request_lifecycle.json")
    except (ConfigurationError, OSError, json.JSONDecodeError):
        faults.append("cell_evidence_file_missing_or_malformed")
    else:
        if disk_submission != persisted.get("submission"):
            faults.append("summary_submission_differs_from_disk")
        disk_records = disk_ledger.get("requests")
        records_valid = isinstance(disk_records, list) and all(
            isinstance(row, dict) for row in disk_records
        )
        if not records_valid:
            faults.append("disk_request_ledger_malformed")
        elif disk_records != persisted.get("provider_requests"):
            faults.append("summary_requests_differ_from_ledger")
        lifecycle = persisted.get("request_lifecycle")
        disk_attempts = disk_lifecycle.get("attempts")
        attempts_valid = isinstance(disk_attempts, list) and all(
            isinstance(row, dict) for row in disk_attempts
        )
        if not isinstance(lifecycle, dict) or not attempts_valid:
            faults.append("disk_lifecycle_malformed")
        elif disk_lifecycle.get("attempt_count") != lifecycle.get("attempt_count") or [
            row.get("state") for row in disk_attempts
        ] != lifecycle.get("states"):
            faults.append("summary_lifecycle_differs_from_disk")
        else:
            try:
                lifecycle_machine = RequestLifecycleMachine.load(
                    summary_path.parent / "request_lifecycle.json", secret=""
                )
            except Exception as exc:
                faults.append(f"adoption_lifecycle_exception:{type(exc).__name__}")
            else:
                reproduced_lifecycle = {
                    **lifecycle_machine.verify(),
                    "path": "request_lifecycle.json",
                    "states": [row["state"] for row in lifecycle_machine.attempts],
                }
                if reproduced_lifecycle != lifecycle:
                    faults.append("summary_lifecycle_not_reproducible")
                if records_valid:
                    identity = lifecycle_identity(
                        requested_model=model_id,
                        canonical_alias=adapter.expected_canonical_slug,
                        pinned_provider=adapter.provider_order[0],
                        fallback_disabled=True,
                        ledger=SimpleNamespace(records=disk_records),
                        lifecycle=lifecycle_machine,
                    )
                    if identity != persisted.get("provider_identity"):
                        faults.append("summary_provider_identity_not_reproducible")
        if records_valid and attempts_valid and store is not None:
            latest = store.latest()
            if latest.get("provider_requests") != disk_records:
                faults.append("trajectory_requests_differ_from_ledger")
            faults.extend(
                f"adoption_{fault}"
                for fault in _completed_request_evidence_faults(
                    disk_attempts,
                    disk_records,
                    latest.get("provider_exchanges"),
                )
            )
        grade = persisted.get("diagnostic_grade")
        independently_recomputed: dict[str, Any] | None = None
        if grade is not None:
            try:
                independently_recomputed = verify_case2_rc1_submission(
                    summary_path.parent / "workspace", disk_submission
                ).to_dict()
            except Exception as exc:
                faults.append(f"adoption_verifier_exception:{type(exc).__name__}")
            else:
                if canonical_sha256(independently_recomputed) != canonical_sha256(grade):
                    faults.append("summary_grade_differs_from_fresh_recomputation")
        if store is not None:
            try:
                reproduced_replay = case2_trajectory_replay_check(
                    root,
                    summary_path.parent / "workspace",
                    store,
                    grade=independently_recomputed,
                    stop_condition=(
                        str(persisted["stop_condition"])
                        if persisted.get("stop_condition") is not None
                        else None
                    ),
                )
                reproduced_replay["status"] = (
                    "passed" if reproduced_replay.get("passed") else "failed"
                )
            except Exception as exc:
                faults.append(f"adoption_replay_exception:{type(exc).__name__}")
            else:
                if canonical_sha256(reproduced_replay) != canonical_sha256(
                    persisted.get("trajectory_replay")
                ):
                    faults.append("summary_trajectory_replay_not_reproducible")
    if returned_summary is not None and canonical_sha256(persisted) != canonical_sha256(
        returned_summary
    ):
        faults.append("returned_summary_differs_from_disk")
    if faults:
        state["global_stop_faults"].extend(faults)
        state["global_stop_faults"] = list(dict.fromkeys(state["global_stop_faults"]))
        state["status"] = "global_stop"
        _write_json(target_state_path, state, secret=key)
        return
    forensic = forensic_adjudication(persisted)
    forensic_path = summary_path.parent / "forensic_adjudication.json"
    _write_json(forensic_path, forensic, secret=key)
    if model_id not in state["completed_models"]:
        state["completed_models"].append(model_id)
    def record_path(path: Path) -> str:
        try:
            return path.relative_to(root).as_posix()
        except ValueError:
            return path.as_posix()

    for field, value in (
        ("summary_paths", record_path(summary_path)),
        ("forensic_paths", record_path(forensic_path)),
    ):
        if value not in state[field]:
            state[field].append(value)
    if matrix_stop_level(str(persisted.get("classification") or "")) == (
        "cell_exclusion_continue_panel"
    ):
        excluded = {
            "model_id": model_id,
            "classification": persisted.get("classification"),
        }
        if excluded not in state["excluded_models"]:
            state["excluded_models"].append(excluded)
    state["global_stop_faults"].extend(global_stop_faults(persisted, forensic))
    refreshed = funding_snapshot_fn(key)
    state["scientific_spend_usd"] = round(_observed_spend(state, refreshed), 8)
    if state["scientific_spend_usd"] > state["scientific_hard_cap_usd"] + 1e-9:
        state["global_stop_faults"].append("budget_cap_breach")
    if credential_locations(summary_path.parent, key):
        state["global_stop_faults"].append("credential_leakage")
    state["active_cell"] = None
    state["global_stop_faults"] = list(dict.fromkeys(state["global_stop_faults"]))
    state["status"] = "global_stop" if state["global_stop_faults"] else "running"
    _write_json(target_state_path, state, secret=key)


def _reconcile_active(
    root: Path,
    *,
    key: str,
    state: dict[str, Any],
    adapters: dict[str, Any],
) -> None:
    active = state.get("active_cell")
    if not isinstance(active, dict):
        return
    mode = active_cell_recovery_mode(root, state)
    run_id = str(active.get("run_id") or "")
    model_id = str(active.get("model_id") or "")
    summary_path = root / RUNS_ROOT / run_id / "run_summary.json"
    if mode == "adopt_completed":
        _adopt_cell(
            root,
            key=key,
            state=state,
            summary_path=summary_path,
            adapter=adapters[model_id],
        )
        return
    if mode.startswith("blocked_"):
        state["global_stop_faults"].append(mode)
        state["status"] = "global_stop"
        _write_json(root / STATE_PATH, state, secret=key)
        return
    snapshot = funding_snapshot(key)
    remaining = _remaining(state, snapshot)
    if remaining <= 0:
        state["global_stop_faults"].append("cost_cap_reached_before_request")
        state["status"] = "global_stop"
        _write_json(root / STATE_PATH, state, secret=key)
        return
    row = model_config(root, model_id)
    result: Case2RunArtifacts = run_case2_episode(
        root,
        Case2RunConfig(run_id, model_id),
        adapter=adapters[model_id],
        openrouter_key=key,
        authorization_digest=state["release_digest"],
        remaining_cost_cap_usd=remaining,
        output_root=root / RUNS_ROOT,
        attempt_seed=int(row["attempt_seed"]),
        provider_seed=row.get("provider_seed"),
        resume=mode == "resume_durable_boundary",
    )
    _adopt_cell(
        root,
        key=key,
        state=state,
        summary_path=result.summary_path,
        adapter=adapters[model_id],
        returned_summary=result.summary,
    )


def run_authorized_sentinel(project_root: Path, *, key: str) -> dict[str, Any]:
    root = project_root.resolve()
    path = root / STATE_PATH
    state = _read(path) if path.is_file() else initialize_state(root, key=key)
    if state["status"] in {"funding_blocked", "route_blocked", "global_stop", "completed"}:
        return state
    adapters = load_case2_adapters(root)
    current_release = read_freeze(root)
    if current_release["closure"]["aggregate_digest"] != state.get("release_digest"):
        state["global_stop_faults"].append("release_mutation_before_active_recovery")
        state["status"] = "global_stop"
        _write_json(path, state, secret=key)
        return state
    _reconcile_active(root, key=key, state=state, adapters=adapters)
    if state["global_stop_faults"]:
        return state
    state["status"] = "running"
    _write_json(path, state, secret=key)
    for index, model_id in enumerate(state["execution_order"]):
        if model_id in state["completed_models"]:
            continue
        if read_freeze(root)["closure"]["aggregate_digest"] != state["release_digest"]:
            state["global_stop_faults"].append("release_mutation")
            state["status"] = "global_stop"
            _write_json(path, state, secret=key)
            return state
        funding = funding_snapshot(key)
        remaining = _remaining(state, funding)
        if remaining <= 0:
            state["global_stop_faults"].append("cost_cap_reached_before_request")
            state["status"] = "global_stop"
            _write_json(path, state, secret=key)
            return state
        run_id = _run_id(model_id, index)
        state["active_cell"] = {
            "model_id": model_id,
            "run_id": run_id,
            "release_digest": state["release_digest"],
            "remaining_cap_usd": remaining,
            "started_at": datetime.now(UTC).isoformat(),
        }
        _write_json(path, state, secret=key)
        _reconcile_active(root, key=key, state=state, adapters=adapters)
        if state["global_stop_faults"]:
            return state
    state["status"] = "completed"
    state["completed_at"] = datetime.now(UTC).isoformat()
    state["funding_after_science"] = funding_snapshot(key)
    state["scientific_spend_usd"] = round(_observed_spend(state, state["funding_after_science"]), 8)
    if credential_locations(root / EXECUTION_ROOT, key):
        state["status"] = "global_stop"
        state["global_stop_faults"].append("credential_leakage")
    _write_json(path, state, secret=key)
    return state


__all__ = [
    "EXECUTION_ROOT",
    "RUNS_ROOT",
    "STATE_PATH",
    "forensic_adjudication",
    "global_stop_faults",
    "active_cell_recovery_mode",
    "initialize_state",
    "route_snapshot",
    "run_authorized_sentinel",
    "summary_integrity_faults",
]

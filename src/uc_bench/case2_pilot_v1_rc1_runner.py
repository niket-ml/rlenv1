"""Direct production runner for the self-contained Case 2 release."""

from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.case1_pilot_v1_rc3_runner import (
    pre_provider_failure_assessment,
    raw_received_event_count,
    replay_not_applicable,
)
from uc_bench.case1_pilot_v1_rc3_runtime import rc3_durable_tool_functions
from uc_bench.case1_pilot_v1_rc3_tools import assert_three_surfaces
from uc_bench.case1_pilot_v1_rc4_runner import _effective_retry_records
from uc_bench.case1_pilot_v1_rc6_lifecycle import (
    RequestLifecycleMachine,
    lifecycle_identity,
)
from uc_bench.case1_pilot_v1_runner import (
    _has_active_call,
    _sampling_args,
    reported_values,
    terminal_tool_status,
    usable_provider_response_count,
)
from uc_bench.case2_pilot_v1_rc1_environment import Case2PilotRC1Environment
from uc_bench.case2_pilot_v1_rc1_interface import production_request
from uc_bench.case2_pilot_v1_rc1_runtime import (
    Case2TrajectoryStore,
    PlannedPreflightInterruption,
    RC6RequestLedger,
    TerminalProviderResponseError,
    build_case2_client,
    case1_pilot_runtime_factory,
    paced_tool_environment,
)
from uc_bench.case2_pilot_v1_rc1_semantics import WEIGHTS
from uc_bench.case2_pilot_v1_rc1_trajectory import (
    case2_trajectory_replay_check,
    restore_case2_environment,
)
from uc_bench.case2_pilot_v1_rc1_verifier import verify_case2_rc1_submission
from uc_bench.durable_trajectory import TrajectoryPersistenceError, transcript_for_resume
from uc_bench.errors import ConfigurationError, DockerRuntimeError
from uc_bench.hashing import canonical_sha256
from uc_bench.mmmvp_open_rc12_environment import rc12_isolation_passed
from uc_bench.model_runner import (
    _redact_public_identifiers,
    _resolve_generated,
    _slug,
    _write_json,
    completion_stats,
)
from uc_bench.v07_runner import _classification
from uc_bench.v071_auth import (
    credential_locations,
    mapping_contains_credential,
    redact_exception_message,
)

PREFLIGHT_AUTHORIZATION = "case2-rc1-fake-provider-production-preflight"


@dataclass(frozen=True, slots=True)
class Case2RunConfig:
    run_id: str
    model_id: str
    case_id: str = "case_02"
    mechanism: str = "default"
    partition: str = "development"
    docker_image: str = "uc-bench-agent:0.1"
    maximum_turns: int = 65
    maximum_total_completion_tokens: int = 90_000
    maximum_completion_tokens_per_turn: int = 5_000
    wall_clock_timeout_seconds: int = 4_200
    minimum_request_interval_seconds: float = 3.25


@dataclass(frozen=True, slots=True)
class Case2RunArtifacts:
    run_root: Path
    workspace_root: Path
    summary_path: Path
    request_ledger_path: Path
    summary: dict[str, Any]


def grader_assessment(
    grade: dict[str, Any] | None, exception: dict[str, str] | None
) -> dict[str, Any]:
    if grade is None:
        return {
            "status": "failed" if exception else "not_applicable",
            "passed": False if exception else None,
            "faults": ["verifier_exception"] if exception else [],
        }
    faults: list[str] = []
    if grade["complete_mission_success"] and grade["first_decision_critical_failure"]:
        faults.append("mission_success_coexists_with_critical_failure")
    if grade["complete_mission_success"] and grade["mission_failures"]:
        faults.append("mission_success_coexists_with_mission_failures")
    if (grade.get("diagnostics") or {}).get("prose_scored"):
        faults.append("scientific_prose_scored")
    if grade.get("failure_class") != "contract_failure":
        requirements = {
            str(row["requirement_id"]): bool(row["passed"])
            for row in grade.get("requirements") or []
        }
        points = (grade.get("diagnostics") or {}).get("property_points") or {}
        if set(requirements) != set(WEIGHTS) or set(points) != set(WEIGHTS):
            faults.append("scientific_property_decomposition_changed")
        else:
            recomputed = sum(float(points[name]) for name in WEIGHTS)
            if abs(float(grade["partial_scientific_quality"]) - recomputed) > 1e-9:
                faults.append("partial_scientific_quality_not_recomputed")
            if grade["complete_mission_success"] != all(requirements.values()):
                faults.append("mission_result_not_equal_to_all_properties")
    return {"status": "passed" if not faults else "failed", "passed": not faults, "faults": faults}


def _release_record(
    root: Path,
    authorization: str,
    *,
    preflight: bool,
    preflight_release: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from uc_bench.case2_pilot_v1_rc1_release import candidate_manifest, read_freeze

    release = (
        preflight_release
        if preflight and preflight_release is not None
        else candidate_manifest(root)
        if preflight
        else read_freeze(root)
    )
    expected = PREFLIGHT_AUTHORIZATION if preflight else release["closure"]["aggregate_digest"]
    if authorization != expected:
        raise ConfigurationError("Case 2 execution authorization is invalid")
    return release


def _provider_exclusion(lifecycle: RequestLifecycleMachine) -> str | None:
    if not lifecycle.attempts:
        return None
    last = lifecycle.attempts[-1]
    state = last.get("state")
    if state == "transient_transport_failure":
        matching = [
            row
            for row in lifecycle.attempts
            if row.get("logical_request_index") == last.get("logical_request_index")
            and row.get("state") == "transient_transport_failure"
        ]
        chain = last.get("error_chain") or []
        timeout = any(
            "timeout" in str(item.get("type") or "").lower()
            or "timed out" in str(item.get("message") or "").lower()
            for item in chain
            if isinstance(item, dict)
        )
        return (
            "isolated_provider_timeout"
            if len(matching) >= 2 and timeout
            else "isolated_provider_failure"
        )
    if state == "terminal_provider_failure":
        return "isolated_provider_failure"
    if state == "provider_response_parse_failure":
        return "provider_adapter_failure"
    return None


def run_case2_episode(
    project_root: Path,
    config: Case2RunConfig,
    *,
    adapter: Any,
    openrouter_key: str,
    authorization_digest: str,
    remaining_cost_cap_usd: float,
    output_root: Path,
    attempt_seed: int,
    provider_seed: int | None,
    native_client_factory: Callable[..., Any] | None = None,
    preflight_mode: bool = False,
    resume: bool = False,
    preflight_interrupt_after_phase: str | None = None,
    preflight_release: dict[str, Any] | None = None,
) -> Case2RunArtifacts:
    """Execute one Case 2 episode without any mutable inherited dispatch."""

    import verifiers as vf
    from datasets import Dataset

    root = project_root.resolve()
    if preflight_mode and native_client_factory is None:
        raise ConfigurationError("Preflight requires an injected fake provider")
    if preflight_interrupt_after_phase and not preflight_mode:
        raise ConfigurationError("Injected interruption is restricted to zero-cost preflight")
    release = _release_record(
        root,
        authorization_digest,
        preflight=preflight_mode,
        preflight_release=preflight_release,
    )
    if config.case_id != "case_02" or config.mechanism != "default":
        raise ConfigurationError("This release authorizes authentic Case 2 only")
    if config.partition != "development":
        raise ConfigurationError("Held-out partitions are forbidden")
    declared = {str(row["model_id"]): row for row in release["model_configuration"]}
    if config.model_id not in declared:
        raise ConfigurationError("Model is outside the frozen Case 2 panel")
    if adapter.model_id != config.model_id:
        raise ConfigurationError("Adapter and requested model differ")
    if adapter.to_dict() != release["provider_adapters"][config.model_id]:
        raise ConfigurationError("Provider adapter differs from the release")
    if adapter.allow_fallbacks or len(adapter.provider_order) != 1:
        raise ConfigurationError("The route must be singly pinned without fallback")
    if int(declared[config.model_id]["attempt_seed"]) != int(attempt_seed):
        raise ConfigurationError("Attempt seed differs from the release")
    if declared[config.model_id].get("provider_seed") != provider_seed:
        raise ConfigurationError("Provider seed differs from the release")
    if remaining_cost_cap_usd <= 0:
        raise ConfigurationError("No positive Case 2 budget remains")
    expected_limits = release["execution_limits"]
    observed_limits = {
        "docker_image": config.docker_image,
        "maximum_turns": config.maximum_turns,
        "maximum_total_completion_tokens": config.maximum_total_completion_tokens,
        "maximum_completion_tokens_per_turn": config.maximum_completion_tokens_per_turn,
        "wall_clock_timeout_seconds": config.wall_clock_timeout_seconds,
        "minimum_request_interval_seconds": config.minimum_request_interval_seconds,
    }
    for field, observed in observed_limits.items():
        if not preflight_mode and observed != expected_limits[field]:
            raise ConfigurationError(f"Case 2 execution limit changed: {field}")

    run_root = output_root.resolve() / _slug(config.run_id)
    workspace = run_root / "workspace"
    if resume:
        if not run_root.is_dir():
            raise ConfigurationError("Resume run does not exist")
        latest_path = run_root / "host_trajectory/latest.json"
        if not latest_path.is_file():
            raise ConfigurationError("Resume run has no durable trajectory")
        latest_value = json.loads(latest_path.read_text(encoding="utf-8"))
        if not isinstance(latest_value, dict):
            raise ConfigurationError("Resume trajectory root must be an object")
        core = restore_case2_environment(root, workspace, latest_value)
        if core.state.phase == "terminal":
            raise ConfigurationError("A terminal Case 2 run cannot be resumed")
        ledger_value = json.loads((run_root / "request_ledger.json").read_text(encoding="utf-8"))
        if not isinstance(ledger_value, dict):
            raise ConfigurationError("Resume request ledger root must be an object")
        existing_records = ledger_value.get("requests")
        if not isinstance(existing_records, list) or not all(
            isinstance(row, dict) for row in existing_records
        ):
            raise ConfigurationError("Resume request ledger records must be objects")
        prior_cost = sum(
            float((row.get("usage") or {}).get("cost") or 0) for row in existing_records
        )
        ledger = RC6RequestLedger(
            run_root / "request_ledger.json",
            adapter,
            secret=openrouter_key,
            remaining_cap_usd=prior_cost + remaining_cost_cap_usd,
            initial_records=existing_records,
        )
        store = Case2TrajectoryStore.reopen(
            run_root / "host_trajectory",
            workspace=workspace,
            core=core,  # type: ignore[arg-type]
            secret=openrouter_key,
        )
        rollout_messages = transcript_for_resume(store.latest())
    else:
        if run_root.exists():
            raise ConfigurationError(f"Run already exists: {run_root}")
        run_root.mkdir(parents=True)
        core = Case2PilotRC1Environment(root, workspace, maximum_tool_calls=80)
        ledger = RC6RequestLedger(
            run_root / "request_ledger.json",
            adapter,
            secret=openrouter_key,
            remaining_cap_usd=remaining_cost_cap_usd,
        )
        store = Case2TrajectoryStore(
            run_root / "host_trajectory",
            workspace=workspace,
            core=core,  # type: ignore[arg-type]
            secret=openrouter_key,
            run_metadata={
                "run_config": asdict(config),
                "case_id": "case_02",
                "release_id": release["release_id"],
                "release_digest": release["closure"]["aggregate_digest"],
                "attempt_seed": attempt_seed,
                "provider_seed": provider_seed,
                "agent_visible": False,
            },
        )
        rollout_messages = []
    store.interrupt_after_phase = preflight_interrupt_after_phase
    request = production_request(config)
    canonical = production_request(Case2RunConfig("identity", config.model_id))
    if request != canonical:
        raise ConfigurationError("Provider-facing request changed with the run identifier")
    if mapping_contains_credential(request, openrouter_key):
        raise ConfigurationError("Credential appeared in the scientific request")
    if canonical_sha256(request) != release["request_sha256"]:
        raise ConfigurationError("Scientific request differs from the release")

    generated: dict[str, Any]
    client: Any = None
    docker: Any = None
    isolation: dict[str, Any] = {}
    rollout_exception: dict[str, Any] | None = None
    persistence_failure = False
    transmitted_surface: list[dict[str, Any]] = []
    execution_stage = "resume_boundary_loaded" if resume else "environment_materialized"
    try:
        docker = case1_pilot_runtime_factory(
            workspace,
            container_name=f"uc-case2-rc1-{_slug(config.run_id, limit=40)}",
            image=config.docker_image,
            core=core,
        )
        docker.start()
        execution_stage = "docker_started"
        isolation = docker.security_snapshot()
        if not rc12_isolation_passed(isolation):
            raise DockerRuntimeError("The two-mount workspace isolation gate failed")
        core.mark_workspace_boundary_enforced(True)
        runtime_tools = rc3_durable_tool_functions(docker, core, store, ledger)
        transmitted_surface = assert_three_surfaces(
            request_tools=request["tools"], runtime_tools=runtime_tools
        )
        execution_stage = "tool_surface_verified"
        prompt_rows = rollout_messages or list(request["messages"])
        if prompt_rows[0].get("role") != "system":
            raise ConfigurationError("Continuation transcript lacks its system message")
        environment = paced_tool_environment(
            vf,
            minimum_interval_seconds=config.minimum_request_interval_seconds,
            dataset=Dataset.from_list([{"prompt": list(prompt_rows[1:]), "answer": ""}]),
            tools=runtime_tools,
            system_prompt=str(prompt_rows[0]["content"]),
            max_turns=max(1, config.maximum_turns - len(store._provider_exchanges)),  # noqa: SLF001
            timeout_seconds=config.wall_clock_timeout_seconds,
            stop_errors=[
                DockerRuntimeError,
                TrajectoryPersistenceError,
                TerminalProviderResponseError,
                PlannedPreflightInterruption,
            ],
            score_rollouts=False,
            env_id="uc-bench-case2-pilot-v1-rc1",
        )
        environment.set_max_total_completion_tokens(config.maximum_total_completion_tokens)
        client = build_case2_client(
            key=openrouter_key,
            adapter=adapter,
            ledger=ledger,
            store=store,
            native_client_factory=native_client_factory,
        )
        execution_stage = "client_constructed"
        generated = _resolve_generated(
            environment.evaluate(
                client=client,
                model=config.model_id,
                sampling_args=_sampling_args(adapter, config, provider_seed),
                num_examples=1,
                rollouts_per_example=1,
                max_concurrent=1,
                save_results=False,
                independent_scoring=True,
                max_retries=0,
            )
        )
        execution_stage = "evaluation_returned"
    except Exception as exc:
        persistence_failure = isinstance(exc, TrajectoryPersistenceError)
        rollout_exception = {
            "type": type(exc).__name__,
            "message": redact_exception_message(exc, secret=openrouter_key),
        }
        generated = {
            "metadata": {},
            "outputs": [
                {
                    "completion": [],
                    "error": rollout_exception,
                    "stop_condition": "runner_exception",
                }
            ],
        }
    finally:
        if client is not None:
            with suppress(Exception):
                _resolve_generated(client.close())
        if docker is not None:
            with suppress(Exception):
                docker.stop()

    output = (generated.get("outputs") or [{}])[0]
    rollout_error = output.get("error") or rollout_exception
    stop_condition = output.get("stop_condition")
    closure = terminal_tool_status(
        stop_condition=stop_condition, cap_reached=ledger.cap_reached, rollout_error=rollout_error
    )
    if closure and _has_active_call(store):
        try:
            status, reason = closure
            store.close_terminal_tool_calls(status=status, boundary_reason=reason, ledger=ledger)
            stop_condition = reason
        except Exception as exc:
            persistence_failure = True
            rollout_exception = {
                "type": type(exc).__name__,
                "message": redact_exception_message(exc, secret=openrouter_key),
            }
    lifecycle_path = run_root / "request_lifecycle.json"
    lifecycle = (
        RequestLifecycleMachine.load(lifecycle_path, secret=openrouter_key)
        if lifecycle_path.is_file()
        else RequestLifecycleMachine(lifecycle_path, secret=openrouter_key)
    )
    effective_records, retry = _effective_retry_records(ledger.records)
    classification = _classification(
        rollout_error=rollout_error,
        completion=output.get("completion") or [],
        submitted=core.state.completion_accepted,
        records=effective_records,
    )
    exclusion = _provider_exclusion(lifecycle)
    if exclusion:
        classification = exclusion
    if ledger.cap_reached:
        classification = "cost_cap_reached"
    if persistence_failure:
        classification = "infrastructure_failure"
    integrity = core.integrity_status()
    if integrity["protected_evidence_mutation_attempted"]:
        classification = "protected_evidence_tampering"
    if not integrity["workspace_boundary_enforced"]:
        classification = "infrastructure_failure"
    latest = store.latest() if store.latest_path.is_file() else {}
    raw_count = raw_received_event_count(store)
    parsed_count = len(latest.get("provider_exchanges") or [])
    boundary = pre_provider_failure_assessment(
        request_count=len(ledger.records),
        raw_response_count=raw_count,
        rollout_error=rollout_error,
        execution_stage=execution_stage,
    )
    if boundary["classification_override"]:
        classification = str(boundary["classification_override"])

    submission = core.export_submission()
    grade: dict[str, Any] | None = None
    grader_exception: dict[str, str] | None = None
    if (
        core.state.completion_accepted
        and integrity["protected_evidence_untampered"]
        and not integrity["protected_evidence_mutation_attempted"]
    ):
        try:
            grade = verify_case2_rc1_submission(workspace, submission).to_dict()
        except Exception as exc:
            grader_exception = {
                "type": type(exc).__name__,
                "message": redact_exception_message(exc, secret=openrouter_key),
            }
            classification = "grader_failure"
    grader = grader_assessment(grade, grader_exception)
    if grader["status"] == "failed":
        classification = "grader_failure"
    usable = usable_provider_response_count(ledger.records)
    replay_applicable = bool(parsed_count and not _has_active_call(store))
    if replay_applicable:
        try:
            replay = case2_trajectory_replay_check(
                root, workspace, store, grade=grade, stop_condition=stop_condition
            )
            replay["status"] = "passed" if replay["passed"] else "failed"
        except Exception as exc:
            replay = {
                "status": "failed",
                "passed": False,
                "faults": [f"replay_exception:{type(exc).__name__}"],
                "reconstructed": False,
                "recomputed_grade_matches": False,
            }
        if replay["status"] == "failed":
            classification = "infrastructure_failure"
    else:
        replay = replay_not_applicable(
            "no_durable_provider_response"
            if not raw_count
            else "provider_response_lifecycle_not_complete"
        )
    scientific_score, reliability = reported_values(
        classification,
        grade,
        usable_responses=usable,
        grader_or_replay_fault=bool(grader_exception) or replay["status"] == "failed",
    )
    identity = lifecycle_identity(
        requested_model=config.model_id,
        canonical_alias=adapter.expected_canonical_slug,
        pinned_provider=adapter.provider_order[0],
        fallback_disabled=not adapter.allow_fallbacks,
        ledger=ledger,
        lifecycle=lifecycle,
    )
    if identity["completed_response_count"] and not identity["compatible"]:
        classification = "provider_identity_failure"
        scientific_score, reliability = None, None
    if grade is not None and classification not in {
        "grader_failure",
        "infrastructure_failure",
        "protected_evidence_tampering",
    }:
        classification = "valid_episode"
        reliability = float(grade["reliability_score"])
    elif (
        grade is None
        and usable
        and classification
        not in {
            "isolated_provider_failure",
            "isolated_provider_timeout",
            "provider_adapter_failure",
            "provider_identity_failure",
            "protected_evidence_tampering",
            "infrastructure_failure",
            "grader_failure",
            "cost_cap_reached",
        }
    ):
        classification = "model_completion_failure"
        reliability = 0.0
    _release_record(
        root,
        authorization_digest,
        preflight=preflight_mode,
        preflight_release=preflight_release,
    )
    metadata = generated.get("metadata") or {}
    summary = {
        "schema_version": "uc-bench-case2-pilot-v1-rc1-run-1",
        "executed_at": datetime.now(UTC).isoformat(),
        "run_config": asdict(config),
        "run_id": config.run_id,
        "model_id": config.model_id,
        "case_id": "case_02",
        "classification": classification,
        "complete_mission_success": grade["complete_mission_success"] if grade else None,
        "partial_scientific_quality": scientific_score,
        "reliability_score": reliability,
        "diagnostic_grade": grade,
        "grader_exception": grader_exception,
        "grader_assessment": grader,
        "submission": submission,
        "rollout_error": _redact_public_identifiers(rollout_error),
        "stop_condition": stop_condition,
        "execution_stage": execution_stage,
        "provider_boundary_status": boundary["provider_boundary_status"],
        "failure_subtype": boundary["failure_subtype"],
        **completion_stats(output),
        "token_usage": output.get("token_usage") or metadata.get("usage") or {},
        "provider_adapter": adapter.to_dict(),
        "provider_identity": identity,
        "provider_requests": ledger.records,
        "provider_request_count": len(ledger.records),
        "effective_provider_request_count": len(effective_records),
        "safe_retry_adjudication": retry,
        "raw_response_persisted_count": raw_count,
        "parsed_provider_exchange_count": parsed_count,
        "usable_provider_response_count": usable,
        "cumulative_reported_cost_usd": round(ledger.cumulative_reported_cost_usd, 8),
        "attempt_seed": attempt_seed,
        "provider_seed": provider_seed,
        "resumed_from_durable_boundary": resume,
        "isolation": isolation,
        "integrity": integrity,
        "trajectory_replay": replay,
        "request_lifecycle": {
            **lifecycle.verify(),
            "path": "request_lifecycle.json",
            "states": [row["state"] for row in lifecycle.attempts],
        },
        "tool_surface": {
            "registry_request_runtime_identical": transmitted_surface == request["tools"],
            "tool_count": len(transmitted_surface),
            "sha256": canonical_sha256(transmitted_surface),
        },
        "release_id": release["release_id"],
        "release_digest": release["closure"]["aggregate_digest"],
        "provider_fallbacks_allowed": False,
        "agent_received_provider_credentials": False,
        "agent_network_enabled": False,
        "other_case_requests": 0,
        "sol_requests": 0,
        "astra_requests": 0,
    }
    _write_json(run_root / "run_summary.json", summary, secret=openrouter_key)
    _write_json(run_root / "submission.json", submission, secret=openrouter_key)
    _write_json(run_root / "verifiers_output.json", generated, secret=openrouter_key)
    if credential_locations(run_root, openrouter_key):
        raise ConfigurationError("Credential leakage guard failed in Case 2 artifacts")
    return Case2RunArtifacts(
        run_root=run_root,
        workspace_root=workspace,
        summary_path=run_root / "run_summary.json",
        request_ledger_path=run_root / "request_ledger.json",
        summary=summary,
    )


__all__ = [
    "Case2RunArtifacts",
    "Case2RunConfig",
    "PREFLIGHT_AUTHORIZATION",
    "grader_assessment",
    "run_case2_episode",
]

"""RC3 Case 1 runner with one tool registry and precise lifecycle reporting."""

from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import suppress
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.case1_pilot_v1_provider import load_case1_pilot_adapters, load_case1_pilot_config
from uc_bench.case1_pilot_v1_rc3_interface import production_request
from uc_bench.case1_pilot_v1_rc3_release import read_rc3_freeze
from uc_bench.case1_pilot_v1_rc3_runtime import rc3_durable_tool_functions
from uc_bench.case1_pilot_v1_rc3_tools import assert_three_surfaces
from uc_bench.case1_pilot_v1_release import read_release_freeze as read_rc1_freeze
from uc_bench.case1_pilot_v1_runner import (
    Case1PilotRunArtifacts,
    Case1PilotRunConfig,
    _has_active_call,
    _sampling_args,
    reported_values,
    terminal_tool_status,
    usable_provider_response_count,
)
from uc_bench.case1_pilot_v1_runtime import (
    Case1PilotTrajectoryStore,
    build_case1_pilot_client,
    case1_pilot_runtime_factory,
    paced_tool_environment,
)
from uc_bench.durable_runner import DurableRequestLedger
from uc_bench.durable_trajectory import TrajectoryPersistenceError
from uc_bench.errors import ConfigurationError, DockerRuntimeError
from uc_bench.hashing import canonical_sha256
from uc_bench.mmmvp_open_rc12_environment import rc12_isolation_passed
from uc_bench.mmmvp_open_rc17_environment import RC17OpenMMMVPEnvironment
from uc_bench.mmmvp_open_rc17_trajectory import rc17_trajectory_replay_check
from uc_bench.mmmvp_open_rc17_verifier import WEIGHTS, verify_rc17_case1_submission
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

RC3_PREFLIGHT_AUTHORIZATION = "rc3-unfrozen-fake-provider-preflight"


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
        if set(requirements) != set(WEIGHTS):
            faults.append("scientific_property_decomposition_changed")
        else:
            recomputed = sum(WEIGHTS[name] for name, passed in requirements.items() if passed)
            if abs(float(grade["partial_scientific_quality"]) - recomputed) > 1e-9:
                faults.append("partial_scientific_quality_not_recomputed")
    return {"status": "passed" if not faults else "failed", "passed": not faults, "faults": faults}


def replay_not_applicable(reason: str) -> dict[str, Any]:
    return {
        "status": "not_applicable",
        "passed": None,
        "faults": [],
        "reason": reason,
        "reconstructed": None,
        "recomputed_grade_matches": None,
    }


def pre_provider_failure_assessment(
    *, request_count: int, raw_response_count: int, rollout_error: Any, execution_stage: str
) -> dict[str, Any]:
    if raw_response_count:
        return {
            "provider_boundary_status": "durable_response_persisted",
            "classification_override": None,
            "failure_subtype": None,
        }
    if request_count:
        return {
            "provider_boundary_status": "request_attempted_without_response",
            "classification_override": None,
            "failure_subtype": None,
        }
    if rollout_error:
        return {
            "provider_boundary_status": "not_started",
            "classification_override": "infrastructure_failure",
            "failure_subtype": (
                "pre_first_request_failure"
                if execution_stage == "client_constructed"
                else "pre_client_configuration_failure"
            ),
        }
    return {
        "provider_boundary_status": "not_started",
        "classification_override": None,
        "failure_subtype": None,
    }


def raw_received_event_count(store: Case1PilotTrajectoryStore) -> int:
    """Count persistence-first raw-response events, including pre-parse failures."""

    count = 0
    for path in sorted(store.journal_root.glob("*.json")):
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        count += row.get("event_type") == "raw_model_response_received"
    return count


def _release_pair(
    root: Path,
    execution_digest: str,
    *,
    preflight_mode: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    scientific = read_rc1_freeze(root)
    if preflight_mode:
        if execution_digest != RC3_PREFLIGHT_AUTHORIZATION:
            raise ConfigurationError("Invalid unfrozen RC3 preflight authorization")
        config = load_case1_pilot_config(root)
        adapters = load_case1_pilot_adapters(root)
        execution = {
            "release_id": "uc-bench-case1-pilot-v1-rc3-preflight",
            "closure": {"aggregate_digest": RC3_PREFLIGHT_AUTHORIZATION},
            "scientific_base_digest": scientific["closure"]["aggregate_digest"],
            "request_sha256": scientific["request_sha256"],
            "tool_schema_sha256": scientific["tool_schema_sha256"],
            "model_configuration": config["models"],
            "provider_adapters": {
                model_id: adapter.to_dict() for model_id, adapter in adapters.items()
            },
        }
        return execution, scientific
    execution = read_rc3_freeze(root)
    if execution["closure"]["aggregate_digest"] != execution_digest:
        raise ConfigurationError("RC3 execution release mutated")
    if execution["scientific_base_digest"] != scientific["closure"]["aggregate_digest"]:
        raise ConfigurationError("RC3 scientific base identity changed")
    return execution, scientific


def run_case1_pilot_rc3_episode(
    project_root: Path,
    config: Case1PilotRunConfig,
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
) -> Case1PilotRunArtifacts:
    """Run Case 1 using the RC1 science and the RC3 infrastructure contract."""

    import verifiers as vf
    from datasets import Dataset

    root = project_root.resolve()
    if preflight_mode and native_client_factory is None:
        raise ConfigurationError("RC3 preflight mode requires an injected fake transport")
    execution, scientific = _release_pair(
        root, authorization_digest, preflight_mode=preflight_mode
    )
    if config.case_id != "case_01" or config.mechanism != "default":
        raise ConfigurationError("RC3 authorizes authentic Case 1 only")
    if config.partition != "development":
        raise ConfigurationError("Held-out partitions are forbidden")
    declared = {str(row["model_id"]): row for row in execution["model_configuration"]}
    if config.model_id not in declared:
        raise ConfigurationError("Model is outside the frozen RC3 panel")
    if adapter.model_id != config.model_id:
        raise ConfigurationError("Adapter and requested model differ")
    if adapter.to_dict() != execution["provider_adapters"][config.model_id]:
        raise ConfigurationError("Provider adapter differs from the frozen definition")
    if adapter.allow_fallbacks or len(adapter.provider_order) != 1:
        raise ConfigurationError("The route must be singly pinned without fallback")
    if int(declared[config.model_id]["attempt_seed"]) != int(attempt_seed):
        raise ConfigurationError("Attempt seed differs from frozen policy")
    if declared[config.model_id].get("provider_seed") != provider_seed:
        raise ConfigurationError("Provider seed differs from frozen policy")
    if remaining_cost_cap_usd <= 0:
        raise ConfigurationError("No positive RC3 scientific budget remains")

    run_root = output_root.resolve() / _slug(config.run_id)
    if run_root.exists():
        raise ConfigurationError(f"Run already exists: {run_root}")
    run_root.mkdir(parents=True)
    workspace = run_root / "workspace"
    core = RC17OpenMMMVPEnvironment(root, "case_01", workspace, maximum_tool_calls=80)
    ledger = DurableRequestLedger(
        run_root / "request_ledger.json",
        adapter,
        secret=openrouter_key,
        remaining_cap_usd=remaining_cost_cap_usd,
    )
    store = Case1PilotTrajectoryStore(
        run_root / "host_trajectory",
        workspace=workspace,
        core=core,  # type: ignore[arg-type]
        secret=openrouter_key,
        run_metadata={
            "run_config": asdict(config),
            "case_id": "case_01",
            "scientific_base_release_id": scientific["release_id"],
            "scientific_base_digest": scientific["closure"]["aggregate_digest"],
            "execution_release_id": execution["release_id"],
            "execution_release_digest": execution["closure"]["aggregate_digest"],
            "attempt_seed": attempt_seed,
            "provider_seed": provider_seed,
            "agent_visible": False,
        },
    )
    request = production_request(config)
    if mapping_contains_credential(request, openrouter_key):
        raise ConfigurationError("Credential appeared in the scientific request")
    if canonical_sha256(request) != execution["request_sha256"]:
        raise ConfigurationError("RC3 scientific request differs from the frozen request")

    generated: dict[str, Any]
    client: Any = None
    docker: Any = None
    isolation: dict[str, Any] = {}
    rollout_exception: dict[str, Any] | None = None
    persistence_failure = False
    runtime_tools: list[Any] = []
    transmitted_surface: list[dict[str, Any]] = []
    execution_stage = "environment_materialized"
    try:
        docker = case1_pilot_runtime_factory(
            workspace,
            container_name=f"uc-case1-rc3-{_slug(config.run_id, limit=40)}",
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
        environment = paced_tool_environment(
            vf,
            minimum_interval_seconds=config.minimum_request_interval_seconds,
            dataset=Dataset.from_list([{"prompt": list(request["messages"][1:]), "answer": ""}]),
            tools=runtime_tools,
            system_prompt=str(request["messages"][0]["content"]),
            max_turns=config.maximum_turns,
            timeout_seconds=config.wall_clock_timeout_seconds,
            stop_errors=[DockerRuntimeError, TrajectoryPersistenceError],
            score_rollouts=False,
            env_id="uc-bench-case1-pilot-v1-rc3",
        )
        environment.set_max_total_completion_tokens(config.maximum_total_completion_tokens)
        client = build_case1_pilot_client(
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
        stop_condition=stop_condition,
        cap_reached=ledger.cap_reached,
        rollout_error=rollout_error,
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

    classification = _classification(
        rollout_error=rollout_error,
        completion=output.get("completion") or [],
        submitted=core.state.completion_accepted,
        records=ledger.records,
    )
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
    raw_response_count = raw_received_event_count(store)
    parsed_exchange_count = len(latest.get("provider_exchanges") or [])
    boundary = pre_provider_failure_assessment(
        request_count=len(ledger.records),
        raw_response_count=raw_response_count,
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
            grade = verify_rc17_case1_submission(root, workspace, submission).to_dict()
        except Exception as exc:
            grader_exception = {
                "type": type(exc).__name__,
                "message": redact_exception_message(exc, secret=openrouter_key),
            }
            classification = "grader_failure"
    grader = grader_assessment(grade, grader_exception)
    if grader["status"] == "failed":
        classification = "grader_failure"

    usable_response_count = usable_provider_response_count(ledger.records)
    replay_applicable = bool(parsed_exchange_count and not _has_active_call(store))
    if replay_applicable:
        try:
            replay = rc17_trajectory_replay_check(
                root, workspace, store, grade=grade, stop_condition=stop_condition
            )
            replay = {**replay, "status": "passed" if replay["passed"] else "failed"}
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
            if not raw_response_count
            else "provider_response_lifecycle_not_complete"
        )

    scientific_score, reliability = reported_values(
        classification,
        grade,
        usable_responses=usable_response_count,
        grader_or_replay_fault=bool(grader_exception) or replay["status"] == "failed",
    )
    _release_pair(root, authorization_digest, preflight_mode=preflight_mode)
    metadata = generated.get("metadata") or {}
    summary = {
        "schema_version": "uc-bench-case1-pilot-v1-rc3-run-1",
        "executed_at": datetime.now(UTC).isoformat(),
        "run_config": asdict(config),
        "run_id": config.run_id,
        "model_id": config.model_id,
        "case_id": "case_01",
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
        "provider_requests": ledger.records,
        "provider_request_count": len(ledger.records),
        "raw_response_persisted_count": raw_response_count,
        "parsed_provider_exchange_count": parsed_exchange_count,
        "usable_provider_response_count": usable_response_count,
        "cumulative_reported_cost_usd": round(ledger.cumulative_reported_cost_usd, 8),
        "attempt_seed": attempt_seed,
        "provider_seed": provider_seed,
        "isolation": isolation,
        "integrity": integrity,
        "trajectory_replay": replay,
        "trajectory_persistence": replay,
        "tool_surface": {
            "registry_request_runtime_identical": transmitted_surface == request["tools"],
            "tool_count": len(transmitted_surface),
            "all_descriptions_nonempty": bool(transmitted_surface)
            and all(row["function"]["description"] for row in transmitted_surface),
            "sha256": canonical_sha256(transmitted_surface),
        },
        "scientific_base_release_id": scientific["release_id"],
        "scientific_base_digest": scientific["closure"]["aggregate_digest"],
        "execution_release_id": execution["release_id"],
        "execution_release_digest": execution["closure"]["aggregate_digest"],
        "provider_fallbacks_allowed": False,
        "agent_received_provider_credentials": False,
        "agent_network_enabled": False,
        "case2_requests": 0,
        "other_case_requests": 0,
        "sol_requests": 0,
        "astra_requests": 0,
    }
    _write_json(run_root / "run_summary.json", summary, secret=openrouter_key)
    _write_json(run_root / "submission.json", submission, secret=openrouter_key)
    _write_json(run_root / "verifiers_output.json", generated, secret=openrouter_key)
    if credential_locations(run_root, openrouter_key):
        raise ConfigurationError("Credential leakage guard failed in RC3 artifacts")
    return Case1PilotRunArtifacts(
        run_root=run_root,
        workspace_root=workspace,
        summary_path=run_root / "run_summary.json",
        request_ledger_path=run_root / "request_ledger.json",
        summary=summary,
    )


__all__ = [
    "RC3_PREFLIGHT_AUTHORIZATION",
    "grader_assessment",
    "pre_provider_failure_assessment",
    "raw_received_event_count",
    "replay_not_applicable",
    "run_case1_pilot_rc3_episode",
]

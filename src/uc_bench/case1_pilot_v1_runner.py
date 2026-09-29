"""Standalone scientific runner for the clean Case 1 pilot provenance root."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.case1_pilot_v1_interface import production_request
from uc_bench.case1_pilot_v1_release import read_release_freeze
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
from uc_bench.mmmvp_open_rc13_trajectory import (
    ACTIVE_TOOL_STATUS,
    rc13_durable_tool_functions,
)
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


def usable_provider_response_count(records: list[dict[str, Any]]) -> int:
    return sum(
        row.get("error") is None
        and bool(row.get("returned_model"))
        and not row.get("identity_violations")
        for row in records
    )


def reported_values(
    classification: str,
    grade: dict[str, Any] | None,
    *,
    usable_responses: int,
    grader_or_replay_fault: bool,
) -> tuple[float | None, float | None]:
    if grader_or_replay_fault:
        return None, None
    if grade is not None:
        return float(grade["partial_scientific_quality"]), float(
            grade["reliability_score"]
        )
    if classification in {
        "provider_adapter_failure",
        "provider_policy_refusal",
        "infrastructure_failure",
        "unknown_harness_failure",
    }:
        return (None, 0.0) if usable_responses else (None, None)
    return (None, 0.0) if usable_responses else (None, None)


def terminal_tool_status(
    *, stop_condition: str | None, cap_reached: bool, rollout_error: Any
) -> tuple[str, str] | None:
    if cap_reached:
        return "unexecuted_cost_boundary", "cost_cap_reached"
    if stop_condition in {"max_turns_reached", "max_total_completion_tokens_reached"}:
        return "unexecuted_horizon", str(stop_condition)
    rendered = str(rollout_error or "").lower()
    if stop_condition in {"timeout", "wall_clock_timeout"} or "timeout" in rendered:
        return "unexecuted_timeout", str(stop_condition or "timeout")
    return None


@dataclass(frozen=True, slots=True)
class Case1PilotRunConfig:
    run_id: str
    model_id: str
    case_id: str = "case_01"
    mechanism: str = "default"
    partition: str = "development"
    docker_image: str = "uc-bench-agent:0.1"
    maximum_turns: int = 65
    maximum_total_completion_tokens: int = 90_000
    maximum_completion_tokens_per_turn: int = 5_000
    wall_clock_timeout_seconds: int = 4_200
    minimum_request_interval_seconds: float = 3.25


@dataclass(frozen=True, slots=True)
class Case1PilotRunArtifacts:
    run_root: Path
    workspace_root: Path
    summary_path: Path
    request_ledger_path: Path
    summary: dict[str, Any]


def _tool_contract(tools: list[Any]) -> list[dict[str, Any]]:
    from verifiers.legacy.utils.tool_utils import convert_func_to_tool_def

    return [
        {
            "type": "function",
            "function": convert_func_to_tool_def(tool).model_dump(mode="json"),
        }
        for tool in tools
    ]


def assert_tool_surface(request: dict[str, Any], tools: list[Any]) -> None:
    if _tool_contract(tools) != request["tools"]:
        raise ConfigurationError("Production tool surface differs from the frozen request")
    if request.get("tool_choice") != "auto":
        raise ConfigurationError("Production tool choice must remain automatic")


def grader_consistency(grade: dict[str, Any] | None) -> dict[str, Any]:
    if grade is None:
        return {"passed": False, "faults": ["no_verifier_result"]}
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
            recomputed = sum(
                WEIGHTS[requirement_id]
                for requirement_id, passed in requirements.items()
                if passed
            )
            if abs(float(grade["partial_scientific_quality"]) - recomputed) > 1e-9:
                faults.append("partial_scientific_quality_not_recomputed")
    return {"passed": not faults, "faults": faults}


def _has_active_call(store: Case1PilotTrajectoryStore) -> bool:
    return bool(
        store.latest_path.is_file()
        and any(
            call.get("status") == ACTIVE_TOOL_STATUS
            for call in store.latest().get("pending_tool_calls") or []
        )
    )


def _sampling_args(adapter: Any, config: Case1PilotRunConfig, seed: int | None) -> dict[str, Any]:
    value = adapter.sampling_args(
        maximum_completion_tokens=config.maximum_completion_tokens_per_turn
    )
    if seed is not None:
        if "seed" not in set(adapter.supported_parameters):
            raise ConfigurationError("A provider seed was declared on a route without seed support")
        value.setdefault("extra_body", {})["seed"] = int(seed)
    return value


def _release_intact(root: Path, expected_digest: str) -> dict[str, Any]:
    release = read_release_freeze(root)
    if release["closure"]["aggregate_digest"] != expected_digest:
        raise ConfigurationError("Frozen Case 1 release mutated during execution")
    return release


def run_case1_pilot_episode(
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
) -> Case1PilotRunArtifacts:
    """Run one fresh, authentic Case 1 cell without consulting legacy releases."""

    import verifiers as vf
    from datasets import Dataset

    root = project_root.resolve()
    release = read_release_freeze(root)
    release_digest = str(release["closure"]["aggregate_digest"])
    if authorization_digest != release_digest:
        raise ConfigurationError("Execution authorization differs from the clean release digest")
    if config.case_id != "case_01" or config.mechanism != "default":
        raise ConfigurationError("The clean pilot authorizes authentic Case 1 only")
    if config.partition != "development":
        raise ConfigurationError("Held-out partitions are forbidden")
    declared = {str(row["model_id"]): row for row in release["model_configuration"]}
    if config.model_id not in declared:
        raise ConfigurationError("Model is outside the frozen five-model panel")
    if adapter.model_id != config.model_id:
        raise ConfigurationError("Adapter and requested model differ")
    if adapter.to_dict() != release["provider_adapters"][config.model_id]:
        raise ConfigurationError("Provider adapter differs from its frozen definition")
    if adapter.allow_fallbacks or len(adapter.provider_order) != 1:
        raise ConfigurationError("The route must be singly pinned with fallback disabled")
    if int(declared[config.model_id]["attempt_seed"]) != int(attempt_seed):
        raise ConfigurationError("Attempt seed differs from the frozen execution policy")
    if declared[config.model_id].get("provider_seed") != provider_seed:
        raise ConfigurationError("Provider seed differs from the frozen execution policy")
    if remaining_cost_cap_usd <= 0:
        raise ConfigurationError("No positive scientific budget remains")

    run_root = output_root.resolve() / _slug(config.run_id)
    if run_root.exists():
        raise ConfigurationError(f"Run already exists: {run_root}")
    run_root.mkdir(parents=True)
    workspace = run_root / "workspace"
    core = RC17OpenMMMVPEnvironment(
        root,
        "case_01",
        workspace,
        maximum_tool_calls=80,
    )
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
            "release_id": release["release_id"],
            "release_digest": release_digest,
            "attempt_seed": attempt_seed,
            "provider_seed": provider_seed,
            "agent_visible": False,
        },
    )
    request = production_request(config)
    if request != production_request(
        Case1PilotRunConfig(run_id="identity", model_id=config.model_id)
    ):
        raise ConfigurationError("Agent-visible request changed across run identifiers")
    if mapping_contains_credential(request, openrouter_key):
        raise ConfigurationError("Credential appeared in the scientific request")
    if release["request_sha256"] != canonical_sha256(request):
        raise ConfigurationError("Scientific request differs from the frozen request")

    generated: dict[str, Any]
    client: Any = None
    docker: Any = None
    isolation: dict[str, Any] = {}
    rollout_exception: dict[str, Any] | None = None
    persistence_failure = False
    try:
        docker = case1_pilot_runtime_factory(
            workspace,
            container_name=f"uc-case1-pilot-{_slug(config.run_id, limit=40)}",
            image=config.docker_image,
            core=core,
        )
        docker.start()
        isolation = docker.security_snapshot()
        if not rc12_isolation_passed(isolation):
            raise DockerRuntimeError("The two-mount workspace isolation gate failed")
        core.mark_workspace_boundary_enforced(True)
        tool_functions = rc13_durable_tool_functions(docker, core, store, ledger)
        assert_tool_surface(request, tool_functions)
        environment = paced_tool_environment(
            vf,
            minimum_interval_seconds=config.minimum_request_interval_seconds,
            dataset=Dataset.from_list(
                [{"prompt": list(request["messages"][1:]), "answer": ""}]
            ),
            tools=tool_functions,
            system_prompt=str(request["messages"][0]["content"]),
            max_turns=config.maximum_turns,
            timeout_seconds=config.wall_clock_timeout_seconds,
            stop_errors=[DockerRuntimeError, TrajectoryPersistenceError],
            score_rollouts=False,
            env_id="uc-bench-case1-pilot-v1-rc1",
        )
        environment.set_max_total_completion_tokens(config.maximum_total_completion_tokens)
        client = build_case1_pilot_client(
            key=openrouter_key,
            adapter=adapter,
            ledger=ledger,
            store=store,
            native_client_factory=native_client_factory,
        )
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
    consistency = (
        grader_consistency(grade)
        if grade is not None
        else {
            "passed": grader_exception is None,
            "faults": ["verifier_exception"] if grader_exception else [],
        }
    )
    if not consistency["passed"]:
        classification = "grader_failure"

    if store.latest_path.is_file():
        try:
            replay = rc17_trajectory_replay_check(
                root,
                workspace,
                store,
                grade=grade,
                stop_condition=stop_condition,
            )
        except Exception as exc:
            replay = {
                "passed": False,
                "faults": [f"replay_exception:{type(exc).__name__}"],
                "reconstructed": False,
                "recomputed_grade_matches": False,
            }
    else:
        replay = {
            "passed": False,
            "faults": ["no_durable_provider_boundary"],
            "reconstructed": False,
            "recomputed_grade_matches": False,
        }
    replay_fault = not replay["passed"]
    if replay_fault:
        classification = "infrastructure_failure"
        consistency = {
            "passed": False,
            "faults": [
                *consistency["faults"],
                "trajectory_persistence_or_replay_failure",
            ],
        }

    usable = usable_provider_response_count(ledger.records)
    scientific_score, reliability = reported_values(
        classification,
        grade,
        usable_responses=usable,
        grader_or_replay_fault=bool(grader_exception) or replay_fault,
    )
    _release_intact(root, release_digest)
    metadata = generated.get("metadata") or {}
    summary = {
        "schema_version": "uc-bench-case1-pilot-v1-run-1",
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
        "grader_consistency": consistency,
        "submission": submission,
        "rollout_error": _redact_public_identifiers(rollout_error),
        "stop_condition": stop_condition,
        **completion_stats(output),
        "token_usage": output.get("token_usage") or metadata.get("usage") or {},
        "provider_adapter": adapter.to_dict(),
        "provider_requests": ledger.records,
        "provider_request_count": len(ledger.records),
        "usable_provider_response_count": usable,
        "cumulative_reported_cost_usd": round(ledger.cumulative_reported_cost_usd, 8),
        "attempt_seed": attempt_seed,
        "provider_seed": provider_seed,
        "isolation": isolation,
        "integrity": integrity,
        "trajectory_persistence": replay,
        "framework_tool_error_count": replay.get("framework_tool_error_count", 0),
        "wrapper_tool_error_count": replay.get("wrapper_tool_error_count", 0),
        "release_id": release["release_id"],
        "release_digest": release_digest,
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
        raise ConfigurationError("Credential leakage guard failed in pilot artifacts")
    return Case1PilotRunArtifacts(
        run_root=run_root,
        workspace_root=workspace,
        summary_path=run_root / "run_summary.json",
        request_ledger_path=run_root / "request_ledger.json",
        summary=summary,
    )


__all__ = [
    "Case1PilotRunArtifacts",
    "Case1PilotRunConfig",
    "assert_tool_surface",
    "grader_consistency",
    "run_case1_pilot_episode",
]

"""Production runner for the audited, condition-blind open MMMVP release candidate."""

from __future__ import annotations

from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.docker_runtime import DockerWorkspace
from uc_bench.durable_runner import DurableRequestLedger, build_durable_scientific_client
from uc_bench.durable_trajectory import DurableTrajectoryStore, TrajectoryPersistenceError
from uc_bench.errors import ConfigurationError, DockerRuntimeError
from uc_bench.mmmvp_blind_interface import OpenExecutionLimits, serialized_open_request
from uc_bench.mmmvp_open_environment import OpenMMMVPEnvironment
from uc_bench.mmmvp_open_freeze import read_open_mmmvp_freeze
from uc_bench.mmmvp_open_trajectory import (
    open_durable_tool_functions,
    open_trajectory_replay_check,
)
from uc_bench.mmmvp_open_verifier import verify_open_submission
from uc_bench.model_runner import (
    _isolation_passed,
    _redact_public_identifiers,
    _resolve_generated,
    _slug,
    _write_json,
    completion_stats,
)
from uc_bench.v07_runner import V07RunArtifacts, _classification, _paced_environment
from uc_bench.v071_auth import (
    credential_locations,
    mapping_contains_credential,
    redact_exception_message,
)

OpenRunArtifacts = V07RunArtifacts

_EXCLUDED = {
    "infrastructure_failure",
    "provider_adapter_failure",
    "provider_policy_refusal",
    "unknown_harness_failure",
}


@dataclass(frozen=True, slots=True)
class OpenRunConfig:
    """Condition-neutral execution limits plus host-only cell identifiers."""

    run_id: str
    model_id: str
    case_id: str
    mechanism: str = "default"
    partition: str = "development"
    docker_image: str = "uc-bench-agent:0.1"
    maximum_turns: int = 65
    maximum_total_completion_tokens: int = 90_000
    maximum_completion_tokens_per_turn: int = 5_000
    wall_clock_timeout_seconds: int = 4_200
    minimum_request_interval_seconds: float = 3.25


def open_condition_id(config: OpenRunConfig) -> str:
    return f"case_03_{config.mechanism}" if config.case_id == "case_03" else config.case_id


def production_request(config: OpenRunConfig) -> dict[str, Any]:
    """Return the exact condition-free request the production runner will emit."""

    limits = OpenExecutionLimits(
        maximum_turns=config.maximum_turns,
        maximum_total_completion_tokens=config.maximum_total_completion_tokens,
        wall_clock_timeout_seconds=config.wall_clock_timeout_seconds,
    )
    return serialized_open_request(limits)


def emit_request_to_fake_provider(
    config: OpenRunConfig,
    provider: Any,
) -> Any:
    """Exercise the production serializer without a model, network, or case evidence."""

    return provider.receive_request(production_request(config))


def _tool_contract(tools: list[Any]) -> list[dict[str, Any]]:
    from verifiers.legacy.utils.tool_utils import convert_func_to_tool_def

    return [
        {"type": "function", "function": convert_func_to_tool_def(tool).model_dump(mode="json")}
        for tool in tools
    ]


def _assert_surface_matches_shared_request(
    request: dict[str, Any],
    tools: list[Any],
) -> None:
    if _tool_contract(tools) != request["tools"]:
        raise ConfigurationError("Production tool surface drifted from the audited request")
    if request.get("tool_choice") != "auto":
        raise ConfigurationError("Production tool choice drifted from the audited request")


def _grader_consistency(grade: dict[str, Any] | None) -> dict[str, Any]:
    if grade is None:
        return {"passed": False, "faults": ["no_verifier_result"]}
    faults: list[str] = []
    if grade["complete_mission_success"] and grade["first_decision_critical_failure"]:
        faults.append("mission_success_coexists_with_critical_failure")
    if grade["complete_mission_success"] and grade["mission_failures"]:
        faults.append("mission_success_coexists_with_mission_failures")
    if grade["diagnostics"].get("prose_scored"):
        faults.append("scientific_prose_scored")
    return {"passed": not faults, "faults": faults}


def _reported(
    classification: str,
    grade: dict[str, Any] | None,
) -> tuple[float | None, float | None]:
    if classification in _EXCLUDED or grade is None:
        return None, None
    return float(grade["partial_scientific_quality"]), float(grade["reliability_score"])


def run_open_mmmvp_episode(
    project_root: Path,
    config: OpenRunConfig,
    *,
    adapter: Any,
    openrouter_key: str,
    authorization_digest: str,
    remaining_cost_cap_usd: float,
) -> OpenRunArtifacts:
    """Run one frozen cell through only the audited open environment and verifier."""

    import verifiers as vf
    from datasets import Dataset

    root = project_root.resolve()
    freeze = read_open_mmmvp_freeze(root)
    if authorization_digest != freeze["hash_set_digest"]:
        raise ConfigurationError("Open MMMVP authorization does not match the RC freeze")
    if config.partition != "development":
        raise ConfigurationError("The open MMMVP runner rejects held-out partitions")
    if config.model_id not in set(freeze["model_ids"]):
        raise ConfigurationError("Model is outside the frozen older-model panel")
    condition_id = open_condition_id(config)
    if condition_id not in set(freeze["condition_ids"]):
        raise ConfigurationError("Condition is outside the frozen five-condition suite")
    if adapter.model_id != config.model_id:
        raise ConfigurationError("Provider adapter model differs from the requested model")
    if adapter.allow_fallbacks or len(adapter.provider_order) != 1:
        raise ConfigurationError("Scientific route must be singly pinned with fallback disabled")

    run_root = root / "build/uc_bench_mmmvp_open_runs" / _slug(config.run_id)
    if run_root.exists():
        raise ConfigurationError(f"Open MMMVP run already exists: {run_root}")
    run_root.mkdir(parents=True)
    workspace = run_root / "workspace"
    core = OpenMMMVPEnvironment(
        root,
        config.case_id,
        workspace,
        mechanism=config.mechanism,
        maximum_tool_calls=80,
    )
    ledger = DurableRequestLedger(
        run_root / "request_ledger.json",
        adapter,
        secret=openrouter_key,
        remaining_cap_usd=remaining_cost_cap_usd,
    )
    store = DurableTrajectoryStore(
        run_root / "host_trajectory",
        workspace=workspace,
        core=core,  # type: ignore[arg-type]
        secret=openrouter_key,
        run_metadata={
            "run_config": asdict(config),
            "condition_id": condition_id,
            "freeze_digest": freeze["hash_set_digest"],
            "agent_visible": False,
        },
    )
    request = production_request(config)
    system_prompt = str(request["messages"][0]["content"])
    initial_prompt = list(request["messages"][1:])
    if mapping_contains_credential(request, openrouter_key):
        raise ConfigurationError("Credential appeared in the scientific request")

    generated: dict[str, Any]
    client: Any = None
    docker: DockerWorkspace | None = None
    isolation: dict[str, Any] = {}
    rollout_exception: dict[str, Any] | None = None
    persistence_failure = False
    try:
        docker = DockerWorkspace(
            workspace_root=workspace,
            container_name=f"uc-mmmvp-open-{_slug(config.run_id, limit=44)}",
            image=config.docker_image,
        )
        docker.start()
        isolation = docker.security_snapshot()
        if not _isolation_passed(isolation):
            raise DockerRuntimeError("Docker isolation preflight failed closed")
        tools = open_durable_tool_functions(docker, core, store, ledger)
        _assert_surface_matches_shared_request(request, tools)
        environment = _paced_environment(
            vf,
            minimum_interval_seconds=config.minimum_request_interval_seconds,
            dataset=Dataset.from_list([{"prompt": initial_prompt, "answer": ""}]),
            tools=tools,
            system_prompt=system_prompt,
            max_turns=config.maximum_turns,
            timeout_seconds=config.wall_clock_timeout_seconds,
            stop_errors=[DockerRuntimeError, TrajectoryPersistenceError],
            score_rollouts=False,
            env_id="uc-bench-open-mmmvp-release-candidate",
        )
        environment.set_max_total_completion_tokens(config.maximum_total_completion_tokens)
        client = build_durable_scientific_client(
            key=openrouter_key,
            adapter=adapter,
            ledger=ledger,
            store=store,
        )
        generated = _resolve_generated(
            environment.evaluate(
                client=client,
                model=config.model_id,
                sampling_args=adapter.sampling_args(
                    maximum_completion_tokens=config.maximum_completion_tokens_per_turn
                ),
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
    completion = output.get("completion") or []
    rollout_error = output.get("error") or rollout_exception
    classification = _classification(
        rollout_error=rollout_error,
        completion=completion,
        submitted=core.state.completion_accepted,
        records=ledger.records,
    )
    if ledger.cap_reached:
        classification = "cost_cap_reached"
    if persistence_failure:
        classification = "infrastructure_failure"

    submission = core.export_submission()
    grade: dict[str, Any] | None = None
    grader_exception: dict[str, str] | None = None
    if core.state.completion_accepted:
        try:
            grade = verify_open_submission(
                root,
                workspace,
                submission,
                condition_id=condition_id,
            ).to_dict()
        except Exception as exc:
            grader_exception = {
                "type": type(exc).__name__,
                "message": redact_exception_message(exc, secret=openrouter_key),
            }
    consistency = (
        _grader_consistency(grade)
        if grade is not None
        else {
            "passed": grader_exception is None,
            "faults": ["verifier_exception"] if grader_exception else [],
        }
    )
    replay: dict[str, Any]
    if store.latest_path.is_file():
        try:
            replay = open_trajectory_replay_check(
                root,
                workspace,
                store,
                condition_id=condition_id,
                grade=grade,
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
    if not replay["passed"]:
        classification = "infrastructure_failure"
        consistency = {
            "passed": False,
            "faults": [*consistency["faults"], "trajectory_persistence_or_replay_failure"],
        }

    scientific_score, reliability = _reported(classification, grade)
    integrity = core.integrity_status()
    metadata = generated.get("metadata") or {}
    summary = {
        "schema_version": "uc-bench-open-mmmvp-run-1",
        "executed_at": datetime.now(UTC).isoformat(),
        "run_config": asdict(config),
        "run_id": config.run_id,
        "model_id": config.model_id,
        "condition_id": condition_id,
        "classification": classification,
        "complete_mission_success": grade["complete_mission_success"] if grade else None,
        "partial_scientific_quality": scientific_score,
        "reliability_score": reliability,
        "diagnostic_grade": grade,
        "grader_exception": grader_exception,
        "grader_consistency": consistency,
        "submission": submission,
        "rollout_error": _redact_public_identifiers(rollout_error),
        "stop_condition": output.get("stop_condition"),
        **completion_stats(output),
        "token_usage": output.get("token_usage") or metadata.get("usage") or {},
        "provider_adapter": adapter.to_dict(),
        "provider_requests": ledger.records,
        "provider_request_count": len(ledger.records),
        "cumulative_reported_cost_usd": round(ledger.cumulative_reported_cost_usd, 8),
        "isolation": isolation,
        "integrity": integrity,
        "trajectory_persistence": replay,
        "serialized_request_sha256": freeze["serialized_request_sha256"],
        "provider_fallbacks_allowed": False,
        "agent_received_provider_credentials": False,
        "agent_network_enabled": False,
        "heldout_requests": 0,
        "astra_requests": 0,
        "freeze_digest": freeze["hash_set_digest"],
    }
    _write_json(run_root / "run_summary.json", summary, secret=openrouter_key)
    _write_json(run_root / "submission.json", submission, secret=openrouter_key)
    _write_json(run_root / "verifiers_output.json", generated, secret=openrouter_key)
    leaked = credential_locations(run_root, openrouter_key)
    if leaked:
        raise ConfigurationError(
            "Credential leakage guard failed in open MMMVP artifacts: " + ", ".join(leaked)
        )
    return OpenRunArtifacts(
        run_root=run_root,
        workspace_root=workspace,
        summary_path=run_root / "run_summary.json",
        request_ledger_path=run_root / "request_ledger.json",
        summary=summary,
    )


__all__ = [
    "OpenRunArtifacts",
    "OpenRunConfig",
    "emit_request_to_fake_provider",
    "open_condition_id",
    "production_request",
    "run_open_mmmvp_episode",
]

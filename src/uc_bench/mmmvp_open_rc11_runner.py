"""Production runner for the infrastructure-only RC1.1 successor."""

from __future__ import annotations

from contextlib import suppress
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.durable_runner import DurableRequestLedger, build_durable_scientific_client
from uc_bench.durable_trajectory import DurableTrajectoryStore, TrajectoryPersistenceError
from uc_bench.errors import ConfigurationError, DockerRuntimeError
from uc_bench.mmmvp_open_freeze import read_open_mmmvp_freeze
from uc_bench.mmmvp_open_rc11_environment import (
    RC11DockerWorkspace,
    RC11OpenMMMVPEnvironment,
    rc11_isolation_passed,
)
from uc_bench.mmmvp_open_rc11_freeze import read_rc11_release_freeze
from uc_bench.mmmvp_open_rc11_trajectory import (
    rc11_durable_tool_functions,
    rc11_trajectory_replay_check,
)
from uc_bench.mmmvp_open_runner import (
    OpenRunArtifacts,
    OpenRunConfig,
    _assert_surface_matches_shared_request,
    _grader_consistency,
    open_condition_id,
    production_request,
)
from uc_bench.mmmvp_open_verifier import verify_open_submission
from uc_bench.model_runner import (
    _redact_public_identifiers,
    _resolve_generated,
    _slug,
    _write_json,
    completion_stats,
)
from uc_bench.v07_runner import _classification, _paced_environment
from uc_bench.v071_auth import (
    credential_locations,
    mapping_contains_credential,
    redact_exception_message,
)

SCIENTIFIC_FREEZE_DIGEST = "466441682b04175432329b41adcfd735cdea66f860d66f046dfae195c91e701c"


def rc11_runtime_factory(
    workspace: Path,
    *,
    container_name: str,
    image: str,
    core: RC11OpenMMMVPEnvironment,
) -> RC11DockerWorkspace:
    """Construct the exact two-mount runtime used by paid RC1.1 episodes."""

    return RC11DockerWorkspace(
        workspace_root=workspace,
        container_name=container_name,
        image=image,
        boundary_handler=core.boundary_event,
        integrity_guard=core._assert_untampered,  # noqa: SLF001 - defence-in-depth hook
    )


def usable_provider_response_count(records: list[dict[str, Any]]) -> int:
    """Count routed, non-error responses that gave the model a usable opportunity."""

    return sum(
        row.get("error") is None
        and bool(row.get("returned_model"))
        and not row.get("identity_violations")
        for row in records
    )


def rc11_reported_values(
    classification: str,
    grade: dict[str, Any] | None,
    *,
    usable_responses: int,
    grader_or_replay_fault: bool = False,
) -> tuple[float | None, float | None]:
    """Apply the predeclared reliability inclusion rules without changing science."""

    if grader_or_replay_fault:
        return None, None
    if grade is not None:
        return float(grade["partial_scientific_quality"]), float(grade["reliability_score"])
    if classification in {"provider_adapter_failure", "provider_policy_refusal"}:
        return (None, 0.0) if usable_responses else (None, None)
    if classification in {"infrastructure_failure", "unknown_harness_failure"}:
        return (None, 0.0) if usable_responses else (None, None)
    if usable_responses:
        return None, 0.0
    return None, None


def run_rc11_open_mmmvp_episode(
    project_root: Path,
    config: OpenRunConfig,
    *,
    adapter: Any,
    openrouter_key: str,
    authorization_digest: str,
    remaining_cost_cap_usd: float,
) -> OpenRunArtifacts:
    """Run one fresh Case-2 cell through unchanged RC1 science and RC1.1 isolation."""

    import verifiers as vf
    from datasets import Dataset

    root = project_root.resolve()
    scientific = read_open_mmmvp_freeze(root)
    release = read_rc11_release_freeze(root)
    if scientific["hash_set_digest"] != SCIENTIFIC_FREEZE_DIGEST:
        raise ConfigurationError("RC1.1 scientific freeze digest changed")
    if authorization_digest != release["infrastructure_digest"]:
        raise ConfigurationError("RC1.1 authorization does not match the release freeze")
    if config.partition != "development":
        raise ConfigurationError("RC1.1 rejects held-out partitions")
    if config.model_id not in set(scientific["model_ids"]):
        raise ConfigurationError("Model is outside the frozen older-model panel")
    condition_id = open_condition_id(config)
    if condition_id != "case_02":
        raise ConfigurationError("RC1.1 authorization covers only the fresh Case-2 sentinel")
    if adapter.model_id != config.model_id:
        raise ConfigurationError("Provider adapter model differs from the requested model")
    if adapter.allow_fallbacks or len(adapter.provider_order) != 1:
        raise ConfigurationError("Scientific route must be singly pinned with fallback disabled")

    run_root = root / "build/uc_bench_mmmvp_open_rc11_runs" / _slug(config.run_id)
    if run_root.exists():
        raise ConfigurationError(f"RC1.1 run already exists: {run_root}")
    run_root.mkdir(parents=True)
    workspace = run_root / "workspace"
    core = RC11OpenMMMVPEnvironment(
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
            "scientific_freeze_digest": scientific["hash_set_digest"],
            "release_infrastructure_digest": release["infrastructure_digest"],
            "agent_visible": False,
        },
    )
    request = production_request(config)
    if request != production_request(OpenRunConfig("identity", config.model_id, "case_01")):
        raise ConfigurationError("RC1.1 request changed across conditions or run IDs")
    if mapping_contains_credential(request, openrouter_key):
        raise ConfigurationError("Credential appeared in the scientific request")
    system_prompt = str(request["messages"][0]["content"])
    initial_prompt = list(request["messages"][1:])

    generated: dict[str, Any]
    client: Any = None
    docker: RC11DockerWorkspace | None = None
    isolation: dict[str, Any] = {}
    rollout_exception: dict[str, Any] | None = None
    persistence_failure = False
    try:
        docker = rc11_runtime_factory(
            workspace,
            container_name=f"uc-mmmvp-rc11-{_slug(config.run_id, limit=42)}",
            image=config.docker_image,
            core=core,
        )
        docker.start()
        isolation = docker.security_snapshot()
        if not rc11_isolation_passed(isolation):
            raise DockerRuntimeError("RC1.1 nested-mount isolation preflight failed closed")
        core.mark_workspace_boundary_enforced(True)
        tools = rc11_durable_tool_functions(docker, core, store, ledger)
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
            env_id="uc-bench-open-mmmvp-rc1-1",
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
            classification = "grader_failure"
    consistency = (
        _grader_consistency(grade)
        if grade is not None
        else {
            "passed": grader_exception is None,
            "faults": ["verifier_exception"] if grader_exception else [],
        }
    )
    if not consistency["passed"]:
        classification = "grader_failure"

    replay: dict[str, Any]
    if store.latest_path.is_file():
        try:
            replay = rc11_trajectory_replay_check(
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
    replay_fault = not replay["passed"]
    if replay_fault:
        classification = "infrastructure_failure"
        consistency = {
            "passed": False,
            "faults": [*consistency["faults"], "trajectory_persistence_or_replay_failure"],
        }

    usable = usable_provider_response_count(ledger.records)
    scientific_score, reliability = rc11_reported_values(
        classification,
        grade,
        usable_responses=usable,
        grader_or_replay_fault=bool(grader_exception) or replay_fault,
    )
    metadata = generated.get("metadata") or {}
    summary = {
        "schema_version": "uc-bench-open-mmmvp-rc1-1-run-1",
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
        "usable_provider_response_count": usable,
        "cumulative_reported_cost_usd": round(ledger.cumulative_reported_cost_usd, 8),
        "isolation": isolation,
        "integrity": integrity,
        "recoverable_contract_violation_count": integrity[
            "recoverable_contract_violation_count"
        ],
        "protected_evidence_mutation_attempted": integrity[
            "protected_evidence_mutation_attempted"
        ],
        "protected_evidence_untampered": integrity["protected_evidence_untampered"],
        "workspace_boundary_enforced": integrity["workspace_boundary_enforced"],
        "trajectory_persistence": replay,
        "serialized_request_sha256": scientific["serialized_request_sha256"],
        "provider_fallbacks_allowed": False,
        "agent_received_provider_credentials": False,
        "agent_network_enabled": False,
        "heldout_requests": 0,
        "astra_requests": 0,
        "scientific_freeze_digest": scientific["hash_set_digest"],
        "release_infrastructure_digest": release["infrastructure_digest"],
    }
    _write_json(run_root / "run_summary.json", summary, secret=openrouter_key)
    _write_json(run_root / "submission.json", submission, secret=openrouter_key)
    _write_json(run_root / "verifiers_output.json", generated, secret=openrouter_key)
    leaked = credential_locations(run_root, openrouter_key)
    if leaked:
        raise ConfigurationError(
            "Credential leakage guard failed in RC1.1 artifacts: " + ", ".join(leaked)
        )
    return OpenRunArtifacts(
        run_root=run_root,
        workspace_root=workspace,
        summary_path=run_root / "run_summary.json",
        request_ledger_path=run_root / "request_ledger.json",
        summary=summary,
    )


__all__ = [
    "SCIENTIFIC_FREEZE_DIGEST",
    "rc11_reported_values",
    "rc11_runtime_factory",
    "run_rc11_open_mmmvp_episode",
    "usable_provider_response_count",
]

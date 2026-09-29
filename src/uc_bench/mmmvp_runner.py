"""Durable scientific runner for the frozen ten-model MMMVP pilot."""

from __future__ import annotations

from contextlib import suppress
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.docker_runtime import DockerWorkspace
from uc_bench.durable_runner import (
    DurableRequestLedger,
    build_durable_scientific_client,
)
from uc_bench.durable_trajectory import DurableTrajectoryStore, TrajectoryPersistenceError
from uc_bench.errors import ConfigurationError, DockerRuntimeError
from uc_bench.mmmvp_environment import MMMVPEnvironment
from uc_bench.mmmvp_freeze import read_mmmvp_freeze
from uc_bench.mmmvp_interface import mmmvp_scientific_system_prompt
from uc_bench.mmmvp_provider import load_compatible_adapters
from uc_bench.mmmvp_score_sources import validate_score_source_registry
from uc_bench.mmmvp_trajectory import (
    mmmvp_durable_tool_functions,
    trajectory_replay_check,
)
from uc_bench.mmmvp_verifier import verify_mmmvp_submission
from uc_bench.model_runner import (
    _isolation_passed,
    _redact_public_identifiers,
    _resolve_generated,
    _slug,
    _write_json,
    completion_stats,
)
from uc_bench.v07_runner import V07RunArtifacts, V07RunConfig, _classification, _paced_environment
from uc_bench.v071_auth import (
    credential_locations,
    mapping_contains_credential,
    redact_exception_message,
)

MMMVPRunConfig = V07RunConfig
MMMVPRunArtifacts = V07RunArtifacts

_EXCLUDED = {
    "infrastructure_failure",
    "provider_adapter_failure",
    "provider_policy_refusal",
    "unknown_harness_failure",
}


def condition_id(config: MMMVPRunConfig) -> str:
    return f"case_03_{config.mechanism}" if config.case_id == "case_03" else config.case_id


def grader_consistency(
    submission: dict[str, Any], grade: dict[str, Any] | None
) -> dict[str, Any]:
    faults: list[str] = []
    if grade is None:
        return {"passed": False, "faults": ["no_verifier_result"]}
    if grade["complete_mission_success"] and grade["first_decision_critical_failure"]:
        faults.append("mission_success_coexists_with_critical_failure")
    if any(item.startswith("optional_sensitivity:") for item in grade["mission_failures"]):
        faults.append("optional_diagnostic_invalidated_mission")
    if validate_score_source_registry():
        faults.append("score_source_registry_invalid")
    if any(
        row["requirement_class"] == "mission_critical_science"
        and row["requirement_id"].startswith("optional_sensitivity:")
        for row in grade["requirements"]
    ):
        faults.append("optional_requirement_misclassified")
    checkpoints = submission.get("checkpoints") or {}
    c5 = checkpoints.get("C5") or {}
    if c5.get("decision") != grade["explicit_decision_object"]:
        faults.append("valid_final_decision_field_not_read")
    if c5.get("belief_change") != grade["numeric_belief_change"]:
        faults.append("valid_numeric_belief_field_not_read")
    if grade["diagnostic_information"]["final_verifier_corrections"].get("prose_scored"):
        faults.append("prose_scored")
    return {"passed": not faults, "faults": faults}


def _reported(
    classification: str, grade: dict[str, Any] | None
) -> tuple[float | None, float | None]:
    if classification in _EXCLUDED or grade is None:
        return None, None
    return float(grade["partial_scientific_quality"]), float(grade["reliability_score"])


def run_mmmvp_episode(
    project_root: Path,
    config: MMMVPRunConfig,
    *,
    openrouter_key: str,
    authorization_digest: str,
    remaining_cost_cap_usd: float,
) -> MMMVPRunArtifacts:
    """Run one immutable cell with no model or scientific retry."""

    import verifiers as vf
    from datasets import Dataset

    root = project_root.resolve()
    freeze = read_mmmvp_freeze(root)
    if authorization_digest != freeze["hash_set_digest"]:
        raise ConfigurationError("MMMVP execution authorization does not match the freeze")
    if config.partition != "development":
        raise ConfigurationError("MMMVP rejects held-out partitions")
    if config.model_id not in set(freeze["model_ids"]):
        raise ConfigurationError("Model is outside the frozen ten-model panel")
    selected_condition = condition_id(config)
    if selected_condition not in {
        "case_01",
        "case_02",
        "case_03_signal_collapses",
        "case_03_signal_remains",
        "case_04",
    }:
        raise ConfigurationError("Condition is outside the frozen five-condition suite")
    adapters = load_compatible_adapters(root)
    if config.model_id not in adapters:
        raise ConfigurationError("Model did not pass compatibility and cannot receive science")
    adapter = adapters[config.model_id]
    if adapter.allow_fallbacks or len(adapter.provider_order) != 1:
        raise ConfigurationError("Scientific route is not singly pinned")

    run_root = root / "build/uc_bench_mmmvp_runs" / _slug(config.run_id)
    if run_root.exists():
        raise ConfigurationError(f"MMMVP run already exists: {run_root}")
    run_root.mkdir(parents=True)
    workspace = run_root / "workspace"
    core = MMMVPEnvironment(
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
        core=core,
        secret=openrouter_key,
        run_metadata={
            "run_config": asdict(config),
            "condition_id": selected_condition,
            "freeze_digest": freeze["hash_set_digest"],
            "agent_visible": False,
        },
    )
    task_text = (workspace / "README.md").read_text(encoding="utf-8")
    system_prompt = mmmvp_scientific_system_prompt(
        task_text, config, condition_id=selected_condition
    )
    initial_prompt = [
        {
            "role": "user",
            "content": "Begin the evidence-chain diligence investigation in /workspace.",
        }
    ]
    if mapping_contains_credential(
        [{"role": "system", "content": system_prompt}, *initial_prompt], openrouter_key
    ):
        raise ConfigurationError("Credential appeared in the scientific prompt")

    generated: dict[str, Any]
    client: Any = None
    docker: DockerWorkspace | None = None
    isolation: dict[str, Any] = {}
    rollout_exception: dict[str, Any] | None = None
    persistence_failure = False
    try:
        docker = DockerWorkspace(
            workspace_root=workspace,
            container_name=f"uc-mmmvp-{_slug(config.run_id, limit=49)}",
            image=config.docker_image,
        )
        docker.start()
        isolation = docker.security_snapshot()
        if not _isolation_passed(isolation):
            raise DockerRuntimeError("Docker isolation preflight failed closed")
        environment = _paced_environment(
            vf,
            minimum_interval_seconds=config.minimum_request_interval_seconds,
            dataset=Dataset.from_list([{"prompt": initial_prompt, "answer": ""}]),
            tools=mmmvp_durable_tool_functions(docker, core, store, ledger),
            system_prompt=system_prompt,
            max_turns=config.maximum_turns,
            timeout_seconds=config.wall_clock_timeout_seconds,
            stop_errors=[DockerRuntimeError, TrajectoryPersistenceError],
            score_rollouts=False,
            env_id="uc-bench-mmmvp-multimodel-pilot",
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

    output = ((generated.get("outputs") or [{}])[0])
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
    if len(submission.get("checkpoints") or {}) == 5:
        try:
            grade = verify_mmmvp_submission(
                root,
                workspace,
                submission,
                condition_id=selected_condition,
            ).to_dict()
        except Exception as exc:
            grader_exception = {
                "type": type(exc).__name__,
                "message": redact_exception_message(exc, secret=openrouter_key),
            }
    consistency = (
        grader_consistency(submission, grade)
        if grade is not None
        else {
            "passed": grader_exception is None,
            "faults": ["verifier_exception"] if grader_exception else [],
        }
    )
    replay: dict[str, Any]
    if store.latest_path.is_file():
        try:
            replay = trajectory_replay_check(
                root,
                workspace,
                store,
                condition_id=selected_condition,
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
        "schema_version": "uc-bench-mmmvp-run-1",
        "executed_at": datetime.now(UTC).isoformat(),
        "run_config": asdict(config),
        "run_id": config.run_id,
        "run_directory": run_root.relative_to(root).as_posix(),
        "workspace_directory": workspace.relative_to(root).as_posix(),
        "host_trajectory_directory": (run_root / "host_trajectory").relative_to(root).as_posix(),
        "model_id": config.model_id,
        "condition_id": selected_condition,
        "case_id": config.case_id,
        "mechanism": config.mechanism,
        "partition": config.partition,
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
        "returned_models": sorted(
            {str(row["returned_model"]) for row in ledger.records if row.get("returned_model")}
        ),
        "actual_providers": sorted(
            {str(row["actual_provider"]) for row in ledger.records if row.get("actual_provider")}
        ),
        "cumulative_reported_cost_usd": round(ledger.cumulative_reported_cost_usd, 8),
        "isolation": isolation,
        "isolation_preflight_passed": _isolation_passed(isolation),
        "integrity": integrity,
        "trajectory_persistence": replay,
        "provider_fallbacks_allowed": False,
        "agent_received_provider_credentials": False,
        "agent_network_enabled": False,
        "heldout_requests": 0,
        "astra_requests": 0,
        "freeze_digest": freeze["hash_set_digest"],
    }
    _write_json(run_root / "run_summary.json", summary, secret=openrouter_key)
    _write_json(run_root / "submission.json", submission, secret=openrouter_key)
    _write_json(
        run_root / "environment_event_log.json",
        {"events": core.state.event_log, "integrity": integrity},
        secret=openrouter_key,
    )
    _write_json(run_root / "verifiers_output.json", generated, secret=openrouter_key)
    leaked = credential_locations(run_root, openrouter_key)
    if leaked:
        raise ConfigurationError(
            "Credential leakage guard failed in MMMVP artifacts: " + ", ".join(leaked)
        )
    return MMMVPRunArtifacts(
        run_root=run_root,
        workspace_root=workspace,
        summary_path=run_root / "run_summary.json",
        request_ledger_path=run_root / "request_ledger.json",
        summary=summary,
    )


__all__ = [
    "MMMVPRunArtifacts",
    "MMMVPRunConfig",
    "condition_id",
    "grader_consistency",
    "run_mmmvp_episode",
]

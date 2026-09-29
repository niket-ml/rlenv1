"""Native runner for the bounded v0.8 MVP development tranche."""

from __future__ import annotations

from contextlib import suppress
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.docker_runtime import DockerWorkspace
from uc_bench.errors import ConfigurationError, DockerRuntimeError
from uc_bench.model_runner import (
    _isolation_passed,
    _redact_public_identifiers,
    _resolve_generated,
    _slug,
    _write_json,
    completion_stats,
)
from uc_bench.openrouter import OPENROUTER_BASE_URL
from uc_bench.v07_provider import load_v07_provider_adapters
from uc_bench.v07_runner import V07RunArtifacts, V07RunConfig, _classification, _paced_environment
from uc_bench.v071_auth import (
    V071RequestLedger,
    build_v071_scientific_client,
    credential_locations,
    mapping_contains_credential,
    redact_exception_message,
)
from uc_bench.v08_environment import V08Environment, v08_tool_functions
from uc_bench.v08_interface import v08_scientific_system_prompt
from uc_bench.v08_snapshot import read_v08_execution_snapshot
from uc_bench.v08_verifier import verify_v08_submission

V08RunConfig = V07RunConfig
V08RunArtifacts = V07RunArtifacts
build_v08_scientific_client = build_v071_scientific_client

_EXCLUDED_EXECUTION_CLASSES = {
    "infrastructure_failure",
    "provider_adapter_failure",
    "provider_policy_refusal",
    "unknown_harness_failure",
}


class V08CostCapReached(RuntimeError):
    """Raised immediately after a response ledger reaches the episode allowance."""


class V08RequestLedger(V071RequestLedger):
    """Checkpoint and enforce the remaining matrix cap after every response."""

    def __init__(self, *args: Any, remaining_cap_usd: float, **kwargs: Any) -> None:
        self.remaining_cap_usd = float(remaining_cap_usd)
        if self.remaining_cap_usd <= 0:
            raise ConfigurationError("No positive v0.8 request budget remains")
        super().__init__(*args, **kwargs)

    def _checkpoint(self) -> None:
        super()._checkpoint()
        if self.cumulative_reported_cost_usd >= self.remaining_cap_usd:
            raise V08CostCapReached("The v0.8 per-request cumulative cost cap was reached")


def _reported_scores(
    classification: str, grade: dict[str, Any] | None
) -> tuple[float | None, float | None]:
    if classification in _EXCLUDED_EXECUTION_CLASSES or grade is None:
        return None, None
    return (
        float(grade["partial_scientific_quality"]),
        float(grade["reliability_score"]),
    )


def _condition_id(config: V08RunConfig) -> str:
    return (
        f"case_03_{config.mechanism}"
        if config.case_id == "case_03"
        else config.case_id
    )


def _grader_consistency(
    submission: dict[str, Any], grade: dict[str, Any] | None
) -> dict[str, Any]:
    faults: list[str] = []
    if grade is None:
        return {"passed": False, "faults": ["no_verifier_result"]}
    if grade["complete_mission_success"] and grade["first_decision_critical_failure"]:
        faults.append("mission_success_coexists_with_critical_failure")
    if any(
        failure.startswith("optional_sensitivity:")
        for failure in grade["mission_failures"]
    ):
        faults.append("optional_diagnostic_invalidated_mission")
    checkpoints = submission.get("checkpoints") or {}
    c4 = checkpoints.get("C4") or {}
    c5 = checkpoints.get("C5") or {}
    if c4.get("initial_decision") != grade["explicit_initial_decision_object"]:
        faults.append("valid_initial_decision_field_not_read")
    if c5.get("decision") != grade["explicit_decision_object"]:
        faults.append("valid_final_decision_field_not_read")
    if c5.get("belief_change") != grade["numeric_belief_change"]:
        faults.append("valid_numeric_belief_field_not_read")
    if grade["legacy_migration_provenance"]["belief"]["mode"] != "native_v08_numeric_belief":
        faults.append("legacy_belief_fallback_used_in_native_episode")
    if grade["legacy_migration_provenance"]["decision"]["mode"] != (
        "native_v08_explicit_decision"
    ):
        faults.append("legacy_decision_fallback_used_in_native_episode")
    return {"passed": not faults, "faults": faults}


def run_v08_episode(
    project_root: Path,
    config: V08RunConfig,
    *,
    openrouter_key: str,
    authorization_digest: str,
    remaining_cost_cap_usd: float = 8.0,
) -> V08RunArtifacts:
    """Run one snapshotted development episode with no scientific retry."""

    import verifiers as vf
    from datasets import Dataset

    root = project_root.resolve()
    snapshot = read_v08_execution_snapshot(root)
    if authorization_digest != snapshot["hash_set_digest"]:
        raise ConfigurationError("v0.8 execution lacks the exact snapshot authorization")
    condition_id = _condition_id(config)
    if config.model_id != "openai/gpt-5.6-sol":
        raise ConfigurationError("The v0.8 development tranche permits only GPT-5.6 Sol")
    if condition_id not in {"case_02", "case_03_signal_remains", "case_04"}:
        raise ConfigurationError("Condition is outside the authorized v0.8 tranche")
    adapters = load_v07_provider_adapters(root)
    adapter = adapters[config.model_id]
    if adapter.provider_order != ("OpenAI",) or adapter.allow_fallbacks:
        raise ConfigurationError("The v0.8 route must be pinned to OpenAI without fallback")

    run_root = root / "build/hard_suite_v08_runs" / _slug(config.run_id)
    if run_root.exists():
        raise ConfigurationError(f"v0.8 run already exists: {run_root}")
    run_root.mkdir(parents=True)
    workspace = run_root / "workspace"
    core = V08Environment(
        root,
        config.case_id,
        workspace,
        mechanism=config.mechanism,
        maximum_tool_calls=80,
    )
    docker: DockerWorkspace | None = None
    ledger_path = run_root / "request_ledger.json"
    ledger = V08RequestLedger(
        ledger_path,
        adapter,
        secret=openrouter_key,
        remaining_cap_usd=remaining_cost_cap_usd,
    )
    task_text = (workspace / "README.md").read_text(encoding="utf-8")
    system_prompt = v08_scientific_system_prompt(
        task_text, config, condition_id=condition_id
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
    isolation: dict[str, Any] = {}
    rollout_exception: dict[str, Any] | None = None
    try:
        docker = DockerWorkspace(
            workspace_root=workspace,
            container_name=f"uc-v08-{_slug(config.run_id, limit=53)}",
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
            tools=v08_tool_functions(docker, core),
            system_prompt=system_prompt,
            max_turns=config.maximum_turns,
            timeout_seconds=config.wall_clock_timeout_seconds,
            stop_errors=[DockerRuntimeError],
            score_rollouts=False,
            env_id="uc-bench-v0-8-mvp-development",
        )
        environment.set_max_total_completion_tokens(config.maximum_total_completion_tokens)
        # This is the already validated native adapter path: the key and base URL
        # are explicit constructor arguments, and no temporary environment lookup
        # occurs before client creation.
        client = build_v08_scientific_client(
            key=openrouter_key,
            base_url=OPENROUTER_BASE_URL,
            adapter=adapter,
            ledger=ledger,
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

    outputs = generated.get("outputs") or []
    output = outputs[0] if outputs and isinstance(outputs[0], dict) else {}
    completion = output.get("completion") or []
    rollout_error = output.get("error") or rollout_exception
    classification = _classification(
        rollout_error=rollout_error,
        completion=completion,
        submitted=core.state.completion_accepted,
        records=ledger.records,
    )
    if (rollout_exception or {}).get("type") == "V08CostCapReached":
        classification = "cost_cap_reached"
    submission = core.export_submission()
    grade: dict[str, Any] | None = None
    grader_exception: dict[str, str] | None = None
    if len(submission.get("checkpoints") or {}) == 5:
        try:
            grade = verify_v08_submission(
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
    consistency = _grader_consistency(submission, grade) if grade else {
        "passed": grader_exception is None,
        "faults": ["verifier_exception"] if grader_exception else [],
    }
    scientific_score, reliability = _reported_scores(classification, grade)
    integrity = core.integrity_status()
    metadata = generated.get("metadata") or {}
    summary = {
        "schema_version": "0.8-development-run-1",
        "executed_at": datetime.now(UTC).isoformat(),
        "run_config": asdict(config),
        "run_id": config.run_id,
        "run_directory": run_root.relative_to(root).as_posix(),
        "workspace_directory": workspace.relative_to(root).as_posix(),
        "model_id": config.model_id,
        "case_id": config.case_id,
        "mechanism": config.mechanism,
        "condition_id": condition_id,
        "partition": config.partition,
        "classification": classification,
        "complete_mission_success": (
            grade["complete_mission_success"] if grade is not None else None
        ),
        "partial_scientific_quality": scientific_score,
        "scientific_score": scientific_score,
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
        "resolved_reasoning_efforts": sorted(
            {
                str(row["resolved_reasoning_effort"])
                for row in ledger.records
                if row.get("resolved_reasoning_effort")
            }
        ),
        "cumulative_reported_cost_usd": round(ledger.cumulative_reported_cost_usd, 8),
        "isolation": isolation,
        "isolation_preflight_passed": _isolation_passed(isolation),
        "integrity": integrity,
        "complete_tool_history_paths": [
            (run_root / "verifiers_output.json").relative_to(root).as_posix(),
            (run_root / "environment_event_log.json").relative_to(root).as_posix(),
        ],
        "authentication_lifecycle": {
            "explicit_key_constructor_argument": True,
            "explicit_base_url_constructor_argument": True,
            "environment_variable_lookup_used": False,
            "credential_redaction_enabled": True,
        },
        "agent_received_provider_credentials": False,
        "agent_network_enabled": False,
        "provider_fallbacks_allowed": False,
        "heldout_requests": 0,
        "astra_requests": 0,
        "execution_snapshot_digest": snapshot["hash_set_digest"],
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
            "Credential leakage guard failed in recorded run artifacts: " + ", ".join(leaked)
        )
    return V08RunArtifacts(
        run_root=run_root,
        workspace_root=workspace,
        summary_path=run_root / "run_summary.json",
        request_ledger_path=ledger_path,
        summary=summary,
    )


__all__ = [
    "V08RunArtifacts",
    "V08RunConfig",
    "build_v08_scientific_client",
    "run_v08_episode",
]

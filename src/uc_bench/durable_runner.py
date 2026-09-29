"""Infrastructure-only v0.8 runner with durable host trajectory checkpoints."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.docker_runtime import DockerWorkspace
from uc_bench.durable_trajectory import (
    DurableTrajectoryStore,
    TrajectoryPersistenceError,
    durable_tool_functions,
    restore_v08_environment,
)
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
from uc_bench.v06_provider import _as_dict
from uc_bench.v062_provider import V062AuditedOpenRouterClient
from uc_bench.v07_provider import load_v07_provider_adapters
from uc_bench.v07_runner import V07RunArtifacts, V07RunConfig, _classification, _paced_environment
from uc_bench.v071_auth import (
    V071RequestLedger,
    build_v071_scientific_client,
    credential_locations,
    mapping_contains_credential,
    redact_exception_message,
)
from uc_bench.v08_environment import V08Environment
from uc_bench.v08_interface import v08_scientific_system_prompt
from uc_bench.v08_runner import (
    V08CostCapReached,
    _condition_id,
    _grader_consistency,
    _reported_scores,
)
from uc_bench.v08_verifier import verify_v08_submission

DurableRunConfig = V07RunConfig
DurableRunArtifacts = V07RunArtifacts


class DurableRequestLedger(V071RequestLedger):
    """Persist cost first, then let the observer checkpoint the received response."""

    def __init__(
        self,
        path: Path,
        adapter: Any,
        *,
        secret: str,
        remaining_cap_usd: float,
        initial_records: list[dict[str, Any]] | None = None,
    ) -> None:
        if remaining_cap_usd <= 0:
            raise ConfigurationError("No positive v0.8 request budget remains")
        self.remaining_cap_usd = float(remaining_cap_usd)
        self.cap_reached = False
        self._secret = secret
        self.path = path.resolve()
        self.adapter = adapter
        self.records = list(initial_records or [])
        self.write_count = 0
        self._checkpoint()

    def _checkpoint(self) -> None:
        # Bypass v0.8's original immediate exception only long enough to persist
        # the corresponding assistant response.  The client calls enforce_cap()
        # before control can return to the agent loop.
        V071RequestLedger._checkpoint(self)
        self.cap_reached = self.cumulative_reported_cost_usd >= self.remaining_cap_usd

    def enforce_cap(self) -> None:
        if self.cap_reached:
            raise V08CostCapReached("The v0.8 per-request cumulative cost cap was reached")


class DurableAuditedOpenRouterClient(V062AuditedOpenRouterClient):
    """Observe the validated request path without changing its request body."""

    def __init__(
        self,
        client_or_config: Any,
        adapter: Any,
        ledger: DurableRequestLedger,
        store: DurableTrajectoryStore,
    ) -> None:
        self.store = store
        super().__init__(client_or_config, adapter, ledger)

    async def get_native_response(
        self,
        prompt: Any,
        model: str,
        sampling_args: Any,
        tools: Any = None,
        **kwargs: Any,
    ) -> Any:
        try:
            response = await super().get_native_response(
                prompt,
                model,
                sampling_args,
                tools,
                **kwargs,
            )
        except Exception as exc:
            self.store.record_model_error(prompt=prompt, error=exc, ledger=self.ledger)
            raise
        self.store.record_model_response(prompt=prompt, response=response, ledger=self.ledger)
        self.ledger.enforce_cap()
        return response


def build_durable_scientific_client(
    *,
    key: str,
    adapter: Any,
    ledger: DurableRequestLedger,
    store: DurableTrajectoryStore,
    native_client_factory: Callable[..., Any] | None = None,
) -> DurableAuditedOpenRouterClient:
    """Use the exact validated explicit-key constructor with one host observer."""

    kwargs: dict[str, Any] = {}
    if native_client_factory is not None:
        kwargs["native_client_factory"] = native_client_factory
    return build_v071_scientific_client(
        key=key,
        base_url=OPENROUTER_BASE_URL,
        adapter=adapter,
        ledger=ledger,
        audited_client_factory=lambda native, selected, request_ledger: (
            DurableAuditedOpenRouterClient(native, selected, request_ledger, store)
        ),
        **kwargs,
    )


def _trajectory_replay_check(
    project_root: Path,
    workspace: Path,
    store: DurableTrajectoryStore,
    *,
    condition_id: str,
    grade: dict[str, Any] | None,
) -> dict[str, Any]:
    verification = store.verify()
    if not verification["passed"]:
        return {**verification, "reconstructed": False, "recomputed_grade_matches": False}
    latest = store.latest()
    restored = restore_v08_environment(project_root, workspace, latest)
    restored_grade: dict[str, Any] | None = None
    if len(restored.export_submission().get("checkpoints") or {}) == 5:
        restored_grade = verify_v08_submission(
            project_root,
            workspace,
            restored.export_submission(),
            condition_id=condition_id,
        ).to_dict()
    return {
        **verification,
        "reconstructed": restored.export_submission()
        == latest["environment"]["submission"],
        "recomputed_grade_matches": restored_grade == grade,
        "resume_boundary_available": (
            restored.state.phase != "terminal"
            and bool(latest.get("messages"))
            and not any(
                call.get("status") == "pending"
                for call in latest.get("pending_tool_calls") or []
            )
        ),
        "terminal_replay_available": restored.state.phase == "terminal",
    }


def run_durable_v08_episode(
    project_root: Path,
    config: DurableRunConfig,
    *,
    openrouter_key: str,
    authorization_digest: str,
    remaining_cost_cap_usd: float,
) -> DurableRunArtifacts:
    """Run one snapshot-03 episode while persisting every continuation boundary."""

    import verifiers as vf
    from datasets import Dataset

    from uc_bench.execution_snapshot_03 import read_execution_snapshot_03

    root = project_root.resolve()
    snapshot = read_execution_snapshot_03(root)
    if authorization_digest != snapshot["hash_set_digest"]:
        raise ConfigurationError("v0.8 snapshot-03 authorization digest differs")
    condition_id = _condition_id(config)
    if config.model_id != "openai/gpt-5.6-sol":
        raise ConfigurationError("The final v0.8 check permits only GPT-5.6 Sol")
    if condition_id not in {"case_03_signal_remains", "case_04"}:
        raise ConfigurationError("Condition is outside the final two-condition check")
    adapters = load_v07_provider_adapters(root)
    adapter = adapters[config.model_id]
    if adapter.provider_order != ("OpenAI",) or adapter.allow_fallbacks:
        raise ConfigurationError("The v0.8 route must be pinned to OpenAI without fallback")

    run_root = root / "build/hard_suite_v08_runs" / _slug(config.run_id)
    if run_root.exists():
        raise ConfigurationError(f"v0.8 durable run already exists: {run_root}")
    run_root.mkdir(parents=True)
    workspace = run_root / "workspace"
    core = V08Environment(
        root,
        config.case_id,
        workspace,
        mechanism=config.mechanism,
        maximum_tool_calls=80,
    )
    ledger_path = run_root / "request_ledger.json"
    ledger = DurableRequestLedger(
        ledger_path,
        adapter,
        secret=openrouter_key,
        remaining_cap_usd=remaining_cost_cap_usd,
    )
    host_trajectory_root = run_root / "host_trajectory"
    store = DurableTrajectoryStore(
        host_trajectory_root,
        workspace=workspace,
        core=core,
        secret=openrouter_key,
        run_metadata={
            "run_config": asdict(config),
            "condition_id": condition_id,
            "execution_snapshot_digest": snapshot["hash_set_digest"],
            "agent_visible": False,
        },
    )
    task_text = (workspace / "README.md").read_text(encoding="utf-8")
    system_prompt = v08_scientific_system_prompt(
        task_text,
        config,
        condition_id=condition_id,
    )
    initial_prompt = [
        {
            "role": "user",
            "content": "Begin the evidence-chain diligence investigation in /workspace.",
        }
    ]
    if mapping_contains_credential(
        [{"role": "system", "content": system_prompt}, *initial_prompt],
        openrouter_key,
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
            container_name=f"uc-v08d-{_slug(config.run_id, limit=52)}",
            image=config.docker_image,
        )
        docker.start()
        isolation = docker.security_snapshot()
        if not _isolation_passed(isolation):
            raise DockerRuntimeError("Docker isolation preflight failed closed")
        tools = durable_tool_functions(docker, core, store, ledger)
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
            env_id="uc-bench-v0-8-mvp-development",
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
    if ledger.cap_reached:
        classification = "cost_cap_reached"
    if persistence_failure:
        classification = "infrastructure_failure"

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
    consistency = (
        _grader_consistency(submission, grade)
        if grade
        else {
            "passed": grader_exception is None,
            "faults": ["verifier_exception"] if grader_exception else [],
        }
    )
    trajectory_replay: dict[str, Any]
    if store.latest_path.is_file():
        try:
            trajectory_replay = _trajectory_replay_check(
                root,
                workspace,
                store,
                condition_id=condition_id,
                grade=grade,
            )
        except Exception as exc:
            trajectory_replay = {
                "passed": False,
                "faults": [f"replay_exception:{type(exc).__name__}"],
                "reconstructed": False,
                "recomputed_grade_matches": False,
            }
    else:
        trajectory_replay = {
            "passed": False,
            "faults": ["no_durable_provider_boundary"],
            "reconstructed": False,
            "recomputed_grade_matches": False,
        }
    if not trajectory_replay["passed"]:
        classification = "infrastructure_failure"
        consistency = {
            "passed": False,
            "faults": [*consistency["faults"], "trajectory_persistence_or_replay_failure"],
        }

    scientific_score, reliability = _reported_scores(classification, grade)
    integrity = core.integrity_status()
    metadata = generated.get("metadata") or {}
    summary = {
        "schema_version": "0.8-durable-development-run-1",
        "executed_at": datetime.now(UTC).isoformat(),
        "run_config": asdict(config),
        "run_id": config.run_id,
        "run_directory": run_root.relative_to(root).as_posix(),
        "workspace_directory": workspace.relative_to(root).as_posix(),
        "host_trajectory_directory": host_trajectory_root.relative_to(root).as_posix(),
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
        "trajectory_persistence": trajectory_replay,
        "complete_tool_history_paths": [
            (run_root / "verifiers_output.json").relative_to(root).as_posix(),
            (run_root / "environment_event_log.json").relative_to(root).as_posix(),
            host_trajectory_root.relative_to(root).as_posix(),
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
        "parent_snapshot_02_digest": snapshot["parent_snapshot_02"]["hash_set_digest"],
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
    return DurableRunArtifacts(
        run_root=run_root,
        workspace_root=workspace,
        summary_path=run_root / "run_summary.json",
        request_ledger_path=ledger_path,
        summary=summary,
    )


def raw_response_dict(response: Any) -> dict[str, Any]:
    """Expose only the serialization used by persistence regression tests."""

    return _as_dict(response)


__all__ = [
    "DurableAuditedOpenRouterClient",
    "DurableRequestLedger",
    "DurableRunArtifacts",
    "DurableRunConfig",
    "build_durable_scientific_client",
    "run_durable_v08_episode",
]

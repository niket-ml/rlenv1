"""Run one v0.6 development episode with pinned cross-provider adapters."""

from __future__ import annotations

import asyncio
import json
import time
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.docker_runtime import DEFAULT_IMAGE, DockerWorkspace
from uc_bench.errors import ConfigurationError, ContractError, DockerRuntimeError
from uc_bench.hard_suite_v06 import V06Builder, V06Environment, grade_v06
from uc_bench.model_runner import (
    _isolation_passed,
    _redact_public_identifiers,
    _resolve_generated,
    _slug,
    _temporary_environment,
    _write_json,
    completion_stats,
)
from uc_bench.openrouter import OPENROUTER_BASE_URL
from uc_bench.v06_freeze import read_v06_freeze_manifest
from uc_bench.v06_provider import (
    AuditedOpenRouterClient,
    RequestLedger,
    classify_execution,
    load_provider_adapters,
    reliability_score,
)


@dataclass(frozen=True, slots=True)
class V06RunConfig:
    model_id: str
    run_id: str
    scenario_id: str
    seed: int
    partition: str = "development"
    maximum_turns: int = 65
    maximum_completion_tokens_per_turn: int = 5_000
    maximum_total_completion_tokens: int = 90_000
    wall_clock_timeout_seconds: int = 4_200
    minimum_request_interval_seconds: float = 3.25
    docker_image: str = DEFAULT_IMAGE

    def __post_init__(self) -> None:
        if not all(value.strip() for value in (self.model_id, self.run_id, self.scenario_id)):
            raise ConfigurationError("v0.6 run identifiers must not be empty")
        if self.partition != "development":
            raise ConfigurationError("v0.6 scientific runner rejects held-out partitions")
        lowered = self.model_id.lower()
        if "astra" in lowered or "gpt-6" in lowered:
            raise ConfigurationError("Astra and GPT-6 models are forbidden in v0.6 development")
        if (
            min(
                self.maximum_turns,
                self.maximum_completion_tokens_per_turn,
                self.maximum_total_completion_tokens,
                self.wall_clock_timeout_seconds,
            )
            <= 0
        ):
            raise ConfigurationError("v0.6 run budgets must be positive")
        if self.minimum_request_interval_seconds < 0:
            raise ConfigurationError("minimum request interval must not be negative")


@dataclass(frozen=True, slots=True)
class V06RunArtifacts:
    run_root: Path
    workspace_root: Path
    summary_path: Path
    request_ledger_path: Path
    summary: dict[str, Any]


def _paced_tool_environment(vf: Any, *, minimum_interval_seconds: float, **kwargs: Any) -> Any:
    class PacedToolEnvironment(vf.ToolEnv):
        def __init__(self, **environment_kwargs: Any) -> None:
            super().__init__(**environment_kwargs)
            self._minimum_request_interval_seconds = minimum_interval_seconds
            self._last_request_started_at: float | None = None

        async def get_model_response(
            self,
            state: Any,
            prompt: Any,
            **response_kwargs: Any,
        ) -> Any:
            now = time.monotonic()
            if self._last_request_started_at is not None:
                remaining = self._minimum_request_interval_seconds - (
                    now - self._last_request_started_at
                )
                if remaining > 0:
                    await asyncio.sleep(remaining)
            self._last_request_started_at = time.monotonic()
            return await super().get_model_response(state, prompt, **response_kwargs)

    return PacedToolEnvironment(**kwargs)


def _commitment_intact(environment: V06Environment) -> bool:
    if not environment.committed_snapshot:
        return False
    try:
        environment._verify_commitment()  # noqa: SLF001 - audit the environment invariant
    except (ContractError, OSError):
        return False
    return True


def _ordinary_scientific_prompt(task_text: str, config: V06RunConfig) -> str:
    return (
        f"{task_text}\n\n"
        "You are conducting research-stage technical diligence on a locked anti-TNF "
        "response predictor. Work in the isolated Linux workspace at /workspace. "
        "Use the supplied tools to inspect evidence, run quantitative checks, and "
        "write the ten requested artifacts. Alternative scientifically defensible "
        "methods are allowed. Preserve uncertainty and stop or abstain when the "
        "evidence cannot support advancement. Complete the prospective commitment "
        "before validation reveal, then select the smallest decision-relevant "
        "follow-up before the final report.\n\n"
        "The network is disabled and provider credentials are unavailable inside the "
        "workspace. Do not fabricate tool outcomes or evidence.\n\n"
        f"You have at most {config.maximum_turns} assistant turns, "
        f"{config.maximum_total_completion_tokens} total completion tokens, and "
        f"{config.wall_clock_timeout_seconds} seconds. Reserve time to submit."
    )


def run_v06_episode(
    project_root: Path,
    config: V06RunConfig,
    *,
    openrouter_key: str,
) -> V06RunArtifacts:
    """Execute and grade one development episode; never accept held-out or Astra."""

    import verifiers as vf
    from datasets import Dataset

    root = project_root.resolve()
    panel = json.loads(
        (root / "configs/hard_suite_v06_model_panel.json").read_text(encoding="utf-8")
    )
    execution = json.loads(
        (root / "configs/hard_suite_v06_execution.json").read_text(encoding="utf-8")
    )
    if (
        panel.get("freeze_authorized") is not True
        or panel.get("scientific_execution_authorized") is not True
        or execution.get("scientific_execution_authorized") is not True
    ):
        raise ConfigurationError("v0.6 scientific runner is not authorized")
    read_v06_freeze_manifest(root)
    adapters = load_provider_adapters(root)
    if config.model_id not in adapters:
        raise ConfigurationError(f"Model is absent from compatible v0.6 panel: {config.model_id}")
    adapter = adapters[config.model_id]
    run_root = root / "build" / "hard_suite_v06_runs" / _slug(config.run_id)
    if run_root.exists():
        raise ConfigurationError(f"v0.6 run directory already exists: {run_root}")
    run_root.mkdir(parents=True)
    package = V06Builder(root).build(
        config.scenario_id,
        output_root=run_root,
        partition="development",
    )
    core = V06Environment(package)
    docker: DockerWorkspace | None = None
    ledger_path = run_root / "request_ledger.json"
    ledger = RequestLedger(ledger_path, adapter)
    task_text = (package.workspace_root / "TASK.md").read_text(encoding="utf-8")
    prompt = [
        {
            "role": "user",
            "content": (
                "Evaluate the locked predictor in /workspace and produce the complete "
                "evidence-chain diligence package. Begin with the intended-use and "
                "data-room evidence."
            ),
        }
    ]
    generated: dict[str, Any]
    client: AuditedOpenRouterClient | None = None
    isolation: dict[str, Any] = {}
    rollout_exception: dict[str, Any] | None = None
    try:
        docker = DockerWorkspace(
            workspace_root=package.workspace_root,
            container_name=f"uc-hard6-{_slug(config.run_id, limit=47)}",
            image=config.docker_image,
        )
        docker.start()
        isolation = docker.security_snapshot()
        if not _isolation_passed(isolation):
            raise DockerRuntimeError("Docker isolation preflight failed closed")
        environment = _paced_tool_environment(
            vf,
            minimum_interval_seconds=config.minimum_request_interval_seconds,
            dataset=Dataset.from_list([{"prompt": prompt, "answer": ""}]),
            tools=[
                *docker.functions(),
                core.commit_validation_plan,
                core.reveal_validation,
                core.request_followup,
                core.submit_diligence,
            ],
            system_prompt=_ordinary_scientific_prompt(task_text, config),
            max_turns=config.maximum_turns,
            timeout_seconds=config.wall_clock_timeout_seconds,
            stop_errors=[DockerRuntimeError],
            score_rollouts=False,
            env_id="uc-bench-hard-suite-v0-6",
        )
        environment.set_max_total_completion_tokens(config.maximum_total_completion_tokens)
        client_config = vf.ClientConfig(
            client_type="openai_chat_completions",
            api_key_var="OPENROUTER_API_KEY",
            api_base_url=OPENROUTER_BASE_URL,
            timeout=180.0,
            connect_timeout=10.0,
            max_connections=2,
            max_keepalive_connections=1,
            max_retries=0,
            extra_headers={"X-OpenRouter-Title": "UC-Bench v0.6 scientific pilot"},
        )
        client = AuditedOpenRouterClient(client_config, adapter, ledger)
        with _temporary_environment("OPENROUTER_API_KEY", openrouter_key):
            generated = _resolve_generated(
                environment.evaluate(
                    client=client,
                    model=config.model_id,
                    sampling_args=adapter.sampling_args(
                        maximum_completion_tokens=(
                            config.maximum_completion_tokens_per_turn
                        )
                    ),
                    num_examples=1,
                    rollouts_per_example=1,
                    max_concurrent=1,
                    save_results=False,
                    independent_scoring=True,
                    max_retries=0,
                )
            )
    except Exception as exc:  # the classification below keeps unknowns out of science
        rollout_exception = {
            "type": type(exc).__name__,
            "message": str(exc),
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
    classification = classify_execution(
        rollout_error=rollout_error,
        completion=completion,
        submitted=core.submitted,
        request_records=ledger.records,
    )
    commitment_immutable = _commitment_intact(core)
    diagnostic = grade_v06(
        root,
        package,
        selected_resource=core.selected_resource,
        commitment_immutable=commitment_immutable,
        completion_accepted=core.submitted and classification == "valid_episode",
    ).to_dict()
    attempt = reliability_score(
        classification,
        float(diagnostic["coverage_adjusted_scientific_score"]),
    )
    metadata = generated.get("metadata") or {}
    summary = {
        "schema_version": "0.6-run-1",
        "executed_at": datetime.now(UTC).isoformat(),
        "run_config": asdict(config),
        "model_id": config.model_id,
        "run_id": config.run_id,
        "run_directory": run_root.relative_to(root).as_posix(),
        "workspace_directory": package.workspace_root.relative_to(root).as_posix(),
        "scenario_id": package.scenario_id,
        "scenario_class": package.private_scenario["scenario_class"],
        "partition": package.partition,
        "classification": classification,
        "attempt_score": attempt,
        "scientific_score": (
            diagnostic["coverage_adjusted_scientific_score"]
            if classification == "valid_episode"
            else None
        ),
        "diagnostic_grade": diagnostic,
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
        "cumulative_reported_cost_usd": round(
            ledger.cumulative_reported_cost_usd, 8
        ),
        "package_digest": package.package_digest,
        "sealed_digest": package.sealed_digest,
        "isolation": isolation,
        "isolation_preflight_passed": _isolation_passed(isolation),
        "agent_received_provider_credentials": False,
        "agent_network_enabled": False,
        "phase_reached": core.phase,
        "commitment_recorded": bool(core.committed_snapshot),
        "commitment_immutable": commitment_immutable,
        "selected_resource_id": core.selected_resource,
        "completion_accepted": core.submitted,
    }
    summary_path = run_root / "run_summary.json"
    _write_json(summary_path, summary, secret=openrouter_key)
    _write_json(
        run_root / "hard_suite_v06_record.json",
        {
            "scenario_id": package.scenario_id,
            "partition": package.partition,
            "events": core.events,
            "phase": core.phase,
            "selected_resource": core.selected_resource,
            "committed_snapshot": core.committed_snapshot,
            "diagnostic_grade": diagnostic,
        },
        secret=openrouter_key,
    )
    _write_json(run_root / "verifiers_output.json", generated, secret=openrouter_key)
    return V06RunArtifacts(
        run_root=run_root,
        workspace_root=package.workspace_root,
        summary_path=summary_path,
        request_ledger_path=ledger_path,
        summary=summary,
    )

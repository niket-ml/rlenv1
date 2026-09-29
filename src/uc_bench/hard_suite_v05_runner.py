"""Run one v0.5 diligence workflow in the isolated coding-agent harness."""

from __future__ import annotations

import asyncio
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.docker_runtime import DEFAULT_IMAGE, DockerWorkspace
from uc_bench.errors import ConfigurationError, DockerRuntimeError
from uc_bench.hard_suite_v05 import V05Builder, V05Environment, grade_v05
from uc_bench.model_runner import (
    _isolation_passed,
    _redact_public_identifiers,
    _resolve_generated,
    _slug,
    _temporary_environment,
    _write_json,
    attempt_score,
    completion_stats,
)
from uc_bench.openrouter import OPENROUTER_BASE_URL


@dataclass(frozen=True, slots=True)
class V05RunConfig:
    model_id: str
    run_id: str
    scenario_id: str
    seed: int
    partition: str = "development"
    maximum_turns: int = 55
    maximum_completion_tokens_per_turn: int = 4_000
    maximum_total_completion_tokens: int = 75_000
    wall_clock_timeout_seconds: int = 3_600
    minimum_request_interval_seconds: float = 3.25
    docker_image: str = DEFAULT_IMAGE

    def __post_init__(self) -> None:
        if not all(value.strip() for value in (self.model_id, self.run_id, self.scenario_id)):
            raise ConfigurationError("v0.5 run identifiers must not be empty")
        if self.partition not in {"development", "heldout"}:
            raise ConfigurationError(f"Unknown v0.5 partition: {self.partition}")
        if (
            min(
                self.maximum_turns,
                self.maximum_completion_tokens_per_turn,
                self.maximum_total_completion_tokens,
                self.wall_clock_timeout_seconds,
            )
            <= 0
        ):
            raise ConfigurationError("v0.5 run budgets must be positive")
        if self.minimum_request_interval_seconds < 0:
            raise ConfigurationError("minimum request interval must not be negative")


@dataclass(frozen=True, slots=True)
class V05RunArtifacts:
    run_root: Path
    workspace_root: Path
    summary_path: Path
    summary: dict[str, Any]


class _PacedToolEnv:
    @staticmethod
    def create(vf: Any, *, minimum_interval_seconds: float, **kwargs: Any) -> Any:
        class PacedToolEnv(vf.ToolEnv):
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
                    elapsed = now - self._last_request_started_at
                    remaining = self._minimum_request_interval_seconds - elapsed
                    if remaining > 0:
                        await asyncio.sleep(remaining)
                self._last_request_started_at = time.monotonic()
                return await super().get_model_response(state, prompt, **response_kwargs)

        return PacedToolEnv(**kwargs)


def run_v05_episode(
    project_root: Path,
    config: V05RunConfig,
    *,
    openrouter_key: str,
) -> V05RunArtifacts:
    """Execute and independently grade exactly one v0.5 episode."""

    import verifiers as vf
    from datasets import Dataset

    project_root = project_root.resolve()
    run_root = project_root / "build" / "hard_suite_v05_runs" / _slug(config.run_id)
    if run_root.exists():
        raise ConfigurationError(f"v0.5 run directory already exists: {run_root}")
    run_root.mkdir(parents=True)
    package = V05Builder(project_root).build(
        config.scenario_id,
        output_root=run_root,
        partition=config.partition,
    )
    core = V05Environment(package)
    docker = DockerWorkspace(
        workspace_root=package.workspace_root,
        container_name=f"uc-hard5-{_slug(config.run_id, limit=47)}",
        image=config.docker_image,
    )
    task_text = (package.workspace_root / "TASK.md").read_text(encoding="utf-8")
    system_prompt = (
        f"{task_text}\n\n"
        "You are in an isolated Linux workspace at /workspace with no network. "
        "Use run_command and Python to inspect and analyze the case. Ordinary "
        "professional alternatives are allowed; make claims only from visible "
        "evidence. Finish only after submit_diligence succeeds.\n\n"
        f"You have at most {config.maximum_turns} assistant turns and "
        f"{config.maximum_total_completion_tokens} total completion tokens.\n"
    )
    prompt = [
        {
            "role": "user",
            "content": (
                "Complete the locked anti-TNF predictor diligence workflow in "
                "/workspace. Preserve the prospective commitment and select the "
                "smallest decision-relevant follow-up resource."
            ),
        }
    ]
    docker.start()
    try:
        isolation = docker.security_snapshot()
        if not _isolation_passed(isolation):
            raise DockerRuntimeError("Docker isolation preflight failed closed")
        environment = _PacedToolEnv.create(
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
            system_prompt=system_prompt,
            max_turns=config.maximum_turns,
            timeout_seconds=config.wall_clock_timeout_seconds,
            stop_errors=[DockerRuntimeError],
            score_rollouts=False,
            env_id="uc-bench-hard-suite-v0-5",
        )
        environment.set_max_total_completion_tokens(config.maximum_total_completion_tokens)
        client = vf.ClientConfig(
            client_type="openai_chat_completions",
            api_key_var="OPENROUTER_API_KEY",
            api_base_url=OPENROUTER_BASE_URL,
            timeout=180.0,
            connect_timeout=10.0,
            max_connections=2,
            max_keepalive_connections=1,
            max_retries=2,
            extra_headers={"X-OpenRouter-Title": "UC-Bench hard suite v0.5"},
        )
        with _temporary_environment("OPENROUTER_API_KEY", openrouter_key):
            generated = _resolve_generated(
                environment.evaluate(
                    client=client,
                    model=config.model_id,
                    sampling_args={
                        "max_tokens": config.maximum_completion_tokens_per_turn,
                        "extra_body": {"parallel_tool_calls": False},
                    },
                    num_examples=1,
                    rollouts_per_example=1,
                    max_concurrent=1,
                    save_results=False,
                    independent_scoring=True,
                    max_retries=1,
                )
            )
    finally:
        docker.stop()

    output = generated["outputs"][0]
    rollout_error = output.get("error")
    if rollout_error:
        classification = "infrastructure_failure"
    elif core.submission is None:
        classification = "agent_task_failure"
    else:
        classification = "valid_episode"
    diagnostic_grade = grade_v05(
        project_root,
        package,
        core.commitment,
        core.assessment,
        core.submission,
        selected_resource=core.selected_resource,
        commitment_immutable=core.commitment_immutable,
        assessment_immutable=core.assessment_immutable,
    ).to_dict()
    grade = diagnostic_grade if classification == "valid_episode" else None
    reliability_score = attempt_score(classification, grade)
    metadata = generated["metadata"]
    summary = {
        "schema_version": "0.5",
        "executed_at": datetime.now(UTC).isoformat(),
        "run_config": asdict(config),
        "model_id": config.model_id,
        "run_id": config.run_id,
        "run_directory": run_root.relative_to(project_root).as_posix(),
        "scenario_id": package.scenario_id,
        "scenario_class": package.private_scenario["scenario_class"],
        "partition": package.partition,
        "classification": classification,
        "attempt_score": reliability_score,
        "infrastructure_failure": bool(rollout_error),
        "rollout_error": _redact_public_identifiers(rollout_error),
        "stop_condition": output.get("stop_condition"),
        **completion_stats(output),
        "token_usage": output.get("token_usage") or metadata.get("usage"),
        "cost": metadata.get("cost"),
        "package_digest": package.package_digest,
        "sealed_digest": package.sealed_digest,
        "isolation": isolation,
        "isolation_preflight_passed": True,
        "agent_received_provider_credentials": False,
        "agent_network_enabled": False,
        "phase_reached": core.phase,
        "commitment_recorded": core.commitment is not None,
        "validation_revealed": (package.workspace_root / "revealed").is_dir(),
        "selected_resource_id": core.selected_resource,
        "followup_revealed": (package.workspace_root / "followup").is_dir(),
        "commitment_immutable": core.commitment_immutable,
        "assessment_immutable": core.assessment_immutable,
        "grade": grade,
        "diagnostic_grade": diagnostic_grade,
    }
    summary_path = run_root / "run_summary.json"
    _write_json(summary_path, summary, secret=openrouter_key)
    _write_json(
        run_root / "hard_suite_v05_record.json",
        {
            "scenario_id": package.scenario_id,
            "partition": package.partition,
            "events": core.events,
            "commitment": core.commitment,
            "assessment": core.assessment,
            "submission": core.submission,
        },
        secret=openrouter_key,
    )
    _write_json(run_root / "verifiers_output.json", generated, secret=openrouter_key)
    return V05RunArtifacts(
        run_root=run_root,
        workspace_root=package.workspace_root,
        summary_path=summary_path,
        summary=summary,
    )

"""Run one composed hard-suite task through the isolated coding-agent harness."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.docker_runtime import DEFAULT_IMAGE, DockerWorkspace
from uc_bench.errors import ConfigurationError, DockerRuntimeError
from uc_bench.hard_suite import HardSuiteBuilder, HardSuiteEnvironment, grade_hard_suite
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
class HardSuiteRunConfig:
    model_id: str
    run_id: str
    variant_id: str
    seed: int
    partition: str = "development"
    maximum_turns: int = 20
    maximum_completion_tokens_per_turn: int = 3_000
    maximum_total_completion_tokens: int = 24_000
    wall_clock_timeout_seconds: int = 1_500
    docker_image: str = DEFAULT_IMAGE

    def __post_init__(self) -> None:
        if not all(value.strip() for value in (self.model_id, self.run_id, self.variant_id)):
            raise ConfigurationError("Hard-suite run identifiers must not be empty")
        if self.partition not in {"development", "heldout", "ladder"}:
            raise ConfigurationError(f"Unknown hard-suite partition: {self.partition}")
        if (
            min(
                self.maximum_turns,
                self.maximum_completion_tokens_per_turn,
                self.maximum_total_completion_tokens,
                self.wall_clock_timeout_seconds,
            )
            <= 0
        ):
            raise ConfigurationError("Hard-suite run budgets must be positive")


@dataclass(frozen=True, slots=True)
class HardSuiteRunArtifacts:
    run_root: Path
    workspace_root: Path
    summary_path: Path
    summary: dict[str, Any]


def run_hard_suite_episode(
    project_root: Path,
    config: HardSuiteRunConfig,
    *,
    openrouter_key: str,
) -> HardSuiteRunArtifacts:
    """Execute one paid episode; callers must enforce external cost and canary gates."""

    import verifiers as vf
    from datasets import Dataset

    project_root = project_root.resolve()
    run_root = project_root / "build" / "hard_suite_runs" / _slug(config.run_id)
    if run_root.exists():
        raise ConfigurationError(f"Hard-suite run directory already exists: {run_root}")
    run_root.mkdir(parents=True)
    package = HardSuiteBuilder(project_root).build(
        config.variant_id,
        output_root=run_root,
        partition=config.partition,
    )
    core = HardSuiteEnvironment(package)
    docker = DockerWorkspace(
        workspace_root=package.workspace_root,
        container_name=f"uc-hard-{_slug(config.run_id, limit=48)}",
        image=config.docker_image,
    )
    task_text = (package.workspace_root / "TASK.md").read_text(encoding="utf-8")
    system_prompt = (
        f"{task_text}\n\n"
        "You are working in an isolated Linux workspace at /workspace. The network is "
        "disabled. Use run_command and Python for every quantitative result. Do not "
        "estimate CSV metrics by eye. Read the public schemas and task contract. Finish "
        "only after submit_hard_suite succeeds.\n\n"
        f"You have at most {config.maximum_turns} assistant turns and "
        f"{config.maximum_total_completion_tokens} total completion tokens.\n"
    )
    prompt = [
        {
            "role": "user",
            "content": (
                "Complete the diligence case in /workspace. Start by inspecting task.json, "
                "the evidence manifest, and every pre-reveal file."
            ),
        }
    ]
    docker.start()
    try:
        isolation = docker.security_snapshot()
        if not _isolation_passed(isolation):
            raise DockerRuntimeError("Docker isolation preflight failed closed")
        environment = vf.ToolEnv(
            dataset=Dataset.from_list([{"prompt": prompt, "answer": ""}]),
            tools=[
                *docker.functions(),
                core.commit_plan,
                core.reveal_evidence,
                core.submit_hard_suite,
            ],
            system_prompt=system_prompt,
            max_turns=config.maximum_turns,
            timeout_seconds=config.wall_clock_timeout_seconds,
            stop_errors=[DockerRuntimeError],
            score_rollouts=False,
            env_id="uc-bench-hard-suite-v0",
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
            extra_headers={"X-OpenRouter-Title": "UC-Bench hard suite v0"},
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
    grade = None
    if classification == "valid_episode":
        grade = grade_hard_suite(
            package.workspace_root,
            package.private_variant,
            core.commitment,
            core.submission,
            commitment_immutable=core.commitment_immutable,
        ).to_dict()
    reliability_score = attempt_score(classification, grade)
    metadata = generated["metadata"]
    summary = {
        "schema_version": "0.2",
        "executed_at": datetime.now(UTC).isoformat(),
        "run_config": asdict(config),
        "model_id": config.model_id,
        "run_id": config.run_id,
        "run_directory": run_root.relative_to(project_root).as_posix(),
        "family_id": package.family_id,
        "variant_id": package.variant_id,
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
        "commitment_recorded": core.commitment is not None,
        "evidence_revealed": core.revealed,
        "commitment_immutable": core.commitment_immutable,
        "grade": grade,
    }
    summary_path = run_root / "run_summary.json"
    _write_json(summary_path, summary, secret=openrouter_key)
    _write_json(
        run_root / "hard_suite_record.json",
        {
            "family_id": package.family_id,
            "variant_id": package.variant_id,
            "partition": package.partition,
            "commitment": core.commitment,
            "submission": core.submission,
        },
        secret=openrouter_key,
    )
    _write_json(run_root / "verifiers_output.json", generated, secret=openrouter_key)
    return HardSuiteRunArtifacts(
        run_root=run_root,
        workspace_root=package.workspace_root,
        summary_path=summary_path,
        summary=summary,
    )

"""Run one short diagnostic packet through the isolated agent harness."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.diagnostic_packets import (
    DiagnosticPacketBuilder,
    DiagnosticPacketEnvironment,
    grade_diagnostic_packet,
    load_packet_scenario,
)
from uc_bench.docker_runtime import DEFAULT_IMAGE, DockerWorkspace
from uc_bench.errors import ConfigurationError, DockerRuntimeError
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
class DiagnosticPacketRunConfig:
    model_id: str
    run_id: str
    task_id: str
    scenario_id: str
    seed: int
    maximum_turns: int = 8
    maximum_completion_tokens_per_turn: int = 2_000
    maximum_total_completion_tokens: int = 8_000
    wall_clock_timeout_seconds: int = 600
    docker_image: str = DEFAULT_IMAGE
    condition: str = "base"

    def __post_init__(self) -> None:
        if not all(
            value.strip() for value in (self.model_id, self.run_id, self.task_id, self.scenario_id)
        ):
            raise ConfigurationError("Packet run identifiers must not be empty")
        if (
            min(
                self.maximum_turns,
                self.maximum_completion_tokens_per_turn,
                self.maximum_total_completion_tokens,
                self.wall_clock_timeout_seconds,
            )
            <= 0
        ):
            raise ConfigurationError("Packet run budgets must be positive")
        if self.condition not in {"base", "expert_playbook"}:
            raise ConfigurationError(f"Unsupported packet condition: {self.condition}")


@dataclass(frozen=True, slots=True)
class DiagnosticPacketRunArtifacts:
    run_root: Path
    workspace_root: Path
    summary_path: Path
    summary: dict[str, Any]


def run_diagnostic_packet_episode(
    project_root: Path,
    config: DiagnosticPacketRunConfig,
    *,
    openrouter_key: str,
) -> DiagnosticPacketRunArtifacts:
    """Execute and grade one packet without exposing its private rubric."""

    import verifiers as vf
    from datasets import Dataset

    project_root = project_root.resolve()
    run_root = project_root / "build" / "packet_runs" / _slug(config.run_id)
    if run_root.exists():
        raise ConfigurationError(f"Packet run directory already exists: {run_root}")
    run_root.mkdir(parents=True)
    package = DiagnosticPacketBuilder(project_root).build(
        config.task_id,
        config.scenario_id,
        output_root=run_root,
        expert_playbook=config.condition == "expert_playbook",
    )
    scenario = load_packet_scenario(project_root, config.task_id, config.scenario_id)
    core = DiagnosticPacketEnvironment(package.workspace_root)
    docker = DockerWorkspace(
        workspace_root=package.workspace_root,
        container_name=f"uc-packet-{_slug(config.run_id, limit=48)}",
        image=config.docker_image,
    )
    task_text = (package.workspace_root / "TASK.md").read_text(encoding="utf-8")
    system_prompt = (
        f"{task_text}\n\n"
        "You are working in an isolated Linux workspace at /workspace. The network is "
        "disabled. Inspect the supplied files, produce the required JSON artifact, and "
        "finish only after submit_packet succeeds. Do not build a predictor or invent "
        "evidence.\n\n"
        f"You have at most {config.maximum_turns} assistant turns and "
        f"{config.maximum_total_completion_tokens} total completion tokens.\n"
    )
    if config.condition == "expert_playbook":
        system_prompt += (
            "\nAn expert procedural scaffold is available at /workspace/EXPERT_PLAYBOOK.md. "
            "Read and apply it before beginning the task.\n"
        )
    prompt = [
        {
            "role": "user",
            "content": (
                "Review the evidence packet in /workspace, write the required final "
                "submission, and call submit_packet."
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
            tools=[*docker.functions(), core.submit_packet],
            system_prompt=system_prompt,
            max_turns=config.maximum_turns,
            timeout_seconds=config.wall_clock_timeout_seconds,
            stop_errors=[DockerRuntimeError],
            score_rollouts=False,
            env_id="uc-bench-diagnostic-packet-v0",
        )
        environment.set_max_total_completion_tokens(config.maximum_total_completion_tokens)
        client = vf.ClientConfig(
            client_type="openai_chat_completions",
            api_key_var="OPENROUTER_API_KEY",
            api_base_url=OPENROUTER_BASE_URL,
            timeout=180.0,
            connect_timeout=10.0,
            max_connections=4,
            max_keepalive_connections=2,
            max_retries=2,
            extra_headers={"X-OpenRouter-Title": "UC-Bench diagnostic v0"},
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
    grade = grade_diagnostic_packet(core.submission, scenario["rubric"]).to_dict()
    reliability_score = attempt_score(
        classification,
        grade if classification == "valid_episode" else None,
    )
    metadata = generated["metadata"]
    summary = {
        "schema_version": "0.1",
        "executed_at": datetime.now(UTC).isoformat(),
        "run_config": asdict(config),
        "model_id": config.model_id,
        "run_id": config.run_id,
        "run_directory": run_root.relative_to(project_root).as_posix(),
        "task_id": config.task_id,
        "scenario_id": config.scenario_id,
        "classification": classification,
        "attempt_score": reliability_score,
        "infrastructure_failure": bool(rollout_error),
        "rollout_error": _redact_public_identifiers(rollout_error),
        "stop_condition": output.get("stop_condition"),
        **completion_stats(output),
        "token_usage": output.get("token_usage") or metadata.get("usage"),
        "cost": metadata.get("cost"),
        "package_digest": package.package_digest,
        "isolation": isolation,
        "isolation_preflight_passed": True,
        "agent_received_provider_credentials": False,
        "agent_network_enabled": False,
        "grade": grade if classification != "infrastructure_failure" else None,
    }
    summary_path = run_root / "run_summary.json"
    _write_json(summary_path, summary, secret=openrouter_key)
    _write_json(
        run_root / "packet_record.json",
        {
            "task_id": config.task_id,
            "scenario_id": config.scenario_id,
            "submission": core.submission,
        },
        secret=openrouter_key,
    )
    _write_json(run_root / "verifiers_output.json", generated, secret=openrouter_key)
    return DiagnosticPacketRunArtifacts(
        run_root=run_root,
        workspace_root=package.workspace_root,
        summary_path=summary_path,
        summary=summary,
    )

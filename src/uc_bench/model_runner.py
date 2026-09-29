"""Run one UC-Bench episode through Verifiers and an isolated Docker workspace."""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.docker_runtime import DEFAULT_IMAGE, DockerWorkspace
from uc_bench.environment import DiligenceEnvironment
from uc_bench.errors import ConfigurationError, DockerRuntimeError
from uc_bench.grading import ScenarioRubric, grade_episode
from uc_bench.openrouter import OPENROUTER_BASE_URL, fetch_key_status
from uc_bench.packaging import StartStateBuilder
from uc_bench.runtime_adapter import DomainToolAdapter
from uc_bench.state import EpisodeState

_SAFE_SLUG = re.compile(r"[^a-zA-Z0-9_.-]+")
_OPENROUTER_USER_ID = re.compile(r"user_[A-Za-z0-9]+")


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError(f"Expected JSON object: {path}")
    return value


def _write_json(path: Path, value: Any, *, secret: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(value, indent=2, sort_keys=True, default=_json_default) + "\n"
    if secret:
        rendered = rendered.replace(secret, "<redacted>")
    rendered = rendered.replace("<redacted_user_id>", "<provider_account_redacted>")
    rendered = _OPENROUTER_USER_ID.sub("<provider_account_redacted>", rendered)
    path.write_text(rendered, encoding="utf-8")


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(exclude_none=True)
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    if hasattr(value, "__dict__"):
        return vars(value)
    return str(value)


def _redact_public_identifiers(value: Any) -> Any:
    rendered = json.dumps(value, default=_json_default)
    rendered = rendered.replace("<redacted_user_id>", "<provider_account_redacted>")
    rendered = _OPENROUTER_USER_ID.sub("<provider_account_redacted>", rendered)
    return json.loads(rendered)


def completion_stats(output: dict[str, Any]) -> dict[str, Any]:
    """Count serialized model turns and tool calls without private Verifiers state."""

    completion = output.get("completion") or []
    assistant_turns = 0
    tool_counts: dict[str, int] = {}
    for message in completion:
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        assistant_turns += 1
        for raw_call in message.get("tool_calls") or []:
            call = raw_call
            if isinstance(raw_call, str):
                try:
                    call = json.loads(raw_call)
                except json.JSONDecodeError:
                    continue
            if not isinstance(call, dict):
                continue
            function = call.get("function") or {}
            name = call.get("name")
            if name is None and isinstance(function, dict):
                name = function.get("name")
            if isinstance(name, str) and name:
                tool_counts[name] = tool_counts.get(name, 0) + 1
    return {
        "turn_count": assistant_turns,
        "tool_call_count": sum(tool_counts.values()),
        "tool_call_counts": dict(sorted(tool_counts.items())),
    }


def attempt_score(classification: str, grade: dict[str, Any] | None) -> float | None:
    """Return the reliability-inclusive score used for model comparisons.

    Infrastructure failures are excluded and therefore have no score. A model
    that receives a usable episode but fails to submit has failed the task and
    scores zero. Submitted episodes retain the deterministic grader score,
    including its contract and decision ceilings.
    """

    if classification == "infrastructure_failure":
        return None
    if classification == "agent_task_failure":
        return 0.0
    if grade is None:
        raise ConfigurationError(
            f"Classification {classification!r} requires a deterministic grade"
        )
    return float(grade["score"])


def _slug(value: str, *, limit: int = 70) -> str:
    normalized = _SAFE_SLUG.sub("-", value).strip("-.")
    if not normalized:
        raise ConfigurationError("Cannot create a safe run identifier")
    return normalized[:limit]


def _resolve_generated(value: Any) -> Any:
    """Support Verifiers releases whose evaluate method is async or synchronous."""

    return asyncio.run(value) if inspect.isawaitable(value) else value


def load_openrouter_key(project_root: Path) -> str:
    """Load only the required local secret without exporting the whole .env file."""

    try:
        from dotenv import dotenv_values
    except ImportError as exc:
        raise ConfigurationError(
            "python-dotenv is required for local model runs; reinstall the rl extra"
        ) from exc
    values = dotenv_values(project_root / ".env")
    key = str(values.get("OPENROUTER_API_KEY") or "").strip()
    if not key or key == "PASTE_YOUR_NEW_OPENROUTER_KEY_HERE":
        raise ConfigurationError("OPENROUTER_API_KEY is not configured in .env")
    if not key.startswith("sk-or-v1-"):
        raise ConfigurationError("OPENROUTER_API_KEY has an unexpected format")
    return key


@contextmanager
def _temporary_environment(name: str, value: str) -> Iterator[None]:
    previous = os.environ.get(name)
    os.environ[name] = value
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = previous


@dataclass(frozen=True, slots=True)
class ModelRunConfig:
    model_id: str
    run_id: str
    condition: str = "full_data"
    scenario_id: str = "authentic_weak_evidence"
    seed: int = 0
    temperature: float | None = None
    maximum_turns: int = 40
    maximum_completion_tokens_per_turn: int = 4_000
    maximum_total_completion_tokens: int = 40_000
    wall_clock_timeout_seconds: int = 1_800
    docker_image: str = DEFAULT_IMAGE

    def __post_init__(self) -> None:
        if not self.model_id.strip() or not self.run_id.strip():
            raise ConfigurationError("model_id and run_id are required")
        if self.condition not in {"full_data", "data_withheld"}:
            raise ConfigurationError(f"Unsupported condition: {self.condition}")
        if self.temperature is not None and not 0.0 <= self.temperature <= 2.0:
            raise ConfigurationError("temperature must be within [0, 2]")
        if min(
            self.maximum_turns,
            self.maximum_completion_tokens_per_turn,
            self.maximum_total_completion_tokens,
            self.wall_clock_timeout_seconds,
        ) <= 0:
            raise ConfigurationError("Run budgets must be positive")


@dataclass(frozen=True, slots=True)
class ModelRunArtifacts:
    run_root: Path
    workspace_root: Path
    summary_path: Path
    episode_record_path: Path
    verifiers_output_path: Path
    summary: dict[str, Any]


def _isolation_passed(snapshot: dict[str, Any]) -> bool:
    return (
        snapshot.get("network_mode") == "none"
        and snapshot.get("read_only_rootfs") is True
        and snapshot.get("privileged") is False
        and snapshot.get("workspace_is_only_bind_mount") is True
        and snapshot.get("credential_environment_present") is False
    )


def run_model_episode(
    project_root: Path,
    config: ModelRunConfig,
    *,
    openrouter_key: str,
) -> ModelRunArtifacts:
    """Execute exactly one paid model trajectory and preserve its complete audit record."""

    import verifiers as vf
    from datasets import Dataset

    project_root = project_root.resolve()
    run_root = project_root / "build" / "model_runs" / _slug(config.run_id)
    if run_root.exists():
        raise ConfigurationError(f"Run directory already exists: {run_root}")
    run_root.mkdir(parents=True)
    package = StartStateBuilder(project_root).build(
        config.condition,
        output_root=run_root,
    )
    workspace = package.workspace_root
    task_config = _read_json(
        project_root / "configs" / "tasks" / "uc_biomarker_diligence_v0.json"
    )
    evaluation_config = task_config["evaluation"]
    analyst_answers = _read_json(workspace / "analyst_answers.json")
    core = DiligenceEnvironment(
        workspace_root=workspace,
        sealed_expression_path=(
            project_root
            / "data"
            / "processed"
            / "sealed"
            / "GSE92415_gene_expression.csv.gz"
        ),
        sealed_labels_path=project_root / "grader_private" / "data" / "gse92415_labels.csv",
        episode=EpisodeState(
            config.run_id,
            "uc_biomarker_diligence_v0",
            config.condition,
            config.scenario_id,
            config.seed,
        ),
        bootstrap_resamples=int(evaluation_config["bootstrap_resamples"]),
        permutation_count=int(evaluation_config["permutation_count"]),
        evaluation_seed=config.seed,
        analyst_answers={str(key): str(value) for key, value in analyst_answers.items()},
        task_schema_root=(
            project_root / "tasks" / "uc_biomarker_diligence_v0" / "schemas"
        ),
    )
    domain = DomainToolAdapter(core)
    container_name = f"uc-bench-{_slug(config.run_id, limit=48)}"
    docker = DockerWorkspace(
        workspace_root=workspace,
        container_name=container_name,
        image=config.docker_image,
    )

    task_text = (workspace / "TASK.md").read_text(encoding="utf-8")
    system_prompt = (
        f"{task_text}\n\n"
        "## Runtime instructions\n\n"
        "You are working in an isolated Linux workspace at /workspace. The network is "
        "disabled. Use the supplied workspace tools to inspect data, write analysis code, "
        "and create the required artifacts. Do not merely describe checks: execute them "
        "and record their numerical evidence. End only after successfully calling "
        "commit_analysis, reveal_validation, and submit in that order. Tool errors are "
        "evidence to diagnose; do not fabricate a successful call.\n\n"
        f"## Operational budget\n\nYou have at most {config.maximum_turns} assistant "
        f"turns and {config.maximum_total_completion_tokens} total completion tokens. "
        "Reserve enough turns to write and validate artifacts, commit, reveal, write the "
        "final decision, and submit.\n"
    )
    prompt = [
        {
            "role": "user",
            "content": (
                "Complete the anti-TNF biomarker diligence task in /workspace. Begin by "
                "inspecting the workspace and task schemas."
            ),
        }
    ]

    key_status_before = fetch_key_status(openrouter_key)
    docker.start()
    try:
        isolation = docker.security_snapshot()
        if not _isolation_passed(isolation):
            raise DockerRuntimeError("Docker isolation preflight failed closed")
        tools = [*docker.functions(), *domain.functions()]
        environment = vf.ToolEnv(
            dataset=Dataset.from_list([{"prompt": prompt, "answer": ""}]),
            tools=tools,
            system_prompt=system_prompt,
            max_turns=config.maximum_turns,
            timeout_seconds=config.wall_clock_timeout_seconds,
            stop_errors=[DockerRuntimeError],
            score_rollouts=False,
            env_id="uc-bench-v0",
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
            extra_headers={"X-OpenRouter-Title": "UC-Bench v0"},
        )
        sampling_args: dict[str, Any] = {
            "max_tokens": config.maximum_completion_tokens_per_turn,
            "extra_body": {"parallel_tool_calls": False},
        }
        if config.temperature is not None:
            sampling_args["temperature"] = config.temperature
        with _temporary_environment("OPENROUTER_API_KEY", openrouter_key):
            generated = _resolve_generated(
                environment.evaluate(
                    client=client,
                    model=config.model_id,
                    sampling_args=sampling_args,
                    num_examples=1,
                    rollouts_per_example=1,
                    max_concurrent=1,
                    save_results=False,
                    independent_scoring=True,
                    max_retries=1,
                )
            )
        balance_check_after_error = None
        try:
            key_status_after = fetch_key_status(openrouter_key)
        except ConfigurationError as exc:
            # A trajectory is the expensive, scientifically relevant result. A
            # transient failure of the optional post-run billing lookup must not
            # discard it or change its task classification.
            key_status_after = None
            balance_check_after_error = str(exc)
    finally:
        docker.stop()

    record = core.record()
    record["start_state"] = {
        "condition": package.condition,
        "file_count": package.file_count,
        "package_digest": package.package_digest,
    }
    reward_config = _read_json(project_root / "configs" / "reward_weights.json")
    grade = None
    if record.get("phase") == "submitted":
        rubric = ScenarioRubric.from_dict(
            _read_json(project_root / "configs" / "authentic_rubric.json")
        )
        grade = grade_episode(
            record,
            workspace_root=workspace,
            rubric=rubric,
            weights=reward_config["weights"],
            soft_contract_failure_ceiling=float(
                reward_config["soft_contract_failure_ceiling"]
            ),
            incorrect_terminal_decision_ceiling=float(
                reward_config["incorrect_terminal_decision_ceiling"]
            ),
        ).to_dict()

    output = generated["outputs"][0]
    interaction = completion_stats(output)
    rollout_error = output.get("error")
    submitted = record.get("phase") == "submitted"
    if rollout_error:
        classification = "infrastructure_failure"
    elif submitted and grade is not None and grade["contract_valid"]:
        classification = "valid_episode"
    elif submitted:
        classification = "submitted_contract_failure"
    else:
        classification = "agent_task_failure"
    reliability_score = attempt_score(classification, grade)
    metadata = generated["metadata"]
    key_usage_delta = (
        max(0.0, key_status_after.usage_usd - key_status_before.usage_usd)
        if key_status_after is not None
        else None
    )
    summary = {
        "schema_version": "0.1",
        "executed_at": datetime.now(UTC).isoformat(),
        "run_config": asdict(config),
        "model_id": config.model_id,
        "run_id": config.run_id,
        "condition": config.condition,
        "scenario_id": config.scenario_id,
        "seed": config.seed,
        "phase": record.get("phase"),
        "classification": classification,
        "attempt_score": reliability_score,
        "infrastructure_failure": bool(rollout_error),
        "rollout_error": _redact_public_identifiers(rollout_error),
        "stop_condition": output.get("stop_condition"),
        **interaction,
        "token_usage": output.get("token_usage") or metadata.get("usage"),
        "cost": metadata.get("cost"),
        "openrouter_key_usage_before_usd": key_status_before.usage_usd,
        "openrouter_key_usage_after_usd": (
            key_status_after.usage_usd if key_status_after is not None else None
        ),
        "openrouter_cost_delta_usd": key_usage_delta,
        "openrouter_balance_check_after_error": balance_check_after_error,
        "package_digest": package.package_digest,
        "isolation": isolation,
        "isolation_preflight_passed": True,
        "agent_received_provider_credentials": False,
        "agent_network_enabled": False,
        "grade": grade,
    }
    summary_path = run_root / "run_summary.json"
    record_path = run_root / "episode_record.json"
    verifiers_path = run_root / "verifiers_output.json"
    _write_json(summary_path, summary, secret=openrouter_key)
    _write_json(record_path, record, secret=openrouter_key)
    _write_json(verifiers_path, generated, secret=openrouter_key)
    return ModelRunArtifacts(
        run_root=run_root,
        workspace_root=workspace,
        summary_path=summary_path,
        episode_record_path=record_path,
        verifiers_output_path=verifiers_path,
        summary=summary,
    )

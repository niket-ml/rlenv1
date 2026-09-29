"""Infrastructure-only v0.7.1 runner over the immutable v0.7 science."""

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
from uc_bench.v07_environment import V07Environment
from uc_bench.v07_grader import grade_submission
from uc_bench.v07_provider import load_v07_provider_adapters
from uc_bench.v07_runner import (
    V07RunArtifacts,
    V07RunConfig,
    _classification,
    _paced_environment,
    v07_scientific_system_prompt,
    v07_tool_functions,
)
from uc_bench.v071_auth import (
    V071RequestLedger,
    build_v071_scientific_client,
    credential_locations,
    mapping_contains_credential,
    redact_exception_message,
)

V071RunConfig = V07RunConfig
V071RunArtifacts = V07RunArtifacts


def v071_reported_scores(
    classification: str, grade: dict[str, Any]
) -> tuple[float | None, float | None]:
    """Separate scientific and reliability scoring from infrastructure failures."""

    infrastructure_classes = {
        "infrastructure_failure",
        "provider_adapter_failure",
        "provider_policy_refusal",
        "unknown_harness_failure",
    }
    if classification == "valid_episode":
        score = float(grade["work_quality_score"])
        return score, score
    if classification in infrastructure_classes:
        return None, None
    return None, 0.0


def run_v071_episode(
    project_root: Path,
    config: V071RunConfig,
    *,
    openrouter_key: str,
    authorization_digest: str,
) -> V071RunArtifacts:
    """Run one v0.7.1 episode using unmodified v0.7 scientific components."""

    import verifiers as vf
    from datasets import Dataset

    from uc_bench.v071_freeze import read_v071_freeze_manifest

    root = project_root.resolve()
    freeze = read_v071_freeze_manifest(root)
    if authorization_digest != freeze["hash_set_digest"]:
        raise ConfigurationError("v0.7.1 execution lacks the exact freeze authorization")
    adapters = load_v07_provider_adapters(root)
    if config.model_id not in adapters:
        raise ConfigurationError("Model is absent from the frozen v0.7 panel")
    adapter = adapters[config.model_id]
    run_root = root / "build/hard_suite_v071_runs" / _slug(config.run_id)
    if run_root.exists():
        raise ConfigurationError(f"v0.7.1 run already exists: {run_root}")
    run_root.mkdir(parents=True)
    workspace = run_root / "workspace"
    core = V07Environment(
        root,
        config.case_id,
        workspace,
        mechanism=config.mechanism,
        maximum_tool_calls=80,
    )
    docker: DockerWorkspace | None = None
    ledger_path = run_root / "request_ledger.json"
    ledger = V071RequestLedger(ledger_path, adapter, secret=openrouter_key)
    task_text = (workspace / "README.md").read_text(encoding="utf-8")
    generated: dict[str, Any]
    client: Any = None
    isolation: dict[str, Any] = {}
    rollout_exception: dict[str, Any] | None = None
    system_prompt = v07_scientific_system_prompt(task_text, config)
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
    try:
        docker = DockerWorkspace(
            workspace_root=workspace,
            container_name=f"uc-v071-{_slug(config.run_id, limit=52)}",
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
            tools=v07_tool_functions(docker, core),
            system_prompt=system_prompt,
            max_turns=config.maximum_turns,
            timeout_seconds=config.wall_clock_timeout_seconds,
            stop_errors=[DockerRuntimeError],
            score_rollouts=False,
            env_id="uc-bench-v0-7-1-development",
        )
        environment.set_max_total_completion_tokens(config.maximum_total_completion_tokens)
        # This is the sole production repair: credentials and URL are explicit,
        # and construction occurs only after the validated key is available.
        client = build_v071_scientific_client(
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
    submission = core.export_submission()
    grade = grade_submission(
        root,
        config.case_id,
        submission,
        mechanism=config.mechanism,
    ).to_dict()
    scientific_score, reliability = v071_reported_scores(classification, grade)
    metadata = generated.get("metadata") or {}
    integrity = core.integrity_status()
    summary = {
        "schema_version": "0.7.1-run-1",
        "executed_at": datetime.now(UTC).isoformat(),
        "run_config": asdict(config),
        "run_id": config.run_id,
        "run_directory": run_root.relative_to(root).as_posix(),
        "workspace_directory": workspace.relative_to(root).as_posix(),
        "model_id": config.model_id,
        "case_id": config.case_id,
        "mechanism": config.mechanism,
        "condition_id": (
            f"case_03_{config.mechanism}" if config.case_id == "case_03" else config.case_id
        ),
        "partition": config.partition,
        "classification": classification,
        "scientific_score": scientific_score,
        "reliability_score": reliability,
        "diagnostic_grade": grade,
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
        "heldout_requests": 0,
        "astra_requests": 0,
        "freeze_hash_set_digest": freeze["hash_set_digest"],
    }
    summary_path = run_root / "run_summary.json"
    _write_json(summary_path, summary, secret=openrouter_key)
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
    return V071RunArtifacts(
        run_root=run_root,
        workspace_root=workspace,
        summary_path=summary_path,
        request_ledger_path=ledger_path,
        summary=summary,
    )

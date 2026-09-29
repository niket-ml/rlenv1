"""One-episode v0.7 runner with exact routes, sealed state, and total diagnostics."""

from __future__ import annotations

import asyncio
import time
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.docker_runtime import DEFAULT_IMAGE, DockerWorkspace
from uc_bench.errors import ConfigurationError, DockerRuntimeError
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
from uc_bench.v061_provider import V061RequestLedger
from uc_bench.v062_provider import V062AuditedOpenRouterClient
from uc_bench.v07_environment import V07Environment
from uc_bench.v07_grader import grade_submission
from uc_bench.v07_provider import load_v07_provider_adapters


@dataclass(frozen=True, slots=True)
class V07RunConfig:
    model_id: str
    run_id: str
    case_id: str
    mechanism: str
    seed: int
    partition: str = "development"
    maximum_turns: int = 65
    maximum_completion_tokens_per_turn: int = 5_000
    maximum_total_completion_tokens: int = 90_000
    wall_clock_timeout_seconds: int = 4_200
    minimum_request_interval_seconds: float = 3.25
    docker_image: str = DEFAULT_IMAGE

    def __post_init__(self) -> None:
        if not all(
            value.strip() for value in (self.model_id, self.run_id, self.case_id, self.mechanism)
        ):
            raise ConfigurationError("v0.7 run identifiers must not be empty")
        if self.partition != "development":
            raise ConfigurationError("v0.7 rejects held-out partitions")
        if "astra" in self.model_id.lower() or "gpt-6" in self.model_id.lower():
            raise ConfigurationError("Astra/GPT-6 is forbidden from v0.7 development")
        if self.case_id not in {"case_01", "case_02", "case_03", "case_04"}:
            raise ConfigurationError(f"Unknown v0.7 case: {self.case_id}")
        expected = (
            {"signal_collapses", "signal_remains"}
            if self.case_id == "case_03"
            else {"default"}
        )
        if self.mechanism not in expected:
            raise ConfigurationError("Mechanism is inconsistent with the visible case")


@dataclass(frozen=True, slots=True)
class V07RunArtifacts:
    run_root: Path
    workspace_root: Path
    summary_path: Path
    request_ledger_path: Path
    summary: dict[str, Any]


def _paced_environment(vf: Any, *, minimum_interval_seconds: float, **kwargs: Any) -> Any:
    class PacedToolEnvironment(vf.ToolEnv):
        def __init__(self, **environment_kwargs: Any) -> None:
            super().__init__(**environment_kwargs)
            self._last_request_started_at: float | None = None

        async def get_model_response(self, state: Any, prompt: Any, **response_kwargs: Any) -> Any:
            now = time.monotonic()
            if self._last_request_started_at is not None:
                remaining = minimum_interval_seconds - (now - self._last_request_started_at)
                if remaining > 0:
                    await asyncio.sleep(remaining)
            self._last_request_started_at = time.monotonic()
            return await super().get_model_response(state, prompt, **response_kwargs)

    return PacedToolEnvironment(**kwargs)


def v07_tool_functions(docker: DockerWorkspace, core: V07Environment) -> list[Any]:
    """Return the exact ordered scientific tool surface used in every episode."""

    return [
        *docker.functions(),
        core.save_checkpoint,
        core.commit_validation_plan,
        core.reveal_validation,
        core.purchase_resource,
        core.submit,
    ]


def v07_scientific_system_prompt(task_text: str, config: V07RunConfig) -> str:
    """Describe professional work and public mechanics without revealing case truth."""

    return (
        f"{task_text}\n\n"
        "You are the technical-diligence lead for a locked baseline-biopsy "
        "anti-TNF response predictor. Work only from the evidence mounted at "
        "/workspace. Sponsor assertions are hypotheses, not ground truth. Any "
        "scientifically defensible patient-level method is allowed. Stop or remain "
        "conditional when evidence is inadequate.\n\n"
        "Use work/ for scripts and derived files. Do not modify supplied evidence. "
        "The checkpoints are semantic records, not formatting tests:\n"
        "- C1: intended use, eligible cohort, patient/visit analysis unit, counts, "
        "dependence/site/timing checks, material versus harmless findings, "
        "uncertainties, and evidence paths.\n"
        "- C2: call commit_validation_plan once with the prospective patient-level "
        "estimand, outcome-blind training-only preprocessing scope, uncertainty "
        "method, discrimination/calibration/utility metrics, decision rules, and at "
        "least two live hypotheses.\n"
        "- After reveal_validation, C3: independently calculate patient-level AUC "
        "with uncertainty, Brier score, calibration error, net benefit, relevant "
        "row/site sensitivities, whether patient/site structure and the commitment "
        "were honoured, whether contaminated results are eligible, and citations.\n"
        "- C4 before purchase: supported diagnosis, competing explanations, visible "
        "resource comparison and limitations, and at least two result-contingent "
        "actions. Save C4, then call purchase_resource exactly once; use resource_id "
        "'none' when no evidence is worth buying.\n"
        "- C5: independently analyse returned evidence, state initial and final "
        "decisions, belief direction, supported/unsupported/made claims, and "
        "remaining uncertainty. Then call submit.\n\n"
        "Payloads may be nested and include explanatory text. Conventional names "
        "such as analysis_unit, n_patients, diagnosed_concepts, evidence_refs, "
        "metrics, selected_resource, belief_direction, supported_claims, "
        "unsupported_claims, and claims_made make the record auditable. A correct "
        "final label without its evidence chain is not success. An error may be "
        "corrected before commitment; the plan cannot be repaired after reveal. "
        "For save_checkpoint and commit_validation_plan, pass the semantic record "
        "as a JSON-encoded object in payload_json. JSON transport mechanics are "
        "recorded separately from scientific quality.\n\n"
        "The container has scientific Python but no network or credentials. Do not "
        f"invent evidence. You have at most {config.maximum_turns} assistant turns, "
        f"{config.maximum_total_completion_tokens} total completion tokens, and "
        f"{config.wall_clock_timeout_seconds} seconds. Reserve time to purchase a "
        "resource (including none), save C5, and submit."
    )


def _classification(
    *,
    rollout_error: Any,
    completion: list[Any],
    submitted: bool,
    records: list[dict[str, Any]],
) -> str:
    from uc_bench.v06_provider import classify_execution

    return classify_execution(
        rollout_error=rollout_error,
        completion=completion,
        submitted=submitted,
        request_records=records,
    )


def run_v07_episode(
    project_root: Path,
    config: V07RunConfig,
    *,
    openrouter_key: str,
    authorization_digest: str,
) -> V07RunArtifacts:
    """Run and checkpoint one frozen development episode with no scientific retry."""

    import verifiers as vf
    from datasets import Dataset
    from verifiers.legacy.clients.client import ClientConfig

    from uc_bench.v07_freeze import read_v07_freeze_manifest

    root = project_root.resolve()
    freeze = read_v07_freeze_manifest(root)
    if authorization_digest != freeze["hash_set_digest"]:
        raise ConfigurationError("v0.7 execution lacks the exact freeze authorization")
    adapters = load_v07_provider_adapters(root)
    if config.model_id not in adapters:
        raise ConfigurationError("Model is absent from the frozen v0.7 panel")
    adapter = adapters[config.model_id]
    run_root = root / "build/hard_suite_v07_runs" / _slug(config.run_id)
    if run_root.exists():
        raise ConfigurationError(f"v0.7 run already exists: {run_root}")
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
    ledger = V061RequestLedger(ledger_path, adapter)
    task_text = (workspace / "README.md").read_text(encoding="utf-8")
    generated: dict[str, Any]
    client: V062AuditedOpenRouterClient | None = None
    isolation: dict[str, Any] = {}
    rollout_exception: dict[str, Any] | None = None
    try:
        docker = DockerWorkspace(
            workspace_root=workspace,
            container_name=f"uc-v07-{_slug(config.run_id, limit=53)}",
            image=config.docker_image,
        )
        docker.start()
        isolation = docker.security_snapshot()
        if not _isolation_passed(isolation):
            raise DockerRuntimeError("Docker isolation preflight failed closed")
        environment = _paced_environment(
            vf,
            minimum_interval_seconds=config.minimum_request_interval_seconds,
            dataset=Dataset.from_list(
                [
                    {
                        "prompt": [
                            {
                                "role": "user",
                                "content": (
                                    "Begin the evidence-chain diligence investigation "
                                    "in /workspace."
                                ),
                            }
                        ],
                        "answer": "",
                    }
                ]
            ),
            tools=v07_tool_functions(docker, core),
            system_prompt=v07_scientific_system_prompt(task_text, config),
            max_turns=config.maximum_turns,
            timeout_seconds=config.wall_clock_timeout_seconds,
            stop_errors=[DockerRuntimeError],
            score_rollouts=False,
            env_id="uc-bench-v0-7-development",
        )
        environment.set_max_total_completion_tokens(config.maximum_total_completion_tokens)
        client_config = ClientConfig(
            client_type="openai_chat_completions",
            api_key_var="OPENROUTER_API_KEY",
            api_base_url=OPENROUTER_BASE_URL,
            timeout=180.0,
            connect_timeout=10.0,
            max_connections=2,
            max_keepalive_connections=1,
            max_retries=0,
            extra_headers={"X-OpenRouter-Title": "UC-Bench v0.7 development"},
        )
        client = V062AuditedOpenRouterClient(client_config, adapter, ledger)
        with _temporary_environment("OPENROUTER_API_KEY", openrouter_key):
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
        rollout_exception = {"type": type(exc).__name__, "message": str(exc)[:2000]}
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
    infrastructure_classes = {
        "infrastructure_failure",
        "provider_adapter_failure",
        "provider_policy_refusal",
        "unknown_harness_failure",
    }
    reliability = grade["work_quality_score"] if classification == "valid_episode" else (
        None if classification in infrastructure_classes else 0.0
    )
    metadata = generated.get("metadata") or {}
    integrity = core.integrity_status()
    summary = {
        "schema_version": "0.7-run-1",
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
        "scientific_score": (
            grade["work_quality_score"] if classification == "valid_episode" else None
        ),
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
    return V07RunArtifacts(
        run_root=run_root,
        workspace_root=workspace,
        summary_path=summary_path,
        request_ledger_path=ledger_path,
        summary=summary,
    )

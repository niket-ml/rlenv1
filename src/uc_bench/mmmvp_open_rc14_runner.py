"""Production runner for the contract-only RC1.4 successor."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.durable_runner import (
    DurableAuditedOpenRouterClient,
    DurableRequestLedger,
)
from uc_bench.durable_trajectory import TrajectoryPersistenceError, _message_rows
from uc_bench.errors import ConfigurationError, DockerRuntimeError
from uc_bench.mmmvp_open_freeze import read_open_mmmvp_freeze
from uc_bench.mmmvp_open_rc12_environment import (
    RC12DockerWorkspace,
    rc12_isolation_passed,
)
from uc_bench.mmmvp_open_rc13_trajectory import (
    ACTIVE_TOOL_STATUS,
    RC13DurableTrajectoryStore,
    rc13_durable_tool_functions,
    rc13_tool_call_context,
    rc13_trajectory_replay_check,
)
from uc_bench.mmmvp_open_rc14_environment import RC14OpenMMMVPEnvironment
from uc_bench.mmmvp_open_rc14_freeze import read_rc14_release_freeze
from uc_bench.mmmvp_open_runner import (
    OpenRunArtifacts,
    OpenRunConfig,
    _assert_surface_matches_shared_request,
    _grader_consistency,
    open_condition_id,
    production_request,
)
from uc_bench.mmmvp_open_verifier import verify_open_submission
from uc_bench.model_runner import (
    _redact_public_identifiers,
    _resolve_generated,
    _slug,
    _write_json,
    completion_stats,
)
from uc_bench.openrouter import OPENROUTER_BASE_URL
from uc_bench.v06_provider import ProviderIdentityError, _as_dict, _response_record
from uc_bench.v061_provider import (
    exact_request_contract,
    post_chat_completion_with_routed_experts_sidecar,
)
from uc_bench.v07_runner import _classification
from uc_bench.v071_auth import (
    build_v071_scientific_client,
    credential_locations,
    mapping_contains_credential,
    redact_exception_message,
)

SCIENTIFIC_FREEZE_DIGEST = "466441682b04175432329b41adcfd735cdea66f860d66f046dfae195c91e701c"


def _known_tool_names(tools: Any) -> frozenset[str]:
    names: set[str] = set()
    for raw in tools or []:
        row = _as_dict(raw)
        function = row.get("function") if isinstance(row, Mapping) else None
        if isinstance(function, Mapping) and function.get("name"):
            names.add(str(function["name"]))
        elif isinstance(row, Mapping) and row.get("name"):
            names.add(str(row["name"]))
    return frozenset(names)


class RC14DurableTrajectoryStore(RC13DurableTrajectoryStore):
    """Add a redacted raw-receive boundary without changing RC1.3."""

    def record_received_response(
        self,
        *,
        prompt: Any,
        response: Any,
        ledger: Any,
    ) -> dict[str, Any]:
        event = {
            "request_index": len(self._provider_exchanges),  # noqa: SLF001
            "prompt": _message_rows(prompt),
            "raw_response": _as_dict(response),
            "persistence_precedes_parsing": True,
            "persistence_precedes_identity_adjudication": True,
        }
        return self._persist("raw_model_response_received", event, ledger)  # noqa: SLF001


class RC14DurableAuditedOpenRouterClient(DurableAuditedOpenRouterClient):
    """One persistence-first request/parser/identity path for RC1.4."""

    store: RC14DurableTrajectoryStore

    async def get_native_response(
        self,
        prompt: Any,
        model: str,
        sampling_args: Any,
        tools: Any = None,
        **kwargs: Any,
    ) -> Any:
        known = _known_tool_names(tools)
        if self.store.latest_path.is_file():
            self.store.reconcile_framework_tool_results(
                prompt,
                ledger=self.ledger,
                known_tool_names=known,
            )
            self.store.assert_provider_request_lifecycle(prompt)
        normalized = dict(sampling_args)
        injected_n = normalized.pop("n", None)
        state_present = "state" in kwargs
        kwargs.pop("state", None)
        if injected_n is not None and (
            not isinstance(injected_n, int)
            or isinstance(injected_n, bool)
            or injected_n != 1
        ):
            raise ConfigurationError(
                "RC1.4 may normalize only the framework's redundant n=1 default"
            )
        request_args = dict(normalized)
        extra_body = dict(request_args.pop("extra_body", {}) or {})
        body: dict[str, Any] = {
            "model": model,
            "messages": prompt,
            **request_args,
            **extra_body,
        }
        if tools:
            body["tools"] = tools
        contract = exact_request_contract(body)
        supported = set(getattr(self.adapter, "supported_parameters", ()))
        unsupported = set(contract["endpoint_visible_parameters"]) - supported
        if unsupported:
            raise ConfigurationError(
                f"Live request contains unsupported parameters: {sorted(unsupported)}"
            )
        extra_headers = kwargs.pop("extra_headers", None)
        if kwargs:
            raise ConfigurationError(f"Unexpected native request kwargs: {sorted(kwargs)}")
        prompt_rows = [_as_dict(message) for message in prompt]
        annotation = {
            "input_n": injected_n,
            "removed_redundant_n_equals_one": injected_n == 1,
            "removed_nontransport_state_object": state_present,
            "semantic_rollout_count_unchanged": True,
        }
        prompt_contract = {
            "message_count": len(prompt_rows),
            "roles": [row.get("role") for row in prompt_rows],
            "tool_result_message_count": sum(
                row.get("role") == "tool" for row in prompt_rows
            ),
            "assistant_reasoning_state_message_count": sum(
                row.get("role") == "assistant"
                and any(
                    row.get(field)
                    for field in ("reasoning", "reasoning_content", "reasoning_details")
                )
                for row in prompt_rows
            ),
        }
        started = time.monotonic()
        try:
            response = await post_chat_completion_with_routed_experts_sidecar(
                self.client,
                "/chat/completions",
                body=body,
                extra_headers=extra_headers,
            )
        except Exception as exc:
            row = self.ledger.record_error(
                exc, latency_seconds=time.monotonic() - started
            )
            row["request_contract"] = contract
            row["runner_normalization"] = annotation
            row["prompt_state_contract"] = prompt_contract
            self.ledger._checkpoint()  # noqa: SLF001
            self.store.record_model_error(prompt=prompt, error=exc, ledger=self.ledger)
            raise
        # The raw provider payload is the first durable boundary.  Parsing,
        # identity validation and all later adjudication happen only after it.
        self.store.record_received_response(
            prompt=prompt, response=response, ledger=self.ledger
        )
        row = _response_record(
            response,
            self.adapter,
            latency_seconds=time.monotonic() - started,
            request_index=len(self.ledger.records),
        )
        raw = _as_dict(response)
        choices = raw.get("choices") or []
        choice = choices[0] if choices and isinstance(choices[0], dict) else {}
        message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
        row["response_contract"] = {
            "finish_reason": choice.get("finish_reason"),
            "tool_call_count": len(message.get("tool_calls") or []),
            "content_present": bool(message.get("content")),
            "reasoning_state_present": any(
                message.get(field)
                for field in ("reasoning", "reasoning_content", "reasoning_details")
            ),
        }
        row["request_contract"] = contract
        row["runner_normalization"] = annotation
        row["prompt_state_contract"] = prompt_contract
        self.ledger.records.append(row)
        self.ledger._checkpoint()  # noqa: SLF001
        self.store.record_model_response(
            prompt=prompt, response=response, ledger=self.ledger
        )
        if row["identity_violations"]:
            raise ProviderIdentityError(
                "Provider identity validation failed: "
                + ", ".join(row["identity_violations"])
            )
        self.ledger.enforce_cap()
        return response


def build_rc14_scientific_client(
    *,
    key: str,
    adapter: Any,
    ledger: DurableRequestLedger,
    store: RC14DurableTrajectoryStore,
    native_client_factory: Callable[..., Any] | None = None,
) -> RC14DurableAuditedOpenRouterClient:
    """Use the unchanged explicit-key constructor with the RC1.4 observer."""

    kwargs: dict[str, Any] = {}
    if native_client_factory is not None:
        kwargs["native_client_factory"] = native_client_factory
    return build_v071_scientific_client(
        key=key,
        base_url=OPENROUTER_BASE_URL,
        adapter=adapter,
        ledger=ledger,
        audited_client_factory=lambda native, selected, request_ledger: (
            RC14DurableAuditedOpenRouterClient(
                native,
                selected,
                request_ledger,
                store,
            )
        ),
        **kwargs,
    )


def rc14_runtime_factory(
    workspace: Path,
    *,
    container_name: str,
    image: str,
    core: RC14OpenMMMVPEnvironment,
) -> RC12DockerWorkspace:
    """Construct the unchanged two-mount RC1.2 runtime."""

    return RC12DockerWorkspace(
        workspace_root=workspace,
        container_name=container_name,
        image=image,
        boundary_handler=core.boundary_event,
        integrity_guard=core._assert_untampered,  # noqa: SLF001
    )


def _rc14_paced_environment(
    vf: Any,
    *,
    minimum_interval_seconds: float,
    **kwargs: Any,
) -> Any:
    """Bind exact call IDs around unchanged framework tool dispatch."""

    class RC14PacedToolEnvironment(vf.ToolEnv):
        def __init__(self, **environment_kwargs: Any) -> None:
            super().__init__(**environment_kwargs)
            self._last_request_started_at: float | None = None

        async def get_model_response(
            self, state: Any, prompt: Any, **response_kwargs: Any
        ) -> Any:
            import asyncio

            now = time.monotonic()
            if self._last_request_started_at is not None:
                remaining = minimum_interval_seconds - (
                    now - self._last_request_started_at
                )
                if remaining > 0:
                    await asyncio.sleep(remaining)
            self._last_request_started_at = time.monotonic()
            return await super().get_model_response(state, prompt, **response_kwargs)

        async def call_tool(
            self,
            tool_name: str,
            tool_args: dict[str, Any],
            tool_call_id: str,
            **call_kwargs: Any,
        ) -> Any:
            with rc13_tool_call_context(tool_call_id):
                return await super().call_tool(
                    tool_name,
                    tool_args,
                    tool_call_id,
                    **call_kwargs,
                )

    return RC14PacedToolEnvironment(**kwargs)


def usable_provider_response_count(records: list[dict[str, Any]]) -> int:
    return sum(
        row.get("error") is None
        and bool(row.get("returned_model"))
        and not row.get("identity_violations")
        for row in records
    )


def rc13_reported_values(
    classification: str,
    grade: dict[str, Any] | None,
    *,
    usable_responses: int,
    grader_or_replay_fault: bool = False,
) -> tuple[float | None, float | None]:
    """Keep science, reliability and infrastructure exclusion separate."""

    if grader_or_replay_fault:
        return None, None
    if grade is not None:
        return float(grade["partial_scientific_quality"]), float(
            grade["reliability_score"]
        )
    if classification in {
        "provider_adapter_failure",
        "provider_policy_refusal",
        "infrastructure_failure",
        "unknown_harness_failure",
    }:
        return (None, 0.0) if usable_responses else (None, None)
    if usable_responses:
        return None, 0.0
    return None, None


def terminal_tool_status(
    *,
    stop_condition: str | None,
    cap_reached: bool,
    rollout_error: Any,
) -> tuple[str, str] | None:
    if cap_reached:
        return "unexecuted_cost_boundary", "cost_cap_reached"
    if stop_condition in {"max_turns_reached", "max_total_completion_tokens_reached"}:
        return "unexecuted_horizon", str(stop_condition)
    rendered_error = str(rollout_error or "").lower()
    if stop_condition in {"timeout", "wall_clock_timeout"} or "timeout" in rendered_error:
        reason = (
            str(stop_condition)
            if stop_condition in {"timeout", "wall_clock_timeout"}
            else "timeout"
        )
        return "unexecuted_timeout", reason
    return None


def _has_active_call(store: RC13DurableTrajectoryStore) -> bool:
    if not store.latest_path.is_file():
        return False
    return any(
        call.get("status") == ACTIVE_TOOL_STATUS
        for call in store.latest().get("pending_tool_calls") or []
    )


def run_rc14_open_mmmvp_episode(
    project_root: Path,
    config: OpenRunConfig,
    *,
    adapter: Any,
    openrouter_key: str,
    authorization_digest: str,
    remaining_cost_cap_usd: float,
) -> OpenRunArtifacts:
    """Run one fresh Case-2 cell through frozen science and RC1.4 lifecycle."""

    import verifiers as vf
    from datasets import Dataset

    root = project_root.resolve()
    scientific = read_open_mmmvp_freeze(root)
    release = read_rc14_release_freeze(root)
    if scientific["hash_set_digest"] != SCIENTIFIC_FREEZE_DIGEST:
        raise ConfigurationError("RC1.4 scientific freeze digest changed")
    if authorization_digest != release["infrastructure_digest"]:
        raise ConfigurationError("RC1.4 authorization does not match the release freeze")
    if config.partition != "development":
        raise ConfigurationError("RC1.4 rejects held-out partitions")
    if config.model_id not in set(scientific["model_ids"]):
        raise ConfigurationError("Model is outside the frozen older-model panel")
    condition_id = open_condition_id(config)
    if condition_id != "case_02":
        raise ConfigurationError("RC1.4 authorization covers only Case 2")
    if adapter.model_id != config.model_id:
        raise ConfigurationError("Provider adapter model differs from requested model")
    if adapter.allow_fallbacks or len(adapter.provider_order) != 1:
        raise ConfigurationError("Scientific route must be singly pinned without fallback")

    run_root = root / "build/uc_bench_mmmvp_open_rc14_runs" / _slug(config.run_id)
    if run_root.exists():
        raise ConfigurationError(f"RC1.4 run already exists: {run_root}")
    run_root.mkdir(parents=True)
    workspace = run_root / "workspace"
    core = RC14OpenMMMVPEnvironment(
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
    store = RC14DurableTrajectoryStore(
        run_root / "host_trajectory",
        workspace=workspace,
        core=core,  # type: ignore[arg-type]
        secret=openrouter_key,
        run_metadata={
            "run_config": asdict(config),
            "condition_id": condition_id,
            "scientific_freeze_digest": scientific["hash_set_digest"],
            "release_infrastructure_digest": release["infrastructure_digest"],
            "agent_visible": False,
        },
    )
    request = production_request(config)
    if request != production_request(OpenRunConfig("identity", config.model_id, "case_01")):
        raise ConfigurationError("RC1.4 request changed across conditions or run IDs")
    if mapping_contains_credential(request, openrouter_key):
        raise ConfigurationError("Credential appeared in the scientific request")
    system_prompt = str(request["messages"][0]["content"])
    initial_prompt = list(request["messages"][1:])

    generated: dict[str, Any]
    client: Any = None
    docker: RC12DockerWorkspace | None = None
    isolation: dict[str, Any] = {}
    rollout_exception: dict[str, Any] | None = None
    persistence_failure = False
    try:
        docker = rc14_runtime_factory(
            workspace,
            container_name=f"uc-mmmvp-rc13-{_slug(config.run_id, limit=42)}",
            image=config.docker_image,
            core=core,
        )
        docker.start()
        isolation = docker.security_snapshot()
        if not rc12_isolation_passed(isolation):
            raise DockerRuntimeError("RC1.4 nested-mount isolation failed closed")
        core.mark_workspace_boundary_enforced(True)
        tool_functions = rc13_durable_tool_functions(docker, core, store, ledger)
        _assert_surface_matches_shared_request(request, tool_functions)
        environment = _rc14_paced_environment(
            vf,
            minimum_interval_seconds=config.minimum_request_interval_seconds,
            dataset=Dataset.from_list([{"prompt": initial_prompt, "answer": ""}]),
            tools=tool_functions,
            system_prompt=system_prompt,
            max_turns=config.maximum_turns,
            timeout_seconds=config.wall_clock_timeout_seconds,
            stop_errors=[DockerRuntimeError, TrajectoryPersistenceError],
            score_rollouts=False,
            env_id="uc-bench-open-mmmvp-rc1-4",
        )
        environment.set_max_total_completion_tokens(config.maximum_total_completion_tokens)
        client = build_rc14_scientific_client(
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

    output = (generated.get("outputs") or [{}])[0]
    rollout_error = output.get("error") or rollout_exception
    stop_condition = output.get("stop_condition")
    closure = terminal_tool_status(
        stop_condition=stop_condition,
        cap_reached=ledger.cap_reached,
        rollout_error=rollout_error,
    )
    if closure and _has_active_call(store):
        try:
            status, reason = closure
            store.close_terminal_tool_calls(
                status=status, boundary_reason=reason, ledger=ledger
            )
            stop_condition = reason
        except Exception as exc:
            persistence_failure = True
            rollout_exception = {
                "type": type(exc).__name__,
                "message": redact_exception_message(exc, secret=openrouter_key),
            }

    completion = output.get("completion") or []
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

    integrity = core.integrity_status()
    if integrity["protected_evidence_mutation_attempted"]:
        classification = "protected_evidence_tampering"
    if not integrity["workspace_boundary_enforced"]:
        classification = "infrastructure_failure"

    submission = core.export_submission()
    grade: dict[str, Any] | None = None
    grader_exception: dict[str, str] | None = None
    if (
        core.state.completion_accepted
        and integrity["protected_evidence_untampered"]
        and not integrity["protected_evidence_mutation_attempted"]
    ):
        try:
            grade = verify_open_submission(
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
            classification = "grader_failure"
    consistency = (
        _grader_consistency(grade)
        if grade is not None
        else {
            "passed": grader_exception is None,
            "faults": ["verifier_exception"] if grader_exception else [],
        }
    )
    if not consistency["passed"]:
        classification = "grader_failure"

    if store.latest_path.is_file():
        try:
            replay = rc13_trajectory_replay_check(
                root,
                workspace,
                store,
                condition_id=condition_id,
                grade=grade,
                stop_condition=stop_condition,
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
    replay_fault = not replay["passed"]
    if replay_fault:
        classification = "infrastructure_failure"
        consistency = {
            "passed": False,
            "faults": [
                *consistency["faults"],
                "trajectory_persistence_or_replay_failure",
            ],
        }

    usable = usable_provider_response_count(ledger.records)
    scientific_score, reliability = rc13_reported_values(
        classification,
        grade,
        usable_responses=usable,
        grader_or_replay_fault=bool(grader_exception) or replay_fault,
    )
    metadata = generated.get("metadata") or {}
    summary = {
        "schema_version": "uc-bench-open-mmmvp-rc1-4-run-1",
        "executed_at": datetime.now(UTC).isoformat(),
        "run_config": asdict(config),
        "run_id": config.run_id,
        "host_trajectory_path": (run_root / "host_trajectory").relative_to(root).as_posix(),
        "model_id": config.model_id,
        "condition_id": condition_id,
        "classification": classification,
        "complete_mission_success": grade["complete_mission_success"] if grade else None,
        "partial_scientific_quality": scientific_score,
        "reliability_score": reliability,
        "diagnostic_grade": grade,
        "grader_exception": grader_exception,
        "grader_consistency": consistency,
        "submission": submission,
        "rollout_error": _redact_public_identifiers(rollout_error),
        "stop_condition": stop_condition,
        **completion_stats(output),
        "token_usage": output.get("token_usage") or metadata.get("usage") or {},
        "provider_adapter": adapter.to_dict(),
        "provider_requests": ledger.records,
        "provider_request_count": len(ledger.records),
        "usable_provider_response_count": usable,
        "cumulative_reported_cost_usd": round(
            ledger.cumulative_reported_cost_usd, 8
        ),
        "isolation": isolation,
        "integrity": integrity,
        "recoverable_contract_violation_count": integrity[
            "recoverable_contract_violation_count"
        ],
        "protected_evidence_mutation_attempted": integrity[
            "protected_evidence_mutation_attempted"
        ],
        "protected_evidence_untampered": integrity[
            "protected_evidence_untampered"
        ],
        "workspace_boundary_enforced": integrity["workspace_boundary_enforced"],
        "trajectory_persistence": replay,
        "framework_tool_error_count": replay.get("framework_tool_error_count", 0),
        "framework_tool_error_classes": replay.get(
            "framework_tool_error_classes", {}
        ),
        "wrapper_tool_error_count": replay.get("wrapper_tool_error_count", 0),
        "horizon_boundary": {
            "unexecuted_terminal_tool_count": replay.get(
                "unexecuted_terminal_tool_count", 0
            ),
            "terminal_tool_name": replay.get("terminal_tool_name"),
            "terminal_boundary_reason": replay.get("terminal_boundary_reason"),
            "resume_boundary_available": replay.get(
                "resume_boundary_available", False
            ),
            "terminal_replay_available": replay.get(
                "terminal_replay_available", False
            ),
        },
        "serialized_request_sha256": scientific["serialized_request_sha256"],
        "agent_visible_contract_sha256": release["agent_visible_contract_sha256"],
        "provider_fallbacks_allowed": False,
        "agent_received_provider_credentials": False,
        "agent_network_enabled": False,
        "heldout_requests": 0,
        "astra_requests": 0,
        "scientific_freeze_digest": scientific["hash_set_digest"],
        "release_infrastructure_digest": release["infrastructure_digest"],
    }
    _write_json(run_root / "run_summary.json", summary, secret=openrouter_key)
    _write_json(run_root / "submission.json", submission, secret=openrouter_key)
    _write_json(run_root / "verifiers_output.json", generated, secret=openrouter_key)
    leaked = credential_locations(run_root, openrouter_key)
    if leaked:
        raise ConfigurationError(
            "Credential leakage guard failed in RC1.4 artifacts: " + ", ".join(leaked)
        )
    return OpenRunArtifacts(
        run_root=run_root,
        workspace_root=workspace,
        summary_path=run_root / "run_summary.json",
        request_ledger_path=run_root / "request_ledger.json",
        summary=summary,
    )


__all__ = [
    "RC14DurableAuditedOpenRouterClient",
    "RC14DurableTrajectoryStore",
    "SCIENTIFIC_FREEZE_DIGEST",
    "build_rc14_scientific_client",
    "rc13_reported_values",
    "rc14_runtime_factory",
    "run_rc14_open_mmmvp_episode",
    "terminal_tool_status",
    "usable_provider_response_count",
]

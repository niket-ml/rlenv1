"""Shared, persistence-first runtime primitives for the clean Case 1 pilot root."""

from __future__ import annotations

import json
import math
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from uc_bench.case1_pilot_v1_host import ensure_docker_cli_on_path
from uc_bench.durable_runner import DurableAuditedOpenRouterClient, DurableRequestLedger
from uc_bench.durable_trajectory import _message_rows
from uc_bench.errors import ConfigurationError
from uc_bench.mmmvp_open_rc12_environment import RC12DockerWorkspace
from uc_bench.mmmvp_open_rc13_trajectory import (
    RC13DurableTrajectoryStore,
    rc13_tool_call_context,
)
from uc_bench.openrouter import OPENROUTER_BASE_URL
from uc_bench.v06_provider import ProviderIdentityError, _as_dict, _response_record
from uc_bench.v061_provider import (
    exact_request_contract,
    post_chat_completion_with_routed_experts_sidecar,
)
from uc_bench.v071_auth import build_v071_scientific_client


def _known_tool_names(tools: Any) -> frozenset[str]:
    result: set[str] = set()
    for raw in tools or []:
        row = _as_dict(raw)
        function = row.get("function") if isinstance(row, Mapping) else None
        if isinstance(function, Mapping) and function.get("name"):
            result.add(str(function["name"]))
    return frozenset(result)


class Case1PilotTrajectoryStore(RC13DurableTrajectoryStore):
    """Persist the raw response before parser, identity, or scientific judgement."""

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


class Case1PilotClient(DurableAuditedOpenRouterClient):
    """Exact pinned-route client with raw-response-first durable persistence."""

    store: Case1PilotTrajectoryStore

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
            raise ConfigurationError("Only the framework's redundant n=1 may be removed")
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
        annotation = {
            "input_n": injected_n,
            "removed_redundant_n_equals_one": injected_n == 1,
            "removed_nontransport_state_object": state_present,
            "semantic_rollout_count_unchanged": True,
        }
        prompt_character_upper = len(
            json.dumps(
                {"messages": body.get("messages"), "tools": body.get("tools")},
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        maximum_request_cost = (
            prompt_character_upper
            * float(self.adapter.maximum_prompt_price_usd_per_million)
            + int(body.get("max_tokens") or 0)
            * float(self.adapter.maximum_completion_price_usd_per_million)
        ) / 1_000_000
        remaining = float(self.ledger.remaining_cap_usd) - float(
            self.ledger.cumulative_reported_cost_usd
        )
        if (
            not math.isfinite(maximum_request_cost)
            or maximum_request_cost < 0
            or maximum_request_cost > remaining + 1e-12
        ):
            raise ConfigurationError(
                "Conservative pre-request cost guard refused a request that could exceed "
                "the remaining cumulative cap"
            )
        annotation["prompt_character_token_upper"] = prompt_character_upper
        annotation["maximum_request_cost_usd"] = maximum_request_cost
        annotation["remaining_cap_before_request_usd"] = remaining
        started = time.monotonic()
        try:
            response = await post_chat_completion_with_routed_experts_sidecar(
                self.client,
                "/chat/completions",
                body=body,
                extra_headers=extra_headers,
            )
        except Exception as exc:
            row = self.ledger.record_error(exc, latency_seconds=time.monotonic() - started)
            row["request_contract"] = contract
            row["runner_normalization"] = annotation
            self.ledger._checkpoint()  # noqa: SLF001
            self.store.record_model_error(prompt=prompt, error=exc, ledger=self.ledger)
            raise
        self.store.record_received_response(prompt=prompt, response=response, ledger=self.ledger)
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
        self.ledger.records.append(row)
        self.ledger._checkpoint()  # noqa: SLF001
        self.store.record_model_response(prompt=prompt, response=response, ledger=self.ledger)
        if row["identity_violations"]:
            raise ProviderIdentityError(
                "Provider identity validation failed: "
                + ", ".join(row["identity_violations"])
            )
        self.ledger.enforce_cap()
        return response


def build_case1_pilot_client(
    *,
    key: str,
    adapter: Any,
    ledger: DurableRequestLedger,
    store: Case1PilotTrajectoryStore,
    native_client_factory: Callable[..., Any] | None = None,
) -> Case1PilotClient:
    kwargs: dict[str, Any] = {}
    if native_client_factory is not None:
        kwargs["native_client_factory"] = native_client_factory
    return build_v071_scientific_client(
        key=key,
        base_url=OPENROUTER_BASE_URL,
        adapter=adapter,
        ledger=ledger,
        audited_client_factory=lambda native, selected, request_ledger: Case1PilotClient(
            native,
            selected,
            request_ledger,
            store,
        ),
        **kwargs,
    )


def case1_pilot_runtime_factory(
    workspace: Path,
    *,
    container_name: str,
    image: str,
    core: Any,
) -> RC12DockerWorkspace:
    ensure_docker_cli_on_path()
    return RC12DockerWorkspace(
        workspace_root=workspace,
        container_name=container_name,
        image=image,
        boundary_handler=core.boundary_event,
        integrity_guard=core._assert_untampered,  # noqa: SLF001
    )


def paced_tool_environment(
    vf: Any,
    *,
    minimum_interval_seconds: float,
    **kwargs: Any,
) -> Any:
    """Bind exact provider tool-call IDs while preserving request pacing."""

    class Case1PilotToolEnvironment(vf.ToolEnv):
        def __init__(self, **environment_kwargs: Any) -> None:
            super().__init__(**environment_kwargs)
            self._last_request_started_at: float | None = None

        async def get_model_response(
            self,
            state: Any,
            prompt: Any,
            **response_kwargs: Any,
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

    return Case1PilotToolEnvironment(**kwargs)


__all__ = [
    "Case1PilotClient",
    "Case1PilotTrajectoryStore",
    "build_case1_pilot_client",
    "case1_pilot_runtime_factory",
    "paced_tool_environment",
]

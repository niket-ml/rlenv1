"""RC4 persistence-first client with one safe pending-request retry."""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections.abc import Callable, Mapping
from typing import Any

import httpx
from openai.types.chat import ChatCompletion
from verifiers.legacy.utils.client_utils import strip_routed_experts_data

from uc_bench.case1_pilot_v1_runtime import (
    Case1PilotClient,
    Case1PilotTrajectoryStore,
    _known_tool_names,
    case1_pilot_runtime_factory,
    paced_tool_environment,
)
from uc_bench.durable_runner import DurableRequestLedger
from uc_bench.errors import ConfigurationError
from uc_bench.openrouter import OPENROUTER_BASE_URL
from uc_bench.v06_provider import ProviderIdentityError, _response_record
from uc_bench.v061_provider import exact_request_contract
from uc_bench.v071_auth import build_v071_scientific_client


class TerminalProviderResponseError(RuntimeError):
    """A persisted provider response cannot be represented by the SDK schema."""


def _transient(error: BaseException) -> bool:
    status = getattr(error, "status_code", None)
    if status in {408, 409, 425, 429, 500, 502, 503, 504}:
        return True
    lowered = str(error).lower()
    return any(
        marker in lowered
        for marker in (
            "temporarily unavailable",
            "connection reset",
            "connection timeout",
            "read timeout",
        )
    )


class RC4TrajectoryStore(Case1PilotTrajectoryStore):
    def record_terminal_provider_response(
        self,
        *,
        prompt: Any,
        raw_response: dict[str, Any],
        retry_index: int,
        ledger: Any,
    ) -> dict[str, Any]:
        return self._persist(  # noqa: SLF001
            "terminal_provider_response_rejected_before_state_application",
            {
                "prompt": prompt,
                "raw_response": raw_response,
                "retry_index": retry_index,
                "assistant_message_applied": False,
                "tool_call_applied": False,
                "scientific_state_mutated": False,
            },
            ledger,
        )


class RC4Case1Client(Case1PilotClient):
    """Parse only after raw persistence; retry one identical pending request safely."""

    store: RC4TrajectoryStore

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
            "safe_pending_request_retry_maximum": 1,
            "pending_request_body_sha256": hashlib.sha256(
                json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode()
            ).hexdigest(),
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
        annotation["prompt_character_token_upper"] = prompt_character_upper
        annotation["maximum_request_cost_usd"] = maximum_request_cost

        for retry_index in range(2):
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
            attempt_annotation = {
                **annotation,
                "remaining_cap_before_request_usd": remaining,
                "pending_request_retry_index": retry_index,
                "request_body_unchanged_for_retry": True,
            }
            started = time.monotonic()
            try:
                raw_http = await self.client.post(
                    "/chat/completions",
                    body=body,
                    cast_to=httpx.Response,
                    options={"headers": extra_headers} if extra_headers else {},
                )
            except Exception as exc:
                row = self.ledger.record_error(
                    exc, latency_seconds=time.monotonic() - started
                )
                row["request_contract"] = contract
                row["runner_normalization"] = attempt_annotation
                self.ledger._checkpoint()  # noqa: SLF001
                self.store.record_model_error(prompt=prompt, error=exc, ledger=self.ledger)
                if retry_index == 0 and _transient(exc):
                    continue
                raise

            try:
                raw_payload = json.loads(raw_http.content)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raw_payload = {
                    "unparseable_response": True,
                    "http_status": raw_http.status_code,
                    "raw_body_utf8": raw_http.content.decode("utf-8", errors="replace"),
                    "raw_body_sha256": hashlib.sha256(raw_http.content).hexdigest(),
                }
                self.store.record_received_response(
                    prompt=prompt, response=raw_payload, ledger=self.ledger
                )
                row = self.ledger.record_error(exc, latency_seconds=time.monotonic() - started)
                row["error"]["classification"] = "provider_adapter_failure"
                row["request_contract"] = contract
                row["runner_normalization"] = attempt_annotation
                self.ledger._checkpoint()  # noqa: SLF001
                self.store.record_terminal_provider_response(
                    prompt=prompt,
                    raw_response=raw_payload,
                    retry_index=retry_index,
                    ledger=self.ledger,
                )
                self.ledger.enforce_cap()
                if retry_index == 0:
                    continue
                raise TerminalProviderResponseError(
                    "Provider response was not valid JSON twice for the same pending request"
                ) from exc

            self.store.record_received_response(
                prompt=prompt,
                response=raw_payload,
                ledger=self.ledger,
            )
            row = _response_record(
                raw_payload,
                self.adapter,
                latency_seconds=time.monotonic() - started,
                request_index=len(self.ledger.records),
            )
            choice = (raw_payload.get("choices") or [{}])[0]
            message = choice.get("message") if isinstance(choice, Mapping) else {}
            if not isinstance(message, Mapping):
                message = {}
            finish_reason = choice.get("finish_reason") if isinstance(choice, Mapping) else None
            row["response_contract"] = {
                "finish_reason": finish_reason,
                "tool_call_count": len(message.get("tool_calls") or []),
                "content_present": bool(message.get("content")),
                "reasoning_state_present": any(
                    message.get(field)
                    for field in ("reasoning", "reasoning_content", "reasoning_details")
                ),
            }
            row["request_contract"] = contract
            row["runner_normalization"] = attempt_annotation
            terminal_error = finish_reason == "error"
            if terminal_error:
                row["error"] = {
                    "classification": "provider_adapter_failure",
                    "http_status": raw_http.status_code,
                    "type": "TerminalProviderResponseError",
                    "message": "Provider returned finish_reason=error",
                }
            self.ledger.records.append(row)
            self.ledger._checkpoint()  # noqa: SLF001
            if terminal_error:
                self.store.record_terminal_provider_response(
                    prompt=prompt,
                    raw_response=raw_payload,
                    retry_index=retry_index,
                    ledger=self.ledger,
                )
                self.ledger.enforce_cap()
                if retry_index == 0:
                    continue
                raise TerminalProviderResponseError(
                    "Provider returned finish_reason=error twice for the same pending request"
                )

            try:
                stripped, routed_data = strip_routed_experts_data(raw_http.content)
                response = ChatCompletion.model_validate_json(stripped)
            except Exception as exc:
                row["error"] = {
                    "classification": "provider_adapter_failure",
                    "http_status": raw_http.status_code,
                    "type": type(exc).__name__,
                    "message": "Persisted provider response failed SDK parsing",
                }
                self.ledger._checkpoint()  # noqa: SLF001
                self.store.record_terminal_provider_response(
                    prompt=prompt,
                    raw_response=raw_payload,
                    retry_index=retry_index,
                    ledger=self.ledger,
                )
                self.ledger.enforce_cap()
                if retry_index == 0:
                    continue
                raise TerminalProviderResponseError(
                    "Provider response failed SDK parsing twice for the same pending request"
                ) from exc
            if routed_data is not None:
                extra = response.choices[0].model_extra
                if extra is not None:
                    extra["routed_experts"]["data"] = routed_data
            self.store.record_model_response(prompt=prompt, response=response, ledger=self.ledger)
            if row["identity_violations"]:
                raise ProviderIdentityError(
                    "Provider identity validation failed: "
                    + ", ".join(row["identity_violations"])
                )
            self.ledger.enforce_cap()
            return response
        raise AssertionError("unreachable retry loop")


def build_rc4_client(
    *,
    key: str,
    adapter: Any,
    ledger: DurableRequestLedger,
    store: RC4TrajectoryStore,
    native_client_factory: Callable[..., Any] | None = None,
) -> RC4Case1Client:
    kwargs: dict[str, Any] = {}
    if native_client_factory is not None:
        kwargs["native_client_factory"] = native_client_factory
    return build_v071_scientific_client(
        key=key,
        base_url=OPENROUTER_BASE_URL,
        adapter=adapter,
        ledger=ledger,
        audited_client_factory=lambda native, selected, request_ledger: RC4Case1Client(
            native, selected, request_ledger, store
        ),
        **kwargs,
    )


__all__ = [
    "RC4Case1Client",
    "RC4TrajectoryStore",
    "TerminalProviderResponseError",
    "build_rc4_client",
    "case1_pilot_runtime_factory",
    "paced_tool_environment",
]

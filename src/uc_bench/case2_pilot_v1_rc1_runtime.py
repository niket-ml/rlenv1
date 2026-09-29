"""Persistence-first provider runtime for the self-contained Case 2 release."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from uc_bench.case1_pilot_v1_rc4_runtime import (
    RC4Case1Client,
    RC4TrajectoryStore,
    TerminalProviderResponseError,
    case1_pilot_runtime_factory,
    paced_tool_environment,
)
from uc_bench.case1_pilot_v1_rc6_lifecycle import (
    LifecycleTransportProxy,
    RC6RequestLedger,
    RequestLifecycleMachine,
)
from uc_bench.durable_trajectory import _message_rows
from uc_bench.hashing import canonical_sha256
from uc_bench.openrouter import OPENROUTER_BASE_URL
from uc_bench.v06_provider import ProviderIdentityError
from uc_bench.v071_auth import build_v071_scientific_client


class Case2TrajectoryStore(RC4TrajectoryStore):
    """Case-neutral atomic journal bound to one Case 2 environment."""

    interrupt_after_phase: str | None = None
    interruption_triggered: bool = False

    def record_terminal_provider_response(
        self,
        *,
        prompt: Any,
        raw_response: dict[str, Any],
        retry_index: int,
        ledger: Any,
    ) -> dict[str, Any]:
        """Represent a rejected provider response without applying it to the agent."""

        exchange = {
            "request_index": len(self._provider_exchanges),  # noqa: SLF001
            "prompt": _message_rows(prompt),
            "assistant_output": None,
            "reasoning_state_payload": {},
            "tool_calls": [],
            "raw_response": raw_response,
            "terminal_response_rejected": True,
            "retry_index": retry_index,
        }
        self._provider_exchanges.append(exchange)  # noqa: SLF001
        return self._persist(  # noqa: SLF001
            "terminal_provider_response_rejected_before_state_application",
            {
                **exchange,
                "assistant_message_applied": False,
                "tool_call_applied": False,
                "scientific_state_mutated": False,
            },
            ledger,
        )

    def record_completed_response_binding(
        self,
        *,
        request_index: int,
        request_body_sha256: str,
        raw_body_sha256: str,
        ledger: RC6RequestLedger,
    ) -> dict[str, Any]:
        """Bind one parsed exchange to the exact transport request and response."""

        if request_index < 0 or request_index >= len(self._provider_exchanges):  # noqa: SLF001
            raise RuntimeError("Completed response has no matching provider exchange")
        exchange = self._provider_exchanges[request_index]  # noqa: SLF001
        if exchange.get("request_index") != request_index:
            raise RuntimeError("Provider exchange index is inconsistent")
        raw_response = exchange.get("raw_response")
        if not isinstance(raw_response, dict):
            raise RuntimeError("Completed response lacks persisted raw response")
        binding = {
            "request_index": request_index,
            "request_body_sha256": request_body_sha256,
            "raw_body_sha256": raw_body_sha256,
            "raw_response_sha256": canonical_sha256(raw_response),
        }
        for field, value in binding.items():
            existing = exchange.get(field)
            if existing is not None and existing != value:
                raise RuntimeError(f"Provider response binding changed: {field}")
            exchange[field] = value
        return self._persist("completed_response_binding", binding, ledger)  # noqa: SLF001

    def record_failed_attempt_binding(
        self,
        *,
        request_index: int,
        state: str,
        request_body_sha256: str,
        raw_body_sha256: str | None,
        ledger: RC6RequestLedger,
    ) -> dict[str, Any]:
        """Bind a failed attempt to its ledger and diagnostic exchange."""

        if request_index < 0 or request_index >= len(self._provider_exchanges):  # noqa: SLF001
            raise RuntimeError("Failed attempt has no matching provider exchange")
        if request_index >= len(ledger.records):
            raise RuntimeError("Failed attempt has no matching request-ledger record")
        exchange = self._provider_exchanges[request_index]  # noqa: SLF001
        record = ledger.records[request_index]
        if exchange.get("request_index") != request_index:
            raise RuntimeError("Failed provider exchange index is inconsistent")
        error = record.get("error")
        if not isinstance(error, dict):
            raise RuntimeError("Failed attempt lacks a structured ledger error")
        binding = {
            "request_index": request_index,
            "attempt_state": state,
            "request_body_sha256": request_body_sha256,
            "error_record_sha256": canonical_sha256(error),
        }
        if raw_body_sha256 is not None:
            raw_response = exchange.get("raw_response")
            if not isinstance(raw_response, dict):
                raise RuntimeError("Rejected response lacks persisted raw response")
            binding.update(
                {
                    "raw_body_sha256": raw_body_sha256,
                    "raw_response_sha256": canonical_sha256(raw_response),
                }
            )
        for field, value in binding.items():
            existing = exchange.get(field)
            if existing is not None and existing != value:
                raise RuntimeError(f"Failed response binding changed: {field}")
            exchange[field] = value
        return self._persist("failed_attempt_binding", binding, ledger)  # noqa: SLF001

    def record_tool_action(self, **kwargs: Any) -> dict[str, Any]:
        value = super().record_tool_action(**kwargs)
        if (
            self.interrupt_after_phase
            and not self.interruption_triggered
            and self.core.state.phase == self.interrupt_after_phase
        ):
            self.interruption_triggered = True
            raise PlannedPreflightInterruption(
                f"planned durable interruption after phase {self.interrupt_after_phase}"
            )
        return value


class PlannedPreflightInterruption(RuntimeError):
    """Host-only injected interruption after a durable tool boundary."""


class Case2Client(RC4Case1Client):
    """Exact pending-request retries plus an explicit atomic request lifecycle."""

    def __init__(
        self,
        native: Any,
        adapter: Any,
        ledger: RC6RequestLedger,
        store: Case2TrajectoryStore,
        lifecycle: RequestLifecycleMachine,
    ) -> None:
        self.lifecycle = lifecycle
        super().__init__(native, adapter, ledger, store)
        self._client = LifecycleTransportProxy(self.client, lifecycle=lifecycle, ledger=ledger)

    def _persist_failed_attempt_bindings(self) -> None:
        changed = False
        failure_states = {
            "transient_transport_failure",
            "terminal_provider_failure",
            "provider_response_parse_failure",
        }
        for index, attempt in enumerate(self.lifecycle.attempts):
            if attempt.get("state") not in failure_states:
                continue
            existing = attempt.get("ledger_request_index")
            if existing is not None and existing != index:
                raise RuntimeError("Failed lifecycle attempt changed ledger index")
            if index >= len(self.ledger.records):
                raise RuntimeError("Failed lifecycle attempt precedes its ledger record")
            record = self.ledger.records[index]
            normalization = record.get("runner_normalization") or {}
            request_digest = attempt.get("request_body_sha256")
            if (
                not isinstance(request_digest, str)
                or normalization.get("pending_request_body_sha256") != request_digest
            ):
                raise RuntimeError("Failed request digest differs from request ledger")
            raw_digest = attempt.get("raw_body_sha256")
            exchange = self.store._provider_exchanges[index]  # noqa: SLF001
            expected_binding = {
                "attempt_state": attempt["state"],
                "request_body_sha256": request_digest,
                "error_record_sha256": canonical_sha256(record.get("error")),
            }
            if isinstance(raw_digest, str):
                expected_binding["raw_body_sha256"] = raw_digest
            if any(exchange.get(field) != value for field, value in expected_binding.items()):
                self.store.record_failed_attempt_binding(
                    request_index=index,
                    state=str(attempt["state"]),
                    request_body_sha256=request_digest,
                    raw_body_sha256=raw_digest if isinstance(raw_digest, str) else None,
                    ledger=self.ledger,
                )
                changed = True
            if existing is None:
                attempt["ledger_request_index"] = index
                changed = True
        if changed:
            self.lifecycle._checkpoint()  # noqa: SLF001 - atomic Case 2 binding repair

    def _persist_completed_response_binding(self, active: dict[str, Any]) -> None:
        ledger_index = len(self.ledger.records) - 1
        if ledger_index < 0:
            raise RuntimeError("Completed response lacks a request-ledger record")
        record = self.ledger.records[ledger_index]
        normalization = record.get("runner_normalization") or {}
        request_digest = active.get("request_body_sha256")
        raw_digest = active.get("raw_body_sha256")
        if (
            not isinstance(request_digest, str)
            or normalization.get("pending_request_body_sha256") != request_digest
        ):
            raise RuntimeError("Lifecycle request digest differs from request ledger")
        if not isinstance(raw_digest, str):
            raise RuntimeError("Lifecycle response digest is absent")
        self.store.record_completed_response_binding(
            request_index=ledger_index,
            request_body_sha256=request_digest,
            raw_body_sha256=raw_digest,
            ledger=self.ledger,
        )

    async def get_native_response(
        self,
        prompt: Any,
        model: str,
        sampling_args: Any,
        tools: Any = None,
        **kwargs: Any,
    ) -> Any:
        try:
            response = await super().get_native_response(
                prompt, model, sampling_args, tools, **kwargs
            )
        except Exception as exc:
            active = self.lifecycle.active()
            if active is not None and active.get("response_received"):
                if isinstance(exc, ProviderIdentityError):
                    self._persist_failed_attempt_bindings()
                    self._persist_completed_response_binding(active)
                    self.lifecycle.transition(
                        int(active["attempt_id"]),
                        "completed_response",
                        ledger_request_index=len(self.ledger.records) - 1,
                    )
                else:
                    self.lifecycle.reconcile_response_failure(self.ledger)
                    self._persist_failed_attempt_bindings()
            else:
                self._persist_failed_attempt_bindings()
            raise
        active = self.lifecycle.active()
        if active is None or not active.get("response_received"):
            raise RuntimeError("Completed response lacks a pending lifecycle attempt")
        self._persist_failed_attempt_bindings()
        self._persist_completed_response_binding(active)
        self.lifecycle.transition(
            int(active["attempt_id"]),
            "completed_response",
            ledger_request_index=len(self.ledger.records) - 1,
        )
        return response


def build_case2_client(
    *,
    key: str,
    adapter: Any,
    ledger: RC6RequestLedger,
    store: Case2TrajectoryStore,
    native_client_factory: Callable[..., Any] | None = None,
) -> Case2Client:
    """Construct only after the explicit key and base URL are available."""

    lifecycle_path = ledger.path.parent / "request_lifecycle.json"
    lifecycle = (
        RequestLifecycleMachine.load(lifecycle_path, secret=key)
        if lifecycle_path.is_file()
        else RequestLifecycleMachine(lifecycle_path, secret=key)
    )
    kwargs: dict[str, Any] = {}
    if native_client_factory is not None:
        kwargs["native_client_factory"] = native_client_factory
    return build_v071_scientific_client(
        key=key,
        base_url=OPENROUTER_BASE_URL,
        adapter=adapter,
        ledger=ledger,
        audited_client_factory=lambda native, selected, request_ledger: Case2Client(
            native, selected, request_ledger, store, lifecycle
        ),
        **kwargs,
    )


__all__ = [
    "Case2Client",
    "Case2TrajectoryStore",
    "PlannedPreflightInterruption",
    "RC6RequestLedger",
    "TerminalProviderResponseError",
    "build_case2_client",
    "case1_pilot_runtime_factory",
    "paced_tool_environment",
]

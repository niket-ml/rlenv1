"""RC6 production client: unchanged request surface plus explicit lifecycle."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from uc_bench.case1_pilot_v1_rc4_runtime import (
    RC4Case1Client,
    RC4TrajectoryStore,
    case1_pilot_runtime_factory,
    paced_tool_environment,
)
from uc_bench.case1_pilot_v1_rc6_lifecycle import (
    LifecycleTransportProxy,
    RC6RequestLedger,
    RequestLifecycleMachine,
)
from uc_bench.openrouter import OPENROUTER_BASE_URL
from uc_bench.v06_provider import ProviderIdentityError
from uc_bench.v071_auth import build_v071_scientific_client


class RC6Case1Client(RC4Case1Client):
    """Apply the RC4 parser/retry path while persisting explicit attempt states."""

    def __init__(
        self,
        native: Any,
        adapter: Any,
        ledger: RC6RequestLedger,
        store: RC4TrajectoryStore,
        lifecycle: RequestLifecycleMachine,
    ) -> None:
        self.lifecycle = lifecycle
        super().__init__(native, adapter, ledger, store)
        self._client = LifecycleTransportProxy(
            self.client, lifecycle=lifecycle, ledger=ledger
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
                    self.lifecycle.transition(
                        int(active["attempt_id"]),
                        "completed_response",
                        ledger_request_index=len(self.ledger.records) - 1,
                    )
                else:
                    self.lifecycle.reconcile_response_failure(self.ledger)
            raise
        active = self.lifecycle.active()
        if active is None or not active.get("response_received"):
            raise RuntimeError("Completed provider response lacks a pending lifecycle attempt")
        self.lifecycle.transition(
            int(active["attempt_id"]),
            "completed_response",
            ledger_request_index=len(self.ledger.records) - 1,
        )
        return response


def build_rc6_client(
    *,
    key: str,
    adapter: Any,
    ledger: RC6RequestLedger,
    store: RC4TrajectoryStore,
    native_client_factory: Callable[..., Any] | None = None,
) -> RC6Case1Client:
    """Construct the same explicit-key client and add only host lifecycle state."""

    lifecycle = RequestLifecycleMachine(
        ledger.path.parent / "request_lifecycle.json", secret=key
    )
    kwargs: dict[str, Any] = {}
    if native_client_factory is not None:
        kwargs["native_client_factory"] = native_client_factory
    return build_v071_scientific_client(
        key=key,
        base_url=OPENROUTER_BASE_URL,
        adapter=adapter,
        ledger=ledger,
        audited_client_factory=lambda native, selected, request_ledger: RC6Case1Client(
            native, selected, request_ledger, store, lifecycle
        ),
        **kwargs,
    )


__all__ = [
    "RC6Case1Client",
    "RC4TrajectoryStore",
    "build_rc6_client",
    "case1_pilot_runtime_factory",
    "paced_tool_environment",
]

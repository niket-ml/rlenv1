"""Atomic provider-attempt lifecycle and identity adjudication for Case-1 RC6."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.durable_runner import DurableRequestLedger
from uc_bench.errors import ConfigurationError
from uc_bench.v071_auth import redact_credentials, redact_exception_message

ATTEMPT_STATES = frozenset(
    {
        "completed_response",
        "transient_transport_failure",
        "terminal_provider_failure",
        "provider_response_parse_failure",
        "pending",
        "cancelled_before_execution",
    }
)
TERMINAL_ATTEMPT_STATES = ATTEMPT_STATES - {"pending"}
_TRANSIENT_STATUSES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})
_TRANSIENT_TYPES = frozenset(
    {
        "APITimeoutError",
        "ConnectError",
        "ConnectTimeout",
        "ReadError",
        "ReadTimeout",
        "TimeoutError",
    }
)


def exception_chain(error: BaseException) -> tuple[BaseException, ...]:
    """Return the complete explicit/implicit exception chain without cycles."""

    result: list[BaseException] = []
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        result.append(current)
        next_error = current.__cause__
        if next_error is None and not current.__suppress_context__:
            next_error = current.__context__
        current = next_error
    return tuple(result)


def transient_failure(error: BaseException) -> bool:
    """Classify timeouts and retryable HTTP failures from the full chain."""

    chain = exception_chain(error)
    for item in chain:
        status = getattr(item, "status_code", None)
        if status in _TRANSIENT_STATUSES:
            return True
        if type(item).__name__ in _TRANSIENT_TYPES:
            return True
        message = str(item).strip().lower()
        if message == "request timed out." or any(
            marker in message
            for marker in (
                "temporarily unavailable",
                "connection reset",
                "connection timeout",
                "read timeout",
                "timed out",
            )
        ):
            return True
    return False


def serialized_exception_chain(error: BaseException, *, secret: str) -> list[dict[str, Any]]:
    return [
        {
            "type": type(item).__name__,
            "message": redact_exception_message(item, secret=secret),
            "status_code": getattr(item, "status_code", None),
        }
        for item in exception_chain(error)
    ]


class RequestLifecycleMachine:
    """Persist one atomic state machine record per physical request attempt."""

    def __init__(self, path: Path, *, secret: str) -> None:
        self.path = path.resolve()
        self.secret = secret
        self.attempts: list[dict[str, Any]] = []
        self._checkpoint()

    @classmethod
    def load(cls, path: Path, *, secret: str) -> RequestLifecycleMachine:
        """Reconstruct without writing or changing the preserved lifecycle."""

        resolved = path.resolve()
        value = json.loads(resolved.read_text(encoding="utf-8"))
        attempts = value.get("attempts") if isinstance(value, dict) else None
        if not isinstance(attempts, list) or not all(
            isinstance(row, dict) for row in attempts
        ):
            raise ConfigurationError("Request lifecycle is malformed")
        result = cls.__new__(cls)
        result.path = resolved
        result.secret = secret
        result.attempts = attempts
        verification = result.verify()
        if not verification["passed"]:
            raise ConfigurationError(
                "Request lifecycle is invalid: " + ", ".join(verification["faults"])
            )
        return result

    def _checkpoint(self) -> None:
        value = redact_credentials(
            {
                "schema_version": "uc-bench-case1-pilot-v1-rc6-request-lifecycle-1",
                "attempt_count": len(self.attempts),
                "completed_response_count": sum(
                    row["state"] == "completed_response" for row in self.attempts
                ),
                "attempts": self.attempts,
            },
            secret=self.secret,
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
        temporary.replace(self.path)

    def active(self) -> dict[str, Any] | None:
        rows = [row for row in self.attempts if row["state"] == "pending"]
        if len(rows) > 1:
            raise ConfigurationError("More than one provider attempt is pending")
        return rows[0] if rows else None

    def begin(self, *, body: dict[str, Any]) -> int:
        if self.active() is not None:
            raise ConfigurationError("Previous provider attempt is still pending")
        body_hash = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest()
        retry_index = 0
        logical_request_index = 0
        if self.attempts:
            previous = self.attempts[-1]
            logical_request_index = int(previous["logical_request_index"]) + 1
            if previous["state"] in {
                "transient_transport_failure",
                "provider_response_parse_failure",
            }:
                if previous["request_body_sha256"] != body_hash:
                    raise ConfigurationError("Safe retry changed the pending request body")
                if int(previous["retry_index"]) != 0:
                    raise ConfigurationError("Only one identical provider retry is allowed")
                retry_index = 1
                logical_request_index = int(previous["logical_request_index"])
        attempt_id = len(self.attempts)
        self.attempts.append(
            {
                "attempt_id": attempt_id,
                "logical_request_index": logical_request_index,
                "retry_index": retry_index,
                "request_body_sha256": body_hash,
                "state": "pending",
                "response_received": False,
                "ledger_request_index": None,
                "transition_history": ["pending"],
                "started_at": datetime.now(UTC).isoformat(),
                "ended_at": None,
                "error_chain": [],
            }
        )
        self._checkpoint()
        return attempt_id

    def mark_response_received(self, attempt_id: int, *, raw_body_sha256: str) -> None:
        row = self.attempts[attempt_id]
        if row["state"] != "pending":
            raise ConfigurationError("Only a pending request may receive a response")
        row["response_received"] = True
        row["raw_body_sha256"] = raw_body_sha256
        self._checkpoint()

    def transition(
        self,
        attempt_id: int,
        state: str,
        *,
        ledger_request_index: int | None = None,
        error: BaseException | None = None,
    ) -> None:
        if state not in TERMINAL_ATTEMPT_STATES:
            raise ConfigurationError(f"Invalid terminal request state: {state}")
        row = self.attempts[attempt_id]
        if row["state"] != "pending":
            raise ConfigurationError("A request attempt may terminate exactly once")
        if state == "completed_response" and not row.get("response_received"):
            raise ConfigurationError("A completed response requires received bytes")
        if state in {"transient_transport_failure", "terminal_provider_failure"} and row.get(
            "response_received"
        ):
            raise ConfigurationError("A no-response provider state cannot contain response bytes")
        row["state"] = state
        row["ledger_request_index"] = ledger_request_index
        row["transition_history"].append(state)
        row["ended_at"] = datetime.now(UTC).isoformat()
        if error is not None:
            row["error_chain"] = serialized_exception_chain(error, secret=self.secret)
        self._checkpoint()

    def cancel_pending(self) -> None:
        row = self.active()
        if row is not None:
            self.transition(int(row["attempt_id"]), "cancelled_before_execution")

    def reconcile_response_failure(self, ledger: DurableRequestLedger) -> None:
        row = self.active()
        if row is None or not row.get("response_received"):
            return
        ledger_index = len(ledger.records) - 1
        record = ledger.records[ledger_index] if ledger_index >= 0 else {}
        error = record.get("error") if isinstance(record, dict) else None
        classification = error.get("classification") if isinstance(error, dict) else None
        state = (
            "provider_response_parse_failure"
            if classification == "provider_adapter_failure"
            else "terminal_provider_failure"
        )
        self.transition(int(row["attempt_id"]), state, ledger_request_index=ledger_index)

    def verify(self) -> dict[str, Any]:
        faults: list[str] = []
        for expected_id, row in enumerate(self.attempts):
            if row.get("attempt_id") != expected_id:
                faults.append("attempt_id_sequence_invalid")
            if row.get("state") not in ATTEMPT_STATES:
                faults.append("unknown_attempt_state")
            history = row.get("transition_history")
            if not isinstance(history, list) or not history or history[0] != "pending":
                faults.append("transition_history_invalid")
            if row.get("state") != "pending" and history != ["pending", row.get("state")]:
                faults.append("attempt_not_terminal_exactly_once")
        active = [row for row in self.attempts if row.get("state") == "pending"]
        if len(active) > 1 or (active and active[0] is not self.attempts[-1]):
            faults.append("pending_attempt_position_invalid")
        return {
            "passed": not faults,
            "faults": list(dict.fromkeys(faults)),
            "attempt_count": len(self.attempts),
            "completed_response_count": sum(
                row.get("state") == "completed_response" for row in self.attempts
            ),
            "pending_count": len(active),
        }


class RC6RequestLedger(DurableRequestLedger):
    """Preserve full-chain provider classification alongside the canonical ledger."""

    def record_error(self, error: BaseException, *, latency_seconds: float) -> dict[str, Any]:
        row = super().record_error(error, latency_seconds=latency_seconds)
        row["error"]["exception_chain"] = serialized_exception_chain(
            error, secret=self._secret
        )
        if transient_failure(error):
            row["error"]["classification"] = "transient_transport_failure"
            if any("timeout" in item["type"].lower() for item in row["error"]["exception_chain"]):
                row["error"]["provider_subtype"] = "timeout"
        self._checkpoint()
        return row


class LifecycleTransportProxy:
    """Observe the exact native post without changing its arguments."""

    def __init__(
        self,
        native: Any,
        *,
        lifecycle: RequestLifecycleMachine,
        ledger: RC6RequestLedger,
    ) -> None:
        self._native = native
        self._lifecycle = lifecycle
        self._ledger = ledger

    def __getattr__(self, name: str) -> Any:
        return getattr(self._native, name)

    async def post(self, path: str, **kwargs: Any) -> Any:
        self._lifecycle.reconcile_response_failure(self._ledger)
        body = kwargs.get("body")
        if not isinstance(body, dict):
            raise ConfigurationError("Scientific provider request body must be an object")
        attempt_id = self._lifecycle.begin(body=body)
        try:
            response = await self._native.post(path, **kwargs)
        except Exception as exc:
            state = (
                "transient_transport_failure"
                if transient_failure(exc)
                else "terminal_provider_failure"
            )
            self._lifecycle.transition(attempt_id, state, error=exc)
            raise
        raw = bytes(getattr(response, "content", b""))
        self._lifecycle.mark_response_received(
            attempt_id, raw_body_sha256=hashlib.sha256(raw).hexdigest()
        )
        return response


def lifecycle_identity(
    *,
    requested_model: str,
    canonical_alias: str,
    pinned_provider: str,
    fallback_disabled: bool,
    ledger: DurableRequestLedger,
    lifecycle: RequestLifecycleMachine,
) -> dict[str, Any]:
    """Fail closed on identity, but only for completed responses."""

    completed = [
        row for row in lifecycle.attempts if row.get("state") == "completed_response"
    ]
    observations: list[dict[str, Any]] = []
    faults: list[str] = []
    allowed = {requested_model, canonical_alias}
    if not fallback_disabled:
        faults.append("fallback_not_disabled")
    for attempt in completed:
        index = attempt.get("ledger_request_index")
        record = (
            ledger.records[index]
            if isinstance(index, int) and 0 <= index < len(ledger.records)
            else {}
        )
        model = record.get("returned_model")
        provider = record.get("actual_provider")
        local: list[str] = []
        if model not in allowed:
            local.append("missing_or_unexpected_model_identity")
        if provider != pinned_provider:
            local.append("missing_or_unexpected_provider_identity")
        if record.get("allow_fallbacks") is not False:
            local.append("fallback_or_provider_drift")
        faults.extend(f"attempt_{attempt['attempt_id']}:{item}" for item in local)
        observations.append(
            {
                "attempt_id": attempt["attempt_id"],
                "ledger_request_index": index,
                "returned_model": model,
                "returned_provider": provider,
                "faults": local,
            }
        )
    return {
        "schema_version": "uc-bench-case1-pilot-v1-rc6-identity-1",
        "requested_model": requested_model,
        "accepted_exact_models": sorted(allowed),
        "pinned_provider": pinned_provider,
        "fallback_disabled": fallback_disabled,
        "attempted_request_count": len(lifecycle.attempts),
        "completed_response_count": len(completed),
        "expected_identity_evidence_count": len(completed),
        "observed_identity_evidence_count": len(observations),
        "compatible": not faults and len(observations) == len(completed),
        "faults": list(dict.fromkeys(faults)),
        "observations": observations,
    }


def lifecycle_cost(ledger: DurableRequestLedger) -> float:
    value = float(ledger.cumulative_reported_cost_usd)
    if not math.isfinite(value) or value < 0:
        raise ConfigurationError("Provider ledger cost must be finite and non-negative")
    return value


def forensic_legacy_request_adjudication(
    *,
    ledger_rows: list[dict[str, Any]],
    requested_model: str,
    canonical_alias: str,
    pinned_provider: str,
) -> dict[str, Any]:
    """Adjudicate an archived ledger without rewriting or pretending to resume it."""

    completed = [row for row in ledger_rows if row.get("error") is None]
    failed = [row for row in ledger_rows if row.get("error") is not None]
    identity_faults: list[str] = []
    allowed = {requested_model, canonical_alias}
    for index, row in enumerate(completed):
        if row.get("returned_model") not in allowed:
            identity_faults.append(f"completed_{index}:model_identity")
        if row.get("actual_provider") != pinned_provider:
            identity_faults.append(f"completed_{index}:provider_identity")
        if row.get("allow_fallbacks") is not False:
            identity_faults.append(f"completed_{index}:fallback")
    terminal = failed[-1] if failed else None
    terminal_error = terminal.get("error") if isinstance(terminal, dict) else None
    timeout = bool(
        isinstance(terminal_error, dict)
        and (
            "timeout" in str(terminal_error.get("type") or "").lower()
            or str(terminal_error.get("message") or "").strip().lower()
            == "request timed out."
        )
    )
    return {
        "attempted_request_count": len(ledger_rows),
        "completed_response_count": len(completed),
        "identity_evidence_count": len(completed),
        "identity_compatible": not identity_faults,
        "identity_faults": identity_faults,
        "terminal_state": "transient_transport_failure" if timeout else (
            "terminal_provider_failure" if terminal is not None else None
        ),
        "classification": (
            "isolated_provider_timeout"
            if timeout
            else "isolated_provider_failure"
            if terminal is not None
            else "completed_responses"
        ),
        "scientific_score": None if terminal is not None else "not_adjudicated",
        "reliability": None if terminal is not None else "not_adjudicated",
    }


def matrix_stop_level(classification: str, *, repeated_identity_drift: bool = False) -> str:
    """Return the predeclared containment level for a completed cell."""

    global_failures = {
        "shared_grade_affecting_evaluator_defect",
        "shared_harness_corruption",
        "release_mutation",
        "credential_leakage",
        "protected_evidence_mutation",
        "cost_cap_breach",
        "cross_case_evidence_exposure",
    }
    if repeated_identity_drift or classification in global_failures:
        return "global_stop"
    if classification in {
        "isolated_provider_timeout",
        "isolated_provider_failure",
        "provider_adapter_failure",
        "provider_policy_refusal",
        "provider_identity_failure",
    }:
        return "cell_exclusion_continue_panel"
    return "continue_panel"


__all__ = [
    "ATTEMPT_STATES",
    "LifecycleTransportProxy",
    "RC6RequestLedger",
    "RequestLifecycleMachine",
    "exception_chain",
    "lifecycle_cost",
    "lifecycle_identity",
    "forensic_legacy_request_adjudication",
    "matrix_stop_level",
    "serialized_exception_chain",
    "transient_failure",
]

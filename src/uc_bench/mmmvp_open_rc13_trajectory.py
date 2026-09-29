"""RC1.3 framework-error lifecycle capture over immutable RC1.2 science."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.durable_trajectory import (
    TrajectoryPersistenceError,
    _assistant_message,
    _message_rows,
    _tool_call_facts,
    durable_wrapped_tools,
    redact_host_record,
)
from uc_bench.mmmvp_open_environment import mmmvp_open_tool_functions
from uc_bench.mmmvp_open_rc12_environment import RC12OpenMMMVPEnvironment
from uc_bench.mmmvp_open_rc12_trajectory import (
    ACTIVE_TOOL_STATUS,
    ERRORED_TOOL_STATUS,
    EXECUTED_TOOL_STATUS,
    TERMINAL_TOOL_STATUSES,
    RC12DurableTrajectoryStore,
    _tool_lifecycle_faults,
    rc12_trajectory_replay_check,
)
from uc_bench.v071_auth import redact_exception_message

FRAMEWORK_ERROR_CLASSES = frozenset(
    {"tool_argument_parse_error", "tool_dispatch_error"}
)
_CURRENT_TOOL_CALL_ID: ContextVar[str | None] = ContextVar(
    "uc_bench_rc13_tool_call_id", default=None
)


@contextmanager
def rc13_tool_call_context(tool_call_id: str) -> Iterator[None]:
    """Bind the exact provider call ID while the framework invokes a wrapper."""

    token = _CURRENT_TOOL_CALL_ID.set(str(tool_call_id))
    try:
        yield
    finally:
        _CURRENT_TOOL_CALL_ID.reset(token)


def _tool_result_rows(messages: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [dict(row) for row in messages if row.get("role") == "tool"]


def _call_ids_from_messages(messages: Sequence[Mapping[str, Any]]) -> list[str]:
    result: list[str] = []
    for message in messages:
        if message.get("role") != "assistant":
            continue
        for raw in message.get("tool_calls") or []:
            if not isinstance(raw, Mapping):
                continue
            result.append(str(raw.get("id")))
    return result


def _framework_error_class(
    call: Mapping[str, Any], *, known_tool_names: frozenset[str]
) -> str:
    raw = call.get("arguments_raw", "{}")
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError, ValueError):
        return "tool_argument_parse_error"
    if not isinstance(parsed, Mapping):
        return "tool_argument_parse_error"
    if str(call.get("name") or "") not in known_tool_names:
        return "tool_dispatch_error"
    # The wrapper did not run even though the call was syntactically valid and
    # named a disclosed tool.  This is still a framework dispatch failure.
    return "tool_dispatch_error"


class RC13DurableTrajectoryStore(RC12DurableTrajectoryStore):
    """Close framework-generated tool errors by exact provider call ID."""

    def _all_provider_calls(self) -> list[dict[str, Any]]:
        return [
            call
            for exchange in self._provider_exchanges
            for call in exchange.get("tool_calls") or []
        ]

    def _provider_call_by_id(self, tool_call_id: str) -> dict[str, Any]:
        matches = [
            call
            for call in self._all_provider_calls()
            if str(call.get("tool_call_id")) == str(tool_call_id)
        ]
        if len(matches) != 1:
            raise TrajectoryPersistenceError(
                f"Tool result ID {tool_call_id!r} matched {len(matches)} provider calls"
            )
        return matches[0]

    def record_model_response(
        self,
        *,
        prompt: Any,
        response: Any,
        ledger: Any,
    ) -> dict[str, Any]:
        """Reject duplicate call IDs before they can enter the durable journal."""

        _, assistant = _assistant_message(response)
        new_calls = _tool_call_facts(assistant)
        new_ids = [str(call.get("tool_call_id")) for call in new_calls]
        prior_ids = {
            str(call.get("tool_call_id")) for call in self._all_provider_calls()
        }
        duplicates = sorted(
            {
                call_id
                for call_id, count in Counter(new_ids).items()
                if count != 1
            }
            | (set(new_ids) & prior_ids)
        )
        if duplicates:
            raise TrajectoryPersistenceError(
                "Duplicate provider tool-call ID: " + ", ".join(duplicates)
            )
        return super().record_model_response(prompt=prompt, response=response, ledger=ledger)

    def _claim_active_call_by_id(self, tool_call_id: str, name: str) -> dict[str, Any]:
        call = self._provider_call_by_id(tool_call_id)
        if call.get("status") != ACTIVE_TOOL_STATUS:
            raise TrajectoryPersistenceError(
                f"Tool call {tool_call_id!r} is not pending_recoverable"
            )
        if call.get("name") != name:
            raise TrajectoryPersistenceError(
                f"Tool call {tool_call_id!r} names {call.get('name')!r}, not {name!r}"
            )
        return call

    def record_tool_action(
        self,
        *,
        name: str,
        invocation_arguments: Mapping[str, Any],
        result: Any,
        error: BaseException | None,
        ledger: Any,
    ) -> dict[str, Any]:
        """Persist ordinary wrapper execution using the exact framework call ID."""

        call_id = _CURRENT_TOOL_CALL_ID.get()
        if not call_id:
            raise TrajectoryPersistenceError(
                f"Tool wrapper {name!r} was entered without an exact tool-call ID"
            )
        call = self._claim_active_call_by_id(call_id, name)
        content = (
            str(result)
            if error is None
            else redact_exception_message(error, secret=self.secret)
        )
        call["status"] = EXECUTED_TOOL_STATUS if error is None else ERRORED_TOOL_STATUS
        call["wrapper_entered"] = True
        if error is not None:
            call["error_class"] = "tool_wrapper_error"
            call["error_result"] = content
        self._synchronize_provider_call(call)
        action = {
            "action_index": len(self._tool_actions),
            "tool_call_id": call_id,
            "name": name,
            "provider_arguments": call.get("arguments"),
            "original_raw_arguments": call.get("arguments_raw"),
            "invocation_arguments": dict(invocation_arguments),
            "result": result if error is None else None,
            "tool_result_content": content,
            "wrapper_entered": True,
            "framework_generated": False,
            "error_class": None if error is None else "tool_wrapper_error",
            "error": (
                None
                if error is None
                else {"type": type(error).__name__, "message": content}
            ),
        }
        self._tool_actions.append(action)
        self._messages.append(
            {"role": "tool", "tool_call_id": call_id, "content": content}
        )
        return self._persist("tool_action", action, ledger)

    def reconcile_framework_tool_results(
        self,
        prompt: Any,
        *,
        ledger: Any,
        known_tool_names: frozenset[str],
    ) -> dict[str, Any] | None:
        """Atomically capture tool errors produced before a wrapper was entered."""

        rows = _message_rows(prompt)
        results = _tool_result_rows(rows)
        result_counts = Counter(str(row.get("tool_call_id")) for row in results)
        duplicate_results = sorted(
            call_id for call_id, count in result_counts.items() if count != 1
        )
        if duplicate_results:
            raise TrajectoryPersistenceError(
                "Duplicate tool-result ID: " + ", ".join(duplicate_results)
            )

        call_ids = _call_ids_from_messages(rows)
        duplicate_calls = sorted(
            call_id for call_id, count in Counter(call_ids).items() if count != 1
        )
        if duplicate_calls:
            raise TrajectoryPersistenceError(
                "Duplicate assistant tool-call ID: " + ", ".join(duplicate_calls)
            )

        stored_results = {
            str(row.get("tool_call_id")): row
            for row in _tool_result_rows(self._messages)
        }
        actions_by_id = {
            str(action.get("tool_call_id")): action for action in self._tool_actions
        }
        captured: list[dict[str, Any]] = []
        for result in results:
            call_id = str(result.get("tool_call_id"))
            call = self._provider_call_by_id(call_id)
            status = str(call.get("status"))
            content = redact_host_record(result.get("content"), secret=self.secret)
            if status == ACTIVE_TOOL_STATUS:
                if call_id in stored_results or call_id in actions_by_id:
                    raise TrajectoryPersistenceError(
                        f"Pending tool call {call_id!r} already has a result or action"
                    )
                error_class = _framework_error_class(
                    call, known_tool_names=known_tool_names
                )
                call.update(
                    {
                        "status": ERRORED_TOOL_STATUS,
                        "error_class": error_class,
                        "error_result": content,
                        "wrapper_entered": False,
                        "framework_generated": True,
                        "closed_at": datetime.now(UTC).isoformat(),
                    }
                )
                self._synchronize_provider_call(call)
                action = {
                    "action_index": len(self._tool_actions),
                    "provider_call_index": call.get("index"),
                    "tool_call_id": call_id,
                    "name": call.get("name"),
                    "provider_arguments": call.get("arguments"),
                    "original_raw_arguments": call.get("arguments_raw"),
                    "invocation_arguments": None,
                    "result": None,
                    "tool_result_content": content,
                    "wrapper_entered": False,
                    "framework_generated": True,
                    "error_class": error_class,
                    "error": {"type": error_class, "message": content},
                }
                self._tool_actions.append(action)
                actions_by_id[call_id] = action
                captured.append(action)
            elif status in {EXECUTED_TOOL_STATUS, ERRORED_TOOL_STATUS}:
                stored = stored_results.get(call_id)
                if stored is None or stored.get("content") != result.get("content"):
                    raise TrajectoryPersistenceError(
                        f"Tool result for {call_id!r} conflicts with its durable result"
                    )
            elif status in TERMINAL_TOOL_STATUSES:
                raise TrajectoryPersistenceError(
                    f"Terminal unexecuted call {call_id!r} unexpectedly has a result"
                )
            else:
                raise TrajectoryPersistenceError(
                    f"Unknown tool lifecycle status {status!r} for {call_id!r}"
                )

        if not captured:
            return None
        # The framework prompt is the exact ordering shown to the model.  Adopt
        # it only in the same atomic record that closes every captured error.
        self._messages = rows
        event = {
            "error_count": len(captured),
            "tool_call_ids": [row["tool_call_id"] for row in captured],
            "errors": captured,
            "workspace_or_scientific_state_changed": False,
        }
        return self._persist("framework_tool_errors_reconciled", event, ledger)

    def assert_provider_request_lifecycle(self, prompt: Any) -> None:
        """Fail closed before a request unless calls and results are one-to-one."""

        rows = _message_rows(prompt)
        message_call_ids = _call_ids_from_messages(rows)
        result_rows = _tool_result_rows(rows)
        result_ids = [str(row.get("tool_call_id")) for row in result_rows]
        if any(count != 1 for count in Counter(message_call_ids).values()):
            raise TrajectoryPersistenceError("Provider prompt contains duplicate tool-call IDs")
        if any(count != 1 for count in Counter(result_ids).values()):
            raise TrajectoryPersistenceError("Provider prompt contains duplicate tool-result IDs")

        positions: dict[str, int] = {}
        for index, message in enumerate(rows):
            if message.get("role") == "assistant":
                for raw in message.get("tool_calls") or []:
                    if isinstance(raw, Mapping):
                        positions[str(raw.get("id"))] = index
            elif message.get("role") == "tool":
                call_id = str(message.get("tool_call_id"))
                if call_id not in positions or positions[call_id] >= index:
                    raise TrajectoryPersistenceError(
                        f"Tool result {call_id!r} has no earlier matching call"
                    )

        all_calls = self._all_provider_calls()
        stored_call_ids = [str(call.get("tool_call_id")) for call in all_calls]
        if any(count != 1 for count in Counter(stored_call_ids).values()):
            raise TrajectoryPersistenceError("Durable history contains duplicate tool-call IDs")
        if set(message_call_ids) != set(stored_call_ids):
            raise TrajectoryPersistenceError(
                "Provider prompt call IDs differ from the durable provider history"
            )
        if set(result_ids) - set(stored_call_ids):
            raise TrajectoryPersistenceError("Provider prompt has a result without a call")

        actions_by_id: dict[str, list[dict[str, Any]]] = {}
        for action in self._tool_actions:
            actions_by_id.setdefault(str(action.get("tool_call_id")), []).append(action)
        for call in all_calls:
            call_id = str(call.get("tool_call_id"))
            status = str(call.get("status"))
            action_count = len(actions_by_id.get(call_id, []))
            result_count = result_ids.count(call_id)
            if status in {EXECUTED_TOOL_STATUS, ERRORED_TOOL_STATUS}:
                if action_count != 1 or result_count != 1:
                    raise TrajectoryPersistenceError(
                        f"Closed call {call_id!r} must have exactly one action and result"
                    )
            elif status == ACTIVE_TOOL_STATUS:
                if result_count:
                    raise TrajectoryPersistenceError(
                        f"Pending call {call_id!r} already has a result"
                    )
                raise TrajectoryPersistenceError(
                    f"Pending call {call_id!r} lacks a framework result before request"
                )
            elif status in TERMINAL_TOOL_STATUSES:
                raise TrajectoryPersistenceError(
                    f"A provider request cannot follow terminal call {call_id!r}"
                )
            else:
                raise TrajectoryPersistenceError(
                    f"Unknown tool lifecycle status {status!r} for {call_id!r}"
                )


def rc13_durable_tool_functions(
    docker: Any,
    core: RC12OpenMMMVPEnvironment,
    store: RC13DurableTrajectoryStore,
    ledger: Any,
) -> list[Any]:
    """Observe the byte-identical public tool surface with exact call IDs."""

    return durable_wrapped_tools(mmmvp_open_tool_functions(docker, core), store, ledger)


def rc13_trajectory_replay_check(
    project_root: Path,
    workspace: Path,
    store: RC13DurableTrajectoryStore,
    *,
    condition_id: str,
    grade: dict[str, Any] | None,
    stop_condition: str | None,
) -> dict[str, Any]:
    """Apply RC1.2 replay plus RC1.3 framework-error invariants."""

    result = rc12_trajectory_replay_check(
        project_root,
        workspace,
        store,
        condition_id=condition_id,
        grade=grade,
        stop_condition=stop_condition,
    )
    latest = store.latest()
    extra_faults: list[str] = []
    framework_actions = [
        action
        for action in latest.get("tool_actions") or []
        if action.get("framework_generated")
    ]
    for action in framework_actions:
        call_id = str(action.get("tool_call_id"))
        if action.get("wrapper_entered") is not False:
            extra_faults.append(f"framework_error_entered_wrapper:{call_id}")
        if action.get("error_class") not in FRAMEWORK_ERROR_CLASSES:
            extra_faults.append(f"invalid_framework_error_class:{call_id}")
        if not action.get("error") or action.get("result") is not None:
            extra_faults.append(f"invalid_framework_error_action:{call_id}")
    lifecycle_faults, _ = _tool_lifecycle_faults(
        latest, stop_condition=stop_condition
    )
    extra_faults.extend(fault for fault in lifecycle_faults if fault not in result["faults"])
    faults = [*result["faults"], *extra_faults]
    return {
        **result,
        "passed": not faults,
        "faults": faults,
        "framework_tool_error_count": len(framework_actions),
        "framework_tool_error_classes": dict(
            Counter(str(action.get("error_class")) for action in framework_actions)
        ),
        "wrapper_tool_error_count": sum(
            bool(action.get("error")) and not action.get("framework_generated")
            for action in latest.get("tool_actions") or []
        ),
    }


__all__ = [
    "FRAMEWORK_ERROR_CLASSES",
    "RC13DurableTrajectoryStore",
    "rc13_durable_tool_functions",
    "rc13_tool_call_context",
    "rc13_trajectory_replay_check",
]

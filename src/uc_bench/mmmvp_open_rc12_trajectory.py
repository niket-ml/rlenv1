"""RC1.2 durable tool lifecycle and replay semantics."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.durable_trajectory import (
    DurableTrajectoryStore,
    TrajectoryPersistenceError,
    _assistant_message,
    _message_rows,
    _tool_call_facts,
    durable_wrapped_tools,
    redact_host_record,
    workspace_manifest,
)
from uc_bench.hashing import canonical_sha256
from uc_bench.mmmvp_open_environment import OpenEpisodeState, mmmvp_open_tool_functions
from uc_bench.mmmvp_open_rc12_environment import RC12OpenMMMVPEnvironment
from uc_bench.mmmvp_open_verifier import verify_open_submission
from uc_bench.v071_auth import redact_exception_message

ACTIVE_TOOL_STATUS = "pending_recoverable"
EXECUTED_TOOL_STATUS = "executed"
ERRORED_TOOL_STATUS = "errored"
TERMINAL_TOOL_STATUSES = frozenset(
    {"unexecuted_horizon", "unexecuted_cost_boundary", "unexecuted_timeout"}
)
ALL_TOOL_STATUSES = frozenset(
    {ACTIVE_TOOL_STATUS, EXECUTED_TOOL_STATUS, ERRORED_TOOL_STATUS, *TERMINAL_TOOL_STATUSES}
)


class RC12DurableTrajectoryStore(DurableTrajectoryStore):
    """Persist explicit active, executed, errored, and terminal tool states."""

    def record_model_response(
        self,
        *,
        prompt: Any,
        response: Any,
        ledger: Any,
    ) -> dict[str, Any]:
        raw_response, assistant = _assistant_message(response)
        prompt_rows = _message_rows(prompt)
        reasoning = {
            field: assistant[field]
            for field in ("reasoning", "reasoning_content", "reasoning_details")
            if assistant.get(field) is not None
        }
        calls = _tool_call_facts(assistant)
        for call in calls:
            call["status"] = ACTIVE_TOOL_STATUS
        self._messages = [*prompt_rows, assistant]
        self._pending_tool_calls = calls
        exchange = {
            "request_index": len(self._provider_exchanges),
            "prompt": prompt_rows,
            "assistant_output": assistant.get("content"),
            "reasoning_state_payload": reasoning,
            "tool_calls": calls,
            "raw_response": raw_response,
        }
        self._provider_exchanges.append(exchange)
        return self._persist("model_response", exchange, ledger)

    def _claim_active_call(self, name: str) -> dict[str, Any]:
        for call in self._pending_tool_calls:
            if call.get("status") == ACTIVE_TOOL_STATUS and call.get("name") == name:
                return call
        raise TrajectoryPersistenceError(
            f"Tool action {name!r} has no pending_recoverable provider tool call"
        )

    def _synchronize_provider_call(self, call: Mapping[str, Any]) -> None:
        """Keep reopened current-call and exchange copies semantically identical."""

        snapshot = dict(call)
        call_id = str(call.get("tool_call_id"))
        matches = [
            exchange_call
            for exchange in self._provider_exchanges
            for exchange_call in exchange.get("tool_calls") or []
            if str(exchange_call.get("tool_call_id")) == call_id
        ]
        if len(matches) != 1:
            raise TrajectoryPersistenceError(
                f"Tool call {call_id!r} does not have exactly one provider exchange"
            )
        if matches[0] is not call:
            matches[0].clear()
            matches[0].update(snapshot)

    def record_tool_action(
        self,
        *,
        name: str,
        invocation_arguments: Mapping[str, Any],
        result: Any,
        error: BaseException | None,
        ledger: Any,
    ) -> dict[str, Any]:
        call = self._claim_active_call(name)
        content = (
            str(result) if error is None else redact_exception_message(error, secret=self.secret)
        )
        call["status"] = EXECUTED_TOOL_STATUS if error is None else ERRORED_TOOL_STATUS
        self._synchronize_provider_call(call)
        action = {
            "action_index": len(self._tool_actions),
            "tool_call_id": call["tool_call_id"],
            "name": name,
            "provider_arguments": call.get("arguments"),
            "invocation_arguments": dict(invocation_arguments),
            "result": result if error is None else None,
            "tool_result_content": content,
            "error": (
                None if error is None else {"type": type(error).__name__, "message": content}
            ),
        }
        self._tool_actions.append(action)
        self._messages.append(
            {
                "role": "tool",
                "tool_call_id": call["tool_call_id"],
                "content": content,
            }
        )
        return self._persist("tool_action", action, ledger)

    def close_terminal_tool_calls(
        self,
        *,
        status: str,
        boundary_reason: str,
        ledger: Any,
    ) -> dict[str, Any] | None:
        """Close active final calls without executing them or changing episode state."""

        if status not in TERMINAL_TOOL_STATUSES:
            raise TrajectoryPersistenceError(f"Invalid terminal tool status: {status}")
        active = [
            call for call in self._pending_tool_calls if call.get("status") == ACTIVE_TOOL_STATUS
        ]
        if not active:
            return None
        before_state = self.core.state_dict()
        before_submission = self.core.export_submission()
        before_workspace = workspace_manifest(self.workspace)
        closed_at = datetime.now(UTC).isoformat()
        for call in active:
            call["status"] = status
            call["boundary_reason"] = boundary_reason
            call["closed_at"] = closed_at
            self._synchronize_provider_call(call)
        event = {
            "status": status,
            "boundary_reason": boundary_reason,
            "tool_call_ids": [call["tool_call_id"] for call in active],
            "tool_names": [call["name"] for call in active],
            "unexecuted_tool_count": len(active),
            "tool_executed": False,
            "resumable": False,
        }
        persisted = self._persist("terminal_tool_closure", event, ledger)
        if (
            self.core.state_dict() != before_state
            or self.core.export_submission() != before_submission
            or workspace_manifest(self.workspace) != before_workspace
        ):
            raise TrajectoryPersistenceError(
                "Closing a terminal tool call changed scientific or workspace state"
            )
        return persisted


def restore_rc12_environment(
    project_root: Path,
    workspace: Path,
    latest: Mapping[str, Any],
) -> RC12OpenMMMVPEnvironment:
    """Reconstruct RC1.2 without replaying a tool or irreversible action."""

    environment = latest.get("environment")
    if not isinstance(environment, Mapping):
        raise TrajectoryPersistenceError("Durable record lacks environment state")
    if environment.get("workspace_manifest") != workspace_manifest(workspace):
        raise TrajectoryPersistenceError("Workspace changed since the durable boundary")
    state_raw = environment.get("state")
    submission = environment.get("submission")
    if not isinstance(state_raw, Mapping) or not isinstance(submission, Mapping):
        raise TrajectoryPersistenceError("Durable record lacks RC1.2 episode state")

    restored = dict(state_raw)
    case_id = str(restored.pop("case_id"))
    mechanism = str(restored.pop("mechanism"))
    recoverable = int(restored.pop("recoverable_contract_violation_count", 0))
    mutation_attempted = bool(restored.pop("protected_evidence_mutation_attempted", False))
    boundary_enforced = bool(restored.pop("workspace_boundary_enforced", False))

    core = object.__new__(RC12OpenMMMVPEnvironment)
    core.project_root = project_root.resolve()
    core.case_id = case_id
    core.mechanism = mechanism
    core.run_root = workspace.resolve()
    core.records_root = Path(str(submission["host_record_locator"])).resolve()
    core.maximum_tool_calls = int(environment["maximum_tool_calls"])
    core.state = OpenEpisodeState(**restored)
    core._start_hashes = dict(environment["start_hashes"])  # noqa: SLF001
    core._protected_evidence_hashes = dict(  # noqa: SLF001
        submission.get("protected_evidence_hashes") or {}
    )
    core._validation_input_hashes = dict(  # noqa: SLF001
        submission.get("validation_input_hashes") or {}
    )
    core.recoverable_contract_violation_count = recoverable
    core.protected_evidence_mutation_attempted = mutation_attempted
    core.workspace_boundary_enforced = boundary_enforced
    if core.export_submission() != dict(submission):
        raise TrajectoryPersistenceError("Restored RC1.2 submission differs from durable state")
    return core


def rc12_durable_tool_functions(
    docker: Any,
    core: RC12OpenMMMVPEnvironment,
    store: RC12DurableTrajectoryStore,
    ledger: Any,
) -> list[Any]:
    """Persist every action from the byte-identical RC1 public tool surface."""

    return durable_wrapped_tools(mmmvp_open_tool_functions(docker, core), store, ledger)


def _assistant_tool_calls(latest: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    calls: dict[str, dict[str, Any]] = {}
    for message in latest.get("messages") or []:
        if message.get("role") != "assistant":
            continue
        for raw in message.get("tool_calls") or []:
            function = raw.get("function") or {}
            calls[str(raw.get("id"))] = {
                "name": str(function.get("name") or raw.get("name") or ""),
                "arguments_raw": function.get("arguments", "{}"),
            }
    return calls


def _last_assistant_tool_calls(latest: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    for message in reversed(latest.get("messages") or []):
        if message.get("role") != "assistant":
            continue
        result: dict[str, dict[str, Any]] = {}
        for raw in message.get("tool_calls") or []:
            function = raw.get("function") or {}
            result[str(raw.get("id"))] = {
                "name": str(function.get("name") or raw.get("name") or ""),
                "arguments_raw": function.get("arguments", "{}"),
            }
        return result
    return {}


def _tool_lifecycle_faults(
    latest: Mapping[str, Any],
    *,
    stop_condition: str | None,
) -> tuple[list[str], dict[str, Any]]:
    faults: list[str] = []
    current_calls = list(latest.get("pending_tool_calls") or [])
    all_calls = [
        call
        for exchange in latest.get("provider_exchanges") or []
        for call in exchange.get("tool_calls") or []
    ]
    statuses = [str(call.get("status")) for call in all_calls]
    unknown = sorted(set(statuses) - ALL_TOOL_STATUSES)
    if unknown:
        faults.append(f"unknown_tool_status:{','.join(unknown)}")
    active = [call for call in current_calls if call.get("status") == ACTIVE_TOOL_STATUS]
    terminal = [call for call in current_calls if call.get("status") in TERMINAL_TOOL_STATUSES]
    if active:
        faults.append("unexplained_mid_episode_pending_tool_call")

    assistant_calls = _assistant_tool_calls(latest)
    final_assistant_calls = _last_assistant_tool_calls(latest)
    actions_by_id: dict[str, list[dict[str, Any]]] = {}
    for action in latest.get("tool_actions") or []:
        actions_by_id.setdefault(str(action.get("tool_call_id")), []).append(action)
    results_by_id: dict[str, list[dict[str, Any]]] = {}
    for message in latest.get("messages") or []:
        if message.get("role") == "tool":
            results_by_id.setdefault(str(message.get("tool_call_id")), []).append(message)
    call_ids = [str(call.get("tool_call_id")) for call in all_calls]
    if len(call_ids) != len(set(call_ids)):
        faults.append("duplicate_provider_tool_call_id")
    unknown_action_ids = sorted(set(actions_by_id) - set(call_ids))
    unknown_result_ids = sorted(set(results_by_id) - set(call_ids))
    if unknown_action_ids:
        faults.append(f"tool_action_without_provider_call:{','.join(unknown_action_ids)}")
    if unknown_result_ids:
        faults.append(f"tool_result_without_provider_call:{','.join(unknown_result_ids)}")

    for call in all_calls:
        call_id = str(call.get("tool_call_id"))
        status = str(call.get("status"))
        actions = actions_by_id.get(call_id, [])
        results = results_by_id.get(call_id, [])
        assistant_call = assistant_calls.get(call_id)
        if assistant_call is None or assistant_call["name"] != call.get("name"):
            faults.append(f"provider_call_missing_from_messages:{call_id}")
        if status in {EXECUTED_TOOL_STATUS, ERRORED_TOOL_STATUS}:
            if len(actions) != 1 or len(results) != 1:
                faults.append(f"closed_call_action_result_count:{call_id}")
            elif actions[0].get("name") != call.get("name"):
                faults.append(f"tool_action_name_mismatch:{call_id}")
            elif (status == ERRORED_TOOL_STATUS) != bool(actions[0].get("error")):
                faults.append(f"tool_action_error_status_mismatch:{call_id}")
        elif actions or results:
            faults.append(f"unexecuted_or_active_call_has_result:{call_id}")
    expected_for_status = {
        "unexecuted_horizon": {
            "max_turns_reached",
            "max_total_completion_tokens_reached",
        },
        "unexecuted_cost_boundary": {"cost_cap_reached"},
        "unexecuted_timeout": {"timeout", "wall_clock_timeout"},
    }
    for call in terminal:
        call_id = str(call.get("tool_call_id"))
        provider_call = final_assistant_calls.get(call_id)
        if provider_call is None or provider_call["name"] != call.get("name"):
            faults.append(f"terminal_call_not_in_final_assistant:{call_id}")
        if call_id in actions_by_id or call_id in results_by_id:
            faults.append(f"unexecuted_call_has_result:{call_id}")
        if stop_condition not in expected_for_status[str(call["status"])]:
            faults.append(f"terminal_status_stop_mismatch:{call_id}")
        if call.get("boundary_reason") != stop_condition:
            faults.append(f"terminal_boundary_reason_mismatch:{call_id}")

    return faults, {
        "resume_boundary_available": bool(latest.get("messages")) and not terminal,
        "terminal_replay_available": bool(terminal),
        "unexecuted_terminal_tool_count": len(terminal),
        "terminal_tool_name": terminal[0].get("name") if len(terminal) == 1 else None,
        "terminal_boundary_reason": (
            terminal[0].get("boundary_reason") if len(terminal) == 1 else None
        ),
    }


def rc12_trajectory_replay_check(
    project_root: Path,
    workspace: Path,
    store: RC12DurableTrajectoryStore,
    *,
    condition_id: str,
    grade: dict[str, Any] | None,
    stop_condition: str | None,
) -> dict[str, Any]:
    """Verify persistence, state, and explicit boundary-tool consistency."""

    verification = store.verify(require_no_pending_tools=False)
    latest = store.latest()
    lifecycle_faults, lifecycle = _tool_lifecycle_faults(latest, stop_condition=stop_condition)
    faults = [*verification["faults"], *lifecycle_faults]
    restored: RC12OpenMMMVPEnvironment | None = None
    restored_grade: dict[str, Any] | None = None
    try:
        restored = restore_rc12_environment(project_root, workspace, latest)
        if restored.state.completion_accepted:
            restored_grade = verify_open_submission(
                project_root,
                workspace,
                restored.export_submission(),
                condition_id=condition_id,
            ).to_dict()
    except Exception as exc:
        faults.append(f"reconstruction:{type(exc).__name__}")

    if lifecycle["terminal_replay_available"]:
        previous_path = store.journal_root / f"{int(latest['sequence']) - 1:06d}.json"
        if not previous_path.is_file():
            faults.append("terminal_closure_missing_previous_record")
        else:
            previous = json.loads(previous_path.read_text(encoding="utf-8"))
            for field in ("state", "submission", "workspace_manifest"):
                if previous["environment"].get(field) != latest["environment"].get(field):
                    faults.append(f"terminal_closure_mutated:{field}")

    reconstructed = bool(
        restored is not None and restored.export_submission() == latest["environment"]["submission"]
    )
    return {
        **verification,
        "passed": not faults,
        "faults": faults,
        "reconstructed": reconstructed,
        "recomputed_grade_matches": restored_grade == grade,
        **lifecycle,
        "recoverable_contract_violation_count": (
            restored.recoverable_contract_violation_count if restored else None
        ),
        "protected_evidence_mutation_attempted": (
            restored.protected_evidence_mutation_attempted if restored else None
        ),
    }


def verify_archived_rc11_journal(host_root: Path) -> dict[str, Any]:
    """Verify an archived RC1.1 journal without opening it for mutation."""

    journal = host_root / "journal"
    paths = sorted(journal.glob("*.json"))
    faults: list[str] = []
    previous: str | None = None
    last: dict[str, Any] | None = None
    for expected, path in enumerate(paths, start=1):
        row = json.loads(path.read_text(encoding="utf-8"))
        stored = row.get("record_sha256")
        digest_value = dict(row)
        digest_value.pop("record_sha256", None)
        if int(row.get("sequence") or -1) != expected:
            faults.append(f"sequence:{path.name}")
        if row.get("previous_record_sha256") != previous:
            faults.append(f"chain:{path.name}")
        if stored != canonical_sha256(digest_value):
            faults.append(f"digest:{path.name}")
        previous = str(stored)
        last = row
    latest = json.loads((host_root / "latest.json").read_text(encoding="utf-8"))
    if last != latest:
        faults.append("latest_not_last_journal_record")
    workspace = host_root.parent / "workspace"
    if latest["environment"]["workspace_manifest"] != workspace_manifest(workspace):
        faults.append("workspace_manifest_mismatch")
    return {
        "passed": not faults,
        "faults": faults,
        "record_count": len(paths),
        "latest": latest,
    }


def archived_rc11_adjudication(run_root: Path) -> dict[str, Any]:
    """Apply RC1.2 lifecycle semantics to an immutable RC1.1 run in memory."""

    summary = json.loads((run_root / "run_summary.json").read_text(encoding="utf-8"))
    verification = verify_archived_rc11_journal(run_root / "host_trajectory")
    latest = verification.pop("latest")
    pending = [
        call for call in latest.get("pending_tool_calls") or [] if call.get("status") == "pending"
    ]
    stop = summary.get("stop_condition")
    terminal_status = None
    replay_health = verification["passed"]
    if pending and stop == "max_turns_reached":
        terminal_status = "unexecuted_horizon"
        assistant_calls = _assistant_tool_calls(latest)
        action_ids = {str(row.get("tool_call_id")) for row in latest.get("tool_actions") or []}
        result_ids = {
            str(row.get("tool_call_id"))
            for row in latest.get("messages") or []
            if row.get("role") == "tool"
        }
        for call in pending:
            call_id = str(call.get("tool_call_id"))
            replay_health = replay_health and call_id in assistant_calls
            replay_health = replay_health and call_id not in action_ids
            replay_health = replay_health and call_id not in result_ids
    elif pending:
        replay_health = False

    usable = int(summary.get("usable_provider_response_count") or 0)
    terminal_run = stop in {
        "no_tools_called",
        "max_turns_reached",
        "max_total_completion_tokens_reached",
        "timeout",
        "wall_clock_timeout",
        "cost_cap_reached",
    }
    return redact_host_record(
        {
            "schema_version": "uc-bench-open-mmmvp-rc1-2-archived-replay-1",
            "source_run": run_root.as_posix(),
            "source_summary_unchanged": True,
            "scientific_rescore": False,
            "source_classification": summary.get("classification"),
            "stop_condition": stop,
            "usable_provider_response_count": usable,
            "journal_health": verification,
            "trajectory_replay_health": replay_health,
            "resume_boundary_available": bool(latest.get("messages")) and not terminal_run,
            "terminal_replay_available": terminal_run and replay_health,
            "unexecuted_terminal_tool_count": len(pending) if terminal_status else 0,
            "terminal_tool_name": pending[0].get("name") if len(pending) == 1 else None,
            "terminal_boundary_reason": stop if terminal_status else None,
            "terminal_tool_status": terminal_status,
            "counterfactual_rc12_reliability": 0.0 if usable else None,
            "scientific_interpretation": (
                "environment_contaminated_by_rc11_path_errors"
                if summary.get("recoverable_contract_violation_count")
                else "usable_opportunity_completion_failure"
            ),
        },
        secret="",
    )


__all__ = [
    "ACTIVE_TOOL_STATUS",
    "ALL_TOOL_STATUSES",
    "ERRORED_TOOL_STATUS",
    "EXECUTED_TOOL_STATUS",
    "RC12DurableTrajectoryStore",
    "TERMINAL_TOOL_STATUSES",
    "archived_rc11_adjudication",
    "rc12_durable_tool_functions",
    "rc12_trajectory_replay_check",
    "restore_rc12_environment",
    "verify_archived_rc11_journal",
]

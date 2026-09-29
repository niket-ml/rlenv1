"""Authoritative lifecycle reconstruction for RC5 run reporting."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


class EmptyTrajectoryError(ValueError):
    """No durable provider response was ever committed."""


class CorruptTrajectoryError(ValueError):
    """A nonempty durable trajectory cannot be reconstructed exactly."""


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CorruptTrajectoryError(f"Malformed durable JSON: {path}") from exc
    if not isinstance(value, dict):
        raise CorruptTrajectoryError(f"JSON object required: {path}")
    return value


def _latest_journal_record(run_root: Path) -> dict[str, Any]:
    journal = run_root / "host_trajectory/journal"
    records = sorted(journal.glob("*.json"))
    if not records:
        raise EmptyTrajectoryError("durable trajectory journal is empty")
    values = [_read_object(path) for path in records]
    sequences: list[int] = []
    for row in values:
        sequence = row.get("sequence")
        if isinstance(sequence, bool) or not isinstance(sequence, int):
            raise CorruptTrajectoryError("durable trajectory sequence must be an integer")
        sequences.append(sequence)
    if sequences != list(range(1, len(values) + 1)):
        raise CorruptTrajectoryError("durable trajectory journal has a sequence gap")
    return values[-1]


def _nonnegative_cost(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CorruptTrajectoryError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise CorruptTrajectoryError(f"{label} must be finite and non-negative")
    return result


def _validated_event_names(
    environment: dict[str, Any],
    state: dict[str, Any],
    durable_tool_actions: list[dict[str, Any]],
) -> list[str]:
    events = state.get("event_log")
    mirrored = environment.get("event_record")
    if not isinstance(events, list) or not all(isinstance(row, dict) for row in events):
        raise CorruptTrajectoryError("durable event record must be a list of objects")
    if mirrored is not None and mirrored != events:
        raise CorruptTrajectoryError("durable event-record copies disagree")
    names: list[str] = []
    sequences: list[int] = []
    for row in events:
        event = row.get("event")
        sequence = row.get("sequence")
        if not isinstance(event, str) or not event:
            raise CorruptTrajectoryError("durable event name must be a nonempty string")
        if isinstance(sequence, bool) or not isinstance(sequence, int):
            raise CorruptTrajectoryError("durable event sequence must be an integer")
        names.append(event)
        sequences.append(sequence)
    if sequences != list(range(1, len(events) + 1)):
        raise CorruptTrajectoryError("durable environment events have a sequence gap")
    if not names or names[0] != "reset" or names.count("reset") != 1:
        raise CorruptTrajectoryError("durable lifecycle must begin with exactly one reset")

    irreversible = (
        "commit_validation_plan",
        "reveal_validation",
        "commit_followup_plan",
        "purchase_resource",
        "submit",
    )
    accepted = [name for name in names if name in irreversible]
    if accepted != list(irreversible[: len(accepted)]):
        raise CorruptTrajectoryError(
            "accepted irreversible actions are missing, duplicated, or out of order"
        )
    action_names = [row.get("name") for row in durable_tool_actions]
    if any(name not in action_names for name in accepted):
        raise CorruptTrajectoryError("accepted irreversible event lacks its durable tool action")
    return names


def reconstruct_lifecycle(run_root: Path) -> dict[str, Any]:
    """Derive lifecycle and conservative spend from durable host-only state."""

    run_root = run_root.resolve()
    latest = _latest_journal_record(run_root)
    environment = latest.get("environment")
    if not isinstance(environment, dict):
        raise CorruptTrajectoryError("durable environment state must be an object")
    state = environment.get("state")
    if not isinstance(state, dict):
        raise CorruptTrajectoryError("durable terminal state must be an object")
    durable_tool_actions = latest.get("tool_actions")
    if not isinstance(durable_tool_actions, list) or not all(
        isinstance(row, dict) for row in durable_tool_actions
    ):
        raise CorruptTrajectoryError("durable tool-action record must be a list of objects")
    names = _validated_event_names(environment, state, durable_tool_actions)
    events = state["event_log"]
    tool_events = [name for name in names if name.startswith("tool_")]
    purchase = next(
        (
            row
            for row in reversed(events)
            if isinstance(row, dict) and row.get("event") == "purchase_resource"
        ),
        None,
    )
    ledger = _read_object(run_root / "request_ledger.json")
    ledger_requests = ledger.get("requests")
    if not isinstance(ledger_requests, list) or not all(
        isinstance(row, dict) for row in ledger_requests
    ):
        raise CorruptTrajectoryError("provider request ledger must contain a list of objects")
    checkpointed = _nonnegative_cost(latest.get("cumulative_cost_usd"), "checkpointed cost")
    provider_ledger = _nonnegative_cost(
        ledger.get("cumulative_reported_cost_usd"), "provider-ledger cost"
    )
    completion_accepted = state.get("completion_accepted")
    if not isinstance(completion_accepted, bool):
        raise CorruptTrajectoryError("completion_accepted must be boolean")
    provider_exchanges = latest.get("provider_exchanges")
    if not isinstance(provider_exchanges, list) or not all(
        isinstance(row, dict) for row in provider_exchanges
    ):
        raise CorruptTrajectoryError("provider exchanges must be a list of objects")
    submitted = "submit" in names and completion_accepted
    terminal_reason = state.get("terminal_reason")
    if terminal_reason is not None and not isinstance(terminal_reason, str):
        raise CorruptTrajectoryError("terminal_reason must be a string or null")
    submission = environment.get("submission")
    if submission is not None and not isinstance(submission, dict):
        raise CorruptTrajectoryError("durable submission must be an object or null")
    final_submission = (submission or {}).get("final_submission")
    if final_submission is not None and not isinstance(final_submission, dict):
        raise CorruptTrajectoryError("durable final submission must be an object or null")
    submission_state = (submission or {}).get("state")
    if submission_state is not None and (
        not isinstance(submission_state, dict)
        or submission_state.get("completion_accepted") is not completion_accepted
    ):
        raise CorruptTrajectoryError("durable submission state disagrees with terminal state")
    phase = state.get("phase")
    mirrored_phase = environment.get("phase")
    if not isinstance(phase, str) or not phase:
        raise CorruptTrajectoryError("durable phase must be a nonempty string")
    if mirrored_phase is not None and mirrored_phase != phase:
        raise CorruptTrajectoryError("durable phase copies disagree")
    has_submit = "submit" in names
    if completion_accepted != has_submit:
        raise CorruptTrajectoryError("completion flag disagrees with accepted submit event")
    if completion_accepted and (
        phase != "terminal"
        or terminal_reason != "submitted"
        or not isinstance(final_submission, dict)
        or not isinstance(final_submission.get("decision"), dict)
    ):
        raise CorruptTrajectoryError("accepted submission lacks a consistent terminal payload")
    completion_state = "submitted" if submitted else str(terminal_reason or "incomplete")
    return {
        "journal_sequence": int(latest["sequence"]),
        "tools_called": len(durable_tool_actions),
        "tool_event_names": tool_events,
        "validation_committed": "commit_validation_plan" in names,
        "validation_revealed": "reveal_validation" in names,
        "followup_committed": "commit_followup_plan" in names,
        "resource_purchased": None if purchase is None else purchase.get("resource_id"),
        "submission_accepted": submitted,
        "final_decision": ((final_submission or {}).get("decision")),
        "provider_request_count": len(ledger_requests),
        "model_response_count": len(provider_exchanges),
        "turn_count": len(durable_tool_actions),
        "completion_state": completion_state,
        "reliability_score": 100.0 if submitted else 0.0,
        "checkpointed_spend_usd": checkpointed,
        "final_provider_ledger_spend_usd": provider_ledger,
        "budget_enforcement_spend_usd": max(checkpointed, provider_ledger),
        "event_sequence": names,
    }


def reconstruct_lifecycle_or_empty(run_root: Path) -> dict[str, Any]:
    """Return an explicit empty lifecycle only when its ledger is reconstructable."""

    try:
        return reconstruct_lifecycle(run_root)
    except EmptyTrajectoryError:
        ledger = _read_object(run_root.resolve() / "request_ledger.json")
        requests = ledger.get("requests")
        if not isinstance(requests, list) or not all(isinstance(row, dict) for row in requests):
            raise CorruptTrajectoryError(
                "provider request ledger must contain a list of objects"
            ) from None
        provider_cost = _nonnegative_cost(
            ledger.get("cumulative_reported_cost_usd"), "provider-ledger cost"
        )
        return {
            "journal_sequence": 0,
            "tools_called": 0,
            "tool_event_names": [],
            "validation_committed": False,
            "validation_revealed": False,
            "followup_committed": False,
            "resource_purchased": None,
            "submission_accepted": False,
            "final_decision": None,
            "provider_request_count": len(requests),
            "model_response_count": 0,
            "turn_count": 0,
            "completion_state": "no_durable_provider_response",
            "reliability_score": 0.0,
            "checkpointed_spend_usd": 0.0,
            "final_provider_ledger_spend_usd": provider_cost,
            "budget_enforcement_spend_usd": provider_cost,
            "event_sequence": [],
        }


__all__ = [
    "CorruptTrajectoryError",
    "EmptyTrajectoryError",
    "reconstruct_lifecycle",
    "reconstruct_lifecycle_or_empty",
]

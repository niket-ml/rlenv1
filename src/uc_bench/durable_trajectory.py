"""Host-only, atomic trajectory persistence for v0.8 development episodes.

This module is infrastructure.  It observes the existing v0.8 client and tool
surface without changing their prompts, schemas, scientific state transitions,
or grading rules.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import re
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from functools import wraps
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256
from uc_bench.v06_provider import _as_dict
from uc_bench.v07_environment import V07EpisodeState
from uc_bench.v071_auth import redact_exception_message
from uc_bench.v08_environment import V08Environment, v08_tool_functions

_OPENROUTER_KEY = re.compile(r"sk-or-v1-[A-Za-z0-9_-]+")
_BEARER = re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s\"']+")
_SECRET_KEYS = {
    "api-key",
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "credentials",
    "password",
    "secret",
}


class TrajectoryPersistenceError(RuntimeError):
    """The host could not durably record a continuation boundary."""


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json", exclude_none=False)
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    if hasattr(value, "__dict__"):
        return vars(value)
    return str(value)


def _redact_string(value: str, secret: str) -> str:
    redacted = value.replace(secret, "<redacted_openrouter_key>") if secret else value
    redacted = _OPENROUTER_KEY.sub("<redacted_openrouter_key>", redacted)
    return _BEARER.sub(r"\1<redacted_authorization>", redacted)


def redact_host_record(value: Any, *, secret: str) -> Any:
    """Return a JSON-safe deep copy with credentials removed by key and value."""

    rendered = json.dumps(value, default=_json_default, ensure_ascii=False)
    normalized = json.loads(rendered)

    def visit(item: Any) -> Any:
        if isinstance(item, str):
            return _redact_string(item, secret)
        if isinstance(item, list):
            return [visit(child) for child in item]
        if isinstance(item, dict):
            result: dict[str, Any] = {}
            for raw_key, child in item.items():
                key = str(raw_key)
                if key.lower().replace("_header", "") in _SECRET_KEYS:
                    result[key] = "<redacted_credential>"
                else:
                    result[key] = visit(child)
            return result
        return item

    return visit(normalized)


def _atomic_write_json(path: Path, value: Any) -> None:
    """Write one complete record through fsync and an atomic rename."""

    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        temporary.replace(path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary.exists():
            temporary.unlink()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def workspace_manifest(workspace: Path) -> dict[str, dict[str, Any]]:
    """Hash every agent-visible file without copying private content into the journal."""

    root = workspace.resolve()
    return {
        path.relative_to(root).as_posix(): {
            "sha256": _sha256(path),
            "bytes": path.stat().st_size,
        }
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }


def _message_rows(messages: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for message in messages or []:
        row = _as_dict(message)
        if row:
            rows.append(row)
        elif isinstance(message, Mapping):
            rows.append(dict(message))
        else:
            raise TrajectoryPersistenceError(
                f"Cannot serialize continuation message of type {type(message).__name__}"
            )
    return rows


def _assistant_message(raw_response: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    response = _as_dict(raw_response)
    choices = response.get("choices") or []
    if not choices or not isinstance(choices[0], Mapping):
        raise TrajectoryPersistenceError("Provider response has no serializable first choice")
    choice = dict(choices[0])
    message = choice.get("message")
    if not isinstance(message, Mapping):
        raise TrajectoryPersistenceError("Provider response has no serializable assistant message")
    assistant = dict(message)
    assistant.setdefault("role", "assistant")
    return response, assistant


def _tool_call_facts(assistant: Mapping[str, Any]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for index, raw in enumerate(assistant.get("tool_calls") or []):
        call = dict(raw) if isinstance(raw, Mapping) else _as_dict(raw)
        function = call.get("function")
        function = dict(function) if isinstance(function, Mapping) else call
        encoded_args = function.get("arguments", "{}")
        try:
            parsed_args = (
                json.loads(encoded_args) if isinstance(encoded_args, str) else encoded_args
            )
        except json.JSONDecodeError:
            parsed_args = None
        facts.append(
            {
                "index": index,
                "tool_call_id": str(call.get("id") or f"missing-id-{index}"),
                "name": str(function.get("name") or call.get("name") or ""),
                "arguments_raw": encoded_args,
                "arguments": parsed_args,
                "status": "pending",
            }
        )
    return facts


class DurableTrajectoryStore:
    """Append self-contained continuation records outside the mounted workspace."""

    def __init__(
        self,
        host_root: Path,
        *,
        workspace: Path,
        core: V08Environment,
        secret: str,
        run_metadata: Mapping[str, Any],
        create: bool = True,
    ) -> None:
        self.host_root = host_root.resolve()
        self.workspace = workspace.resolve()
        if self.workspace == self.host_root or self.workspace in self.host_root.parents:
            raise ConfigurationError("Host trajectory records must be outside the workspace")
        if self.workspace in self.host_root.parents:
            raise ConfigurationError("Host trajectory path is agent-visible")
        self.journal_root = self.host_root / "journal"
        self.latest_path = self.host_root / "latest.json"
        self.metadata_path = self.host_root / "metadata.json"
        self.core = core
        self.secret = secret
        self.run_metadata = dict(run_metadata)
        self._sequence = 0
        self._previous_digest: str | None = None
        self._messages: list[dict[str, Any]] = []
        self._provider_exchanges: list[dict[str, Any]] = []
        self._tool_actions: list[dict[str, Any]] = []
        self._pending_tool_calls: list[dict[str, Any]] = []
        if create:
            if self.host_root.exists():
                raise ConfigurationError(
                    f"Host trajectory directory already exists: {self.host_root}"
                )
            self.journal_root.mkdir(parents=True)
            os.chmod(self.host_root, 0o700)
            os.chmod(self.journal_root, 0o700)
            _atomic_write_json(
                self.metadata_path,
                redact_host_record(
                    {
                        "schema_version": "0.8-host-trajectory-metadata-1",
                        "created_at": datetime.now(UTC).isoformat(),
                        "workspace_mount_excludes_host_records": True,
                        "run_metadata": self.run_metadata,
                    },
                    secret=self.secret,
                ),
            )
        else:
            self._load()

    @classmethod
    def reopen(
        cls,
        host_root: Path,
        *,
        workspace: Path,
        core: V08Environment,
        secret: str,
    ) -> DurableTrajectoryStore:
        metadata = json.loads((host_root / "metadata.json").read_text(encoding="utf-8"))
        return cls(
            host_root,
            workspace=workspace,
            core=core,
            secret=secret,
            run_metadata=metadata.get("run_metadata") or {},
            create=False,
        )

    def _load(self) -> None:
        if not self.latest_path.is_file():
            raise TrajectoryPersistenceError("No durable continuation record exists")
        latest = json.loads(self.latest_path.read_text(encoding="utf-8"))
        self._sequence = int(latest["sequence"])
        self._previous_digest = str(latest["record_sha256"])
        self._messages = list(latest["messages"])
        self._provider_exchanges = list(latest["provider_exchanges"])
        self._tool_actions = list(latest["tool_actions"])
        self._pending_tool_calls = list(latest["pending_tool_calls"])

    def _environment_record(self) -> dict[str, Any]:
        state = self.core.state_dict()
        submission = self.core.export_submission()
        manifest = workspace_manifest(self.workspace)
        return {
            "state": state,
            "phase": state["phase"],
            "checkpoint_state": submission.get("checkpoints") or {},
            "submission": submission,
            "committed_plan_hash": state.get("committed_plan_hash"),
            "reveal_state": {
                "revealed": any(path.startswith("revealed/") for path in manifest),
                "files": sorted(path for path in manifest if path.startswith("revealed/")),
            },
            "purchase_state": {
                "selected_resource": state.get("selected_resource"),
                "spent_units": state.get("spent_units"),
                "files": sorted(path for path in manifest if path.startswith("purchased/")),
            },
            "event_record": state.get("event_log") or [],
            "start_hashes": dict(self.core._start_hashes),  # noqa: SLF001 - restore boundary
            "maximum_tool_calls": self.core.maximum_tool_calls,
            "workspace_manifest": manifest,
        }

    def _persist(self, event_type: str, event: Mapping[str, Any], ledger: Any) -> dict[str, Any]:
        sequence = self._sequence + 1
        provider_records = list(getattr(ledger, "records", []) or [])
        value: dict[str, Any] = {
            "schema_version": "0.8-host-trajectory-record-1",
            "sequence": sequence,
            "recorded_at": datetime.now(UTC).isoformat(),
            "event_type": event_type,
            "event": dict(event),
            "previous_record_sha256": self._previous_digest,
            "messages": self._messages,
            "assistant_output": (
                self._provider_exchanges[-1].get("assistant_output")
                if self._provider_exchanges
                else None
            ),
            "reasoning_state_payload": (
                self._provider_exchanges[-1].get("reasoning_state_payload")
                if self._provider_exchanges
                else {}
            ),
            "provider_exchanges": self._provider_exchanges,
            "tool_actions": self._tool_actions,
            "pending_tool_calls": self._pending_tool_calls,
            "environment": self._environment_record(),
            "provider_requests": provider_records,
            "request_cost_usd": (
                float(provider_records[-1].get("reported_cost_usd") or 0.0)
                if provider_records
                else 0.0
            ),
            "cumulative_cost_usd": round(
                float(getattr(ledger, "cumulative_reported_cost_usd", 0.0)), 8
            ),
            "run_metadata": self.run_metadata,
        }
        sanitized = redact_host_record(value, secret=self.secret)
        digest_value = dict(sanitized)
        digest_value.pop("record_sha256", None)
        sanitized["record_sha256"] = canonical_sha256(digest_value)
        journal_path = self.journal_root / f"{sequence:06d}.json"
        if journal_path.exists():
            raise TrajectoryPersistenceError(f"Trajectory sequence already exists: {sequence}")
        try:
            _atomic_write_json(journal_path, sanitized)
            _atomic_write_json(self.latest_path, sanitized)
        except Exception as exc:
            raise TrajectoryPersistenceError(
                f"Atomic trajectory persistence failed: {type(exc).__name__}"
            ) from exc
        self._sequence = sequence
        self._previous_digest = str(sanitized["record_sha256"])
        return sanitized

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

    def record_model_error(
        self,
        *,
        prompt: Any,
        error: BaseException,
        ledger: Any,
    ) -> dict[str, Any]:
        self._messages = _message_rows(prompt)
        event = {
            "request_index": len(self._provider_exchanges),
            "prompt": self._messages,
            "error_type": type(error).__name__,
            "error_message": redact_exception_message(error, secret=self.secret),
        }
        self._provider_exchanges.append(event)
        return self._persist("provider_error", event, ledger)

    def _claim_pending_call(self, name: str) -> dict[str, Any]:
        for call in self._pending_tool_calls:
            if call.get("status") == "pending" and call.get("name") == name:
                return call
        raise TrajectoryPersistenceError(f"Tool action {name!r} has no pending provider tool call")

    def record_tool_action(
        self,
        *,
        name: str,
        invocation_arguments: Mapping[str, Any],
        result: Any,
        error: BaseException | None,
        ledger: Any,
    ) -> dict[str, Any]:
        call = self._claim_pending_call(name)
        content = (
            str(result) if error is None else redact_exception_message(error, secret=self.secret)
        )
        call["status"] = "completed" if error is None else "errored"
        action = {
            "action_index": len(self._tool_actions),
            "tool_call_id": call["tool_call_id"],
            "name": name,
            "provider_arguments": call.get("arguments"),
            "invocation_arguments": dict(invocation_arguments),
            "result": result if error is None else None,
            "tool_result_content": content,
            "error": (
                None
                if error is None
                else {
                    "type": type(error).__name__,
                    "message": content,
                }
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

    def latest(self) -> dict[str, Any]:
        if not self.latest_path.is_file():
            raise TrajectoryPersistenceError("No durable continuation record exists")
        return json.loads(self.latest_path.read_text(encoding="utf-8"))

    def verify(self, *, require_no_pending_tools: bool = True) -> dict[str, Any]:
        paths = sorted(self.journal_root.glob("*.json"))
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
        if last is None:
            faults.append("empty_journal")
        else:
            if self.latest() != last:
                faults.append("latest_not_last_journal_record")
            if last["environment"]["state"] != self.core.state_dict():
                faults.append("core_state_mismatch")
            if last["environment"]["submission"] != self.core.export_submission():
                faults.append("submission_mismatch")
            if last["environment"]["workspace_manifest"] != workspace_manifest(self.workspace):
                faults.append("workspace_manifest_mismatch")
            if require_no_pending_tools and any(
                call.get("status") == "pending" for call in last["pending_tool_calls"]
            ):
                faults.append("pending_tool_call")
        files = [self.metadata_path, self.latest_path, *paths]
        exact_secret_found = any(
            self.secret and self.secret.encode() in path.read_bytes()
            for path in files
            if path.is_file()
        )
        patterned_secret_found = any(
            _OPENROUTER_KEY.search(path.read_text(encoding="utf-8"))
            for path in files
            if path.is_file()
        )
        if exact_secret_found or patterned_secret_found:
            faults.append("credential_leak")
        return {
            "passed": not faults,
            "faults": faults,
            "record_count": len(paths),
            "model_response_count": sum(
                json.loads(path.read_text(encoding="utf-8"))["event_type"] == "model_response"
                for path in paths
            ),
            "tool_action_count": sum(
                json.loads(path.read_text(encoding="utf-8"))["event_type"] == "tool_action"
                for path in paths
            ),
            "latest_record_sha256": previous,
            "complete_messages_preserved": bool(last and last.get("messages")),
            "reasoning_state_preserved_when_returned": True,
            "host_records_outside_workspace": self.workspace not in self.host_root.parents,
            "credential_leak_found": exact_secret_found or patterned_secret_found,
        }


def restore_v08_environment(
    project_root: Path,
    workspace: Path,
    latest: Mapping[str, Any],
) -> V08Environment:
    """Reconstruct the existing v0.8 core without replaying an irreversible action."""

    environment = latest.get("environment")
    if not isinstance(environment, Mapping):
        raise TrajectoryPersistenceError("Durable record lacks environment state")
    if environment.get("workspace_manifest") != workspace_manifest(workspace):
        raise TrajectoryPersistenceError("Workspace changed since the durable boundary")
    state_raw = environment.get("state")
    if not isinstance(state_raw, Mapping):
        raise TrajectoryPersistenceError("Durable record lacks episode state")
    core = object.__new__(V08Environment)
    core.project_root = project_root.resolve()
    core.case_id = str(state_raw["case_id"])
    core.run_root = workspace.resolve()
    core.maximum_tool_calls = int(environment["maximum_tool_calls"])
    core.state = V07EpisodeState(**dict(state_raw))
    core._start_hashes = dict(environment["start_hashes"])  # noqa: SLF001
    if core.export_submission() != environment.get("submission"):
        raise TrajectoryPersistenceError("Restored submission differs from durable state")
    return core


def durable_tool_functions(
    docker: Any,
    core: V08Environment,
    store: DurableTrajectoryStore,
    ledger: Any,
) -> list[Callable[..., Any]]:
    """Wrap the unchanged tools with a post-action persistence observer."""

    return durable_wrapped_tools(v08_tool_functions(docker, core), store, ledger)


def durable_wrapped_tools(
    tools: list[Callable[..., Any]],
    store: DurableTrajectoryStore,
    ledger: Any,
) -> list[Callable[..., Any]]:
    """Observe an explicitly supplied tool surface without changing its contract."""

    wrapped: list[Callable[..., Any]] = []
    for tool in tools:
        signature = inspect.signature(tool)

        @wraps(tool)
        def observed(
            *args: Any,
            __tool: Callable[..., Any] = tool,
            __signature: inspect.Signature = signature,
            **kwargs: Any,
        ) -> Any:
            bound = __signature.bind_partial(*args, **kwargs)
            try:
                result = __tool(*args, **kwargs)
            except Exception as exc:
                store.record_tool_action(
                    name=__tool.__name__,
                    invocation_arguments=bound.arguments,
                    result=None,
                    error=exc,
                    ledger=ledger,
                )
                raise
            store.record_tool_action(
                name=__tool.__name__,
                invocation_arguments=bound.arguments,
                result=result,
                error=None,
                ledger=ledger,
            )
            return result

        wrapped.append(observed)
    return wrapped


def transcript_for_resume(latest: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return the exact native message sequence at a durable continuation boundary."""

    pending = [
        call for call in latest.get("pending_tool_calls") or [] if call.get("status") == "pending"
    ]
    if pending:
        raise TrajectoryPersistenceError(
            "Continuation requires completing pending tool actions before another model request"
        )
    messages = latest.get("messages")
    if not isinstance(messages, list) or not messages:
        raise TrajectoryPersistenceError("No complete continuation transcript is available")
    return [dict(row) for row in messages]


__all__ = [
    "DurableTrajectoryStore",
    "TrajectoryPersistenceError",
    "durable_tool_functions",
    "durable_wrapped_tools",
    "redact_host_record",
    "restore_v08_environment",
    "transcript_for_resume",
    "workspace_manifest",
]

"""Exact RC4 production-path rehearsal with local fake provider fixtures."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import httpx
from openai.types.chat import ChatCompletion

from uc_bench.case1_pilot_v1_provider import load_case1_pilot_adapters, model_config
from uc_bench.case1_pilot_v1_rc3_tools import case1_tool_definitions
from uc_bench.case1_pilot_v1_rc4_interface import production_request
from uc_bench.case1_pilot_v1_rc4_runner import (
    RC4_PREFLIGHT_AUTHORIZATION,
    run_case1_pilot_rc4_episode,
)
from uc_bench.case1_pilot_v1_rc4_runtime import RC4TrajectoryStore
from uc_bench.case1_pilot_v1_runner import Case1PilotRunConfig
from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256
from uc_bench.mmmvp_open_rc17_trajectory import restore_rc17_environment
from uc_bench.model_runner import _write_json

PREFLIGHT_MODEL = "google/gemini-3.1-pro-preview"
PREFLIGHT_KEY = "sk-" + "or-v1-rc4-fake-transport-secret"


class RC4FakeNativeClient:
    """AsyncOpenAI-shaped fake that can inject one persisted terminal response."""

    def __init__(
        self,
        capture: list[dict[str, Any]],
        *,
        terminal_responses: int = 0,
        invalid_json_responses: int = 0,
        **constructor: Any,
    ) -> None:
        self.capture = capture
        self.constructor = constructor
        self.terminal_responses = terminal_responses
        self.invalid_json_responses = invalid_json_responses
        self.closed = False

    async def post(
        self,
        path: str,
        *,
        body: dict[str, Any],
        cast_to: Any,
        options: dict[str, Any],
    ) -> httpx.Response:
        del cast_to
        self.capture.append(
            {"path": path, "body": copy.deepcopy(body), "options": copy.deepcopy(options)}
        )
        index = len(self.capture)
        if index <= self.invalid_json_responses:
            return httpx.Response(200, content=b"{not-json")
        logical_index = index - self.invalid_json_responses
        if logical_index <= self.terminal_responses:
            message: dict[str, Any] = {"role": "assistant", "content": None}
            finish = "error"
        elif logical_index == self.terminal_responses + 1:
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "rc4-preflight-inspect",
                        "type": "function",
                        "function": {
                            "name": "inspect_workspace",
                            "arguments": json.dumps({"relative_path": "."}),
                        },
                    }
                ],
            }
            finish = "tool_calls"
        elif logical_index == self.terminal_responses + 2:
            message = {
                "role": "assistant",
                "content": "Controlled fake-provider terminal response.",
            }
            finish = "stop"
        else:
            raise ConfigurationError("RC4 fake provider received an unexpected request")
        payload = {
            "id": f"rc4-fake-{index}",
            "object": "chat.completion",
            "created": 0,
            "model": PREFLIGHT_MODEL,
            "provider": "Google AI Studio",
            "choices": [{"index": 0, "finish_reason": finish, "message": message}],
            "usage": {
                "prompt_tokens": 1,
                "completion_tokens": 1,
                "total_tokens": 2,
                "cost": 0.0,
            },
        }
        return httpx.Response(200, content=json.dumps(payload).encode())

    async def close(self) -> None:
        transport = self.constructor.get("http_client")
        if transport is not None:
            await transport.aclose()
        self.closed = True


def _run(
    root: Path,
    output_root: Path,
    *,
    terminal_responses: int,
    invalid_json_responses: int = 0,
) -> tuple[Any, list[dict[str, Any]], list[RC4FakeNativeClient]]:
    capture: list[dict[str, Any]] = []
    instances: list[RC4FakeNativeClient] = []

    def factory(**kwargs: Any) -> RC4FakeNativeClient:
        instance = RC4FakeNativeClient(
            capture,
            terminal_responses=terminal_responses,
            invalid_json_responses=invalid_json_responses,
            **kwargs,
        )
        instances.append(instance)
        return instance

    adapter = load_case1_pilot_adapters(root)[PREFLIGHT_MODEL]
    row = model_config(root, PREFLIGHT_MODEL)
    suffix = f"terminal-{terminal_responses}-invalid-{invalid_json_responses}"
    result = run_case1_pilot_rc4_episode(
        root,
        Case1PilotRunConfig(f"rc4-production-{suffix}", PREFLIGHT_MODEL),
        adapter=adapter,
        openrouter_key=PREFLIGHT_KEY,
        authorization_digest=RC4_PREFLIGHT_AUTHORIZATION,
        remaining_cost_cap_usd=1.0,
        output_root=output_root,
        attempt_seed=int(row["attempt_seed"]),
        provider_seed=row.get("provider_seed"),
        native_client_factory=factory,
        preflight_mode=True,
    )
    return result, capture, instances


def run_exact_production_preflight(project_root: Path, output_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    fixture = json.loads(
        (
            root
            / "artifacts/uc_bench_case1_pilot_v1_rc4/opus_terminal_error_fixture.json"
        ).read_text(encoding="utf-8")
    )
    archived_ledger = json.loads(
        (
            root
            / "artifacts/uc_bench_case1_pilot_v1_rc3/science/runs/"
            "case1-rc3-01-anthropic-claude-opus-4.1-attempt-0/request_ledger.json"
        ).read_text(encoding="utf-8")
    )
    preserved_error_exact = archived_ledger["requests"][-1]["error"] == fixture[
        "preserved_error"
    ]
    synthetic_shape = fixture["faithful_synthetic_parser_fixture"]
    try:
        ChatCompletion.model_validate(synthetic_shape)
    except Exception as exc:
        synthetic_parser_rejection = "finish_reason" in str(exc) and "error" in str(exc)
    else:  # pragma: no cover - would expose an upstream SDK schema change
        synthetic_parser_rejection = False
    normal, normal_calls, normal_instances = _run(
        root, output_root / "normal", terminal_responses=0
    )
    retried, retry_calls, retry_instances = _run(
        root, output_root / "terminal", terminal_responses=1
    )
    exhausted, exhausted_calls, exhausted_instances = _run(
        root, output_root / "exhausted", terminal_responses=2
    )
    invalid, invalid_calls, invalid_instances = _run(
        root,
        output_root / "invalid-json",
        terminal_responses=0,
        invalid_json_responses=1,
    )
    expected = case1_tool_definitions()
    request = production_request(Case1PilotRunConfig("preflight", PREFLIGHT_MODEL))
    latest = json.loads(
        (retried.run_root / "host_trajectory/latest.json").read_text(encoding="utf-8")
    )
    restored = restore_rc17_environment(root, retried.workspace_root, latest)
    reopened = RC4TrajectoryStore.reopen(
        retried.run_root / "host_trajectory",
        workspace=retried.workspace_root,
        core=restored,  # type: ignore[arg-type]
        secret=PREFLIGHT_KEY,
    )
    request_hashes = [
        canonical_sha256(call["body"])
        for call in retry_calls[:2]
    ]
    terminal_events = []
    raw_events = []
    for path in sorted((retried.run_root / "host_trajectory/journal").glob("*.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        event = row.get("event") if isinstance(row.get("event"), dict) else {}
        if row.get("event_type") == "terminal_provider_response_rejected_before_state_application":
            terminal_events.append(event)
        if row.get("event_type") == "raw_model_response_received":
            raw_events.append(event)
    action_names = [row.get("name") for row in latest.get("tool_actions") or []]
    checks = {
        "exact_paid_entry_point_used": True,
        "exact_preserved_opus_error_exercised": preserved_error_exact
        and fixture["raw_response_was_preserved_in_rc3"] is False,
        "synthetic_terminal_shape_matches_evidenced_error": synthetic_shape["choices"][0][
            "finish_reason"
        ]
        == "error"
        and synthetic_parser_rejection,
        "agent_visible_completion_prompt_exact": request["messages"][-1]["content"].startswith(
            "Complete the full predictor evidence investigation autonomously."
        ),
        "tool_schema_unchanged": request["tools"] == expected,
        "normal_roundtrip_two_requests": len(normal_calls) == 2,
        "terminal_retry_three_requests": len(retry_calls) == 3,
        "successful_terminal_retry_remains_eligible": retried.summary.get(
            "classification"
        )
        != "provider_adapter_failure"
        and (retried.summary.get("safe_retry_adjudication") or {}).get(
            "safe_retry_recovered_count"
        )
        == 1,
        "second_terminal_failure_stops_after_one_retry": len(exhausted_calls) == 2
        and exhausted.summary.get("classification") == "provider_adapter_failure"
        and exhausted.summary.get("parsed_provider_exchange_count") == 0
        and (exhausted.summary.get("safe_retry_adjudication") or {}).get(
            "safe_retry_exhausted_count"
        )
        == 1,
        "invalid_json_is_persisted_and_retried_once": len(invalid_calls) == 3
        and invalid.summary.get("raw_response_persisted_count") == 3
        and invalid.summary.get("parsed_provider_exchange_count") == 2
        and invalid.summary.get("classification") != "provider_adapter_failure"
        and (invalid.summary.get("provider_identity") or {}).get("compatible") is True,
        "invalid_json_retry_body_identical": canonical_sha256(invalid_calls[0]["body"])
        == canonical_sha256(invalid_calls[1]["body"]),
        "terminal_response_persisted_before_judgement": len(terminal_events) == 1
        and len(raw_events) == 3,
        "pending_request_body_identical": len(set(request_hashes)) == 1,
        "terminal_response_applied_no_state": bool(terminal_events)
        and terminal_events[0]["assistant_message_applied"] is False
        and terminal_events[0]["tool_call_applied"] is False
        and terminal_events[0]["scientific_state_mutated"] is False,
        "irreversible_actions_not_duplicated": action_names.count("inspect_workspace") == 1,
        "tool_result_ingested_after_retry": any(
            row.get("role") == "tool" for row in retry_calls[-1]["body"].get("messages") or []
        ),
        "replay_exact": (retried.summary.get("trajectory_replay") or {}).get("passed") is True,
        "restart_exact": reopened.verify(require_no_pending_tools=True)["passed"],
        "normal_identity_valid": (normal.summary.get("provider_identity") or {}).get(
            "compatible"
        )
        is True,
        "retry_identity_valid": (retried.summary.get("provider_identity") or {}).get(
            "compatible"
        )
        is True,
        "zero_cost": normal.summary["cumulative_reported_cost_usd"] == 0
        and retried.summary["cumulative_reported_cost_usd"] == 0,
        "client_closed": all(
            instance.closed
            for instance in [
                *normal_instances,
                *retry_instances,
                *exhausted_instances,
                *invalid_instances,
            ]
        ),
    }
    value = {
        "schema_version": "uc-bench-case1-pilot-v1-rc4-production-preflight-1",
        "passed": all(checks.values()),
        "api_requests": 0,
        "scientific_model_requests": 0,
        "fake_provider_requests": (
            len(normal_calls)
            + len(retry_calls)
            + len(exhausted_calls)
            + len(invalid_calls)
        ),
        "checks": checks,
        "normal_summary_sha256": hashlib.sha256(normal.summary_path.read_bytes()).hexdigest(),
        "retry_summary_sha256": hashlib.sha256(retried.summary_path.read_bytes()).hexdigest(),
        "ephemeral_storage": "outside_release_closure",
        "historical_raw_replay_limitation": fixture["limitation"],
    }
    if not value["passed"]:
        failed = sorted(key for key, passed in checks.items() if not passed)
        raise ConfigurationError("RC4 preflight failed: " + ", ".join(failed))
    return value


def write_exact_production_preflight(
    project_root: Path, output_root: Path, report_path: Path
) -> dict[str, Any]:
    value = run_exact_production_preflight(project_root, output_root)
    _write_json(report_path, value, secret=PREFLIGHT_KEY)
    return value


__all__ = ["PREFLIGHT_KEY", "run_exact_production_preflight", "write_exact_production_preflight"]

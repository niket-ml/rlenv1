"""Zero-cost rehearsal of the exact RC6 production path."""

from __future__ import annotations

import copy
import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import httpx

import uc_bench.case1_pilot_v1_rc4_preflight as inherited
from uc_bench.case1_pilot_v1_provider import load_case1_pilot_adapters, model_config
from uc_bench.case1_pilot_v1_rc5_lock import INHERITED_EXTENSION_LOCK
from uc_bench.case1_pilot_v1_rc6_runner import (
    RC6_PREFLIGHT_AUTHORIZATION,
    run_case1_pilot_rc6_episode,
)
from uc_bench.case1_pilot_v1_runner import Case1PilotRunConfig
from uc_bench.errors import ConfigurationError
from uc_bench.model_runner import _write_json

PREFLIGHT_MODEL = "google/gemini-3.1-pro-preview"


class _ModelError(RuntimeError):
    pass


class _APITimeoutError(RuntimeError):
    pass


def _timeout_chain() -> BaseException:
    outer = _ModelError("ModelError")
    api = _APITimeoutError("Request timed out.")
    read = type("ReadTimeout", (TimeoutError,), {})("read operation timed out")
    read.__cause__ = TimeoutError("socket timed out")
    api.__cause__ = read
    outer.__cause__ = api
    return outer


class _RC6TransportFake:
    """Exact AsyncOpenAI post shape with configurable no-response failures."""

    def __init__(
        self,
        capture: list[dict[str, Any]],
        *,
        failures: int,
        status: int | None,
        **constructor: Any,
    ) -> None:
        self.capture = capture
        self.failures = failures
        self.status = status
        self.constructor = constructor
        self.successes = 0
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
        if len(self.capture) <= self.failures:
            if self.status is None:
                raise _timeout_chain()
            error = RuntimeError(f"provider HTTP {self.status}")
            error.status_code = self.status  # type: ignore[attr-defined]
            raise error
        self.successes += 1
        if self.successes == 1:
            message: dict[str, Any] = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "rc6-transport-inspect",
                        "type": "function",
                        "function": {
                            "name": "inspect_workspace",
                            "arguments": json.dumps({"relative_path": "."}),
                        },
                    }
                ],
            }
            finish = "tool_calls"
        elif self.successes == 2:
            message = {"role": "assistant", "content": "RC6 transport fixture complete."}
            finish = "stop"
        else:
            raise ConfigurationError("Transport fixture received an unexpected request")
        payload = {
            "id": f"rc6-transport-{len(self.capture)}",
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


def _transport_run(
    root: Path,
    output: Path,
    *,
    name: str,
    failures: int,
    status: int | None = None,
) -> tuple[Any, list[dict[str, Any]], list[_RC6TransportFake]]:
    capture: list[dict[str, Any]] = []
    instances: list[_RC6TransportFake] = []

    def factory(**kwargs: Any) -> _RC6TransportFake:
        instance = _RC6TransportFake(
            capture, failures=failures, status=status, **kwargs
        )
        instances.append(instance)
        return instance

    row = model_config(root, PREFLIGHT_MODEL)
    result = run_case1_pilot_rc6_episode(
        root,
        Case1PilotRunConfig(f"rc6-transport-{name}", PREFLIGHT_MODEL),
        adapter=load_case1_pilot_adapters(root)[PREFLIGHT_MODEL],
        openrouter_key=inherited.PREFLIGHT_KEY,
        authorization_digest=RC6_PREFLIGHT_AUTHORIZATION,
        remaining_cost_cap_usd=1.0,
        output_root=output,
        attempt_seed=int(row["attempt_seed"]),
        provider_seed=row.get("provider_seed"),
        native_client_factory=factory,
        preflight_mode=True,
    )
    return result, capture, instances


@contextmanager
def _rc6_preflight_context() -> Iterator[None]:
    with INHERITED_EXTENSION_LOCK:
        originals = {
            "run_case1_pilot_rc4_episode": inherited.run_case1_pilot_rc4_episode,
            "RC4_PREFLIGHT_AUTHORIZATION": inherited.RC4_PREFLIGHT_AUTHORIZATION,
            "PREFLIGHT_KEY": inherited.PREFLIGHT_KEY,
        }
        inherited.run_case1_pilot_rc4_episode = run_case1_pilot_rc6_episode
        inherited.RC4_PREFLIGHT_AUTHORIZATION = RC6_PREFLIGHT_AUTHORIZATION
        inherited.PREFLIGHT_KEY = "sk-" + "or-v1-rc6-fake-transport-secret"
        try:
            yield
        finally:
            for name, value in originals.items():
                setattr(inherited, name, value)


def run_exact_production_preflight(project_root: Path, output_root: Path) -> dict[str, Any]:
    with _rc6_preflight_context():
        value = inherited.run_exact_production_preflight(project_root, output_root)
        recovered, recovered_calls, recovered_clients = _transport_run(
            project_root.resolve(),
            output_root / "transport",
            name="timeout-recovered",
            failures=1,
        )
        exhausted, exhausted_calls, exhausted_clients = _transport_run(
            project_root.resolve(),
            output_root / "transport",
            name="timeout-exhausted",
            failures=2,
        )
        rate_limited, rate_calls, rate_clients = _transport_run(
            project_root.resolve(),
            output_root / "transport",
            name="rate-limit-exhausted",
            failures=2,
            status=429,
        )
        server_failed, server_calls, server_clients = _transport_run(
            project_root.resolve(),
            output_root / "transport",
            name="server-error-exhausted",
            failures=2,
            status=503,
        )
    summaries = sorted(output_root.rglob("run_summary.json"))
    checks = dict(value["checks"])
    checks["rc6_lifecycle_present_and_valid"] = len(summaries) == 8 and all(
        __import__("json").loads(path.read_text(encoding="utf-8"))
        .get("request_lifecycle", {})
        .get("passed")
        is True
        for path in summaries
    )
    recovered_lifecycle = recovered.summary["request_lifecycle"]
    exhausted_lifecycle = exhausted.summary["request_lifecycle"]
    rate_lifecycle = rate_limited.summary["request_lifecycle"]
    server_lifecycle = server_failed.summary["request_lifecycle"]
    checks.update(
        {
            "timeout_retry_is_identical": len(recovered_calls) == 3
            and recovered_lifecycle["states"][:2]
            == ["transient_transport_failure", "completed_response"]
            and recovered_calls[0]["body"] == recovered_calls[1]["body"],
            "timeout_retry_continues_episode": recovered.summary["classification"]
            != "isolated_provider_timeout"
            and recovered.summary["provider_identity"]["compatible"] is True,
            "two_timeouts_exclude_only_cell": len(exhausted_calls) == 2
            and exhausted_lifecycle["states"]
            == ["transient_transport_failure", "transient_transport_failure"]
            and exhausted.summary["classification"] == "isolated_provider_timeout"
            and exhausted.summary["reliability_score"] is None,
            "http_429_is_provider_failure_not_completion": len(rate_calls) == 2
            and rate_lifecycle["states"]
            == ["transient_transport_failure", "transient_transport_failure"]
            and rate_limited.summary["classification"] == "isolated_provider_failure"
            and rate_limited.summary["reliability_score"] is None,
            "http_503_is_provider_failure_not_completion": len(server_calls) == 2
            and server_lifecycle["states"]
            == ["transient_transport_failure", "transient_transport_failure"]
            and server_failed.summary["classification"] == "isolated_provider_failure"
            and server_failed.summary["reliability_score"] is None,
            "transport_clients_closed": all(
                client.closed
                for client in [
                    *recovered_clients,
                    *exhausted_clients,
                    *rate_clients,
                    *server_clients,
                ]
            ),
        }
    )
    return {
        **value,
        "schema_version": "uc-bench-case1-pilot-v1-rc6-production-preflight-1",
        "passed": all(checks.values()),
        "checks": checks,
        "rc6_transport_fixture_requests": (
            len(recovered_calls) + len(exhausted_calls) + len(rate_calls)
            + len(server_calls)
        ),
    }


def write_exact_production_preflight(
    project_root: Path, output_root: Path, target: Path
) -> dict[str, Any]:
    value = run_exact_production_preflight(project_root, output_root)
    _write_json(target, value, secret="")
    return value


__all__ = ["run_exact_production_preflight", "write_exact_production_preflight"]

"""Exact production-entry-point RC3 rehearsal with an injected fake transport."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import httpx

from uc_bench.case1_pilot_v1_provider import load_case1_pilot_adapters, model_config
from uc_bench.case1_pilot_v1_rc3_interface import production_request
from uc_bench.case1_pilot_v1_rc3_runner import (
    RC3_PREFLIGHT_AUTHORIZATION,
    run_case1_pilot_rc3_episode,
)
from uc_bench.case1_pilot_v1_rc3_tools import case1_tool_definitions
from uc_bench.case1_pilot_v1_runner import Case1PilotRunConfig
from uc_bench.case1_pilot_v1_runtime import Case1PilotTrajectoryStore
from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256
from uc_bench.mmmvp_open_rc12_environment import rc12_isolation_passed
from uc_bench.mmmvp_open_rc17_trajectory import restore_rc17_environment
from uc_bench.model_runner import _write_json

PREFLIGHT_MODEL = "google/gemini-3.1-pro-preview"
PREFLIGHT_KEY = "sk-" + "or-v1-rc3-fake-transport-secret"


class CapturingFakeNativeClient:
    """A local AsyncOpenAI-shaped transport that cannot perform network I/O."""

    def __init__(self, capture: list[dict[str, Any]], **constructor: Any) -> None:
        self.capture = capture
        self.constructor = constructor
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
            {
                "path": path,
                "body": copy.deepcopy(body),
                "options": copy.deepcopy(options),
            }
        )
        index = len(self.capture)
        if index == 1:
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "rc3-preflight-inspect",
                        "type": "function",
                        "function": {
                            "name": "inspect_workspace",
                            "arguments": json.dumps({"relative_path": "."}),
                        },
                    }
                ],
            }
            finish = "tool_calls"
        elif index == 2:
            message = {
                "role": "assistant",
                "content": "Controlled fake-provider terminal response.",
            }
            finish = "stop"
        else:
            raise ConfigurationError("RC3 fake provider received an unexpected third request")
        payload = {
            "id": f"rc3-fake-{index}",
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
        return httpx.Response(200, content=json.dumps(payload).encode("utf-8"))

    async def close(self) -> None:
        transport = self.constructor.get("http_client")
        if transport is not None:
            await transport.aclose()
        self.closed = True


def run_exact_production_preflight(
    project_root: Path, output_root: Path
) -> dict[str, Any]:
    root = project_root.resolve()
    capture: list[dict[str, Any]] = []
    instances: list[CapturingFakeNativeClient] = []

    def factory(**kwargs: Any) -> CapturingFakeNativeClient:
        instance = CapturingFakeNativeClient(capture, **kwargs)
        instances.append(instance)
        return instance

    adapter = load_case1_pilot_adapters(root)[PREFLIGHT_MODEL]
    row = model_config(root, PREFLIGHT_MODEL)
    config = Case1PilotRunConfig(
        run_id="rc3-exact-production-path-fake-provider",
        model_id=PREFLIGHT_MODEL,
    )
    result = run_case1_pilot_rc3_episode(
        root,
        config,
        adapter=adapter,
        openrouter_key=PREFLIGHT_KEY,
        authorization_digest=RC3_PREFLIGHT_AUTHORIZATION,
        remaining_cost_cap_usd=1.0,
        output_root=output_root,
        attempt_seed=int(row["attempt_seed"]),
        provider_seed=row.get("provider_seed"),
        native_client_factory=factory,
        preflight_mode=True,
    )
    expected = case1_tool_definitions()
    request = production_request(config)
    transmitted = [
        [
            item.model_dump(mode="json") if hasattr(item, "model_dump") else item
            for item in (row["body"].get("tools") or [])
        ]
        for row in capture
    ]
    second_messages = capture[1]["body"].get("messages") if len(capture) > 1 else []
    tool_results = [row for row in second_messages or [] if row.get("role") == "tool"]
    latest_path = result.run_root / "host_trajectory/latest.json"
    latest = json.loads(latest_path.read_text(encoding="utf-8")) if latest_path.is_file() else {}
    actions = latest.get("tool_actions") or []
    restored = restore_rc17_environment(root, result.workspace_root, latest)
    reopened = Case1PilotTrajectoryStore.reopen(
        result.run_root / "host_trajectory",
        workspace=result.workspace_root,
        core=restored,  # type: ignore[arg-type]
        secret=PREFLIGHT_KEY,
    )
    restart_verification = reopened.verify(require_no_pending_tools=True)
    constructor = instances[0].constructor if instances else {}
    provider_settings = [row["body"].get("provider") for row in capture]
    checks = {
        "exact_paid_entry_point_used": True,
        "real_environment_materialized": (result.workspace_root / "MISSION.md").is_file(),
        "real_docker_isolation_passed": rc12_isolation_passed(result.summary["isolation"]),
        "real_durable_ledger_used": result.request_ledger_path.is_file(),
        "real_trajectory_store_used": latest_path.is_file(),
        "two_provider_requests": len(capture) == 2,
        "all_transmitted_surfaces_identical": len(transmitted) == 2
        and all(surface == expected for surface in transmitted),
        "request_registry_identical": request["tools"] == expected,
        "runtime_registry_identical": (result.summary.get("tool_surface") or {}).get(
            "registry_request_runtime_identical"
        )
        is True,
        "all_descriptions_nonempty": all(
            row["function"].get("description") for row in expected
        ),
        "workspace_tool_call_executed": any(
            row.get("name") == "inspect_workspace" and not row.get("error") for row in actions
        ),
        "tool_result_in_second_request": len(tool_results) == 1
        and tool_results[0].get("tool_call_id") == "rc3-preflight-inspect",
        "terminal_response_recorded": result.summary.get("stop_condition")
        in {None, "stop", "no_tools_called"}
        and result.summary.get("raw_response_persisted_count") == 2,
        "reconstruction_and_replay_exact": (result.summary.get("trajectory_replay") or {}).get(
            "passed"
        )
        is True,
        "store_restart_exact": restart_verification["passed"],
        "grading_not_applicable": (result.summary.get("grader_assessment") or {}).get(
            "status"
        )
        == "not_applicable",
        "zero_cost": result.summary.get("cumulative_reported_cost_usd") == 0,
        "fake_backend_only": len(instances) == 1,
        "explicit_fake_key_supplied": constructor.get("api_key") == PREFLIGHT_KEY,
        "explicit_openrouter_base_url_supplied": str(constructor.get("base_url")).rstrip("/")
        == "https://openrouter.ai/api/v1",
        "native_retries_disabled": constructor.get("max_retries") == 0,
        "expected_default_header_supplied": constructor.get("default_headers")
        == {"X-OpenRouter-Title": "UC-Bench v0.7.1 development"},
        "fake_client_closed": bool(instances) and all(instance.closed for instance in instances),
        "model_unchanged_on_both_requests": all(
            row["body"].get("model") == PREFLIGHT_MODEL for row in capture
        ),
        "pinned_provider_unchanged_on_both_requests": all(
            value == {
                "order": ["Google AI Studio"],
                "only": ["Google AI Studio"],
                "allow_fallbacks": False,
                "require_parameters": True,
                "max_price": {"prompt": 2.0, "completion": 12.0},
            }
            for value in provider_settings
        ),
        "provider_tool_digest_unchanged": canonical_sha256(expected)
        == result.summary["tool_surface"]["sha256"],
    }
    value = {
        "schema_version": "uc-bench-case1-pilot-v1-rc3-production-preflight-1",
        "passed": all(checks.values()),
        "api_requests": 0,
        "fake_provider_requests": len(capture),
        "scientific_model_requests": 0,
        "reported_cost_usd": result.summary.get("cumulative_reported_cost_usd"),
        "tool_schema_sha256": canonical_sha256(expected),
        "transmitted_tool_schema_sha256": [canonical_sha256(row) for row in transmitted],
        "summary_identity": {
            "scientific_base_release_id": result.summary.get("scientific_base_release_id"),
            "scientific_base_digest": result.summary.get("scientific_base_digest"),
            "execution_release_id": result.summary.get("execution_release_id"),
            "execution_release_digest": result.summary.get("execution_release_digest"),
        },
        "summary_classification": result.summary.get("classification"),
        "replay_status": (result.summary.get("trajectory_replay") or {}).get("status"),
        "grader_status": (result.summary.get("grader_assessment") or {}).get("status"),
        "checks": checks,
        "ephemeral_summary_sha256": hashlib.sha256(result.summary_path.read_bytes()).hexdigest(),
        "preflight_run_storage": "ephemeral_not_in_release_closure",
    }
    if not value["passed"]:
        failed = sorted(name for name, passed in checks.items() if not passed)
        raise ConfigurationError(
            "Exact RC3 production-path preflight did not pass: " + ", ".join(failed)
        )
    return value


def write_exact_production_preflight(
    project_root: Path, output_root: Path, report_path: Path
) -> dict[str, Any]:
    value = run_exact_production_preflight(project_root, output_root)
    _write_json(report_path, value, secret=PREFLIGHT_KEY)
    return value


__all__ = [
    "PREFLIGHT_KEY",
    "CapturingFakeNativeClient",
    "run_exact_production_preflight",
    "write_exact_production_preflight",
]

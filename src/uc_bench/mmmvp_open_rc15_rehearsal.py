"""Zero-cost full production-path launch rehearsal for RC1.5."""

from __future__ import annotations

import json
import secrets
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import httpx

from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256, sha256_file
from uc_bench.mmmvp_open_controls import build_open_reference
from uc_bench.mmmvp_open_freeze import read_open_mmmvp_freeze
from uc_bench.mmmvp_open_rc12_trajectory import restore_rc12_environment
from uc_bench.mmmvp_open_rc14_freeze import read_rc14_release_freeze
from uc_bench.mmmvp_open_rc14_runner import (
    RC14DurableTrajectoryStore,
    build_rc14_scientific_client,
    run_rc14_open_mmmvp_episode,
)
from uc_bench.mmmvp_open_rc15_adapter import load_rc15_launch_routes
from uc_bench.mmmvp_open_rc15_cost import calculate_rc15_cost_plan
from uc_bench.mmmvp_open_rc15_order import order_record
from uc_bench.mmmvp_open_runner import OpenRunConfig, production_request
from uc_bench.model_runner import _write_json
from uc_bench.v071_auth import credential_locations

PREFREEZE_REHEARSAL_PATH = Path(
    "artifacts/mmmvp_open_rc15/pre_freeze_rehearsal.json"
)
POSTFREEZE_PREFLIGHT_PATH = Path(
    "artifacts/mmmvp_open_rc15/post_freeze_preflight.json"
)
FAKE_KEY = "sk-or-v1-rc15-zero-cost-rehearsal"


def _tool_response(
    *,
    route: Any,
    index: int,
    name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": f"rc15-fixture-{index}",
        "created": 0,
        "object": "chat.completion",
        "model": route.canonical_slug,
        "provider": route.provider,
        "choices": [
            {
                "index": 0,
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": f"rc15-call-{index}",
                            "type": "function",
                            "function": {
                                "name": name,
                                "arguments": json.dumps(arguments),
                            },
                        }
                    ],
                },
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
            "cost": 0.0,
        },
    }


def _final_response(route: Any, index: int) -> dict[str, Any]:
    return {
        "id": f"rc15-fixture-{index}",
        "created": 0,
        "object": "chat.completion",
        "model": route.canonical_slug,
        "provider": route.provider,
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": "The structured submission was accepted.",
                },
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
            "cost": 0.0,
        },
    }


def _scripted_actions(project_root: Path) -> list[tuple[str, dict[str, Any]]]:
    with tempfile.TemporaryDirectory(prefix="uc-rc15-reference-") as directory:
        reference, workspace = build_open_reference(
            project_root,
            "case_02",
            Path(directory) / "workspace",
            alternative=True,
        )
        final = reference["final_submission"]
        files = {
            relative: (workspace / relative).read_text(encoding="utf-8")
            for relative in (
                "work/analysis_table.csv",
                "work/analysis.py",
                "work/results.json",
            )
        }
        return [
            (
                "commit_validation_plan",
                {"payload_json": json.dumps(reference["validation_plan"])},
            ),
            ("reveal_validation", {}),
            *[
                (
                    "write_file",
                    {"relative_path": relative, "content": content},
                )
                for relative, content in files.items()
            ],
            (
                "commit_followup_plan",
                {"payload_json": json.dumps(reference["followup_plan"])},
            ),
            (
                "purchase_resource",
                {"resource_id": reference["followup_plan"]["chosen_resource"]},
            ),
            ("submit", {"payload_json": json.dumps(final)}),
        ]


class ScriptedNativeClient:
    """AsyncOpenAI-compatible zero-network fixture transport."""

    def __init__(
        self,
        *,
        route: Any,
        actions: list[tuple[str, dict[str, Any]]],
        http_client: httpx.AsyncClient,
        restart_probe: Any,
    ) -> None:
        self.route = route
        self.actions = actions
        self.http_client = http_client
        self.restart_probe = restart_probe
        self.request_bodies: list[dict[str, Any]] = []
        self.restart_result: dict[str, Any] | None = None

    async def post(
        self,
        path: str,
        *,
        body: dict[str, Any],
        cast_to: Any,
        options: dict[str, Any],
    ) -> httpx.Response:
        del cast_to, options
        if path != "/chat/completions":
            raise ConfigurationError("Fixture received an unexpected endpoint")
        index = len(self.request_bodies)
        self.request_bodies.append(body)
        if index > 0:
            expected_previous_id = f"rc15-call-{index - 1}"
            if not any(
                row.get("role") == "tool"
                and row.get("tool_call_id") == expected_previous_id
                for row in body.get("messages") or []
            ):
                raise ConfigurationError("Fixture did not receive the prior tool result")
        if index == 2 and self.restart_result is None:
            self.restart_result = self.restart_probe()
        if index < len(self.actions):
            name, arguments = self.actions[index]
            payload = _tool_response(
                route=self.route,
                index=index,
                name=name,
                arguments=arguments,
            )
        else:
            payload = _final_response(self.route, index)
        request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
        return httpx.Response(
            200,
            content=json.dumps(payload).encode(),
            headers={"content-type": "application/json"},
            request=request,
        )

    async def close(self) -> None:
        await self.http_client.aclose()


def run_prefreeze_rehearsal(project_root: Path) -> dict[str, Any]:
    """Run the frozen RC1.4 episode engine end to end with a fake provider."""

    root = project_root.resolve()
    target = root / PREFREEZE_REHEARSAL_PATH
    if target.exists():
        raise ConfigurationError("RC1.5 pre-freeze rehearsal already exists")
    scientific = read_open_mmmvp_freeze(root)
    rc14 = read_rc14_release_freeze(root)
    routes = load_rc15_launch_routes(root)
    route = routes["mistralai/mistral-large-2512"]
    offline_cost = calculate_rc15_cost_plan(root)
    rehearsal_order = order_record(
        list(routes),
        release_infrastructure_digest="prefreeze-candidate",
        entropy=secrets.token_bytes(32),
    )
    actions = _scripted_actions(root)
    run_id = f"open-mmmvp-rc15-prefreeze-rehearsal-{uuid4().hex[:12]}"
    config = OpenRunConfig(
        run_id=run_id,
        model_id=route.model_id,
        case_id="case_02",
        minimum_request_interval_seconds=0.0,
    )
    expected_request = production_request(
        OpenRunConfig("paid-shape", route.model_id, "case_02")
    )
    if production_request(config) != expected_request:
        raise ConfigurationError("Rehearsal and paid serialized requests differ")

    native_clients: list[ScriptedNativeClient] = []
    active_store: RC14DurableTrajectoryStore | None = None

    def restart_probe() -> dict[str, Any]:
        if active_store is None:
            raise ConfigurationError("Rehearsal restart probe has no durable store")
        latest = active_store.latest()
        if (latest.get("environment") or {}).get("state", {}).get("phase") != "revealed":
            raise ConfigurationError("Rehearsal interruption did not occur after reveal")
        workspace = active_store.workspace
        restored = restore_rc12_environment(root, workspace, latest)
        reopened = RC14DurableTrajectoryStore.reopen(
            active_store.host_root,
            workspace=workspace,
            core=restored,  # type: ignore[arg-type]
            secret=FAKE_KEY,
        )
        verification = reopened.verify(require_no_pending_tools=True)
        return {
            "simulated_process_stop": True,
            "interruption_phase": "revealed",
            "reopened": True,
            "verification_passed": verification["passed"],
            "messages_exact": reopened.latest()["messages"] == latest["messages"],
            "state_exact": reopened.latest()["environment"] == latest["environment"],
        }

    original_builder = build_rc14_scientific_client

    def fixture_builder(**kwargs: Any) -> Any:
        nonlocal active_store
        active_store = kwargs["store"]

        def native_factory(**native_kwargs: Any) -> ScriptedNativeClient:
            if native_kwargs.get("api_key") != FAKE_KEY:
                raise ConfigurationError("Fake constructor did not receive explicit key")
            if str(native_kwargs.get("base_url")).rstrip("/") != (
                "https://openrouter.ai/api/v1"
            ):
                raise ConfigurationError("Fake constructor received the wrong base URL")
            client = ScriptedNativeClient(
                route=route,
                actions=actions,
                http_client=native_kwargs["http_client"],
                restart_probe=restart_probe,
            )
            native_clients.append(client)
            return client

        return original_builder(**kwargs, native_client_factory=native_factory)

    with patch(
        "uc_bench.mmmvp_open_rc14_runner.build_rc14_scientific_client",
        fixture_builder,
    ):
        result = run_rc14_open_mmmvp_episode(
            root,
            config,
            adapter=route.adapter,
            openrouter_key=FAKE_KEY,
            authorization_digest=rc14["infrastructure_digest"],
            remaining_cost_cap_usd=1.0,
        )
    if len(native_clients) != 1:
        raise ConfigurationError("Rehearsal constructed an unexpected client count")
    native = native_clients[0]
    summary = result.summary
    grade = summary.get("diagnostic_grade") or {}
    restart = native.restart_result or {}
    passed = bool(
        summary.get("complete_mission_success") is True
        and summary.get("classification") == "valid_episode"
        and summary.get("cumulative_reported_cost_usd") == 0
        and summary.get("trajectory_persistence", {}).get("passed")
        and restart.get("verification_passed")
        and restart.get("messages_exact")
        and restart.get("state_exact")
        and len(native.request_bodies) == len(actions) + 1
        and grade.get("complete_mission_success") is True
        and not credential_locations(result.run_root, FAKE_KEY)
    )
    value = {
        "schema_version": "uc-bench-open-mmmvp-rc1-5-prefreeze-rehearsal-1",
        "status": "passed" if passed else "failed",
        "api_requests": 0,
        "network_requests": 0,
        "scientific_requests": 0,
        "fake_provider_requests": len(native.request_bodies),
        "production_episode_function": (
            "uc_bench.mmmvp_open_rc14_runner.run_rc14_open_mmmvp_episode"
        ),
        "production_request_sha256": canonical_sha256(expected_request),
        "scientific_freeze_digest": scientific["hash_set_digest"],
        "source_rc14_infrastructure_digest": rc14["infrastructure_digest"],
        "loaded_model_count": 10,
        "compatible_model_count": len(routes),
        "compatible_models": list(routes),
        "excluded_models": ["z-ai/glm-5.2"],
        "cost_plan": {
            "median_usd": offline_cost["sentinel_no_cache_median_usd"],
            "p90_usd": offline_cost["sentinel_no_cache_p90_usd"],
            "hard_cap_usd": offline_cost["scientific_hard_cap_usd"],
            "independent_calculations_agree": offline_cost[
                "independent_calculations_agree"
            ],
            "eligible_by_cost_distribution": offline_cost[
                "sentinel_no_cache_p90_usd"
            ]
            <= offline_cost["scientific_hard_cap_usd"],
        },
        "randomized_order": rehearsal_order,
        "workspace_materialized": result.workspace_root.is_dir(),
        "client_constructed_with_explicit_credentials": True,
        "first_request_matches_paid_serialization": True,
        "tool_result_ingestion_count": len(actions),
        "final_response_recorded": len(native.request_bodies) == len(actions) + 1,
        "interruption_restart": restart,
        "valid_fake_submission": summary.get("complete_mission_success"),
        "partial_scientific_quality": summary.get("partial_scientific_quality"),
        "grader_consistency": summary.get("grader_consistency"),
        "trajectory_persistence": summary.get("trajectory_persistence"),
        "run_summary_path": result.summary_path.relative_to(root).as_posix(),
        "run_summary_sha256": sha256_file(result.summary_path),
        "credential_leakage": False,
        "scientific_hashes_verified": True,
        "infrastructure_hashes_verified": True,
    }
    _write_json(target, value, secret=FAKE_KEY)
    if not passed:
        raise ConfigurationError("RC1.5 full production-path rehearsal failed")
    return value


def frozen_preflight(project_root: Path) -> dict[str, Any]:
    """Recompute the frozen launch inputs without network or new episode output."""

    from uc_bench.mmmvp_open_rc15_freeze import read_rc15_release_freeze

    root = project_root.resolve()
    release = read_rc15_release_freeze(root)
    rehearsal = json.loads((root / PREFREEZE_REHEARSAL_PATH).read_text())
    cost = calculate_rc15_cost_plan(root)
    routes = load_rc15_launch_routes(root)
    request_hash = canonical_sha256(
        production_request(OpenRunConfig("frozen", next(iter(routes)), "case_02"))
    )
    checks = {
        "freeze_valid": True,
        "model_subset_matches": list(routes) == rehearsal["compatible_models"],
        "median_matches": cost["sentinel_no_cache_median_usd"]
        == rehearsal["cost_plan"]["median_usd"],
        "p90_matches": cost["sentinel_no_cache_p90_usd"]
        == rehearsal["cost_plan"]["p90_usd"],
        "hard_cap_matches": cost["scientific_hard_cap_usd"]
        == rehearsal["cost_plan"]["hard_cap_usd"],
        "request_matches": request_hash == rehearsal["production_request_sha256"],
        "scientific_digest_matches": release["scientific_freeze_digest"]
        == rehearsal["scientific_freeze_digest"],
        "fake_summary_unchanged": sha256_file(root / rehearsal["run_summary_path"])
        == rehearsal["run_summary_sha256"],
    }
    value = {
        "schema_version": "uc-bench-open-mmmvp-rc1-5-frozen-preflight-1",
        "status": "passed" if all(checks.values()) else "failed",
        "api_requests": 0,
        "scientific_requests": 0,
        "release_infrastructure_digest": release["infrastructure_digest"],
        "checks": checks,
        "recomputed_cost": {
            "median_usd": cost["sentinel_no_cache_median_usd"],
            "p90_usd": cost["sentinel_no_cache_p90_usd"],
            "hard_cap_usd": cost["scientific_hard_cap_usd"],
            "independent_calculations_agree": cost[
                "independent_calculations_agree"
            ],
        },
    }
    _write_json(root / POSTFREEZE_PREFLIGHT_PATH, value, secret="")
    if value["status"] != "passed":
        raise ConfigurationError("Frozen RC1.5 preflight differs from rehearsal")
    return value


__all__ = [
    "POSTFREEZE_PREFLIGHT_PATH",
    "PREFREEZE_REHEARSAL_PATH",
    "frozen_preflight",
    "run_prefreeze_rehearsal",
]

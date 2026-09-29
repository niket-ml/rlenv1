"""Zero-network production-path rehearsal for RC1.6 valid and invalid paths."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import httpx

from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256
from uc_bench.mmmvp_open_controls import build_open_reference
from uc_bench.mmmvp_open_rc12_trajectory import restore_rc12_environment
from uc_bench.mmmvp_open_rc14_runner import (
    RC14DurableTrajectoryStore,
    build_rc14_scientific_client,
)
from uc_bench.mmmvp_open_rc15_adapter import load_rc15_launch_routes
from uc_bench.mmmvp_open_rc16_runner import _run_rc16_episode
from uc_bench.mmmvp_open_runner import OpenRunConfig, production_request
from uc_bench.v071_auth import credential_locations

PREFREEZE_REHEARSAL_PATH = Path("artifacts/mmmvp_open_rc16/pre_freeze_rehearsal.json")
POSTFREEZE_PREFLIGHT_PATH = Path("artifacts/mmmvp_open_rc16/post_freeze_preflight.json")
FAKE_KEY = "sk-or-v1-rc16-zero-cost-rehearsal"
_CANDIDATE_DIGEST = "rc16-prefreeze-candidate"
_GEMINI_RUN = Path(
    "build/uc_bench_mmmvp_open_rc14_runs/"
    "open-mmmvp-rc15-sentinel-00-google-gemini-3.1-pro-preview-case-02-atte"
)


def _provider_payload(
    route: Any,
    index: int,
    action: tuple[str, dict[str, Any]] | None,
) -> dict[str, Any]:
    if action is None:
        finish_reason = "stop"
        message: dict[str, Any] = {
            "role": "assistant",
            "content": "The structured submission was accepted.",
        }
    else:
        name, arguments = action
        finish_reason = "tool_calls"
        message = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": f"rc16-call-{index}",
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(arguments)},
                }
            ],
        }
    return {
        "id": f"rc16-fixture-{index}",
        "created": 0,
        "object": "chat.completion",
        "model": route.canonical_slug,
        "provider": route.provider,
        "choices": [{"index": 0, "finish_reason": finish_reason, "message": message}],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
            "cost": 0.0,
        },
    }


class RC16FixtureClient:
    def __init__(
        self,
        *,
        route: Any,
        actions: list[tuple[str, dict[str, Any]]],
        http_client: httpx.AsyncClient,
        store: Any,
        project_root: Path,
        corrupt_environment_before_finish: bool,
    ) -> None:
        self.route = route
        self.actions = actions
        self.http_client = http_client
        self.store = store
        self.project_root = project_root
        self.corrupt_environment_before_finish = corrupt_environment_before_finish
        self.request_bodies: list[dict[str, Any]] = []
        self.restart_result: dict[str, Any] | None = None

    def _restart_once_after_reveal(self) -> None:
        if self.restart_result is not None or not self.store.latest_path.is_file():
            return
        latest = self.store.latest()
        if (latest.get("environment") or {}).get("state", {}).get("phase") != "revealed":
            return
        restored = restore_rc12_environment(self.project_root, self.store.workspace, latest)
        reopened = RC14DurableTrajectoryStore.reopen(
            self.store.host_root,
            workspace=self.store.workspace,
            core=restored,
            secret=FAKE_KEY,
        )
        verification = reopened.verify(require_no_pending_tools=True)
        self.restart_result = {
            "reopened": True,
            "verification_passed": verification["passed"],
            "messages_exact": reopened.latest()["messages"] == latest["messages"],
            "state_exact": reopened.latest()["environment"] == latest["environment"],
        }

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
        self._restart_once_after_reveal()
        index = len(self.request_bodies)
        self.request_bodies.append(body)
        action = self.actions[index] if index < len(self.actions) else None
        if action is None and self.corrupt_environment_before_finish:
            target = self.store.workspace / "data/cohort_metadata.csv"
            target.write_bytes(b"\xff")
        payload = _provider_payload(self.route, index, action)
        request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
        return httpx.Response(
            200,
            content=json.dumps(payload).encode(),
            headers={"content-type": "application/json"},
            request=request,
        )

    async def close(self) -> None:
        await self.http_client.aclose()


def _reference_actions(
    project_root: Path, *, malformed_output: bool
) -> list[tuple[str, dict[str, Any]]]:
    with tempfile.TemporaryDirectory(prefix="uc-rc16-reference-") as directory:
        reference, workspace = build_open_reference(
            project_root,
            "case_02",
            Path(directory) / "workspace",
            alternative=True,
        )
        files = {
            relative: (workspace / relative).read_text(encoding="utf-8")
            for relative in (
                "work/analysis_table.csv",
                "work/analysis.py",
                "work/results.json",
            )
        }
        if malformed_output:
            files["work/results.json"] = "null\n"
        return [
            (
                "commit_validation_plan",
                {"payload_json": json.dumps(reference["validation_plan"])},
            ),
            ("reveal_validation", {}),
            *[
                ("write_file", {"relative_path": relative, "content": content})
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
            ("submit", {"payload_json": json.dumps(reference["final_submission"])}),
        ]


def _gemini_actions(project_root: Path) -> list[tuple[str, dict[str, Any]]]:
    latest = json.loads(
        (project_root / _GEMINI_RUN / "host_trajectory/latest.json").read_text(encoding="utf-8")
    )
    return [
        (str(row["name"]), dict(row.get("invocation_arguments") or {}))
        for row in latest["tool_actions"]
    ]


def _run_path(
    project_root: Path,
    *,
    label: str,
    actions: list[tuple[str, dict[str, Any]]],
    corrupt_environment: bool = False,
) -> dict[str, Any]:
    root = project_root.resolve()
    route = load_rc15_launch_routes(root)["mistralai/mistral-large-2512"]
    config = OpenRunConfig(
        run_id=f"open-mmmvp-rc16-{label}-{uuid4().hex[:10]}",
        model_id=route.model_id,
        case_id="case_02",
        minimum_request_interval_seconds=0.0,
    )
    clients: list[RC16FixtureClient] = []
    original_builder = build_rc14_scientific_client

    def fixture_builder(**kwargs: Any) -> Any:
        def native_factory(**native_kwargs: Any) -> RC16FixtureClient:
            if native_kwargs.get("api_key") != FAKE_KEY:
                raise ConfigurationError("Fixture constructor lacks the explicit key")
            if str(native_kwargs.get("base_url")).rstrip("/") != "https://openrouter.ai/api/v1":
                raise ConfigurationError("Fixture constructor has the wrong base URL")
            client = RC16FixtureClient(
                route=route,
                actions=actions,
                http_client=native_kwargs["http_client"],
                store=kwargs["store"],
                project_root=root,
                corrupt_environment_before_finish=corrupt_environment,
            )
            clients.append(client)
            return client

        return original_builder(**kwargs, native_client_factory=native_factory)

    with patch(
        "uc_bench.mmmvp_open_rc14_runner.build_rc14_scientific_client",
        fixture_builder,
    ):
        result = _run_rc16_episode(
            root,
            config,
            adapter=route.adapter,
            openrouter_key=FAKE_KEY,
            authorization_digest=_CANDIDATE_DIGEST,
            remaining_cost_cap_usd=1.0,
            release={"infrastructure_digest": _CANDIDATE_DIGEST},
        )
    client = clients[0]
    summary = result.summary
    return {
        "label": label,
        "classification": summary["classification"],
        "strict_mission_success": summary.get("complete_mission_success"),
        "partial_scientific_quality": summary.get("partial_scientific_quality"),
        "grader_exception": summary.get("grader_exception"),
        "grader_consistency": summary.get("grader_consistency"),
        "trajectory_persistence": summary.get("trajectory_persistence"),
        "restart": client.restart_result,
        "request_count": len(client.request_bodies),
        "cost_usd": summary.get("cumulative_reported_cost_usd"),
        "run_summary": result.summary_path.relative_to(root).as_posix(),
        "credentials_absent": not credential_locations(result.run_root, FAKE_KEY),
    }


def run_rc16_prefreeze_rehearsal(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    valid = _run_path(
        root,
        label="prefreeze-valid",
        actions=_reference_actions(root, malformed_output=False),
    )
    scalar = _run_path(root, label="prefreeze-gemini-scalar", actions=_gemini_actions(root))
    malformed = _run_path(
        root,
        label="prefreeze-malformed-agent",
        actions=_reference_actions(root, malformed_output=True),
    )
    corrupted = _run_path(
        root,
        label="prefreeze-corrupt-environment",
        actions=_reference_actions(root, malformed_output=False),
        corrupt_environment=True,
    )
    paths = [valid, scalar, malformed, corrupted]
    passed = bool(
        valid["strict_mission_success"] is True
        and scalar["strict_mission_success"] is False
        and scalar["partial_scientific_quality"] == 40.0
        and malformed["strict_mission_success"] is False
        and malformed["grader_exception"] is None
        and corrupted["classification"] == "infrastructure_failure"
        and all(row["trajectory_persistence"]["passed"] for row in paths)
        and all(row["credentials_absent"] and row["cost_usd"] == 0 for row in paths)
        and all(
            row["restart"] is not None
            and row["restart"]["verification_passed"]
            and row["restart"]["messages_exact"]
            and row["restart"]["state_exact"]
            for row in paths
        )
    )
    return {
        "schema_version": "uc-bench-open-mmmvp-rc1-6-prefreeze-rehearsal-1",
        "status": "passed" if passed else "failed",
        "api_requests": 0,
        "network_requests": 0,
        "production_episode_function": "uc_bench.mmmvp_open_rc16_runner._run_rc16_episode",
        "production_request_sha256": canonical_sha256(
            production_request(OpenRunConfig("identity", "mistralai/mistral-large-2512", "case_02"))
        ),
        "paths": paths,
        "valid_typed_artifact_passes": valid["strict_mission_success"] is True,
        "gemini_scalar_is_normal_40_failure": (
            scalar["strict_mission_success"] is False
            and scalar["partial_scientific_quality"] == 40.0
            and scalar["grader_exception"] is None
        ),
        "malformed_agent_artifact_fails_gracefully": (
            malformed["strict_mission_success"] is False and malformed["grader_exception"] is None
        ),
        "corrupt_environment_is_global_stop": corrupted["classification"]
        == "infrastructure_failure",
        "scientific_requests": 0,
        "heldout_requests": 0,
        "astra_requests": 0,
    }


__all__ = [
    "POSTFREEZE_PREFLIGHT_PATH",
    "PREFREEZE_REHEARSAL_PATH",
    "run_rc16_prefreeze_rehearsal",
]

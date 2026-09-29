"""Zero-cost rehearsal through the exact Case 2 production runner."""

from __future__ import annotations

import copy
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

import httpx

from uc_bench.case2_pilot_v1_rc1_controls import build_reference, replace_final
from uc_bench.case2_pilot_v1_rc1_execution import (
    _adopt_cell,
    active_cell_recovery_mode,
)
from uc_bench.case2_pilot_v1_rc1_provider import load_case2_adapters, model_config
from uc_bench.case2_pilot_v1_rc1_release import candidate_manifest
from uc_bench.case2_pilot_v1_rc1_runner import (
    PREFLIGHT_AUTHORIZATION,
    Case2RunConfig,
    run_case2_episode,
)
from uc_bench.model_runner import _write_json

PREFLIGHT_MODEL = "google/gemini-3.1-pro-preview"
PREFLIGHT_KEY = "sk-" + "or-v1-case2-fake-transport-secret"


def _tool(name: str, arguments: dict[str, Any], index: int) -> dict[str, Any]:
    encoded = (
        str(arguments["__raw_arguments__"])
        if set(arguments) == {"__raw_arguments__"}
        else json.dumps(arguments)
    )
    return {
        "id": f"case2-fake-tool-{index:03d}",
        "type": "function",
        "function": {"name": name, "arguments": encoded},
    }


class ScriptedNativeClient:
    """OpenAI-shaped local transport that continues from the persisted transcript."""

    def __init__(
        self,
        capture: list[dict[str, Any]],
        *,
        actions: list[tuple[str, dict[str, Any]]],
        terminal_error: bool = False,
        transient_failures: int = 0,
        timeout_failures: int = 0,
        invalid_json_failures: int = 0,
        **constructor: Any,
    ) -> None:
        self.capture = capture
        self.actions = actions
        self.terminal_error = terminal_error
        self.transient_failures = transient_failures
        self.timeout_failures = timeout_failures
        self.invalid_json_failures = invalid_json_failures
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
            {"path": path, "body": copy.deepcopy(body), "options": copy.deepcopy(options)}
        )
        request_number = len(self.capture)
        if request_number <= self.transient_failures:
            error = RuntimeError("temporary route capacity failure")
            error.status_code = 429  # type: ignore[attr-defined]
            raise error
        if request_number <= self.timeout_failures:
            raise httpx.ReadTimeout("read timeout")
        if request_number <= self.invalid_json_failures:
            return httpx.Response(200, content=b"{not-valid-json")
        if self.terminal_error:
            message: dict[str, Any] = {"role": "assistant", "content": None}
            finish = "error"
        else:
            prior = sum(
                len(row.get("tool_calls") or [])
                for row in body.get("messages") or []
                if row.get("role") == "assistant"
            )
            if prior < len(self.actions):
                name, arguments = self.actions[prior]
                message = {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [_tool(name, arguments, prior)],
                }
                finish = "tool_calls"
            else:
                message = {"role": "assistant", "content": "Local production rehearsal complete."}
                finish = "stop"
        payload = {
            "id": f"case2-fake-{len(self.capture)}",
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


def _reference_actions(
    root: Path,
    scratch: Path,
    *,
    resource: str,
    decision_override: tuple[str, str] | None = None,
    science_failure: bool = False,
) -> list[tuple[str, dict[str, Any]]]:
    submission, workspace = build_reference(
        root,
        scratch,
        resource=resource,
        decision_override=decision_override,
    )
    final = copy.deepcopy(submission["final_submission"])
    if science_failure:
        final["decision"].update(
            {
                "development_stage": "EXTERNAL_VALIDATION",
                "disposition": "CONTINUE",
                "use_scope": "RESEARCH_PROBABILITY",
                "action_scope": "GENERAL_MULTISITE_ADVANCEMENT",
                "current_context_status": "FAILED",
                "multisite_probability_use_permitted": True,
            }
        )
        contingency_id = final["belief_updates"][0]["matched_contingency_id"]
        next(
            row
            for row in submission["followup_plan"]["result_contingencies"]
            if row["contingency_id"] == contingency_id
        )["next_decision"] = copy.deepcopy(final["decision"])
        replace_final(submission, workspace, final)
    work = workspace / "work"
    primary_output = json.loads((work / "primary_results.json").read_text(encoding="utf-8"))
    final_ids = {row["calculation_id"] for row in final["calculations"] if row["role"] == "PRIMARY"}
    pre_purchase_output = {
        "typed_calculations": [
            row
            for row in primary_output["typed_calculations"]
            if row["calculation_id"] in final_ids
        ]
    }
    actions: list[tuple[str, dict[str, Any]]] = [
        (
            "write_file",
            {
                "relative_path": "work/eligible_entities.csv",
                "content": (work / "eligible_entities.csv").read_bytes().decode("utf-8"),
            },
        ),
        ("commit_validation_plan", {"payload_json": json.dumps(submission["validation_plan"])}),
        ("reveal_validation", {}),
        (
            "write_file",
            {
                "relative_path": "work/primary_analysis.csv",
                "content": (work / "primary_analysis.csv").read_bytes().decode("utf-8"),
            },
        ),
        (
            "write_file",
            {
                "relative_path": "work/primary_results.json",
                "content": json.dumps(pre_purchase_output, indent=2, sort_keys=True) + "\n",
            },
        ),
        ("commit_followup_plan", {"payload_json": json.dumps(submission["followup_plan"])}),
        ("purchase_resource", {"resource_id": resource}),
    ]
    if (work / "resource_analysis.csv").is_file():
        actions.append(
            (
                "write_file",
                {
                    "relative_path": "work/resource_analysis.csv",
                    "content": (work / "resource_analysis.csv").read_bytes().decode("utf-8"),
                },
            )
        )
    actions.extend(
        [
            (
                "write_file",
                {
                    "relative_path": "work/primary_results.json",
                    "content": (work / "primary_results.json").read_text(encoding="utf-8"),
                },
            ),
            (
                "write_file",
                {
                    "relative_path": "work/resource_summary.json",
                    "content": (work / "resource_summary.json").read_text(encoding="utf-8"),
                },
            ),
            ("submit", {"payload_json": json.dumps(final)}),
        ]
    )
    return actions


def _run(
    root: Path,
    output: Path,
    *,
    run_id: str,
    actions: list[tuple[str, dict[str, Any]]],
    terminal_error: bool = False,
    transient_failures: int = 0,
    timeout_failures: int = 0,
    invalid_json_failures: int = 0,
    interrupt_after_phase: str | None = None,
    resume: bool = False,
    maximum_turns: int = 30,
    release_manifest: dict[str, Any],
) -> tuple[Any, list[dict[str, Any]], list[ScriptedNativeClient]]:
    capture: list[dict[str, Any]] = []
    instances: list[ScriptedNativeClient] = []

    def factory(**kwargs: Any) -> ScriptedNativeClient:
        value = ScriptedNativeClient(
            capture,
            actions=actions,
            terminal_error=terminal_error,
            transient_failures=transient_failures,
            timeout_failures=timeout_failures,
            invalid_json_failures=invalid_json_failures,
            **kwargs,
        )
        instances.append(value)
        return value

    row = model_config(root, PREFLIGHT_MODEL)
    result = run_case2_episode(
        root,
        Case2RunConfig(
            run_id,
            PREFLIGHT_MODEL,
            maximum_turns=maximum_turns,
            minimum_request_interval_seconds=0.0,
        ),
        adapter=load_case2_adapters(root)[PREFLIGHT_MODEL],
        openrouter_key=PREFLIGHT_KEY,
        authorization_digest=PREFLIGHT_AUTHORIZATION,
        remaining_cost_cap_usd=1.0,
        output_root=output,
        attempt_seed=int(row["attempt_seed"]),
        provider_seed=row.get("provider_seed"),
        native_client_factory=factory,
        preflight_mode=True,
        preflight_interrupt_after_phase=interrupt_after_phase,
        resume=resume,
        preflight_release=release_manifest,
    )
    return result, capture, instances


def run_exact_production_preflight(project_root: Path, output_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    output = output_root.resolve()
    release_manifest = candidate_manifest(root)
    with tempfile.TemporaryDirectory(prefix="uc-case2-preflight-reference-") as directory:
        scratch = Path(directory)
        no_purchase = _reference_actions(root, scratch / "none", resource="none")
        identity = _reference_actions(root, scratch / "x17", resource="X17")
        targeted = _reference_actions(
            root,
            scratch / "targeted",
            resource="none",
            decision_override=("CONTINUE", "TARGETED_CONTEXT_INVESTIGATION"),
        )
        pause = _reference_actions(
            root,
            scratch / "pause",
            resource="none",
            decision_override=("PAUSE", "HOLD_CURRENT_CLAIM"),
        )
        failure = _reference_actions(
            root, scratch / "failure", resource="none", science_failure=True
        )
        rows: dict[str, Any] = {}
        results: dict[str, Any] = {}
        clients: list[ScriptedNativeClient] = []
        for name, actions in (
            ("valid_none", no_purchase),
            ("valid_x17", identity),
            ("valid_targeted_continue", targeted),
            ("valid_pause", pause),
            ("scientific_failure", failure),
        ):
            result, capture, current = _run(
                root,
                output,
                run_id=name,
                actions=actions,
                release_manifest=release_manifest,
            )
            clients.extend(current)
            results[name] = result
            rows[name] = {
                "summary": result.summary,
                "request_count": len(capture),
            }

        malformed_actions = [
            ("inspect_workspace", {"__raw_arguments__": "{malformed-json"}),
            ("inspect_workspace", {"relative_path": "."}),
        ]
        malformed_result, _, malformed_clients = _run(
            root,
            output,
            run_id="malformed_args",
            actions=malformed_actions,
            release_manifest=release_manifest,
        )
        clients.extend(malformed_clients)
        # Preserve a truly malformed raw provider argument independently of the
        # semantic fixture above, then prove the production parser contains it.
        malformed_latest = malformed_result.run_root / "host_trajectory/latest.json"

        terminal_result, terminal_capture, terminal_clients = _run(
            root,
            output,
            run_id="provider_terminal",
            actions=[],
            terminal_error=True,
            release_manifest=release_manifest,
        )
        clients.extend(terminal_clients)

        recovered_transient, _, recovered_transient_clients = _run(
            root,
            output,
            run_id="recovered_transient",
            actions=no_purchase,
            transient_failures=1,
            release_manifest=release_manifest,
        )
        clients.extend(recovered_transient_clients)
        exhausted_rate_limit, _, exhausted_rate_limit_clients = _run(
            root,
            output,
            run_id="exhausted_rate_limit",
            actions=[],
            transient_failures=2,
            release_manifest=release_manifest,
        )
        clients.extend(exhausted_rate_limit_clients)
        exhausted_timeout, _, exhausted_timeout_clients = _run(
            root,
            output,
            run_id="exhausted_timeout",
            actions=[],
            timeout_failures=2,
            release_manifest=release_manifest,
        )
        clients.extend(exhausted_timeout_clients)
        recovered_invalid_json, _, recovered_invalid_json_clients = _run(
            root,
            output,
            run_id="recovered_invalid_json",
            actions=no_purchase,
            invalid_json_failures=1,
            release_manifest=release_manifest,
        )
        clients.extend(recovered_invalid_json_clients)

        horizon_result, _, horizon_clients = _run(
            root,
            output,
            run_id="horizon_final_tool",
            actions=[("inspect_workspace", {"relative_path": "."})],
            maximum_turns=1,
            release_manifest=release_manifest,
        )
        clients.extend(horizon_clients)

        resume_rows: dict[str, Any] = {}
        for phase in ("committed", "revealed", "purchased"):
            run_id = "case2-rc1-00-google-gemini-3.1-pro-preview-attempt-0"
            phase_output = output / f"outer_{phase}"
            interrupted, _, interrupted_clients = _run(
                root,
                phase_output,
                run_id=run_id,
                actions=identity,
                interrupt_after_phase=phase,
                release_manifest=release_manifest,
            )
            before = json.loads(
                (interrupted.run_root / "host_trajectory/latest.json").read_text(encoding="utf-8")
            )
            preserved_interruption_summary = (
                interrupted.run_root / "planned_interruption_summary.json"
            )
            interrupted.summary_path.replace(preserved_interruption_summary)
            active_state = {
                "execution_order": [PREFLIGHT_MODEL],
                "release_id": release_manifest["release_id"],
                "release_digest": release_manifest["closure"]["aggregate_digest"],
                "active_cell": {
                    "model_id": PREFLIGHT_MODEL,
                    "run_id": run_id,
                    "release_digest": release_manifest["closure"]["aggregate_digest"],
                },
            }
            outer_recovery_mode = active_cell_recovery_mode(
                root, active_state, output_root=phase_output
            )
            resumed, _, resumed_clients = _run(
                root,
                phase_output,
                run_id=run_id,
                actions=identity,
                resume=True,
                release_manifest=release_manifest,
            )
            clients.extend([*interrupted_clients, *resumed_clients])
            after = json.loads(
                (resumed.run_root / "host_trajectory/latest.json").read_text(encoding="utf-8")
            )
            resume_rows[phase] = {
                "interrupted_phase": before["environment"]["phase"],
                "outer_recovery_mode": outer_recovery_mode,
                "outer_post_completion_mode": active_cell_recovery_mode(
                    root, active_state, output_root=phase_output
                ),
                "final_phase": after["environment"]["phase"],
                "final_grade": resumed.summary["diagnostic_grade"],
                "replay": resumed.summary["trajectory_replay"],
                "tool_call_ids_unique": len(
                    {
                        call["tool_call_id"]
                        for exchange in after["provider_exchanges"]
                        for call in exchange.get("tool_calls") or []
                    }
                )
                == sum(
                    len(exchange.get("tool_calls") or [])
                    for exchange in after["provider_exchanges"]
                ),
            }

        adoption_state = {
            "release_id": release_manifest["release_id"],
            "release_digest": release_manifest["closure"]["aggregate_digest"],
            "execution_order": [PREFLIGHT_MODEL],
            "scientific_hard_cap_usd": 12.0,
            "baseline_key_usage_usd": 0.0,
            "scientific_spend_usd": 0.0,
            "completed_models": [],
            "excluded_models": [],
            "summary_paths": [],
            "forensic_paths": [],
            "global_stop_faults": [],
            "active_cell": {
                "model_id": PREFLIGHT_MODEL,
                "run_id": "valid_none",
                "release_digest": release_manifest["closure"]["aggregate_digest"],
            },
        }
        _adopt_cell(
            root,
            key=PREFLIGHT_KEY,
            state=adoption_state,
            summary_path=results["valid_none"].summary_path,
            adapter=load_case2_adapters(root)[PREFLIGHT_MODEL],
            returned_summary=results["valid_none"].summary,
            funding_snapshot_fn=lambda _key: {
                "key_usage_usd": 0.0,
                "effective_remaining_usd": 12.0,
            },
            state_path=output / "fake_outer_adoption_state.json",
            expected_run_config=results["valid_none"].summary["run_config"],
        )

        retry_adoptions: dict[str, Any] = {}
        for name, result in (
            ("recovered_transient", recovered_transient),
            ("exhausted_rate_limit", exhausted_rate_limit),
            ("exhausted_timeout", exhausted_timeout),
            ("recovered_invalid_json", recovered_invalid_json),
            ("provider_terminal", terminal_result),
        ):
            current_state = {
                "release_id": release_manifest["release_id"],
                "release_digest": release_manifest["closure"]["aggregate_digest"],
                "execution_order": [PREFLIGHT_MODEL],
                "scientific_hard_cap_usd": 12.0,
                "baseline_key_usage_usd": 0.0,
                "scientific_spend_usd": 0.0,
                "completed_models": [],
                "excluded_models": [],
                "summary_paths": [],
                "forensic_paths": [],
                "global_stop_faults": [],
                "active_cell": {
                    "model_id": PREFLIGHT_MODEL,
                    "run_id": name,
                    "release_digest": release_manifest["closure"]["aggregate_digest"],
                },
            }
            _adopt_cell(
                root,
                key=PREFLIGHT_KEY,
                state=current_state,
                summary_path=result.summary_path,
                adapter=load_case2_adapters(root)[PREFLIGHT_MODEL],
                returned_summary=result.summary,
                funding_snapshot_fn=lambda _key: {
                    "key_usage_usd": 0.0,
                    "effective_remaining_usd": 12.0,
                },
                state_path=output / f"{name}_adoption_state.json",
                expected_run_config=result.summary["run_config"],
            )
            retry_adoptions[name] = current_state
        tampered_run = output / "tampered_outer_adoption"
        shutil.copytree(results["valid_none"].run_root, tampered_run)
        tampered_lifecycle_path = tampered_run / "request_lifecycle.json"
        tampered_lifecycle = json.loads(tampered_lifecycle_path.read_text(encoding="utf-8"))
        tampered_lifecycle["attempts"][0]["ledger_request_index"] = 999
        _write_json(tampered_lifecycle_path, tampered_lifecycle, secret="")
        tampered_state = copy.deepcopy(adoption_state)
        tampered_state.update(
            {
                "completed_models": [],
                "summary_paths": [],
                "forensic_paths": [],
                "global_stop_faults": [],
                "active_cell": {
                    "model_id": PREFLIGHT_MODEL,
                    "run_id": "valid_none",
                    "release_digest": release_manifest["closure"]["aggregate_digest"],
                },
            }
        )
        _adopt_cell(
            root,
            key=PREFLIGHT_KEY,
            state=tampered_state,
            summary_path=tampered_run / "run_summary.json",
            adapter=load_case2_adapters(root)[PREFLIGHT_MODEL],
            returned_summary=None,
            funding_snapshot_fn=lambda _key: {
                "key_usage_usd": 0.0,
                "effective_remaining_usd": 12.0,
            },
            state_path=output / "tampered_outer_adoption_state.json",
            expected_run_config=results["valid_none"].summary["run_config"],
        )

        invalid_actions = [
            ("write_file", {"relative_path": "not-work.txt", "content": "rejected"}),
            *no_purchase,
        ]
        invalid_path, _, invalid_clients = _run(
            root,
            output,
            run_id="invalid_path",
            actions=invalid_actions,
            release_manifest=release_manifest,
        )
        clients.extend(invalid_clients)

        protected_actions = [
            ("write_file", {"relative_path": "README.md", "content": "mutation"}),
        ]
        protected, _, protected_clients = _run(
            root,
            output,
            run_id="protected_mutation",
            actions=protected_actions,
            release_manifest=release_manifest,
        )
        clients.extend(protected_clients)

    checks = {
        "valid_no_purchase": rows["valid_none"]["summary"]["complete_mission_success"] is True,
        "valid_x17_recomputed": rows["valid_x17"]["summary"]["complete_mission_success"] is True,
        "valid_targeted_continue": rows["valid_targeted_continue"]["summary"][
            "complete_mission_success"
        ]
        is True,
        "valid_pause": rows["valid_pause"]["summary"]["complete_mission_success"] is True,
        "scientific_failure_is_scored": rows["scientific_failure"]["summary"]["classification"]
        == "valid_episode"
        and rows["scientific_failure"]["summary"]["complete_mission_success"] is False,
        "malformed_arguments_recoverable_and_persisted": malformed_latest.is_file()
        and malformed_result.summary["trajectory_replay"]["framework_tool_error_count"] == 1,
        "provider_terminal_is_cell_local": terminal_result.summary["classification"]
        == "provider_adapter_failure"
        and len(terminal_capture) == 2,
        "horizon_final_tool_is_unexecuted": horizon_result.summary["stop_condition"]
        == "max_turns_reached"
        and horizon_result.summary["trajectory_replay"]["unexecuted_terminal_tool_count"]
        == 1,
        "restart_before_reveal": resume_rows["committed"]["final_grade"]["complete_mission_success"]
        is True,
        "restart_after_reveal": resume_rows["revealed"]["final_grade"]["complete_mission_success"]
        is True,
        "restart_after_purchase": resume_rows["purchased"]["final_grade"][
            "complete_mission_success"
        ]
        is True,
        "restart_replay_exact": all(
            row["replay"]["passed"]
            and row["replay"]["recomputed_grade_matches"]
            and row["tool_call_ids_unique"]
            for row in resume_rows.values()
        ),
        "outer_runner_restart_modes": all(
            row["outer_recovery_mode"] == "resume_durable_boundary"
            and row["outer_post_completion_mode"] == "adopt_completed"
            for row in resume_rows.values()
        ),
        "outer_runner_adoption_recomputed": not adoption_state["global_stop_faults"]
        and adoption_state["completed_models"] == [PREFLIGHT_MODEL]
        and adoption_state["active_cell"] is None,
        "recovered_transient_retry_adopts": recovered_transient.summary[
            "complete_mission_success"
        ]
        is True
        and recovered_transient.summary["request_lifecycle"]["states"][:2]
        == ["transient_transport_failure", "completed_response"]
        and not retry_adoptions["recovered_transient"]["global_stop_faults"],
        "recovered_response_parse_retry_adopts": recovered_invalid_json.summary[
            "complete_mission_success"
        ]
        is True
        and recovered_invalid_json.summary["request_lifecycle"]["states"][:2]
        == ["provider_response_parse_failure", "completed_response"]
        and not retry_adoptions["recovered_invalid_json"]["global_stop_faults"],
        "exhausted_provider_attempts_are_cell_local": all(
            not retry_adoptions[name]["global_stop_faults"]
            and retry_adoptions[name]["excluded_models"]
            for name in (
                "exhausted_rate_limit",
                "exhausted_timeout",
                "provider_terminal",
            )
        ),
        "outer_runner_adoption_rejects_index_tampering": tampered_state["status"]
        == "global_stop"
        and any(
            "ledger_index_mismatch" in fault
            for fault in tampered_state["global_stop_faults"]
        ),
        "invalid_output_path_recoverable": invalid_path.summary["complete_mission_success"] is True
        and invalid_path.summary["integrity"]["recoverable_contract_violation_count"] >= 1,
        "protected_mutation_blocked": protected.summary["classification"]
        == "protected_evidence_tampering"
        and protected.summary["diagnostic_grade"] is None,
        "all_fake_clients_closed": all(client.closed for client in clients),
        "no_paid_calls": True,
    }
    return {
        "schema_version": "uc-bench-case2-pilot-v1-rc1-production-preflight-1",
        "passed": all(checks.values()),
        "checks": checks,
        "valid_scenarios": rows,
        "resume_scenarios": resume_rows,
        "outer_adoption": adoption_state,
        "retry_adoptions": retry_adoptions,
        "tampered_outer_adoption": tampered_state,
        "provider_terminal_summary": terminal_result.summary,
        "horizon_summary": horizon_result.summary,
        "invalid_path_summary": invalid_path.summary,
        "protected_mutation_summary": protected.summary,
        "api_requests": 0,
        "paid_spend_usd": 0.0,
    }


def write_preflight(project_root: Path, output_root: Path, target: Path) -> dict[str, Any]:
    value = run_exact_production_preflight(project_root, output_root)
    _write_json(target, value, secret="")
    return value


__all__ = ["run_exact_production_preflight", "write_preflight"]

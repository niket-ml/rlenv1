"""Fresh non-scientific compatibility canaries for the frozen Case 1 pilot."""

from __future__ import annotations

import asyncio
import inspect
import json
import math
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.case1_pilot_v1_interface import production_request
from uc_bench.case1_pilot_v1_release import read_release_freeze
from uc_bench.case1_pilot_v1_runner import Case1PilotRunConfig
from uc_bench.case1_pilot_v1_runtime import (
    Case1PilotTrajectoryStore,
    build_case1_pilot_client,
)
from uc_bench.durable_runner import DurableRequestLedger
from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256
from uc_bench.mmmvp_open_rc13_trajectory import rc13_tool_call_context
from uc_bench.model_runner import _write_json
from uc_bench.v071_auth import credential_locations, redact_exception_message

COMPATIBILITY_ROOT = Path("artifacts/uc_bench_case1_pilot_v1_rc1/compatibility")
COMPATIBILITY_RESULTS = COMPATIBILITY_ROOT / "results.json"


class TechnicalCore:
    """Minimal host state for exercising persistence without scientific evidence."""

    def __init__(self) -> None:
        self.phase = "awaiting_tool"
        self.action_count = 0
        self.submission_observed = False
        self.maximum_tool_calls = 12
        self._start_hashes: dict[str, str] = {}

    def state_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "action_count": self.action_count,
            "submission_observed": self.submission_observed,
            "event_log": [],
        }

    def export_submission(self) -> dict[str, Any]:
        return {
            "technical_canary": True,
            "phase": self.phase,
            "action_count": self.action_count,
            "submission_observed": self.submission_observed,
        }


@dataclass(slots=True)
class CompatibilityBudget:
    hard_cap_usd: float = 2.0
    reported_spend_usd: float = 0.0

    def remaining(self) -> float:
        value = self.hard_cap_usd - self.reported_spend_usd
        if value <= 0:
            raise ConfigurationError("Compatibility hard cap has no remaining allowance")
        return value

    def observe(self, increment: float) -> None:
        if not math.isfinite(increment) or increment < -1e-12:
            raise ConfigurationError("Compatibility cost increment is invalid")
        self.reported_spend_usd += max(0.0, increment)
        if self.reported_spend_usd > self.hard_cap_usd + 1e-9:
            raise ConfigurationError("Compatibility hard cap was exceeded")


def neutral_request(model_id: str) -> dict[str, Any]:
    """Keep production schemas/settings while replacing all scientific content."""

    request = production_request(Case1PilotRunConfig("compatibility", model_id))
    target_length = sum(len(str(row.get("content") or "")) for row in request["messages"])
    contract = {
        "purpose": "technical_round_trip_only",
        "phases": ["inspect", "receive_result", "submit"],
        "constraints": {
            "use_function_tools": True,
            "preserve_prior_messages": True,
            "no_scientific_inference": True,
        },
        "submission": {"payload_json": "a JSON string containing a neutral acknowledgement"},
    }
    system = (
        "This is a non-scientific transport and persistence canary. The content is "
        "synthetic and contains no patient, predictor, outcome, resource, or answer data. "
        "Use the supplied production function interface exactly as requested.\n\n"
        + json.dumps(contract, indent=2, sort_keys=True)
    )
    if len(system) < target_length:
        system += "\n" + ("Neutral context padding. " * 200)[: target_length - len(system)]
    request["messages"] = [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": (
                "Call inspect_workspace once with relative_path '.'. This verifies only "
                "that the function round trip works."
            ),
        },
    ]
    return request


def _calls_from_latest(store: Case1PilotTrajectoryStore) -> list[dict[str, Any]]:
    latest = store.latest()
    return [
        dict(row)
        for row in latest.get("pending_tool_calls") or []
        if row.get("status") == "pending_recoverable"
    ]


def _record_neutral_results(
    store: Case1PilotTrajectoryStore,
    core: TechnicalCore,
    ledger: DurableRequestLedger,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for call in _calls_from_latest(store):
        call_id = str(call["tool_call_id"])
        name = str(call.get("name") or "")
        arguments = call.get("arguments")
        invocation = dict(arguments) if isinstance(arguments, dict) else {}
        result = {
            "technical_canary": True,
            "accepted_for_transport": True,
            "tool_name": name,
            "arguments_parseable": isinstance(arguments, dict),
            "scientific_state_used": False,
        }
        core.action_count += 1
        core.phase = "result_returned"
        if name == "submit":
            core.submission_observed = True
            core.phase = "terminal"
        with rc13_tool_call_context(call_id):
            store.record_tool_action(
                name=name,
                invocation_arguments=invocation,
                result=result,
                error=None,
                ledger=ledger,
            )
        rows.append({"tool_call_id": call_id, "name": name, **result})
    return rows


async def _close(client: Any) -> None:
    value = client.close()
    if inspect.isawaitable(value):
        await value


async def run_one_canary(
    project_root: Path,
    *,
    key: str,
    model_id: str,
    adapter: Any,
    output_root: Path,
    budget: CompatibilityBudget,
) -> dict[str, Any]:
    root = project_root.resolve()
    read_release_freeze(root)
    model_root = output_root / model_id.replace("/", "--")
    model_root.mkdir(parents=True, exist_ok=False)
    workspace = model_root / "workspace"
    workspace.mkdir()
    (workspace / "README.txt").write_text(
        "Synthetic compatibility workspace. No scientific evidence is present.\n",
        encoding="utf-8",
    )
    core = TechnicalCore()
    ledger = DurableRequestLedger(
        model_root / "request_ledger.json",
        adapter,
        secret=key,
        remaining_cap_usd=budget.remaining(),
    )
    store = Case1PilotTrajectoryStore(
        model_root / "host_trajectory",
        workspace=workspace,
        core=core,  # type: ignore[arg-type]
        secret=key,
        run_metadata={
            "purpose": "non_scientific_compatibility",
            "model_id": model_id,
            "case_data": False,
            "agent_visible": False,
        },
    )
    request = neutral_request(model_id)
    client: Any = None
    before = budget.reported_spend_usd
    tool_rows: list[dict[str, Any]] = []
    first_finish: str | None = None
    second_finish: str | None = None
    try:
        client = build_case1_pilot_client(
            key=key,
            adapter=adapter,
            ledger=ledger,
            store=store,
        )
        sampling = adapter.sampling_args(maximum_completion_tokens=2_000)
        first = await client.get_native_response(
            request["messages"], model_id, sampling, request["tools"]
        )
        first_raw = getattr(first, "model_dump", lambda **_: first)(mode="json")
        first_choice = (first_raw.get("choices") or [{}])[0]
        first_finish = first_choice.get("finish_reason")
        tool_rows.extend(_record_neutral_results(store, core, ledger))
        if not tool_rows:
            raise ConfigurationError("Canary returned no tool invocation")

        # Reopen the exact durable state before the second provider turn.
        await _close(client)
        client = None
        reopened = Case1PilotTrajectoryStore.reopen(
            model_root / "host_trajectory",
            workspace=workspace,
            core=core,  # type: ignore[arg-type]
            secret=key,
        )
        if not reopened.verify(require_no_pending_tools=True)["passed"]:
            raise ConfigurationError("Canary restart verification failed")
        store = reopened
        client = build_case1_pilot_client(
            key=key,
            adapter=adapter,
            ledger=ledger,
            store=store,
        )
        continuation = [
            *store.latest()["messages"],
            {
                "role": "user",
                "content": (
                    "The neutral tool result is now visible. Call submit with payload_json "
                    "set to the JSON string {\"technical_acknowledgement\":true}."
                ),
            },
        ]
        second = await client.get_native_response(
            continuation, model_id, sampling, request["tools"]
        )
        second_raw = getattr(second, "model_dump", lambda **_: second)(mode="json")
        second_choice = (second_raw.get("choices") or [{}])[0]
        second_finish = second_choice.get("finish_reason")
        tool_rows.extend(_record_neutral_results(store, core, ledger))
        verification = store.verify(require_no_pending_tools=True)
        returned = sorted(
            {
                str(row["returned_model"])
                for row in ledger.records
                if row.get("returned_model")
            }
        )
        providers = sorted(
            {
                str(row["actual_provider"])
                for row in ledger.records
                if row.get("actual_provider")
            }
        )
        round_trip = bool(
            verification["passed"]
            and len(ledger.records) == 2
            and tool_rows
            and returned == [adapter.expected_canonical_slug]
            and providers == list(adapter.provider_order)
        )
        result = {
            "model_id": model_id,
            "classification": "technically_compatible" if round_trip else "shared_harness_failure",
            "technical_round_trip_passed": round_trip,
            "tool_invocation_recorded": bool(tool_rows),
            "tool_result_ingested": len(ledger.records) == 2,
            "restart_replay_exact": verification["passed"],
            "submission_tool_observed": core.submission_observed,
            "final_response_recorded": len(ledger.records) == 2,
            "tool_arguments_parseable": all(row["arguments_parseable"] for row in tool_rows),
            "tool_names": [row["name"] for row in tool_rows],
            "requested_model": model_id,
            "returned_models": returned,
            "requested_provider": adapter.provider_order[0],
            "actual_providers": providers,
            "fallback_disabled": not adapter.allow_fallbacks,
            "reasoning_state_preservation": verification[
                "reasoning_state_preserved_when_returned"
            ],
            "usage_accounting": all(bool(row.get("usage")) for row in ledger.records),
            "first_finish_reason": first_finish,
            "second_finish_reason": second_finish,
            "request_count": len(ledger.records),
            "cost_usd": round(ledger.cumulative_reported_cost_usd, 8),
            "synthetic_neutral_content": True,
            "case_data_in_request": False,
            "production_tool_schema_sha256": canonical_sha256(request["tools"]),
            "adapter": adapter.to_dict(),
            "error": None,
        }
    except Exception as exc:
        verification = (
            store.verify(require_no_pending_tools=False)
            if store.latest_path.is_file()
            else {"passed": False, "faults": ["no_response_persisted"]}
        )
        provider_error = any(row.get("error") for row in ledger.records)
        identity_error = any(row.get("identity_violations") for row in ledger.records)
        classification = (
            "provider_specific_failure"
            if provider_error or identity_error
            else "shared_harness_failure"
        )
        result = {
            "model_id": model_id,
            "classification": classification,
            "technical_round_trip_passed": False,
            "request_count": len(ledger.records),
            "cost_usd": round(ledger.cumulative_reported_cost_usd, 8),
            "raw_response_persisted_before_adjudication": store.latest_path.is_file(),
            "trajectory_verification": verification,
            "synthetic_neutral_content": True,
            "case_data_in_request": False,
            "adapter": adapter.to_dict(),
            "error": {
                "type": type(exc).__name__,
                "message": redact_exception_message(exc, secret=key),
            },
        }
    finally:
        if client is not None:
            with suppress(Exception):
                await _close(client)
    budget.observe(ledger.cumulative_reported_cost_usd)
    _write_json(model_root / "result.json", result, secret=key)
    if credential_locations(model_root, key):
        raise ConfigurationError("Credential appeared in compatibility artifacts")
    if budget.reported_spend_usd < before:
        raise ConfigurationError("Compatibility cost accounting moved backwards")
    return result


def run_compatibility_panel(
    project_root: Path,
    *,
    key: str,
    adapters: dict[str, Any],
) -> dict[str, Any]:
    root = project_root.resolve()
    release = read_release_freeze(root)
    target = root / COMPATIBILITY_RESULTS
    output_root = root / COMPATIBILITY_ROOT / "attempts"
    if target.exists() or output_root.exists():
        raise ConfigurationError("Fresh compatibility results already exist")
    output_root.mkdir(parents=True)
    budget = CompatibilityBudget(float(release["budgets_usd"]["compatibility_hard_cap"]))
    results = [
        asyncio.run(
            run_one_canary(
                root,
                key=key,
                model_id=model_id,
                adapter=adapters[model_id],
                output_root=output_root,
                budget=budget,
            )
        )
        for model_id in release["execution_order"]
    ]
    shared = [row for row in results if row["classification"] == "shared_harness_failure"]
    compatible = [
        row for row in results if row["classification"] == "technically_compatible"
    ]
    value = {
        "schema_version": "uc-bench-case1-pilot-v1-compatibility-1",
        "executed_at": datetime.now(UTC).isoformat(),
        "status": "shared_stop" if shared else "completed",
        "release_digest": release["closure"]["aggregate_digest"],
        "hard_cap_usd": budget.hard_cap_usd,
        "cost_usd": round(budget.reported_spend_usd, 8),
        "model_count": len(results),
        "technically_compatible_model_count": len(compatible),
        "provider_specific_exclusion_count": sum(
            row["classification"] == "provider_specific_failure" for row in results
        ),
        "shared_harness_failure_count": len(shared),
        "scientific_requests": 0,
        "case_data_in_requests": False,
        "case2_requests": 0,
        "sol_requests": 0,
        "astra_requests": 0,
        "results": results,
    }
    _write_json(target, value, secret=key)
    if credential_locations(root / COMPATIBILITY_ROOT, key):
        raise ConfigurationError("Credential appeared in compatibility output")
    return value


__all__ = [
    "COMPATIBILITY_RESULTS",
    "COMPATIBILITY_ROOT",
    "CompatibilityBudget",
    "neutral_request",
    "run_compatibility_panel",
    "run_one_canary",
]

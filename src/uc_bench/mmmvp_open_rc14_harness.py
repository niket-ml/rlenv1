"""RC1.4 production-path compatibility convergence and forensic adjudication.

Compatibility here means only that the pinned provider interface can complete
the technical request/tool/result/continuation lifecycle.  Model instruction
following and scientific correctness are deliberately not compatibility gates.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.durable_runner import DurableRequestLedger
from uc_bench.durable_trajectory import (
    TrajectoryPersistenceError,
    durable_wrapped_tools,
    transcript_for_resume,
    workspace_manifest,
)
from uc_bench.errors import ConfigurationError
from uc_bench.hashing import sha256_file
from uc_bench.mmmvp_open_provider import load_open_route_contract_adapters
from uc_bench.mmmvp_open_rc13_trajectory import ACTIVE_TOOL_STATUS
from uc_bench.mmmvp_open_rc14_runner import (
    RC14DurableTrajectoryStore,
    _rc14_paced_environment,
    build_rc14_scientific_client,
)
from uc_bench.model_runner import _resolve_generated, _write_json
from uc_bench.openrouter import fetch_credit_balance, fetch_key_status
from uc_bench.v071_auth import credential_locations, redact_exception_message

ROUND01_RESULTS_PATH = Path("artifacts/mmmvp_open_rc14/compatibility_results.json")
FORENSIC_ADJUDICATION_PATH = Path(
    "artifacts/mmmvp_open_rc14/compatibility_round_01_forensic.json"
)
CONVERGENCE_RESULTS_PATH = Path(
    "artifacts/mmmvp_open_rc14/compatibility_convergence_results.json"
)
ROUND02_ATTEMPTS_ROOT = Path(
    "artifacts/mmmvp_open_rc14/compatibility_round_02_attempts"
)
HISTORICAL_TECHNICAL_PATH = Path(
    "artifacts/mmmvp_open_release/compatibility_results.json"
)
TOTAL_COMPATIBILITY_CAP_USD = 2.0
CANARY_MAXIMUM_TURNS = 2
CANARY_MAXIMUM_COMPLETION_TOKENS_PER_TURN = 5_000
CANARY_MAXIMUM_TOTAL_COMPLETION_TOKENS = 10_000
CANARY_TIMEOUT_SECONDS = 600
MINIMUM_COMPATIBLE_MODELS = 8


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError(f"Expected JSON object: {path}")
    return value


def _funding(key: str) -> dict[str, float]:
    status = fetch_key_status(key)
    credits = fetch_credit_balance(key) or {}
    account = float(credits.get("remaining_usd", 0.0))
    return {
        "key_usage_usd": status.usage_usd,
        "key_limit_usd": status.limit_usd,
        "key_limit_remaining_usd": status.limit_remaining_usd,
        "account_remaining_usd": account,
        "effective_remaining_usd": min(status.limit_remaining_usd, account),
    }


def _ledger_request(project_root: Path, model_id: str) -> dict[str, Any]:
    path = (
        project_root
        / "artifacts/mmmvp_open_rc14/compatibility_attempts"
        / model_id.replace("/", "--")
        / "request_ledger.json"
    )
    value = _read(path)
    requests = value.get("requests") or []
    if len(requests) != 1 or not isinstance(requests[0], dict):
        raise ConfigurationError(f"Round-01 ledger is incomplete for {model_id}")
    return requests[0]


def _historical_roundtrip_pass(row: Mapping[str, Any]) -> bool:
    return bool(
        row.get("classification") == "compatible"
        and row.get("request_count") == 2
        and row.get("tool_calling")
        and row.get("tool_result_ingestion")
        and row.get("structured_submission")
        and row.get("actual_providers")
        and row.get("returned_models")
    )


def forensic_adjudicate_round01(
    project_root: Path, *, write: bool = True
) -> dict[str, Any]:
    """Reassess immutable round 01 using technical evidence only."""

    root = project_root.resolve()
    original_path = root / ROUND01_RESULTS_PATH
    original_digest = sha256_file(original_path)
    original = _read(original_path)
    historical = _read(root / HISTORICAL_TECHNICAL_PATH)
    history_by_model = {
        str(row["model_id"]): row for row in historical.get("results") or []
    }
    rows: list[dict[str, Any]] = []
    for original_row in original.get("results") or []:
        model_id = str(original_row["model_id"])
        ledger = _ledger_request(root, model_id)
        prior = history_by_model.get(model_id) or {}
        prior_roundtrip = _historical_roundtrip_pass(prior)
        current_response = ledger.get("error") is None and bool(
            ledger.get("returned_model")
        )
        current_identity = current_response and not ledger.get("identity_violations")
        current_tool_call = (
            (ledger.get("response_contract") or {}).get("tool_call_count") == 1
        )
        finish_reason = ledger.get("finish_reason")
        provider_error = (ledger.get("error") or {}).get("classification")
        if model_id == "z-ai/glm-5.2":
            status = "provider_route_unresolved"
            rerun = True
            basis = (
                "Historical full round trip passed, but round 01 produced a current "
                "price-filter 404 before any response. Current route availability "
                "requires one new check."
            )
        elif model_id == "qwen/qwen3.5-397b-a17b":
            status = "technical_roundtrip_unproven"
            rerun = True
            basis = (
                "The historical round trip ended in a provider 429 and round 01 "
                "ended at the artificial reasoning-token ceiling before a tool call."
            )
        elif prior_roundtrip and current_identity:
            status = "technically_compatible"
            rerun = False
            basis = (
                "A preserved historical two-request tool/result round trip and a "
                "current parseable identity-valid response jointly establish the "
                "technical interface. Round-01 semantics are not adjudicated."
            )
        else:
            status = "technical_roundtrip_unproven"
            rerun = True
            basis = "The preserved evidence does not establish the complete lifecycle."
        rows.append(
            {
                "model_id": model_id,
                "original_round01_classification": original_row.get("classification"),
                "original_round01_error": original_row.get("error"),
                "technical_status": status,
                "rerun_required": rerun,
                "basis": basis,
                "evidence": {
                    "historical_two_request_roundtrip": prior_roundtrip,
                    "round01_parseable_provider_response": current_response,
                    "round01_identity_valid_under_production_validator": current_identity,
                    "round01_tool_call_recorded": current_tool_call,
                    "round01_finish_reason": finish_reason,
                    "round01_provider_error_class": provider_error,
                    "round01_contract_summary_semantics_ignored": True,
                },
            }
        )
    value = {
        "schema_version": "uc-bench-open-mmmvp-rc1-4-round01-forensic-1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "complete",
        "original_result_preserved": True,
        "original_result_sha256_before": original_digest,
        "original_result_sha256_after": sha256_file(original_path),
        "original_recorded_compatible_model_count": original.get(
            "compatible_model_count"
        ),
        "scientific_correctness_considered": False,
        "contract_summary_correctness_considered": False,
        "technically_compatible_model_count": sum(
            row["technical_status"] == "technically_compatible" for row in rows
        ),
        "rerun_models": [row["model_id"] for row in rows if row["rerun_required"]],
        "models": rows,
    }
    if write:
        _write_json(root / FORENSIC_ADJUDICATION_PATH, value, secret="")
    return value


class TechnicalCanaryCore:
    """Minimal non-scientific state needed by the production durable store."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace.resolve()
        self.workspace.mkdir(parents=True, exist_ok=False)
        (self.workspace / "README.md").write_text(
            "Technical provider round-trip workspace. Contains no case data.\n",
            encoding="utf-8",
        )
        self.maximum_tool_calls = 4
        self._events: list[dict[str, Any]] = []
        self._phase = "awaiting_technical_tool"
        self._start_hashes = {
            path: row["sha256"] for path, row in workspace_manifest(self.workspace).items()
        }

    def record_tool(self, payload: str) -> str:
        self._events.append({"event": "technical_tool_returned", "payload": payload})
        self._phase = "tool_result_available"
        return json.dumps(
            {"accepted": True, "technical_result": "round_trip_result"},
            sort_keys=True,
        )

    def state_dict(self) -> dict[str, Any]:
        return {
            "case_id": "non_scientific_technical_canary",
            "phase": self._phase,
            "event_log": list(self._events),
            "selected_resource": None,
            "spent_units": 0,
            "committed_plan_hash": None,
        }

    def export_submission(self) -> dict[str, Any]:
        return {"checkpoints": {}, "state": self.state_dict()}


def technical_canary_tools(core: TechnicalCanaryCore) -> list[Callable[..., Any]]:
    def record_technical_round_trip(payload: str) -> str:
        """Record any short harmless payload and return a technical result."""

        return core.record_tool(payload)

    return [record_technical_round_trip]


def technical_replay_check(
    store: RC14DurableTrajectoryStore,
    *,
    workspace: Path,
    core: TechnicalCanaryCore,
    secret: str,
) -> dict[str, Any]:
    verification = store.verify(require_no_pending_tools=False)
    if not verification["passed"]:
        return {
            **verification,
            "reopened": False,
            "transcript_exact": False,
        }
    latest = store.latest()
    reopened = RC14DurableTrajectoryStore.reopen(
        store.host_root,
        workspace=workspace,
        core=core,  # type: ignore[arg-type]
        secret=secret,
    )
    reopened_verification = reopened.verify(require_no_pending_tools=False)
    pending = [
        row
        for row in latest.get("pending_tool_calls") or []
        if row.get("status") == ACTIVE_TOOL_STATUS
    ]
    transcript_exact = False
    if not pending:
        transcript_exact = transcript_for_resume(latest) == latest.get("messages")
    return {
        **verification,
        "passed": bool(verification["passed"] and reopened_verification["passed"]),
        "reopened": reopened_verification["passed"],
        "transcript_exact": transcript_exact,
        "pending_tool_call_count": len(pending),
        "latest_record_sha256": latest.get("record_sha256"),
    }


def _provider_failure_from_records(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    for row in records:
        error = row.get("error")
        if error:
            return dict(error)
        if row.get("identity_violations"):
            return {
                "classification": "provider_adapter_failure",
                "identity_violations": list(row["identity_violations"]),
            }
    return None


def _technical_observation(
    *,
    generated: dict[str, Any],
    ledger: DurableRequestLedger,
    store: RC14DurableTrajectoryStore,
    replay: dict[str, Any],
) -> dict[str, Any]:
    latest = store.latest() if store.latest_path.is_file() else {}
    exchanges = latest.get("provider_exchanges") or []
    actions = latest.get("tool_actions") or []
    raw_receive_count = sum(
        json.loads(path.read_text(encoding="utf-8")).get("event_type")
        == "raw_model_response_received"
        for path in sorted(store.journal_root.glob("*.json"))
    )
    tool_call_count = sum(
        len(exchange.get("tool_calls") or []) for exchange in exchanges
    )
    tool_result_count = sum(
        row.get("role") == "tool" for row in latest.get("messages") or []
    )
    framework_errors = [row for row in actions if row.get("framework_generated")]
    wrapper_errors = [
        row
        for row in actions
        if row.get("error") and not row.get("framework_generated")
    ]
    provider_failure = _provider_failure_from_records(ledger.records)
    finish_reasons = [row.get("finish_reason") for row in ledger.records]
    parseable_count = len(exchanges)
    complete_round_trip = bool(
        provider_failure is None
        and parseable_count >= 2
        and tool_call_count >= 1
        and tool_result_count >= 1
        and raw_receive_count == parseable_count
        and replay.get("passed")
        and replay.get("reopened")
    )
    behavior_tags: list[str] = []
    if any(reason == "length" for reason in finish_reasons):
        behavior_tags.append("reasoning_or_output_length_termination")
    if not tool_call_count:
        behavior_tags.append("no_tool_call")
    if framework_errors:
        behavior_tags.append("recoverable_framework_tool_error")
    if wrapper_errors:
        behavior_tags.append("recoverable_wrapper_tool_error")
    if parseable_count < 2 and provider_failure is None:
        behavior_tags.append("model_did_not_complete_round_trip")
    output = (generated.get("outputs") or [{}])[0]
    return {
        "complete_technical_round_trip": complete_round_trip,
        "provider_failure": provider_failure,
        "parseable_response_count": parseable_count,
        "raw_response_receive_count": raw_receive_count,
        "tool_call_count": tool_call_count,
        "tool_result_count": tool_result_count,
        "continuation_response_recorded": parseable_count >= 2,
        "final_response_recorded": parseable_count >= 2,
        "usage_and_identity_persisted": bool(ledger.records)
        and all(bool(row.get("usage")) for row in ledger.records if not row.get("error")),
        "finish_reasons": finish_reasons,
        "behavior_tags": behavior_tags,
        "recoverable_framework_tool_error_count": len(framework_errors),
        "recoverable_wrapper_tool_error_count": len(wrapper_errors),
        "rollout_stop_condition": output.get("stop_condition"),
        "rollout_error": output.get("error"),
    }


@dataclass(slots=True)
class ConvergenceBudget:
    prior_spend_usd: float
    hard_cap_usd: float = TOTAL_COMPATIBILITY_CAP_USD
    round02_spend_usd: float = 0.0

    @property
    def remaining_usd(self) -> float:
        return self.hard_cap_usd - self.prior_spend_usd - self.round02_spend_usd

    def authorize_cell(self, adapter: Any) -> None:
        # Two requests with the scientific per-turn output setting.  The prompt
        # upper bound is deliberately generous for this tiny case-free canary.
        prompt_upper = 20_000
        upper = 2 * (
            prompt_upper * adapter.maximum_prompt_price_usd_per_million
            + CANARY_MAXIMUM_COMPLETION_TOKENS_PER_TURN
            * adapter.maximum_completion_price_usd_per_million
        ) / 1_000_000
        if not math.isfinite(upper) or upper <= 0:
            raise ConfigurationError("Invalid compatibility request cost bound")
        if upper > self.remaining_usd + 1e-12:
            raise ConfigurationError(
                "Remaining RC1.4 compatibility allowance cannot cover the next cell"
            )

    def observe(self, cost_usd: float) -> None:
        if cost_usd < 0 or not math.isfinite(cost_usd):
            raise ConfigurationError("Invalid compatibility cost observation")
        self.round02_spend_usd += cost_usd
        if self.remaining_usd < -1e-9:
            raise ConfigurationError("RC1.4 compatibility allowance was exceeded")


def _transient_provider_failure(error: Mapping[str, Any] | None) -> bool:
    if not error:
        return False
    status = error.get("http_status")
    message = str(error.get("message") or "").lower()
    return bool(
        status in {408, 409, 429}
        or isinstance(status, int)
        and status >= 500
        or any(token in message for token in ("timeout", "temporarily", "connection reset"))
    )


def _result_classification(observation: Mapping[str, Any], replay: Mapping[str, Any]) -> str:
    failure = observation.get("provider_failure")
    if failure:
        return "provider_specific_failure"
    if not replay.get("passed") or observation.get("raw_response_receive_count") != observation.get(
        "parseable_response_count"
    ):
        return "shared_infrastructure_failure"
    if observation.get("complete_technical_round_trip"):
        return "technically_compatible"
    if "reasoning_or_output_length_termination" in observation.get("behavior_tags", []):
        return "technical_inconclusive_token_exhaustion"
    return "technical_unproven_model_behavior"


def run_one_production_path_canary(
    project_root: Path,
    *,
    key: str,
    model_id: str,
    output_root: Path,
    budget: ConvergenceBudget,
    attempt_index: int,
) -> dict[str, Any]:
    """Run one case-free canary through the RC1.4 scientific lifecycle classes."""

    import verifiers as vf
    from datasets import Dataset

    root = project_root.resolve()
    adapter = load_open_route_contract_adapters(root)[model_id]
    budget.authorize_cell(adapter)
    attempt_root = output_root / model_id.replace("/", "--") / f"attempt-{attempt_index}"
    attempt_root.mkdir(parents=True, exist_ok=False)
    workspace = attempt_root / "workspace"
    core = TechnicalCanaryCore(workspace)
    ledger = DurableRequestLedger(
        attempt_root / "request_ledger.json",
        adapter,
        secret=key,
        remaining_cap_usd=budget.remaining_usd,
    )
    store = RC14DurableTrajectoryStore(
        attempt_root / "host_trajectory",
        workspace=workspace,
        core=core,  # type: ignore[arg-type]
        secret=key,
        run_metadata={
            "model_id": model_id,
            "purpose": "non_scientific_production_path_compatibility",
            "agent_visible": False,
        },
    )
    tools = durable_wrapped_tools(technical_canary_tools(core), store, ledger)
    environment = _rc14_paced_environment(
        vf,
        minimum_interval_seconds=0.0,
        dataset=Dataset.from_list(
            [
                {
                    "prompt": [
                        {
                            "role": "user",
                            "content": (
                                "Call record_technical_round_trip once with any short "
                                "harmless payload. After receiving its result, reply "
                                "briefly without another tool call."
                            ),
                        }
                    ],
                    "answer": "",
                }
            ]
        ),
        tools=tools,
        system_prompt=(
            "This is a case-free technical round trip. It contains no scientific "
            "question and your payload content is not graded."
        ),
        max_turns=CANARY_MAXIMUM_TURNS,
        timeout_seconds=CANARY_TIMEOUT_SECONDS,
        stop_errors=[TrajectoryPersistenceError],
        score_rollouts=False,
        env_id="uc-bench-open-mmmvp-rc1-4-technical-canary",
    )
    environment.set_max_total_completion_tokens(CANARY_MAXIMUM_TOTAL_COMPLETION_TOKENS)
    generated: dict[str, Any]
    client: Any = None
    exception: dict[str, Any] | None = None
    try:
        client = build_rc14_scientific_client(
            key=key,
            adapter=adapter,
            ledger=ledger,
            store=store,
        )
        generated = _resolve_generated(
            environment.evaluate(
                client=client,
                model=model_id,
                sampling_args=adapter.sampling_args(
                    maximum_completion_tokens=CANARY_MAXIMUM_COMPLETION_TOKENS_PER_TURN
                ),
                num_examples=1,
                rollouts_per_example=1,
                max_concurrent=1,
                save_results=False,
                independent_scoring=True,
                max_retries=0,
            )
        )
    except Exception as exc:
        exception = {
            "type": type(exc).__name__,
            "message": redact_exception_message(exc, secret=key),
        }
        generated = {
            "outputs": [
                {
                    "completion": [],
                    "error": exception,
                    "stop_condition": "runner_exception",
                }
            ]
        }
    finally:
        if client is not None:
            with suppress(Exception):
                _resolve_generated(client.close())
    replay = (
        technical_replay_check(store, workspace=workspace, core=core, secret=key)
        if store.latest_path.is_file()
        else {
            "passed": False,
            "faults": ["no_durable_provider_boundary"],
            "reopened": False,
            "transcript_exact": False,
        }
    )
    observation = _technical_observation(
        generated=generated,
        ledger=ledger,
        store=store,
        replay=replay,
    ) if store.latest_path.is_file() else {
        "complete_technical_round_trip": False,
        "provider_failure": next(
            (row.get("error") for row in ledger.records if row.get("error")), None
        ),
        "parseable_response_count": 0,
        "raw_response_receive_count": 0,
        "tool_call_count": 0,
        "tool_result_count": 0,
        "continuation_response_recorded": False,
        "final_response_recorded": False,
        "usage_and_identity_persisted": bool(ledger.records),
        "finish_reasons": [],
        "behavior_tags": [],
        "recoverable_framework_tool_error_count": 0,
        "recoverable_wrapper_tool_error_count": 0,
        "rollout_stop_condition": "runner_exception",
        "rollout_error": exception,
    }
    classification = _result_classification(observation, replay)
    cost = round(ledger.cumulative_reported_cost_usd, 8)
    budget.observe(cost)
    result = {
        "schema_version": "uc-bench-open-mmmvp-rc1-4-technical-canary-cell-1",
        "model_id": model_id,
        "attempt_index": attempt_index,
        "classification": classification,
        "requested_provider": adapter.provider_order[0],
        "request_count": len(ledger.records),
        "cost_usd": cost,
        "scientific_content_present": False,
        "contract_summary_semantics_checked": False,
        "production_components": {
            "request_builder": "MMMVPProviderAdapter.sampling_args",
            "identity_validator": "uc_bench.v06_provider._response_record",
            "response_parser": "RC13DurableTrajectoryStore.record_model_response",
            "tool_dispatcher": "mmmvp_open_rc14_runner._rc14_paced_environment",
            "durable_ledger": "DurableRequestLedger",
            "trajectory_store": "RC13DurableTrajectoryStore",
            "client": "RC14DurableAuditedOpenRouterClient",
        },
        "observation": observation,
        "trajectory_replay": replay,
        "provider_requests": ledger.records,
        "exception": exception,
        "adapter": adapter.to_dict(),
    }
    _write_json(attempt_root / "result.json", result, secret=key)
    if credential_locations(attempt_root, key):
        raise ConfigurationError("Credential appeared in RC1.4 canary artifacts")
    return result


def run_compatibility_convergence(project_root: Path, *, key: str) -> dict[str, Any]:
    root = project_root.resolve()
    target = root / CONVERGENCE_RESULTS_PATH
    output_root = root / ROUND02_ATTEMPTS_ROOT
    if target.exists() or output_root.exists():
        raise ConfigurationError("RC1.4 convergence evidence already exists")
    forensic = forensic_adjudicate_round01(root)
    unresolved = list(forensic["rerun_models"])
    if len(unresolved) > 7:
        raise ConfigurationError("RC1.4 forensic rerun set unexpectedly exceeds seven")
    round01 = _read(root / ROUND01_RESULTS_PATH)
    prior_spend = float(round01["cost_usd"])
    budget = ConvergenceBudget(prior_spend_usd=prior_spend)
    funding_before = _funding(key)
    if funding_before["effective_remaining_usd"] < budget.remaining_usd:
        raise ConfigurationError("Insufficient headroom for remaining compatibility allowance")
    output_root.mkdir(parents=True, exist_ok=False)
    live_results: list[dict[str, Any]] = []
    for model_id in unresolved:
        first = run_one_production_path_canary(
            root,
            key=key,
            model_id=model_id,
            output_root=output_root,
            budget=budget,
            attempt_index=0,
        )
        live_results.append(first)
        failure = first["observation"].get("provider_failure")
        if (
            first["classification"] == "provider_specific_failure"
            and _transient_provider_failure(failure)
            and first["observation"].get("parseable_response_count") == 0
        ):
            retry = run_one_production_path_canary(
                root,
                key=key,
                model_id=model_id,
                output_root=output_root,
                budget=budget,
                attempt_index=1,
            )
            live_results.append(retry)
    final_live: dict[str, dict[str, Any]] = {}
    for row in live_results:
        final_live[row["model_id"]] = row
    model_rows: list[dict[str, Any]] = []
    forensic_by_model = {row["model_id"]: row for row in forensic["models"]}
    adapters = load_open_route_contract_adapters(root)
    for model_id in adapters:
        inherited = forensic_by_model[model_id]
        live = final_live.get(model_id)
        if live is None:
            final_status = inherited["technical_status"]
            source = "forensic_round01_plus_historical_roundtrip"
            provider_exclusion = False
        else:
            final_status = live["classification"]
            source = "round02_production_path_canary"
            provider_exclusion = final_status == "provider_specific_failure"
        model_rows.append(
            {
                "model_id": model_id,
                "technical_status": final_status,
                "evidence_source": source,
                "provider_specific_exclusion": provider_exclusion,
                "forensic_round01": inherited,
                "round02": live,
            }
        )
    compatible = [
        row for row in model_rows if row["technical_status"] == "technically_compatible"
    ]
    shared_faults = [
        row for row in model_rows if row["technical_status"] == "shared_infrastructure_failure"
    ]
    funding_after = _funding(key)
    status = (
        "global_stop_shared_infrastructure"
        if shared_faults
        else "passed"
        if len(compatible) >= MINIMUM_COMPATIBLE_MODELS
        else "stopped_widespread_technical_noncompletion"
    )
    value = {
        "schema_version": "uc-bench-open-mmmvp-rc1-4-compatibility-convergence-1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": status,
        "minimum_compatible_models": MINIMUM_COMPATIBLE_MODELS,
        "model_count": len(model_rows),
        "technically_compatible_model_count": len(compatible),
        "technically_compatible_models": [row["model_id"] for row in compatible],
        "provider_specific_exclusions": [
            row["model_id"] for row in model_rows if row["provider_specific_exclusion"]
        ],
        "round01_original_preserved": sha256_file(root / ROUND01_RESULTS_PATH)
        == forensic["original_result_sha256_before"],
        "round01_cost_usd": prior_spend,
        "round02_cost_usd": round(budget.round02_spend_usd, 8),
        "total_rc14_compatibility_cost_usd": round(
            prior_spend + budget.round02_spend_usd, 8
        ),
        "total_compatibility_hard_cap_usd": TOTAL_COMPATIBILITY_CAP_USD,
        "remaining_compatibility_allowance_usd": round(budget.remaining_usd, 8),
        "round02_requested_models": unresolved,
        "round02_request_count": sum(row["request_count"] for row in live_results),
        "safe_retry_count": max(0, len(live_results) - len(unresolved)),
        "scientific_requests": 0,
        "case_data_in_requests": False,
        "heldout_requests": 0,
        "astra_requests": 0,
        "funding_before": funding_before,
        "funding_after": funding_after,
        "failure_containment": {
            "global_stop_classes": [
                "shared_harness_corruption",
                "lifecycle_inconsistency",
                "hash_drift",
                "credential_exposure",
                "protected_data_mutation",
                "budget_breach",
            ],
            "cell_exclusion_classes": [
                "isolated_provider_outage",
                "price_filter_failure",
                "route_specific_http_error",
            ],
            "maximum_transient_retry_per_cell": 1,
        },
        "models": model_rows,
    }
    _write_json(target, value, secret=key)
    if credential_locations(root / "artifacts/mmmvp_open_rc14", key):
        raise ConfigurationError("Credential appeared in RC1.4 convergence artifacts")
    return value


def load_converged_rc14_adapters(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    result = _read(root / CONVERGENCE_RESULTS_PATH)
    if result.get("status") != "passed" or result.get("scientific_requests") != 0:
        raise ConfigurationError("RC1.4 technical compatibility has not converged")
    adapters = load_open_route_contract_adapters(root)
    passing = set(result.get("technically_compatible_models") or [])
    if len(passing) < MINIMUM_COMPATIBLE_MODELS or not passing <= set(adapters):
        raise ConfigurationError("RC1.4 compatible subset is invalid")
    return {model_id: adapter for model_id, adapter in adapters.items() if model_id in passing}


__all__ = [
    "CANARY_MAXIMUM_COMPLETION_TOKENS_PER_TURN",
    "CONVERGENCE_RESULTS_PATH",
    "ConvergenceBudget",
    "FORENSIC_ADJUDICATION_PATH",
    "MINIMUM_COMPATIBLE_MODELS",
    "ROUND01_RESULTS_PATH",
    "ROUND02_ATTEMPTS_ROOT",
    "TechnicalCanaryCore",
    "forensic_adjudicate_round01",
    "load_converged_rc14_adapters",
    "run_compatibility_convergence",
    "run_one_production_path_canary",
    "technical_canary_tools",
    "technical_replay_check",
]

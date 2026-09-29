"""Minimal paid compatibility check for the revised RC1.4 visible contract."""

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

from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256
from uc_bench.mmmvp_open_provider import load_open_route_contract_adapters
from uc_bench.mmmvp_open_rc14_contract import RC14_AGENT_VISIBLE_CONTRACT
from uc_bench.model_runner import _write_json
from uc_bench.openrouter import OPENROUTER_BASE_URL, fetch_credit_balance, fetch_key_status
from uc_bench.v06_provider import _as_dict
from uc_bench.v071_auth import (
    V071RequestLedger,
    build_v071_scientific_client,
    credential_locations,
    redact_exception_message,
)

RESULTS_PATH = Path("artifacts/mmmvp_open_rc14/compatibility_results.json")
ATTEMPTS_ROOT = Path("artifacts/mmmvp_open_rc14/compatibility_attempts")
MAX_COMPLETION_TOKENS = 700
COMPATIBILITY_HARD_CAP_USD = 2.0


def _expected_acknowledgement() -> dict[str, Any]:
    return {
        "contract_revision": "rc1.4",
        "schema_version": "mmmvp-open-rc1-2",
        "unit_of_analysis_values": [
            "BIOLOGICAL_ENTITY",
            "SOURCE_RECORD_CLUSTERED",
        ],
        "calculation_cohort_fields": [
            "entity_ids",
            "included_row_count",
            "split_values",
        ],
        "analysis_table_conditional_fields": [
            "aggregation",
            "analysis_structure",
            "column_map",
        ],
        "supported_claim_nonempty_fields": [
            "calculation_ids",
            "evidence_refs",
        ],
    }


def contract_canary_tools() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "submit_contract_check",
                "description": (
                    "Submit the requested mechanical-contract facts as one JSON string."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {"payload_json": {"type": "string"}},
                    "required": ["payload_json"],
                    "additionalProperties": False,
                },
            },
        }
    ]


@dataclass(slots=True)
class ContractCompatibilityBudget:
    hard_cap_usd: float = COMPATIBILITY_HARD_CAP_USD
    reported_spend_usd: float = 0.0

    def authorize(self, adapter: Any, messages: list[dict[str, Any]], tools: list[Any]) -> None:
        # Deliberately conservative: one input character is treated as one token.
        characters = len(json.dumps({"messages": messages, "tools": tools})) + 512
        upper = (
            characters * adapter.maximum_prompt_price_usd_per_million
            + MAX_COMPLETION_TOKENS * adapter.maximum_completion_price_usd_per_million
        ) / 1_000_000
        if self.reported_spend_usd + upper > self.hard_cap_usd + 1e-12:
            raise ConfigurationError("RC1.4 compatibility cap refused the next request")

    def observe(self, ledger: V071RequestLedger, before: float) -> None:
        increment = ledger.cumulative_reported_cost_usd - before
        if increment < -1e-12 or not math.isfinite(increment):
            raise ConfigurationError("RC1.4 compatibility cost accounting is invalid")
        self.reported_spend_usd += max(0.0, increment)
        if self.reported_spend_usd > self.hard_cap_usd + 1e-9:
            raise ConfigurationError("RC1.4 compatibility cap was exceeded")


def _first_tool_call(response: Any) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    raw = _as_dict(response)
    choices = raw.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        raise ConfigurationError("Contract canary response has no first choice")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise ConfigurationError("Contract canary response has no assistant message")
    calls = message.get("tool_calls") or []
    if len(calls) != 1 or not isinstance(calls[0], dict):
        raise ConfigurationError("Expected exactly one contract submission tool call")
    call = calls[0]
    function = call.get("function") or {}
    if function.get("name") != "submit_contract_check":
        raise ConfigurationError("Contract canary used the wrong tool")
    arguments = function.get("arguments")
    try:
        outer = json.loads(arguments) if isinstance(arguments, str) else dict(arguments or {})
        payload = json.loads(outer["payload_json"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ConfigurationError("Contract canary submission is not valid nested JSON") from exc
    if payload != _expected_acknowledgement():
        raise ConfigurationError("Contract canary did not preserve the disclosed constraints")
    return raw, message, call


async def _close(client: Any) -> None:
    result = client.close()
    if inspect.isawaitable(result):
        await result


async def run_one_contract_canary(
    project_root: Path,
    *,
    key: str,
    model_id: str,
    output_root: Path,
    budget: ContractCompatibilityBudget,
) -> dict[str, Any]:
    root = project_root.resolve()
    adapter = load_open_route_contract_adapters(root)[model_id]
    model_root = output_root / model_id.replace("/", "--")
    model_root.mkdir(parents=True, exist_ok=False)
    ledger = V071RequestLedger(model_root / "request_ledger.json", adapter, secret=key)
    compact_contract = json.dumps(
        RC14_AGENT_VISIBLE_CONTRACT, sort_keys=True, separators=(",", ":")
    )
    tools = contract_canary_tools()
    messages = [
        {
            "role": "system",
            "content": (
                "This is a non-scientific document-ingestion check. Read the supplied "
                "mechanical contract and call submit_contract_check exactly once. Do not "
                "infer a scientific task or discuss API conformance."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Mechanical contract:\n{compact_contract}\n\n"
                "Submit a JSON object with exactly these five keys: contract_revision, "
                "schema_version, unit_of_analysis_values, calculation_cohort_fields, "
                "analysis_table_conditional_fields, supported_claim_nonempty_fields. "
                "Sort every list lexicographically."
            ),
        },
    ]
    client: Any = None
    raw_response: dict[str, Any] | None = None
    try:
        budget.authorize(adapter, messages, tools)
        client = build_v071_scientific_client(
            key=key,
            base_url=OPENROUTER_BASE_URL,
            adapter=adapter,
            ledger=ledger,
        )
        before = ledger.cumulative_reported_cost_usd
        response = await client.get_native_response(
            messages,
            model_id,
            adapter.sampling_args(maximum_completion_tokens=MAX_COMPLETION_TOKENS),
            tools,
        )
        budget.observe(ledger, before)
        raw_response, message, call = _first_tool_call(response)
        result = {
            "model_id": model_id,
            "classification": "compatible",
            "requested_model": model_id,
            "returned_models": sorted(
                {str(row["returned_model"]) for row in ledger.records if row.get("returned_model")}
            ),
            "requested_provider": adapter.provider_order[0],
            "actual_providers": sorted(
                {
                    str(row["actual_provider"])
                    for row in ledger.records
                    if row.get("actual_provider")
                }
            ),
            "fallback_disabled": not adapter.allow_fallbacks,
            "revised_contract_ingested": True,
            "structured_submission": bool(call.get("id")),
            "tool_calling_inherited": True,
            "tool_result_ingestion_inherited": True,
            "reasoning_state_preservation_inherited": True,
            "restart_safety_inherited": True,
            "usage_accounting": all(bool(row.get("usage")) for row in ledger.records),
            "finish_reason": (raw_response.get("choices") or [{}])[0].get("finish_reason"),
            "request_count": len(ledger.records),
            "cost_usd": round(ledger.cumulative_reported_cost_usd, 8),
            "contract_sha256": canonical_sha256(RC14_AGENT_VISIBLE_CONTRACT),
            "adapter": adapter.to_dict(),
            "error": None,
        }
        if result["actual_providers"] != list(adapter.provider_order):
            raise ConfigurationError("Contract canary provider identity changed")
        if result["returned_models"] != [adapter.expected_canonical_slug]:
            raise ConfigurationError("Contract canary returned-model identity changed")
        _write_json(model_root / "provider_response.json", raw_response, secret=key)
        _write_json(model_root / "result.json", result, secret=key)
        if credential_locations(model_root, key):
            raise ConfigurationError("Credential appeared in contract-canary artifacts")
        return result
    except Exception as exc:
        result = {
            "model_id": model_id,
            "classification": "incompatible",
            "requested_provider": adapter.provider_order[0],
            "request_count": len(ledger.records),
            "cost_usd": round(ledger.cumulative_reported_cost_usd, 8),
            "contract_sha256": canonical_sha256(RC14_AGENT_VISIBLE_CONTRACT),
            "adapter": adapter.to_dict(),
            "error": {
                "type": type(exc).__name__,
                "message": redact_exception_message(exc, secret=key),
            },
        }
        if raw_response is not None:
            _write_json(model_root / "provider_response.json", raw_response, secret=key)
        _write_json(model_root / "result.json", result, secret=key)
        return result
    finally:
        if client is not None:
            with suppress(Exception):
                await _close(client)


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


def run_contract_canaries(project_root: Path, *, key: str) -> dict[str, Any]:
    root = project_root.resolve()
    target = root / RESULTS_PATH
    output_root = root / ATTEMPTS_ROOT
    if target.exists() or output_root.exists():
        raise ConfigurationError("RC1.4 compatibility evidence already exists")
    adapters = load_open_route_contract_adapters(root)
    if len(adapters) != 10:
        raise ConfigurationError("RC1.4 requires the unchanged ten-model panel")
    funding_before = _funding(key)
    if funding_before["effective_remaining_usd"] < COMPATIBILITY_HARD_CAP_USD:
        raise ConfigurationError("Insufficient headroom for the compatibility hard cap")
    output_root.mkdir(parents=True, exist_ok=False)
    budget = ContractCompatibilityBudget()
    results = [
        asyncio.run(
            run_one_contract_canary(
                root,
                key=key,
                model_id=model_id,
                output_root=output_root,
                budget=budget,
            )
        )
        for model_id in adapters
    ]
    funding_after = _funding(key)
    compatible = [row for row in results if row["classification"] == "compatible"]
    value = {
        "schema_version": "uc-bench-open-mmmvp-rc1-4-contract-compatibility-1",
        "executed_at": datetime.now(UTC).isoformat(),
        "status": "passed" if len(compatible) == 10 else "failed",
        "purpose": "revised_contract_ingestion_and_structured_submission_only",
        "model_count": 10,
        "compatible_model_count": len(compatible),
        "incompatible_model_count": 10 - len(compatible),
        "request_count": sum(int(row["request_count"]) for row in results),
        "hard_cap_usd": COMPATIBILITY_HARD_CAP_USD,
        "cost_usd": round(budget.reported_spend_usd, 8),
        "scientific_requests": 0,
        "case_data_in_requests": False,
        "heldout_requests": 0,
        "astra_requests": 0,
        "funding_before": funding_before,
        "funding_after": funding_after,
        "contract_sha256": canonical_sha256(RC14_AGENT_VISIBLE_CONTRACT),
        "results": results,
    }
    _write_json(target, value, secret=key)
    if credential_locations(root / "artifacts/mmmvp_open_rc14", key):
        raise ConfigurationError("Credential appeared in RC1.4 compatibility artifacts")
    return value


def load_rc14_compatible_adapters(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    value = json.loads((root / RESULTS_PATH).read_text(encoding="utf-8"))
    if value.get("status") != "passed" or value.get("compatible_model_count") != 10:
        raise ConfigurationError("RC1.4 does not have ten clean compatibility passes")
    adapters = load_open_route_contract_adapters(root)
    passing = {row["model_id"] for row in value["results"] if row["classification"] == "compatible"}
    if set(adapters) != passing:
        raise ConfigurationError("RC1.4 compatibility panel differs from frozen routes")
    return adapters


__all__ = [
    "ATTEMPTS_ROOT",
    "COMPATIBILITY_HARD_CAP_USD",
    "ContractCompatibilityBudget",
    "MAX_COMPLETION_TOKENS",
    "RESULTS_PATH",
    "contract_canary_tools",
    "load_rc14_compatible_adapters",
    "run_contract_canaries",
    "run_one_contract_canary",
]

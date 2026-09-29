#!/usr/bin/env python3
"""Exercise the literal Verifiers-to-provider path without scientific content."""

from __future__ import annotations

import argparse
import json
import time
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import verifiers as vf
from datasets import Dataset

from uc_bench.errors import ConfigurationError
from uc_bench.model_runner import _resolve_generated, load_openrouter_key
from uc_bench.openrouter import fetch_key_status
from uc_bench.v061_provider import (
    EXACT_COMPATIBILITY_CAP_USD,
    MAXIMUM_COMPLETION_TOKENS,
    V061ProviderAdapter,
    V061RequestLedger,
    load_v061_provider_adapters,
)
from uc_bench.v062_provider import build_v062_client

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = (
    PROJECT_ROOT
    / "artifacts/diagnostics/hard_suite_v062_full_stack_compatibility.json"
)
ATTEMPT_ROOT = (
    PROJECT_ROOT
    / "artifacts/diagnostics/hard_suite_v062_full_stack_compatibility_attempts"
)


def record_workspace_ready(status: str) -> dict[str, str]:
    """Return a harmless tool result for the integration canary."""

    return {"recorded_status": status}


def _slug(model_id: str) -> str:
    return "".join(char if char.isalnum() else "-" for char in model_id).strip("-")


def _write(value: dict[str, Any]) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(OUTPUT_PATH)


def _run_attempt(
    *,
    key: str,
    adapter: V061ProviderAdapter,
    ledger: V061RequestLedger,
) -> dict[str, Any]:
    environment = vf.ToolEnv(
        dataset=Dataset.from_list(
            [
                {
                    "prompt": [
                        {
                            "role": "user",
                            "content": (
                                "Call record_workspace_ready exactly once with status "
                                "'ready'. After seeing its result, reply 'done'."
                            ),
                        }
                    ],
                    "answer": "",
                }
            ]
        ),
        tools=[record_workspace_ready],
        system_prompt=(
            "You are checking an ordinary local research workspace. This contains "
            "no benchmark case, biological evidence, or scientific question."
        ),
        max_turns=3,
        timeout_seconds=240,
        score_rollouts=False,
        env_id="uc-bench-v0-6-2-non-scientific-full-stack-canary",
    )
    client = build_v062_client(key=key, adapter=adapter, ledger=ledger)
    generated: dict[str, Any]
    error: dict[str, str] | None = None
    try:
        generated = _resolve_generated(
            environment.evaluate(
                client=client,
                model=adapter.model_id,
                sampling_args=adapter.sampling_args(
                    maximum_completion_tokens=MAXIMUM_COMPLETION_TOKENS
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
        error = {"type": type(exc).__name__, "message": str(exc)[:2000]}
        generated = {}
    finally:
        with suppress(Exception):
            _resolve_generated(client.close())
    records = ledger.records
    response_rows = [row for row in records if not row.get("error")]
    transport_ok = (
        bool(records)
        and not any(row.get("error") for row in records)
        and not any(row.get("identity_violations") for row in records)
    )
    normalized = bool(records) and all(
        (row.get("runner_normalization") or {}).get(
            "removed_redundant_n_equals_one"
        )
        is True
        and "n"
        not in set((row.get("request_contract") or {}).get("endpoint_visible_parameters") or [])
        for row in records
    )
    tool_call_observed = any(
        (row.get("response_contract") or {}).get("tool_call_count", 0) > 0
        for row in response_rows
    )
    tool_result_ingested = any(
        (row.get("prompt_state_contract") or {}).get("tool_result_message_count", 0)
        > 0
        for row in response_rows
    )
    stopped = bool(response_rows) and (
        response_rows[-1].get("response_contract") or {}
    ).get("finish_reason") == "stop"
    full_stack = (
        transport_ok
        and normalized
        and tool_call_observed
        and tool_result_ingested
        and stopped
    )
    if full_stack:
        classification = "compatible_full_stack"
    elif transport_ok and normalized and not tool_call_observed:
        classification = "usable_auto_tool_nonselection"
    elif transport_ok and normalized:
        classification = "usable_tool_loop_noncompletion"
    else:
        classification = "provider_adapter_failure"
    outputs = generated.get("outputs") or []
    output = outputs[0] if outputs and isinstance(outputs[0], dict) else {}
    return {
        "classification": classification,
        "request_count": len(records),
        "transport_contract_accepted": transport_ok,
        "redundant_n_normalized": normalized,
        "tool_call_observed": tool_call_observed,
        "tool_result_ingested": tool_result_ingested,
        "normal_stop_observed": stopped,
        "rollout_error": error or output.get("error"),
        "reported_cost_usd": ledger.cumulative_reported_cost_usd,
        "request_contracts": [row.get("request_contract") for row in records],
        "response_contracts": [row.get("response_contract") for row in records],
        "prompt_state_contracts": [row.get("prompt_state_contract") for row in records],
        "actual_providers": sorted(
            {str(row["actual_provider"]) for row in records if row.get("actual_provider")}
        ),
        "returned_models": sorted(
            {str(row["returned_model"]) for row in records if row.get("returned_model")}
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--maximum-incremental-cost-usd", type=float)
    args = parser.parse_args()
    if not args.execute:
        print(
            json.dumps(
                {
                    "mode": "planning_only",
                    "models": 5,
                    "maximum_attempts_per_model": 2,
                    "retry_only_after_usable_auto_tool_nonselection": True,
                    "maximum_incremental_cost_usd": EXACT_COMPATIBILITY_CAP_USD,
                    "scientific_requests": 0,
                },
                indent=2,
            )
        )
        return 0
    if args.maximum_incremental_cost_usd != EXACT_COMPATIBILITY_CAP_USD:
        raise ConfigurationError(
            f"Full-stack compatibility requires the ${EXACT_COMPATIBILITY_CAP_USD:.2f} cap"
        )
    if OUTPUT_PATH.exists():
        raise ConfigurationError("v0.6.2 full-stack result already exists")
    key = load_openrouter_key(PROJECT_ROOT)
    adapters = load_v061_provider_adapters(PROJECT_ROOT)
    usage_before = fetch_key_status(key).usage_usd
    results: list[dict[str, Any]] = []
    checkpoint: dict[str, Any] = {
        "schema_version": "0.6.2-full-stack-compatibility-1",
        "status": "running",
        "started_at": datetime.now(UTC).isoformat(),
        "non_scored": True,
        "scientific_requests": 0,
        "heldout_requests": 0,
        "astra_requests": 0,
        "maximum_incremental_cost_usd": EXACT_COMPATIBILITY_CAP_USD,
        "key_usage_before_usd": usage_before,
        "results": results,
    }
    _write(checkpoint)
    stop = False
    for model_id, adapter in adapters.items():
        attempts = []
        for attempt_index in range(2):
            status = fetch_key_status(key)
            reported = sum(
                float(attempt.get("reported_cost_usd") or 0.0)
                for row in results
                for attempt in row.get("attempts") or []
            ) + sum(float(row.get("reported_cost_usd") or 0.0) for row in attempts)
            observed = max(reported, status.usage_usd - usage_before)
            if observed >= EXACT_COMPATIBILITY_CAP_USD:
                checkpoint["status"] = "stopped_cost_cap"
                stop = True
                break
            if results or attempts:
                time.sleep(4)
            ledger = V061RequestLedger(
                ATTEMPT_ROOT / f"{_slug(model_id)}-{attempt_index}.json",
                adapter,
            )
            attempt = _run_attempt(key=key, adapter=adapter, ledger=ledger)
            attempt["attempt_index"] = attempt_index
            attempts.append(attempt)
            if attempt["classification"] == "compatible_full_stack":
                break
            if attempt["classification"] != "usable_auto_tool_nonselection":
                break
        passed = any(
            attempt["classification"] == "compatible_full_stack"
            for attempt in attempts
        )
        results.append(
            {
                "model_id": model_id,
                "classification": (
                    "compatible_full_stack" if passed else attempts[-1]["classification"]
                ),
                "attempt_count": len(attempts),
                "automatic_tool_selection_rate": (
                    sum(attempt["tool_call_observed"] for attempt in attempts)
                    / len(attempts)
                ),
                "attempts": attempts,
            }
        )
        checkpoint["results"] = results
        checkpoint["updated_at"] = datetime.now(UTC).isoformat()
        checkpoint["response_reported_spend_usd"] = round(
            sum(
                float(attempt.get("reported_cost_usd") or 0.0)
                for row in results
                for attempt in row.get("attempts") or []
            ),
            8,
        )
        _write(checkpoint)
        if stop:
            break
    usage_after = fetch_key_status(key).usage_usd
    checkpoint["key_usage_after_usd"] = usage_after
    checkpoint["key_usage_delta_usd"] = usage_after - usage_before
    checkpoint["model_adapter_pass_count"] = sum(
        row["classification"] == "compatible_full_stack" for row in results
    )
    checkpoint["status"] = (
        "passed"
        if len(results) == len(adapters)
        and checkpoint["model_adapter_pass_count"] == len(adapters)
        and max(
            float(checkpoint.get("response_reported_spend_usd") or 0.0),
            float(checkpoint["key_usage_delta_usd"]),
        )
        <= EXACT_COMPATIBILITY_CAP_USD
        else "failed"
    )
    checkpoint["completed_at"] = datetime.now(UTC).isoformat()
    _write(checkpoint)
    print(json.dumps(checkpoint, indent=2, sort_keys=True))
    return 0 if checkpoint["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

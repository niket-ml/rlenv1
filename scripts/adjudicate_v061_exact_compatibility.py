#!/usr/bin/env python3
"""Separate v0.6.1 adapter compatibility from automatic tool-use behaviour."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIRST_PATH = (
    PROJECT_ROOT
    / "artifacts/diagnostics/hard_suite_v061_exact_payload_compatibility.json"
)
SECOND_PATH = (
    PROJECT_ROOT
    / "artifacts/diagnostics/hard_suite_v061_exact_payload_compatibility_v2.json"
)
OUTPUT_PATH = (
    PROJECT_ROOT
    / "artifacts/diagnostics/"
    "hard_suite_v061_exact_payload_compatibility_adjudication.json"
)
FIRST_LEDGER_ROOT = (
    PROJECT_ROOT
    / "artifacts/diagnostics/hard_suite_v061_exact_payload_compatibility_attempts"
)


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError(f"Expected object: {path}")
    return value


def _slug(model_id: str) -> str:
    return "".join(char if char.isalnum() else "-" for char in model_id).strip("-")


def _first_finish_reason(model_id: str) -> str | None:
    ledger = _read(FIRST_LEDGER_ROOT / f"{_slug(model_id)}.json")
    requests = ledger.get("requests") or []
    if len(requests) != 1 or not isinstance(requests[0], dict):
        raise ConfigurationError(f"First exact ledger is incomplete: {model_id}")
    return requests[0].get("finish_reason")


def adjudicate(
    first: dict[str, Any], second: dict[str, Any]
) -> dict[str, Any]:
    """Pass transport only when a same-envelope tool call is already observed."""

    first_rows = {str(row["model_id"]): row for row in first.get("results") or []}
    second_rows = {str(row["model_id"]): row for row in second.get("results") or []}
    if set(first_rows) != set(second_rows) or len(second_rows) != 5:
        raise ConfigurationError("Exact compatibility attempts do not cover one panel")
    results = []
    variable_models = []
    for model_id, current in second_rows.items():
        prior = first_rows[model_id]
        contract = current.get("request_contract") or {}
        response = current.get("response_contract") or {}
        current_transport_ok = (
            not current.get("error")
            and not current.get("identity_violations")
            and current.get("actual_provider")
            in set(contract.get("provider_only") or [])
            and current.get("returned_model") in {model_id}
            and contract.get("maximum_token_field") == "max_tokens"
            and contract.get("maximum_tokens") == 5_000
            and contract.get("tool_count") == 1
            and "tool_choice" in set(contract.get("body_keys") or [])
            and contract.get("require_parameters") is True
            and contract.get("allow_fallbacks") is False
        )
        # The first and second Kimi/Claude requests used the same body envelope.
        # For other providers the second attempt added explicit automatic tool
        # choice, so only the second response is relevant to the frozen adapter.
        same_envelope = (
            (prior.get("request_contract") or {}).get(
                "request_body_contract_digest"
            )
            == contract.get("request_body_contract_digest")
        )
        observations = [response.get("tool_call_count") == 1]
        if same_envelope:
            observations.insert(0, _first_finish_reason(model_id) == "tool_calls")
        tool_verified = any(observations)
        variability = tool_verified and not all(observations)
        if variability:
            variable_models.append(model_id)
        compatible = current_transport_ok and tool_verified
        results.append(
            {
                **current,
                "classification": (
                    "compatible_exact_payload"
                    if compatible
                    else "provider_adapter_failure"
                ),
                "same_envelope_tool_call_observations": observations,
                "same_envelope_tool_call_verified": tool_verified,
                "automatic_tool_selection_rate": (
                    sum(observations) / len(observations)
                ),
                "automatic_tool_selection_variability_observed": variability,
                "current_transport_contract_accepted": current_transport_ok,
                "classification_boundary": (
                    "HTTP/schema/route/identity failures are adapter failures; "
                    "a usable response that elects not to call an optional tool is "
                    "model completion behaviour and remains reliability-visible."
                ),
            }
        )
    passed = all(
        row["classification"] == "compatible_exact_payload" for row in results
    )
    return {
        "schema_version": "0.6.1-exact-compatibility-adjudication-1",
        "status": "passed" if passed else "failed",
        "generated_at": datetime.now(UTC).isoformat(),
        "non_scored": True,
        "scientific_requests": 0,
        "heldout_requests": 0,
        "astra_requests": 0,
        "model_response_count": len(results),
        "model_adapter_pass_count": sum(
            row["classification"] == "compatible_exact_payload" for row in results
        ),
        "automatic_tool_selection_variability_models": variable_models,
        "automatic_tool_selection_variability_is_scientific_reliability_visible": True,
        "source_attempts": [
            FIRST_PATH.relative_to(PROJECT_ROOT).as_posix(),
            SECOND_PATH.relative_to(PROJECT_ROOT).as_posix(),
        ],
        "response_reported_spend_usd": round(
            float(first.get("response_reported_spend_usd") or 0.0)
            + float(second.get("response_reported_spend_usd") or 0.0),
            8,
        ),
        "results": results,
    }


def main() -> int:
    output = adjudicate(_read(FIRST_PATH), _read(SECOND_PATH))
    if OUTPUT_PATH.exists():
        existing = _read(OUTPUT_PATH)
        output["generated_at"] = existing.get("generated_at")
        if output != existing:
            raise ConfigurationError(
                "Existing v0.6.1 compatibility adjudication is not reproducible"
            )
        print(json.dumps(existing, indent=2, sort_keys=True))
        return 0 if existing["status"] == "passed" else 1
    temporary = OUTPUT_PATH.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(OUTPUT_PATH)
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if output["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

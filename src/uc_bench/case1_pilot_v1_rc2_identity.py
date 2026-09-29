"""Exact-model identity adjudication for the Case 1 pilot RC2 successor."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def adjudicate_exact_identity(
    *,
    requested_model: str,
    canonical_alias: str,
    pinned_provider: str,
    fallback_disabled: bool,
    request_records: Sequence[Mapping[str, Any]],
    raw_responses: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Accept only one requested slug or its single predeclared dated alias."""

    allowed_models = (str(requested_model), str(canonical_alias))
    faults: list[str] = []
    if not requested_model or not canonical_alias or requested_model == canonical_alias:
        faults.append("invalid_predeclared_identity_pair")
    if not pinned_provider:
        faults.append("missing_pinned_provider")
    if not fallback_disabled:
        faults.append("fallback_or_substitution_not_disabled")
    if not request_records:
        faults.append("missing_request_identity_evidence")
    if not raw_responses:
        faults.append("missing_raw_response_identity_evidence")
    if len(request_records) != len(raw_responses):
        faults.append("identity_evidence_count_mismatch")

    observations: list[dict[str, Any]] = []
    for index in range(max(len(request_records), len(raw_responses))):
        record = request_records[index] if index < len(request_records) else {}
        raw = raw_responses[index] if index < len(raw_responses) else {}
        ledger_model = record.get("returned_model")
        ledger_provider = record.get("actual_provider")
        raw_model = raw.get("model")
        raw_provider = raw.get("provider")
        row_faults: list[str] = []
        if not ledger_model or not raw_model:
            row_faults.append("missing_model_identity")
        if not ledger_provider or not raw_provider:
            row_faults.append("missing_provider_identity")
        if ledger_model and str(ledger_model) not in allowed_models:
            row_faults.append("unexpected_model_identity")
        if raw_model and str(raw_model) not in allowed_models:
            row_faults.append("unexpected_raw_model_identity")
        if ledger_provider and str(ledger_provider) != pinned_provider:
            row_faults.append("provider_drift")
        if raw_provider and str(raw_provider) != pinned_provider:
            row_faults.append("raw_provider_drift")
        if ledger_model and raw_model and str(ledger_model) != str(raw_model):
            row_faults.append("contradictory_model_identity_fields")
        if ledger_provider and raw_provider and str(ledger_provider) != str(raw_provider):
            row_faults.append("contradictory_provider_identity_fields")
        if record.get("identity_violations"):
            row_faults.append("upstream_identity_violation")
        if record.get("error") is not None:
            row_faults.append("request_did_not_produce_identity_evidence")
        observations.append(
            {
                "request_index": index,
                "ledger_model": ledger_model,
                "raw_model": raw_model,
                "ledger_provider": ledger_provider,
                "raw_provider": raw_provider,
                "faults": row_faults,
            }
        )
        faults.extend(f"request_{index}:{fault}" for fault in row_faults)

    return {
        "schema_version": "uc-bench-case1-pilot-v1-rc2-identity-1",
        "compatible": not faults,
        "requested_model": requested_model,
        "accepted_exact_models": list(allowed_models),
        "pinned_provider": pinned_provider,
        "fallback_disabled": fallback_disabled,
        "request_count": len(request_records),
        "raw_response_count": len(raw_responses),
        "observations": observations,
        "faults": list(dict.fromkeys(faults)),
        "family_level_aliases_accepted": False,
        "missing_or_conflicting_identity_fails_closed": True,
    }


__all__ = ["adjudicate_exact_identity"]

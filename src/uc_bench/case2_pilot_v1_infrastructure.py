"""Zero-cost Case-2 adoption of the proven Case-1 RC6 host infrastructure.

This module is intentionally science-free.  It makes the provider request
lifecycle and panel-containment policy available to the unfrozen Case-2
development workspace without importing Case-1 data, truth, prompts, or
grading rules.  Case-2 scientific adapters are held back until the readiness
review resolves the public context-robustness and provisional-identity
contracts.
"""

from __future__ import annotations

from typing import Any

from uc_bench.case1_pilot_v1_rc6_lifecycle import (
    RC6RequestLedger,
    RequestLifecycleMachine,
    forensic_legacy_request_adjudication,
    lifecycle_cost,
    lifecycle_identity,
    matrix_stop_level,
    transient_failure,
)


def adjudicate_archived_provider_cell(
    *,
    ledger: dict[str, Any],
    requested_model: str,
    canonical_alias: str,
    pinned_provider: str,
) -> dict[str, Any]:
    """Reclassify an archived provider ledger without inventing missing evidence.

    Older ledgers did not retain complete exception chains, so this function
    deliberately does not claim a transient subtype when the saved record
    cannot establish it.  Any terminal route error is still an isolated,
    unscored cell and cannot stop unrelated models.
    """

    rows = ledger.get("requests")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError("archived request ledger must contain an object array")
    result = forensic_legacy_request_adjudication(
        ledger_rows=rows,
        requested_model=requested_model,
        canonical_alias=canonical_alias,
        pinned_provider=pinned_provider,
    )
    result["matrix_stop_level"] = matrix_stop_level(str(result["classification"]))
    result["exception_subtype_evidence"] = (
        "complete" if all(
            row.get("error") is None
            or isinstance((row.get("error") or {}).get("exception_chain"), list)
            for row in rows
        ) else "legacy_incomplete"
    )
    return result


__all__ = [
    "RC6RequestLedger",
    "RequestLifecycleMachine",
    "adjudicate_archived_provider_cell",
    "lifecycle_cost",
    "lifecycle_identity",
    "matrix_stop_level",
    "transient_failure",
]

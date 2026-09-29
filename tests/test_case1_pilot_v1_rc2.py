from __future__ import annotations

import copy
import json
import os
from pathlib import Path

import pytest

from uc_bench.case1_pilot_v1_rc2_compatibility import (
    rc1_immutable_evidence_hashes,
    replay_preserved_compatibility,
)
from uc_bench.case1_pilot_v1_rc2_identity import adjudicate_exact_identity
from uc_bench.case1_pilot_v1_rc2_release import scientific_parity
from uc_bench.case1_pilot_v1_release import read_release_freeze, release_hashes

ROOT = Path(os.environ.get("UC_BENCH_CLEAN_ROOT", Path(__file__).resolve().parents[1])).resolve()
REQUESTED = "vendor/model-preview"
CANONICAL = "vendor/model-2026-01-02"
PROVIDER = "Pinned Provider"


def evidence(model: str = REQUESTED, provider: str = PROVIDER) -> tuple[list[dict], list[dict]]:
    record = {
        "returned_model": model,
        "actual_provider": provider,
        "identity_violations": [],
        "error": None,
    }
    raw = {"model": model, "provider": provider}
    return [record], [raw]


def adjudicate(records: list[dict], raw: list[dict], **overrides: object) -> dict:
    arguments = {
        "requested_model": REQUESTED,
        "canonical_alias": CANONICAL,
        "pinned_provider": PROVIDER,
        "fallback_disabled": True,
        "request_records": records,
        "raw_responses": raw,
    }
    arguments.update(overrides)
    return adjudicate_exact_identity(**arguments)  # type: ignore[arg-type]


def test_requested_slug_is_accepted_directly() -> None:
    records, raw = evidence()
    assert adjudicate(records, raw)["compatible"]


def test_predeclared_dated_canonical_slug_is_accepted() -> None:
    records, raw = evidence(CANONICAL)
    assert adjudicate(records, raw)["compatible"]


@pytest.mark.parametrize(
    ("model", "provider", "fault"),
    (
        ("vendor/wrong-model", PROVIDER, "unexpected_model_identity"),
        (REQUESTED, "Wrong Provider", "provider_drift"),
        ("vendor/model-preview-2", PROVIDER, "unexpected_model_identity"),
    ),
)
def test_substitution_or_provider_drift_fails(
    model: str, provider: str, fault: str
) -> None:
    records, raw = evidence(model, provider)
    result = adjudicate(records, raw)
    assert not result["compatible"]
    assert any(fault in item for item in result["faults"])


def test_missing_identity_fails_closed() -> None:
    result = adjudicate([], [])
    assert not result["compatible"]
    assert "missing_request_identity_evidence" in result["faults"]
    assert "missing_raw_response_identity_evidence" in result["faults"]


def test_fallback_or_provider_drift_declaration_fails() -> None:
    records, raw = evidence()
    result = adjudicate(records, raw, fallback_disabled=False)
    assert not result["compatible"]
    assert "fallback_or_substitution_not_disabled" in result["faults"]


def test_contradictory_identity_fields_fail() -> None:
    records, raw = evidence()
    raw[0]["model"] = CANONICAL
    result = adjudicate(records, raw)
    assert not result["compatible"]
    assert any("contradictory_model_identity_fields" in item for item in result["faults"])


def test_family_level_alias_is_not_accepted() -> None:
    records, raw = evidence("vendor/model")
    result = adjudicate(records, raw)
    assert not result["compatible"]
    assert result["family_level_aliases_accepted"] is False


def test_all_five_preserved_rc1_ledgers_replay_as_compatible_without_api_calls() -> None:
    result = replay_preserved_compatibility(ROOT)
    assert result["status"] == "passed"
    assert result["new_api_requests"] == 0
    assert result["new_compatibility_spend_usd"] == 0
    assert result["original_rc1_shared_checker_failure_count"] == 5
    assert result["corrected_rc2_compatible_count"] == 5
    assert all(
        row["original_rc1_classification"] == "shared_harness_failure"
        and row["corrected_rc2_classification"] == "technically_compatible"
        for row in result["results"]
    )


def test_deliberately_altered_preserved_ledger_evidence_fails() -> None:
    result = replay_preserved_compatibility(ROOT)
    row = result["results"][0]
    ledger = json.loads((ROOT / row["evidence_paths"]["ledger"]).read_text())
    latest = json.loads((ROOT / row["evidence_paths"]["trajectory"]).read_text())
    records = copy.deepcopy(ledger["requests"])
    raw = [copy.deepcopy(item["raw_response"]) for item in latest["provider_exchanges"]]
    records[0]["returned_model"] = records[0]["returned_model"] + "-substitute"
    adapter = row["identity"]
    altered = adjudicate_exact_identity(
        requested_model=adapter["requested_model"],
        canonical_alias=adapter["accepted_exact_models"][1],
        pinned_provider=adapter["pinned_provider"],
        fallback_disabled=True,
        request_records=records,
        raw_responses=raw,
    )
    assert not altered["compatible"]
    assert any("unexpected_model_identity" in item for item in altered["faults"])


def test_rc1_scientific_closure_and_compatibility_evidence_are_immutable() -> None:
    rc1 = read_release_freeze(ROOT)
    assert release_hashes(ROOT) == rc1["closure"]["hashes"]
    first = rc1_immutable_evidence_hashes(ROOT)
    second = rc1_immutable_evidence_hashes(ROOT)
    assert first == second
    assert scientific_parity(ROOT)["passed"]

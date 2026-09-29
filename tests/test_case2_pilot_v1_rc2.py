from __future__ import annotations

import copy
from pathlib import Path

import pytest

from uc_bench.case2_pilot_v1_rc1_provider import load_case2_config
from uc_bench.case2_pilot_v1_rc2_endpoint import (
    adjudicate_endpoint,
    parse_endpoint_identity,
    route_evidence,
)
from uc_bench.openrouter_catalog import CatalogModel

ROOT = Path(__file__).resolve().parents[1]


def _declared(model_id: str = "openai/gpt-5.1") -> dict:
    return next(
        row for row in load_case2_config(ROOT)["models"] if row["model_id"] == model_id
    )


def _endpoint(row: dict | None = None, **overrides: object) -> dict:
    declared = row or _declared()
    value = {
        "name": f"{declared['provider']} | {declared['canonical_slug']}",
        "provider_name": declared["provider"],
        "model_name": f"Human label for {declared['model_id']}",
        "context_length": declared["context_length"],
        "max_completion_tokens": declared["maximum_completion_tokens"],
        "supported_parameters": list(declared["supported_parameters"]),
        "pricing_usd_per_token": {
            "prompt": declared["maximum_route_price_usd_per_million"]["prompt"] / 1_000_000,
            "completion": (
                declared["maximum_route_price_usd_per_million"]["completion"] / 1_000_000
            ),
        },
    }
    value.update(overrides)
    return value


def _catalog(row: dict | None = None, *, canonical: str | None = None) -> CatalogModel:
    declared = row or _declared()
    return CatalogModel(
        model_id=declared["model_id"],
        canonical_slug=canonical or declared["canonical_slug"],
        context_length=declared["context_length"],
        maximum_completion_tokens=declared["maximum_completion_tokens"],
        supported_parameters=(),
        pricing={},
    )


def _adjudicate(endpoint: dict, row: dict | None = None, *, fallback_disabled: bool = True):
    declared = row or _declared()
    prices = declared["maximum_route_price_usd_per_million"]
    return adjudicate_endpoint(
        endpoint,
        expected_provider=declared["provider"],
        expected_canonical_slug=declared["canonical_slug"],
        maximum_prompt_price_usd_per_million=prices["prompt"],
        maximum_completion_price_usd_per_million=prices["completion"],
        expected_context_length=declared["context_length"],
        expected_maximum_completion_tokens=declared["maximum_completion_tokens"],
        fallback_disabled=fallback_disabled,
    )


@pytest.mark.parametrize(
    "model_id",
    [
        "google/gemini-3.1-pro-preview",
        "openai/gpt-5.1",
        "anthropic/claude-sonnet-4",
    ],
)
def test_current_live_schema_for_every_frozen_route(model_id: str) -> None:
    declared = _declared(model_id)
    result = route_evidence(
        model_id,
        declared,
        _catalog(declared),
        [_endpoint(declared)],
        fallback_disabled=True,
    )
    assert result["route_available"]
    assert result["matching_pinned_endpoint_count"] == 1
    assert result["matching_pinned_endpoints"][0]["identity"]["canonical_source"] == "current_name"


def test_historical_schema_uses_exact_model_name_slug() -> None:
    declared = _declared()
    endpoint = _endpoint(declared, name=None, model_name=declared["canonical_slug"])
    result = _adjudicate(endpoint, declared)
    assert result["passed"]
    assert result["identity"]["canonical_source"] == "historical_model_name"


def test_exact_provider_and_dated_slug_are_required() -> None:
    assert _adjudicate(_endpoint())["passed"]
    wrong_provider = _adjudicate(
        _endpoint(name=f"Wrong | {_declared()['canonical_slug']}", provider_name="Wrong")
    )
    assert not wrong_provider["passed"]
    assert "provider_mismatch" in wrong_provider["faults"]


def test_nearby_slug_fails_without_fuzzy_matching() -> None:
    nearby = "openai/gpt-5.1-20251114"
    result = _adjudicate(_endpoint(name=f"OpenAI | {nearby}"))
    assert not result["passed"]
    assert "canonical_slug_mismatch" in result["faults"]


def test_catalogue_alias_match_cannot_override_endpoint_canonical_mismatch() -> None:
    declared = _declared()
    result = route_evidence(
        declared["model_id"],
        declared,
        _catalog(declared),
        [_endpoint(name="OpenAI | openai/gpt-5.1-20251114")],
        fallback_disabled=True,
    )
    assert result["catalogue_alias_mapping_matches"]
    assert not result["route_available"]
    assert "no_endpoint_satisfies_frozen_route_constraints" in result["route_faults"]


@pytest.mark.parametrize(
    ("endpoint", "fault"),
    [
        ({"name": None, "model_name": "GPT-5.1"}, "canonical_slug_missing"),
        ({"name": "OpenAI - openai/gpt-5.1-20251113"}, "current_name_separator_malformed"),
        (
            {"name": "OpenAI | openai/gpt-5.1-20251113 | extra"},
            "current_name_duplicate_separator",
        ),
    ],
)
def test_missing_or_malformed_canonical_identity_fails_closed(
    endpoint: dict, fault: str
) -> None:
    result = _adjudicate(_endpoint(**endpoint))
    assert not result["passed"]
    assert fault in result["faults"]


def test_contradictory_current_and_historical_fields_fail() -> None:
    result = _adjudicate(_endpoint(model_name="openai/gpt-5.1-20251114"))
    assert not result["passed"]
    assert "canonical_identity_fields_contradict" in result["faults"]


def test_multiple_endpoints_retain_only_rows_satisfying_price_and_limits() -> None:
    declared = _declared()
    expensive = _endpoint()
    expensive["pricing_usd_per_token"] = copy.deepcopy(expensive["pricing_usd_per_token"])
    expensive["pricing_usd_per_token"]["completion"] = 0.000_011
    result = route_evidence(
        declared["model_id"],
        declared,
        _catalog(declared),
        [expensive, _endpoint()],
        fallback_disabled=True,
    )
    assert result["route_available"]
    assert result["endpoint_count"] == 2
    assert result["matching_pinned_endpoint_count"] == 1
    assert "completion_price_exceeds_frozen_limit" in result["endpoint_adjudications"][0][
        "faults"
    ]


def test_human_display_label_cannot_mislead_identity_parser() -> None:
    endpoint = _endpoint(model_name="OpenAI: openai/gpt-5-nearby")
    result = _adjudicate(endpoint)
    assert result["passed"]
    assert result["identity"]["display_label"] == "OpenAI: openai/gpt-5-nearby"
    assert result["identity"]["canonical_slug"] == _declared()["canonical_slug"]


def test_unexpected_fields_do_not_change_exact_adjudication_or_evidence_digest() -> None:
    baseline = _adjudicate(_endpoint())
    extended = _adjudicate(_endpoint(secretly_new_field={"ignored": True}))
    assert baseline["passed"] and extended["passed"]
    assert baseline["endpoint_evidence_sha256"] == extended["endpoint_evidence_sha256"]


def test_fallback_enabled_fails_closed() -> None:
    result = _adjudicate(_endpoint(), fallback_disabled=False)
    assert not result["passed"]
    assert "fallback_enabled" in result["faults"]


def test_missing_catalogue_alias_and_mismatching_canonical_fail_precisely() -> None:
    declared = _declared()
    missing = route_evidence(
        declared["model_id"], declared, None, [_endpoint()], fallback_disabled=True
    )
    assert not missing["route_available"]
    assert "requested_alias_missing_from_authenticated_catalogue" in missing["route_faults"]
    mismatch = route_evidence(
        declared["model_id"],
        declared,
        _catalog(declared, canonical="openai/gpt-5.1-20251114"),
        [_endpoint()],
        fallback_disabled=True,
    )
    assert not mismatch["route_available"]
    assert "catalogue_canonical_slug_mismatch" in mismatch["route_faults"]


def test_malformed_provider_and_non_string_model_name_fail_closed() -> None:
    malformed_provider = parse_endpoint_identity(_endpoint(provider_name=" OpenAI"))
    assert "provider_missing_or_malformed" in malformed_provider.faults
    malformed_label = parse_endpoint_identity(_endpoint(model_name={"name": "GPT"}))
    assert "model_name_malformed" in malformed_label.faults

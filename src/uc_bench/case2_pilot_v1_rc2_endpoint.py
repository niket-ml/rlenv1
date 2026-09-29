"""Fail-closed endpoint identity adjudication for the Case 2 RC2 successor.

This module only interprets authenticated OpenRouter catalogue metadata.  It
does not construct inference requests and has no access to Case 2 evidence.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

from uc_bench.hashing import canonical_sha256

_PROVIDER_SEPARATOR = " | "
_CANONICAL_SLUG = re.compile(
    r"^[a-z0-9][a-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._/-]*$"
)


@dataclass(frozen=True, slots=True)
class EndpointIdentity:
    provider: str | None
    canonical_slug: str | None
    canonical_source: str | None
    current_name_provider: str | None
    historical_model_slug: str | None
    display_label: str | None
    faults: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.faults

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "canonical_slug": self.canonical_slug,
            "canonical_source": self.canonical_source,
            "current_name_provider": self.current_name_provider,
            "historical_model_slug": self.historical_model_slug,
            "display_label": self.display_label,
            "valid": self.valid,
            "faults": list(self.faults),
        }


def _exact_slug(value: Any) -> str | None:
    if not isinstance(value, str) or value != value.strip():
        return None
    return value if _CANONICAL_SLUG.fullmatch(value) else None


def parse_endpoint_identity(endpoint: dict[str, Any]) -> EndpointIdentity:
    """Parse current and historical endpoint identities without inference.

    Current endpoint rows encode ``"Provider | org/model-slug"`` in ``name``.
    Historical rows stored the exact canonical slug in ``model_name``.  A
    non-slug ``model_name`` is retained only as a human display label.
    """

    faults: list[str] = []
    raw_provider = endpoint.get("provider_name")
    provider = raw_provider if isinstance(raw_provider, str) and raw_provider else None
    if provider is None or provider != raw_provider.strip():
        faults.append("provider_missing_or_malformed")

    current_provider: str | None = None
    current_slug: str | None = None
    raw_name = endpoint.get("name")
    if raw_name is not None:
        if not isinstance(raw_name, str) or not raw_name:
            faults.append("current_name_malformed")
        elif raw_name.count(_PROVIDER_SEPARATOR) != 1:
            faults.append(
                "current_name_duplicate_separator"
                if raw_name.count(_PROVIDER_SEPARATOR) > 1
                else "current_name_separator_malformed"
            )
        else:
            current_provider, candidate = raw_name.split(_PROVIDER_SEPARATOR, 1)
            if not current_provider or current_provider != current_provider.strip():
                faults.append("current_name_provider_malformed")
            if provider is not None and current_provider != provider:
                faults.append("current_name_provider_contradicts_provider_name")
            current_slug = _exact_slug(candidate)
            if current_slug is None:
                faults.append("current_name_canonical_slug_malformed")

    raw_model_name = endpoint.get("model_name")
    historical_slug = _exact_slug(raw_model_name)
    display_label = (
        raw_model_name
        if isinstance(raw_model_name, str) and historical_slug is None
        else None
    )
    if raw_model_name is not None and not isinstance(raw_model_name, str):
        faults.append("model_name_malformed")

    if current_slug is not None and historical_slug is not None:
        if current_slug != historical_slug:
            faults.append("canonical_identity_fields_contradict")
        canonical_slug = current_slug
        source = "current_name_and_historical_model_name"
    elif current_slug is not None:
        canonical_slug = current_slug
        source = "current_name"
    elif raw_name is None and historical_slug is not None:
        canonical_slug = historical_slug
        source = "historical_model_name"
    else:
        canonical_slug = None
        source = None
        faults.append("canonical_slug_missing")

    return EndpointIdentity(
        provider=provider,
        canonical_slug=canonical_slug,
        canonical_source=source,
        current_name_provider=current_provider,
        historical_model_slug=historical_slug,
        display_label=display_label,
        faults=tuple(dict.fromkeys(faults)),
    )


def _finite_nonnegative(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def adjudicate_endpoint(
    endpoint: dict[str, Any],
    *,
    expected_provider: str,
    expected_canonical_slug: str,
    maximum_prompt_price_usd_per_million: float,
    maximum_completion_price_usd_per_million: float,
    expected_context_length: int,
    expected_maximum_completion_tokens: int,
    fallback_disabled: bool,
) -> dict[str, Any]:
    """Require exact identity and every frozen route constraint."""

    identity = parse_endpoint_identity(endpoint)
    faults = list(identity.faults)
    if identity.provider is not None and identity.provider != expected_provider:
        faults.append("provider_mismatch")
    if (
        identity.canonical_slug is not None
        and identity.canonical_slug != expected_canonical_slug
    ):
        faults.append("canonical_slug_mismatch")
    if not fallback_disabled:
        faults.append("fallback_enabled")

    prices = endpoint.get("pricing_usd_per_token")
    pricing = prices if isinstance(prices, dict) else {}
    prompt = _finite_nonnegative(pricing.get("prompt"))
    completion = _finite_nonnegative(pricing.get("completion"))
    if prompt is None:
        faults.append("prompt_price_missing_or_malformed")
    elif prompt * 1_000_000 > maximum_prompt_price_usd_per_million:
        faults.append("prompt_price_exceeds_frozen_limit")
    if completion is None:
        faults.append("completion_price_missing_or_malformed")
    elif completion * 1_000_000 > maximum_completion_price_usd_per_million:
        faults.append("completion_price_exceeds_frozen_limit")

    context = endpoint.get("context_length")
    completion_limit = endpoint.get("max_completion_tokens")
    if isinstance(context, bool) or context != expected_context_length:
        faults.append("context_length_mismatch")
    if isinstance(completion_limit, bool) or completion_limit != expected_maximum_completion_tokens:
        faults.append("maximum_completion_tokens_mismatch")

    safe_evidence = {
        "name": endpoint.get("name"),
        "provider_name": endpoint.get("provider_name"),
        "model_name": endpoint.get("model_name"),
        "context_length": endpoint.get("context_length"),
        "max_completion_tokens": endpoint.get("max_completion_tokens"),
        "pricing_usd_per_token": endpoint.get("pricing_usd_per_token"),
        "supported_parameters": endpoint.get("supported_parameters"),
    }
    unique_faults = list(dict.fromkeys(faults))
    return {
        "passed": not unique_faults,
        "faults": unique_faults,
        "identity": identity.to_dict(),
        "constraints": {
            "expected_provider": expected_provider,
            "expected_canonical_slug": expected_canonical_slug,
            "maximum_prompt_price_usd_per_million": maximum_prompt_price_usd_per_million,
            "maximum_completion_price_usd_per_million": (
                maximum_completion_price_usd_per_million
            ),
            "expected_context_length": expected_context_length,
            "expected_maximum_completion_tokens": expected_maximum_completion_tokens,
            "fallback_disabled": fallback_disabled,
        },
        "endpoint_evidence": safe_evidence,
        "endpoint_evidence_sha256": canonical_sha256(safe_evidence),
    }


def route_evidence(
    model_id: str,
    declared: dict[str, Any],
    visible: Any,
    endpoints: list[dict[str, Any]],
    *,
    fallback_disabled: bool,
) -> dict[str, Any]:
    """Adjudicate catalogue alias mapping and every candidate endpoint."""

    observed_slug = visible.canonical_slug if visible is not None else None
    catalogue_match = bool(
        visible is not None
        and getattr(visible, "model_id", None) == model_id
        and observed_slug == declared["canonical_slug"]
    )
    price = declared["maximum_route_price_usd_per_million"]
    adjudications = [
        adjudicate_endpoint(
            endpoint,
            expected_provider=declared["provider"],
            expected_canonical_slug=declared["canonical_slug"],
            maximum_prompt_price_usd_per_million=float(price["prompt"]),
            maximum_completion_price_usd_per_million=float(price["completion"]),
            expected_context_length=int(declared["context_length"]),
            expected_maximum_completion_tokens=int(declared["maximum_completion_tokens"]),
            fallback_disabled=fallback_disabled,
        )
        for endpoint in endpoints
    ]
    retained = [row for row in adjudications if row["passed"]]
    route_faults: list[str] = []
    if visible is None:
        route_faults.append("requested_alias_missing_from_authenticated_catalogue")
    elif getattr(visible, "model_id", None) != model_id:
        route_faults.append("catalogue_requested_alias_mismatch")
    if visible is not None and observed_slug != declared["canonical_slug"]:
        route_faults.append("catalogue_canonical_slug_mismatch")
    if not fallback_disabled:
        route_faults.append("fallback_enabled")
    if not retained:
        route_faults.append("no_endpoint_satisfies_frozen_route_constraints")
    return {
        "model_id": model_id,
        "declared_provider": declared["provider"],
        "declared_canonical_slug": declared["canonical_slug"],
        "visible_to_key": visible is not None,
        "observed_canonical_slug": observed_slug,
        "catalogue_alias_mapping_matches": catalogue_match,
        "fallback_disabled": fallback_disabled,
        "endpoint_count": len(adjudications),
        "matching_pinned_endpoint_count": len(retained),
        "matching_pinned_endpoints": retained,
        "endpoint_adjudications": adjudications,
        "route_faults": route_faults,
        "route_available": not route_faults,
        "endpoint_evidence_set_sha256": canonical_sha256(
            [row["endpoint_evidence_sha256"] for row in adjudications]
        ),
    }


__all__ = [
    "EndpointIdentity",
    "adjudicate_endpoint",
    "parse_endpoint_identity",
    "route_evidence",
]

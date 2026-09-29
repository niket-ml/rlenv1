"""Read-only OpenRouter catalog inspection for the v0.6 provider panel.

This module deliberately contains no inference endpoint.  It exists so panel
availability, routing, interfaces, and prices can be audited before any spend.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.openrouter import OPENROUTER_BASE_URL


@dataclass(frozen=True, slots=True)
class CatalogModel:
    model_id: str
    canonical_slug: str | None
    context_length: int | None
    maximum_completion_tokens: int | None
    supported_parameters: tuple[str, ...]
    pricing: dict[str, float | None]

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "canonical_slug": self.canonical_slug,
            "context_length": self.context_length,
            "maximum_completion_tokens": self.maximum_completion_tokens,
            "supported_parameters": list(self.supported_parameters),
            "pricing_usd_per_token": self.pricing,
        }


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _integer(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None


def _get_json(url: str, key: str) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
            "User-Agent": "UC-Bench/0.6 read-only panel audit",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status = int(response.status)
            value = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        try:
            value = json.loads(exc.read().decode("utf-8"))
        except json.JSONDecodeError:
            value = {}
    except (OSError, TimeoutError, json.JSONDecodeError) as exc:
        raise ConfigurationError(f"OpenRouter catalog check failed: {type(exc).__name__}") from exc
    if not isinstance(value, dict):
        raise ConfigurationError("OpenRouter catalog response was not an object")
    return status, value


def fetch_user_catalog(key: str) -> dict[str, CatalogModel]:
    """Return models visible to the authenticated key without making a model call."""

    status, response = _get_json(f"{OPENROUTER_BASE_URL}/models/user", key)
    if status != 200:
        raise ConfigurationError(f"OpenRouter user catalog failed with HTTP {status}")
    rows = response.get("data")
    if not isinstance(rows, list):
        raise ConfigurationError("OpenRouter user catalog did not contain a model list")
    result: dict[str, CatalogModel] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            continue
        top_provider = row.get("top_provider")
        top = top_provider if isinstance(top_provider, dict) else {}
        pricing = row.get("pricing")
        prices = pricing if isinstance(pricing, dict) else {}
        result[str(row["id"])] = CatalogModel(
            model_id=str(row["id"]),
            canonical_slug=(
                str(row["canonical_slug"]) if isinstance(row.get("canonical_slug"), str) else None
            ),
            context_length=_integer(row.get("context_length")),
            maximum_completion_tokens=_integer(top.get("max_completion_tokens")),
            supported_parameters=tuple(
                sorted(str(item) for item in row.get("supported_parameters") or [])
            ),
            pricing={
                name: _number(prices.get(name))
                for name in (
                    "prompt",
                    "completion",
                    "input_cache_read",
                    "input_cache_write",
                    "internal_reasoning",
                )
            },
        )
    return result


def fetch_model_endpoints(key: str, model_id: str) -> list[dict[str, Any]]:
    """Return non-secret endpoint metadata for an exact model ID."""

    # OpenRouter's route treats the organisation/model slash as part of the
    # path; only characters within either component should be escaped.
    encoded = urllib.parse.quote(model_id, safe="/")
    status, response = _get_json(f"{OPENROUTER_BASE_URL}/models/{encoded}/endpoints", key)
    if status != 200:
        raise ConfigurationError(
            f"OpenRouter endpoint catalog for {model_id} failed with HTTP {status}"
        )
    data = response.get("data")
    if not isinstance(data, dict):
        return []
    endpoints = data.get("endpoints")
    if not isinstance(endpoints, list):
        return []
    safe: list[dict[str, Any]] = []
    for endpoint in endpoints:
        if not isinstance(endpoint, dict):
            continue
        pricing = endpoint.get("pricing")
        prices = pricing if isinstance(pricing, dict) else {}
        safe.append(
            {
                "name": endpoint.get("name"),
                "provider_name": endpoint.get("provider_name"),
                "model_name": endpoint.get("model_name"),
                "context_length": _integer(endpoint.get("context_length")),
                "max_completion_tokens": _integer(endpoint.get("max_completion_tokens")),
                "supported_parameters": sorted(
                    str(item) for item in endpoint.get("supported_parameters") or []
                ),
                "pricing_usd_per_token": {
                    name: _number(prices.get(name))
                    for name in (
                        "prompt",
                        "completion",
                        "input_cache_read",
                        "input_cache_write",
                        "internal_reasoning",
                    )
                },
            }
        )
    return safe

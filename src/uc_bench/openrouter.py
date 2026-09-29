"""Minimal host-side OpenRouter account checks with no credential serialization."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any

from uc_bench.errors import ConfigurationError

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


@dataclass(frozen=True, slots=True)
class OpenRouterKeyStatus:
    is_free_tier: bool | None
    usage_usd: float
    limit_usd: float | None
    limit_remaining_usd: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _request(path: str, key: str) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(
        f"{OPENROUTER_BASE_URL}{path}",
        headers={
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
            "User-Agent": "uc-bench-v0/0.1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            value = json.loads(response.read().decode("utf-8"))
            return int(response.status), value if isinstance(value, dict) else {}
    except urllib.error.HTTPError as exc:
        return int(exc.code), {}
    except (OSError, TimeoutError, json.JSONDecodeError) as exc:
        raise ConfigurationError(
            f"OpenRouter account check failed: {type(exc).__name__}"
        ) from exc


def fetch_key_status(key: str) -> OpenRouterKeyStatus:
    """Return non-secret usage and limit fields for the current API key."""

    status, response = _request("/key", key)
    data = response.get("data", {})
    if status != 200 or not isinstance(data, dict):
        raise ConfigurationError(f"OpenRouter key authentication failed with HTTP {status}")
    usage = data.get("usage")
    if not isinstance(usage, int | float):
        raise ConfigurationError("OpenRouter key status did not include numeric usage")
    limit = data.get("limit")
    remaining = data.get("limit_remaining")
    return OpenRouterKeyStatus(
        is_free_tier=(
            bool(data["is_free_tier"]) if data.get("is_free_tier") is not None else None
        ),
        usage_usd=float(usage),
        limit_usd=float(limit) if isinstance(limit, int | float) else None,
        limit_remaining_usd=(
            float(remaining) if isinstance(remaining, int | float) else None
        ),
    )


def fetch_credit_balance(key: str) -> dict[str, float] | None:
    """Return account credits when this key is allowed to query them."""

    status, response = _request("/credits", key)
    data = response.get("data", {})
    if status != 200 or not isinstance(data, dict):
        return None
    total = data.get("total_credits")
    usage = data.get("total_usage")
    if not isinstance(total, int | float) or not isinstance(usage, int | float):
        return None
    return {
        "total_credits_usd": float(total),
        "total_usage_usd": float(usage),
        "remaining_usd": float(total) - float(usage),
    }

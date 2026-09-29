"""Credential-safe client construction for the infrastructure-only v0.7.1.

This module deliberately accepts an already loaded secret and passes it to the
native client constructor.  It never relies on environment-variable lookup.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import httpx
from openai import AsyncOpenAI

from uc_bench.errors import ConfigurationError
from uc_bench.openrouter import OPENROUTER_BASE_URL
from uc_bench.v06_provider import _error_record
from uc_bench.v061_provider import V061ProviderAdapter, V061RequestLedger
from uc_bench.v062_provider import V062AuditedOpenRouterClient

_OPENROUTER_KEY = re.compile(r"sk-or-v1-[A-Za-z0-9_-]+")


def redact_credentials(value: Any, *, secret: str | None = None) -> Any:
    """Return a JSON-safe value with exact and pattern-matched keys removed."""

    rendered = json.dumps(value, default=str)
    if secret:
        rendered = rendered.replace(secret, "<redacted_openrouter_key>")
    rendered = _OPENROUTER_KEY.sub("<redacted_openrouter_key>", rendered)
    return json.loads(rendered)


def redact_exception_message(error: BaseException, *, secret: str) -> str:
    """Render an exception without retaining credentials."""

    value = str(error)
    value = value.replace(secret, "<redacted_openrouter_key>")
    return _OPENROUTER_KEY.sub("<redacted_openrouter_key>", value)[:2_000]


def validate_explicit_credentials(key: str, base_url: str) -> None:
    """Fail closed before constructing a transport or issuing a request."""

    if not isinstance(key, str) or not key.strip():
        raise ConfigurationError("An explicit OpenRouter API key is required")
    if not key.startswith("sk-or-v1-"):
        raise ConfigurationError("The explicit OpenRouter API key has an invalid format")
    if base_url.rstrip("/") != OPENROUTER_BASE_URL:
        raise ConfigurationError("The explicit API base URL is not OpenRouter")


class V071RequestLedger(V061RequestLedger):
    """Persist request evidence only after credential redaction.

    Authentication errors are transport failures.  They cannot become model
    scientific failures or receive a scientific score.
    """

    def __init__(
        self,
        path: Path,
        adapter: V061ProviderAdapter,
        *,
        secret: str,
    ) -> None:
        self._secret = secret
        super().__init__(path, adapter)

    def record_error(self, error: BaseException, *, latency_seconds: float) -> dict[str, Any]:
        status = getattr(error, "status_code", None)
        message = redact_exception_message(error, secret=self._secret)
        sanitized = RuntimeError(message)
        if status is not None:
            sanitized.status_code = status  # type: ignore[attr-defined]
        row = _error_record(
            sanitized,
            self.adapter,
            latency_seconds=latency_seconds,
            request_index=len(self.records),
        )
        row["error"]["type"] = type(error).__name__
        if status == 401:
            row["error"]["classification"] = "infrastructure_failure"
            row["error"]["infrastructure_subtype"] = "authentication_failure"
        elif status == 404 and any(
            marker in message.lower()
            for marker in (
                "filter by parameters",
                "requested parameters",
                "no endpoints found",
            )
        ):
            row["error"]["classification"] = "provider_adapter_failure"
        self.records.append(redact_credentials(row, secret=self._secret))
        self._checkpoint()
        return self.records[-1]

    def _checkpoint(self) -> None:
        value = redact_credentials(
            {
                "schema_version": "0.7.1-request-ledger-1",
                "adapter": self.adapter.to_dict(),
                "request_count": len(self.records),
                "cumulative_reported_cost_usd": round(
                    self.cumulative_reported_cost_usd, 8
                ),
                "requests": self.records,
            },
            secret=self._secret,
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)
        self.write_count += 1


def build_v071_scientific_client(
    *,
    key: str,
    base_url: str,
    adapter: V061ProviderAdapter,
    ledger: V071RequestLedger,
    native_client_factory: Callable[..., Any] = AsyncOpenAI,
    audited_client_factory: Callable[..., Any] = V062AuditedOpenRouterClient,
) -> V062AuditedOpenRouterClient:
    """Construct the exact production client from explicit credentials.

    Validation happens before ``native_client_factory`` is invoked.  The
    resulting native client—not a variable-name-based config—is supplied to
    the audited Verifiers adapter.
    """

    validate_explicit_credentials(key, base_url)
    timeout = httpx.Timeout(180.0, connect=10.0)
    limits = httpx.Limits(max_connections=2, max_keepalive_connections=1)
    http_client = httpx.AsyncClient(timeout=timeout, limits=limits)
    try:
        native = native_client_factory(
            api_key=key,
            base_url=base_url,
            max_retries=0,
            default_headers={"X-OpenRouter-Title": "UC-Bench v0.7.1 development"},
            http_client=http_client,
        )
    except Exception:
        # Construction failed before ownership of the transport was transferred.
        # Closing is scheduled by the caller only after a client exists; here the
        # lightweight AsyncClient has made no request and holds no workspace state.
        raise
    return audited_client_factory(native, adapter, ledger)


def credential_locations(root: Path, secret: str) -> list[str]:
    """Return relative file paths that contain the exact credential bytes."""

    if not secret:
        return []
    needle = secret.encode("utf-8")
    locations: list[str] = []
    if not root.exists():
        return locations
    for path in sorted(root.rglob("*")):
        if path.is_file() and needle in path.read_bytes():
            locations.append(path.relative_to(root).as_posix())
    return locations


def mapping_contains_credential(value: Mapping[str, Any] | list[Any], secret: str) -> bool:
    """Check in-memory prompt or payload structures for the exact key."""

    return secret in json.dumps(value, default=str)

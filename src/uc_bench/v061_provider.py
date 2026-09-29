"""Infrastructure-only v0.6.1 provider adapter.

This module leaves the v0.6 scientific task and grader untouched.  It makes the
compatibility request and scientific request share one request-body builder,
and it rejects parameters not advertised by the eligible pinned route.
"""

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from verifiers.legacy.clients.client import ClientConfig
from verifiers.legacy.utils.client_utils import (
    post_chat_completion_with_routed_experts_sidecar,
)

from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256
from uc_bench.model_runner import _temporary_environment
from uc_bench.openrouter import OPENROUTER_BASE_URL
from uc_bench.openrouter_catalog import (
    CatalogModel,
    fetch_model_endpoints,
    fetch_user_catalog,
)
from uc_bench.v06_provider import (
    AuditedOpenRouterClient,
    ProviderAdapter,
    ProviderIdentityError,
    RequestLedger,
    _as_dict,
    _error_record,
    _response_record,
)

PANEL_PATH = Path("configs/hard_suite_v06_model_panel.json")
EXACT_COMPATIBILITY_PATH = Path(
    "artifacts/diagnostics/hard_suite_v061_exact_payload_compatibility_adjudication.json"
)
MAXIMUM_COMPLETION_TOKENS = 5_000
EXACT_COMPATIBILITY_CAP_USD = 1.0


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError(f"Expected object: {path}")
    return value


def _price_within(endpoint: Mapping[str, Any], ceiling: Mapping[str, Any]) -> bool:
    pricing = endpoint.get("pricing_usd_per_token") or {}
    prompt = pricing.get("prompt")
    completion = pricing.get("completion")
    return (
        isinstance(prompt, int | float)
        and isinstance(completion, int | float)
        and float(prompt) <= float(ceiling["prompt"]) / 1_000_000
        and float(completion) <= float(ceiling["completion"]) / 1_000_000
    )


def eligible_route_contract(
    proposed: Mapping[str, Any],
    endpoints: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return parameters supported by every eligible native route."""

    providers = {str(value) for value in proposed["provider_order"]}
    ceiling = proposed["maximum_route_price_usd_per_million"]
    eligible = [
        endpoint
        for endpoint in endpoints
        if str(endpoint.get("provider_name")) in providers
        and _price_within(endpoint, ceiling)
    ]
    if not eligible:
        raise ConfigurationError(
            f"No eligible pinned route remains for {proposed['model_id']}"
        )
    supported_sets = [
        {str(name) for name in endpoint.get("supported_parameters") or []}
        for endpoint in eligible
    ]
    intersection = set.intersection(*supported_sets)
    required = {"max_tokens", "reasoning", "tools"}
    required.add("tool_choice")
    missing = required - intersection
    if missing:
        raise ConfigurationError(
            f"Eligible route lost required parameters for {proposed['model_id']}: "
            f"{sorted(missing)}"
        )
    return {
        "model_id": str(proposed["model_id"]),
        "provider_order": list(proposed["provider_order"]),
        "eligible_endpoint_count": len(eligible),
        "eligible_endpoint_names": sorted(str(row.get("name")) for row in eligible),
        "supported_parameter_intersection": sorted(intersection),
        "eligible_endpoint_contract_digest": canonical_sha256(eligible),
    }


@dataclass(frozen=True, slots=True)
class V061ProviderAdapter(ProviderAdapter):
    """v0.6 adapter with a frozen supported-parameter contract."""

    supported_parameters: tuple[str, ...]
    endpoint_contract_digest: str

    def __post_init__(self) -> None:
        ProviderAdapter.__post_init__(self)
        supported = set(self.supported_parameters)
        required = {"max_tokens", "reasoning", "tools"}
        required.add("tool_choice")
        if not required <= supported:
            raise ConfigurationError(
                f"v0.6.1 route lacks required parameters: {sorted(required - supported)}"
            )
        if not self.endpoint_contract_digest:
            raise ConfigurationError("v0.6.1 endpoint contract digest is absent")

    def sampling_args(self, *, maximum_completion_tokens: int) -> dict[str, Any]:
        if maximum_completion_tokens <= 1024 and self.provider_order == ("Anthropic",):
            raise ConfigurationError(
                "Anthropic scientific requests require room above the reasoning minimum"
            )
        supported = set(self.supported_parameters)
        extra_body: dict[str, Any] = {
            "provider": {
                "order": list(self.provider_order),
                "only": list(self.provider_order),
                "allow_fallbacks": False,
                "require_parameters": True,
                "max_price": {
                    "prompt": self.maximum_prompt_price_usd_per_million,
                    "completion": self.maximum_completion_price_usd_per_million,
                },
            },
            "reasoning": {"effort": self.requested_reasoning_effort},
        }
        # ``provider_default_auto`` and explicit ``auto`` are the same intended
        # opportunity.  Sending it explicitly prevents a provider default from
        # silently disabling tools while leaving model choice unconstrained.
        extra_body["tool_choice"] = "auto"
        if "parallel_tool_calls" in supported:
            extra_body["parallel_tool_calls"] = False
        sampling = {
            "max_tokens": maximum_completion_tokens,
            "extra_body": extra_body,
        }
        emitted = request_parameter_names(sampling, tools_present=True)
        unsupported = emitted - supported
        if unsupported:
            raise ConfigurationError(
                f"v0.6.1 would emit unsupported parameters: {sorted(unsupported)}"
            )
        return sampling

    def to_dict(self) -> dict[str, Any]:
        return {
            **ProviderAdapter.to_dict(self),
            "adapter_revision": "0.6.1",
            "supported_parameters": list(self.supported_parameters),
            "endpoint_contract_digest": self.endpoint_contract_digest,
            "compatibility_and_science_share_request_builder": True,
        }


def _adapter_from_contract(
    proposed: Mapping[str, Any], contract: Mapping[str, Any]
) -> V061ProviderAdapter:
    return V061ProviderAdapter(
        model_id=str(proposed["model_id"]),
        expected_canonical_slug=str(proposed["expected_canonical_slug"]),
        provider_order=tuple(str(value) for value in proposed["provider_order"]),
        allow_fallbacks=bool(proposed.get("allow_fallbacks")),
        requested_reasoning_effort=str(proposed["requested_reasoning_effort"]),
        tool_choice=str(proposed["scientific_tool_choice"]),
        preserve_reasoning_state=bool(
            proposed.get("preserve_reasoning_details_across_tool_turns")
        ),
        maximum_prompt_price_usd_per_million=float(
            proposed["maximum_route_price_usd_per_million"]["prompt"]
        ),
        maximum_completion_price_usd_per_million=float(
            proposed["maximum_route_price_usd_per_million"]["completion"]
        ),
        supported_parameters=tuple(contract["supported_parameter_intersection"]),
        endpoint_contract_digest=str(contract["eligible_endpoint_contract_digest"]),
    )


def discover_v061_adapters(
    project_root: Path, key: str
) -> tuple[dict[str, V061ProviderAdapter], dict[str, CatalogModel], dict[str, Any]]:
    """Discover exact routes read-only before the exact-payload canary."""

    root = project_root.resolve()
    panel = _read_object(root / PANEL_PATH)
    catalog = fetch_user_catalog(key)
    contracts: dict[str, Any] = {}
    adapters: dict[str, V061ProviderAdapter] = {}
    for proposed in panel["models"]:
        model_id = str(proposed["model_id"])
        model = catalog.get(model_id)
        if model is None or model.canonical_slug != proposed["expected_canonical_slug"]:
            raise ConfigurationError(f"v0.6.1 canonical pin failed: {model_id}")
        contract = eligible_route_contract(
            proposed, fetch_model_endpoints(key, model_id)
        )
        contracts[model_id] = contract
        adapters[model_id] = _adapter_from_contract(proposed, contract)
    return adapters, catalog, contracts


def load_v061_provider_adapters(
    project_root: Path,
) -> dict[str, V061ProviderAdapter]:
    """Load only adapters that passed the exact scientific-payload canary."""

    root = project_root.resolve()
    panel = _read_object(root / PANEL_PATH)
    result = _read_object(root / EXACT_COMPATIBILITY_PATH)
    if (
        result.get("status") != "passed"
        or result.get("scientific_requests") != 0
        or result.get("heldout_requests") != 0
        or result.get("astra_requests") != 0
    ):
        raise ConfigurationError("v0.6.1 exact-payload compatibility is not clean")
    rows = {str(row["model_id"]): row for row in result.get("results") or []}
    adapters: dict[str, V061ProviderAdapter] = {}
    for proposed in panel["models"]:
        model_id = str(proposed["model_id"])
        row = rows.get(model_id)
        if row is None or row.get("classification") != "compatible_exact_payload":
            raise ConfigurationError(f"No exact-payload pass for {model_id}")
        adapters[model_id] = _adapter_from_contract(proposed, row["route_contract"])
    if set(rows) != set(adapters):
        raise ConfigurationError("v0.6.1 panel and exact compatibility differ")
    return adapters


def request_parameter_names(
    sampling_args: Mapping[str, Any], *, tools_present: bool
) -> set[str]:
    """Return endpoint-visible parameter names from the final request body."""

    extra = sampling_args.get("extra_body") or {}
    names = {str(name) for name in sampling_args if name != "extra_body"}
    names.update(
        str(name)
        for name in extra
        if name not in {"provider"}
    )
    if tools_present:
        names.add("tools")
    return names


def exact_request_contract(body: Mapping[str, Any]) -> dict[str, Any]:
    provider = body.get("provider") or {}
    visible_parameters = sorted(
        name
        for name in body
        if name not in {"model", "messages", "provider"}
    )
    return {
        "body_keys": sorted(body),
        "endpoint_visible_parameters": visible_parameters,
        "maximum_token_field": (
            "max_tokens"
            if "max_tokens" in body
            else "max_completion_tokens"
            if "max_completion_tokens" in body
            else None
        ),
        "maximum_tokens": body.get("max_tokens", body.get("max_completion_tokens")),
        "parallel_tool_calls_present": "parallel_tool_calls" in body,
        "provider_order": list(provider.get("order") or []),
        "provider_only": list(provider.get("only") or []),
        "allow_fallbacks": provider.get("allow_fallbacks"),
        "require_parameters": provider.get("require_parameters"),
        "tool_count": len(body.get("tools") or []),
        "request_body_contract_digest": canonical_sha256(
            {
                "keys": sorted(body),
                "parameters": visible_parameters,
                "provider": provider,
                "tool_count": len(body.get("tools") or []),
            }
        ),
    }


class V061RequestLedger(RequestLedger):
    """Ledger that correctly identifies OpenRouter parameter-routing failures."""

    def record_error(self, error: BaseException, *, latency_seconds: float) -> dict[str, Any]:
        row = _error_record(
            error,
            self.adapter,
            latency_seconds=latency_seconds,
            request_index=len(self.records),
        )
        lowered = str(error).lower()
        status = getattr(error, "status_code", None)
        if status == 404 and (
            "filter by parameters" in lowered
            or "requested parameters" in lowered
            or "no endpoints found" in lowered
        ):
            row["error"]["classification"] = "provider_adapter_failure"
        self.records.append(row)
        self._checkpoint()
        return row


class V061AuditedOpenRouterClient(AuditedOpenRouterClient):
    """Client whose live body is exactly the body checked by compatibility."""

    async def get_native_response(
        self,
        prompt: Any,
        model: str,
        sampling_args: Any,
        tools: Any = None,
        **kwargs: Any,
    ) -> Any:
        request_args = dict(sampling_args)
        extra_body = dict(request_args.pop("extra_body", {}) or {})
        body: dict[str, Any] = {
            "model": model,
            "messages": prompt,
            **request_args,
            **extra_body,
        }
        if tools:
            body["tools"] = tools
        contract = exact_request_contract(body)
        supported = set(getattr(self.adapter, "supported_parameters", ()))
        unsupported = set(contract["endpoint_visible_parameters"]) - supported
        if unsupported:
            raise ConfigurationError(
                f"Live request contains unsupported parameters: {sorted(unsupported)}"
            )
        extra_headers = kwargs.pop("extra_headers", None)
        if kwargs:
            raise ConfigurationError(
                f"Unexpected native request kwargs: {sorted(kwargs)}"
            )
        started = time.monotonic()
        try:
            response = await post_chat_completion_with_routed_experts_sidecar(
                self.client,
                "/chat/completions",
                body=body,
                extra_headers=extra_headers,
            )
        except Exception as exc:
            row = self.ledger.record_error(
                exc, latency_seconds=time.monotonic() - started
            )
            row["request_contract"] = contract
            self.ledger._checkpoint()  # noqa: SLF001 - same audited ledger boundary
            raise
        row = _response_record(
            response,
            self.adapter,
            latency_seconds=time.monotonic() - started,
            request_index=len(self.ledger.records),
        )
        raw = _as_dict(response)
        choices = raw.get("choices") or []
        choice = choices[0] if choices and isinstance(choices[0], dict) else {}
        message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
        row["response_contract"] = {
            "finish_reason": choice.get("finish_reason"),
            "tool_call_count": len(message.get("tool_calls") or []),
            "content_present": bool(message.get("content")),
            "reasoning_state_present": any(
                message.get(field)
                for field in ("reasoning", "reasoning_content", "reasoning_details")
            ),
        }
        row["request_contract"] = contract
        self.ledger.records.append(row)
        self.ledger._checkpoint()  # noqa: SLF001 - same audited ledger boundary
        if row["identity_violations"]:
            raise ProviderIdentityError(
                "Provider identity validation failed: "
                + ", ".join(row["identity_violations"])
            )
        return response


def v061_client_config() -> ClientConfig:
    return ClientConfig(
        client_type="openai_chat_completions",
        api_key_var="OPENROUTER_API_KEY",
        api_base_url=OPENROUTER_BASE_URL,
        timeout=180.0,
        connect_timeout=10.0,
        max_connections=2,
        max_keepalive_connections=1,
        max_retries=0,
        extra_headers={"X-OpenRouter-Title": "UC-Bench v0.6.1"},
    )


def build_v061_client(
    *, key: str, adapter: V061ProviderAdapter, ledger: V061RequestLedger
) -> V061AuditedOpenRouterClient:
    """Construct the client only while its credential environment is present."""

    with _temporary_environment("OPENROUTER_API_KEY", key):
        return V061AuditedOpenRouterClient(v061_client_config(), adapter, ledger)


def verify_live_v061_identity(
    key: str, adapters: dict[str, V061ProviderAdapter]
) -> dict[str, Any]:
    """Verify canonical identity and the frozen parameter contract read-only."""

    catalog = fetch_user_catalog(key)
    rows = []
    for model_id, adapter in adapters.items():
        model = catalog.get(model_id)
        if model is None or model.canonical_slug != adapter.expected_canonical_slug:
            raise ConfigurationError(f"v0.6.1 live canonical pin failed: {model_id}")
        contract = eligible_route_contract(
            {
                "model_id": adapter.model_id,
                "provider_order": list(adapter.provider_order),
                "scientific_tool_choice": adapter.tool_choice,
                "maximum_route_price_usd_per_million": {
                    "prompt": adapter.maximum_prompt_price_usd_per_million,
                    "completion": adapter.maximum_completion_price_usd_per_million,
                },
            },
            fetch_model_endpoints(key, model_id),
        )
        if contract["eligible_endpoint_contract_digest"] != adapter.endpoint_contract_digest:
            raise ConfigurationError(f"v0.6.1 endpoint contract changed: {model_id}")
        emitted = request_parameter_names(
            adapter.sampling_args(
                maximum_completion_tokens=MAXIMUM_COMPLETION_TOKENS
            ),
            tools_present=True,
        )
        if not emitted <= set(contract["supported_parameter_intersection"]):
            raise ConfigurationError(f"v0.6.1 unsupported live payload: {model_id}")
        rows.append(
            {
                "model_id": model_id,
                "canonical_slug": model.canonical_slug,
                "provider_order": list(adapter.provider_order),
                "request_parameters": sorted(emitted),
                "endpoint_contract_digest": adapter.endpoint_contract_digest,
            }
        )
    return {
        "checked_at": datetime.now(UTC).isoformat(),
        "status": "passed",
        "inference_requests_made": 0,
        "models": rows,
    }

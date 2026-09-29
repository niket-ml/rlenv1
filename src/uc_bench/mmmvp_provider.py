"""Pinned, provider-aware adapters for the ten-model MMMVP panel."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256
from uc_bench.openrouter_catalog import CatalogModel, fetch_model_endpoints, fetch_user_catalog

PANEL_PATH = Path("configs/uc_bench_mmmvp_model_panel.json")
ROUTE_CONTRACTS_PATH = Path("artifacts/mmmvp/route_contracts.json")
COMPATIBILITY_PATH = Path("artifacts/mmmvp/compatibility_results.json")


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError(f"Expected object: {path}")
    return value


def _price_within(endpoint: Mapping[str, Any], row: Mapping[str, Any]) -> bool:
    price = endpoint.get("pricing_usd_per_token") or {}
    ceiling = row["maximum_route_price_usd_per_million"]
    prompt = price.get("prompt")
    completion = price.get("completion")
    return bool(
        isinstance(prompt, (int, float))
        and isinstance(completion, (int, float))
        and float(prompt) <= float(ceiling["prompt"]) / 1_000_000 + 1e-15
        and float(completion) <= float(ceiling["completion"]) / 1_000_000 + 1e-15
    )


def route_contract(row: Mapping[str, Any], endpoints: list[dict[str, Any]]) -> dict[str, Any]:
    eligible = [
        endpoint
        for endpoint in endpoints
        if endpoint.get("provider_name") == row["provider"] and _price_within(endpoint, row)
    ]
    if not eligible:
        raise ConfigurationError(f"No eligible pinned route for {row['model_id']}")
    intersections = [set(endpoint.get("supported_parameters") or []) for endpoint in eligible]
    supported = set.intersection(*intersections)
    required = {"max_tokens", "tools", "tool_choice"}
    mode = row["reasoning_mode"]
    if mode in {"effort", "enabled"}:
        required.add("reasoning")
    if mode == "effort":
        required.add("reasoning_effort")
    missing = required - supported
    if missing:
        raise ConfigurationError(
            f"Pinned route for {row['model_id']} lacks {sorted(missing)}"
        )
    return {
        "model_id": row["model_id"],
        "canonical_slug": row["expected_canonical_slug"],
        "provider": row["provider"],
        "reasoning_mode": mode,
        "eligible_endpoint_count": len(eligible),
        "eligible_endpoint_names": sorted(str(item.get("name")) for item in eligible),
        "supported_parameter_intersection": sorted(supported),
        "context_length_minimum": min(int(item["context_length"]) for item in eligible),
        "maximum_completion_tokens_minimum": min(
            int(item["max_completion_tokens"]) for item in eligible
        ),
        "eligible_endpoints": eligible,
        "contract_digest": canonical_sha256(eligible),
    }


@dataclass(frozen=True, slots=True)
class MMMVPProviderAdapter:
    model_id: str
    expected_canonical_slug: str
    provider_order: tuple[str, ...]
    allow_fallbacks: bool
    requested_reasoning_effort: str
    reasoning_mode: str
    tool_choice: str
    preserve_reasoning_state: bool
    maximum_prompt_price_usd_per_million: float
    maximum_completion_price_usd_per_million: float
    supported_parameters: tuple[str, ...]
    endpoint_contract_digest: str
    context_length: int
    maximum_completion_tokens: int

    def __post_init__(self) -> None:
        if len(self.provider_order) != 1 or self.allow_fallbacks:
            raise ConfigurationError("MMMVP requires one provider and no fallback")
        if self.reasoning_mode not in {"effort", "enabled", "not_supported"}:
            raise ConfigurationError("Unknown reasoning mode")
        if self.tool_choice != "auto":
            raise ConfigurationError("Every MMMVP route uses automatic tool choice")
        if min(self.context_length, self.maximum_completion_tokens) <= 0:
            raise ConfigurationError("Provider token limits must be positive")

    @property
    def accepted_response_models(self) -> set[str]:
        return {self.model_id, self.expected_canonical_slug}

    def sampling_args(self, *, maximum_completion_tokens: int) -> dict[str, Any]:
        if maximum_completion_tokens <= 1024 and self.provider_order == ("Anthropic",):
            raise ConfigurationError("Anthropic needs room above its reasoning minimum")
        maximum = min(int(maximum_completion_tokens), self.maximum_completion_tokens)
        extra: dict[str, Any] = {
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
            "tool_choice": "auto",
        }
        if self.reasoning_mode == "effort":
            extra["reasoning"] = {"effort": self.requested_reasoning_effort}
        elif self.reasoning_mode == "enabled":
            extra["reasoning"] = {"enabled": True}
        emitted = {"max_tokens", "tools", "tool_choice"}
        if "reasoning" in extra:
            emitted.add("reasoning")
        if not emitted <= set(self.supported_parameters):
            unsupported = sorted(emitted - set(self.supported_parameters))
            raise ConfigurationError(
                f"Adapter would emit unsupported parameters: {unsupported}"
            )
        return {"max_tokens": maximum, "extra_body": extra}

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter_revision": "mmmvp-1",
            "model_id": self.model_id,
            "expected_canonical_slug": self.expected_canonical_slug,
            "provider_order": list(self.provider_order),
            "allow_fallbacks": self.allow_fallbacks,
            "requested_reasoning_effort": self.requested_reasoning_effort,
            "reasoning_mode": self.reasoning_mode,
            "reasoning_state_requirement": (
                "preserve_if_returned"
                if self.reasoning_mode != "not_supported"
                else "not_applicable"
            ),
            "tool_choice": self.tool_choice,
            "preserve_reasoning_state": self.preserve_reasoning_state,
            "maximum_route_price_usd_per_million": {
                "prompt": self.maximum_prompt_price_usd_per_million,
                "completion": self.maximum_completion_price_usd_per_million,
            },
            "supported_parameters": list(self.supported_parameters),
            "endpoint_contract_digest": self.endpoint_contract_digest,
            "context_length": self.context_length,
            "maximum_completion_tokens": self.maximum_completion_tokens,
        }


def _adapter(row: Mapping[str, Any], contract: Mapping[str, Any]) -> MMMVPProviderAdapter:
    return MMMVPProviderAdapter(
        model_id=str(row["model_id"]),
        expected_canonical_slug=str(row["expected_canonical_slug"]),
        provider_order=(str(row["provider"]),),
        allow_fallbacks=False,
        requested_reasoning_effort=str(row["requested_reasoning_effort"]),
        reasoning_mode=str(row["reasoning_mode"]),
        tool_choice="auto",
        preserve_reasoning_state=True,
        maximum_prompt_price_usd_per_million=float(
            row["maximum_route_price_usd_per_million"]["prompt"]
        ),
        maximum_completion_price_usd_per_million=float(
            row["maximum_route_price_usd_per_million"]["completion"]
        ),
        supported_parameters=tuple(contract["supported_parameter_intersection"]),
        endpoint_contract_digest=str(contract["contract_digest"]),
        context_length=int(contract["context_length_minimum"]),
        maximum_completion_tokens=int(contract["maximum_completion_tokens_minimum"]),
    )


def discover_mmmvp_adapters(
    project_root: Path, key: str
) -> tuple[dict[str, MMMVPProviderAdapter], dict[str, CatalogModel], dict[str, Any]]:
    root = project_root.resolve()
    panel = _read(root / PANEL_PATH)
    catalog = fetch_user_catalog(key)
    contracts: dict[str, Any] = {}
    adapters: dict[str, MMMVPProviderAdapter] = {}
    for row in panel["models"]:
        model_id = str(row["model_id"])
        observed = catalog.get(model_id)
        if observed is None or observed.canonical_slug != row["expected_canonical_slug"]:
            raise ConfigurationError(f"Canonical model pin failed: {model_id}")
        contract = route_contract(row, fetch_model_endpoints(key, model_id))
        contracts[model_id] = contract
        adapters[model_id] = _adapter(row, contract)
    return adapters, catalog, contracts


def load_route_contract_adapters(project_root: Path) -> dict[str, MMMVPProviderAdapter]:
    root = project_root.resolve()
    panel = _read(root / PANEL_PATH)
    frozen = _read(root / ROUTE_CONTRACTS_PATH)
    contracts = frozen.get("contracts") or {}
    adapters = {
        str(row["model_id"]): _adapter(row, contracts[str(row["model_id"])])
        for row in panel["models"]
    }
    if set(adapters) != set(contracts):
        raise ConfigurationError("Panel and route contracts differ")
    return adapters


def load_compatible_adapters(project_root: Path) -> dict[str, MMMVPProviderAdapter]:
    root = project_root.resolve()
    adapters = load_route_contract_adapters(root)
    compatibility = _read(root / COMPATIBILITY_PATH)
    passing = {
        str(row["model_id"])
        for row in compatibility.get("results") or []
        if row.get("classification") == "compatible"
    }
    return {model_id: adapter for model_id, adapter in adapters.items() if model_id in passing}


__all__ = [
    "COMPATIBILITY_PATH",
    "MMMVPProviderAdapter",
    "PANEL_PATH",
    "ROUTE_CONTRACTS_PATH",
    "discover_mmmvp_adapters",
    "load_compatible_adapters",
    "load_route_contract_adapters",
    "route_contract",
]

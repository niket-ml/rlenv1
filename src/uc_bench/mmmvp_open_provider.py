"""Pinned route contracts for the immutable open MMMVP release candidate."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.mmmvp_provider import MMMVPProviderAdapter, route_contract
from uc_bench.openrouter_catalog import CatalogModel, fetch_model_endpoints, fetch_user_catalog

PANEL_PATH = Path("configs/uc_bench_mmmvp_open_model_panel.json")
ROUTE_CONTRACTS_PATH = Path("artifacts/mmmvp_open_release/route_contracts.json")
COMPATIBILITY_PATH = Path("artifacts/mmmvp_open_release/compatibility_results.json")


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError(f"Expected JSON object: {path}")
    return value


def _normalized(row: Mapping[str, Any]) -> dict[str, Any]:
    return {**row, "expected_canonical_slug": row["canonical_slug"]}


def _adapter(row: Mapping[str, Any], contract: Mapping[str, Any]) -> MMMVPProviderAdapter:
    return MMMVPProviderAdapter(
        model_id=str(row["model_id"]),
        expected_canonical_slug=str(row["canonical_slug"]),
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


def discover_open_release_adapters(
    project_root: Path, key: str
) -> tuple[dict[str, MMMVPProviderAdapter], dict[str, CatalogModel], dict[str, Any]]:
    """Discover authenticated exact-model, exact-provider contracts without inference."""

    root = project_root.resolve()
    panel = _read(root / PANEL_PATH)
    catalog = fetch_user_catalog(key)
    contracts: dict[str, Any] = {}
    adapters: dict[str, MMMVPProviderAdapter] = {}
    for row in panel["models"]:
        model_id = str(row["model_id"])
        observed = catalog.get(model_id)
        if observed is None:
            raise ConfigurationError(f"Model is unavailable to the authenticated key: {model_id}")
        if observed.canonical_slug != row["canonical_slug"]:
            raise ConfigurationError(f"Canonical model pin changed: {model_id}")
        contract = route_contract(_normalized(row), fetch_model_endpoints(key, model_id))
        contracts[model_id] = contract
        adapters[model_id] = _adapter(row, contract)
    return adapters, catalog, contracts


def load_open_route_contract_adapters(
    project_root: Path,
) -> dict[str, MMMVPProviderAdapter]:
    root = project_root.resolve()
    panel = _read(root / PANEL_PATH)
    artifact = _read(root / ROUTE_CONTRACTS_PATH)
    if artifact.get("status") != "passed" or artifact.get("inference_requests") != 0:
        raise ConfigurationError("Open MMMVP route-contract discovery was not read-only and clean")
    contracts = artifact.get("contracts") or {}
    adapters = {
        str(row["model_id"]): _adapter(row, contracts[str(row["model_id"])])
        for row in panel["models"]
    }
    if set(adapters) != set(contracts):
        raise ConfigurationError("Open MMMVP panel and route contracts differ")
    return adapters


def load_open_compatible_adapters(
    project_root: Path,
) -> dict[str, MMMVPProviderAdapter]:
    root = project_root.resolve()
    adapters = load_open_route_contract_adapters(root)
    result = _read(root / COMPATIBILITY_PATH)
    passing = {
        str(row["model_id"])
        for row in result.get("results") or []
        if row.get("classification") == "compatible"
    }
    return {model_id: adapter for model_id, adapter in adapters.items() if model_id in passing}


__all__ = [
    "COMPATIBILITY_PATH",
    "PANEL_PATH",
    "ROUTE_CONTRACTS_PATH",
    "discover_open_release_adapters",
    "load_open_compatible_adapters",
    "load_open_route_contract_adapters",
]

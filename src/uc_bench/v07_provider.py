"""Pinned OpenRouter adapters for the bounded v0.7 development run."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.v061_provider import V061ProviderAdapter, verify_live_v061_identity

PANEL_PATH = Path("configs/hard_suite_v07_model_panel.json")
EXACT_COMPATIBILITY_PATH = Path(
    "artifacts/diagnostics/hard_suite_v061_exact_payload_compatibility_adjudication.json"
)
FULL_STACK_COMPATIBILITY_PATH = Path(
    "artifacts/diagnostics/hard_suite_v062_full_stack_compatibility.json"
)


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError(f"Expected object: {path}")
    return value


def load_v07_provider_adapters(project_root: Path) -> dict[str, V061ProviderAdapter]:
    """Load only the two pins with prior exact-body and full-stack passes."""

    root = project_root.resolve()
    panel = _read(root / PANEL_PATH)
    exact = _read(root / EXACT_COMPATIBILITY_PATH)
    full = _read(root / FULL_STACK_COMPATIBILITY_PATH)
    if exact.get("status") != "passed" or full.get("status") != "passed":
        raise ConfigurationError("The inherited exact provider compatibility is not passed")
    if any(int(exact.get(field) or 0) for field in ("heldout_requests", "astra_requests")):
        raise ConfigurationError("Compatibility evidence includes forbidden exposure")
    if any(int(full.get(field) or 0) for field in ("heldout_requests", "astra_requests")):
        raise ConfigurationError("Full-stack evidence includes forbidden exposure")
    exact_rows = {str(row["model_id"]): row for row in exact.get("results") or []}
    full_rows = {str(row["model_id"]): row for row in full.get("results") or []}
    adapters: dict[str, V061ProviderAdapter] = {}
    for proposed in panel.get("models") or []:
        model_id = str(proposed["model_id"])
        if "astra" in model_id.lower() or "gpt-6" in model_id.lower():
            raise ConfigurationError("Astra/GPT-6 is forbidden from v0.7 development")
        exact_row = exact_rows.get(model_id) or {}
        full_row = full_rows.get(model_id) or {}
        if exact_row.get("classification") != "compatible_exact_payload":
            raise ConfigurationError(f"No exact-payload pass for {model_id}")
        if full_row.get("classification") != "compatible_full_stack":
            raise ConfigurationError(f"No full-stack pass for {model_id}")
        contract = exact_row.get("route_contract") or {}
        if list(contract.get("provider_order") or []) != list(proposed["provider_order"]):
            raise ConfigurationError(f"Provider route changed for {model_id}")
        adapters[model_id] = V061ProviderAdapter(
            model_id=model_id,
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
    expected = {"openai/gpt-5.6-sol", "openai/gpt-5.2"}
    if set(adapters) != expected:
        raise ConfigurationError(f"v0.7 model panel must be exactly {sorted(expected)}")
    return adapters


def verify_live_v07_identity(
    key: str, adapters: dict[str, V061ProviderAdapter]
) -> dict[str, Any]:
    """Read-only canonical model, provider, price and parameter verification."""

    return verify_live_v061_identity(key, adapters)

"""Pinned provider configuration for the clean Case 1 pilot provenance root."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.mmmvp_provider import MMMVPProviderAdapter

CONFIG_PATH = Path("configs/uc_bench_case1_pilot_v1_rc1.json")
RELEASE_ID = "uc-bench-case1-pilot-v1-rc1"


def load_case1_pilot_config(project_root: Path) -> dict[str, Any]:
    path = project_root.resolve() / CONFIG_PATH
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("release_id") != RELEASE_ID:
        raise ConfigurationError("Case 1 pilot configuration identity is invalid")
    if value.get("case_id") != "case_01" or value.get("partition") != "development":
        raise ConfigurationError("Case 1 pilot scope changed")
    models = value.get("models") or []
    identifiers = [str(row.get("model_id")) for row in models if isinstance(row, dict)]
    if len(identifiers) != 5 or len(set(identifiers)) != 5:
        raise ConfigurationError("Case 1 pilot requires five unique models")
    order = value.get("execution_order")
    if not isinstance(order, list) or set(order) != set(identifiers):
        raise ConfigurationError("Case 1 pilot execution order differs from its panel")
    if order[0] != "google/gemini-3.1-pro-preview":
        raise ConfigurationError("Gemini must remain the first scientific sentinel")
    if set(identifiers) & set(value.get("forbidden_models") or []):
        raise ConfigurationError("Case 1 pilot panel contains a forbidden model")
    return value


def _adapter(row: dict[str, Any]) -> MMMVPProviderAdapter:
    price = row.get("maximum_route_price_usd_per_million") or {}
    supported = tuple(str(item) for item in row.get("supported_parameters") or [])
    adapter = MMMVPProviderAdapter(
        model_id=str(row["model_id"]),
        expected_canonical_slug=str(row["canonical_slug"]),
        provider_order=(str(row["provider"]),),
        allow_fallbacks=False,
        requested_reasoning_effort=str(row["requested_reasoning_effort"]),
        reasoning_mode=str(row["reasoning_mode"]),
        tool_choice="auto",
        preserve_reasoning_state=True,
        maximum_prompt_price_usd_per_million=float(price["prompt"]),
        maximum_completion_price_usd_per_million=float(price["completion"]),
        supported_parameters=supported,
        endpoint_contract_digest=str(row["endpoint_contract_digest"]),
        context_length=int(row["context_length"]),
        maximum_completion_tokens=int(row["maximum_completion_tokens"]),
    )
    emitted = adapter.sampling_args(maximum_completion_tokens=5_000)
    if (emitted.get("extra_body") or {}).get("provider", {}).get("allow_fallbacks") is not False:
        raise ConfigurationError("Case 1 pilot adapter did not disable fallbacks")
    return adapter


def load_case1_pilot_adapters(project_root: Path) -> dict[str, MMMVPProviderAdapter]:
    config = load_case1_pilot_config(project_root)
    result = {_row["model_id"]: _adapter(_row) for _row in config["models"]}
    if list(result) != [row["model_id"] for row in config["models"]]:
        raise ConfigurationError("Case 1 pilot adapter order changed")
    return result


def model_config(project_root: Path, model_id: str) -> dict[str, Any]:
    config = load_case1_pilot_config(project_root)
    rows = {row["model_id"]: row for row in config["models"]}
    try:
        return dict(rows[model_id])
    except KeyError as exc:
        raise ConfigurationError(f"Model is outside the Case 1 pilot: {model_id}") from exc


__all__ = [
    "CONFIG_PATH",
    "RELEASE_ID",
    "load_case1_pilot_adapters",
    "load_case1_pilot_config",
    "model_config",
]

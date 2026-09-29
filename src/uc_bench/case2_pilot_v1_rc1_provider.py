"""Pinned provider policy for the three-cell Case 2 release."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.mmmvp_provider import MMMVPProviderAdapter

CONFIG_PATH = Path("configs/uc_bench_case2_pilot_v1_rc1.json")
RELEASE_ID = "uc-bench-case2-pilot-v1-rc1"


def load_case2_config(project_root: Path) -> dict[str, Any]:
    value = json.loads((project_root.resolve() / CONFIG_PATH).read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("release_id") != RELEASE_ID:
        raise ConfigurationError("Case 2 release configuration identity is invalid")
    if value.get("case_id") != "case_02" or value.get("partition") != "development":
        raise ConfigurationError("Case 2 release scope changed")
    rows = value.get("models") or []
    identifiers = [str(row.get("model_id")) for row in rows if isinstance(row, dict)]
    order = value.get("execution_order")
    if len(identifiers) != 3 or len(set(identifiers)) != 3:
        raise ConfigurationError("Case 2 sentinel requires three unique models")
    if order != identifiers:
        raise ConfigurationError("Case 2 execution order must equal the declared model order")
    if set(identifiers) & set(value.get("forbidden_models") or []):
        raise ConfigurationError("Case 2 sentinel contains a forbidden model")
    return value


def _adapter(row: dict[str, Any]) -> MMMVPProviderAdapter:
    price = row.get("maximum_route_price_usd_per_million")
    if not isinstance(price, dict) or set(price) != {"prompt", "completion"}:
        raise ConfigurationError("A nested prompt/completion route price is required")
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
        supported_parameters=tuple(str(item) for item in row["supported_parameters"]),
        endpoint_contract_digest=str(row["endpoint_contract_digest"]),
        context_length=int(row["context_length"]),
        maximum_completion_tokens=int(row["maximum_completion_tokens"]),
    )
    emitted = adapter.sampling_args(maximum_completion_tokens=5_000)
    provider = (emitted.get("extra_body") or {}).get("provider") or {}
    if provider.get("allow_fallbacks") is not False or provider.get("order") != [row["provider"]]:
        raise ConfigurationError("Case 2 adapter did not preserve the single pinned route")
    return adapter


def load_case2_adapters(project_root: Path) -> dict[str, MMMVPProviderAdapter]:
    config = load_case2_config(project_root)
    return {str(row["model_id"]): _adapter(row) for row in config["models"]}


def model_config(project_root: Path, model_id: str) -> dict[str, Any]:
    rows = {row["model_id"]: row for row in load_case2_config(project_root)["models"]}
    if model_id not in rows:
        raise ConfigurationError(f"Model is outside the Case 2 sentinel: {model_id}")
    return dict(rows[model_id])


__all__ = [
    "CONFIG_PATH",
    "RELEASE_ID",
    "load_case2_adapters",
    "load_case2_config",
    "model_config",
]

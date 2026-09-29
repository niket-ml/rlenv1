"""Canonical launch metadata for the infrastructure-only RC1.5 successor.

All RC1.5 launch controls consume :class:`CanonicalLaunchRoute`.  Raw provider
records are decoded once here, with the real nested route-price contract, and
are never interpreted independently by cost, ordering, rehearsal, or launch
code.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.mmmvp_open_provider import load_open_route_contract_adapters
from uc_bench.mmmvp_open_rc14_harness import load_converged_rc14_adapters
from uc_bench.mmmvp_provider import MMMVPProviderAdapter

PRICE_CONTAINER_FIELD = "maximum_route_price_usd_per_million"
PROMPT_PRICE_FIELD = f"{PRICE_CONTAINER_FIELD}.prompt"
COMPLETION_PRICE_FIELD = f"{PRICE_CONTAINER_FIELD}.completion"


def _finite_nonnegative(value: Any, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ConfigurationError(f"{field} must be a finite non-negative number")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ConfigurationError(f"{field} must be a finite non-negative number")
    return result


def _positive_integer(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigurationError(f"{field} must be a positive integer")
    return value


def _required_text(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"{field} must be non-empty text")
    return value


@dataclass(frozen=True, slots=True)
class CanonicalLaunchRoute:
    """Validated, version-neutral route facts needed to launch an episode."""

    adapter: MMMVPProviderAdapter
    model_id: str
    canonical_slug: str
    provider: str
    prompt_price_usd_per_million: float
    completion_price_usd_per_million: float
    context_length: int
    maximum_completion_tokens: int
    reasoning_mode: str
    requested_reasoning_effort: str
    price_source_fields: tuple[str, str]

    @classmethod
    def from_adapter(cls, adapter: MMMVPProviderAdapter) -> CanonicalLaunchRoute:
        """Create the canonical view from the already typed provider adapter."""

        if not isinstance(adapter, MMMVPProviderAdapter):
            raise ConfigurationError("RC1.5 requires the typed MMMVP provider adapter")
        serialized = adapter.to_dict()
        return cls._validated(adapter, serialized)

    @classmethod
    def from_serialized_adapter(
        cls, value: Mapping[str, Any]
    ) -> CanonicalLaunchRoute:
        """Decode an archived adapter through the sole RC1.5 raw-schema boundary."""

        try:
            price = value[PRICE_CONTAINER_FIELD]
            if not isinstance(price, Mapping):
                raise ConfigurationError(
                    f"{PRICE_CONTAINER_FIELD} must be an object"
                )
            prompt_price = _finite_nonnegative(
                price["prompt"], field=PROMPT_PRICE_FIELD
            )
            completion_price = _finite_nonnegative(
                price["completion"], field=COMPLETION_PRICE_FIELD
            )
            providers = value["provider_order"]
            if not isinstance(providers, list | tuple) or len(providers) != 1:
                raise ConfigurationError("provider_order must contain exactly one provider")
            supported = value["supported_parameters"]
            if not isinstance(supported, list | tuple):
                raise ConfigurationError("supported_parameters must be an array")
            adapter = MMMVPProviderAdapter(
                model_id=_required_text(value["model_id"], field="model_id"),
                expected_canonical_slug=_required_text(
                    value["expected_canonical_slug"],
                    field="expected_canonical_slug",
                ),
                provider_order=(
                    _required_text(providers[0], field="provider_order[0]"),
                ),
                allow_fallbacks=bool(value["allow_fallbacks"]),
                requested_reasoning_effort=_required_text(
                    value["requested_reasoning_effort"],
                    field="requested_reasoning_effort",
                ),
                reasoning_mode=_required_text(
                    value["reasoning_mode"], field="reasoning_mode"
                ),
                tool_choice=_required_text(value["tool_choice"], field="tool_choice"),
                preserve_reasoning_state=bool(value["preserve_reasoning_state"]),
                maximum_prompt_price_usd_per_million=prompt_price,
                maximum_completion_price_usd_per_million=completion_price,
                supported_parameters=tuple(str(item) for item in supported),
                endpoint_contract_digest=_required_text(
                    value["endpoint_contract_digest"],
                    field="endpoint_contract_digest",
                ),
                context_length=_positive_integer(
                    value["context_length"], field="context_length"
                ),
                maximum_completion_tokens=_positive_integer(
                    value["maximum_completion_tokens"],
                    field="maximum_completion_tokens",
                ),
            )
        except KeyError as exc:
            if exc.args[0] in {"prompt", "completion"}:
                raise ConfigurationError(
                    "Canonical provider price field is missing: "
                    f"{PRICE_CONTAINER_FIELD}.{exc.args[0]}"
                ) from exc
            raise ConfigurationError(
                f"Canonical provider adapter field is missing: {exc.args[0]}"
            ) from exc
        return cls._validated(adapter, value)

    @classmethod
    def _validated(
        cls,
        adapter: MMMVPProviderAdapter,
        serialized: Mapping[str, Any],
    ) -> CanonicalLaunchRoute:
        try:
            prices = serialized[PRICE_CONTAINER_FIELD]
            if not isinstance(prices, Mapping):
                raise ConfigurationError(
                    f"{PRICE_CONTAINER_FIELD} must be an object"
                )
            prompt_price = _finite_nonnegative(
                prices["prompt"], field=PROMPT_PRICE_FIELD
            )
            completion_price = _finite_nonnegative(
                prices["completion"], field=COMPLETION_PRICE_FIELD
            )
        except KeyError as exc:
            missing = (
                PRICE_CONTAINER_FIELD
                if exc.args[0] == PRICE_CONTAINER_FIELD
                else f"{PRICE_CONTAINER_FIELD}.{exc.args[0]}"
            )
            raise ConfigurationError(
                f"Canonical provider price field is missing: {missing}"
            ) from exc
        context = _positive_integer(adapter.context_length, field="context_length")
        completion_limit = _positive_integer(
            adapter.maximum_completion_tokens,
            field="maximum_completion_tokens",
        )
        if len(adapter.provider_order) != 1 or adapter.allow_fallbacks:
            raise ConfigurationError("RC1.5 requires one pinned provider without fallback")
        if prompt_price != float(adapter.maximum_prompt_price_usd_per_million):
            raise ConfigurationError("Serialized and typed prompt prices differ")
        if completion_price != float(
            adapter.maximum_completion_price_usd_per_million
        ):
            raise ConfigurationError("Serialized and typed completion prices differ")
        return cls(
            adapter=adapter,
            model_id=_required_text(adapter.model_id, field="model_id"),
            canonical_slug=_required_text(
                adapter.expected_canonical_slug,
                field="expected_canonical_slug",
            ),
            provider=_required_text(adapter.provider_order[0], field="provider_order[0]"),
            prompt_price_usd_per_million=prompt_price,
            completion_price_usd_per_million=completion_price,
            context_length=context,
            maximum_completion_tokens=completion_limit,
            reasoning_mode=_required_text(
                adapter.reasoning_mode, field="reasoning_mode"
            ),
            requested_reasoning_effort=_required_text(
                adapter.requested_reasoning_effort,
                field="requested_reasoning_effort",
            ),
            price_source_fields=(PROMPT_PRICE_FIELD, COMPLETION_PRICE_FIELD),
        )

    def to_record(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "canonical_slug": self.canonical_slug,
            "provider": self.provider,
            "maximum_route_price_usd_per_million": {
                "prompt": self.prompt_price_usd_per_million,
                "completion": self.completion_price_usd_per_million,
            },
            "price_source_fields": list(self.price_source_fields),
            "context_length": self.context_length,
            "maximum_completion_tokens": self.maximum_completion_tokens,
            "reasoning_mode": self.reasoning_mode,
            "requested_reasoning_effort": self.requested_reasoning_effort,
            "allow_fallbacks": False,
        }


def load_rc15_all_routes(project_root: Path) -> dict[str, CanonicalLaunchRoute]:
    """Validate every current panel entry before applying compatibility status."""

    return {
        model_id: CanonicalLaunchRoute.from_adapter(adapter)
        for model_id, adapter in load_open_route_contract_adapters(project_root).items()
    }


def load_rc15_launch_routes(project_root: Path) -> dict[str, CanonicalLaunchRoute]:
    """Inherit exactly the nine RC1.4 technical passes through one typed path."""

    all_routes = load_rc15_all_routes(project_root)
    inherited = load_converged_rc14_adapters(project_root)
    routes = {
        model_id: all_routes[model_id]
        for model_id in inherited
    }
    if len(routes) != 9 or "z-ai/glm-5.2" in routes:
        raise ConfigurationError("RC1.5 must inherit nine passes and exclude GLM")
    return routes


__all__ = [
    "COMPLETION_PRICE_FIELD",
    "CanonicalLaunchRoute",
    "PRICE_CONTAINER_FIELD",
    "PROMPT_PRICE_FIELD",
    "load_rc15_all_routes",
    "load_rc15_launch_routes",
]

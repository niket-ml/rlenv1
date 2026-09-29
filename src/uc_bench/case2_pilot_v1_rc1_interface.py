"""Neutral provider-facing request for the Case 2 release."""

from __future__ import annotations

from typing import Any

from uc_bench.case1_pilot_v1_rc4_interface import production_request as _validated_request


def production_request(config: Any) -> dict[str, Any]:
    """Return the byte-identical validated autonomous workflow request."""

    return _validated_request(config)


__all__ = ["production_request"]

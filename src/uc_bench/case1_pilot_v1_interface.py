"""Frozen request constructor for the clean Case 1 pilot."""

from __future__ import annotations

from typing import Any

from uc_bench.mmmvp_blind_interface import OpenExecutionLimits
from uc_bench.mmmvp_open_rc17_interface import serialized_rc17_request


def production_request(config: Any) -> dict[str, Any]:
    return serialized_rc17_request(
        OpenExecutionLimits(
            maximum_turns=int(config.maximum_turns),
            maximum_total_completion_tokens=int(config.maximum_total_completion_tokens),
            wall_clock_timeout_seconds=int(config.wall_clock_timeout_seconds),
        )
    )


__all__ = ["production_request"]

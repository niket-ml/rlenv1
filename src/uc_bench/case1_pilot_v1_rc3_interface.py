"""RC3 request construction from the sole Case 1 tool-contract registry."""

from __future__ import annotations

from typing import Any

from uc_bench.case1_pilot_v1_rc3_tools import case1_tool_definitions
from uc_bench.mmmvp_open_rc17_interface import SYSTEM_PROMPT

INITIAL_USER_MESSAGE = "Begin the predictor evidence investigation in /workspace."


def production_request(_config: Any) -> dict[str, Any]:
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": INITIAL_USER_MESSAGE},
        ],
        "tools": case1_tool_definitions(),
        "tool_choice": "auto",
    }


__all__ = ["INITIAL_USER_MESSAGE", "production_request"]

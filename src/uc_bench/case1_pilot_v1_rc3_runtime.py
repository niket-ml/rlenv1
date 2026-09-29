"""RC3 runtime tool construction bound to the authoritative Case 1 registry."""

from __future__ import annotations

from typing import Any

from uc_bench.case1_pilot_v1_rc3_tools import bind_runtime_tools
from uc_bench.mmmvp_open_rc13_trajectory import rc13_durable_tool_functions


def rc3_durable_tool_functions(
    docker: Any, core: Any, store: Any, ledger: Any
) -> list[Any]:
    return bind_runtime_tools(rc13_durable_tool_functions(docker, core, store, ledger))


__all__ = ["rc3_durable_tool_functions"]

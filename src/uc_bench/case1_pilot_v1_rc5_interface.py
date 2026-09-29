"""Agent-visible Case-1 RC5 request.

The provider-facing prompt and tool schema are deliberately identical to RC4.
RC5's repaired public contract is materialized inside the workspace.
"""

from uc_bench.case1_pilot_v1_rc4_interface import (
    INITIAL_USER_MESSAGE,
    production_request,
)

__all__ = ["INITIAL_USER_MESSAGE", "production_request"]

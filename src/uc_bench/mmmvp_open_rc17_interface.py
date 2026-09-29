"""Exact agent-visible request surface for the isolated Case-1 successor."""

from __future__ import annotations

import copy
from typing import Any

from uc_bench.mmmvp_blind_interface import OpenExecutionLimits, serialized_open_request

SYSTEM_PROMPT = """Assess the locked predictor and supplied evidence for its stated intended use.
Determine what the evidence supports, whether one follow-up resource has decision value, and
the appropriate bounded next action.

Work only in /workspace. Supplied evidence is immutable; write derived work under work/.
Outcomes begin sealed. The irreversible order is validation-plan commitment, outcome reveal,
follow-up-plan commitment, exactly one resource action (including `none`), then submission.
Rejected contract payloads may be repaired before the corresponding action succeeds.

Start with MISSION.md and field_guide.md. submission_contract.json is the complete
machine-readable contract; scientific_methods.json lists the method families the verifier can
recompute; contract_templates/ contains editable structural skeletons; validate_contract.py reports
mechanical errors without scientific answers. The interface supports only the published method
families and does not claim unrestricted statistical-method acceptance.

Choose the scientific workflow and decision from the evidence. Resource names and enum options
are not recommendations. Free text is retained for audit but cannot independently earn or lose
scientific credit. Decision-driving numbers are independently recomputed from saved artifacts.
The grader, private outcomes before reveal, and expected decisions are outside the workspace."""


def serialized_rc17_request(
    limits: OpenExecutionLimits | None = None,
) -> dict[str, Any]:
    """Use the established production tool surface with the corrected neutral prompt."""

    request = copy.deepcopy(serialized_open_request(limits))
    request["messages"][0]["content"] = SYSTEM_PROMPT
    return request


__all__ = ["SYSTEM_PROMPT", "serialized_rc17_request"]

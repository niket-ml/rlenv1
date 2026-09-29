"""Single condition-blind interface for the open-ended MMMVP successor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

NEUTRAL_MISSION = (
    "Assess the supplied predictor and evidence package for the stated intended use. "
    "Determine what can and cannot be concluded, perform the analyses you consider "
    "necessary, decide whether further evidence is worth purchasing within the budget, "
    "and recommend the appropriate next development action. Preserve the evidence "
    "supporting your conclusions."
)

BLIND_INTERFACE_CONTRACT = r"""
INTERFACE AND IRREVERSIBLE ACTIONS

Work only inside /workspace. Supplied evidence is immutable; write code, derived
data, and results under work/. The available inspection, file-writing, and command
tools operate only in that workspace and have no network access or credentials.

Validation outcomes are initially unavailable. Before reveal, call
commit_validation_plan exactly once. The committed plan cannot be replaced after
reveal_validation. After examining the revealed evidence, call
commit_followup_plan exactly once before purchase_resource. Purchase exactly one
catalogue resource or the resource ID none. A purchase cannot be changed. Finish
with submit. Other investigation and artifact-writing steps may occur in any order
consistent with those irreversible boundaries.

MACHINE-READABLE CONTRACT

Read submission_contract.json before committing or submitting. It states every
required field, disclosed enum, relationship, and minimum array size. It does not
prescribe which scientific analysis, metric, unit, defect, resource, or conclusion
is appropriate for the evidence.
Additional fields are retained for audit. Free text is checked only for presence;
it is not matched against hidden phrases and cannot independently pass or fail a
scientific requirement.

Resource identity and timing come from the environment event record. Material
quantities are independently recomputed from raw data and saved artifacts. A
reported number, diagnosis, or action without its supporting artifact chain is
insufficient. Alternative valid workflows are accepted when their evidence
supports the same professional property. Harmless presentation errors are
reported separately from scientific work.
""".strip()


@dataclass(frozen=True, slots=True)
class OpenExecutionLimits:
    """Condition-free values that may enter the agent-visible prompt builder."""

    maximum_turns: int = 65
    maximum_total_completion_tokens: int = 90_000
    wall_clock_timeout_seconds: int = 4_200


def mmmvp_blind_scientific_system_prompt(
    limits: OpenExecutionLimits | None = None,
) -> str:
    """Build the sole agent-visible prompt without accepting private identifiers."""

    if limits is None:
        limits = OpenExecutionLimits()
    return (
        NEUTRAL_MISSION
        + "\n\n"
        + BLIND_INTERFACE_CONTRACT
        + "\n\nEXECUTION BUDGET\n"
        + f"At most {limits.maximum_turns} assistant turns, "
        + f"{limits.maximum_total_completion_tokens} total completion tokens, and "
        + f"{limits.wall_clock_timeout_seconds} seconds are available."
    )


def serialized_open_request(
    limits: OpenExecutionLimits | None = None,
) -> dict[str, Any]:
    """Build the sole provider request surface used by audit and production."""

    # Local import avoids an interface/environment import cycle while keeping
    # the actual tool contract authoritative in one place.
    from verifiers.legacy.utils.tool_utils import convert_func_to_tool_def

    from uc_bench.mmmvp_open_environment import mmmvp_open_tool_functions

    class SerializationDocker:
        def inspect_workspace(self, relative_path: str = ".") -> str:
            return relative_path

        def read_file(self, relative_path: str) -> str:
            return relative_path

        def write_file(self, relative_path: str, content: str) -> str:
            return relative_path + content

        def run_command(self, command: str) -> str:
            return command

    class SerializationCore:
        def record_workspace_tool(self, *_args: Any, **_kwargs: Any) -> None:
            return None

        def commit_validation_plan(self, payload_json: str) -> dict[str, Any]:
            """Irreversibly commit an agent-chosen plan before outcomes are available."""

            return {"payload_json": payload_json}

        def reveal_validation(self) -> list[str]:
            """Reveal sealed outcomes after the validation plan has been committed."""

            return []

        def commit_followup_plan(self, payload_json: str) -> dict[str, Any]:
            """Commit a resource choice and result-contingent actions before purchase."""

            return {"payload_json": payload_json}

        def purchase_resource(self, resource_id: str) -> list[str]:
            """Irreversibly purchase one catalogue resource, including none."""

            return [resource_id]

        def submit(self, payload_json: str) -> dict[str, Any]:
            """Submit the evidence-linked final recommendation after the resource action."""

            return {"payload_json": payload_json}

    tool_rows = [
        convert_func_to_tool_def(tool).model_dump(mode="json")
        for tool in mmmvp_open_tool_functions(SerializationDocker(), SerializationCore())  # type: ignore[arg-type]
    ]

    if limits is None:
        limits = OpenExecutionLimits()
    return {
        "messages": [
            {
                "role": "system",
                "content": mmmvp_blind_scientific_system_prompt(limits),
            },
            {
                "role": "user",
                "content": "Begin the predictor evidence investigation in /workspace.",
            },
        ],
        "tools": [{"type": "function", "function": row} for row in tool_rows],
        "tool_choice": "auto",
    }


__all__ = [
    "BLIND_INTERFACE_CONTRACT",
    "NEUTRAL_MISSION",
    "OpenExecutionLimits",
    "mmmvp_blind_scientific_system_prompt",
    "serialized_open_request",
]

"""The single authoritative provider-facing tool contract for Case 1 RC3."""

from __future__ import annotations

import copy
from collections.abc import Callable, Sequence
from typing import Any

from uc_bench.errors import ConfigurationError

# This registry is byte-identical to the already audited RC1/RC2 provider surface.
# Every RC3 request, runtime binding, canary, and equality check consumes this value.
CASE1_TOOL_CONTRACT_REGISTRY: tuple[dict[str, Any], ...] = (
    {
        "type": "function",
        "function": {
            "name": "inspect_workspace",
            "description": "List files visible inside the workspace.",
            "parameters": {
                "properties": {
                    "relative_path": {
                        "default": ".",
                        "title": "Relative Path",
                        "type": "string",
                    }
                },
                "title": "inspect_workspace_args",
                "type": "object",
                "additionalProperties": False,
                "required": ["relative_path"],
            },
            "strict": True,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read one visible UTF-8 workspace file.",
            "parameters": {
                "properties": {
                    "relative_path": {"title": "Relative Path", "type": "string"}
                },
                "required": ["relative_path"],
                "title": "read_file_args",
                "type": "object",
                "additionalProperties": False,
            },
            "strict": True,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write a UTF-8 analysis artifact inside the visible workspace.",
            "parameters": {
                "properties": {
                    "relative_path": {"title": "Relative Path", "type": "string"},
                    "content": {"title": "Content", "type": "string"},
                },
                "required": ["relative_path", "content"],
                "title": "write_file_args",
                "type": "object",
                "additionalProperties": False,
            },
            "strict": True,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Run an analysis command inside the sealed workspace container.",
            "parameters": {
                "properties": {"command": {"title": "Command", "type": "string"}},
                "required": ["command"],
                "title": "run_command_args",
                "type": "object",
                "additionalProperties": False,
            },
            "strict": True,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "commit_validation_plan",
            "description": (
                "Irreversibly commit an agent-chosen plan before outcomes are available."
            ),
            "parameters": {
                "properties": {
                    "payload_json": {"title": "Payload Json", "type": "string"}
                },
                "required": ["payload_json"],
                "title": "commit_validation_plan_args",
                "type": "object",
                "additionalProperties": False,
            },
            "strict": True,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reveal_validation",
            "description": "Reveal sealed outcomes after the validation plan has been committed.",
            "parameters": {
                "properties": {},
                "title": "reveal_validation_args",
                "type": "object",
                "additionalProperties": False,
                "required": [],
            },
            "strict": True,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "commit_followup_plan",
            "description": (
                "Commit a resource choice and result-contingent actions before purchase."
            ),
            "parameters": {
                "properties": {
                    "payload_json": {"title": "Payload Json", "type": "string"}
                },
                "required": ["payload_json"],
                "title": "commit_followup_plan_args",
                "type": "object",
                "additionalProperties": False,
            },
            "strict": True,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "purchase_resource",
            "description": "Irreversibly purchase one catalogue resource, including none.",
            "parameters": {
                "properties": {
                    "resource_id": {"title": "Resource Id", "type": "string"}
                },
                "required": ["resource_id"],
                "title": "purchase_resource_args",
                "type": "object",
                "additionalProperties": False,
            },
            "strict": True,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit",
            "description": (
                "Submit the evidence-linked final recommendation after the resource action."
            ),
            "parameters": {
                "properties": {
                    "payload_json": {"title": "Payload Json", "type": "string"}
                },
                "required": ["payload_json"],
                "title": "submit_args",
                "type": "object",
                "additionalProperties": False,
            },
            "strict": True,
        },
    },
)


def case1_tool_definitions() -> list[dict[str, Any]]:
    """Return a defensive copy of the sole provider-facing definition list."""

    names: list[str] = []
    for index, row in enumerate(CASE1_TOOL_CONTRACT_REGISTRY):
        if set(row) != {"type", "function"} or row.get("type") != "function":
            raise ConfigurationError(f"Registry row {index} has an invalid outer contract")
        function = row.get("function") or {}
        name = str(function.get("name") or "")
        parameters = function.get("parameters") or {}
        if (
            not name
            or not str(function.get("description") or "").strip()
            or function.get("strict") is not True
            or parameters.get("type") != "object"
            or parameters.get("additionalProperties") is not False
            or not isinstance(parameters.get("properties"), dict)
            or not isinstance(parameters.get("required"), list)
        ):
            raise ConfigurationError(f"Registry row {index} is incomplete")
        names.append(name)
    expected = [
        "inspect_workspace",
        "read_file",
        "write_file",
        "run_command",
        "commit_validation_plan",
        "reveal_validation",
        "commit_followup_plan",
        "purchase_resource",
        "submit",
    ]
    if names != expected or len(set(names)) != 9:
        raise ConfigurationError("Registry name identity or ordering changed")
    return copy.deepcopy(list(CASE1_TOOL_CONTRACT_REGISTRY))


def bind_runtime_tools(tools: Sequence[Callable[..., Any]]) -> list[Callable[..., Any]]:
    """Bind implementations to the registry and prove their generated schemas exactly."""

    from verifiers.legacy.utils.tool_utils import convert_func_to_tool_def

    by_name = {tool.__name__: tool for tool in tools}
    expected_names = [row["function"]["name"] for row in CASE1_TOOL_CONTRACT_REGISTRY]
    if len(by_name) != len(tools) or set(by_name) != set(expected_names):
        raise ConfigurationError("Runtime implementations do not bijectively match the registry")
    ordered: list[Callable[..., Any]] = []
    for row in CASE1_TOOL_CONTRACT_REGISTRY:
        definition = row["function"]
        tool = by_name[definition["name"]]
        tool.__doc__ = str(definition["description"])
        ordered.append(tool)
    generated = [
        {"type": "function", "function": convert_func_to_tool_def(tool).model_dump(mode="json")}
        for tool in ordered
    ]
    if generated != case1_tool_definitions():
        raise ConfigurationError("Registry-bound runtime tools changed their provider schema")
    return ordered


def assert_three_surfaces(
    *, request_tools: list[dict[str, Any]], runtime_tools: Sequence[Callable[..., Any]]
) -> list[dict[str, Any]]:
    """Require registry, request, and generated runtime bytes to be exactly equal."""

    from verifiers.legacy.utils.tool_utils import convert_func_to_tool_def

    generated = [
        {"type": "function", "function": convert_func_to_tool_def(tool).model_dump(mode="json")}
        for tool in runtime_tools
    ]
    registry = case1_tool_definitions()
    if request_tools != registry or generated != registry:
        raise ConfigurationError("Case 1 tool surfaces are not byte-identical")
    if any(not str(row["function"].get("description") or "").strip() for row in registry):
        raise ConfigurationError("Every Case 1 tool description must remain non-empty")
    return generated


__all__ = [
    "CASE1_TOOL_CONTRACT_REGISTRY",
    "assert_three_surfaces",
    "bind_runtime_tools",
    "case1_tool_definitions",
]

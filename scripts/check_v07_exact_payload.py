#!/usr/bin/env python3
"""Validate the exact v0.7 scientific request body locally; make no API call."""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from verifiers.legacy.utils.tool_utils import convert_func_to_tool_def

from uc_bench.docker_runtime import DockerWorkspace
from uc_bench.hashing import canonical_sha256
from uc_bench.v061_provider import exact_request_contract
from uc_bench.v07_environment import V07Environment
from uc_bench.v07_provider import load_v07_provider_adapters
from uc_bench.v07_runner import V07RunConfig, v07_scientific_system_prompt, v07_tool_functions

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts/diagnostics/hard_suite_v07_exact_payload_compatibility.json"


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        result = dump(mode="json", exclude_none=True)
        return dict(result)
    raise TypeError(f"Cannot serialize tool definition: {type(value).__name__}")


def main() -> int:
    adapters = load_v07_provider_adapters(ROOT)
    rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="uc-v07-payload-") as directory:
        temporary = Path(directory)
        collapse = V07Environment(
            ROOT,
            "case_03",
            temporary / "collapse",
            mechanism="signal_collapses",
        )
        remains = V07Environment(
            ROOT,
            "case_03",
            temporary / "remains",
            mechanism="signal_remains",
        )
        if collapse._start_hashes != remains._start_hashes:  # noqa: SLF001
            raise RuntimeError("Case 3 visible packet differs by sealed return")
        docker = DockerWorkspace(
            workspace_root=collapse.run_root,
            container_name="uc-v07-local-payload",
        )
        tools = [
            _as_dict(convert_func_to_tool_def(tool))
            for tool in v07_tool_functions(docker, collapse)
        ]
        tool_names = [str(row.get("name")) for row in tools]
        expected_tools = [
            "inspect_workspace",
            "read_file",
            "write_file",
            "run_command",
            "save_checkpoint",
            "commit_validation_plan",
            "reveal_validation",
            "purchase_resource",
            "submit",
        ]
        if tool_names != expected_tools:
            raise RuntimeError(f"Unexpected v0.7 tool surface: {tool_names}")
        task_text = (collapse.run_root / "README.md").read_text(encoding="utf-8")
        for model_id, adapter in adapters.items():
            config = V07RunConfig(
                model_id=model_id,
                run_id="local-payload-only",
                case_id="case_03",
                mechanism="signal_collapses",
                seed=70703,
            )
            sampling = adapter.sampling_args(
                maximum_completion_tokens=config.maximum_completion_tokens_per_turn
            )
            extra = dict(sampling.pop("extra_body"))
            body = {
                "model": model_id,
                "messages": [
                    {"role": "system", "content": v07_scientific_system_prompt(task_text, config)},
                    {
                        "role": "user",
                        "content": (
                            "Begin the evidence-chain diligence investigation "
                            "in /workspace."
                        ),
                    },
                ],
                **sampling,
                **extra,
                "tools": tools,
            }
            contract = exact_request_contract(body)
            visible = set(contract["endpoint_visible_parameters"])
            if not visible <= set(adapter.supported_parameters):
                raise RuntimeError(f"Unsupported exact parameters for {model_id}")
            if contract["provider_only"] != list(adapter.provider_order):
                raise RuntimeError(f"Provider pin missing for {model_id}")
            if contract["allow_fallbacks"] is not False or contract["tool_count"] != 9:
                raise RuntimeError(f"Unsafe exact payload for {model_id}")
            rows.append(
                {
                    "model_id": model_id,
                    "classification": "compatible_local_exact_scientific_payload",
                    "request_contract": contract,
                    "tool_schema_digest": canonical_sha256(tools),
                    "system_prompt_digest": canonical_sha256(body["messages"][0]),
                    "inherited_live_exact_payload_pass": True,
                    "inherited_live_full_stack_pass": True,
                }
            )
    result = {
        "schema_version": "0.7-local-exact-payload-1",
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "passed",
        "method": (
            "local serialization of the exact scientific prompt, nine tool schemas, "
            "adapter sampling arguments, and route envelope"
        ),
        "new_provider_requests": 0,
        "scientific_requests": 0,
        "heldout_requests": 0,
        "astra_requests": 0,
        "case_03_visible_packet_identical": True,
        "models": rows,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(OUTPUT)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

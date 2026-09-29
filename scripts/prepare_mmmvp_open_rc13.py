#!/usr/bin/env python3
"""Extract the exact RC1.2 DeepSeek lifecycle failure without model calls."""

from __future__ import annotations

import json
from pathlib import Path

from uc_bench.hashing import canonical_sha256, sha256_file
from uc_bench.model_runner import _write_json

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    ROOT
    / "build/uc_bench_mmmvp_open_rc12_runs"
    / "open-mmmvp-rc12-sentinel-04-deepseek-deepseek-v3.2-case-02"
    / "host_trajectory/latest.json"
)
TARGET = ROOT / "artifacts/mmmvp_open_rc13/deepseek_framework_error_fixture.json"


def main() -> None:
    if TARGET.exists():
        raise SystemExit(f"Refusing to overwrite RC1.3 fixture: {TARGET}")
    latest = json.loads(SOURCE.read_text(encoding="utf-8"))
    target_id = "call_bc0368acb4f747b2adc02396"
    assistant = next(
        message
        for message in reversed(latest["messages"])
        if message.get("role") == "assistant"
        and any(
            str(call.get("id")) == target_id
            for call in message.get("tool_calls") or []
        )
    )
    raw_call = next(
        call for call in assistant["tool_calls"] if str(call.get("id")) == target_id
    )
    result = next(
        message
        for message in latest["messages"]
        if message.get("role") == "tool"
        and str(message.get("tool_call_id")) == target_id
    )
    pending = next(
        call
        for call in latest["pending_tool_calls"]
        if str(call.get("tool_call_id")) == target_id
    )
    value = {
        "schema_version": "uc-bench-open-mmmvp-rc1-3-framework-error-fixture-1",
        "source_rc12_latest_path": SOURCE.relative_to(ROOT).as_posix(),
        "source_rc12_latest_sha256": sha256_file(SOURCE),
        "source_sequence": latest["sequence"],
        "tool_call_id": target_id,
        "tool_name": raw_call["function"]["name"],
        "raw_arguments": raw_call["function"]["arguments"],
        "framework_result": result,
        "rc12_persisted_status": pending["status"],
        "rc12_parsed_arguments": pending["arguments"],
        "fixture_digest": canonical_sha256(
            {
                "call": raw_call,
                "result": result,
                "pending": pending,
            }
        ),
        "contains_provider_error_or_account_identifier": False,
    }
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    _write_json(TARGET, value, secret="")
    print(
        json.dumps(
            {
                "target": TARGET.relative_to(ROOT).as_posix(),
                "tool_call_id": target_id,
                "raw_argument_bytes": len(value["raw_arguments"].encode("utf-8")),
                "source_sha256": value["source_rc12_latest_sha256"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

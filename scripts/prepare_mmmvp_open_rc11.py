#!/usr/bin/env python3
"""Create zero-cost RC1.1 inheritance evidence without touching RC1 artifacts."""

from __future__ import annotations

import json
from pathlib import Path

from uc_bench.mmmvp_open_freeze import read_open_mmmvp_freeze
from uc_bench.mmmvp_open_rc11_compatibility import create_compatibility_inheritance
from uc_bench.mmmvp_open_release_freeze import read_open_release_freeze

ROOT = Path(__file__).resolve().parents[1]


def _archived_gemini_command() -> str:
    path = ROOT / (
        "build/uc_bench_mmmvp_open_runs/"
        "open-mmmvp-sentinel-00-google-gemini-3.1-pro-preview-case-02/"
        "host_trajectory/latest.json"
    )
    latest = json.loads(path.read_text(encoding="utf-8"))
    for message in latest["messages"]:
        for call in message.get("tool_calls") or []:
            function = call.get("function") or {}
            arguments = json.loads(function.get("arguments") or "{}")
            if function.get("name") == "run_command" and "commit_vp.json" in str(
                arguments.get("command") or ""
            ):
                return str(arguments["command"])
    raise RuntimeError("The preserved Gemini command was not found")


def main() -> int:
    scientific = read_open_mmmvp_freeze(ROOT)
    release = read_open_release_freeze(ROOT)
    fixture_path = ROOT / "artifacts/mmmvp_open_rc11/gemini_root_write_fixture.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))["arguments"]["command"]
    if fixture != _archived_gemini_command():
        raise RuntimeError("The exact Gemini regression fixture differs from the trajectory")
    adjudication = json.loads(
        (
            ROOT
            / "artifacts/mmmvp_open_rc11/rc1_gemini_reliability_adjudication.json"
        ).read_text(encoding="utf-8")
    )
    if adjudication.get("retroactive_score_change") is not False:
        raise RuntimeError("The RC1 adjudication must not alter the archived score")
    inheritance = create_compatibility_inheritance(ROOT)
    print(
        json.dumps(
            {
                "status": "passed",
                "api_requests": 0,
                "scientific_freeze_digest": scientific["hash_set_digest"],
                "rc1_release_digest": release["category_digest_set"],
                "inherited_compatibility_models": inheritance["inherited_model_count"],
                "exact_gemini_fixture": True,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

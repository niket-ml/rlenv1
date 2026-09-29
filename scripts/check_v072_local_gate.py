#!/usr/bin/env python3
"""Run and record the complete local v0.7.2 pre-freeze gate."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.model_runner import load_openrouter_key
from uc_bench.v071_auth import credential_locations, mapping_contains_credential
from uc_bench.v071_freeze import read_v071_freeze_manifest
from uc_bench.v072_freeze import (
    CONTROLS_PATH,
    COST_PATH,
    EXACT_PAYLOAD_PATH,
    REPLAY_ROOT,
    v072_scientific_hashes,
)
from uc_bench.v072_interface import V072_AGENT_CONTRACT

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts/diagnostics/hard_suite_v072_local_gate.json"


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected object: {path}")
    return value


def _run(command: list[str], *, environment: dict[str, str] | None = None) -> dict[str, Any]:
    started = datetime.now(UTC)
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    finished = datetime.now(UTC)
    combined = (result.stdout + "\n" + result.stderr).strip()
    return {
        "command": command,
        "return_code": result.returncode,
        "duration_seconds": round((finished - started).total_seconds(), 3),
        "output_tail": combined[-4_000:],
    }


def main() -> int:
    parent = read_v071_freeze_manifest(ROOT)
    current_science = v072_scientific_hashes(ROOT)
    mismatches = sorted(
        path
        for path in set(parent["scientific_hashes"]) | set(current_science)
        if parent["scientific_hashes"].get(path) != current_science.get(path)
    )
    exact = _read(ROOT / EXACT_PAYLOAD_PATH)
    controls = _read(ROOT / CONTROLS_PATH)
    replay = _read(ROOT / REPLAY_ROOT / "replay_summary.json")
    cost = _read(ROOT / COST_PATH)
    environment = dict(os.environ)
    environment["PYTHONPATH"] = "src"
    commands = [
        _run(["./.venv/bin/python", "-m", "pytest"], environment=environment),
        _run(["./.venv/bin/ruff", "check", "src", "tests", "scripts"]),
        _run(["./.venv/bin/python", "-m", "uc_bench", "doctor"], environment=environment),
        _run(["./.venv/bin/python", "scripts/project_status.py", "--check"]),
        _run(
            ["./.venv/bin/python", "scripts/run_docker_preflight.py"],
            environment=environment,
        ),
    ]
    key = load_openrouter_key(ROOT)
    leak_locations: list[str] = []
    for relative in (
        "artifacts/diagnostics/hard_suite_v072_replay_fixtures",
        "artifacts/diagnostics/hard_suite_v072_controls.json",
        "artifacts/diagnostics/hard_suite_v072_exact_payload_compatibility.json",
        "artifacts/diagnostics/hard_suite_v072_cost_plan.json",
    ):
        path = ROOT / relative
        if path.is_dir():
            leak_locations.extend(
                f"{relative}/{location}" for location in credential_locations(path, key)
            )
        elif path.is_file() and key.encode("utf-8") in path.read_bytes():
            leak_locations.append(relative)
    prompt_leak = mapping_contains_credential({"agent_visible_contract": V072_AGENT_CONTRACT}, key)
    failed = sum(row["return_code"] != 0 for row in commands)
    prerequisite_checks = {
        "exact_provider_payload_compatible": exact.get("status") == "passed",
        "semantic_and_anti_gaming_controls_pass": controls.get("status") == "passed",
        "five_trace_zero_cost_replay_pass": replay.get("status") == "passed",
        "replay_not_uniformly_capped": replay.get("uniformly_capped") is False,
        "staged_cost_plan_present": cost.get("status") == "predeclared_no_paid_execution",
        "no_new_api_request_in_gates": (
            exact.get("new_provider_requests") == 0
            and controls.get("new_api_requests") == 0
            and replay.get("new_api_requests") == 0
            and cost.get("v072_new_api_requests_at_plan_time") == 0
        ),
        "credential_not_in_agent_contract_or_gate_artifacts": not leak_locations
        and not prompt_leak,
    }
    passed = not failed and not mismatches and all(prerequisite_checks.values())
    result = {
        "schema_version": "0.7.2-local-gate-1",
        "completed_at": datetime.now(UTC).isoformat(),
        "status": "passed" if passed else "failed",
        "parent_v071_hash_set_digest": parent["hash_set_digest"],
        "parent_scientific_hash_set_digest": parent["parent_v07_hash_set_digest"],
        "scientific_hash_file_count": len(current_science),
        "scientific_hash_mismatch_count": len(mismatches),
        "scientific_hash_mismatches": mismatches,
        "prerequisite_checks": prerequisite_checks,
        "credential_leakage_detected": bool(leak_locations or prompt_leak),
        "credential_leak_locations": leak_locations,
        "commands": commands,
        "failed_command_count": failed,
        "scientific_requests": 0,
        "heldout_requests": 0,
        "astra_requests": 0,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(OUTPUT)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

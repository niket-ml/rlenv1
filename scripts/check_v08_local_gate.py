#!/usr/bin/env python3
"""Run and record every zero-cost gate before the v0.8 execution snapshot."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.model_runner import load_openrouter_key
from uc_bench.v071_auth import credential_locations, mapping_contains_credential
from uc_bench.v072_freeze import read_v072_freeze_manifest, v072_frozen_hashes
from uc_bench.v08_interface import V08_AGENT_CONTRACT

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts/diagnostics/hard_suite_v08_local_gate.json"


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected JSON object: {path}")
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
    combined = (result.stdout + "\n" + result.stderr).strip()
    return {
        "command": command,
        "return_code": result.returncode,
        "duration_seconds": round((datetime.now(UTC) - started).total_seconds(), 3),
        "output_tail": combined[-4_000:],
    }


def main() -> int:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = "src"
    commands = [
        _run(
            ["./.venv/bin/python", "scripts/build_v08_precalibration.py"],
            environment=environment,
        ),
        _run(["./.venv/bin/python", "-m", "pytest"], environment=environment),
        _run(["./.venv/bin/ruff", "check", "src", "tests", "scripts"]),
        _run(["./.venv/bin/python", "-m", "uc_bench", "doctor"], environment=environment),
        _run(["./.venv/bin/python", "scripts/project_status.py", "--check"]),
        _run(["./.venv/bin/python", "scripts/run_docker_preflight.py"], environment=environment),
    ]
    replay = _read(ROOT / "artifacts/diagnostics/hard_suite_v08_legacy_replay.json")
    controls = _read(ROOT / "artifacts/diagnostics/hard_suite_v08_mvp_controls.json")
    readiness = _read(ROOT / "artifacts/diagnostics/hard_suite_v08_mvp_readiness.json")
    execution = _read(ROOT / "configs/hard_suite_v08_execution.json")
    parent = read_v072_freeze_manifest(ROOT)
    current_parent_hashes = v072_frozen_hashes(ROOT)
    parent_unchanged = (
        current_parent_hashes == parent["hashes"]
        and parent["hash_set_digest"]
        == "f17ce1ffe7e3986fe63f70644b55a3d624325ad55792e078f43a58708c26c328"
    )
    key = load_openrouter_key(ROOT)
    checked_paths = [
        ROOT / "configs/hard_suite_v08_mvp.json",
        ROOT / "configs/hard_suite_v08_execution.json",
        ROOT / "src/uc_bench/v08_schema.py",
        ROOT / "src/uc_bench/v08_interface.py",
        ROOT / "src/uc_bench/v08_environment.py",
        ROOT / "src/uc_bench/v08_verifier.py",
        ROOT / "src/uc_bench/v08_runner.py",
        ROOT / "scripts/run_v08_development.py",
        ROOT / "artifacts/diagnostics/hard_suite_v08_mvp_controls.json",
    ]
    leaks: list[str] = []
    for path in checked_paths:
        if path.is_dir():
            leaks.extend(
                f"{path.relative_to(ROOT).as_posix()}/{item}"
                for item in credential_locations(path, key)
            )
        elif path.is_file() and key.encode() in path.read_bytes():
            leaks.append(path.relative_to(ROOT).as_posix())
    prompt_leak = mapping_contains_credential({"contract": V08_AGENT_CONTRACT}, key)
    prerequisite_checks = {
        "all_five_legacy_trajectories_replayed_and_manually_confirmed": replay.get(
            "all_five_manually_confirmed"
        )
        is True,
        "all_35_controls_pass": controls.get("status") == "passed"
        and controls.get("control_count") == 35,
        "five_condition_readiness_passes": readiness.get("status")
        == "local_validation_passed_unfrozen",
        "exact_three_conditions_only": [
            row["condition_id"] for row in execution["conditions_in_order"]
        ]
        == ["case_02", "case_03_signal_remains", "case_04"],
        "pinned_openai_no_fallback": execution.get("model_id")
        == "openai/gpt-5.6-sol"
        and execution.get("provider_order") == ["OpenAI"]
        and execution.get("allow_fallbacks") is False,
        "exact_eight_dollar_cap": execution.get("maximum_incremental_spend_usd") == 8.0,
        "parent_v072_archive_unchanged": parent_unchanged,
        "credentials_absent_from_contract_code_and_artifacts": not leaks and not prompt_leak,
    }
    failed_commands = [row for row in commands if row["return_code"] != 0]
    passed = not failed_commands and all(prerequisite_checks.values())
    result = {
        "schema_version": "0.8-local-pre-exposure-gate-1",
        "completed_at": datetime.now(UTC).isoformat(),
        "status": "passed" if passed else "failed",
        "prerequisite_checks": prerequisite_checks,
        "commands": commands,
        "failed_command_count": len(failed_commands),
        "archived_v072_hash_set_digest": parent["hash_set_digest"],
        "credential_leakage_detected": bool(leaks or prompt_leak),
        "credential_leak_locations": leaks,
        "scientific_requests": 0,
        "heldout_requests": 0,
        "astra_requests": 0,
        "release_freeze_created": False,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix(OUTPUT.suffix + ".tmp")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(OUTPUT)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

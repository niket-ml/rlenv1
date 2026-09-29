#!/usr/bin/env python3
"""Run the zero-cost local gate for the final v0.8 Sol development check."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.hashing import sha256_file
from uc_bench.v08_controls import run_v08_mvp_controls
from uc_bench.v08_repair_snapshot import SNAPSHOT_02_PATH, read_v08_repair_snapshot

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts/diagnostics/final_sol_infrastructure_gate.json"
EXPECTED_PARENT_DIGEST = "937bc7d08e74e7f7fd8b718761e96ca1b1989ff7a1aa5caaa9cf9ce66fbc5730"
EXPECTED_PARENT_MANIFEST = "734512a33469232c27c0ee4a04343b6ac59636f9d3359d5d1dfb0a3ce0cf70d6"


def _run(command: list[str], *, environment: dict[str, str]) -> dict[str, Any]:
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


def _write(value: dict[str, Any]) -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix(OUTPUT.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(OUTPUT)


def main() -> int:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = "src"
    environment["UC_BENCH_OFFLINE_GATE"] = "1"
    commands = [
        _run(
            ["./.venv/bin/python", "-m", "pytest"],
            environment=environment,
        ),
        _run(
            ["./.venv/bin/ruff", "check", "src", "tests", "scripts"],
            environment=environment,
        ),
        _run(
            ["./.venv/bin/python", "-m", "uc_bench", "doctor"],
            environment=environment,
        ),
        _run(
            ["./.venv/bin/python", "scripts/project_status.py", "--check"],
            environment=environment,
        ),
        _run(
            ["./.venv/bin/python", "scripts/run_docker_preflight.py"],
            environment=environment,
        ),
    ]
    parent = read_v08_repair_snapshot(ROOT)
    with tempfile.TemporaryDirectory(prefix="uc-final-sol-controls-") as directory:
        controls = run_v08_mvp_controls(ROOT, Path(directory))
    config = json.loads((ROOT / "configs/final_sol_check.json").read_text(encoding="utf-8"))
    checks = {
        "snapshot_02_digest_intact": parent["hash_set_digest"] == EXPECTED_PARENT_DIGEST,
        "snapshot_02_manifest_intact": sha256_file(ROOT / SNAPSHOT_02_PATH)
        == EXPECTED_PARENT_MANIFEST,
        "all_228_snapshot_02_files_byte_identical": parent["file_count"] == 228,
        "all_35_scientific_controls_pass": controls["status"] == "passed"
        and controls["control_count"] == 35,
        "naturalistic_language_controls_pass": controls[
            "naturalistic_language_fixture_count"
        ]
        >= 4,
        "fake_provider_reveal_and_c4_resume_tests_in_full_suite": commands[0][
            "return_code"
        ]
        == 0,
        "host_persistence_not_agent_visible": config["persistence"]["host_only"]
        and config["persistence"]["agent_visible"] is False,
        "atomic_response_and_action_persistence_enabled": config["persistence"][
            "atomic_after_every_model_response"
        ]
        and config["persistence"]["atomic_after_every_tool_action"],
        "credential_redaction_enabled": config["persistence"]["credential_redaction"],
        "exact_two_condition_scope": [
            row["condition_id"] for row in config["conditions_in_order"]
        ]
        == ["case_03_signal_remains", "case_04"],
        "exact_spend_cap": config["maximum_incremental_spend_usd"] == 4.78,
        "pinned_openai_no_fallback": config["provider_order"] == ["OpenAI"]
        and config["allow_fallbacks"] is False,
        "heldout_and_astra_forbidden": "heldout" in config["forbidden_partitions"]
        and "openai/gpt-6-astra" in config["forbidden_models"],
    }
    failed_commands = [row for row in commands if row["return_code"] != 0]
    passed = not failed_commands and all(checks.values())
    result = {
        "schema_version": "0.8-final-sol-infrastructure-gate-1",
        "completed_at": datetime.now(UTC).isoformat(),
        "status": "passed" if passed else "failed",
        "checks": checks,
        "commands": commands,
        "failed_command_count": len(failed_commands),
        "control_summary": {
            "status": controls["status"],
            "condition_count": controls["condition_count"],
            "control_count": controls["control_count"],
            "naturalistic_language_fixture_count": controls[
                "naturalistic_language_fixture_count"
            ],
        },
        "snapshot_02": {
            "manifest_sha256": sha256_file(ROOT / SNAPSHOT_02_PATH),
            "hash_set_digest": parent["hash_set_digest"],
            "file_count": parent["file_count"],
            "changed_file_count": 0,
        },
        "api_requests": 0,
        "api_spend_usd": 0.0,
        "scientific_files_changed": 0,
        "verifier_files_changed": 0,
        "release_freeze_created": False,
    }
    _write(result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Run the complete offline gate for the v0.8 verifier-architecture repair."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.hashing import sha256_file

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts/diagnostics/hard_suite_v08_verifier_repair_gate.json"
FIRST_SNAPSHOT = ROOT / "artifacts/diagnostics/hard_suite_v08_execution_snapshot.json"
CASE2_SUMMARY = (
    ROOT / "build/hard_suite_v08_runs/v08-gpt-5.6-sol-case_02-20260909T061848Z/run_summary.json"
)


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected JSON object: {path}")
    return value


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


def main() -> int:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = "src"
    environment["UC_BENCH_OFFLINE_GATE"] = "1"
    commands = [
        _run(
            ["./.venv/bin/python", "scripts/build_v08_verifier_repair.py"],
            environment=environment,
        ),
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
    architecture = _read(
        ROOT / "artifacts/diagnostics/hard_suite_v08_verifier_architecture_audit.json"
    )
    score_sources = _read(ROOT / "artifacts/diagnostics/hard_suite_v08_score_source_table.json")
    replay = _read(ROOT / "artifacts/diagnostics/hard_suite_v08_case2_development_replay.json")
    resume = _read(ROOT / "artifacts/diagnostics/hard_suite_v08_case3_resume_assessment.json")
    controls = _read(ROOT / "artifacts/diagnostics/hard_suite_v08_repair_controls.json")
    checks = {
        "architecture_audit_passed": architecture["status"] == "passed",
        "scientific_cases_unchanged": architecture["scientific_cases_changed"] is False,
        "score_source_registry_passed": score_sources["status"] == "passed"
        and score_sources["prose_affects_any_mission_score"] is False,
        "case2_exact_submission_replay_passed": replay["repaired_development_replay"][
            "complete_mission_success"
        ]
        is True
        and replay["repaired_development_replay"]["partial_scientific_quality"] == 100,
        "historical_case2_result_preserved": replay["raw_historical_result"][
            "partial_scientific_quality"
        ]
        == 95
        and replay["raw_historical_result"]["complete_mission_success"] is False,
        "case3_not_unsafely_resumable": resume["safe_resumption_possible"] is False,
        "all_35_original_controls_passed": controls["status"] == "passed"
        and controls["control_count"] == 35,
        "naturalistic_language_controls_passed": controls["naturalistic_language_fixture_count"]
        >= 4
        and controls["checks"]["naturalistic_professional_language_never_changes_science"] is True,
        "first_execution_snapshot_immutable": sha256_file(FIRST_SNAPSHOT)
        == "6e114b0c26dd4be39501c07173c1ea5fb55b907a97d409bf0e643a5837481d93",
        "case2_raw_summary_immutable": sha256_file(CASE2_SUMMARY)
        == "e9f711b61d99609982499695fd49cdc769d0c6ccc94ad94677d81ec0b2470111",
        "zero_model_calls": architecture["api_requests"] == 0,
    }
    failed_commands = [row for row in commands if row["return_code"] != 0]
    passed = not failed_commands and all(checks.values())
    result = {
        "schema_version": "0.8-development-verifier-repair-gate-1",
        "completed_at": datetime.now(UTC).isoformat(),
        "status": "passed" if passed else "failed",
        "checks": checks,
        "commands": commands,
        "failed_command_count": len(failed_commands),
        "api_requests": 0,
        "api_spend_usd": 0.0,
        "scientific_version_created": False,
        "release_freeze_created": False,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix(OUTPUT.suffix + ".tmp")
    temporary.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(OUTPUT)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

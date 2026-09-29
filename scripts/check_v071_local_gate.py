#!/usr/bin/env python3
"""Run and record all local v0.7.1 pre-freeze engineering gates."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.v07_freeze import read_v07_freeze_manifest, v07_frozen_hashes

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts/diagnostics/hard_suite_v071_local_gate.json"


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
    parent = read_v07_freeze_manifest(ROOT)
    current_science = v07_frozen_hashes(ROOT)
    environment = dict(os.environ)
    environment["PYTHONPATH"] = "src"
    commands = [
        _run(["./.venv/bin/python", "-m", "pytest"], environment=environment),
        _run(["./.venv/bin/ruff", "check", "src", "tests", "scripts"]),
        _run(["./.venv/bin/python", "-m", "uc_bench", "doctor"], environment=environment),
        _run(["./.venv/bin/python", "scripts/project_status.py", "--check"]),
    ]
    mismatches = sorted(
        path
        for path in set(parent["hashes"]) | set(current_science)
        if parent["hashes"].get(path) != current_science.get(path)
    )
    failed = sum(row["return_code"] != 0 for row in commands)
    result = {
        "schema_version": "0.7.1-local-gate-1",
        "completed_at": datetime.now(UTC).isoformat(),
        "status": "passed" if not failed and not mismatches else "failed",
        "parent_scientific_hash_set_digest": parent["hash_set_digest"],
        "scientific_hash_file_count": len(current_science),
        "scientific_hash_mismatch_count": len(mismatches),
        "scientific_hash_mismatches": mismatches,
        "exact_v071_regression_file": "tests/test_v071_infrastructure.py",
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

#!/usr/bin/env python3
"""Run every zero-cost release gate and persist the open MMMVP RC result."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.mmmvp_open_audit import run_open_endedness_audit
from uc_bench.mmmvp_open_controls import CONDITIONS
from uc_bench.mmmvp_open_freeze import AUDIT_PATH, LOCAL_GATE_PATH


def _run(root: Path, command: list[str]) -> dict[str, Any]:
    started = time.monotonic()
    environment = dict(os.environ)
    environment["PYTHONPATH"] = "src"
    result = subprocess.run(
        command,
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "command": command,
        "returncode": result.returncode,
        "wall_seconds": round(time.monotonic() - started, 3),
        "stdout_tail": result.stdout[-4000:],
        "stderr_tail": result.stderr[-4000:],
        "passed": result.returncode == 0,
    }


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    root = Path(".").resolve()
    commands = [
        _run(root, ["./.venv/bin/ruff", "check", "src", "tests", "scripts"]),
        _run(root, ["./.venv/bin/python", "-m", "pytest", "-q"]),
        _run(root, ["./.venv/bin/python", "-m", "uc_bench", "doctor"]),
        _run(root, ["./.venv/bin/python", "scripts/project_status.py", "--check"]),
        _run(root, ["./.venv/bin/python", "scripts/run_docker_preflight.py"]),
    ]
    audit_root = Path(tempfile.mkdtemp(prefix="uc-mmmvp-open-rc1-audit-"))
    audit_started = time.monotonic()
    audit = run_open_endedness_audit(root, audit_root)
    audit_command = {
        "command": ["run_open_endedness_audit", "<temporary-host-root>"],
        "returncode": 0 if audit["status"] == "passed" else 1,
        "wall_seconds": round(time.monotonic() - audit_started, 3),
        "stdout_tail": json.dumps(
            {
                "status": audit["status"],
                "controls": audit["controls"]["status"],
                "red_team": audit["red_team_review"]["status"],
            },
            sort_keys=True,
        ),
        "stderr_tail": "",
        "passed": audit["status"] == "passed",
    }
    commands.append(audit_command)
    _write_json(root / AUDIT_PATH, audit)
    passed = all(row["passed"] for row in commands)
    gate = {
        "schema_version": "uc-bench-open-mmmvp-local-gate-1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "passed" if passed else "failed",
        "api_requests": 0,
        "compatibility_requests": 0,
        "scientific_requests": 0,
        "condition_ids": list(CONDITIONS),
        "commands": commands,
        "open_endedness_audit_status": audit["status"],
        "control_status": audit["controls"]["status"],
        "unresolved_blocking_or_major_findings": audit["red_team_review"][
            "unresolved_blocking_or_major_findings"
        ],
        "accepted_limitations": [
            row
            for row in audit["red_team_review"]["findings"]
            if row["status"] == "accepted_limitation"
        ],
        "release_candidate_only": True,
        "model_exposure_authorized": False,
    }
    _write_json(root / LOCAL_GATE_PATH, gate)
    print(
        json.dumps(
            {
                "status": gate["status"],
                "api_requests": 0,
                "audit": AUDIT_PATH.as_posix(),
                "local_gate": LOCAL_GATE_PATH.as_posix(),
            },
            sort_keys=True,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

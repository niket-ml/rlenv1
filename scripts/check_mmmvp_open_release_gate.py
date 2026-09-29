#!/usr/bin/env python3
"""Rerun RC1 gates without mutating the already-frozen scientific artifacts."""

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
from uc_bench.mmmvp_open_freeze import read_open_mmmvp_freeze
from uc_bench.mmmvp_open_provider import load_open_route_contract_adapters

OUTPUT_PATH = Path("artifacts/mmmvp_open_release/pre_exposure_gate.json")


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


def main() -> int:
    root = Path(".").resolve()
    target = root / OUTPUT_PATH
    if target.exists():
        raise RuntimeError("The pre-exposure gate result already exists")
    before = read_open_mmmvp_freeze(root)
    commands = [
        _run(root, ["./.venv/bin/ruff", "check", "src", "tests", "scripts"]),
        _run(root, ["./.venv/bin/python", "-m", "pytest", "-q"]),
        _run(root, ["./.venv/bin/python", "-m", "uc_bench", "doctor"]),
        _run(root, ["./.venv/bin/python", "scripts/project_status.py", "--check"]),
        _run(root, ["./.venv/bin/python", "scripts/run_docker_preflight.py"]),
    ]
    audit_root = Path(tempfile.mkdtemp(prefix="uc-mmmvp-open-release-audit-"))
    started = time.monotonic()
    audit = run_open_endedness_audit(root, audit_root)
    commands.append(
        {
            "command": ["run_open_endedness_audit", "<temporary-host-root>"],
            "returncode": 0 if audit["status"] == "passed" else 1,
            "wall_seconds": round(time.monotonic() - started, 3),
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
    )
    adapters = load_open_route_contract_adapters(root)
    after = read_open_mmmvp_freeze(root)
    unchanged = before["hash_set_digest"] == after["hash_set_digest"]
    unresolved = audit["red_team_review"]["unresolved_blocking_or_major_findings"]
    passed = all(row["passed"] for row in commands) and unchanged and not unresolved
    value = {
        "schema_version": "uc-bench-open-mmmvp-pre-exposure-gate-1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "passed" if passed else "failed",
        "api_requests": 0,
        "scientific_requests": 0,
        "compatibility_requests": 0,
        "scientific_freeze_digest_before": before["hash_set_digest"],
        "scientific_freeze_digest_after": after["hash_set_digest"],
        "scientific_freeze_unchanged": unchanged,
        "route_adapter_count": len(adapters),
        "commands": commands,
        "open_endedness_audit": {
            "status": audit["status"],
            "request_sha256": audit["serialized_request_sha256"],
            "red_team_findings": audit["red_team_review"]["findings"],
            "unresolved_blocking_or_major_findings": unresolved,
        },
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(target)
    print(json.dumps({"status": value["status"], "api_requests": 0}, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Run the complete zero-cost RC1.3 lifecycle and invariance gate."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.hashing import canonical_sha256, sha256_file
from uc_bench.mmmvp_open_audit import run_open_endedness_audit
from uc_bench.mmmvp_open_freeze import read_open_mmmvp_freeze
from uc_bench.mmmvp_open_rc11_compatibility import compatibility_identity
from uc_bench.mmmvp_open_rc12_freeze import read_rc12_release_freeze
from uc_bench.mmmvp_open_rc13_freeze import (
    RC13_GATE_PATH,
    SCIENTIFIC_FREEZE_DIGEST,
    SERIALIZED_REQUEST_DIGEST,
    TOOL_SCHEMA_DIGEST,
    rc12_complete_archive_hashes,
)

ROOT = Path(__file__).resolve().parents[1]
SECRET_PATTERN = re.compile(rb"sk-or-v1-[A-Za-z0-9_-]{16,}")


def _run(command: list[str]) -> dict[str, Any]:
    started = time.monotonic()
    environment = dict(os.environ)
    environment["PYTHONPATH"] = "src"
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "command": command,
        "returncode": result.returncode,
        "wall_seconds": round(time.monotonic() - started, 3),
        "stdout_tail": result.stdout[-8000:],
        "stderr_tail": result.stderr[-8000:],
        "passed": result.returncode == 0,
    }


def _credential_locations(root: Path) -> list[str]:
    if not root.exists():
        return []
    return [
        path.relative_to(ROOT).as_posix()
        for path in root.rglob("*")
        if path.is_file() and SECRET_PATTERN.search(path.read_bytes())
    ]


def main() -> int:
    target = ROOT / RC13_GATE_PATH
    if target.exists():
        raise RuntimeError("The RC1.3 pre-exposure gate already exists")
    scientific_before = read_open_mmmvp_freeze(ROOT)
    rc12_before = read_rc12_release_freeze(ROOT)
    archive_before = rc12_complete_archive_hashes(ROOT)
    identity_before = compatibility_identity(ROOT)
    compatibility = json.loads(
        (ROOT / "artifacts/mmmvp_open_rc13/inherited_compatibility.json").read_text()
    )
    cost = json.loads(
        (ROOT / "artifacts/mmmvp_open_rc13/cost_plan.json").read_text()
    )
    fixture = json.loads(
        (ROOT / "artifacts/mmmvp_open_rc13/deepseek_framework_error_fixture.json").read_text()
    )
    friction = json.loads(
        (
            ROOT
            / "artifacts/mmmvp_open_rc13/rc12_submission_friction_diagnostic.json"
        ).read_text()
    )

    commands = [
        _run(
            [
                "./.venv/bin/python",
                "-m",
                "pytest",
                "-q",
                "tests/test_mmmvp_open_rc13.py",
            ]
        ),
        _run(["./.venv/bin/ruff", "check", "src", "tests", "scripts"]),
        _run(["./.venv/bin/python", "-m", "pytest", "-q"]),
        _run(["./.venv/bin/python", "-m", "uc_bench", "doctor"]),
        _run(["./.venv/bin/python", "scripts/project_status.py", "--check"]),
        _run(["./.venv/bin/python", "scripts/run_docker_preflight.py"]),
        _run(["./.venv/bin/python", "scripts/run_mmmvp_open_rc12_docker_preflight.py"]),
    ]
    with tempfile.TemporaryDirectory(prefix="uc-mmmvp-rc13-audit-") as temporary:
        started = time.monotonic()
        audit = run_open_endedness_audit(ROOT, Path(temporary))
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

    scientific_after = read_open_mmmvp_freeze(ROOT)
    rc12_after = read_rc12_release_freeze(ROOT)
    archive_after = rc12_complete_archive_hashes(ROOT)
    identity_after = compatibility_identity(ROOT)
    credential_locations = _credential_locations(ROOT / "artifacts/mmmvp_open_rc13")
    fixture_source = ROOT / fixture["source_rc12_latest_path"]
    config12 = json.loads(
        (ROOT / "configs/uc_bench_mmmvp_open_rc12_release.json").read_text()
    )
    config13 = json.loads(
        (ROOT / "configs/uc_bench_mmmvp_open_rc13_release.json").read_text()
    )
    invariants = {
        "scientific_freeze_exact": scientific_before["hash_set_digest"]
        == scientific_after["hash_set_digest"]
        == SCIENTIFIC_FREEZE_DIGEST,
        "serialized_request_exact": identity_after["serialized_request_sha256"]
        == SERIALIZED_REQUEST_DIGEST,
        "tool_schema_exact": identity_after["tool_schema_sha256"]
        == TOOL_SCHEMA_DIGEST,
        "rc12_release_unchanged": rc12_before == rc12_after,
        "rc12_archive_unchanged": archive_before == archive_after,
        "provider_facing_identity_unchanged": identity_before == identity_after,
        "scientific_episode_budget_unchanged": config12["scientific_episode"]
        == config13["scientific_episode"],
        "ten_compatibility_passes_inherited": compatibility.get(
            "inherited_model_count"
        )
        == 10,
        "no_paid_compatibility_calls": compatibility.get(
            "paid_compatibility_requests"
        )
        == 0,
        "exact_deepseek_fixture_matches_rc12": sha256_file(fixture_source)
        == fixture["source_rc12_latest_sha256"],
        "cost_plan_uses_five_rc12_cells": len(cost.get("observations") or []) == 5,
        "cost_plan_no_scientific_calls": cost.get("scientific_api_requests") == 0,
        "submission_friction_kept_separate": friction.get(
            "source_trajectories_reused_for_rc13_scoring"
        )
        is False,
        "undisclosed_contract_rule_flagged": (
            "machine_enforced_rule_not_disclosed_to_agent"
            in friction.get("warnings", [])
        ),
        "credentials_absent_from_artifacts": not credential_locations,
        "no_api_requests": True,
    }
    passed = (
        all(row["passed"] for row in commands)
        and all(invariants.values())
        and not audit["red_team_review"]["unresolved_blocking_or_major_findings"]
    )
    value = {
        "schema_version": "uc-bench-open-mmmvp-rc1-3-pre-exposure-gate-1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "passed" if passed else "failed",
        "api_requests": 0,
        "scientific_requests": 0,
        "compatibility_requests": 0,
        "scientific_freeze_digest": scientific_after["hash_set_digest"],
        "rc12_infrastructure_digest": rc12_after["infrastructure_digest"],
        "rc12_archive_digest": canonical_sha256(archive_after),
        "rc12_archive_file_count": len(archive_after),
        "compatibility_identity": identity_after,
        "credential_locations": credential_locations,
        "cost_gate": {
            "ten_cell_no_cache_p90_usd": cost["ten_cell_no_cache_p90_usd"],
            "authorized_cap_usd": cost["authorized_cap_usd"],
            "paid_execution_allowed": cost["paid_execution_allowed"],
        },
        "invariants": invariants,
        "commands": commands,
        "open_endedness_audit": {
            "status": audit["status"],
            "request_sha256": audit["serialized_request_sha256"],
            "unresolved_blocking_or_major_findings": audit["red_team_review"][
                "unresolved_blocking_or_major_findings"
            ],
        },
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(target)
    print(
        json.dumps(
            {
                "status": value["status"],
                "api_requests": 0,
                "paid_execution_allowed": cost["paid_execution_allowed"],
            },
            sort_keys=True,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

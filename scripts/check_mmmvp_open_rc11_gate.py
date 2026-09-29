#!/usr/bin/env python3
"""Run the complete zero-cost RC1.1 infrastructure and invariance gate."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.hashing import canonical_sha256
from uc_bench.mmmvp_open_audit import run_open_endedness_audit
from uc_bench.mmmvp_open_freeze import read_open_mmmvp_freeze
from uc_bench.mmmvp_open_rc11_compatibility import (
    INHERITANCE_PATH,
    compatibility_identity,
)
from uc_bench.mmmvp_open_rc11_freeze import (
    RC1_RELEASE_DIGEST,
    RC11_GATE_PATH,
    SCIENTIFIC_FREEZE_DIGEST,
    rc1_archive_hashes,
)
from uc_bench.mmmvp_open_release_freeze import read_open_release_freeze

ROOT = Path(__file__).resolve().parents[1]


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
        "stdout_tail": result.stdout[-6000:],
        "stderr_tail": result.stderr[-6000:],
        "passed": result.returncode == 0,
    }


def main() -> int:
    target = ROOT / RC11_GATE_PATH
    if target.exists():
        raise RuntimeError("The RC1.1 pre-exposure gate already exists")
    scientific_before = read_open_mmmvp_freeze(ROOT)
    release_before = read_open_release_freeze(ROOT)
    archive_before = rc1_archive_hashes(ROOT)
    inheritance = json.loads((ROOT / INHERITANCE_PATH).read_text(encoding="utf-8"))
    identity_before = compatibility_identity(ROOT)
    commands = [
        _run(["./.venv/bin/ruff", "check", "src", "tests", "scripts"]),
        _run(["./.venv/bin/python", "-m", "pytest", "-q"]),
        _run(["./.venv/bin/python", "-m", "uc_bench", "doctor"]),
        _run(["./.venv/bin/python", "scripts/project_status.py", "--check"]),
        _run(["./.venv/bin/python", "scripts/run_docker_preflight.py"]),
        _run(["./.venv/bin/python", "scripts/run_mmmvp_open_rc11_docker_preflight.py"]),
    ]
    with tempfile.TemporaryDirectory(prefix="uc-mmmvp-rc11-audit-") as temporary:
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
    release_after = read_open_release_freeze(ROOT)
    archive_after = rc1_archive_hashes(ROOT)
    identity_after = compatibility_identity(ROOT)
    invariants = {
        "scientific_freeze_exact": scientific_before["hash_set_digest"]
        == scientific_after["hash_set_digest"]
        == SCIENTIFIC_FREEZE_DIGEST,
        "rc1_release_freeze_exact": release_before["category_digest_set"]
        == release_after["category_digest_set"]
        == RC1_RELEASE_DIGEST,
        "rc1_archive_unchanged": archive_before == archive_after,
        "compatibility_identity_unchanged": identity_before == identity_after,
        "serialized_request_exact": identity_after["serialized_request_sha256"]
        == scientific_after["serialized_request_sha256"],
        "nine_compatibility_passes_inherited": inheritance.get("inherited_model_count") == 9,
        "qwen_original_failure_preserved": bool(inheritance.get("original_qwen_failure")),
        "no_api_requests": True,
    }
    passed = (
        all(row["passed"] for row in commands)
        and all(invariants.values())
        and not audit["red_team_review"]["unresolved_blocking_or_major_findings"]
    )
    value = {
        "schema_version": "uc-bench-open-mmmvp-rc1-1-pre-exposure-gate-1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "passed" if passed else "failed",
        "api_requests": 0,
        "scientific_requests": 0,
        "compatibility_requests": 0,
        "scientific_freeze_digest": scientific_after["hash_set_digest"],
        "rc1_release_digest": release_after["category_digest_set"],
        "rc1_archive_digest": canonical_sha256(archive_after),
        "compatibility_identity": identity_after,
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
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(target)
    print(json.dumps({"status": value["status"], "api_requests": 0}, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

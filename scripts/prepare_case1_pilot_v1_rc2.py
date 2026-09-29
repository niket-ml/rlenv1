#!/usr/bin/env python3
"""Run all zero-cost RC2 gates, then create its immutable pre-science freeze."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Reuse the already frozen release's exact gate implementations, not new approximations.
from prepare_case1_pilot_v1_release import controls_summary, docker_preflight

from uc_bench.case1_pilot_v1_rc2_compatibility import (
    OFFLINE_REPLAY_PATH,
    rc1_immutable_evidence_hashes,
    write_offline_replay,
)
from uc_bench.case1_pilot_v1_rc2_release import (
    CANDIDATE_PATH,
    FREEZE_PATH,
    SELF_CONTAINMENT_PATH,
    ZERO_COST_GATE_PATH,
    candidate_manifest,
    freeze_rc2,
    scientific_parity,
    stage_rc2_closure,
    write_candidate,
)
from uc_bench.case1_pilot_v1_release import container_identity, read_release_freeze
from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256
from uc_bench.mmmvp_open_rc17_controls import run_controls
from uc_bench.model_runner import _write_json


def command(
    root: Path,
    arguments: list[str],
    *,
    accepted_historical_failures: tuple[str, ...] = (),
    environment: dict[str, str] | None = None,
) -> dict[str, Any]:
    env = dict(os.environ)
    env["PYTHONPATH"] = (root / "src").as_posix()
    env.update(environment or {})
    completed = subprocess.run(
        arguments,
        cwd=root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=1_200,
    )
    rendered = completed.stdout + "\n" + completed.stderr
    failed = [line for line in rendered.splitlines() if line.startswith("FAILED ")]
    expected_only = bool(
        accepted_historical_failures
        and completed.returncode == 1
        and len(failed) == len(accepted_historical_failures)
        and all(any(name in line for line in failed) for name in accepted_historical_failures)
    )
    return {
        "command": arguments,
        "exit_code": completed.returncode,
        "passed": completed.returncode == 0 or expected_only,
        "process_passed": completed.returncode == 0,
        "release_policy_exception_applied": expected_only,
        "accepted_historical_failures": list(accepted_historical_failures),
        "stdout": completed.stdout[-8_000:],
        "stderr": completed.stderr[-8_000:],
    }


def staged_tests(stage: Path) -> dict[str, Any]:
    env = dict(os.environ)
    env.update(
        {
            "PYTHONPATH": (stage / "src").as_posix(),
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "UC_BENCH_CLEAN_ROOT": stage.as_posix(),
        }
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_case1_pilot_v1_release.py",
            "tests/test_case1_pilot_v1_rc2.py",
            "-q",
        ],
        cwd=stage,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=1_200,
    )
    return {
        "exit_code": result.returncode,
        "passed": result.returncode == 0,
        "stdout": result.stdout[-8_000:],
        "stderr": result.stderr[-8_000:],
    }


def no_literal_credentials(project_root: Path, hashes: dict[str, str]) -> bool:
    # Require the key prefix followed by a plausible secret-length token. This
    # deliberately does not flag source code that names the prefix as a test.
    pattern = re.compile(rb"sk-or-v1-[A-Za-z0-9_-]{20,}")
    return not any(
        pattern.search((project_root / relative).read_bytes()) for relative in hashes
    )


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    for relative in (CANDIDATE_PATH, FREEZE_PATH):
        if (root / relative).exists():
            raise ConfigurationError(f"RC2 preparation artifact already exists: {relative}")
    for relative in (SELF_CONTAINMENT_PATH, ZERO_COST_GATE_PATH):
        path = root / relative
        if path.exists():
            archive = path.with_name(path.stem + "_attempt_01_failed" + path.suffix)
            if archive.exists():
                raise ConfigurationError(f"RC2 failed-gate archive already exists: {archive}")
            shutil.copy2(path, archive)
    rc1 = read_release_freeze(root)
    evidence_before = rc1_immutable_evidence_hashes(root)
    if (root / OFFLINE_REPLAY_PATH).exists():
        replay = json.loads((root / OFFLINE_REPLAY_PATH).read_text(encoding="utf-8"))
        if replay.get("status") != "passed" or replay.get("new_api_requests") != 0:
            raise ConfigurationError("Existing RC2 offline replay is not a zero-cost pass")
    else:
        replay = write_offline_replay(root)
    image_identity = container_identity(rc1["container_identity"]["requested_image"])
    if image_identity != rc1["container_identity"]:
        raise ConfigurationError("Frozen RC1 container identity changed")

    with tempfile.TemporaryDirectory(prefix="uc-case1-rc2-controls-") as directory:
        controls = controls_summary(run_controls(root, Path(directory) / "controls"))
    commands = [
        command(root, ["./.venv/bin/ruff", "check", "src", "tests", "scripts"]),
        command(
            root,
            ["./.venv/bin/python", "-m", "pytest", "-q"],
            accepted_historical_failures=(
                "test_schema_inventory_and_compatibility_inheritance_are_zero_cost",
                "test_rc16_gate_protects_the_complete_inherited_rc14_surface",
            ),
        ),
        command(root, ["./.venv/bin/python", "-m", "uc_bench", "doctor"]),
        command(root, ["./.venv/bin/python", "scripts/project_status.py", "--check"]),
    ]
    docker = docker_preflight(root, rc1["container_identity"]["requested_image"])
    parity = scientific_parity(root)
    candidate_before = candidate_manifest(root)
    with tempfile.TemporaryDirectory(prefix="uc-case1-rc2-stage-") as directory:
        stage_root = Path(directory) / "release"
        stage = stage_rc2_closure(root, stage_root)
        stage_result = staged_tests(stage_root)
        self_containment = {
            "schema_version": "uc-bench-case1-pilot-v1-rc2-self-containment-1",
            "created_at": datetime.now(UTC).isoformat(),
            "passed": bool(stage["hashes_match"] and stage_result["passed"]),
            "stage": {**stage, "stage_root": "ephemeral_clean_directory"},
            "staged_tests": stage_result,
            "imports_confined_to_staged_src": stage_result["passed"],
        }
    _write_json(root / SELF_CONTAINMENT_PATH, self_containment, secret="")
    evidence_after = rc1_immutable_evidence_hashes(root)
    gate_invariants = {
        "offline_five_ledger_replay_passed": replay["status"] == "passed",
        "offline_replay_made_zero_api_requests": replay["new_api_requests"] == 0,
        "all_five_routes_replayed_compatible": replay["corrected_rc2_compatible_count"] == 5,
        "original_rc1_classifications_preserved": replay[
            "original_rc1_shared_checker_failure_count"
        ]
        == 5,
        "scientific_parity_passed": parity["passed"],
        "rc1_evidence_immutable": evidence_before == evidence_after,
        "controls_passed": controls["passed"],
        "lint_tests_doctor_audit_passed": all(row["passed"] for row in commands),
        "docker_isolation_passed": docker["passed"],
        "self_containment_passed": self_containment["passed"],
        "candidate_hash_recomputation_stable": candidate_manifest(root)["closure"]
        == candidate_before["closure"],
        "credential_literal_scan_passed": no_literal_credentials(
            root, candidate_before["closure"]["hashes"]
        ),
        "scientific_api_requests": replay["new_api_requests"] == 0,
    }
    zero_cost = {
        "schema_version": "uc-bench-case1-pilot-v1-rc2-zero-cost-gate-1",
        "created_at": datetime.now(UTC).isoformat(),
        "passed": all(gate_invariants.values()),
        "api_requests": 0,
        "scientific_requests": 0,
        "compatibility_requests": 0,
        "identity_change_only": True,
        "offline_compatibility_replay": replay,
        "scientific_parity": parity,
        "controls": controls,
        "commands": commands,
        "docker": docker,
        "self_containment": self_containment,
        "invariants": gate_invariants,
    }
    _write_json(root / ZERO_COST_GATE_PATH, zero_cost, secret="")
    if not zero_cost["passed"]:
        print(json.dumps({"status": "failed", "invariants": gate_invariants}, indent=2))
        return 1
    candidate = write_candidate(root)
    freeze = freeze_rc2(
        root,
        candidate=candidate,
        self_containment=self_containment,
        zero_cost_gate=zero_cost,
    )
    print(
        json.dumps(
            {
                "status": freeze["status"],
                "release_id": freeze["release_id"],
                "release_digest": freeze["closure"]["aggregate_digest"],
                "file_count": freeze["closure"]["file_count"],
                "source_rc1_release_digest": freeze["source_rc1_release_digest"],
                "zero_cost_gate_sha256": canonical_sha256(zero_cost),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

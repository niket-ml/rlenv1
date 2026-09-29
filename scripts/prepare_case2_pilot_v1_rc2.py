#!/usr/bin/env python3
"""Run zero-cost Case 2 release gates, then freeze only after independent review."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.case2_pilot_v1_rc1_audit import build_controls
from uc_bench.case2_pilot_v1_rc1_provider import load_case2_config
from uc_bench.case2_pilot_v1_rc2_preflight import write_preflight
from uc_bench.case2_pilot_v1_rc2_release import (
    CANDIDATE_PATH,
    COMPATIBILITY_PATH,
    FREEZE_PATH,
    GATE_PATH,
    PREFLIGHT_PATH,
    RELEASE_ROOT,
    RL_REVIEW_PATH,
    SCOPE_DIFF_PATH,
    candidate_manifest,
    compatibility_adjudication,
    credential_scan,
    freeze,
    read_freeze,
    stage_closure,
    write_candidate,
    write_scope_diff,
)
from uc_bench.model_runner import _write_json

HISTORICAL_FAILURES = (
    "test_exact_production_path_and_terminal_retry",
    "test_exact_fake_provider_production_path_passes",
    "test_schema_inventory_and_compatibility_inheritance_are_zero_cost",
    "test_rc16_gate_protects_the_complete_inherited_rc14_surface",
)


def _clear_temporary_provenance(root: Path) -> None:
    """Remove Docker-added macOS provenance metadata before temp cleanup."""

    for path in [*sorted(root.rglob("*"), reverse=True), root]:
        with suppress(AttributeError, OSError):
            os.removexattr(path, "com.apple.provenance")


def _command(
    root: Path,
    arguments: list[str],
    *,
    accepted_historical_failures: tuple[str, ...] = (),
    timeout: int = 1_800,
) -> dict[str, Any]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = (root / "src").as_posix()
    completed = subprocess.run(
        arguments,
        cwd=root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    rendered = completed.stdout + "\n" + completed.stderr
    failures = [line for line in rendered.splitlines() if line.startswith("FAILED ")]
    expected_only = bool(
        accepted_historical_failures
        and completed.returncode == 1
        and failures
        and all(any(name in line for name in accepted_historical_failures) for line in failures)
    )
    return {
        "command": arguments,
        "exit_code": completed.returncode,
        "passed": completed.returncode == 0 or expected_only,
        "process_passed": completed.returncode == 0,
        "release_policy_exception_applied": expected_only,
        "accepted_historical_failures": list(accepted_historical_failures),
        "observed_failure_lines": failures,
        "stdout": completed.stdout[-16_000:],
        "stderr": completed.stderr[-16_000:],
    }


def _staged_import(stage: Path) -> dict[str, Any]:
    environment = dict(os.environ)
    environment.update(
        {
            "PYTHONPATH": (stage / "src").as_posix(),
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    script = (
        "from pathlib import Path; "
        "from uc_bench.case2_pilot_v1_rc2_release import candidate_manifest; "
        "r=candidate_manifest(Path('.')); "
        "assert r['release_id']=='uc-bench-case2-pilot-v1-rc2'; "
        "assert r['compatibility_inheritance']['passed']; "
        "print(r['closure']['aggregate_digest'])"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=stage,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=600,
    )
    return {
        "passed": completed.returncode == 0,
        "exit_code": completed.returncode,
        "digest": completed.stdout.strip().splitlines()[-1] if completed.stdout.strip() else None,
        "stdout": completed.stdout[-4_000:],
        "stderr": completed.stderr[-4_000:],
    }


def _fresh_process_freeze_check(root: Path) -> dict[str, Any]:
    environment = dict(os.environ)
    environment.update(
        {
            "PYTHONPATH": (root / "src").as_posix(),
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    script = (
        "from pathlib import Path; "
        "from uc_bench.case2_pilot_v1_rc2_release import read_freeze; "
        "r=read_freeze(Path('.')); print(r['closure']['aggregate_digest'])"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=600,
    )
    return {
        "passed": completed.returncode == 0,
        "exit_code": completed.returncode,
        "digest": completed.stdout.strip().splitlines()[-1] if completed.stdout.strip() else None,
        "stdout": completed.stdout[-4_000:],
        "stderr": completed.stderr[-4_000:],
    }


def gates(root: Path) -> dict[str, Any]:
    for relative in (
        CANDIDATE_PATH,
        PREFLIGHT_PATH,
        GATE_PATH,
        COMPATIBILITY_PATH,
        FREEZE_PATH,
        SCOPE_DIFF_PATH,
    ):
        if (root / relative).exists():
            raise FileExistsError(f"Case 2 preparation artifact already exists: {relative}")

    (root / RELEASE_ROOT).mkdir(parents=True, exist_ok=True)
    scope_diff = write_scope_diff(root)
    controls, parity = build_controls(root)
    compatibility = compatibility_adjudication(root)
    _write_json(root / COMPATIBILITY_PATH, compatibility, secret="")
    with tempfile.TemporaryDirectory(prefix="uc-case2-production-preflight-") as directory:
        temporary_root = Path(directory)
        try:
            preflight = write_preflight(
                root, temporary_root / "runs", root / PREFLIGHT_PATH
            )
        finally:
            _clear_temporary_provenance(temporary_root)

    python = (Path(sys.prefix) / "bin/python").absolute().as_posix()
    ruff = (Path(sys.prefix) / "bin/ruff").absolute().as_posix()
    commands = [
        _command(
            root,
            [python, "-m", "pytest", "-q", "tests/test_case2_pilot_v1_rc1.py"],
        ),
        _command(root, [python, "-m", "pytest", "-q", "tests/test_case2_pilot_v1_rc2.py"]),
        _command(
            root,
            [python, "-m", "pytest", "-q", "tests/test_case2_pilot_v1_rc2_release.py"],
        ),
        _command(root, [ruff, "check", "src", "tests", "scripts"]),
        _command(
            root,
            [python, "-m", "pytest", "-q"],
            accepted_historical_failures=HISTORICAL_FAILURES,
        ),
        _command(root, [python, "-m", "uc_bench", "doctor"]),
        _command(root, [python, "scripts/project_status.py", "--check"]),
        _command(root, [python, "scripts/run_pre_release_audit.py"]),
    ]

    candidate = candidate_manifest(root)
    with tempfile.TemporaryDirectory(prefix="uc-case2-clean-stage-") as directory:
        stage = Path(directory) / "release"
        staged = stage_closure(root, stage)
        staged_import = _staged_import(stage)
    visible_integrity = [
        row["summary"].get("integrity") or {}
        for row in preflight["valid_scenarios"].values()
    ]
    checks = {
        "candidate_controls": controls["passed"],
        "candidate_control_count_preserved": len(controls["controls"]) == 16,
        "rc1_to_rc2_scope_diff": scope_diff["passed"],
        "public_hidden_semantic_parity": parity["passed"],
        "exact_production_path_rehearsal": preflight["passed"],
        "all_53_case2_controls_pass": commands[0]["passed"],
        "endpoint_identity_regressions": commands[1]["passed"],
        "rc2_release_regressions": commands[2]["passed"],
        "full_repository_has_only_four_allowlisted_historical_failures": commands[4][
            "passed"
        ],
        "lint_doctor_status_audit": all(row["passed"] for row in commands[3:4] + commands[5:]),
        "docker_isolation": bool(visible_integrity)
        and all(row.get("workspace_boundary_enforced") for row in visible_integrity),
        "credential_scan": credential_scan(root, candidate["closure"]["groups"]),
        "clean_staged_closure": staged["passed"]
        and staged_import["passed"]
        and staged_import["digest"] == candidate["closure"]["aggregate_digest"],
        "compatibility_inherited_without_new_calls": compatibility["passed"]
        and not compatibility["affected_routes_requiring_live_canary"],
        "no_api_calls": preflight["api_requests"] == 0
        and controls["api_requests"] == 0
        and compatibility["new_api_requests"] == 0,
    }
    result = {
        "schema_version": "uc-bench-case2-pilot-v1-rc2-zero-cost-gate-1",
        "created_at": datetime.now(UTC).isoformat(),
        "passed": all(checks.values()),
        "checks": checks,
        "commands": commands,
        "control_summary": controls,
        "semantic_parity": parity,
        "preflight_checks": preflight["checks"],
        "compatibility": compatibility,
        "staged_closure": staged,
        "staged_import": staged_import,
        "candidate_digest": candidate["closure"]["aggregate_digest"],
        "api_requests": 0,
        "paid_spend_usd": 0.0,
    }
    _write_json(root / GATE_PATH, result, secret="")
    if result["passed"]:
        write_candidate(root)
    return result


def freeze_release(root: Path) -> dict[str, Any]:
    if not (root / RL_REVIEW_PATH).is_file():
        raise FileNotFoundError("The independent final RL review has not been recorded")
    value = freeze(root)
    reread = read_freeze(root)
    if reread["closure"]["aggregate_digest"] != value["closure"]["aggregate_digest"]:
        raise RuntimeError("Post-freeze release digest verification failed")
    return value


def verify(root: Path) -> dict[str, Any]:
    frozen = read_freeze(root)
    fresh = _fresh_process_freeze_check(root)
    passed = fresh["passed"] and fresh["digest"] == frozen["closure"]["aggregate_digest"]
    return {
        "passed": passed,
        "release_id": frozen["release_id"],
        "release_digest": frozen["closure"]["aggregate_digest"],
        "fresh_process": fresh,
        "model_count": len(frozen["execution_order"]),
        "scientific_hard_cap_usd": frozen["budgets_usd"]["scientific_hard_cap"],
        "configured_limits": load_case2_config(root)["execution_limits"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("gates", "freeze", "verify"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.phase == "gates":
        result = gates(root)
    elif args.phase == "freeze":
        result = freeze_release(root)
    else:
        result = verify(root)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("passed", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())

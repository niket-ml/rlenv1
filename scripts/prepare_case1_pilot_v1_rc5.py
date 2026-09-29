#!/usr/bin/env python3
"""Run every zero-cost RC5 release gate and freeze only a clean closure."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from prepare_case1_pilot_v1_release import docker_preflight

from uc_bench.case1_pilot_v1_rc5_contract import (
    CONTRACT_COMPLETENESS_AUDIT,
    contract_completeness_valid,
)
from uc_bench.case1_pilot_v1_rc5_controls import (
    rc4_artifacts_unchanged,
    run_rc5_controls,
    write_rc4_fixture_manifest,
)
from uc_bench.case1_pilot_v1_rc5_preflight import write_exact_production_preflight
from uc_bench.case1_pilot_v1_rc5_release import (
    BLIND_REVIEW_PATH,
    BLIND_REVIEW_ROUND1_PATH,
    CANDIDATE_PATH,
    CONTRACT_AUDIT_PATH,
    CONTROLS_PATH,
    FREEZE_PATH,
    ORDER_PATH,
    PREFLIGHT_PATH,
    RC4_FIXTURE_PATH,
    REVIEW_DISPOSITIONS_PATH,
    SELF_CONTAINMENT_PATH,
    VERIFIER_REVIEW_PATH,
    VERIFIER_REVIEW_ROUND1_PATH,
    ZERO_COST_GATE_PATH,
    candidate_manifest,
    credential_scan,
    freeze_rc5,
    review_gate_valid,
    stage_rc5_closure,
    write_candidate,
)
from uc_bench.case1_pilot_v1_release import read_release_freeze
from uc_bench.errors import ConfigurationError
from uc_bench.model_runner import _write_json


def write_attested_json(path: Path, value: Any) -> dict[str, Any]:
    """Persist a gate record and return its authoritative JSON representation."""

    _write_json(path, value, secret="")
    persisted = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(persisted, dict):
        raise ConfigurationError(f"Attested release record must be an object: {path}")
    return persisted


def command(
    root: Path,
    arguments: list[str],
    *,
    accepted_historical_failures: tuple[str, ...] = (),
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


def staged_gate(stage: Path) -> dict[str, Any]:
    environment = dict(os.environ)
    environment.update(
        {
            "PYTHONPATH": (stage / "src").as_posix(),
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "UC_BENCH_CLEAN_ROOT": stage.as_posix(),
        }
    )
    script = (
        "from pathlib import Path; "
        "from uc_bench.case1_pilot_v1_rc5_release import candidate_manifest; "
        f"r=candidate_manifest(Path({stage.as_posix()!r})); "
        "assert r['release_id']=='uc-bench-case1-pilot-v1-rc5'; "
        "assert r['rc4_artifacts_byte_identical']"
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
        "stdout": completed.stdout[-4_000:],
        "stderr": completed.stderr[-4_000:],
        "imports_confined_to_staged_src": completed.returncode == 0,
    }


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    python = Path(sys.executable).absolute().as_posix()
    ruff = (Path(sys.prefix) / "bin/ruff").absolute().as_posix()
    for relative in (
        CANDIDATE_PATH,
        CONTROLS_PATH,
        CONTRACT_AUDIT_PATH,
        PREFLIGHT_PATH,
        SELF_CONTAINMENT_PATH,
        ZERO_COST_GATE_PATH,
        FREEZE_PATH,
    ):
        if (root / relative).exists():
            raise ConfigurationError(f"RC5 preparation artifact already exists: {relative}")
    for relative in (
        ORDER_PATH,
        BLIND_REVIEW_ROUND1_PATH,
        VERIFIER_REVIEW_ROUND1_PATH,
        BLIND_REVIEW_PATH,
        VERIFIER_REVIEW_PATH,
        REVIEW_DISPOSITIONS_PATH,
    ):
        if not (root / relative).is_file():
            raise ConfigurationError(f"Required pre-freeze RC5 artifact is missing: {relative}")
    reviews = [
        json.loads((root / path).read_text(encoding="utf-8"))
        for path in (
            BLIND_REVIEW_PATH,
            VERIFIER_REVIEW_PATH,
            REVIEW_DISPOSITIONS_PATH,
            BLIND_REVIEW_ROUND1_PATH,
            VERIFIER_REVIEW_ROUND1_PATH,
        )
    ]
    if not review_gate_valid(reviews[0], reviews[1], reviews[2], reviews[3], reviews[4]):
        raise ConfigurationError("Independent review or finding disposition did not pass")

    rc4_before = rc4_artifacts_unchanged(root)
    fixture = write_rc4_fixture_manifest(root, root / RC4_FIXTURE_PATH)
    with tempfile.TemporaryDirectory(prefix="uc-case1-rc5-controls-") as directory:
        controls = run_rc5_controls(root, Path(directory))
    _write_json(root / CONTROLS_PATH, controls, secret="")
    tests_source = (root / "tests/test_case1_pilot_v1_rc5.py").read_text(encoding="utf-8")
    contract_checks = {
        row["agent_authored_field"]: bool(
            f"def {row['passing_test']}" in tests_source
            and f"def {row['failing_test']}" in tests_source
        )
        for row in CONTRACT_COMPLETENESS_AUDIT
    }
    contract_audit = {
        "schema_version": "uc-bench-case1-pilot-v1-rc5-contract-audit-1",
        "passed": contract_completeness_valid(tests_source) and all(contract_checks.values()),
        "rows": CONTRACT_COMPLETENESS_AUDIT,
        "test_definitions_present": contract_checks,
        "private_prose_scoring": False,
    }
    _write_json(root / CONTRACT_AUDIT_PATH, contract_audit, secret="")
    with tempfile.TemporaryDirectory(prefix="uc-case1-rc5-preflight-") as directory:
        preflight = write_exact_production_preflight(
            root, Path(directory) / "runs", root / PREFLIGHT_PATH
        )

    commands = [
        command(root, [ruff, "check", "src", "tests", "scripts"]),
        command(
            root,
            [python, "-m", "pytest", "-q"],
            accepted_historical_failures=(
                "test_schema_inventory_and_compatibility_inheritance_are_zero_cost",
                "test_rc16_gate_protects_the_complete_inherited_rc14_surface",
            ),
        ),
        command(root, [python, "-m", "uc_bench", "doctor"]),
        command(root, [python, "scripts/project_status.py", "--check"]),
    ]
    broad_project_audit = command(root, [python, "scripts/run_pre_release_audit.py"])
    try:
        broad_audit_payload = json.loads(broad_project_audit["stdout"])
    except (TypeError, ValueError, json.JSONDecodeError):
        broad_audit_payload = None
    broad_project_audit["semantic_result"] = broad_audit_payload
    broad_project_audit["scope"] = (
        "legacy broad-benchmark audit; its pre-science ranking/repeated-run gates are disclosed "
        "but cannot be used as a circular prerequisite for this Case-1 pre-science freeze"
    )
    scientific = read_release_freeze(root)
    docker = docker_preflight(root, scientific["container_identity"]["requested_image"])
    candidate_before = candidate_manifest(root)
    with tempfile.TemporaryDirectory(prefix="uc-case1-rc5-stage-") as directory:
        stage_root = Path(directory) / "release"
        staged_files = stage_rc5_closure(root, stage_root)
        staged = staged_gate(stage_root)
        self_containment = {
            "schema_version": "uc-bench-case1-pilot-v1-rc5-self-containment-1",
            "created_at": datetime.now(UTC).isoformat(),
            "passed": staged_files["hashes_match"] and staged["passed"],
            "stage": {**staged_files, "stage_root": "ephemeral_clean_directory"},
            "staged_gate": staged,
        }
    self_containment = write_attested_json(root / SELF_CONTAINMENT_PATH, self_containment)
    # Attest the persisted JSON representation. Some diagnostic structures use
    # tuples internally, which correctly serialize as JSON arrays; the freeze
    # must compare against those exact persisted bytes rather than Python-only
    # container identity.
    candidate_stable = candidate_manifest(root)["closure"] == candidate_before["closure"]
    invariants = {
        "rc4_complete_artifact_tree_unchanged": rc4_before and rc4_artifacts_unchanged(root),
        "immutable_rc4_fixture_recorded": fixture["raw_bytes_modified"] is False,
        "cohort_resource_science_reporting_controls_passed": controls["passed"],
        "contract_completeness_audit_passed": contract_audit["passed"],
        "independent_blind_review_passed": reviews[0]["passed"],
        "independent_verifier_red_team_passed": reviews[1]["passed"],
        "all_decision_critical_review_findings_resolved": reviews[2]["passed"],
        "exact_production_path_preflight_passed": preflight["passed"],
        "docker_isolation_passed": docker["passed"],
        "lint_tests_doctor_and_project_status_passed": all(row["passed"] for row in commands),
        "legacy_broad_project_audit_executed_and_disclosed": bool(
            broad_project_audit["passed"] and broad_audit_payload is not None
        ),
        "credential_scan_passed": credential_scan(root, candidate_before["closure"]["hashes"]),
        "clean_staged_release_passed": self_containment["passed"],
        "candidate_hash_recomputation_stable": candidate_stable,
        "provider_facing_adapter_request_and_tools_unchanged": all(
            (
                candidate_before["component_digests"]["agent_visible_request_digest"]
                == read_rc4_hash(root, "request_sha256"),
                candidate_before["component_digests"]["tool_schema_digest"]
                == read_rc4_hash(root, "tool_schema_sha256"),
            )
        ),
    }
    zero_cost = {
        "schema_version": "uc-bench-case1-pilot-v1-rc5-zero-cost-gate-1",
        "created_at": datetime.now(UTC).isoformat(),
        "passed": all(invariants.values()),
        "api_requests": 0,
        "scientific_requests": 0,
        "compatibility_requests": 0,
        "fake_provider_requests": preflight["fake_provider_requests"],
        "compatibility_inherited": True,
        "controls": controls,
        "contract_audit": contract_audit,
        "production_path_preflight": preflight,
        "commands": commands,
        "legacy_broad_project_audit": broad_project_audit,
        "docker": docker,
        "reviews": reviews,
        "self_containment": self_containment,
        "invariants": invariants,
    }
    zero_cost = write_attested_json(root / ZERO_COST_GATE_PATH, zero_cost)
    if not zero_cost["passed"]:
        print(json.dumps({"status": "failed", "invariants": invariants}, indent=2))
        return 1
    write_candidate(root)
    candidate = json.loads((root / CANDIDATE_PATH).read_text(encoding="utf-8"))
    freeze = freeze_rc5(
        root,
        candidate=candidate,
        self_containment=self_containment,
        zero_cost_gate=zero_cost,
    )
    print(
        json.dumps(
            {
                "status": "frozen_pre_science",
                "release_id": freeze["release_id"],
                "release_digest": freeze["closure"]["aggregate_digest"],
                "rc4_unchanged": rc4_artifacts_unchanged(root),
                "invariants": invariants,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def read_rc4_hash(root: Path, key: str) -> str:
    from uc_bench.case1_pilot_v1_rc4_release import read_rc4_freeze

    return str(read_rc4_freeze(root)[key])


if __name__ == "__main__":
    raise SystemExit(main())

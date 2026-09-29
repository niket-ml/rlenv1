#!/usr/bin/env python3
"""Run the complete zero-cost RC1.4 contract-only pre-exposure gate."""

from __future__ import annotations

import json
import subprocess
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import uc_bench.mmmvp_open_audit as open_audit
import uc_bench.mmmvp_open_controls as controls
from uc_bench.hashing import canonical_sha256, sha256_file
from uc_bench.mmmvp_blind_interface import serialized_open_request
from uc_bench.mmmvp_open_freeze import read_open_mmmvp_freeze
from uc_bench.mmmvp_open_rc11_compatibility import compatibility_identity
from uc_bench.mmmvp_open_rc12_environment import RC12OpenMMMVPEnvironment
from uc_bench.mmmvp_open_rc13_freeze import read_rc13_release_freeze
from uc_bench.mmmvp_open_rc14_audit import (
    replay_archived_submissions,
    write_contract_disclosure_audit,
)
from uc_bench.mmmvp_open_rc14_contract import RC14_AGENT_VISIBLE_CONTRACT
from uc_bench.mmmvp_open_rc14_environment import RC14OpenMMMVPEnvironment
from uc_bench.mmmvp_open_rc14_harness import (
    CONVERGENCE_RESULTS_PATH,
    forensic_adjudicate_round01,
)

TARGET = Path("artifacts/mmmvp_open_rc14/pre_exposure_gate_04.json")


def _command(root: Path, arguments: list[str]) -> dict[str, Any]:
    started = time.monotonic()
    completed = subprocess.run(arguments, cwd=root, text=True, capture_output=True, check=False)
    return {
        "command": arguments,
        "returncode": completed.returncode,
        "passed": completed.returncode == 0,
        "stdout_tail": completed.stdout[-6000:],
        "stderr_tail": completed.stderr[-6000:],
        "wall_seconds": round(time.monotonic() - started, 3),
    }


def _workspace_contract_only_delta(root: Path, temporary: Path) -> dict[str, Any]:
    rc13_root = temporary / "rc13"
    rc14_root = temporary / "rc14"
    RC12OpenMMMVPEnvironment(root, "case_01", rc13_root)
    RC14OpenMMMVPEnvironment(root, "case_01", rc14_root)

    def files(base: Path) -> dict[str, bytes]:
        return {
            path.relative_to(base).as_posix(): path.read_bytes()
            for path in sorted(base.rglob("*"))
            if path.is_file()
        }

    before = files(rc13_root)
    after = files(rc14_root)
    all_paths = set(before) | set(after)
    changed = sorted(path for path in all_paths if before.get(path) != after.get(path))
    return {
        "passed": changed == ["submission_contract.json"],
        "changed_paths": changed,
        "old_contract_sha256": sha256_file(rc13_root / "submission_contract.json"),
        "new_contract_sha256": sha256_file(rc14_root / "submission_contract.json"),
        "all_other_agent_visible_files_byte_identical": changed
        == ["submission_contract.json"],
    }


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    target = root / TARGET
    if target.exists():
        raise SystemExit("RC1.4 pre-exposure gate already exists")
    scientific = read_open_mmmvp_freeze(root)
    rc13_before = read_rc13_release_freeze(root)
    identity_before = compatibility_identity(root)
    disclosure = write_contract_disclosure_audit(root)
    replay = replay_archived_submissions(root)
    forensic = forensic_adjudicate_round01(root)
    convergence = json.loads((root / CONVERGENCE_RESULTS_PATH).read_text())
    commands = [
        _command(
            root,
            ["./.venv/bin/python", "-m", "pytest", "-q", "tests/test_mmmvp_open_rc14.py"],
        ),
        _command(root, ["./.venv/bin/ruff", "check", "src", "tests", "scripts"]),
        _command(root, ["./.venv/bin/python", "-m", "pytest", "-q"]),
        _command(root, ["./.venv/bin/python", "-m", "uc_bench", "doctor"]),
        _command(root, ["./.venv/bin/python", "scripts/project_status.py", "--check"]),
        _command(root, ["./.venv/bin/python", "scripts/run_docker_preflight.py"]),
        _command(
            root,
            ["./.venv/bin/python", "scripts/run_mmmvp_open_rc12_docker_preflight.py"],
        ),
    ]
    with tempfile.TemporaryDirectory(prefix="uc-rc14-gate-") as directory:
        temporary = Path(directory)
        delta = _workspace_contract_only_delta(root, temporary / "delta")
        old_controls_environment = controls.OpenMMMVPEnvironment
        old_audit_environment = open_audit.OpenMMMVPEnvironment
        try:
            controls.OpenMMMVPEnvironment = RC14OpenMMMVPEnvironment
            open_audit.OpenMMMVPEnvironment = RC14OpenMMMVPEnvironment
            open_result = open_audit.run_open_endedness_audit(
                root, temporary / "open-endedness"
            )
        finally:
            controls.OpenMMMVPEnvironment = old_controls_environment
            open_audit.OpenMMMVPEnvironment = old_audit_environment
    rc13_after = read_rc13_release_freeze(root)
    identity_after = compatibility_identity(root)
    config13 = json.loads(
        (root / "configs/uc_bench_mmmvp_open_rc13_release.json").read_text()
    )
    config14 = json.loads(
        (root / "configs/uc_bench_mmmvp_open_rc14_release.json").read_text()
    )
    scientific_hashes = scientific["hashes"]
    protected_logic_paths = [
        "src/uc_bench/mmmvp_open_schema.py",
        "src/uc_bench/mmmvp_open_verifier.py",
        "src/uc_bench/mmmvp_open_calculations.py",
        "grader_private/mmmvp_open_rc1/validity_cards.json",
    ]
    logic_unchanged = all(
        scientific_hashes.get(path) == sha256_file(root / path)
        for path in protected_logic_paths
    )
    serialized = serialized_open_request()
    contract_text = json.dumps(RC14_AGENT_VISIBLE_CONTRACT).lower()
    credential_markers = []
    for path in sorted((root / "artifacts/mmmvp_open_rc14").rglob("*")):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "sk-or-v1-" in text or "authorization: bearer" in text.lower():
            credential_markers.append(path.relative_to(root).as_posix())
    invariants = {
        "rc13_immutable": rc13_before == rc13_after,
        "scientific_freeze_unchanged": scientific["hash_set_digest"]
        == "466441682b04175432329b41adcfd735cdea66f860d66f046dfae195c91e701c",
        "verifier_schema_calculation_and_truth_logic_unchanged": logic_unchanged,
        "provider_request_unchanged": identity_before["serialized_request_sha256"]
        == identity_after["serialized_request_sha256"]
        == "d50747a564877dea31329cd71e9a8a1e3b4ed8f913b802d059cc3c053d0d9523",
        "tool_schema_unchanged": identity_before["tool_schema_sha256"]
        == identity_after["tool_schema_sha256"]
        == "a29133462152f7c78452a5e13c76efc2991142b8703ce418cdf4a78d10f842d7",
        "provider_route_and_adapter_identity_unchanged": identity_before["models"]
        == identity_after["models"],
        "scientific_episode_budget_unchanged": config13["scientific_episode"]
        == config14["scientific_episode"],
        "only_visible_workspace_contract_changed": delta["passed"],
        "contract_disclosure_audit_passed": disclosure["status"] == "passed",
        "archived_replay_passed_without_rescoring": replay["status"] == "passed"
        and not replay["archived_scores_recomputed"]
        and not replay["archived_scores_reinterpreted"],
        "all_archived_schema_issues_now_disclosed": replay[
            "all_replayed_issues_now_disclosed"
        ],
        "open_endedness_controls_passed": open_result["status"] == "passed",
        "contract_contains_no_case_identity": not any(
            token in contract_text
            for token in ("case_01", "case_02", "case_03", "case_04")
        ),
        "credential_scan_passed": not credential_markers,
        "round01_compatibility_preserved": forensic[
            "original_result_sha256_before"
        ]
        == forensic["original_result_sha256_after"],
        "production_path_compatibility_converged": convergence.get("status")
        == "passed"
        and convergence.get("scientific_requests") == 0
        and convergence.get("case_data_in_requests") is False,
        "serialized_tool_surface_still_condition_blind": canonical_sha256(
            serialized["tools"]
        )
        == identity_before["tool_schema_sha256"],
    }
    passed = all(row["passed"] for row in commands) and all(invariants.values())
    value = {
        "schema_version": "uc-bench-open-mmmvp-rc1-4-pre-exposure-gate-1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "passed" if passed else "failed",
        "api_requests": 0,
        "scientific_requests": 0,
        "compatibility_requests": 0,
        "commands": commands,
        "invariants": invariants,
        "workspace_delta": delta,
        "contract_disclosure_audit": disclosure,
        "archived_submission_replay": replay,
        "round01_forensic_adjudication": forensic,
        "compatibility_convergence": convergence,
        "open_endedness_audit": {
            "status": open_result["status"],
            "unresolved_blocking_or_major_findings": open_result.get(
                "unresolved_blocking_or_major_findings"
            ),
        },
        "credential_locations": credential_markers,
        "rc13_infrastructure_digest": rc13_before["infrastructure_digest"],
        "scientific_freeze_digest": scientific["hash_set_digest"],
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_target = target.with_suffix(".json.tmp")
    temporary_target.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary_target.replace(target)
    print(
        json.dumps(
            {
                "status": value["status"],
                "api_requests": 0,
                "contract_sha256": disclosure["contract_sha256"],
            },
            sort_keys=True,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

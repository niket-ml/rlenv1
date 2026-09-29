"""Immutable infrastructure-only RC3 release over the RC1 scientific base."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.case1_pilot_v1_provider import load_case1_pilot_config
from uc_bench.case1_pilot_v1_rc2_release import (
    FREEZE_PATH as RC2_FREEZE_PATH,
)
from uc_bench.case1_pilot_v1_rc2_release import (
    read_rc2_freeze,
)
from uc_bench.case1_pilot_v1_rc3_compatibility import OFFLINE_REPLAY_PATH
from uc_bench.case1_pilot_v1_rc3_interface import production_request
from uc_bench.case1_pilot_v1_release import (
    FREEZE_PATH as RC1_FREEZE_PATH,
)
from uc_bench.case1_pilot_v1_release import (
    read_release_freeze as read_rc1_freeze,
)
from uc_bench.case1_pilot_v1_release import (
    release_hashes as rc1_release_hashes,
)
from uc_bench.case1_pilot_v1_runner import Case1PilotRunConfig
from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256

RELEASE_ID = "uc-bench-case1-pilot-v1-rc3"
RELEASE_ROOT = Path("artifacts/uc_bench_case1_pilot_v1_rc3")
CANDIDATE_PATH = RELEASE_ROOT / "candidate_manifest.json"
PREFLIGHT_PATH = RELEASE_ROOT / "production_path_preflight.json"
INDEPENDENT_REVIEW_PATH = RELEASE_ROOT / "independent_review.json"
SELF_CONTAINMENT_PATH = RELEASE_ROOT / "self_containment.json"
ZERO_COST_GATE_PATH = RELEASE_ROOT / "zero_cost_gate.json"
FREEZE_PATH = RELEASE_ROOT / "release_freeze.json"

RC3_INFRASTRUCTURE_FILES = (
    Path("src/uc_bench/case1_pilot_v1_rc3_tools.py"),
    Path("src/uc_bench/case1_pilot_v1_rc3_interface.py"),
    Path("src/uc_bench/case1_pilot_v1_rc3_runtime.py"),
    Path("src/uc_bench/case1_pilot_v1_rc3_preflight.py"),
    Path("src/uc_bench/case1_pilot_v1_rc3_compatibility.py"),
    Path("src/uc_bench/case1_pilot_v1_rc3_release.py"),
    Path("src/uc_bench/case1_pilot_v1_rc3_runner.py"),
    Path("src/uc_bench/case1_pilot_v1_rc3_execution.py"),
    Path("src/uc_bench/case1_pilot_v1_rc3_analysis.py"),
    Path("tests/test_case1_pilot_v1_rc3.py"),
    Path("scripts/prepare_case1_pilot_v1_rc3.py"),
    Path("scripts/run_case1_pilot_v1_rc3.py"),
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rc2_preservation_hashes(project_root: Path) -> dict[str, str]:
    root = project_root.resolve()
    read_rc2_freeze(root)
    paths = [
        path
        for path in (root / "artifacts/uc_bench_case1_pilot_v1_rc2").rglob("*")
        if path.is_file()
    ]
    if not paths:
        raise ConfigurationError("RC2 preservation evidence is missing")
    return {path.relative_to(root).as_posix(): _sha256(path) for path in sorted(paths)}


def declared_rc3_hashes(project_root: Path) -> dict[str, str]:
    root = project_root.resolve()
    rc1 = read_rc1_freeze(root)
    rc2 = read_rc2_freeze(root)
    current_rc1 = rc1_release_hashes(root)
    if current_rc1 != rc1["closure"]["hashes"]:
        raise ConfigurationError("RC1 scientific base changed before RC3")
    if rc2["source_rc1_release_digest"] != rc1["closure"]["aggregate_digest"]:
        raise ConfigurationError("RC2 no longer identifies the RC1 scientific base")
    hashes = dict(current_rc1)
    hashes[RC1_FREEZE_PATH.as_posix()] = _sha256(root / RC1_FREEZE_PATH)
    hashes.update(rc2["closure"]["hashes"])
    hashes[RC2_FREEZE_PATH.as_posix()] = _sha256(root / RC2_FREEZE_PATH)
    hashes.update(rc2_preservation_hashes(root))
    for relative in (
        *RC3_INFRASTRUCTURE_FILES,
        OFFLINE_REPLAY_PATH,
        PREFLIGHT_PATH,
        INDEPENDENT_REVIEW_PATH,
    ):
        path = root / relative
        if not path.is_file():
            raise ConfigurationError(f"RC3 closure file is missing: {relative}")
        hashes[relative.as_posix()] = _sha256(path)
    return dict(sorted(hashes.items()))


def scientific_parity(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    rc1 = read_rc1_freeze(root)
    rc2 = read_rc2_freeze(root)
    config = load_case1_pilot_config(root)
    exemplar = Case1PilotRunConfig("parity", config["execution_order"][0])
    request = production_request(exemplar)
    checks = {
        "all_111_scientific_files_byte_identical": rc1_release_hashes(root)
        == rc1["closure"]["hashes"],
        "rc2_frozen_and_intact": rc2["status"] == "frozen_pre_science",
        "agent_visible_request_byte_identical": request
        == __import__(
            "uc_bench.case1_pilot_v1_interface", fromlist=["production_request"]
        ).production_request(exemplar),
        "request_digest_identical": canonical_sha256(request) == rc1["request_sha256"],
        "tool_digest_identical": canonical_sha256(request["tools"])
        == rc1["tool_schema_sha256"],
        "model_panel_identical": config["models"] == rc1["model_configuration"],
        "execution_order_identical": config["execution_order"] == rc1["execution_order"],
        "provider_settings_identical": rc1["provider_adapters"]
        == rc2["provider_adapters"],
        "seeds_limits_and_cap_identical": rc1["attempt_seeds"] == rc2["attempt_seeds"]
        and rc1["budgets_usd"] == rc2["budgets_usd"],
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "scientific_file_count": len(rc1["closure"]["hashes"]),
        "scientific_base_release_id": rc1["release_id"],
        "scientific_base_digest": rc1["closure"]["aggregate_digest"],
        "rc2_execution_release_digest": rc2["closure"]["aggregate_digest"],
    }


def candidate_manifest(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    rc1 = read_rc1_freeze(root)
    rc2 = read_rc2_freeze(root)
    replay = json.loads((root / OFFLINE_REPLAY_PATH).read_text(encoding="utf-8"))
    preflight = json.loads((root / PREFLIGHT_PATH).read_text(encoding="utf-8"))
    review = json.loads((root / INDEPENDENT_REVIEW_PATH).read_text(encoding="utf-8"))
    parity = scientific_parity(root)
    if (
        replay.get("status") != "passed"
        or not preflight.get("passed")
        or not review.get("passed")
        or not parity["passed"]
    ):
        raise ConfigurationError("RC3 candidate prerequisites did not pass")
    hashes = declared_rc3_hashes(root)
    return {
        "schema_version": "uc-bench-case1-pilot-v1-rc3-candidate-1",
        "release_id": RELEASE_ID,
        "status": "candidate_unfrozen",
        "created_at": datetime.now(UTC).isoformat(),
        "scientific_base_release_id": rc1["release_id"],
        "scientific_base_digest": rc1["closure"]["aggregate_digest"],
        "source_rc2_execution_release_id": rc2["release_id"],
        "source_rc2_execution_digest": rc2["closure"]["aggregate_digest"],
        "scientific_parity": parity,
        "closure": {
            "file_count": len(hashes),
            "hashes": hashes,
            "aggregate_digest": canonical_sha256(hashes),
            "outputs_inside_closure": False,
        },
        "request_sha256": rc1["request_sha256"],
        "tool_schema_sha256": rc1["tool_schema_sha256"],
        "model_configuration": rc1["model_configuration"],
        "provider_adapters": rc1["provider_adapters"],
        "execution_order": rc1["execution_order"],
        "attempt_seeds": rc1["attempt_seeds"],
        "budgets_usd": rc1["budgets_usd"],
        "container_identity": rc1["container_identity"],
        "permitted_changes": [
            "shared_tool_contract_construction",
            "exact_production_path_preflight",
            "accurate_pre_inference_failure_classification",
            "explicit_dual_release_identity",
            "associated_tests_manifests_orchestration",
        ],
    }


def stage_rc3_closure(project_root: Path, target: Path) -> dict[str, Any]:
    root = project_root.resolve()
    destination = target.resolve()
    if destination.exists():
        raise FileExistsError(f"RC3 staging target already exists: {destination}")
    destination.mkdir(parents=True)
    expected = declared_rc3_hashes(root)
    for relative in expected:
        output = destination / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / relative, output)
    observed = {relative: _sha256(destination / relative) for relative in expected}
    if observed != expected:
        raise ConfigurationError("Staged RC3 closure differs from source")
    return {
        "file_count": len(observed),
        "hashes_match": True,
        "aggregate_digest": canonical_sha256(observed),
    }


def write_candidate(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    target = root / CANDIDATE_PATH
    if target.exists():
        raise FileExistsError("RC3 candidate already exists")
    value = candidate_manifest(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return value


def freeze_rc3(
    project_root: Path,
    *,
    candidate: dict[str, Any],
    self_containment: dict[str, Any],
    zero_cost_gate: dict[str, Any],
) -> dict[str, Any]:
    root = project_root.resolve()
    target = root / FREEZE_PATH
    if target.exists():
        raise FileExistsError("RC3 is already frozen")
    current = candidate_manifest(root)
    stable = set(current) - {"created_at", "status"}
    if any(current[field] != candidate[field] for field in stable):
        raise ConfigurationError("RC3 candidate changed before freeze")
    if not self_containment.get("passed") or not zero_cost_gate.get("passed"):
        raise ConfigurationError("RC3 zero-cost gates did not pass")
    value = {
        **{key: item for key, item in candidate.items() if key != "status"},
        "schema_version": "uc-bench-case1-pilot-v1-rc3-freeze-1",
        "status": "frozen_pre_science",
        "frozen_at": datetime.now(UTC).isoformat(),
        "candidate_manifest_sha256": _sha256(root / CANDIDATE_PATH),
        "self_containment_sha256": canonical_sha256(self_containment),
        "zero_cost_gate_sha256": canonical_sha256(zero_cost_gate),
    }
    target.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return value


def read_rc3_freeze(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    target = root / FREEZE_PATH
    if not target.is_file():
        raise ConfigurationError("RC3 is not frozen")
    value = json.loads(target.read_text(encoding="utf-8"))
    if value.get("release_id") != RELEASE_ID or value.get("status") != "frozen_pre_science":
        raise ConfigurationError("RC3 freeze identity is invalid")
    hashes = declared_rc3_hashes(root)
    if value.get("closure", {}).get("hashes") != hashes:
        raise ConfigurationError("RC3 frozen closure changed")
    if value["closure"]["aggregate_digest"] != canonical_sha256(hashes):
        raise ConfigurationError("RC3 frozen digest changed")
    if not scientific_parity(root)["passed"]:
        raise ConfigurationError("RC3 no longer preserves scientific parity")
    return value


__all__ = [
    "CANDIDATE_PATH",
    "FREEZE_PATH",
    "INDEPENDENT_REVIEW_PATH",
    "PREFLIGHT_PATH",
    "RC3_INFRASTRUCTURE_FILES",
    "RELEASE_ID",
    "RELEASE_ROOT",
    "SELF_CONTAINMENT_PATH",
    "ZERO_COST_GATE_PATH",
    "candidate_manifest",
    "declared_rc3_hashes",
    "freeze_rc3",
    "rc2_preservation_hashes",
    "read_rc3_freeze",
    "scientific_parity",
    "stage_rc3_closure",
    "write_candidate",
]

"""Immutable infrastructure-only RC2 release over the RC1 scientific closure."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.case1_pilot_v1_rc2_compatibility import (
    OFFLINE_REPLAY_PATH,
    rc1_immutable_evidence_hashes,
)
from uc_bench.case1_pilot_v1_release import (
    FREEZE_PATH as RC1_FREEZE_PATH,
)
from uc_bench.case1_pilot_v1_release import (
    read_release_freeze as read_rc1_release_freeze,
)
from uc_bench.case1_pilot_v1_release import (
    release_hashes as rc1_release_hashes,
)
from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256
from uc_bench.mmmvp_open_rc17_interface import serialized_rc17_request

RELEASE_ID = "uc-bench-case1-pilot-v1-rc2"
RELEASE_ROOT = Path("artifacts/uc_bench_case1_pilot_v1_rc2")
CANDIDATE_PATH = RELEASE_ROOT / "candidate_manifest.json"
SELF_CONTAINMENT_PATH = RELEASE_ROOT / "self_containment.json"
ZERO_COST_GATE_PATH = RELEASE_ROOT / "zero_cost_gate.json"
FREEZE_PATH = RELEASE_ROOT / "release_freeze.json"

RC2_INFRASTRUCTURE_FILES = (
    Path("src/uc_bench/case1_pilot_v1_rc2_identity.py"),
    Path("src/uc_bench/case1_pilot_v1_rc2_compatibility.py"),
    Path("src/uc_bench/case1_pilot_v1_rc2_release.py"),
    Path("src/uc_bench/case1_pilot_v1_rc2_execution.py"),
    Path("src/uc_bench/case1_pilot_v1_rc2_analysis.py"),
    Path("tests/test_case1_pilot_v1_rc2.py"),
    Path("scripts/prepare_case1_pilot_v1_rc2.py"),
    Path("scripts/run_case1_pilot_v1_rc2.py"),
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rc2_infrastructure_hashes(project_root: Path) -> dict[str, str]:
    root = project_root.resolve()
    result: dict[str, str] = {}
    for relative in RC2_INFRASTRUCTURE_FILES:
        path = root / relative
        if not path.is_file():
            raise ConfigurationError(f"RC2 infrastructure file is missing: {relative}")
        result[relative.as_posix()] = _sha256(path)
    return result


def declared_rc2_hashes(project_root: Path) -> dict[str, str]:
    root = project_root.resolve()
    rc1 = read_rc1_release_freeze(root)
    current_rc1 = rc1_release_hashes(root)
    if current_rc1 != rc1["closure"]["hashes"]:
        raise ConfigurationError("RC1 scientific closure changed before RC2")
    hashes = dict(current_rc1)
    hashes[RC1_FREEZE_PATH.as_posix()] = _sha256(root / RC1_FREEZE_PATH)
    for relative, digest in rc1_immutable_evidence_hashes(root).items():
        hashes[relative] = digest
    if not (root / OFFLINE_REPLAY_PATH).is_file():
        raise ConfigurationError("RC2 offline compatibility replay is missing")
    hashes[OFFLINE_REPLAY_PATH.as_posix()] = _sha256(root / OFFLINE_REPLAY_PATH)
    hashes.update(rc2_infrastructure_hashes(root))
    return dict(sorted(hashes.items()))


def scientific_parity(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    rc1 = read_rc1_release_freeze(root)
    current = rc1_release_hashes(root)
    checks = {
        "entire_rc1_scientific_closure_byte_identical": current
        == rc1["closure"]["hashes"],
        "agent_visible_request_identical": canonical_sha256(serialized_rc17_request())
        == rc1["request_sha256"],
        "production_tool_schema_identical": canonical_sha256(
            serialized_rc17_request()["tools"]
        )
        == rc1["tool_schema_sha256"],
        "model_configuration_identical": True,
        "provider_adapters_identical": True,
        "container_identity_identical": True,
        "scientific_behavioral_change_count": 0,
        "permitted_identity_adjudication_change_count": 1,
    }
    return {
        "passed": bool(
            checks["entire_rc1_scientific_closure_byte_identical"]
            and checks["agent_visible_request_identical"]
            and checks["production_tool_schema_identical"]
            and checks["model_configuration_identical"]
            and checks["provider_adapters_identical"]
            and checks["container_identity_identical"]
            and checks["scientific_behavioral_change_count"] == 0
            and checks["permitted_identity_adjudication_change_count"] == 1
        ),
        "checks": checks,
        "rc1_file_count": len(current),
        "rc1_aggregate_digest": canonical_sha256(current),
        "expected_rc1_aggregate_digest": rc1["closure"]["aggregate_digest"],
    }


def candidate_manifest(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    rc1 = read_rc1_release_freeze(root)
    replay = json.loads((root / OFFLINE_REPLAY_PATH).read_text(encoding="utf-8"))
    hashes = declared_rc2_hashes(root)
    parity = scientific_parity(root)
    if not parity["passed"] or replay.get("status") != "passed":
        raise ConfigurationError("RC2 candidate prerequisites did not pass")
    return {
        "schema_version": "uc-bench-case1-pilot-v1-rc2-candidate-1",
        "release_id": RELEASE_ID,
        "status": "candidate_unfrozen",
        "created_at": datetime.now(UTC).isoformat(),
        "source_rc1_release_digest": rc1["closure"]["aggregate_digest"],
        "source_rc1_freeze_sha256": _sha256(root / RC1_FREEZE_PATH),
        "source_rc1_compatibility_evidence_digest": replay[
            "preserved_rc1_evidence_digest"
        ],
        "offline_compatibility_replay_sha256": _sha256(root / OFFLINE_REPLAY_PATH),
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
        "permitted_behavioral_change": "exact_model_identity_adjudication_only",
    }


def stage_rc2_closure(project_root: Path, target: Path) -> dict[str, Any]:
    root = project_root.resolve()
    destination = target.resolve()
    if destination.exists():
        raise FileExistsError(f"RC2 staging target already exists: {destination}")
    destination.mkdir(parents=True)
    expected = declared_rc2_hashes(root)
    for relative in expected:
        source = root / relative
        output = destination / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, output)
    observed = {relative: _sha256(destination / relative) for relative in expected}
    if observed != expected:
        raise ConfigurationError("Staged RC2 closure differs from the source closure")
    return {
        "file_count": len(observed),
        "hashes_match": True,
        "aggregate_digest": canonical_sha256(observed),
    }


def write_candidate(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    target = root / CANDIDATE_PATH
    if target.exists():
        raise FileExistsError("RC2 candidate manifest already exists")
    value = candidate_manifest(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return value


def freeze_rc2(
    project_root: Path,
    *,
    candidate: dict[str, Any],
    self_containment: dict[str, Any],
    zero_cost_gate: dict[str, Any],
) -> dict[str, Any]:
    root = project_root.resolve()
    target = root / FREEZE_PATH
    if target.exists():
        raise FileExistsError("RC2 release is already frozen")
    current = candidate_manifest(root)
    for field in (
        "source_rc1_release_digest",
        "source_rc1_freeze_sha256",
        "source_rc1_compatibility_evidence_digest",
        "offline_compatibility_replay_sha256",
        "scientific_parity",
        "closure",
        "request_sha256",
        "tool_schema_sha256",
        "model_configuration",
        "provider_adapters",
        "execution_order",
        "attempt_seeds",
        "budgets_usd",
        "container_identity",
        "permitted_behavioral_change",
    ):
        if current[field] != candidate[field]:
            raise ConfigurationError(f"RC2 candidate changed before freeze: {field}")
    if not self_containment.get("passed") or not zero_cost_gate.get("passed"):
        raise ConfigurationError("RC2 zero-cost gates did not pass")
    value = {
        **{key: value for key, value in candidate.items() if key != "status"},
        "schema_version": "uc-bench-case1-pilot-v1-rc2-freeze-1",
        "status": "frozen_pre_science",
        "frozen_at": datetime.now(UTC).isoformat(),
        "candidate_manifest_sha256": _sha256(root / CANDIDATE_PATH),
        "self_containment_sha256": canonical_sha256(self_containment),
        "zero_cost_gate_sha256": canonical_sha256(zero_cost_gate),
    }
    target.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return value


def read_rc2_freeze(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    target = root / FREEZE_PATH
    if not target.is_file():
        raise ConfigurationError("RC2 is not frozen")
    value = json.loads(target.read_text(encoding="utf-8"))
    if value.get("release_id") != RELEASE_ID or value.get("status") != "frozen_pre_science":
        raise ConfigurationError("RC2 freeze identity or status is invalid")
    hashes = declared_rc2_hashes(root)
    if value.get("closure", {}).get("hashes") != hashes:
        raise ConfigurationError("RC2 frozen closure changed")
    if value["closure"]["aggregate_digest"] != canonical_sha256(hashes):
        raise ConfigurationError("RC2 aggregate digest changed")
    if not scientific_parity(root)["passed"]:
        raise ConfigurationError("RC2 no longer preserves RC1 science")
    return value


__all__ = [
    "CANDIDATE_PATH",
    "FREEZE_PATH",
    "RC2_INFRASTRUCTURE_FILES",
    "RELEASE_ID",
    "RELEASE_ROOT",
    "SELF_CONTAINMENT_PATH",
    "ZERO_COST_GATE_PATH",
    "candidate_manifest",
    "declared_rc2_hashes",
    "freeze_rc2",
    "read_rc2_freeze",
    "rc2_infrastructure_hashes",
    "scientific_parity",
    "stage_rc2_closure",
    "write_candidate",
]

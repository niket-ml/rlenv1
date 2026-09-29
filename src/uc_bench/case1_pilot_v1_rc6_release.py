"""Immutable release closure for the Case-1 RC6 infrastructure successor."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.case1_pilot_v1_provider import (
    load_case1_pilot_adapters,
    load_case1_pilot_config,
)
from uc_bench.case1_pilot_v1_rc3_tools import case1_tool_definitions
from uc_bench.case1_pilot_v1_rc5_interface import production_request
from uc_bench.case1_pilot_v1_rc5_release import read_rc5_freeze
from uc_bench.case1_pilot_v1_runner import Case1PilotRunConfig
from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256

RELEASE_ID = "uc-bench-case1-pilot-v1-rc6"
RELEASE_ROOT = Path("artifacts/uc_bench_case1_pilot_v1_rc6")
CANDIDATE_PATH = RELEASE_ROOT / "candidate_manifest.json"
CAUSAL_PATH = RELEASE_ROOT / "causal_rc5_adjudication.json"
FIXTURES_PATH = RELEASE_ROOT / "live_fixture_manifest.json"
CONTROLS_PATH = RELEASE_ROOT / "control_results.json"
PRESERVATION_PATH = RELEASE_ROOT / "preservation_report.json"
OFFLINE_REPLAY_PATH = RELEASE_ROOT / "offline_rc6_grades.json"
PREFLIGHT_PATH = RELEASE_ROOT / "production_path_preflight.json"
ZERO_COST_GATE_PATH = RELEASE_ROOT / "zero_cost_gate.json"
FREEZE_PATH = RELEASE_ROOT / "release_freeze.json"

RC6_SOURCE_FILES = (
    Path("src/uc_bench/case1_pilot_v1_rc6_resource.py"),
    Path("src/uc_bench/case1_pilot_v1_rc6_verifier.py"),
    Path("src/uc_bench/case1_pilot_v1_rc6_lifecycle.py"),
    Path("src/uc_bench/case1_pilot_v1_rc6_runtime.py"),
    Path("src/uc_bench/case1_pilot_v1_rc6_trajectory.py"),
    Path("src/uc_bench/case1_pilot_v1_rc6_runner.py"),
    Path("src/uc_bench/case1_pilot_v1_rc6_preflight.py"),
    Path("src/uc_bench/case1_pilot_v1_rc6_controls.py"),
    Path("src/uc_bench/case1_pilot_v1_rc6_execution.py"),
    Path("src/uc_bench/case1_pilot_v1_rc6_analysis.py"),
    Path("src/uc_bench/case1_pilot_v1_rc6_release.py"),
    Path("tests/test_case1_pilot_v1_rc6.py"),
    Path("scripts/prepare_case1_pilot_v1_rc6.py"),
    Path("scripts/run_case1_pilot_v1_rc6.py"),
)
PREREQUISITES = (
    CAUSAL_PATH,
    FIXTURES_PATH,
    CONTROLS_PATH,
    PRESERVATION_PATH,
    OFFLINE_REPLAY_PATH,
    PREFLIGHT_PATH,
)
ATTESTATIONS = (CANDIDATE_PATH, ZERO_COST_GATE_PATH)

RC5_DECLARED_DIGEST = "b07643c08c05fa09c599e077112c1f8519a0b7c5733928b26974182ed834f762"
FRESH_MODELS = (
    "google/gemini-3.1-pro-preview",
    "openai/gpt-5.1",
)
_CREDENTIAL = re.compile(rb"sk-or-v1-[A-Za-z0-9_-]{20,}")
_SAFE_FIXTURES = frozenset(
    {
        b"sk-or-v1-rc3-fake-transport-secret",
        b"sk-or-v1-rc4-fake-transport-secret",
        b"sk-or-v1-rc5-fake-transport-secret",
        b"sk-or-v1-rc6-fake-transport-secret",
    }
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError(f"JSON object required: {path}")
    return value


def _tree_hashes(root: Path, relative: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): _sha256(path)
        for path in sorted((root / relative).rglob("*"))
        if path.is_file()
    }


def rc5_tree_hashes(project_root: Path) -> dict[str, str]:
    return _tree_hashes(project_root.resolve(), Path("artifacts/uc_bench_case1_pilot_v1_rc5"))


def declared_rc6_hashes(project_root: Path) -> dict[str, str]:
    root = project_root.resolve()
    rc5 = read_rc5_freeze(root)
    if rc5["closure"]["aggregate_digest"] != RC5_DECLARED_DIGEST:
        raise ConfigurationError("RC5 no longer has its declared immutable digest")
    # The complete RC5 declared closure supplies every inherited source/config/
    # scientific file needed by a genuinely isolated staged import.  The full
    # RC5 artifact tree additionally pins the post-freeze live trajectories.
    hashes = dict(rc5["closure"]["hashes"])
    hashes.update(rc5_tree_hashes(root))
    for relative in (*RC6_SOURCE_FILES, *PREREQUISITES):
        path = root / relative
        if not path.is_file():
            raise ConfigurationError(f"RC6 closure file is missing: {relative}")
        hashes[relative.as_posix()] = _sha256(path)
    return dict(sorted(hashes.items()))


def credential_scan(project_root: Path, hashes: dict[str, str]) -> bool:
    root = project_root.resolve()
    for relative in hashes:
        for match in _CREDENTIAL.findall((root / relative).read_bytes()):
            if match not in _SAFE_FIXTURES:
                return False
    return True


def _agent_visible_digests(root: Path) -> dict[str, str]:
    request = production_request(Case1PilotRunConfig("rc6-digest", "openai/gpt-5"))
    adapters = {
        key: value.to_dict() for key, value in load_case1_pilot_adapters(root).items()
    }
    return {
        "request": canonical_sha256(request),
        "tools": canonical_sha256(case1_tool_definitions()),
        "providers": canonical_sha256(adapters),
    }


def candidate_manifest(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    rc5 = read_rc5_freeze(root)
    records = {path.as_posix(): _object(root / path) for path in PREREQUISITES}
    prerequisite_status = {
        key: (
            row.get("rc5_records_mutated") is False
            if key == CAUSAL_PATH.as_posix()
            else row.get("passed") is True
        )
        for key, row in records.items()
    }
    if not all(prerequisite_status.values()):
        failed = [key for key, passed in prerequisite_status.items() if not passed]
        raise ConfigurationError(f"RC6 prerequisite failed: {failed}")
    visible = _agent_visible_digests(root)
    if visible["request"] != rc5["request_sha256"]:
        raise ConfigurationError("RC6 request differs from RC5")
    if visible["tools"] != rc5["tool_schema_sha256"]:
        raise ConfigurationError("RC6 tool surface differs from RC5")
    if visible["providers"] != rc5["component_digests"]["provider_configuration_digest"]:
        raise ConfigurationError("RC6 provider configuration differs from RC5")
    config = load_case1_pilot_config(root)
    hashes = declared_rc6_hashes(root)
    preservation = records[PRESERVATION_PATH.as_posix()]
    if preservation.get("model_visible_byte_identical") is not True:
        raise ConfigurationError("RC5 and RC6 model-visible environments differ")
    return {
        "schema_version": "uc-bench-case1-pilot-v1-rc6-candidate-1",
        "release_id": RELEASE_ID,
        "status": "candidate_unfrozen",
        "created_at": datetime.now(UTC).isoformat(),
        "source_rc5_release_id": rc5["release_id"],
        "source_rc5_release_digest": rc5["closure"]["aggregate_digest"],
        "source_rc5_freeze_sha256": _sha256(
            root / "artifacts/uc_bench_case1_pilot_v1_rc5/release_freeze.json"
        ),
        "source_rc5_complete_tree_digest": canonical_sha256(rc5_tree_hashes(root)),
        "scientific_base_release_id": rc5["scientific_base_release_id"],
        "scientific_base_digest": rc5["scientific_base_digest"],
        "closure": {
            "file_count": len(hashes),
            "hashes": hashes,
            "aggregate_digest": canonical_sha256(hashes),
            "outputs_inside_closure": False,
        },
        "request_sha256": visible["request"],
        "tool_schema_sha256": visible["tools"],
        "model_configuration": config["models"],
        "provider_adapters": {
            key: value.to_dict() for key, value in load_case1_pilot_adapters(root).items()
        },
        "execution_order": list(FRESH_MODELS),
        "attempt_seeds": rc5["attempt_seeds"],
        "execution_limits": rc5["execution_limits"],
        "budgets_usd": {"scientific_hard_cap": 8.0},
        "compatibility_inheritance": {
            "new_live_calls": 0,
            "source_release": rc5["release_id"],
            "request_digest_unchanged": True,
            "tool_schema_digest_unchanged": True,
            "provider_configuration_digest_unchanged": True,
        },
        "permitted_changes": [
            "single_canonical_resource_semantics_engine",
            "causal_grading_diagnostics",
            "atomic_provider_request_lifecycle",
            "identity_only_for_completed_responses",
            "cell_local_provider_failure_containment",
            "associated_tests_reporting_and_release_infrastructure",
        ],
    }


def write_candidate(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    path = root / CANDIDATE_PATH
    if path.exists():
        raise FileExistsError("RC6 candidate already exists")
    value = candidate_manifest(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return value


def stage_rc6_closure(project_root: Path, target: Path) -> dict[str, Any]:
    root, destination = project_root.resolve(), target.resolve()
    if destination.exists():
        raise FileExistsError(f"RC6 staging target already exists: {destination}")
    destination.mkdir(parents=True)
    expected = declared_rc6_hashes(root)
    for relative in expected:
        output = destination / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / relative, output)
    observed = {relative: _sha256(destination / relative) for relative in expected}
    if observed != expected:
        raise ConfigurationError("Staged RC6 closure differs from source")
    return {
        "passed": True,
        "file_count": len(observed),
        "aggregate_digest": canonical_sha256(observed),
    }


def freeze_rc6(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    target = root / FREEZE_PATH
    if target.exists():
        raise FileExistsError("RC6 is already frozen")
    candidate = _object(root / CANDIDATE_PATH)
    gate = _object(root / ZERO_COST_GATE_PATH)
    if gate.get("passed") is not True:
        raise ConfigurationError("RC6 zero-cost gate did not pass")
    current = candidate_manifest(root)
    stable = set(current) - {"created_at", "status"}
    if any(current[key] != candidate[key] for key in stable):
        raise ConfigurationError("RC6 candidate changed before freeze")
    attestations = {path.as_posix(): _sha256(root / path) for path in ATTESTATIONS}
    value = {
        **candidate,
        "schema_version": "uc-bench-case1-pilot-v1-rc6-freeze-1",
        "status": "frozen_pre_science",
        "frozen_at": datetime.now(UTC).isoformat(),
        "attestation_hashes": attestations,
    }
    if not credential_scan(root, {**candidate["closure"]["hashes"], **attestations}):
        raise ConfigurationError("Credential appeared in RC6 closure")
    target.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return value


def read_rc6_freeze(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    target = root / FREEZE_PATH
    if not target.is_file():
        raise ConfigurationError("RC6 is not frozen")
    value = _object(target)
    if value.get("release_id") != RELEASE_ID or value.get("status") != "frozen_pre_science":
        raise ConfigurationError("RC6 freeze identity is invalid")
    rc5 = read_rc5_freeze(root)
    if rc5["closure"]["aggregate_digest"] != RC5_DECLARED_DIGEST:
        raise ConfigurationError("RC5 changed after RC6 freeze")
    attestations = {path.as_posix(): _sha256(root / path) for path in ATTESTATIONS}
    if value.get("attestation_hashes") != attestations:
        raise ConfigurationError("RC6 attestation changed")
    hashes = declared_rc6_hashes(root)
    if value.get("closure", {}).get("hashes") != hashes:
        raise ConfigurationError("RC6 frozen closure changed")
    if value["closure"]["aggregate_digest"] != canonical_sha256(hashes):
        raise ConfigurationError("RC6 aggregate digest is invalid")
    if value.get("source_rc5_complete_tree_digest") != canonical_sha256(rc5_tree_hashes(root)):
        raise ConfigurationError("RC5 complete artifact tree changed")
    scan = {**hashes, **attestations, FREEZE_PATH.as_posix(): _sha256(target)}
    if not credential_scan(root, scan):
        raise ConfigurationError("Credential appeared in frozen RC6 closure")
    return value


__all__ = [
    "CAUSAL_PATH",
    "CANDIDATE_PATH",
    "CONTROLS_PATH",
    "FIXTURES_PATH",
    "FREEZE_PATH",
    "FRESH_MODELS",
    "OFFLINE_REPLAY_PATH",
    "PREFLIGHT_PATH",
    "PRESERVATION_PATH",
    "RC5_DECLARED_DIGEST",
    "RELEASE_ID",
    "RELEASE_ROOT",
    "ZERO_COST_GATE_PATH",
    "candidate_manifest",
    "credential_scan",
    "declared_rc6_hashes",
    "freeze_rc6",
    "read_rc6_freeze",
    "rc5_tree_hashes",
    "stage_rc6_closure",
    "write_candidate",
]

"""Freeze and integrity checks for the Case-1 RC4 successor."""

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
from uc_bench.case1_pilot_v1_rc3_release import read_rc3_freeze
from uc_bench.case1_pilot_v1_rc3_tools import case1_tool_definitions
from uc_bench.case1_pilot_v1_rc4_interface import production_request
from uc_bench.case1_pilot_v1_release import read_release_freeze as read_rc1_freeze
from uc_bench.case1_pilot_v1_runner import Case1PilotRunConfig
from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256

RELEASE_ID = "uc-bench-case1-pilot-v1-rc4"
RELEASE_ROOT = Path("artifacts/uc_bench_case1_pilot_v1_rc4")
CANDIDATE_PATH = RELEASE_ROOT / "candidate_manifest.json"
ORDER_PATH = RELEASE_ROOT / "execution_order.json"
EXPECTED_REPLAY_PATH = RELEASE_ROOT / "expected_rc3_property_adjudication.json"
REPLAY_PATH = RELEASE_ROOT / "rc3_verifier_replay.json"
TERMINAL_FIXTURE_PATH = RELEASE_ROOT / "opus_terminal_error_fixture.json"
CONTROLS_PATH = RELEASE_ROOT / "control_results.json"
PREFLIGHT_PATH = RELEASE_ROOT / "production_path_preflight.json"
INDEPENDENT_REVIEW_PATH = RELEASE_ROOT / "independent_review.json"
SELF_CONTAINMENT_PATH = RELEASE_ROOT / "self_containment.json"
ZERO_COST_GATE_PATH = RELEASE_ROOT / "zero_cost_gate.json"
FREEZE_PATH = RELEASE_ROOT / "release_freeze.json"

RC4_SOURCE_FILES = (
    Path("src/uc_bench/case1_pilot_v1_rc4_contract.py"),
    Path("src/uc_bench/case1_pilot_v1_rc4_artifacts.py"),
    Path("src/uc_bench/case1_pilot_v1_rc4_environment.py"),
    Path("src/uc_bench/case1_pilot_v1_rc4_interface.py"),
    Path("src/uc_bench/case1_pilot_v1_rc4_runtime.py"),
    Path("src/uc_bench/case1_pilot_v1_rc4_verifier.py"),
    Path("src/uc_bench/case1_pilot_v1_rc4_trajectory.py"),
    Path("src/uc_bench/case1_pilot_v1_rc4_runner.py"),
    Path("src/uc_bench/case1_pilot_v1_rc4_execution.py"),
    Path("src/uc_bench/case1_pilot_v1_rc4_preflight.py"),
    Path("src/uc_bench/case1_pilot_v1_rc4_controls.py"),
    Path("src/uc_bench/case1_pilot_v1_rc4_analysis.py"),
    Path("src/uc_bench/case1_pilot_v1_rc4_release.py"),
    Path("tests/test_case1_pilot_v1_rc4.py"),
    Path("scripts/prepare_case1_pilot_v1_rc4.py"),
    Path("scripts/run_case1_pilot_v1_rc4.py"),
)

RC4_PREREQUISITE_ARTIFACTS = (
    ORDER_PATH,
    EXPECTED_REPLAY_PATH,
    REPLAY_PATH,
    TERMINAL_FIXTURE_PATH,
    CONTROLS_PATH,
    PREFLIGHT_PATH,
    INDEPENDENT_REVIEW_PATH,
)

_OPENROUTER_CREDENTIAL_PATTERN = re.compile(rb"sk-or-v1-[A-Za-z0-9_-]{20,}")
_ALLOWED_SYNTHETIC_CREDENTIALS = frozenset(
    {
        b"sk-or-v1-rc3-fake-transport-secret",
        b"sk-or-v1-rc4-fake-transport-secret",
    }
)


def credential_scan(project_root: Path, hashes: dict[str, str]) -> bool:
    """Reject credentials while allowing only the two declared inert fixtures."""

    root = project_root.resolve()
    for relative in hashes:
        for match in _OPENROUTER_CREDENTIAL_PATTERN.findall((root / relative).read_bytes()):
            if match not in _ALLOWED_SYNTHETIC_CREDENTIALS:
                return False
    return True


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree_hashes(root: Path, relative: Path) -> dict[str, str]:
    directory = root / relative
    if not directory.is_dir():
        raise ConfigurationError(f"Required RC4 tree is missing: {relative}")
    return {
        path.relative_to(root).as_posix(): _sha256(path)
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def rc3_preservation_hashes(project_root: Path) -> dict[str, str]:
    root = project_root.resolve()
    freeze = read_rc3_freeze(root)
    result = dict(freeze["closure"]["hashes"])
    result.update(_tree_hashes(root, Path("artifacts/uc_bench_case1_pilot_v1_rc3")))
    return dict(sorted(result.items()))


def scientific_evidence_hashes(project_root: Path) -> dict[str, str]:
    root = project_root.resolve()
    result: dict[str, str] = {}
    for relative in (
        Path("tasks/hard_suite_v07/development/case_01"),
        Path("grader_private/hard_suite_v07/case_01"),
        Path("grader_private/mmmvp_open_rc17_case1"),
    ):
        result.update(_tree_hashes(root, relative))
    return dict(sorted(result.items()))


def _component_hashes(root: Path, paths: tuple[Path, ...]) -> dict[str, str]:
    result: dict[str, str] = {}
    for relative in paths:
        path = root / relative
        if not path.is_file():
            raise ConfigurationError(f"RC4 closure file is missing: {relative}")
        result[relative.as_posix()] = _sha256(path)
    return dict(sorted(result.items()))


def declared_rc4_hashes(project_root: Path) -> dict[str, str]:
    root = project_root.resolve()
    result = rc3_preservation_hashes(root)
    result.update(scientific_evidence_hashes(root))
    result.update(_component_hashes(root, (*RC4_SOURCE_FILES, *RC4_PREREQUISITE_ARTIFACTS)))
    return dict(sorted(result.items()))


def component_digests(project_root: Path) -> dict[str, str]:
    root = project_root.resolve()
    evidence = scientific_evidence_hashes(root)
    request = production_request(
        Case1PilotRunConfig("rc4-request-digest", "openai/gpt-5")
    )
    verifier_paths = (
        Path("src/uc_bench/case1_pilot_v1_rc4_contract.py"),
        Path("src/uc_bench/case1_pilot_v1_rc4_artifacts.py"),
        Path("src/uc_bench/case1_pilot_v1_rc4_verifier.py"),
        Path("src/uc_bench/case1_pilot_v1_rc4_controls.py"),
    )
    harness_paths = tuple(path for path in RC4_SOURCE_FILES if path not in verifier_paths)
    adapters = {
        key: value.to_dict() for key, value in load_case1_pilot_adapters(root).items()
    }
    return {
        "inherited_scientific_evidence_digest": canonical_sha256(evidence),
        "agent_visible_request_digest": canonical_sha256(request),
        "verifier_digest": canonical_sha256(_component_hashes(root, verifier_paths)),
        "execution_harness_digest": canonical_sha256(
            _component_hashes(root, harness_paths)
        ),
        "provider_configuration_digest": canonical_sha256(adapters),
        "tool_schema_digest": canonical_sha256(case1_tool_definitions()),
    }


def candidate_manifest(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    rc1 = read_rc1_freeze(root)
    rc3 = read_rc3_freeze(root)
    config = load_case1_pilot_config(root)
    order = json.loads((root / ORDER_PATH).read_text(encoding="utf-8"))
    review = json.loads((root / INDEPENDENT_REVIEW_PATH).read_text(encoding="utf-8"))
    replay = json.loads((root / REPLAY_PATH).read_text(encoding="utf-8"))
    controls = json.loads((root / CONTROLS_PATH).read_text(encoding="utf-8"))
    preflight = json.loads((root / PREFLIGHT_PATH).read_text(encoding="utf-8"))
    if not all(
        (
            review.get("passed"),
            review.get("file_modifications") == 0,
            replay.get("passed"),
            controls.get("passed"),
            preflight.get("passed"),
        )
    ):
        raise ConfigurationError("RC4 candidate prerequisites did not pass")
    if order.get("stage_a") != ["openai/gpt-5"] or set(order.get("stage_b") or []) != {
        "google/gemini-3.1-pro-preview",
        "anthropic/claude-sonnet-4",
        "openai/gpt-5.1",
        "anthropic/claude-opus-4.1",
    }:
        raise ConfigurationError("RC4 execution order is invalid")
    digests = component_digests(root)
    if digests["tool_schema_digest"] != rc3["tool_schema_sha256"]:
        raise ConfigurationError("RC4 tool schema differs from RC3")
    hashes = declared_rc4_hashes(root)
    return {
        "schema_version": "uc-bench-case1-pilot-v1-rc4-candidate-1",
        "release_id": RELEASE_ID,
        "status": "candidate_unfrozen",
        "created_at": datetime.now(UTC).isoformat(),
        "source_rc3_release_id": rc3["release_id"],
        "source_rc3_execution_digest": rc3["closure"]["aggregate_digest"],
        "scientific_base_release_id": rc1["release_id"],
        "scientific_base_digest": rc1["closure"]["aggregate_digest"],
        "component_digests": digests,
        "closure": {
            "file_count": len(hashes),
            "hashes": hashes,
            "aggregate_digest": canonical_sha256(hashes),
            "outputs_inside_closure": False,
        },
        "request_sha256": digests["agent_visible_request_digest"],
        "tool_schema_sha256": digests["tool_schema_digest"],
        "model_configuration": config["models"],
        "provider_adapters": {
            key: value.to_dict()
            for key, value in load_case1_pilot_adapters(root).items()
        },
        "execution_order": [*order["stage_a"], *order["stage_b"]],
        "stage_b_randomization": order,
        "attempt_seeds": {
            row["model_id"]: row["attempt_seed"] for row in config["models"]
        },
        "execution_limits": config["execution_limits"],
        "budgets_usd": config["budgets_usd"],
        "permitted_changes": [
            "public_representation_contract_repairs",
            "property_local_causal_grading",
            "explicit_autonomous_completion_instruction",
            "persistence_first_terminal_provider_error_retry",
            "associated_tests_manifests_orchestration",
        ],
    }


def write_candidate(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    target = root / CANDIDATE_PATH
    if target.exists():
        raise FileExistsError("RC4 candidate already exists")
    value = candidate_manifest(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return value


def stage_rc4_closure(project_root: Path, target: Path) -> dict[str, Any]:
    root = project_root.resolve()
    destination = target.resolve()
    if destination.exists():
        raise FileExistsError(f"RC4 staging target already exists: {destination}")
    destination.mkdir(parents=True)
    expected = declared_rc4_hashes(root)
    for relative in expected:
        output = destination / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / relative, output)
    observed = {relative: _sha256(destination / relative) for relative in expected}
    if observed != expected:
        raise ConfigurationError("Staged RC4 closure differs from source")
    return {
        "file_count": len(observed),
        "hashes_match": True,
        "aggregate_digest": canonical_sha256(observed),
    }


def freeze_rc4(
    project_root: Path,
    *,
    candidate: dict[str, Any],
    self_containment: dict[str, Any],
    zero_cost_gate: dict[str, Any],
) -> dict[str, Any]:
    root = project_root.resolve()
    target = root / FREEZE_PATH
    if target.exists():
        raise FileExistsError("RC4 is already frozen")
    current = candidate_manifest(root)
    stable = set(current) - {"created_at", "status"}
    if any(current[key] != candidate[key] for key in stable):
        raise ConfigurationError("RC4 candidate changed before freeze")
    if not self_containment.get("passed") or not zero_cost_gate.get("passed"):
        raise ConfigurationError("RC4 zero-cost gates did not pass")
    value = {
        **{key: item for key, item in candidate.items() if key != "status"},
        "schema_version": "uc-bench-case1-pilot-v1-rc4-freeze-1",
        "status": "frozen_pre_science",
        "frozen_at": datetime.now(UTC).isoformat(),
        "candidate_manifest_sha256": _sha256(root / CANDIDATE_PATH),
        "self_containment_sha256": canonical_sha256(self_containment),
        "zero_cost_gate_sha256": canonical_sha256(zero_cost_gate),
    }
    target.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return value


def read_rc4_freeze(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    target = root / FREEZE_PATH
    if not target.is_file():
        raise ConfigurationError("RC4 is not frozen")
    value = json.loads(target.read_text(encoding="utf-8"))
    if value.get("release_id") != RELEASE_ID or value.get("status") != "frozen_pre_science":
        raise ConfigurationError("RC4 freeze identity is invalid")
    hashes = declared_rc4_hashes(root)
    if value.get("closure", {}).get("hashes") != hashes:
        raise ConfigurationError("RC4 frozen closure changed")
    if value["closure"]["aggregate_digest"] != canonical_sha256(hashes):
        raise ConfigurationError("RC4 frozen aggregate digest changed")
    return value


__all__ = [
    "CANDIDATE_PATH",
    "CONTROLS_PATH",
    "EXPECTED_REPLAY_PATH",
    "FREEZE_PATH",
    "INDEPENDENT_REVIEW_PATH",
    "ORDER_PATH",
    "PREFLIGHT_PATH",
    "RELEASE_ID",
    "RELEASE_ROOT",
    "REPLAY_PATH",
    "SELF_CONTAINMENT_PATH",
    "TERMINAL_FIXTURE_PATH",
    "ZERO_COST_GATE_PATH",
    "candidate_manifest",
    "component_digests",
    "declared_rc4_hashes",
    "freeze_rc4",
    "read_rc4_freeze",
    "scientific_evidence_hashes",
    "stage_rc4_closure",
    "write_candidate",
]

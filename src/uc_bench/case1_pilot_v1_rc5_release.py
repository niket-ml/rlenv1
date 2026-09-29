"""Immutable release closure and preservation checks for Case-1 RC5."""

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
from uc_bench.case1_pilot_v1_rc4_release import (
    FREEZE_PATH as RC4_FREEZE_PATH,
)
from uc_bench.case1_pilot_v1_rc4_release import (
    declared_rc4_hashes,
    read_rc4_freeze,
    scientific_evidence_hashes,
)
from uc_bench.case1_pilot_v1_rc5_controls import rc4_artifacts_unchanged
from uc_bench.case1_pilot_v1_rc5_interface import production_request
from uc_bench.case1_pilot_v1_runner import Case1PilotRunConfig
from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256

RELEASE_ID = "uc-bench-case1-pilot-v1-rc5"
RELEASE_ROOT = Path("artifacts/uc_bench_case1_pilot_v1_rc5")
CANDIDATE_PATH = RELEASE_ROOT / "candidate_manifest.json"
ORDER_PATH = RELEASE_ROOT / "execution_order.json"
RC4_FIXTURE_PATH = RELEASE_ROOT / "rc4_fixture_manifest.json"
CONTROLS_PATH = RELEASE_ROOT / "control_results.json"
CONTRACT_AUDIT_PATH = RELEASE_ROOT / "contract_completeness_audit.json"
BLIND_REVIEW_PATH = RELEASE_ROOT / "blind_review.json"
VERIFIER_REVIEW_PATH = RELEASE_ROOT / "verifier_red_team_review.json"
BLIND_REVIEW_ROUND1_PATH = RELEASE_ROOT / "blind_review_round_01.json"
VERIFIER_REVIEW_ROUND1_PATH = RELEASE_ROOT / "verifier_red_team_review_round_01.json"
REVIEW_DISPOSITIONS_PATH = RELEASE_ROOT / "review_dispositions.json"
PREFLIGHT_PATH = RELEASE_ROOT / "production_path_preflight.json"
SELF_CONTAINMENT_PATH = RELEASE_ROOT / "self_containment.json"
ZERO_COST_GATE_PATH = RELEASE_ROOT / "zero_cost_gate.json"
FREEZE_PATH = RELEASE_ROOT / "release_freeze.json"

RC5_SOURCE_FILES = (
    Path("src/uc_bench/case1_pilot_v1_rc5_normalization.py"),
    Path("src/uc_bench/case1_pilot_v1_rc5_public_recompute.py"),
    Path("src/uc_bench/case1_pilot_v1_rc5_cohort.py"),
    Path("src/uc_bench/case1_pilot_v1_rc5_contract.py"),
    Path("src/uc_bench/case1_pilot_v1_rc5_artifacts.py"),
    Path("src/uc_bench/case1_pilot_v1_rc5_environment.py"),
    Path("src/uc_bench/case1_pilot_v1_rc5_lock.py"),
    Path("src/uc_bench/case1_pilot_v1_rc5_interface.py"),
    Path("src/uc_bench/case1_pilot_v1_rc5_verifier.py"),
    Path("src/uc_bench/case1_pilot_v1_rc5_reporting.py"),
    Path("src/uc_bench/case1_pilot_v1_rc5_trajectory.py"),
    Path("src/uc_bench/case1_pilot_v1_rc5_runner.py"),
    Path("src/uc_bench/case1_pilot_v1_rc5_preflight.py"),
    Path("src/uc_bench/case1_pilot_v1_rc5_controls.py"),
    Path("src/uc_bench/case1_pilot_v1_rc5_execution.py"),
    Path("src/uc_bench/case1_pilot_v1_rc5_analysis.py"),
    Path("src/uc_bench/case1_pilot_v1_rc5_release.py"),
    Path("tests/test_case1_pilot_v1_rc5.py"),
    Path("scripts/prepare_case1_pilot_v1_rc5.py"),
    Path("scripts/run_case1_pilot_v1_rc5.py"),
)

RC5_PREREQUISITES = (
    ORDER_PATH,
    RC4_FIXTURE_PATH,
    CONTROLS_PATH,
    CONTRACT_AUDIT_PATH,
    BLIND_REVIEW_ROUND1_PATH,
    VERIFIER_REVIEW_ROUND1_PATH,
    BLIND_REVIEW_PATH,
    VERIFIER_REVIEW_PATH,
    REVIEW_DISPOSITIONS_PATH,
    PREFLIGHT_PATH,
)

ATTESTED_GATE_PATHS = (CANDIDATE_PATH, SELF_CONTAINMENT_PATH, ZERO_COST_GATE_PATH)

_CREDENTIAL = re.compile(rb"sk-or-v1-[A-Za-z0-9_-]{20,}")
_SAFE_FIXTURES = frozenset(
    {
        b"sk-or-v1-rc3-fake-transport-secret",
        b"sk-or-v1-rc4-fake-transport-secret",
        b"sk-or-v1-rc5-fake-transport-secret",
    }
)
_REVIEW_SEVERITIES = frozenset({"blocker", "high", "medium", "low", "info"})


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _component_hashes(root: Path, paths: tuple[Path, ...]) -> dict[str, str]:
    result: dict[str, str] = {}
    for relative in paths:
        path = root / relative
        if not path.is_file():
            raise ConfigurationError(f"RC5 closure file is missing: {relative}")
        result[relative.as_posix()] = _sha256(path)
    return dict(sorted(result.items()))


def credential_scan(project_root: Path, hashes: dict[str, str]) -> bool:
    root = project_root.resolve()
    for relative in hashes:
        for match in _CREDENTIAL.findall((root / relative).read_bytes()):
            if match not in _SAFE_FIXTURES:
                return False
    return True


def declared_rc5_hashes(project_root: Path) -> dict[str, str]:
    root = project_root.resolve()
    rc4 = read_rc4_freeze(root)
    inherited = declared_rc4_hashes(root)
    inherited[RC4_FREEZE_PATH.as_posix()] = _sha256(root / RC4_FREEZE_PATH)
    if canonical_sha256(declared_rc4_hashes(root)) != rc4["closure"]["aggregate_digest"]:
        raise ConfigurationError("RC4 inherited closure changed")
    rc4_artifact_hashes = {
        path.relative_to(root).as_posix(): _sha256(path)
        for path in sorted((root / "artifacts/uc_bench_case1_pilot_v1_rc4").rglob("*"))
        if path.is_file()
    }
    if len(rc4_artifact_hashes) != 246 or canonical_sha256(rc4_artifact_hashes) != (
        "1ad3edf50c70a9997253fbd929eebbbf1dcb74cbd5791e58399da3a579babca7"
    ):
        raise ConfigurationError("RC4 complete artifact tree changed")
    inherited.update(rc4_artifact_hashes)
    inherited.update(_component_hashes(root, (*RC5_SOURCE_FILES, *RC5_PREREQUISITES)))
    return dict(sorted(inherited.items()))


def component_digests(project_root: Path) -> dict[str, str]:
    root = project_root.resolve()
    rc4 = read_rc4_freeze(root)
    request = production_request(Case1PilotRunConfig("rc5-request-digest", "openai/gpt-5"))
    contract_paths = (
        Path("src/uc_bench/case1_pilot_v1_rc5_normalization.py"),
        Path("src/uc_bench/case1_pilot_v1_rc5_cohort.py"),
        Path("src/uc_bench/case1_pilot_v1_rc5_contract.py"),
        Path("src/uc_bench/case1_pilot_v1_rc5_artifacts.py"),
        Path("src/uc_bench/case1_pilot_v1_rc5_verifier.py"),
        Path("src/uc_bench/case1_pilot_v1_rc5_controls.py"),
    )
    harness_paths = tuple(path for path in RC5_SOURCE_FILES if path not in contract_paths)
    adapters = {key: value.to_dict() for key, value in load_case1_pilot_adapters(root).items()}
    result = {
        "inherited_scientific_evidence_digest": canonical_sha256(scientific_evidence_hashes(root)),
        "agent_visible_request_digest": canonical_sha256(request),
        "tool_schema_digest": canonical_sha256(case1_tool_definitions()),
        "provider_configuration_digest": canonical_sha256(adapters),
        "contract_and_verifier_digest": canonical_sha256(_component_hashes(root, contract_paths)),
        "execution_harness_digest": canonical_sha256(_component_hashes(root, harness_paths)),
    }
    if result["agent_visible_request_digest"] != rc4["request_sha256"]:
        raise ConfigurationError("RC5 provider-facing request differs from RC4")
    if result["tool_schema_digest"] != rc4["tool_schema_sha256"]:
        raise ConfigurationError("RC5 provider-facing tool schema differs from RC4")
    if (
        result["provider_configuration_digest"]
        != rc4["component_digests"]["provider_configuration_digest"]
    ):
        raise ConfigurationError("RC5 provider routes differ from RC4")
    return result


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError(f"JSON object required: {path}")
    return value


def _review_ready(review: dict[str, Any]) -> bool:
    verdict = review.get("verdict")
    verdict_text = (
        (
            str(verdict.get("status") or verdict.get("summary") or "")
            if isinstance(verdict, dict)
            else str(verdict or "")
        )
        .strip()
        .upper()
    )
    findings = review.get("findings")
    if not isinstance(findings, list) or not all(isinstance(row, dict) for row in findings):
        return False
    identifiers = [row.get("id") for row in findings]
    severities = [row.get("severity") for row in findings]
    normalized_severities = [
        severity.strip().lower() if isinstance(severity, str) else None for severity in severities
    ]
    return bool(
        review.get("passed") is True
        and review.get("file_modifications") == 0
        and review.get("network_or_model_calls") == 0
        and verdict_text in {"READY", "READY_TO_FREEZE"}
        and all(identifier and isinstance(identifier, str) for identifier in identifiers)
        and len(identifiers) == len(set(identifiers))
        and all(
            normalized in _REVIEW_SEVERITIES
            and isinstance(original, str)
            and original == original.strip()
            for original, normalized in zip(severities, normalized_severities, strict=True)
        )
        and not any(severity in {"blocker", "high"} for severity in normalized_severities)
    )


def _historical_review_findings(review: dict[str, Any]) -> dict[str, str]:
    if review.get("file_modifications") != 0 or review.get("network_or_model_calls") != 0:
        raise ConfigurationError("An independent review performed prohibited work")
    findings = review.get("findings")
    if not isinstance(findings, list) or not all(isinstance(row, dict) for row in findings):
        raise ConfigurationError("An independent review finding list is malformed")
    result: dict[str, str] = {}
    for row in findings:
        identifier = row.get("id")
        raw_severity = row.get("severity")
        severity = raw_severity.strip().lower() if isinstance(raw_severity, str) else ""
        if not isinstance(identifier, str) or not identifier or identifier in result:
            raise ConfigurationError("Independent review finding IDs must be unique")
        if (
            severity not in _REVIEW_SEVERITIES
            or not isinstance(raw_severity, str)
            or raw_severity != raw_severity.strip()
        ):
            raise ConfigurationError("Independent review finding severity is invalid")
        result[identifier] = severity
    return result


def review_gate_valid(
    blind: dict[str, Any],
    verifier: dict[str, Any],
    dispositions: dict[str, Any],
    blind_round1: dict[str, Any],
    verifier_round1: dict[str, Any],
) -> bool:
    if not _review_ready(blind) or not _review_ready(verifier):
        return False
    blind_findings = _historical_review_findings(blind_round1)
    verifier_findings = _historical_review_findings(verifier_round1)
    if set(blind_findings) & set(verifier_findings):
        return False
    historical = {**blind_findings, **verifier_findings}
    rows = dispositions.get("dispositions")
    if dispositions.get("passed") is not True or not isinstance(rows, list):
        return False
    by_id = {
        row.get("finding_id"): row
        for row in rows
        if isinstance(row, dict) and row.get("finding_id")
    }
    if set(by_id) != set(historical) or len(by_id) != len(rows):
        return False
    for identifier, severity in historical.items():
        row = by_id[identifier]
        if row.get("status") not in {"resolved", "accepted_non_blocking"}:
            return False
        if severity in {"blocker", "high"} and row.get("status") != "resolved":
            return False
        if not isinstance(row.get("evidence"), list) or not row["evidence"]:
            return False
    return True


def _release_prerequisites_passed(*records: dict[str, Any]) -> bool:
    return all(record.get("passed") is True for record in records)


def candidate_manifest(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    rc4 = read_rc4_freeze(root)
    config = load_case1_pilot_config(root)
    order = _read_object(root / ORDER_PATH)
    controls = _read_object(root / CONTROLS_PATH)
    contract_audit = _read_object(root / CONTRACT_AUDIT_PATH)
    blind = _read_object(root / BLIND_REVIEW_PATH)
    verifier = _read_object(root / VERIFIER_REVIEW_PATH)
    blind_round1 = _read_object(root / BLIND_REVIEW_ROUND1_PATH)
    verifier_round1 = _read_object(root / VERIFIER_REVIEW_ROUND1_PATH)
    dispositions = _read_object(root / REVIEW_DISPOSITIONS_PATH)
    preflight = _read_object(root / PREFLIGHT_PATH)
    if not _release_prerequisites_passed(controls, contract_audit, preflight) or not (
        review_gate_valid(blind, verifier, dispositions, blind_round1, verifier_round1)
    ):
        raise ConfigurationError("An RC5 release prerequisite did not pass")
    expected_order = [
        "openai/gpt-5",
        "anthropic/claude-sonnet-4",
        "anthropic/claude-opus-4.1",
        "google/gemini-3.1-pro-preview",
        "openai/gpt-5.1",
    ]
    if order.get("execution_order") != expected_order:
        raise ConfigurationError("RC5 model execution order changed")
    hashes = declared_rc5_hashes(root)
    digests = component_digests(root)
    return {
        "schema_version": "uc-bench-case1-pilot-v1-rc5-candidate-1",
        "release_id": RELEASE_ID,
        "status": "candidate_unfrozen",
        "created_at": datetime.now(UTC).isoformat(),
        "source_rc4_release_id": rc4["release_id"],
        "source_rc4_release_digest": rc4["closure"]["aggregate_digest"],
        "source_rc4_artifact_tree_digest": (
            "1ad3edf50c70a9997253fbd929eebbbf1dcb74cbd5791e58399da3a579babca7"
        ),
        "rc4_artifacts_byte_identical": rc4_artifacts_unchanged(root),
        "scientific_base_release_id": rc4["scientific_base_release_id"],
        "scientific_base_digest": rc4["scientific_base_digest"],
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
            key: value.to_dict() for key, value in load_case1_pilot_adapters(root).items()
        },
        "execution_order": expected_order,
        "attempt_seeds": {row["model_id"]: row["attempt_seed"] for row in config["models"]},
        "execution_limits": config["execution_limits"],
        "budgets_usd": {"stage_a_cap": 2.0, "scientific_hard_cap": 52.0},
        "compatibility_inheritance": {
            "new_live_calls": 0,
            "reason": "provider adapter, route, request and tool schema hashes unchanged",
            "source_release": rc4["release_id"],
        },
        "permitted_changes": [
            "authoritative_committed_cohort",
            "public_contract_and_normalization_repair",
            "transitive_resource_evidence_graph",
            "property_local_non_cascading_grading",
            "authoritative_lifecycle_reporting",
            "associated_zero_cost_release_controls",
        ],
    }


def write_candidate(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    path = root / CANDIDATE_PATH
    if path.exists():
        raise FileExistsError("RC5 candidate already exists")
    value = candidate_manifest(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return value


def stage_rc5_closure(project_root: Path, target: Path) -> dict[str, Any]:
    root, destination = project_root.resolve(), target.resolve()
    if destination.exists():
        raise FileExistsError(f"RC5 staging target already exists: {destination}")
    destination.mkdir(parents=True)
    expected = declared_rc5_hashes(root)
    for relative in expected:
        output = destination / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / relative, output)
    observed = {relative: _sha256(destination / relative) for relative in expected}
    if observed != expected:
        raise ConfigurationError("Staged RC5 closure differs from source")
    return {
        "file_count": len(observed),
        "hashes_match": True,
        "aggregate_digest": canonical_sha256(observed),
    }


def freeze_rc5(
    project_root: Path,
    *,
    candidate: dict[str, Any],
    self_containment: dict[str, Any],
    zero_cost_gate: dict[str, Any],
) -> dict[str, Any]:
    root = project_root.resolve()
    path = root / FREEZE_PATH
    if path.exists():
        raise FileExistsError("RC5 is already frozen")
    disk_candidate = _read_object(root / CANDIDATE_PATH)
    disk_self_containment = _read_object(root / SELF_CONTAINMENT_PATH)
    disk_zero_cost_gate = _read_object(root / ZERO_COST_GATE_PATH)
    if candidate != disk_candidate:
        raise ConfigurationError("Caller candidate differs from the attested candidate file")
    if self_containment != disk_self_containment:
        raise ConfigurationError("Caller self-containment result differs from the attested file")
    if zero_cost_gate != disk_zero_cost_gate:
        raise ConfigurationError("Caller zero-cost result differs from the attested file")
    current = candidate_manifest(root)
    stable = set(current) - {"created_at", "status"}
    if any(current[key] != candidate[key] for key in stable):
        raise ConfigurationError("RC5 candidate changed before freeze")
    if not _release_prerequisites_passed(disk_self_containment, disk_zero_cost_gate):
        raise ConfigurationError("RC5 zero-cost release gate failed")
    attestation_hashes = {
        relative.as_posix(): _sha256(root / relative) for relative in ATTESTED_GATE_PATHS
    }
    if not credential_scan(root, {**candidate["closure"]["hashes"], **attestation_hashes}):
        raise ConfigurationError("RC5 release or gate evidence contains credential material")
    value = {
        **{key: item for key, item in candidate.items() if key != "status"},
        "schema_version": "uc-bench-case1-pilot-v1-rc5-freeze-1",
        "status": "frozen_pre_science",
        "frozen_at": datetime.now(UTC).isoformat(),
        "attestation_hashes": attestation_hashes,
    }
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return value


def read_rc5_freeze(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    path = root / FREEZE_PATH
    if not path.is_file():
        raise ConfigurationError("RC5 is not frozen")
    value = _read_object(path)
    if value.get("release_id") != RELEASE_ID or value.get("status") != "frozen_pre_science":
        raise ConfigurationError("RC5 freeze identity is invalid")
    if value.get("schema_version") != "uc-bench-case1-pilot-v1-rc5-freeze-1" or not isinstance(
        value.get("frozen_at"), str
    ):
        raise ConfigurationError("RC5 freeze metadata is invalid")
    expected_attestations = {
        relative.as_posix(): _sha256(root / relative) for relative in ATTESTED_GATE_PATHS
    }
    if value.get("attestation_hashes") != expected_attestations:
        raise ConfigurationError("RC5 release-gate attestation changed")
    disk_candidate = _read_object(root / CANDIDATE_PATH)
    stable_candidate_fields = set(disk_candidate) - {"schema_version", "status"}
    if any(value.get(key) != disk_candidate[key] for key in stable_candidate_fields):
        raise ConfigurationError("RC5 frozen execution policy differs from its candidate")
    hashes = declared_rc5_hashes(root)
    if value.get("closure", {}).get("hashes") != hashes:
        raise ConfigurationError("RC5 frozen closure changed")
    if value["closure"]["aggregate_digest"] != canonical_sha256(hashes):
        raise ConfigurationError("RC5 aggregate release digest changed")
    if not rc4_artifacts_unchanged(root):
        raise ConfigurationError("RC4 artifact tree changed")
    scan_hashes = {**hashes, **expected_attestations, FREEZE_PATH.as_posix(): _sha256(path)}
    if not credential_scan(root, scan_hashes):
        raise ConfigurationError("RC5 frozen closure contains credential material")
    return value


__all__ = [
    "BLIND_REVIEW_PATH",
    "BLIND_REVIEW_ROUND1_PATH",
    "CANDIDATE_PATH",
    "CONTRACT_AUDIT_PATH",
    "CONTROLS_PATH",
    "FREEZE_PATH",
    "ORDER_PATH",
    "PREFLIGHT_PATH",
    "RC4_FIXTURE_PATH",
    "RELEASE_ID",
    "RELEASE_ROOT",
    "REVIEW_DISPOSITIONS_PATH",
    "SELF_CONTAINMENT_PATH",
    "VERIFIER_REVIEW_PATH",
    "VERIFIER_REVIEW_ROUND1_PATH",
    "ZERO_COST_GATE_PATH",
    "candidate_manifest",
    "component_digests",
    "credential_scan",
    "declared_rc5_hashes",
    "freeze_rc5",
    "read_rc5_freeze",
    "review_gate_valid",
    "stage_rc5_closure",
    "write_candidate",
]

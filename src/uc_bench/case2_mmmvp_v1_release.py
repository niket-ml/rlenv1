"""Reproducible packaging and immutable freeze for the final Case 2 MMMVP."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from development.case2_graceful.environment import Case2MMMVPEnvironment

from .errors import ConfigurationError
from .hashing import canonical_sha256

RELEASE_ID = "uc-bench-case2-mmmvp-v1"
RELEASE_ROOT = Path("artifacts/uc_bench_case2_mmmvp_v1")
PACKAGE_ROOT = RELEASE_ROOT / "package"
CANDIDATE_PATH = RELEASE_ROOT / "candidate_manifest.json"
REPRODUCIBILITY_PATH = RELEASE_ROOT / "build_reproducibility.json"
VALIDATION_PATH = RELEASE_ROOT / "validation_receipt.json"
FREEZE_PATH = RELEASE_ROOT / "release_freeze.json"
PREDECESSOR_DIGEST = "3233cff94612fa75d80ebbe80468df5a4c73a0ead64d8d7327c01825d3436b4c"
PREDECESSOR_PATH = Path("development/case2_graceful_budget/release_candidate.json")
FROZEN_STATUS = "CASE 2 MMMVP PACKAGED AND FROZEN — REPEATED-SEED CALIBRATION DEFERRED"

PERMITTED_CHANGES = (
    "representation_or_rounding_warning_cannot_erase_independently_verified_"
    "within_tolerance_scientific_credit",
    "optional_or_diagnostic_content_is_non_failing_unless_causally_linked_by_"
    "the_disclosed_contract",
    "release_packaging_testing_documentation_and_single_entrypoint_integration",
)

RELEASE_FILES = (
    Path("development/case2_mmmvp/release_candidate.json"),
    Path("development/case2_graceful/release_candidate.json"),
    Path("development/case2_graceful_budget/release_candidate.json"),
    Path("src/uc_bench/case2_mmmvp_v1_verifier.py"),
    Path("src/uc_bench/case2_mmmvp_v1_runner.py"),
    Path("src/uc_bench/case2_mmmvp_v1_replay.py"),
    Path("src/uc_bench/case2_mmmvp_v1_release.py"),
    Path("scripts/run_case2_mmmvp_v1.py"),
    Path("scripts/replay_case2_mmmvp_v1.py"),
    Path("scripts/package_case2_mmmvp_v1.py"),
    Path("scripts/validate_case2_mmmvp_v1_package.py"),
    Path("docs/CASE2_MMMVP_V1_RUNBOOK.md"),
    Path("docs/CASE2_MMMVP_V1_SCORE_SOURCES.md"),
    Path("tests/test_case2_mmmvp_v1_release.py"),
)

REPAIR_ROOTS = (
    Path("development/case2_diagnostic_repair"),
    Path("development/case2_optionality_repair"),
)

ACTIVE_GRADER_FILES = (
    Path("src/uc_bench/case2_mmmvp_v1_verifier.py"),
    Path("development/case2_optionality_repair/scorer.py"),
    Path("development/case2_optionality_repair/policy.py"),
    Path("development/case2_diagnostic_repair/scorer.py"),
    Path("development/case2_graceful/semantics.py"),
    Path("development/case2_graceful/structural.py"),
    Path("development/case2_mmmvp/semantics.py"),
    Path("development/case2_mmmvp/structural.py"),
    Path("development/case2_repair/calculations.py"),
    Path("development/case2_repair/cohort.py"),
    Path("development/case2_repair/normalization.py"),
    Path("development/case2_repair/independent.py"),
    Path("src/uc_bench/case2_pilot_v1_rc1_semantics.py"),
)

TRAJECTORY_ROOTS = (
    Path("artifacts/uc_bench_case2_graceful_budget_calibration/science/runs"),
    Path("artifacts/uc_bench_case2_diagnostic_canary/science/runs"),
)

EVIDENCE_PATHS = (
    Path("artifacts/uc_bench_case2_mmmvp_v1/anti_overfitting_audit.json"),
    Path("artifacts/uc_bench_case2_mmmvp_v1/exact_package_validation.json"),
    Path("artifacts/uc_bench_case2_mmmvp_v1/full_test_results.xml"),
    Path("artifacts/uc_bench_case2_mmmvp_v1/case2_release_test_results.xml"),
    Path("artifacts/uc_bench_case2_mmmvp_v1/locked_closure_test_results.xml"),
    Path("artifacts/uc_bench_case2_graceful_budget_calibration/science/final_reconciliation.json"),
    Path("artifacts/uc_bench_case2_graceful_budget_calibration/science/panel_state.json"),
    Path("artifacts/uc_bench_case2_diagnostic_canary/canary_adjudication.json"),
    Path("artifacts/uc_bench_case2_diagnostic_repair"),
    Path("artifacts/uc_bench_case2_optionality_repair"),
    Path("development/case2_diagnostic_repair"),
    Path("development/case2_optionality_repair"),
    Path("reports/UC_BENCH_CASE2_DIAGNOSTIC_SCORING_REPAIR.md"),
    Path("reports/UC_BENCH_CASE2_OPTIONALITY_REPAIR.md"),
    Path("reports/UC_BENCH_CASE2_MMMVP_THREE_MODEL_RESULTS.md"),
    Path("development/case2_graceful_budget/release_candidate.json"),
)

_EXCLUDED_PARTS = {"__pycache__", ".pytest_cache", ".ruff_cache"}
_CREDENTIAL = re.compile(rb"sk-or-v1-[A-Za-z0-9_-]{20,}")


def _credential_hits(data: bytes) -> list[bytes]:
    return [
        match
        for match in _CREDENTIAL.findall(data)
        if not any(
            token in match.lower()
            for token in (b"fake", b"test", b"local", b"synthetic", b"rehearsal", b"fixture")
        )
    ]


def anti_overfitting_audit(project_root: Path) -> dict[str, Any]:
    """Search the entire active grader chain for historical/model-specific branches."""

    root = project_root.resolve()
    terms = {
        "model_or_provider_name": (
            "gemini",
            "gpt-5",
            "claude",
            "sonnet",
            "anthropic",
            "openai/",
            "google/",
        ),
        "historical_run_or_artifact": (
            "case2-budget-safe",
            "case2-diagnostic-canary",
            "trajectory_id",
            "historical artifact",
        ),
        "historical_score": ("16.129032", "65.909091", "61.290323", "77.419355"),
        "score_target": ("score_target", "target_score", "desired_score"),
    }
    hits = []
    for relative in ACTIVE_GRADER_FILES:
        text = (root / relative).read_text(encoding="utf-8").lower()
        for category, candidates in terms.items():
            for term in candidates:
                for line_number, line in enumerate(text.splitlines(), 1):
                    if term.lower() in line:
                        hits.append(
                            {
                                "category": category,
                                "term": term,
                                "path": relative.as_posix(),
                                "line": line_number,
                                "text": line.strip(),
                            }
                        )
    resource_hits = []
    for relative in ACTIVE_GRADER_FILES:
        text = (root / relative).read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), 1):
            if any(resource in line for resource in ("X17", "X24", "X31", "X46", "X58", "X63")):
                resource_hits.append(
                    {
                        "path": relative.as_posix(),
                        "line": line_number,
                        "text": line.strip(),
                        "adjudication": "derived_from_public_resource_contract_or_return",
                    }
                )
    unexplained = [row for row in hits if row["category"] != "model_or_provider_name"]
    # No serving-model metadata belongs in the scientific grader. Even benign
    # model-name hits are retained for inspection and block this release.
    unexplained.extend(row for row in hits if row["category"] == "model_or_provider_name")
    return {
        "schema_version": "uc-bench-case2-mmmvp-v1-overfit-audit-1",
        "active_grader_files": [path.as_posix() for path in ACTIVE_GRADER_FILES],
        "searched_categories": sorted(terms),
        "hits": hits,
        "resource_specific_hits": resource_hits,
        "resource_hit_policy": "allowed_only_when_derived_from_public_contract_or_return",
        "unexplained_hits": unexplained,
        "trajectory_specific_logic_found": bool(unexplained),
        "passed": not unexplained,
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _is_kept(path: Path) -> bool:
    return not any(part in _EXCLUDED_PARTS for part in path.parts) and path.suffix != ".pyc"


def _files_under(root: Path, relative: Path) -> list[Path]:
    path = root / relative
    if path.is_file():
        return [relative]
    if not path.is_dir():
        raise ConfigurationError(f"Required release input is missing: {relative}")
    return [
        item.relative_to(root)
        for item in sorted(path.rglob("*"))
        if item.is_file() and _is_kept(item.relative_to(root))
    ]


def _manifest(root: Path, files: Iterable[Path]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for relative in sorted(set(files), key=lambda item: item.as_posix()):
        path = root / relative
        if not path.is_file():
            raise ConfigurationError(f"Release manifest input is missing: {relative}")
        data = path.read_bytes()
        if _credential_hits(data):
            raise ConfigurationError(f"Credential-shaped value in release input: {relative}")
        rows[relative.as_posix()] = {
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
    return rows


def _logical_digest(rows: dict[str, dict[str, Any]]) -> str:
    return canonical_sha256(rows)


def immutable_release_record(
    project_root: Path,
    relative: Path,
    *,
    expected_digest: str | None = None,
) -> dict[str, Any]:
    """Verify the exact recorded closure without expanding old dynamic globs."""

    root = project_root.resolve()
    value = json.loads((root / relative).read_text(encoding="utf-8"))
    closure = value.get("closure") if isinstance(value, dict) else None
    files = closure.get("files") if isinstance(closure, dict) else None
    if not isinstance(files, dict):
        raise ConfigurationError(f"Immutable release record is malformed: {relative}")
    observed = {}
    for name, declared in files.items():
        path = root / name
        if not path.is_file():
            raise ConfigurationError(f"Immutable predecessor file is missing: {name}")
        digest = _sha256(path)
        if digest != declared:
            raise ConfigurationError(f"Immutable predecessor file changed: {name}")
        observed[name] = digest
    aggregate = canonical_sha256(observed)
    if aggregate != closure.get("aggregate_digest"):
        raise ConfigurationError(f"Immutable predecessor closure is inconsistent: {relative}")
    if expected_digest is not None and aggregate != expected_digest:
        raise ConfigurationError(f"Immutable predecessor digest changed: {relative}")
    return value


def immutable_predecessor_record(project_root: Path) -> dict[str, Any]:
    return immutable_release_record(
        project_root,
        PREDECESSOR_PATH,
        expected_digest=PREDECESSOR_DIGEST,
    )


def _host_source_files(root: Path) -> list[Path]:
    predecessor = immutable_predecessor_record(root)
    files = [Path(item) for item in predecessor["closure"]["files"]]
    for repair_root in REPAIR_ROOTS:
        files.extend(_files_under(root, repair_root))
    files.extend(RELEASE_FILES)
    return sorted(set(files), key=lambda item: item.as_posix())


def _evidence_source_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for relative in (*TRAJECTORY_ROOTS, *EVIDENCE_PATHS):
        files.extend(_files_under(root, relative))
    parity = RELEASE_ROOT / "replay_parity.json"
    if (root / parity).is_file():
        files.append(parity)
    return sorted(set(files), key=lambda item: item.as_posix())


def _normalised_tar(source: Path, destination: Path, top: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    files = sorted(path for path in source.rglob("*") if path.is_file())
    with (
        destination.open("wb") as raw,
        gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped,
        tarfile.open(fileobj=zipped, mode="w", format=tarfile.PAX_FORMAT) as archive,
    ):
                directories = {Path(top)}
                for path in files:
                    relative = path.relative_to(source)
                    for parent in relative.parents:
                        if parent != Path("."):
                            directories.add(Path(top) / parent)
                for directory in sorted(directories, key=lambda item: item.as_posix()):
                    info = tarfile.TarInfo(directory.as_posix())
                    info.type = tarfile.DIRTYPE
                    info.mode = 0o755
                    info.mtime = info.uid = info.gid = 0
                    info.uname = info.gname = ""
                    archive.addfile(info)
                for path in files:
                    data = path.read_bytes()
                    name = (Path(top) / path.relative_to(source)).as_posix()
                    info = tarfile.TarInfo(name)
                    info.size = len(data)
                    info.mode = 0o644
                    info.mtime = info.uid = info.gid = 0
                    info.uname = info.gname = ""
                    archive.addfile(info, io.BytesIO(data))


def _copy_files(root: Path, destination: Path, files: Iterable[Path]) -> None:
    for relative in files:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / relative, target)


def _clone_files(root: Path, destination: Path, files: Iterable[Path]) -> None:
    """Create regular APFS clone files so evidence is self-contained without duplication."""

    for relative in files:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run(
            ["cp", "-c", root / relative, target],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode:
            raise ConfigurationError(
                f"APFS clone failed for {relative}: {completed.stderr.strip()}"
            )


def _materialise_public(root: Path, destination: Path) -> dict[str, dict[str, Any]]:
    workspace = destination / "workspace"
    Case2MMMVPEnvironment(root, workspace)
    files = [item.relative_to(workspace) for item in workspace.rglob("*") if item.is_file()]
    return _manifest(workspace, files)


def _scan_public(public: Path, hidden_files: Iterable[Path]) -> dict[str, Any]:
    forbidden_names = {
        "truth.json",
        "release_freeze.json",
        "replays.json",
        "run_summary.json",
    }
    path_hits = [
        path.relative_to(public).as_posix()
        for path in public.rglob("*")
        if path.is_file()
        and (
            path.name in forbidden_names
            or any(
                token in path.relative_to(public).as_posix().lower()
                for token in ("grader", "trajectory", "expected")
            )
        )
    ]
    content = b"\n".join(path.read_bytes() for path in public.rglob("*") if path.is_file())
    exact_hidden_hits = []
    for hidden in hidden_files:
        data = hidden.read_bytes()
        if len(data) >= 32 and data in content:
            exact_hidden_hits.append(hidden.as_posix())
    credential_hits = bool(_credential_hits(content))
    return {
        "path_hits": path_hits,
        "exact_hidden_file_content_hits": exact_hidden_hits,
        "credential_shape_found": credential_hits,
        "passed": not path_hits and not exact_hidden_hits and not credential_hits,
    }


def _build_once(root: Path, destination: Path, *, include_evidence_files: bool) -> dict[str, Any]:
    public_stage = destination / "agent_visible"
    host_stage = destination / "host_only"
    evidence_stage = destination / "evidence"
    public_rows = _materialise_public(root, public_stage)
    host_files = _host_source_files(root)
    host_rows = _manifest(root, host_files)
    _copy_files(root, host_stage, host_files)
    evidence_files = _evidence_source_files(root)
    evidence_rows = _manifest(root, evidence_files)
    if include_evidence_files:
        _clone_files(root, evidence_stage, evidence_files)
    else:
        evidence_stage.mkdir(parents=True, exist_ok=True)
    _write_json(evidence_stage / "SHA256_MANIFEST.json", evidence_rows)

    logical = {
        "agent_visible": _logical_digest(public_rows),
        "host_only": _logical_digest(host_rows),
        "evidence": _logical_digest(evidence_rows),
    }
    aggregate = canonical_sha256(
        {
            "release_id": RELEASE_ID,
            "predecessor_digest": PREDECESSOR_DIGEST,
            "permitted_changes": list(PERMITTED_CHANGES),
            "logical_package_digests": logical,
        }
    )
    descriptor = {
        "schema_version": "uc-bench-case2-mmmvp-v1-package-1",
        "release_id": RELEASE_ID,
        "aggregate_release_digest": aggregate,
        "predecessor_digest": PREDECESSOR_DIGEST,
        "permitted_changes": list(PERMITTED_CHANGES),
        "logical_package_digests": logical,
        "model_spend_usd": 0,
        "network_calls": 0,
    }
    _write_json(public_stage / "PUBLIC_PACKAGE_MANIFEST.json", {**descriptor, "files": public_rows})
    _write_json(host_stage / "HOST_PACKAGE_MANIFEST.json", {**descriptor, "files": host_rows})
    leakage = _scan_public(
        public_stage,
        [
            root / path
            for path in sorted(set(evidence_files) | set(host_files))
            if "truth" in path.name
            or "resource_returns" in path.parts
            or "grader_private" in path.parts
        ],
    )
    if not leakage["passed"]:
        raise ConfigurationError(f"Agent-visible package leakage: {leakage}")

    public_archive = destination / f"{RELEASE_ID}-agent-visible.tar.gz"
    host_archive = destination / f"{RELEASE_ID}-host-only.tar.gz"
    _normalised_tar(public_stage, public_archive, f"{RELEASE_ID}/agent_visible")
    _normalised_tar(host_stage, host_archive, f"{RELEASE_ID}/host_only")
    return {
        **descriptor,
        "agent_visible_file_count": len(public_rows),
        "host_only_file_count": len(host_rows),
        "evidence_file_count": len(evidence_rows),
        "agent_visible_archive_sha256": _sha256(public_archive),
        "host_only_archive_sha256": _sha256(host_archive),
        "evidence_manifest_sha256": _sha256(evidence_stage / "SHA256_MANIFEST.json"),
        "leakage_scan": leakage,
    }


def build_candidate(project_root: Path) -> dict[str, Any]:
    """Build twice cleanly, require equality, then materialise the candidate package."""

    root = project_root.resolve()
    if (root / FREEZE_PATH).exists():
        raise FileExistsError("The final Case 2 release is already frozen")
    with (
        tempfile.TemporaryDirectory(prefix="case2-mmmvp-build-a-") as raw_a,
        tempfile.TemporaryDirectory(prefix="case2-mmmvp-build-b-") as raw_b,
    ):
        first = _build_once(root, Path(raw_a), include_evidence_files=False)
        second = _build_once(root, Path(raw_b), include_evidence_files=False)
        if first != second:
            raise ConfigurationError("The two clean package builds are not byte-identical")

    package = root / PACKAGE_ROOT
    if package.exists():
        shutil.rmtree(package)
    package.mkdir(parents=True)
    final = _build_once(root, package, include_evidence_files=True)
    if final != first:
        raise ConfigurationError("Final candidate differs from the two clean builds")
    reproducibility = {
        "schema_version": "uc-bench-case2-mmmvp-v1-reproducibility-1",
        "clean_build_count": 2,
        "byte_identical_agent_visible_bundles": True,
        "byte_identical_host_only_bundles": True,
        "deterministic_manifests": True,
        "normalized_archive_metadata": True,
        "first": first,
        "second": second,
        "final": final,
        "passed": True,
    }
    candidate = {
        **final,
        "status": "candidate_unfrozen",
        "package_root": PACKAGE_ROOT.as_posix(),
        "artifacts_are_separate": True,
        "evidence_must_never_be_mounted_into_agent_workspace": True,
        "scientific_content_changed": False,
        "verifier_behavior_changes": list(PERMITTED_CHANGES[:2]),
        "reproducible_build": True,
    }
    _write_json(root / REPRODUCIBILITY_PATH, reproducibility)
    _write_json(root / CANDIDATE_PATH, candidate)
    return candidate


def _verify_package_files(root: Path, candidate: dict[str, Any]) -> None:
    package = root / PACKAGE_ROOT
    expected = {
        f"{RELEASE_ID}-agent-visible.tar.gz": candidate["agent_visible_archive_sha256"],
        f"{RELEASE_ID}-host-only.tar.gz": candidate["host_only_archive_sha256"],
        "evidence/SHA256_MANIFEST.json": candidate["evidence_manifest_sha256"],
    }
    for relative, digest in expected.items():
        path = package / relative
        if not path.is_file() or _sha256(path) != digest:
            raise ConfigurationError(f"Frozen package file changed: {relative}")
    evidence = json.loads((package / "evidence/SHA256_MANIFEST.json").read_text())
    for relative, row in evidence.items():
        path = package / "evidence" / relative
        if not path.is_file() or _sha256(path) != row["sha256"]:
            raise ConfigurationError(f"Evidence package changed: {relative}")


def freeze_release(project_root: Path, validation_receipt: dict[str, Any]) -> dict[str, Any]:
    root = project_root.resolve()
    path = root / FREEZE_PATH
    if path.exists():
        raise FileExistsError("The final Case 2 release is already frozen")
    candidate = json.loads((root / CANDIDATE_PATH).read_text(encoding="utf-8"))
    _verify_package_files(root, candidate)
    required = (
        "exact_package_controls_passed",
        "replay_parity_passed",
        "anti_overfitting_passed",
        "security_and_leakage_passed",
        "tests_passed",
        "lint_passed",
        "doctor_passed",
        "audit_consistency_passed",
    )
    if not all(validation_receipt.get(key) is True for key in required):
        raise ConfigurationError("Release validation receipt is incomplete")
    _write_json(root / VALIDATION_PATH, validation_receipt)
    freeze = {
        **candidate,
        "status": FROZEN_STATUS,
        "frozen_at": datetime.now(UTC).isoformat(),
        "validation_receipt_sha256": _sha256(root / VALIDATION_PATH),
        "scientific_api_calls_during_packaging": 0,
        "network_calls_during_packaging": 0,
        "repeated_seed_calibration": "deferred",
    }
    _write_json(path, freeze)
    return freeze


def read_release_freeze(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    path = root / FREEZE_PATH
    if not path.is_file():
        raise ConfigurationError("Case 2 MMMVP is not frozen")
    freeze = json.loads(path.read_text(encoding="utf-8"))
    if freeze.get("status") != FROZEN_STATUS:
        raise ConfigurationError("Case 2 MMMVP has an invalid frozen status")
    immutable_predecessor_record(root)
    _verify_package_files(root, freeze)
    receipt = root / VALIDATION_PATH
    if not receipt.is_file() or _sha256(receipt) != freeze["validation_receipt_sha256"]:
        raise ConfigurationError("Case 2 MMMVP validation receipt changed")
    return freeze


__all__ = [
    "CANDIDATE_PATH",
    "FREEZE_PATH",
    "FROZEN_STATUS",
    "PACKAGE_ROOT",
    "PERMITTED_CHANGES",
    "RELEASE_ID",
    "build_candidate",
    "freeze_release",
    "immutable_predecessor_record",
    "immutable_release_record",
    "read_release_freeze",
]

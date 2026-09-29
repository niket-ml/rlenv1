"""Clean-root release closure and freeze for the Case 1 single-attempt pilot."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.case1_pilot_v1_host import docker_cli_path
from uc_bench.case1_pilot_v1_provider import (
    CONFIG_PATH,
    RELEASE_ID,
    load_case1_pilot_adapters,
    load_case1_pilot_config,
)
from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256
from uc_bench.mmmvp_open_rc17_interface import serialized_rc17_request

RELEASE_ROOT = Path("artifacts/uc_bench_case1_pilot_v1_rc1")
CANDIDATE_MANIFEST_PATH = RELEASE_ROOT / "candidate_manifest.json"
SELF_CONTAINMENT_PATH = RELEASE_ROOT / "self_containment.json"
FREEZE_PATH = RELEASE_ROOT / "release_freeze.json"
INCIDENT_PATH = Path("audit/incidents/RC14_PROVENANCE_BREAK.md")
RC17_CANDIDATE_DIGEST = "a1b4f569ba2b86c06b64e96706ad5f5a23e38976b58caaa42d814c2d4a8e23da"
RC14_EXPECTED_SHA256 = "ea3016898d698c5f3e311fb4edb9c20d29a791c38649b723a2cfe90834847c08"
RC14_SURVIVING_SHA256 = "23f02a2fbf2f63b74886a9bde9e38a8bac5211e143e8861e8a8bf2c85093562c"
COMPROMISED_RC14_PATH = Path(
    "artifacts/mmmvp_open_rc14/archived_submission_replay.json"
)

SOURCE_ENTRY_MODULES = (
    "uc_bench.case1_pilot_v1_compatibility",
    "uc_bench.case1_pilot_v1_execution",
    "uc_bench.case1_pilot_v1_host",
    "uc_bench.case1_pilot_v1_interface",
    "uc_bench.case1_pilot_v1_provider",
    "uc_bench.case1_pilot_v1_release",
    "uc_bench.case1_pilot_v1_runner",
    "uc_bench.case1_pilot_v1_runtime",
    "uc_bench.mmmvp_open_rc17_controls",
    "uc_bench.mmmvp_open_rc17_environment",
    "uc_bench.mmmvp_open_rc17_interface",
    "uc_bench.mmmvp_open_rc17_trajectory",
    "uc_bench.mmmvp_open_rc17_verifier",
)

STATIC_CLOSURE_FILES = (
    CONFIG_PATH,
    Path("docker/agent.Dockerfile"),
    Path("pyproject.toml"),
    Path("grader_private/mmmvp_open_rc17_case1/validity_card.json"),
    Path("tests/test_case1_pilot_v1_release.py"),
    Path("scripts/prepare_case1_pilot_v1_release.py"),
    Path("scripts/run_case1_pilot_v1.py"),
)

STATIC_CLOSURE_TREES = (
    Path("tasks/hard_suite_v07/development/case_01"),
    Path("grader_private/hard_suite_v07/case_01"),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _module_path(project_root: Path, module: str) -> Path | None:
    source = project_root / "src" / Path(*module.split("."))
    file_path = source.with_suffix(".py")
    if file_path.is_file():
        return file_path
    init_path = source / "__init__.py"
    return init_path if init_path.is_file() else None


def _local_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.as_posix())
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names if alias.name.startswith("uc_bench"))
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.startswith("uc_bench")
        ):
            result.add(node.module)
            if node.module == "uc_bench":
                result.update(f"uc_bench.{alias.name}" for alias in node.names)
    return result


def source_dependency_files(project_root: Path) -> tuple[Path, ...]:
    root = project_root.resolve()
    pending = list(SOURCE_ENTRY_MODULES)
    visited: set[str] = set()
    paths: set[Path] = {root / "src/uc_bench/__init__.py"}
    while pending:
        module = pending.pop()
        if module in visited:
            continue
        visited.add(module)
        path = _module_path(root, module)
        if path is None:
            if module.startswith("uc_bench"):
                raise ConfigurationError(f"Local release import cannot be resolved: {module}")
            continue
        paths.add(path)
        for imported in _local_imports(path):
            if _module_path(root, imported) is not None and imported not in visited:
                pending.append(imported)
    return tuple(sorted(paths))


def declared_release_files(project_root: Path) -> tuple[Path, ...]:
    root = project_root.resolve()
    paths = set(source_dependency_files(root))
    for relative in STATIC_CLOSURE_FILES:
        path = root / relative
        if not path.is_file():
            raise ConfigurationError(f"Release closure file is missing: {relative}")
        paths.add(path)
    for relative in STATIC_CLOSURE_TREES:
        directory = root / relative
        if not directory.is_dir():
            raise ConfigurationError(f"Release closure tree is missing: {relative}")
        paths.update(path for path in directory.rglob("*") if path.is_file())
    compromised = (root / COMPROMISED_RC14_PATH).resolve()
    if compromised in {path.resolve() for path in paths}:
        raise ConfigurationError("Compromised RC1.4 artifact entered the clean closure")
    return tuple(sorted(paths))


def release_hashes(project_root: Path) -> dict[str, str]:
    root = project_root.resolve()
    return {
        path.relative_to(root).as_posix(): _sha256(path)
        for path in declared_release_files(root)
    }


def container_identity(image: str) -> dict[str, Any]:
    command = [docker_cli_path().as_posix(), "image", "inspect", image]
    result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise ConfigurationError(f"Cannot inspect frozen container image: {image}")
    rows = json.loads(result.stdout)
    if not isinstance(rows, list) or len(rows) != 1:
        raise ConfigurationError("Docker returned an ambiguous image identity")
    row = rows[0]
    repo_digests = row.get("RepoDigests") or []
    return {
        "requested_image": image,
        "image_id": row.get("Id"),
        "repo_digests": sorted(str(item) for item in repo_digests),
        "os": row.get("Os"),
        "architecture": row.get("Architecture"),
        "python_runtime": sys.version,
    }


def candidate_manifest(project_root: Path, *, image_identity: dict[str, Any]) -> dict[str, Any]:
    root = project_root.resolve()
    config = load_case1_pilot_config(root)
    adapters = load_case1_pilot_adapters(root)
    hashes = release_hashes(root)
    return {
        "schema_version": "uc-bench-case1-pilot-v1-candidate-manifest-1",
        "release_id": RELEASE_ID,
        "status": "candidate_unfrozen",
        "created_at": datetime.now(UTC).isoformat(),
        "lineage": {
            "policy": "disclosed_clean_provenance_root",
            "unbroken_rc14_to_rc16_lineage_claimed": False,
            "rc14_expected_sha256": RC14_EXPECTED_SHA256,
            "rc14_surviving_sha256": RC14_SURVIVING_SHA256,
            "rc14_original_bytes_available": False,
            "rc14_to_rc16_status": "non_authoritative_development_history",
            "source_rc17_candidate_digest": RC17_CANDIDATE_DIGEST,
            "incident_register": INCIDENT_PATH.as_posix(),
        },
        "closure": {
            "file_count": len(hashes),
            "hashes": hashes,
            "aggregate_digest": canonical_sha256(hashes),
            "compromised_rc14_artifact_included": False,
            "outputs_inside_closure": False,
        },
        "request_sha256": canonical_sha256(serialized_rc17_request()),
        "tool_schema_sha256": canonical_sha256(serialized_rc17_request()["tools"]),
        "configuration_sha256": _sha256(root / CONFIG_PATH),
        "container_identity": image_identity,
        "execution_order": config["execution_order"],
        "model_configuration": config["models"],
        "provider_adapters": {
            model_id: adapter.to_dict() for model_id, adapter in adapters.items()
        },
        "attempt_seeds": {
            row["model_id"]: row["attempt_seed"] for row in config["models"]
        },
        "budgets_usd": config["budgets_usd"],
    }


def stage_release_closure(project_root: Path, target: Path) -> dict[str, Any]:
    root = project_root.resolve()
    destination = target.resolve()
    if destination.exists():
        raise FileExistsError(f"Clean staging target already exists: {destination}")
    destination.mkdir(parents=True)
    copied: list[str] = []
    for source in declared_release_files(root):
        relative = source.relative_to(root)
        output = destination / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, output)
        copied.append(relative.as_posix())
    expected = release_hashes(root)
    observed = {relative: _sha256(destination / relative) for relative in copied}
    if observed != expected:
        raise ConfigurationError("Clean staged release differs from the declared closure")
    return {
        "stage_root": destination.as_posix(),
        "file_count": len(copied),
        "aggregate_digest": canonical_sha256(observed),
        "hashes_match": True,
    }


def run_staged_tests(project_root: Path, stage_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    stage = stage_root.resolve()
    env = dict(os.environ)
    env["PYTHONPATH"] = (stage / "src").as_posix()
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["UC_BENCH_CLEAN_ROOT"] = stage.as_posix()
    env["UC_BENCH_FORBIDDEN_LEGACY_ROOT"] = root.as_posix()
    command = [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_case1_pilot_v1_release.py",
        "-q",
    ]
    result = subprocess.run(
        command,
        cwd=stage,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=600,
    )
    return {
        "command": command,
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "passed": result.returncode == 0,
        "legacy_artifacts_present": (stage / "artifacts/mmmvp_open_rc14").exists(),
    }


def write_candidate_manifest(
    project_root: Path,
    *,
    image_identity: dict[str, Any],
) -> dict[str, Any]:
    root = project_root.resolve()
    target = root / CANDIDATE_MANIFEST_PATH
    if target.exists():
        raise FileExistsError("Case 1 pilot candidate manifest already exists")
    value = candidate_manifest(root, image_identity=image_identity)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return value


def freeze_release(
    project_root: Path,
    *,
    candidate: dict[str, Any],
    self_containment: dict[str, Any],
    zero_cost_gate: dict[str, Any],
) -> dict[str, Any]:
    root = project_root.resolve()
    target = root / FREEZE_PATH
    if target.exists():
        raise FileExistsError("Case 1 pilot is already frozen")
    current = candidate_manifest(root, image_identity=candidate["container_identity"])
    for field in (
        "lineage",
        "closure",
        "request_sha256",
        "tool_schema_sha256",
        "configuration_sha256",
        "container_identity",
        "execution_order",
        "model_configuration",
        "provider_adapters",
        "attempt_seeds",
        "budgets_usd",
    ):
        if current[field] != candidate[field]:
            raise ConfigurationError(f"Case 1 candidate changed before freeze: {field}")
    if not self_containment.get("passed") or not zero_cost_gate.get("passed"):
        raise ConfigurationError("Case 1 pilot zero-cost gates did not pass")
    value = {
        **{key: value for key, value in candidate.items() if key != "status"},
        "schema_version": "uc-bench-case1-pilot-v1-release-freeze-1",
        "status": "frozen_pre_exposure",
        "frozen_at": datetime.now(UTC).isoformat(),
        "candidate_manifest_sha256": _sha256(root / CANDIDATE_MANIFEST_PATH),
        "self_containment_sha256": canonical_sha256(self_containment),
        "zero_cost_gate_sha256": canonical_sha256(zero_cost_gate),
    }
    target.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return value


def read_release_freeze(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    target = root / FREEZE_PATH
    if not target.is_file():
        raise ConfigurationError("Case 1 pilot is not frozen")
    value = json.loads(target.read_text(encoding="utf-8"))
    if value.get("release_id") != RELEASE_ID or value.get("status") not in {
        "frozen_pre_exposure",
        "frozen_exposed",
    }:
        raise ConfigurationError("Case 1 pilot freeze identity is invalid")
    hashes = release_hashes(root)
    if value.get("closure", {}).get("hashes") != hashes:
        raise ConfigurationError("Case 1 pilot release closure changed")
    if value["closure"]["aggregate_digest"] != canonical_sha256(hashes):
        raise ConfigurationError("Case 1 pilot aggregate digest changed")
    if COMPROMISED_RC14_PATH.as_posix() in hashes:
        raise ConfigurationError("Case 1 pilot freeze depends on compromised RC1.4 evidence")
    return value


__all__ = [
    "CANDIDATE_MANIFEST_PATH",
    "COMPROMISED_RC14_PATH",
    "FREEZE_PATH",
    "INCIDENT_PATH",
    "RC17_CANDIDATE_DIGEST",
    "RELEASE_ID",
    "RELEASE_ROOT",
    "SELF_CONTAINMENT_PATH",
    "candidate_manifest",
    "container_identity",
    "declared_release_files",
    "freeze_release",
    "read_release_freeze",
    "release_hashes",
    "run_staged_tests",
    "source_dependency_files",
    "stage_release_closure",
    "write_candidate_manifest",
]

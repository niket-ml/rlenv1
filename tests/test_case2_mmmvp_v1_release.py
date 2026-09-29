"""Packaging-path tests only; scientific expectations remain in locked controls."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path

from uc_bench.case2_mmmvp_v1_release import (
    CANDIDATE_PATH,
    PACKAGE_ROOT,
    RELEASE_ID,
    REPRODUCIBILITY_PATH,
    anti_overfitting_audit,
)

ROOT = Path(__file__).resolve().parents[1]


def _candidate():
    return json.loads((ROOT / CANDIDATE_PATH).read_text(encoding="utf-8"))


def _safe_extract(archive: Path, destination: Path) -> None:
    with tarfile.open(archive, "r:gz") as handle:
        for member in handle.getmembers():
            target = (destination / member.name).resolve()
            assert destination.resolve() in target.parents or target == destination.resolve()
            assert not member.issym() and not member.islnk() and not member.isdev()
            assert not Path(member.name).is_absolute()
        handle.extractall(destination)  # noqa: S202 - members are validated immediately above


def test_two_clean_builds_and_final_candidate_are_identical():
    receipt = json.loads((ROOT / REPRODUCIBILITY_PATH).read_text(encoding="utf-8"))
    assert receipt["passed"]
    assert receipt["first"] == receipt["second"] == receipt["final"]
    assert receipt["byte_identical_agent_visible_bundles"]
    assert receipt["byte_identical_host_only_bundles"]


def test_actual_archives_are_normalized_safe_and_match_candidate():
    candidate = _candidate()
    package = ROOT / PACKAGE_ROOT
    for kind in ("agent-visible", "host-only"):
        archive = package / f"{RELEASE_ID}-{kind}.tar.gz"
        assert hashlib.sha256(archive.read_bytes()).hexdigest() == candidate[
            f"{kind.replace('-', '_')}_archive_sha256"
        ]
        with tarfile.open(archive, "r:gz") as handle:
            assert handle.getmembers()
            for member in handle.getmembers():
                assert member.mtime == 0
                assert member.uid == member.gid == 0
                assert member.uname == member.gname == ""
                assert not member.issym() and not member.islnk() and not member.isdev()
                assert not Path(member.name).is_absolute()
                assert ".." not in Path(member.name).parts


def test_agent_visible_archive_has_no_host_or_historical_material(tmp_path):
    archive = ROOT / PACKAGE_ROOT / f"{RELEASE_ID}-agent-visible.tar.gz"
    _safe_extract(archive, tmp_path)
    files = [path for path in tmp_path.rglob("*") if path.is_file()]
    names = [path.relative_to(tmp_path).as_posix().lower() for path in files]
    text = b"\n".join(path.read_bytes() for path in files)
    forbidden_names = ("grader", "trajectory", "replays.json", "truth.json", "run_summary")
    forbidden_content = (
        b"grader_private",
        b"case2-budget-safe",
        b"case2-diagnostic-canary",
        b"16.129032",
        b"65.909091",
        b"61.290323",
        b"77.419355",
        b"sk-or-v1-",
    )
    assert not any(any(token in name for token in forbidden_names) for name in names)
    assert not any(token in text for token in forbidden_content)


def test_evidence_package_is_regular_complete_and_hash_verified():
    evidence = ROOT / PACKAGE_ROOT / "evidence"
    manifest = json.loads((evidence / "SHA256_MANIFEST.json").read_text(encoding="utf-8"))
    assert len(manifest) == _candidate()["evidence_file_count"]
    for relative, row in manifest.items():
        path = evidence / relative
        assert path.is_file() and not path.is_symlink()
        assert path.stat().st_size == row["bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]


def test_active_grader_has_no_historical_or_model_specific_logic():
    result = anti_overfitting_audit(ROOT)
    assert result["passed"], result["unexplained_hits"]


def test_exact_extracted_host_package_runs_locked_controls_and_lifecycle(tmp_path):
    archive = ROOT / PACKAGE_ROOT / f"{RELEASE_ID}-host-only.tar.gz"
    _safe_extract(archive, tmp_path)
    host = tmp_path / RELEASE_ID / "host_only"
    environment = {**os.environ, "PYTHONPATH": f"{host / 'src'}:{host}"}
    locked = [
        "development/case2_diagnostic_repair/test_diagnostic_repair.py",
        "development/case2_diagnostic_repair/test_authority_separation.py",
        "development/case2_optionality_repair/test_optionality.py",
    ]
    controls = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *locked],
        cwd=host,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert controls.returncode == 0, controls.stdout + controls.stderr
    validation = subprocess.run(
        [sys.executable, "scripts/validate_case2_mmmvp_v1_package.py"],
        cwd=host,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert validation.returncode == 0, validation.stdout + validation.stderr
    payload = json.loads(validation.stdout)
    assert payload["passed"]
    assert payload["network_calls"] == payload["paid_model_calls"] == 0


"""Immutable verifier-hardening RC1.6 freeze over preserved RC1.5."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256, sha256_file
from uc_bench.mmmvp_open_freeze import read_open_mmmvp_freeze
from uc_bench.mmmvp_open_rc11_compatibility import compatibility_identity
from uc_bench.mmmvp_open_rc15_freeze import read_rc15_release_freeze

SCIENTIFIC_FREEZE_DIGEST = "466441682b04175432329b41adcfd735cdea66f860d66f046dfae195c91e701c"
RC15_INFRASTRUCTURE_DIGEST = "fd505c1d639fd4ecaabe6c3828f3f157cd4e4aebb685a6e5788868b611ee4bc4"
RC15_FREEZE_SHA256 = "9f04207c2288bd70136f8eb10c35c127ff3b0fe6687cf87855d1944d2ba42fed"
RC15_GEMINI_SUMMARY_SHA256 = "a88ce2a87e77e0f2222f435c36903540357ae4463c4084bd8306515e4d98231d"
RC15_GEMINI_TREE_DIGEST = "cd33e2acc6e98a3fedf585443f035b609ef7a86c357627ce27ee40edf1785d21"
RC15_SENTINEL_STATE_SHA256 = "5fc617506aded80f60b3d2ae69bbb42ef3acbb6eb785132b59cd8fc83a8b5fc8"
RC15_OFFICIAL_REPORT_SHA256 = "6735184de0ad5a3c1af996996930180b151917b3928dc174106ba70105483b52"
RC16_FREEZE_PATH = Path("artifacts/mmmvp_open_rc16/release_freeze.json")
RC16_GATE_PATH = Path("artifacts/mmmvp_open_rc16/pre_exposure_gate.json")

_INFRASTRUCTURE_FILES = (
    "configs/uc_bench_mmmvp_open_rc16_release.json",
    "src/uc_bench/mmmvp_open_rc16_artifacts.py",
    "src/uc_bench/mmmvp_open_rc16_verifier.py",
    "src/uc_bench/mmmvp_open_rc16_trajectory.py",
    "src/uc_bench/mmmvp_open_rc16_runner.py",
    "src/uc_bench/mmmvp_open_rc16_corpus.py",
    "src/uc_bench/mmmvp_open_rc16_rehearsal.py",
    "src/uc_bench/mmmvp_open_rc16_cost.py",
    "src/uc_bench/mmmvp_open_rc16_order.py",
    "src/uc_bench/mmmvp_open_rc16_sentinel.py",
    "src/uc_bench/mmmvp_open_rc16_analysis.py",
    "src/uc_bench/mmmvp_open_rc16_freeze.py",
    "scripts/prepare_mmmvp_open_rc16.py",
    "scripts/check_mmmvp_open_rc16_gate.py",
    "scripts/create_mmmvp_open_rc16_freeze.py",
    "scripts/check_mmmvp_open_rc16_frozen_preflight.py",
    "scripts/plan_mmmvp_open_rc16_cost.py",
    "scripts/create_mmmvp_open_rc16_order.py",
    "scripts/run_mmmvp_open_rc16_sentinel.py",
    "scripts/analyze_mmmvp_open_rc16_sentinel.py",
    "tests/test_mmmvp_open_rc16.py",
    "artifacts/mmmvp_open_rc16/compatibility_inheritance.json",
    "artifacts/mmmvp_open_rc16/parser_trust_boundary_audit.json",
    "artifacts/mmmvp_open_rc16/gemini_regression.json",
    "artifacts/mmmvp_open_rc16/crash_corpus.json",
    "artifacts/mmmvp_open_rc16/red_team_parser_review.json",
    "artifacts/mmmvp_open_rc16/pre_freeze_rehearsal.json",
    "artifacts/mmmvp_open_rc16/pre_exposure_gate.json",
)


def rc16_infrastructure_hashes(project_root: Path) -> dict[str, str]:
    root = project_root.resolve()
    paths = [root / relative for relative in _INFRASTRUCTURE_FILES]
    missing = [path.relative_to(root).as_posix() for path in paths if not path.is_file()]
    if missing:
        raise ConfigurationError(f"RC1.6 infrastructure files are missing: {missing}")
    return {path.relative_to(root).as_posix(): sha256_file(path) for path in sorted(paths)}


def _validate_inheritance(project_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    root = project_root.resolve()
    scientific = read_open_mmmvp_freeze(root)
    rc15 = read_rc15_release_freeze(root)
    identity = compatibility_identity(root)
    gemini_summary = root / (
        "build/uc_bench_mmmvp_open_rc14_runs/"
        "open-mmmvp-rc15-sentinel-00-google-gemini-3.1-pro-preview-case-02-atte/"
        "run_summary.json"
    )
    gemini_root = gemini_summary.parent
    gemini_tree = {
        path.relative_to(gemini_root).as_posix(): sha256_file(path)
        for path in sorted(gemini_root.rglob("*"))
        if path.is_file()
    }
    if scientific["hash_set_digest"] != SCIENTIFIC_FREEZE_DIGEST:
        raise ConfigurationError("RC1.6 scientific freeze drift")
    if rc15["infrastructure_digest"] != RC15_INFRASTRUCTURE_DIGEST:
        raise ConfigurationError("RC1.5 infrastructure changed")
    if sha256_file(root / "artifacts/mmmvp_open_rc15/release_freeze.json") != RC15_FREEZE_SHA256:
        raise ConfigurationError("RC1.5 freeze changed")
    if sha256_file(gemini_summary) != RC15_GEMINI_SUMMARY_SHA256:
        raise ConfigurationError("RC1.5 Gemini official output changed")
    if canonical_sha256(gemini_tree) != RC15_GEMINI_TREE_DIGEST:
        raise ConfigurationError("RC1.5 Gemini trajectory tree changed")
    if (
        sha256_file(root / "artifacts/mmmvp_open_rc15/sentinel_state.json")
        != RC15_SENTINEL_STATE_SHA256
        or sha256_file(root / "reports/UC_BENCH_MMMVP_OPEN_RC15_CASE2_SENTINEL_STOP.md")
        != RC15_OFFICIAL_REPORT_SHA256
    ):
        raise ConfigurationError("RC1.5 official unscored result changed")
    rc15_config = json.loads((root / "configs/uc_bench_mmmvp_open_rc15_release.json").read_text())
    rc16_config = json.loads((root / "configs/uc_bench_mmmvp_open_rc16_release.json").read_text())
    if rc15_config["scientific_episode"] != rc16_config["scientific_episode"]:
        raise ConfigurationError("RC1.6 changed scientific execution settings")
    if identity["serialized_request_sha256"] != rc15["serialized_request_sha256"]:
        raise ConfigurationError("RC1.6 request hash changed")
    if identity["tool_schema_sha256"] != rc15["tool_schema_sha256"]:
        raise ConfigurationError("RC1.6 tool schema changed")
    return scientific, rc15


def create_rc16_release_freeze(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    target = root / RC16_FREEZE_PATH
    if target.exists():
        raise ConfigurationError("RC1.6 is already frozen")
    scientific, rc15 = _validate_inheritance(root)
    evidence_paths = (
        "compatibility_inheritance.json",
        "parser_trust_boundary_audit.json",
        "gemini_regression.json",
        "crash_corpus.json",
        "red_team_parser_review.json",
        "pre_freeze_rehearsal.json",
        "pre_exposure_gate.json",
    )
    evidence = {
        name: json.loads((root / "artifacts/mmmvp_open_rc16" / name).read_text())
        for name in evidence_paths
    }
    if any(row.get("status") != "passed" for row in evidence.values()):
        raise ConfigurationError("RC1.6 zero-cost evidence contains a failed gate")
    if any(int(row.get("api_requests") or 0) for row in evidence.values()):
        raise ConfigurationError("RC1.6 pre-freeze evidence made an API request")
    infrastructure = rc16_infrastructure_hashes(root)
    value = {
        "schema_version": "uc-bench-open-mmmvp-rc1-6-release-freeze-1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "immutable_verifier_hardening_successor",
        "source_rc15_infrastructure_digest": rc15["infrastructure_digest"],
        "source_rc15_freeze_sha256": RC15_FREEZE_SHA256,
        "source_rc15_gemini_summary_sha256": RC15_GEMINI_SUMMARY_SHA256,
        "source_rc15_gemini_tree_digest": RC15_GEMINI_TREE_DIGEST,
        "source_rc15_sentinel_state_sha256": RC15_SENTINEL_STATE_SHA256,
        "source_rc15_official_report_sha256": RC15_OFFICIAL_REPORT_SHA256,
        "scientific_freeze_digest": scientific["hash_set_digest"],
        "scientific_hashes": scientific["hashes"],
        "serialized_request_sha256": rc15["serialized_request_sha256"],
        "tool_schema_sha256": rc15["tool_schema_sha256"],
        "agent_visible_contract_sha256": rc15["agent_visible_contract_sha256"],
        "scientific_content_unchanged": True,
        "prompt_contract_tools_routes_unchanged": True,
        "scoring_semantics_and_weights_unchanged": True,
        "verifier_change_scope": (
            "total typed artifact parsing and independent lifecycle/grader replay"
        ),
        "compatibility_inherited_without_requests": True,
        "technically_compatible_models": rc15["technically_compatible_models"],
        "provider_specific_exclusions": rc15["provider_specific_exclusions"],
        "infrastructure_hashes": infrastructure,
        "infrastructure_digest": canonical_sha256(infrastructure),
        "scientific_hard_cap_usd": 50.0,
        "sentinel_condition": "case_02",
        "remaining_matrix_authorized": False,
        "provider_fallbacks_allowed": False,
        "heldout_included": False,
        "astra_included": False,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(target)
    return value


def read_rc16_release_freeze(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    target = root / RC16_FREEZE_PATH
    if not target.is_file():
        raise ConfigurationError("RC1.6 is not frozen")
    value = json.loads(target.read_text(encoding="utf-8"))
    scientific, rc15 = _validate_inheritance(root)
    expected = {
        "source_rc15_infrastructure_digest": rc15["infrastructure_digest"],
        "source_rc15_freeze_sha256": RC15_FREEZE_SHA256,
        "source_rc15_gemini_summary_sha256": RC15_GEMINI_SUMMARY_SHA256,
        "source_rc15_gemini_tree_digest": RC15_GEMINI_TREE_DIGEST,
        "source_rc15_sentinel_state_sha256": RC15_SENTINEL_STATE_SHA256,
        "source_rc15_official_report_sha256": RC15_OFFICIAL_REPORT_SHA256,
        "scientific_freeze_digest": scientific["hash_set_digest"],
        "serialized_request_sha256": rc15["serialized_request_sha256"],
        "tool_schema_sha256": rc15["tool_schema_sha256"],
        "agent_visible_contract_sha256": rc15["agent_visible_contract_sha256"],
    }
    if any(value.get(key) != wanted for key, wanted in expected.items()):
        raise ConfigurationError("RC1.6 frozen identities changed")
    infrastructure = rc16_infrastructure_hashes(root)
    if value.get("infrastructure_hashes") != infrastructure or value.get(
        "infrastructure_digest"
    ) != canonical_sha256(infrastructure):
        raise ConfigurationError("Frozen RC1.6 infrastructure changed")
    if value.get("heldout_included") or value.get("astra_included"):
        raise ConfigurationError("Held-out or Astra content entered RC1.6")
    return value


__all__ = [
    "RC16_FREEZE_PATH",
    "RC16_GATE_PATH",
    "create_rc16_release_freeze",
    "read_rc16_release_freeze",
]

"""Immutable RC1.4 contract-only release freeze over preserved RC1.3."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256, sha256_file
from uc_bench.mmmvp_open_freeze import read_open_mmmvp_freeze
from uc_bench.mmmvp_open_rc11_compatibility import compatibility_identity
from uc_bench.mmmvp_open_rc13_freeze import read_rc13_release_freeze
from uc_bench.mmmvp_open_rc14_contract import RC14_AGENT_VISIBLE_CONTRACT

RC13_INFRASTRUCTURE_DIGEST = "c27c5b6af9f044baebb5364d0f069fa80e7022e5fb6ece1bffc6a4fde47dff29"
SCIENTIFIC_FREEZE_DIGEST = "466441682b04175432329b41adcfd735cdea66f860d66f046dfae195c91e701c"
SERIALIZED_REQUEST_DIGEST = "d50747a564877dea31329cd71e9a8a1e3b4ed8f913b802d059cc3c053d0d9523"
TOOL_SCHEMA_DIGEST = "a29133462152f7c78452a5e13c76efc2991142b8703ce418cdf4a78d10f842d7"
RC14_FREEZE_PATH = Path("artifacts/mmmvp_open_rc14/release_freeze.json")
RC14_GATE_PATH = Path("artifacts/mmmvp_open_rc14/pre_exposure_gate_04.json")

_INFRASTRUCTURE_FILES = (
    "configs/uc_bench_mmmvp_open_rc14_release.json",
    "src/uc_bench/mmmvp_open_rc14_contract.py",
    "src/uc_bench/mmmvp_open_rc14_environment.py",
    "src/uc_bench/mmmvp_open_rc14_audit.py",
    "src/uc_bench/mmmvp_open_rc14_compatibility.py",
    "src/uc_bench/mmmvp_open_rc14_harness.py",
    "src/uc_bench/mmmvp_open_rc14_cost.py",
    "src/uc_bench/mmmvp_open_rc14_order.py",
    "src/uc_bench/mmmvp_open_rc14_freeze.py",
    "src/uc_bench/mmmvp_open_rc14_runner.py",
    "src/uc_bench/mmmvp_open_rc14_sentinel.py",
    "src/uc_bench/mmmvp_open_rc14_analysis.py",
    "scripts/prepare_mmmvp_open_rc14.py",
    "scripts/run_mmmvp_open_rc14_compatibility.py",
    "scripts/plan_mmmvp_open_rc14_cost.py",
    "scripts/create_mmmvp_open_rc14_order.py",
    "scripts/check_mmmvp_open_rc14_gate.py",
    "scripts/create_mmmvp_open_rc14_freeze.py",
    "scripts/run_mmmvp_open_rc14_sentinel.py",
    "scripts/analyze_mmmvp_open_rc14_sentinel.py",
    "tests/test_mmmvp_open_rc14.py",
    "tests/fixtures/mmmvp_open_rc14_round01_response_shapes.json",
    "artifacts/mmmvp_open_rc14/contract_disclosure_audit.json",
    "artifacts/mmmvp_open_rc14/archived_submission_replay.json",
    "artifacts/mmmvp_open_rc14/pre_exposure_gate.json",
    "artifacts/mmmvp_open_rc14/compatibility_results.json",
    "artifacts/mmmvp_open_rc14/compatibility_round_01_forensic.json",
    "artifacts/mmmvp_open_rc14/compatibility_convergence_results.json",
    "artifacts/mmmvp_open_rc14/pre_exposure_gate_02.json",
    "artifacts/mmmvp_open_rc14/pre_exposure_gate_03.json",
    "artifacts/mmmvp_open_rc14/pre_exposure_gate_04.json",
)


def _rc14_infrastructure_paths(root: Path) -> list[Path]:
    paths = [root / relative for relative in _INFRASTRUCTURE_FILES]
    attempts = root / "artifacts/mmmvp_open_rc14/compatibility_attempts"
    if attempts.is_dir():
        paths.extend(path for path in attempts.rglob("*") if path.is_file())
    round02 = root / "artifacts/mmmvp_open_rc14/compatibility_round_02_attempts"
    if round02.is_dir():
        paths.extend(path for path in round02.rglob("*") if path.is_file())
    missing = [path.relative_to(root).as_posix() for path in paths if not path.is_file()]
    if missing:
        raise ConfigurationError(f"RC1.4 infrastructure files are missing: {missing}")
    return sorted(set(paths))


def rc14_infrastructure_hashes(project_root: Path) -> dict[str, str]:
    root = project_root.resolve()
    return {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in _rc14_infrastructure_paths(root)
    }


def _validate_inheritance(project_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    root = project_root.resolve()
    scientific = read_open_mmmvp_freeze(root)
    rc13 = read_rc13_release_freeze(root)
    identity = compatibility_identity(root)
    observed = {
        "scientific": scientific["hash_set_digest"],
        "request": identity["serialized_request_sha256"],
        "tools": identity["tool_schema_sha256"],
        "rc13": rc13["infrastructure_digest"],
    }
    expected = {
        "scientific": SCIENTIFIC_FREEZE_DIGEST,
        "request": SERIALIZED_REQUEST_DIGEST,
        "tools": TOOL_SCHEMA_DIGEST,
        "rc13": RC13_INFRASTRUCTURE_DIGEST,
    }
    if observed != expected:
        raise ConfigurationError(f"RC1.4 inheritance drift: {observed}")
    rc13_config = json.loads(
        (root / "configs/uc_bench_mmmvp_open_rc13_release.json").read_text()
    )
    rc14_config = json.loads(
        (root / "configs/uc_bench_mmmvp_open_rc14_release.json").read_text()
    )
    if rc13_config["scientific_episode"] != rc14_config["scientific_episode"]:
        raise ConfigurationError("RC1.4 changed the scientific episode budget")
    return scientific, rc13


def create_rc14_release_freeze(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    target = root / RC14_FREEZE_PATH
    if target.exists():
        raise ConfigurationError("RC1.4 is already frozen")
    scientific, rc13 = _validate_inheritance(root)
    gate = json.loads((root / RC14_GATE_PATH).read_text(encoding="utf-8"))
    disclosure = json.loads(
        (root / "artifacts/mmmvp_open_rc14/contract_disclosure_audit.json").read_text()
    )
    replay = json.loads(
        (root / "artifacts/mmmvp_open_rc14/archived_submission_replay.json").read_text()
    )
    compatibility = json.loads(
        (
            root
            / "artifacts/mmmvp_open_rc14/compatibility_convergence_results.json"
        ).read_text()
    )
    if gate.get("status") != "passed" or gate.get("api_requests") != 0:
        raise ConfigurationError("The zero-cost RC1.4 gate did not pass")
    if disclosure.get("status") != "passed" or replay.get("status") != "passed":
        raise ConfigurationError("RC1.4 contract disclosure evidence did not pass")
    if compatibility.get("status") != "passed" or compatibility.get(
        "technically_compatible_model_count", 0
    ) < 8:
        raise ConfigurationError("RC1.4 technical compatibility did not converge")
    if compatibility.get("scientific_requests") != 0:
        raise ConfigurationError("Scientific content entered RC1.4 compatibility")
    compatible_models = set(compatibility["technically_compatible_models"])
    infrastructure = rc14_infrastructure_hashes(root)
    value = {
        "schema_version": "uc-bench-open-mmmvp-rc1-4-release-freeze-1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "immutable_contract_successor",
        "source_rc13_infrastructure_digest": rc13["infrastructure_digest"],
        "scientific_freeze_digest": scientific["hash_set_digest"],
        "scientific_hashes": scientific["hashes"],
        "scientific_cases_and_hidden_outcomes_byte_identical": True,
        "verifier_logic_byte_identical": True,
        "tools_byte_identical": True,
        "provider_routes_byte_identical": True,
        "serialized_request_sha256": SERIALIZED_REQUEST_DIGEST,
        "tool_schema_sha256": TOOL_SCHEMA_DIGEST,
        "agent_visible_contract_sha256": canonical_sha256(RC14_AGENT_VISIBLE_CONTRACT),
        "only_agent_visible_contract_changed": True,
        "infrastructure_hashes": infrastructure,
        "infrastructure_digest": canonical_sha256(infrastructure),
        "compatibility_cost_usd": compatibility[
            "total_rc14_compatibility_cost_usd"
        ],
        "scientific_hard_cap_usd": 52.0,
        "technically_compatible_models": sorted(compatible_models),
        "provider_specific_compatibility_exclusions": compatibility[
            "provider_specific_exclusions"
        ],
        "sentinel_condition": "case_02",
        "sentinel_order_created_after_freeze": True,
        "cost_plan_created_after_freeze": True,
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


def read_rc14_release_freeze(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    target = root / RC14_FREEZE_PATH
    if not target.is_file():
        raise ConfigurationError("RC1.4 is not frozen")
    value = json.loads(target.read_text(encoding="utf-8"))
    scientific, rc13 = _validate_inheritance(root)
    expected = {
        "source_rc13_infrastructure_digest": rc13["infrastructure_digest"],
        "scientific_freeze_digest": scientific["hash_set_digest"],
        "serialized_request_sha256": SERIALIZED_REQUEST_DIGEST,
        "tool_schema_sha256": TOOL_SCHEMA_DIGEST,
        "agent_visible_contract_sha256": canonical_sha256(RC14_AGENT_VISIBLE_CONTRACT),
    }
    if any(value.get(key) != wanted for key, wanted in expected.items()):
        raise ConfigurationError("RC1.4 frozen identities changed")
    infrastructure = rc14_infrastructure_hashes(root)
    if value.get("infrastructure_hashes") != infrastructure or value.get(
        "infrastructure_digest"
    ) != canonical_sha256(infrastructure):
        raise ConfigurationError("Frozen RC1.4 infrastructure changed")
    if value.get("heldout_included") or value.get("astra_included"):
        raise ConfigurationError("Held-out or Astra content entered RC1.4")
    return value


__all__ = [
    "RC13_INFRASTRUCTURE_DIGEST",
    "RC14_FREEZE_PATH",
    "RC14_GATE_PATH",
    "SCIENTIFIC_FREEZE_DIGEST",
    "SERIALIZED_REQUEST_DIGEST",
    "TOOL_SCHEMA_DIGEST",
    "create_rc14_release_freeze",
    "rc14_infrastructure_hashes",
    "read_rc14_release_freeze",
]

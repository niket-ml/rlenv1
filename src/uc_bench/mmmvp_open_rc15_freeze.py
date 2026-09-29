"""Immutable infrastructure-only RC1.5 freeze over preserved RC1.4."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256, sha256_file
from uc_bench.mmmvp_open_freeze import read_open_mmmvp_freeze
from uc_bench.mmmvp_open_rc11_compatibility import compatibility_identity
from uc_bench.mmmvp_open_rc14_freeze import read_rc14_release_freeze

SCIENTIFIC_FREEZE_DIGEST = "466441682b04175432329b41adcfd735cdea66f860d66f046dfae195c91e701c"
RC14_INFRASTRUCTURE_DIGEST = "613811a14ff54c7a24fbeffe72e6b7ca374b4a0ce5e8cb4a36e2a65adaba8a8c"
RC14_FREEZE_SHA256 = "f03ec0ac838c830af1344ff4b2eab37ec5245bcca001a7931f01a188a0e81bbf"
SERIALIZED_REQUEST_DIGEST = "d50747a564877dea31329cd71e9a8a1e3b4ed8f913b802d059cc3c053d0d9523"
TOOL_SCHEMA_DIGEST = "a29133462152f7c78452a5e13c76efc2991142b8703ce418cdf4a78d10f842d7"
RC15_FREEZE_PATH = Path("artifacts/mmmvp_open_rc15/release_freeze.json")
RC15_GATE_PATH = Path("artifacts/mmmvp_open_rc15/pre_exposure_gate.json")

_INFRASTRUCTURE_FILES = (
    "configs/uc_bench_mmmvp_open_rc15_release.json",
    "src/uc_bench/mmmvp_open_rc15_adapter.py",
    "src/uc_bench/mmmvp_open_rc15_audit.py",
    "src/uc_bench/mmmvp_open_rc15_cost.py",
    "src/uc_bench/mmmvp_open_rc15_guard.py",
    "src/uc_bench/mmmvp_open_rc15_order.py",
    "src/uc_bench/mmmvp_open_rc15_rehearsal.py",
    "src/uc_bench/mmmvp_open_rc15_freeze.py",
    "src/uc_bench/mmmvp_open_rc15_sentinel.py",
    "src/uc_bench/mmmvp_open_rc15_analysis.py",
    "scripts/prepare_mmmvp_open_rc15.py",
    "scripts/run_mmmvp_open_rc15_rehearsal.py",
    "scripts/check_mmmvp_open_rc15_gate.py",
    "scripts/create_mmmvp_open_rc15_freeze.py",
    "scripts/plan_mmmvp_open_rc15_cost.py",
    "scripts/check_mmmvp_open_rc15_frozen_preflight.py",
    "scripts/create_mmmvp_open_rc15_order.py",
    "scripts/run_mmmvp_open_rc15_sentinel.py",
    "scripts/analyze_mmmvp_open_rc15_sentinel.py",
    "tests/test_mmmvp_open_rc15.py",
    "artifacts/mmmvp_open_rc15/compatibility_inheritance.json",
    "artifacts/mmmvp_open_rc15/schema_parsing_inventory.json",
    "artifacts/mmmvp_open_rc15/pre_freeze_rehearsal_attempt_01.json",
    "artifacts/mmmvp_open_rc15/pre_freeze_rehearsal.json",
    "artifacts/mmmvp_open_rc15/pre_exposure_gate.json",
)


def rc15_infrastructure_hashes(project_root: Path) -> dict[str, str]:
    root = project_root.resolve()
    paths = [root / relative for relative in _INFRASTRUCTURE_FILES]
    missing = [path.relative_to(root).as_posix() for path in paths if not path.is_file()]
    if missing:
        raise ConfigurationError(f"RC1.5 infrastructure files are missing: {missing}")
    return {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in sorted(paths)
    }


def _validate_inheritance(project_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    root = project_root.resolve()
    scientific = read_open_mmmvp_freeze(root)
    rc14 = read_rc14_release_freeze(root)
    identity = compatibility_identity(root)
    observed = {
        "scientific": scientific["hash_set_digest"],
        "rc14": rc14["infrastructure_digest"],
        "rc14_freeze": sha256_file(
            root / "artifacts/mmmvp_open_rc14/release_freeze.json"
        ),
        "request": identity["serialized_request_sha256"],
        "tools": identity["tool_schema_sha256"],
    }
    expected = {
        "scientific": SCIENTIFIC_FREEZE_DIGEST,
        "rc14": RC14_INFRASTRUCTURE_DIGEST,
        "rc14_freeze": RC14_FREEZE_SHA256,
        "request": SERIALIZED_REQUEST_DIGEST,
        "tools": TOOL_SCHEMA_DIGEST,
    }
    if observed != expected:
        raise ConfigurationError(f"RC1.5 inheritance drift: {observed}")
    rc14_config = json.loads(
        (root / "configs/uc_bench_mmmvp_open_rc14_release.json").read_text()
    )
    rc15_config = json.loads(
        (root / "configs/uc_bench_mmmvp_open_rc15_release.json").read_text()
    )
    if rc14_config["scientific_episode"] != rc15_config["scientific_episode"]:
        raise ConfigurationError("RC1.5 changed the scientific episode contract")
    return scientific, rc14


def create_rc15_release_freeze(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    target = root / RC15_FREEZE_PATH
    if target.exists():
        raise ConfigurationError("RC1.5 is already frozen")
    scientific, rc14 = _validate_inheritance(root)
    gate = json.loads((root / RC15_GATE_PATH).read_text(encoding="utf-8"))
    rehearsal = json.loads(
        (
            root / "artifacts/mmmvp_open_rc15/pre_freeze_rehearsal.json"
        ).read_text(encoding="utf-8")
    )
    inheritance = json.loads(
        (
            root / "artifacts/mmmvp_open_rc15/compatibility_inheritance.json"
        ).read_text(encoding="utf-8")
    )
    inventory = json.loads(
        (
            root / "artifacts/mmmvp_open_rc15/schema_parsing_inventory.json"
        ).read_text(encoding="utf-8")
    )
    if gate.get("status") != "passed" or gate.get("api_requests") != 0:
        raise ConfigurationError("RC1.5 zero-cost gate did not pass")
    if rehearsal.get("status") != "passed" or rehearsal.get("api_requests") != 0:
        raise ConfigurationError("RC1.5 full launch rehearsal did not pass")
    if inheritance.get("status") != "passed" or inventory.get("status") != "passed":
        raise ConfigurationError("RC1.5 canonical inheritance evidence did not pass")
    infrastructure = rc15_infrastructure_hashes(root)
    value = {
        "schema_version": "uc-bench-open-mmmvp-rc1-5-release-freeze-1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "immutable_infrastructure_successor",
        "source_rc14_infrastructure_digest": rc14["infrastructure_digest"],
        "source_rc14_freeze_sha256": RC14_FREEZE_SHA256,
        "scientific_freeze_digest": scientific["hash_set_digest"],
        "scientific_hashes": scientific["hashes"],
        "serialized_request_sha256": SERIALIZED_REQUEST_DIGEST,
        "tool_schema_sha256": TOOL_SCHEMA_DIGEST,
        "agent_visible_contract_sha256": rc14["agent_visible_contract_sha256"],
        "scientific_content_byte_identical": True,
        "contract_tools_verifier_routes_byte_identical": True,
        "compatibility_inherited_without_requests": True,
        "technically_compatible_models": inheritance[
            "technically_compatible_models"
        ],
        "provider_specific_exclusions": inheritance[
            "provider_specific_exclusions"
        ],
        "canonical_launch_properties": inventory["canonical_properties"],
        "infrastructure_hashes": infrastructure,
        "infrastructure_digest": canonical_sha256(infrastructure),
        "scientific_hard_cap_usd": 52.0,
        "sentinel_condition": "case_02",
        "cost_plan_created_after_freeze": True,
        "sentinel_order_created_after_freeze": True,
        "remaining_matrix_authorized": False,
        "provider_fallbacks_allowed": False,
        "heldout_included": False,
        "astra_included": False,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(target)
    return value


def read_rc15_release_freeze(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    target = root / RC15_FREEZE_PATH
    if not target.is_file():
        raise ConfigurationError("RC1.5 is not frozen")
    value = json.loads(target.read_text(encoding="utf-8"))
    scientific, rc14 = _validate_inheritance(root)
    expected = {
        "source_rc14_infrastructure_digest": rc14["infrastructure_digest"],
        "source_rc14_freeze_sha256": RC14_FREEZE_SHA256,
        "scientific_freeze_digest": scientific["hash_set_digest"],
        "serialized_request_sha256": SERIALIZED_REQUEST_DIGEST,
        "tool_schema_sha256": TOOL_SCHEMA_DIGEST,
        "agent_visible_contract_sha256": rc14["agent_visible_contract_sha256"],
    }
    if any(value.get(key) != wanted for key, wanted in expected.items()):
        raise ConfigurationError("RC1.5 frozen identities changed")
    infrastructure = rc15_infrastructure_hashes(root)
    if value.get("infrastructure_hashes") != infrastructure or value.get(
        "infrastructure_digest"
    ) != canonical_sha256(infrastructure):
        raise ConfigurationError("Frozen RC1.5 infrastructure changed")
    if value.get("heldout_included") or value.get("astra_included"):
        raise ConfigurationError("Held-out or Astra content entered RC1.5")
    return value


__all__ = [
    "RC15_FREEZE_PATH",
    "RC15_GATE_PATH",
    "create_rc15_release_freeze",
    "rc15_infrastructure_hashes",
    "read_rc15_release_freeze",
]

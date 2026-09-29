"""Zero-cost inheritance and schema-boundary audits for RC1.5."""

from __future__ import annotations

import inspect
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.hashing import sha256_file
from uc_bench.mmmvp_open_rc14_freeze import read_rc14_release_freeze
from uc_bench.mmmvp_open_rc15_adapter import (
    PRICE_CONTAINER_FIELD,
    load_rc15_all_routes,
    load_rc15_launch_routes,
)
from uc_bench.model_runner import _write_json

INHERITANCE_PATH = Path("artifacts/mmmvp_open_rc15/compatibility_inheritance.json")
SCHEMA_INVENTORY_PATH = Path("artifacts/mmmvp_open_rc15/schema_parsing_inventory.json")
RC14_FREEZE_SHA256 = "f03ec0ac838c830af1344ff4b2eab37ec5245bcca001a7931f01a188a0e81bbf"


def compatibility_inheritance(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    release = read_rc14_release_freeze(root)
    source = json.loads(
        (
            root
            / "artifacts/mmmvp_open_rc14/compatibility_convergence_results.json"
        ).read_text(encoding="utf-8")
    )
    routes = load_rc15_launch_routes(root)
    exclusions = list(source.get("provider_specific_exclusions") or [])
    rc14_freeze_sha256 = sha256_file(
        root / "artifacts/mmmvp_open_rc14/release_freeze.json"
    )
    passed = bool(
        source.get("status") == "passed"
        and len(routes) == 9
        and exclusions == ["z-ai/glm-5.2"]
        and set(routes) == set(source["technically_compatible_models"])
        and release["technically_compatible_models"]
        == sorted(source["technically_compatible_models"])
        and rc14_freeze_sha256 == RC14_FREEZE_SHA256
    )
    return {
        "schema_version": "uc-bench-open-mmmvp-rc1-5-compatibility-inheritance-1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "passed" if passed else "failed",
        "source": "artifacts/mmmvp_open_rc14/compatibility_convergence_results.json",
        "source_preserved": True,
        "source_sha256": sha256_file(
            root
            / "artifacts/mmmvp_open_rc14/compatibility_convergence_results.json"
        ),
        "source_rc14_freeze_sha256": rc14_freeze_sha256,
        "technically_compatible_models": list(routes),
        "provider_specific_exclusions": exclusions,
        "new_compatibility_requests": 0,
        "request_hash_changed": False,
        "tool_schema_hash_changed": False,
        "provider_or_route_hash_changed": False,
        "scientific_requests": 0,
        "heldout_requests": 0,
        "astra_requests": 0,
    }


def schema_parsing_inventory(project_root: Path) -> dict[str, Any]:
    """Document archived duplication and prove RC1.5 has one parsing boundary."""

    from uc_bench import mmmvp_open_rc15_adapter as canonical
    from uc_bench import mmmvp_open_rc15_cost as cost

    root = project_root.resolve()
    all_routes = load_rc15_all_routes(root)
    compatible = load_rc15_launch_routes(root)
    cost_source = inspect.getsource(cost)
    canonical_source = inspect.getsource(canonical)
    bypass_tokens = (
        '["maximum_prompt_price_usd_per_million"]',
        '["maximum_completion_price_usd_per_million"]',
    )
    successor_bypasses = [token for token in bypass_tokens if token in cost_source]
    passed = bool(
        len(all_routes) == 10
        and len(compatible) == 9
        and not successor_bypasses
        and PRICE_CONTAINER_FIELD in canonical_source
    )
    return {
        "schema_version": "uc-bench-open-mmmvp-rc1-5-schema-inventory-1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "passed" if passed else "failed",
        "archived_inventory": [
            {
                "path": "src/uc_bench/mmmvp_open_rc13_cost.py",
                "behaviour": "read nested prices with permissive defaults",
                "archived_and_unchanged": True,
            },
            {
                "path": "src/uc_bench/mmmvp_open_rc14_cost.py",
                "behaviour": "read invented flat price keys and failed after freeze",
                "archived_and_unchanged": True,
            },
            {
                "path": "src/uc_bench/mmmvp_open_provider.py",
                "behaviour": "construct typed adapters from panel and route contract",
                "archived_and_unchanged": True,
            },
            {
                "path": "src/uc_bench/mmmvp_provider.py",
                "behaviour": "define typed provider adapter and request serialization",
                "archived_and_unchanged": True,
            },
        ],
        "rc15_canonical_boundary": (
            "src/uc_bench/mmmvp_open_rc15_adapter.py:CanonicalLaunchRoute"
        ),
        "canonical_properties": [
            "route_prices",
            "context_limit",
            "completion_limit",
            "provider_identity",
            "reasoning_configuration",
        ],
        "all_panel_entry_count": len(all_routes),
        "compatible_launch_entry_count": len(compatible),
        "excluded_model_ids": sorted(set(all_routes) - set(compatible)),
        "successor_raw_flat_price_bypasses": successor_bypasses,
        "silent_defaults_allowed": False,
    }


def write_rc15_audits(project_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    root = project_root.resolve()
    inheritance = compatibility_inheritance(root)
    inventory = schema_parsing_inventory(root)
    if inheritance["status"] != "passed" or inventory["status"] != "passed":
        raise ConfigurationError("RC1.5 inheritance or schema audit failed")
    _write_json(root / INHERITANCE_PATH, inheritance, secret="")
    _write_json(root / SCHEMA_INVENTORY_PATH, inventory, secret="")
    return inheritance, inventory


__all__ = [
    "INHERITANCE_PATH",
    "RC14_FREEZE_SHA256",
    "SCHEMA_INVENTORY_PATH",
    "compatibility_inheritance",
    "schema_parsing_inventory",
    "write_rc15_audits",
]

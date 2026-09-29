"""Zero-cost inheritance of the ten RC1.1 compatibility passes."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256, sha256_file
from uc_bench.mmmvp_open_provider import load_open_route_contract_adapters
from uc_bench.mmmvp_open_rc11_compatibility import compatibility_identity
from uc_bench.mmmvp_open_rc11_freeze import read_rc11_release_freeze
from uc_bench.model_runner import _write_json

INHERITANCE_PATH = Path("artifacts/mmmvp_open_rc12/inherited_compatibility.json")
RC11_RESULTS_PATH = Path("artifacts/mmmvp_open_rc11/compatibility_results.json")


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError(f"Expected object: {path}")
    return value


def create_rc12_compatibility_inheritance(project_root: Path) -> dict[str, Any]:
    """Lock ten prior passes only when every provider-facing identity is unchanged."""

    root = project_root.resolve()
    target = root / INHERITANCE_PATH
    if target.exists():
        raise ConfigurationError("RC1.2 compatibility inheritance already exists")
    rc11_release = read_rc11_release_freeze(root)
    rc11_results = _read(root / RC11_RESULTS_PATH)
    current_identity = compatibility_identity(root)
    rc11_inheritance = _read(root / "artifacts/mmmvp_open_rc11/inherited_compatibility.json")
    if current_identity != rc11_inheritance.get("identity"):
        raise ConfigurationError("Provider-facing compatibility identity changed after RC1.1")
    results = list(rc11_results.get("results") or [])
    if rc11_results.get("status") != "passed" or len(results) != 10:
        raise ConfigurationError("RC1.1 does not contain exactly ten compatibility passes")
    if any(row.get("classification") != "compatible" for row in results):
        raise ConfigurationError("A model in RC1.1 compatibility did not pass")
    adapters = load_open_route_contract_adapters(root)
    for row in results:
        model_id = str(row.get("model_id"))
        adapter = adapters.get(model_id)
        if adapter is None or row.get("adapter") != adapter.to_dict():
            raise ConfigurationError(f"Adapter changed since compatibility: {model_id}")
        if row.get("actual_providers") != list(adapter.provider_order):
            raise ConfigurationError(f"Provider pin changed since compatibility: {model_id}")
    value = {
        "schema_version": "uc-bench-open-mmmvp-rc1-2-compatibility-inheritance-1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "passed",
        "api_requests": 0,
        "scientific_requests": 0,
        "paid_compatibility_requests": 0,
        "inherited_model_count": 10,
        "identity": current_identity,
        "identity_digest": canonical_sha256(current_identity),
        "source_rc11_infrastructure_digest": rc11_release["infrastructure_digest"],
        "source_results_sha256": sha256_file(root / RC11_RESULTS_PATH),
        "source_original_qwen_failure_preserved": bool(
            rc11_results.get("qwen_original_failure_preserved")
        ),
        "results": [{**row, "inheritance": "exact_rc11_compatibility_evidence"} for row in results],
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    _write_json(target, value, secret="")
    return value


def load_rc12_compatible_adapters(project_root: Path) -> dict[str, Any]:
    """Return the unchanged adapters for all ten inherited passes."""

    root = project_root.resolve()
    inheritance = _read(root / INHERITANCE_PATH)
    if inheritance.get("status") != "passed" or inheritance.get("inherited_model_count") != 10:
        raise ConfigurationError("RC1.2 compatibility inheritance is incomplete")
    if compatibility_identity(root) != inheritance.get("identity"):
        raise ConfigurationError("Provider-facing identity changed after RC1.2 inheritance")
    adapters = load_open_route_contract_adapters(root)
    passing = {str(row["model_id"]) for row in inheritance["results"]}
    selected = {model_id: adapter for model_id, adapter in adapters.items() if model_id in passing}
    if len(selected) != 10:
        raise ConfigurationError("RC1.2 did not resolve all ten inherited adapters")
    return selected


__all__ = [
    "INHERITANCE_PATH",
    "RC11_RESULTS_PATH",
    "create_rc12_compatibility_inheritance",
    "load_rc12_compatible_adapters",
]

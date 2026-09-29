"""Zero-cost RC1.3 inheritance of unchanged RC1.2 compatibility evidence."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256, sha256_file
from uc_bench.mmmvp_open_provider import load_open_route_contract_adapters
from uc_bench.mmmvp_open_rc11_compatibility import compatibility_identity
from uc_bench.mmmvp_open_rc12_freeze import read_rc12_release_freeze
from uc_bench.model_runner import _write_json

INHERITANCE_PATH = Path("artifacts/mmmvp_open_rc13/inherited_compatibility.json")
RC12_INHERITANCE_PATH = Path("artifacts/mmmvp_open_rc12/inherited_compatibility.json")


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError(f"Expected object: {path}")
    return value


def create_rc13_compatibility_inheritance(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    target = root / INHERITANCE_PATH
    if target.exists():
        raise ConfigurationError("RC1.3 compatibility inheritance already exists")
    rc12_release = read_rc12_release_freeze(root)
    source = _read(root / RC12_INHERITANCE_PATH)
    identity = compatibility_identity(root)
    if source.get("status") != "passed" or source.get("inherited_model_count") != 10:
        raise ConfigurationError("RC1.2 compatibility evidence is incomplete")
    if identity != source.get("identity"):
        raise ConfigurationError("Provider-facing compatibility identity changed")
    adapters = load_open_route_contract_adapters(root)
    rows = list(source.get("results") or [])
    if len(rows) != 10 or any(row.get("classification") != "compatible" for row in rows):
        raise ConfigurationError("RC1.2 does not contain ten compatible models")
    for row in rows:
        model_id = str(row["model_id"])
        adapter = adapters.get(model_id)
        if adapter is None or row.get("adapter") != adapter.to_dict():
            raise ConfigurationError(f"Adapter drift for {model_id}")
        if row.get("actual_providers") != list(adapter.provider_order):
            raise ConfigurationError(f"Provider route drift for {model_id}")
    value = {
        "schema_version": "uc-bench-open-mmmvp-rc1-3-compatibility-inheritance-1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "passed",
        "api_requests": 0,
        "scientific_requests": 0,
        "paid_compatibility_requests": 0,
        "inherited_model_count": 10,
        "identity": identity,
        "identity_digest": canonical_sha256(identity),
        "source_rc12_infrastructure_digest": rc12_release["infrastructure_digest"],
        "source_rc12_inheritance_sha256": sha256_file(root / RC12_INHERITANCE_PATH),
        "results": [
            {**row, "inheritance": "exact_rc12_compatibility_evidence"}
            for row in rows
        ],
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    _write_json(target, value, secret="")
    return value


def load_rc13_compatible_adapters(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    value = _read(root / INHERITANCE_PATH)
    if value.get("status") != "passed" or value.get("inherited_model_count") != 10:
        raise ConfigurationError("RC1.3 compatibility inheritance is incomplete")
    if compatibility_identity(root) != value.get("identity"):
        raise ConfigurationError("Provider-facing identity changed after inheritance")
    adapters = load_open_route_contract_adapters(root)
    passing = {str(row["model_id"]) for row in value["results"]}
    selected = {
        model_id: adapter
        for model_id, adapter in adapters.items()
        if model_id in passing
    }
    if len(selected) != 10:
        raise ConfigurationError("RC1.3 did not resolve all ten inherited adapters")
    return selected


__all__ = [
    "INHERITANCE_PATH",
    "create_rc13_compatibility_inheritance",
    "load_rc13_compatible_adapters",
]

"""Compatibility inheritance and the one authorized Qwen retry for RC1.1."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256, sha256_file
from uc_bench.mmmvp_blind_interface import serialized_open_request
from uc_bench.mmmvp_open_compatibility import CompatibilityBudget, run_one_open_canary
from uc_bench.mmmvp_open_freeze import read_open_mmmvp_freeze
from uc_bench.mmmvp_open_provider import load_open_route_contract_adapters
from uc_bench.mmmvp_open_rc11_freeze import read_rc11_release_freeze
from uc_bench.model_runner import _write_json
from uc_bench.v071_auth import credential_locations

INHERITANCE_PATH = Path("artifacts/mmmvp_open_rc11/inherited_compatibility.json")
RESULTS_PATH = Path("artifacts/mmmvp_open_rc11/compatibility_results.json")
ATTEMPTS_ROOT = Path("artifacts/mmmvp_open_rc11/compatibility_attempts")
OLD_RESULTS_PATH = Path("artifacts/mmmvp_open_release/compatibility_results.json")
QWEN_MODEL_ID = "qwen/qwen3.5-397b-a17b"
QWEN_RETRY_CAP_USD = 0.25
QWEN_BACKOFF_SECONDS = 5.0

_INHERITED_IMPLEMENTATION_FILES = (
    "configs/uc_bench_mmmvp_open_model_panel.json",
    "artifacts/mmmvp_open_release/route_contracts.json",
    "src/uc_bench/mmmvp_open_provider.py",
    "src/uc_bench/mmmvp_open_compatibility.py",
    "src/uc_bench/mmmvp_provider.py",
    "src/uc_bench/v071_auth.py",
    "src/uc_bench/v062_provider.py",
    "src/uc_bench/v061_provider.py",
    "src/uc_bench/v06_provider.py",
    "src/uc_bench/mmmvp_blind_interface.py",
)


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError(f"Expected object: {path}")
    return value


def compatibility_identity(project_root: Path) -> dict[str, Any]:
    """Hash every compatibility property authorized for inheritance."""

    root = project_root.resolve()
    scientific = read_open_mmmvp_freeze(root)
    adapters = load_open_route_contract_adapters(root)
    request = serialized_open_request()
    implementation_hashes = {
        relative: sha256_file(root / relative) for relative in _INHERITED_IMPLEMENTATION_FILES
    }
    models: dict[str, Any] = {}
    for model_id, adapter in adapters.items():
        adapter_value = adapter.to_dict()
        models[model_id] = {
            "adapter_sha256": canonical_sha256(adapter_value),
            "provider_pin_sha256": canonical_sha256(
                {
                    "model_id": model_id,
                    "canonical_slug": adapter.expected_canonical_slug,
                    "provider_order": list(adapter.provider_order),
                    "allow_fallbacks": adapter.allow_fallbacks,
                    "endpoint_contract_digest": adapter.endpoint_contract_digest,
                }
            ),
            "sampling_configuration_sha256": canonical_sha256(
                adapter.sampling_args(maximum_completion_tokens=5000)
            ),
            "reasoning_state_sha256": canonical_sha256(
                {
                    "requested_reasoning_effort": adapter.requested_reasoning_effort,
                    "reasoning_mode": adapter.reasoning_mode,
                    "preserve_reasoning_state": adapter.preserve_reasoning_state,
                }
            ),
        }
    return {
        "scientific_freeze_digest": scientific["hash_set_digest"],
        "serialized_request_sha256": canonical_sha256(request),
        "frozen_serialized_request_sha256": scientific["serialized_request_sha256"],
        "tool_schema_sha256": canonical_sha256(request["tools"]),
        "implementation_hashes": implementation_hashes,
        "implementation_digest": canonical_sha256(implementation_hashes),
        "models": models,
    }


def create_compatibility_inheritance(project_root: Path) -> dict[str, Any]:
    """Prove which RC1 canaries may be inherited without a model request."""

    root = project_root.resolve()
    target = root / INHERITANCE_PATH
    if target.exists():
        raise ConfigurationError("RC1.1 compatibility inheritance already exists")
    old = _read(root / OLD_RESULTS_PATH)
    if old.get("status") != "passed" or old.get("scientific_requests") != 0:
        raise ConfigurationError("RC1 compatibility evidence is not clean")
    identity = compatibility_identity(root)
    if identity["serialized_request_sha256"] != identity["frozen_serialized_request_sha256"]:
        raise ConfigurationError("Serialized RC1 request changed")
    adapters = load_open_route_contract_adapters(root)
    inherited: list[dict[str, Any]] = []
    original_qwen: dict[str, Any] | None = None
    for row in old.get("results") or []:
        model_id = str(row.get("model_id"))
        if model_id == QWEN_MODEL_ID:
            original_qwen = row
            continue
        if row.get("classification") != "compatible":
            raise ConfigurationError(f"Unexpected non-Qwen compatibility failure: {model_id}")
        current = adapters[model_id]
        if row.get("adapter") != current.to_dict():
            raise ConfigurationError(f"Inherited adapter changed: {model_id}")
        if row.get("actual_providers") != list(current.provider_order):
            raise ConfigurationError(f"Inherited serving provider differs: {model_id}")
        inherited.append({**row, "inheritance": "exact_rc1_evidence"})
    if len(inherited) != 9 or original_qwen is None:
        raise ConfigurationError("Expected nine RC1 passes and one preserved Qwen failure")
    error = original_qwen.get("error") or {}
    if (
        original_qwen.get("cost_usd") != 0
        or "429" not in str(error.get("message") or "")
        or original_qwen.get("classification") != "incompatible"
    ):
        raise ConfigurationError("Original Qwen failure is not the authorized zero-cost 429")
    value = {
        "schema_version": "uc-bench-open-mmmvp-rc1-1-compatibility-inheritance-1",
        "created_at": datetime.now(UTC).isoformat(),
        "api_requests": 0,
        "scientific_requests": 0,
        "status": "passed",
        "identity": identity,
        "inherited_model_count": len(inherited),
        "inherited_results": inherited,
        "original_qwen_failure": original_qwen,
        "qwen_retry_authorized": True,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    _write_json(target, value, secret="")
    return value


def load_rc11_compatible_adapters(project_root: Path) -> dict[str, Any]:
    """Return only models with inherited or fresh RC1.1 compatibility evidence."""

    root = project_root.resolve()
    adapters = load_open_route_contract_adapters(root)
    results = _read(root / RESULTS_PATH)
    passing = {
        str(row["model_id"])
        for row in results.get("results") or []
        if row.get("classification") == "compatible"
    }
    return {model_id: adapter for model_id, adapter in adapters.items() if model_id in passing}


def retry_qwen_and_finalize_compatibility(
    project_root: Path,
    *,
    key: str,
    authorization_digest: str,
) -> dict[str, Any]:
    """Run exactly one same-route Qwen canary and finalize RC1.1 compatibility."""

    root = project_root.resolve()
    release = read_rc11_release_freeze(root)
    if authorization_digest != release["infrastructure_digest"]:
        raise ConfigurationError("Qwen retry authorization differs from the RC1.1 freeze")
    target = root / RESULTS_PATH
    if target.exists() or (root / ATTEMPTS_ROOT).exists():
        raise ConfigurationError("The one authorized RC1.1 Qwen retry was already used")
    inheritance = _read(root / INHERITANCE_PATH)
    if inheritance.get("status") != "passed" or not inheritance.get("qwen_retry_authorized"):
        raise ConfigurationError("Qwen retry inheritance gate did not pass")
    if compatibility_identity(root) != inheritance["identity"]:
        raise ConfigurationError("Compatibility identity changed after inheritance")

    output_root = root / ATTEMPTS_ROOT
    output_root.mkdir(parents=True, exist_ok=False)
    budget = CompatibilityBudget(hard_cap_usd=QWEN_RETRY_CAP_USD)
    time.sleep(QWEN_BACKOFF_SECONDS)
    retry = asyncio.run(
        run_one_open_canary(
            root,
            key=key,
            model_id=QWEN_MODEL_ID,
            output_root=output_root,
            budget=budget,
            attempt_index=1,
        )
    )
    if retry.get("adapter", {}).get("provider_order") != ["DeepInfra"]:
        raise ConfigurationError("Qwen retry route changed from DeepInfra")
    if retry.get("cost_usd", 0.0) > QWEN_RETRY_CAP_USD + 1e-9:
        raise ConfigurationError("Qwen retry exceeded its hard cap")

    results = list(inheritance["inherited_results"])
    results.append({**retry, "inheritance": "fresh_rc11_retry"})
    compatible = [row for row in results if row.get("classification") == "compatible"]
    value = {
        "schema_version": "uc-bench-open-mmmvp-rc1-1-compatibility-1",
        "executed_at": datetime.now(UTC).isoformat(),
        "status": "passed" if len(compatible) >= 8 else "stopped_insufficient_compatibility",
        "scientific_freeze_digest": release["scientific_freeze_digest"],
        "release_infrastructure_digest": release["infrastructure_digest"],
        "inherited_model_count": 9,
        "qwen_retry_count": 1,
        "qwen_original_failure_preserved": True,
        "qwen_retry_backoff_seconds": QWEN_BACKOFF_SECONDS,
        "compatible_model_count": len(compatible),
        "incompatible_model_count": len(results) - len(compatible),
        "hard_cap_usd": QWEN_RETRY_CAP_USD,
        "cost_usd": round(budget.reported_spend_usd, 8),
        "scientific_requests": 0,
        "heldout_requests": 0,
        "astra_requests": 0,
        "results": results,
    }
    _write_json(target, value, secret=key)
    if credential_locations(root / "artifacts/mmmvp_open_rc11", key):
        raise ConfigurationError("Credential appeared in RC1.1 compatibility artifacts")
    return value


__all__ = [
    "INHERITANCE_PATH",
    "QWEN_MODEL_ID",
    "QWEN_RETRY_CAP_USD",
    "RESULTS_PATH",
    "compatibility_identity",
    "create_compatibility_inheritance",
    "load_rc11_compatible_adapters",
    "retry_qwen_and_finalize_compatibility",
]

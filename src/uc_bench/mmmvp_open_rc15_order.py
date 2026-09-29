"""Randomized compatible-panel order generation for RC1.5."""

from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256
from uc_bench.mmmvp_open_rc15_adapter import load_rc15_launch_routes

ORDER_PATH = Path("artifacts/mmmvp_open_rc15/sentinel_order.json")


def order_record(
    model_ids: list[str],
    *,
    release_infrastructure_digest: str,
    entropy: bytes,
) -> dict[str, Any]:
    if len(entropy) != 32:
        raise ConfigurationError("RC1.5 order requires exactly 256 bits of entropy")
    if len(model_ids) != 9 or len(set(model_ids)) != 9:
        raise ConfigurationError("RC1.5 order requires nine distinct compatible models")
    execution_order = sorted(
        model_ids,
        key=lambda model: canonical_sha256(
            {"entropy": entropy.hex(), "model_id": model}
        ),
    )
    return {
        "schema_version": "uc-bench-open-mmmvp-rc1-5-sentinel-order-1",
        "created_at": datetime.now(UTC).isoformat(),
        "method": "host_csprng_256_bit_entropy_then_sha256_sort",
        "entropy_commitment_sha256": canonical_sha256(entropy.hex()),
        "execution_order": execution_order,
        "model_count": len(execution_order),
        "technically_compatible_models_only": True,
        "release_infrastructure_digest": release_infrastructure_digest,
    }


def persist_order(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        raise ConfigurationError(f"RC1.5 order already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def create_rc15_sentinel_order(project_root: Path) -> dict[str, Any]:
    from uc_bench.mmmvp_open_rc15_freeze import read_rc15_release_freeze

    root = project_root.resolve()
    release = read_rc15_release_freeze(root)
    routes = load_rc15_launch_routes(root)
    value = order_record(
        list(routes),
        release_infrastructure_digest=release["infrastructure_digest"],
        entropy=secrets.token_bytes(32),
    )
    persist_order(root / ORDER_PATH, value)
    return value


__all__ = [
    "ORDER_PATH",
    "create_rc15_sentinel_order",
    "order_record",
    "persist_order",
]

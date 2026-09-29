"""One-time random, recorded execution order for the RC1.4 sentinel."""

from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256
from uc_bench.mmmvp_open_rc14_harness import load_converged_rc14_adapters

ORDER_PATH = Path("artifacts/mmmvp_open_rc14/sentinel_order.json")


def create_rc14_sentinel_order(project_root: Path) -> dict[str, Any]:
    from uc_bench.mmmvp_open_rc14_freeze import read_rc14_release_freeze

    root = project_root.resolve()
    target = root / ORDER_PATH
    if target.exists():
        raise ConfigurationError("RC1.4 sentinel order already exists")
    models = list(load_converged_rc14_adapters(root))
    release = read_rc14_release_freeze(root)
    random_bytes = secrets.token_bytes(32)
    decorated = sorted(
        models,
        key=lambda model: canonical_sha256(
            {"entropy": random_bytes.hex(), "model_id": model}
        ),
    )
    value = {
        "schema_version": "uc-bench-open-mmmvp-rc1-4-sentinel-order-1",
        "created_at": datetime.now(UTC).isoformat(),
        "method": "host_csprng_256_bit_entropy_then_sha256_sort",
        "entropy_commitment_sha256": canonical_sha256(random_bytes.hex()),
        "execution_order": decorated,
        "model_count": len(decorated),
        "technically_compatible_models_only": True,
        "release_infrastructure_digest": release["infrastructure_digest"],
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(target)
    return value


__all__ = ["ORDER_PATH", "create_rc14_sentinel_order"]

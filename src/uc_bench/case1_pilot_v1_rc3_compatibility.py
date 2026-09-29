"""Zero-network RC3 compatibility inheritance and provider-surface parity."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.case1_pilot_v1_rc2_compatibility import (
    RC1_COMPATIBILITY_ROOT,
    replay_preserved_compatibility,
)
from uc_bench.case1_pilot_v1_rc3_interface import production_request
from uc_bench.case1_pilot_v1_runner import Case1PilotRunConfig
from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256
from uc_bench.model_runner import _write_json

RC3_ROOT = Path("artifacts/uc_bench_case1_pilot_v1_rc3")
OFFLINE_REPLAY_PATH = RC3_ROOT / "offline_compatibility_replay.json"


def replay_rc3_compatibility(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    rc2 = replay_preserved_compatibility(root)
    expected_digest = canonical_sha256(
        production_request(
            Case1PilotRunConfig("compatibility", "google/gemini-3.1-pro-preview")
        )["tools"]
    )
    results: list[dict[str, Any]] = []
    for row in rc2["results"]:
        original_path = root / row["evidence_paths"]["original_result"]
        original = json.loads(original_path.read_text(encoding="utf-8"))
        digest = original.get("production_tool_schema_sha256")
        results.append(
            {
                "model_id": row["model_id"],
                "rc1_original_classification": row["original_rc1_classification"],
                "rc2_corrected_classification": row["corrected_rc2_classification"],
                "rc3_classification": (
                    "technically_compatible"
                    if row["corrected_rc2_classification"] == "technically_compatible"
                    and digest == expected_digest
                    else "incompatible"
                ),
                "preserved_provider_tool_schema_sha256": digest,
                "rc3_provider_tool_schema_sha256": expected_digest,
                "provider_visible_schema_unchanged": digest == expected_digest,
                "request_count": row["request_count"],
                "evidence_paths": row["evidence_paths"],
            }
        )
    passed = bool(
        rc2["status"] == "passed"
        and len(results) == 5
        and all(row["rc3_classification"] == "technically_compatible" for row in results)
    )
    return {
        "schema_version": "uc-bench-case1-pilot-v1-rc3-compatibility-replay-1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "passed" if passed else "failed",
        "new_api_requests": 0,
        "new_compatibility_spend_usd": 0.0,
        "provider_visible_schema_unchanged": all(
            row["provider_visible_schema_unchanged"] for row in results
        ),
        "compatible_count": sum(
            row["rc3_classification"] == "technically_compatible" for row in results
        ),
        "tool_schema_sha256": expected_digest,
        "source_results_sha256": hashlib.sha256(
            (root / RC1_COMPATIBILITY_ROOT / "results.json").read_bytes()
        ).hexdigest(),
        "results": results,
    }


def write_rc3_compatibility_replay(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    target = root / OFFLINE_REPLAY_PATH
    if target.exists():
        raise ConfigurationError("RC3 compatibility replay already exists")
    value = replay_rc3_compatibility(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    _write_json(target, value, secret="")
    if value["status"] != "passed":
        raise ConfigurationError("RC3 compatibility inheritance did not pass")
    return value


__all__ = ["OFFLINE_REPLAY_PATH", "replay_rc3_compatibility", "write_rc3_compatibility_replay"]

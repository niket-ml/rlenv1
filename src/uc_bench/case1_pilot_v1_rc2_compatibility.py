"""Zero-network re-adjudication of the five immutable RC1 compatibility ledgers."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.case1_pilot_v1_provider import (
    load_case1_pilot_adapters,
    load_case1_pilot_config,
)
from uc_bench.case1_pilot_v1_rc2_identity import adjudicate_exact_identity
from uc_bench.case1_pilot_v1_release import FREEZE_PATH as RC1_FREEZE_PATH
from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256
from uc_bench.model_runner import _write_json

RC1_COMPATIBILITY_ROOT = Path("artifacts/uc_bench_case1_pilot_v1_rc1/compatibility")
RC2_ROOT = Path("artifacts/uc_bench_case1_pilot_v1_rc2")
OFFLINE_REPLAY_PATH = RC2_ROOT / "offline_compatibility_replay.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rc1_immutable_evidence_hashes(project_root: Path) -> dict[str, str]:
    root = project_root.resolve()
    paths = [root / RC1_FREEZE_PATH]
    paths.extend(
        path for path in (root / RC1_COMPATIBILITY_ROOT).rglob("*") if path.is_file()
    )
    if not all(path.is_file() for path in paths):
        raise ConfigurationError("RC1 freeze or compatibility evidence is missing")
    return {
        path.relative_to(root).as_posix(): _sha256(path) for path in sorted(set(paths))
    }


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError(f"Expected JSON object: {path}")
    return value


def _model_evidence(root: Path, model_id: str) -> dict[str, Any]:
    model_root = root / RC1_COMPATIBILITY_ROOT / "attempts" / model_id.replace("/", "--")
    latest = _read(model_root / "host_trajectory/latest.json")
    ledger = _read(model_root / "request_ledger.json")
    original = _read(model_root / "result.json")
    raw = [
        dict(exchange["raw_response"])
        for exchange in latest.get("provider_exchanges") or []
        if isinstance(exchange, dict) and isinstance(exchange.get("raw_response"), dict)
    ]
    records = [dict(row) for row in ledger.get("requests") or [] if isinstance(row, dict)]
    return {
        "model_root": model_root,
        "latest": latest,
        "ledger": ledger,
        "original": original,
        "raw_responses": raw,
        "request_records": records,
    }


def replay_preserved_compatibility(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    config = load_case1_pilot_config(root)
    adapters = load_case1_pilot_adapters(root)
    original_panel = _read(root / RC1_COMPATIBILITY_ROOT / "results.json")
    if original_panel.get("status") != "shared_stop":
        raise ConfigurationError("RC1 compatibility result is not the preserved shared stop")
    results: list[dict[str, Any]] = []
    for model_id in config["execution_order"]:
        evidence = _model_evidence(root, model_id)
        adapter = adapters[model_id]
        original = evidence["original"]
        identity = adjudicate_exact_identity(
            requested_model=model_id,
            canonical_alias=adapter.expected_canonical_slug,
            pinned_provider=adapter.provider_order[0],
            fallback_disabled=not adapter.allow_fallbacks,
            request_records=evidence["request_records"],
            raw_responses=evidence["raw_responses"],
        )
        technical = {
            name: bool(original.get(name))
            for name in (
                "tool_invocation_recorded",
                "tool_result_ingested",
                "restart_replay_exact",
                "submission_tool_observed",
                "final_response_recorded",
                "tool_arguments_parseable",
                "usage_accounting",
                "synthetic_neutral_content",
            )
        }
        technical["case_data_absent"] = original.get("case_data_in_request") is False
        technical["production_fallback_disabled"] = original.get("fallback_disabled") is True
        corrected = bool(identity["compatible"] and all(technical.values()))
        results.append(
            {
                "model_id": model_id,
                "original_rc1_classification": original.get("classification"),
                "corrected_rc2_classification": (
                    "technically_compatible" if corrected else "incompatible"
                ),
                "identity": identity,
                "technical_invariants": technical,
                "request_count": len(evidence["request_records"]),
                "new_api_requests": 0,
                "evidence_paths": {
                    "ledger": (evidence["model_root"] / "request_ledger.json")
                    .relative_to(root)
                    .as_posix(),
                    "trajectory": (evidence["model_root"] / "host_trajectory/latest.json")
                    .relative_to(root)
                    .as_posix(),
                    "original_result": (evidence["model_root"] / "result.json")
                    .relative_to(root)
                    .as_posix(),
                },
            }
        )
    hashes = rc1_immutable_evidence_hashes(root)
    passed = bool(
        len(results) == 5
        and all(row["original_rc1_classification"] == "shared_harness_failure" for row in results)
        and all(row["corrected_rc2_classification"] == "technically_compatible" for row in results)
    )
    return {
        "schema_version": "uc-bench-case1-pilot-v1-rc2-offline-compatibility-1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "passed" if passed else "failed",
        "original_rc1_panel_status": original_panel.get("status"),
        "corrected_rc2_panel_status": "passed" if passed else "failed",
        "original_rc1_shared_checker_failure_count": sum(
            row["original_rc1_classification"] == "shared_harness_failure" for row in results
        ),
        "corrected_rc2_compatible_count": sum(
            row["corrected_rc2_classification"] == "technically_compatible" for row in results
        ),
        "new_api_requests": 0,
        "new_compatibility_spend_usd": 0.0,
        "preserved_rc1_evidence_hashes": hashes,
        "preserved_rc1_evidence_digest": canonical_sha256(hashes),
        "results": results,
    }


def write_offline_replay(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    target = root / OFFLINE_REPLAY_PATH
    if target.exists():
        raise ConfigurationError("RC2 offline compatibility replay already exists")
    value = replay_preserved_compatibility(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    _write_json(target, value, secret="")
    if value["status"] != "passed":
        raise ConfigurationError("RC2 offline compatibility replay did not pass")
    return value


__all__ = [
    "OFFLINE_REPLAY_PATH",
    "RC1_COMPATIBILITY_ROOT",
    "RC2_ROOT",
    "rc1_immutable_evidence_hashes",
    "replay_preserved_compatibility",
    "write_offline_replay",
]

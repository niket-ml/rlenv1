#!/usr/bin/env python3
"""Analyze v0.6.1 using the unchanged predeclared v0.6 ceiling rules."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from analyze_v06_probe import render_report

from uc_bench.errors import ConfigurationError
from uc_bench.v06_probe_analysis import analyze_v06_probe
from uc_bench.v061_freeze import read_v061_freeze_manifest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = PROJECT_ROOT / "artifacts/diagnostics/hard_suite_v061_calibration_runs.json"
OUTPUT_PATH = PROJECT_ROOT / "artifacts/diagnostics/hard_suite_v061_probe_analysis.json"
REPORT_PATH = PROJECT_ROOT / "reports/generated/hard_suite_v061_probe_report.md"


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError(f"Expected object: {path}")
    return value


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    freeze = read_v061_freeze_manifest(PROJECT_ROOT)
    checkpoint = _read(INPUT_PATH)
    config = _read(PROJECT_ROOT / "configs/hard_suite_v06.json")
    panel = _read(PROJECT_ROOT / "configs/hard_suite_v06_model_panel.json")
    execution = _read(PROJECT_ROOT / "configs/hard_suite_v061_execution.json")
    if checkpoint.get("strategy") != "sentinel":
        raise ConfigurationError("This report requires the v0.6.1 sentinel checkpoint")
    if checkpoint.get("heldout_requests") != 0 or checkpoint.get("astra_requests") != 0:
        raise ConfigurationError("Held-out or Astra exposure entered v0.6.1")
    analysis = analyze_v06_probe(
        checkpoint.get("runs") or [],
        config=config,
        model_ids=[str(row["model_id"]) for row in panel["models"]],
        scenario_ids=list(execution["sentinel"]["scenario_ids"]),
        project_root=PROJECT_ROOT,
    )
    analysis.update(
        {
            "schema_version": "0.6.1-probe-analysis-1",
            "generated_at": datetime.now(UTC).isoformat(),
            "runner_revision": "0.6.1",
            "scientific_contract_revision": "0.6-byte-identical",
            "freeze_hash_set_digest": freeze["hash_set_digest"],
            "response_reported_spend_usd": checkpoint.get(
                "response_reported_spend_usd"
            ),
            "key_usage_delta_usd": checkpoint.get("key_usage_delta_usd"),
            "heldout_requests": 0,
            "astra_requests": 0,
        }
    )
    _write(OUTPUT_PATH, json.dumps(analysis, indent=2, sort_keys=True) + "\n")
    report = render_report(analysis).replace(
        "UC-Bench v0.6 controlled", "UC-Bench v0.6.1 controlled", 1
    )
    _write(REPORT_PATH, report)
    print(json.dumps(analysis, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

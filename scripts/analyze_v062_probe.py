#!/usr/bin/env python3
"""Analyze v0.6.2 using the unchanged predeclared v0.6 ceiling rules."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from analyze_v06_probe import render_report

from uc_bench.errors import ConfigurationError
from uc_bench.v06_probe_analysis import analyze_v06_probe
from uc_bench.v062_freeze import read_v062_freeze_manifest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNS_PATH = PROJECT_ROOT / "artifacts/diagnostics/hard_suite_v062_calibration_runs.json"
ANALYSIS_PATH = PROJECT_ROOT / "artifacts/diagnostics/hard_suite_v062_probe_analysis.json"
REPORT_PATH = PROJECT_ROOT / "reports/generated/hard_suite_v062_probe.md"


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError(f"Expected object: {path}")
    return value


def main() -> int:
    manifest = read_v062_freeze_manifest(PROJECT_ROOT)
    checkpoint = _read(RUNS_PATH)
    config = _read(PROJECT_ROOT / "configs/hard_suite_v06.json")
    panel = _read(PROJECT_ROOT / "configs/hard_suite_v06_model_panel.json")
    execution = _read(PROJECT_ROOT / "configs/hard_suite_v062_execution.json")
    analysis = analyze_v06_probe(
        checkpoint.get("runs") or [],
        config=config,
        model_ids=[str(row["model_id"]) for row in panel["models"]],
        scenario_ids=list(execution["sentinel"]["scenario_ids"]),
        project_root=PROJECT_ROOT,
    )
    analysis.update(
        {
            "schema_version": "0.6.2-probe-analysis-1",
            "generated_at": datetime.now(UTC).isoformat(),
            "freeze_hash_set_digest": manifest["hash_set_digest"],
            "runner_revision": "0.6.2",
            "scientific_contract_revision": "0.6-byte-identical",
            "checkpoint_status": checkpoint.get("status"),
            "spend": {
                "scientific_response_reported_usd": checkpoint.get(
                    "response_reported_spend_usd"
                ),
                "scientific_key_usage_delta_usd": checkpoint.get(
                    "key_usage_delta_usd"
                ),
            },
        }
    )
    ANALYSIS_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = ANALYSIS_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(analysis, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(ANALYSIS_PATH)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(render_report(analysis), encoding="utf-8")
    print(json.dumps(analysis, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

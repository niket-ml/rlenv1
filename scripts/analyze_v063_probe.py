#!/usr/bin/env python3
"""Analyze v0.6.3 with the unchanged predeclared scientific gates."""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from analyze_v06_probe import render_report

from uc_bench.errors import ConfigurationError
from uc_bench.v06_probe_analysis import analyze_v06_probe
from uc_bench.v063_freeze import read_v063_freeze_manifest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNS_PATH = PROJECT_ROOT / "artifacts/diagnostics/hard_suite_v063_calibration_runs.json"
ANALYSIS_PATH = PROJECT_ROOT / "artifacts/diagnostics/hard_suite_v063_probe_analysis.json"
REPORT_PATH = PROJECT_ROOT / "reports/generated/hard_suite_v063_probe.md"


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError(f"Expected object: {path}")
    return value


def main() -> int:
    manifest = read_v063_freeze_manifest(PROJECT_ROOT)
    checkpoint = _read(RUNS_PATH)
    config = _read(PROJECT_ROOT / "configs/hard_suite_v06.json")
    panel = _read(PROJECT_ROOT / "configs/hard_suite_v06_model_panel.json")
    execution = _read(PROJECT_ROOT / "configs/hard_suite_v063_execution.json")
    rows = checkpoint.get("runs") or []
    analysis = analyze_v06_probe(
        rows,
        config=config,
        model_ids=[str(row["model_id"]) for row in panel["models"]],
        scenario_ids=list(execution["sentinel"]["scenario_ids"]),
        project_root=PROJECT_ROOT,
    )
    failure_counts = Counter(str(row.get("classification")) for row in rows)
    analysis.update(
        {
            "schema_version": "0.6.3-probe-analysis-1",
            "generated_at": datetime.now(UTC).isoformat(),
            "freeze_hash_set_digest": manifest["hash_set_digest"],
            "runner_revision": "0.6.3",
            "scientific_contract_revision": (
                "0.6-tasks-prompts-thresholds-and-scoring-invariants"
            ),
            "checkpoint_status": checkpoint.get("status"),
            "checkpoint_stop_reason": checkpoint.get("stop_reason"),
            "failure_class_counts": dict(sorted(failure_counts.items())),
            "infrastructure_exclusions": [
                row
                for row in rows
                if row.get("classification")
                in {
                    "infrastructure_failure",
                    "provider_adapter_failure",
                    "provider_policy_refusal",
                    "unknown_harness_failure",
                    "grader_infrastructure_failure",
                    "post_rollout_infrastructure_failure",
                }
            ],
            "spend": {
                "v063_response_reported_usd": checkpoint.get(
                    "response_reported_spend_usd"
                ),
                "v063_key_usage_delta_usd": checkpoint.get("key_usage_delta_usd"),
                "predecessor_v062_response_reported_usd": 0.4286534,
                "aggregate_response_reported_usd": checkpoint.get(
                    "aggregate_scientific_spend_usd"
                ),
                "aggregate_authorized_cap_usd": 56.0,
            },
            "claims": {
                "controlled_internal_calibration_only": True,
                "stable_ranking_allowed": False,
                "external_expert_validation_present": False,
                "authentic_geo_anchor_separate": True,
                "heldout_or_astra_used": False,
            },
        }
    )
    ANALYSIS_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = ANALYSIS_PATH.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(analysis, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(ANALYSIS_PATH)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    prefix = (
        "# UC-Bench v0.6.3 controlled sentinel\n\n"
        "This is a one-seed development diagnostic, not a stable ranking. v0.6.2 "
        "is separately preserved as a grader-infrastructure no-go.\n\n"
    )
    REPORT_PATH.write_text(prefix + render_report(analysis), encoding="utf-8")
    print(json.dumps(analysis, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

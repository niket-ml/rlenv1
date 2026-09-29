#!/usr/bin/env python3
"""Validate scored trajectory rows and produce repeated-evaluation summaries."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from uc_bench.evaluation import (
    EpisodeScoreRow,
    paired_condition_lift,
    rank_first_probabilities,
    summarize_groups,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = PROJECT_ROOT / "trajectories" / "episode_scores.jsonl"
OUTPUT_PATH = PROJECT_ROOT / "reports" / "generated" / "evaluation_summary.json"


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def main() -> int:
    protocol = read_json(PROJECT_ROOT / "configs" / "evaluation_protocol.json")
    if not INPUT_PATH.is_file() or not INPUT_PATH.read_text(encoding="utf-8").strip():
        result = {
            "schema_version": "0.1",
            "status": "not_run",
            "input_path": INPUT_PATH.relative_to(PROJECT_ROOT).as_posix(),
            "valid_episode_rows": 0,
            "model_ranking_available": False,
            "reason": "No real scored model trajectories are present.",
            "blocking_findings": ["AF-007", "AF-005"],
        }
    else:
        rows = [
            EpisodeScoreRow.from_dict(json.loads(line))
            for line in INPUT_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        infrastructure_failures = sum(row.infrastructure_failure for row in rows)
        summaries = summarize_groups(
            rows,
            bootstrap_resamples=int(protocol["bootstrap_resamples"]),
            seed=20260906,
            floor_threshold=float(protocol["floor_threshold"]),
            ceiling_threshold=float(protocol["ceiling_threshold"]),
        )
        result = {
            "schema_version": "0.1",
            "status": "complete",
            "valid_episode_rows": len(rows) - infrastructure_failures,
            "infrastructure_failure_rows": infrastructure_failures,
            "group_summaries": summaries,
            "paired_condition_lift": paired_condition_lift(rows),
            "rank_first_probability": rank_first_probabilities(
                rows,
                condition="full_data",
                scenario_family=protocol["headline_scenario_family"],
                resamples=int(protocol["bootstrap_resamples"]),
                seed=20260907,
            ),
            "model_ranking_available": len({row.model_id for row in rows}) >= 2,
        }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

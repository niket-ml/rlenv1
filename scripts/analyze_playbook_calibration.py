#!/usr/bin/env python3
"""Analyze paired playbook effects without treating them as SFT evidence."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

from uc_bench.hashing import sha256_file

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_PATH = PROJECT_ROOT / "artifacts" / "diagnostics" / "playbook_calibration_runs.json"
OUTPUT_PATH = PROJECT_ROOT / "artifacts" / "diagnostics" / "playbook_calibration_analysis.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "generated" / "playbook_calibration.md"


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected JSON object: {path}")
    return value


def paired_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        if row["classification"] == "infrastructure_failure":
            continue
        key = (
            str(row["model_id"]),
            str(row["task_type"]),
            str(row["task_id"]),
            str(row["scenario_id"]),
        )
        grouped[key][str(row["condition"])] = row
    output = []
    for key, conditions in grouped.items():
        if set(conditions) != {"base", "expert_playbook"}:
            raise ValueError(f"Incomplete intervention pair: {key}")
        base = conditions["base"]
        playbook = conditions["expert_playbook"]
        output.append(
            {
                "model_id": key[0],
                "task_type": key[1],
                "task_id": key[2],
                "scenario_id": key[3],
                "base_score": float(base["score"]),
                "playbook_score": float(playbook["score"]),
                "paired_delta": float(playbook["score"]) - float(base["score"]),
                "base_classification": base["classification"],
                "playbook_classification": playbook["classification"],
                "base_turn_count": int(base["turn_count"]),
                "playbook_turn_count": int(playbook["turn_count"]),
            }
        )
    return sorted(
        output,
        key=lambda row: (
            row["model_id"],
            row["task_type"],
            row["task_id"],
            row["scenario_id"],
        ),
    )


def model_summaries(pairs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    model_ids = list(dict.fromkeys(str(row["model_id"]) for row in pairs))
    return [
        {
            "model_id": model_id,
            "pair_count": len(selected),
            "base_mean": mean(float(row["base_score"]) for row in selected),
            "playbook_mean": mean(float(row["playbook_score"]) for row in selected),
            "mean_paired_delta": mean(float(row["paired_delta"]) for row in selected),
            "improved_pair_count": sum(float(row["paired_delta"]) > 0 for row in selected),
            "unchanged_pair_count": sum(float(row["paired_delta"]) == 0 for row in selected),
            "worsened_pair_count": sum(float(row["paired_delta"]) < 0 for row in selected),
        }
        for model_id in model_ids
        for selected in [[row for row in pairs if row["model_id"] == model_id]]
    ]


def render_report(output: dict[str, Any]) -> str:
    lines = [
        "# Expert-playbook paired calibration",
        "",
        "> One attempt per condition. This tests a prompting/playbook intervention; it does "
        "not establish that SFT, RLHF, or pretraining changes are needed.",
        "",
        "| model | base | playbook | paired delta | improved / same / worsened |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in output["model_summaries"]:
        lines.append(
            f"| {row['model_id']} | {row['base_mean']:.2f} | "
            f"{row['playbook_mean']:.2f} | {row['mean_paired_delta']:+.2f} | "
            f"{row['improved_pair_count']} / {row['unchanged_pair_count']} / "
            f"{row['worsened_pair_count']} |"
        )
    lines.extend(
        [
            "",
            "The effect is heterogeneous: the scaffold can improve short local reasoning "
            "while consuming enough workflow horizon to make another model fail to submit. "
            "That makes playbook prompting a measured intervention, not a default remedy.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    raw = read_json(RAW_PATH)
    pairs = paired_rows(list(raw["runs"]))
    summaries = model_summaries(pairs)
    output = {
        "schema_version": "0.1",
        "status": "paired_calibration_not_causal_training_claim",
        "raw_artifact": RAW_PATH.relative_to(PROJECT_ROOT).as_posix(),
        "raw_artifact_sha256": sha256_file(RAW_PATH),
        "intervention_class": "model_adaptation",
        "intervention": "prompting_playbook",
        "pair_count": len(pairs),
        "attempts_per_condition": 1,
        "ranking_claim_allowed": False,
        "sft_or_rlhf_claim_allowed": False,
        "model_summaries": summaries,
        "paired_results": pairs,
    }
    OUTPUT_PATH.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    REPORT_PATH.write_text(render_report(output), encoding="utf-8")
    print(json.dumps(summaries, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Combine independently frozen calibration slices without making a ranking claim."""

from __future__ import annotations

import json
from itertools import pairwise
from pathlib import Path
from typing import Any

from uc_bench.hashing import sha256_file

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKET_PATH = PROJECT_ROOT / "artifacts" / "diagnostics" / "packet_calibration_analysis.json"
DATA_PATH = PROJECT_ROOT / "artifacts" / "diagnostics" / "data_task_calibration_analysis.json"
OUTPUT_PATH = PROJECT_ROOT / "artifacts" / "diagnostics" / "combined_calibration_analysis.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "generated" / "combined_calibration.md"


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected JSON object: {path}")
    return value


def combine_model_summaries(packet: dict[str, Any], data: dict[str, Any]) -> list[dict[str, Any]]:
    packet_rows = {row["model_id"]: row for row in packet["model_summaries"]}
    data_rows = {row["model_id"]: row for row in data["model_summaries"]}
    if set(packet_rows) != set(data_rows):
        raise ValueError("Calibration slices have different model sets")
    output = []
    for model_id in packet_rows:
        packet_row = packet_rows[model_id]
        data_row = data_rows[model_id]
        packet_n = int(packet_row["n"])
        data_n = int(data_row["attempt_count"])
        combined = (
            float(packet_row["score_mean"]) * packet_n
            + float(data_row["mean_attempt_score"]) * data_n
        ) / (packet_n + data_n)
        output.append(
            {
                "model_id": model_id,
                "tier": packet_row["tier"],
                "decision_packet_mean": float(packet_row["score_mean"]),
                "decision_packet_n": packet_n,
                "executable_data_mean": float(data_row["mean_attempt_score"]),
                "executable_data_n": data_n,
                "combined_calibration_mean": combined,
                "combined_n": packet_n + data_n,
                "data_valid_episode_rate": float(data_row["valid_episode_rate"]),
                "packet_failure_signatures": packet_row["failure_signatures"],
                "data_failure_signatures": data_row["failure_signatures"],
            }
        )
    return output


def render_report(output: dict[str, Any]) -> str:
    lines = [
        "# Combined v0 calibration view",
        "",
        "> CALIBRATION ONLY — 14 frozen cells per model, one attempt per cell. This is "
        "not a leaderboard or statistically supported model ranking.",
        "",
        "| model | decision packets | executable data | combined | data completion |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in output["model_summaries"]:
        lines.append(
            f"| {row['model_id']} | {row['decision_packet_mean']:.2f} | "
            f"{row['executable_data_mean']:.2f} | "
            f"{row['combined_calibration_mean']:.2f} | "
            f"{100 * row['data_valid_episode_rate']:.0f}% |"
        )
    lines.extend(
        [
            "",
            "## What this supports",
            "",
            f"- Directional strict temporal order across the combined frozen cells: "
            f"`{str(output['strict_temporal_order']).lower()}`.",
            "- The executable-data separation is mainly completion and schema-repair "
            "reliability; valid submissions were at ceiling.",
            "- The packet separation includes decision, evidence, diagnosis, and next-action "
            "errors, so it is not solely a formatting benchmark.",
            "",
            "## What this does not support yet",
            "",
            "- No claim that an LLM failure was caused by undersampling in its pretraining data.",
            "- No claim that expert SFT/RLHF is required; the base-versus-expert-playbook "
            "intervention has not run.",
            "- No public ranking: there is one attempt per cell, calibration variants are "
            "not held out, and the strongest models still hit ceiling on many cells.",
            "- No contamination-resistance claim until the full-versus-withheld paired run "
            "is completed.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    packet = read_json(PACKET_PATH)
    data = read_json(DATA_PATH)
    summaries = combine_model_summaries(packet, data)
    combined_means = [float(row["combined_calibration_mean"]) for row in summaries]
    strict_order = all(left > right for left, right in pairwise(combined_means))
    output = {
        "schema_version": "0.1",
        "status": "calibration_only_not_ranking",
        "leaderboard_evidence": False,
        "ranking_claim_allowed": False,
        "source_artifacts": [
            {
                "path": PACKET_PATH.relative_to(PROJECT_ROOT).as_posix(),
                "sha256": sha256_file(PACKET_PATH),
            },
            {
                "path": DATA_PATH.relative_to(PROJECT_ROOT).as_posix(),
                "sha256": sha256_file(DATA_PATH),
            },
        ],
        "strict_temporal_order": strict_order,
        "model_summaries": summaries,
        "causal_claim_status": {
            "workflow_completion_gap": "observed",
            "evidence_diagnosis_gap": "observed_in_packet_slice",
            "biological_dataset_undersampling": "environment_ladder_exists_not_model_cause",
            "llm_pretraining_undersampling": "not_identified",
            "expert_sft_or_rlhf_required": "not_tested",
            "contamination_resistance": "not_tested_in_combined_matrix",
        },
    }
    OUTPUT_PATH.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    REPORT_PATH.write_text(render_report(output), encoding="utf-8")
    print(
        json.dumps(
            {
                "strict_temporal_order": strict_order,
                "ranking_claim_allowed": False,
                "model_means": {
                    row["model_id"]: row["combined_calibration_mean"] for row in summaries
                },
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

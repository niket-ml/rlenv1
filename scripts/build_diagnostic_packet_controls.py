#!/usr/bin/env python3
"""Replay deterministic packet controls and universal-policy attacks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from uc_bench.diagnostic_packets import (
    grade_diagnostic_packet,
    validate_diagnostic_packets,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def submission_for(
    rubric: dict[str, Any], *, decision: str | None = None
) -> dict[str, Any]:
    return {
        "decision": decision or rubric["expected_decision"],
        "confidence": sum(float(item) for item in rubric["confidence_range"]) / 2.0,
        "diagnostic_codes": rubric["expected_diagnostic_codes"],
        "evidence_ids": rubric["required_evidence_ids"],
        "next_action_type": rubric["expected_next_action_type"],
        "rationale": "Machine-scored control; prose is not graded.",
    }


def main() -> int:
    config = read_json(PROJECT_ROOT / "configs" / "diagnostic_packets.json")
    validation = validate_diagnostic_packets(config)
    reference_scores = []
    universal_submissions = {
        "advance": {
            "decision": "advance",
            "confidence": 0.8,
            "diagnostic_codes": ["none"],
            "evidence_ids": ["VAL-001", "POL-001"],
            "next_action_type": "independent_replication",
            "rationale": "Universal advancement control.",
        },
        "stop": {
            "decision": "stop",
            "confidence": 0.9,
            "diagnostic_codes": ["sample_identity_conflict"],
            "evidence_ids": ["CTX-001", "POL-001"],
            "next_action_type": "resolve_sample_identity",
            "rationale": "Universal stopping control.",
        },
        "insufficient_evidence": {
            "decision": "insufficient_evidence",
            "confidence": 0.8,
            "diagnostic_codes": ["underpowered_validation"],
            "evidence_ids": ["CTX-001", "VAL-001", "POL-001"],
            "next_action_type": "expand_validation_sample",
            "rationale": "Universal abstention control.",
        },
    }
    universal_scores = {name: [] for name in universal_submissions}
    for scenario in config["scenarios"]:
        rubric = scenario["rubric"]
        reference_scores.append(
            grade_diagnostic_packet(submission_for(rubric), rubric).score
        )
        for name, submission in universal_submissions.items():
            universal_scores[name].append(
                grade_diagnostic_packet(submission, rubric).score
            )
    universal_means = {
        decision: sum(scores) / len(scores)
        for decision, scores in universal_scores.items()
    }
    if min(reference_scores) != 100.0:
        raise RuntimeError("Reference packet control did not score 100")
    if any(score >= 60.0 for score in universal_means.values()):
        raise RuntimeError(f"A universal decision policy passed: {universal_means}")
    output = {
        "schema_version": "0.1",
        **validation,
        "reference_minimum_score": min(reference_scores),
        "universal_decision_mean_scores": universal_means,
        "all_universal_decision_policies_fail": True,
        "controlled_results_are_biology_claims": False,
    }
    path = PROJECT_ROOT / "artifacts" / "diagnostics" / "packet_controls.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

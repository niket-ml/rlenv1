#!/usr/bin/env python3
"""Regrade preserved model trajectories after an audited reward-policy change."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from uc_bench.canary_audit import rebuild_canary_audit
from uc_bench.grading import ScenarioRubric, grade_episode

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    reward = read_json(PROJECT_ROOT / "configs" / "reward_weights.json")
    rubric = ScenarioRubric.from_dict(
        read_json(PROJECT_ROOT / "configs" / "authentic_rubric.json")
    )
    updated: dict[str, float | None] = {}
    for summary_path in sorted(
        (PROJECT_ROOT / "build" / "model_runs").glob("*/run_summary.json")
    ):
        summary = read_json(summary_path)
        if summary.get("classification") == "infrastructure_failure":
            summary["attempt_score"] = None
            write_json(summary_path, summary)
            updated[str(summary["run_id"])] = None
            continue
        if summary.get("phase") != "submitted":
            summary["attempt_score"] = 0.0
            write_json(summary_path, summary)
            updated[str(summary["run_id"])] = 0.0
            continue
        record = read_json(summary_path.with_name("episode_record.json"))
        workspace = summary_path.parent / str(summary["condition"])
        grade = grade_episode(
            record,
            workspace_root=workspace,
            rubric=rubric,
            weights=reward["weights"],
            soft_contract_failure_ceiling=float(
                reward["soft_contract_failure_ceiling"]
            ),
            incorrect_terminal_decision_ceiling=float(
                reward["incorrect_terminal_decision_ceiling"]
            ),
        ).to_dict()
        summary["grade"] = grade
        summary["classification"] = (
            "valid_episode" if grade["contract_valid"] else "submitted_contract_failure"
        )
        summary["attempt_score"] = float(grade["score"])
        write_json(summary_path, summary)
        updated[str(summary["run_id"])] = float(grade["score"])

    for artifact_path in sorted(
        (PROJECT_ROOT / "artifacts" / "runtime").glob("smoke*_runs.json")
    ):
        artifact = read_json(artifact_path)
        for row in artifact.get("runs", []):
            run_id = str(row.get("run_id"))
            if run_id in updated:
                row["score"] = updated[run_id]
        artifact["regraded_with_reward_policy"] = "configs/reward_weights.json"
        write_json(artifact_path, artifact)

    rebuild_canary_audit(PROJECT_ROOT)
    print(json.dumps({"regraded_submitted_runs": len(updated)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

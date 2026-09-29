#!/usr/bin/env python3
"""Build deterministic reference and no-analysis controls for T03-T06."""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.data_diagnostics import (
    DataDiagnosticBuilder,
    grade_data_diagnostic,
    iter_data_diagnostic_scenarios,
    reference_submission,
)


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected JSON object: {path}")
    return value


def _no_analysis_submission(workspace_root: Path, decision: str) -> dict[str, Any]:
    task = _read_object(workspace_root / "task.json")
    return {
        "task_id": task["task_id"],
        "scenario_id": task["scenario_id"],
        "decision": decision,
        "confidence": 0.5,
        "diagnostic_codes": ["none"],
        "metrics": {name: 0.0 for name in task["metric_contract"]},
        "affected_ids": [],
        "analysis_method": task["analysis_method"],
        "next_action_type": "continue_prespecified_analysis",
        "rationale": "Static schema-aware control; no data analysis performed.",
    }


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    rows = []
    with tempfile.TemporaryDirectory(prefix="uc-data-controls-") as directory:
        output_root = Path(directory)
        for task_id, scenario_id in iter_data_diagnostic_scenarios(project_root):
            package = DataDiagnosticBuilder(project_root).build(
                task_id, scenario_id, output_root=output_root
            )
            reference = grade_data_diagnostic(
                package.workspace_root, reference_submission(package.workspace_root)
            )
            controls = {
                decision: grade_data_diagnostic(
                    package.workspace_root,
                    _no_analysis_submission(package.workspace_root, decision),
                ).score
                for decision in ("advance", "insufficient_evidence", "stop")
            }
            rows.append(
                {
                    "task_id": task_id,
                    "scenario_id": scenario_id,
                    "package_digest": package.package_digest,
                    "reference_score": reference.score,
                    "no_analysis_scores": controls,
                }
            )
    reference_minimum = min(row["reference_score"] for row in rows)
    means = {
        decision: sum(row["no_analysis_scores"][decision] for row in rows) / len(rows)
        for decision in ("advance", "insufficient_evidence", "stop")
    }
    challenge_scenarios = {
        "T03": "duplicates_3",
        "T04": "dropout_30",
        "T05": "phi_30",
        "T06": "noise_n120_20",
    }
    expert_separation = all(
        row["reference_score"] > max(row["no_analysis_scores"].values())
        for row in rows
        if challenge_scenarios.get(row["task_id"]) == row["scenario_id"]
    )
    value = {
        "schema_version": "0.1",
        "generated_at": datetime.now(UTC).isoformat(),
        "scenario_count": len(rows),
        "reference_minimum_score": reference_minimum,
        "reference_gate_passed": reference_minimum >= 90.0,
        "no_analysis_mean_scores": means,
        "universal_policy_gate_passed": all(score < 60.0 for score in means.values()),
        "challenge_scenarios": challenge_scenarios,
        "expert_separation_gate_passed": expert_separation,
        "rows": rows,
    }
    output = project_root / "artifacts" / "diagnostics" / "data_task_controls.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: value[key] for key in value if key != "rows"}, indent=2))


if __name__ == "__main__":
    main()

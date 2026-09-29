#!/usr/bin/env python3
"""Persist compact, non-model reference replay traces for every v0.5 state."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from uc_bench.hard_suite_v05 import iter_v05_scenarios, run_reference_v05_episode

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "artifacts" / "reference" / "v05_replay_traces.json"


def main() -> None:
    traces = []
    with tempfile.TemporaryDirectory(prefix="uc-v05-reference-") as temporary:
        for scenario in iter_v05_scenarios(PROJECT_ROOT):
            package, environment, grade = run_reference_v05_episode(
                PROJECT_ROOT,
                str(scenario["scenario_id"]),
                output_root=Path(temporary),
            )
            traces.append(
                {
                    "scenario_id": scenario["scenario_id"],
                    "scenario_class": scenario["scenario_class"],
                    "controlled_or_authentic": "controlled",
                    "model_trajectory": False,
                    "events": environment.events,
                    "commitment_digest": environment.commitment_sha256,
                    "assessment_digest": environment.assessment_sha256,
                    "selected_resource": environment.selected_resource,
                    "initial_decision": environment.assessment["provisional_decision"],
                    "final_decision": environment.submission["decision"],
                    "grade": grade.to_dict(),
                    "package_digest": package.package_digest,
                    "sealed_digest": package.sealed_digest,
                }
            )
    output = {
        "schema_version": "0.5",
        "status": "deterministic_reference_replays_not_model_results",
        "model_calls": 0,
        "astra_requests": 0,
        "traces": traces,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(OUTPUT_PATH.relative_to(PROJECT_ROOT))


if __name__ == "__main__":
    main()

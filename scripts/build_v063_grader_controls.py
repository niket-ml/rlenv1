#!/usr/bin/env python3
"""Generate deterministic evidence for the v0.6.3 grader-only repair."""

from __future__ import annotations

import csv
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from uc_bench.hard_suite_v06 import (
    ALL_ARTIFACTS,
    V06Package,
    grade_v06,
    load_v06_scenario,
    run_reference_v06_episode,
)
from uc_bench.v063_grader import grade_v063, grader_infrastructure_failed

PROJECT_ROOT = Path(__file__).resolve().parents[1]
V062_RUN = (
    PROJECT_ROOT
    / "build/hard_suite_v06_runs/"
    "hard62-gpt-5.6-sol-dev6_clean_progression-0-20260908T194210Z"
)
OUTPUT = PROJECT_ROOT / "artifacts/diagnostics/hard_suite_v063_grader_controls.json"


def _captured_package() -> V06Package:
    workspace = V062_RUN / "hard6-dev6_clean_progression"
    start = json.loads((workspace / "START_STATE.json").read_text(encoding="utf-8"))
    return V06Package(
        scenario_id="dev6_clean_progression",
        partition="development",
        workspace_root=workspace,
        sealed_root=V062_RUN / "hard6-dev6_clean_progression-sealed",
        package_digest=str(start["package_digest"]),
        sealed_digest="preserved-v062-run",
        private_scenario=load_v06_scenario(
            PROJECT_ROOT,
            "dev6_clean_progression",
            partition="development",
        ),
        schema_root=workspace / "schemas",
    )


def _mutate_count(package: V06Package) -> None:
    path = package.workspace_root / ALL_ARTIFACTS[0]
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows[0]["patient_count"] = "unresolved"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="uc-v063-controls-") as directory:
        package, _environment, _grade = run_reference_v06_episode(
            PROJECT_ROOT,
            "dev6_clean_progression",
            output_root=Path(directory),
        )
        frozen = grade_v06(
            PROJECT_ROOT,
            package,
            selected_resource="none",
            commitment_immutable=True,
            completion_accepted=True,
        )
        repaired = grade_v063(
            PROJECT_ROOT,
            package,
            selected_resource="none",
            commitment_immutable=True,
            completion_accepted=True,
        )
        parity = repaired.to_dict() == frozen.to_dict()
        _mutate_count(package)
        partial = grade_v063(
            PROJECT_ROOT,
            package,
            selected_resource="none",
            commitment_immutable=True,
            completion_accepted=True,
        )
    captured = grade_v063(
        PROJECT_ROOT,
        _captured_package(),
        selected_resource="none",
        commitment_immutable=True,
        completion_accepted=False,
    )
    checks = {
        "valid_reference_byte_identical_to_v06": parity,
        "reference_score_at_least_90": repaired.coverage_adjusted_scientific_score
        >= 90,
        "invalid_numeric_field_does_not_crash": not grader_infrastructure_failed(
            partial
        ),
        "invalid_numeric_field_loses_only_inventory_count_property": (
            partial.artifact_scores["A01"] == 80
            and all(
                partial.artifact_scores[name] == repaired.artifact_scores[name]
                for name in repaired.artifact_scores
                if name != "A01"
            )
        ),
        "captured_v062_submission_regrades_without_crash": (
            not grader_infrastructure_failed(captured)
        ),
        "captured_v062_regrade_is_diagnostic_only": (
            captured.completion_accepted is False
            and captured.reliability_inclusive_score == 0
        ),
    }
    result = {
        "schema_version": "0.6.3-grader-controls-1",
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "passed" if all(checks.values()) else "failed",
        "scientific_tasks_changed": False,
        "scientific_prompts_changed": False,
        "scientific_thresholds_changed": False,
        "scientific_scoring_invariants_changed": False,
        "grader_implementation_changed": True,
        "checks": checks,
        "reference_score": repaired.coverage_adjusted_scientific_score,
        "single_bad_field_score": partial.coverage_adjusted_scientific_score,
        "single_bad_field_artifact_scores": partial.artifact_scores,
        "captured_v062_diagnostic_regrade": {
            "headline_or_ceiling_eligible": False,
            "score": captured.coverage_adjusted_scientific_score,
            "artifact_scores": captured.artifact_scores,
        },
        "heldout_requests": 0,
        "astra_requests": 0,
        "model_requests": 0,
    }
    temporary = OUTPUT.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(OUTPUT)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

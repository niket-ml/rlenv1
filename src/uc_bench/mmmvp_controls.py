"""Zero-cost construct, anti-gaming, and alternative-workflow controls."""

from __future__ import annotations

import copy
import csv
import json
import shutil
from pathlib import Path
from typing import Any

from uc_bench.mmmvp_schema import SCHEMA_VERSION, TARGET_HYPOTHESIS_ID
from uc_bench.mmmvp_verifier import verify_mmmvp_submission
from uc_bench.v08_controls import (
    CONDITIONS,
    build_reference_solution,
    sync_event_digests,
)


def finalise_reference(submission: dict[str, Any], condition_id: str) -> dict[str, Any]:
    value = copy.deepcopy(submission)
    for checkpoint in value["checkpoints"].values():
        checkpoint["schema_version"] = SCHEMA_VERSION
    c3 = value["checkpoints"]["C3"]
    contamination = c3["preprocessing_and_contamination"]
    established = condition_id.startswith("case_03")
    contamination.pop("contaminated_evidence_eligible", None)
    contamination["established_contamination"] = established
    contamination["primary_evidence_eligible"] = not established
    c4 = value["checkpoints"]["C4"]
    prediction = c4["prediction_before_investigation"]
    prediction["target_hypothesis_id"] = TARGET_HYPOTHESIS_ID
    prediction["belief_before"] = 0.5
    c5 = value["checkpoints"]["C5"]
    c5["belief_change"]["target_hypothesis_id"] = TARGET_HYPOTHESIS_ID
    c5["belief_change"].pop("target_hypothesis", None)
    c5["belief_change"]["support_probability_before"] = 0.5
    if condition_id == "case_02":
        c5["belief_change"]["support_probability_after"] = 0.35
    elif condition_id == "case_04":
        selected = next(
            event["resource_id"]
            for event in value["event_log"]
            if event.get("event") == "purchase_resource"
        )
        c5["belief_change"]["support_probability_after"] = (
            0.5 if selected == "none" else 0.2
        )
    elif condition_id == "case_03_signal_collapses":
        c5["belief_change"]["support_probability_after"] = 0.2
    elif condition_id == "case_03_signal_remains":
        c5["belief_change"]["support_probability_after"] = 0.75
        c5["claims"]["supported"] = sorted(
            set(c5["claims"]["supported"])
            | {"original_validation_invalid", "research_use_prognostic_validation"}
        )
        c5["claims"]["prohibited"] = sorted(
            set(c5["claims"]["prohibited"])
            | {
                "independent_validation_passed",
                "treatment_effect",
                "clinical_utility_proven",
                "safe_threshold_use",
                "all_platforms",
            }
        )
        c5["claims"]["asserted"] = ["research_use_prognostic_validation"]
    else:
        c5["belief_change"]["support_probability_after"] = 0.6
    c5.pop("preprocessing_and_contamination", None)
    sync_event_digests(value)
    return value


def build_mmmvp_reference(
    project_root: Path,
    condition_id: str,
    run_root: Path,
    *,
    alternative: bool,
) -> tuple[dict[str, Any], Path]:
    submission, workspace = build_reference_solution(
        project_root,
        condition_id,
        run_root,
        alternative=alternative,
    )
    return finalise_reference(submission, condition_id), workspace


def run_mmmvp_controls(project_root: Path, temporary_root: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for index, condition_id in enumerate(CONDITIONS):
        reference, workspace = build_mmmvp_reference(
            project_root,
            condition_id,
            temporary_root / f"{index}-reference",
            alternative=False,
        )
        alternative, alt_workspace = build_mmmvp_reference(
            project_root,
            condition_id,
            temporary_root / f"{index}-alternative",
            alternative=True,
        )
        for name, submission, selected_workspace in (
            ("correct_reference", reference, workspace),
            ("different_valid_solution", alternative, alt_workspace),
        ):
            grade = verify_mmmvp_submission(
                project_root,
                selected_workspace,
                submission,
                condition_id=condition_id,
            )
            rows.append(
                {
                    "condition_id": condition_id,
                    "control": name,
                    "complete_mission_success": grade.complete_mission_success,
                    "partial_scientific_quality": grade.partial_scientific_quality,
                    "mission_failures": list(grade.mission_failures),
                }
            )

        wrong = copy.deepcopy(reference)
        if condition_id == "case_04":
            wrong["checkpoints"]["C5"]["decision"]["disposition"] = "CONTINUE"
            wrong["checkpoints"]["C5"]["decision"]["development_stage"] = (
                "EXTERNAL_VALIDATION"
            )
        elif condition_id.startswith("case_03"):
            wrong["checkpoints"]["C3"]["preprocessing_and_contamination"][
                "primary_evidence_eligible"
            ] = True
        else:
            wrong["checkpoints"]["C1"]["analysis_unit"]["level"] = "BIOPSY"
        sync_event_digests(wrong)
        wrong_grade = verify_mmmvp_submission(
            project_root, workspace, wrong, condition_id=condition_id
        )
        rows.append(
            {
                "condition_id": condition_id,
                "control": "plausible_scientific_error",
                "complete_mission_success": wrong_grade.complete_mission_success,
                "partial_scientific_quality": wrong_grade.partial_scientific_quality,
                "mission_failures": list(wrong_grade.mission_failures),
            }
        )

        hard_workspace = temporary_root / f"{index}-hard-coded"
        shutil.copytree(workspace, hard_workspace)
        hard_coded = copy.deepcopy(reference)
        hard_coded["checkpoints"]["C3"]["artifact_manifest"]["patient_table_path"] = (
            "work/copied_expected_values_without_patient_rows.csv"
        )
        sync_event_digests(hard_coded)
        hard_grade = verify_mmmvp_submission(
            project_root, hard_workspace, hard_coded, condition_id=condition_id
        )
        rows.append(
            {
                "condition_id": condition_id,
                "control": "hard_coded_without_artifacts",
                "complete_mission_success": hard_grade.complete_mission_success,
                "partial_scientific_quality": hard_grade.partial_scientific_quality,
                "mission_failures": list(hard_grade.mission_failures),
            }
        )

        altered_workspace = temporary_root / f"{index}-altered-input"
        shutil.copytree(workspace, altered_workspace)
        altered = copy.deepcopy(reference)
        outcomes_path = altered_workspace / "revealed/validation_outcomes.csv"
        outcome_rows = list(csv.DictReader(outcomes_path.open(encoding="utf-8", newline="")))
        for row in outcome_rows[: min(20, len(outcome_rows))]:
            row["week6_response"] = str(1 - int(row["week6_response"]))
        with outcomes_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(outcome_rows[0]))
            writer.writeheader()
            writer.writerows(outcome_rows)
        altered_grade = verify_mmmvp_submission(
            project_root, altered_workspace, altered, condition_id=condition_id
        )
        rows.append(
            {
                "condition_id": condition_id,
                "control": "altered_input",
                "complete_mission_success": altered_grade.complete_mission_success,
                "partial_scientific_quality": altered_grade.partial_scientific_quality,
                "mission_failures": list(altered_grade.mission_failures),
            }
        )

        unsupported_workspace = temporary_root / f"{index}-unsupported-decision"
        shutil.copytree(workspace, unsupported_workspace)
        unsupported = copy.deepcopy(reference)
        unsupported["checkpoints"]["C3"]["artifact_manifest"][
            "calculated_outputs_path"
        ] = "work/nonexistent_calculations.json"
        sync_event_digests(unsupported)
        unsupported_grade = verify_mmmvp_submission(
            project_root,
            unsupported_workspace,
            unsupported,
            condition_id=condition_id,
        )
        rows.append(
            {
                "condition_id": condition_id,
                "control": "correct_decision_without_required_analysis",
                "complete_mission_success": unsupported_grade.complete_mission_success,
                "partial_scientific_quality": unsupported_grade.partial_scientific_quality,
                "mission_failures": list(unsupported_grade.mission_failures),
            }
        )

        optional_workspace = temporary_root / f"{index}-optional"
        shutil.copytree(workspace, optional_workspace)
        optional = copy.deepcopy(reference)
        calculated_path = optional_workspace / optional["checkpoints"]["C3"][
            "artifact_manifest"
        ]["calculated_outputs_path"]
        calculated = json.loads(calculated_path.read_text(encoding="utf-8"))
        calculated.setdefault("sensitivity_metrics", {})["site_weighted_auc"] = 0.0
        calculated_path.write_text(
            json.dumps(calculated, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        optional_grade = verify_mmmvp_submission(
            project_root, optional_workspace, optional, condition_id=condition_id
        )
        rows.append(
            {
                "condition_id": condition_id,
                "control": "incorrect_optional_diagnostic",
                "complete_mission_success": optional_grade.complete_mission_success,
                "partial_scientific_quality": optional_grade.partial_scientific_quality,
                "mission_failures": list(optional_grade.mission_failures),
            }
        )
    passing_reference = all(
        row["complete_mission_success"]
        for row in rows
        if row["control"] in {"correct_reference", "different_valid_solution"}
    )
    wrong_rejected = all(
        not row["complete_mission_success"]
        for row in rows
        if row["control"] == "plausible_scientific_error"
    )
    gaming_rejected = all(
        not row["complete_mission_success"]
        for row in rows
        if row["control"]
        in {
            "hard_coded_without_artifacts",
            "altered_input",
            "correct_decision_without_required_analysis",
        }
    )
    optional_safe = all(
        row["complete_mission_success"]
        for row in rows
        if row["control"] == "incorrect_optional_diagnostic"
    )
    return {
        "schema_version": "uc-bench-mmmvp-controls-1",
        "api_requests": 0,
        "status": (
            "passed"
            if passing_reference and wrong_rejected and gaming_rejected and optional_safe
            else "failed"
        ),
        "reference_and_alternative_passed": passing_reference,
        "plausible_scientific_errors_rejected": wrong_rejected,
        "hard_coded_altered_and_unsupported_rejected": gaming_rejected,
        "optional_diagnostic_cannot_fail_mission": optional_safe,
        "control_count": len(rows),
        "results": rows,
    }


__all__ = ["build_mmmvp_reference", "finalise_reference", "run_mmmvp_controls"]

"""Zero-cost scientific and anti-gaming controls for the v0.8 five-condition MVP."""

from __future__ import annotations

import copy
import csv
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from uc_bench.hard_suite_v072 import replay_v072_reference
from uc_bench.v07_cases import load_truth
from uc_bench.v08_schema import SCHEMA_VERSION
from uc_bench.v08_verifier import (
    V08ReplayGrade,
    load_v08_mvp,
    recompute_v08_followup_values,
    verify_v08_submission,
)

CONDITIONS = (
    "case_01",
    "case_02",
    "case_03_signal_collapses",
    "case_03_signal_remains",
    "case_04",
)

# Every member denotes a consequential property of the scientific evidence
# chain. Schema validity, filenames, prose and presentation are deliberately
# absent. Prefix entries cover independently scored numerical calculations.
PROFESSIONAL_MISSION_REQUIREMENTS = {
    "patient_analysis_unit",
    "cohort_counts",
    "dependence_site_and_timing_inspected",
    "commit_before_reveal",
    "patient_level_estimand",
    "outcome_blind_training_fit",
    "valid_uncertainty_plan",
    "primary_metrics_prespecified",
    "patient_mapping_artifact",
    "preprocessing_membership_artifact",
    "contaminated_evidence_contained",
    "material_diagnosis",
    "decision_relevant_resource",
    "followup_evidence_artifact",
    "evidence_consistent_belief_change",
    "explicit_bounded_decision",
    "claim_scope",
}


def _case_and_mechanism(condition_id: str) -> tuple[str, str]:
    if condition_id == "case_03_signal_collapses":
        return "case_03", "signal_collapses"
    if condition_id == "case_03_signal_remains":
        return "case_03", "signal_remains"
    return condition_id, "default"


def _digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def sync_event_digests(submission: dict[str, Any]) -> None:
    """Keep event provenance aligned after a local control mutation."""

    committed = _digest(submission["checkpoints"]["C2"])
    for event in submission["event_log"]:
        if event.get("event") == "save_checkpoint" and event.get("schema_valid") is not False:
            checkpoint = event["checkpoint"]
            event["digest"] = _digest(submission["checkpoints"][checkpoint])
        elif event.get("event") == "commit_validation_plan":
            event["digest"] = committed
        elif event.get("event") in {"reveal_validation", "submit"}:
            event["committed_plan_hash"] = committed


def _explicit_disposition(legacy: Any) -> str:
    if isinstance(legacy, dict):
        legacy = legacy.get("decision")
    return {
        "ADVANCE": "CONTINUE",
        "CONDITIONAL_ADVANCE": "CONTINUE",
        "PAUSE": "PAUSE",
        "STOP": "STOP",
        "INSUFFICIENT_EVIDENCE": "INSUFFICIENT_EVIDENCE",
    }[str(legacy)]


def _native_v08_c5(
    project_root: Path,
    workspace: Path,
    submission: dict[str, Any],
    condition_id: str,
) -> None:
    policy = next(
        row
        for row in load_v08_mvp(project_root)["active_conditions"]
        if row["condition_id"] == condition_id
    )
    case_id, _ = _case_and_mechanism(condition_id)
    truth = load_truth(project_root, case_id)
    c2 = submission["checkpoints"]["C2"]
    c4 = submission["checkpoints"]["C4"]
    c5 = submission["checkpoints"]["C5"]
    selected = next(
        event["resource_id"]
        for event in submission["event_log"]
        if event.get("event") == "purchase_resource"
    )
    values, count, meta = recompute_v08_followup_values(workspace, c2, selected)
    c5["investigation_analysis"]["calculated_values"] = values
    c5["investigation_analysis"]["resolved_patient_count"] = count
    evidence_paths = {
        "none": ["purchased/none/no_new_evidence.json"],
        "X17": [
            "purchased/X17/source_record_crosswalk.csv",
            "purchased/X17/package_limitations.json",
        ],
        "X31": [
            "purchased/X31/replay_predictions.csv",
            "revealed/validation_outcomes.csv",
        ],
        "X46": [
            "purchased/X46/matched_predictions.csv",
            "purchased/X46/matched_outcomes.csv",
        ],
    }[selected]
    relative = "work/v08_followup_calculated_outputs.json"
    path = workspace / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "calculated_values": values,
                "resolved_patient_count": count,
                "new_evidence_received": meta["new_evidence_received"],
                "evidence_paths": evidence_paths,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    c5["investigation_analysis"]["artifact_manifest"] = {"calculated_outputs_path": relative}
    c5["investigation_analysis"]["evidence_paths"] = evidence_paths
    rule = policy["belief_change_rule"]
    after = {
        "INCREASE": 0.75,
        "DECREASE": 0.20,
        "NONDECREASE": 0.60,
        "NONINCREASE": 0.35,
    }[rule]
    c5["belief_change"] = {
        "target_hypothesis": "locked predictor supports the bounded intended use",
        "support_probability_before": 0.50,
        "support_probability_after": after,
        "evidence": ["checkpoints/C3.json", f"purchased/{selected}"],
    }
    disposition = _explicit_disposition(c5["decisions"]["final"])
    continuing = disposition == "CONTINUE"
    c5["decision"] = {
        "development_stage": (
            "EXTERNAL_VALIDATION"
            if continuing
            else ("STOPPED" if disposition == "STOP" else "INTERNAL_VALIDATION")
        ),
        "disposition": disposition,
        "allowed_use": (
            list(truth["supported_claims"])
            if continuing
            else (["retrospective_failure_analysis_only"] if disposition == "STOP" else [])
        ),
        "unresolved_gates": list(c5["remaining_uncertainties"]),
        "prohibited_use": list(truth["prohibited_claims"]),
        "required_next_evidence": (
            list(c5["remaining_uncertainties"])
            if disposition in {"CONTINUE", "PAUSE", "INSUFFICIENT_EVIDENCE"}
            else []
        ),
    }
    initial_disposition = _explicit_disposition(c5["decisions"]["initial"])
    c4["initial_decision"] = {
        "development_stage": (
            "EXTERNAL_VALIDATION"
            if initial_disposition == "CONTINUE"
            else ("STOPPED" if initial_disposition == "STOP" else "INTERNAL_VALIDATION")
        ),
        "disposition": initial_disposition,
        "allowed_use": (
            list(truth["supported_claims"])
            if initial_disposition == "CONTINUE"
            else (["retrospective_failure_analysis_only"] if initial_disposition == "STOP" else [])
        ),
        "unresolved_gates": list(c5["remaining_uncertainties"]),
        "prohibited_use": list(truth["prohibited_claims"]),
        "required_next_evidence": (
            list(c5["remaining_uncertainties"])
            if initial_disposition in {"CONTINUE", "PAUSE", "INSUFFICIENT_EVIDENCE"}
            else []
        ),
    }
    c4["decision_question"] = {
        "none": "CURRENT_PROBABILITY_USE",
        "X17": "PATIENT_IDENTITY",
        "X31": "CLEAN_PIPELINE_SIGNAL",
        "X46": "TRANSPORT",
    }[selected]
    c4["why_decision_resolving"] = (
        "The chosen action directly addresses the declared immediate decision question."
    )
    for checkpoint in submission["checkpoints"].values():
        checkpoint["schema_version"] = SCHEMA_VERSION
    sync_event_digests(submission)


def build_reference_solution(
    project_root: Path,
    condition_id: str,
    run_root: Path,
    *,
    alternative: bool,
) -> tuple[dict[str, Any], Path]:
    """Build one native-v0.8 reference using only the existing case packet."""

    case_id, mechanism = _case_and_mechanism(condition_id)
    submission, _ = replay_v072_reference(
        project_root,
        case_id,
        run_root,
        mechanism=mechanism,
        alternative=alternative,
    )
    _native_v08_c5(project_root, run_root, submission, condition_id)
    return submission, run_root


def _clone(
    source_submission: dict[str, Any], source_workspace: Path, target: Path
) -> tuple[dict[str, Any], Path]:
    shutil.copytree(source_workspace, target)
    return copy.deepcopy(source_submission), target


def _plausible_wrong(submission: dict[str, Any], condition_id: str) -> None:
    c1 = submission["checkpoints"]["C1"]
    c2 = submission["checkpoints"]["C2"]
    c3 = submission["checkpoints"]["C3"]
    c5 = submission["checkpoints"]["C5"]
    if condition_id == "case_01":
        c5["belief_change"]["support_probability_after"] = 0.10
        c5["decision"].update(
            {
                "development_stage": "STOPPED",
                "disposition": "STOP",
                "allowed_use": ["retrospective_failure_analysis_only"],
                "required_next_evidence": [],
            }
        )
    elif condition_id == "case_02":
        biopsy = {"level": "BIOPSY", "patient_key": "sample_id"}
        c1["analysis_unit"] = biopsy
        c2["validation_plan"]["analysis_unit"] = biopsy
        c3["execution"]["patient_dependence_preserved"] = False
    elif condition_id.startswith("case_03"):
        c3["preprocessing_and_contamination"]["contaminated_evidence_eligible"] = True
    else:
        c5["belief_change"]["support_probability_after"] = 0.85
        c5["decision"].update(
            {
                "development_stage": "EXTERNAL_VALIDATION",
                "disposition": "CONTINUE",
                "allowed_use": ["safe_threshold_use"],
                "required_next_evidence": ["prospective deployment"],
            }
        )
    sync_event_digests(submission)


def _write_outcomes(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _result_row(condition_id: str, control: str, grade: V08ReplayGrade) -> dict[str, Any]:
    return {
        "condition_id": condition_id,
        "control": control,
        "complete_mission_success": grade.complete_mission_success,
        "partial_scientific_quality": grade.partial_scientific_quality,
        "checkpoint_scores": grade.checkpoint_scores,
        "mission_failures": list(grade.mission_failures),
        "first_decision_critical_failure": grade.first_decision_critical_failure,
    }


def run_v08_mvp_controls(project_root: Path, temporary_root: Path) -> dict[str, Any]:
    """Run seven zero-cost controls for each of the five active conditions."""

    rows: list[dict[str, Any]] = []
    reference_grades: list[V08ReplayGrade] = []
    naturalistic_reference: tuple[dict[str, Any], Path] | None = None
    for index, condition_id in enumerate(CONDITIONS):
        reference, reference_workspace = build_reference_solution(
            project_root,
            condition_id,
            temporary_root / f"{index}-reference",
            alternative=False,
        )
        alternative, alternative_workspace = build_reference_solution(
            project_root,
            condition_id,
            temporary_root / f"{index}-alternative",
            alternative=True,
        )
        if condition_id == "case_02":
            naturalistic_reference = (copy.deepcopy(reference), reference_workspace)
        for control, submission, workspace in (
            ("correct_reference", reference, reference_workspace),
            ("different_valid_solution", alternative, alternative_workspace),
        ):
            grade = verify_v08_submission(
                project_root, workspace, submission, condition_id=condition_id
            )
            rows.append(_result_row(condition_id, control, grade))
            if control == "correct_reference":
                reference_grades.append(grade)

        wrong, wrong_workspace = _clone(
            reference, reference_workspace, temporary_root / f"{index}-wrong"
        )
        _plausible_wrong(wrong, condition_id)
        rows.append(
            _result_row(
                condition_id,
                "plausible_scientific_error",
                verify_v08_submission(
                    project_root, wrong_workspace, wrong, condition_id=condition_id
                ),
            )
        )

        hard_coded, hard_coded_workspace = _clone(
            reference, reference_workspace, temporary_root / f"{index}-hard-coded"
        )
        hard_coded["checkpoints"]["C3"]["artifact_manifest"]["patient_table_path"] = (
            "work/nonexistent_patient_artifact.csv"
        )
        sync_event_digests(hard_coded)
        rows.append(
            _result_row(
                condition_id,
                "hard_coded_without_artifacts",
                verify_v08_submission(
                    project_root,
                    hard_coded_workspace,
                    hard_coded,
                    condition_id=condition_id,
                ),
            )
        )

        altered, altered_workspace = _clone(
            reference, reference_workspace, temporary_root / f"{index}-altered"
        )
        outcomes = altered_workspace / "revealed/validation_outcomes.csv"
        outcome_rows = list(csv.DictReader(outcomes.read_text(encoding="utf-8").splitlines()))
        for row in outcome_rows[: min(20, len(outcome_rows))]:
            row["week6_response"] = str(1 - int(row["week6_response"]))
        _write_outcomes(outcomes, outcome_rows)
        rows.append(
            _result_row(
                condition_id,
                "altered_input",
                verify_v08_submission(
                    project_root, altered_workspace, altered, condition_id=condition_id
                ),
            )
        )

        unsupported, unsupported_workspace = _clone(
            reference, reference_workspace, temporary_root / f"{index}-unsupported"
        )
        empty_relative = "work/no_required_calculations.json"
        (unsupported_workspace / empty_relative).write_text("{}\n", encoding="utf-8")
        unsupported["checkpoints"]["C3"]["primary_metrics"] = {}
        unsupported["checkpoints"]["C3"]["artifact_manifest"]["calculated_outputs_path"] = (
            empty_relative
        )
        sync_event_digests(unsupported)
        rows.append(
            _result_row(
                condition_id,
                "correct_decision_without_required_analysis",
                verify_v08_submission(
                    project_root,
                    unsupported_workspace,
                    unsupported,
                    condition_id=condition_id,
                ),
            )
        )

        optional, optional_workspace = _clone(
            reference, reference_workspace, temporary_root / f"{index}-optional"
        )
        calculated_path = (
            optional_workspace
            / optional["checkpoints"]["C3"]["artifact_manifest"]["calculated_outputs_path"]
        )
        calculated = json.loads(calculated_path.read_text(encoding="utf-8"))
        calculated["sensitivity_metrics"] = {
            key: 0.0 for key in calculated.get("sensitivity_metrics", {})
        }
        calculated_path.write_text(
            json.dumps(calculated, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        rows.append(
            _result_row(
                condition_id,
                "incorrect_optional_diagnostic",
                verify_v08_submission(
                    project_root, optional_workspace, optional, condition_id=condition_id
                ),
            )
        )

    if naturalistic_reference is None:
        raise AssertionError("Case 2 reference was not constructed")
    naturalistic_submission, naturalistic_workspace = naturalistic_reference
    fixture_path = project_root / "tests/fixtures/v08_naturalistic_decision_language.json"
    fixtures = json.loads(fixture_path.read_text(encoding="utf-8"))["fixtures"]
    naturalistic_rows: list[dict[str, Any]] = []
    for fixture in fixtures:
        submission = copy.deepcopy(naturalistic_submission)
        decision = submission["checkpoints"]["C5"]["decision"]
        for field in (
            "allowed_use",
            "prohibited_use",
            "unresolved_gates",
            "required_next_evidence",
        ):
            decision[field] = fixture[field]
        sync_event_digests(submission)
        grade = verify_v08_submission(
            project_root,
            naturalistic_workspace,
            submission,
            condition_id="case_02",
        )
        naturalistic_rows.append(
            {
                "fixture_id": fixture["fixture_id"],
                "complete_mission_success": grade.complete_mission_success,
                "partial_scientific_quality": grade.partial_scientific_quality,
                "mission_failures": list(grade.mission_failures),
            }
        )

    by_control = {
        control: [row for row in rows if row["control"] == control]
        for control in sorted({row["control"] for row in rows})
    }
    pass_controls = {
        "correct_reference",
        "different_valid_solution",
        "incorrect_optional_diagnostic",
    }
    fail_controls = {
        "plausible_scientific_error",
        "hard_coded_without_artifacts",
        "altered_input",
        "correct_decision_without_required_analysis",
    }
    checks = {
        "all_references_pass": all(
            row["complete_mission_success"] for row in by_control["correct_reference"]
        ),
        "all_different_valid_solutions_pass": all(
            row["complete_mission_success"] for row in by_control["different_valid_solution"]
        ),
        "all_plausible_scientific_errors_fail": all(
            not row["complete_mission_success"] for row in by_control["plausible_scientific_error"]
        ),
        "all_hard_coded_answers_fail": all(
            not row["complete_mission_success"]
            for row in by_control["hard_coded_without_artifacts"]
        ),
        "all_altered_inputs_invalidate_fixed_answers": all(
            not row["complete_mission_success"] for row in by_control["altered_input"]
        ),
        "all_unsupported_correct_decisions_fail": all(
            not row["complete_mission_success"]
            for row in by_control["correct_decision_without_required_analysis"]
        ),
        "optional_diagnostics_never_fail_mission": all(
            row["complete_mission_success"] for row in by_control["incorrect_optional_diagnostic"]
        ),
        "naturalistic_professional_language_never_changes_science": all(
            row["complete_mission_success"] and row["partial_scientific_quality"] == 100
            for row in naturalistic_rows
        ),
        "expected_pass_and_fail_partition": all(
            row["complete_mission_success"] == (row["control"] in pass_controls)
            for row in rows
            if row["control"] in pass_controls | fail_controls
        ),
    }
    requirement_inventory: dict[str, dict[str, str]] = {}
    for grade in reference_grades:
        for requirement in grade.requirements:
            if requirement.requirement_class != "mission_critical_science":
                continue
            base = requirement.requirement_id.split(":", maxsplit=1)[0]
            if base not in {"primary_calculation", "followup_calculation"}:
                base = requirement.requirement_id
            requirement_inventory[requirement.requirement_id] = {
                "professional_consequence": requirement.consequence,
                "actionable_remedy": requirement.remedy,
            }
            if base not in PROFESSIONAL_MISSION_REQUIREMENTS and base not in {
                "primary_calculation",
                "followup_calculation",
            }:
                checks["mission_requirements_are_professional_science"] = False
    checks.setdefault("mission_requirements_are_professional_science", True)
    return {
        "schema_version": "0.8-mvp-controls-1",
        "status": "passed" if all(checks.values()) else "failed",
        "api_requests": 0,
        "api_spend_usd": 0.0,
        "condition_count": len(CONDITIONS),
        "control_count": len(rows),
        "naturalistic_language_fixture_count": len(naturalistic_rows),
        "checks": checks,
        "rows": rows,
        "naturalistic_language_rows": naturalistic_rows,
        "mission_requirement_inventory": requirement_inventory,
    }


__all__ = [
    "CONDITIONS",
    "PROFESSIONAL_MISSION_REQUIREMENTS",
    "build_reference_solution",
    "run_v08_mvp_controls",
    "sync_event_digests",
]

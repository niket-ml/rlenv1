"""Reference paths and controls for the v0.7.2 interface-only successor."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from uc_bench.v07_cases import RESOURCE_CATALOG, load_truth
from uc_bench.v072_artifacts import (
    recompute_followup_artifact,
    write_canonical_analysis_artifacts,
)
from uc_bench.v072_environment import V072Environment
from uc_bench.v072_grader import V072Grade, grade_v072_submission
from uc_bench.v072_schema import SCHEMA_VERSION


def _checkpoint(**facts: Any) -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, **facts}


def _belief_direction(case_id: str, mechanism: str, selected: str) -> str:
    if case_id == "case_01":
        return "UNCHANGED_SUPPORTED" if selected == "none" else "MODEST_INCREASE"
    if case_id == "case_02":
        return "DECREASE_SITE_BLOCKER_REMAINS"
    if case_id == "case_03":
        return {
            "signal_collapses": "LARGE_DECREASE",
            "signal_remains": "INCREASE_AFTER_VALID_REPLAY",
        }[mechanism]
    return "DECREASE_UTILITY_CONCERN_CONFIRMED"


def reference_v072_checkpoints(
    project_root: Path,
    workspace_root: Path,
    case_id: str,
    *,
    mechanism: str = "default",
    alternative: bool = False,
) -> tuple[dict[str, dict[str, Any]], str]:
    """Build a high-quality solution using the disclosed artifact contract."""

    truth = load_truth(project_root, case_id)
    selected = truth["acceptable_resources"][-1] if alternative else truth["preferred_resource"]
    method = (
        "Patient bootstrap with hierarchical site sensitivity"
        if alternative
        else ("Patient-stratified cluster bootstrap")
    )
    checkpoints = {
        "C1": _checkpoint(
            analysis_unit={"level": "PATIENT", "patient_key": "fingerprint_cluster"},
            cohort_counts={
                "sample_count": truth["n_samples"],
                "patient_count": truth["n_patients"],
                "site_count": len(truth["site_counts"]),
                "patient_count_by_site": truth["site_counts"],
            },
            checks={
                "dependence_inspected": True,
                "site_distribution_inspected": True,
                "endpoint_timing_checked": True,
            },
            findings={
                "diagnosed_concepts": list(truth["required_concepts"]),
                "nonmaterial_findings": list(truth["harmless_anomalies"]),
                "nonmaterial_finding_is_blocker": False,
            },
            remaining_uncertainties=["external transportability"],
            evidence_refs={
                "analysis_unit": truth["evidence_path"]["analysis_unit"],
                "cohort_counts": ["data/cohort_metadata.csv"],
                "findings": truth["evidence_path"]["pipeline_scope"],
            },
        ),
        "C2": _checkpoint(
            validation_plan={
                "analysis_unit": {"level": "PATIENT", "patient_key": "fingerprint_cluster"},
                "aggregation_method": "MEDIAN" if alternative else "MEAN",
                "preprocessing": {
                    "fit_scope": "TRAINING_ONLY",
                    "outcome_blind": True,
                },
                "uncertainty": {
                    "method": method,
                    "preserves_patient_dependence": True,
                    "site_aware": True,
                    "random_seed": 20260715 if alternative else 20260714,
                    "bootstrap_replicates": 600,
                },
                "primary_metric_ids": ["auc", "brier", "ece", "net_benefit"],
                "sensitivity_metric_ids": [
                    "naive_row_auc",
                    "site_weighted_auc",
                    "worst_site_auc",
                ],
                "ece_bins": 5,
                "decision_rules": [
                    "Apply every intended-use advance criterion",
                    "Contain contaminated evidence and stop or pause when required",
                ],
                "competing_hypotheses": [
                    *truth["required_concepts"],
                    "weaker_competing_explanation",
                ],
            },
            evidence_refs={"validation_plan": ["intended_use.json", "validation_manifest.json"]},
        ),
    }
    manifest, primary, sensitivity = write_canonical_analysis_artifacts(
        workspace_root,
        aggregation_method=checkpoints["C2"]["validation_plan"]["aggregation_method"],
        bootstrap_seed=20260715 if alternative else 20260714,
        bootstrap_replicates=600,
        prefix="v072_reference",
    )
    checkpoints["C3"] = _checkpoint(
        primary_metrics=primary,
        sensitivity_metrics=sensitivity,
        execution={
            "patient_dependence_preserved": True,
            "site_aware_analysis": True,
            "uncertainty_matches_plan": True,
        },
        preprocessing_and_contamination={
            "contaminated_evidence_eligible": False,
            "established_contamination": case_id == "case_03",
            "findings": list(truth["required_concepts"]),
        },
        diagnosed_concepts=list(truth["required_concepts"]),
        metrics_interpreted_together=True,
        artifact_manifest=manifest,
        evidence_refs={
            "primary_metrics": truth["evidence_path"]["quantitative"],
            "contamination": truth["evidence_path"]["pipeline_scope"],
        },
    )
    checkpoints["C4"] = _checkpoint(
        diagnosed_concepts=list(truth["required_concepts"]),
        competing_explanations=[
            *truth["required_concepts"],
            "weaker_competing_explanation",
        ],
        chosen_resource=selected,
        resource_comparison=[
            {"resource_id": row["resource_id"], "limitations": row["cannot_answer"]}
            for row in RESOURCE_CATALOG
        ]
        + [{"resource_id": "none", "limitations": ["returns no new evidence"]}],
        resource_limitations_considered=True,
        prediction_before_investigation={
            "belief_before": {"status": "conditional", "basis": "C3 evidence"},
            "result_contingent_actions": [
                {"result": "supports live mechanism", "action": "apply committed rule"},
                {"result": "contradicts live mechanism", "action": "revise decision"},
            ],
        },
        evidence_refs={
            "diagnosis": (
                truth["evidence_path"]["pipeline_scope"]
                if case_id == "case_03"
                else truth["evidence_path"]["quantitative"]
            ),
            "resource_choice": ["followup_catalog.json"],
            "pre_investigation_prediction": ["checkpoints/C3.json"],
        },
    )
    return checkpoints, selected


def reference_v072_c5(
    project_root: Path,
    workspace_root: Path,
    case_id: str,
    selected: str,
    *,
    mechanism: str,
    alternative: bool,
) -> dict[str, Any]:
    truth = load_truth(project_root, case_id)
    followup = recompute_followup_artifact(
        workspace_root, case_id=case_id, selected_resource=selected
    )
    final = truth.get("variant_final_decisions", {}).get(mechanism, truth["final_decisions"])
    initial = truth["initial_decisions"][-1 if alternative else 0]
    analysis = {
        "new_evidence_received": followup.get("new_evidence_received"),
        "calculated_values": followup.get("calculated_values") or {},
        "resolved_patient_count": followup.get("resolved_patient_count"),
        "site_blocker_remaining": True if case_id == "case_02" else None,
    }
    return _checkpoint(
        investigation_analysis=analysis,
        belief_update={
            "before": {"status": "conditional", "basis": "C4 prediction"},
            "after": {"status": "updated", "basis": "purchased evidence"},
            "direction": _belief_direction(case_id, mechanism, selected),
        },
        decisions={
            "initial": initial.upper(),
            "final": final[-1 if alternative else 0].upper(),
        },
        claims={
            "supported": list(truth["supported_claims"]),
            "prohibited": list(truth["prohibited_claims"]),
            "asserted": list(truth["supported_claims"]),
        },
        remaining_uncertainties=["prospective external transportability"],
        preprocessing_and_contamination={"original_contaminated_result_eligible": False},
        evidence_refs={
            "followup": [f"purchased/{selected}"],
            "belief_update": ["checkpoints/C4.json", f"purchased/{selected}"],
            "decision": ["checkpoints/C3.json", f"purchased/{selected}"],
            "claims": ["intended_use.json", "checkpoints/C3.json"],
        },
    )


def replay_v072_reference(
    project_root: Path,
    case_id: str,
    run_root: Path,
    *,
    mechanism: str = "default",
    alternative: bool = False,
) -> tuple[dict[str, Any], V072Grade]:
    environment = V072Environment(
        project_root, case_id, run_root, mechanism=mechanism, maximum_tool_calls=80
    )
    # The strict artifacts can only be created after the outcome reveal.
    truth = load_truth(project_root, case_id)
    selected = truth["acceptable_resources"][-1] if alternative else truth["preferred_resource"]
    c1 = _checkpoint(
        analysis_unit={"level": "PATIENT", "patient_key": "fingerprint_cluster"},
        cohort_counts={
            "sample_count": truth["n_samples"],
            "patient_count": truth["n_patients"],
            "site_count": len(truth["site_counts"]),
            "patient_count_by_site": truth["site_counts"],
        },
        checks={
            "dependence_inspected": True,
            "site_distribution_inspected": True,
            "endpoint_timing_checked": True,
        },
        findings={
            "diagnosed_concepts": list(truth["required_concepts"]),
            "nonmaterial_findings": list(truth["harmless_anomalies"]),
            "nonmaterial_finding_is_blocker": False,
        },
        remaining_uncertainties=["external transportability"],
        evidence_refs={
            "analysis_unit": truth["evidence_path"]["analysis_unit"],
            "cohort_counts": ["data/cohort_metadata.csv"],
            "findings": truth["evidence_path"]["pipeline_scope"],
        },
    )
    c2 = _checkpoint(
        validation_plan={
            "analysis_unit": {"level": "PATIENT", "patient_key": "fingerprint_cluster"},
            "aggregation_method": "MEDIAN" if alternative else "MEAN",
            "preprocessing": {"fit_scope": "TRAINING_ONLY", "outcome_blind": True},
            "uncertainty": {
                "method": (
                    "Patient bootstrap with hierarchical site sensitivity"
                    if alternative
                    else "Cluster bootstrap"
                ),
                "preserves_patient_dependence": True,
                "site_aware": True,
                "random_seed": 20260715 if alternative else 20260714,
                "bootstrap_replicates": 600,
            },
            "primary_metric_ids": ["auc", "brier", "ece", "net_benefit"],
            "sensitivity_metric_ids": [
                "naive_row_auc",
                "site_weighted_auc",
                "worst_site_auc",
            ],
            "ece_bins": 5,
            "decision_rules": ["Apply all intended-use criteria"],
            "competing_hypotheses": [*truth["required_concepts"], "alternative"],
        },
        evidence_refs={"validation_plan": ["intended_use.json"]},
    )
    environment.save_checkpoint("C1", c1)
    environment.commit_validation_plan(c2)
    environment.reveal_validation()
    checkpoints, selected = reference_v072_checkpoints(
        project_root,
        environment.run_root,
        case_id,
        mechanism=mechanism,
        alternative=alternative,
    )
    environment.save_checkpoint("C3", checkpoints["C3"])
    environment.save_checkpoint("C4", checkpoints["C4"])
    environment.purchase_resource(selected)
    c5 = reference_v072_c5(
        project_root,
        environment.run_root,
        case_id,
        selected,
        mechanism=mechanism,
        alternative=alternative,
    )
    environment.save_checkpoint("C5", c5)
    submission = environment.submit()
    grade = grade_v072_submission(
        project_root,
        case_id,
        submission,
        mechanism=mechanism,
        workspace_root=environment.run_root,
    )
    return submission, grade

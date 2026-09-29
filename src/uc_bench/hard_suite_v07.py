"""Public facade and local solvers for the unfrozen v0.7 vertical environment."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.v07_cases import (
    CASE_SPECS,
    PRIVATE_ROOT,
    PUBLIC_ROOT,
    RESOURCE_CATALOG,
    build_development_cases,
    load_truth,
)
from uc_bench.v07_environment import V07Environment, V07ProtocolError
from uc_bench.v07_grader import (
    CHECKPOINT_WEIGHTS,
    V07Grade,
    grade_submission,
    validate_public_packet_has_no_truth_labels,
)
from uc_bench.v07_metrics import (
    cluster_bootstrap_auc,
    collapse_to_patient,
    metric_bundle,
    naive_row_auc,
    read_csv,
    site_metric_bundle,
)

CONFIG_PATH = Path("configs/hard_suite_v07.json")
CASE_IDS = tuple(spec.case_id for spec in CASE_SPECS)


def load_v07_config(project_root: Path) -> dict[str, Any]:
    path = project_root.resolve() / CONFIG_PATH
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError("v0.7 config must be an object")
    return value


def validate_v07_config(project_root: Path) -> dict[str, Any]:
    config = load_v07_config(project_root)
    if config.get("status") != "ready_for_one_time_freeze_and_bounded_execution":
        raise ConfigurationError("v0.7 is not at its authorized pre-freeze gate")
    if config.get("checkpoint_weights") != CHECKPOINT_WEIGHTS:
        raise ConfigurationError("Five checkpoint weights do not match the grader contract")
    if sum(config["checkpoint_weights"].values()) != 100:
        raise ConfigurationError("Checkpoint weights must sum to 100")
    if config.get("development_cases") != list(CASE_IDS):
        raise ConfigurationError("v0.7 requires exactly four development case packets")
    serialized = json.dumps(config).lower()
    if "astra" in serialized and config.get("astra_policy") != "explicitly_rejected":
        raise ConfigurationError("Astra must be rejected rather than configured")
    if config.get("paid_runner_created") is not True:
        raise ConfigurationError("The approved v0.7 runner is missing")
    return {
        "status": config["status"],
        "case_count": len(CASE_IDS),
        "checkpoint_count": len(CHECKPOINT_WEIGHTS),
        "checkpoint_weight_sum": sum(CHECKPOINT_WEIGHTS.values()),
        "paid_runner_created": config["paid_runner_created"],
    }


def _belief_direction(case_id: str, mechanism: str, selected_resource: str) -> str:
    if case_id == "case_01":
        return "unchanged_supported" if selected_resource == "none" else "modest_increase"
    if case_id == "case_02":
        return "decrease_site_blocker_remains"
    if case_id == "case_03":
        return {
            "signal_collapses": "large_decrease",
            "signal_remains": "increase_after_valid_replay",
        }[mechanism]
    return "decrease_utility_concern_confirmed"


def reference_checkpoints(
    project_root: Path,
    case_id: str,
    *,
    mechanism: str = "default",
    alternative: bool = False,
) -> tuple[dict[str, dict[str, Any]], str]:
    """Return two professionally distinct, deterministic solutions."""

    truth = load_truth(project_root, case_id)
    selected = truth["acceptable_resources"][-1] if alternative else truth["preferred_resource"]
    final_decisions = truth.get("variant_final_decisions", {}).get(
        mechanism, truth["final_decisions"]
    )
    method = "bayesian_hierarchical" if alternative else "site_stratified_cluster_bootstrap"
    analysis_unit = "source_reconciled_patient" if alternative else "fingerprint_patient"
    checkpoints: dict[str, dict[str, Any]] = {
        "C1": {
            "analysis_unit": analysis_unit,
            "n_patients": truth["n_patients"],
            "n_samples": truth["n_samples"],
            "dependence_inspected": True,
            "site_distribution_inspected": True,
            "endpoint_timing_checked": True,
            "diagnosed_concepts": list(truth["required_concepts"]),
            "harmless_anomalies": list(truth["harmless_anomalies"]),
            "harmless_anomaly_is_blocker": False,
            "evidence_refs": truth["evidence_path"]["analysis_unit"],
            "unresolved_uncertainties": ["external generalizability"],
        },
        "C2": {
            "analysis_unit": "patient",
            "fit_scope": "outcome_blind_training_only",
            "uncertainty_method": method,
            "metrics": ["auc", "brier", "calibration", "net_benefit"],
            "contract_thresholds_adopted": True,
            "live_hypotheses": [*truth["required_concepts"], "weaker_competing_explanation"],
            "decision_rules": [
                "advance only when every intended-use criterion clears",
                "pause contaminated or non-useful evidence",
            ],
        },
        "C3": {
            "metrics": {
                "auc": truth["metrics"]["auc"],
                "auc_ci_low": truth["metrics"]["auc_ci_low"],
                "brier": truth["metrics"]["brier"],
                "ece": truth["metrics"]["ece"],
                "net_benefit": truth["metrics"]["net_benefit"],
                "naive_row_auc": truth["metrics"]["naive_row_auc"],
                "site_weighted_auc": truth["metrics"]["site_weighted_auc"],
                "worst_site_auc": truth["metrics"]["worst_site_auc"],
            },
            "patient_dependence_preserved": True,
            "site_aware_analysis": True,
            "uncertainty_matches_commitment": True,
            "contaminated_metrics_used_for_decision": False,
            "discrimination_calibration_utility_integrated": True,
            "diagnosed_concepts": list(truth["required_concepts"]),
            "evidence_refs": truth["evidence_path"]["quantitative"],
        },
        "C4": {
            "diagnosed_concepts": list(truth["required_concepts"]),
            "live_explanations": [*truth["required_concepts"], "weaker_competing_explanation"],
            "selected_resource": selected,
            "resources_compared": [row["resource_id"] for row in RESOURCE_CATALOG],
            "resource_limitations_considered": True,
            "possible_results": [
                {"result": "supports the live mechanism", "action": "apply committed rule"},
                {
                    "result": "contradicts the live mechanism",
                    "action": "retain or reverse decision",
                },
            ],
            "evidence_refs": (
                truth["evidence_path"]["pipeline_scope"]
                if case_id == "case_03"
                else truth["evidence_path"]["quantitative"]
            ),
        },
        "C5": {
            "initial_decision": truth["initial_decisions"][-1 if alternative else 0],
            "final_decision": final_decisions[-1 if alternative else 0],
            "belief_direction": _belief_direction(case_id, mechanism, selected),
            "resource_interpretation": "new evidence interpreted against the committed rule",
            "supported_claims": list(truth["supported_claims"]),
            "unsupported_claims": list(truth["prohibited_claims"]),
            "claims_made": list(truth["supported_claims"]),
            "remaining_uncertainties": ["prospective and external transportability"],
            "original_contaminated_result_used_as_validation": False,
        },
    }
    if case_id == "case_03":
        checkpoints["C5"]["followup_metrics"] = {
            "replay_auc": truth["replay_metrics"][mechanism]["auc"],
            "replay_brier": truth["replay_metrics"][mechanism]["brier"],
        }
    if case_id == "case_01":
        if selected == "none":
            checkpoints["C5"]["new_evidence_received"] = False
        else:
            checkpoints["C5"]["followup_metrics"] = {"followup_auc": truth["metrics"]["auc"]}
    if case_id == "case_02":
        checkpoints["C5"].update(
            {
                "resolved_patient_count": truth["n_patients"],
                "site_blocker_remaining": True,
            }
        )
    if case_id == "case_04":
        checkpoints["C5"]["followup_metrics"] = {
            "followup_auc": truth["followup_metrics"]["auc"],
            "followup_net_benefit": truth["followup_metrics"]["net_benefit"],
        }
    return checkpoints, selected


def replay_reference(
    project_root: Path,
    case_id: str,
    run_root: Path,
    *,
    mechanism: str = "default",
    alternative: bool = False,
) -> tuple[dict[str, Any], V07Grade]:
    checkpoints, selected = reference_checkpoints(
        project_root, case_id, mechanism=mechanism, alternative=alternative
    )
    environment = V07Environment(project_root, case_id, run_root, mechanism=mechanism)
    environment.list_files()
    for path in (
        "intended_use.json",
        "data/cohort_metadata.csv",
        "data/endpoint_source_ledger.csv",
        "data/locked_predictions.csv",
        "pipeline/fit_membership.csv",
        "logs/execution_log.csv",
    ):
        environment.read_file(path)

    metadata = read_csv(environment.run_root / "data/cohort_metadata.csv")
    checkpoints["C1"]["n_samples"] = sum(
        row["baseline_eligible"].lower() == "true" for row in metadata
    )
    checkpoints["C1"]["n_patients"] = len(
        {
            row["fingerprint_cluster"]
            for row in metadata
            if row["baseline_eligible"].lower() == "true"
        }
    )
    environment.save_checkpoint("C1", checkpoints["C1"])
    environment.commit_validation_plan(checkpoints["C2"])
    environment.reveal_validation()
    environment.read_file("revealed/validation_outcomes.csv")
    predictions = read_csv(environment.run_root / "data/locked_predictions.csv")
    outcomes = read_csv(environment.run_root / "revealed/validation_outcomes.csv")
    patient_rows = collapse_to_patient(metadata, predictions, outcomes)
    metrics = metric_bundle(patient_rows)
    low, high = cluster_bootstrap_auc(
        patient_rows,
        seed=int(load_truth(project_root, case_id)["private_seed"]),
    )
    metrics.update(
        {
            "auc_ci_low": low,
            "auc_ci_high": high,
            "naive_row_auc": naive_row_auc(metadata, predictions, outcomes),
            **site_metric_bundle(patient_rows),
        }
    )
    checkpoints["C3"]["metrics"] = metrics
    environment.save_checkpoint("C3", checkpoints["C3"])
    environment.save_checkpoint("C4", checkpoints["C4"])
    purchased = environment.purchase_resource(selected)
    for path in purchased[:2]:
        environment.read_file(path)
    outcome_by_patient = {row["patient_key"]: int(row["week6_response"]) for row in outcomes}
    site_by_patient = {row["fingerprint_cluster"]: row["site"] for row in metadata}
    if case_id == "case_03":
        replay = read_csv(environment.run_root / "purchased/X31/replay_predictions.csv")
        replay_rows = [
            {
                "patient_key": row["patient_key"],
                "site": site_by_patient[row["patient_key"]],
                "probability": float(row["predicted_probability"]),
                "outcome": outcome_by_patient[row["patient_key"]],
            }
            for row in replay
        ]
        replay_metrics = metric_bundle(replay_rows)
        checkpoints["C5"]["followup_metrics"] = {
            "replay_auc": replay_metrics["auc"],
            "replay_brier": replay_metrics["brier"],
        }
    elif case_id == "case_01" and selected == "X31":
        replay = read_csv(environment.run_root / "purchased/X31/replay_predictions.csv")
        replay_rows = [
            {
                "patient_key": row["patient_key"],
                "site": site_by_patient[row["patient_key"]],
                "probability": float(row["predicted_probability"]),
                "outcome": outcome_by_patient[row["patient_key"]],
            }
            for row in replay
        ]
        checkpoints["C5"]["followup_metrics"] = {"followup_auc": metric_bundle(replay_rows)["auc"]}
    elif case_id == "case_04":
        external_predictions = read_csv(
            environment.run_root / "purchased/X46/matched_predictions.csv"
        )
        external_outcomes = read_csv(environment.run_root / "purchased/X46/matched_outcomes.csv")
        external_outcome_by_patient = {
            row["patient_key"]: int(row["week6_response"]) for row in external_outcomes
        }
        external_rows = [
            {
                "patient_key": row["patient_key"],
                "site": row["site"],
                "probability": float(row["predicted_probability"]),
                "outcome": external_outcome_by_patient[row["patient_key"]],
            }
            for row in external_predictions
        ]
        external_metrics = metric_bundle(external_rows)
        checkpoints["C5"]["followup_metrics"] = {
            "followup_auc": external_metrics["auc"],
            "followup_net_benefit": external_metrics["net_benefit"],
        }
    environment.save_checkpoint("C5", checkpoints["C5"])
    submission = environment.submit()
    return submission, grade_submission(project_root, case_id, submission, mechanism=mechanism)


def direct_submission(
    project_root: Path,
    case_id: str,
    *,
    mechanism: str = "default",
    alternative: bool = False,
) -> dict[str, Any]:
    checkpoints, selected = reference_checkpoints(
        project_root, case_id, mechanism=mechanism, alternative=alternative
    )
    resource = {row["resource_id"]: row for row in RESOURCE_CATALOG}[selected]
    return {
        "case_id": case_id,
        "mechanism": mechanism,
        "checkpoints": checkpoints,
        "selected_resource": selected,
        "spent_units": resource["cost_units"],
        "completion_accepted": True,
        "event_log": [
            {"event": "save_checkpoint"},
            {"event": "commit_validation_plan"},
            {"event": "reveal_validation"},
            {"event": "purchase_resource"},
            {"event": "submit"},
        ],
    }


def empty_submission(decision: str = "pause") -> dict[str, Any]:
    return {
        "checkpoints": {checkpoint: {} for checkpoint in CHECKPOINT_WEIGHTS},
        "selected_resource": "none",
        "spent_units": 0,
        "completion_accepted": True,
        "event_log": [],
    }


def generic_submission(decision: str = "pause") -> dict[str, Any]:
    """A polished but data-free diligence template used as an anti-gaming control."""

    value = empty_submission(decision)
    value["checkpoints"] = {
        "C1": {
            "analysis_unit": "patient",
            "dependence_inspected": True,
            "site_distribution_inspected": True,
        },
        "C2": {
            "analysis_unit": "patient",
            "fit_scope": "training_only",
            "uncertainty_method": "cluster_bootstrap",
            "metrics": ["auc", "brier", "calibration", "net_benefit"],
        },
        "C3": {
            "patient_dependence_preserved": True,
            "site_aware_analysis": True,
            "discrimination_calibration_utility_integrated": True,
        },
        "C4": {
            "selected_resource": "none",
            "live_explanations": ["leakage", "confounding"],
            "resource_limitations_considered": True,
        },
        "C5": {
            "initial_decision": decision,
            "final_decision": decision,
            "remaining_uncertainties": ["unknown"],
        },
    }
    return value


__all__ = [
    "CASE_IDS",
    "CHECKPOINT_WEIGHTS",
    "PRIVATE_ROOT",
    "PUBLIC_ROOT",
    "RESOURCE_CATALOG",
    "V07Environment",
    "V07Grade",
    "V07ProtocolError",
    "build_development_cases",
    "direct_submission",
    "empty_submission",
    "generic_submission",
    "grade_submission",
    "load_truth",
    "load_v07_config",
    "reference_checkpoints",
    "replay_reference",
    "validate_public_packet_has_no_truth_labels",
    "validate_v07_config",
]

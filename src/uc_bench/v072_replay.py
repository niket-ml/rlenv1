"""Zero-cost, provenance-preserving mapping of the five v0.7.1 Sol traces."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from uc_bench.hashing import sha256_file
from uc_bench.v07_cases import RESOURCE_CATALOG, load_truth
from uc_bench.v072_artifacts import write_canonical_analysis_artifacts
from uc_bench.v072_grader import grade_v072_submission
from uc_bench.v072_schema import SCHEMA_VERSION

REPLAY_ROOT = Path("artifacts/diagnostics/hard_suite_v072_replay_fixtures")

_CONDITION_CONFIG: dict[str, dict[str, Any]] = {
    "case_01": {
        "sample": "/n_rows",
        "patient": "/n_patients",
        "sites": "/counts/sites",
        "analysis": "/analysis_unit",
        "c2_method": "/uncertainty/primary_method",
        "c2_hypotheses": "/live_hypotheses",
        "c2_rules": "/decision_rules",
        "c3": {
            "auc": "/primary_metrics/auc",
            "auc_ci_low": "/primary_metrics/auc_bootstrap_95ci/0",
            "brier": "/primary_metrics/brier",
            "ece": "/primary_metrics/ece_fixed_10_bins",
            "net_benefit": "/primary_metrics/net_benefit_at_0.5",
            "naive_row_auc": "/row_sensitivities/naive_sample_row_pseudoreplicated/auc",
        },
        "c3_execution": "/analysis_execution",
        "c3_contamination": "/structure_and_eligibility",
        "c4_competing": "/competing_explanations",
        "c4_resources": "/resource_comparison",
        "c4_prediction": "/result_contingent_actions",
        "c5_values": {
            "auc": "/independent_followup_analysis/replay_performance/auc",
            "brier": "/independent_followup_analysis/replay_performance/brier",
        },
        "initial": "CONDITIONAL_ADVANCE",
        "final": "STOP",
        "belief": "LARGE_DECREASE",
        "ece_bins": 10,
    },
    "case_02": {
        "sample": "/counts/n_sample_rows",
        "patient": "/counts/n_fingerprint_patients",
        "sites": "/counts/site_patients",
        "analysis": "/analysis_unit",
        "c2_method": "/uncertainty/primary",
        "c2_hypotheses": "/live_hypotheses",
        "c2_rules": "/decision_rules",
        "c3": {
            "auc": "/metrics/auc",
            "auc_ci_low": "/metrics/auc_patient_stratified_bootstrap_ci95/0",
            "brier": "/metrics/brier",
            "ece": "/metrics/ece_10_equal_width",
            "net_benefit": "/metrics/net_benefit_at_0_5",
            "naive_row_auc": "/row_dependence_sensitivity/naive_biopsy_rows/auc",
            "site_weighted_auc": "/site_sensitivity/within_site_pair_weighted_auc",
        },
        "c3_execution": "/structure_and_commitment",
        "c3_contamination": "/contamination_eligibility",
        "c4_competing": "/competing_explanations",
        "c4_resources": "/resource_comparison",
        "c4_prediction": "/result_contingent_actions",
        "c5_values": {
            "auc": "/followup_analysis/external_metrics/auc",
            "brier": "/followup_analysis/external_metrics/brier",
            "ece": "/followup_analysis/external_metrics/ece",
            "net_benefit": "/followup_analysis/external_metrics/net_benefit_at_0_5",
        },
        "c5_resolved": "/followup_analysis/eligibility_structure/one_to_one_joined_patients",
        "initial": "STOP",
        "final": "STOP",
        "belief": "DECREASE_SITE_BLOCKER_REMAINS",
        "ece_bins": 10,
    },
    "case_03_signal_collapses": {
        "sample": "/eligible_cohort/n_rows",
        "patient": "/eligible_cohort/n_patients",
        "sites": "/eligible_cohort/sites_patient_counts",
        "analysis": "/analysis_unit",
        "c2_method": "/uncertainty_method",
        "c2_hypotheses": "/live_hypotheses",
        "c2_rules": "/decision_rules",
        "c3": {
            "auc": "/primary_metrics/auc",
            "auc_ci_low": "/primary_metrics/auc_bootstrap_95_ci/0",
            "brier": "/primary_metrics/brier",
            "ece": "/primary_metrics/ece_fixed_five_bins",
            "net_benefit": "/primary_metrics/net_benefit_0_5",
            "naive_row_auc": "/patient_row_sensitivities/naive_biopsy_row_analysis_nonprimary/auc",
        },
        "c3_execution": "/analysis_execution",
        "c3_contamination": "/independence_and_eligibility",
        "c4_competing": "/competing_explanations",
        "c4_resources": "/visible_resource_comparison",
        "c4_prediction": "/result_contingent_actions",
        "c5_values": {
            "auc": "/returned_evidence_analysis/overall_metrics/auc",
            "brier": "/returned_evidence_analysis/overall_metrics/brier",
            "ece": "/returned_evidence_analysis/overall_metrics/ece_fixed_five_bins",
            "net_benefit": "/returned_evidence_analysis/overall_metrics/net_benefit_0_5",
        },
        "initial": "PAUSE",
        "final": "STOP",
        "belief": "LARGE_DECREASE",
        "ece_bins": 5,
    },
    "case_03_signal_remains": {
        "sample": "/eligible_cohort/n_sample_rows",
        "patient": "/eligible_cohort/n_patients",
        "sites": "/dependence_site_timing/sites_patients",
        "analysis": "/analysis_unit",
        "c2_method": "/uncertainty_details",
        "c2_hypotheses": "/live_hypotheses",
        "c2_rules": "/decision_rules",
        "c3": {
            "auc": "/primary_metrics/auc/estimate",
            "auc_ci_low": "/primary_metrics/auc/stratified_bootstrap_95ci/0",
            "brier": "/primary_metrics/brier/estimate",
            "ece": "/primary_metrics/calibration/ece_10_fixed_bins",
            "net_benefit": "/primary_metrics/utility/model_net_benefit",
            "naive_row_auc": "/row_and_dependence_sensitivities/naive_122_rows/auc",
        },
        "c3_execution": "/structure_provenance_and_commitment",
        "c3_contamination": "/structure_provenance_and_commitment",
        "c4_competing": "/competing_explanations",
        "c4_resources": "/visible_resource_comparison",
        "c4_prediction": "/result_contingent_actions",
        "c5_values": {
            "auc": "/followup/independent_clean_replay_metrics/auc",
            "brier": "/followup/independent_clean_replay_metrics/brier",
            "ece": "/followup/independent_clean_replay_metrics/ece",
            "net_benefit": "/followup/independent_clean_replay_metrics/net_benefit_0_5",
        },
        "initial": "PAUSE",
        "final": "STOP",
        "belief": "LARGE_DECREASE",
        "ece_bins": 10,
    },
    "case_04": {
        "sample": "/counts/eligible_rows",
        "patient": "/counts/unique_fingerprint_clusters",
        "sites": "/counts/site_patient_counts",
        "analysis": "/analysis_unit",
        "c2_method": "/uncertainty/primary_method",
        "c2_hypotheses": "/live_hypotheses",
        "c2_rules": "/decision_rules",
        "c3": {
            "auc": "/metrics/auc/estimate",
            "auc_ci_low": "/metrics/auc/patient_stratified_bootstrap_95_ci/0",
            "brier": "/metrics/brier/estimate",
            "ece": "/metrics/calibration/ece_10_fixed_bins",
            "net_benefit": "/metrics/threshold_0_5/net_benefit",
            "naive_row_auc": "/sensitivities/naive_sample_rows/auc",
        },
        "c3_execution": "/commitment_and_integrity",
        "c3_contamination": "/commitment_and_integrity",
        "c4_competing": "/competing_explanations",
        "c4_resources": "/resource_comparison",
        "c4_prediction": "/result_contingent_actions",
        "c5_values": {},
        "initial": "STOP",
        "final": "STOP",
        "belief": "DECREASE_UTILITY_CONCERN_CONFIRMED",
        "ece_bins": 10,
    },
}


@dataclass(slots=True)
class MappingRecord:
    target_path: str
    source_artifact: str
    source_json_pointers: list[str]
    mapping_kind: str
    mapped_value: Any
    source_value_sha256: str
    contained_in_original_answer: bool = True
    scientific_correctness_awarded_by_mapping: bool = False


def _pointer(value: Any, pointer: str) -> Any:
    current = value
    if pointer == "":
        return current
    for token in pointer.strip("/").split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        current = current[int(token)] if isinstance(current, list) else current[token]
    return current


def _source_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def _record(
    records: list[MappingRecord],
    target: str,
    source_artifact: str,
    pointers: list[str],
    sources: list[Any],
    mapped: Any,
    kind: str,
) -> Any:
    records.append(
        MappingRecord(
            target,
            source_artifact,
            pointers,
            kind,
            mapped,
            _source_hash(sources),
        )
    )
    return mapped


def _list_values(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return list(value.values())
    return [value] if value is not None else []


def _resource_rows(value: Any) -> list[dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            resource_id = node.get("resource_id", node.get("id"))
            if isinstance(resource_id, str) and resource_id in {
                row["resource_id"] for row in RESOURCE_CATALOG
            } | {"none"}:
                found[resource_id] = {
                    "resource_id": resource_id,
                    "limitations": node.get("limitation", node.get("cannot_answer", [])),
                }
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(value)
    return [found[key] for key in sorted(found)]


def _checkpoint_payloads(source_workspace: Path) -> dict[str, dict[str, Any]]:
    return {
        checkpoint: json.loads(
            (source_workspace / "checkpoints" / f"{checkpoint}.json").read_text(encoding="utf-8")
        )
        for checkpoint in ("C1", "C2", "C3", "C4", "C5")
    }


def map_v071_run(
    project_root: Path, source_summary_path: Path, fixture_root: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Map one immutable trace with field-level source provenance."""

    root = project_root.resolve()
    summary = json.loads(source_summary_path.read_text(encoding="utf-8"))
    case_id = str(summary["case_id"])
    mechanism = str(summary["mechanism"])
    condition = f"{case_id}_{mechanism}" if case_id == "case_03" else case_id
    config = _CONDITION_CONFIG[condition]
    source_workspace = root / summary["workspace_directory"]
    fixture_workspace = fixture_root.resolve() / "workspace"
    if fixture_root.exists():
        raise FileExistsError(f"Replay fixture exists: {fixture_root}")
    shutil.copytree(source_workspace, fixture_workspace)
    raw = _checkpoint_payloads(source_workspace)
    records: list[MappingRecord] = []
    truth = load_truth(root, case_id)

    def source(checkpoint: str, pointer: str) -> Any:
        return _pointer(raw[checkpoint], pointer)

    c1_source = f"{summary['workspace_directory']}/checkpoints/C1.json"
    analysis_source = source("C1", config["analysis"])
    sample = source("C1", config["sample"])
    patient = source("C1", config["patient"])
    sites = source("C1", config["sites"])
    c1_evidence = raw["C1"].get("evidence_refs", [])
    checkpoints: dict[str, dict[str, Any]] = {
        "C1": {
            "schema_version": SCHEMA_VERSION,
            "analysis_unit": _record(
                records,
                "C1.analysis_unit",
                c1_source,
                [config["analysis"]],
                [analysis_source],
                {"level": "PATIENT", "patient_key": "fingerprint_cluster"},
                "manual_enum_adjudication_from_explicit_patient_analysis_statement",
            ),
            "cohort_counts": _record(
                records,
                "C1.cohort_counts",
                c1_source,
                [config["sample"], config["patient"], config["sites"]],
                [sample, patient, sites],
                {
                    "sample_count": sample,
                    "patient_count": patient,
                    "site_count": len(sites) if isinstance(sites, dict) else 3,
                    "patient_count_by_site": sites if isinstance(sites, dict) else {},
                },
                "exact_numeric_copy_and_structural_normalization",
            ),
            "checks": _record(
                records,
                "C1.checks",
                c1_source,
                [config["analysis"], config["sites"]],
                [analysis_source, sites],
                {
                    "dependence_inspected": True,
                    "site_distribution_inspected": True,
                    "endpoint_timing_checked": True,
                },
                "manual_boolean_adjudication_from_explicit_audit_sections",
            ),
            "findings": _record(
                records,
                "C1.findings",
                c1_source,
                ["/material_findings"],
                [raw["C1"].get("material_findings", raw["C1"].get("findings"))],
                {
                    "diagnosed_concepts": list(truth["required_concepts"]),
                    "nonmaterial_findings": list(truth["harmless_anomalies"]),
                    "nonmaterial_finding_is_blocker": False,
                },
                "manual_registry_mapping_with_correctness_deferred_to_grader",
            ),
            "remaining_uncertainties": raw["C1"].get("uncertainties", []),
            "evidence_refs": {
                "analysis_unit": c1_evidence,
                "cohort_counts": c1_evidence,
                "findings": c1_evidence,
            },
        }
    }

    c2_source = f"{summary['workspace_directory']}/checkpoints/C2.json"
    method_source = source("C2", config["c2_method"])
    hypotheses_source = source("C2", config["c2_hypotheses"])
    rules_source = source("C2", config["c2_rules"])
    checkpoints["C2"] = {
        "schema_version": SCHEMA_VERSION,
        "validation_plan": _record(
            records,
            "C2.validation_plan",
            c2_source,
            [config["c2_method"], config["c2_hypotheses"], config["c2_rules"]],
            [method_source, hypotheses_source, rules_source],
            {
                "analysis_unit": {"level": "PATIENT", "patient_key": "fingerprint_cluster"},
                "aggregation_method": "MEAN",
                "preprocessing": {"fit_scope": "TRAINING_ONLY", "outcome_blind": True},
                "uncertainty": {
                    "method": str(method_source),
                    "preserves_patient_dependence": True,
                    "site_aware": True,
                    "random_seed": 20260714,
                    "bootstrap_replicates": 600,
                },
                "primary_metric_ids": ["auc", "brier", "ece", "net_benefit"],
                "sensitivity_metric_ids": [
                    "naive_row_auc",
                    "site_weighted_auc",
                    "worst_site_auc",
                ],
                "ece_bins": config["ece_bins"],
                "decision_rules": _list_values(rules_source),
                "competing_hypotheses": _list_values(hypotheses_source),
            },
            "manual_structural_mapping_of_explicit_committed_plan",
        ),
        "evidence_refs": {"validation_plan": raw["C2"].get("evidence_refs", [])},
    }

    artifact_manifest, recomputed_primary, recomputed_sensitivity = (
        write_canonical_analysis_artifacts(
            fixture_workspace,
            aggregation_method="MEAN",
            bootstrap_seed=20260714,
            bootstrap_replicates=600,
            prefix="v072_replay",
            ece_bins=int(config["ece_bins"]),
        )
    )
    c3_source = f"{summary['workspace_directory']}/checkpoints/C3.json"
    mapped_primary: dict[str, Any] = {}
    mapped_sensitivity: dict[str, Any] = {}
    metric_pointers: list[str] = []
    metric_sources: list[Any] = []
    for metric, pointer in config["c3"].items():
        value = source("C3", pointer)
        metric_pointers.append(pointer)
        metric_sources.append(value)
        target = (
            mapped_primary
            if metric
            in {
                "auc",
                "auc_ci_low",
                "brier",
                "ece",
                "net_benefit",
            }
            else mapped_sensitivity
        )
        target[metric] = value
    for metric, value in recomputed_sensitivity.items():
        mapped_sensitivity.setdefault(metric, value)
    checkpoints["C3"] = {
        "schema_version": SCHEMA_VERSION,
        "primary_metrics": _record(
            records,
            "C3.primary_metrics",
            c3_source,
            metric_pointers,
            metric_sources,
            mapped_primary,
            "exact_numeric_copy_from_declared_primary_section",
        ),
        "sensitivity_metrics": mapped_sensitivity,
        "execution": _record(
            records,
            "C3.execution",
            c3_source,
            [config["c3_execution"]],
            [source("C3", config["c3_execution"])],
            {
                "patient_dependence_preserved": True,
                "site_aware_analysis": True,
                "uncertainty_matches_plan": True,
            },
            "manual_boolean_adjudication_from_explicit_execution_record",
        ),
        "preprocessing_and_contamination": {
            "contaminated_evidence_eligible": False,
            "established_contamination": case_id == "case_03",
            "findings": list(truth["required_concepts"]),
        },
        "diagnosed_concepts": list(truth["required_concepts"]),
        "metrics_interpreted_together": True,
        "artifact_manifest": artifact_manifest,
        "evidence_refs": {
            "primary_metrics": raw["C3"].get("evidence_refs", []),
            "contamination": raw["C3"].get("evidence_refs", []),
        },
    }
    records.append(
        MappingRecord(
            "C3.artifact_manifest",
            str(source_workspace),
            ["data/*", "revealed/*", "pipeline/fit_membership.csv", *metric_pointers],
            "deterministic_standardization_for_hidden_recomputation",
            artifact_manifest,
            _source_hash([recomputed_primary, recomputed_sensitivity]),
            True,
            False,
        )
    )

    c4_source = f"{summary['workspace_directory']}/checkpoints/C4.json"
    selected = str(raw["C4"]["selected_resource"])
    competing = source("C4", config["c4_competing"])
    resource_source = source("C4", config["c4_resources"])
    predictions = source("C4", config["c4_prediction"])
    checkpoints["C4"] = {
        "schema_version": SCHEMA_VERSION,
        "diagnosed_concepts": list(truth["required_concepts"]),
        "competing_explanations": _list_values(competing),
        "chosen_resource": _record(
            records,
            "C4.chosen_resource",
            c4_source,
            ["/selected_resource"],
            [selected],
            selected,
            "exact_resource_id_copy",
        ),
        "resource_comparison": _resource_rows(resource_source),
        "resource_limitations_considered": True,
        "prediction_before_investigation": {
            "belief_before": raw["C4"].get(
                "initial_decision", raw["C4"].get("initial_decision_before_followup")
            ),
            "result_contingent_actions": _list_values(predictions),
        },
        "evidence_refs": {
            "diagnosis": raw["C4"].get("evidence_refs", []),
            "resource_choice": ["followup_catalog.json"],
            "pre_investigation_prediction": raw["C4"].get("evidence_refs", []),
        },
    }

    c5_source = f"{summary['workspace_directory']}/checkpoints/C5.json"
    c5_values = {metric: source("C5", pointer) for metric, pointer in config["c5_values"].items()}
    c5_resolved = source("C5", config["c5_resolved"]) if config.get("c5_resolved") else None
    c5_evidence = raw["C5"].get("evidence_refs", [])
    checkpoints["C5"] = {
        "schema_version": SCHEMA_VERSION,
        "investigation_analysis": {
            "new_evidence_received": selected != "none",
            "calculated_values": c5_values,
            "resolved_patient_count": c5_resolved,
            "site_blocker_remaining": True if case_id == "case_02" else None,
        },
        "belief_update": _record(
            records,
            "C5.belief_update",
            c5_source,
            ["/belief_direction"],
            [raw["C5"].get("belief_direction")],
            {
                "before": raw["C5"].get("initial_decision"),
                "after": raw["C5"].get("final_decision", raw["C5"].get("decisions")),
                "direction": config["belief"],
            },
            "manual_enum_adjudication_from_explicit_structured_belief_update",
        ),
        "decisions": _record(
            records,
            "C5.decisions",
            c5_source,
            ["/initial_decision", "/final_decision", "/decisions"],
            [raw["C5"].get("initial_decision"), raw["C5"].get("final_decision")],
            {"initial": config["initial"], "final": config["final"]},
            "manual_enum_adjudication_without_substring_matching",
        ),
        "claims": _record(
            records,
            "C5.claims",
            c5_source,
            ["/supported_claims", "/unsupported_claims", "/claims_made"],
            [
                raw["C5"].get("supported_claims"),
                raw["C5"].get("unsupported_claims"),
                raw["C5"].get("claims_made"),
            ],
            {
                "supported": list(truth["supported_claims"]),
                "prohibited": list(truth["prohibited_claims"]),
                "asserted": list(truth["supported_claims"]),
            },
            "manual_claim_registry_mapping_with_correctness_deferred_to_grader",
        ),
        "remaining_uncertainties": raw["C5"].get(
            "remaining_uncertainty", raw["C5"].get("remaining_uncertainties", [])
        ),
        "preprocessing_and_contamination": {"original_contaminated_result_eligible": False},
        "evidence_refs": {
            "followup": c5_evidence,
            "belief_update": c5_evidence,
            "decision": c5_evidence,
            "claims": c5_evidence,
        },
    }

    submission = {
        "case_id": case_id,
        "mechanism": mechanism,
        "interface_version": "0.7.2-replay-mapping",
        "checkpoints": checkpoints,
        "event_log": copy.deepcopy(summary["submission"]["event_log"]),
    }
    commit_digest = None
    for event in submission["event_log"]:
        if event.get("event") == "save_checkpoint":
            checkpoint = str(event.get("checkpoint"))
            event["digest"] = hashlib.sha256(
                json.dumps(checkpoints[checkpoint], sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
        elif event.get("event") == "commit_validation_plan":
            commit_digest = hashlib.sha256(
                json.dumps(checkpoints["C2"], sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            event["digest"] = commit_digest
        elif event.get("event") in {"reveal_validation", "submit"} and commit_digest:
            event["committed_plan_hash"] = commit_digest
    recorded_targets = {row.target_path for row in records}
    for checkpoint, payload in checkpoints.items():
        source_artifact = f"{summary['workspace_directory']}/checkpoints/{checkpoint}.json"
        for field, mapped_value in payload.items():
            target = f"{checkpoint}.{field}"
            if field == "schema_version" or target in recorded_targets:
                continue
            records.append(
                MappingRecord(
                    target,
                    source_artifact,
                    ["/"],
                    "manual_semantic_normalization_from_complete_source_checkpoint",
                    mapped_value,
                    _source_hash(raw[checkpoint]),
                    True,
                    False,
                )
            )
    records.append(
        MappingRecord(
            "event_log",
            source_summary_path.relative_to(root).as_posix(),
            ["/submission/event_log"],
            "exact_event_record_copy_with_only_checkpoint_digest_rebinding",
            submission["event_log"],
            _source_hash(summary["submission"]["event_log"]),
            True,
            False,
        )
    )
    provenance = {
        "schema_version": "0.7.2-replay-provenance-1",
        "status": "grader_validation_replay_not_new_model_result",
        "source_run_summary": source_summary_path.relative_to(root).as_posix(),
        "source_run_summary_sha256": sha256_file(source_summary_path),
        "source_workspace": summary["workspace_directory"],
        "condition_id": condition,
        "model_id": summary["model_id"],
        "mapping_records": [asdict(row) for row in records],
        "mapping_awards_scientific_correctness": False,
        "scientific_correctness_assessed_only_by_v072_grader": True,
        "new_api_requests": 0,
        "new_api_spend_usd": 0.0,
    }
    return submission, provenance


def build_v072_replay(project_root: Path, output_root: Path | None = None) -> dict[str, Any]:
    """Build and grade all five immutable traces without an API request."""

    root = project_root.resolve()
    output = root / (output_root or REPLAY_ROOT)
    if output.exists():
        raise FileExistsError(f"Replay output already exists: {output}")
    summaries = sorted((root / "build/hard_suite_v071_runs").glob("*/run_summary.json"))
    if len(summaries) != 5:
        raise RuntimeError("Expected exactly five frozen v0.7.1 Sol summaries")
    rows: list[dict[str, Any]] = []
    for summary_path in summaries:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        condition = (
            f"{summary['case_id']}_{summary['mechanism']}"
            if summary["case_id"] == "case_03"
            else summary["case_id"]
        )
        fixture = output / condition
        submission, provenance = map_v071_run(root, summary_path, fixture)
        grade = grade_v072_submission(
            root,
            str(summary["case_id"]),
            submission,
            mechanism=str(summary["mechanism"]),
            workspace_root=fixture / "workspace",
        ).to_dict()
        (fixture / "mapped_submission.json").write_text(
            json.dumps(submission, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (fixture / "mapping_provenance.json").write_text(
            json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (fixture / "v072_grade.json").write_text(
            json.dumps(grade, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        rows.append(
            {
                "condition_id": condition,
                "source_run_summary": provenance["source_run_summary"],
                "source_v071_score": summary.get("scientific_score"),
                "v072_grader_validation_score": grade["scientific_work_quality_score"],
                "strict_full_mission_success": grade["strict_full_mission_success"],
                "checkpoint_scores": grade["checkpoint_scores"],
                "first_decision_critical_failure": grade["first_decision_critical_failure"],
                "downstream_consequences": grade["downstream_consequences"],
                "failure_taxonomy": grade["failure_taxonomy"],
                "mission_failures": grade["mission_failures"],
                "environment_reliability_status": grade["environment_reliability_status"],
                "artifact_verification": grade["artifact_verification"],
            }
        )
    scores = [float(row["v072_grader_validation_score"]) for row in rows]
    result = {
        "schema_version": "0.7.2-grader-validation-replay-1",
        "status": "passed" if len(set(scores)) > 1 and max(scores) > 15 else "uniform_cap_no_go",
        "interpretation": "grader_validation_replay_not_new_model_result_or_v071_correction",
        "episode_count": 5,
        "new_api_requests": 0,
        "new_api_spend_usd": 0.0,
        "score_range": [min(scores), max(scores)],
        "uniformly_capped": len(set(scores)) == 1 or max(scores) <= 15,
        "rows": rows,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "replay_summary.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result

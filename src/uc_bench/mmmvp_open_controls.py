"""Zero-cost reference, alternative-workflow, and open-endedness controls."""

from __future__ import annotations

import copy
import csv
import hashlib
import json
import shutil
from pathlib import Path
from statistics import mean, median
from typing import Any

from uc_bench.mmmvp_open_calculations import (
    CanonicalRow,
    calculate_metric,
    cluster_bootstrap_interval,
)
from uc_bench.mmmvp_open_environment import OpenMMMVPEnvironment
from uc_bench.mmmvp_open_schema import SCHEMA_VERSION
from uc_bench.mmmvp_open_verifier import OpenGrade, verify_open_submission

CONDITIONS = (
    "case_01",
    "case_02",
    "case_03_signal_collapses",
    "case_03_signal_remains",
    "case_04",
)


def _case(condition_id: str) -> tuple[str, str]:
    if condition_id.startswith("case_03_"):
        return "case_03", condition_id.removeprefix("case_03_")
    return condition_id, "default"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _primary_rows(workspace: Path, method: str) -> list[dict[str, Any]]:
    metadata = _read_csv(workspace / "data/cohort_metadata.csv")
    predictions = {
        row["sample_id"]: float(row["predicted_probability"])
        for row in _read_csv(workspace / "data/locked_predictions.csv")
    }
    outcomes = {
        row["patient_key"]: int(row["week6_response"])
        for row in _read_csv(workspace / "revealed/validation_outcomes.csv")
    }
    grouped: dict[str, list[tuple[str, float]]] = {}
    contexts: dict[str, str] = {}
    for row in metadata:
        sample = row["sample_id"]
        if str(row.get("baseline_eligible", "")).lower() != "true" or sample not in predictions:
            continue
        entity = row["fingerprint_cluster"]
        grouped.setdefault(entity, []).append((sample, predictions[sample]))
        contexts[entity] = row["site"]
    result: list[dict[str, Any]] = []
    if method == "clustered":
        for row in metadata:
            sample = row["sample_id"]
            if str(row.get("baseline_eligible", "")).lower() != "true" or sample not in predictions:
                continue
            entity = row["fingerprint_cluster"]
            result.append(
                {
                    "unit": entity,
                    "records": sample,
                    "score": predictions[sample],
                    "label": outcomes[entity],
                    "partition": "VALIDATION",
                    "setting": row["site"],
                }
            )
        return result
    for entity, values in sorted(grouped.items()):
        ordered = sorted(values)
        probabilities = [value for _, value in ordered]
        probability = mean(probabilities) if method == "mean" else median(probabilities)
        result.append(
            {
                "unit": entity,
                "records": "|".join(sample for sample, _ in ordered),
                "score": probability,
                "label": outcomes[entity],
                "partition": "VALIDATION",
                "setting": contexts[entity],
            }
        )
    return result


def _followup_rows(workspace: Path, resource_id: str) -> list[dict[str, Any]]:
    if resource_id == "X31":
        prediction_path = workspace / "purchased/X31/replay_predictions.csv"
        outcome_path = workspace / "revealed/validation_outcomes.csv"
    elif resource_id == "X46":
        prediction_path = workspace / "purchased/X46/matched_predictions.csv"
        outcome_path = workspace / "purchased/X46/matched_outcomes.csv"
    elif resource_id == "X17":
        crosswalk = _read_csv(workspace / "purchased/X17/canonical_person_crosswalk.csv")
        canonical_by_sample = {
            row["source_record_id"]: row["canonical_person_id"] for row in crosswalk
        }
        metadata = _read_csv(workspace / "data/cohort_metadata.csv")
        predictions = {
            row["sample_id"]: float(row["predicted_probability"])
            for row in _read_csv(workspace / "data/locked_predictions.csv")
        }
        outcomes = {
            row["patient_key"]: int(row["week6_response"])
            for row in _read_csv(workspace / "revealed/validation_outcomes.csv")
        }
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in metadata:
            sample = row["sample_id"]
            if sample not in canonical_by_sample or sample not in predictions:
                continue
            grouped.setdefault(canonical_by_sample[sample], []).append(row)
        result: list[dict[str, Any]] = []
        for canonical, records in sorted(grouped.items()):
            fingerprint_ids = {row["fingerprint_cluster"] for row in records}
            labels = {outcomes[identifier] for identifier in fingerprint_ids}
            assert len(labels) == 1
            result.append(
                {
                    "unit": canonical,
                    "records": "|".join(sorted(row["sample_id"] for row in records)),
                    "score": mean(predictions[row["sample_id"]] for row in records),
                    "label": next(iter(labels)),
                    "partition": "VALIDATION",
                    "setting": "|".join(sorted({row["site"] for row in records})),
                }
            )
        return result
    else:
        return []
    outcomes = {row["patient_key"]: int(row["week6_response"]) for row in _read_csv(outcome_path)}
    return [
        {
            "unit": row["patient_key"],
            "records": row["patient_key"],
            "score": float(row["predicted_probability"]),
            "label": outcomes[row["patient_key"]],
            "partition": "VALIDATION",
            "setting": row.get("site", ""),
        }
        for row in _read_csv(prediction_path)
    ]


def _canonical(rows: list[dict[str, Any]]) -> list[CanonicalRow]:
    return [
        CanonicalRow(
            entity_id=str(row["unit"]),
            source_record_ids=tuple(sorted(str(row["records"]).split("|"))),
            prediction=float(row["score"]),
            outcome=int(row["label"]),
            split=str(row["partition"]),
            contexts=tuple(sorted(filter(None, str(row["setting"]).split("|")))),
        )
        for row in rows
    ]


def _typed_calculations(
    table_id: str,
    rows: list[dict[str, Any]],
    *,
    structure: str,
    role: str,
    evidence_source: str,
    metrics: tuple[str, ...],
    output_id: str,
) -> list[dict[str, Any]]:
    canonical = _canonical(rows)
    estimator = "EMPIRICAL" if structure == "ENTITY_AGGREGATED" else "ENTITY_WEIGHTED"
    result: list[dict[str, Any]] = []
    for index, metric in enumerate(metrics):
        parameters: dict[str, Any] = {}
        if metric == "CALIBRATION_ERROR":
            parameters["bin_count"] = 7
        if metric == "NET_BENEFIT":
            parameters["threshold"] = 0.5
        calculation_id = f"{role}_{metric}_{index}"
        row: dict[str, Any] = {
            "calculation_id": calculation_id,
            "role": role,
            "source_analysis_table_id": table_id,
            "unit_of_analysis": (
                "BIOLOGICAL_ENTITY"
                if structure == "ENTITY_AGGREGATED"
                else "SOURCE_RECORD_CLUSTERED"
            ),
            "cohort": {
                "split_values": ["VALIDATION"],
                "entity_ids": [],
                "included_row_count": len(rows),
            },
            "outcome_column": "label",
            "prediction_column": "score",
            "context_columns": ["setting"],
            "metric": metric,
            "estimator": estimator,
            "parameters": parameters,
            "reported_value": calculate_metric(canonical, metric, estimator, parameters),
            "evidence_source": evidence_source,
            "output_artifact_id": output_id,
        }
        if metric == "ROC_AUC":
            low, high = cluster_bootstrap_interval(
                canonical,
                estimator,
                replicates=600,
                seed=41,
            )
            row["uncertainty"] = {
                "method": "CLUSTER_BOOTSTRAP_PERCENTILE",
                "level": 0.95,
                "replicates": 600,
                "seed": 41,
                "lower": low,
                "upper": high,
            }
        result.append(row)
    return result


def _row_diagnostic(table_id: str, rows: list[dict[str, Any]], output_id: str) -> dict[str, Any]:
    canonical = _canonical(rows)
    return {
        "calculation_id": "DIAGNOSTIC_ROW_AUC",
        "role": "DIAGNOSTIC",
        "source_analysis_table_id": table_id,
        "unit_of_analysis": "SOURCE_RECORD_CLUSTERED",
        "cohort": {
            "split_values": ["VALIDATION"],
            "entity_ids": [],
            "included_row_count": len(rows),
        },
        "outcome_column": "label",
        "prediction_column": "score",
        "context_columns": ["setting"],
        "metric": "ROC_AUC",
        "estimator": "ROW_EMPIRICAL",
        "parameters": {},
        "reported_value": calculate_metric(canonical, "ROC_AUC", "ROW_EMPIRICAL", {}),
        "evidence_source": "SUPPLIED_AND_REVEALED",
        "output_artifact_id": output_id,
    }


def _resource(condition_id: str, alternative: bool) -> tuple[str, str]:
    if condition_id == "case_01":
        return ("X31", "PIPELINE_REPLAY") if alternative else ("none", "NO_NEW_EVIDENCE")
    if condition_id == "case_02":
        return ("none", "NO_NEW_EVIDENCE") if alternative else ("X17", "RECORD_LINKAGE")
    if condition_id.startswith("case_03"):
        return "X31", "PIPELINE_REPLAY"
    return ("X46", "EXTERNAL_COHORT") if alternative else ("none", "NO_NEW_EVIDENCE")


def _decision(condition_id: str) -> tuple[str, str, str]:
    return {
        "case_01": ("EXTERNAL_VALIDATION", "CONTINUE", "RESEARCH_PROBABILITY"),
        "case_02": ("INTERNAL_VALIDATION", "PAUSE", "NO_USE"),
        "case_03_signal_collapses": ("STOPPED", "STOP", "RETROSPECTIVE_AUDIT"),
        "case_03_signal_remains": (
            "EXTERNAL_VALIDATION",
            "CONTINUE",
            "RESEARCH_PROBABILITY",
        ),
        "case_04": ("INTERNAL_VALIDATION", "PAUSE", "RESEARCH_RANKING"),
    }[condition_id]


def _direction(condition_id: str, resource_id: str) -> str:
    if resource_id == "none":
        return "UNCHANGED"
    if condition_id in {"case_01", "case_03_signal_remains"}:
        return "INCREASE"
    return "DECREASE"


def _plan(
    method: str,
    planned_output_paths: list[str] | None = None,
    *,
    condition_id: str = "case_01",
) -> dict[str, Any]:
    criteria = {
        "case_01": [
            ("G_AUC", "PRIMARY_ROC_AUC_0", "ROC_AUC", "AT_LEAST", 0.65),
            ("G_BRIER", "PRIMARY_BRIER_SCORE_1", "BRIER_SCORE", "AT_MOST", 0.25),
            ("G_UTILITY", "PRIMARY_NET_BENEFIT_3", "NET_BENEFIT", "AT_LEAST", 0.0),
        ],
        "case_02": [
            (
                "G_CONTEXT",
                "PRIMARY_SITE_WEIGHTED_ROC_AUC_4",
                "SITE_WEIGHTED_ROC_AUC",
                "AT_LEAST",
                0.65,
            )
        ],
        "case_03_signal_collapses": [
            ("G_REPLAY", "FOLLOWUP_ROC_AUC_0", "ROC_AUC", "AT_LEAST", 0.60)
        ],
        "case_03_signal_remains": [("G_REPLAY", "FOLLOWUP_ROC_AUC_0", "ROC_AUC", "AT_LEAST", 0.60)],
        "case_04": [("G_UTILITY", "PRIMARY_NET_BENEFIT_3", "NET_BENEFIT", "AT_LEAST", 0.0)],
    }[condition_id]
    return {
        "schema_version": SCHEMA_VERSION,
        "decision_definition": (
            "Whether the supplied evidence supports a bounded next development action."
        ),
        "evidence_standard": (
            "Auditable estimates and provenance must support the scope of the action."
        ),
        "hypotheses": [
            {
                "hypothesis_id": "H1",
                "statement": "The evidence is adequate for one bounded development step.",
                "belief": 0.5,
                "decision_effect_if_true": "SUPPORTS",
            },
            {
                "hypothesis_id": "H2",
                "statement": "A material evidence defect prevents that step.",
                "belief": 0.5,
                "decision_effect_if_true": "INVALIDATES",
            },
        ],
        "planned_analyses": [
            {
                "analysis_id": "A1",
                "question": "What decision-relevant result follows from the supplied records?",
                "method": f"{method} entity aggregation with source-linked calculations",
                "analysis_unit": "entities reconstructed from source relationships",
                "input_paths": [
                    "data/cohort_metadata.csv",
                    "data/locked_predictions.csv",
                    "pipeline/fit_membership.csv",
                ],
                "planned_output_paths": planned_output_paths
                or ["work/analysis_table.csv", "work/results.json"],
                "decision_relevance": "establish the evidence available for the bounded decision",
            }
        ],
        "decision_criteria": [
            {
                "criterion_id": criterion_id,
                "calculation_id": calculation_id,
                "metric": metric,
                "comparator": comparator,
                "threshold": threshold,
            }
            for criterion_id, calculation_id, metric, comparator, threshold in criteria
        ],
        "evidence_refs": ["intended_use.json", "data/cohort_metadata.csv"],
    }


def _decision_object(stage: str, disposition: str, use_scope: str) -> dict[str, Any]:
    return {
        "development_stage": stage,
        "disposition": disposition,
        "use_scope": use_scope,
        "allowed_use": ["bounded work consistent with the selected use scope"],
        "prohibited_use": ["uses exceeding the completed evidence"],
        "unresolved_gates": ["independent evidence appropriate to the next stage"],
        "required_next_evidence": ["evidence resolving the remaining gate"],
    }


def _followup(
    condition_id: str,
    resource_id: str,
    evidence_target: str,
    final_decision: tuple[str, str, str] | None = None,
) -> dict[str, Any]:
    direction = _direction(condition_id, resource_id)
    current = _decision_object("INTERNAL_VALIDATION", "PAUSE", "NO_USE")
    if condition_id == "case_01" and resource_id == "none":
        current = _decision_object("EXTERNAL_VALIDATION", "CONTINUE", "RESEARCH_PROBABILITY")
    stage, disposition, use_scope = final_decision or _decision(condition_id)
    observed_decision = _decision_object(stage, disposition, use_scope)
    opposite_decision = (
        _decision_object("STOPPED", "STOP", "NO_USE")
        if disposition == "CONTINUE"
        else _decision_object("EXTERNAL_VALIDATION", "CONTINUE", "RESEARCH_PROBABILITY")
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "decision_question_id": "Q1",
        "decision_question": (
            "Which remaining uncertainty, if any, changes the immediate development action?"
        ),
        "chosen_resource": resource_id,
        "evidence_target": evidence_target,
        "live_explanations": [
            {
                "explanation_id": "E1",
                "statement": "The current evidence reflects a stable bounded result.",
                "distinguishing_evidence": "a result consistent with the locked evidence chain",
            },
            {
                "explanation_id": "E2",
                "statement": "A material evidence defect explains the apparent result.",
                "distinguishing_evidence": "a result inconsistent with the locked evidence chain",
            },
        ],
        "alternatives_considered": [
            {"resource_id": resource_id, "limitations": "addresses only its stated return"},
            {"resource_id": "X63", "limitations": "does not create missing empirical evidence"},
        ],
        "result_contingencies": [
            {
                "contingency_id": "C_OBSERVED",
                "observable_result": (
                    "the returned evidence matches the result subsequently calculated"
                ),
                "hypothesis_updates": [
                    {"hypothesis_id": "H1", "direction": direction},
                    {
                        "hypothesis_id": "H2",
                        "direction": (
                            "DECREASE"
                            if direction == "INCREASE"
                            else ("INCREASE" if direction == "DECREASE" else "UNCHANGED")
                        ),
                    },
                ],
                "next_decision": observed_decision,
                "next_action": "apply the bounded action supported by the returned evidence",
            },
            {
                "contingency_id": "C_OPPOSITE",
                "observable_result": "the returned evidence supports the competing explanation",
                "hypothesis_updates": [
                    {
                        "hypothesis_id": "H1",
                        "direction": "DECREASE" if direction != "DECREASE" else "INCREASE",
                    },
                    {
                        "hypothesis_id": "H2",
                        "direction": "INCREASE" if direction != "DECREASE" else "DECREASE",
                    },
                ],
                "next_decision": opposite_decision,
                "next_action": "revise the development action",
            },
        ],
        "beliefs_before": {"H1": 0.5, "H2": 0.5},
        "current_decision": current,
        "evidence_refs": ["followup_catalog.json", "work/results.json"],
    }


def _claim_rows(condition_id: str) -> list[dict[str, Any]]:
    supported_scope = {
        "case_01": "PROGNOSTIC_PROBABILITY",
        "case_02": None,
        "case_03_signal_collapses": None,
        "case_03_signal_remains": "PROGNOSTIC_PROBABILITY",
        "case_04": "PROGNOSTIC_RANKING",
    }[condition_id]
    rows: list[dict[str, Any]] = []
    if supported_scope:
        supporting_calculations = {
            "case_01": [
                "PRIMARY_ROC_AUC_0",
                "PRIMARY_BRIER_SCORE_1",
                "PRIMARY_CALIBRATION_ERROR_2",
            ],
            "case_03_signal_remains": [
                "FOLLOWUP_ROC_AUC_0",
                "FOLLOWUP_BRIER_SCORE_1",
                "FOLLOWUP_CALIBRATION_ERROR_2",
            ],
            "case_04": ["PRIMARY_ROC_AUC_0"],
        }[condition_id]
        rows.append(
            {
                "claim_id": "CLAIM_SUPPORTED",
                "statement": "A bounded claim is supported by the saved evidence.",
                "status": "SUPPORTED",
                "scope": supported_scope,
                "evidence_refs": ["work/results.json"],
                "calculation_ids": supporting_calculations,
            }
        )
    for index, scope in enumerate(
        (
            "INDEPENDENT_VALIDATION",
            "CLINICAL_UTILITY",
            "TREATMENT_EFFECT",
            "CROSS_CONTEXT_TRANSPORT",
        )
    ):
        rows.append(
            {
                "claim_id": f"CLAIM_LIMIT_{index}",
                "statement": "This broader scope is not established by the completed evidence.",
                "status": "NOT_SUPPORTED",
                "scope": scope,
                "evidence_refs": ["intended_use.json"],
                "calculation_ids": [],
            }
        )
    if condition_id in {"case_03_signal_collapses", "case_04"}:
        rows.append(
            {
                "claim_id": "CLAIM_PROBABILITY_LIMIT",
                "statement": "Probability use is not supported.",
                "status": "NOT_SUPPORTED",
                "scope": "PROGNOSTIC_PROBABILITY",
                "evidence_refs": ["work/results.json"],
                "calculation_ids": ["PRIMARY_BRIER_SCORE_1"],
            }
        )
    return rows


def build_open_reference(
    project_root: Path,
    condition_id: str,
    run_root: Path,
    *,
    alternative: bool,
    recover_from_schema_error: bool = False,
    forced_resource: tuple[str, str] | None = None,
    planned_output_paths: list[str] | None = None,
    final_decision: tuple[str, str, str] | None = None,
    criterion_thresholds: dict[str, float] | None = None,
) -> tuple[dict[str, Any], Path]:
    case_id, mechanism = _case(condition_id)
    environment = OpenMMMVPEnvironment(project_root, case_id, run_root, mechanism=mechanism)
    method = "clustered" if alternative else "mean"
    plan = _plan(method, planned_output_paths, condition_id=condition_id)
    for criterion in plan["decision_criteria"]:
        if criterion_thresholds and criterion["calculation_id"] in criterion_thresholds:
            criterion["threshold"] = criterion_thresholds[criterion["calculation_id"]]
    if recover_from_schema_error:
        rejected = copy.deepcopy(plan)
        rejected["hypotheses"] = []
        assert not environment.commit_validation_plan(json.dumps(rejected))["accepted"]
    assert environment.commit_validation_plan(json.dumps(plan))["accepted"]
    environment.reveal_validation()
    primary = _primary_rows(run_root, method)
    _write_csv(run_root / "work/analysis_table.csv", primary)
    (run_root / "work/analysis.py").write_text(
        (
            "# Diagnostic provenance only. Scientific credit comes from independent\n"
            "# recomputation of typed calculations from source-linked analysis tables.\n"
        ),
        encoding="utf-8",
    )
    resource_id, target = forced_resource or _resource(condition_id, alternative)
    followup = _followup(condition_id, resource_id, target, final_decision)
    assert environment.commit_followup_plan(json.dumps(followup))["accepted"]
    environment.purchase_resource(resource_id)
    followup_rows = _followup_rows(run_root, resource_id)
    followup_summary_path: str | None = None
    if followup_rows:
        _write_csv(run_root / "work/followup_table.csv", followup_rows)
    row_rows = _primary_rows(run_root, "clustered")
    if method != "clustered":
        _write_csv(run_root / "work/source_record_table.csv", row_rows)
    artifact_manifest: list[dict[str, Any]] = [
        {
            "artifact_id": "TABLE_PRIMARY",
            "path": "work/analysis_table.csv",
            "role": "ANALYSIS_TABLE",
            "source_paths": [
                "data/cohort_metadata.csv",
                "data/locked_predictions.csv",
                "revealed/validation_outcomes.csv",
            ],
            "column_map": {
                "entity_id": "unit",
                "source_record_ids": "records",
                "prediction": "score",
                "outcome": "label",
                "split": "partition",
                "context": "setting",
            },
            "analysis_structure": (
                "SOURCE_RECORD_CLUSTERED" if method == "clustered" else "ENTITY_AGGREGATED"
            ),
            "aggregation": "NONE" if method == "clustered" else "MEAN",
        },
        {
            "artifact_id": "CODE_PRIMARY",
            "path": "work/analysis.py",
            "role": "CODE",
            "source_paths": [],
        },
        {
            "artifact_id": "OUTPUT_PRIMARY",
            "path": "work/results.json",
            "role": "CALCULATION_OUTPUT",
            "source_paths": ["work/analysis_table.csv", "work/analysis.py"],
        },
    ]
    if method != "clustered":
        artifact_manifest.append(
            {
                "artifact_id": "TABLE_SOURCE_RECORDS",
                "path": "work/source_record_table.csv",
                "role": "ANALYSIS_TABLE",
                "source_paths": [
                    "data/cohort_metadata.csv",
                    "data/locked_predictions.csv",
                    "revealed/validation_outcomes.csv",
                ],
                "column_map": {
                    "entity_id": "unit",
                    "source_record_ids": "records",
                    "prediction": "score",
                    "outcome": "label",
                    "split": "partition",
                    "context": "setting",
                },
                "analysis_structure": "SOURCE_RECORD_CLUSTERED",
                "aggregation": "NONE",
            }
        )
    if followup_rows:
        purchased_sources = {
            "X31": [
                "purchased/X31/replay_predictions.csv",
                "revealed/validation_outcomes.csv",
            ],
            "X46": [
                "purchased/X46/matched_predictions.csv",
                "purchased/X46/matched_outcomes.csv",
            ],
            "X17": [
                "purchased/X17/canonical_person_crosswalk.csv",
                "revealed/validation_outcomes.csv",
                "data/cohort_metadata.csv",
                "data/locked_predictions.csv",
            ],
        }[resource_id]
        artifact_manifest.append(
            {
                "artifact_id": "TABLE_FOLLOWUP",
                "path": "work/followup_table.csv",
                "role": "ANALYSIS_TABLE",
                "source_paths": purchased_sources,
                "column_map": {
                    "entity_id": "unit",
                    "source_record_ids": "records",
                    "prediction": "score",
                    "outcome": "label",
                    "split": "partition",
                    "context": "setting",
                },
                "analysis_structure": "ENTITY_AGGREGATED",
                "aggregation": "MEAN" if resource_id == "X17" else "NONE",
            }
        )
    elif resource_id != "none":
        purchased_file = next(
            path
            for path in sorted((run_root / "purchased" / resource_id).rglob("*"))
            if path.is_file()
        )
        relative = purchased_file.relative_to(run_root).as_posix()
        followup_summary_path = "work/followup_evidence.json"
        (run_root / followup_summary_path).write_text(
            json.dumps(
                {
                    "source_path": relative,
                    "source_sha256": hashlib.sha256(purchased_file.read_bytes()).hexdigest(),
                    "source_bytes": purchased_file.stat().st_size,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        artifact_manifest.append(
            {
                "artifact_id": "FOLLOWUP_PROVENANCE",
                "path": followup_summary_path,
                "role": "PROVENANCE",
                "source_paths": [relative],
            }
        )
    primary_metrics = (
        "ROC_AUC",
        "BRIER_SCORE",
        "CALIBRATION_ERROR",
        "NET_BENEFIT",
        "SITE_WEIGHTED_ROC_AUC",
        "WORST_SITE_ROC_AUC",
        "ENTITY_COUNT",
    )
    calculations = _typed_calculations(
        "TABLE_PRIMARY",
        primary,
        structure=("SOURCE_RECORD_CLUSTERED" if method == "clustered" else "ENTITY_AGGREGATED"),
        role="PRIMARY",
        evidence_source="SUPPLIED_AND_REVEALED",
        metrics=primary_metrics,
        output_id="OUTPUT_PRIMARY",
    )
    calculations.append(
        _row_diagnostic(
            "TABLE_PRIMARY" if method == "clustered" else "TABLE_SOURCE_RECORDS",
            row_rows,
            "OUTPUT_PRIMARY",
        )
    )
    if followup_rows:
        followup_metrics = (
            ("ROC_AUC", "ENTITY_COUNT")
            if resource_id == "X17"
            else (
                "ROC_AUC",
                "BRIER_SCORE",
                "CALIBRATION_ERROR",
                "NET_BENEFIT",
                "ENTITY_COUNT",
            )
        )
        calculations.extend(
            _typed_calculations(
                "TABLE_FOLLOWUP",
                followup_rows,
                structure="ENTITY_AGGREGATED",
                role="FOLLOWUP",
                evidence_source="PURCHASED",
                metrics=followup_metrics,
                output_id="OUTPUT_PRIMARY",
            )
        )
    (run_root / "work/results.json").write_text(
        json.dumps(
            {
                "typed_calculations": [
                    {
                        "calculation_id": row["calculation_id"],
                        "reported_value": row["reported_value"],
                    }
                    for row in calculations
                ]
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    direction = _direction(condition_id, resource_id)
    after_h1 = {"INCREASE": 0.7, "DECREASE": 0.3, "UNCHANGED": 0.5}[direction]
    after_h2 = {"INCREASE": 0.3, "DECREASE": 0.7, "UNCHANGED": 0.5}[direction]
    stage, disposition, use_scope = final_decision or _decision(condition_id)
    claims = _claim_rows(condition_id)
    available_calculation_ids = {row["calculation_id"] for row in calculations}
    for claim in claims:
        if not set(claim["calculation_ids"]) <= available_calculation_ids:
            claim["status"] = "UNRESOLVED"
            claim["calculation_ids"] = []
    final = {
        "schema_version": SCHEMA_VERSION,
        "artifact_manifest": artifact_manifest,
        "calculations": calculations,
        "findings": [
            {
                "finding_id": "F1",
                "statement": "The preserved evidence supports the bounded action stated below.",
                "status": "SUPPORTED",
                "decision_effect": "SUPPORTS" if disposition == "CONTINUE" else "WEAKENS",
                "evidence_refs": ["work/analysis_table.csv", "work/results.json"],
                "calculation_ids": [calculations[0]["calculation_id"]],
            }
        ],
        "evidence_assessments": [
            {
                "evidence_id": "EV1",
                "source_paths": ["pipeline/fit_membership.csv", "logs/execution_log.csv"],
                "eligible_for_decision": not condition_id.startswith("case_03"),
                "rationale": "Eligibility follows from the preserved execution evidence.",
            }
        ],
        "belief_updates": [
            {
                "hypothesis_id": "H1",
                "before": 0.5,
                "after": after_h1,
                "evidence_refs": ["work/results.json"],
                "matched_contingency_id": "C_OBSERVED",
            },
            {
                "hypothesis_id": "H2",
                "before": 0.5,
                "after": after_h2,
                "evidence_refs": ["work/results.json"],
                "matched_contingency_id": "C_OBSERVED",
            },
        ],
        "decision": _decision_object(stage, disposition, use_scope),
        "claims": claims,
        "remaining_uncertainties": ["evidence required for any broader use"],
        "evidence_refs": [
            "intended_use.json",
            "work/analysis_table.csv",
            "work/results.json",
            *([followup_summary_path] if followup_summary_path else []),
            *(
                [
                    next(
                        path.relative_to(run_root).as_posix()
                        for path in sorted((run_root / "purchased" / resource_id).rglob("*"))
                        if path.is_file()
                    )
                ]
                if resource_id != "none"
                else ["purchased/none/no_new_evidence.json"]
            ),
        ],
    }
    submission_result = environment.submit(json.dumps(final))
    assert submission_result["accepted"], submission_result
    return environment.export_submission(), run_root


def _grade_row(condition_id: str, control: str, grade: OpenGrade) -> dict[str, Any]:
    return {
        "condition_id": condition_id,
        "control": control,
        "complete_mission_success": grade.complete_mission_success,
        "partial_scientific_quality": grade.partial_scientific_quality,
        "mission_failures": list(grade.mission_failures),
        "first_decision_critical_failure": grade.first_decision_critical_failure,
        "failure_class": grade.failure_class,
    }


def _replace_final_submission(
    submission: dict[str, Any],
    workspace: Path,
    final: dict[str, Any],
) -> None:
    digest = hashlib.sha256(
        json.dumps(final, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    submission["final_submission"] = final
    submission["state"]["final_submission_hash"] = digest
    submit_event = next(row for row in submission["event_log"] if row["event"] == "submit")
    submit_event["final_submission_hash"] = digest
    records = workspace.parent / ".mmmvp_host_records" / workspace.name
    records.mkdir(parents=True, exist_ok=True)
    submission["host_record_locator"] = records.resolve().as_posix()
    (records / "final_submission.json").write_text(
        json.dumps(final, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _copy_workspace(source: Path, target: Path) -> None:
    shutil.copytree(source, target)
    source_records = source.parent / ".mmmvp_host_records" / source.name
    target_records = target.parent / ".mmmvp_host_records" / target.name
    target_records.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_records, target_records)


def _relocate_submission(submission: dict[str, Any], workspace: Path) -> dict[str, Any]:
    relocated = copy.deepcopy(submission)
    relocated["host_record_locator"] = (
        (workspace.parent / ".mmmvp_host_records" / workspace.name).resolve().as_posix()
    )
    return relocated


def _sync_calculation_output(workspace: Path, final: dict[str, Any]) -> None:
    output = workspace / "work/results.json"
    output.write_text(
        json.dumps(
            {
                "typed_calculations": [
                    {
                        "calculation_id": row["calculation_id"],
                        "reported_value": row["reported_value"],
                    }
                    for row in final["calculations"]
                ]
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def run_open_controls(project_root: Path, temporary_root: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    references: dict[str, tuple[dict[str, Any], Path]] = {}
    alternatives: dict[str, tuple[dict[str, Any], Path]] = {}
    for index, condition_id in enumerate(CONDITIONS):
        reference = build_open_reference(
            project_root,
            condition_id,
            temporary_root / f"{index}-reference",
            alternative=False,
            recover_from_schema_error=condition_id == "case_01",
        )
        alternative = build_open_reference(
            project_root,
            condition_id,
            temporary_root / f"{index}-alternative",
            alternative=True,
        )
        references[condition_id] = reference
        alternatives[condition_id] = alternative
        for name, (submission, workspace) in (
            ("correct_reference", reference),
            ("different_valid_workflow", alternative),
        ):
            rows.append(
                _grade_row(
                    condition_id,
                    name,
                    verify_open_submission(
                        project_root,
                        workspace,
                        submission,
                        condition_id=condition_id,
                    ),
                )
            )

    reference, reference_workspace = references["case_01"]
    workspace = temporary_root / "case1-no-analysis"
    _copy_workspace(reference_workspace, workspace)
    no_analysis = _relocate_submission(reference, workspace)
    no_analysis_final = copy.deepcopy(no_analysis["final_submission"])
    no_analysis_final["calculations"] = []
    for finding in no_analysis_final["findings"]:
        finding["calculation_ids"] = []
    for claim in no_analysis_final["claims"]:
        claim["calculation_ids"] = []
    _replace_final_submission(no_analysis, workspace, no_analysis_final)
    rows.append(
        _grade_row(
            "case_01",
            "correct_action_without_analysis",
            verify_open_submission(project_root, workspace, no_analysis, condition_id="case_01"),
        )
    )

    universal_action_results: dict[str, list[bool]] = {
        "always_advance": [],
        "always_abstain": [],
        "always_stop": [],
    }
    universal_decisions = {
        "always_advance": _decision_object(
            "EXTERNAL_VALIDATION", "CONTINUE", "RESEARCH_PROBABILITY"
        ),
        "always_abstain": _decision_object(
            "INTERNAL_VALIDATION", "INSUFFICIENT_EVIDENCE", "NO_USE"
        ),
        "always_stop": _decision_object("STOPPED", "STOP", "NO_USE"),
    }
    for index, (condition_id, (submission, source_workspace)) in enumerate(references.items()):
        for policy_name, decision in universal_decisions.items():
            workspace = temporary_root / f"universal-action-{index}-{policy_name}"
            _copy_workspace(source_workspace, workspace)
            generic = _relocate_submission(submission, workspace)
            generic_final = copy.deepcopy(generic["final_submission"])
            generic_final["decision"] = decision
            _replace_final_submission(generic, workspace, generic_final)
            grade = verify_open_submission(
                project_root,
                workspace,
                generic,
                condition_id=condition_id,
            )
            universal_action_results[policy_name].append(grade.complete_mission_success)
            rows.append(_grade_row(condition_id, policy_name, grade))

    generic_plan = build_open_reference(
        project_root,
        "case_01",
        temporary_root / "generic-checklist",
        alternative=False,
        planned_output_paths=["work/generic_checklist.txt"],
    )
    rows.append(
        _grade_row(
            "case_01",
            "generic_checklist_not_implemented",
            verify_open_submission(
                project_root,
                generic_plan[1],
                generic_plan[0],
                condition_id="case_01",
            ),
        )
    )

    always_buy_results: list[bool] = []
    always_none_results: list[bool] = []
    for index, condition_id in enumerate(CONDITIONS):
        for policy_name, forced_resource in (
            ("always_buy_expert_review", ("X63", "EXPERT_REVIEW")),
            ("always_purchase_nothing", ("none", "NO_NEW_EVIDENCE")),
        ):
            fixture = build_open_reference(
                project_root,
                condition_id,
                temporary_root / f"universal-{index}-{policy_name}",
                alternative=False,
                forced_resource=forced_resource,
            )
            grade = verify_open_submission(
                project_root,
                fixture[1],
                fixture[0],
                condition_id=condition_id,
            )
            if policy_name == "always_buy_expert_review":
                always_buy_results.append(grade.complete_mission_success)
            else:
                always_none_results.append(grade.complete_mission_success)
            rows.append(_grade_row(condition_id, policy_name, grade))

    case4_wrong_resource = build_open_reference(
        project_root,
        "case_04",
        temporary_root / "case4-unnecessary",
        alternative=False,
        forced_resource=("X31", "PIPELINE_REPLAY"),
    )
    rows.append(
        _grade_row(
            "case_04",
            "unnecessary_purchase",
            verify_open_submission(
                project_root,
                case4_wrong_resource[1],
                case4_wrong_resource[0],
                condition_id="case_04",
            ),
        )
    )

    workspace = temporary_root / "case1-unnecessary-abstention"
    _copy_workspace(reference_workspace, workspace)
    abstain = _relocate_submission(reference, workspace)
    abstain_final = copy.deepcopy(abstain["final_submission"])
    abstain_final["decision"] = _decision_object(
        "INTERNAL_VALIDATION", "INSUFFICIENT_EVIDENCE", "NO_USE"
    )
    _replace_final_submission(abstain, workspace, abstain_final)
    rows.append(
        _grade_row(
            "case_01",
            "unnecessary_abstention",
            verify_open_submission(project_root, workspace, abstain, condition_id="case_01"),
        )
    )

    case2, case2_source_workspace = references["case_02"]
    case2_workspace = temporary_root / "case2-unsupported-confident-action"
    _copy_workspace(case2_source_workspace, case2_workspace)
    confident = _relocate_submission(case2, case2_workspace)
    confident_final = copy.deepcopy(confident["final_submission"])
    confident_final["decision"] = _decision_object(
        "EXTERNAL_VALIDATION", "CONTINUE", "RESEARCH_PROBABILITY"
    )
    _replace_final_submission(confident, case2_workspace, confident_final)
    rows.append(
        _grade_row(
            "case_02",
            "unsupported_confident_action",
            verify_open_submission(
                project_root, case2_workspace, confident, condition_id="case_02"
            ),
        )
    )

    altered_workspace = temporary_root / "case2-altered"
    _copy_workspace(case2_source_workspace, altered_workspace)
    altered = _relocate_submission(case2, altered_workspace)
    outcome_path = altered_workspace / "revealed/validation_outcomes.csv"
    outcomes = _read_csv(outcome_path)
    for row in outcomes[:20]:
        row["week6_response"] = str(1 - int(row["week6_response"]))
    _write_csv(outcome_path, outcomes)
    rows.append(
        _grade_row(
            "case_02",
            "hard_coded_values_on_altered_input",
            verify_open_submission(
                project_root, altered_workspace, altered, condition_id="case_02"
            ),
        )
    )

    collapse, _ = references["case_03_signal_collapses"]
    remains, remains_source_workspace = references["case_03_signal_remains"]
    remains_workspace = temporary_root / "case3-remains-copied-conclusion"
    _copy_workspace(remains_source_workspace, remains_workspace)
    copied = _relocate_submission(remains, remains_workspace)
    _replace_final_submission(
        copied,
        remains_workspace,
        copy.deepcopy(collapse["final_submission"]),
    )
    rows.append(
        _grade_row(
            "case_03_signal_remains",
            "copied_paired_variant_conclusion",
            verify_open_submission(
                project_root,
                remains_workspace,
                copied,
                condition_id="case_03_signal_remains",
            ),
        )
    )

    table_path = case2_workspace / "work/analysis_table.csv"
    bad_workspace = temporary_root / "case2-partial"
    _copy_workspace(case2_source_workspace, bad_workspace)
    partial = _relocate_submission(case2, bad_workspace)
    bad_table = _read_csv(bad_workspace / table_path.relative_to(case2_workspace))
    bad_table[0]["score"] = "0.999"
    _write_csv(bad_workspace / table_path.relative_to(case2_workspace), bad_table)
    partial_grade = verify_open_submission(
        project_root, bad_workspace, partial, condition_id="case_02"
    )
    rows.append(_grade_row("case_02", "recoverable_partial_credit", partial_grade))

    justified_abstention, case2_no_purchase_workspace = build_open_reference(
        project_root,
        "case_02",
        temporary_root / "case2-justified-abstention",
        alternative=False,
        forced_resource=("none", "NO_NEW_EVIDENCE"),
        final_decision=("INTERNAL_VALIDATION", "INSUFFICIENT_EVIDENCE", "NO_USE"),
    )
    justified_grade = verify_open_submission(
        project_root,
        case2_no_purchase_workspace,
        justified_abstention,
        condition_id="case_02",
    )
    rows.append(_grade_row("case_02", "justified_abstention", justified_grade))

    case2_x46 = build_open_reference(
        project_root,
        "case_02",
        temporary_root / "case2-transport-question",
        alternative=False,
        forced_resource=("X46", "EXTERNAL_COHORT"),
    )
    case2_x46_grade = verify_open_submission(
        project_root,
        case2_x46[1],
        case2_x46[0],
        condition_id="case_02",
    )
    rows.append(_grade_row("case_02", "accepted_transport_question", case2_x46_grade))

    dense_workspace = temporary_root / "case1-dense-unlabelled-numbers"
    _copy_workspace(reference_workspace, dense_workspace)
    dense = _relocate_submission(reference, dense_workspace)
    dense_final = copy.deepcopy(dense["final_submission"])
    dense_final["calculations"] = []
    for item in [*dense_final["findings"], *dense_final["claims"]]:
        item["calculation_ids"] = []
        if item in dense_final["claims"] and item["status"] == "SUPPORTED":
            item["status"] = "UNRESOLVED"
    (dense_workspace / "work/results.json").write_text(
        json.dumps({"numbers": list(range(1000)), "auc_like": 0.731, "brier_like": 0.19}),
        encoding="utf-8",
    )
    _replace_final_submission(dense, dense_workspace, dense_final)
    rows.append(
        _grade_row(
            "case_01",
            "dense_unlabelled_numbers",
            verify_open_submission(project_root, dense_workspace, dense, condition_id="case_01"),
        )
    )

    wrong_table_workspace = temporary_root / "case2-correct-number-wrong-table"
    _copy_workspace(case2_source_workspace, wrong_table_workspace)
    wrong_table = _relocate_submission(case2, wrong_table_workspace)
    wrong_table_final = copy.deepcopy(wrong_table["final_submission"])
    auc = next(
        item
        for item in wrong_table_final["calculations"]
        if item["calculation_id"] == "PRIMARY_ROC_AUC_0"
    )
    auc["source_analysis_table_id"] = "TABLE_SOURCE_RECORDS"
    auc["unit_of_analysis"] = "SOURCE_RECORD_CLUSTERED"
    auc["estimator"] = "ENTITY_WEIGHTED"
    _replace_final_submission(wrong_table, wrong_table_workspace, wrong_table_final)
    rows.append(
        _grade_row(
            "case_02",
            "correct_number_wrong_source_table",
            verify_open_submission(
                project_root,
                wrong_table_workspace,
                wrong_table,
                condition_id="case_02",
            ),
        )
    )

    clustered_submission, clustered_source = alternatives["case_02"]
    independent_workspace = temporary_root / "case2-row-independent"
    _copy_workspace(clustered_source, independent_workspace)
    independent = _relocate_submission(clustered_submission, independent_workspace)
    independent_final = copy.deepcopy(independent["final_submission"])
    for item in independent_final["calculations"]:
        if item["role"] == "PRIMARY":
            item["estimator"] = "ROW_EMPIRICAL"
    _replace_final_submission(independent, independent_workspace, independent_final)
    rows.append(
        _grade_row(
            "case_02",
            "row_independent_analysis",
            verify_open_submission(
                project_root,
                independent_workspace,
                independent,
                condition_id="case_02",
            ),
        )
    )

    label_only_workspace = temporary_root / "case2-method-label-without-grouping"
    _copy_workspace(clustered_source, label_only_workspace)
    label_only = _relocate_submission(clustered_submission, label_only_workspace)
    label_table_path = label_only_workspace / "work/analysis_table.csv"
    label_rows = _read_csv(label_table_path)
    for item in label_rows:
        item["unit"] = item["records"]
    _write_csv(label_table_path, label_rows)
    rows.append(
        _grade_row(
            "case_02",
            "method_label_without_grouping",
            verify_open_submission(
                project_root,
                label_only_workspace,
                label_only,
                condition_id="case_02",
            ),
        )
    )

    rounded_workspace = temporary_root / "case1-harmless-rounding"
    _copy_workspace(reference_workspace, rounded_workspace)
    rounded = _relocate_submission(reference, rounded_workspace)
    rounded_final = copy.deepcopy(rounded["final_submission"])
    rounded_calc = next(
        item
        for item in rounded_final["calculations"]
        if item["calculation_id"] == "PRIMARY_BRIER_SCORE_1"
    )
    rounded_calc["reported_value"] = round(float(rounded_calc["reported_value"]), 3)
    _sync_calculation_output(rounded_workspace, rounded_final)
    _replace_final_submission(rounded, rounded_workspace, rounded_final)
    rounded_grade = verify_open_submission(
        project_root, rounded_workspace, rounded, condition_id="case_01"
    )
    rows.append(_grade_row("case_01", "harmless_rounding", rounded_grade))

    optional_workspace = temporary_root / "case4-incorrect-optional"
    case4, case4_source = references["case_04"]
    _copy_workspace(case4_source, optional_workspace)
    optional = _relocate_submission(case4, optional_workspace)
    optional_final = copy.deepcopy(optional["final_submission"])
    optional_calc = copy.deepcopy(optional_final["calculations"][0])
    optional_calc.update(
        {
            "calculation_id": "OPTIONAL_INCORRECT_AUC",
            "role": "SENSITIVITY",
            "reported_value": -999.0,
        }
    )
    optional_calc.pop("uncertainty", None)
    optional_final["calculations"].append(optional_calc)
    _sync_calculation_output(optional_workspace, optional_final)
    _replace_final_submission(optional, optional_workspace, optional_final)
    optional_grade = verify_open_submission(
        project_root, optional_workspace, optional, condition_id="case_04"
    )
    rows.append(_grade_row("case_04", "incorrect_optional_calculation", optional_grade))

    renamed_workspace = temporary_root / "case1-renamed-columns"
    _copy_workspace(reference_workspace, renamed_workspace)
    renamed = _relocate_submission(reference, renamed_workspace)
    renamed_final = copy.deepcopy(renamed["final_submission"])
    column_names = {
        "unit": "participant",
        "records": "source_keys",
        "score": "probability",
        "label": "event",
        "partition": "split_set",
        "setting": "centre",
    }
    for table_name in ("analysis_table.csv", "source_record_table.csv"):
        path = renamed_workspace / "work" / table_name
        table_rows = _read_csv(path)
        renamed_rows = [
            {column_names[key]: value for key, value in row.items()} for row in table_rows
        ]
        _write_csv(path, renamed_rows)
    for artifact in renamed_final["artifact_manifest"]:
        if artifact["role"] == "ANALYSIS_TABLE":
            artifact["column_map"] = {
                semantic: column_names[column]
                for semantic, column in artifact["column_map"].items()
            }
    for calculation in renamed_final["calculations"]:
        calculation["outcome_column"] = "event"
        calculation["prediction_column"] = "probability"
        calculation["context_columns"] = ["centre"]
    _replace_final_submission(renamed, renamed_workspace, renamed_final)
    renamed_grade = verify_open_submission(
        project_root, renamed_workspace, renamed, condition_id="case_01"
    )
    rows.append(_grade_row("case_01", "semantic_column_remapping", renamed_grade))

    conditional, conditional_workspace = build_open_reference(
        project_root,
        "case_01",
        temporary_root / "case1-conditional-continuation",
        alternative=False,
        final_decision=("INTERNAL_VALIDATION", "CONTINUE", "RESEARCH_PROBABILITY"),
    )
    conditional_grade = verify_open_submission(
        project_root, conditional_workspace, conditional, condition_id="case_01"
    )
    rows.append(_grade_row("case_01", "conditional_continuation", conditional_grade))

    cautious, cautious_workspace = build_open_reference(
        project_root,
        "case_01",
        temporary_root / "case1-justified-pause",
        alternative=False,
        final_decision=("INTERNAL_VALIDATION", "PAUSE", "NO_USE"),
        criterion_thresholds={"PRIMARY_ROC_AUC_0": 0.80},
    )
    cautious_grade = verify_open_submission(
        project_root, cautious_workspace, cautious, condition_id="case_01"
    )
    rows.append(_grade_row("case_01", "justified_pause", cautious_grade))

    stopped = build_open_reference(
        project_root,
        "case_01",
        temporary_root / "case1-unsupported-stop",
        alternative=False,
        final_decision=("STOPPED", "STOP", "NO_USE"),
    )
    rows.append(
        _grade_row(
            "case_01",
            "unsupported_pessimistic_stop",
            verify_open_submission(project_root, stopped[1], stopped[0], condition_id="case_01"),
        )
    )

    clinical = build_open_reference(
        project_root,
        "case_01",
        temporary_root / "case1-clinical-advance",
        alternative=False,
        final_decision=("PROSPECTIVE_EVALUATION", "CONTINUE", "CLINICAL_DECISION_SUPPORT"),
    )
    rows.append(
        _grade_row(
            "case_01",
            "unsupported_clinical_advancement",
            verify_open_submission(project_root, clinical[1], clinical[0], condition_id="case_01"),
        )
    )

    moved_workspace = temporary_root / "case1-posthoc-criterion"
    _copy_workspace(reference_workspace, moved_workspace)
    moved = _relocate_submission(reference, moved_workspace)
    moved["validation_plan"]["decision_criteria"][0]["threshold"] = 0.99
    rows.append(
        _grade_row(
            "case_01",
            "posthoc_decision_standard_movement",
            verify_open_submission(project_root, moved_workspace, moved, condition_id="case_01"),
        )
    )

    evidence_workspace = temporary_root / "case1-protected-evidence-mutation"
    _copy_workspace(reference_workspace, evidence_workspace)
    evidence_attack = _relocate_submission(reference, evidence_workspace)
    evidence_path = evidence_workspace / "revealed/validation_outcomes.csv"
    evidence_path.write_text(evidence_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    rows.append(
        _grade_row(
            "case_01",
            "protected_evidence_mutation",
            verify_open_submission(
                project_root,
                evidence_workspace,
                evidence_attack,
                condition_id="case_01",
            ),
        )
    )

    reference_pass = all(
        row["complete_mission_success"]
        for row in rows
        if row["control"] in {"correct_reference", "different_valid_workflow"}
    )
    negative_controls = [
        row
        for row in rows
        if row["control"]
        not in {
            "correct_reference",
            "different_valid_workflow",
            "recoverable_partial_credit",
            "always_advance",
            "always_abstain",
            "always_stop",
            "always_buy_expert_review",
            "always_purchase_nothing",
            "justified_abstention",
            "accepted_transport_question",
            "harmless_rounding",
            "incorrect_optional_calculation",
            "conditional_continuation",
            "justified_pause",
            "semantic_column_remapping",
        }
    ]
    partial_ok = (
        not partial_grade.complete_mission_success
        and 0 < partial_grade.partial_scientific_quality < 100
    )
    mission_consistent = all(
        not row["complete_mission_success"] or row["first_decision_critical_failure"] is None
        for row in rows
    )
    return {
        "schema_version": "uc-bench-open-controls-1",
        "api_requests": 0,
        "status": (
            "passed"
            if reference_pass
            and all(not row["complete_mission_success"] for row in negative_controls)
            and all(not all(results) for results in universal_action_results.values())
            and not verify_open_submission(
                project_root,
                generic_plan[1],
                generic_plan[0],
                condition_id="case_01",
            ).complete_mission_success
            and not all(always_buy_results)
            and not all(always_none_results)
            and justified_grade.complete_mission_success
            and case2_x46_grade.complete_mission_success
            and rounded_grade.complete_mission_success
            and optional_grade.complete_mission_success
            and conditional_grade.complete_mission_success
            and cautious_grade.complete_mission_success
            and renamed_grade.complete_mission_success
            and partial_ok
            and mission_consistent
            else "failed"
        ),
        "reference_and_two_workflows_pass": reference_pass,
        "negative_controls_rejected": all(
            not row["complete_mission_success"] for row in negative_controls
        ),
        "universal_policy_fails": all(
            not all(results) for results in universal_action_results.values()
        ),
        "generic_checklist_fails": not verify_open_submission(
            project_root,
            generic_plan[1],
            generic_plan[0],
            condition_id="case_01",
        ).complete_mission_success,
        "universal_purchase_policy_fails": (
            not all(always_buy_results) and not all(always_none_results)
        ),
        "justified_abstention_passes": justified_grade.complete_mission_success,
        "all_disclosed_case2_resource_policies_exercised": case2_x46_grade.complete_mission_success,
        "harmless_rounding_passes": rounded_grade.complete_mission_success,
        "optional_incorrect_calculation_is_diagnostic_only": (
            optional_grade.complete_mission_success
        ),
        "case1_disclosed_action_alternatives_pass": (
            conditional_grade.complete_mission_success and cautious_grade.complete_mission_success
        ),
        "semantic_column_remapping_passes": renamed_grade.complete_mission_success,
        "partial_credit_preserved": partial_ok,
        "mission_failure_consistency": mission_consistent,
        "results": rows,
    }


__all__ = ["CONDITIONS", "build_open_reference", "run_open_controls"]

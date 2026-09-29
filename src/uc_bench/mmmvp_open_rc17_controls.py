"""Zero-cost scientific and adversarial controls for the isolated Case-1 successor."""

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
from uc_bench.mmmvp_open_rc17_contract import (
    SCHEMA_VERSION,
    validate_followup_plan,
    validate_validation_plan,
)
from uc_bench.mmmvp_open_rc17_environment import RC17OpenMMMVPEnvironment
from uc_bench.mmmvp_open_rc17_verifier import (
    _resource_expected,
    verify_rc17_case1_submission,
)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(rows: list[dict[str, Any]]) -> list[CanonicalRow]:
    return [
        CanonicalRow(
            entity_id=str(row["unit"]),
            source_record_ids=tuple(sorted(str(row["records"]).split("|"))),
            prediction=float(row["score"]),
            outcome=int(row["label"]),
            split="VALIDATION",
            contexts=tuple(sorted(filter(None, str(row.get("setting", "")).split("|")))),
        )
        for row in rows
    ]


def _primary_rows(workspace: Path, aggregation: str) -> list[dict[str, Any]]:
    metadata = _read_csv(workspace / "data/cohort_metadata.csv")
    predictions = {
        row["sample_id"]: float(row["predicted_probability"])
        for row in _read_csv(workspace / "data/locked_predictions.csv")
    }
    outcomes = {
        row["patient_key"]: int(row["week6_response"])
        for row in _read_csv(workspace / "revealed/validation_outcomes.csv")
    }
    eligible = [
        row
        for row in metadata
        if row.get("baseline_eligible", "").lower() == "true" and row["sample_id"] in predictions
    ]
    if aggregation == "NONE":
        return [
            {
                "unit": row["fingerprint_cluster"],
                "records": row["sample_id"],
                "score": predictions[row["sample_id"]],
                "label": outcomes[row["fingerprint_cluster"]],
                "partition": "VALIDATION",
                "setting": row["site"],
            }
            for row in eligible
        ]
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in eligible:
        grouped.setdefault(row["fingerprint_cluster"], []).append(row)
    result: list[dict[str, Any]] = []
    for entity, source_rows in sorted(grouped.items()):
        ordered = sorted(source_rows, key=lambda row: row["sample_id"])
        values = [predictions[row["sample_id"]] for row in ordered]
        if aggregation == "MEAN":
            score = mean(values)
        elif aggregation == "MEDIAN":
            score = median(values)
        else:
            score = values[0]
        result.append(
            {
                "unit": entity,
                "records": "|".join(row["sample_id"] for row in ordered),
                "score": score,
                "label": outcomes[entity],
                "partition": "VALIDATION",
                "setting": "|".join(sorted({row["site"] for row in ordered})),
            }
        )
    return result


def _eligible_manifest(workspace: Path, *, exclude_pending: bool) -> tuple[Path, set[str]]:
    metadata = _read_csv(workspace / "data/cohort_metadata.csv")
    grouped: dict[str, list[str]] = {}
    for row in metadata:
        if row.get("baseline_eligible", "").lower() == "true":
            grouped.setdefault(row["fingerprint_cluster"], []).append(row["sample_id"])
    rows: list[dict[str, Any]] = []
    included: set[str] = set()
    for entity, sources in sorted(grouped.items()):
        exclude = exclude_pending and entity == "F0001"
        if not exclude:
            included.add(entity)
        rows.append(
            {
                "entity_id": entity,
                "source_record_ids": "|".join(sorted(sources)),
                "included": str(not exclude).lower(),
                "preoutcome_exclusion_reason": ("PREOUTCOME_ENDPOINT_AMBIGUITY" if exclude else ""),
            }
        )
    path = workspace / "work/eligible_entities.csv"
    _write_csv(path, rows)
    return path, included


def _decision(disposition: str, use_scope: str) -> dict[str, Any]:
    stage = "EXTERNAL_VALIDATION" if disposition == "CONTINUE" else "INTERNAL_VALIDATION"
    return {
        "development_stage": stage,
        "disposition": disposition,
        "use_scope": use_scope,
        "allowed_use": ["Use only in bounded retrospective research."],
        "prohibited_use": ["No treatment selection or clinical deployment."],
        "unresolved_gates": ["Independent prospective evidence remains outstanding."],
        "required_next_evidence": ["Decision-matched independent validation."],
    }


def _plan(
    workspace: Path,
    *,
    aggregation: str,
    probability_metric: str,
    utility_metric: str,
    context_metric: str,
    exclude_pending: bool,
    thresholds: dict[str, float] | None = None,
) -> tuple[dict[str, Any], set[str]]:
    manifest, included = _eligible_manifest(workspace, exclude_pending=exclude_pending)
    clustered = aggregation == "NONE"
    estimator = "ENTITY_WEIGHTED" if clustered else "EMPIRICAL"
    uncertainty = "CLUSTER_BOOTSTRAP_PERCENTILE" if clustered else "ENTITY_BOOTSTRAP_PERCENTILE"
    metric = {
        "DISCRIMINATION": "ROC_AUC",
        "PROBABILITY_ACCURACY": probability_metric,
        "CALIBRATION": "CALIBRATION_ERROR",
        "THRESHOLD_UTILITY": utility_metric,
        "CONTEXT_ROBUSTNESS": context_metric,
    }
    default_thresholds = {
        "DISCRIMINATION": 0.70,
        "PROBABILITY_ACCURACY": (0.23 if probability_metric == "BRIER_SCORE" else 0.68),
        "CALIBRATION": 0.12,
        "THRESHOLD_UTILITY": 0.02,
        "CONTEXT_ROBUSTNESS": 0.55,
    }
    default_thresholds.update(thresholds or {})
    comparator = {
        "DISCRIMINATION": "AT_LEAST",
        "PROBABILITY_ACCURACY": "AT_MOST",
        "CALIBRATION": "AT_MOST",
        "THRESHOLD_UTILITY": "AT_LEAST",
        "CONTEXT_ROBUSTNESS": "AT_LEAST",
    }
    exclusions = (
        [
            {
                "entity_id": "F0001",
                "reason": "PREOUTCOME_ENDPOINT_AMBIGUITY",
                "evidence_refs": ["data/endpoint_source_ledger.csv"],
            }
        ]
        if exclude_pending
        else []
    )
    criteria = [
        {
            "criterion_id": f"G_{prop}",
            "calculation_id": f"C_{prop}",
            "property": prop,
            "metric": metric[prop],
            "comparator": comparator[prop],
            "threshold": default_thresholds[prop],
        }
        for prop in (
            "DISCRIMINATION",
            "PROBABILITY_ACCURACY",
            "CALIBRATION",
            "THRESHOLD_UTILITY",
            "CONTEXT_ROBUSTNESS",
        )
    ]
    return (
        {
            "schema_version": SCHEMA_VERSION,
            "decision_definition": "Whether the locked predictor supports the next bounded stage.",
            "evidence_standard": "Prospective patient-level validation with decision metrics.",
            "hypotheses": [
                {
                    "hypothesis_id": "H_SUPPORT",
                    "statement": "The evidence supports a bounded research step.",
                    "belief": 0.5,
                    "decision_effect_if_true": "SUPPORTS",
                },
                {
                    "hypothesis_id": "H_LIMIT",
                    "statement": "A material limitation prevents that step.",
                    "belief": 0.5,
                    "decision_effect_if_true": "INVALIDATES",
                },
            ],
            "planned_analyses": [
                {
                    "analysis_id": "A_PRIMARY",
                    "question": "Does the locked predictor meet the bounded evidence standard?",
                    "method": "Declared patient-respecting validation workflow.",
                    "analysis_unit": "Person with the declared dependence handling.",
                    "input_paths": [
                        "intended_use.json",
                        "identity_provenance.json",
                        "data/cohort_metadata.csv",
                        "data/locked_predictions.csv",
                        "data/endpoint_source_ledger.csv",
                        "work/eligible_entities.csv",
                    ],
                    "planned_output_paths": [
                        "work/primary_analysis.csv",
                        "work/primary_results.json",
                    ],
                    "decision_relevance": "Provides the quantitative decision evidence.",
                }
            ],
            "decision_criteria": criteria,
            "prospective_specification": {
                "biological_unit": "PERSON",
                "dependence_handling": (
                    "SOURCE_RECORD_CLUSTERING" if clustered else "PERSON_LEVEL_AGGREGATION"
                ),
                "aggregation": aggregation,
                "eligible_entity_manifest_path": "work/eligible_entities.csv",
                "eligible_entity_manifest_sha256": _sha(manifest),
                "identity_provenance_path": "identity_provenance.json",
                "outcome_role": "SEALED_VALIDATION_OUTCOMES",
                "estimator": estimator,
                "discrimination_metric": "ROC_AUC",
                "probability_metric": probability_metric,
                "calibration_metric": "CALIBRATION_ERROR",
                "calibration_bin_count": 7,
                "utility_metric": utility_metric,
                "utility_threshold": 0.5,
                "context_metric": context_metric,
                "uncertainty_method": uncertainty,
                "uncertainty_replicates": 200,
                "uncertainty_seed": 41,
                "uncertainty_level": 0.95,
                "exclusions": exclusions,
            },
            "evidence_refs": [
                "intended_use.json",
                "identity_provenance.json",
                "data/endpoint_source_ledger.csv",
                "work/eligible_entities.csv",
            ],
        },
        included,
    )


def _calculation(
    calculation_id: str,
    prop: str,
    metric: str,
    table_id: str,
    rows: list[dict[str, Any]],
    included: set[str],
    *,
    structure: str,
    aggregation: str,
    estimator: str,
    role: str,
    output_id: str,
) -> dict[str, Any]:
    selected = [row for row in _canonical(rows) if row.entity_id in included]
    normalized = {
        "BINARY_CONCORDANCE": "ROC_AUC",
        "THRESHOLD_EXPECTED_UTILITY": "NET_BENEFIT",
    }.get(metric, metric)
    parameters: dict[str, Any] = {}
    if normalized == "CALIBRATION_ERROR":
        parameters["bin_count"] = 7
    if normalized == "NET_BENEFIT":
        parameters["threshold"] = 0.5
        if metric == "THRESHOLD_EXPECTED_UTILITY":
            parameters.update({"true_positive_value": 1.0, "false_positive_cost": 1.0})
    result = {
        "calculation_id": calculation_id,
        "role": role,
        "source_analysis_table_id": table_id,
        "unit_of_analysis": (
            "SOURCE_RECORD_CLUSTERED"
            if structure == "SOURCE_RECORD_CLUSTERED"
            else "BIOLOGICAL_ENTITY"
        ),
        "cohort": {
            "split_values": ["VALIDATION"],
            "entity_ids": sorted(included),
            "included_row_count": len(selected),
        },
        "outcome_column": "label",
        "prediction_column": "score",
        "context_columns": ["setting"],
        "metric": metric,
        "estimator": estimator,
        "parameters": parameters,
        "reported_value": calculate_metric(selected, normalized, estimator, parameters),
        "evidence_source": "PURCHASED" if role == "FOLLOWUP" else "SUPPLIED_AND_REVEALED",
        "output_artifact_id": output_id,
    }
    if prop == "DISCRIMINATION":
        low, high = cluster_bootstrap_interval(
            selected,
            estimator,
            replicates=200,
            seed=41,
        )
        result["uncertainty"] = {
            "method": (
                "CLUSTER_BOOTSTRAP_PERCENTILE"
                if structure == "SOURCE_RECORD_CLUSTERED"
                else "ENTITY_BOOTSTRAP_PERCENTILE"
            ),
            "level": 0.95,
            "replicates": 200,
            "seed": 41,
            "lower": low,
            "upper": high,
        }
    return result


def _resource_rows(workspace: Path, resource: str) -> list[dict[str, Any]]:
    if resource == "X17":
        crosswalk = _read_csv(workspace / "purchased/X17/canonical_person_crosswalk.csv")
        canonical = {row["source_record_id"]: row for row in crosswalk}
        metadata = _read_csv(workspace / "data/cohort_metadata.csv")
        predictions = {
            row["sample_id"]: float(row["predicted_probability"])
            for row in _read_csv(workspace / "data/locked_predictions.csv")
        }
        outcomes = {
            row["patient_key"]: int(row["week6_response"])
            for row in _read_csv(workspace / "revealed/validation_outcomes.csv")
        }
        grouped: dict[str, list[dict[str, str]]] = {}
        for row in metadata:
            grouped.setdefault(canonical[row["sample_id"]]["canonical_person_id"], []).append(row)
        return [
            {
                "unit": key,
                "records": "|".join(sorted(row["sample_id"] for row in values)),
                "score": mean(predictions[row["sample_id"]] for row in values),
                "label": outcomes[values[0]["fingerprint_cluster"]],
                "partition": "VALIDATION",
                "setting": "|".join(sorted({row["site"] for row in values})),
            }
            for key, values in sorted(grouped.items())
        ]
    if resource in {"X31", "X46"}:
        stem = "replay" if resource == "X31" else "matched"
        prediction_path = workspace / f"purchased/{resource}/{stem}_predictions.csv"
        outcome_path = (
            workspace / "revealed/validation_outcomes.csv"
            if resource == "X31"
            else workspace / "purchased/X46/matched_outcomes.csv"
        )
        outcomes = {
            row["patient_key"]: int(row["week6_response"]) for row in _read_csv(outcome_path)
        }
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
    return []


def _resource_question(resource: str) -> str:
    return {
        "none": "CURRENT_DECISION_ALREADY_RESOLVED",
        "X17": "IDENTITY_LINKAGE",
        "X24": "ENDPOINT_VALIDITY",
        "X31": "PIPELINE_REPRODUCIBILITY",
        "X46": "CROSS_CONTEXT_TRANSPORT",
        "X58": "PRECISION_WITH_SAME_PROCESS",
        "X63": "EXPERT_INTERPRETATION",
    }[resource]


def _resource_basis(resource: str) -> list[str]:
    return {
        "none": ["work/primary_results.json"],
        "X17": ["identity_provenance.json", "data/cohort_metadata.csv"],
        "X24": ["data/endpoint_source_ledger.csv"],
        "X31": ["logs/execution_log.csv", "model/reproduction_cases.csv"],
        "X46": ["intended_use.json", "followup_catalog.json"],
        "X58": ["work/primary_results.json", "followup_catalog.json"],
        "X63": ["intended_use.json", "sponsor/assertions.md"],
    }[resource]


def _followup(resource: str) -> dict[str, Any]:
    question = _resource_question(resource)
    return {
        "schema_version": SCHEMA_VERSION,
        "decision_question_id": "Q_RESOURCE",
        "decision_question": "Which remaining uncertainty changes the immediate action?",
        "decision_question_type": question,
        "chosen_resource": resource,
        "evidence_target": {
            "none": "NO_NEW_EVIDENCE",
            "X17": "RECORD_LINKAGE",
            "X24": "ENDPOINT_REVIEW",
            "X31": "PIPELINE_REPLAY",
            "X46": "EXTERNAL_COHORT",
            "X58": "ADDITIONAL_SAMPLE",
            "X63": "EXPERT_REVIEW",
        }[resource],
        "materiality_threshold": 0 if resource in {"none", "X17", "X63"} else 0.05,
        "live_explanations": [
            {
                "explanation_id": "E_SUPPORT",
                "statement": "The bounded evidence chain is adequate.",
                "distinguishing_evidence": "The selected evidence is consistent and material.",
            },
            {
                "explanation_id": "E_LIMIT",
                "statement": "A limitation explains the apparent result.",
                "distinguishing_evidence": "The selected evidence changes or invalidates it.",
            },
        ],
        "alternatives_considered": [
            {"resource_id": resource, "limitations": "Answers only the declared question."},
            {"resource_id": "X63", "limitations": "Does not create empirical evidence."},
        ],
        "result_contingencies": [
            {
                "contingency_id": "K_SUPPORT",
                "observable_result": "The evidence supports the bounded step.",
                "hypothesis_updates": [
                    {"hypothesis_id": "H_SUPPORT", "direction": "INCREASE"},
                    {"hypothesis_id": "H_LIMIT", "direction": "DECREASE"},
                ],
                "next_decision": _decision("CONTINUE", "RESEARCH_PROBABILITY"),
                "next_action": "Continue only to the bounded next evidence stage.",
            },
            {
                "contingency_id": "K_LIMIT",
                "observable_result": "The evidence exposes a blocker.",
                "hypothesis_updates": [
                    {"hypothesis_id": "H_SUPPORT", "direction": "DECREASE"},
                    {"hypothesis_id": "H_LIMIT", "direction": "INCREASE"},
                ],
                "next_decision": _decision("PAUSE", "RESEARCH_PROBABILITY"),
                "next_action": "Pause advancement and contain the claim.",
            },
        ],
        "beliefs_before": {"H_SUPPORT": 0.5, "H_LIMIT": 0.5},
        "current_decision": _decision("CONTINUE", "RESEARCH_PROBABILITY"),
        "evidence_refs": _resource_basis(resource),
    }


def _effect(expected: dict[str, Any], resource: str, primary_auc: float) -> tuple[str, bool]:
    if resource == "none":
        return "NO_NEW_EVIDENCE", False
    if resource == "X17":
        return "INEFFECTIVE", False
    if resource == "X63":
        return "REDUCES_UNCERTAINTY", False
    if resource == "X24":
        # Both the ordinary and altered-input fixtures expose a pre-purchase
        # endpoint-adjudication gate, so the blinded review resolves a material
        # uncertainty even when it confirms every label.
        material = True
        return (
            "EXPOSES_BLOCKER"
            if expected["roc_auc"] <= 0.5 or expected["net_benefit"] < 0
            else "RESOLVES",
            material,
        )
    if resource == "X31":
        material = expected["primary_auc_absolute_delta"] > 0.05
        return ("EXPOSES_BLOCKER" if material else "RESOLVES"), material
    if resource == "X46":
        return (
            "EXPOSES_BLOCKER"
            if expected["roc_auc"] <= 0.5 or expected["net_benefit"] < 0
            else "REDUCES_UNCERTAINTY",
            True,
        )
    material = abs(expected["roc_auc"] - primary_auc) > 0.05 or expected["net_benefit"] < 0
    return ("EXPOSES_BLOCKER" if material else "REDUCES_UNCERTAINTY"), material


def build_reference(
    project_root: Path,
    run_root: Path,
    *,
    aggregation: str = "MEAN",
    probability_metric: str = "BRIER_SCORE",
    utility_metric: str = "NET_BENEFIT",
    context_metric: str = "WORST_SITE_ROC_AUC",
    exclude_pending: bool = False,
    resource: str = "none",
    control_outcomes: Path | None = None,
    control_provenance: Path | None = None,
    control_resources: dict[str, Path] | None = None,
) -> tuple[dict[str, Any], Path]:
    environment = RC17OpenMMMVPEnvironment(
        project_root,
        "case_01",
        run_root,
        control_outcomes=control_outcomes,
        control_outcome_provenance=control_provenance,
        control_resource_overrides=control_resources,
    )
    plan, included = _plan(
        run_root,
        aggregation=aggregation,
        probability_metric=probability_metric,
        utility_metric=utility_metric,
        context_metric=context_metric,
        exclude_pending=exclude_pending,
    )
    committed = environment.commit_validation_plan(json.dumps(plan))
    assert committed["accepted"], committed
    environment.reveal_validation()
    primary_rows = _primary_rows(run_root, aggregation)
    _write_csv(run_root / "work/primary_analysis.csv", primary_rows)
    structure = "SOURCE_RECORD_CLUSTERED" if aggregation == "NONE" else "ENTITY_AGGREGATED"
    estimator = "ENTITY_WEIGHTED" if aggregation == "NONE" else "EMPIRICAL"
    metrics = {row["property"]: row["metric"] for row in plan["decision_criteria"]}
    calculations = [
        _calculation(
            f"C_{prop}",
            prop,
            metrics[prop],
            "TABLE_PRIMARY",
            primary_rows,
            included,
            structure=structure,
            aggregation=aggregation,
            estimator=estimator,
            role="PRIMARY",
            output_id="OUTPUT_RESULTS",
        )
        for prop in metrics
    ]
    artifacts: list[dict[str, Any]] = [
        {
            "artifact_id": "TABLE_PRIMARY",
            "path": "work/primary_analysis.csv",
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
            "analysis_structure": structure,
            "aggregation": aggregation,
        },
        {
            "artifact_id": "OUTPUT_RESULTS",
            "path": "work/primary_results.json",
            "role": "CALCULATION_OUTPUT",
            "source_paths": ["work/primary_analysis.csv"],
        },
    ]
    followup = _followup(resource)
    accepted = environment.commit_followup_plan(json.dumps(followup))
    assert accepted["accepted"], accepted
    environment.purchase_resource(resource)
    resource_rows = _resource_rows(run_root, resource)
    resource_calculation_ids: list[str] = []
    if resource_rows:
        _write_csv(run_root / "work/resource_analysis.csv", resource_rows)
        source_paths = {
            "X17": [
                "purchased/X17/canonical_person_crosswalk.csv",
                "revealed/validation_outcomes.csv",
                "data/cohort_metadata.csv",
                "data/locked_predictions.csv",
            ],
            "X31": [
                "purchased/X31/replay_predictions.csv",
                "revealed/validation_outcomes.csv",
            ],
            "X46": [
                "purchased/X46/matched_predictions.csv",
                "purchased/X46/matched_outcomes.csv",
            ],
        }[resource]
        artifacts.append(
            {
                "artifact_id": "TABLE_RESOURCE",
                "path": "work/resource_analysis.csv",
                "role": "ANALYSIS_TABLE",
                "source_paths": source_paths,
                "column_map": {
                    "entity_id": "unit",
                    "source_record_ids": "records",
                    "prediction": "score",
                    "outcome": "label",
                    "split": "partition",
                    "context": "setting",
                },
                "analysis_structure": "ENTITY_AGGREGATED",
                "aggregation": "MEAN" if resource == "X17" else "NONE",
            }
        )
        followup_metric = "ENTITY_COUNT" if resource == "X17" else "ROC_AUC"
        identifier = "C_RESOURCE"
        calculations.append(
            _calculation(
                identifier,
                "FOLLOWUP",
                followup_metric,
                "TABLE_RESOURCE",
                resource_rows,
                {row["unit"] for row in resource_rows},
                structure="ENTITY_AGGREGATED",
                aggregation="MEAN" if resource == "X17" else "NONE",
                estimator="EMPIRICAL",
                role="FOLLOWUP",
                output_id="OUTPUT_RESULTS",
            )
        )
        resource_calculation_ids.append(identifier)
    primary_auc = next(
        float(row["reported_value"])
        for row in calculations
        if row["calculation_id"] == "C_DISCRIMINATION"
    )
    expected = _resource_expected(
        run_root,
        resource,
        primary_auc,
        calibration_bin_count=7,
        validation_plan=plan,
    )
    resource_manifest = json.loads(
        (run_root / f"purchased/{resource}/resource_manifest.json").read_text()
    )
    source_hashes = {
        f"purchased/{resource}/{row['path']}": row["sha256"] for row in resource_manifest["files"]
    }
    resource_summary = {
        "schema_version": "case1-resource-summary-1",
        "resource_id": resource,
        "source_hashes": source_hashes,
        "results": expected,
    }
    _json(run_root / "work/resource_summary.json", resource_summary)
    artifacts.append(
        {
            "artifact_id": "RESOURCE_SUMMARY",
            "path": "work/resource_summary.json",
            "role": "PROVENANCE",
            "source_paths": sorted(source_hashes),
        }
    )
    _json(
        run_root / "work/primary_results.json",
        {
            "typed_calculations": [
                {
                    "calculation_id": row["calculation_id"],
                    "reported_value": row["reported_value"],
                }
                for row in calculations
            ]
        },
    )
    effect, material = _effect(expected, resource, primary_auc)
    primary_pass = all(
        (
            row["reported_value"] >= criterion["threshold"]
            if criterion["comparator"] == "AT_LEAST"
            else row["reported_value"] <= criterion["threshold"]
        )
        for criterion in plan["decision_criteria"]
        for row in calculations
        if row["calculation_id"] == criterion["calculation_id"]
    )
    if resource == "X24":
        primary_pass = bool(
            expected["roc_auc"] >= 0.70
            and expected["brier_score"] <= 0.23
            and expected["calibration_error"] <= 0.12
            and expected["net_benefit"] >= 0.02
            and expected["worst_site_roc_auc"] >= 0.55
        )
    continue_decision = primary_pass and effect != "EXPOSES_BLOCKER"
    decision = _decision(
        "CONTINUE" if continue_decision else "PAUSE",
        "RESEARCH_PROBABILITY" if continue_decision else "NO_USE",
    )
    if effect == "EXPOSES_BLOCKER":
        after_support, after_limit, contingency = 0.25, 0.75, "K_LIMIT"
    elif effect in {"NO_NEW_EVIDENCE", "INEFFECTIVE"}:
        after_support, after_limit, contingency = 0.5, 0.5, "K_SUPPORT"
    else:
        after_support, after_limit, contingency = 0.70, 0.30, "K_SUPPORT"
    claims = [
        {
            "claim_id": "CLAIM_PROBABILITY",
            "statement": "The internal evidence supports a bounded prognostic probability claim.",
            "status": "SUPPORTED" if continue_decision else "UNRESOLVED",
            "scope": "PROGNOSTIC_PROBABILITY",
            "evidence_refs": ["work/primary_results.json"],
            "calculation_ids": (
                ["C_DISCRIMINATION", "C_PROBABILITY_ACCURACY", "C_CALIBRATION"]
                if continue_decision
                else []
            ),
        },
        *[
            {
                "claim_id": f"LIMIT_{scope}",
                "statement": "The broader use is not established.",
                "status": "NOT_SUPPORTED",
                "scope": scope,
                "evidence_refs": [],
                "calculation_ids": [],
            }
            for scope in (
                "INDEPENDENT_VALIDATION",
                "CLINICAL_UTILITY",
                "TREATMENT_EFFECT",
                "CROSS_CONTEXT_TRANSPORT",
            )
        ],
    ]
    final = {
        "schema_version": SCHEMA_VERSION,
        "artifact_manifest": artifacts,
        "calculations": calculations,
        "findings": [
            {
                "finding_id": "F_PRIMARY",
                "statement": "The saved analysis determines the bounded action.",
                "status": "SUPPORTED",
                "decision_effect": "SUPPORTS" if continue_decision else "WEAKENS",
                "evidence_refs": ["work/primary_analysis.csv", "work/primary_results.json"],
                "calculation_ids": ["C_DISCRIMINATION"],
            }
        ],
        "evidence_assessments": [
            {
                "evidence_id": "EV_RESOURCE",
                "source_paths": sorted(source_hashes),
                "eligible_for_decision": True,
                "rationale": "The returned evidence is linked and independently recomputed.",
            }
        ],
        "belief_updates": [
            {
                "hypothesis_id": "H_SUPPORT",
                "before": 0.5,
                "after": after_support,
                "evidence_refs": ["work/resource_summary.json"],
                "matched_contingency_id": contingency,
            },
            {
                "hypothesis_id": "H_LIMIT",
                "before": 0.5,
                "after": after_limit,
                "evidence_refs": ["work/resource_summary.json"],
                "matched_contingency_id": contingency,
            },
        ],
        "decision": decision,
        "claims": claims,
        "remaining_uncertainties": ["Independent prospective validation remains required."],
        "evidence_refs": [
            "intended_use.json",
            "work/primary_analysis.csv",
            "work/primary_results.json",
            "work/resource_summary.json",
        ],
        "resource_assessment": {
            "resource_id": resource,
            "question_type": _resource_question(resource),
            "summary_artifact_path": "work/resource_summary.json",
            "source_paths": sorted(source_hashes),
            "calculation_ids": resource_calculation_ids,
            "observed_effect": effect,
            "material": material,
        },
        "narrative_summary": "Bounded scientific conclusion with explicit limitations.",
    }
    submitted = environment.submit(json.dumps(final))
    assert submitted["accepted"], submitted
    return environment.export_submission(), run_root


def _copy_episode(source_submission: dict[str, Any], source: Path, target: Path) -> dict[str, Any]:
    shutil.copytree(source, target)
    source_records = source.parent / ".mmmvp_host_records" / source.name
    target_records = target.parent / ".mmmvp_host_records" / target.name
    target_records.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_records, target_records)
    result = copy.deepcopy(source_submission)
    result["host_record_locator"] = target_records.resolve().as_posix()
    return result


def _replace_final(submission: dict[str, Any], workspace: Path, final: dict[str, Any]) -> None:
    digest = hashlib.sha256(
        json.dumps(final, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    submission["final_submission"] = final
    submission["state"]["final_submission_hash"] = digest
    next(row for row in submission["event_log"] if row["event"] == "submit")[
        "final_submission_hash"
    ] = digest
    records = workspace.parent / ".mmmvp_host_records" / workspace.name
    _json(records / "final_submission.json", final)


def _sync_output(workspace: Path, final: dict[str, Any]) -> None:
    _json(
        workspace / "work/primary_results.json",
        {
            "typed_calculations": [
                {
                    "calculation_id": row["calculation_id"],
                    "reported_value": row["reported_value"],
                }
                for row in final["calculations"]
            ]
        },
    )


def _grade(project_root: Path, submission: dict[str, Any], workspace: Path) -> dict[str, Any]:
    return verify_rc17_case1_submission(project_root, workspace, submission).to_dict()


def _negative_inputs(project_root: Path, root: Path) -> tuple[Path, Path, Path]:
    sealed = project_root / "grader_private/hard_suite_v07/case_01/sealed"
    outcomes = _read_csv(sealed / "validation_outcomes.csv")
    for row in outcomes:
        row["week6_response"] = str(1 - int(row["week6_response"]))
    outcome_path = root / "negative_validation_outcomes.csv"
    _write_csv(outcome_path, outcomes)
    provenance_path = root / "negative_outcome_provenance.json"
    _json(
        provenance_path,
        {
            "prediction_blinded_review": True,
            "unsealed_only_after_commit": True,
            "requires_endpoint_adjudication": True,
            "status": "provisional_import_pending_blinded_adjudication",
        },
    )
    resource = root / "negative_x24"
    resource.mkdir(parents=True)
    _write_csv(
        resource / "adjudicated_endpoints.csv",
        [
            {
                "patient_key": row["patient_key"],
                "week6_response": row["week6_response"],
                "assessment_day": 42,
                "source": "blinded_adjudication",
                "reviewer_agreement": "concordant",
            }
            for row in outcomes
        ],
    )
    _json(
        resource / "adjudication_provenance.json",
        {"blinded_to_prediction": True, "reviewers": 2},
    )
    return outcome_path, provenance_path, resource


def run_controls(project_root: Path, root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    controls: list[dict[str, Any]] = []

    workflows = [
        ("reference_mean", {}),
        ("valid_median", {"aggregation": "MEDIAN"}),
        ("valid_first", {"aggregation": "FIRST"}),
        ("valid_clustered", {"aggregation": "NONE"}),
        (
            "valid_alias_and_logloss",
            {
                "probability_metric": "LOG_LOSS",
                "utility_metric": "THRESHOLD_EXPECTED_UTILITY",
                "context_metric": "SITE_WEIGHTED_ROC_AUC",
            },
        ),
        ("valid_preoutcome_exclusion", {"exclude_pending": True}),
        ("valid_clustered_x24", {"aggregation": "NONE", "resource": "X24"}),
        (
            "valid_alias_x24",
            {
                "probability_metric": "LOG_LOSS",
                "utility_metric": "THRESHOLD_EXPECTED_UTILITY",
                "context_metric": "SITE_WEIGHTED_ROC_AUC",
                "resource": "X24",
            },
        ),
    ]
    references: dict[str, tuple[dict[str, Any], Path]] = {}
    for name, kwargs in workflows:
        episode = build_reference(project_root, root / name, **kwargs)
        references[name] = episode
        controls.append({"control": name, "grade": _grade(project_root, *episode)})

    vacuous = {
        "vacuous_auc": {"DISCRIMINATION": 0.0},
        "vacuous_brier": {"PROBABILITY_ACCURACY": 1.0},
        "vacuous_utility": {"THRESHOLD_UTILITY": -1.0},
        "vacuous_context": {"CONTEXT_ROBUSTNESS": 0.0},
    }
    scratch = RC17OpenMMMVPEnvironment(project_root, "case_01", root / "vacuous_scratch")
    for name, thresholds in vacuous.items():
        plan, _ = _plan(
            scratch.run_root,
            aggregation="MEAN",
            probability_metric="BRIER_SCORE",
            utility_metric="NET_BENEFIT",
            context_metric="WORST_SITE_ROC_AUC",
            exclude_pending=False,
            thresholds=thresholds,
        )
        controls.append(
            {
                "control": name,
                "validation_accepted": validate_validation_plan(plan).valid,
                "issues": [row.to_dict() for row in validate_validation_plan(plan).issues],
            }
        )

    zero_x31 = _followup("X31")
    zero_x31["materiality_threshold"] = 0
    controls.append(
        {
            "control": "zero_materiality_x31",
            "validation_accepted": validate_followup_plan(zero_x31).valid,
            "issues": [row.to_dict() for row in validate_followup_plan(zero_x31).issues],
        }
    )

    reference, reference_workspace = references["reference_mean"]
    no_analysis_workspace = root / "no_analysis"
    no_analysis = _copy_episode(reference, reference_workspace, no_analysis_workspace)
    final = copy.deepcopy(no_analysis["final_submission"])
    final["artifact_manifest"] = [
        row for row in final["artifact_manifest"] if row["artifact_id"] == "RESOURCE_SUMMARY"
    ]
    final["calculations"] = []
    final["findings"][0]["calculation_ids"] = []
    final["claims"] = [row for row in final["claims"] if row["status"] != "SUPPORTED"]
    final["decision"] = _decision("PAUSE", "NO_USE")
    _replace_final(no_analysis, no_analysis_workspace, final)
    controls.append(
        {
            "control": "correct_decision_without_analysis",
            "grade": _grade(project_root, no_analysis, no_analysis_workspace),
        }
    )

    subset_workspace = root / "post_reveal_subset"
    subset = _copy_episode(reference, reference_workspace, subset_workspace)
    subset_final = copy.deepcopy(subset["final_submission"])
    keep = sorted(set(subset_final["calculations"][0]["cohort"]["entity_ids"]))[:40]
    table_rows = _read_csv(subset_workspace / "work/primary_analysis.csv")
    selected = [row for row in _canonical(table_rows) if row.entity_id in set(keep)]
    for row in subset_final["calculations"]:
        if row["role"] != "PRIMARY":
            continue
        row["cohort"]["entity_ids"] = keep
        row["cohort"]["included_row_count"] = len(selected)
        normalized = {
            "BINARY_CONCORDANCE": "ROC_AUC",
            "THRESHOLD_EXPECTED_UTILITY": "NET_BENEFIT",
        }.get(row["metric"], row["metric"])
        row["reported_value"] = calculate_metric(
            selected, normalized, row["estimator"], row["parameters"]
        )
        if row.get("uncertainty"):
            low, high = cluster_bootstrap_interval(
                selected,
                row["estimator"],
                replicates=row["uncertainty"]["replicates"],
                seed=row["uncertainty"]["seed"],
            )
            row["uncertainty"]["lower"] = low
            row["uncertainty"]["upper"] = high
    _sync_output(subset_workspace, subset_final)
    _replace_final(subset, subset_workspace, subset_final)
    controls.append(
        {
            "control": "post_reveal_favourable_subset",
            "grade": _grade(project_root, subset, subset_workspace),
        }
    )

    wrong_workspace = root / "wrong_decision"
    wrong = _copy_episode(reference, reference_workspace, wrong_workspace)
    wrong_final = copy.deepcopy(wrong["final_submission"])
    wrong_final["decision"] = _decision("PAUSE", "RESEARCH_PROBABILITY")
    _replace_final(wrong, wrong_workspace, wrong_final)
    controls.append(
        {
            "control": "correct_analysis_wrong_decision",
            "grade": _grade(project_root, wrong, wrong_workspace),
        }
    )

    stop_workspace = root / "universal_stop"
    stop = _copy_episode(reference, reference_workspace, stop_workspace)
    stop_final = copy.deepcopy(stop["final_submission"])
    stop_final["decision"] = _decision("STOP", "NO_USE")
    _replace_final(stop, stop_workspace, stop_final)
    controls.append(
        {
            "control": "original_universal_stop",
            "grade": _grade(project_root, stop, stop_workspace),
        }
    )

    clinical_workspace = root / "unsupported_clinical"
    clinical = _copy_episode(reference, reference_workspace, clinical_workspace)
    clinical_final = copy.deepcopy(clinical["final_submission"])
    clinical_final["decision"] = _decision("CONTINUE", "CLINICAL_DECISION_SUPPORT")
    _replace_final(clinical, clinical_workspace, clinical_final)
    controls.append(
        {
            "control": "unsupported_clinical_advance",
            "grade": _grade(project_root, clinical, clinical_workspace),
        }
    )

    optional_workspace = root / "optional_invalid"
    optional = _copy_episode(reference, reference_workspace, optional_workspace)
    optional_final = copy.deepcopy(optional["final_submission"])
    optional_final["artifact_manifest"].append(
        {
            "artifact_id": "OPTIONAL_NOTE",
            "path": "work/missing_optional_note.txt",
            "role": "OTHER",
            "source_paths": [],
        }
    )
    _replace_final(optional, optional_workspace, optional_final)
    controls.append(
        {
            "control": "invalid_optional_artifact",
            "grade": _grade(project_root, optional, optional_workspace),
        }
    )

    prose_workspace = root / "prose_contradiction"
    prose = _copy_episode(reference, reference_workspace, prose_workspace)
    prose_final = copy.deepcopy(prose["final_submission"])
    prose_final["narrative_summary"] = "Proceed to clinical deployment and prove treatment effect."
    _replace_final(prose, prose_workspace, prose_final)
    controls.append(
        {
            "control": "contradictory_prose_diagnostic",
            "grade": _grade(project_root, prose, prose_workspace),
        }
    )

    machine_workspace = root / "contradictory_machine_decision"
    machine = _copy_episode(reference, reference_workspace, machine_workspace)
    machine_final = copy.deepcopy(machine["final_submission"])
    machine_final["decision"].update(
        {"development_stage": "STOPPED", "disposition": "CONTINUE", "use_scope": "NO_USE"}
    )
    machine_final["findings"][0]["decision_effect"] = "INVALIDATES"
    _replace_final(machine, machine_workspace, machine_final)
    controls.append(
        {
            "control": "contradictory_machine_decision",
            "grade": _grade(project_root, machine, machine_workspace),
        }
    )

    malformed_workspace = root / "malformed_primary"
    malformed = _copy_episode(reference, reference_workspace, malformed_workspace)
    (malformed_workspace / "work/primary_analysis.csv").write_bytes(b"\xff\xfe\x00broken")
    controls.append(
        {
            "control": "malformed_agent_artifact",
            "grade": _grade(project_root, malformed, malformed_workspace),
        }
    )

    for resource in ("none", "X17", "X24", "X31", "X46", "X58", "X63"):
        episode = build_reference(project_root, root / f"resource_{resource}", resource=resource)
        controls.append(
            {"control": f"resource_{resource}", "grade": _grade(project_root, *episode)}
        )

    negative_outcome, negative_provenance, negative_x24 = _negative_inputs(
        project_root, root / "negative_inputs"
    )
    negative = build_reference(
        project_root,
        root / "negative_reference",
        resource="X24",
        control_outcomes=negative_outcome,
        control_provenance=negative_provenance,
        control_resources={"X24": negative_x24},
    )
    controls.append({"control": "negative_reference", "grade": _grade(project_root, *negative)})

    continue_workspace = root / "negative_universal_continue"
    continue_submission = _copy_episode(negative[0], negative[1], continue_workspace)
    continue_final = copy.deepcopy(continue_submission["final_submission"])
    continue_final["decision"] = _decision("CONTINUE", "RESEARCH_PROBABILITY")
    continue_final["claims"][0]["status"] = "SUPPORTED"
    continue_final["claims"][0]["calculation_ids"] = [
        "C_DISCRIMINATION",
        "C_PROBABILITY_ACCURACY",
        "C_CALIBRATION",
    ]
    _replace_final(continue_submission, continue_workspace, continue_final)
    controls.append(
        {
            "control": "negative_universal_continue",
            "grade": _grade(project_root, continue_submission, continue_workspace),
        }
    )
    negative_none = build_reference(
        project_root,
        root / "negative_universal_none",
        resource="none",
        control_outcomes=negative_outcome,
        control_provenance=negative_provenance,
    )
    controls.append(
        {"control": "negative_universal_none", "grade": _grade(project_root, *negative_none)}
    )

    copied_workspace = root / "negative_copied_answer"
    copied = _copy_episode(negative[0], negative[1], copied_workspace)
    copied_final = copy.deepcopy(copied["final_submission"])
    original_final = reference["final_submission"]
    copied_final["calculations"] = copy.deepcopy(original_final["calculations"])
    _sync_output(copied_workspace, copied_final)
    _replace_final(copied, copied_workspace, copied_final)
    controls.append(
        {
            "control": "negative_copied_values",
            "grade": _grade(project_root, copied, copied_workspace),
        }
    )

    copied_table_workspace = root / "negative_copied_entire_analysis"
    copied_table = _copy_episode(negative[0], negative[1], copied_table_workspace)
    shutil.copy2(
        reference_workspace / "work/primary_analysis.csv",
        copied_table_workspace / "work/primary_analysis.csv",
    )
    copied_table_final = copy.deepcopy(copied_table["final_submission"])
    copied_table_final["calculations"] = copy.deepcopy(original_final["calculations"])
    _sync_output(copied_table_workspace, copied_table_final)
    _replace_final(copied_table, copied_table_workspace, copied_table_final)
    controls.append(
        {
            "control": "negative_copied_entire_analysis",
            "grade": _grade(project_root, copied_table, copied_table_workspace),
        }
    )

    fabricated_workspace = root / "fabricated_outcome_informed_scores"
    fabricated = _copy_episode(reference, reference_workspace, fabricated_workspace)
    fabricated_final = copy.deepcopy(fabricated["final_submission"])
    fabricated_rows = _read_csv(fabricated_workspace / "work/primary_analysis.csv")
    for row in fabricated_rows:
        row["score"] = float(row["label"])
    _write_csv(fabricated_workspace / "work/primary_analysis.csv", fabricated_rows)
    fabricated_canonical = _canonical(fabricated_rows)
    for row in fabricated_final["calculations"]:
        if row["role"] != "PRIMARY":
            continue
        normalized = {
            "BINARY_CONCORDANCE": "ROC_AUC",
            "THRESHOLD_EXPECTED_UTILITY": "NET_BENEFIT",
        }.get(row["metric"], row["metric"])
        row["reported_value"] = calculate_metric(
            fabricated_canonical,
            normalized,
            row["estimator"],
            row["parameters"],
        )
        if row.get("uncertainty"):
            low, high = cluster_bootstrap_interval(
                fabricated_canonical,
                row["estimator"],
                replicates=row["uncertainty"]["replicates"],
                seed=row["uncertainty"]["seed"],
            )
            row["uncertainty"]["lower"] = low
            row["uncertainty"]["upper"] = high
    _sync_output(fabricated_workspace, fabricated_final)
    _replace_final(fabricated, fabricated_workspace, fabricated_final)
    controls.append(
        {
            "control": "fabricated_outcome_informed_scores",
            "grade": _grade(project_root, fabricated, fabricated_workspace),
        }
    )

    belief_workspace = root / "negative_template_belief"
    belief = _copy_episode(negative[0], negative[1], belief_workspace)
    belief_final = copy.deepcopy(belief["final_submission"])
    for row in belief_final["belief_updates"]:
        row["after"] = row["before"]
    _replace_final(belief, belief_workspace, belief_final)
    controls.append(
        {
            "control": "negative_unrevised_belief",
            "grade": _grade(project_root, belief, belief_workspace),
        }
    )

    summary = {
        "schema_version": "case1-rc1.7-controls-1",
        "controls": controls,
    }
    _json(root / "control_results.json", summary)
    return summary


__all__ = ["build_reference", "run_controls"]

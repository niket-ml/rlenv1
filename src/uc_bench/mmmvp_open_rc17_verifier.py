"""Case-1 RC1.7 scientific verifier with prospective cohort binding."""

from __future__ import annotations

import copy
import csv
import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, median
from typing import Any

from sklearn.metrics import roc_auc_score

from uc_bench.mmmvp_open_calculations import CalculationResult, CanonicalRow, calculate_metric
from uc_bench.mmmvp_open_rc16_artifacts import (
    validate_analysis_table_artifact,
    verify_typed_calculations_total,
)
from uc_bench.mmmvp_open_rc16_verifier import (
    EnvironmentEvidenceError,
    _protected_workspace_hashes_total,
    _safe_file,
    _streaming_sha256,
    index_agent_artifacts_total,
)
from uc_bench.mmmvp_open_rc17_contract import (
    METRIC_ALIASES,
    QUESTION_RESOURCE,
    SCHEMA_VERSION,
    UNCERTAINTY_ALIASES,
    validate_final_submission,
    validate_followup_plan,
    validate_validation_plan,
)
from uc_bench.mmmvp_open_verifier import OpenGrade, OpenRequirement

WEIGHTS = {
    "prospective_design_and_integrity": 15,
    "saved_artifact_chain": 10,
    "committed_entity_and_dependence_analysis": 15,
    "discrimination_and_uncertainty": 10,
    "probability_and_calibration": 10,
    "threshold_utility": 8,
    "context_robustness": 8,
    "decision_relevant_followup": 10,
    "belief_revision": 7,
    "bounded_decision_and_claims": 7,
}

@dataclass(frozen=True, slots=True)
class ResourceResult:
    valid: bool
    relevant: bool
    used: bool
    observed_effect: str | None
    material: bool | None
    expected_results: dict[str, Any]
    faults: tuple[str, ...]


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"empty CSV: {path}")
    return rows


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _normalised_final(final: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(final)
    value["schema_version"] = "mmmvp-open-rc1-2"
    for calculation in value.get("calculations") or []:
        metric = calculation.get("metric")
        calculation["metric"] = METRIC_ALIASES.get(metric, metric)
        uncertainty = calculation.get("uncertainty")
        if isinstance(uncertainty, dict):
            method = uncertainty.get("method")
            uncertainty["method"] = UNCERTAINTY_ALIASES.get(method, method)
    return value


def _host_record_integrity(
    workspace: Path, submission: dict[str, Any]
) -> tuple[bool, dict[str, Any]]:
    records = workspace.parent / ".mmmvp_host_records" / workspace.name
    try:
        stored = {
            name: _load_json(records / f"{name}.json")
            for name in ("validation_plan", "followup_plan", "final_submission")
        }
        input_hashes = _load_json(records / "validation_input_hashes.json")
        binding = _load_json(records / "validation_outcome_binding.json")
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise EnvironmentEvidenceError(f"RC1.7 host records are invalid: {exc}") from exc
    expected_events = [
        "commit_validation_plan",
        "reveal_validation",
        "commit_followup_plan",
        "purchase_resource",
        "submit",
    ]
    events = submission.get("event_log") or []
    observed = [row.get("event") for row in events if row.get("event") in expected_events]
    hashes = {
        name: hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        for name, value in stored.items()
    }
    state = submission.get("state") or {}
    purchase = [row for row in events if row.get("event") == "purchase_resource"]
    valid = bool(
        observed == expected_events
        and all(submission.get(name) == stored[name] for name in stored)
        and submission.get("validation_input_hashes") == input_hashes
        and submission.get("validation_outcome_binding") == binding
        and state.get("validation_plan_hash") == hashes["validation_plan"]
        and state.get("followup_plan_hash") == hashes["followup_plan"]
        and state.get("final_submission_hash") == hashes["final_submission"]
        and len(purchase) == 1
        and purchase[0].get("resource_id") == stored["followup_plan"].get("chosen_resource")
    )
    protected = submission.get("protected_evidence_hashes") == _protected_workspace_hashes_total(
        workspace
    )
    return valid and protected, {
        "event_sequence": observed,
        "host_records_match": all(submission.get(name) == stored[name] for name in stored),
        "state_hashes_match": all(
            state.get(f"{name}_hash") == digest for name, digest in hashes.items()
        ),
        "purchase_matches": len(purchase) == 1
        and purchase[0].get("resource_id") == stored["followup_plan"].get("chosen_resource"),
        "protected_evidence_matches": protected,
    }


def _committed_cohort(
    workspace: Path, submission: dict[str, Any]
) -> tuple[set[str], dict[str, tuple[str, ...]], dict[str, Any]]:
    validation = submission["validation_plan"]
    spec = validation["prospective_specification"]
    path = _safe_file(workspace, spec["eligible_entity_manifest_path"])
    if path is None:
        return set(), {}, {"fault": "eligible_manifest_missing"}
    observed_hash = _streaming_sha256(path)
    committed_hash = spec["eligible_entity_manifest_sha256"]
    input_hash = (submission.get("validation_input_hashes") or {}).get(
        spec["eligible_entity_manifest_path"]
    )
    rows = _read_csv(path)
    sources = {
        row["entity_id"]: tuple(sorted(filter(None, row["source_record_ids"].split("|"))))
        for row in rows
    }
    included = {row["entity_id"] for row in rows if row["included"].lower() == "true"}
    return (
        included,
        sources,
        {
            "path": spec["eligible_entity_manifest_path"],
            "observed_sha256": observed_hash,
            "committed_sha256": committed_hash,
            "host_input_sha256": input_hash,
            "hashes_match": observed_hash == committed_hash == input_hash,
            "listed_entity_count": len(rows),
            "included_entity_count": len(included),
        },
    )


def _identity_provenance_valid(workspace: Path, submission: dict[str, Any]) -> bool:
    spec = submission["validation_plan"]["prospective_specification"]
    path = _safe_file(workspace, spec["identity_provenance_path"])
    if path is None:
        return False
    try:
        value = _load_json(path)
        relation = value["authoritative_relationship"]
        return bool(
            relation["prediction_source_entity_field"]
            == "data/cohort_metadata.csv:fingerprint_cluster"
            and relation["outcome_entity_field"] == "SEALED_VALIDATION_OUTCOMES:patient_key"
            and relation["relationship"] == "same_privacy_preserving_person_identifier"
            and (submission.get("validation_input_hashes") or {}).get(
                spec["identity_provenance_path"]
            )
            == _streaming_sha256(path)
        )
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return False


def _outcome_binding_valid(workspace: Path, submission: dict[str, Any]) -> bool:
    binding = submission.get("validation_outcome_binding") or {}
    path = _safe_file(workspace, binding.get("path"))
    return bool(
        binding.get("role")
        == submission["validation_plan"]["prospective_specification"].get("outcome_role")
        and path is not None
        and binding.get("sha256") == _streaming_sha256(path)
    )


def _artifact_state(
    workspace: Path,
    final: dict[str, Any],
    resource_id: str,
) -> tuple[
    dict[str, tuple[dict[str, Any], Path]],
    list[str],
    dict[str, Any],
    dict[str, CalculationResult],
    list[dict[str, Any]],
]:
    normalized = _normalised_final(final)
    artifacts, errors = index_agent_artifacts_total(workspace, normalized)
    linked: dict[str, list[str]] = {}
    for row in normalized.get("calculations") or []:
        linked.setdefault(str(row.get("source_analysis_table_id") or ""), []).append(
            str(row.get("calculation_id") or "")
        )
    tables: dict[str, Any] = {}
    validations: list[dict[str, Any]] = []
    for artifact_id, artifact in artifacts.items():
        if artifact[0].get("role") != "ANALYSIS_TABLE":
            continue
        validation, table = validate_analysis_table_artifact(
            workspace,
            artifact_id,
            artifact,
            resource_id,
            linked_calculation_ids=tuple(linked.get(artifact_id, [])),
        )
        validations.append(validation.to_dict())
        if table is not None:
            tables[artifact_id] = table
    calculations, output_validations = verify_typed_calculations_total(
        normalized, artifacts, tables
    )
    validations.extend(row.to_dict() for row in output_validations)
    return artifacts, errors, tables, calculations, validations


def _primary_checks(
    submission: dict[str, Any],
    tables: dict[str, Any],
    calculations: dict[str, CalculationResult],
    included: set[str],
) -> dict[str, bool]:
    validation = submission["validation_plan"]
    final = submission["final_submission"]
    spec = validation["prospective_specification"]
    original_by_id = {row["calculation_id"]: row for row in final.get("calculations") or []}
    criteria = {row["property"]: row for row in validation["decision_criteria"]}
    metric_for = {
        "DISCRIMINATION": spec["discrimination_metric"],
        "PROBABILITY_ACCURACY": spec["probability_metric"],
        "CALIBRATION": spec["calibration_metric"],
        "THRESHOLD_UTILITY": spec["utility_metric"],
        "CONTEXT_ROBUSTNESS": spec["context_metric"],
    }
    valid_by_property: dict[str, bool] = {}
    for prop, criterion in criteria.items():
        calculation_id = criterion["calculation_id"]
        result = calculations.get(calculation_id)
        original = original_by_id.get(calculation_id) or {}
        cohort = original.get("cohort") or {}
        table = tables.get(str(original.get("source_analysis_table_id") or ""))
        structure_ok = bool(
            table is not None
            and (
                spec["dependence_handling"] == "PERSON_LEVEL_AGGREGATION"
                and table.structure == "ENTITY_AGGREGATED"
                and table.aggregation == spec["aggregation"]
                or spec["dependence_handling"] == "SOURCE_RECORD_CLUSTERING"
                and table.structure == "SOURCE_RECORD_CLUSTERED"
                and table.aggregation == "NONE"
            )
        )
        metric_ok = original.get("metric") == metric_for[prop]
        estimator_ok = original.get("estimator") == spec["estimator"]
        cohort_ok = set(cohort.get("entity_ids") or []) == included and int(
            cohort.get("included_row_count") or -1
        ) == (
            len(included)
            if spec["dependence_handling"] == "PERSON_LEVEL_AGGREGATION"
            else sum(1 for row in table.rows if row.entity_id in included)
            if table is not None
            else -1
        )
        params = original.get("parameters") or {}
        parameter_ok = True
        if prop == "CALIBRATION":
            parameter_ok = int(params.get("bin_count") or -1) == spec["calibration_bin_count"]
        if prop == "THRESHOLD_UTILITY":
            parameter_ok = math.isclose(
                float(params.get("threshold", -1)), float(spec["utility_threshold"]), abs_tol=1e-12
            )
            if original.get("metric") == "THRESHOLD_EXPECTED_UTILITY":
                parameter_ok = (
                    parameter_ok
                    and math.isclose(
                        float(params.get("true_positive_value", -1)), 1.0, abs_tol=1e-12
                    )
                    and math.isclose(
                        float(params.get("false_positive_cost", -1)),
                        float(spec["utility_threshold"]) / (1 - float(spec["utility_threshold"])),
                        abs_tol=1e-12,
                    )
                )
        uncertainty_ok = True
        if prop == "DISCRIMINATION":
            uncertainty = original.get("uncertainty") or {}
            uncertainty_ok = bool(
                uncertainty.get("method") == spec["uncertainty_method"]
                and uncertainty.get("replicates") == spec["uncertainty_replicates"]
                and uncertainty.get("seed") == spec["uncertainty_seed"]
                and math.isclose(
                    float(uncertainty.get("level", -1)),
                    float(spec["uncertainty_level"]),
                    abs_tol=1e-12,
                )
                and result is not None
                and result.uncertainty_valid
            )
        valid_by_property[prop] = bool(
            result is not None
            and result.valid
            and structure_ok
            and metric_ok
            and estimator_ok
            and cohort_ok
            and parameter_ok
            and uncertainty_ok
        )
    return valid_by_property


def _criteria_results(
    validation: dict[str, Any],
    calculations: dict[str, CalculationResult],
    final: dict[str, Any],
) -> dict[str, bool]:
    results: dict[str, bool] = {}
    original = {row.get("calculation_id"): row for row in final.get("calculations") or []}
    for row in validation.get("decision_criteria") or []:
        calculation = calculations.get(row["calculation_id"])
        passed = False
        if (
            calculation is not None
            and calculation.valid
            and calculation.recomputed_value is not None
        ):
            value = float(calculation.recomputed_value)
            threshold = float(row["threshold"])
            passed = value >= threshold if row["comparator"] == "AT_LEAST" else value <= threshold
            if row.get("property") == "DISCRIMINATION":
                uncertainty = (original.get(row["calculation_id"]) or {}).get("uncertainty") or {}
                passed = passed and float(uncertainty.get("lower", -1)) >= 0.58
        results[row["property"]] = passed
    return results


def _binary_metrics(
    predictions: list[float], outcomes: list[int], threshold: float = 0.5
) -> dict[str, float]:
    auc = float(roc_auc_score(outcomes, predictions))
    brier = mean(
        (prediction - outcome) ** 2
        for prediction, outcome in zip(predictions, outcomes, strict=True)
    )
    tp = sum(
        prediction >= threshold and outcome == 1
        for prediction, outcome in zip(predictions, outcomes, strict=True)
    )
    fp = sum(
        prediction >= threshold and outcome == 0
        for prediction, outcome in zip(predictions, outcomes, strict=True)
    )
    net_benefit = tp / len(outcomes) - fp / len(outcomes) * threshold / (1 - threshold)
    return {"roc_auc": auc, "brier_score": brier, "net_benefit": net_benefit}


def _committed_rows_with_labels(
    workspace: Path,
    validation_plan: dict[str, Any],
    labels: dict[str, int],
) -> tuple[list[CanonicalRow], str]:
    """Rebuild the committed primary estimand with replacement labels."""

    spec = validation_plan["prospective_specification"]
    metadata = _read_csv(workspace / "data/cohort_metadata.csv")
    metadata_by_source = {row["sample_id"]: row for row in metadata}
    predictions = {
        row["sample_id"]: float(row["predicted_probability"])
        for row in _read_csv(workspace / "data/locked_predictions.csv")
    }
    manifest = _read_csv(workspace / spec["eligible_entity_manifest_path"])
    rows: list[CanonicalRow] = []
    for item in manifest:
        if item["included"].lower() != "true":
            continue
        entity = item["entity_id"]
        sources = tuple(sorted(filter(None, item["source_record_ids"].split("|"))))
        if spec["dependence_handling"] == "SOURCE_RECORD_CLUSTERING":
            for source in sources:
                rows.append(
                    CanonicalRow(
                        entity_id=entity,
                        source_record_ids=(source,),
                        prediction=predictions[source],
                        outcome=labels[entity],
                        split="VALIDATION",
                        contexts=(metadata_by_source[source]["site"],),
                    )
                )
            continue
        values = [predictions[source] for source in sources]
        aggregation = spec["aggregation"]
        if aggregation == "MEAN":
            prediction = mean(values)
        elif aggregation == "MEDIAN":
            prediction = median(values)
        else:
            prediction = predictions[sources[0]]
        rows.append(
            CanonicalRow(
                entity_id=entity,
                source_record_ids=sources,
                prediction=prediction,
                outcome=labels[entity],
                split="VALIDATION",
                contexts=tuple(
                    sorted({metadata_by_source[source]["site"] for source in sources})
                ),
            )
        )
    return rows, str(spec["estimator"])


def _resource_expected(
    workspace: Path,
    resource_id: str,
    primary_auc: float,
    *,
    calibration_bin_count: int,
    validation_plan: dict[str, Any],
) -> dict[str, Any]:
    purchased = workspace / "purchased" / resource_id
    if resource_id == "none":
        return {"new_evidence": False}
    if resource_id == "X17":
        rows = _read_csv(purchased / "canonical_person_crosswalk.csv")
        limitations = _load_json(purchased / "package_limitations.json")
        return {
            "canonical_entity_count": len({row["canonical_person_id"] for row in rows}),
            "unresolved_record_count": len(limitations.get("unresolved_fields") or []),
        }
    if resource_id == "X24":
        adjudicated = _read_csv(purchased / "adjudicated_endpoints.csv")
        original = {
            row["patient_key"]: int(row["week6_response"])
            for row in _read_csv(workspace / "revealed/validation_outcomes.csv")
        }
        labels = {row["patient_key"]: int(row["week6_response"]) for row in adjudicated}
        canonical, estimator = _committed_rows_with_labels(
            workspace, validation_plan, labels
        )
        ids = {row.entity_id for row in canonical}
        utility_threshold = float(
            validation_plan["prospective_specification"]["utility_threshold"]
        )
        result = {
            "changed_label_count": sum(labels[key] != original.get(key) for key in ids),
            "reviewer_disagreement_count": sum(
                row.get("reviewer_agreement") != "concordant" for row in adjudicated
            ),
        }
        result.update(
            {
                "roc_auc": calculate_metric(canonical, "ROC_AUC", estimator, {}),
                "binary_concordance": calculate_metric(
                    canonical, "ROC_AUC", estimator, {}
                ),
                "brier_score": calculate_metric(canonical, "BRIER_SCORE", estimator, {}),
                "log_loss": calculate_metric(canonical, "LOG_LOSS", estimator, {}),
                "net_benefit": calculate_metric(
                    canonical,
                    "NET_BENEFIT",
                    estimator,
                    {"threshold": utility_threshold},
                ),
                "threshold_expected_utility": calculate_metric(
                    canonical,
                    "NET_BENEFIT",
                    estimator,
                    {"threshold": utility_threshold},
                ),
            }
        )
        result["calibration_error"] = calculate_metric(
            canonical,
            "CALIBRATION_ERROR",
            estimator,
            {"bin_count": calibration_bin_count},
        )
        result["worst_site_roc_auc"] = calculate_metric(
            canonical,
            "WORST_SITE_ROC_AUC",
            estimator,
            {},
        )
        result["site_weighted_roc_auc"] = calculate_metric(
            canonical,
            "SITE_WEIGHTED_ROC_AUC",
            estimator,
            {},
        )
        return result
    if resource_id == "X31":
        predictions = _read_csv(purchased / "replay_predictions.csv")
        outcomes = {
            row["patient_key"]: int(row["week6_response"])
            for row in _read_csv(workspace / "revealed/validation_outcomes.csv")
        }
        result = _binary_metrics(
            [float(row["predicted_probability"]) for row in predictions],
            [outcomes[row["patient_key"]] for row in predictions],
        )
        result["primary_auc_absolute_delta"] = abs(result["roc_auc"] - primary_auc)
        return result
    if resource_id in {"X46", "X58"}:
        stem = "matched" if resource_id == "X46" else "additional"
        predictions = _read_csv(purchased / f"{stem}_predictions.csv")
        outcomes = {
            row["patient_key"]: int(row["week6_response"])
            for row in _read_csv(purchased / f"{stem}_outcomes.csv")
        }
        result = {"entity_count": len(predictions)}
        result.update(
            _binary_metrics(
                [float(row["predicted_probability"]) for row in predictions],
                [outcomes[row["patient_key"]] for row in predictions],
            )
        )
        return result
    memo = _load_json(purchased / "review_memo.json")
    return {
        "new_empirical_evidence": False,
        "recommendation_count": len(memo.get("recommendations") or []),
    }


def _resource_result(
    workspace: Path,
    submission: dict[str, Any],
    artifacts: dict[str, tuple[dict[str, Any], Path]],
    calculations: dict[str, CalculationResult],
) -> ResourceResult:
    followup = submission["followup_plan"]
    final = submission["final_submission"]
    assessment = final["resource_assessment"]
    resource = followup["chosen_resource"]
    faults: list[str] = []
    if assessment.get("resource_id") != resource or assessment.get("question_type") != followup.get(
        "decision_question_type"
    ):
        faults.append("assessment_commitment_mismatch")
    if QUESTION_RESOURCE.get(followup.get("decision_question_type")) != resource:
        faults.append("question_resource_mismatch")
    has_verified_primary = any(row.valid and row.role == "PRIMARY" for row in calculations.values())
    relevant = has_verified_primary
    summary_path = _safe_file(workspace, assessment.get("summary_artifact_path"))
    if summary_path is None:
        return ResourceResult(
            False, relevant, False, None, None, {}, tuple(faults + ["summary_missing"])
        )
    try:
        summary = _load_json(summary_path)
        manifest = _load_json(workspace / f"purchased/{resource}/resource_manifest.json")
        listed = {row["path"]: row["sha256"] for row in manifest["files"]}
        expected_sources = {
            f"purchased/{resource}/{name}": digest for name, digest in listed.items()
        }
        if (
            summary.get("schema_version") != "case1-resource-summary-1"
            or summary.get("resource_id") != resource
        ):
            faults.append("summary_contract_mismatch")
        if summary.get("source_hashes") != expected_sources:
            faults.append("summary_source_hashes_mismatch")
        for relative, digest in expected_sources.items():
            path = _safe_file(workspace, relative)
            if path is None or _streaming_sha256(path) != digest:
                faults.append("returned_source_hash_mismatch")
                break
        primary_id = next(
            row["calculation_id"]
            for row in submission["validation_plan"]["decision_criteria"]
            if row["property"] == "DISCRIMINATION"
        )
        primary = calculations.get(primary_id)
        primary_auc = (
            float(primary.recomputed_value)
            if primary and primary.recomputed_value is not None
            else math.nan
        )
        expected = _resource_expected(
            workspace,
            resource,
            primary_auc,
            calibration_bin_count=submission["validation_plan"]["prospective_specification"][
                "calibration_bin_count"
            ],
            validation_plan=submission["validation_plan"],
        )
        observed = summary.get("results") or {}
        if set(observed) != set(expected):
            faults.append("resource_result_keys_mismatch")
        else:
            for key, wanted in expected.items():
                got = observed[key]
                if isinstance(wanted, bool):
                    if got is not wanted:
                        faults.append(f"resource_result_mismatch:{key}")
                elif not isinstance(got, (int, float)) or not math.isclose(
                    float(got), float(wanted), abs_tol=0.002
                ):
                    faults.append(f"resource_result_mismatch:{key}")
        threshold = float(followup["materiality_threshold"])
        provenance = _load_json(workspace / "revealed/outcome_provenance.json")
        if resource == "none":
            effect, material = "NO_NEW_EVIDENCE", False
            relevant = relevant and not bool(provenance.get("requires_endpoint_adjudication"))
        elif resource == "X17":
            included_count = sum(
                1
                for row in _read_csv(
                    workspace
                    / submission["validation_plan"]["prospective_specification"][
                        "eligible_entity_manifest_path"
                    ]
                )
                if row["included"].lower() == "true"
            )
            material = bool(
                expected["unresolved_record_count"]
                or expected["canonical_entity_count"] != included_count
            )
            effect = "RESOLVES" if material else "INEFFECTIVE"
            relevant = relevant and material
        elif resource == "X24":
            ledger = _read_csv(workspace / "data/endpoint_source_ledger.csv")
            unresolved_before_purchase = bool(
                any("pending" in row.get("review_status", "") for row in ledger)
                or provenance.get("requires_endpoint_adjudication")
            )
            material = unresolved_before_purchase
            relevant = relevant and material
            effect = (
                "EXPOSES_BLOCKER"
                if expected["roc_auc"] <= 0.5 or expected["net_benefit"] < 0
                else "RESOLVES"
            )
        elif resource == "X31":
            material = expected["primary_auc_absolute_delta"] > threshold
            effect = "EXPOSES_BLOCKER" if material else "RESOLVES"
            relevant = relevant and material
        elif resource == "X63":
            material = bool(expected["new_empirical_evidence"])
            effect = "RESOLVES" if material else "REDUCES_UNCERTAINTY"
            relevant = relevant and material
        elif resource == "X46":
            # A matched external cohort directly answers a prospectively declared
            # transport question even when it agrees with the internal result.
            material = True
            effect = (
                "EXPOSES_BLOCKER"
                if expected["roc_auc"] <= 0.5 or expected["net_benefit"] < 0
                else "REDUCES_UNCERTAINTY"
            )
            relevant = relevant and material
        else:
            material = (
                abs(expected["roc_auc"] - primary_auc) > threshold or expected["net_benefit"] < 0
            )
            effect = "EXPOSES_BLOCKER" if material else "REDUCES_UNCERTAINTY"
            relevant = relevant and material
        if not relevant:
            faults.append("declared_question_not_material_for_returned_evidence")
        if (
            assessment.get("observed_effect") != effect
            or assessment.get("material") is not material
        ):
            faults.append("resource_effect_mismatch")
        summary_manifested = any(
            row.get("path") == assessment.get("summary_artifact_path")
            and row.get("role") == "PROVENANCE"
            for row in final.get("artifact_manifest") or []
        )
        if not summary_manifested:
            faults.append("summary_not_manifested")
        assessment_sources = set(assessment.get("source_paths") or [])
        if not set(expected_sources).issubset(assessment_sources):
            faults.append("returned_evidence_not_cited")
        calculation_ids = set(assessment.get("calculation_ids") or [])
        if not calculation_ids.issubset(calculations):
            faults.append("resource_calculation_reference_invalid")
        # X24/X58 use the same independently recomputed standardized summary
        # contract; the inherited typed-table verifier has no decoder for those
        # packages. X17/X31/X46 additionally support typed follow-up tables.
        empirical_resource = resource in {"X17", "X31", "X46"}
        if empirical_resource and not calculation_ids:
            faults.append("resource_calculations_missing")
        if any(
            not calculations[identifier].valid or calculations[identifier].role != "FOLLOWUP"
            for identifier in calculation_ids
            if identifier in calculations
        ):
            faults.append("resource_calculation_invalid")
        used = summary_manifested and set(expected_sources).issubset(assessment_sources)
        unique_faults = tuple(dict.fromkeys(faults))
        technical_faults = tuple(
            fault
            for fault in unique_faults
            if fault != "declared_question_not_material_for_returned_evidence"
        )
        return ResourceResult(
            not technical_faults,
            relevant,
            used,
            effect,
            material,
            expected,
            unique_faults,
        )
    except (KeyError, OSError, StopIteration, TypeError, ValueError, json.JSONDecodeError) as exc:
        return ResourceResult(
            False,
            relevant,
            False,
            None,
            None,
            {},
            tuple(faults + [f"resource_summary_invalid:{type(exc).__name__}"]),
        )


def _belief_valid(submission: dict[str, Any], resource: ResourceResult) -> bool:
    validation = submission["validation_plan"]
    followup = submission["followup_plan"]
    final = submission["final_submission"]
    before = {row["hypothesis_id"]: float(row["belief"]) for row in validation["hypotheses"]}
    if followup.get("beliefs_before") != before:
        return False
    updates = final.get("belief_updates") or []
    if {row.get("hypothesis_id") for row in updates} != set(before):
        return False
    if any(
        not math.isclose(float(row.get("before", -1)), before[row["hypothesis_id"]], abs_tol=1e-12)
        for row in updates
    ):
        return False
    if resource.observed_effect in {"NO_NEW_EVIDENCE", "INEFFECTIVE"}:
        return all(
            math.isclose(float(row["after"]), float(row["before"]), abs_tol=1e-12)
            for row in updates
        )
    support_ids = {
        row["hypothesis_id"]
        for row in validation["hypotheses"]
        if row.get("decision_effect_if_true") == "SUPPORTS"
    }
    limiting_ids = {
        row["hypothesis_id"]
        for row in validation["hypotheses"]
        if row.get("decision_effect_if_true") in {"WEAKENS", "INVALIDATES"}
    }
    support_delta = sum(
        float(row["after"]) - float(row["before"])
        for row in updates
        if row["hypothesis_id"] in support_ids
    )
    limiting_delta = sum(
        float(row["after"]) - float(row["before"])
        for row in updates
        if row["hypothesis_id"] in limiting_ids
    )
    if resource.observed_effect == "EXPOSES_BLOCKER":
        return support_delta < 0 and limiting_delta > 0
    return support_delta >= 0 and limiting_delta <= 0 and (support_delta > 0 or limiting_delta < 0)


def _decision_and_claims_valid(
    submission: dict[str, Any],
    criteria: dict[str, bool],
    resource: ResourceResult,
    calculations: dict[str, CalculationResult],
) -> bool:
    final = submission["final_submission"]
    decision = final["decision"]
    disposition = decision.get("disposition")
    stage = decision.get("development_stage")
    use_scope = decision.get("use_scope")
    if disposition == "CONTINUE" and (
        stage == "STOPPED"
        or use_scope not in {"RESEARCH_RANKING", "RESEARCH_PROBABILITY"}
    ):
        return False
    if disposition == "STOP" and (stage != "STOPPED" or use_scope != "NO_USE"):
        return False
    if disposition in {"PAUSE", "INSUFFICIENT_EVIDENCE"} and (
        stage == "STOPPED" or use_scope not in {"NO_USE", "RETROSPECTIVE_AUDIT"}
    ):
        return False
    supported_effects = {
        row.get("decision_effect")
        for row in final.get("findings") or []
        if row.get("status") == "SUPPORTED"
    }
    if disposition == "CONTINUE" and (
        "SUPPORTS" not in supported_effects or "INVALIDATES" in supported_effects
    ):
        return False
    if disposition in {"PAUSE", "STOP", "INSUFFICIENT_EVIDENCE"} and not (
        {"WEAKENS", "INVALIDATES"} & supported_effects
    ):
        return False
    assessment_sources = {
        path
        for row in final.get("evidence_assessments") or []
        if row.get("eligible_for_decision") is True
        for path in row.get("source_paths") or []
    }
    if not set(final["resource_assessment"].get("source_paths") or []).issubset(
        assessment_sources
    ):
        return False
    all_primary = all(criteria.values())
    if resource.observed_effect == "EXPOSES_BLOCKER" and resource.material:
        supports_continue = False
    elif submission["followup_plan"]["chosen_resource"] == "X24" and resource.expected_results.get(
        "changed_label_count", 0
    ):
        validation = submission["validation_plan"]
        thresholds = {row["property"]: row for row in validation["decision_criteria"]}
        corrected = resource.expected_results
        result_key = {
            "ROC_AUC": "roc_auc",
            "BINARY_CONCORDANCE": "binary_concordance",
            "BRIER_SCORE": "brier_score",
            "LOG_LOSS": "log_loss",
            "CALIBRATION_ERROR": "calibration_error",
            "NET_BENEFIT": "net_benefit",
            "THRESHOLD_EXPECTED_UTILITY": "threshold_expected_utility",
            "WORST_SITE_ROC_AUC": "worst_site_roc_auc",
            "SITE_WEIGHTED_ROC_AUC": "site_weighted_roc_auc",
        }

        def corrected_passes(prop: str) -> bool:
            criterion = thresholds[prop]
            value = corrected[result_key[criterion["metric"]]]
            return (
                value >= criterion["threshold"]
                if criterion["comparator"] == "AT_LEAST"
                else value <= criterion["threshold"]
            )

        supports_continue = bool(
            all(
                corrected_passes(prop)
                for prop in (
                    "DISCRIMINATION",
                    "PROBABILITY_ACCURACY",
                    "CALIBRATION",
                    "THRESHOLD_UTILITY",
                    "CONTEXT_ROBUSTNESS",
                )
            )
        )
    else:
        supports_continue = all_primary
    if supports_continue != (decision.get("disposition") == "CONTINUE"):
        return False
    if decision.get("use_scope") in {"CLINICAL_DECISION_SUPPORT", "TREATMENT_SELECTION"}:
        return False
    broad = {
        "INDEPENDENT_VALIDATION",
        "CLINICAL_UTILITY",
        "TREATMENT_EFFECT",
        "CROSS_CONTEXT_TRANSPORT",
    }
    claims = final.get("claims") or []
    status_by_scope: dict[str, set[str]] = {}
    for row in claims:
        status_by_scope.setdefault(str(row.get("scope")), set()).add(str(row.get("status")))
    if any(len(statuses) > 1 for statuses in status_by_scope.values()):
        return False
    if any(row.get("scope") in broad and row.get("status") == "SUPPORTED" for row in claims):
        return False
    supported = {row.get("scope") for row in claims if row.get("status") == "SUPPORTED"}
    if (
        decision.get("use_scope") == "RESEARCH_PROBABILITY"
        and "PROGNOSTIC_PROBABILITY" not in supported
    ):
        return False
    if decision.get("use_scope") == "RESEARCH_RANKING" and "PROGNOSTIC_RANKING" not in supported:
        return False
    original = {row.get("calculation_id"): row for row in final.get("calculations") or []}
    valid_calculation_ids = {
        identifier
        for identifier, result in calculations.items()
        if result.valid and (original.get(identifier) or {}).get("estimator") != "ROW_EMPIRICAL"
    }
    criterion_ids = {
        row["property"]: row["calculation_id"]
        for row in submission["validation_plan"]["decision_criteria"]
    }
    if decision.get("use_scope") == "RESEARCH_PROBABILITY":
        required = {
            criterion_ids["DISCRIMINATION"],
            criterion_ids["PROBABILITY_ACCURACY"],
            criterion_ids["CALIBRATION"],
        }
        probability_claims = [
            row
            for row in claims
            if row.get("status") == "SUPPORTED"
            and row.get("scope") == "PROGNOSTIC_PROBABILITY"
        ]
        if not probability_claims or not any(
            required.issubset(set(row.get("calculation_ids") or []))
            for row in probability_claims
        ):
            return False
    if decision.get("use_scope") == "RESEARCH_RANKING":
        required = {criterion_ids["DISCRIMINATION"]}
        ranking_claims = [
            row
            for row in claims
            if row.get("status") == "SUPPORTED" and row.get("scope") == "PROGNOSTIC_RANKING"
        ]
        if not ranking_claims or not any(
            required.issubset(set(row.get("calculation_ids") or [])) for row in ranking_claims
        ):
            return False
    return all(
        row.get("status") != "SUPPORTED"
        or bool(row.get("evidence_refs"))
        and bool(row.get("calculation_ids"))
        and set(row["calculation_ids"]).issubset(valid_calculation_ids)
        for row in claims
    )


def _prose_diagnostics(final: dict[str, Any]) -> list[str]:
    decision = final.get("decision") or {}
    prose = [final.get("narrative_summary") or ""]
    prose.extend(str(row) for row in decision.get("allowed_use") or [])
    prose.extend(str(row) for row in decision.get("prohibited_use") or [])
    prose.extend(str(row.get("statement") or "") for row in final.get("findings") or [])
    text = "\n".join(prose).lower()
    flags: list[str] = []
    if re.search(r"\b(clinical deployment|clinically deploy|treatment effect)\b", text):
        flags.append("possible_unsupported_scope_language")
    if decision.get("disposition") == "CONTINUE" and re.search(r"\b(stop|abandon)\b", text):
        flags.append("possible_disposition_contradiction")
    if decision.get("disposition") in {"PAUSE", "STOP", "INSUFFICIENT_EVIDENCE"} and re.search(
        r"\b(deploy|unconditional advance)\b", text
    ):
        flags.append("possible_disposition_contradiction")
    return flags


def verify_rc17_case1_submission(
    project_root: Path,
    workspace: Path,
    submission: dict[str, Any],
) -> OpenGrade:
    """Verify one Case-1 episode. Agent faults return grades; host faults raise."""

    del project_root
    workspace = workspace.resolve()
    if not isinstance(submission, dict):
        submission = {}
    validation = submission.get("validation_plan") or {}
    followup = submission.get("followup_plan") or {}
    final = submission.get("final_submission") or {}
    schema_results = (
        validate_validation_plan(validation),
        validate_followup_plan(followup),
        validate_final_submission(final),
    )
    schema_valid = all(row.valid for row in schema_results)
    if not schema_valid:
        return OpenGrade(
            complete_mission_success=False,
            partial_scientific_quality=0.0,
            reliability_score=100.0
            if (submission.get("state") or {}).get("completion_accepted")
            else 0.0,
            mission_failures=("schema_contract",),
            first_decision_critical_failure=None,
            requirements=(
                OpenRequirement(
                    "schema_contract",
                    "interface",
                    "contract",
                    False,
                    [[issue.to_dict() for issue in row.issues] for row in schema_results],
                    "disclosed RC1.7 contract",
                    "The submission cannot be interpreted.",
                    "Use the local contract validator.",
                    (),
                ),
            ),
            diagnostics={
                "verifier_version": "case1-rc1.7",
                "schema_issues": [
                    [issue.to_dict() for issue in row.issues] for row in schema_results
                ],
            },
            failure_class="contract_failure",
        )
    try:
        process_valid, process_details = _host_record_integrity(workspace, submission)
        included, committed_sources, cohort_details = _committed_cohort(workspace, submission)
        identity_valid = _identity_provenance_valid(workspace, submission)
        outcome_binding_valid = _outcome_binding_valid(workspace, submission)
        artifacts, artifact_errors, tables, calculations, artifact_validations = _artifact_state(
            workspace, final, followup["chosen_resource"]
        )
        primary = _primary_checks(submission, tables, calculations, included)
        criteria = _criteria_results(validation, calculations, final)
        resource = _resource_result(workspace, submission, artifacts, calculations)
    except EnvironmentEvidenceError:
        raise
    except (
        ArithmeticError,
        csv.Error,
        json.JSONDecodeError,
        KeyError,
        OSError,
        StopIteration,
        TypeError,
        UnicodeError,
        ValueError,
        MemoryError,
        RecursionError,
    ) as exc:
        return OpenGrade(
            complete_mission_success=False,
            partial_scientific_quality=0.0,
            reliability_score=100.0,
            mission_failures=("malformed_agent_artifact",),
            first_decision_critical_failure={
                "stage": "analysis",
                "requirement_id": "malformed_agent_artifact",
                "consequence": "Saved work cannot be independently reconstructed.",
                "remedy": "Repair the disclosed artifact contract.",
                "evidence": [],
            },
            requirements=(
                OpenRequirement(
                    "malformed_agent_artifact",
                    "analysis",
                    "mission_critical_science",
                    False,
                    type(exc).__name__,
                    "finite parseable artifacts",
                    "Saved work cannot be independently reconstructed.",
                    "Repair the disclosed artifact contract.",
                    (),
                ),
            ),
            diagnostics={
                "verifier_version": "case1-rc1.7",
                "agent_artifact_error": type(exc).__name__,
            },
            failure_class="scientific_failure",
        )

    planned_paths = {
        path
        for analysis in validation["planned_analyses"]
        for path in analysis["planned_output_paths"]
    }
    manifested_paths = {row.get("path") for row in final.get("artifact_manifest") or []}
    plan_implemented = bool(
        cohort_details.get("hashes_match")
        and identity_valid
        and outcome_binding_valid
        and planned_paths.issubset(manifested_paths)
        and included
        and set(committed_sources) >= included
    )
    valid_primary_calculations = {
        row["calculation_id"]
        for row in validation["decision_criteria"]
        if row["property"] in primary and primary[row["property"]]
    }
    primary_output_ids = {
        row.get("output_artifact_id")
        for row in final.get("calculations") or []
        if row.get("calculation_id") in valid_primary_calculations
    }
    saved_chain = bool(
        primary_output_ids
        and primary_output_ids.issubset(artifacts)
        and all(calculations[identifier].valid for identifier in valid_primary_calculations)
    )
    entity_valid = bool(
        included
        and primary
        and all(
            set((row.get("cohort") or {}).get("entity_ids") or []) == included
            for row in final.get("calculations") or []
            if row.get("role") == "PRIMARY"
        )
        and any(
            table.structure in {"ENTITY_AGGREGATED", "SOURCE_RECORD_CLUSTERED"}
            for table in tables.values()
        )
    )
    scientific_analysis_exists = all(primary.values())
    belief_valid = bool(
        scientific_analysis_exists
        and resource.valid
        and resource.relevant
        and _belief_valid(submission, resource)
    )
    decision_valid = bool(
        scientific_analysis_exists
        and _decision_and_claims_valid(submission, criteria, resource, calculations)
    )

    status = {
        "prospective_design_and_integrity": plan_implemented and process_valid,
        "saved_artifact_chain": saved_chain,
        "committed_entity_and_dependence_analysis": entity_valid,
        "discrimination_and_uncertainty": primary.get("DISCRIMINATION", False),
        "probability_and_calibration": primary.get("PROBABILITY_ACCURACY", False)
        and primary.get("CALIBRATION", False),
        "threshold_utility": primary.get("THRESHOLD_UTILITY", False),
        "context_robustness": primary.get("CONTEXT_ROBUSTNESS", False),
        "decision_relevant_followup": resource.valid and resource.relevant and resource.used,
        "belief_revision": belief_valid,
        "bounded_decision_and_claims": decision_valid,
    }
    consequences = {
        "prospective_design_and_integrity": (
            "Outcome-dependent analysis choices cannot support the development decision."
        ),
        "saved_artifact_chain": "Reported results cannot be reproduced from saved evidence.",
        "committed_entity_and_dependence_analysis": (
            "Dependent records or a post-reveal subset can distort the result."
        ),
        "discrimination_and_uncertainty": "Ranking performance and its precision are unsupported.",
        "probability_and_calibration": "Probability claims are unsupported.",
        "threshold_utility": "The action threshold may be harmful or useless.",
        "context_robustness": "A pooled result may hide site failure.",
        "decision_relevant_followup": (
            "The purchased evidence does not answer the committed question or was not used."
        ),
        "belief_revision": "Beliefs do not follow the observed evidence.",
        "bounded_decision_and_claims": "The action or claim exceeds the verified evidence.",
    }
    remedies = {
        "prospective_design_and_integrity": (
            "Bind and preserve the full pre-outcome plan and event sequence."
        ),
        "saved_artifact_chain": "Save source-linked tables and typed calculation outputs.",
        "committed_entity_and_dependence_analysis": (
            "Use exactly the committed people and dependence rule."
        ),
        "discrimination_and_uncertainty": (
            "Run a supported discrimination estimate with patient-respecting uncertainty."
        ),
        "probability_and_calibration": "Run the committed probability and calibration analyses.",
        "threshold_utility": "Evaluate the stated threshold with a supported utility measure.",
        "context_robustness": "Run the committed site/context robustness analysis.",
        "decision_relevant_followup": (
            "Choose evidence for a material question and preserve its verified summary."
        ),
        "belief_revision": "Update stable hypotheses in the evidence-supported direction.",
        "bounded_decision_and_claims": "Narrow the decision and mark broader claims unsupported.",
    }
    requirements = tuple(
        OpenRequirement(
            identifier,
            "planning"
            if identifier.startswith("prospective")
            else "analysis"
            if identifier
            in {
                "saved_artifact_chain",
                "committed_entity_and_dependence_analysis",
                "discrimination_and_uncertainty",
                "probability_and_calibration",
                "threshold_utility",
                "context_robustness",
            }
            else "followup"
            if identifier == "decision_relevant_followup"
            else "revision"
            if identifier == "belief_revision"
            else "decision",
            "mission_critical_science",
            passed,
            {
                "primary": primary,
                "criteria": criteria,
                "resource_faults": list(resource.faults),
            },
            "independently verified evidence property",
            consequences[identifier],
            remedies[identifier],
            (),
        )
        for identifier, passed in status.items()
    )
    failures = tuple(identifier for identifier, passed in status.items() if not passed)
    partial = round(sum(weight for identifier, weight in WEIGHTS.items() if status[identifier]), 6)
    first = None
    if failures:
        row = next(item for item in requirements if not item.passed)
        first = {
            "stage": row.stage,
            "requirement_id": row.requirement_id,
            "consequence": row.consequence,
            "remedy": row.remedy,
            "evidence": list(row.evidence),
        }
    complete = not failures
    failure_class = (
        "none" if complete else ("integrity_failure" if not process_valid else "scientific_failure")
    )
    return OpenGrade(
        complete_mission_success=complete,
        partial_scientific_quality=partial,
        reliability_score=100.0
        if (submission.get("state") or {}).get("completion_accepted")
        else 0.0,
        mission_failures=failures,
        first_decision_critical_failure=first,
        requirements=requirements,
        diagnostics={
            "verifier_version": "case1-rc1.7",
            "weights": WEIGHTS,
            "process": process_details,
            "cohort": cohort_details,
            "identity_provenance_valid": identity_valid,
            "outcome_binding_valid": outcome_binding_valid,
            "artifact_errors": artifact_errors,
            "artifact_validation": artifact_validations,
            "calculation_results": {key: value.to_dict() for key, value in calculations.items()},
            "primary_properties": primary,
            "criterion_results": criteria,
            "resource": {
                "valid": resource.valid,
                "relevant": resource.relevant,
                "used": resource.used,
                "observed_effect": resource.observed_effect,
                "material": resource.material,
                "expected_results": resource.expected_results,
                "faults": list(resource.faults),
            },
            "prose_scored": False,
            "prose_diagnostic_flags": _prose_diagnostics(final),
            "schema_version": SCHEMA_VERSION,
        },
        failure_class=failure_class,
    )


__all__ = ["WEIGHTS", "verify_rc17_case1_submission"]

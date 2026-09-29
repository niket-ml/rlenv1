"""Construct-valid, cohort-aware and non-cascading Case-1 RC5 verifier."""

from __future__ import annotations

import copy
import csv
import hashlib
import json
import math
from dataclasses import replace
from pathlib import Path
from typing import Any

from uc_bench.case1_pilot_v1_rc5_artifacts import (
    validate_analysis_table_artifact_rc5,
    verify_typed_calculations_rc4,
)
from uc_bench.case1_pilot_v1_rc5_cohort import (
    CommittedCohort,
    reconstruct_committed_cohort,
)
from uc_bench.case1_pilot_v1_rc5_contract import (
    PROPERTY_DEPENDENCIES,
    RESOURCE_SUMMARY_SCHEMA_VERSION,
    SCHEMA_VERSION,
    validate_final_submission,
    validate_followup_plan,
    validate_validation_plan,
)
from uc_bench.case1_pilot_v1_rc5_normalization import (
    NormalizationError,
    normalize_source_hashes,
)
from uc_bench.case1_pilot_v1_rc5_public_recompute import (
    belief_revision_errors,
    expected_resource_results,
)
from uc_bench.mmmvp_open_calculations import CalculationResult
from uc_bench.mmmvp_open_rc16_verifier import (
    EnvironmentEvidenceError,
    _protected_workspace_hashes_total,
    index_agent_artifacts_total,
)
from uc_bench.mmmvp_open_rc17_contract import QUESTION_RESOURCE
from uc_bench.mmmvp_open_rc17_verifier import (
    ResourceResult,
    _criteria_results,
    _identity_provenance_valid,
    _load_json,
    _normalised_final,
    _outcome_binding_valid,
    _primary_checks,
    _prose_diagnostics,
    _safe_file,
    _streaming_sha256,
)
from uc_bench.mmmvp_open_verifier import OpenGrade, OpenRequirement

WEIGHTS = {
    identifier: int(specification["weight"])
    for identifier, specification in PROPERTY_DEPENDENCIES.items()
}


def _load_json_without_duplicate_keys(path: Path) -> dict[str, Any]:
    """Load a scored JSON object without allowing duplicate keys to disappear."""

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"duplicate JSON key: {key}")
            value[key] = item
        return value

    result = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates)
    if not isinstance(result, dict):
        raise ValueError("JSON object required")
    return result


def _prospective_integrity(
    workspace: Path, submission: dict[str, Any]
) -> tuple[bool, dict[str, Any]]:
    records = workspace.parent / ".mmmvp_host_records" / workspace.name
    try:
        stored = {
            name: json.loads((records / f"{name}.json").read_text())
            for name in ("validation_plan", "followup_plan", "final_submission")
        }
        stored_inputs = json.loads((records / "validation_input_hashes.json").read_text())
        stored_binding = json.loads((records / "validation_outcome_binding.json").read_text())
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise EnvironmentEvidenceError(
            f"RC5 prospective host records are invalid: {type(exc).__name__}: {exc}"
        ) from exc
    events = submission.get("event_log") or []
    expected_events = [
        "commit_validation_plan",
        "reveal_validation",
        "commit_followup_plan",
        "purchase_resource",
        "submit",
    ]
    event_rows_are_objects = isinstance(events, list) and all(
        isinstance(row, dict) for row in events
    )
    observed_events = (
        [row.get("event") for row in events if row.get("event") in expected_events]
        if event_rows_are_objects
        else []
    )
    digests = {
        name: hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        for name, value in stored.items()
    }
    state = submission.get("state") or {}
    purchases = (
        [row for row in events if row.get("event") == "purchase_resource"]
        if event_rows_are_objects
        else []
    )
    details = {
        "event_sequence": observed_events,
        "event_rows_are_objects": event_rows_are_objects,
        "validation_plan_record_matches": submission.get("validation_plan")
        == stored["validation_plan"],
        "followup_plan_record_matches": submission.get("followup_plan") == stored["followup_plan"],
        "final_submission_record_matches": submission.get("final_submission")
        == stored["final_submission"],
        "validation_input_hashes_match": submission.get("validation_input_hashes") == stored_inputs,
        "outcome_binding_record_matches": submission.get("validation_outcome_binding")
        == stored_binding,
        "validation_plan_hash_matches": state.get("validation_plan_hash")
        == digests["validation_plan"],
        "followup_plan_hash_matches": state.get("followup_plan_hash") == digests["followup_plan"],
        "final_submission_hash_matches": state.get("final_submission_hash")
        == digests["final_submission"],
        "purchase_matches_commitment": len(purchases) == 1
        and purchases[0].get("resource_id") == stored["followup_plan"].get("chosen_resource"),
        "submission_accepted": bool(state.get("completion_accepted")),
        "protected_evidence_matches": submission.get("protected_evidence_hashes")
        == _protected_workspace_hashes_total(workspace),
    }
    valid = observed_events == expected_events and all(
        value for key, value in details.items() if key != "event_sequence"
    )
    return bool(valid), details


def _host_input_hashes(workspace: Path) -> dict[str, str]:
    path = (
        workspace.parent / ".mmmvp_host_records" / workspace.name / "validation_input_hashes.json"
    )
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not all(
        isinstance(key, str) and isinstance(digest, str) for key, digest in value.items()
    ):
        raise EnvironmentEvidenceError("RC5 validation input hashes are invalid")
    return value


def _artifact_state(
    workspace: Path,
    final: dict[str, Any],
    resource_id: str,
    cohort: CommittedCohort,
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
        validation, table = validate_analysis_table_artifact_rc5(
            workspace,
            artifact_id,
            artifact,
            resource_id,
            cohort,
            linked_calculation_ids=tuple(linked.get(artifact_id, [])),
        )
        validations.append(validation.to_dict())
        if table is not None:
            tables[artifact_id] = table
    calculations, output_validations = verify_typed_calculations_rc4(normalized, artifacts, tables)
    validations.extend(row.to_dict() for row in output_validations)
    return artifacts, errors, tables, calculations, validations


def _returned_source_hashes(workspace: Path, resource: str) -> tuple[dict[str, str], str]:
    manifest_relative = f"purchased/{resource}/resource_manifest.json"
    manifest_path = _safe_file(workspace, manifest_relative)
    if manifest_path is None:
        raise ValueError("resource manifest is missing")
    manifest = _load_json(manifest_path)
    rows = manifest.get("files")
    if not isinstance(rows, list):
        raise ValueError("resource manifest files must be a list")
    expected: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) < {"path", "sha256"}:
            raise ValueError("resource manifest file entry is invalid")
        relative = f"purchased/{resource}/{row['path']}"
        if relative in expected:
            raise ValueError("resource manifest contains duplicate paths")
        expected[relative] = str(row["sha256"])
    return dict(sorted(expected.items())), manifest_relative


def _resource_result_rc5(
    workspace: Path,
    submission: dict[str, Any],
    calculations: dict[str, CalculationResult],
    criteria: dict[str, bool],
    cohort: CommittedCohort,
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
    committed_primary_ids = {
        str(row.get("calculation_id") or "")
        for row in submission["validation_plan"]["decision_criteria"]
        if isinstance(row, dict)
    }
    primary_evaluable = bool(committed_primary_ids) and all(
        identifier in calculations
        and calculations[identifier].valid
        and calculations[identifier].role == "PRIMARY"
        for identifier in committed_primary_ids
    )
    relevant = any(row.valid and row.role == "PRIMARY" for row in calculations.values())
    summary_path = _safe_file(workspace, assessment.get("summary_artifact_path"))
    if summary_path is None:
        return ResourceResult(
            False, relevant, False, None, None, {}, tuple(faults + ["summary_missing"])
        )
    try:
        summary = _load_json_without_duplicate_keys(summary_path)
        expected_sources, manifest_relative = _returned_source_hashes(workspace, resource)
        if (
            summary.get("schema_version") != RESOURCE_SUMMARY_SCHEMA_VERSION
            or summary.get("resource_id") != resource
        ):
            faults.append("summary_contract_mismatch")
        try:
            observed_sources = normalize_source_hashes(summary.get("source_hashes"))
        except NormalizationError:
            observed_sources = {}
            faults.append("summary_source_hashes_invalid")
        permitted = dict(expected_sources)
        manifest_path = workspace / manifest_relative
        permitted[manifest_relative] = _streaming_sha256(manifest_path)
        if not set(expected_sources).issubset(observed_sources):
            faults.append("summary_source_hashes_missing")
        if not set(observed_sources).issubset(permitted):
            faults.append("summary_source_hashes_unexpected")
        for relative, digest in observed_sources.items():
            path = _safe_file(workspace, relative)
            if (
                path is None
                or permitted.get(relative) != digest
                or _streaming_sha256(path) != digest
            ):
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
        expected = expected_resource_results(
            workspace,
            submission["validation_plan"],
            resource,
            primary_auc=primary_auc,
        )
        observed = summary.get("results") or {}
        if not isinstance(observed, dict) or set(observed) != set(expected):
            faults.append("resource_result_keys_mismatch")
        else:
            for key, wanted in expected.items():
                got = observed[key]
                if isinstance(wanted, bool):
                    if got is not wanted:
                        faults.append(f"resource_result_mismatch:{key}")
                elif (
                    isinstance(got, bool)
                    or not isinstance(got, (int, float))
                    or not math.isclose(float(got), float(wanted), abs_tol=0.002)
                ):
                    faults.append(f"resource_result_mismatch:{key}")

        threshold = float(followup["materiality_threshold"])
        with (workspace / "data/endpoint_source_ledger.csv").open(
            encoding="utf-8", newline=""
        ) as handle:
            endpoint_rows = list(csv.DictReader(handle))
        unresolved_included = {
            str(row.get("patient_key"))
            for row in endpoint_rows
            if str(row.get("patient_key")) in cohort.included_entities
            and any(
                marker in str(row.get("review_status", "")).lower()
                for marker in ("discordant", "pending", "ambiguous")
            )
        }
        if resource == "none":
            effect, material = "NO_NEW_EVIDENCE", False
            relevant = primary_evaluable and len(criteria) == 5 and not unresolved_included
        elif resource == "X17":
            material = bool(
                expected["unresolved_record_count"]
                or expected["canonical_entity_count"] != len(cohort.included_entities)
            )
            effect = "RESOLVES" if material else "INEFFECTIVE"
            provenance = _load_json(workspace / "identity_provenance.json")
            authoritative = (
                provenance.get("authoritative_relationship", {}).get("relationship")
                == "same_privacy_preserving_person_identifier"
            )
            relevant = relevant and material and not authoritative
        elif resource == "X24":
            material = bool(unresolved_included)
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
        if (
            assessment.get("observed_effect") != effect
            or assessment.get("material") is not material
        ):
            faults.append("resource_effect_mismatch")
        calculation_ids = set(assessment.get("calculation_ids") or [])
        if not calculation_ids.issubset(calculations):
            faults.append("resource_calculation_reference_invalid")
        empirical_resource = resource in {"X17", "X31", "X46"}
        if empirical_resource and not calculation_ids:
            faults.append("resource_calculations_missing")
        if any(
            not calculations[identifier].valid or calculations[identifier].role != "FOLLOWUP"
            for identifier in calculation_ids
            if identifier in calculations
        ):
            faults.append("resource_calculation_invalid")
        summary_relative = str(assessment["summary_artifact_path"])
        linked_to_revision = all(
            summary_relative in set(row.get("evidence_refs") or [])
            for row in final.get("belief_updates") or []
        )
        if not linked_to_revision:
            faults.append("resource_summary_not_bound_to_belief_revision")
        if not relevant:
            faults.append("declared_question_not_material_for_current_bounded_decision")
        unique_faults = tuple(dict.fromkeys(faults))
        technical_faults = tuple(
            fault
            for fault in unique_faults
            if fault != "declared_question_not_material_for_current_bounded_decision"
        )
        used = bool(not technical_faults and linked_to_revision)
        return ResourceResult(
            not technical_faults,
            relevant,
            used,
            effect,
            material,
            expected,
            unique_faults,
        )
    except (
        ArithmeticError,
        KeyError,
        MemoryError,
        OSError,
        RecursionError,
        StopIteration,
        TypeError,
        UnicodeError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        return ResourceResult(
            False,
            relevant,
            False,
            None,
            None,
            {},
            tuple(faults + [f"resource_summary_invalid:{type(exc).__name__}"]),
        )


def _selected_contingency(submission: dict[str, Any]) -> dict[str, Any] | None:
    followup = submission.get("followup_plan") or {}
    final = submission.get("final_submission") or {}
    contingencies = {
        row.get("contingency_id"): row
        for row in followup.get("result_contingencies") or []
        if isinstance(row, dict) and isinstance(row.get("contingency_id"), str)
    }
    updates = final.get("belief_updates") or []
    if not updates or not all(isinstance(row, dict) for row in updates):
        return None
    selected_ids = {row.get("matched_contingency_id") for row in updates}
    if len(selected_ids) != 1:
        return None
    return contingencies.get(next(iter(selected_ids)))


def _belief_valid_rc5(submission: dict[str, Any], resource: ResourceResult) -> bool:
    return not belief_revision_errors(
        submission["validation_plan"],
        submission["followup_plan"],
        submission["final_submission"],
        resource.observed_effect,
    )


def _decision_and_claims_valid_rc5(
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
    selected = _selected_contingency(submission)
    if selected is None:
        return False
    committed_decision = selected.get("next_decision") or {}
    if any(
        decision.get(field) != committed_decision.get(field)
        for field in ("development_stage", "disposition", "use_scope")
    ):
        return False
    if disposition == "CONTINUE" and (
        stage == "STOPPED" or use_scope not in {"RESEARCH_RANKING", "RESEARCH_PROBABILITY"}
    ):
        return False
    if disposition == "STOP" and (stage != "STOPPED" or use_scope != "NO_USE"):
        return False
    if disposition in {"PAUSE", "INSUFFICIENT_EVIDENCE"} and (
        stage == "STOPPED" or use_scope in {"CLINICAL_DECISION_SUPPORT", "TREATMENT_SELECTION"}
    ):
        return False
    findings = final.get("findings") or []
    original = {row.get("calculation_id"): row for row in final.get("calculations") or []}
    valid_ids = {
        identifier
        for identifier, result in calculations.items()
        if result.valid and (original.get(identifier) or {}).get("estimator") != "ROW_EMPIRICAL"
    }
    supported_findings = [row for row in findings if row.get("status") == "SUPPORTED"]
    if any(
        not row.get("evidence_refs")
        or not row.get("calculation_ids")
        or not set(row.get("calculation_ids") or []).issubset(valid_ids)
        for row in supported_findings
    ):
        return False
    supported_effects = {row.get("decision_effect") for row in supported_findings}
    if disposition == "CONTINUE" and (
        "SUPPORTS" not in supported_effects or "INVALIDATES" in supported_effects
    ):
        return False
    if disposition in {"PAUSE", "STOP", "INSUFFICIENT_EVIDENCE"} and not (
        {"WEAKENS", "INVALIDATES"} & supported_effects
    ):
        return False
    all_primary = all(criteria.values())
    if resource.observed_effect == "EXPOSES_BLOCKER" and resource.material:
        supports_continue = False
    elif submission["followup_plan"]["chosen_resource"] == "X24" and resource.expected_results.get(
        "changed_label_count", 0
    ):
        thresholds = {
            row["property"]: row for row in submission["validation_plan"]["decision_criteria"]
        }
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

        supports_continue = all(
            corrected_passes(prop)
            for prop in (
                "DISCRIMINATION",
                "PROBABILITY_ACCURACY",
                "CALIBRATION",
                "THRESHOLD_UTILITY",
                "CONTEXT_ROBUSTNESS",
            )
        )
    else:
        supports_continue = all_primary
    if bool(supports_continue) != (disposition == "CONTINUE"):
        return False
    if use_scope in {"CLINICAL_DECISION_SUPPORT", "TREATMENT_SELECTION"}:
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
    if use_scope == "RESEARCH_PROBABILITY" and "PROGNOSTIC_PROBABILITY" not in supported:
        return False
    if use_scope == "RESEARCH_RANKING" and "PROGNOSTIC_RANKING" not in supported:
        return False
    criterion_ids = {
        row["property"]: row["calculation_id"]
        for row in submission["validation_plan"]["decision_criteria"]
    }
    if use_scope == "RESEARCH_PROBABILITY":
        required = {
            criterion_ids["DISCRIMINATION"],
            criterion_ids["PROBABILITY_ACCURACY"],
            criterion_ids["CALIBRATION"],
        }
        candidates = [
            row
            for row in claims
            if row.get("status") == "SUPPORTED" and row.get("scope") == "PROGNOSTIC_PROBABILITY"
        ]
        if not any(required.issubset(set(row.get("calculation_ids") or [])) for row in candidates):
            return False
    if use_scope == "RESEARCH_RANKING":
        required = {criterion_ids["DISCRIMINATION"]}
        candidates = [
            row
            for row in claims
            if row.get("status") == "SUPPORTED" and row.get("scope") == "PROGNOSTIC_RANKING"
        ]
        if not any(required.issubset(set(row.get("calculation_ids") or [])) for row in candidates):
            return False
    return all(
        row.get("status") != "SUPPORTED"
        or bool(row.get("evidence_refs"))
        and bool(row.get("calculation_ids"))
        and set(row["calculation_ids"]).issubset(valid_ids)
        for row in claims
    )


def _entity_dependence_valid(
    submission: dict[str, Any], tables: dict[str, Any], cohort: CommittedCohort
) -> bool:
    validation = submission["validation_plan"]
    final = submission["final_submission"]
    spec = validation["prospective_specification"]
    included = set(cohort.included_entities)
    primary_rows = [row for row in final.get("calculations") or [] if row.get("role") == "PRIMARY"]
    if not cohort.valid or not included or not primary_rows:
        return False
    for row in primary_rows:
        table = tables.get(str(row.get("source_analysis_table_id") or ""))
        declared = set((row.get("cohort") or {}).get("entity_ids") or [])
        table_entities = {item.entity_id for item in table.rows} if table is not None else set()
        if table is None or declared not in (set(), included) or table_entities != included:
            return False
        expected_rows = (
            len(included)
            if spec["dependence_handling"] == "PERSON_LEVEL_AGGREGATION"
            else len(table.rows)
        )
        if (row.get("cohort") or {}).get("included_row_count") != expected_rows:
            return False
        if spec["dependence_handling"] == "PERSON_LEVEL_AGGREGATION":
            if table.structure != "ENTITY_AGGREGATED" or table.aggregation != spec["aggregation"]:
                return False
        elif table.structure != "SOURCE_RECORD_CLUSTERED" or table.aggregation != "NONE":
            return False
    return True


def _saved_chain_valid(
    validation: dict[str, Any],
    final: dict[str, Any],
    artifacts: dict[str, tuple[dict[str, Any], Path]],
    validations: list[dict[str, Any]],
) -> bool:
    planned = {
        path
        for analysis in validation.get("planned_analyses") or []
        for path in analysis.get("planned_output_paths") or []
    }
    manifested = {
        str(row.get("path"))
        for row in final.get("artifact_manifest") or []
        if isinstance(row, dict)
    }
    valid_paths = {
        str(manifest.get("path"))
        for manifest, _path in artifacts.values()
        if isinstance(manifest.get("path"), str)
    }
    decision_calculation_ids = {
        str(row.get("calculation_id") or "")
        for row in validation.get("decision_criteria") or []
        if isinstance(row, dict)
    }
    assessment = final.get("resource_assessment") or {}
    if isinstance(assessment, dict):
        decision_calculation_ids.update(
            str(identifier) for identifier in assessment.get("calculation_ids") or []
        )
    for collection in (final.get("claims") or [], final.get("findings") or []):
        for row in collection:
            if isinstance(row, dict) and row.get("status") == "SUPPORTED":
                decision_calculation_ids.update(
                    str(identifier) for identifier in row.get("calculation_ids") or []
                )
    calculations_by_id = {
        str(row.get("calculation_id") or ""): row
        for row in final.get("calculations") or []
        if isinstance(row, dict)
    }
    decision_rows = [
        calculations_by_id[identifier]
        for identifier in decision_calculation_ids
        if identifier in calculations_by_id
    ]
    decision_ids = {
        str(row.get(key) or "")
        for row in decision_rows
        for key in ("source_analysis_table_id", "output_artifact_id")
    }
    decision_ids.discard("")
    validation_by_id: dict[str, list[bool]] = {}
    for row in validations:
        validation_by_id.setdefault(str(row.get("artifact_id") or ""), []).append(
            bool(row.get("valid"))
        )
    return bool(
        planned.issubset(manifested)
        and planned.issubset(valid_paths)
        and decision_calculation_ids.issubset(calculations_by_id)
        and decision_ids
        and decision_ids.issubset(artifacts)
        and all(validation_by_id.get(identifier) for identifier in decision_ids)
        # A calculation-output artifact may contain additional, explicitly
        # optional calculations. At least one independently valid validation
        # must establish each decision-linked artifact; an uncited optional
        # calculation sharing that file cannot invalidate the decision chain.
        and all(any(validation_by_id[identifier]) for identifier in decision_ids)
    )


def _requirement(identifier: str, passed: bool, observed: Any) -> OpenRequirement:
    metadata = {
        "prospective_design_and_integrity": (
            "planning",
            "Outcome-dependent choices may bias the decision.",
            "Preserve the complete pre-outcome commitment and hashes.",
        ),
        "saved_artifact_chain": (
            "analysis",
            "One or more decision-linked results cannot be replayed.",
            "Repair only the missing or malformed source-linked artifact.",
        ),
        "committed_entity_and_dependence_analysis": (
            "analysis",
            "The patient unit or dependence structure is unsupported.",
            "Reconstruct exactly the committed people with a supported dependence rule.",
        ),
        "discrimination_and_uncertainty": (
            "analysis",
            "Ranking performance or its precision is unsupported.",
            "Recompute discrimination with patient-respecting uncertainty.",
        ),
        "probability_and_calibration": (
            "analysis",
            "Probability accuracy or calibration is unsupported.",
            "Recompute the failed probability or calibration component.",
        ),
        "threshold_utility": (
            "analysis",
            "Decision utility at the intended threshold is unsupported.",
            "Recompute utility at the committed threshold.",
        ),
        "context_robustness": (
            "analysis",
            "A pooled estimate may conceal site failure.",
            "Recompute the committed context analysis.",
        ),
        "decision_relevant_followup": (
            "followup",
            "The resource action did not answer the committed material question.",
            "Link and use evidence for the actual unresolved question.",
        ),
        "belief_revision": (
            "revision",
            "Numeric beliefs do not follow the observed evidence.",
            "Revise stable hypotheses in the verified evidence direction.",
        ),
        "bounded_decision_and_claims": (
            "decision",
            "The final action or claim exceeds established evidence.",
            "Narrow the action and claims to verified evidence.",
        ),
    }
    stage, consequence, remedy = metadata[identifier]
    return OpenRequirement(
        identifier,
        stage,
        "mission_critical_science",
        passed,
        observed,
        PROPERTY_DEPENDENCIES[identifier]["authoritative_evidence"],
        consequence,
        remedy,
        (),
    )


def verify_case1_rc5_submission(
    project_root: Path, workspace: Path, submission: dict[str, Any]
) -> OpenGrade:
    del project_root
    workspace = workspace.resolve()
    submission = submission if isinstance(submission, dict) else {}
    validation = submission.get("validation_plan") or {}
    followup = submission.get("followup_plan") or {}
    final = submission.get("final_submission") or {}
    schema_results = (
        validate_validation_plan(validation),
        validate_followup_plan(followup),
        validate_final_submission(final),
    )
    if not all(row.valid for row in schema_results):
        return OpenGrade(
            False,
            0.0,
            100.0 if (submission.get("state") or {}).get("completion_accepted") else 0.0,
            ("schema_contract",),
            None,
            (
                OpenRequirement(
                    "schema_contract",
                    "interface",
                    "contract",
                    False,
                    [[issue.to_dict() for issue in row.issues] for row in schema_results],
                    "public submission contract",
                    "The submission cannot be interpreted.",
                    "Use the visible local validators.",
                    (),
                ),
            ),
            {
                "verifier_version": "case1-rc5",
                "schema_issues": [
                    [issue.to_dict() for issue in row.issues] for row in schema_results
                ],
                "prose_scored": False,
            },
            "contract_failure",
        )

    try:
        process_valid, process_details = _prospective_integrity(workspace, submission)
        cohort = reconstruct_committed_cohort(
            workspace, validation, host_input_hashes=_host_input_hashes(workspace)
        )
        identity_valid = _identity_provenance_valid(workspace, submission)
        outcome_valid = _outcome_binding_valid(workspace, submission)
    except EnvironmentEvidenceError:
        raise
    except (
        ArithmeticError,
        json.JSONDecodeError,
        KeyError,
        OSError,
        TypeError,
        ValueError,
        UnicodeError,
        MemoryError,
        RecursionError,
    ) as exc:
        process_valid = False
        process_details = {"prospective_agent_artifact_error": type(exc).__name__}
        cohort = CommittedCohort("", "", "", None, (), ("cohort_reconstruction_failed",))
        identity_valid = outcome_valid = False

    try:
        artifacts, artifact_errors, tables, calculations, artifact_validations = _artifact_state(
            workspace, final, followup["chosen_resource"], cohort
        )
        normalized_submission = copy.deepcopy(submission)
        for row in normalized_submission["final_submission"].get("calculations") or []:
            if row.get("role") == "PRIMARY" and not (row.get("cohort") or {}).get("entity_ids"):
                row.setdefault("cohort", {})["entity_ids"] = sorted(cohort.included_entities)
        primary = _primary_checks(
            normalized_submission, tables, calculations, set(cohort.included_entities)
        )
        discrimination_id = next(
            row["calculation_id"]
            for row in validation["decision_criteria"]
            if row["property"] == "DISCRIMINATION"
        )
        discrimination_result = calculations.get(discrimination_id)
        point_calculations = dict(calculations)
        point_submission = copy.deepcopy(normalized_submission)
        if discrimination_result is not None and set(discrimination_result.faults) <= {
            "uncertainty_mismatch"
        }:
            point_calculations[discrimination_id] = replace(
                discrimination_result, valid=True, uncertainty_valid=True, faults=()
            )
            specification = validation["prospective_specification"]
            for row in point_submission["final_submission"].get("calculations") or []:
                if row.get("calculation_id") == discrimination_id:
                    row["uncertainty"] = {
                        "method": specification["uncertainty_method"],
                        "replicates": specification["uncertainty_replicates"],
                        "seed": specification["uncertainty_seed"],
                        "level": specification["uncertainty_level"],
                    }
        point_primary = _primary_checks(
            point_submission,
            tables,
            point_calculations,
            set(cohort.included_entities),
        )
        discrimination_point_valid = point_primary.get("DISCRIMINATION", False)
        original_discrimination = next(
            row
            for row in final.get("calculations") or []
            if row.get("calculation_id") == discrimination_id
        )
        discrimination_uncertainty_valid = bool(
            discrimination_point_valid
            and discrimination_result is not None
            and isinstance(original_discrimination.get("uncertainty"), dict)
            and discrimination_result.uncertainty_valid
        )
        criteria = _criteria_results(validation, calculations, final)
        resource = _resource_result_rc5(workspace, submission, calculations, criteria, cohort)
    except (
        ArithmeticError,
        json.JSONDecodeError,
        KeyError,
        OSError,
        StopIteration,
        TypeError,
        ValueError,
        UnicodeError,
        MemoryError,
        RecursionError,
    ) as exc:
        process_details = {
            **process_details,
            "downstream_agent_artifact_error": type(exc).__name__,
        }
        artifacts, artifact_errors, tables, calculations, artifact_validations = (
            {},
            [f"malformed_agent_artifact:{type(exc).__name__}"],
            {},
            {},
            [],
        )
        primary = {
            "DISCRIMINATION": False,
            "PROBABILITY_ACCURACY": False,
            "CALIBRATION": False,
            "THRESHOLD_UTILITY": False,
            "CONTEXT_ROBUSTNESS": False,
        }
        discrimination_point_valid = discrimination_uncertainty_valid = False
        criteria = dict(primary)
        resource = None

    prospective = bool(
        process_valid
        and cohort.valid
        and cohort.details()["hashes_match"]
        and identity_valid
        and outcome_valid
        and cohort.included_entities
    )
    saved_chain = _saved_chain_valid(validation, final, artifacts, artifact_validations)
    entity = _entity_dependence_valid(submission, tables, cohort)
    followup_valid = bool(resource and resource.valid and resource.relevant and resource.used)
    belief = bool(resource and resource.observed_effect and _belief_valid_rc5(submission, resource))
    decision = bool(
        resource
        and resource.valid
        and resource.relevant
        and resource.used
        and _decision_and_claims_valid_rc5(submission, criteria, resource, calculations)
    )
    status = {
        "prospective_design_and_integrity": prospective,
        "saved_artifact_chain": saved_chain,
        "committed_entity_and_dependence_analysis": entity,
        "discrimination_and_uncertainty": (
            discrimination_point_valid and discrimination_uncertainty_valid
        ),
        "probability_and_calibration": primary.get("PROBABILITY_ACCURACY", False)
        and primary.get("CALIBRATION", False),
        "threshold_utility": primary.get("THRESHOLD_UTILITY", False),
        "context_robustness": primary.get("CONTEXT_ROBUSTNESS", False),
        "decision_relevant_followup": followup_valid,
        "belief_revision": belief,
        "bounded_decision_and_claims": decision,
    }
    observed = {
        "prospective_design_and_integrity": {
            "process": process_details,
            "cohort": cohort.details(),
            "identity_provenance_valid": identity_valid,
            "outcome_binding_valid": outcome_valid,
        },
        "saved_artifact_chain": {
            "artifact_errors": artifact_errors,
            "artifact_validation": artifact_validations,
            "unlinked_optional_artifact_errors_are_diagnostic_only": True,
        },
        "committed_entity_and_dependence_analysis": {
            "included_entity_count": len(cohort.included_entities),
            "verified_table_ids": sorted(tables),
        },
        "discrimination_and_uncertainty": {
            "discrimination_point_estimate": discrimination_point_valid,
            "uncertainty": discrimination_uncertainty_valid,
        },
        "probability_and_calibration": {
            "probability_accuracy": primary.get("PROBABILITY_ACCURACY", False),
            "calibration": primary.get("CALIBRATION", False),
        },
        "threshold_utility": primary.get("THRESHOLD_UTILITY", False),
        "context_robustness": primary.get("CONTEXT_ROBUSTNESS", False),
        "decision_relevant_followup": None
        if resource is None
        else {
            "valid": resource.valid,
            "relevant": resource.relevant,
            "used": resource.used,
            "faults": list(resource.faults),
        },
        "belief_revision": belief,
        "bounded_decision_and_claims": decision,
    }
    requirements = tuple(
        _requirement(identifier, bool(status[identifier]), observed[identifier])
        for identifier in WEIGHTS
    )
    failures = tuple(identifier for identifier in WEIGHTS if not status[identifier])
    first = None
    if failures:
        row = next(item for item in requirements if item.requirement_id == failures[0])
        first = {
            "stage": row.stage,
            "requirement_id": row.requirement_id,
            "consequence": row.consequence,
            "remedy": row.remedy,
            "evidence": list(row.evidence),
        }
    property_points = {key: float(WEIGHTS[key]) if status[key] else 0.0 for key in WEIGHTS}
    property_points["discrimination_and_uncertainty"] = 5.0 * float(
        discrimination_point_valid
    ) + 5.0 * float(discrimination_uncertainty_valid)
    property_points["probability_and_calibration"] = 5.0 * float(
        primary.get("PROBABILITY_ACCURACY", False)
    ) + 5.0 * float(primary.get("CALIBRATION", False))
    shared_root_causes: list[dict[str, Any]] = []
    if not cohort.valid:
        shared_root_causes.append(
            {
                "root": "committed_cohort_invalid",
                "faults": list(cohort.faults),
                "downstream_invalidated": [
                    name
                    for name in (
                        "committed_entity_and_dependence_analysis",
                        "discrimination_and_uncertainty",
                        "probability_and_calibration",
                        "threshold_utility",
                        "context_robustness",
                        "bounded_decision_and_claims",
                    )
                    if not status[name]
                ],
            }
        )
    complete = not failures
    return OpenGrade(
        complete,
        round(sum(property_points.values()), 6),
        100.0 if (submission.get("state") or {}).get("completion_accepted") else 0.0,
        failures,
        first,
        requirements,
        {
            "verifier_version": "case1-rc5",
            "weights": WEIGHTS,
            "property_points": property_points,
            "property_dependencies": PROPERTY_DEPENDENCIES,
            "process": process_details,
            "cohort": cohort.details(),
            "artifact_errors": artifact_errors,
            "artifact_validation": artifact_validations,
            "calculation_results": {key: value.to_dict() for key, value in calculations.items()},
            "primary_properties": primary,
            "criterion_results": criteria,
            "resource": None
            if resource is None
            else {
                "valid": resource.valid,
                "relevant": resource.relevant,
                "used": resource.used,
                "observed_effect": resource.observed_effect,
                "material": resource.material,
                "expected_results": resource.expected_results,
                "faults": list(resource.faults),
            },
            "shared_root_causes": shared_root_causes,
            "prose_scored": False,
            "prose_diagnostic_flags": _prose_diagnostics(final),
            "schema_version": SCHEMA_VERSION,
        },
        "none"
        if complete
        else (
            "integrity_failure" if not process_valid or not cohort.valid else "scientific_failure"
        ),
    )


__all__ = ["WEIGHTS", "verify_case1_rc5_submission"]

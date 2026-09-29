"""Property-local RC4 verifier for the fixed Case-1 scientific design."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from uc_bench.case1_pilot_v1_rc4_artifacts import (
    validate_analysis_table_artifact_rc4,
    verify_typed_calculations_rc4,
)
from uc_bench.case1_pilot_v1_rc4_contract import (
    PROPERTY_DEPENDENCIES,
    SCHEMA_VERSION,
    validate_final_submission,
    validate_followup_plan,
    validate_validation_plan,
)
from uc_bench.mmmvp_open_rc16_verifier import (
    EnvironmentEvidenceError,
    _protected_workspace_hashes_total,
    index_agent_artifacts_total,
)
from uc_bench.mmmvp_open_rc17_verifier import (
    ResourceResult,
    _belief_valid,
    _committed_cohort,
    _criteria_results,
    _decision_and_claims_valid,
    _identity_provenance_valid,
    _normalised_final,
    _outcome_binding_valid,
    _primary_checks,
    _prose_diagnostics,
    _resource_result,
)
from uc_bench.mmmvp_open_verifier import OpenGrade, OpenRequirement

WEIGHTS = {
    identifier: int(specification["weight"])
    for identifier, specification in PROPERTY_DEPENDENCIES.items()
}


def _property_local_resource_result(
    workspace: Path,
    submission: dict[str, Any],
    artifacts: dict[str, tuple[dict[str, Any], Path]],
    calculations: dict[str, Any],
    criteria: dict[str, bool],
) -> ResourceResult:
    """Remove only the inherited blanket primary-calculation dependency.

    Some evidence packages answer identity, endpoint, or transport questions
    directly. Comparison/no-purchase choices still retain the primary-result
    prerequisites needed to interpret them.
    """

    result = _resource_result(workspace, submission, artifacts, calculations)
    if result.relevant or not result.valid or not result.used:
        return result
    resource = submission["followup_plan"]["chosen_resource"]
    independently_resolving = resource in {"X17", "X24", "X46"}
    if resource == "none":
        independently_resolving = all(criteria.values())
    if not independently_resolving or (not result.material and resource != "none"):
        return result
    faults = tuple(
        fault
        for fault in result.faults
        if fault != "declared_question_not_material_for_returned_evidence"
    )
    return replace(result, relevant=True, faults=faults)


def _prospective_integrity(
    workspace: Path, submission: dict[str, Any]
) -> tuple[bool, dict[str, Any]]:
    """Verify only the decision-time commitment chain needed by P1."""

    records = workspace.parent / ".mmmvp_host_records" / workspace.name
    try:
        stored_plan = json.loads((records / "validation_plan.json").read_text())
        stored_inputs = json.loads((records / "validation_input_hashes.json").read_text())
        stored_binding = json.loads(
            (records / "validation_outcome_binding.json").read_text()
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise EnvironmentEvidenceError(
            f"RC4 prospective host records are invalid: {type(exc).__name__}: {exc}"
        ) from exc
    events = submission.get("event_log") or []
    prospective_events = [
        row.get("event")
        for row in events
        if row.get("event") in {"commit_validation_plan", "reveal_validation"}
    ]
    digest = hashlib.sha256(
        json.dumps(stored_plan, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    state = submission.get("state") or {}
    protected = submission.get("protected_evidence_hashes") == (
        _protected_workspace_hashes_total(workspace)
    )
    details = {
        "prospective_event_sequence": prospective_events,
        "validation_plan_record_matches": submission.get("validation_plan") == stored_plan,
        "validation_input_hashes_match": submission.get("validation_input_hashes")
        == stored_inputs,
        "outcome_binding_record_matches": submission.get("validation_outcome_binding")
        == stored_binding,
        "validation_plan_hash_matches": state.get("validation_plan_hash") == digest,
        "protected_evidence_matches": protected,
    }
    return bool(
        prospective_events == ["commit_validation_plan", "reveal_validation"]
        and all(value for key, value in details.items() if key != "prospective_event_sequence")
    ), details


def _artifact_state(
    workspace: Path,
    final: dict[str, Any],
    resource_id: str,
) -> tuple[
    dict[str, tuple[dict[str, Any], Path]],
    list[str],
    dict[str, Any],
    dict[str, Any],
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
        validation, table = validate_analysis_table_artifact_rc4(
            workspace,
            artifact_id,
            artifact,
            resource_id,
            linked_calculation_ids=tuple(linked.get(artifact_id, [])),
        )
        validations.append(validation.to_dict())
        if table is not None:
            tables[artifact_id] = table
    calculations, output_validations = verify_typed_calculations_rc4(
        normalized, artifacts, tables
    )
    validations.extend(row.to_dict() for row in output_validations)
    return artifacts, errors, tables, calculations, validations


def _entity_dependence_valid(
    submission: dict[str, Any], tables: dict[str, Any], included: set[str]
) -> bool:
    validation = submission["validation_plan"]
    final = submission["final_submission"]
    spec = validation["prospective_specification"]
    primary_rows = [row for row in final.get("calculations") or [] if row.get("role") == "PRIMARY"]
    if not included or not primary_rows:
        return False
    for row in primary_rows:
        table = tables.get(str(row.get("source_analysis_table_id") or ""))
        cohort = row.get("cohort") or {}
        declared_entities = set(cohort.get("entity_ids") or [])
        table_entities = {item.entity_id for item in table.rows} if table is not None else set()
        if (
            table is None
            or frozenset(declared_entities) not in {frozenset(), frozenset(included)}
            or table_entities != included
        ):
            return False
        expected_rows = (
            len(included)
            if spec["dependence_handling"] == "PERSON_LEVEL_AGGREGATION"
            else sum(1 for item in table.rows if item.entity_id in included)
        )
        if cohort.get("included_row_count") != expected_rows:
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
    artifact_errors: list[str],
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
    decision_ids = {
        str(row.get(key) or "")
        for row in final.get("calculations") or []
        if row.get("role") in {"PRIMARY", "FOLLOWUP"}
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
        and decision_ids
        and decision_ids.issubset(artifacts)
        and all(validation_by_id.get(identifier) for identifier in decision_ids)
        and all(all(validation_by_id[identifier]) for identifier in decision_ids)
    )


def _requirement(
    identifier: str,
    passed: bool,
    observed: Any,
    consequence: str,
    remedy: str,
) -> OpenRequirement:
    stages = {
        "prospective_design_and_integrity": "planning",
        "saved_artifact_chain": "analysis",
        "committed_entity_and_dependence_analysis": "analysis",
        "discrimination_and_uncertainty": "analysis",
        "probability_and_calibration": "analysis",
        "threshold_utility": "analysis",
        "context_robustness": "analysis",
        "decision_relevant_followup": "followup",
        "belief_revision": "revision",
        "bounded_decision_and_claims": "decision",
    }
    return OpenRequirement(
        identifier,
        stages[identifier],
        "mission_critical_science",
        passed,
        observed,
        PROPERTY_DEPENDENCIES[identifier]["authoritative_evidence"],
        consequence,
        remedy,
        (),
    )


def verify_case1_rc4_submission(
    project_root: Path,
    workspace: Path,
    submission: dict[str, Any],
) -> OpenGrade:
    """Independently verify each property from its narrowest evidence chain."""

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
    if not all(row.valid for row in schema_results):
        return OpenGrade(
            complete_mission_success=False,
            partial_scientific_quality=0.0,
            reliability_score=(
                100.0 if (submission.get("state") or {}).get("completion_accepted") else 0.0
            ),
            mission_failures=("schema_contract",),
            first_decision_critical_failure=None,
            requirements=(
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
            diagnostics={
                "verifier_version": "case1-rc4",
                "schema_issues": [
                    [issue.to_dict() for issue in row.issues] for row in schema_results
                ],
                "prose_scored": False,
            },
            failure_class="contract_failure",
        )
    # Host commitments and prospective cohort evidence are evaluated before
    # agent-authored post-reveal artifacts. A malformed downstream artifact may
    # therefore never erase an independently valid P1 commitment.
    try:
        process_valid, process_details = _prospective_integrity(workspace, submission)
        included, committed_sources, cohort_details = _committed_cohort(workspace, submission)
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
        included, committed_sources, cohort_details = set(), {}, {}
        identity_valid = outcome_valid = False

    try:
        artifacts, artifact_errors, tables, calculations, artifact_validations = _artifact_state(
            workspace, final, followup["chosen_resource"]
        )
        normalized_submission = copy.deepcopy(submission)
        for row in normalized_submission["final_submission"].get("calculations") or []:
            if row.get("role") == "PRIMARY" and not (row.get("cohort") or {}).get(
                "entity_ids"
            ):
                row.setdefault("cohort", {})["entity_ids"] = sorted(included)
        primary = _primary_checks(normalized_submission, tables, calculations, included)
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
                discrimination_result,
                valid=True,
                uncertainty_valid=True,
                faults=(),
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
            point_submission, tables, point_calculations, included
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
        resource = _property_local_resource_result(
            workspace, submission, artifacts, calculations, criteria
        )
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
        # Malformed post-reveal agent artifacts fail only the properties that
        # require those artifacts. Prospective host commitments above survive.
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
        discrimination_point_valid = False
        discrimination_uncertainty_valid = False
        criteria = dict(primary)
        resource = None

    prospective = bool(
        process_valid
        and cohort_details.get("hashes_match")
        and identity_valid
        and outcome_valid
        and included
        and set(committed_sources) >= included
    )
    saved_chain = _saved_chain_valid(
        validation, final, artifacts, artifact_errors, artifact_validations
    )
    entity = _entity_dependence_valid(submission, tables, included)
    followup_valid = bool(resource and resource.valid and resource.relevant and resource.used)
    belief = bool(resource and resource.observed_effect and _belief_valid(submission, resource))
    decision = bool(
        resource
        and resource.valid
        and resource.relevant
        and _decision_and_claims_valid(submission, criteria, resource, calculations)
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
    consequences = {
        "prospective_design_and_integrity": "Outcome-dependent choices may bias the decision.",
        "saved_artifact_chain": "One or more decision-linked results cannot be replayed.",
        "committed_entity_and_dependence_analysis": (
            "The patient unit or dependence structure is unsupported."
        ),
        "discrimination_and_uncertainty": "Ranking performance or its precision is unsupported.",
        "probability_and_calibration": "Probability accuracy or calibration is unsupported.",
        "threshold_utility": "Decision utility at the intended threshold is unsupported.",
        "context_robustness": "A pooled estimate may conceal site failure.",
        "decision_relevant_followup": (
            "The resource action did not resolve the committed material question."
        ),
        "belief_revision": "Numeric beliefs do not follow the observed evidence.",
        "bounded_decision_and_claims": "The final action or claim exceeds established evidence.",
    }
    remedies = {
        "prospective_design_and_integrity": (
            "Preserve the complete pre-outcome commitment and hashes."
        ),
        "saved_artifact_chain": "Repair only the missing or malformed source-linked artifact.",
        "committed_entity_and_dependence_analysis": (
            "Reconstruct the committed people with a valid dependence rule."
        ),
        "discrimination_and_uncertainty": (
            "Recompute discrimination with patient-respecting uncertainty."
        ),
        "probability_and_calibration": "Recompute the failed probability or calibration component.",
        "threshold_utility": "Recompute utility at the committed threshold.",
        "context_robustness": "Recompute the committed context analysis.",
        "decision_relevant_followup": "Select and use evidence for the actual unresolved question.",
        "belief_revision": "Revise stable hypotheses in the verified evidence direction.",
        "bounded_decision_and_claims": "Narrow the action and claims to verified evidence.",
    }
    observed = {
        "prospective_design_and_integrity": {
            "process": process_details,
            "cohort": cohort_details,
            "identity_provenance_valid": identity_valid,
            "outcome_binding_valid": outcome_valid,
        },
        "saved_artifact_chain": {
            "artifact_errors": artifact_errors,
            "unlinked_optional_artifact_errors_are_diagnostic_only": True,
            "artifact_validation": artifact_validations,
        },
        "committed_entity_and_dependence_analysis": {
            "included_entity_count": len(included),
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
        "decision_relevant_followup": (
            None
            if resource is None
            else {
                "valid": resource.valid,
                "relevant": resource.relevant,
                "used": resource.used,
                "faults": list(resource.faults),
            }
        ),
        "belief_revision": belief,
        "bounded_decision_and_claims": decision,
    }
    requirements = tuple(
        _requirement(
            identifier,
            bool(status[identifier]),
            observed[identifier],
            consequences[identifier],
            remedies[identifier],
        )
        for identifier in WEIGHTS
    )
    failures = tuple(identifier for identifier in WEIGHTS if not status[identifier])
    first = None
    if failures:
        identifier = failures[0]
        row = next(item for item in requirements if item.requirement_id == identifier)
        first = {
            "stage": row.stage,
            "requirement_id": identifier,
            "consequence": row.consequence,
            "remedy": row.remedy,
            "evidence": list(row.evidence),
        }
    property_points = {
        key: float(WEIGHTS[key]) if status[key] else 0.0 for key in WEIGHTS
    }
    property_points["discrimination_and_uncertainty"] = (
        5.0 * float(discrimination_point_valid)
        + 5.0 * float(discrimination_uncertainty_valid)
    )
    property_points["probability_and_calibration"] = (
        5.0 * float(primary.get("PROBABILITY_ACCURACY", False))
        + 5.0 * float(primary.get("CALIBRATION", False))
    )
    partial = round(sum(property_points.values()), 6)
    complete = not failures
    return OpenGrade(
        complete_mission_success=complete,
        partial_scientific_quality=partial,
        reliability_score=(
            100.0 if (submission.get("state") or {}).get("completion_accepted") else 0.0
        ),
        mission_failures=failures,
        first_decision_critical_failure=first,
        requirements=requirements,
        diagnostics={
            "verifier_version": "case1-rc4",
            "weights": WEIGHTS,
            "property_points": property_points,
            "property_dependencies": PROPERTY_DEPENDENCIES,
            "process": process_details,
            "cohort": cohort_details,
            "identity_provenance_valid": identity_valid,
            "outcome_binding_valid": outcome_valid,
            "artifact_errors": artifact_errors,
            "artifact_validation": artifact_validations,
            "calculation_results": {key: value.to_dict() for key, value in calculations.items()},
            "primary_properties": primary,
            "criterion_results": criteria,
            "resource": (
                None
                if resource is None
                else {
                    "valid": resource.valid,
                    "relevant": resource.relevant,
                    "used": resource.used,
                    "observed_effect": resource.observed_effect,
                    "material": resource.material,
                    "expected_results": resource.expected_results,
                    "faults": list(resource.faults),
                }
            ),
            "prose_scored": False,
            "prose_diagnostic_flags": _prose_diagnostics(final),
            "schema_version": SCHEMA_VERSION,
        },
        failure_class=(
            "none"
            if complete
            else ("integrity_failure" if not process_valid else "scientific_failure")
        ),
    )


__all__ = ["WEIGHTS", "verify_case1_rc4_submission"]

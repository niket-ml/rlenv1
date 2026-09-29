"""Single public contract and completeness inventory for Case-1 RC5."""

from __future__ import annotations

import copy
from typing import Any

from uc_bench.case1_pilot_v1_rc4_contract import (
    PROPERTY_DEPENDENCIES as RC4_PROPERTY_DEPENDENCIES,
)
from uc_bench.case1_pilot_v1_rc4_contract import (
    PUBLIC_CONTRACT as RC4_PUBLIC_CONTRACT,
)
from uc_bench.case1_pilot_v1_rc4_contract import (
    RESOURCE_RETURN_SCHEMA_VERSION,
    RESOURCE_SUMMARY_SCHEMA_VERSION,
    SCHEMA_VERSION,
)
from uc_bench.case1_pilot_v1_rc4_contract import (
    validate_final_submission as _validate_final_submission,
)
from uc_bench.case1_pilot_v1_rc4_contract import (
    validate_followup_plan as _validate_followup_plan,
)
from uc_bench.case1_pilot_v1_rc4_contract import (
    validate_validation_plan as _validate_validation_plan,
)
from uc_bench.case1_pilot_v1_rc5_normalization import (
    NormalizationError,
    normalize_source_hashes,
)
from uc_bench.mmmvp_open_schema import OpenSchemaIssue, OpenSchemaResult

_EXPECTED_AGENT_SCHEMA_ERRORS = (
    ArithmeticError,
    AttributeError,
    IndexError,
    KeyError,
    RecursionError,
    TypeError,
    ValueError,
)


def _total_validation(kind: str, payload: Any, validator: Any) -> OpenSchemaResult:
    """Turn malformed nested agent values into disclosed schema issues."""

    try:
        return validator(payload)
    except _EXPECTED_AGENT_SCHEMA_ERRORS as exc:
        return OpenSchemaResult(
            kind,
            (
                OpenSchemaIssue(
                    "$",
                    "malformed_nested_value",
                    f"Malformed nested agent value: {type(exc).__name__}",
                ),
            ),
        )


def validate_validation_plan(payload: Any) -> OpenSchemaResult:
    return _total_validation("validation_plan", payload, _validate_validation_plan)


def validate_followup_plan(payload: Any) -> OpenSchemaResult:
    return _total_validation("followup_plan", payload, _validate_followup_plan)


def validate_final_submission(payload: Any) -> OpenSchemaResult:
    return _total_validation("final_submission", payload, _validate_final_submission)


def validate_payload(kind: str, payload: Any) -> OpenSchemaResult:
    validators = {
        "validation_plan": validate_validation_plan,
        "followup_plan": validate_followup_plan,
        "final_submission": validate_final_submission,
    }
    if kind not in validators:
        return OpenSchemaResult(
            kind,
            (OpenSchemaIssue("$", "unknown_payload_kind", "Unknown payload kind"),),
        )
    return validators[kind](payload)


PROPERTY_DEPENDENCIES = copy.deepcopy(RC4_PROPERTY_DEPENDENCIES)
PROPERTY_DEPENDENCIES["decision_relevant_followup"]["authoritative_evidence"] = [
    "committed question and resource",
    "resource assessment linked to its saved summary",
    "normalized summary source hashes linked to returned files",
    "independently recomputed returned result and its decision consequence",
]
PROPERTY_DEPENDENCIES["bounded_decision_and_claims"]["depends_on"] = [
    "verified_criteria_used_by_the_claim",
    "verified_resource_evidence_graph",
]
PROPERTY_DEPENDENCIES["decision_relevant_followup"]["conditional_dependencies"]["none"] = (
    "all five committed criteria are independently evaluable, the bounded immediate "
    "decision is resolved in either direction, and no included provenance flag remains"
)
PROPERTY_DEPENDENCIES["decision_relevant_followup"]["conditional_dependencies"]["X63"] = (
    "advisory-only in this release: its disclosed package contains no new empirical evidence, "
    "so it may inform diagnostic prose but cannot resolve the bounded current decision"
)


def _audit_row(
    field: str,
    public_rule: str,
    validator: str,
    passing_test: str,
    failing_test: str,
) -> dict[str, str | bool]:
    # The cited tests are executable release evidence, not documentation labels.
    # All submission-object families are exercised by the table-driven positive
    # and negative tests. Resource-summary normalization has its own fixtures.
    if not field.startswith("resource_summary."):
        passing_test = "test_contract_field_families_accept_reference_submission"
        failing_test = "test_contract_field_families_reject_targeted_mutations"
    return {
        "agent_authored_field": field,
        "public_rule": public_rule,
        "local_validator_check": validator,
        "passing_test": passing_test,
        "failing_test": failing_test,
        "prose_affects_score": False,
    }


# This inventory is release-blocking.  Patterns cover repeated array members;
# they are intentionally expressed using the same paths shown in the public
# object schemas.
CONTRACT_COMPLETENESS_AUDIT = [
    _audit_row(
        "validation_plan.schema_version",
        "objects.validation_plan",
        "validate_contract.py validation",
        "test_exact_rc4_trajectory_replays_as_123_person_general_cohort",
        "test_complete_control_suite_and_reporting_recovery",
    ),
    _audit_row(
        "validation_plan.hypotheses[*].{hypothesis_id,belief,decision_effect_if_true}",
        "relationships_and_conditionals:validation_competing_hypotheses",
        "validate_contract.py validation",
        "test_exact_rc4_trajectory_replays_as_123_person_general_cohort",
        "test_generic_decision_policy_and_hard_coded_values_fail",
    ),
    _audit_row(
        "validation_plan.planned_analyses[*].{analysis_id,input_paths,planned_output_paths}",
        "relationships_and_conditionals:validation_inputs_exist_before_reveal",
        "validate_contract.py validation plus commit_validation_plan",
        "test_two_materially_different_valid_primary_workflows_pass",
        "test_complete_control_suite_and_reporting_recovery",
    ),
    _audit_row(
        "validation_plan.prospective_specification.*",
        "prospective_binding",
        "validate_contract.py validation plus shared CommittedCohort commit check",
        "test_exact_rc4_trajectory_replays_as_123_person_general_cohort",
        "test_complete_control_suite_and_reporting_recovery",
    ),
    _audit_row(
        "validation_plan.decision_criteria[*].{calculation_id,property,metric,comparator,threshold}",
        "relationships_and_conditionals:criterion_property_metric_binding",
        "validate_contract.py validation",
        "test_two_materially_different_valid_primary_workflows_pass",
        "test_generic_decision_policy_and_hard_coded_values_fail",
    ),
    _audit_row(
        "followup_plan.{decision_question_type,chosen_resource,evidence_target,materiality_threshold}",
        "relationships_and_conditionals:resource_question_and_use",
        "validate_contract.py followup",
        "test_complete_control_suite_and_reporting_recovery",
        "test_generic_decision_policy_and_hard_coded_values_fail",
    ),
    _audit_row(
        "followup_plan.beliefs_before",
        "relationships_and_conditionals:followup_beliefs_preserved",
        "validate_contract.py followup plus commit_followup_plan",
        "test_exact_rc4_trajectory_replays_as_123_person_general_cohort",
        "test_generic_decision_policy_and_hard_coded_values_fail",
    ),
    _audit_row(
        "final_submission.artifact_manifest[*].{artifact_id,path,role,source_paths,column_map,analysis_structure,aggregation}",
        "relationships_and_conditionals:artifact_paths_and_hashes",
        "validate_contract.py final and validate_saved_artifact.py",
        "test_two_materially_different_valid_primary_workflows_pass",
        "test_generic_decision_policy_and_hard_coded_values_fail",
    ),
    _audit_row(
        "final_submission.calculations[*].*",
        "relationships_and_conditionals:calculation_parameters",
        "validate_contract.py final and validate_saved_artifact.py",
        "test_exact_rc4_trajectory_replays_as_123_person_general_cohort",
        "test_generic_decision_policy_and_hard_coded_values_fail",
    ),
    _audit_row(
        "resource_summary.{schema_version,resource_id,source_hashes,results}",
        "resource_evidence_graph",
        "validate_saved_artifact.py",
        "test_resource_hash_forms_normalize_identically",
        "test_malformed_or_duplicate_resource_hashes_fail",
    ),
    _audit_row(
        "final_submission.resource_assessment.{resource_id,question_type,summary_artifact_path,calculation_ids,observed_effect,material}",
        "relationships_and_conditionals:resource_assessment_binding",
        "validate_contract.py final",
        "test_exact_rc4_trajectory_replays_as_123_person_general_cohort",
        "test_complete_control_suite_and_reporting_recovery",
    ),
    _audit_row(
        "final_submission.belief_updates[*].{hypothesis_id,before,after,matched_contingency_id}",
        "relationships_and_conditionals:belief_revision_against_contingency",
        "validate_contract.py final",
        "test_exact_rc4_trajectory_replays_as_123_person_general_cohort",
        "test_generic_decision_policy_and_hard_coded_values_fail",
    ),
    _audit_row(
        "final_submission.decision.{development_stage,disposition,use_scope}",
        "relationships_and_conditionals:decision_tuple_consistency",
        "validate_contract.py final",
        "test_professional_prose_paraphrase_does_not_change_score",
        "test_generic_decision_policy_and_hard_coded_values_fail",
    ),
    _audit_row(
        "final_submission.findings[*].{status,decision_effect,calculation_ids}",
        "relationships_and_conditionals:decision_from_criteria_and_followup",
        "validate_contract.py final",
        "test_exact_rc4_trajectory_replays_as_123_person_general_cohort",
        "test_generic_decision_policy_and_hard_coded_values_fail",
    ),
    _audit_row(
        "final_submission.claims[*].{status,scope,calculation_ids}",
        "relationships_and_conditionals:claim_scope_evidence",
        "validate_contract.py final",
        "test_exact_rc4_trajectory_replays_as_123_person_general_cohort",
        "test_generic_decision_policy_and_hard_coded_values_fail",
    ),
]


def _public_contract() -> dict[str, Any]:
    value = copy.deepcopy(RC4_PUBLIC_CONTRACT)
    value["contract_revision"] = "case1-rc5"
    # Public dependencies explain scientific causality without exposing score
    # weights, partial-credit allocation or internal regression-test names.
    value["scientific_property_dependency_graph"] = {
        identifier: {
            key: copy.deepcopy(item)
            for key, item in specification.items()
            if key not in {"weight", "partial_credit"}
        }
        for identifier, specification in PROPERTY_DEPENDENCIES.items()
    }
    validation_fields = value["objects"]["validation_plan"]["fields"]
    criteria = next(row for row in validation_fields if row["path"] == "decision_criteria")
    criteria["minimum_items"] = 5
    criteria["exact_items"] = 5
    validation_fields.extend(
        [
            {
                "path": "prospective_specification.exclusions[*].entity_id",
                "type": "identifier",
                "required": True,
            },
            {
                "path": "prospective_specification.exclusions[*].reason",
                "type": "enum",
                "enum": "preoutcome_exclusion_reason",
                "required": True,
            },
            {
                "path": "prospective_specification.exclusions[*].evidence_refs",
                "type": "array<string>",
                "required": True,
                "nonempty": True,
            },
        ]
    )
    for row in value["objects"]["validation_plan"]["additional_required"]:
        path = row["path"]
        if row.get("enum"):
            row["type"] = "enum"
        elif path in {
            "prospective_specification.eligible_entity_manifest_path",
            "prospective_specification.identity_provenance_path",
        }:
            row.update({"type": "string", "nonempty": True})
        elif path == "prospective_specification.eligible_entity_manifest_sha256":
            row["type"] = "sha256"
        elif path in {
            "prospective_specification.calibration_bin_count",
            "prospective_specification.uncertainty_replicates",
        }:
            row["type"] = "positive_integer"
        elif path == "prospective_specification.uncertainty_seed":
            row["type"] = "integer"
        elif path == "prospective_specification.utility_threshold":
            row["type"] = "finite_number"
        elif path == "prospective_specification.uncertainty_level":
            row["type"] = "number[0,1]"
        if row["path"] == "prospective_specification.exclusions":
            row.update(
                {
                    "type": "array<object>",
                    "unique_by": "entity_id",
                    "description": (
                        "Array; may be empty. Every item contains exactly one entity_id, "
                        "a disclosed preoutcome_exclusion_reason in reason, and a nonempty "
                        "evidence_refs array of visible pre-outcome paths."
                    ),
                }
            )
    for row in value["objects"]["followup_plan"]["additional_required"]:
        if row.get("enum"):
            row["type"] = "enum"
        elif row["path"] == "materiality_threshold":
            row["type"] = "finite_number"
    final_fields = value["objects"]["final_submission"]["fields"]
    for field in ("calculations", "belief_updates"):
        next(row for row in final_fields if row["path"] == field)["minimum_items"] = 1
    for row in value["objects"]["final_submission"]["additional_required"]:
        if row["path"] == "resource_assessment.resource_id":
            row.update({"type": "enum", "enum": "resource_id"})
        elif row["path"] == "resource_assessment.summary_artifact_path":
            row.update({"type": "string", "nonempty": True})
        elif row["path"] in {
            "resource_assessment.source_paths",
            "resource_assessment.calculation_ids",
        }:
            row.update({"type": "array<string>", "nonempty": False})
        elif row["path"] == "resource_assessment.material":
            row["type"] = "boolean"
        elif row.get("enum"):
            row["type"] = "enum"
        elif row["path"] == "narrative_summary":
            row.update({"type": "string", "nonempty": True})
    value["prospective_binding"]["rules"] = [
        (
            "The manifest CSV has exactly the disclosed columns and contains every "
            "baseline-eligible biological entity exactly once."
        ),
        (
            "Every entity lists exactly all of its baseline-eligible source records; "
            "a source record cannot be duplicated or reassigned."
        ),
        (
            "Excluded entities remain listed with included=false. Each exclusion must "
            "be committed before reveal, use a disclosed reason, and cite visible "
            "pre-outcome evidence that establishes that reason."
        ),
        (
            "PREOUTCOME_ENDPOINT_AMBIGUITY cites data/endpoint_source_ledger.csv and "
            "requires a documented pending, discordant or ambiguous status for that entity."
        ),
        (
            "PREOUTCOME_MISSING_PREDICTION cites data/locked_predictions.csv and requires "
            "all source records for that entity to lack predictions."
        ),
        (
            "The manifest path and lower-case SHA-256 are committed before reveal and "
            "cannot change afterward."
        ),
        (
            "The primary analysis contains exactly included=true entities and their source "
            "records. Excluded entities are never silently reintroduced."
        ),
        (
            "Purchased cohorts remain separate unless the returned package explicitly maps "
            "them to the committed source records."
        ),
    ]
    value["criterion_metric_families"] = {
        "DISCRIMINATION": ["ROC_AUC", "BINARY_CONCORDANCE"],
        "PROBABILITY_ACCURACY": ["BRIER_SCORE", "LOG_LOSS"],
        "CALIBRATION": ["CALIBRATION_ERROR"],
        "THRESHOLD_UTILITY": ["NET_BENEFIT", "THRESHOLD_EXPECTED_UTILITY"],
        "CONTEXT_ROBUSTNESS": ["SITE_WEIGHTED_ROC_AUC", "WORST_SITE_ROC_AUC"],
    }
    value["resource_summary_contract"].update(
        {
            "accepted_source_hash_forms": [
                "object mapping each relative path to its lower-case SHA-256",
                "list of objects containing exactly path and sha256",
            ],
            "normalization_rule": (
                "Both unambiguous forms normalize to one path-to-hash mapping. Blank paths, "
                "duplicates, conflicts, missing hashes and malformed hashes fail."
            ),
        }
    )
    value["resource_materiality_rules"]["X63"] = (
        "This package returns advice derived from the existing packet, with structured "
        "new_empirical_evidence=false. Recommendations alone are diagnostic and do not make "
        "the purchase decision-resolving; material/relevant credit would require structured "
        "new empirical evidence."
    )
    value["resource_evidence_graph"] = {
        "edges": [
            "resource_assessment.summary_artifact_path -> saved resource_summary.json",
            "resource_summary.source_hashes -> normalized path-to-hash mapping",
            (
                "normalized source hashes -> every environment-returned file listed by "
                "resource_manifest.json"
            ),
        ],
        "sufficiency": (
            "A correctly linked, hash-verified graph plus independently correct results and "
            "an evidence-consistent decision is sufficient. The summary needs no special "
            "artifact role and returned paths need not be duplicated in evidence_assessments."
        ),
        "resource_assessment_source_paths": (
            "A professional audit field retained for compatibility; it is not a second "
            "mission-critical provenance edge."
        ),
        "none_branch": (
            "CURRENT_DECISION_ALREADY_RESOLVED may choose none when verified current evidence "
            "resolves the bounded decision. no_new_evidence.json adds no evidence, so beliefs "
            "remain unchanged. A prospectively excluded unresolved record may remain a future "
            "gate without forcing a purchase for the current claim scope."
        ),
    }
    for relationship in value["relationships_and_conditionals"]:
        if relationship.get("id") == "resource_question_and_use":
            relationship["rule"] = (
                "decision_question_type determines the resource and evidence target. The "
                "resource assessment links its saved summary; normalized summary hashes bind "
                "the returned files; independently recomputed results and the final decision "
                "must satisfy the published materiality rule."
            )
        elif relationship.get("id") == "resource_assessment_binding":
            relationship["rule"] = (
                "resource_id and question_type match the commitment and event record; "
                "summary_artifact_path starts the public evidence graph; calculation_ids, "
                "observed_effect and material match independently recomputed evidence. "
                "source_paths is an audit field and is not duplicate proof of provenance."
            )
        elif relationship.get("id") == "decision_tuple_consistency":
            relationship["rule"] = (
                "CONTINUE requires a non-STOPPED stage and RESEARCH_RANKING or "
                "RESEARCH_PROBABILITY. STOP requires STOPPED and NO_USE. PAUSE and "
                "INSUFFICIENT_EVIDENCE require a non-STOPPED stage and a non-clinical "
                "scope; they may retain a previously supported bounded research use. A "
                "continued path needs a supported SUPPORTS finding; a contained path "
                "needs a supported WEAKENS or INVALIDATES finding."
            )
        elif relationship.get("id") == "symbolic_outcome_binding":
            relationship["rule"] = (
                "Before reveal, commit only SEALED_VALIDATION_OUTCOMES. After reveal, "
                "revealed/evidence_binding.json names the immutable outcome file, its entity "
                "and outcome columns, and its SHA-256 for local recomputation."
            )
    value["relationships_and_conditionals"].extend(
        [
            {
                "id": "belief_revision_against_contingency",
                "rule": (
                    "Every belief update names the same one committed contingency. Each "
                    "numeric before-to-after direction must equal that contingency's "
                    "machine-readable hypothesis_updates direction. NO_NEW_EVIDENCE and "
                    "INEFFECTIVE require unchanged beliefs. EXPOSES_BLOCKER and "
                    "MISLEADING_REASSURANCE permit SUPPORTS beliefs only to decrease or remain "
                    "unchanged and WEAKENS/INVALIDATES beliefs only to increase or remain "
                    "unchanged, with at least one material change. RESOLVES and "
                    "REDUCES_UNCERTAINTY use the opposite signs, again with at least one "
                    "material change. NONE-effect hypotheses remain unchanged. The final "
                    "development_stage, disposition and use_scope must equal the selected "
                    "contingency's next_decision values. Prose is not compared."
                ),
            },
            {
                "id": "complete_action_record_integrity",
                "rule": (
                    "The authoritative host record must contain, in order, one accepted "
                    "commit_validation_plan, reveal_validation, commit_followup_plan, "
                    "purchase_resource and submit action. Saved validation, follow-up and "
                    "final objects and their state hashes must match those accepted records."
                ),
            },
        ]
    )
    value["prose_policy"] = (
        "Professional-language fields are retained for audit. No free-text content, wording, "
        "substring, regular expression or private vocabulary affects mission credit."
    )
    value["local_validation"] = {
        "contract_validator": (
            "validate_contract.py checks all disclosed fields, enums, cardinalities and public "
            "cross-field relationships. For a final record it also recomputes visible primary "
            "and purchased-resource evidence. The environment separately authenticates the "
            "irreversible host event state and protected-file hashes."
        ),
        "artifact_validator": (
            "validate_saved_artifact.py checks saved calculation-output structure and binds a "
            "resource summary transitively to the purchased manifest and returned file hashes; "
            "when the saved plan and final record exist it runs the same public recomputation."
        ),
        "templates": (
            "Templates are structural examples with placeholders. They are not valid submissions "
            "until every placeholder and evidence binding has been replaced."
        ),
    }
    return value


PUBLIC_CONTRACT = _public_contract()


def validate_resource_summary_structure(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return ["resource_summary_object_required"]
    faults: list[str] = []
    resource = value.get("resource_id")
    expected_keys = set(
        PUBLIC_CONTRACT["resource_summary_contract"]["result_keys"].get(resource, [])
    )
    if value.get("schema_version") != RESOURCE_SUMMARY_SCHEMA_VERSION:
        faults.append("resource_summary_schema_version_invalid")
    if not expected_keys:
        faults.append("resource_id_invalid")
    try:
        normalize_source_hashes(value.get("source_hashes"))
    except NormalizationError as exc:
        faults.append(f"source_hashes_invalid:{exc}")
    results = value.get("results")
    if not isinstance(results, dict) or set(results) != expected_keys:
        faults.append("resource_result_keys_mismatch")
    return faults


def _public_rule_exists(reference: str) -> bool:
    if reference.startswith("relationships_and_conditionals:"):
        identifier = reference.split(":", 1)[1]
        return identifier in {
            str(row.get("id"))
            for row in PUBLIC_CONTRACT.get("relationships_and_conditionals", [])
            if isinstance(row, dict)
        }
    value: Any = PUBLIC_CONTRACT
    for part in reference.split("."):
        if not isinstance(value, dict) or part not in value:
            return False
        value = value[part]
    return True


def contract_completeness_valid(test_source: str | None = None) -> bool:
    required = {
        "agent_authored_field",
        "public_rule",
        "local_validator_check",
        "passing_test",
        "failing_test",
        "prose_affects_score",
    }
    structurally_valid = bool(CONTRACT_COMPLETENESS_AUDIT) and all(
        set(row) == required
        and all(row[key] for key in required - {"prose_affects_score"})
        and row["prose_affects_score"] is False
        and _public_rule_exists(str(row["public_rule"]))
        for row in CONTRACT_COMPLETENESS_AUDIT
    )
    if not structurally_valid or test_source is None:
        return structurally_valid
    return all(
        f"def {row['passing_test']}" in test_source and f"def {row['failing_test']}" in test_source
        for row in CONTRACT_COMPLETENESS_AUDIT
    )


__all__ = [
    "CONTRACT_COMPLETENESS_AUDIT",
    "PROPERTY_DEPENDENCIES",
    "PUBLIC_CONTRACT",
    "RESOURCE_RETURN_SCHEMA_VERSION",
    "RESOURCE_SUMMARY_SCHEMA_VERSION",
    "SCHEMA_VERSION",
    "contract_completeness_valid",
    "validate_final_submission",
    "validate_followup_plan",
    "validate_payload",
    "validate_resource_summary_structure",
    "validate_validation_plan",
]

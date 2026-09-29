"""Public, answer-neutral contract for the unfrozen Case 2 RC1 candidate.

This is a Case-2 adapter over the mature Case-1 RC6 structural contract.  It
changes only the identity declaration, context non-vacuity rule, and the
machine-readable decision facts needed to grade those rules without reading
prose.  It contains no observed result, preferred resource, or preferred
disposition.
"""

from __future__ import annotations

import copy
from typing import Any

from uc_bench.case1_pilot_v1_rc5_contract import (
    PUBLIC_CONTRACT as RC6_STRUCTURAL_CONTRACT,
)
from uc_bench.case1_pilot_v1_rc5_contract import (
    SCHEMA_VERSION as RC6_SCHEMA_VERSION,
)
from uc_bench.case1_pilot_v1_rc5_contract import (
    validate_final_submission as _validate_rc6_final,
)
from uc_bench.case1_pilot_v1_rc5_contract import (
    validate_followup_plan as _validate_rc6_followup,
)
from uc_bench.case1_pilot_v1_rc5_contract import (
    validate_validation_plan as _validate_rc6_validation,
)
from uc_bench.mmmvp_open_schema import OpenSchemaIssue, OpenSchemaResult

SCHEMA_VERSION = "mmmvp-open-case2-pilot-v1-rc1"

PREPURCHASE_IDENTITY_BASES = {
    "PROVISIONAL_FINGERPRINT_AGGREGATION",
    "PROVISIONAL_FINGERPRINT_WEIGHTED_ROWS",
}
TABLE_IDENTITY_BASES = {
    *PREPURCHASE_IDENTITY_BASES,
    "REPORTED_PATIENT_SENSITIVITY",
    "ADJUDICATED_CANONICAL_PERSON",
    "EXTERNAL_COHORT_PERSON",
}
IDENTITY_CLAIM_BASES = {
    "PROVISIONAL_UNIT",
    "ADJUDICATED_PERSON",
    "NO_PERSON_LEVEL_CLAIM",
}
ACTION_SCOPES = {
    "GENERAL_MULTISITE_ADVANCEMENT",
    "TARGETED_CONTEXT_INVESTIGATION",
    "HOLD_CURRENT_CLAIM",
    "END_DEVELOPMENT_PATH",
}
CONTEXT_STATUSES = {"PASSED", "FAILED", "NOT_EVALUABLE"}
CONTEXT_MINIMUMS = {
    "SITE_WEIGHTED_ROC_AUC": 0.65,
    "WORST_SITE_ROC_AUC": 0.55,
}
CONTEXT_CAPABLE_TARGETS = {"EXTERNAL_COHORT", "RECORD_LINKAGE"}


def _issue(path: str, code: str, message: str) -> OpenSchemaIssue:
    return OpenSchemaIssue(path, code, message)


def _translated(payload: Any, kind: str) -> Any:
    """Translate only successor representation fields for inherited shape checks."""

    if not isinstance(payload, dict):
        return payload
    value = copy.deepcopy(payload)
    value["schema_version"] = RC6_SCHEMA_VERSION
    if kind == "validation_plan":
        specification = value.get("prospective_specification")
        if isinstance(specification, dict):
            specification["biological_unit"] = "PERSON"
        # The inherited RC6 shell requires strictly positive utility.  Keep
        # that mature non-vacuity rule; Case 2 changes only identity and the
        # context floor.
        criteria = value.get("decision_criteria")
        if isinstance(criteria, list):
            context_seen = False
            normalized: list[Any] = []
            for row in criteria:
                if isinstance(row, dict) and row.get("property") == "CONTEXT_ROBUSTNESS":
                    if context_seen:
                        continue
                    context_seen = True
                normalized.append(row)
            value["decision_criteria"] = normalized
    if kind in {"followup_plan", "final_submission"}:
        decisions: list[dict[str, Any]] = []
        if kind == "final_submission" and isinstance(value.get("decision"), dict):
            decisions.append(value["decision"])
        if kind == "followup_plan":
            decisions.extend(
                row["next_decision"]
                for row in value.get("result_contingencies") or []
                if isinstance(row, dict) and isinstance(row.get("next_decision"), dict)
            )
        # RC6 did not represent "continue the investigation but do not advance
        # the predictor".  Normalize that new Case-2 representation only for
        # inherited shape validation; candidate-specific rules below validate
        # the actual submitted fields.
        for decision in decisions:
            if (
                decision.get("disposition") == "CONTINUE"
                and decision.get("action_scope") == "TARGETED_CONTEXT_INVESTIGATION"
            ):
                decision["development_stage"] = "EXTERNAL_VALIDATION"
                decision["use_scope"] = "RESEARCH_PROBABILITY"
    return value


def _decision_shape_issues(decision: dict[str, Any], path: str) -> list[OpenSchemaIssue]:
    issues: list[OpenSchemaIssue] = []
    scope = decision.get("action_scope")
    disposition = decision.get("disposition")
    use_scope = decision.get("use_scope")
    permitted = decision.get("multisite_probability_use_permitted")
    if scope == "GENERAL_MULTISITE_ADVANCEMENT" and (
        disposition != "CONTINUE" or permitted is not True
    ):
        issues.append(
            _issue(
                path,
                "action_tuple_invalid",
                "General advancement requires CONTINUE and permitted multi-site probability use",
            )
        )
    elif scope == "TARGETED_CONTEXT_INVESTIGATION" and (
        disposition != "CONTINUE"
        or use_scope != "RETROSPECTIVE_AUDIT"
        or permitted is not False
        or decision.get("next_evidence_target") not in CONTEXT_CAPABLE_TARGETS
    ):
        issues.append(
            _issue(
                path,
                "action_tuple_invalid",
                "Targeted continuation requires RETROSPECTIVE_AUDIT, prohibits current "
                "multi-site probability use, and names context-capable evidence",
            )
        )
    elif scope == "HOLD_CURRENT_CLAIM" and (
        disposition not in {"PAUSE", "INSUFFICIENT_EVIDENCE"}
        or use_scope not in {"NO_USE", "RETROSPECTIVE_AUDIT"}
        or permitted is not False
    ):
        issues.append(
            _issue(
                path,
                "action_tuple_invalid",
                "A held claim uses PAUSE or INSUFFICIENT_EVIDENCE without current "
                "multi-site probability use",
            )
        )
    elif scope == "END_DEVELOPMENT_PATH" and (
        disposition != "STOP"
        or decision.get("development_stage") != "STOPPED"
        or use_scope != "NO_USE"
        or permitted is not False
    ):
        issues.append(
            _issue(
                path, "action_tuple_invalid", "Ending the path requires STOPPED, STOP and NO_USE"
            )
        )
    return issues


def _merge(kind: str, base: OpenSchemaResult, issues: list[OpenSchemaIssue]) -> OpenSchemaResult:
    return OpenSchemaResult(kind, tuple((*base.issues, *issues)))


def _validate_validation_plan_impl(payload: Any) -> OpenSchemaResult:
    base = _validate_rc6_validation(_translated(payload, "validation_plan"))
    issues: list[OpenSchemaIssue] = []
    if not isinstance(payload, dict):
        return base
    if payload.get("schema_version") != SCHEMA_VERSION:
        issues.append(_issue("schema_version", "invalid_version", f"Expected {SCHEMA_VERSION}"))
    specification = payload.get("prospective_specification")
    if not isinstance(specification, dict):
        return _merge("validation_plan", base, issues)
    identity_basis = specification.get("identity_basis")
    if identity_basis not in PREPURCHASE_IDENTITY_BASES:
        issues.append(
            _issue(
                "prospective_specification.identity_basis",
                "invalid_enum",
                f"Expected one of {sorted(PREPURCHASE_IDENTITY_BASES)}",
            )
        )
    if specification.get("biological_unit") != "PROVISIONAL_LINKAGE_UNIT":
        issues.append(
            _issue(
                "prospective_specification.biological_unit",
                "invalid_enum",
                "Pre-purchase primary work uses PROVISIONAL_LINKAGE_UNIT",
            )
        )
    if specification.get("identity_provenance_path") != "identity_provenance.json":
        issues.append(
            _issue(
                "prospective_specification.identity_provenance_path",
                "identity_contract_mismatch",
                "Expected identity_provenance.json",
            )
        )
    expected_handling = {
        "PROVISIONAL_FINGERPRINT_AGGREGATION": "PERSON_LEVEL_AGGREGATION",
        "PROVISIONAL_FINGERPRINT_WEIGHTED_ROWS": "SOURCE_RECORD_CLUSTERING",
    }.get(identity_basis)
    if expected_handling and specification.get("dependence_handling") != expected_handling:
        issues.append(
            _issue(
                "prospective_specification.dependence_handling",
                "identity_dependence_mismatch",
                "Dependence handling must match the disclosed identity basis",
            )
        )
    criteria = payload.get("decision_criteria")
    if not isinstance(criteria, list):
        return _merge("validation_plan", base, issues)
    properties = [row.get("property") for row in criteria if isinstance(row, dict)]
    required_once = {
        "DISCRIMINATION",
        "PROBABILITY_ACCURACY",
        "CALIBRATION",
        "THRESHOLD_UTILITY",
    }
    if len(criteria) not in {5, 6} or any(properties.count(prop) != 1 for prop in required_once):
        issues.append(
            _issue(
                "decision_criteria",
                "criterion_cardinality",
                "Use one criterion for each non-context property and one or both context metrics",
            )
        )
    context = [
        row
        for row in criteria
        if isinstance(row, dict) and row.get("property") == "CONTEXT_ROBUSTNESS"
    ]
    if not 1 <= len(context) <= 2 or len({row.get("metric") for row in context}) != len(context):
        issues.append(
            _issue(
                "decision_criteria",
                "context_criterion_cardinality",
                "Commit SITE_WEIGHTED_ROC_AUC, WORST_SITE_ROC_AUC, or both exactly once",
            )
        )
    for index, row in enumerate(context):
        metric = row.get("metric")
        threshold = row.get("threshold")
        floor = CONTEXT_MINIMUMS.get(str(metric))
        if (
            floor is None
            or row.get("comparator") != "AT_LEAST"
            or isinstance(threshold, bool)
            or not isinstance(threshold, (int, float))
            or threshold < floor
        ):
            issues.append(
                _issue(
                    f"decision_criteria.context[{index}]",
                    "vacuous_context_criterion",
                    "SITE_WEIGHTED_ROC_AUC needs >=0.65; WORST_SITE_ROC_AUC needs >=0.55",
                )
            )
    all_properties = {
        "DISCRIMINATION",
        "PROBABILITY_ACCURACY",
        "CALIBRATION",
        "THRESHOLD_UTILITY",
        "CONTEXT_ROBUSTNESS",
    }
    if set(properties) != all_properties:
        issues.append(
            _issue(
                "decision_criteria",
                "criterion_family_coverage",
                f"Expected every property in {sorted(all_properties)}",
            )
        )
    selected_metrics = {str(row.get("metric")) for row in context}
    if specification.get("context_metric") not in selected_metrics:
        issues.append(
            _issue(
                "prospective_specification.context_metric",
                "context_method_mismatch",
                "The primary context metric must be one of the committed context criteria",
            )
        )
    return _merge("validation_plan", base, issues)


def _validate_followup_plan_impl(payload: Any) -> OpenSchemaResult:
    base = _validate_rc6_followup(_translated(payload, "followup_plan"))
    issues: list[OpenSchemaIssue] = []
    if isinstance(payload, dict):
        if payload.get("schema_version") != SCHEMA_VERSION:
            issues.append(_issue("schema_version", "invalid_version", f"Expected {SCHEMA_VERSION}"))
        for index, row in enumerate(payload.get("result_contingencies") or []):
            decision = row.get("next_decision") if isinstance(row, dict) else None
            if not isinstance(decision, dict):
                continue
            for field, accepted in (
                ("action_scope", ACTION_SCOPES),
                ("current_context_status", CONTEXT_STATUSES),
                ("identity_claim_basis", IDENTITY_CLAIM_BASES),
            ):
                if decision.get(field) not in accepted:
                    issues.append(
                        _issue(
                            f"result_contingencies[{index}].next_decision.{field}",
                            "invalid_enum",
                            f"Expected one of {sorted(accepted)}",
                        )
                    )
            if not isinstance(decision.get("multisite_probability_use_permitted"), bool):
                issues.append(
                    _issue(
                        (
                            f"result_contingencies[{index}].next_decision."
                            "multisite_probability_use_permitted"
                        ),
                        "wrong_type",
                        "Expected a boolean",
                    )
                )
            if (
                decision.get("next_evidence_target")
                not in PUBLIC_CONTRACT["enums"]["evidence_target"]
            ):
                issues.append(
                    _issue(
                        f"result_contingencies[{index}].next_decision.next_evidence_target",
                        "invalid_enum",
                        "Expected a disclosed evidence_target value",
                    )
                )
            issues.extend(
                _decision_shape_issues(decision, f"result_contingencies[{index}].next_decision")
            )
    return _merge("followup_plan", base, issues)


def _validate_final_submission_impl(payload: Any) -> OpenSchemaResult:
    base = _validate_rc6_final(_translated(payload, "final_submission"))
    issues: list[OpenSchemaIssue] = []
    if not isinstance(payload, dict):
        return base
    if payload.get("schema_version") != SCHEMA_VERSION:
        issues.append(_issue("schema_version", "invalid_version", f"Expected {SCHEMA_VERSION}"))
    for index, row in enumerate(payload.get("artifact_manifest") or []):
        if not isinstance(row, dict) or row.get("role") != "ANALYSIS_TABLE":
            continue
        if row.get("identity_basis") not in TABLE_IDENTITY_BASES:
            issues.append(
                _issue(
                    f"artifact_manifest[{index}].identity_basis",
                    "invalid_enum",
                    f"Expected one of {sorted(TABLE_IDENTITY_BASES)}",
                )
            )
    decision = payload.get("decision")
    if not isinstance(decision, dict):
        return _merge("final_submission", base, issues)
    for field, accepted in (
        ("action_scope", ACTION_SCOPES),
        ("current_context_status", CONTEXT_STATUSES),
        ("identity_claim_basis", IDENTITY_CLAIM_BASES),
    ):
        if decision.get(field) not in accepted:
            issues.append(
                _issue(f"decision.{field}", "invalid_enum", f"Expected one of {sorted(accepted)}")
            )
    if not isinstance(decision.get("multisite_probability_use_permitted"), bool):
        issues.append(
            _issue(
                "decision.multisite_probability_use_permitted",
                "wrong_type",
                "Expected a boolean",
            )
        )
    if decision.get("next_evidence_target") not in PUBLIC_CONTRACT["enums"]["evidence_target"]:
        issues.append(
            _issue(
                "decision.next_evidence_target",
                "invalid_enum",
                "Expected a disclosed evidence_target value",
            )
        )
    issues.extend(_decision_shape_issues(decision, "decision"))
    return _merge("final_submission", base, issues)


_MALFORMED_PAYLOAD_ERRORS = (
    AttributeError,
    IndexError,
    KeyError,
    TypeError,
    ValueError,
)


def _total_validation(kind: str, validator: Any, payload: Any) -> OpenSchemaResult:
    """Make every agent-controlled payload a deterministic validation result."""

    try:
        return validator(payload)
    except _MALFORMED_PAYLOAD_ERRORS as exc:
        return OpenSchemaResult(
            kind,
            (
                _issue(
                    "$",
                    "malformed_payload",
                    f"Payload has an invalid nested value ({type(exc).__name__})",
                ),
            ),
        )


def validate_validation_plan(payload: Any) -> OpenSchemaResult:
    return _total_validation("validation_plan", _validate_validation_plan_impl, payload)


def validate_followup_plan(payload: Any) -> OpenSchemaResult:
    return _total_validation("followup_plan", _validate_followup_plan_impl, payload)


def validate_final_submission(payload: Any) -> OpenSchemaResult:
    return _total_validation("final_submission", _validate_final_submission_impl, payload)


def validate_payload(kind: str, payload: Any) -> OpenSchemaResult:
    validators = {
        "validation_plan": validate_validation_plan,
        "followup_plan": validate_followup_plan,
        "final_submission": validate_final_submission,
    }
    if kind not in validators:
        return OpenSchemaResult(
            kind,
            (_issue("$", "unknown_payload_kind", "Unknown payload kind"),),
        )
    return validators[kind](payload)


def _public_contract() -> dict[str, Any]:
    value = copy.deepcopy(RC6_STRUCTURAL_CONTRACT)
    value["contract_revision"] = "case2-pilot-v1-rc1-candidate"
    value["payload_schema_version"] = SCHEMA_VERSION
    value["enums"].update(
        {
            "biological_unit": ["PROVISIONAL_LINKAGE_UNIT"],
            "identity_basis": sorted(TABLE_IDENTITY_BASES),
            "prepurchase_identity_basis": sorted(PREPURCHASE_IDENTITY_BASES),
            "identity_claim_basis": sorted(IDENTITY_CLAIM_BASES),
            "action_scope": sorted(ACTION_SCOPES),
            "context_status": sorted(CONTEXT_STATUSES),
        }
    )
    for kind in value["objects"].values():
        for row in kind.get("fields", []):
            if row.get("path") == "schema_version":
                row["notes"] = f"must equal {SCHEMA_VERSION!r}"
    validation_required = value["objects"]["validation_plan"]["additional_required"]
    for field in value["objects"]["validation_plan"]["fields"]:
        if field.get("path") == "decision_criteria":
            field.pop("exact_items", None)
            field["maximum_items"] = 6
    validation_required.append(
        {
            "path": "prospective_specification.identity_basis",
            "required": True,
            "description": "Pre-purchase machine-readable identity estimand",
            "enum": "identity_basis",
            "type": "enum",
        }
    )
    validation_required[-1]["enum"] = "prepurchase_identity_basis"
    decision_fields = value["objects"]["final_submission"]["additional_required"]
    decision_fields.extend(
        [
            {
                "path": "decision.action_scope",
                "required": True,
                "enum": "action_scope",
                "type": "enum",
            },
            {
                "path": "decision.current_context_status",
                "required": True,
                "enum": "context_status",
                "type": "enum",
            },
            {
                "path": "decision.multisite_probability_use_permitted",
                "required": True,
                "type": "boolean",
            },
            {
                "path": "decision.next_evidence_target",
                "required": True,
                "enum": "evidence_target",
                "type": "enum",
            },
            {
                "path": "decision.identity_claim_basis",
                "required": True,
                "enum": "identity_claim_basis",
                "type": "enum",
            },
        ]
    )
    value["objects"]["final_submission"]["fields"].append(
        {
            "path": "artifact_manifest[*].identity_basis",
            "required": False,
            "required_when": "artifact_manifest[*].role == ANALYSIS_TABLE",
            "enum": "identity_basis",
            "type": "enum",
        }
    )
    followup_fields = value["objects"]["followup_plan"]["fields"]
    followup_fields.extend(
        [
            {
                "path": "result_contingencies[*].next_decision.action_scope",
                "required": True,
                "enum": "action_scope",
                "type": "enum",
            },
            {
                "path": "result_contingencies[*].next_decision.current_context_status",
                "required": True,
                "enum": "context_status",
                "type": "enum",
            },
            {
                "path": (
                    "result_contingencies[*].next_decision.multisite_probability_use_permitted"
                ),
                "required": True,
                "type": "boolean",
            },
            {
                "path": "result_contingencies[*].next_decision.next_evidence_target",
                "required": True,
                "enum": "evidence_target",
                "type": "enum",
            },
            {
                "path": "result_contingencies[*].next_decision.identity_claim_basis",
                "required": True,
                "enum": "identity_claim_basis",
                "type": "enum",
            },
        ]
    )
    value["non_vacuity"]["CONTEXT_ROBUSTNESS"] = {
        "comparator": "AT_LEAST",
        "metric_bounds": {
            "SITE_WEIGHTED_ROC_AUC": {"at_least": 0.65},
            "WORST_SITE_ROC_AUC": {"at_least": 0.55},
        },
        "reason": (
            "A site-weighted threshold of 0.65 requires meaningful performance above chance "
            "while allowing a modest reduction from the pooled 0.70 gate. A worst-site "
            "threshold of 0.55 prevents a nearly chance-level site from being hidden by "
            "pooled performance. Uncertainty and intended scope still govern the action."
        ),
    }
    value["identity_semantics"] = {
        "source_record_id": "one biopsy record; data field sample_id",
        "fingerprint_cluster": (
            "provisional outcome-blind dependence/linkage unit; not adjudicated person truth"
        ),
        "reported_patient_id": (
            "supplied identifier whose internal consistency must be investigated; not "
            "automatically canonical person truth"
        ),
        "prepurchase_workflows": [
            "aggregate within provisional fingerprint clusters and limit the estimand",
            "retain source rows with fingerprint-cluster-aware weighting and uncertainty",
            "use reported-patient grouping only as a labelled sensitivity analysis",
        ],
        "claim_limit": (
            "Before identity adjudication, a provisional-unit count is not an adjudicated "
            "patient count. A no-X17 workflow may pass with controlled dependence and limited "
            "claims. After X17, an adjudicated-person claim requires a saved recomputation "
            "using its outcome-independent crosswalk."
        ),
        "multi_context_rule": (
            "Never invent one site for an adjudicated person spanning contexts. Preserve the "
            "prospectively committed provisional context analysis, or calculate a separate "
            "canonical-person-weighted source-row context analysis. Report all site counts, "
            "non-evaluable sites, and multi-context entities; silent omission fails."
        ),
    }
    value["context_decision_standard"] = {
        "committed_estimands": [
            "SITE_WEIGHTED_ROC_AUC at threshold >= 0.65",
            "WORST_SITE_ROC_AUC at threshold >= 0.55",
            "both, in which case both must pass",
        ],
        "audit_requirement": (
            "Save every intended-use site's row count, entity count, evaluability status and "
            "estimate. A missing, silently omitted or one-class site makes context not "
            "evaluable for general multi-site advancement. Optional site diagnostics do not "
            "invalidate unrelated primary properties unless used by a claim or action."
        ),
        "decision_invariant": (
            "General multi-site continuation is supported only when every committed primary "
            "and context criterion passes. After context failure or non-evaluability, PAUSE "
            "or INSUFFICIENT_EVIDENCE may hold the claim; STOP needs evidence that the path is "
            "not worthwhile; CONTINUE is permitted only as a targeted context investigation "
            "that prohibits current multi-site probability use, marks context unresolved, "
            "does not claim transport/independent validation, and names a context-capable next "
            "evidence target. Continuing an investigation is not advancing the predictor."
        ),
    }
    value["resource_materiality_rules"] = {
        "none": (
            "Valid when verified current evidence already resolves the immediate bounded "
            "action. It adds no evidence, material is false and beliefs remain unchanged; "
            "other uncertainties may remain explicit future gates while the claim is held."
        ),
        "X17": (
            "Material when the outcome-blind crosswalk changes provisional membership or "
            "leaves a material identity uncertainty. A person-level claim additionally "
            "requires saved recomputation using the returned mapping."
        ),
        "X24": (
            "Material when visible endpoint provenance makes adjudication an unresolved gate "
            "and the blinded package resolves or materially narrows that gate."
        ),
        "X31": (
            "Decision-resolving only when the absolute replay-versus-primary discrimination "
            "difference exceeds the prospectively committed materiality threshold."
        ),
        "X46": (
            "Material when transport is the declared unresolved question and the returned "
            "matched-context evidence is calculated and used to bound or block the claim."
        ),
        "X58": (
            "Material when the additional same-process sample crosses a committed gate, "
            "exposes harmful utility, or changes a comparable estimate by more than the "
            "prospectively committed materiality threshold."
        ),
        "X63": (
            "Recommendations derived only from the existing packet are diagnostic, not new "
            "decision-resolving evidence. A memo with new_empirical_evidence=false cannot "
            "earn decision-relevant purchase credit."
        ),
    }
    summary = value["resource_summary_contract"]
    summary["schema_version"] = "case2-resource-summary-1"
    summary["result_keys"] = {
        "none": ["new_evidence"],
        "X17": [
            "source_record_count",
            "provisional_unit_count",
            "adjudicated_person_count",
            "membership_changed",
            "unresolved_record_count",
        ],
        "X24": [
            "reviewed_entity_count",
            "changed_label_count",
            "reviewer_disagreement_count",
        ],
        "X31": [
            "entity_count",
            "roc_auc",
            "brier_score",
            "net_benefit",
            "site_weighted_roc_auc",
            "worst_site_roc_auc",
        ],
        "X46": [
            "entity_count",
            "roc_auc",
            "brier_score",
            "net_benefit",
            "site_weighted_roc_auc",
            "worst_site_roc_auc",
        ],
        "X58": [
            "entity_count",
            "roc_auc",
            "brier_score",
            "net_benefit",
            "site_weighted_roc_auc",
            "worst_site_roc_auc",
        ],
        "X63": ["new_empirical_evidence", "recommendation_count"],
    }
    for relationship in value.get("relationships_and_conditionals") or []:
        if relationship.get("id") == "decision_from_criteria_and_followup":
            relationship["rule"] = value["context_decision_standard"]["decision_invariant"]
        elif relationship.get("id") == "decision_tuple_consistency":
            relationship["rule"] = (
                "GENERAL_MULTISITE_ADVANCEMENT requires CONTINUE and permitted current "
                "multi-site probability use. TARGETED_CONTEXT_INVESTIGATION requires "
                "CONTINUE with RETROSPECTIVE_AUDIT, prohibits current multi-site probability "
                "use and names context-capable evidence. HOLD_CURRENT_CLAIM uses PAUSE or "
                "INSUFFICIENT_EVIDENCE. END_DEVELOPMENT_PATH uses STOPPED/STOP/NO_USE."
            )
        elif relationship.get("id") == "claim_scope_evidence":
            relationship["rule"] = (
                "A supported provisional-unit probability claim requires valid committed "
                "discrimination, probability, calibration, utility and context evidence. "
                "Adjudicated-person claims additionally require X17-linked recomputation. "
                "Internal evidence cannot itself establish independent validation, clinical "
                "utility, treatment effect or cross-context transport."
            )
    value["scientific_property_completeness_audit"] = {
        "prospective_design_and_integrity": {
            "public_rule": "prospective_primary_binding and immutable commit-before-reveal",
            "authoritative_source": "host event record, committed records and input hashes",
            "local_check": "evaluate_case2_submission prospective plan reconstruction",
            "positive_test": "reference prospective episode",
            "negative_test": "reordered or mutated commitment",
        },
        "saved_artifact_chain": {
            "public_rule": "calculation_output_artifact_contract",
            "authoritative_source": "saved source-linked tables and calculation outputs",
            "local_check": "independent artifact and calculation recomputation",
            "positive_test": "reference saved artifacts",
            "negative_test": "copied reported value after altered input",
        },
        "committed_entity_and_dependence_analysis": {
            "public_rule": "identity_semantics",
            "authoritative_source": "committed manifest plus raw identity relationships",
            "local_check": "reconstructed provisional/adjudicated membership and table rows",
            "positive_test": "aggregation and entity-weighted alternatives",
            "negative_test": "row-independent or premature canonical-person claim",
        },
        "discrimination_and_uncertainty": {
            "public_rule": "non_vacuity.DISCRIMINATION and committed uncertainty method",
            "authoritative_source": "verified table and typed calculation",
            "local_check": "independent AUC and bootstrap recomputation",
            "positive_test": "reference AUC calculation",
            "negative_test": "wrong value or uncertainty unit",
        },
        "probability_and_calibration": {
            "public_rule": "committed probability and calibration metrics",
            "authoritative_source": "verified table and committed bin count",
            "local_check": "independent metric recomputation",
            "positive_test": "reference Brier/ECE calculations",
            "negative_test": "wrong label or bin count",
        },
        "threshold_utility": {
            "public_rule": "committed utility metric and action threshold",
            "authoritative_source": "verified table and committed threshold",
            "local_check": "independent utility recomputation",
            "positive_test": "reference net benefit",
            "negative_test": "uncommitted decision threshold",
        },
        "context_robustness": {
            "public_rule": "context_decision_standard",
            "authoritative_source": "saved all-site counts, statuses and estimates",
            "local_check": "independent site inventory and context metric recomputation",
            "positive_test": "complete site audit",
            "negative_test": "vacuous threshold or silent site omission",
        },
        "decision_relevant_followup": {
            "public_rule": "resource_question_mapping and resource_summary_contract",
            "authoritative_source": "commit, returned package, summary and calculations",
            "local_check": "resource-specific recomputation and relevance",
            "positive_test": "X17, X46 and none pathways",
            "negative_test": "unused return or expert memo substitution",
        },
        "belief_revision": {
            "public_rule": "committed numeric contingency directions",
            "authoritative_source": "verified resource effect and numeric updates",
            "local_check": "direction-preserving hypothesis update",
            "positive_test": "matched observed contingency",
            "negative_test": "contradictory or post-hoc update",
        },
        "bounded_decision_and_claims": {
            "public_rule": "context_decision_standard and identity_semantics.claim_limit",
            "authoritative_source": "machine decision object, claims and verified evidence",
            "local_check": "evidence-supported action/claim invariant",
            "positive_test": "bounded pause, insufficiency, stop and targeted/general continue",
            "negative_test": "universal advancement or unsupported broad claim",
        },
    }
    value["prose_policy"] = (
        "Professional-language audit fields are retained for replay but never determine "
        "mission credit. All scored identity, context, action and claim facts use disclosed "
        "machine fields, event records, hashes or independently recomputed artifacts."
    )
    return value


PUBLIC_CONTRACT = _public_contract()


__all__ = [
    "ACTION_SCOPES",
    "CONTEXT_CAPABLE_TARGETS",
    "CONTEXT_MINIMUMS",
    "CONTEXT_STATUSES",
    "IDENTITY_CLAIM_BASES",
    "PREPURCHASE_IDENTITY_BASES",
    "PUBLIC_CONTRACT",
    "SCHEMA_VERSION",
    "TABLE_IDENTITY_BASES",
    "validate_final_submission",
    "validate_followup_plan",
    "validate_payload",
    "validate_validation_plan",
]

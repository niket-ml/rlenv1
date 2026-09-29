"""RC6 verifier: RC5 science with one canonical resource evaluator and causality."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import uc_bench.case1_pilot_v1_rc5_verifier as inherited
from uc_bench.case1_pilot_v1_rc5_contract import PROPERTY_DEPENDENCIES
from uc_bench.case1_pilot_v1_rc5_lock import INHERITED_EXTENSION_LOCK
from uc_bench.case1_pilot_v1_rc6_resource import (
    evaluate_resource_semantics,
    resource_result_from_semantics,
)
from uc_bench.mmmvp_open_verifier import OpenGrade

WEIGHTS = inherited.WEIGHTS


def _atom(
    identifier: str,
    value: bool,
    *,
    cause: str,
    contract: str,
    affects: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "predicate_id": identifier,
        "value": bool(value),
        "cause_if_false": cause,
        "public_contract_reference": contract,
        "property_dependencies_affected": list(affects),
    }


def _causal_diagnostics(grade: OpenGrade) -> dict[str, Any]:
    diagnostics = grade.diagnostics
    requirements = {row.requirement_id: row for row in grade.requirements}
    process = diagnostics.get("process") or {}
    cohort = diagnostics.get("cohort") or {}
    resource = diagnostics.get("resource_semantics") or {}
    calculation_results = diagnostics.get("calculation_results") or {}
    artifact_rows = diagnostics.get("artifact_validation") or []

    predicates: dict[str, list[dict[str, Any]]] = {
        "prospective_design_and_integrity": [
            _atom(
                "irreversible_event_and_hash_integrity",
                all(
                    process.get(key) is True
                    for key in (
                        "validation_plan_hash_matches",
                        "followup_plan_hash_matches",
                        "final_submission_hash_matches",
                        "purchase_matches_commitment",
                        "submission_accepted",
                    )
                ),
                cause="agent_caused",
                contract="complete_action_record_integrity",
                affects=("prospective_design_and_integrity",),
            ),
            _atom(
                "prospective_cohort_integrity",
                not cohort.get("faults") and cohort.get("hashes_match") is True,
                cause="agent_caused",
                contract="prospective_primary_binding",
                affects=(
                    "prospective_design_and_integrity",
                    "committed_entity_and_dependence_analysis",
                ),
            ),
        ],
        "saved_artifact_chain": [
            _atom(
                "decision_linked_artifacts_parse_and_replay",
                requirements.get("saved_artifact_chain") is not None
                and requirements["saved_artifact_chain"].passed,
                cause="agent_caused",
                contract="artifact_references_resolve; calculation_saved_output",
                affects=(
                    "saved_artifact_chain",
                    "discrimination_and_uncertainty",
                    "probability_and_calibration",
                    "threshold_utility",
                    "context_robustness",
                    "bounded_decision_and_claims",
                ),
            ),
            *[
                _atom(
                    f"artifact:{row.get('artifact_id')}:{index}",
                    bool(row.get("valid")),
                    cause="agent_caused",
                    contract="artifact_paths_and_hashes; calculation_saved_output",
                    affects=("saved_artifact_chain",),
                )
                for index, row in enumerate(artifact_rows)
                if isinstance(row, dict)
            ],
        ],
        "committed_entity_and_dependence_analysis": [
            _atom(
                "committed_patient_unit_and_dependence_valid",
                requirements.get("committed_entity_and_dependence_analysis") is not None
                and requirements["committed_entity_and_dependence_analysis"].passed,
                cause="agent_caused",
                contract="prospective_primary_binding; calculation_structure_estimator",
                affects=(
                    "committed_entity_and_dependence_analysis",
                    "discrimination_and_uncertainty",
                    "probability_and_calibration",
                    "threshold_utility",
                    "context_robustness",
                ),
            )
        ],
        "discrimination_and_uncertainty": [
            _atom(
                "discrimination_point_estimate_valid",
                bool(
                    (requirements.get("discrimination_and_uncertainty") or object())
                    and (next(
                        (
                            row.observed
                            for row in grade.requirements
                            if row.requirement_id == "discrimination_and_uncertainty"
                        ),
                        {},
                    ) or {}).get("discrimination_point_estimate")
                ),
                cause="agent_caused",
                contract="criterion_property_metric_binding",
                affects=("discrimination_and_uncertainty", "bounded_decision_and_claims"),
            ),
            _atom(
                "discrimination_uncertainty_valid",
                bool(
                    (next(
                        (
                            row.observed
                            for row in grade.requirements
                            if row.requirement_id == "discrimination_and_uncertainty"
                        ),
                        {},
                    ) or {}).get("uncertainty")
                ),
                cause="agent_caused",
                contract="calculation_uncertainty",
                affects=("discrimination_and_uncertainty", "bounded_decision_and_claims"),
            ),
        ],
        "probability_and_calibration": [
            _atom(
                "probability_accuracy_valid",
                bool((diagnostics.get("primary_properties") or {}).get("PROBABILITY_ACCURACY")),
                cause="agent_caused",
                contract="criterion_property_metric_binding; calculation_parameters",
                affects=("probability_and_calibration", "bounded_decision_and_claims"),
            ),
            _atom(
                "calibration_valid",
                bool((diagnostics.get("primary_properties") or {}).get("CALIBRATION")),
                cause="agent_caused",
                contract="criterion_property_metric_binding; calculation_parameters",
                affects=("probability_and_calibration", "bounded_decision_and_claims"),
            ),
        ],
        "threshold_utility": [
            _atom(
                "threshold_utility_valid",
                bool((diagnostics.get("primary_properties") or {}).get("THRESHOLD_UTILITY")),
                cause="agent_caused",
                contract="intended_use_parameter_binding; calculation_parameters",
                affects=("threshold_utility", "bounded_decision_and_claims"),
            )
        ],
        "context_robustness": [
            _atom(
                "context_robustness_valid",
                bool((diagnostics.get("primary_properties") or {}).get("CONTEXT_ROBUSTNESS")),
                cause="agent_caused",
                contract="criterion_property_metric_binding",
                affects=("context_robustness", "bounded_decision_and_claims"),
            )
        ],
        "decision_relevant_followup": [
            _atom(
                name,
                bool(resource.get(name)),
                cause=(
                    "agent_caused"
                    if name
                    in {
                        "declared_material_correct",
                        "declared_effect_correct",
                        "evidence_bound_to_revision",
                        "assessment_matches_commitment",
                        "resource_calculations_valid",
                    }
                    else "agent_or_external_evidence"
                ),
                contract=f"resource_question_and_use:{name}",
                affects=("decision_relevant_followup", "bounded_decision_and_claims"),
            )
            for name in (
                "question_relevant",
                "returned_evidence_authentic",
                "returned_result_correct",
                "declared_material_correct",
                "declared_effect_correct",
                "evidence_bound_to_revision",
                "assessment_matches_commitment",
                "resource_calculations_valid",
            )
        ],
        "belief_revision": [
            _atom(
                "numeric_belief_revision_matches_verified_effect",
                requirements.get("belief_revision") is not None
                and requirements["belief_revision"].passed,
                cause="agent_caused",
                contract="belief_revision_against_contingency",
                affects=("belief_revision",),
            )
        ],
        "bounded_decision_and_claims": [
            _atom(
                "decision_and_claim_scope_supported",
                requirements.get("bounded_decision_and_claims") is not None
                and requirements["bounded_decision_and_claims"].passed,
                cause="agent_caused",
                contract="decision_from_criteria_and_followup; claim_scope_evidence",
                affects=("bounded_decision_and_claims",),
            )
        ],
    }

    failures: dict[str, Any] = {}
    for requirement_id in grade.mission_failures:
        atoms = predicates.get(requirement_id, [])
        false_count = sum(not row["value"] for row in atoms)
        weight = float(WEIGHTS.get(requirement_id, 0))
        for row in atoms:
            row["counterfactual_score_impact"] = (
                weight if not row["value"] and false_count == 1 else 0.0
            )
        failures[requirement_id] = {
            "atomic_predicates": atoms,
            "dependency_chain": PROPERTY_DEPENDENCIES.get(requirement_id, {}),
            "property_points_observed": float(
                (diagnostics.get("property_points") or {}).get(requirement_id, 0.0)
            ),
            "maximum_property_points": weight,
        }

    # The RC5 hidden/public divergence is retained as forensic evidence only.
    if resource.get("question_relevant") is True:
        failures.setdefault("decision_relevant_followup", {}).setdefault(
            "score_inert_evaluator_diagnostics", []
        ).append(
            {
                "predicate_id": "rc5_hidden_x24_generic_primary_gate",
                "value_in_rc5": False,
                "value_in_rc6": True,
                "cause": "evaluator_caused",
                "counterfactual_score_impact": 0.0
                if not resource.get("declared_material_correct")
                else None,
                "affects": ["decision_relevant_followup", "bounded_decision_and_claims"],
            }
        )
    return {
        "failed_properties": failures,
        "calculation_faults": {
            key: value.get("faults")
            for key, value in calculation_results.items()
            if isinstance(value, dict) and value.get("faults")
        },
        "prose_scored": False,
    }


def verify_case1_rc6_submission(
    project_root: Path, workspace: Path, submission: dict[str, Any]
) -> OpenGrade:
    """Grade RC5-compatible evidence with the canonical public resource path."""

    captured: dict[str, Any] = {}
    with INHERITED_EXTENSION_LOCK:
        original = inherited._resource_result_rc5  # noqa: SLF001

        def capture(
            current_workspace: Path,
            current_submission: dict[str, Any],
            current_calculations: dict[str, Any],
            *_rest: Any,
        ) -> Any:
            facts = evaluate_resource_semantics(
                current_workspace, current_submission, current_calculations
            )
            captured.update(facts.to_dict())
            return resource_result_from_semantics(facts)

        try:
            inherited._resource_result_rc5 = capture  # type: ignore[assignment]  # noqa: SLF001
            grade = inherited.verify_case1_rc5_submission(
                project_root, workspace, submission
            )
        finally:
            inherited._resource_result_rc5 = original  # type: ignore[assignment]  # noqa: SLF001

    diagnostics = dict(grade.diagnostics)
    diagnostics.update(
        {
            "verifier_version": "case1-rc6",
            "resource_semantics": captured,
            "public_hidden_resource_semantics_equal": bool(
                (diagnostics.get("resource") or {}).get("relevant")
                == captured.get("question_relevant")
                and (diagnostics.get("resource") or {}).get("material")
                == captured.get("expected_material")
                and (diagnostics.get("resource") or {}).get("observed_effect")
                == captured.get("expected_effect")
            ),
        }
    )
    interim = replace(grade, diagnostics=diagnostics)
    diagnostics["causal_grading"] = _causal_diagnostics(interim)
    return replace(interim, diagnostics=diagnostics)


__all__ = ["WEIGHTS", "verify_case1_rc6_submission"]

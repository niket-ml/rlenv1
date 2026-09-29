"""Agent-visible v0.8 development contract and condition-specific decision rules."""

from __future__ import annotations

from uc_bench.v07_runner import V07RunConfig, v07_scientific_system_prompt
from uc_bench.v072_interface import V072_AGENT_CONTRACT

_PREFIX = V072_AGENT_CONTRACT.split("C4 must be saved before purchase", 1)[0]

V08_AGENT_CONTRACT = (
    _PREFIX.replace("V0.7.2", "V0.8 DEVELOPMENT").replace(
        '"0.7.2-submission-1"', '"0.8-development-submission-1"'
    )
    + r"""C4 must be saved before purchase and contains:
- diagnosed_concepts and competing_explanations arrays;
- decision_question: CURRENT_PROBABILITY_USE, PATIENT_IDENTITY, TRANSPORT, or
  CLEAN_PIPELINE_SIGNAL;
- chosen_resource: exact ID none, X17, X24, X31, X46, X58, or X63;
- why_decision_resolving: a free-text explanation tied to the declared question;
- resource_comparison: array of objects with resource_id and limitations;
- resource_limitations_considered boolean;
- prediction_before_investigation with explicit belief_before and at least two
  result_contingent_actions;
- initial_decision, using the complete decision object defined below;
- evidence_refs including diagnosis, resource_choice, and
  pre_investigation_prediction.
The actual chosen resource and timing come only from the environment event log.
The machine checks the disclosed decision_question/resource pairing; it does not
search the explanation for preferred words.

C5 fields after purchase:
- investigation_analysis with new_evidence_received, calculated_values,
  resolved_patient_count, and site_blocker_remaining. Use null where a
  case-specific value is not applicable; calculated_values uses exact metric IDs.
  It must also include artifact_manifest.calculated_outputs_path and a nonempty
  evidence_paths array. The saved JSON must contain calculated_values and the
  evidence paths used. Save this even when the correct result is no new numeric
  calculation (for example after choosing none or an identity crosswalk).
- belief_change with target_hypothesis, numeric support_probability_before and
  support_probability_after in [0,1], and a nonempty evidence array. The grader
  checks only the evidence-supported direction, not one exact probability.
- decision, with development_stage (DISCOVERY, INTERNAL_VALIDATION,
  EXTERNAL_VALIDATION, PROSPECTIVE_EVALUATION, or STOPPED), disposition
  (CONTINUE, PAUSE, STOP, or INSUFFICIENT_EVIDENCE), and arrays allowed_use,
  unresolved_gates, prohibited_use, and required_next_evidence. This is the final
  decision; do not substitute a bare ADVANCE or CONDITIONAL_ADVANCE label.
- claims.supported, claims.prohibited, and claims.asserted arrays of claim IDs;
- remaining_uncertainties array;
- preprocessing_and_contamination.original_contaminated_result_eligible boolean;
- evidence_refs including followup, belief_update, decision, and claims.

The initial_decision and final decision use the same complete object. A
conditional conclusion is expressed through its development stage, disposition,
allowed use, unresolved gates, prohibited use and required next evidence—not an
extra preferred phrase.

The saved follow-up calculation JSON is verified against returned raw evidence.
The hidden verifier independently reconstructs important calculations. Optional
sensitivity calculations are diagnostic only and cannot invalidate correct
primary work. The latest schema-valid save is authoritative; a rejected save may
be corrected. All machine-enforced names, enums, paths and action ordering are
stated here. Scientific explanations are graded by evidence-supported properties,
never exact wording.

The environment event record—not prose or duplicated checkpoint text—is the
only authority for tool calls, commitment/reveal order, C4-before-purchase,
resource purchase/cost, and submission. Missing or invalid individual fields lose
only their affected scientific checks unless no usable analysis exists. Schema,
parsing, model completion, provider, and infrastructure status are reported
separately. Full mission success requires every decision-critical scientific
requirement; partial work quality is reported separately.
"""
).strip()


_CONDITION_RULES: dict[str, str] = {
    "case_01": (
        "For CURRENT_PROBABILITY_USE, choose none when the current evidence already "
        "supports a bounded research continuation. Choose X31 with "
        "CLEAN_PIPELINE_SIGNAL only when minor execution uncertainty is still the "
        "question that must be resolved."
    ),
    "case_02": (
        "Choose X17 only with PATIENT_IDENTITY when reconciling source-patient identity "
        "is the immediate unresolved question. Choose X46 only with TRANSPORT when a "
        "matched external cohort is needed to decide transport. Choose none only with "
        "CURRENT_PROBABILITY_USE when the existing patient/site evidence already makes "
        "the immediate advancement decision PAUSE or STOP and causal resolution is not "
        "needed for that decision. All three choices are valid only when the saved "
        "evidence supports the declared question."
    ),
    "case_03_signal_collapses": (
        "The decision question is CLEAN_PIPELINE_SIGNAL and the decision-resolving "
        "resource is X31, because the original contaminated result is ineligible and a "
        "clean replay tests whether the locked signal survives."
    ),
    "case_03_signal_remains": (
        "The decision question is CLEAN_PIPELINE_SIGNAL and the decision-resolving "
        "resource is X31. If the clean replay is valid and retains signal, numeric belief "
        "must increase from its pre-investigation value and the final decision must "
        "recover toward bounded research continuation. No exact probability or phrase is "
        "required. Clinical, treatment-effect and safe-threshold claims remain prohibited."
    ),
    "case_04": (
        "The immediate aim is to decide whether the locked probabilities support current "
        "probability-based use. Choose none with CURRENT_PROBABILITY_USE when existing "
        "calibration and utility evidence already resolves that decision as PAUSE or STOP. "
        "Choose X46 only with TRANSPORT when you explicitly make transport—not current-use "
        "eligibility—the unresolved question. Unnecessary purchasing is not rewarded."
    ),
}


def v08_scientific_system_prompt(
    task_text: str, config: V07RunConfig, *, condition_id: str
) -> str:
    """Build the exact native prompt without exposing private case truth."""

    if condition_id not in _CONDITION_RULES:
        raise ValueError(f"Unknown v0.8 condition: {condition_id}")
    return (
        v07_scientific_system_prompt(task_text, config)
        + "\n\n"
        + V08_AGENT_CONTRACT
        + "\n\nCONDITION-SPECIFIC DECISION RULE (AGENT VISIBLE)\n"
        + _CONDITION_RULES[condition_id]
    )


def v08_condition_rule(condition_id: str) -> str:
    return _CONDITION_RULES[condition_id]


__all__ = ["V08_AGENT_CONTRACT", "v08_condition_rule", "v08_scientific_system_prompt"]

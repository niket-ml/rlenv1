"""Final agent-visible MMMVP contract over the unchanged five investigations."""

from __future__ import annotations

from uc_bench.v07_runner import V07RunConfig, v07_scientific_system_prompt
from uc_bench.v08_interface import V08_AGENT_CONTRACT, v08_condition_rule

CLAIM_DEFINITIONS = r"""
The claim IDs have these complete meanings:
- research_use_prognostic_validation: the predictor may proceed only to bounded
  research validation for the stated prognostic intended use;
- naive_row_performance_not_decision_valid: biopsy-row performance is not valid
  evidence for a patient-level development decision;
- original_validation_invalid: the originally reported validation is invalid;
- ranking_signal_only: the evidence supports ranking/discrimination only, not
  calibrated probability use;
- independent_validation_passed: an independent external validation has passed;
- safe_threshold_use: the locked probabilities have demonstrated safe utility at
  the stated decision threshold;
- clinical_utility_proven: prospective clinical utility has been established;
- treatment_effect: the predictor estimates differential treatment effect rather
  than prognosis;
- all_platforms: the result is established across all relevant assay platforms.
""".strip()


MMMVP_AGENT_CONTRACT = (
    V08_AGENT_CONTRACT.replace("V0.8 DEVELOPMENT", "UC-BENCH MMMVP")
    .replace('"0.8-development-submission-1"', '"mmmvp-submission-1"')
    .replace(
        "- prediction_before_investigation with explicit belief_before and at least two\n"
        "  result_contingent_actions;",
        "- prediction_before_investigation with target_hypothesis_id exactly\n"
        "  PREDICTOR_SUPPORTS_INTENDED_USE_ADVANCEMENT, numeric belief_before in\n"
        "  [0,1], and at least two result_contingent_actions;",
    )
    .replace(
        "- belief_change with target_hypothesis, numeric support_probability_before and\n"
        "  support_probability_after in [0,1], and a nonempty evidence array. The grader\n"
        "  checks only the evidence-supported direction, not one exact probability.",
        "- belief_change with target_hypothesis_id exactly\n"
        "  PREDICTOR_SUPPORTS_INTENDED_USE_ADVANCEMENT, numeric\n"
        "  support_probability_before and support_probability_after in [0,1], and a\n"
        "  nonempty evidence array. The target and before value must equal the C4\n"
        "  commitment. The grader checks the evidence-supported direction, not one\n"
        "  exact probability.",
    )
    .replace(
        "- preprocessing_and_contamination.original_contaminated_result_eligible boolean;\n",
        "",
    )
    .replace(
        "- diagnosed_concepts array and metrics_interpreted_together boolean;",
        "- diagnosed_concepts array and metrics_interpreted_together boolean;\n"
        "- preprocessing_and_contamination contains established_contamination and\n"
        "  primary_evidence_eligible booleans. Set the former from the supplied fit\n"
        "  lineage. Primary evidence is ineligible exactly when validation rows entered\n"
        "  fitting; a clean case must not be labelled contaminated;",
    )
    + "\n\n"
    + CLAIM_DEFINITIONS
    + r"""

The C5 claims.supported, claims.prohibited and claims.asserted arrays use only
those IDs. `supported` means established by the completed evidence chain;
`prohibited` means not justified for the final scope; `asserted` means actually
asserted in the diligence conclusion. An asserted claim must also be supported
and must not be prohibited. The verifier never searches prose for a claim ID.

The numeric belief target is always the single disclosed hypothesis:
PREDICTOR_SUPPORTS_INTENDED_USE_ADVANCEMENT. Its meaning is that the locked
predictor has enough valid evidence to advance one development stage for its
stated intended use; it never by itself means clinical utility, treatment effect,
safe deployment or universal transport. Choosing `none` yields no new evidence,
so belief must remain unchanged where the condition rule says UNCHANGED.
"""
).strip()


_FINAL_RULE_ADDITIONS = {
    "case_01": (
        " Belief in PREDICTOR_SUPPORTS_INTENDED_USE_ADVANCEMENT may stay unchanged "
        "or increase after the selected action."
    ),
    "case_02": (
        " With none, belief must stay unchanged because no evidence was purchased. "
        "With X17 or X46 it may stay unchanged or decrease, but must not increase while "
        "the patient/site blocker remains."
    ),
    "case_03_signal_collapses": (
        " The valid collapse must decrease belief in "
        "PREDICTOR_SUPPORTS_INTENDED_USE_ADVANCEMENT."
    ),
    "case_03_signal_remains": (
        " The valid retained signal must increase belief in "
        "PREDICTOR_SUPPORTS_INTENDED_USE_ADVANCEMENT."
    ),
    "case_04": (
        " With none, belief must stay unchanged because no evidence was purchased. "
        "The X46 result, if selected for TRANSPORT, must decrease belief when its "
        "recomputed calibration and utility failure persists."
    ),
}


def mmmvp_condition_rule(condition_id: str) -> str:
    if condition_id not in _FINAL_RULE_ADDITIONS:
        raise ValueError(f"Unknown MMMVP condition: {condition_id}")
    return v08_condition_rule(condition_id) + _FINAL_RULE_ADDITIONS[condition_id]


def mmmvp_scientific_system_prompt(
    task_text: str,
    config: V07RunConfig,
    *,
    condition_id: str,
) -> str:
    return (
        v07_scientific_system_prompt(task_text, config)
        + "\n\n"
        + MMMVP_AGENT_CONTRACT
        + "\n\nCONDITION-SPECIFIC DECISION RULE (AGENT VISIBLE)\n"
        + mmmvp_condition_rule(condition_id)
    )


__all__ = [
    "CLAIM_DEFINITIONS",
    "MMMVP_AGENT_CONTRACT",
    "mmmvp_condition_rule",
    "mmmvp_scientific_system_prompt",
]

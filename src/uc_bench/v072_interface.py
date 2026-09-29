"""Agent-visible v0.7.2 contract; hidden grading introduces no extra interface rules."""

from __future__ import annotations

from uc_bench.v07_runner import V07RunConfig, v07_scientific_system_prompt

V072_AGENT_CONTRACT = r"""
V0.7.2 MACHINE-READABLE SUBMISSION CONTRACT

Every checkpoint payload_json must be a JSON object with
"schema_version":"0.7.2-submission-1". Put the documented fields either directly
at the checkpoint root or together under a "facts" object. Do not put different
values in both locations. Extra "explanation" or "annotations" fields are saved
for human inspection but are never used to infer a fact, action, decision, claim,
or belief. Exact matching is used only for the enums, resource IDs, metric IDs,
and artifact column contracts stated below.

The complete machine-readable concept registry is:
- scientific finding IDs: minor_execution_uncertainty, miscalibration,
  negative_threshold_utility, patient_dependence, preprocessing_fit_scope,
  signal_supported, site_confounding, validation_information_leakage;
- nonmaterial finding IDs: batch_alias_typo, duplicate_assay_export,
  minor_endpoint_disagreement, noncausal_clock_skew,
  two_missing_noncritical_covariates;
- claim IDs: all_platforms, clinical_utility_proven,
  independent_validation_passed, naive_row_performance_not_decision_valid,
  original_validation_invalid, ranking_signal_only,
  research_use_prognostic_validation, safe_threshold_use, treatment_effect.
Do not invent another exact ID. If a nuance is not captured by an ID, place it
in free text and use the closest supported ID only when scientifically justified.

Machine-checked evidence groups are also explicit. Analysis-unit conclusions
must cite data/cohort_metadata.csv and data/endpoint_source_ledger.csv.
Quantitative conclusions must cite data/locked_predictions.csv and
revealed/validation_outcomes.csv. Pipeline-scope or contamination diagnoses must
cite pipeline/preprocess.py, pipeline/fit_membership.csv, and
logs/execution_log.csv. Resource conclusions must cite followup_catalog.json and,
after purchase, the relevant purchased/<resource>/ files. Derived work artifacts
may be cited in addition but do not replace the underlying evidence.

C1 fields:
- analysis_unit: {"level":"PATIENT|BIOPSY|SITE","patient_key":"..."};
- cohort_counts: {"sample_count":number,"patient_count":number,
  "site_count":number,"patient_count_by_site":object};
- checks: dependence_inspected, site_distribution_inspected, and
  endpoint_timing_checked (booleans);
- findings: diagnosed_concepts (IDs), nonmaterial_findings (IDs), and
  nonmaterial_finding_is_blocker (boolean);
- remaining_uncertainties (array);
- evidence_refs: object mapping each important conclusion ID to an array of
  workspace-relative paths. Include at least analysis_unit, cohort_counts, and
  findings.

C2 must be committed before reveal and contains:
- validation_plan.analysis_unit in the C1 form;
- validation_plan.aggregation_method: MEAN, MEDIAN, or FIRST_LOCKED;
- validation_plan.preprocessing.fit_scope: TRAINING_ONLY or
  LOCKED_TRAINING_ONLY, plus outcome_blind boolean;
- validation_plan.uncertainty: method (free text),
  preserves_patient_dependence boolean, site_aware boolean, random_seed integer,
  and bootstrap_replicates integer from 200 through 10000. The seed and replicate
  count are chosen and committed by you; the verifier uses these declared values
  and introduces no hidden random seed;
- validation_plan.primary_metric_ids: use exact IDs auc, brier, ece, and
  net_benefit for decision-primary metrics; auc_ci_low is calculated with auc;
- validation_plan.sensitivity_metric_ids (exact metric IDs where applicable);
- validation_plan.ece_bins: integer 2-20;
- validation_plan.decision_rules and competing_hypotheses arrays;
- evidence_refs including validation_plan.
The C2 primary_metric_ids control grading. A value placed only in sensitivity
metrics is never substituted for a declared primary result.

C3 fields after reveal:
- primary_metrics: exact numeric keys auc, auc_ci_low, brier, ece, net_benefit;
- sensitivity_metrics: optional numeric keys naive_row_auc, site_weighted_auc,
  and worst_site_auc, separate from primary_metrics;
- execution: patient_dependence_preserved, site_aware_analysis, and
  uncertainty_matches_plan booleans;
- preprocessing_and_contamination: contaminated_evidence_eligible and
  established_contamination booleans plus findings array;
- diagnosed_concepts array and metrics_interpreted_together boolean;
- artifact_manifest with three workspace-relative paths:
  patient_table_path, preprocessing_fit_path, calculated_outputs_path;
- evidence_refs including primary_metrics and contamination.

The patient-table CSV is the saved underlying analysis artifact. Its required
columns are patient_key, site, probability, outcome, split, sample_ids. It must
contain one row per analysis patient; split must be VALIDATION; sample_ids joins
multiple contributing samples with |. It jointly records patient mapping,
predictions, labels, and split. The preprocessing-fit CSV must contain sample_id,
cohort_role,included_in_reference_fit. The calculated-output JSON must contain
objects primary_metrics and sensitivity_metrics using the metric IDs above.
The hidden verifier independently reconstructs patient mappings, aggregation,
labels, fit membership, metrics, and uncertainty from the supplied raw evidence.
Reported constants without matching saved artifacts receive no numeric credit.

C4 must be saved before purchase and contains:
- diagnosed_concepts and competing_explanations arrays;
- chosen_resource: exact ID none, X17, X24, X31, X46, X58, or X63;
- resource_comparison: array of objects with resource_id and limitations;
- resource_limitations_considered boolean;
- prediction_before_investigation with explicit belief_before and at least two
  result_contingent_actions;
- evidence_refs including diagnosis, resource_choice, and
  pre_investigation_prediction.
The actual chosen resource and timing come only from the environment event log.

C5 fields after purchase:
- investigation_analysis with new_evidence_received, calculated_values,
  resolved_patient_count, and site_blocker_remaining. Use null where a
  case-specific value is not applicable; calculated_values uses exact metric IDs;
- belief_update with explicit before, after, and direction. Direction enum:
  UNCHANGED_SUPPORTED, MODEST_INCREASE, DECREASE_SITE_BLOCKER_REMAINS,
  LARGE_DECREASE, INCREASE_AFTER_VALID_REPLAY, or
  DECREASE_UTILITY_CONCERN_CONFIRMED;
- decisions.initial and decisions.final. Each is exactly ADVANCE,
  CONDITIONAL_ADVANCE, PAUSE, STOP, or INSUFFICIENT_EVIDENCE. You may instead use
  {"decision":"ENUM"} at either position. Prose such as "no advancement" is not
  interpreted as an enum;
- claims.supported, claims.prohibited, and claims.asserted arrays of claim IDs;
- remaining_uncertainties array;
- preprocessing_and_contamination.original_contaminated_result_eligible boolean;
- evidence_refs including followup, belief_update, decision, and claims.

The environment event record—not prose or duplicated checkpoint text—is the
only authority for tool calls, commitment/reveal order, C4-before-purchase,
resource purchase/cost, and submission. Missing or invalid individual fields lose
only their affected scientific checks unless no usable analysis exists. Schema,
parsing, model completion, provider, and infrastructure status are reported
separately. Full mission success requires every decision-critical scientific
requirement; partial work quality is reported separately.
""".strip()


def v072_scientific_system_prompt(task_text: str, config: V07RunConfig) -> str:
    """Append only the disclosed interface contract to the unchanged v0.7 prompt."""

    return v07_scientific_system_prompt(task_text, config) + "\n\n" + V072_AGENT_CONTRACT

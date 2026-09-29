# Locked anti-TNF predictor diligence — semantic artifact workflow

You are the cross-functional technical diligence lead for a locked baseline-
biopsy transcriptomic predictor. Your job is not to optimize the predictor.
Determine which evidence is valid, what can be claimed, whether the asset should
advance, and which single next investment has the highest decision value.

This is one persistent decision chain. Produce ten compact artifacts whose
dependencies reflect real professional work:

| Stage | Required artifact | Purpose |
|---:|---|---|
| 1 | `submission/cohort_inventory.csv` | Reconcile cohort roles, drugs, endpoints, platforms, visibility, rows, patients, and missingness. |
| 2 | `submission/provenance_audit.json` | Verify source integrity and distinguish evidence from sponsor attestations. |
| 3 | `submission/patient_visit_map.csv` | Preserve patient/visit identity, repeated measures, exclusions, unresolved links, and dependence clusters. |
| 4 | `submission/endpoint_audit.json` | State the target, timing, label sources, ambiguities, and admissible endpoint scope. |
| 5 | `submission/preprocessing_lineage.json` | Trace transformation fit cohorts, outcome visibility, validation refits, platforms, and leakage. |
| 6 | `submission/reproduction_predictions.csv` | Independently reproduce the supplied locked-model reference predictions. |
| 7 | `submission/committed_validation_plan.json` | Fix the estimand, dependence-aware uncertainty, metrics, sensitivity analyses, hypotheses, and decision rule before reveal. |
| 8 | `submission/validation_results.json` | Execute the committed internal/external validation and delimit claim scope. |
| 9 | `submission/resource_value_memo.json` | Compare the available resources against live competing hypotheses and choose exactly one or `none`. |
| 10 | `submission/final_diligence_report.json` | Revise beliefs after the follow-up and make a supported final decision and recovery plan. |

## Artifact interfaces

The JSON schemas define a small collection interface, not a preferred analysis
method. Extra fields are allowed. Free-text explanations and method names are
not graded by exact wording. Scientific credit follows checkable properties and
evidence. CSV column order is irrelevant; additional columns are allowed.
In the committed plan, the four `reports_*` booleans declare whether the plan
actually reports discrimination, uncertainty, calibration, and decision
utility; they do not prescribe the estimator used.

Required CSV columns:

- `cohort_inventory.csv`: `cohort_id`, `role`, `row_count`, `patient_count`,
  `drug`, `endpoint`, `timepoint`, `platform`, `outcome_visibility`,
  `eligibility_status`, `evidence_refs`.
- `patient_visit_map.csv`: `sample_id`, `reported_patient_id`,
  `canonical_patient_id`, `fingerprint_group`, `visit_label`,
  `baseline_eligible`, `dependence_cluster`, `linkage_status`,
  `exclusion_reason`, `evidence_refs`.
- `reproduction_predictions.csv`: `sample_id`, `reference_probability`,
  `reproduced_probability`, `absolute_error`, `model_sha256`.

Use `;` inside a CSV cell for multiple evidence paths. Evidence references must
point to actual workspace files. It is valid to mark a linkage, endpoint, or
claim unresolved when the available evidence cannot resolve it.

## Irreversible sequence

1. Inspect `case/`, `data/`, `model/`, `resources/`, and `schemas/`.
2. Produce artifacts 1–7.
3. Call `commit_validation_plan`. The presence or absence and content of all
   seven pre-reveal artifacts, the locked model, and declared analysis files are
   hashed. This is irreversible.
4. Call `reveal_validation` once.
5. Produce `validation_results.json` and `resource_value_memo.json`.
6. Call `request_followup`. The memo and selected resource become immutable;
   only that resource packet is revealed.
7. Produce `final_diligence_report.json` and call `submit_diligence`.

You may use frequentist, Bayesian, grouped-bootstrap, mixed-model, hierarchical,
or sensitivity-analysis approaches. The method must preserve patient
dependence, use only outcome-blind preprocessing, match the intended estimand,
and support the claims made. A different valid method is not an error.

Advancing is not intrinsically rewarded. Correct containment, conditional
conclusions, recovery, and justified abstention receive scientific credit.
Unnecessary escalation is penalized when evidence is sufficient. If one
artifact is invalid, identify which descendants are at risk and continue work
that remains valid.

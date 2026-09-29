# Locked anti-TNF predictor diligence

You are the technical diligence lead for a locked baseline-biopsy transcriptomic
predictor. Your job is not to improve the predictor. Decide which claims are
currently admissible, whether the asset should advance, and which single
follow-up resource has the highest decision value.

This is one persistent case. Findings propagate: an unresolved identity problem
changes the valid analysis unit; an invalid endpoint changes what performance
means; a leaky preprocessing step invalidates affected estimates; and a cohort
that differs in endpoint, drug, or platform may not support the intended-use
claim. A blocker does not require you to abandon the rest of the audit. Detect
it, contain the affected claims, continue valid work, and state the smallest
next action.

## Start state

Inspect every ordinary diligence artifact under:

- `case/`: intended use, cohort registry, provenance, and preprocessing history;
- `data/`: patient/visit records and locked predictions with validation outcomes
  withheld;
- `model/`: immutable model, feature contract, reproduction inputs, and reference
  predictions;
- `resources/resource_catalog.json`: the six available follow-up investments;
- `schemas/`: the three small machine-readable action contracts.

You may use shell commands and Python freely. No particular statistical package,
test name, or implementation is required. Support conclusions with paths and
observable values. If evidence cannot identify one cause, retain competing
hypotheses rather than guessing private truth.

## Workflow

1. Audit intended use, provenance, patient/visit identity, missingness, endpoint
   construction, assay/platform compatibility, preprocessing scope, and baseline
   reproduction.
2. Write `submission/commitment.json`. The structured statuses are a claim-
   eligibility ledger, not a request for boilerplate. Include at least two live
   hypotheses and a validation plan appropriate to the evidence.
3. Call `commit_validation_plan`. This hashes the commitment, locked predictor,
   and the analysis artifacts you name. It is irreversible.
4. Call `reveal_validation`. Sealed external outcomes become available once.
   Analyze them without changing committed artifacts.
5. Write `submission/validation_assessment.json`, including discrimination,
   uncertainty, calibration, threshold utility, the provisional decision, and a
   request for exactly one resource or `none`.
6. Call `request_followup`. The assessment and resource choice are locked. Only
   that resource packet is revealed. A resource may resolve the blocker, reduce
   uncertainty, expose another blocker, be ineffective, or provide misleading
   reassurance.
7. Analyze the follow-up evidence. Write `submission/final_submission.json` and
   call `submit_diligence`.

Decisions may be `advance`, `conditional_advance`, `pause`, `stop`, or
`insufficient_evidence`. Advancing is not intrinsically better than stopping.
Unnecessary escalation is penalized when current evidence is sufficient; false
certainty is penalized when no available intervention resolves the evidence.

The private grader recomputes numerical evidence and evaluates scientific
properties: valid analysis unit, endpoint coherence, leakage containment,
transportability, calibration and utility, prospective commitment, value of
information, belief revision, reproducibility, and graceful abstention. It does
not reward exact prose or one reference narrative.


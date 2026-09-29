# UC-Bench v0.6: semantic evidence-chain diligence

Status: **implemented locally, not frozen, compatibility passed, no v0.6
scientific-task exposure**.

v0.6 asks an agent to decide whether a locked baseline-biopsy anti-TNF response
predictor should advance, what remains uncertain, and which one next investment
has the greatest decision value. It does not reward training a better model.
Finding that the evidence is inadequate is success when that conclusion is
supported and the invalid claims are contained.

v0.5 and all of its diagnostic results remain unchanged. v0.6 is a separately
versioned successor to address two v0.5 no-go findings: exact-vocabulary
dependence and concentration of the model gap in one state.

## State and artifact DAG

```text
data room
  ├── A01 cohort inventory ─────┬── A03 patient/visit map ─┐
  ├── A02 provenance audit ─────┼── A04 endpoint audit ────┤
  └── locked assay/model ───────┴── A05 lineage ───────────┤
                                  A06 reproduction ────────┤
                                                          ▼
                                               A07 committed plan
                                                          │ irreversible
                                                          ▼
                                               sealed outcome reveal
                                                          ▼
                                               A08 validation results
                                                          ▼
                                               A09 resource-value memo
                                                          │ irreversible
                                                          ▼
                                               one follow-up packet
                                                          ▼
                                               A10 final diligence report
```

The commit hashes the presence or absence and content of A01–A07, the locked
model, and declared analysis files. Missing work is therefore visible, but an
agent may still commit, contain the limitation, and earn later recovery credit.
The resource memo is immutable after the selected packet is revealed.

## Task-justification cards

| Artifact | Professional owner | Decision affected | Consequence of failure | Valid alternatives | Grader invariants | Paired remedy | Why it is substantive |
|---|---|---|---|---|---|---|---|
| A01 `cohort_inventory.csv` | Data curator and clinical data lead | Which rows and cohorts are eligible for each claim | Mismatched evidence enters validation | Long-form or cohort-level reconciled inventory | Source cohorts, roles, drug/endpoint/platform, rows and patients reconcile | Source data-room reconciliation | Cohort role determines evidence admissibility |
| A02 `provenance_audit.json` | Governance and reproducibility lead | Whether a source is intact and decision-eligible | Sponsor claims or altered files become ground truth | Hash manifest or independent source ledger | Assets checked, attestations remain unverified, labels sealed, licence bounded | Curated provenance metadata | Provenance changes what can be claimed |
| A03 `patient_visit_map.csv` | Clinical curator and biostatistician | Analysis and uncertainty unit | Repeated biopsies become independent patients | Canonical, fingerprint, or probabilistic linkage | All rows accounted for, repeats clustered, unresolved links contained | Source-record crosswalk | Dependence changes estimates and intervals |
| A04 `endpoint_audit.json` | IBD endpoint expert | Outcome meaning and timing | Clinical response, remission, or healing are collapsed | Primary plus sensitivity, latent-label, or adjudication plan | Target/time explicit, sources retained, ambiguity contained, transfer bounded | Blinded adjudication or endpoint-matched cohort | Endpoint meaning changes intended use |
| A05 `preprocessing_lineage.json` | Platform specialist and ML validator | Whether predictions are leakage-safe | Validation-fitted transforms inflate results | Frozen training transform, outcome-blind bridge, prospective ranks | Fit cohorts and label access recorded, refit detected, platform mismatch contained | Locked leakage-safe rerun | A plausible score may be scientifically invalid |
| A06 `reproduction_predictions.csv` | ML validation engineer | Whether the supplied predictor is actually immutable | A different model is evaluated | Independent implementation, container, or verified executable | Samples preserved, numerical tolerance met, model hash unchanged | Independent replay | It tests executable identity, not a preferred tool |
| A07 `committed_validation_plan.json` | Biostatistician and validation lead | What is fixed before reveal | Post-reveal flexibility supports optimistic claims | Grouped bootstrap, robust model, hierarchical model, mixed model | Patient dependence, fit scope, estimand, metrics, decision rule, competing hypotheses | Commit enforcement plus statistical review | It makes prospective reasoning irreversible |
| A08 `validation_results.json` | Statistician and utility analyst | What the evidence establishes | Wrong unit or biased metric supports advancement | Frequentist, Bayesian, clustered, or sensitivity estimates | Plan honoured, numbers reproducible, uncertainty aligned, claims bounded | Safe reanalysis or matched evidence | Quantitative work and interpretation must agree |
| A09 `resource_value_memo.json` | Experimental-design lead | Which one investment is worth making | Money buys reassurance rather than discrimination | Qualitative, decision-tree, or Bayesian value of information | Alternatives compared, smallest discriminating resource selected, `none` allowed | Decision-relevant evidence review | Choice depends on live competing explanations |
| A10 `final_diligence_report.json` | Cross-functional diligence lead | Advance, pause, stop, or remain unresolved | Commercial action exceeds evidence | Conditional decision, early stop, or staged recovery | Decision supported, belief moves correctly, claims bounded, smallest next action correct | Identified evidence resource | The agent must revise rather than merely summarize |

## Controlled branching

The six states share one job and perturb one interacting part of its evidence
chain: clean progression, patient identity/dependence, endpoint ambiguity,
preprocessing leakage, endpoint × drug × platform transfer, and underpowered or
irreducible external evidence. The selected resource may resolve the blocker,
reduce uncertainty, expose a second blocker, fail, mislead, or correctly be
`none`.

Descendants of a bad artifact are marked **at risk**, not automatically zeroed.
Every artifact receives its own scientific-invariant score. Later artifacts can
earn credit for detecting an upstream defect, limiting claim scope, selecting a
remedy, or stopping correctly.

## Scores

Four quantities are reported rather than collapsed:

- completed-artifact quality: mean scientific quality among parseable artifacts;
- artifact coverage: the percentage present and parseable;
- coverage-adjusted scientific score: ten equal artifact weights, missing work zero;
- reliability-inclusive score: coverage-adjusted score only after accepted final submission, otherwise zero.

The report also carries artifact state, first substantive divergence,
descendants at risk, family scores, the ten-capability vector, and separate
process annotations. Schema errors do not silently change scientific scores.
Infrastructure exclusions occur outside this grader and require concrete
runtime evidence.

## Construct controls

The current zero-cost control artifact is
`artifacts/diagnostics/hard_suite_v06_controls.json`:

- reference minimum: 100;
- alternate valid workflow minimum: 100;
- paraphrase score difference: 0;
- deliberately mediocre workflow: below reference in all ten families;
- worst universal advance/abstain/stop decision-policy mean: 41.95;
- ordinary early scientific error: 98.75, demonstrating non-cascading credit;
- post-commit mutation: rejected;
- development/held-out IDs and seeds: disjoint and absent from the task text.

These are internally authored expert-equivalence controls, not external expert
validation. That limitation is acceptable for development calibration but must
be resolved before strong commercial or public construct-validity claims.

## Authentic versus controlled evidence

The controlled states establish causal failure and intervention behavior. The
authentic GEO anchor retains real source provenance and contamination caveats,
but is not pooled with controlled scores. Controlled recovery is not a new
clinical or biological claim, and authentic performance is not evidence of
model reasoning without the matched data-withheld control.

## BixBench3 boundary

> BixBench3 evaluates whether agents can execute specified study-scale
> computational analyses. UC-Bench evaluates whether agents can audit the
> validity of a biomedical evidence chain, contain invalid claims, revise
> beliefs and select the next decision-relevant experiment.

v0.6 borrows explicit artifact dependencies, depth-based diagnosis, replay, and
cost/process accounting. It does not require one published statistical method,
large data for its own sake, or exact reproduction of a paper pipeline.

## Release gates

No panel may be frozen until the exact cross-provider models pass non-scored
compatibility canaries. No scientific run may start without a new explicit cost
cap. The ceiling metric is the strongest model's mean coverage-adjusted
scientific score across accepted submissions. Completion or timeout failures
affect reliability but cannot manufacture scientific headroom; every sentinel
cell must contain a valid submission for the ceiling interpretation to proceed.

The predeclared ceiling bands are: 60–70 desired, above 70 through 75 acceptable,
above 75 through 80 insufficient headroom, above 80 a ceiling no-go, and below
60 an over-hard no-go. The strongest model must also have no more than 25% of
accepted cells at 95 or above, retain meaningful partial artifact credit, and
show material losses across at least three scientific capabilities. Each
material deduction must cite the produced artifact, its deterministic state and
score, the professional consequence, and an actionable paired remedy belonging
to additional data, labels/metadata, expert assistance, tools/process, directly
tested model adaptation, or experimental design.

No artifact family may contribute more than 30% of the strongest model's
scientific gap. Scenario concentration is reported in the two-state sentinel
but is not identifiable against a 30% cap there: one of two positive shares must
be at least 50%. The scenario gate is therefore predeclared for the complete six
development states. Reference and alternative valid workflows must remain at
least 90, graceful recovery remains independently visible, and completion
reliability remains separate. One seed is calibration, never a stable ranking.

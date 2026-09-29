# UC-Bench hard suite v0.4

## Status and claim boundary

v0.4 is a controlled biomedical-statistical simulation for calibrating agent
failure, containment, and recovery. It is not an authentic-cohort performance
claim and one seed per cell cannot establish a stable model ranking. Authentic
results remain a separate, currently empty partition.

The v0.3 development run is preserved but paused at 16 usable cells out of 30.
It is a documented ceiling failure for quantitative reasoning: GPT-5.6 Sol
averaged 98.4 on that component. v0.4 was designed and sealed before any v0.4
model call. GPT-6 Astra remains an unspent held-out ceiling probe and is not a
development model.

## What the agent does

Each episode starts with several public files: a pilot table, an intended-use
decision context, candidate estimands and analysis methods, public metric
definitions and tolerances, resource descriptions, schemas, and an evidence
manifest. Candidate IDs are options rather than answer labels.

The agent must:

1. inspect the complete start state and data structure;
2. identify the decision-relevant estimand, uncertainty unit, and analysis;
3. rank competing explanations and choose one available resource or `none`;
4. irreversibly commit the plan and resource before reveal;
5. receive only the selected resource packet;
6. recompute the required statistics and interpret them scientifically; and
7. submit an advance, stop, or insufficient-evidence decision plus the smallest
   correct recovery action.

The agent has 40 turns, 50,000 total completion tokens, and 2,400 seconds. This
generous horizon is intended to make scientific reasoning, rather than schema
or time pressure, the source of difficulty.

## Five paired task families

| Family | Quantitative composition | Effective intervention | Ineffective control | Recovery behavior |
|---|---|---|---|---|
| Q01 identity/dependence | row vs patient AUC, patient-cluster bootstrap, unique units, Kish effective n, leakage inflation, identity conflicts | patient/visit/biopsy reconciliation | more visits under unresolved IDs; clinical opinion without reconciliation | metadata resolves the inference unit |
| Q02 transport | eight endpoint × drug × platform cells, main effects, AUC-scale three-way interaction, site-cluster uncertainty | adequately sized factorial bridge matching all three factors | clinical opinion; drug/platform match with endpoint mismatch | more decision-matched data helps; advice does not identify transport |
| Q03 process confounding | naive, patient-grouped, batch-blocked AUC; batch-outcome phi; global and within-batch permutation | leakage-safe grouped and batch-blocked validation | more rows under the unsafe process; specialist review without regenerated predictions | tooling fixes execution, but residual scientific uncertainty can still require endpoint-matched replication |
| Q04 label sensitivity | reviewer agreement, kappa, extracted-label AUC, exhaustive ambiguity bounds, adjudicated AUC | blinded IBD expert endpoint adjudication | more labels under the same ambiguous extraction rule; advice without adjudication | expert adjudication helps where additional ambiguous labels do not |
| Q05 decision sufficiency | site-cluster AUC interval, Brier score, sensitivity, specificity, prevalence-standardised PPV, net benefit, achieved vs required n | powered independent intended-use replication | design advice without outcomes; small partially matched replication | additional information helps only when uncertainty and utility targets are reached |

Control variants withhold the one resolving resource. Choosing `none` and
abstaining is then correct when all available resources leave the live
explanations unresolved. Treated variants make the intervention available. If
evidence becomes sufficient, unnecessary escalation is penalized. Q03
deliberately demonstrates that a process intervention can repair execution
without resolving the scientific evidence.

No task identifies a need for prompting, retrieval, tool training, domain SFT,
RL, or preference optimization. Those remedies may be claimed only after a
future paired adaptation experiment directly tests them.

## Scoring

The 100-point score is:

- 30 quantitative statistical reasoning;
- 15 scientific diagnosis;
- 15 decision;
- 15 resource selection and value of information;
- 15 recovery design; and
- 10 immutable commitment and reproducibility.

The quantitative component separately credits estimand choice, analysis method,
uncertainty unit, and every recomputed metric. Numeric tolerances are public and
the grader independently recomputes targets. Partial-credit controls isolate a
wrong estimand, computational error, wrong interpretation, wrong decision, and
bad recovery design; they receive distinct, nonzero component deductions. A
usable unsubmitted attempt scores zero. Verified provider or infrastructure
failures are excluded.

## Breaking-point ladders

Every family has four deterministic levels and at least one reference decision
transition:

- mean rows per patient: 1.0, 1.5, 2.5, 4.0;
- joint transport signal bonus: -1.0, -0.6, -0.2, 0.2;
- batch-label correlation: 0.1, 0.3, 0.5, 0.7;
- ambiguous-label fraction: 0.05, 0.12, 0.22, 0.35; and
- replication n: 30, 55, 90, 160.

The generated reference curves are in
`artifacts/diagnostics/hard_suite_v04_ladders.json`. They establish grader and
decision-boundary behavior without model spend. Model breaking curves require
separate frozen evaluations and are not fabricated from the ten calibration
cases.

## Anti-gaming and local gates

Before model evaluation, both development and held-out partitions must pass:

- reference solver at least 95;
- deliberately mediocre solver below reference in every family;
- mechanical baseline below 60;
- universal advance/abstain/stop policies below 60;
- keyword stuffing has zero score effect;
- no answer or selected packet in the public pre-reveal workspace;
- wrong resources receive no value-of-information credit;
- component-specific partial credit behaves as declared;
- every paired intervention changes the reference decision; and
- every ladder crosses a decision boundary.

The current zero-cost artifact records all 11 gates as passed. Development and
held-out seeds are different. The held-out set remains sealed and has had zero
Astra exposures.

## Evaluation and acceptance

The bounded development calibration contains 30 cells: ten frozen development
variants × GPT-5.6 Sol, GPT-5.4, and GPT-5.2 × one attempt. It has a strict $30
incremental OpenRouter cap, live account-usage checks before each episode,
checkpointing, hash-verified resume, request pacing, no Astra, and no mid-run
tuning.

The predeclared acceptance gates are:

- strongest mean below 85, ideally 65–80;
- no more than 25% of strongest-model tasks at 95 or above;
- weakest model neither universally fails nor scores zero everywhere;
- at least three distinct interpretable substantive failure domains;
- failures involve quantitative/scientific reasoning, evidence diagnosis,
  recovery, or long-horizon execution rather than mainly schemas;
- no family explains more than 30% of the strongest-to-weakest gap;
- infrastructure failures are excluded and usable unsubmitted attempts score
  zero; and
- controlled and authentic results remain separate.

Only if every mandatory development gate passes may one separately capped
held-out Astra ceiling canary be considered. Astra at 85 or above is an explicit
no-go. Repeated seeds and uncertainty analysis are still required before any
stable ranking claim.

The primary report artifact is a model × failure-mode × intervention matrix
with paired recovery and breaking-point curves. Aggregate ordering is
secondary.

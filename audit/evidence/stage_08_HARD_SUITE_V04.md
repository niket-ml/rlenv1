# Stage 8 evidence — biomedical-statistical hard suite v0.4

Date: 2026-09-07

## Blocker and design decision

Infrastructure is ready and the OpenRouter key had $34.74101563 of its $60
limit remaining when v0.3 was paused. The blocker was benchmark validity:
v0.3's Sol quantitative component averaged 98.4, so its apparent overall
difficulty came mainly from rubric/resource judgments rather than sufficiently
hard statistical analysis.

v0.4 therefore composes five decision-relevant quantitative families:
patient-level dependence and identity, endpoint × drug × platform transport,
split and batch confounding, ambiguous-label sensitivity, and intended-use
uncertainty/utility. Each family has a control, an effective paired
intervention, ineffective resources, and a four-level breaking-point ladder.
The agent chooses the estimand and method before reveal and then computes and
interprets the answer.

## Zero-cost changes before freeze

No v0.4 model was exposed while the generators and gates were calibrated. The
initial deterministic ladder run caught and corrected three issues:

1. the transport ladder began above the decision threshold, so its four signal
   levels were shifted to span insufficient-to-advance;
2. the process ladder replaced labels without coherently regenerating scores,
   so it now generates predictions and labels from one controlled mechanism;
3. the evidence decision reported a required sample size but did not require
   that the observed sample reach it, so achieved precision is now an explicit
   advancement condition.

The precision correction invalidated the provisional held-out Q05 seed. A
zero-cost deterministic search, before model exposure, replaced 80507 with
80503; its control remains insufficient and its powered replication advances.
The effective Q04 resource was also made taxonomically explicit as expert
assistance: blinded IBD endpoint adjudication produces corrected labels, while
more labels under the same extraction rule does not help.

## Local gates

`artifacts/diagnostics/hard_suite_v04_controls.json` records 11 of 11 passing:

- reference minimum 100 across all 20 development and held-out variants;
- reference above deliberately mechanical solver in every family;
- mechanical baseline mean 35.9451, below 60;
- universal advance, insufficient-evidence, and stop means all below 36;
- keyword stuffing changes the score by zero;
- no private answer fields or selected evidence packet in held-out start states;
- component-specific partial-credit controls behave as declared;
- wrong resources receive no resource-selection credit;
- all ten development/held-out intervention pairs change reference decision;
- all five breaking ladders cross a decision boundary; and
- schema or horizon failure is not needed to create score degradation.

The controls execute zero model calls. The five ladder transitions are stored
in `artifacts/diagnostics/hard_suite_v04_ladders.json`.

## Intervention coverage

- More matched data helps while expert opinion does not: Q02 and Q05.
- Expert adjudication helps while more ambiguous labels do not: Q04.
- Better identity metadata resolves the inference unit: Q01.
- Tooling repairs leakage but does not guarantee scientific sufficiency: Q03.
- With no discriminating resource, abstention is correct: every control and the
  post-repair unresolved Q03 state.
- Where treated evidence is sufficient, unnecessary escalation is penalized.
- No model-adaptation remedy is claimed because none is directly tested.

## Frozen paid-development protocol

- Models: GPT-5.6 Sol, GPT-5.4, GPT-5.2.
- Matrix: ten development variants × three models × one seed = 30 cells.
- Maximum incremental OpenRouter spend: $30, checked from live key usage before
  every episode; estimated token costs are secondary.
- 40 turns, 50,000 total completion tokens, 2,400 seconds, and 3.25-second
  request pacing per trajectory.
- Resume verifies hashes for config, held-out manifest, ladder specification,
  controls, task, schemas, and generator/grader.
- No mid-run task or grader tuning. No Astra request.

The final analysis reports model × failure mode × intervention, paired recovery,
model × family × component, and breaking-point curves. Controlled and authentic
results are separate. Aggregate ordering is secondary and cannot become a
stable ranking without repeated seeds and uncertainty analysis.

## Freeze and repository gates

The immutable manifest was created at 2026-09-07T16:32:14Z before any v0.4
model call. It hashes 14 task, config, private-manifest, grader, runner, schema,
control, ladder, and cost-orchestration files. Immediate verification passed.

The final no-cost provider-status preflight then caught a cost-guard field-name
bug before any paid request: the runner used `remaining_usd` rather than the
actual status field `limit_remaining_usd`. The original manifest remains
unchanged. A linked amendment at 16:33:48Z records the one-line guard repair,
new orchestrator hash, parent-manifest hash, zero v0.4 requests, and zero Astra
exposures. No task, evidence, grader, prompt, model, seed, budget, or cap changed.

Repository-wide gates also passed before freeze: project doctor, audit
consistency, 108 unittest cases, the full pytest suite, and Ruff over `src/`,
`tests/`, and `scripts/`.

## Remaining blockers

The frozen development matrix is complete. One GPT-5.4 process-control attempt
ended on a transient DNS/API connection failure, was retained as infrastructure,
and was excluded. A hash-verified resume retried the same unmodified cell. The
final record contains 30 usable cells plus that one excluded attempt.

| Model | Usable cells | Mean | ≥95 | Zero | Quant | Science | Decision | VOI | Recovery |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| GPT-5.6 Sol | 10 | 80.50 | 10% | 0% | 99.59 | 46.0 | 60.0 | 100.0 | 65.0 |
| GPT-5.4 | 10 | 77.65 | 0% | 0% | 97.25 | 46.0 | 80.0 | 80.0 | 50.5 |
| GPT-5.2 | 10 | 70.35 | 0% | 0% | 92.31 | 36.0 | 50.0 | 90.0 | 44.5 |

Observed key usage increased from $25.25898437 to $30.93732022, an incremental
v0.4 spend of $5.67833585. The conservative token-price estimate was
$10.90121575. The strict incremental cap was $30. Astra requests remained zero.

The directional aggregate gradient is useful calibration evidence, not a
stable ranking. Every cell was a valid submitted episode; schema share of
failed cells was zero. Failures span quantitative estimand/uncertainty choice,
scientific diagnosis, final decisions, resource value of information, and
recovery. Notable paired behavior includes:

- GPT-5.2 transport control selected the wrong estimand and scored 58.32; the
  matched bridge repaired quantitative scoring to 100 but not its decision.
- GPT-5.4 chose an ineffective partially matched transport cohort in control,
  then recovered +12.75 when the full factorial bridge was available.
- Expert label adjudication improved GPT-5.2 by +18.5 and GPT-5.4 by +21.0, but
  Sol computed it exactly and still failed to update its decision, falling 29.
- Process repair produced heterogeneous score changes (+0.75, -14.25, -8.75)
  and correctly exposed that tooling alone does not guarantee scientific
  judgment.
- Powered replication did not produce strict behavioral recovery for any model;
  correct numeric evidence often failed to repair downstream recovery design.

## Development acceptance: no-go

Six of seven mandatory gates pass: strongest mean below 85, ceiling rate at
most 25%, weakest model nonzero, at least three substantive failure domains,
schema not primary, and no universal floor. The family-concentration gate fails:
Q03 explains 43.6% of the Sol–GPT-5.2 gap, above the frozen 30% maximum (Q01
13.3%, Q02 16.9%, Q04 9.9%, Q05 16.3%).

Two additional ideal diagnostics fail: Sol is 0.50 above the desired 65–80
range, and its quantitative component remains near ceiling at 99.59 rather than
60–85. v0.4 is materially better than v0.3 for composed, non-schema failure
diagnosis, but quantitative discrimination remains too weak and the aggregate
gap is too dependent on one family.

The decision is **NO-GO**. Do not run Astra and do not tune v0.4 after observing
these results. Any successor must be a new predeclared version that distributes
genuine quantitative difficulty across Q01/Q02/Q04/Q05 while preserving the
valid process family and graceful partial credit. Repeated seeds and held-out
uncertainty remain required before any ranking claim.

Raw calibration SHA-256:
`ae66fb1d78a3c1e53b7dfc63f9ed30de9bac0c3f1054821feeed125853650768`.

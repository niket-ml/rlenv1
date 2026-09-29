# UC-Bench hard suite v0.2

Status: frozen before any hard-suite development-model or Astra completion.

## Product claim

The primary output is a model × failure mode × intervention matrix. The suite
tests whether an agent can detect and contain a scientific evidence failure,
select the smallest correct next action, and recover when the relevant resource
is supplied. An aggregate score is secondary. No stable ranking may be claimed
from the one-seed calibration.

The suite does **not** infer that SFT, RL, retrieval, or tool training is needed
from an unaided model failure. Each intervention claim requires a predeclared
paired case. Of the model-adaptation interventions, only the expert prompting
playbook has currently been tested, and its observed effect was heterogeneous.

## Agent workflow and boundary

```text
public start state
  cohort cards + locked pilot predictions + identity fingerprints
  feature contract + batch metadata + one named resource offer
          |
          v
quantitative pre-analysis
  rank >=2 hypotheses + predeclare >=4 metrics + choose experiment
          |
          v
commit_plan  ── hashes commitment.json; irreversible
          |
          v
reveal_evidence  ── one use only
  factorial bridge + adjudicated labels + provenance + resource delivery
          |
          v
quantitative recomputation + scientific interpretation
          |
          v
submit_hard_suite
  schema support first; private grader independently recomputes all metrics
```

The agent has no network and never receives the OpenRouter key. Sealed evidence
is physically outside the mounted workspace until the commitment succeeds. The
commitment hash is checked again on submission. Unknown evidence identifiers
are rejected; extra citations to real manifest evidence are not penalized.

## Five causal intervention pairs

| family | observably wrong | ineffective/absent resource | resolving resource | smallest correct action | paired recovery target |
|---|---|---|---|---|---|
| H01 identity metadata | identical expression fingerprints have incompatible patient/visit IDs | more rows with the same ambiguity | patient/visit reconciliation | patient linkage audit | stop becomes advance only after conflicts are removed |
| H02 transfer data | endpoint × platform × drug change together and only the joint match recovers AUC | IBD expert plausibility advice | adequately sized endpoint-, drug-, and platform-matched cohort | factorial transfer bridge | abstention becomes advance with matched outcome evidence |
| H03 process vs science | apparent AUC is entangled with batch and undocumented split provenance | larger sample under the same process | leakage-safe split and provenance checks | leakage-safe reanalysis | execution is contained, but endpoint judgment remains unresolved |
| H04 label expertise | systematic endpoint-label disagreement persists in a large cohort | additional rows carrying the same labels | blinded expert endpoint adjudication | blinded label readjudication | label diagnosis disappears and locked-model evidence recovers |
| H05 evidence sufficiency | a small bridge cannot discriminate several transfer explanations | expert experiment advice without new outcomes | independent replication | independent replication | correct abstention becomes advance; further escalation is penalized |

Every task records the observed problem, detection/containment target, smallest
action, resource class, pair role, and expected resource effect in the private
specification. Recovery is reported separately for decision, detection,
containment, action selection, and total score.

## Quantitative contract

The grader recomputes 14 metrics from agent-visible CSVs:

- identity conflict count;
- required-feature retention;
- batch/outcome phi;
- pilot sample size and AUC;
- label disagreement, adjudicated AUC, and adjudication gain;
- all-matched bridge sample size and AUC;
- endpoint-, platform-, drug-, and all-matched AUC gains.

All definitions and tolerances are copied into each task's `task.json`. ROC AUC
uses a public pairwise definition. The decision thresholds are public. There are
no hidden confidence bands, grader vocabulary clues, or penalties for reasonable
extra evidence.

## Score decomposition

| component | weight | what earns credit |
|---|---:|---|
| decision | 15% | correct advance / insufficient evidence / stop |
| quantitative analysis | 20% | continuous per-metric partial credit across all 14 metrics |
| scientific diagnosis | 20% | correct primary failure and recall of interacting failures |
| evidence integration | 15% | relevant real evidence IDs; extra real citations do not hurt |
| recovery design | 15% | containment, smallest experiment, resource, intervention assessment |
| commitment and reproducibility | 15% | immutable commitment, live hypothesis, discriminating metrics and experiment |

Infrastructure failures are excluded. A usable attempt that fails to submit is
zero. Authentic and controlled variants must be reported separately.

## Breaking-point ladders

The 20 controlled levels are generated from the frozen configuration, not model
answers:

- identity conflicts: 0, 1, 2, 4 groups;
- matched-cohort sample size: 20, 35, 50, 90;
- batch/outcome phi: 0.1, 0.3, 0.5, 0.7;
- label disagreement: 0.03, 0.10, 0.20, 0.30;
- matched replication AUC: 0.55, 0.62, 0.70, 0.78.

The report plots score and correct-decision rate at every level. Each controlled
ladder already passes a local transition check: at least two distinct reference
decision/diagnosis states occur across its four levels.

## Acceptance gates

- strongest/frontier mean below 85, ideally 65–80;
- no more than 25% of frontier tasks at 95 or above;
- weakest model neither universally fails nor scores zero;
- at least three interpretable scientific, evidence, recovery, or long-horizon
  failure modes;
- JSON/schema failures are not the primary model gap;
- no family explains more than 30% of the top-to-bottom gap;
- reference solver at least 90;
- deliberately mediocre solver below reference in every family;
- universal advance, abstain, and stop policies fail;
- answer leakage, reward hacking, and partial-credit controls pass.

Only after these local gates and development-model calibration pass may one
bounded Astra ceiling canary be run. Astra at 85 or above is an explicit no-go,
not a leaderboard result.


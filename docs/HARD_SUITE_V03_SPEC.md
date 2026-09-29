# UC-Bench hard suite v0.3

Status: frozen controlled suite; one-seed development calibration in progress.

## Product claim and non-claim

The product identifies an observable evidence failure, whether the agent found
and contained it, the smallest resource that can resolve it, and whether the
agent recovers when that resource is available. The primary artifact is a
model × failure mode × intervention matrix. Aggregate scores are secondary.

The current v0.3 cases are controlled, biologically motivated fixtures. They
test agent behavior and causal intervention logic; they do not estimate the
prevalence of failures in authentic clinical data. Authentic-cohort results
must be run and reported in a separate partition.

No unaided failure identifies a need for SFT, RL, retrieval, or tool training.
A model-adaptation claim is allowed only after that exact adaptation is tested
as a paired intervention.

## Agent workflow

```text
multi-file public baseline
  cohort contracts + predictions + fingerprints + feature map + provenance
                 |
                 v
compute metrics and rank competing explanations
                 |
                 v
choose R1 / R2 / R3 / none and commit_plan
  commitment hash is irreversible
                 |
                 v
reveal_evidence once
  only the committed resource packet becomes visible
                 |
                 v
recompute + diagnose + contain + decide + propose smallest next action
                 |
                 v
submit_hard_suite
  private grader recomputes numerical truth and checks commitment immutability
```

The agent is isolated in Docker with no network or provider credentials. Sealed
packets sit outside the mounted workspace. The public schemas return precise
errors, the 32-turn/40,000-completion-token horizon is generous, and usable
unsubmitted attempts score zero. Provider and infrastructure failures are
excluded.

## Intervention pairs

The control and treated cases in a family share the same public baseline. They
differ only in whether the correct resource can be selected. If selected, only
that packet is revealed.

| family | observably wrong | ineffective resource | resolving resource | smallest correct action | expected recovery |
|---|---|---|---|---|---|
| H01 identity metadata | identical expression fingerprints carry incompatible patient/visit IDs | more rows or clinical plausibility advice | patient/visit source-record reconciliation | reconcile patient, biopsy date, and visit | conflicts disappear; decision can advance |
| H02 transfer data | only endpoint × drug × platform joint matching recovers AUC | endpoint-only or drug/platform-only cohort | adequately sized jointly matched cohort | one factorial transfer bridge | interaction becomes identifiable; decision can advance |
| H03 process vs science | high AUC is entangled with batch and unsafe split provenance | more rows or biological plausibility advice | leakage-safe grouped split and fit-only preprocessing | regenerate locked predictions safely | execution is fixed, but endpoint judgment may remain unresolved |
| H04 label expertise | systematic endpoint-label disagreement changes AUC | more labels from the same extraction rule or statistical advice | blinded expert endpoint adjudication | adjudicate the prespecified week-6 endpoint | label failure is removed; decision can advance |
| H05 evidence sufficiency | a small mismatched bridge cannot distinguish live explanations | expert design advice alone or a small partially matched cohort | adequately sized independent replication | run the replication | sufficient positive evidence advances; otherwise abstention remains correct |

These pairs deliberately cover: data helps while advice does not; expert
adjudication helps while more rows do not; metadata resolves identity; tooling
fixes execution but not scientific transfer judgment; no available resource
currently resolves a control; and sufficient treated evidence penalizes needless
escalation.

## Per-task diagnostic record

Every scored task produces:

- observable failure and private recomputed metric truth;
- total and component scores;
- detection, containment, decision, and smallest-action flags;
- selected resource, resolving intervention, and intervention class;
- the paired treated/control result and observed recovery;
- substantive failure domains: quantitative analysis, scientific reasoning,
  evidence diagnosis, recovery design, or long-horizon execution;
- a separate schema-primary flag so formatting cannot masquerade as difficulty.

The public weights are: decision 15%, quantitative analysis 15%, scientific
diagnosis 15%, evidence integration 10%, resource selection 20%, recovery
design 15%, and commitment/reproducibility 10%. A scientifically perfect answer
using the wrong resource is capped at 80.

## Local gates before any Astra request

- reference solver at least 90 on every case;
- deliberately mediocre solver below reference in every family;
- universal advance, abstain, and stop policies all fail;
- reward-hacking, answer-leakage, and irreversible-commit checks pass;
- partial credit degrades monotonically;
- frontier development mean below 85, ideally 65–80;
- frontier ceiling rate at most 25%;
- weakest development model is neither all-zero nor universal failure;
- at least three substantive, interpretable failure domains;
- schema errors are not the primary source of difficulty;
- no task family explains more than 30% of the observed model gap;
- the one-seed development order is directionally consistent before a ceiling
  probe, while remaining explicitly insufficient for a ranking claim.

The local controls pass. The development gates remain closed until all 30
frozen one-seed cells finish. Only then may one bounded Astra held-out control
slice run. Astra at or above 85 is an explicit no-go.

## Breaking-point curves

The shared controlled evidence generator exposes four levels for each of five
scientific parameters: identity-conflict count, matched-cohort size, batch/outcome
phi, endpoint-label disagreement, and replication AUC. The reference solution
crosses a diagnosis or decision boundary on every ladder. Paid model curves are
separate experiments; they must not be inferred from the ten paired cells.

## Reporting boundary

`reports/generated/hard_suite_v03_report.md` separates controlled and authentic
results, lists every model/family/intervention cell, reports paired recovery,
and shows the reference breaking transitions. No stable ranking is allowed
until repeated held-out seeds and task-clustered uncertainty are available.

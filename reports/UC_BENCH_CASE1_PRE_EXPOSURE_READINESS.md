# UC-Bench Case 1 pre-exposure readiness review

Date: 2026-09-10  
Scope: Case 1 only; zero scientific API calls  
Decision: **NO-GO — scientifically ambiguous in its current verifier/contract pairing**

## Executive finding

Case 1 contains a useful, commercially realistic core: a locked pre-treatment anti-TNF response predictor, repeated biopsy records, a sealed outcome reveal, an irreversible analysis commitment, and a bounded evidence-investment decision. Its patient-level quantitative result is tractable and independently reproducible.

It is not ready for paid comparison. The most serious issue is not that the case is too easy. It is that the verifier accepts a vacuous precommitment and a post-reveal cherry-picked cohort. A submission can commit criteria such as `AUC >= 0`, calculate on a favorable subset chosen after reveal, and still receive 100/100. Several other scientific choices that the visible evidence leaves legitimately open are decided privately by the verifier. Those defects would confound model capability with benchmark-author preference.

No in-place repair was made. RC1.6 and every RC1.6 trajectory remain byte-preserved. Fixing the findings below requires a separately versioned, Case-1-only contract/verifier candidate and renewed zero-cost controls; silently changing frozen RC1.6 would be worse than stopping.

## Preservation and exposure status

- RC1.6 plus all seven RC1.6 sentinel run trees: 1,003 files, combined canonical digest `12204b578f93b00ffc4f05da14098d07400f85c111cbe4904d3efee4f26a0010` before and after this review.
- Exact visible Case 1 workspace: 17 files, digest `b6434d2f614ca149771cd86d5fce63dfc3b04267b0a3210799b279f988aa3f2e`.
- Exact serialized production request: digest `0b0410becf5d79adee1e334bb179a72675be75440d60bc1c3e1f9e0fdda1ff52`.
- Paid scientific calls: 0.
- Compatibility/inference calls: 0. Route confirmation used authenticated read-only model and endpoint metadata requests only.
- Case 2 was not resumed, modified, regraded, or executed. Only its archived token/cost metadata was read to produce the requested budget estimate.

One repository-test defect was exposed during the audit: `test_archived_replay_is_diagnostic_not_rescoring` rewrites the frozen RC1.4 `archived_submission_replay.json` timestamp while testing it. The freeze correctly detected the mutation: expected hash `ea301689...`, observed `23f02a...`. No trajectory was changed, but this means the full release-chain regression is not clean and the test must be redirected to a temporary copy before any future release gate.

## What the agent sees and does

```text
Visible predictor evidence
  |-- intended use + action threshold
  |-- 134 locked baseline predictions + cohort/source fields
  |-- endpoint-source ledger (outcomes still sealed)
  |-- preprocessing code/config + fit-membership ledger
  |-- reproduction examples + execution log + sponsor assertions
  |-- seven possible follow-ups with cost, delay and stated returns
  v
Inspect and form hypotheses
  v
COMMIT VALIDATION PLAN  [irreversible]
  v
REVEAL 124 patient outcomes
  v
Save auditable patient mapping, analysis table and typed calculations
  v
COMMIT FOLLOW-UP PLAN   [irreversible]
  v
PURCHASE one resource or `none` [irreversible]
  v
Analyze returned evidence, revise belief, and submit a bounded decision
```

The available tools are:

- `inspect_workspace`, `read_file`, `write_file`, and a network-disabled `run_command` for evidence inspection and reproducible analysis;
- `commit_validation_plan` and `reveal_validation` for the prospective validation boundary;
- `commit_followup_plan` and `purchase_resource` for the value-of-information boundary;
- `submit` for the final evidence-linked decision object.

The hidden verifier—not the model—reconstructs calculations from raw evidence and saved artifacts. The model has no network, credentials, oracle, hidden outcome, or grader access.

## Evidence available before reveal

- Intended use: prognostic research-triage probability for adults with moderate-to-severe ulcerative colitis before first infliximab; day-42 clinical-response endpoint; threshold 0.5.
- 134 prediction rows and cohort metadata containing 124 fingerprint clusters; ten clusters have repeated records.
- An endpoint-source ledger with 124 patient keys, visits within the stated day window, and one pending discordance flag.
- Frozen preprocessing code/configuration, a fit-membership ledger, execution logs, and three reproduction cases.
- Sponsor assertions explicitly marked as unverified.
- A resource catalogue: source reconciliation (X17), endpoint adjudication (X24), pipeline replay (X31), matched external evidence (X46), a larger same-process sample (X58), expert review (X63), or no purchase.

Material visible observations include: repeated-row prediction differences up to about 0.0228; no repeated pair straddles the 0.5 threshold; none of the listed validation IDs appears in the listed training IDs; the three reproduction examples differ from their expected outputs by 0.001–0.002; and site-level mean predictions differ. These facts create competing, professionally plausible hypotheses rather than a single obvious defect.

## Consequential branches

1. **Unit of analysis**
   - One row per inferred person using a deterministic predeclared aggregation.
   - A repeated-measures/cluster-aware estimand that retains rows while respecting dependence.
   - Naive row independence is not defensible.

2. **Prospective validation design**
   - Commit a discrimination estimand with patient-respecting uncertainty.
   - If probability use is contemplated, assess probability accuracy/calibration.
   - If the threshold affects the decision, assess threshold utility.
   - State the full eligible cohort and permissible exclusions before reveal.

3. **Evidence diagnosis after reveal**
   - Signal survives dependence-aware analysis versus row-level inflation.
   - Pipeline scope is clean versus contaminated or insufficiently documented.
   - Endpoint ambiguity is material versus immaterial.
   - Site/context heterogeneity reverses versus does not reverse the bounded conclusion.

4. **Follow-up choice**
   - Buy nothing if the immediate bounded internal decision is already resolved.
   - Buy X31 if reproducibility is the declared unresolved gate.
   - X46 is professionally reasonable if transport is explicitly the remaining decision question; the present private policy nevertheless rejects it.
   - Other resources can be rational only when their returned evidence targets the declared unresolved question.

5. **Final decision**
   - Continue a bounded research stage when precommitted criteria are met and scope remains narrow.
   - Pause when a concrete, decision-relevant gate remains unresolved.
   - Stop only when valid evidence defeats the investigated path.
   - Do not infer treatment effect, clinical utility, independent validation, or cross-platform transport from internal prognostic validation.

## Why the task is genuinely nontrivial

The valuable difficulty is compositional, not obscure. A successful agent must connect identifiers across files, distinguish records from people, commit an estimand before labels, preserve the evidence chain, calculate discrimination/probability/utility at the correct dependence unit, distinguish harmless anomalies from material leakage, select the smallest decision-relevant follow-up, revise belief after new evidence, and bound the final claim. Each is a normal predictor-diligence responsibility and an error can change an investment or development decision.

The independently reproduced full-cohort patient-level values are AUC 0.787879 (patient bootstrap interval approximately 0.7002–0.8641), Brier score 0.190208, calibration error 0.032207, and net benefit at 0.5 of 0.169355. These support tractability; they do not cure the contract/verifier ambiguity.

## Accepted alternatives: intended versus actually enforced

| Professional property | Intended valid alternatives | Current verifier behavior |
|---|---|---|
| Person dependence | Deterministic one-person aggregation; cluster-aware/repeated-measures analysis | Both reference families pass |
| Aggregation | Mean, median, first eligible record, or another prespecified deterministic rule | Tested mean/median/first workflows pass |
| Discrimination | ROC AUC or defensible concordance-equivalent estimate with patient-respecting uncertainty | Exact `ROC_AUC` plus bootstrap is privately required |
| Probability accuracy | Brier; or log loss with a calibration assessment | Brier/log-loss plus a separate exact calibration-error type is required |
| Utility | Net benefit or an equivalent threshold-specific expected-utility analysis | Exact net benefit is required |
| Immediate action | Bounded continue; defensible pause when a concrete unresolved reproducibility gate is named | Continue/pause can pass conditionally |
| Follow-up | `none` for a resolved bounded question; X31 for an unresolved replay question; X46 for a declared transport question | Only `none` and X31 are privately accepted |
| Scope | Research ranking or probability only when supported; narrower no-use/audit scope when uncertainty warrants it | Machine claim IDs and enums control credit; prose is not graded |

Thus two distinct reference workflows pass, but the advertised method freedom is materially wider than the implemented freedom.

## Independent red-team and main-audit findings

The independent reviewer first received only the exact production prompt and visible workspace. It then received the private truth, validity card, verifier, controls, and resource returns. The main audit was conducted separately and reconciled against it.

| Severity | Finding and concrete evidence | Consequence | Smallest sound remedy |
|---|---|---|---|
| **Blocker** | A copied reference submission still passes 100/100 after changing its committed criteria to `AUC >= 0`, `Brier <= 1`, and `net benefit >= -1`. The final calculation can also name a post-reveal subset through `cohort.entity_ids`. | A model can manufacture prospective consistency and cherry-pick after seeing outcomes. | Prospectively bind estimator family, patient/record rule, parameters, full eligible-cohort rule/hash, permitted exclusions, and non-vacuous public decision criteria; require the primary artifact to contain the full committed cohort. |
| **High** | Exact ROC-AUC/bootstrap, calibration-error, and net-benefit types are privately required although the visible contract says no method or metric is prescribed and the validity card accepts equivalent families. | Defensible scientific methods fail for author preference. | Grade scientific invariants/estimands and disclosed sufficiency conditions, not one metric vocabulary. |
| **High** | The verifier joins revealed outcomes to `fingerprint_cluster` by treating the `F####` identifier as the endpoint `patient_key`; no visible file declares this authoritative crosswalk. | The main patient mapping rests on a hidden assumption. | Add an agent-visible provenance declaration or crosswalk whose integrity can be checked. |
| **High** | A pre-reveal plan is expected to name an outcome artifact that does not yet exist. | An honest prospective plan can be penalized for not predicting a future path. | Permit a disclosed symbolic outcome role before reveal and bind the concrete file/hash when it becomes available. |
| **High** | X46 returns a matched external cohort with materially weak performance, making it defensible when transport is the declared unresolved question; private truth accepts only `none` or X31. | A rational value-of-information strategy can fail. | Accept X46 conditionally on a predeclared transport question, or visibly exclude transport from the immediate decision. |
| **High** | Site robustness is named decision-critical in the private validity card but is not required by the verifier. | A required professional property and the score disagree. | Either disclose and grade context robustness with method alternatives, or remove it from the claimed construct. |
| **High** | Selecting X17 can return filenames/schema that do not match the RC1.6 canonical artifact expectations. | A legitimate choice can cause an environmental artifact failure. | Make every offered resource consumable through the same disclosed artifact contract and test every resource branch. |
| **High** | The live contract is 31,185 bytes/1,057 lines, while the earlier open-endedness audit analyzed a much smaller contract rendering. | Completion and navigation burden are not represented by the prior construct audit. | Audit the exact serialized prompt; supply compact machine templates/validators without adding scientific hints. |
| **Medium** | X31 credit can be earned with a linked replay citation without a strong materiality comparison to the original. | Belief revision can become performative. | Recompute replay deltas and require the decision to follow their direction/materiality. |
| **Medium** | All machine scientific credit comes from enums, IDs and saved calculations; decision prose is only checked for presence. Contradictory prose can coexist with a passing machine decision. | The environment does not measure explanatory scientific reasoning as strongly as claimed. | Keep prose out of deterministic scientific rank, but add separately reported contradiction/unsupported-claim diagnostics with evidence, not hidden phrasing. |
| **Medium** | Generic Case-1 controls are weak in isolation: a fully analyzed “always advance” fixture and a fully analyzed “always none” fixture pass because they happen to match this positive case. | Case 1 alone cannot demonstrate resistance to universal policies. | Keep cross-condition policy controls; add same-appearance Case-1 variants with different evidence-supported actions before claiming template resistance. |

One blind-review concern was cleared: rejected irreversible calls do not consume the action, so clear tool feedback permits correction. Another was narrowed: an invalid optional calculation does not fail a mission when no scored decision depends on it. The red team and main audit agreed on the reward-hacking blocker, hidden linkage, method restriction, resource-policy ambiguity, and mismatch between claimed and enforced scientific properties.

## Deterministic controls and regression results

| Check | Result |
|---|---|
| Case 1 reference solution | Pass, 100 |
| Distinct valid dependence-aware solution | Pass, 100 |
| Correct final action without required analysis | Fail, partial 10 |
| Copied/hard-coded result after altering a locked prediction | Fail, partial 50; saved-chain, entity, quantitative, decision and claim checks fail |
| Invalid optional sensitivity calculation with correct primary work | Pass, 100 |
| Vacuous committed thresholds | **Incorrectly passes, 100 — blocker** |
| Generic checklist-only answer | Fail, partial 90 |
| Unsupported clinical advancement | Fail, partial 80 |
| Post-hoc criterion movement | Fail, partial 80 |
| Evidence mutation | Fail, partial 90 |
| Harmless rounding / semantic column mapping | Pass, 100 |
| Systematic malformed-agent-input corpus | 300 submission mutations + 40 workspace mutations; zero verifier exceptions/hangs |
| Universal policies across all five conditions | Fail overall, but Case 1 alone does not distinguish all of them |
| Relevant pytest selection | 103 passed; 2 release-integrity failures caused by the mutation-prone RC1.4 test itself |
| Ruff | Pass |
| Project doctor | Pass |
| Existing open-MMMVP controls | Pass, subject to the blocker above |

The altered-input result shows that ordinary hard-coded numbers are caught. It does not catch the stronger attack in which the agent exploits its own vacuous threshold or chooses the scoring cohort after reveal.

## Route confirmation and cost plan

All five requested routes are currently visible to this authenticated OpenRouter account, have a matching configured canonical slug, expose tool-capable endpoints, and previously passed RC1.6 technical compatibility. Fallbacks are disabled.

| Requested route | Pinned returned slug / provider | Route ceiling, prompt/completion per 1M | Analog expected | Analog no-cache |
|---|---|---:|---:|---:|
| `anthropic/claude-opus-4.1` | `anthropic/claude-4.1-opus-20250805` / Amazon Bedrock | $15 / $75 | $32.666535 | $32.666535 |
| `google/gemini-3.1-pro-preview` | `google/gemini-3.1-pro-preview-20260219` / Google AI Studio | $2 / $12 | $0.318986 | $0.658722 |
| `openai/gpt-5.1` | `openai/gpt-5.1-20251113` / OpenAI | $1.25 / $10 | $0.712242* | $2.702610* |
| `openai/gpt-5` | `openai/gpt-5-2025-08-07` / OpenAI | $1.25 / $10 | $0.712242 | $2.702610 |
| `anthropic/claude-sonnet-4` | `anthropic/claude-4-sonnet-20250522` / Amazon Bedrock | $3 / $15 | $5.756004 | $5.756004 |
| **Five-cell total** |  |  | **$40.166009** | **$44.486481** |

`*` GPT-5.1 was not reached in the current-contract RC1.6 sentinel, so its estimate uses the observed GPT-5 token/caching workload at the identical configured OpenAI prices and execution settings.

These are exact arithmetic estimates from the nearest available same-contract, same-runner Case-2 trajectories, not measured Case-1 costs. Case 1 has a smaller visible evidence package, but trajectory length is model-dependent. A safe five-cell cap remains **$52**.

Current key/account headroom is **$15.721995803** (`$114.278004197` used of a `$130` key limit). It does not cover the cap. The exact balance and key-limit increase required to make a $52 cap available is **$36.278004197**. No top-up or limit change was made.

## Construct-validity decision

Case 1 is neither merely too easy nor artificially difficult in its biological core. It is **scientifically ambiguous as currently scored**, with one direct reward hack. Paying for model trajectories now would not answer whether models can perform predictor diligence.

Release gates before exposure:

1. Close the vacuous-threshold and post-reveal cohort-selection paths.
2. Make the identifier relationship authoritative and visible.
3. Align method alternatives and site-robustness claims with actual scoring.
4. Resolve X46 and repair every offered resource branch.
5. Audit the exact live contract and add a compact, agent-visible template/validator.
6. Add controls for trivial thresholds, subset selection, each resource, contradictory machine/prose decisions, and at least one same-appearance action-changing variant.
7. Make the release-integrity tests operate on temporary copies and restore a clean immutable ancestor chain.
8. Require reference and distinct-valid workflows to pass, wrong-science and hard-coded/altered-input fixtures to fail, malformed inputs to remain non-crashing, and all frozen hashes to pass.

Only after those gates pass should the paid tranche be: **one fresh Case-1 attempt on each of the five routes above, randomized order, $52 cumulative cap, no other cases, no replacement models, one predeclared safe retry only for isolated transient provider failures, and no ranking claim from one attempt**. Legitimate scientific or model-completion failures should not stop other cells; shared integrity, contract, grader, credential, protected-data, or budget failures should.

External specialist validation remains absent at this pre-MVP stage and must be disclosed before broad scientific or commercial validity claims.

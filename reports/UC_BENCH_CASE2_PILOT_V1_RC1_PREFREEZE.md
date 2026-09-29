# UC-Bench Case 2 pilot v1 RC1 — pre-freeze review package

## Release decision

**Ready for pre-freeze review; deliberately not frozen and not authorized for inference.**

The two approved construct repairs are implemented without changing the original Case 2
data, locked predictions, sealed outcomes, preprocessing evidence, resource contents, or
historical results. Case 1 RC6 remains accepted at digest
`a1795f1be20b02bb02d86516a664a3d62aed7d6ca716bdd45cb277b4c1ea6d19`.

The candidate now distinguishes provisional linkage from adjudicated person identity and
grades evidence-supported action scope rather than a privately preferred disposition. Two
independent zero-cost reviews found no remaining blocker or high-severity issue after the
listed repairs. No compatibility check or model call was made; paid spend is zero.

## 1. Plain-language environment schematic

```text
PUBLIC START
  203 biopsy records + two non-canonical identity fields
  locked probabilities + intended use + preprocessing/provenance evidence
       |
       v
[1] COMMIT VALIDATION PLAN  <irreversible>
  cohort manifest + dependence strategy + estimators + uncertainty + decision gates
       |
       v
[2] REVEAL SEALED OUTCOMES  <cannot edit the plan>
  build saved analysis table(s), calculations, and per-site audit
       |
       v
[3] COMMIT ONE FOLLOW-UP QUESTION AND CONTINGENCIES  <irreversible>
       |
       v
[4] PURCHASE EXACTLY ONE RESOURCE OR `none`  <irreversible>
  verify provenance -> calculate returned evidence -> revise the same beliefs
       |
       v
[5] SUBMIT  <terminal>
  bounded action + current use permission + unresolved gates + supported claims
       |
       v
ONE SEMANTIC ENGINE
  reconstructs cohort, identity, calculations, context, resource effect,
  belief revision, and decision consistency for both public and hidden grading
```

The evaluator scores ten scientific properties independently. It reports the earliest
failed property and the transitive downstream properties affected by it; unrelated valid
work keeps credit.

## 2. Exact workflow and irreversible boundaries

1. Inspect the intended use, source records, prediction provenance, preprocessing lineage,
   endpoint ledger and follow-up catalogue. Outcomes remain sealed.
2. Choose a defensible provisional-unit workflow; write a complete cohort manifest and
   precommit five or six criteria, including either or both disclosed context estimands.
3. Call `commit_validation_plan`; later changes cannot affect the committed record.
4. Call `reveal_validation`; join outcomes only to the committed cohort and save every
   decision-driving table and calculation.
5. Diagnose what is now resolved and what remains decision-relevant. Commit one question,
   one resource (including `none`), a materiality rule, and result-contingent actions.
6. Call `commit_followup_plan`, then `purchase_resource` exactly once.
7. Validate source hashes, calculate the returned evidence through a purchased-evidence
   table where empirical evidence was bought, and link it to numeric belief revision.
8. Submit an action that distinguishes current use from further investigation and limits
   claims to verified evidence.

The host event record is authoritative for actions and timing. Saved files are authoritative
for scientific numbers. Free prose is audit-only and never exact-matched.

## 3. Exact public identity wording

The public `identity_provenance.json` defines:

- `source_record_id`: “one biopsy record”; canonical-person truth is false.
- `fingerprint_cluster`: “provisional dependence/linkage unit derived without outcomes”;
  canonical-person truth is false and the field is outcome-blind.
- `reported_patient_id`: “supplied identifier whose consistency must be investigated”;
  canonical-person truth is false.
- Claim rule: “A provisional-unit count is not an adjudicated patient count. An
  adjudicated-person claim requires returned identity evidence and a saved analysis using
  that mapping.”

The public field guide accepts:

- aggregation within provisional fingerprint units while limiting the estimand;
- retained source rows with entity weighting and cluster-aware uncertainty; and
- reported-patient grouping only as a labelled sensitivity analysis before adjudication.

An identity purchase is optional. If selected, its outcome-independent crosswalk must drive
a saved post-purchase calculation before any adjudicated-person claim.

## 4. Exact public context/action wording

The public field guide states:

> Commit exactly one criterion for discrimination, probability accuracy, calibration and
> threshold utility, plus either or both context criteria. `SITE_WEIGHTED_ROC_AUC` requires
> a threshold of at least 0.65; `WORST_SITE_ROC_AUC` requires at least 0.55. Save each
> site's source-row count, analysis-row count, entity count, evaluability and ROC AUC in
> the context calculation output.

It then states:

> General multi-site continuation requires every committed primary/context criterion to
> pass. After context failure or non-evaluability, PAUSE or INSUFFICIENT_EVIDENCE may hold
> the claim; STOP needs valid invalidating evidence. CONTINUE remains possible only for a
> targeted context investigation that prohibits current multi-site probability use and
> does not claim transport or independent validation. Continuing an investigation is not
> advancing the predictor.

The rationale is also public: 0.65 requires meaningful site-weighted discrimination above
chance while allowing a modest reduction from the pooled gate; 0.55 prevents a near-chance
site from being hidden by pooled performance. No observed Case 2 value appears in this rule.

## 5. Before/after contract diff

| Construct | Historical behavior | RC1 candidate |
|---|---|---|
| Identity | Fingerprint grouping could be treated as the operational patient truth. | Both supplied identity fields are explicitly provisional/unverified; dependence-aware workflows are accepted and person claims require adjudication plus recomputation. |
| Context | Public gates lacked a context floor while a private grader preferred PAUSE/STOP. | Either/both public context estimands, public non-vacuity floors, complete site audit, and an evidence-supported action invariant. |
| Final action | An otherwise defensible enum could lose because it differed from a hidden narrative. | PAUSE, STOP, INSUFFICIENT_EVIDENCE and two forms of CONTINUE are judged by supported scope and claims. |
| Follow-up | Some historical paths did not prove that purchased evidence drove the cited calculation. | Empirical follow-up calculations must resolve to a verified purchased table under the chosen resource path. Ineffective purchases earn no follow-up credit. |
| Scoring | Some malformed/process failures could cascade. | Property-local exception containment plus explicit transitive scientific dependencies. |

The machine-readable diff is in `contract_diff.json`.

## 6. Why the repair does not reveal the planted answer

The public start state contains no sealed outcome, private truth, grader, observed metric,
adjudicated membership, mapping-change count, preferred resource, or expected action. The
rules are prospective professional standards that apply to controlled altered inputs as
well as the authentic case. The agent still has to discover:

- whether the two supplied identifiers agree;
- how dependence changes the estimand and uncertainty;
- whether the locked predictor satisfies the committed gates;
- which uncertainty remains after calculation;
- whether any purchase is worth making; and
- which action and claim scope the resulting evidence supports.

The no-leak audit passes, and altered-input controls make copied counts, fixed results and
universal decisions fail.

## 7. Accepted decision/action table

| Disposition | Action scope | When it can pass | Current multi-site probability use |
|---|---|---|---:|
| CONTINUE | `GENERAL_MULTISITE_ADVANCEMENT` | Every committed primary and context gate passes. | permitted |
| CONTINUE | `TARGETED_CONTEXT_INVESTIGATION` | Context remains failed/non-evaluable; the next target can address it; no transport or current validation success is claimed. | prohibited |
| PAUSE | `HOLD_CURRENT_CLAIM` | A consequential gate remains unresolved or valid evidence exposes a blocker. | prohibited |
| INSUFFICIENT_EVIDENCE | `HOLD_CURRENT_CLAIM` | Evidence does not resolve a directional advancement claim and the next evidence is specific. | prohibited |
| STOP | `END_DEVELOPMENT_PATH` | Valid saved evidence establishes that this development path is not worthwhile. | prohibited |

No row is preferred. Matching the result-contingent commitment is necessary but not
sufficient: the decision must also follow recomputed evidence.

## 8. Identity-state diagram

```text
                     PRE-PURCHASE
203 biopsy records -----------------------------------------------+
     |                                                            |
     | outcome-blind fingerprint linkage                          |
     v                                                            v
provisional linkage units                              reported-patient grouping
     |                                                  sensitivity only
     +--------------------------+-------------------------+
                                |
              +-----------------+------------------+
              |                                    |
      aggregate within units            retain rows with unit weights
      + limited estimand                 + cluster bootstrap
              |                                    |
              +---------- bounded claims ----------+
                                |
                    optional identity question
                                |
                     purchase identity evidence?
                         /                 \
                       no                  yes
                       |                    |
          preserve provisional scope       v
                                blinded canonical crosswalk
                                           |
                                saved remapped analysis
                                           |
                              adjudicated-person claim allowed
```

The diagram is a workflow contract, not a disclosure of the hidden mapping result.

## 9. Public/hidden semantic parity

The public validator and hidden verifier call the same
`case2_pilot_v1_rc1_semantics.py` implementation. In the parity fixture:

- public and hidden mission result: identical;
- partial score: identical;
- all ten property outcomes: identical;
- resource facts/materiality/effect: identical;
- copied public support source: byte-identical to host source.

The full diagnostic objects intentionally differ only because hidden grading authenticates
the host event record while local scientific validation cannot. The hidden wrapper contains
no answer table, disposition whitelist, private threshold, resource preference, identity
assumption or prose matcher.

## 10. Controls and historical-fixture replays

All **53 Case 2 candidate controls/tests** pass; all **64 candidate plus readiness tests**
pass. The broad repository run passes **991 selected tests** after isolating the four
disclosed legacy archive/preflight checks described below. Important results:

| Control family | Result |
|---|---|
| Two identity workflows | Provisional aggregation and dependence-aware retained-row workflows both complete successfully. |
| False identity claims | Pre-adjudication canonical-person claims and row-independent analysis fail the relevant scientific properties. |
| Identity purchase | Mapping change alters the saved person-level analysis; copied results and purchase-without-recomputation fail. |
| Context thresholds | 0.5001/0.51 are rejected; disclosed 0.65/0.55 floors and either/both estimands are accepted. |
| Decisions | Supported PAUSE, INSUFFICIENT_EVIDENCE, targeted CONTINUE and STOP pass; unsupported general advancement fails. |
| Generic policies | Universal PAUSE and STOP fail on a strong-context altered input; unconditional advancement fails on context failure. |
| Resource evidence | Valid supported purchase/no-purchase paths pass; wrong-table calculations, unused evidence, copied results, ineffective purchases and a memo standing in for data fail. |
| Saved artifacts | Important values are recomputed; an omitted output reports causal downstream failures without erasing unrelated work. |
| Robustness | Malformed payloads, nested values, event rows and non-object state fail safely; a 5,694-mutation sweep produced no crash. |
| Semantic parity | Public and hidden scientific outcomes are identical. |

The exact five immutable RC1.6 submissions are retained as shape/causality fixtures, not
rescored: parser totality, artifact-chain status, identity handling, resource choice,
belief/claim arrays and first-failure ordering are all exercised. The exact Qwen and
DeepSeek request ledgers remain cell-local provider-failure fixtures. The repaired v0.8 Sol
run remains tractability evidence only; its historical score is not imported into RC1.

## 11. Independent reviews and dispositions

- **Blind computational-biology review: APPROVE.** With only the public packet, the
  reviewer found it answer-neutral and internally coherent, and identified two materially
  different valid workflows without needing hidden facts.
- **RL scientific red team: implementation-level pre-freeze approval.** It initially found
  two blockers and several high findings involving generic actions, purchased-evidence
  lineage, totality and materiality. Every blocker/high was repaired and retested. The final
  review found no remaining blocker or high issue; the complete candidate test file passed.

Full findings and fixes are preserved in `rl_scientific_review.json`; the final release gate
must require the same clean disposition object rather than a shallow `passed` flag.

## 12. Exact freeze-manifest proposal

No freeze is created now. A later reviewed freeze must include:

- hashes of every candidate source and test file;
- hashes of the exact original public packet, sealed evidence and resource returns;
- hashes of every agent-visible start-state file and copied support module;
- the single semantic-engine digest and public/hidden parity result;
- all zero-cost control and independent-review results;
- the exact future runner, route policy, request lifecycle, replay and reporting code;
- a credential/no-leak attestation; and
- a freshly checked funding gate.

It must exclude credentials, private truth from the public packet, a preferred disposition
or resource, and the compromised RC1.4 archive as an authority. The proposed current hash
sets are in `freeze_manifest_proposal.json`; because the production Case 2 runner has not
yet been frozen, that file correctly says `freeze_now: false`.

## 13. Refreshed staged cost plan

| Stage | Pinned models | Median estimate | Planning contingency | Hard cap |
|---|---|---:|---:|---:|
| Smallest sentinel | Gemini 3.1 Pro Preview / Google AI Studio; GPT-5.1 / OpenAI; Claude Sonnet 4 / Amazon Bedrock | $7.04 | included within cap | $12.00 |
| Full pilot | Above plus GPT-5 / OpenAI and Claude Opus 4.1 / Amazon Bedrock | $40.42 | $50.53 no-cache +25% case | $52.00 |

These are historical planning estimates, not empirical P90s. Routes/prices must be checked
again before freeze and immediately before any separately authorized inference.

## 14. Account and key headroom

Read-only checks on 2026-09-12 reported:

- account credits: `$230.00`; usage: `$195.717976447`; remaining: `$34.282023553`;
- API-key limit: `$230.00`; usage: `$195.717976447`; remaining: `$34.282023553`;
- effective headroom: **`$34.282023553`**.

The `$12` sentinel cap is covered with `$22.282023553` remaining after reservation. The
`$52` full-pilot cap is not covered: both account credit and API-key limit would need an
additional **`$17.717976447`** of headroom. No account setting was changed.

## Remaining construct-validity and release risks

- This is one internally authored calibrated case, not a broad benchmark or externally
  validated expert-equivalence claim.
- The public context floors are defensible predeclared standards, but their construct
  validity has not been reviewed by an external biostatistician or clinical expert.
- The strong-context control is synthetic and establishes anti-policy behavior, not clinical
  generalization.
- Historical model trajectories were produced under older contracts and are diagnostic
  fixtures only.
- Four unrelated legacy repository checks remain red because archived RC1.4/Case-1
  infrastructure no longer satisfies its own old freeze/preflight assumptions. They are
  disclosed external exceptions and are not inherited by this provenance root. All other
  991 repository tests pass in the isolated broad run.
- The Case 2 production runner/route closure still has to be materialized and rehearsed
  before a freeze or paid call. This is an execution-readiness task, not a scientific change.

## Recommendation

Approve this scientific/semantic candidate for a separate runner-and-freeze closure. After
that zero-cost closure and a fresh funding check, the smallest credible paid step is the
three-model Case 2 sentinel under a `$12` cumulative cap. Do not run the five-model pilot
until the additional `$17.717976447` headroom exists and the sentinel shows no grader or
harness contamination.

# UC-Bench Case 1 RC1.7 pre-exposure report

## Release decision

**Scientific construct: ready for exposure. Release: blocked; do not freeze or spend.**

RC1.7 is the next unused version and is an isolated, zero-cost Case 1 successor. Its
scientific design passed the local reference, alternative-workflow, adversarial,
resource-branch, altered-input, malformed-artifact, protected-data and restart
checks. A fresh independent two-phase red team found no remaining blocker or
high-severity scientific defect after reconciliation.

The full release gate nevertheless fails because a frozen RC1.4 diagnostic artifact
was mutated by an old repository test before this work began. The expected SHA-256 is
`ea3016898d698c5f3e311fb4edb9c20d29a791c38649b723a2cfe90834847c08`; the surviving
file is `23f02a2fbf2f63b74886a9bde9e38a8bac5211e143e8861e8a8bf2c85093562c`.
No exact preserved copy was found, so the archive is explicitly marked compromised
rather than reconstructed. RC1.7 has not been frozen and no model call was made.

This is not evidence that Case 1 is too easy or artificially difficult. It is a
scientifically coherent case whose empirical difficulty remains uncalibrated until
repeated model exposure. The current stop is provenance integrity, not task design.

## Plain-language environment schematic

```text
Agent-visible packet
  |-- intended use and action threshold
  |-- locked predictions + cohort/source metadata
  |-- endpoint-source ledger + explicit identity relationship
  |-- model/pipeline provenance
  |-- neutral resource catalogue
  |-- short mission + schema + method definitions + templates + validator
  |
  v
Choose before outcomes
  biological unit + dependence rule
  complete eligible-person manifest + hash + pre-outcome exclusions
  estimators + parameters + uncertainty + five non-vacuous criteria
  |
  | irreversible commit
  v
Environment reveals outcomes and binds SEALED_VALIDATION_OUTCOMES
to the actual path and SHA-256
  |
  v
Agent saves the committed patient-respecting analysis
  discrimination + probability accuracy + calibration + threshold utility
  + site/context robustness
  |
  v
Agent declares one unresolved decision question
  |-- already resolved -> none
  |-- identity -> X17
  |-- endpoint validity -> X24
  |-- reproducibility -> X31
  |-- transport -> X46
  |-- same-process precision -> X58
  `-- expert interpretation -> X63
  |
  | irreversible commitment and purchase
  v
Agent saves a resource summary from returned source files,
revises numeric beliefs, and makes a bounded decision with restrained claims
  |
  v
Hidden verifier reconstructs the raw evidence chain and recomputes every
decision-driving result; strict mission success requires all ten scientific links
```

The task's difficult work is not contract discovery. It is selecting the patient
unit, prospectively fixing the estimand and cohort, respecting dependent biopsies,
computing several decision-relevant properties, deciding what uncertainty is
material, selecting the minimum useful evidence purchase, revising beliefs from the
returned result, and limiting the claim to what an internal validation can support.

## Exact contract and verifier changes

| Readiness finding | RC1.7 repair | Verification |
|---|---|---|
| Vacuous thresholds and post-reveal favorable subsets could pass | Commitment now binds the person/source manifest and hash, exclusions, aggregation, estimator, bins, utility threshold, uncertainty method/seed/repetitions/level and all five criteria. Primary calculations must use the exact included set. Public non-vacuity floors reject chance or harmful gates. | Direct AUC, Brier, utility, context and subset attacks fail. |
| Future outcome filename could not honestly be committed | The plan commits the symbolic role `SEALED_VALIDATION_OUTCOMES`; reveal records the actual path and hash host-side. | Outcome binding is checked independently. |
| `fingerprint_cluster` to `patient_key` was a hidden join | `identity_provenance.json` declares the fields as the same privacy-preserving person identifier and states the many-record-to-one-person cardinality. | Manifest membership is reconstructed from visible metadata and checked against raw rows. |
| Advertised method freedom exceeded implemented freedom | `scientific_methods.json` and `method_definitions.json` disclose every supported family and operational definition, and identify unimplemented methods as outside RC1.7. | Mean, median, first, source-row clustered/entity-weighted, metric aliases and log-loss workflows pass. |
| Site robustness was decision-critical in design but optional in grading | Context robustness is one of five required, precommitted primary properties. | Worst-site and site-weighted alternatives are recomputed. |
| Resources were partly schema-incompatible or graded by hidden whitelist | Every branch receives `resource_manifest.json`; X17 is normalized to the common crosswalk contract. Credit follows the public question/resource mapping, exact returned hashes, recomputed result, committed materiality and actual downstream use. | All seven branches are consumable; relevant and irrelevant uses separate correctly. |
| X31 could receive credit without a material replay comparison | X31/X46/X58 require a public positive materiality threshold of at least 0.02; X31 uses the absolute replay-versus-primary discrimination delta. | A zero-threshold X31 plan is rejected and the authentic sub-threshold replay does not earn follow-up credit. |
| The 1,057-line interface created a completion floor | The live prompt is short and neutral; mechanics are split into complete JSON schema, field guide, method file, structural templates and a local preflight. | Exact serialized request is audited; untouched templates fail; the local validator never certifies action readiness. |
| Generic checklist earned 90 partial points | RC1.6 gave 90 because nine binary 10-point categories could pass while only `prospective_plan_implemented` failed. RC1.7 weights ten scientific properties and awards them only from independently verified artifacts or evidence-conditioned actions. | Correct decision without analysis scores 0; correct analysis plus wrong final decision retains 93 but fails the mission. |
| A generic policy could fit the positive case | Added an unpaid control with byte-identical pre-reveal appearance but different sealed outcomes/follow-up evidence and correct action. | Universal continue, no-purchase, copied analyses and unrevised belief all fail; the correct negative workflow passes. |
| Old archive test mutated frozen output | The exact legacy pytest node is redirected to a temporary copy. Existing archive bytes are not rewritten. | Hash is stable before/after the test, but the already-mutated ancestor remains compromised. |
| RC1.7 state was not reconstructible through the durable production lifecycle | Added an RC1.7-specific restoration and replay checker using the same durable store and wrapped tool lifecycle as the production harness. | Interruption after reveal restores identical state, performs no duplicate reveal, continues once, and replays cleanly. |

## Supported scientific alternatives

| Property | Accepted release families |
|---|---|
| Patient/dependence unit | One row per person using predeclared mean, median or lexicographic-first aggregation; or all source rows with entity weights and patient-cluster bootstrap |
| Discrimination | ROC AUC or binary concordance, with ties worth one half |
| Probability accuracy | Brier score or binary log loss |
| Calibration | Equal-width expected calibration error with 2–20 predeclared bins |
| Threshold utility | Net benefit or the disclosed equivalent threshold expected utility |
| Uncertainty | Person bootstrap for person-level tables; patient-cluster bootstrap for retained source rows |
| Context robustness | Worst-site AUC or site-weighted AUC |
| Exclusions | None, documented pre-outcome endpoint ambiguity, or documented pre-outcome missing prediction; every eligible person remains in the manifest |

Bayesian intervals, DeLong intervals and refitting workflows are not secretly
rejected: they are explicitly outside the machine-recomputed RC1.7 release surface.
That is a remaining scope limitation, not a claim that those methods are invalid.

## Consequential branches and resource matrix

The resource ID is mechanically determined by the agent's declared question, but
the question itself is chosen from the evidence. No resource is intrinsically the
right answer.

| Branch | What earns scientific credit | Authentic-control result |
|---|---|---|
| `none` | Primary evidence already resolves the bounded immediate decision and no visible adjudication gate remains | Valid, used, relevant; 100, mission pass |
| X17 identity | Returned crosswalk changes or leaves unresolved person/source membership | Technically valid and used; immaterial here; 83, mission fail |
| X24 endpoint | Visible endpoint provenance makes adjudication material and blinded review resolves or changes the decision | Valid, material; 100, mission pass |
| X31 reproducibility | Replay comparison exceeds the prospectively committed positive threshold and the final decision uses it | Replay delta is below the declared threshold here; 83, mission fail |
| X46 transport | Transport was the declared unresolved question and the matched-context result bounds or blocks the final claim | Valid, material, exposes blocker; 100, mission pass |
| X58 precision | Added same-process evidence crosses a committed gate, exposes harm or materially changes an estimate | Valid, material, exposes blocker; 100, mission pass |
| X63 expertise | Memo adds decision-relevant information not already present; recommendation alone is not empirical evidence | Technically valid and used; immaterial here; 83, mission fail |

These are controls of scientific adjudication, not a public answer key. The agent
does not see the private verifier, control outcomes or this report.

## Partial scientific-quality decomposition

| Mission-critical property | Points | Authoritative evidence |
|---|---:|---|
| Prospective design and integrity | 15 | Committed record, event timing, input and cohort hashes |
| Saved artifact chain | 10 | Parsed source-linked tables and output records |
| Entity/dependence analysis | 15 | Raw-row reconstruction against the committed manifest and rule |
| Discrimination and uncertainty | 10 | Independently recomputed typed calculation |
| Probability and calibration | 10 | Independently recomputed typed calculations |
| Threshold utility | 8 | Independently recomputed calculation at intended-use threshold |
| Context robustness | 8 | Independently recomputed site/context result |
| Decision-relevant follow-up | 10 | Declared question, purchase event, returned hashes, recomputed materiality and use |
| Belief revision | 7 | Numeric before/after changes consistent with observed evidence and contingency |
| Bounded decision and claims | 7 | Machine decision object and calculation-supported claim scopes |

Free text, verbosity, file presence by itself and schema compliance earn no points.
Prose can create diagnostic warnings but cannot change the scientific score.
Strict mission success requires every row above; reliability remains separate.

## Zero-cost attack and control results

- 36 controls executed with zero API requests.
- Eight materially different professional workflows passed at 100: mean, median,
  lexicographic first, source-row clustered/entity-weighted, metric-alias/log-loss,
  pre-outcome exclusion, and two endpoint-adjudication variants.
- Sixteen named attacks were rejected: four vacuous gates, zero-materiality X31,
  post-reveal subset selection, correct decision without analysis, copied values,
  copied entire analysis, outcome-informed forged predictions, universal continue,
  universal no-purchase, universal stop, unrevised belief, contradictory machine
  decision and unsupported clinical advancement.
- Correct decision without analysis scored 0 and failed.
- Correct calculations with a wrong final decision scored 93 and failed strict
  mission success, preserving useful training signal.
- An unlinked malformed optional diagnostic did not invalidate a correct primary
  mission.
- Contradictory prose left the score unchanged and generated a diagnostic flag;
  contradictory machine fields failed the decision property.
- Malformed primary artifacts failed without verifier crash or hang.
- The negative same-appearance reference passed; copied positive answers did not.
- Protected evidence mutation terminated through the integrity path, outside
  ordinary scientific scoring.
- Interruption immediately after reveal reconstructed the exact message/workspace/
  episode boundary, did not repeat the reveal, continued one tool exactly once and
  passed lifecycle replay.

## Independent red-team review

The fresh reviewer first saw only an instantiated agent-visible workspace. It drew
the workflow and attacked threshold selection, cohort selection, template anchoring,
method disclosure, resource relevance, prose/machine contradictions and malformed
artifacts. It then received the verifier, private validity card and controls.

Initial findings included two blockers and two high-severity issues: it suspected
that calculations were not bound to raw data; found a real zero-materiality X31
path; found a hidden resource evidence-path whitelist; and found incomplete
machine-decision consistency. Reconciliation established that raw primary values
were already reconstructed field-by-field, while the three real defects were
repaired and directly regression-tested. Moderate findings concerning optional
artifacts, X24 aggregation, local-validator overclaim and stale private narrative
were also repaired. The final independent verdict was **READY**, with no remaining
blocker/high regression.

## Repository, isolation and audit gates

| Gate | Result |
|---|---|
| RC1.7 focused tests | 14 passed |
| Ruff over `src`, `tests`, `scripts` | Passed |
| Project doctor | Passed (`status: ok`) |
| Project audit consistency | Passed (10 stages, 7 disclosed open findings) |
| Generic Docker preflight | Passed |
| Exact open-MMMVP Docker isolation | Passed: network none, read-only root/workspace, writable `work/`, no credential environment, nine denied mutation probes |
| RC1.6 release/trajectory preservation | 1,003 files; digest matches `12204b578f93b00ffc4f05da14098d07400f85c111cbe4904d3efee4f26a0010` |
| Full repository pytest | Reached 100%; exactly two failures, both caused by the one known RC1.4 archive mismatch |
| Complete ancestor release chain | **Failed**; RC1.4 archived replay hash compromised |

## Immutable candidate evidence

RC1.7 is deliberately **not frozen**. The deterministic readiness artifact records:

- exact agent-visible workspace: 30 files, hash-set digest
  `2892626cf623dc2e8b152705bf10b948687b8dfdc2cc0777c7ab1c1586ee4384`;
- exact serialized request SHA-256
  `44bdb4e753628d81f94f970070a9d59d8f3f80e3b469e94a8eb48e249e4c6fe3`;
- RC1.7 candidate source hash-set digest
  `a1b4f569ba2b86c06b64e96706ad5f5a23e38976b58caaa42d814c2d4a8e23da`;
- zero scientific, compatibility or other API requests.

The per-file hashes and complete workspace manifest are in
`artifacts/mmmvp_open_rc17/case1_readiness.json`.

## Construct-validity limitations

1. This is one internally authored controlled case, not a broad biology benchmark.
2. No external biostatistician, transcriptomics specialist or clinical reviewer has
   independently validated the task; the red team is another model instance.
3. The supported-method surface is intentionally finite. Valid but unimplemented
   methods cannot be compared by the deterministic verifier in this release.
4. Baseline eligibility and the week-6 endpoint construct remain supplied source
   assertions. The case tests whether the agent limits claims accordingly; it does
   not establish their external truth.
5. The same-appearance negative is a controlled synthetic perturbation and must be
   reported separately from the authentic Case 1 packet.
6. One attempt cannot establish task difficulty, saturation or a stable model
   ranking. The requested paid tranche would only be a single-attempt pilot.
7. Historical technical route checks predate the revised visible contract. No fresh
   compatibility call was permitted in this zero-cost phase.
8. The RC1.4 archive compromise prevents a clean release provenance chain.

## Five-model tranche and funding

No paid tranche is currently recommended because the ancestor-integrity gate fails.
Once that provenance issue is resolved through an explicitly accepted release
policy, the smallest informative exposure remains one randomized Case 1 attempt per
model:

| Requested model | Pinned/returned route from preserved evidence | Provider | Expected | No-cache estimate |
|---|---|---|---:|---:|
| Claude Opus 4.1 | `anthropic/claude-4.1-opus-20250805` | Amazon Bedrock | $32.666535 | $32.666535 |
| Gemini 3.1 Pro Preview | `google/gemini-3.1-pro-preview-20260219` | Google AI Studio | $0.318986 | $0.658722 |
| GPT-5.1 | `openai/gpt-5.1-20251113` | OpenAI | $0.712242 proxy | $2.702610 proxy |
| GPT-5 | `openai/gpt-5-2025-08-07` | OpenAI | $0.712242 | $2.702610 |
| Claude Sonnet 4 | `anthropic/claude-4-sonnet-20250522` | Amazon Bedrock | $5.756004 | $5.756004 |
| **Total** |  |  | **$40.166009** | **$44.486481** |

The conditional hard cap is **$52**. Last observed key usage was
$114.278004197 of a $130 limit, leaving $15.721995803; the minimum key-limit and
funding increase needed to cover the cap was therefore **$36.278004197**. Those
account figures were not refreshed because this phase prohibited API calls. Route
availability and compatibility are inherited historical evidence, not a fresh
post-contract confirmation.

## Precise stopping point

Stop at RC1.7 development state. Preserve the candidate and report. Do not freeze,
run compatibility, randomize a paid order or execute any model. The only blocking
question is how to establish an honest successor provenance chain when an inherited
frozen artifact has no recoverable original bytes. That requires an explicit release
policy decision; changing science, recreating guessed bytes or silently accepting the
hash mismatch would be invalid.

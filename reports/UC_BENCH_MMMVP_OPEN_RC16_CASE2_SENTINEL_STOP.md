# UC-Bench open MMMVP RC1.6: verifier hardening and Case-2 sentinel stop report

## Executive result

RC1.6 met its primary verifier-hardening objective and was frozen as an immutable verifier-only successor to RC1.5. The preserved RC1.5 Gemini trajectory now replays deterministically as a 40/100 scientific failure with 100 reliability, without a grader exception or a false lifecycle failure.

The paid Case-2 sentinel did not complete. Five models produced valid, gradeable episodes; Qwen was excluded after an isolated upstream rate-limit failure; DeepSeek then encountered an isolated connection/read failure that the frozen runner incorrectly classified as `unknown_harness_failure`. That classification triggered a global stop after 7 of 9 attempted cells. Kimi K3 and GPT-5.1 were not launched.

Therefore the sentinel result is **insufficient evidence after an early infrastructure stop**. The five gradeable episodes show genuine scientific/workflow variation and a credible non-zero scientific floor, no ceiling, and no artificial contract/submission floor. They do not establish a stable ranking or a complete nine-model comparison.

## Immutable identities and preservation

- RC1.6 infrastructure digest: `d1f26b6df3876e9fc0faa1ffeb37fbec075cee572f1beeec25bca9bfbd55e869`
- Scientific freeze digest: `466441682b04175432329b41adcfd735cdea66f860d66f046dfae195c91e701c`
- Preserved RC1.5 infrastructure digest: `fd505c1d639fd4ecaabe6c3828f3f157cd4e4aebb685a6e5788868b611ee4bc4`
- Preserved RC1.5 Gemini summary: `a88ce2a87e77e0f2222f435c36903540357ae4463c4084bd8306515e4d98231d`
- Preserved RC1.5 Gemini trajectory tree: `cd33e2acc6e98a3fedf585443f035b609ef7a86c357627ce27ee40edf1785d21`
- Preserved RC1.5 official unscored report: `6735184de0ad5a3c1af996996930180b151917b3928dc174106ba70105483b52`
- Preserved RC1.4 archived replay: `ea3016898d698c5f3e311fb4edb9c20d29a791c38649b723a2cfe90834847c08`

The RC1.5 archive remains officially unscored. No RC1.5 trajectory or result was retroactively changed.

## Verifier-hardening result

`work/auc.txt` in the preserved Gemini run is syntactically valid JSON but is semantically invalid as the disclosed `CALCULATION_OUTPUT`: its top level is a number, not an object containing `typed_calculations`. RC1.6 records this as an agent-controlled artifact failure, including `saved_output_mismatch`, gives no AUC credit, and does not crash. The prior verifier exception is classified as infrastructure failure; it is not attributed to Gemini.

RC1.6 now uses typed artifact-validation results with artifact ID/path, expected role, observed top-level type, fault codes, linked calculation IDs, and origin. Agent-controlled JSON/CSV, manifest, column-map, uncertainty, path and work-file failures return deterministic structured failures. Environment-owned corruption remains an infrastructure failure. Unexpected internal invariants remain grader failures. Lifecycle reconstruction and grader replay are independently adjudicated.

The bounded independent red-team review found and resolved:

- deeply nested/extreme JSON escape paths;
- symlink and unsafe path resolution;
- unbounded whole-file hashing/table parsing;
- malformed host/environment evidence paths;
- live tool decode/schema conversion paths;
- unresolved-provenance row-bound bypass;
- unbounded retained calculation IDs/matches/faults.

No concrete parser path remained open at sign-off.

## Zero-cost gates

- RC1.6 tests: all 54 passed.
- Repository tests excluding the mutation-prone RC1.4 file: all passed.
- RC1.4 tests under full byte-snapshot restoration: all 26 passed.
- Ruff: passed.
- Project doctor: passed.
- Audit consistency: passed.
- General and open-MMMVP Docker preflights: passed; network disabled and credentials absent.
- Crash corpus: 16 archived accepted workspaces, reference and alternative solutions for all five conditions, 58 control rows including all 35 declared controls, 40 mutated workspaces, and 300 systematic submission-field mutations.
- Crash-corpus result: zero verifier exceptions, zero hangs, no changes to previously gradeable outcomes, unchanged reference/alternative passes, and unchanged anti-gaming failures.
- Production rehearsal: valid typed artifact passed; Gemini scalar produced a normal 40-point failure; malformed agent artifacts failed gracefully; corrupted environment evidence produced a global infrastructure stop.
- Pre-freeze and post-freeze rehearsals: passed with zero API requests.
- Credential scan after execution: no key or authorization marker found in RC1.6 artifacts, reports, or run trees.

## Preserved Gemini regression

| Property | RC1.6 diagnostic replay |
|---|---|
| Exception | None |
| Strict mission | Fail |
| Partial scientific quality | 40/100 |
| Reliability | 100/100 |
| First critical failure | `prospective_plan_implemented` |
| `work/auc.txt` | scalar; `saved_output_mismatch`; no AUC credit |
| Physical sample swap | asserted by the agent, not endorsed by benchmark/oracle |
| Trajectory reconstruction | Pass |
| Lifecycle fault | None |

## Cost and execution

Before launch, effective headroom was `$55.547240141`. The exact no-cache nine-cell estimates were median `$31.514873941` and P90 `$45.892719941`, independently reproduced by an expanded distribution and an exact multinomial calculation. The hard scientific cap was `$50`.

The frozen randomized order was:

1. Claude Sonnet 4
2. GPT-5
3. Claude Opus 4.1
4. Gemini 3.1 Pro Preview
5. Mistral Large 2512
6. Qwen 3.5 397B A17B
7. DeepSeek V3.2
8. Kimi K3
9. GPT-5.1

Live reconciled key usage rose from `$74.452759859` to `$114.278004197`, or `$39.825244338`. The checkpoint captured `$39.81543558` before final billing reconciliation. The seven run summaries total `$39.82355709`. All figures are below the `$50` cap. The current API-key limit remainder is `$15.721995803`.

## Scientific and operational results

`P` means the scientific requirement passed. `F` means it failed. Infrastructure-excluded cells have no scientific score.

| Model | Mission | Partial | Reliability | Plan | Patient/dependence | Site/quantitative | Resource choice | Resource use | Belief revision | Decision support | Submissions A/R | Tool errors | Turns / requests | Reported cost | Classification |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Claude Sonnet 4 | Fail | 40 | 100 | F | P | F | P | P | F | F | 1/0 | 0 | 45/46 | $5.756004 | valid episode |
| GPT-5 | Fail | 20 | 100 | P | F | F | F | F | F | F | 1/0 | 1 | 43/44 | $0.712242 | valid episode |
| Claude Opus 4.1 | Fail | 30 | 100 | F | F | F | F | P | F | P | 1/0 | 0 | 55/56 | $32.666535 | valid episode |
| Gemini 3.1 Pro Preview | Fail | 20 | 100 | F | F | F | F | P | F | F | 1/0 | 1 | 20/21 | $0.318986 | valid episode |
| Mistral Large 2512 | Fail | 20 | 100 | F | F | F | F | F | F | P | 1/1 | 0 | 33/34 | $0.274047 | valid episode |
| Qwen 3.5 397B A17B | Excluded | — | — | — | — | — | — | — | — | — | 0/0 | 0 | 8/9 | $0.062910 | upstream 429 infrastructure failure |
| DeepSeek V3.2 | Excluded | — | — | — | — | — | — | — | — | — | 0/0 | 0 | 20/21 | $0.032832 | isolated connection error, misclassified by frozen runner |
| Kimi K3 | Not run | — | — | — | — | — | — | — | — | — | — | — | — | — | blocked by global stop |
| GPT-5.1 | Not run | — | — | — | — | — | — | — | — | — | — | — | — | — | blocked by global stop |

All five gradeable models passed the schema contract and irreversible-action integrity checks. All five failed the saved-artifact chain. All five failed belief commitment/revision and bounded-claims requirements. There were no undisclosed machine requirements in submission failures.

### First critical failures and downstream effects

- **Claude Sonnet 4:** first failure `prospective_plan_implemented`. The reported analysis did not implement the precommitted analysis or document a defensible deviation. This prevents downstream quantitative results, belief revision, final decision, and claims from being treated as prospectively supported, despite correct patient/dependence work and an appropriate X46 investigation.
- **GPT-5:** first failure `saved_artifact_chain`. Its reported results could not be independently checked from source-linked tables and typed calculation records. This invalidated patient/dependence, site/quantitative, follow-up, evidence-use, belief-revision, decision-support, and claim checks. It selected X63.
- **Claude Opus 4.1:** first failure `prospective_plan_implemented`. The plan-to-analysis mismatch invalidated the prospective evidence chain; entity/site work, resource justification, belief revision and bounded claims also failed. It selected X46 and did reach an evidence-supported PAUSE/NO_USE decision, but not a complete mission.
- **Gemini 3.1 Pro Preview:** first failure `prospective_plan_implemented`. Downstream artifact, entity/site, resource-choice, belief, decision and bounded-claim requirements failed. It selected no purchase and submitted CONTINUE/RESEARCH_PROBABILITY, but the required analysis did not support that decision.
- **Mistral Large 2512:** first failure `prospective_plan_implemented`. Downstream artifact, patient/site, resource-use, belief and bounded-claim requirements failed. It selected X17 and reached an evidence-supported PAUSE/NO_USE decision. Its one rejected submission involved disclosed `column_map` and array constraints and was successfully repaired; this is recoverable submission friction, not a hidden contract floor.

### Artifact-validation failures

- **Sonnet:** one external-validation table invariant mismatch; five calculation outputs were malformed JSON.
- **GPT-5:** one mapped CSV column missing; seven calculation outputs lacked the disclosed `typed_calculations`/calculation-ID structure.
- **Opus:** two table invariant mismatches, one invalid binary outcome, one malformed JSON output, and four calculation outputs without typed calculation records.
- **Fresh Gemini:** one table invariant mismatch plus a second manifest entry with role mismatch/malformed JSON.
- **Mistral:** one mapped CSV column missing and three calculation outputs without typed calculation records.

These are agent artifact failures with trace evidence. None caused a verifier or replay exception.

### Belief revision and decisions

No model passed belief commitment/revision. GPT-5 and Mistral submitted no belief updates. Sonnet, Opus and Gemini supplied updates, but they did not preserve and follow a valid precommitted hypothesis/contingency chain.

Only Opus and Mistral passed evidence-supported decision. No model passed bounded claims. Thus a superficially reasonable final disposition was not enough for mission success.

### Submission and tool behavior

- Sonnet, GPT-5, Opus and Gemini: one accepted submission, no rejected submission.
- Mistral: one rejected and one accepted submission; all rejection rules were disclosed and recoverable.
- GPT-5: one recoverable tool-argument parse error.
- Gemini: one recoverable wrapper tool error.
- No gradeable model had a lifecycle fault, provider fallback, credential leak, protected-data mutation, or grader-replay inconsistency.

## Provider and harness failures

Qwen completed eight usable provider responses before DeepInfra returned `429 engine_overloaded`. Its lifecycle reconstruction passed. The cell was excluded as an isolated provider failure and did not receive a scientific score.

DeepSeek completed twenty usable provider responses before `APIConnectionError('Connection error.')` caused by `ReadError/BrokenResourceError`. Its lifecycle reconstruction and grader replay both passed; there was no shared-state corruption. The generic exception classifier labeled this `unknown_harness_failure`, and the frozen RC1.6 stop policy then treated that label as shared corruption. This is a precise provider-error classification defect. It is not a DeepSeek scientific failure and not evidence of an inconsistent tool lifecycle.

Because RC1.6 was already frozen, the run was not patched or resumed. Kimi and GPT-5.1 remain unexposed in RC1.6.

## Case-2 assessment

- **Genuine capability separation:** suggestive among the five gradeable episodes. Partial quality spans 20–40 and requirement-level pass profiles differ.
- **Credible scientific floor:** yes. Every gradeable model earned meaningful partial credit and failed for consequential evidence-chain errors.
- **Ceiling:** no. Zero of five gradeable missions passed.
- **Artificial contract/completion floor:** not observed among gradeable cells. Every model eventually submitted; only one disclosed, recoverable rejection occurred.
- **Insufficient evidence:** yes overall. Two panel cells were not run and two attempted cells were infrastructure-excluded. One attempt on one development condition cannot support a stable model ranking.

The result supports a narrow claim: after the contract and verifier artifacts were removed, Case 2 elicited real differences in scientific workflow behavior. It does not yet establish a complete cross-model gradient. Failures are also concentrated: four of five first failures are prospective-plan implementation, and all five fail artifact provenance. That concentration must be considered before treating Case 2 as a broad capability measure.

No other condition, held-out case, Astra call, or additional seed was run.

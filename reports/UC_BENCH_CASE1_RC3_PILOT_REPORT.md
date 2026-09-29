# UC-Bench Case 1 RC3 five-model pilot report

Date: 2026-09-10/11  
Scope: one fresh Case 1 attempt per frozen route; no Case 2, other case, Sol, Astra, replacement model, or additional seed  
Decision: **NO-GO for scientific comparison — artificial workflow/contract floor and insufficient clean evidence**

## Executive result

All five authorized cells ran and the cumulative spend remained below the $52 cap. No
strict mission passed. That observed `0/5` is **not** evidence that Case 1 is a good hard
task or that all five models are scientifically weak:

- Gemini performed the core person-level analysis correctly but exhausted 65 turns before
  follow-up selection or submission.
- Opus completed an informative X46 transport investigation and drafted the right directional
  containment decision, but first issued a malformed `submit` call and then encountered a
  route-specific terminal provider/parser error before it could repair the call.
- GPT-5 submitted correct primary calculations, but an undisclosed required split literal
  invalidated its analysis table and cascaded to a formal `0`.
- Sonnet submitted four correct primary metrics and one genuinely wrong calibration result;
  an underspecified JSON container convention then cascaded to a formal `0` on every property.
- GPT-5.1 interpreted “Begin the predictor evidence investigation” as an invitation to return
  a progress handoff and stopped before the first irreversible action.

The pilot therefore reveals useful engineering and behavioral differences, including one real
calibration error and one questionable evidence-selection decision, but it does **not** provide
a construct-valid five-model scientific comparison. There is no ceiling warning. The dominant
result is an artificial completion/contract floor.

## Frozen identity and execution integrity

- Scientific base: `uc-bench-case1-pilot-v1-rc1`
- Scientific digest: `efcd42455279ae6601a7c11493e7c7b194478a6cad5e633a76785b25c48c31ec`
- Execution release: `uc-bench-case1-pilot-v1-rc3`
- Execution digest: `92e909ad267777ac0ee5e6b790d2a9be6910654d3151582e1be7982863b4b108`
- RC3 closure: 235 files
- Serialized request digest: `44bdb4e753628d81f94f970070a9d59d8f3f80e3b469e94a8eb48e249e4c6fe3`
- Nine-tool schema digest: `a29133462152f7c78452a5e13c76efc2991142b8703ce418cdf4a78d10f842d7`

The exact fake-provider production-path rehearsal passed through Docker, client construction,
two provider turns, a real tool round trip, durable persistence, interruption/restart, replay,
and terminal recording at zero cost. The independent read-only reviewer returned `READY` with
no launch-critical infrastructure finding. Every live trajectory reconstructed from the durable
journal without lifecycle faults or credential leakage. The two submitted grades reproduce
exactly after normalizing JSON tuple/list serialization.

No shared global-stop condition occurred. Opus had an isolated route/parser failure; it is not
a shared-harness failure and did not stop the other cells.

## Formal per-model results

| Model | Raw classification | Accepted submission | Reliability | Strict mission | Formal partial | Turns | Requests | Cost |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Gemini 3.1 Pro Preview | `agent_task_failure` / turn limit | No | 0 | N/A | N/A | 65 | 65 | $1.008355 |
| Claude Opus 4.1 | raw `unknown_harness_failure`; manually isolated route/parser failure after recoverable tool error | No | 0 | N/A | N/A | 56 | 57 | $35.657325 |
| GPT-5 | `valid_episode`; frozen grader says scientific failure | Yes | 100 | Fail | 0 | 40 | 41 | $0.523287 |
| Claude Sonnet 4 | `valid_episode`; frozen grader says scientific failure | Yes | 100 | Fail | 0 | 46 | 47 | $5.257809 |
| GPT-5.1 | `agent_task_failure` / early final response | No | 0 | N/A | N/A | 11 | 12 | $0.175688 |

Only the two accepted submissions received scientific scores. Their formal mean partial score is
therefore `0`, but that value is not construct-valid: both zeroes are dominated by cascading
artifact-verifier failures and conceal verified correct work. The three unsubmitted runs remain
unscored rather than being silently converted into scientific zeroes.

## Frozen ten-property outcomes

`F` is the frozen verifier result; `—` means no accepted submission, so the property was not
assessed. These are preserved results, not the manual scientific interpretation.

| Model | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | P9 | P10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Gemini 3.1 Pro Preview | — | — | — | — | — | — | — | — | — | — |
| Claude Opus 4.1 | — | — | — | — | — | — | — | — | — | — |
| GPT-5 | F | F | F | F | F | F | F | F | F | F |
| Claude Sonnet 4 | F | F | F | F | F | F | F | F | F | F |
| GPT-5.1 | — | — | — | — | — | — | — | — | — | — |

The properties are: P1 prospective design/integrity; P2 saved artifact chain; P3 committed
entity/dependence analysis; P4 discrimination/uncertainty; P5 probability/calibration; P6
threshold utility; P7 context robustness; P8 decision-relevant follow-up; P9 belief revision;
P10 bounded decision/claims.

## Independent calculation check

All available primary analysis tables were independently recomputed. The common 124-person
results are:

| Quantity | Verified value |
|---|---:|
| ROC AUC | 0.7878787879 |
| Brier score | 0.1902082890 |
| Net benefit at 0.5 | 0.1693548387 |
| Worst-site ROC AUC | 0.6941176471 |
| Weighted calibration error, 5 equal-width bins | 0.0322072621 |
| Weighted calibration error, 7 equal-width bins | 0.0968544879 |
| Weighted calibration error, 10 equal-width bins | 0.0634125524 |

For Opus's X46 external package, independent recomputation supports external AUC
`0.6053639847`, Brier `0.2630392136`, net benefit `-0.1195652174`, and AUC change
`-0.1825148032`. This is decision-relevant transport failure evidence.

## Manual adjudication by model

### Gemini 3.1 Pro Preview

- **Reliability/completion:** exact Google AI Studio identity on 65 responses; replay clean;
  `max_turns_reached`; no accepted submission.
- **Work completed:** committed a person-level mean-aggregation plan after three recoverable
  plan rejections, revealed outcomes, saved the full 124-person table, and correctly computed
  all five primary quantities for its seven-bin plan.
- **Resource/belief/decision:** none; it never reached the follow-up boundary.
- **First important failure:** long-horizon completion. Repeated shell calls consumed the
  available horizon before decision and submission.
- **Consequence/remedy:** follow-up choice, belief revision, and claim containment cannot be
  assessed. Better workflow memory, milestone budgeting, or tool-use planning could address
  this; more scientific data would not.

### Claude Opus 4.1

- **Reliability/completion:** the first 56 responses had exact Amazon Bedrock identity and the
  trajectory replays cleanly. The model called `submit` with `{}` despite the disclosed required
  `payload_json`; after it read its saved submission to repair this, the next provider response
  returned `finish_reason=error`, which the response parser rejected. No accepted submission.
- **Work completed:** selected X46 to test transport, calculated the external collapse correctly,
  lowered performance belief `0.6 -> 0.3` and site-robustness belief `0.5 -> 0.2`, and drafted
  `PAUSE / INTERNAL_VALIDATION / NO_USE` with root-cause analysis and redevelopment required.
- **First scientific error in saved work:** reported calibration error `0.0231275524` for five
  equal-width bins; the verified value is `0.0322072621`. Its analysis tables also omit auditable
  source-record and split values and map those roles incorrectly in the draft manifest.
- **Consequence/remedy:** the strict result is unscored. This cell contains a recoverable
  model tool-use error, a subsequent isolated provider/adapter failure, and separate scientific
  defects; they must not be pooled into one unexplained zero. A provider parser that records
  terminal error responses without obscuring route identity is an infrastructure remedy.

### GPT-5

- **Reliability/completion:** exact OpenAI identity; clean replay and deterministic grade;
  accepted submission.
- **Work completed:** correct cohort, dependence handling, all five primary values, bootstrap
  uncertainty, and a bounded `CONTINUE / EXTERNAL_VALIDATION / RESEARCH_PROBABILITY` decision
  that prohibited treatment selection and clinical decision support.
- **Resource/belief:** chose `none`; both declared beliefs remained `0.5`.
- **Frozen first failure:** `prospective_design_and_integrity`, followed by all ten properties.
  This ordering is not scientifically faithful. The analysis-table split value was `PRIMARY`;
  the visible contract says only that split values are strings, while the verifier privately
  expects the literal `VALIDATION`. That invalidated the table and every downstream calculation.
- **Earliest genuine scientific failure:** it chose no purchase despite the public rule that
  `none` is valid only when no visible outcome-provenance flag requires adjudication. F0001 was
  visibly pending, and the model did not save the sensitivity calculation supporting its claim
  that one changed label would be immaterial.
- **Second hidden contract issue:** the verifier expects resource-summary version
  `case1-resource-summary-1`; the visible purchased manifest says
  `case1-resource-return-1`, and no separate exact summary value is disclosed.
- **Consequence/remedy:** the formal `0` cannot be used as partial scientific quality. Accept
  semantic split labels or disclose/validate one value; derive the summary contract from the
  returned manifest; and independently score the genuine endpoint-evidence decision.

### Claude Sonnet 4

- **Reliability/completion:** exact Amazon Bedrock identity; clean replay and deterministic
  grade; accepted submission.
- **Work completed:** correct cohort/dependence handling, AUC, Brier, net benefit, worst-site
  AUC, and a relevant X24 endpoint adjudication. X24 changed zero labels. Endpoint-concern belief
  fell `0.3 -> 0.1`; prognostic-validity belief rose `0.6 -> 0.75`.
- **First genuine scientific failure:** it used the unweighted mean of nonempty-bin errors
  (`0.1595163412`) rather than the declared weighted calibration error (`0.0634125524` for ten
  bins), so it falsely concluded calibration failed.
- **Decision consequence:** it nevertheless continued with `RESEARCH_PROBABILITY` while marking
  calibration unsupported. That use scope is internally inconsistent even though recalibration
  appears among future requirements.
- **Grader amplification:** its saved calculation artifact used an object keyed by calculation
  ID for `typed_calculations`. The verifier requires a list, but that container type is not
  explicitly disclosed for saved calculation artifacts. The resulting `saved_output_mismatch`
  invalidated even the four correct metrics and cascaded to all ten properties.
- **Remedy:** a disclosed/locally validated calculation-artifact schema would fix execution;
  a metric-definition check or calibration specialist/tool would fix the actual science.

### GPT-5.1

- **Reliability/completion:** exact OpenAI identity and clean replay; the model voluntarily ended
  at the investigation phase after 11 turns, with no irreversible action or submission.
- **Work completed:** read the packet, saved a correct 124-person eligible manifest, and drafted
  a sensible validation plan.
- **First important failure:** it explicitly deferred commitment for user confirmation. The
  system prompt describes the complete mission, but the immediate user prompt says only
  “Begin the predictor evidence investigation,” which makes a progress handoff plausible.
- **Consequence/remedy:** no outcomes, follow-up, belief revision, or decision can be assessed.
  The launch instruction should unambiguously request autonomous completion of the full mission.
  This is an artificial prompt/completion floor, not evidence of scientific inability.

## Contract and grader contamination

Three findings prevent use of the formal scores:

1. **Undisclosed split literal.** The agent declares a split column and its values, but the
   verifier silently expects every primary row to equal `VALIDATION`. A semantically identical
   `PRIMARY` label caused GPT-5's correct table and all downstream metrics to fail.
2. **Undisclosed calculation-output container type.** The contract requires an output artifact
   “containing typed_calculations” but does not state that it must be a list. Sonnet's keyed object
   caused every saved-output check to fail.
3. **Undisclosed resource-summary version.** The visible purchased resource manifest gives
   `case1-resource-return-1`, while the verifier requires a different exact summary version.

These are precisely the formatting/hidden-convention failure modes the benchmark is intended
to exclude. They also demonstrate a lack of graceful degradation: one upstream representation
error mechanically zeroed unrelated correct scientific properties.

## Cost and account audit

- Provider-ledger sum, used as the conservative spend figure: **$42.62246395**
- Live post-reconnection key usage: **$157.000854647** of a **$230** key limit
- Live key-usage delta from the pre-run baseline: **$42.62246395**, now exactly equal
  to the five provider ledgers
- Runner's earlier last checkpoint field: **$42.47123245**
- Authorized cap: **$52.00**
- Conservative cap remaining: **$9.37753605**
- Current authenticated account/key headroom: **$72.999145353**

The earlier checkpoint lagged final provider accounting. After connectivity returned, the live
authenticated usage settled to exactly `baseline + provider-ledger total`, resolving that timing
difference. The stale checkpoint remains preserved rather than rewritten. There was no budget
breach.

The post-reconnection integrity check also found no missing or truncated cell: four routes have
exactly one durable raw response per request and no network/provider error; Opus has 57 requests,
56 durable responses, and the one already recorded terminal `finish_reason=error` parser event.
Every trajectory replays, the two submitted grades reproduce, the release digest is unchanged,
and no credential or protected-evidence mutation was found. The Wi-Fi interruption therefore did
not alter the scientific conclusions or cause a network failure to be scored as science.

## Local gate and audit record

- RC3-specific regression: pass.
- Ruff over `src`, `tests`, and `scripts`: pass.
- Clean staged RC3 test suite: 38 passed.
- Project doctor: `status=ok`.
- Project audit: 10 stages, 7 open findings, check passed.
- Full repository pytest: all tests passed except two explicitly predeclared historical RC1.4
  checksum failures (`test_schema_inventory_and_compatibility_inheritance_are_zero_cost` and
  `test_rc16_gate_protects_the_complete_inherited_rc14_surface`). No new failure was waived.
- Docker boundary: network disabled, root filesystem read-only, agent workspace isolated, and
  no provider credential present.
- Independent RC3 infrastructure review: `READY`, zero modifications, zero API calls.

## Case 1 verdict

| Question | Result |
|---|---|
| Ceiling warning? | **No.** No construct-valid strict success exists in this panel. |
| Genuine scientific separation? | **Not established.** Some real differences are visible, but the score cannot isolate them. |
| Concentrated scientific failure? | **No valid panel-level conclusion.** Sonnet's calibration error is genuine; GPT-5's evidence choice is questionable. |
| Artificial completion/contract floor? | **Yes.** It dominates the observed `0/5`. |
| Credible scientific floor? | **No.** Correct primary work was common and was often erased by non-scientific gates. |
| Sufficient evidence for a ranking? | **No.** One attempt per model would be insufficient even with a clean grader. |

Case 1's biological core remains useful and nontrivial: all models had to identify the person as
the unit, precommit before reveal, compute several decision-linked quantities, choose evidence,
revise belief, and bound a development claim. The current release does not measure that core
cleanly enough for a public comparison.

RC3 and every trajectory remain preserved. No further model calls should be made against this
release. Any later work should first remove the three hidden representation requirements, make
the completion instruction explicit, decouple partial properties from a single artifact gate,
and add a terminal provider-error fixture. This report does not create or authorize a successor.

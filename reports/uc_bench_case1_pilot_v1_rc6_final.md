# UC-Bench Case 1 RC6 final report

## Outcome

RC6 froze cleanly as `uc-bench-case1-pilot-v1-rc6` with release digest
`a1795f1be20b02bb02d86516a664a3d62aed7d6ca716bdd45cb277b4c1ea6d19`.

The authorized two-cell run completed with no global-stop fault and cost $1.84177605:

| Model | Trajectory provenance | Strict mission | Partial scientific quality | Reliability | First failure | Turns / requests | Cost |
|---|---|---:|---:|---:|---|---:|---:|
| GPT-5 | RC5 trajectory, RC6 offline grading | Pass | 100 | 100 | None | 46 / 47 | $0.57976500 |
| Claude Sonnet 4 | RC5 trajectory, RC6 offline grading | Fail | 37 | 100 | Unreplayable saved-artifact chain | 61 / 62 | $8.93531100 |
| Gemini 3.1 Pro Preview | Fresh RC6 | Not completed | N/A | 0 | Reached 65-response boundary without submitting | 64 / 65 | $1.05476480 |
| GPT-5.1 | Fresh RC6 | Pass | 100 | 100 | None | 65 / 48 | $0.78701125 |
| Claude Opus 4.1 | RC5 provider-excluded episode | N/A | N/A | N/A | Isolated timeout before response 48 | 47 / 48 attempts | $25.53460500 |

“Turns” above is the harness's durable tool-turn count; requests are physical provider
attempts. Gemini's unsubmitted episode is not assigned a scientific score. Opus is excluded
from both scientific performance and reliability.

This is a single-attempt Case 1 development pilot, not a stable model ranking.

## Immutable preservation

- RC4 revalidated at `d9a79a6f1d29248bad2c3b71a3d0546aea1b5ac9920007ae69445242f397ee66`.
- RC5 revalidated at its declared digest
  `b07643c08c05fa09c599e077112c1f8519a0b7c5733928b26974182ed834f762`.
- All 40 agent-visible RC5/RC6 files matched byte-for-byte. Both visible-tree digests are
  `ac76e0c9bcd393c91087ed78e2e8034f846f165e7d86a1dd65b522514c4d5cf3`.
- The request digest, tool-schema digest, provider configuration, model routes, seeds,
  limits, scoring, data, hidden outcomes and resource returns remained unchanged.
- RC6 inherited compatibility because the provider-facing request and tool surface did not
  change. No compatibility or scientific call beyond the two authorized cells was made.

## Causal RC5 adjudication

### Sonnet

The fair RC6 replay is still 37/100 and mission fail. The RC5 hidden relevance bug was real
but score-inert.

| Counterfactual | Score | Mission | Effect |
|---|---:|---:|---|
| Original RC5 submission | 37 | Fail | Baseline |
| Correct hidden X24 relevance only | 37 | Fail | No score or mission change |
| Correct Sonnet's `material` declaration only | 37 | Fail | Hidden RC5 relevance bug still blocks P8; no score change |
| Correct missing calculation artifacts/output links only | 70 | Fail | Restores the evidence chain; other authored calculation/material errors remain |
| Correct relevance and nothing authored | 37 | Fail | No score or mission change |
| Correct every evaluator defect, preserve every authored error | 37 | Fail | Delta 0; mission unchanged |

Genuine Sonnet failures:

- It correctly included all 124 prospectively committed people, making X24 relevant because
  F0001 retained unresolved endpoint provenance.
- Its primary analysis table was valid and it saved `primary_calculations.json`.
- It omitted the calculation-output artifacts from the manifest and linked all five primary
  calculations to `resource_summary`; the decision-driving calculation chain therefore could
  not be replayed.
- Its calibration and utility calculations used the wrong disclosed parameter keys
  (`calibration_bin_count` versus `bin_count`, and `utility_threshold` versus `threshold`).
- X24 changed zero labels but resolved the included endpoint-provenance question. The public
  contract explicitly makes that material. Sonnet's `observed_effect: RESOLVES` was right;
  `material: false` was a genuine disclosed-rule error.
- The bounded continue decision consequently relied on an unreplayable numerical chain and an
  invalid resource assessment.

The hidden RC5 evaluator incorrectly made X24 relevance depend on unrelated primary-calculation
validity. Correcting that changes neither P8 nor P10 for this submission because Sonnet's own
materiality error independently fails P8, and its evidence/decision errors independently fail
P10.

### Opus

Requests 1–47 returned exact `anthropic/claude-opus-4.1` / Amazon Bedrock identity. Request
48 ended with the preserved chain
`ModelError -> APITimeoutError("Request timed out.") -> ReadTimeout -> TimeoutError` and no
response. A no-response timeout contains no identity evidence. The configured safe retry was
not attempted in RC5. The correct classification is isolated provider timeout, with no
scientific score and reliability N/A. RC5's original record remains unchanged.

## RC6 verifier and lifecycle evidence

The canonical resource engine returns independent fields for relevance, evidence authenticity,
result correctness, expected/declared materiality, expected/declared effect, binding to belief
revision and the final resource-property verdict. The hidden grader consumes this one result;
it has no second resource-specific decision tree. Numerical recomputation and protected hashes
remain independent.

Public/hidden semantic parity passed for `none`, X17, X24, X31, X46, X58 and X63. In the exact
archived Sonnet fixture, X24 remains relevant when primary artifact links are broken, while the
broken calculation chain still fails its own properties.

The exact production path passed all lifecycle controls:

- response persistence before parsing/judgment;
- identical-body retry after one timeout;
- safe continuation after successful retry;
- cell exclusion with reliability N/A after two timeouts;
- 429 and 503 classified as provider failures rather than model completion;
- wrong or missing identity on a completed response fails closed;
- no-response attempts do not create identity mismatches;
- invalid JSON is preserved and retried once;
- restart and replay are exact;
- a clean turn-limit completion without provider fault receives reliability zero.

## Common RC6-grader findings

### GPT-5

Passed all ten scientific properties. It used 123 patients after a prospectively justified
one-patient exclusion, selected no purchase because the bounded current decision was resolved,
kept beliefs at 0.60/0.40, and limited use to research probability estimation pending matched
external validation.

### Sonnet 4

Passed prospective integrity, entity/dependence analysis and belief-revision checks. Failed the
saved-artifact chain first, then discrimination/uncertainty, probability/calibration, utility,
context robustness, decision-relevant follow-up and bounded claims through documented
dependencies. The first failure and downstream consequences are scientific/evidence-chain
errors, not wording or hidden-schema failures.

### Gemini 3.1 Pro Preview

All 65 responses had exact pinned model/provider identity; replay and integrity passed. Gemini
committed and revealed validation, committed a no-purchase plan and purchased `none`, but then
continued debugging its self-authored calculation parameters. It reached the disclosed turn
boundary with one unexecuted `run_command` and never submitted. Draft files are retained for
diagnosis, but the episode has no scientific grade. This is a model-completion failure, not a
provider, contract, verifier or infrastructure failure.

### GPT-5.1

Passed all ten properties. Independent recomputation found 123 included patients, ROC AUC
0.7848806366, Brier score 0.1913436038, calibration error 0.0958137398, net benefit at 0.5 of
0.1707317073 and worst-site ROC AUC 0.6941176471. It correctly chose no purchase for the bounded
current question, left beliefs unchanged at 0.50/0.50, continued only to external validation,
and prohibited clinical decision support, treatment selection and transport claims.

## Construct interpretation

- Strict complete missions: 2 of 4 scientifically attempted models. One further model produced
  a valid but failed scientific submission; one did not submit.
- Mean partial scientific quality among the three scoreable submissions: 79/100.
- There is genuine observed separation: 100, 37 and an unsubmitted completion failure under an
  identical model-visible environment.
- There is no credible scientific floor: Sonnet retained meaningful partial credit and Gemini
  completed most of the workflow before failing to finish.
- There is no universal artificial contract/completion floor: two models completed perfectly,
  all identities/replays were clean, and Sonnet's deductions trace to professional errors.
- There is a ceiling warning for this individual case because GPT-5 and GPT-5.1 each achieved
  100 once. This is not saturation evidence; repeated attempts and more cases are required.
- Scientific first-failure concentration is currently 100% at the saved-artifact chain, but
  only one scoreable scientific failure exists. That statistic is not stable evidence of a
  benchmark-wide bottleneck.

## Release gate accounting

All RC6-focused tests, controls, lint, doctor, project-status audit, broad audit execution,
Docker isolation, credential scan, malformed-response tests, exact live-shape fixtures and
clean-stage reconstruction passed. The complete historical suite had exactly two known
pre-existing RC1.4 immutability failures already disclosed and accepted by RC5; no new failure
was accepted. The broad legacy audit correctly continues to forbid public ranking claims because
this pilot lacks repeated runs and external validation.

## Decision

**Go for porting the tested resource-semantics, causal-diagnostic and request-lifecycle
architecture to Cases 2–4.** This is an engineering-architecture go, not evidence that those
cases are scientifically valid and not approval for additional model calls.

Do not claim a stable model ranking. Case 1 now demonstrates tractability, meaningful partial
failure, a distinct long-horizon completion failure and clean infrastructure separation, but
two one-shot 100s create a case-level ceiling warning that only repeated attempts can quantify.

## Future Opus funding estimate

The archived near-complete Opus run used 1,602,557 prompt tokens and 19,950 completion tokens.
At the frozen route ceilings, its no-cache estimate is $25.534605. With a 25% one-run planning
allowance, the projected no-cache P90 cap is **$31.91825625**. This is a planning bound from one
trajectory, not an empirical percentile.

Post-RC6 account and key-limit headroom are each $34.282023553, so the current exact top-up and
key-limit increase required to cover that P90 are both **$0.00**. The margin above the planning
cap is only about $2.36; a future Opus run should refresh both values immediately before launch.
No Opus call was made in RC6.

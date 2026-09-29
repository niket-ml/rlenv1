# UC-Bench Case 2 graceful-failure calibration results

Date: 2026-09-13 PDT (runs completed 2026-09-14 UTC)

## Decision

The authorized three-model calibration completed within budget and without a
provider, identity, replay, integrity, credential, or shared-infrastructure failure.
Case 2 produced genuine differences in how the models conducted the investigation.

The release is nevertheless a **no-go for quantitative comparison of diagnostic
partial scores**. Manual post-run adjudication found that the graceful diagnostic
scorer converts non-failing artifact warnings into errors. In the Sonnet trajectory,
scientifically correct rounded values fall inside the public tolerance and pass the
strict scientific properties, but the diagnostic layer invalidates them under
`saved_output_rounding_binding`. The strict complete-mission outcomes are unaffected.
The frozen release and all raw trajectories remain unchanged.

## Frozen execution surface

- Release: `uc-bench-case2-graceful-failure-v1-budget1`
- Digest: `3233cff94612fa75d80ebbe80468df5a4c73a0ead64d8d7327c01825d3436b4c`
- Predecessor: `uc-bench-case2-graceful-failure-v1`
- Predecessor digest: `1276e91e322b2e84c0a008b24b41add487dcdd2a5faea211ab7d837fb5db3aa4`
- Preservation: all 345 predecessor files hash-identical; nine host-only
  cost-accounting files added.
- Scientific content, prompts, tools, grader, routes, thresholds, and episode budgets:
  unchanged.

The infrastructure-only successor reserves a conservative maximum before each
physical request, settles the reservation when provider billing arrives, carries
unresolved reservations across restart, and enforces the same cumulative panel cap.

## Results

| Model | Strict mission | Reported diagnostic partial | Reliability | End state | Investigation | Turns / requests | Cost |
|---|---:|---:|---:|---|---|---:|---:|
| Gemini 3.1 Pro Preview | Fail | 16.13 | 0 | Turn limit after reveal; no submission | None selected | 65 / 65 | $0.8773 |
| GPT-5.1 | Fail | 65.91 | 100 | Accepted submission; `STOP` | X46, cross-context transport | 51 / 53 | $1.1709 |
| Claude Sonnet 4 | Fail | 43.01 **(contaminated)** | 0 | Turn limit after X46 purchase; no submission | X46, cross-context transport | 65 / 65 | $7.3937 |

The arithmetic mean of the emitted partial scores is 41.68, but it is not a valid
headline result because at least Sonnet's partial score is downward biased by the
diagnostic-scoring contradiction.

### Mission-critical property outcomes

| Property | Gemini | GPT-5.1 | Sonnet 4 |
|---|---:|---:|---:|
| Prospective design and integrity | Pass | Fail | Pass |
| Saved artifact chain | Fail | Fail | Pass |
| Entity/dependence analysis | Fail | Pass | Pass |
| Discrimination and uncertainty | Fail | Pass | Fail |
| Probability and calibration | Fail | Fail | Pass |
| Threshold utility | Fail | Fail | Pass |
| Context robustness | Fail | Fail | Fail |
| Decision-relevant follow-up | Fail | Fail | Fail |
| Bounded decision and claims | Fail | Fail | Fail |

Strict complete-mission success was 0/3. This is a conjunction over consequential
scientific and lifecycle properties, not the diagnostic partial score.

## Manual adjudication

### Gemini 3.1 Pro Preview

Gemini created substantive local work, including a metric script and patient-level
table, but did not register it through the disclosed authoritative work index. It
spent most of the 65-turn allowance inspecting and building, reached reveal near the
end, and never committed a follow-up, purchased evidence, or submitted. Its earliest
important failure is long-horizon workflow completion. One attempted write outside
`work/` produced recoverable feedback and was corrected. This is a model
completion/workflow-efficiency failure, not a provider or harness failure.

### GPT-5.1

GPT-5.1 completed the whole interaction and selected X46 for transport evidence, a
scientifically relevant choice. It then stopped development after the external
transport evidence weakened its context hypothesis (belief 0.50 to 0.20). The
submission still failed because:

1. a declared precommit input artifact was mutated after reveal;
2. several uncertainty records did not match the committed uncertainty method;
3. the X46 analysis was not independently verifiable from its declared table and
   calculation bindings; and
4. the final decision was not fully supported by its own committed contingency.

The direction of `STOP` was plausible, but it was not made decision-eligible by the
saved evidence chain. These are genuine prospective-integrity, uncertainty, and
evidence-binding failures.

### Claude Sonnet 4

Sonnet constructed the strongest primary artifact chain and correctly computed
probability/calibration and threshold-utility quantities. It omitted the committed
cluster-respecting uncertainty for discrimination, did not save a source-linked
site audit, then bought X46 but reached the turn limit before analyzing the return,
revising beliefs, or submitting. Those omissions are genuine scientific and
completion failures.

Its emitted partial score is additionally contaminated: six rounded calculation
outputs differ from the independent recomputation by much less than the disclosed
0.002 tolerance and are marked `scientific_valid: true`; the strict verifier passes
the relevant probability/calibration and utility properties. The diagnostic layer
nevertheless changes each warning into a fatal binding error. Therefore 43.01 must
not be compared numerically with the other models.

## Infrastructure, spend, and scope

- 183/183 provider responses were usable.
- Returned model/provider identities matched the pinned routes; fallback was disabled.
- Zero provider failures, retries, grader crashes, replay mismatches, or global-stop
  faults.
- Every trajectory reconstructed and regraded deterministically.
- No credential leakage or protected-data mutation was found.
- No Case 1, Case 3, Case 4, Sol, or Astra request was made.
- Actual API spend: **$9.4419394** of the authorized $50.
- Unused authorization: **$40.5580606**.
- Post-settlement key usage: $222.677825097 of $300; key headroom $77.322174903.
- Post-settlement account headroom: $107.322174903.
- Outstanding reservations: $0.

The final account delta exactly equals the sum of provider-reported request costs.
Intermediate key-usage snapshots lagged provider settlement and are not the final
accounting authority.

## Interpretation

Case 2 is showing useful workflow separation:

- Gemini performed analysis but failed to organize and finish the decision chain.
- Sonnet built a valid primary chain but omitted uncertainty/context evidence and did
  not complete the follow-up loop.
- GPT-5.1 completed the loop but violated prospective integrity and failed to bind
  follow-up evidence tightly enough to support its final action.

There is no ceiling warning. There is also no defensible stable ranking: this is one
attempt per model, two attempts did not submit, and the partial scorer is contaminated.
The result is best labeled **valid trajectory evidence plus a quantitative diagnostic
scoring no-go**.

## Exact next step

Before any further paid Case 2 calibration, perform one zero-cost verifier repair:

1. keep structural warnings non-fatal when the independent numerical verifier marks
   a calculation scientifically valid within the disclosed tolerance;
2. replay these three immutable trajectories as explicitly labeled diagnostic
   regrades; and
3. rerun the adversarial and alternative-workflow controls to prove the correction
   neither rescues wrong science nor fits these models' answers.

No successor or repair was created automatically as part of this report.


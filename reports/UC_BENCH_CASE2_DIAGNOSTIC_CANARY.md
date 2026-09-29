# UC-Bench Case 2 fresh diagnostic canary

Date: 2026-09-14 PDT / UTC

## Decision

**CANARY NO-GO — DISTINCT FROZEN STRICT-VERIFIER CONTRADICTION.**

The locked partial-scoring repair behaved correctly on a fresh natural artifact chain,
including the rounding-warning edge. However, the broader Case 2 engineering-validation
gate does not pass: an optional, agent-visible diagnostic uncertainty field can make two
otherwise correct required properties fail the frozen strict verifier.

The requested success label
`CASE 2 MMMVP PILOT VALIDATED — REPEATED-SEED CALIBRATION DEFERRED` is therefore **not**
applied. No automatic repair, scientific successor, repeated attempt, other model, other
case, Sol, or Astra run was started.

## Preservation and pre-spend gates

- Frozen release: `uc-bench-case2-graceful-failure-v1-budget1`.
- Frozen digest before and after execution:
  `3233cff94612fa75d80ebbe80468df5a4c73a0ead64d8d7327c01825d3436b4c`.
- Frozen closure: 354 files.
- Diagnostic policy digest:
  `74bf65ff82247f4d53dde873f61b70efaedbabf9d0aea98cc07f1f3475f0cc9d`.
- Immutable diagnostic execution snapshot:
  `development/case2_diagnostic_repair/execution_snapshot_01.json`.
- Snapshot digest:
  `1b9c5b425bdf6742386105f9615b82a2c15e4c9f1c16a1c41ebe5db4d29a1658`.
- Repair controls: 33/33 passed.
- Complete Case 2 closure: 449/449 passed with local Docker access.
- Anti-overfitting search: no model/provider names, historical run IDs, historical
  artifact paths, historical numerical constants, or score-targeting logic in active
  scoring branches.
- Lint passed.

The first 449-test invocation was sandboxed from the local Docker socket and produced
37 Docker-dependent failures plus 412 passes. Its XML is preserved as
`case2_closure_449_sandbox_denied.xml`. The identical invocation with Docker access
passed 449/449; the socket denial was not treated as a product failure.

No paid call occurred before these gates and the snapshot was not changed afterward.

## Authorized call and infrastructure result

Exactly one fresh attempt ran:

| Field | Result |
|---|---|
| Requested model | `anthropic/claude-sonnet-4` |
| Returned model | `anthropic/claude-sonnet-4` on all 65 responses |
| Canonical route | `anthropic/claude-4-sonnet-20250522` |
| Provider | Amazon Bedrock on all 65 responses |
| Fallback/substitution | Disabled; none observed |
| Experiment seed | `2026091401` |
| Provider sampling seed | Not supported by this route; frozen value remained `null` |
| Requests / turns | 65 / 65 |
| Input / output tokens | 2,737,813 / 39,323 |
| Final-context input / output tokens | 34,986 / 39,323 |
| Provider-reported settled cost | **$8.803284** |
| Hard cap | $12.00 |
| Stop | `max_turns_reached` |
| Technical classification | Clean route and infrastructure; model-completion failure |

All 65 request lifecycles completed. Identity validation, credential redaction,
protected-evidence integrity, Docker isolation, complete host-only persistence,
deterministic trajectory replay, and frozen-grader consistency passed. There were no
provider, adapter, infrastructure, authentication, identity, persistence, grader-crash,
or budget failures.

Immediately before execution, effective account/key headroom was $77.322174903.
Immediately after the provider run it was $68.990307903. The durable request ledger
settled every reservation and reports the authoritative run cost above; the immediate
OpenRouter usage refresh lagged that request-level total by $0.471417.

## Frozen and repaired scores

| Outcome | Frozen strict path | Locked repaired diagnostic path |
|---|---:|---:|
| Complete mission | Fail | Fail; unchanged |
| Partial scientific quality | 77.419355 | 77.419355 |
| Reliability | 0 | 0; unchanged |
| Failure class | Model completion failure | Model completion failure; unchanged |

The repaired diagnostic was run twice and was byte-for-byte deterministic. No strict
requirement, mission field, first-failure field, dependency, completion field, or
reliability field changed between the paths.

Every partial-score property was also unchanged:

| Property | Frozen direct quality | Repaired direct quality | Strict property |
|---|---:|---:|---:|
| Prospective design and integrity | 1.0 | 1.0 | Pass |
| Saved artifact chain | 1.0 | 1.0 | Pass |
| Entity/dependence analysis | 1.0 | 1.0 | Pass |
| Discrimination and uncertainty | 1.0 | 1.0 | Pass |
| Probability and calibration | 1.0 | 1.0 | Fail; see contradiction below |
| Threshold utility | 1.0 | 1.0 | Fail; see contradiction below |
| Context robustness | 0.5 | 0.5 | Fail |
| Decision-relevant follow-up | 0.0 | 0.0 | Fail |
| Bounded decision and claims | 0.0 | 0.0 | Fail |

There were **no item-level scorer deltas** and no scientific rescue. The natural
`saved_output_rounding_binding` warning occurred on all six registered calculations.
It remained visible and did not remove their independently verified point credit.
This directly validates the narrow warning/rounding repair without relying on the
historical Sonnet trajectory.

## Exact newly exposed contradiction

The public contract says:

- `calculations[*].uncertainty` is `required: false`;
- its method field is marked `diagnostic_only: true`;
- the mission rule requiring an interval is specifically the discrimination rule; and
- optional work cannot invalidate an otherwise correct primary chain.

The frozen numerical verifier nevertheless accepts uncertainty only for ROC AUC or its
alias. If optional uncertainty is supplied for Brier score or net benefit, it emits
`uncertainty_mismatch`; that changes the required probability/calibration and utility
properties from pass to fail even though their point estimates independently recompute
within tolerance.

A zero-cost in-memory counterfactual removed only the two optional uncertainty objects:

| Required property | With optional intervals | Without optional intervals |
|---|---:|---:|
| Probability and calibration | Fail | Pass |
| Threshold utility | Fail | Pass |

All underlying tables, cohorts, metrics, point estimates, thresholds and artifacts were
unchanged. Partial quality stayed 77.419355 because the property-local diagnostic layer
already retained the valid point credit. Mission success remained impossible for the
independent genuine failures and missing submission below.

This violates the predeclared general invariant: **optional diagnostic work cannot
invalidate correct required work**. It is not a response to a low model score and does
not justify tuning to this trajectory. The raw run and machine canary adjudication are
preserved unchanged; no verifier change follows automatically.

## Manual scientific adjudication

### Independently recomputed primary work

The model correctly constructed 96 provisional biological entities from 203 source
records using the committed `FIRST` aggregation and produced these point results:

| Quantity | Independently recomputed | Assessment |
|---|---:|---|
| ROC AUC | 0.716964286 | Correct |
| Brier score | 0.199368715 | Correct |
| 10-bin equal-width calibration error | 0.078456906 | Correct |
| Net benefit at 0.5 | 0.302083333 | Correct |
| Site-weighted AUC | 0.555400546 | Correct |
| Worst-site AUC | 0.492559524 | Correct |

The committed AUC interval was within the disclosed verifier tolerance. The Brier and
net-benefit interval calculations used NumPy resampling and interpolated percentiles,
not the deterministic `random.Random` and order-statistic convention disclosed in
`scientific_methods.json`. They are valid sensitivity attempts but not valid under the
declared deterministic convention; because they were explicitly optional diagnostics,
that defect should remain local to those interval claims.

### First failures

- **Frozen-reported first decision-critical failure:** probability/calibration, caused
  by the optional-uncertainty contradiction above. This is not accepted as the first
  genuine scientific failure.
- **Earliest genuine scientific failure:** the context audit reports each site's
  `source_row_count` as its entity count. It reports Central 24 instead of 30 source
  records, Coast 14 instead of 36, and North 58 instead of 137. The entity-level point
  estimates are correct, but the required source-to-entity dependence audit is not.
  This is consequential because repeated biopsies could otherwise be hidden.
- **Later genuine scientific/workflow failure:** the accepted follow-up plan commits
  only pass and fail contingencies. The purchased evidence is mixed: external pooled
  AUC 0.672078 and site-weighted AUC 0.670345, but worst-site AUC 0.448864. The draft
  final then selects an uncommitted `external_validation_mixed` branch.
- The external analysis omits the external net benefit of -0.086957 and therefore
  fails to update the utility belief despite evidence relevant to the final use claim.

### Resource, belief revision and decision

The model selected X46 for cross-context transport. That was a scientifically relevant
choice. It read all three returned files and correctly recomputed external AUC, Brier,
site-weighted AUC and worst-site AUC. It did **not** use the resource validly in an
accepted evidence chain: the X46 artifacts and calculations were never registered in
an accepted final submission, the actual mixed result did not match a committed branch,
and the resource was described as `RESOLVES` despite exposing a remaining worst-site
blocker.

The unsubmitted draft changed beliefs as follows:

- discrimination 0.85 to 0.90;
- calibration 0.90 to 0.85;
- context robustness 0.25 to 0.15;
- worst-site adequacy 0.20 to 0.10;
- utility 0.95 to 0.95.

The downward context revisions were directionally sensible. No belief revision is an
accepted benchmark result because the model never submitted; keeping utility unchanged
also misses the negative external net-benefit evidence.

No final decision was accepted. The draft proposed `CONTINUE` at external-validation
stage for retrospective audit only, prohibited clinical decision support and prospective
multi-site use, left context robustness unresolved, supported only prognostic ranking,
rejected multi-site transport, and left clinical utility unresolved. That scope was
substantively cautious, but it was neither lifecycle-valid nor bound to a committed
contingency.

## Completion and workflow evidence

The first recoverable workflow failure was an incomplete validation-plan submission at
event 22. The model corrected three rejected validation-plan attempts and committed at
event 36. It later corrected four rejected follow-up-plan attempts and committed at event
56. Three premature resource attempts correctly returned recoverable phase-order errors.

After purchasing and analysing X46, the model wrote `work/final_submission.py` at event
63 but did not execute it, did not create the intended JSON file, and never called
`submit`. The 65-turn limit therefore produced a genuine model-completion failure with
reliability zero. It is separate from the verifier contradiction and from scientific
errors.

## Final classification

- Diagnostic rounding repair: **validated on its intended fresh edge**.
- Strict Case 2 mission scoring: **not validated** because optional diagnostic
  uncertainty can invalidate required properties.
- Scientific result: meaningful partial success plus genuine context-audit,
  contingency, evidence-use and belief-revision failures.
- Contract/completion result: multiple recoverable contract errors followed by a
  turn-limit non-submission.
- Provider/infrastructure result: clean.
- Stable model ranking: unsupported; one fresh attempt only.

Case 3 was not started under this authorization. Case 2 evidence is preserved for a
separate human decision; this report does not create or authorize another repair.


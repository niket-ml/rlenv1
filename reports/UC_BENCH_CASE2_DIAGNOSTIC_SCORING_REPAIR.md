# UC-Bench Case 2 diagnostic-scoring repair

Date: 2026-09-13 PDT / 2026-09-14 UTC

## Outcome

The narrow zero-cost repair passes. It changes no frozen scientific mission rule and
does not retroactively replace any original score.

The repaired development diagnostic scores are now suitable for comparing partial
work quality across these three preserved trajectories. They are not a stable model
ranking: there is one attempt per model and two runs did not submit.

No model or network call was made. No scientific successor was created.

## Locked policy

The model-independent repair policy was written before implementation and before
historical replay. SHA-256:

`74bf65ff82247f4d53dde873f61b70efaedbabf9d0aea98cc07f1f3475f0cc9d`

It classifies faults as scientific errors, decision-critical provenance/lifecycle
errors, recoverable contract errors, non-failing warnings, or optional diagnostics.
For each class it predeclares strict, partial, diagnostic, reliability, and failure-
classification effects.

## Exact correction

The frozen scorer remains untouched. The new diagnostic-only scorer:

1. uses the frozen independent numerical result as the sole arithmetic authority;
2. restores a scientific point only when that authority reports
   `scientific_valid: true`, a recomputed value exists, and the old rejection consists
   solely of `saved_output_rounding_binding` plus its secondary override marker;
3. keeps the representation warning visible;
4. separately routes genuine full-graph source/output errors to the affected
   saved-artifact-chain item; and
5. recomputes only diagnostic direct-quality points. Strict mission, dependency,
   decision, resource, completion, and reliability fields are inherited unchanged.

This matters for causal scoring: a missing source link can reduce provenance credit
without redefining a correctly recomputed number as mathematically wrong.

## Duplicate-authority audit

The defect was one contradictory chain:

`independent numerical pass` → `representation warning` →
`errors.extend(warnings)` → `artifact_binding_invalid` → `scientific point erased`.

No other warning-promotion or model/trajectory-specific reversal was found. The
complete audit and per-component authority table are retained separately.

One replay-input issue was also identified and contained. GPT-5.1's run summary
embeds a diagnostic-normalized uncertainty alias, whereas its immutable accepted host
save retains the original disclosed alias. Replaying the summary copy created a false
strict-property change. The replay loader now reconstructs accepted host saves plus
the preserved event state. This restored exact agreement with the original strict
grade and did not change any scorer rule.

## Controls and tests

- 33/33 new synthetic and authority-separation controls passed.
- 449/449 complete Case 2 closure tests passed.
- Docker isolation and exact production-path controls passed.
- Lint and JSON validation passed.
- Malformed inputs fail safely.
- Exact, rounded, inside/outside-tolerance, alternative-precision, altered-input,
  wrong-unit/cohort/split, missing-table, source/output, mutation, uncertainty,
  optional/required, alternative-workflow, and universal-policy controls all passed.
- No model names, run IDs, historical paths, or historical numerical constants occur
  in scoring branches.
- Pre-existing X17/X31/X46/X58/X63 branches are public resource-schema semantics,
  not model- or trajectory-specific exceptions; this repair does not change them.

The first broad test invocation was denied access to the local Docker socket and was
not interpreted as a product failure. The identical command passed completely when
run with local Docker permission.

## Diagnostic replay results

Every output is labeled `DEVELOPMENT DIAGNOSTIC REPLAY — NOT A RETROACTIVE FROZEN SCORE`.

| Model | Original strict | Replay strict | Original partial | Replay partial | Delta | Reliability / completion |
|---|---:|---:|---:|---:|---:|---|
| Gemini 3.1 Pro Preview | Fail | Fail | 16.129032 | 16.129032 | 0 | 0 / model completion failure |
| GPT-5.1 | Fail | Fail | 65.909091 | 65.909091 | 0 | 100 / valid completed episode |
| Claude Sonnet 4 | Fail | Fail | 43.010753 | 61.290323 | +18.279570 | 0 / model completion failure |

### Property-level changes

Gemini and GPT-5.1 have no property delta.

Sonnet changes only where the locked general policy requires:

| Property | Original direct quality | Replay direct quality | Cause |
|---|---:|---:|---|
| Saved artifact chain | 1.0 | 0.0 | Six output artifacts omit an unambiguous source-table link: genuine provenance failure |
| Discrimination and uncertainty | 0.0 | 0.5 | Correct AUC point restored; committed uncertainty remains missing |
| Probability and calibration | 0.0 | 1.0 | Both independently correct within-tolerance points restored |
| Threshold utility | 0.0 | 1.0 | Independently correct within-tolerance point restored |
| Context robustness | 0.0 | 0.5 | Correct context point estimates restored; required source-linked context audit remains missing |

The net increase is not an unconditional rescue: losing saved-chain credit offsets
part of the restored arithmetic credit. Follow-up evidence remains unused, no final
decision exists, reliability remains zero, and strict mission failure remains.

No genuine scientific failure was rescued in any trajectory. All strict property
statuses, mission results, completion classifications, and reliability values are
unchanged.

## Preservation

- Frozen release: `uc-bench-case2-graceful-failure-v1-budget1`
- Frozen digest reverified:
  `3233cff94612fa75d80ebbe80468df5a4c73a0ead64d8d7327c01825d3436b4c`
- Frozen closure: 354 files.
- Raw trajectory tree: 915 files.
- Raw tree SHA-256 before and after replay:
  `1c6f78ae7cb7d1dc2a3b769e4565303483f88343c635ffd8fd172242463b1f70`
- Original summaries, scores, ledgers, submissions, workspaces, and host records:
  unchanged.

The initially rejected diagnostic replay was preserved rather than overwritten. It
demonstrates why provenance and arithmetic had to remain separate authorities.

## Quantitative-use decision

**GO for repaired diagnostic partial-work comparison; NO-GO for treating original
frozen partial scores as corrected or for claiming a model ranking.** Strict mission
results remain the benchmark outcome.

## Smallest justified fresh paid validation

If fresh execution is desired, the smallest informative check is one unchanged
Case 2 attempt with Claude Sonnet 4, followed by the repaired diagnostic scorer:

- expected spend: approximately **$7.40**, based on the preserved run;
- proposed hard cap: **$12.00**;
- purpose: verify the diagnostic scorer on a new natural artifact chain without
  tuning the scientific task.

That call is only a proposal. It was not authorized or run here.


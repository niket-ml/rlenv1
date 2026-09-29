# UC-Bench Case 2 RC2 — post-sentinel manual adjudication

## Outcome

The RC2 infrastructure repair succeeded, all three pinned routes were verified, and all
three authorized cells ran without provider, credential, persistence, replay, freeze, or
budget failure. The scientific comparison is nevertheless **not interpretable** because
the only submitted episode exposed material contradictions between the agent-visible
contract and the hidden verifier. The official frozen outputs remain unchanged; this is
a separate development forensic adjudication, not a rescore.

Do not run the remaining GPT-5 or Claude Opus Case 2 cells against this frozen evaluator.

## Release and execution integrity

- RC1 digest before and after RC2 work:
  `8257d5d804e46bbc1b86cddc24a9ffcc0d744b0a73ad95aa92d0ccbc8436cd00`
- RC2 digest before and after scientific execution:
  `f45dd99d4359c3de78e2e7ceb5b8115eaf35483bb82aa0c97316b1260fa03291`
- The machine diff passed all 16 required equalities. The only functional successor
  change was endpoint-catalog identity normalization.
- The zero-cost gate passed 15/15 checks. Case 2 controls, endpoint regressions, release
  regressions, fake-provider rehearsal, restart/replay, Docker isolation, credential
  scan, lint, doctor, audit, semantic parity, and clean-stage verification passed.
- The complete repository suite ran to completion. Two of the four predeclared
  historical exceptions appeared; no new test failure appeared.
- No compatibility inference calls were made. Compatibility was inherited because
  request, tool, adapter, model, provider, and execution-policy hashes were unchanged.
- Post-freeze catalogue checks passed all three routes with fallback disabled.
- Scientific spend was `$10.29837445` of the `$12` cap. No model other than the three
  authorized Case 2 routes was called.

## Route evidence

| Requested route | Pinned provider | Dated canonical slug | Live responses | Identity result |
|---|---|---|---:|---|
| `google/gemini-3.1-pro-preview` | Google AI Studio | `google/gemini-3.1-pro-preview-20260219` | 65/65 | exact pass |
| `openai/gpt-5.1` | OpenAI | `openai/gpt-5.1-20251113` | 17/17 | exact pass |
| `anthropic/claude-sonnet-4` | Amazon Bedrock | `anthropic/claude-4-sonnet-20250522` | 56/56 | exact pass |

## Frozen per-cell results

| Model | Official class | Strict mission | Partial quality | Reliability | Turns / requests | Cost |
|---|---|---:|---:|---:|---:|---:|
| Gemini 3.1 Pro Preview | model completion failure | not scored | not scored | 0 | 65 / 65 | `$1.02696120` |
| GPT-5.1 | model completion failure | not scored | not scored | 0 | 16 / 17 | `$0.21169225` |
| Claude Sonnet 4 | valid submitted episode | fail | 0 | 100 | 55 / 56 | `$9.05972100` |

### Gemini 3.1 Pro Preview

Gemini committed a provisional-fingerprint aggregation, revealed outcomes, calculated
primary performance, committed an X46 transport question, purchased X46, and calculated
the returned context metric. It then exhausted 65 turns without calling `submit`.

Its saved primary values were AUC `0.71696`, Brier `0.19937`, calibration error
`0.07846`, net benefit `0.30208`, and site-weighted AUC `0.55540`. Its saved X46
site-weighted AUC was `0.67034`. The unsent draft incorrectly used a calculation-output
JSON as an analysis table, omitted the primary artifact chain from the decision object,
and described the small returned package as high-quality evidence with no material
limitation. These are useful workflow/scientific observations, but they are not an
official grade because no submission was accepted.

Selected resource: X46. Initial committed beliefs: `0.8` and `0.2`. No authoritative
post-evidence belief update or final decision exists. Earliest official failure:
model-completion failure at the turn limit, not a scored scientific failure.

### GPT-5.1

GPT-5.1 inspected the packet but never committed a validation plan. Its final provider
response ended with `finish_reason=length`, used all 5,000 response tokens as reasoning,
contained no tool call, and therefore ended the workflow. No resource, belief revision,
or final decision exists. This is a separately labelled model-completion failure, not
a provider, contract, infrastructure, or scored scientific failure.

### Claude Sonnet 4

Sonnet completed the full action chain and submitted. It used provisional fingerprint
aggregation, found that all four non-context criteria passed while site-weighted AUC
failed (`0.569 < 0.65`), bought X17 to test identity linkage, and found one merged person
without restoration of context robustness (`0.573 < 0.65`). It revised its support
belief from `0.80` to `0.85` and its context-failure belief from `0.30` to `0.75`. Its
final decision was to continue only a targeted context investigation while prohibiting
current multi-site probability and clinical use.

The official verifier reported 0/10 scientific properties and partial quality 0. That
score cannot be interpreted because the first failure and much of the downstream zero
were created by the contradictions below.

## Construct/grader contamination found after exposure

### 1. Undisclosed manifest separator

The visible field guide specifies the manifest columns but no delimiter inside the
`source_record_ids` cell. Sonnet used a normal quoted CSV cell with comma-separated IDs.
Its manifest contains the correct 96 provisional entities and all 203 source records.
The hidden parser splits only on `|`, creating 65 false membership mismatches. Parsing
the same cells on comma or pipe yields zero mismatches.

This is a representation trap, not a biological-unit error.

### 2. Directly contradictory split-label rule

The visible contract says `PRIMARY`, `VALIDATION`, or any internally consistent nonempty
label receives identical credit and that no private literal is required. Sonnet used
`PRIMARY` consistently in the table and calculation `split_values`. The hidden verifier
nevertheless rejects every table whose literal is not exactly `VALIDATION`.

This is an undisclosed exact-string requirement that directly contradicts the contract.

### 3. Optional sensitivity made mission-critical

The field guide describes reported-patient grouping as a sensitivity analysis. Sonnet
prospectively listed that sensitivity but did not complete its optional outputs. The
hidden prospective-plan check requires every planned output, regardless of role or
decision use, and therefore invalidated prospective integrity and all causal descendants.

This conflicts with the requirement that optional work cannot invalidate a correct
primary analysis.

### 4. Resource-summary schema-version contradiction

The visible contract tells the agent to use `case1-resource-summary-1`. The hidden Case 2
verifier requires `case2-resource-summary-1`. No submission can satisfy both literals.
Sonnet happened to choose the hidden version but still omitted the disclosed normalized
`source_hashes -> results` evidence graph. The latter is a real provenance omission; the
version requirement itself is contaminated.

## Genuine Sonnet deficiencies that remain visible

The contract defects do not imply that Sonnet completed the science correctly. Separate
trace-supported deficiencies include:

- it committed bootstrap uncertainty but omitted the final machine-readable uncertainty
  objects and intervals;
- it supplied calibration parameter `bins` instead of the disclosed `bin_count`;
- rounded final reported values did not exactly equal its saved calculation-output
  values, breaking the disclosed reproducibility binding;
- its site audit was saved separately but not linked as the required context calculation
  output;
- its X17 summary omitted the disclosed normalized source-hash mapping and exact results
  object;
- it described X17 as reducing uncertainty although the environment's rule classifies
  resolved linkage with zero unresolved records as resolving the identity question; and
- its belief updates and final claims therefore were not fully bound to a valid saved
  evidence chain.

These are credible capability or execution findings. They cannot support the official
0/10 vector because the contaminated upstream checks erased independent partial credit.

## Interpretation and next decision

- Infrastructure result: pass.
- Provider result: three exact-route passes; zero provider exclusions.
- Completion behavior: genuinely different—Gemini reached the horizon after substantial
  work, GPT-5.1 stopped before commitment, and Sonnet completed the action chain.
- Scientific capability separation: not established.
- Ceiling warning: none can be inferred.
- Artificial floor: yes, from contract/verifier contradictions plus two ungraded
  non-submissions.
- Safe to expand to GPT-5 and Claude Opus: **no**.

RC2 should remain immutable as a construct-failure diagnostic. No further paid Case 2
calls should occur until a separately reviewed repair has naturalistic regression tests
for comma-delimited memberships, arbitrary consistent split labels, optional analyses,
and the resource-summary contract. Any future repair must replay these three preserved
trajectories diagnostically without altering their frozen results.

Current effective account and key-limit headroom after the run is `$23.983649103`.
A separate `$52` stage would require at least `$28.01635090` more balance and the same
increase in key-limit headroom, but funding is not the present blocker; construct validity
is.

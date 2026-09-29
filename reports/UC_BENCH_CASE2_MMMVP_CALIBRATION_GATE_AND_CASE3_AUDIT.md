# Case 2 calibration gate and Case 3 read-only audit

## Outcome

**Case 2 scientific execution is funding-blocked, not scientifically failed.**
The authorized three-model comparison has not begun. There were **zero inference
calls, zero compatibility calls and $0 incremental scientific spend**. No model
result, scientific failure, completion failure or reliability score exists for
this frozen comparison. Historical trajectories are not pooled into it.

The candidate is adopted as the immutable execution freeze by reference in
[execution_freeze.json](../artifacts/uc_bench_case2_mmmvp_calibration/execution_freeze.json).
Its original bytes and historical pre-authorization metadata are unchanged.
The separate receipt records the user's later conditional authorization, not a
new scientific version. Activation remains blocked until every live gate passes.

## Funding and route verification

Authenticated read-only metadata was refreshed at **2026-09-13 21:59:23 UTC**.

| Funding item | Observed USD |
|---|---:|
| Total account credits | 330.000000000 |
| Account usage | 206.016350897 |
| Available account credit | **123.983649103** |
| API-key limit | 230.000000000 |
| API-key usage | 206.016350897 |
| API-key headroom | **23.983649103** |
| Required cumulative scientific cap | **36.000000000** |
| Account shortfall | **0** |
| Key-headroom shortfall | **12.016350897** |

**No additional account credit is needed.** Raise the API-key limit to at least
**$242.02** (an increase of $12.02), then refresh the gate before any inference.
Neither the account nor the key limit was changed by the assistant.

All three requested aliases, canonical identities, pinned providers, price
ceilings and context/completion limits passed the authenticated catalogue and
endpoint checker. Fallbacks and substitutions remain disabled. These are metadata
observations, not claims of a fresh inference round trip or observed returned
scientific-response identity.

| Frozen order | Requested model | Canonical identity | Pinned provider | Accepted input/output USD per million | Context / endpoint completion limit |
|---|---|---|---|---|---|
| 1 | `openai/gpt-5.1` | `openai/gpt-5.1-20251113` | OpenAI | 1.25 / 10 | 400,000 / 128,000 |
| 2 | `anthropic/claude-sonnet-4` | `anthropic/claude-4-sonnet-20250522` | Amazon Bedrock | 3 / 15 | 200,000 / 64,000 |
| 3 | `google/gemini-3.1-pro-preview` | `google/gemini-3.1-pro-preview-20260219` | Google AI Studio | 2 / 12 | 1,048,576 / 65,536 |

Each model has two matching eligible endpoint entries. Other providers and
over-ceiling entries were explicitly rejected; they are not fallback options.
The scientific per-request completion cap remains 5,000, regardless of the larger
endpoint maximum. Preserve 65 turns, 90,000 total completion tokens, 4,200 seconds
per episode and full conversation/reasoning-state retention.

The existing cost proposal remains $19.08 for the complete panel and $28.61 for
the conservative no-cache workload stress scenario, under a $36 hard cap.
These are planning estimates, not empirical median/P90 measurements. Funding is
tested against the full cap, not against the lower estimate.

Full sanitized evidence:
[prelaunch_gate_20260913.json](../artifacts/uc_bench_case2_mmmvp_calibration/prelaunch_gate_20260913.json).

## Freeze verification

- Candidate file SHA-256:
  `d8415797b27dcb8e9856914fde076819085391e09426890cc2f69127d0ee12ad`.
- Scientific/code closure digest, all **323** entries matched:
  `a681bf89f38b94f1617e126660556776f3b30416d9b8a9c6647bce9f69253526`.
- Public starting packet: exactly **23 files**, full manifest matched.
- All candidate review/test attestations matched.
- Preserved order: GPT-5.1, Claude Sonnet 4, Gemini 3.1 Pro Preview.
- Candidate remains read-only; execution authorization and metadata evidence are
  separate read-only records. No scientific, prompt, contract, verifier, runner,
  tool, route or data file was modified or regenerated.
- Execution-reference receipt SHA-256:
  `e054582ec7f6aedad54863ec28ca0cbec150d6bdf54bca0bb54ea6490a9abcb2`.
- Read-only route/funding evidence SHA-256:
  `8094773380f9d5e8bda53a0d3679650af01424dbe077d80c71e0dd3fc119dd6c`.
- Case 1 RC6's own read-only freeze verification also passed unchanged at
  `a1795f1be20b02bb02d86516a664a3d62aed7d6ca716bdd45cb277b4c1ea6d19`.

The freeze must be checked again immediately before the first future call.
There was no first call during this gate.

## Frozen comparison: no executions yet

| Model | Executed | Strict mission | Partial quality | Reliability | Failure classification | Scientific spend |
|---|---|---|---|---|---|---:|
| GPT-5.1 | No | Not measured | Not measured | Not measured | Funding gate prevented launch | $0 |
| Claude Sonnet 4 | No | Not measured | Not measured | Not measured | Funding gate prevented launch | $0 |
| Gemini 3.1 Pro Preview | No | Not measured | Not measured | Not measured | Funding gate prevented launch | $0 |

This is **0 of 3 executed**, not 0 of 3 missions passed. Funding is an operator
precondition, not an excluded provider cell or an infrastructure/model failure.

| Scientific property | GPT-5.1 | Sonnet 4 | Gemini 3.1 Pro |
|---|---|---|---|
| Prospective design/integrity | Not run | Not run | Not run |
| Saved artifact chain | Not run | Not run | Not run |
| Entity/dependence analysis | Not run | Not run | Not run |
| Discrimination/uncertainty | Not run | Not run | Not run |
| Probability/calibration | Not run | Not run | Not run |
| Threshold utility | Not run | Not run | Not run |
| Context robustness | Not run | Not run | Not run |
| Decision-relevant follow-up | Not run | Not run | Not run |
| Bounded decisions/claims | Not run | Not run | Not run |

No saved agent work, selected resources, ex-ante question, belief history, final
decision, rejected submission, tool error, token use, episode wall time, first
scientific failure or downstream invalidated claim exists for these unstarted
cells. Those fields are unavailable, not zero-scored. Manual scientific
adjudication and per-cell reconstruction/double grading are therefore not
applicable yet. The prior local fake-provider/replay controls remain evidence
about engineering only; they are not substituted for live results.

## Interpretation and next authorized action

**Case 2 verdict: INSUFFICIENT EVIDENCE for a new model comparison because the
funding gate prevented all three runs.** This is not a ceiling, floor, scientific
separation or provider-contaminated result. Local readiness is unchanged.

After the API-key limit is corrected, the existing authorization permits the
same three cells in the same order within $36, following a fresh funding, route
and integrity check. It does not permit redesign, extra seeds, other cases or
substitutions. Continue past genuine model scientific/completion/tool/contract
failures; stop for the declared shared integrity, grader, lifecycle, security or
budget faults. Every apparent scientific failure still requires manual
artifact-level adjudication. No further routine scientific approval is needed
for this already-authorized tranche once its conditions are met.

Remaining limitations are unchanged: one controlled case and one attempt per
model cannot establish a stable ranking; deterministic grading supports a finite
set of disclosed professional workflows, not universal scientific judgment;
formal belief consistency is not Bayesian calibration; and no training-cause or
intervention-benefit claim follows without repeated paired evidence.

## Case 3 read-only audit

The independent read-only audit is complete:
[Case 3 audit](UC_BENCH_CASE3_READ_ONLY_AUDIT.md).
No Case 3 files, data, contracts, graders, controls or trajectories were modified,
and no Case 3 model calls, tests, materializations or successor were created.

Its scientific purpose is worth retaining: reject compromised validation, examine
clean evidence and revise a bounded decision. Three issues need resolution before
later exposure:

1. Original static replay returns and later executable returns are different
   scientific materializations. Their results and provenance cannot be mixed.
2. The historical v0.8 prompt names the defect, X31 and the desired recovery.
   Success there is not evidence of unassisted discovery.
3. Private action/resource allowlists can reject supported bounded alternatives.
   These should not be inherited unchanged merely because the data are useful.

The original collapse/remains returns support materially different progression
assessments. They do not logically require one exact action label regardless of
the committed decision scope. The audit recommends reusing existing science and
proven execution mechanics, not inventing additional cases or difficulty.
Case 3 is **audit-complete, not launch-ready**. No port has been authorized here.

## End-of-day status

| Case | Status at this gate | Next bounded step |
|---|---|---|
| 1 | Accepted final RC6 MMMVP pilot, preserved | None; no rerun or successor |
| 2 | Same immutable MMMVP candidate; routes/integrity pass, key headroom insufficient | Increase key limit to at least $242.02; then refresh gates and execute the already-authorized three-cell panel |
| 3 | Read-only audit complete; credible purpose, unresolved provenance/contract issues | Review the three bounded findings before authorizing a port; no exposure |
| 4 | Original packet, controls and historical development artifacts exist; no current port or release audit performed | Remain unchanged and out of this execution scope |

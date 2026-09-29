# Case 2 frozen three-model calibration

## Outcome

Exactly the authorized three cells completed in the frozen order. Total API spend was
**$7.2195348 of the $36 cap**, matching the independent key-usage delta. There were no
provider exclusions, retries, shared infrastructure failures, protected-data mutations or
credential leaks. All three trajectories reconstruct and reproduce their original grades.

**This does not establish a scientific floor or a ranking.** The frozen scores collapse
correct saved work behind cohort-manifest and artifact-registration failures. There are also
genuine evidence-chain errors, but nine failed properties are not nine independent scientific
deficits. Case 2 is preserved unchanged; this report does not repair or rescore it.

## Execution and integrity

- Candidate SHA-256: `d8415797b27dcb8e9856914fde076819085391e09426890cc2f69127d0ee12ad`.
- 323-file closure: `a681bf89f38b94f1617e126660556776f3b30416d9b8a9c6647bce9f69253526`.
- GPT-5.1 → Sonnet 4 → Gemini 3.1 Pro Preview; one attempt each, no substitutions/fallback.
- Limits unchanged: 65 turns, 5,000 completion tokens/request, 90,000 completion tokens/episode,
  4,200 seconds/episode. Full messages, returned reasoning, tools and costs persisted.
- Case 2 imports shared working-tree code. It therefore finished before the first Case 3
  implementation edit; concurrent source isolation was not assumed.
- The prelaunch gate refreshed funding, route identity/availability/prices and hashes.
- Final funding refresh, 2026-09-13 22:34:11 UTC: account **$116.764114303**, key remainder
  **$86.764114303**. These are timestamped balances, not a promise about future availability.

| Model / pinned provider | Strict mission | Frozen partial /100 | Reliability /100 | Turns / requests / tool actions | Prompt / completion tokens | Runtime | Cost |
|---|---|---:|---:|---|---|---:|---:|
| GPT-5.1 / OpenAI | Fail; unsubmitted | 0 | 0 | 16 / 17 / 32 | 694,612 / 18,566 | 233.387 s | $0.385909 |
| Claude Sonnet 4 / Amazon Bedrock | Fail; submitted | 0 | 100 | 53 / 54 / 53 | 1,838,661 / 31,037 | 457.235 s | $5.981538 |
| Gemini 3.1 Pro Preview / Google AI Studio | Fail; submitted | 0 | 100 | 52 / 53 / 52 | 971,431 / 19,298 | 289.760 s | $0.8520878 |

Turns are the runner's recorded turn count; requests are provider calls; tool actions are
separately counted. Prompt-token totals include repeated conversation history, not unique
context. Reliability means accepted submission, not scientific correctness.

Every completed response had the requested model or its declared exact dated alias on the
pinned provider: GPT-5.1-20251113, Claude-4-Sonnet-20250522, Gemini-3.1-Pro-Preview-20260219.

## All nine frozen property outcomes

| Property | GPT-5.1 | Sonnet 4 | Gemini 3.1 Pro |
|---|---|---|---|
| Prospective design and integrity | Fail | Fail | Fail |
| Saved-artifact chain | Fail | Fail | Fail |
| Committed entity and dependence analysis | Fail | Fail | Fail |
| Discrimination and uncertainty | Fail | Fail | Fail |
| Probability and calibration | Fail | Fail | Fail |
| Threshold utility | Fail | Fail | Fail |
| Context robustness | Fail | Fail | Fail |
| Decision-relevant follow-up | Fail | Fail | Fail |
| Bounded decision and claims | Fail | Fail | Fail |

The machine-level first failure is the cohort commitment in every cell. Required public
columns were `entity_id,source_record_ids,included,preoutcome_exclusion_reason`.
GPT supplied four different columns; Sonnet and Gemini supplied only `entity_id`.
This is a disclosed contract/evidence-binding problem, not evidence that all three agents
failed to understand biological units. Missing fields were committed rather than rejected
and repaired before reveal. That interaction contributes to a contract floor.

## Manual scientific adjudication and retained correct work

### GPT-5.1

Saved `work/analysis_table.csv` correctly represents 96 provisional biological groups,
including source memberships, mean probabilities, labels and contexts. Independent inspection
verified those values. The model did not create its declared work index, save calculation
outputs, select a resource or submit a final decision. Its last response exhausted 5,000
completion tokens in reasoning, with no tool call; the runner stopped at `no_tools_called`.
This is noncompletion under the frozen termination protocol, not proof that another response
or a different output budget could not have completed the work. Neither was tested.

The defensible conclusion is **model completion failure plus cohort-manifest contract failure**.
No final scientific decision, resource judgment or belief revision was observed. Do not infer
biological-unit incompetence or count unattempted calculations as independent wrong results.
Its correct intermediate table is retained here as diagnostic partial work; the frozen
numerical partial score remains zero and is explicitly not a faithful summary of that work.

### Sonnet 4

The first independently demonstrated scientific/evidence-chain error is a mismatch between the
registered analysis and the calculation: `work/analysis_index.json` calls
`work/complete_analysis_table.csv` entity-aggregated, but the file contains 203 biopsy rows for
96 entities. Actual metrics use a different 96-row table. Sonnet also omitted the committed
95% entity-bootstrap uncertainty (1,000 replicates, seed 42).

Independently correct work remains:

- 96-group AUC **0.7209821429**, Brier **0.1986889361**, net benefit **0.3020833333**.
- Site-weighted AUC **0.5686693948**, worst-site AUC **0.5044642857**.
- X46 external AUC **0.6720779221**, site-weighted **0.6703448826**, worst-site **0.4488636364**.

Calibration was genuinely calculated incorrectly: an unweighted average of occupied-bin
errors gives 0.1016308025; population-weighted ECE is **0.0820026337**. Both are below 0.12,
so this error does not itself flip the calibration gate.

X46 was relevant ex ante to Sonnet's declared cross-context transport question. Its return
did not rescue the weak site evidence. Sonnet's final action was **PAUSE / HOLD_CURRENT_CLAIM /
NO_USE**, with clinical decision support, multisite probability use and treatment selection
prohibited. Its transport rejection is directionally supported by manually verified data;
its claimed well-calibrated/prognostic findings lack the submitted reproducible chain and
committed uncertainty. Frozen `returned_evidence_not_authentic` means missing hash/summary
binding—not observed falsification or tampering.

Beliefs: discrimination 0.85→0.95; context robustness 0.30→0.10; calibration 0.80→0.90;
utility 0.90→0.95. These are observed declarations, not validated probabilistic calibration.
There were four rejected validation plans and four rejected follow-up plans, all recovered;
no final submission rejection or wrapper-level tool error.

### Gemini 3.1 Pro Preview

The first independently demonstrated scientific/evidence-chain failure is a placeholder
registered as the real analysis. `work/analysis_table.csv` contains one row
`F0001,S0001,0.5,1,test,Site1`, while the submission claims the 203-record analysis. Its actual
script and `work/results.json` performed meaningful weighted calculations on the real data:

- AUC **0.7198660714**, 100-cluster-bootstrap interval **[0.5951979307, 0.8262681159]**.
- Brier **0.1987443466**, population-weighted ECE **0.0734639288**, net benefit **0.3072916667**.

Those values independently match the declared weighted-row method. The problem is not a
demonstrated inability to calculate them; the submitted evidence points elsewhere. Downstream
supported findings and the final claim therefore lack the required auditable numerical chain.

Gemini purchased **none**, then **STOPPED the current development path / NO_USE**. Existing weak
site performance can support stopping this multisite-use claim. Its assertion that X17 would
not change AUC was not empirically established. Hypothesis H1 remained 0.8→0.8→0.8; no repeated
belief-calibration claim is warranted. One attempted write outside `work/` was recoverably
rejected. No submission-stage schema rejection occurred.

## Failure classes and interpretation

| Class | Observation |
|---|---|
| Scientific | Sonnet's missing committed uncertainty and ECE definition; Sonnet/Gemini's misbound primary evidence |
| Contract / submission | All three invalid cohort manifests; Sonnet's eight recovered plan submissions; missing typed output links |
| Model completion | GPT stopped without final submission after a reasoning-only length response |
| Recoverable tool use | Gemini's one out-of-scope write rejection |
| Provider | None excluded; no retry |
| Shared infrastructure | None; all lifecycle, integrity, persistence and canonical replay checks passed |

The useful signal is **workflow/evidence-chain differences with a substantial contract and
completion floor**. There is insufficient evidence for a clean scientific floor, ceiling,
cross-model ranking or training-cause diagnosis. A checklist, artifact-link validation or
completion support might help, but no paired intervention was run, so none is a demonstrated
remedy. The frozen verifier is deterministic; nevertheless, its registration sensitivity
prevents interpreting zero as absence of useful science. No further Case 2 call or edit was made.

## Replay receipts

All raw runs are under `artifacts/uc_bench_case2_mmmvp_calibration/science/runs/`.
Each contains `run_summary.json`, full `host_trajectory`, request/lifecycle ledgers, isolated
workspace and a separate `post_cell_adjudication.json`. The latter is an annotation, not an
overwritten original result.

| Model | Durable records | Canonical repeated-grade SHA-256 |
|---|---:|---|
| GPT-5.1 | 83 | `33f6ce83f5515b1f38b95294022049f4c41a7c1b0ccec6b211659fa151d79011` |
| Sonnet 4 | 215 | `29182273405a7c28bf41043bff4cf339f186616d61debafa847e483698982706` |
| Gemini | 211 | `ddf78ec127cdb73ee17a46b3d414bcade518c1b2311b56edae33ef259b0130a1` |

No scientific conclusion here relies solely on a grader label; the saved table/script/output
checks are recorded in the per-cell adjudications.

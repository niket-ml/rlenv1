# Case 3 read-only readiness audit

**Verdict: scientific purpose worth retaining; not ready for new model exposure.**
The smallest next step is a provenance-and-contract decision plus a bounded
infrastructure port, not new datasets or a new biological investigation.

The independent reviewer `/root/case3_readonly_audit` inspected source, public
and private files, recorded controls and histories. The main agent corroborated
the prompt leak, private action restrictions and changed X31 implementation.
This was history-informed internal review, not blind or external expert
validation. No tests, materializers, resource execution, API calls or Case 3 file
changes occurred. This report does not authorize implementation.

## What exists and what the agent investigates

The original packet has 15 files, 112 patients and 122 samples. It includes
cohort and endpoint records, locked predictions, feature summaries, model records,
preprocessing configuration/membership/code, execution chronology, sponsor claims,
intended use, a validation manifest and a resource catalogue. The visible reference
membership includes validation records despite a declared training-only fit.
The claimed original AUC is perfect, but an assertion is not a validated result.

Sources: [original packet](</Users/niketrajeevan/Documents/ChatGPT/RL envs/tasks/hard_suite_v07/development/case_03/README.md:1>),
[fit membership](</Users/niketrajeevan/Documents/ChatGPT/RL envs/tasks/hard_suite_v07/development/case_03/pipeline/fit_membership.csv:182>),
[illustrative preprocessing](</Users/niketrajeevan/Documents/ChatGPT/RL envs/tasks/hard_suite_v07/development/case_03/pipeline/preprocess.py:1>).

The professionally meaningful investigation is:

```text
Inspect intended use, biological unit and preprocessing provenance
       |
Commit cohort, analysis and eligibility rules before outcomes
       |
Reveal and calculate original performance
       |
Decide whether it is eligible evidence (not simply whether AUC is high)
       |
Commit the unresolved question and contingent next actions
       |
Optional resource action, including a clean pipeline return
       |
Calculate new performance; preserve original evidence's invalid status
       |
Collapse -> no advancement supported by this signal
Remains  -> bounded research progression may be supported; external gates remain
       |
Report supported claims, uncertainty, next evidence and limitations
```

Existing action interfaces include command execution and the irreversible
validation commit, reveal, follow-up commit, purchase/no-purchase and final
submission sequence. Original releases also have checkpoint-oriented forms;
their interfaces must not be treated as identical to the open MMMVP interface.
The neutral catalogue contains X17, X24, X31, X46, X58, X63 and none.
An early bounded pause may be defensible for an immediate decision; it does not
demonstrate completion of the separate investigation into clean signal recovery.

## Important provenance distinction: two implementations

| Generation | What X31 actually supplies | What can honestly be claimed |
|---|---|---|
| Original v0.7 / v0.8 | Pre-generated replay prediction CSVs plus authored lineage asserting training-only fit and unchanged weights | A controlled evidence/provenance scenario; not an executable proof that the displayed preprocessing caused the original inflated AUC |
| Open MMMVP | Executes a separate frozen three-feature logistic model with private training inputs, normalization and hashed outputs | A real executable controlled return; not numerically the same predictor/return as the original generation |

The original generator constructs a noisy retained signal versus noise-only
collapse and later attaches a lineage record:
[original resource generator](</Users/niketrajeevan/Documents/ChatGPT/RL envs/src/uc_bench/v07_cases.py:459>) and
[lineage construction](</Users/niketrajeevan/Documents/ChatGPT/RL envs/src/uc_bench/v07_cases.py:617>).
Its original high predictions are themselves outcome-informed:
[original prediction generation](</Users/niketrajeevan/Documents/ChatGPT/RL envs/src/uc_bench/v07_cases.py:228>).

The open materializer copies the original data packet but replaces descriptions
and adds its interface. For Case 3 X31 it executes another implementation:
[open materialization](</Users/niketrajeevan/Documents/ChatGPT/RL envs/src/uc_bench/mmmvp_open_environment.py:292>) and
[X31 dispatch](</Users/niketrajeevan/Documents/ChatGPT/RL envs/src/uc_bench/mmmvp_open_environment.py:540>).

Modern retained inputs average public features by fingerprint. Collapse permutes
those patient feature vectors. Thus the two modern returns differ in feature-to-
patient alignment, not just reference-fit scope. Training rows and coefficients
are separately authored; this audit found no demonstrated binding to the original
manifest's weight hash.
[modern input construction](</Users/niketrajeevan/Documents/ChatGPT/RL envs/src/uc_bench/mmmvp_open_interventions.py:103>);
[executed normalization and predictions](</Users/niketrajeevan/Documents/ChatGPT/RL envs/src/uc_bench/mmmvp_open_interventions.py:170>).

**Do not silently mix these generations.** Preserve both. A later port must name
one authoritative input/return generation and keep claims within its provenance.
Do not report the old metrics as results of the new execution, or call a switch
between them a byte-preserving infrastructure change. No generation was selected
or altered during this audit.

## Do the paired conditions support different decisions?

The original hidden truth records the following values. They are **historical
stored values, not freshly recomputed values or modern-model results**.

| Original X31 condition | AUC | AUC lower bound | Brier | ECE | Net benefit |
|---|---:|---:|---:|---:|---:|
| Signal collapses | 0.4895 | 0.3867 | 0.2936 | 0.1720 | -0.0268 |
| Signal remains | 0.7444 | 0.6452 | 0.2056 | 0.0707 | 0.0982 |

Against the original intended-use gates, collapse fails while remains clears the
specified performance gates:
[stored replay metrics](</Users/niketrajeevan/Documents/ChatGPT/RL envs/grader_private/hard_suite_v07/case_03/truth.json:63>);
[original decision thresholds](</Users/niketrajeevan/Documents/ChatGPT/RL envs/tasks/hard_suite_v07/development/case_03/intended_use.json:2>).

That is a meaningful difference in progression evidence. It does not mean
every defensible business question must produce a different exact final enum.
A cautious pause pending independent validation may be compatible with retained
internal signal. A correct clean analysis cannot restore eligibility to the
original contaminated result. Retained discrimination is also not evidence of
clinical treatment benefit or transport.

## Principal construct and grading risks

### 1. Proven answer coaching in historical prompts

The v0.8 condition-specific instructions explicitly say that the original result
is contaminated, the question is CLEAN_PIPELINE_SIGNAL and the resource is X31.
The signal-remains instruction additionally requires increased belief and
recovery toward continuation. These strings are appended to the production prompt:
[condition-specific instructions](</Users/niketrajeevan/Documents/ChatGPT/RL envs/src/uc_bench/v08_interface.py:92>);
[prompt append](</Users/niketrajeevan/Documents/ChatGPT/RL envs/src/uc_bench/v08_interface.py:125>).

Therefore historical success on that prompt cannot establish independent defect
discovery, independent resource choice or blind recognition of the variant.
This is a prompt limitation, not evidence of model capability failure.

The later open materialization is more neutral and has recorded identical
pre-purchase variants. Its existing audit still acknowledges that X31 is an
obvious choice when the visible fit-membership issue is found. Treat that as a
limitation in measuring resource selection, not a reason to make the data obscure.
[recorded open audit](</Users/niketrajeevan/Documents/ChatGPT/RL envs/artifacts/mmmvp_open_rc1/open_endedness_audit.json:1540>).

### 2. Private action/resource restrictions can override justified choices

Original hidden truth specifies X31, fixed action outcomes and prescribed belief
directions. Modern cards retain STOP/STOPPED for collapse and
CONTINUE/EXTERNAL_VALIDATION for remains, with X31 investigation policies.
[original fixed directions/actions](</Users/niketrajeevan/Documents/ChatGPT/RL envs/grader_private/hard_suite_v07/case_03/truth.json:148>);
[modern collapse card](</Users/niketrajeevan/Documents/ChatGPT/RL envs/grader_private/mmmvp_open_rc1/validity_cards.json:278>);
[modern remains card](</Users/niketrajeevan/Documents/ChatGPT/RL envs/grader_private/mmmvp_open_rc1/validity_cards.json:396>).

The open verifier checks final stage, disposition and scope against those private
lists, in addition to checking calculations and committed criteria:
[decision adjudication](</Users/niketrajeevan/Documents/ChatGPT/RL envs/src/uc_bench/mmmvp_open_verifier.py:693>).

This is a concrete risk that supported scientific work plus a defensible bounded
pause fails because the private card demands continuation. Conversely, matching
the card is not enough to establish scientific validity. A later port must resolve
the decision contract rather than merely inherit these private expected labels.
No grader was repaired or candidate control rerun here.

### 3. Do not port an older public scientific checker

No scientific scorer was found copied by the inspected open RC14/16 Case 3
materializer. Scorer exposure is therefore an **inheritance risk**, not an asserted
current Case 3 leak.

Do not copy an entire historical environment along with good lifecycle code:
RC6 imports an RC5 environment that ships public recomputation, and archived
Case 2 environments expose a full scientific grade.
[RC6 environment import](</Users/niketrajeevan/Documents/ChatGPT/RL envs/src/uc_bench/case1_pilot_v1_rc6_runner.py:14>);
[RC5 public validator construction](</Users/niketrajeevan/Documents/ChatGPT/RL envs/src/uc_bench/case1_pilot_v1_rc5_environment.py:703>);
[archived Case 2 checker](</Users/niketrajeevan/Documents/ChatGPT/RL envs/src/uc_bench/case2_pilot_v1_rc1_environment.py:202>).

Use the repaired Case 2 structural-only boundary as the port pattern:
[structural-only exports](</Users/niketrajeevan/Documents/ChatGPT/RL envs/development/case2_mmmvp/environment.py:106>).
This is a future reuse recommendation, not a request to reopen accepted Case 1.

## Reusable controls, alternatives and history

Existing evidence can be retained without rewriting it:

- Original records, sealed outcomes, resource packages and both controlled outcomes.
- Source-linked calculations, protected hashes and commitment chronology.
- Recorded positive controls for reference and distinct aggregation/dependence
  workflows, and negative controls for copied paired decisions and altered-input
  copied results. These are archived control results, not fresh local passes.
- Historical artifacts and traces, labelled by their original prompt, return
  generation and grading policy.

Sources: [recorded controls](</Users/niketrajeevan/Documents/ChatGPT/RL envs/artifacts/mmmvp_open_rc1/open_endedness_audit.json:54>),
[paired-copy rejection](</Users/niketrajeevan/Documents/ChatGPT/RL envs/artifacts/mmmvp_open_rc1/open_endedness_audit.json:630>).

Meaningful professional variation includes dependence-preserving aggregation
versus appropriately weighted repeated rows, direct fit-membership reconstruction
versus lineage auditing, ranking versus probability claims, and conditional
continuation with explicit unresolved external gates. Existing readiness prose
already recognizes an early stop when clean recovery has no value under an
explicit business contract:
[historical readiness alternatives](</Users/niketrajeevan/Documents/ChatGPT/RL envs/reports/generated/hard_suite_v08_mvp_readiness.md:20>).
A future implementation must distinguish an acceptable bounded stop from a claim
to have completed unperformed clean-replay analysis.

Historical v0.7.1 collapse chose X46; remains used X31 but was penalized under
legacy belief/action expectations. Do not interpret those scores as current
capability diagnoses without the full contract context. The original v0.8
interrupted remains attempt lacks complete messages, tool results and runner
state; it cannot safely resume:
[preserved resume assessment](</Users/niketrajeevan/Documents/ChatGPT/RL envs/artifacts/diagnostics/hard_suite_v08_case3_resume_assessment.json:3>).
This does not imply later durable trajectories have the same defect.

## Smallest next port, subject to later approval

1. **Declare the existing authoritative materialization.** Bind original versus
   open-generation inputs, predictor identity, return files and claims; preserve
   the other generation and every historical score unchanged.
2. **Use a neutral, disclosed decision contract.** Do not inherit the historical
   solution-giving prompt, fixed belief movements or unqualified hidden
   resource/action preferences. Judge supported claims and committed decision
   scope; retain the paired evidence difference.
3. **Port only proven execution/verification mechanics.** RC6 lifecycle,
   provider identity, tool dispatcher, durable ledger, timeout isolation and
   replay; repaired Case 2's private boundary, artifact-referencing interface,
   committed-cohort reconstruction and causal partial grading. Case 2 classes
   are Case-2-specific and cannot simply be instantiated as Case 3.

This audit supports retaining the Case 3 investigation but **does not establish
launch readiness**. The requested scope ends here: no new data, no successor,
no infrastructure port, no fresh controls and no model exposure.

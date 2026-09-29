# Results

Updated 28 September 2026. These are the existing pilot results; no new model runs were made for this summary.

## Models

| Report label | Model | Requested API ID |
|---|---|---|
| Model 1 | GPT-5 | `openai/gpt-5` |
| Model 2 | GPT-5.1 | `openai/gpt-5.1` |
| Model 3 | Claude Sonnet 4 | `anthropic/claude-sonnet-4` |
| Model 4 | Gemini 3.1 Pro Preview | `google/gemini-3.1-pro-preview` |

## Case 1

| Model | Outcome | Work score / 100 | Submitted | API requests | Cost USD |
|---|---|---:|---|---:|---:|
| GPT-5 | Pass | 100 | Yes | 47 | 0.58 |
| GPT-5.1 | Pass | 100 | Yes | 48 | 0.79 |
| Sonnet 4 | Fail | 37 | Yes | 62 | 8.94 |
| Gemini 3.1 Pro Preview | Incomplete | Unscored | No | 65 | 1.05 |

Two models passed. Sonnet's saved files did not provide a reproducible chain for the reported calculations. Gemini reached the response limit without submitting.

GPT-5 and Sonnet were graded from their preserved RC5 runs using the final RC6 verifier. GPT-5.1 and Gemini ran directly on RC6. An Opus 4.1 attempt was excluded after a provider timeout.

[Final Case 1 report and exact costs](../reports/uc_bench_case1_pilot_v1_rc6_final.md)

## Case 2

| Model | Outcome | Work score / 100 | Submitted | API requests | Cost USD |
|---|---|---:|---|---:|---:|
| GPT-5 | Fail | 78.49 | Yes | 36 | 0.50 |
| GPT-5.1 | Fail | 65.91 | Yes | 53 | 1.17 |
| Sonnet 4 | Incomplete | 61.29 | No | 65 | 7.39 |
| Gemini 3.1 Pro Preview | Incomplete | 16.13 | No | 65 | 0.88 |

None passed the complete mission.

- GPT-5 omitted its promised uncertainty interval. Its utility calculation also lacked required parameters, although the numerical value was correct.
- GPT-5.1 changed a declared input after seeing outcomes and left gaps in the evidence supporting its follow-up analysis.
- Sonnet omitted required uncertainty and did not finish analysing the purchased evidence.
- Gemini did not register enough completed analysis before the response limit. No specific scientific error was established.

GPT-5 ran as a later supplemental attempt. The other scores come from accepted replays under the repaired verifier. The second Sonnet attempt remains archived and is excluded from this table.

[Final release report](../reports/UC_BENCH_CASE2_MMMVP_V1_RELEASE.md) · [Replay scores](../artifacts/uc_bench_case2_mmmvp_v1/replay_parity.json) · [GPT-5 run](../artifacts/uc_bench_case2_mmmvp_v1/supplemental_science/runs/case2-mmmvp-v1-gpt5-supplement-20260914-1/run_summary.json)

Case 2 is [packaged and frozen](../artifacts/uc_bench_case2_mmmvp_v1/release_freeze.json). Earlier reports calling it unfrozen predate that record.

## What the scores mean

A work score awards credit for independently verified analysis. Passing the mission requires every required scientific check to pass and a completed submission. An agent can earn substantial credit and still fail the mission.

Case 1 leaves unfinished attempts unscored. Case 2 assigns credit to verifiable unfinished work. Their average work scores therefore use different denominators.

Each model has one retained attempt per case in these tables. The results show what happened in those attempts; repeated runs are needed to estimate reliability.

## Cases 3 and 4

**Case 3:** the current version has six passing reference workflows and 102 recorded focused test passes. Model evaluation on this version is pending. The two reference outcomes have AUCs of about 0.50 and 0.73. [Readiness report](../reports/UC_BENCH_CASE3_MMMVP_LOCAL_READINESS.md).

Older Sol runs exist for [signal collapse](../build/hard_suite_v072_runs/v072-gpt-5.6-sol-case_03_signal_collapses-20260909T043741Z/run_summary.json) and [retained signal](../build/hard_suite_v08_runs/v08d-gpt-5.6-sol-case_03_signal_remains-20260909T073739Z/run_summary.json). They used earlier versions. The collapse record includes contradictory success/failure diagnostics, so those historical scores are not current results.

**Case 4:** an [older Sol run](../build/hard_suite_v08_runs/v08d-gpt-5.6-sol-case_04-20260909T074038Z/run_summary.json) exists. Its grading rules need review before its score can be used. There is no final Case 4 release or result for the current model panel.

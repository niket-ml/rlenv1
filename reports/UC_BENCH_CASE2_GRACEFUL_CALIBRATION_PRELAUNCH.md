# Case 2 staged calibration: stopped before inference

**NO-GO: unresolved request billing is not reserved by the sealed cost checker.**

The user authorized a $44 cumulative staged panel, with Gemini first under $15.
No scientific or compatibility API calls were made, and no environment, grader,
contract, route, budget or frozen file was changed. There is no scientific result.
The authorization is unspent; the explicit budget-enforcement stop condition applies.

## Minimal checks completed

- Execution closure verified:
  `1276e91e322b2e84c0a008b24b41add487dcdd2a5faea211ab7d837fb5db3aa4`.
- The manifest's validation-receipt hash and all referenced test-report hashes match.
- The two documented historical RC1.4 provenance failures remain the recorded
  exceptions. Both temporary-directory setup-error rechecks are recorded as passing.
- All protected-tree/specification hashes remain unchanged. No historical grading
  or trajectory was resumed or rescored.
- The new calibration output path was absent before prelaunch work. Only local
  fault-injection evidence now exists there; no scientific run directory was created.
- Installed Docker image verified locally:
  `sha256:637830b4ea37fba004f823960608eef0a04fe768b3a67b04ce67e69651adcca8`.
- The local production-path probe confirmed network-disabled, read-only-root,
  unprivileged Docker isolation, with only `/workspace` and writable
  `/workspace/work` mounts; no credential environment was present.

Live funding/route refresh was not reached: the local budget-safety condition
failed first. Previous funding figures are not presented as a fresh check. No key
was loaded and no account setting was changed during this prelaunch work.

## Exact defect

The normal per-request upper-bound check exists, but it subtracts only **reported**
cost. An exception with unresolved billing is recorded with empty usage and zero
reported cost. The automatic retry therefore reuses the full available allowance.

Relevant frozen code:

- [Error cost defaults to zero](</Users/niketrajeevan/Documents/ChatGPT/RL envs/src/uc_bench/v06_provider.py:334>).
- [Cumulative cost sums reported amounts only](</Users/niketrajeevan/Documents/ChatGPT/RL envs/src/uc_bench/v06_provider.py:364>).
- [Pre-request check subtracts that reported total](</Users/niketrajeevan/Documents/ChatGPT/RL envs/src/uc_bench/case1_pilot_v1_rc4_runtime.py:151>).
- [A transient failure can immediately retry](</Users/niketrajeevan/Documents/ChatGPT/RL envs/src/uc_bench/case1_pilot_v1_rc4_runtime.py:178>).
- [Resume also reconstructs prior cost from reported usage](</Users/niketrajeevan/Documents/ChatGPT/RL envs/development/case2_graceful/runner.py:304>).

### Zero-cost reproduction through the frozen production runner

The existing `run_case2_episode` and real client factory were used with an injected
local transport that raises `ReadTimeout("connection timeout")`. Outbound Python
networking was blocked. This is a fault-injection check, not a Gemini attempt or a
live compatibility check. No source code was patched, and no new test suite was run.

| Physical fake request | Maximum request cost recorded | Remaining allowance recorded | Reported cost | Billing evidence |
|---|---:|---:|---:|---|
| Initial | $0.069454 | $0.100000 | $0 | Missing; injected timeout |
| Permitted retry | $0.069454 | $0.100000 | $0 | Missing; injected timeout |

The combined unresolved bounds are **$0.138908**, exceeding the **$0.10** test
allowance. The retry should not have been allowed while the first bound was still
unresolved. The same issue can occur near the real $15 stage cap or $44 panel cap.
This does **not** claim that a provider actually charged either amount; there were
no real requests. It demonstrates that the required conservative guarantee fails.

The exact evidence is retained in:

- [Request ledger](</Users/niketrajeevan/Documents/ChatGPT/RL envs/artifacts/uc_bench_case2_graceful_calibration/prelaunch/local_fault_injection/local-unresolved-billing-proof/request_ledger.json>).
- [Request lifecycle](</Users/niketrajeevan/Documents/ChatGPT/RL envs/artifacts/uc_bench_case2_graceful_calibration/prelaunch/local_fault_injection/local-unresolved-billing-proof/request_lifecycle.json>).
- [Local probe summary and persistence](</Users/niketrajeevan/Documents/ChatGPT/RL envs/artifacts/uc_bench_case2_graceful_calibration/prelaunch/local_fault_injection/local-unresolved-billing-proof/run_summary.json>).

The earlier local gate demonstrated reported-cost checkpointing and bounded retry
counts, but did not establish unresolved-billing reservation safety. This is a gap
in that validation, not a reason to change any scientific requirement or score.

## Scheduled cells

| Model / route | Execution | Scientific properties, quality, reliability, decisions and recovery | Actual API spend |
|---|---|---|---:|
| Gemini 3.1 Pro Preview / Google AI Studio | Not launched | Not observed; not zero | $0 |
| GPT-5.1 / OpenAI | Not launched | Not observed; not zero | $0 |
| Sonnet 4 / Amazon Bedrock | Not launched | Not observed; not zero | $0 |

The fake transport's timeout classification is not evidence of an actual provider
outage. No model capability, contract-friction, recovery, scientific-separation,
ranking or saturation conclusion is possible from this prelaunch stop.

## Required next decision—not implemented

Execution needs a narrowly authorized budget-accounting repair: persist a
reservation before each physical attempt; retain unresolved reservations across
retries, cells and restart; deduct actual settled charges plus outstanding bounds;
release a bound only after settlement or confirmed non-billing. Confirmed charges
and unresolved estimates must remain separate in reporting.

No increased cap, scientific change, additional attempt or replacement model is
needed. The sealed release is preserved. No patch or automatic successor has been
created; further engineering requires authorization beyond the execution-only request.

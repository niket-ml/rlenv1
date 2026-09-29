# Stage 8 — v0.6 semantic-artifact and provider-panel audit

Date: 2026-09-08

Decision: **the pre-exposure construction gates passed, but the frozen v0.6
sentinel is an infrastructure no-go. It produced no model response or
scientific result and must not be resumed.**

## Complete

- Preserved the frozen v0.5 suite and diagnostic no-go. Its 17 hashes still
  match; its recorded ceiling-model exposure remains zero.
- Implemented a separately versioned ten-artifact evidence DAG, new scenario
  IDs and seeds, six development states, and six held-out states.
- Implemented independent semantic-invariant grading, coverage, completed-work
  quality, reliability-inclusive score, capability vector, first divergence,
  and descendants-at-risk reporting.
- Implemented irreversible hashing of the presence and content of A01–A07,
  the locked model, and declared analysis files; resource selection is also
  immutable after reveal.
- Passed reference, alternate-method, professional-paraphrase, mediocre,
  universal-policy, graceful-partial-credit, leakage, and mutation controls.
- Completed the authorized non-scored compatibility stage. Sol, Claude Opus 5,
  pinned Gemini 3.1 Pro Preview, Kimi K3, and GPT-5.2 all passed on exact native
  routes.
- Integrated those adapters into the scientific runner with route price caps,
  request-level identity verification, provider-visible reasoning-state
  preservation, atomic cost ledgers, and zero SDK retries.
- Added a fair 65-turn, 90,000-total-completion-token, 4,200-second envelope,
  deterministic submission handling, one verified-infrastructure retry, and a
  fail-closed context policy.
- Froze the complete 30-cell configuration before any scientific model response;
  the manifest contains 31 hashes under hash-set digest
  `f96e3c725700a0f696a0ad44e7d08a0cff5a8024fb09710d88605b760078eb6e`.
- Strengthened the pre-exposure ceiling contract without changing any scientific
  task, scenario, prompt, artifact invariant, or score: 60–70 is desired, above
  70 through 75 acceptable, above 75 through 80 insufficient headroom, above 80
  a ceiling no-go, and below 60 an over-hard no-go.
- Added deterministic probe analysis that separates accepted-submission
  scientific quality from reliability; attributes the strongest model's losses
  by capability, artifact family, and scenario; tests meaningful partial credit;
  and requires artifact trace, professional consequence, actionable remedy, and
  intervention class for every material deduction.
- Predeclared the two-state scenario-concentration limitation: observed shares
  will be reported, while the 30% gate is applied only to all six development
  states because two positive shares cannot both be at or below 30%.
- Refreshed authenticated routes, exact prices, account balance, and key limit
  using read-only metadata calls. Inference calls made by the cost refresh: 0.
- Launched only the balanced development sentinel. The first cell stopped after
  two preserved zero-cost gateway attempts and the frozen retry allowance was
  exhausted. No endpoint returned a model response, no artifact was agent-
  produced, and no remaining cell was attempted.

## Failed or superseded

- v0.5 remains a no-go: one state explained 67.25% of its observed gap and two
  valid responses exposed vocabulary-dependent grading.
- A GPT-only development panel is superseded for v0.6. It remains useful only
  as a same-family temporal ladder within the wider panel.
- External expert equivalence was not performed. The internal controls support
  development calibration only, not strong public or commercial validity.
- The first freeze preview failed closed because the freeze reader expected the
  wrong local-control field name. The reader was corrected and the preview was
  regenerated; no actual freeze or model call occurred.
- The frozen scientific adapter failed twice before inference. Attempt 1 returned
  HTTP 401 because the client was constructed before the key was exported.
  Process-level credential export corrected that without changing frozen files.
  Attempt 2 returned HTTP 404 at OpenRouter's `Filter by Parameters` step.
- Compatibility did not test the exact scientific payload. The scientific
  adapter supplied `parallel_tool_calls: false` together with
  `require_parameters: true`, while the pinned OpenAI endpoint did not advertise
  `parallel_tool_calls`. The frozen classifier recorded both as
  `unknown_harness_failure`; the audit identifies the second as a provider-
  adapter routing defect without rewriting the raw record.

## Changed in v0.6

- Three aggregate v0.5 submissions become ten meaningful professional
  artifacts.
- Exact narrative matching is removed from scientific credit; parsed
  properties and recomputed evidence determine scores.
- Missing work affects coverage and reliability without erasing the quality of
  completed work.
- Provider adapters use automatic tool choice for Anthropic and Moonshot.
  Claude uses an ordinary workflow prompt and enough completion room for the
  provider reasoning minimum. Gemini reasoning fields are round-tripped without
  rewriting. Both OpenAI models use native routes.
- Every request pins provider order/only, disables fallback, imposes a price
  ceiling, and verifies returned model/provider identity.
- Scientific response refusals score zero reliability; only explicit
  provider-policy blocks are excluded. Usable non-submission preserves
  partial-artifact diagnostics but also scores zero reliability.
- The freeze preview hashes task, grader, controlled and held-out states,
  adapters, runner, controls, cost contract, Docker contract, and runtime
  package versions. It explicitly records that v0.6 is not yet frozen.

## Spend

- v0.6 endpoint/model responses: 0; gateway attempts: 2.
- Compatibility stage cap: $3.
- Response-reported compatibility spend: $0.04574225.
- Final reconciled account/key usage before the sentinel: $38.62223292 of $130;
  remaining: $91.37776708.
- Full 30-cell projection: $92.55 median, $138.36 P90, $167 P90-plus-20%
  conservative cap; projected sequential wall time 3.21 hours median and 6.85
  hours P90.
- Balanced ten-cell sentinel projection: $30.85 median, $46.12 P90, $56 cap;
  1.07 hours median and 2.28 hours P90.
- Required upward-rounded account top-up/key-limit increase: $0 for the sentinel
  or $75.63 for the full cap from the recorded baseline. No account setting was
  changed.
- Sentinel incremental spend: $0 by both response and final key reconciliation.
- Astra requests: 0; held-out requests: 0.

## Remaining blockers

1. Frozen v0.6 cannot be resumed or repaired. An infrastructure-only v0.6.1 must
   preserve the scientific tasks and add exact compatibility/scientific-payload
   parity, credential initialization before client construction, supported-
   parameter filtering, and correct adapter-error classification.
2. Any v0.6.1 run needs a new freeze/checkpoint and explicit approval; the v0.6
   retry allowance is exhausted.
3. A one-seed development pilot cannot support a stable ranking. Held-out and
   ceiling-probe execution remain prohibited.
4. External expert equivalence remains absent; internally authored controls
   support development calibration, not strong public or commercial claims.

## Evidence

- `configs/hard_suite_v06.json`
- `configs/hard_suite_v06_model_panel.json`
- `configs/hard_suite_v06_execution.json`
- `grader_private/hard_suite_v06_heldout.json`
- `tasks/hard_suite_v06/TASK.md`
- `src/uc_bench/hard_suite_v06.py`
- `src/uc_bench/v06_compatibility.py`
- `src/uc_bench/v06_provider.py`
- `src/uc_bench/hard_suite_v06_runner.py`
- `src/uc_bench/v06_freeze.py`
- `src/uc_bench/v06_probe_analysis.py`
- `scripts/build_v06_controls.py`
- `scripts/run_v06_compatibility.py`
- `scripts/build_v06_cost_plan.py`
- `scripts/freeze_v06.py`
- `scripts/run_v06_pilot.py`
- `scripts/analyze_v06_probe.py`
- `artifacts/diagnostics/hard_suite_v06_controls.json`
- `artifacts/diagnostics/hard_suite_v06_provider_plan.json`
- `artifacts/diagnostics/hard_suite_v06_compatibility.json`
- `artifacts/diagnostics/hard_suite_v06_compatibility_attempts/`
- `artifacts/diagnostics/hard_suite_v06_cost_plan.json`
- `artifacts/diagnostics/hard_suite_v06_freeze_preview.json`
- `artifacts/diagnostics/hard_suite_v06_freeze.json`
- `artifacts/diagnostics/hard_suite_v06_calibration_runs.json`
- `artifacts/diagnostics/hard_suite_v06_probe_analysis.json`
- `reports/generated/hard_suite_v06_compatibility_report.md`
- `reports/generated/hard_suite_v06_provider_plan.md`
- `reports/generated/hard_suite_v06_cost_plan.md`
- `reports/generated/hard_suite_v06_probe_report.md`
- `reports/generated/hard_suite_v06_sentinel_no_go.md`
- `docs/HARD_SUITE_V06_SPEC.md`
- `docs/V06_CROSS_PROVIDER_PANEL.md`
- `docs/V06_PRE_EXPOSURE_GATE.md`
- `tests/test_hard_suite_v06.py`
- `tests/test_openrouter_catalog.py`
- `tests/test_v06_compatibility.py`
- `tests/test_v06_provider.py`
- `tests/test_v06_execution.py`
- `tests/test_v06_cost_plan.py`

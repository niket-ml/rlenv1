# Stage 8 evidence — UC-Bench v0.7 vertical slice

Decision: local construct gate passes; paid calibration remains unauthorized.

## Preservation boundary

- v0.6.3 remains frozen at hash-set digest `cdfabd12d6a8e588039bb5897f314a35008b795e6914311b56d26541708074ed`.
- No v0.6.3 score or grader was changed.
- v0.7 has made zero model calls and is not frozen.
- No v0.7 runner, held-out case, or Astra configuration exists.

## Evidence

- Scientific contract: `docs/HARD_SUITE_V07_SPEC.md`
- Public task and four case packets: `tasks/hard_suite_v07/`
- Environment and grader: `src/uc_bench/v07_environment.py`, `src/uc_bench/v07_grader.py`
- Controls: `artifacts/diagnostics/hard_suite_v07_controls.json`
- Validity cards: `artifacts/diagnostics/hard_suite_v07_case_validity_cards.json`
- Failure/remedy and paired interventions: `artifacts/diagnostics/hard_suite_v07_failure_remedy_map.json`, `artifacts/diagnostics/hard_suite_v07_intervention_design.json`
- Reset traceability: `artifacts/diagnostics/hard_suite_v07_reset_traceability.json`
- Replays: `artifacts/replays/hard_suite_v07/`
- Cost gate: `artifacts/diagnostics/hard_suite_v07_cost_plan.json`
- Pre-approval synthesis: `reports/generated/hard_suite_v07_preapproval.md`

## Local gate

Reference and alternative workflows score 100. Empty, generic, and keyword attacks score at most 15. Universal decision policies cannot pass all four missions. Buy-everything fails. The ordinary-error recovery score is 94. Tamper, hidden-access, and commitment-mutation controls fail closed. Opposite clean-replay returns require opposite final decisions. The maximum reference trajectory uses 18 of 80 tool calls.

The builder-authored computational-biology and RL-environment checklists pass. This is not independent external expert validation.

## Next authorized boundary

Review only. A subsequent approval would be needed to implement and freeze a runner for eight development episodes: Sol and GPT-5.2 on four cases under a $40 incremental cap. No task or grader change would be allowed after exposure. Held-out and Astra remain prohibited.

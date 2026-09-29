# Stage 8 evidence — hard-suite ceiling correction and v0.3 calibration

Date: 2026-09-07

## Ceiling failures preserved

- Packet calibration: GPT-5.6 Sol 100, GPT-5.4 95, GPT-5.2 95. No-go.
- Executable data calibration: GPT-5.6 Sol 100, GPT-5.4 100,
  GPT-5.2 87.5. No-go.
- Playbook pairing: effects were heterogeneous and are not evidence that SFT,
  RLHF, retrieval, or any untested model adaptation is required.
- Hard suite v0.2: apparent difficulty depended on a 20-turn horizon. Sol had
  three usable unsubmitted zeros and GPT-5.4 reached the horizon on its first
  four cells. No-go; preserved as a benchmark-design failure.

## v0.3 structural correction

v0.3 uses five causal resource-selection pairs, a 32-turn/40,000-token horizon,
and an irreversible R1/R2/R3/none commitment before a single evidence reveal.
Control and treated cases share the same public baseline. The treated case only
makes the resolving resource available; the agent must identify and commit it.

The intervention classes are additional data, labels/metadata, expert help, and
process/tooling. Model adaptation is not inferred. Controlled and authentic
results are reported separately.

## Zero-cost gates

- Reference: 100 on every development and held-out case.
- Expert separation: passed in all five families.
- Universal advance/abstain/stop means: 25.75 / 41.05 / 38.05.
- Perfect science with wrong resource: maximum 80.
- Keyword/cite-all reward hack: maximum 47.82.
- Answer leakage: none detected.
- Partial credit: monotonic and nonzero.

All local gates passed before development calibration.

## Paid calibration protocol

- Models: `openai/gpt-5.6-sol`, `openai/gpt-5.4`, `openai/gpt-5.2`.
- Attempts: one per development cell; 30 planned cells total.
- Purpose: difficulty and intervention calibration only, never a ranking.
- Local conservative cost cap: $30.
- Astra calls: zero.
- Sequential no-go: stop after a complete model slice if mean is at least 85,
  ceiling rate exceeds 25%, or every task is zero.

Sol completed its ten-cell slice at 83.2619, with no task at 95 or above and no
zero/unsubmitted task. This passes the mandatory frontier ceiling gate but sits
just above the ideal 65–80 band.

## Infrastructure amendment

The first GPT-5.4 treated-identity attempt hit OpenRouter's new-account limit of
20 requests/minute after 23 valid turns. It was classified and retained as an
infrastructure failure, excluded from scoring, and not treated as an agent zero.

The resume introduced only a 3.25-second minimum interval between provider
requests. No task, evidence, grader, system prompt, model, seed, turn/token/time
budget, frozen config, or held-out artifact changed. Resume remained guarded by
the original config digest and suite/held-out hashes. This is a harness-only
rate-limit accommodation and must be disclosed with the results.

## Paused status — superseded by v0.4

The paid v0.3 process was interrupted during an inter-task cooldown, not during
a provider request. No v0.3 or `uc-hard3` process/container remains. The raw
checkpoint is preserved unchanged at SHA-256
`6b28f70b8b79518360d5fc5611ebe1673b95f06126847d09d0b53d63a720f9be`.

- 16 usable cells of 30 planned; 17 attempt records total.
- One HTTP 429 is retained as infrastructure failure and excluded.
- GPT-5.6 Sol: 10 cells, mean 83.2619, quantitative component mean 98.4,
  ceiling rate 0, zero rate 0.
- GPT-5.4: 6 cells, mean 69.5499, ceiling rate 1/6, zero rate 0.
- GPT-5.2: no v0.3 cells run.
- Astra: zero requests.
- OpenRouter key usage increased from $22.68207697 to $25.25898437: observed
  incremental spend $2.57690740. The token-price planning estimate is
  conservatively higher at $8.864724.
- Key limit at pause: $60; reported remaining allowance: $34.74101563.

The detailed model × family × component rows are preserved in
`artifacts/diagnostics/hard_suite_v03_analysis.json`. The available family means
show why the result is diagnostic but incomplete: Sol's quantitative score is
near-perfect while its resource/recovery judgments vary; GPT-5.4 has only three
complete families and ranges from 53.0 on transport to 87.12 on process.

v0.3 is quantitatively insufficient and will not be resumed. Its resource
selection, scientific diagnosis, and recovery failures remain useful design
evidence. It is not a failed infrastructure run and not a stable ranking.

## Remaining release blockers

- Do not resume or overwrite the v0.3 matrix.
- Calibrate v0.4 only after its new local quantitative gates and immutable
  freeze pass.
- Do not run Astra during development; a later ceiling probe still requires all
  mandatory v0.4 gates.
- Even after a ceiling canary, repeat held-out seeds and task-clustered
  uncertainty are required before any stable ranking.
- Package an authentic cohort partition before making claims about real-world
  failure prevalence.

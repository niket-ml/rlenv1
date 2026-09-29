# UC-Bench v0.6 final pre-exposure engineering and cost gate

Date: 2026-09-08

Status: **historical pre-exposure gate. The suite was subsequently frozen, but
its sentinel stopped on an adapter/harness failure before any model response.**
See `reports/generated/hard_suite_v06_sentinel_no_go.md`.

## 1. Scientific-runner adapter implementation

The scientific runner now constructs one provider adapter per exact panel model.
Each request carries both `order` and `only` for the native provider,
`allow_fallbacks: false`, `require_parameters: true`, and a route price ceiling.
The response ledger independently verifies the returned model and actual provider.
An identity mismatch stops the provider and is never scored as scientific failure.

Provider-specific behavior is intentionally equivalent rather than textually
identical:

| Requested model | Required route | Scientific tool choice | Reasoning handling |
|---|---|---|---|
| `openai/gpt-5.6-sol` | OpenAI | provider-default automatic | request medium; preserve returned state |
| `anthropic/claude-opus-5` | Anthropic | automatic | request medium; retain provider state; completion ceiling stays above the 1,024-token reasoning minimum |
| `google/gemini-3.1-pro-preview` | Google AI Studio | provider-default automatic | request medium; round-trip `reasoning_details` unchanged across tool turns |
| `moonshotai/kimi-k3` | Moonshot AI | automatic | never force a particular tool while thinking |
| `openai/gpt-5.2` | OpenAI | provider-default automatic | request medium; preserve returned state |

The task prompt is ordinary anti-TNF predictor diligence language. It contains no
SDK-conformance or reverse-engineering framing. Private chain of thought is neither
requested nor graded. Only provider-visible state fields and the visible tool
transcript are preserved.

Every request ledger records requested and returned model, requested and actual
provider, route policy, requested and reported reasoning setting, finish reason,
refusal, retries, token usage, reasoning-token fields, cache read/write fields,
latency, cost, and any identity violation. The ledger is atomically checkpointed
after every response or error.

## 2. Compatibility findings carried forward

All five non-scored compatibility canaries passed on the exact routes above.
Response-reported compatibility spend was `$0.04574225`. The scientific runner
incorporates the two substantive adapter findings:

- Claude receives automatic tool choice, an ordinary scientific-workflow prompt,
  and enough output room for Anthropic reasoning. The original compatibility-only
  conformance wording was archived as a provider-policy failure.
- Kimi receives automatic tool choice. Its archived forced-tool attempt returned a
  provider adapter error and is not model scientific evidence.
- Gemini provider reasoning fields are copied without summarization or rewriting
  into subsequent tool turns.
- Both OpenAI models use their pinned native route.

Scientific response refusal is a zero-reliability model outcome. Only an explicit
provider-level policy block, verified transport failure, route/adapter failure, or
unresolved harness failure is excluded pending diagnosis.

## 3. Fair execution envelope

All five models receive the same scientific opportunity because every selected
route passed the required interface. Provider-specific syntax differs only where
required by the provider.

| Budget property | Predeclared value | Rationale |
|---|---:|---|
| Wall-clock timeout | 4,200 seconds per episode | permits long-horizon analysis without using duration as difficulty |
| Maximum assistant turns | 65 | above v0.5 P90 of 51.6 turns and maximum of 55 |
| Completion tokens per request | 5,000 | enough for reasoning plus a tool action; valid for every route |
| Total completion tokens | 90,000 | 1.20× the v0.5 envelope for ten separate artifacts |
| Minimum request interval | 3.25 seconds | reduces provider throttling without constraining reasoning |
| Requested reasoning | medium | logged as requested; reported resolution is also logged and not assumed |
| Context policy | complete visible transcript | no silent truncation or provider-specific summaries |
| Compaction | disabled | context exhaustion fails closed; any future capsule policy requires a new version |
| Parallel tool calls | disabled | preserves deterministic state-transition ordering |
| SDK/request retries | zero | prevents invisible retry asymmetry |
| Episode retry | one | only after a verified infrastructure failure, same cell and frozen inputs |

The smallest advertised context is GPT-5.2 at 400,000 tokens; the other routes
advertise approximately one million. Cumulative billed input across many turns is
not the same as the largest single-turn context. If an individual transcript
exceeds a route's context, the episode is classified as context-budget exhaustion;
it is not silently compacted.

Submission handling is predeclared:

- valid submissions receive the deterministic coverage-adjusted scientific score;
- usable unsubmitted attempts receive zero reliability, while parseable artifact
  scores remain available as diagnostics;
- verified infrastructure failures are excluded and may receive one same-cell
  retry;
- provider adapter, route, and explicit provider-policy failures are separate from
  scientific performance and block continuation until resolved;
- unknown harness failures are excluded only pending diagnosis, never silently
  relabelled as infrastructure.

## 4. Local and mock verification

The repository has 191 tests. The complete suite passes, as do Ruff, project
doctor, audit consistency, `git diff --check`, and the existing v0.5 freeze audit
(17 frozen hashes match; Astra exposure remains zero).

The v0.6-specific tests establish that:

- each of the five adapters can write and deterministically grade all ten artifacts;
- tool output and provider-visible reasoning state survive the next turn unchanged;
- pre-reveal artifact presence and content are committed and later mutation fails;
- response/provider identity cannot silently change or fall back;
- an execution/resume preflight rechecks every live canonical alias and native
  tool route before the first scientific request;
- request cost and cache evidence checkpoint after every response;
- cost arithmetic, v0.5 workload quantiles, cap consistency, and upward-cent
  funding requirements are independently tested;
- transport, provider, adapter, refusal, and scientific failure classes remain
  distinct;
- unsubmitted usable work retains its partial-artifact diagnostics but receives
  zero reliability;
- context-window and wall-clock exhaustion score as execution failures rather
  than becoming adapter/infrastructure exclusions;
- resume rejects any frozen hash, panel, execution contract, or runtime-version
  change;
- the underlying episode function cannot bypass authorization or the freeze;
- both held-out partitions and any Astra/GPT-6 model are rejected before an
  environment is built;
- the sentinel contains all five models on the same two states and cannot create a
  ranking claim;
- the ceiling metric uses accepted-submission scientific quality and cannot be
  lowered by non-submission, timeout, schema, or provider failure;
- exact 60–70, 70–75, 75–80, and above-80 ceiling bands are deterministic;
- capability, artifact-family, scenario, and partial-credit diagnostics are
  calculated from the same frozen artifact scores;
- every material scientific deduction carries artifact trace evidence, a
  professional consequence, and an actionable intervention class.

## 5. Exact proposed panel

Cross-family frontier comparison:

- `openai/gpt-5.6-sol` → canonical
  `openai/gpt-5.6-sol-20260709`, OpenAI;
- `anthropic/claude-opus-5` → canonical
  `anthropic/claude-opus-5-20260723`, Anthropic;
- `google/gemini-3.1-pro-preview` → canonical
  `google/gemini-3.1-pro-preview-20260219`, Google AI Studio;
- `moonshotai/kimi-k3` → canonical
  `moonshotai/kimi-k3-20260715`, Moonshot AI.

Same-family temporal comparison:

- `openai/gpt-5.6-sol`;
- `openai/gpt-5.2` → canonical `openai/gpt-5.2-20251211`, OpenAI.

All were authenticated-visible and returned the requested model and native provider
in compatibility. Astra is absent. Claude Sonnet is not a runtime fallback; using it
would require a separately predeclared panel version.

## 6. Post-adapter cost plan

The planning basis is the 18 observed v0.5 episodes:

- cumulative input: 882,243.5 median, 1,281,744.1 P90;
- output: 9,524 median, 20,948.3 P90;
- turns: 40 median, 51.6 P90;
- wall time: 165.1 seconds median, 362.5 seconds P90.

The v0.6 estimate applies a disclosed 1.20× workload factor for the ten-artifact
episode. It uses the exact compatibility-observed native-route prices. A 60% cache
case is reported only as sensitivity; compatibility observed zero reusable cache
hits, so the no-cache case governs funding and caps.

| Model | Input/output $ per million | Median episode | P90 episode |
|---|---:|---:|---:|
| GPT-5.6 Sol | 2 / 10 | $2.231672 | $3.327565 |
| Claude Opus 5 | 5 / 25 | $5.579181 | $8.318914 |
| Gemini 3.1 Pro Preview | 2 / 12 | $2.254530 | $3.377841 |
| Kimi K3 | 3 / 15 | $3.347509 | $4.991348 |
| GPT-5.2 | 1.75 / 14 | $2.012715 | $3.043594 |

| Option | Episodes | Median | P90 | 60% cache median | Hard cap | Sequential wall time median/P90 |
|---|---:|---:|---:|---:|---:|---:|
| A. Full matrix directly | 30 | $92.55 | $138.36 | $45.35 | $167 | 3.21 / 6.85 h |
| B1. Balanced sentinel | 10 | $30.85 | $46.12 | $15.12 | $56 | 1.07 / 2.28 h |
| B2. Remaining cells after pass | 20 | total remains bounded by full cap | — | — | total $167 from original baseline | roughly another 2.1 / 4.6 h |

Compatibility spend already incurred is separate: `$0.04574225`.

## 7. Staged execution recommendation

Use option B: freeze the complete 30-cell suite and panel, then run the balanced
sentinel before the remaining cells. The sentinel exposes every model equally to
two scientifically different development states:

- `dev6_clean_progression` tests justified progression without unnecessary
  escalation;
- `dev6_preprocessing_leakage` tests leakage detection, containment, resource
  selection, and revision after reveal.

The sentinel is not a mini-leaderboard. Continue only if all ten cells produce
valid accepted submissions, frozen hashes remain unchanged, no route, identity,
adapter, or provider-policy failure is unresolved, and the strongest accepted-
submission scientific mean is 60–70 (desired) or above 70 through 75
(acceptable). Stop below 60 as over-hard, above 75 through 80 for insufficient
headroom, or above 80 as a ceiling no-go.

Continuation additionally requires no more than 25% of the strongest model's
cells at 95 or above, losses across at least three scientific capabilities, no
artifact family contributing more than 30% of its gap, meaningful partial
credit, and complete artifact-level trace/remedy evidence for every material
deduction. Completion reliability is reported separately and cannot be used to
make the scientific score look difficult. Task, grader, prompt, threshold,
state, and panel changes are prohibited after first exposure; a failed sentinel
is a versioned no-go, not a tuning set.

The observed two-state scenario shares are reported, but the 30% scenario-
concentration rule is not a sentinel continuation gate: with only two positive
loss shares, at least one must be 50% or greater. It becomes mandatory only on
the full six-state development matrix. This limitation is explicit rather than
silently weakening the threshold.

This option gives the best information per dollar because it can detect provider
integration collapse, completion contamination, an over-hard suite, insufficient
headroom, a scientific ceiling, concentrated artifact-family losses, or missing
partial credit after one-third of the matrix without dropping any provider or
weakening the eventual full comparison.

## 8. Funding gate

Read-only OpenRouter status at the cost refresh:

- account credit remaining: `$91.37776708`;
- API-key limit remaining: `$91.37776708`;
- current key limit: `$130.00`;
- current key usage: `$38.62223292`.

The recommended sentinel needs **no top-up and no key-limit increase**. The full
`$56` incremental cap is available with `$35.37776708` of remaining headroom.

To authorize the complete matrix cap from the present baseline, add at least
**$75.63** and raise the API-key limit by at least **$75.63**, from `$130.00` to
`$205.63`. No account setting was changed by this gate.

## 9. Proposed freeze manifest

The preview manifest exists, but the actual freeze manifest does not. The proposed
manifest contains:

- exact five-model IDs, canonical expectations, provider routes, fallback policy,
  and price ceilings;
- six development state IDs and their predeclared seeds;
- all held-out definitions, with exposure counters fixed at zero;
- ten artifact definitions and seven JSON schemas;
- task prompt, environment, deterministic grader, provider adapter, scientific
  runner, checkpoint/resume runner, freeze code, Docker contract, and project
  dependency specification;
- local control, compatibility, and cost-gate artifacts;
- episode budgets, submission/failure policy, sentinel continuation rules, full
  acceptance gates, and exact spend caps;
- SHA-256 for every frozen file plus a hash-set digest;
- Python and key runtime-package versions;
- zero scientific calls before freeze, zero held-out exposure, zero Astra exposure,
  and no ranking authorization.

The preview explicitly says `frozen_before_scientific_model_calls: false`. An
actual manifest can be written only after both authorization flags are deliberately
changed and the explicit acknowledgement command is supplied. It cannot be
overwritten.

## 10. Remaining construct-validity limitations

- No external specialist has independently validated expert equivalence. The
  current controls are internally authored and support development calibration
  only.
- No v0.6 scientific trajectory exists yet, so the 1.20× workload and compatibility
  latency scaling are planning assumptions.
- The six controlled states establish mechanism isolation, not authentic prevalence
  or real-world effect size. Authentic GEO evidence remains separate.
- One seed per cell cannot establish a stable ranking or uncertainty interval.
- The sentinel can evaluate its scientific ceiling band, artifact-family
  concentration, capability-loss spread, and partial credit, but only two states
  cannot establish the 30% scenario-concentration or three-distinct-scenario
  failure-mode gates; those require all six development states.
- Compatibility shows interface viability, not equal latent reasoning effort across
  vendors. Requested and reported settings will be disclosed rather than treated as
  identical internals.
- The grader has internal reference, alternative, paraphrase, mediocre, universal
  policy, leakage, mutation, and partial-credit controls, but model exposure may
  still reveal an unanticipated construct issue. Post-exposure repair requires a
  new benchmark version.

## Next approval boundary

Recommended sequence after funding and explicit approval:

1. set `freeze_authorized` and both scientific authorization fields to true as one
   reviewed change;
2. write the one-time freeze manifest;
3. run only the 10-cell sentinel with an exact `$56` incremental cap.

The scientific command that would require approval is:

```bash
PYTHONPATH=src ./.venv/bin/python scripts/run_v06_pilot.py \
  --strategy sentinel \
  --execute \
  --maximum-incremental-cost-usd 56
```

Before execution, the authorization flags and one-time manifest must record the
explicit approval. The full-matrix command is intentionally not the recommended
first spend.

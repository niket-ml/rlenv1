# UC-Bench v0.6 cross-provider panel protocol

Status: **all five compatibility canaries passed; panel remains unfrozen and
scientific execution is not authorized**.

Authenticated read-only OpenRouter metadata was captured in
`artifacts/diagnostics/hard_suite_v06_provider_plan.json`. This establishes
account visibility and advertised interfaces, not end-to-end compatibility or
scientific performance. Version identities below are OpenRouter catalog
identities observed on 2026-09-08; they are not independent release assertions
from each model developer.

## Proposed comparisons

Cross-family frontier:

- `openai/gpt-5.6-sol` → `openai/gpt-5.6-sol-20260709`, native OpenAI;
- `anthropic/claude-opus-5` → `anthropic/claude-opus-5-20260723`, native Anthropic;
- `google/gemini-3.1-pro-preview` → `google/gemini-3.1-pro-preview-20260219`, Google AI Studio;
- `moonshotai/kimi-k3` → `moonshotai/kimi-k3-20260715`, native Moonshot AI.

Same-family temporal ladder:

- `openai/gpt-5.6-sol`;
- `openai/gpt-5.2` → `openai/gpt-5.2-20251211`, native OpenAI.

Every request will set an exact provider order and `allow_fallbacks: false`.
Gemini's dated canonical slug is checked again immediately before execution; a
change is a hard stop. Claude Sonnet 5 is only a declared cost fallback and
would require a new predeclaration, not a silent substitution. The untouched
ceiling model is absent from development configuration and execution.

## Compatibility stage

One non-scored canary is required for every exact model, not merely every
vendor. Each canary uses no more than three small requests and checks:

1. a provider-valid function call carrying an opaque project identifier;
2. exact ingestion of the tool result on the next turn;
3. strict structured output containing the preserved visible state;
4. ingestion of an explicit compacted-state capsule;
5. provider-specific maximum-token parameter acceptance and observed bound;
6. tool/stop finish reasons;
7. requested versus actual provider and response model identity;
8. usage and cache-accounting fields;
9. harmless-request refusal detection; and
10. local injected refusal and infrastructure-error classification.

“Reasoning state” means visible working state and the tool transcript. The
canary neither requests nor assumes access to private chain-of-thought. Adapter,
refusal, and infrastructure outcomes receive no scientific score.

For each request the harness records the requested and returned model,
requested and actual provider, requested reasoning effort, resolved effort when
reported, context/token interface, finish reason, usage, cache details, latency,
cost, and retries. A provider adapter failure cannot enter a scientific matrix.

The compatibility cap was exactly $3. The final result passed all checks for
all five models. Conservative response-reported spend was $0.04574225,
including retained failed adapter attempts; the live key counter had posted
$0.03468225 when checked. No scientific or Astra request was made.

Two provider-specific adapter findings were resolved before scientific panel
freeze:

- Kimi K3 rejects a specified/forced tool choice while thinking is enabled;
  automatic tool choice completed the same required tool loop.
- Claude Opus 5's native route blocked explicit “SDK conformance test” wording
  as suspected reverse engineering. The scientifically irrelevant wording was
  replaced by an ordinary project-status workflow with identical interface
  checks. Claude then completed the function call, tool-result ingestion,
  structured responses, and compacted-state turn. Its canary ceiling is 2,048
  tokens because Anthropic reasoning configurations require room above their
  minimum reasoning budget.

Every failed attempt is retained under
`artifacts/diagnostics/hard_suite_v06_compatibility_attempts/`. These were
provider-adapter or refusal outcomes and never received scientific scores.

## Cost plan

The final read-only post-adapter refresh reconciled the full compatibility spend:

- account credits: $80.00;
- account usage: $38.62223292;
- remaining: $41.37776708;
- key limit: $80.00;
- key-limit remaining: $41.37776708.

Compatibility cost was $0.04574225. It is already incurred and is separate from
the scientific projection.

Using the completed v0.5 trajectories, a 1.20× ten-artifact workload factor,
compatibility-observed prices, and no cache credit, the five-model × six-state
scientific pilot is $92.55 at median workload and $138.36 at P90. Its P90 plus
20% contingency hard cap is $167. A balanced ten-episode sentinel is $30.85
median and $46.12 P90, with a $56 cap.

The sentinel therefore requires at least $14.63 more account funding and a
$14.63 key-limit increase. Funding the full cap from the present baseline
requires $125.63 for each. These values round upward to the cent. No account
setting was changed. Full calculations and assumptions are in
`reports/generated/hard_suite_v06_cost_plan.md` and
`docs/V06_PRE_EXPOSURE_GATE.md`.

## Freeze and execution order

1. Preserve v0.5 and verify its frozen hashes.
2. Pass all v0.6 local construct controls.
3. Present this availability and proxy-cost report.
4. Obtain explicit approval for the $3 non-scored compatibility stage. **Done.**
5. Run canaries and classify provider behavior separately. **Done: 5/5 pass.**
6. Remove no provider merely to manufacture an ordering; repair adapters or
   predeclare any panel change.
7. Re-estimate the 30-episode panel from measured usage and request a new cap.
   **Done: $167 full cap; $56 sentinel cap.**
8. Freeze tasks, graders, states, model IDs, provider routes, prompts, and gates.
   **Not authorized; only a preview exists.**
9. Run only compatible models with checkpoint/resume and no held-out ceiling probe.
   **Not authorized.**

The resulting report must show model × artifact, capability, controlled state,
completion reliability, and cost. The same-family and cross-family comparisons
are complementary. Aggregate order is secondary and no ranking is stable until
repeated seeds and uncertainty analysis exist.

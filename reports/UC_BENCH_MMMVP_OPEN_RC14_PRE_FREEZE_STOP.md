# UC-Bench open MMMVP RC1.4 pre-freeze stop report

Status: **STOPPED BEFORE FREEZE AND SCIENTIFIC EXPOSURE**

RC1.4 was intended to be a contract-only successor to RC1.3. The local contract,
regression, replay, isolation, and immutability gates passed. The first paid,
case-free compatibility round did not pass, so RC1.4 was not frozen and the
Case-2 sentinel was not started.

## Preserved scientific state

- RC1.3 remains immutable.
- RC1.3 infrastructure digest:
  `c27c5b6af9f044baebb5364d0f069fa80e7022e5fb6ece1bffc6a4fde47dff29`.
- Scientific freeze digest:
  `466441682b04175432329b41adcfd735cdea66f860d66f046dfae195c91e701c`.
- Only `submission_contract.json` differed in the agent-visible RC1.4 workspace.
- No case, hidden outcome, scientific truth, tool, action rule, verifier rule,
  accepted alternative, model route, or scientific budget changed.
- No scientific, held-out, or Astra request was made.

## Contract and zero-cost validation

The public contract now enumerates all machine-enforced fields and conditions:

- 20 enum families;
- 133 distinct field paths;
- 15 relationship or conditional constraints;
- the five required action-sequence steps;
- the two allowed `unit_of_analysis` values;
- calculation cohort, artifact lineage, uncertainty, claim-reference, evidence,
  commitment, purchase, belief-update, and final-submission requirements.

Free text cannot determine a scientific score. The disclosure audit found no
case identity or forbidden scientific hint in the contract.

Validation passed:

- 11 focused RC1.4 tests;
- 646 full repository tests;
- Ruff across `src`, `tests`, and `scripts`;
- project doctor and audit consistency;
- standard and scientific Docker/isolation checks;
- credential scan;
- RC1.3 before/after immutability check.

## Archived submission replay (diagnostic only)

The archived submissions were not modified, rescored, or reinterpreted.
Replaying their schema errors shows which old rejections the revised visible
contract would pre-empt:

| Archived model | Attempts | Previously undisclosed issue occurrences now disclosed | Newly disclosed issue families |
|---|---:|---:|---|
| Mistral Large 2512 | 36 | 80 | calculation unit of analysis; cohort object; cohort split values; cohort included-row count |
| Claude Sonnet 4 | 3 | 30 | calculation unit of analysis; cohort object; cohort split values; cohort included-row count |
| Gemini 3.1 Pro Preview | 24 | 26 | calculation unit of analysis; cohort object; cohort split values; cohort included-row count |

These counts do not imply the archived attempts would otherwise have passed;
other disclosed or scientific errors remain their original outcomes.

## Compatibility round 01

The case-free round made ten requests and cost **$0.20406263**. The recorded
gate result is **1/10 compatible**. It is preserved and must not be rewritten.

Offline inspection shows that this number is contaminated by defects in the
compatibility canary and must not be interpreted as nine model failures:

| Model | Saved observation | Forensic classification |
|---|---|---|
| `openai/gpt-5.1` | OpenAI route correct; 700/700 completion tokens were reasoning; no tool call; `length` | Inconclusive: canary token ceiling |
| `anthropic/claude-opus-4.1` | Bedrock route correct; one tool call; submitted contract summary differed | Contract-ingestion mismatch; raw arguments were not persisted, so the exact difference is unavailable |
| `google/gemini-3.1-pro-preview` | Google route correct; 671/695 completion tokens were reasoning; no tool call; `length` | Inconclusive: canary token ceiling |
| `anthropic/claude-sonnet-4` | Bedrock route correct; exact requested tool payload present | Valid semantic compatibility; falsely rejected by a second, stricter model-slug equality check |
| `moonshotai/kimi-k3` | Moonshot route correct; exact requested tool payload present | Valid semantic compatibility; falsely rejected by a second, stricter model-slug equality check |
| `z-ai/glm-5.2` | No provider response; 404 at the configured maximum-price filter | Provider/route infrastructure failure |
| `openai/gpt-5` | OpenAI route correct; 640/640 completion tokens were reasoning; no tool call; `length` | Inconclusive: canary token ceiling |
| `qwen/qwen3.5-397b-a17b` | DeepInfra route correct; completion exhausted by reasoning; no tool call; `length` | Inconclusive: canary token ceiling |
| `deepseek/deepseek-v3.2` | StreamLake route correct; one tool call; submitted contract summary differed | Contract-ingestion mismatch; raw arguments were not persisted, so the exact difference is unavailable |
| `mistralai/mistral-large-2512` | Mistral route correct; exact requested tool payload | Passed |

The canary had three defects:

1. A universal 700-token ceiling was not an equivalent opportunity across
   reasoning interfaces and caused four `length` terminations.
2. It added an exact canonical-slug assertion after the shared request ledger
   had already accepted and recorded the returned route identity. This falsely
   rejected two correct submissions.
3. It persisted raw responses only after semantic validation, so the exact
   tool arguments for the two semantic mismatches were lost even though the
   request ledger proves that one tool call occurred.

The GLM failure is separate: the unchanged route's maximum-price filter found
no eligible endpoint. This is infrastructure, not scientific performance.

## Funding and mandatory stop

- Compatibility headroom before round 01: **$56.525407418**.
- Compatibility spend: **$0.20406263**.
- Recorded headroom after round 01: **$56.326518068**.
- Scientific spend: **$0**.
- RC1.4 freeze: **not created**.
- Sentinel randomized order: **not created**.
- Sentinel P90 and authorization check: **not finalized**, because they are
  conditional on ten clean compatibility passes.

The Case-2 question—whether the ten models differ in scientific workflow
capability after contract and infrastructure artifacts are removed—therefore
remains unanswered.

## Narrow next action requiring authorization

Preserve compatibility round 01, repair only the case-free canary, and write a
separate round-02 path:

1. use the shared runner's established identity validation rather than a second
   incompatible slug equality rule;
2. provide provider-equivalent room to complete the tiny tool call;
3. persist every redacted raw response before semantic assertions;
4. diagnose the unchanged GLM price-filter route without silently falling back;
5. rerun only the nine unresolved routes under the unspent portion of the
   original $2 compatibility allowance.

No scientific contract, case, verifier, route, or task would change. Freeze,
cost planning, randomization, and the sentinel would remain blocked until that
separate evidence passes.

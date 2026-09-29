# UC-Bench Case 2 pilot RC1: post-freeze preflight stop

## Outcome

The Case 2 release passed every local zero-cost gate and was frozen successfully, but no
scientific episode was launched. The live route checker rejected all three cells because its
endpoint-identity predicate no longer matches the current OpenRouter endpoint metadata schema.
This is a shared infrastructure defect, not model or scientific evidence.

## Immutable release

- Release: `uc-bench-case2-pilot-v1-rc1`
- Aggregate digest: `8257d5d804e46bbc1b86cddc24a9ffcc0d744b0a73ad95aa92d0ccbc8436cd00`
- Status: `frozen_pre_science`
- Scientific calls: 0
- Scientific spend: $0.00

The zero-cost gate passed all Case 2 controls, public/hidden semantic parity, the exact
fake-provider production rehearsal, Docker isolation, credential scanning, lint, doctor,
audit, clean staging and the complete repository regression policy. Independent read-only RL
review was `APPROVE` with no blocker or high-severity finding.

## Funding snapshot

Immediately before route preflight:

- account remaining: $34.282023553
- API-key limit remaining: $34.282023553
- API-key limit: $230.00
- API-key usage: $195.717976447
- $12 sentinel cap covered: yes

## Live route evidence

The authenticated model catalog exposed all three requested aliases and returned the exact
frozen canonical dated slug for each. The endpoint API also returned the intended provider and
dated slug, but it encoded them as follows:

| Requested model | Pinned provider | Frozen dated slug | Matching live endpoints | Live price range, prompt/completion per million |
|---|---|---|---:|---:|
| `google/gemini-3.1-pro-preview` | Google AI Studio | `google/gemini-3.1-pro-preview-20260219` | 3 | $1/$6 to $3.60/$21.60 |
| `openai/gpt-5.1` | OpenAI | `openai/gpt-5.1-20251113` | 3 | $0.625/$5 to $2.50/$20 |
| `anthropic/claude-sonnet-4` | Amazon Bedrock | `anthropic/claude-4-sonnet-20250522` | 2 | $3/$15 |

Current endpoint records put the human label in `model_name`, for example
`OpenAI: GPT-5.1`, and put the exact route slug in `name`, for example
`OpenAI | openai/gpt-5.1-20251113`. The frozen checker requires `model_name` to equal the
requested alias or dated slug. It therefore reports zero matches even though the exact pinned
routes are present.

## Smallest evidenced repair

Create an infrastructure-only successor that changes only endpoint-catalog identity
normalization. Extract a dedicated canonical endpoint slug from the exact `name` field after
the provider separator, then require all of:

1. exact pinned `provider_name`;
2. exact canonical endpoint slug;
3. authenticated catalog alias-to-canonical match;
4. frozen price and limit constraints;
5. fallback disabled.

Add fixtures for the current live schema, the historical schema, wrong provider, nearby model,
missing slug and contradictory fields. Preserve this RC1 freeze and all science unchanged.
Because request, tool and adapter digests need not change, compatibility can remain inherited if
those digests are still exact. Do not launch science until the successor passes the same local
gates and post-freeze route check.

## Interpretation

There is no Case 2 model result and no basis for a ranking, ceiling, floor or capability claim.
The sentinel stopped correctly at a shared pre-exposure infrastructure gate.

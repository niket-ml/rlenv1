# UC-Bench open MMMVP RC1.4 harness-convergence report

## Outcome

The compatibility/model-behaviour/infrastructure separation was repaired and validated. Nine of ten routes are technically compatible. RC1.4 passed its zero-cost gates and was frozen without changing scientific content.

The Case-2 scientific sentinel was **not run**. After the immutable freeze, the frozen cost planner crashed while reading the real adapter-price schema. This is shared harness corruption under the predeclared global-stop policy. RC1.4 has therefore been preserved unchanged; no order was generated and no scientific request was made.

Consequently, this pass does **not** answer whether Case 2 differentiates scientific workflow capability. It establishes that the compatibility layer is no longer manufacturing most of the earlier failures, while exposing one remaining shared pre-execution defect.

## What changed in the unfrozen RC1.4 development workspace

- Compatibility now tests only the technical round trip: pinned identity, parseable response, recorded tool call, returned tool result, continuation, final response, usage persistence, and exact replay.
- Compatibility and science use the same RC1.4 request construction, client path, identity validator, response parser, tool dispatcher, durable ledger, and replay machinery.
- Redacted raw provider responses are persisted before parsing or adjudication. A later assertion failure cannot erase the evidence.
- Provider-aware scientific-runner token and reasoning configurations replace the universal 700-token ceiling.
- Compatibility semantics were removed: an incorrect canary argument or contract summary is model behaviour when the interface itself worked.
- Failures are contained at two levels:
  - global stop: shared corruption, lifecycle inconsistency, hash drift, credential exposure, protected-data mutation, or budget breach;
  - cell exclusion: isolated provider outage, price-filter failure, or route-specific HTTP failure, with at most one predeclared safe retry.
- Ten captured round-01 response shapes now exercise the production path, including alternate valid slugs, reasoning-only length termination, malformed arguments, semantic disagreement, provider errors, restart, and replay.

No scientific case, hidden outcome, scientific prompt, tool surface, verifier rule, model route, or archived RC1.3/earlier artifact was changed.

## Round-01 forensic adjudication

The original RC1.4 round-01 result remains intact at `artifacts/mmmvp_open_rc14/compatibility_results.json` (SHA-256 `1c52a12e7c0ed48d58b427abf1698606983a611c0c99de19a5eaa0253756e88f`). It was not rewritten or rescored.

The separate forensic adjudication used preserved response evidence and earlier complete production-path round trips. Contract-summary disagreement was ignored, and reasoning-only token exhaustion was treated as inconclusive rather than scientific or model failure.

| Route | Technical disposition | New rerun? | Basis |
|---|---:|---:|---|
| `openai/gpt-5.1` | pass | no | Preserved complete round trip; current length stop did not negate it |
| `anthropic/claude-opus-4.1` | pass | no | Complete round trip; contract-summary disagreement is behavioural |
| `google/gemini-3.1-pro-preview` | pass | no | Preserved complete round trip; current length stop was inconclusive |
| `anthropic/claude-sonnet-4` | pass | no | Preserved exact payload established the round trip |
| `moonshotai/kimi-k3` | pass | no | Preserved exact payload established the round trip |
| `openai/gpt-5` | pass | no | Preserved complete round trip |
| `deepseek/deepseek-v3.2` | pass | no | Complete round trip; summary disagreement is behavioural |
| `mistralai/mistral-large-2512` | pass | no | Round-01 technical pass |
| `qwen/qwen3.5-397b-a17b` | pass | yes | Fresh two-request production-path canary: one tool call, one tool result, continuation recorded |
| `z-ai/glm-5.2` | provider-specific exclusion | yes | Pinned StreamLake route returned HTTP 404 at the maximum-price filter before a model response |

The rerun set was two routes, smaller than the permitted unresolved set because preserved full-round-trip evidence already proved the other eight interfaces.

## Compatibility spend

- Preserved round 01: `$0.20406263`
- Convergence reruns: `$0.00080205`
- Total RC1.4 compatibility spend: `$0.20486468`
- Remaining compatibility allowance: `$1.79513532`
- Scientific requests: `0`
- Held-out/Astra requests: `0`

## Tests and freeze

The final pre-exposure gate passed:

- RC1.4 focused production-path tests: passed;
- full repository test suite: passed;
- Ruff: passed;
- project doctor and audit consistency: passed;
- Docker isolation and protected-workspace checks: passed;
- credential scan, scientific hash checks, route identity checks, and archived replay: passed.

An earlier gate artifact records a sandbox-denied Docker socket. The same gate was rerun with Docker access and passed; the authoritative result is `pre_exposure_gate_04.json` (SHA-256 `9637aebe16644d58424398cbbf1d1489edcdff58e4acd7d15e490da8f6f11da0`).

RC1.4 freeze:

- freeze artifact SHA-256: `f03ec0ac838c830af1344ff4b2eab37ec5245bcca001a7931f01a188a0e81bbf`;
- scientific digest: `466441682b04175432329b41adcfd735cdea66f860d66f046dfae195c91e701c`;
- infrastructure digest: `613811a14ff54c7a24fbeffe72e6b7ca374b4a0ce5e8cb4a36e2a65adaba8a8c`;
- agent-visible contract digest: `9697f1a1609bf7f6f54b1086546b17a7adb98d193ad48d552fbae7e5e623535a`.

## Global stop after freeze

The authorized post-freeze cost-planning command failed before creating a cost plan or issuing an API request:

```text
KeyError: 'maximum_prompt_price_usd_per_million'
```

The immutable RC1.4 planner expected flat price keys, while the preserved adapter summaries store both prices inside `maximum_route_price_usd_per_million`. Because cost planning is a shared pre-execution control, bypassing it or patching frozen RC1.4 would violate the requested lifecycle. No sentinel order was created and no scientific execution began.

## Read-only funding diagnostic — not execution authorization

For diagnosis only, applying the intended calculation to the existing nested price fields gives:

- ten-cell sentinel median: `$34.769718323`;
- ten-cell sentinel no-cache P90: `$51.215524882`;
- total including compatibility median: `$34.974583003`;
- total including compatibility P90: `$51.420389562`;
- current effective key-limit headroom after compatibility: `$56.321344791`.

The account therefore appears to cover the `$52` scientific cap. This calculation does not cure the frozen planner failure and does not authorize a manual bypass.

## Failure taxonomy for this pass

| Class | Observed? | Evidence |
|---|---:|---|
| Scientific failure | not evaluated | No Case-2 scientific calls were made |
| Model completion failure | no adjudicated scientific instance | Reasoning-only compatibility length stops were correctly treated as inconclusive |
| Submission/contract failure | no scientific instance | Contract-summary disagreement was removed from compatibility judgement |
| Recoverable tool-use failure | fixtures validated | Malformed arguments remain reconstructable model behaviour, not incompatibility |
| Provider-specific failure | yes | GLM/StreamLake price-filter HTTP 404; isolated to that cell |
| Shared infrastructure failure | yes | Frozen post-freeze cost planner used the wrong price-field shape; global stop enforced |

## Decision

**No-go for the RC1.4 Case-2 sentinel in this pass.** This is an infrastructure no-go, not evidence that Case 2 or any model failed scientifically. RC1.4 remains immutable, and the key scientific question must remain unanswered until the lifecycle contradiction is explicitly resolved outside this frozen version.

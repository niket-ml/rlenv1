# Stage 7 real-model canary audit

Date: 2026-09-06

## Scope

This was an infrastructure canary, not a leaderboard run. The objective was to
verify that a real OpenRouter model could use the eight-tool UC-Bench surface
while its coding workspace remained isolated from credentials, sealed data,
and the private grader.

## Isolation result

The local `uc-bench-agent:0.1` image passed the following preflight:

- network mode `none`;
- read-only container root filesystem;
- unprivileged container with all Linux capabilities dropped;
- `/workspace` as the only bind mount;
- no API-key or token environment variables in the container;
- working pinned numpy, pandas, scipy, and scikit-learn installation; and
- successful read of the 47-row agent-visible development manifest.

The OpenRouter key remained in the host `.env` file and was provided only to
the host-side Verifiers client. It was never mounted or exported to the agent
container.

## Real attempts

| Endpoint | Admission | Model turns | Tool calls | Result |
|---|---:|---:|---:|---|
| `google/gemma-4-31b-it:free` | rejected | 0 | 0 | upstream shared-pool HTTP 429; infrastructure failure |
| `google/gemma-4-26b-a4b-it:free` | rejected | 0 | 0 | upstream shared-pool HTTP 429; infrastructure failure |
| `minimax/minimax-m3:free` | admitted | 17 | 30 | exhausted 16,000-token completion budget before commit; agent task failure |

The admitted MiniMax trajectory made 1 workspace inspection, 14 file reads,
10 isolated shell calls, and 5 file writes. It reconstructed key cohort facts
and identified endpoint, drug, and platform transfer, but repeatedly rewrote a
large analysis script. It never called `commit_analysis`,
`reveal_validation`, or `submit`; therefore it received no scientific score.

## Interpretation

The admitted trajectory proves the real model-to-Verifiers-to-Docker workspace
loop. The two rejected trajectories demonstrate that provider-capacity errors
are kept separate from task failures. The admitted failure is inspectable and
task-relevant, but it is not graceful failure because the model did not reach a
valid terminal evidence decision.

Stage 7 remains `in_progress`. No model-ranking claim is allowed from these
attempts.

## Cost and next gate

All three endpoints were catalog-priced at zero and the account had no paid
credits, so these attempts incurred no model charge. The next gate is:

1. verify the purchased $30 balance and $30 provider key limit;
2. run one `openai/gpt-5.6-luna` paid canary;
3. audit its complete trace and actual before/after key-usage delta; and
4. only after a valid episode, run the pinned three-model, three-attempt smoke.

The nine-run smoke has a $5.02 point estimate from the admitted canary's token
load and a $9.051 local planning guard. The provider-side $30 key limit is an
independent account-wide hard ceiling and does not expand the smoke scope.

## Closure update

Stage 7 subsequently passed. The clean smoke artifact is
`artifacts/runtime/smoke_pilot_v2_runs.json`: GPT-5.6 Sol completed three of
three valid episodes, Gemini completed two valid episodes plus one submitted
contract failure, and Claude produced three agent task failures. Provider and
task failures remained separate. Later packet and executable-data calibrations
produced 56 additional planned cells with only provider-rate-limit retries
excluded.

AF-007 is closed. These runs establish real-agent integration and inspectable
failure behavior; they do not by themselves establish a leaderboard ranking.

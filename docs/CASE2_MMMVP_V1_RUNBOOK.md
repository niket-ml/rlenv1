# UC-Bench Case 2 MMMVP v1 runbook

## Professional task

The agent performs technical diligence on a locked biomedical predictor. It must
choose a defensible biological unit, commit its validation plan before outcomes are
revealed, calculate and save decision-relevant results, inspect context robustness,
choose at most one follow-up resource, revise its position when warranted, and bound
the final development claim.

## Starting state

The agent receives only the agent-visible bundle: public cohort and provenance
evidence, locked predictions, intended use, public contracts, allowed methods and
tolerances, resource catalogue, validator and minimal interface. Hidden outcomes,
resource-return contents, truth, graders, controls, replays and historical results are
host-only or evidence-only.

## Lifecycle

1. Inspect public evidence and write analysis artifacts under `work/`.
2. Call `commit_validation_plan` once with a disclosed schema-valid plan.
3. Call `reveal_validation` once; the committed plan cannot then be changed.
4. Compute the committed analyses and save their underlying tables and outputs.
5. Call `commit_followup_plan` with one resource or `none` and explicit contingencies.
6. Call `purchase_resource` at most once, consistently with the commitment.
7. Save any required follow-up calculations, belief update and bounded decision.
8. Call `submit` once with the final machine-readable object.

The environment may return recoverable contract feedback. Protected inputs cannot be
mutated, and a stopped terminal episode cannot be resumed for another attempt.

## Required artifacts

The verifier follows the agent's registered artifact graph. Required analyses must
retain source-linked analysis tables and machine-readable calculation outputs.
Important numerical claims are recomputed from the saved rows. Valid alternative
aggregation and statistical workflows are accepted when they preserve the committed
estimand, dependence structure, provenance and disclosed scientific properties.

## Three distinct measurements

- **Strict mission success:** every decision-critical scientific property passes and
  the host accepted the final submission.
- **Partial scientific quality:** independently correct property-local work retained
  for diagnosis; this is not a mission threshold.
- **Reliability:** whether the model completed the required lifecycle and obtained an
  accepted submission.

Failure classes are reported separately: scientific, contract, model completion,
provider and infrastructure.

## Local fake-provider execution

From the repository root, with Docker Desktop running:

```bash
PYTHONPATH=src:. .venv.nosync/bin/python scripts/run_case2_mmmvp_v1.py --fake
```

This executes the packaged production lifecycle with deterministic fake-provider
actions and makes no network request.

## One real episode later

A real episode is intentionally not authorized by packaging. After explicit approval,
use the frozen release digest, a pinned model/provider from the frozen configuration,
fallbacks disabled and a separately stated cost cap:

```bash
PYTHONPATH=src:. .venv.nosync/bin/python scripts/run_case2_mmmvp_v1.py \
  --execute --model-id MODEL_ID --maximum-incremental-cost-usd CAP \
  --authorization-digest FROZEN_DIGEST
```

The script refuses a real request when the supplied authorization does not match the
freeze. It loads the API credential host-side; credentials are never placed in the
agent workspace, prompt, tool result or ledger.

## Replay and grade

```bash
PYTHONPATH=src:. .venv.nosync/bin/python scripts/replay_case2_mmmvp_v1.py
```

Replay is read-only, runs the canonical packaged verifier over the four immutable
trajectories and checks parity with the separately preserved accepted development
replay. It never rewrites historical scores.

## Packaging-pass status and limitations

This packaging pass spends **$0** and makes no model or network call. Internally
authored controls are not external expert validation. Only four natural trajectories
have been inspected. Repeated seeds are required before model comparison. The current
contract cannot cite an uncertainty sub-result separately from its containing
calculation. No stable model ranking is claimed. Case 2 is one MMMVP case, not a broad
computational-biology benchmark.

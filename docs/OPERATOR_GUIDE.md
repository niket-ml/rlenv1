# UC-Bench v0 operator guide

## What the operator does

Docker Desktop only needs to be open. Do not manually create containers,
images, volumes, or Docker models; UC-Bench creates and destroys one locked-
down container per trajectory.

The local `.env` file contains only:

```dotenv
OPENROUTER_API_KEY=<local secret>
```

It is ignored by Git and must never be copied into a notebook, task package,
trajectory, screenshot, or chat message.

## Current spend controls

The OpenRouter account and key are funded, with an operator-controlled key
limit. Auto top-up remains disabled. The provider key limit is an account-wide
hard ceiling; it does not authorize additional experiments by itself.

The Stage 7 nine-run smoke retains its separate $9.051 local planning cap.
UC-Bench also enforces turn, token, timeout, and per-run planning guards. A
larger evaluation requires a new, explicit run decision even while unused
credits remain.

The v0.3 development calibration is paused and must not be resumed. Its raw
checkpoint remains preserved for diagnostic analysis.

The v0.4 development calibration has a strict $30 incremental-spend cap. It
checks live key usage before each trajectory, checkpoints after each trajectory,
excludes only verified infrastructure failures, and refuses Astra. Resume
verifies the immutable freeze manifest. A 3.25-second intra-trajectory request
interval respects OpenRouter's temporary 20-request/minute new-account limit
without changing the task.

## Safe commands

These commands do not call a paid model:

```bash
make runtime-preflight
make smoke-plan
PYTHONPATH=src ./.venv/bin/python scripts/check_openrouter_ready.py
```

The historical Stage 7 integration canary is explicit and never runs by accident:

```bash
PYTHONPATH=src ./.venv/bin/python scripts/run_model_canary.py \
  --execute
```

The canary uses the same 40-turn and 40,000-total-completion-token envelope as
the smoke trajectories. A previous 20-turn free-model envelope was empirically
too short for the serial tool workflow and is retained only in historical run
artifacts.

The nine-run smoke remains planning-only unless both `--execute` and a local
cost cap are supplied:

```bash
PYTHONPATH=src ./.venv/bin/python scripts/run_smoke_pilot.py
```

The Stage 7 smoke is complete; do not rerun it merely because account credits
remain.

Do not run the historical v0.3 resume command. v0.4 is planning-safe by default:

```bash
PYTHONPATH=src ./.venv/bin/python scripts/run_v04_calibration.py
```

The v0.4 matrix is complete and must not be rerun merely because budget remains.
`scripts/analyze_v04.py` reports a mandatory no-go, so Astra is not authorized.
Do not tune the observed v0.4 tasks; any successor requires a new version and a
new pre-exposure freeze.

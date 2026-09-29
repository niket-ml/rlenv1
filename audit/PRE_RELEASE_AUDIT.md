# UC-Bench v0 automated pre-release audit

Date: 2026-09-06

## Decision

**NO-GO for model-ranking or public benchmark claims.** The environment core is
reproducible, but real agent trajectories and independent review do not yet
exist. This is an intentionally fail-closed result, not a failed environment
build.

## Automated result

Seven of eleven release checks pass:

- Public benchmark, reward, task, smoke, and evaluation invariants validate.
- All six pinned GEO source files match their declared byte counts and SHA-256
  digests.
- No sealed GSE92415 sample identifier appears in the scanned public source,
  configuration, documentation, notebook, artifact, packaged episode, task,
  test, or report surfaces (0 matching files across 59 forbidden identifiers).
- The reference episode reaches terminal submission from a fresh packaged
  start state.
- Expert/mediocre and keyword-only grader controls pass.
- Universal abstention, advancement, stopping, and AUC-chasing policies fail the
  symmetric scenario controls.
- The deterministic runtime fixture has no infrastructure failures.

Four checks do not pass:

- No real-model smoke has run (`AF-007`): all three model variables are unset,
  no provider key is present, and no Docker, Prime, or Modal backend is ready.
- No prespecified repeated multi-model evaluation has run (`AF-005`).
- High-severity findings therefore remain open.
- Independent scientific and reward-hacking review is still pending.

The benchmark author cannot self-approve the independent-review gate.

## Reproduction

Run:

```bash
make pre-release-audit
```

The machine-readable result is written to
`artifacts/release/pre_release_audit.json`. The audit command returns success
when it executes correctly even when its scientific decision is `no_go`; CI or
release automation must inspect `release_decision` rather than treating command
execution as release approval.

# Runtime integration

UC-Bench uses a two-part agent harness:

1. An isolated coding runtime mounts one generated start state and gives the
   agent its native file, Python, and shell workflow.
2. Four benchmark-domain tools remain outside that runtime:
   `ask_analyst`, `commit_analysis`, `reveal_validation`, and `submit`.

The split is a security boundary. The coding runtime must not mount
`grader_private/`, the sealed expression matrix, private scenario manifests,
or host credentials. The domain tools own the private state and return only
their documented public observations.

`src/uc_bench/runtime_adapter.py` exposes those four operations using the
installed Verifiers 0.3.1 tool schema. It intentionally does not add a local
host-shell tool. A host subprocess with only `cwd` changed is not a sandbox and
could read the private grader paths. Production rollouts therefore require a
Docker, VM, or equivalent isolated coding harness.

This choice follows two useful external lessons:

- The Hugging Face RL-environments guide separates environment state, tools,
  rewards, rollout execution, and training-loop integration, and notes that
  frameworks differ mainly in how those parts are wired and isolated:
  <https://adithyask-rl-environments-guide.hf.space/>.
- TrainLoop reports better reliability and lower token use when complex
  knowledge-work agents are recast as code-native tasks with scripts and clear
  Markdown rather than a large collection of bespoke tools:
  <https://www.trainloop.ai/research/mercor>.

That is why UC-Bench gives the agent ordinary `.py`, `.json`, `.csv.gz`, and
Markdown files, while keeping only irreversible or private actions as custom
tools. The environment core remains framework-neutral so the harness can move
from Verifiers to Harbor or another runner without changing task semantics or
grader logic.

## Offline smoke

Run:

```bash
make runtime-smoke
```

The smoke constructs the actual Verifiers tool definitions and drives three
fresh packages through deterministic fixtures: a valid reference, a
schema-valid but reckless scientific decision, and a post-commit mutation.
These fixtures test wiring and error classification only; they are explicitly
not model or leaderboard results.

## Real-model smoke requirements

The frozen smoke matrix is three models × three attempts in the `full_data`
condition. Model names are supplied through `UC_BENCH_MODEL_A`,
`UC_BENCH_MODEL_B`, and `UC_BENCH_MODEL_C`; provider credentials are read from
the corresponding provider's environment variable. Credential values must
never be written to trajectory or audit artifacts.

Select the isolated runtime with `UC_BENCH_ISOLATION_BACKEND`, using one of
`docker`, `prime`, or `modal`. Docker requires a working local daemon; Prime
requires `PRIME_API_KEY`; Modal requires both `MODAL_TOKEN_ID` and
`MODAL_TOKEN_SECRET`. A host subprocess and a changed working directory are
explicitly rejected as isolation. `make runtime-smoke` reports readiness using
booleans only and never serializes credential values.

Before a real run, the selected runtime must pass these checks:

- one isolated filesystem per rollout;
- no private paths or credentials mounted into the agent container;
- the full-data start-state digest matches its manifest;
- the four domain tools connect to rollout-local state;
- artifacts are collected before sandbox destruction;
- infrastructure failures are reported separately from scientific failures;
- concurrency cannot mix episode state.

The nine-trajectory smoke is an integration check. It is not enough to claim
model ranking; Stage 8 requires approximately ten trajectories per model per
headline condition.

## Local Docker implementation

`src/uc_bench/docker_runtime.py` implements the local v0 harness. Each episode
gets one network-disabled container with a read-only root filesystem, all
capabilities dropped, no host credentials, and only its generated start state
mounted at `/workspace`. The agent receives `inspect_workspace`, `read_file`,
`write_file`, and `run_command`; the four irreversible domain tools stay on
the host.

Build and verify the pinned image without contacting a model:

```bash
make runtime-image
make runtime-preflight
```

`scripts/run_model_canary.py` is dry-run safe unless `--execute` is supplied.
`scripts/run_smoke_pilot.py` is also planning-only by default and requires an
explicit local cost cap in addition to the provider-side key limit. Host-side
before/after OpenRouter key usage is recorded so cost accounting does not
depend on Verifiers preserving provider-specific response fields.

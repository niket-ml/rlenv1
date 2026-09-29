# Stage 4 environment and tool boundary

Decision: **the environment boundary passes its v0 gate**.

The agent receives one of two reproducible start states. `full_data` contains
the two development cohorts; `data_withheld` retains the identical task and
tool contract but omits development expression and outcomes. Neither package
contains GSE92415 features, outcomes, individual predictions, or any of the 59
sealed sample identifiers.

| Check | Evidence | Result |
|---|---|---|
| Reproducible full-data package | `make environment-build` | 17 files; digest `79672b4ef2aa4bb9b2f52a941a4235f6843e74d12b3791e6ba264cb6d11a1ce5` |
| Matched data-withheld control | `make environment-build` | 15 files; digest `7f75ef6d8b8f5596779efe3e7b133a8b2402bbdbb10be47580f30ab2fe1c4499` |
| Sealed-ID scan | both generated manifests | 59 forbidden IDs scanned; zero matches |
| Safe model execution | `src/uc_bench/predictor.py` | only inspectable JSON linear-rank models; no arbitrary serialization |
| Commit/reveal state machine | `tests/test_environment.py`, `tests/test_state.py` | ordered one-time transitions pass |
| Post-commit mutation | `test_mutated_model_fails_before_reveal` | rejected before private model application |
| Sealed training contamination | `test_sealed_sample_in_training_manifest_is_rejected` | rejected at commit |
| Private result surface | `test_complete_episode_reveals_only_aggregate_result` | only AUC, interval, p-value, and n emitted |
| Fresh-state expert replay | `artifacts/reference/environment_episode.json` | submitted; exactly reproduces direct reference result |

The public predictor contract accepts 1–50 named genes and finite logistic
coefficients over within-sample percentile ranks. The private evaluator loads
the model as data and never executes agent-supplied code. Model version,
feature schema, decision threshold, permutation count, provenance sample IDs,
artifact ordering, and artifact hashes are checked before validation.

The fixed `ask_analyst` answer bank accepts three enumerated topics and has a
three-call limit. Unknown topics fail explicitly instead of being scored by
language similarity. The environment record retains queries, state
transitions, digests, and aggregate validation but not private rows.

Replay commands:

```bash
make environment
make check
```

Generated start-state directories are ignored build artifacts. Their source
task cards, schemas, packaging code, manifests, tests, and replay record are
versioned.

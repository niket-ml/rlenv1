# Stage 5 grader validation

Decision: **the deterministic graceful-failure grader passes the initial
separation and reward-hacking gate**.

The grader reads state transitions, committed hashes, safe-model and provenance
artifacts, structured executed checks, the aggregate validation result, stable
diagnostic codes, the terminal decision, and a typed next action. Explanatory
prose is retained for human audit but contributes no keyword or embedding
score. Raw AUC is used only to score the precommitted expected AUC and decision
threshold; it is not a model-quality reward.

| Controlled attempt | Graceful-failure score | Contract valid | Expected behavior |
|---|---:|---|---|
| Expert reference | 100 | yes | Evidence-backed `insufficient_evidence` |
| Deliberately mediocre | 40 | yes | Same result, but AUC 0.95 expectation and unsafe `advance` |
| Keyword-only caution | 40 | no | Correct language/decision without committed evidence hits the soft ceiling |
| Structured false `pass` claims | 40 | no | Recomputed model/data statistics contradict the submitted JSON |
| Sealed-outcome access | 0 | no | Hard invalidation |

The expert–mediocre separation is 60 points, above the prespecified 30-point
minimum. The mediocre attempt deliberately shares the exact predictor,
development evidence, and validation result with the expert, so the difference
comes from diagnosis, calibration, and action—not biological luck.

Anti-hacking behavior is mechanical:

- Diagnostic codes receive credit only when supported by independently
  recomputed workspace evidence or the private validation state.
- Adding unsupported codes reduces diagnostic precision.
- Missing, changed, or unhashable committed artifacts fail contract checks.
- A submitted `status: pass` contradicted by recomputation triggers the
  40-point soft ceiling.
- A schema-valid but scientifically reckless attempt can retain mechanical
  integrity points; partial credit remains interpretable.
- Missing required artifacts triggers the 40-point soft ceiling.
- Sealed access, post-commit mutation, or another hard-invalid monitor event
  returns zero.

Evidence:

- `src/uc_bench/grading.py`
- `src/uc_bench/evidence_verification.py`
- `configs/authentic_rubric.json`
- `artifacts/grading/reference_separation.json`
- `tests/test_grading.py`
- `tests/test_environment.py`

Replay commands:

```bash
make grade-reference
make check
```

This gate does not establish model separation across private evidence states;
that is Stage 6 onward. The perfect expert score is a rubric conformance test,
not a leaderboard result.

# Stage 3 expert reference episode

Decision: **the authentic cohort supports `insufficient_evidence`, not
advancement**.

The reference analysis fixes the five-gene panel before sealed validation and
does not search the 17,151-gene feature space. Each gene is represented by its
within-sample percentile rank, the five ranks form one response composite, and
a one-variable L2 logistic regression supplies probabilities.

| Evaluation | AUC | 95% stratified bootstrap interval |
|---|---:|---:|
| GSE16879 fit/sanity check | 0.930 | reported as optimistic, not validation |
| GSE73661 untouched replication | 0.867 | available in `development_evidence.json` |
| Precommitted GSE92415 expectation | 0.667 | 0.517–0.817 |
| GSE92415 sealed result | 0.667 | 0.513–0.814 |

The sealed permutation p-value is 0.0147. That is evidence of directional
signal, but it does not override the prespecified advancement rule: AUC must be
at least 0.70, the lower interval bound must exceed 0.50, and the null test must
pass. The endpoint, drug, platform, and sample-size transfer uncertainties also
remain. The correct graceful-failure action is to preserve the result and
request a larger prospectively registered, endpoint-matched cohort using the
same locked assay.

Replay command:

```bash
make reference
```

Primary evidence:

- `artifacts/reference/model.json`
- `artifacts/reference/predictor_manifest.json`
- `artifacts/reference/development_evidence.json`
- `artifacts/reference/commitment.json`
- `artifacts/reference/validation_result.json`
- `artifacts/reference/final_submission.json`
- `artifacts/reference/episode.json`

`artifacts/reference/mediocre_episode.json` is a controlled comparison using
the same model and validation result but an unjustified expected AUC of 0.95
and an `advance` decision based only on being above chance. This isolates
scientific judgment from predictor performance for the Stage 5 expert-
separation test.

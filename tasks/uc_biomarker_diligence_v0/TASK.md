# Anti-TNF biomarker diligence

You are conducting technical diligence on a baseline-biopsy transcriptomic
predictor for ulcerative-colitis response to anti-TNF therapy. The deliverable
is a defensible evidence decision, not the highest possible AUC.

You must audit the development evidence, construct a small predictor that
satisfies `schemas/model.schema.json`, state its expected transfer performance,
and irreversibly commit the model and provenance manifest before requesting
one blinded validation. The validator privately applies your JSON model to the
sealed cohort. You receive only aggregate AUC, its bootstrap interval,
permutation p-value, and evaluated sample count. You never receive validation
features, outcomes, or individual predictions.

## Required decision chain

1. Inspect the start state and verify file integrity.
2. Reconstruct development cohorts at the patient level.
3. Check treatment arm, baseline timepoint, tissue, response definition, and
   endpoint mismatch.
4. Align features without treating cohort-native normalized arrays as a shared
   absolute expression scale.
5. Build a leakage-safe, low-dimensional reference analysis.
6. Evaluate stability, negative controls, and uncertainty.
7. Write the three commit artifacts below, then call `commit_analysis` once.
8. Call `reveal_validation` once and diagnose the aggregate result.
9. Choose `advance`, `stop`, or `insufficient_evidence` with calibrated
   confidence.
10. Cite real artifacts and name the smallest next action that could resolve
    the uncertainty.

Apply the prespecified numerical decision policy in
`reference/benchmark.json`. `advance` requires every listed advancement
criterion; `stop` is reserved for a hard unresolved integrity failure; a valid
episode that meets neither rule is `insufficient_evidence`.

The milestones are a workflow, not ten independent trivia questions. Setup
work is deliberately downweighted. A plausible gene list, scientific prose, or
good validation AUC cannot compensate for leakage, mutation after commit,
fabricated checks, or a decision unsupported by the evidence.

## Public machine-readable contract

The files in `schemas/` define the exact field names and controlled
vocabularies used by deterministic grading. These are part of the task, not
hidden answer keywords. In particular:

- `status: "pass"` means a check was executed and its fields are accurate; it
  does not mean that no mismatch or limitation was found;
- all manifest entries must be exact `sample_id` values from
  `data/metadata.csv`, never cohort aliases, wildcards, or count placeholders;
- provenance roles record how samples were used and may overlap;
- `GSE73661` is untouched replication only if none of its sample IDs were used
  for model fitting, tuning, or feature selection; and
- development AUCs, confidence intervals, permutation results, counts, and
every claimed `pass` are recomputed from the committed predictor.

`public_evaluator.py` contains the exact sealed-data-free rank transform,
stratified bootstrap, and replication permutation definitions used for this
recomputation. Run it on the final bytes of `submission/model.json` and copy
its exact development outputs into the evidence artifact. It never loads or
exposes sealed features, outcomes, or predictions.

If a check cannot be supported, use `fail`, `not_run`, or
`insufficient_evidence` plus a concise `reason`. That preserves contract
validity while reducing the evidence score; an inaccurate `pass` invalidates
the soft contract.

## Commit artifacts

Create all four files under `submission/`:

- `model.json`, following `schemas/model.schema.json`;
- `predictor_manifest.json`, following
  `schemas/predictor_manifest.schema.json`;
- `analysis_evidence.json`, following
  `schemas/analysis_evidence.schema.json`; and
- `commitment.json`, following `schemas/commitment.schema.json` and listing the
  model, manifest, and analysis evidence among `artifact_paths`.

The supported model is intentionally constrained and inspectable: a logistic
linear model over within-sample percentile ranks of 1–50 named genes. The
grader executes no agent-supplied serialized code. All named genes must exist
in the sealed platform or evaluation fails closed.

You may also include analysis `.py` files in `artifact_paths` so their exact
bytes are frozen for replay. They are hashed but never executed by the private
grader; quantitative `status: pass` claims are instead recomputed from the
committed JSON predictor and the supplied workspace data.

Committing records canonical SHA-256 hashes in the given artifact ordering.
Any committed-file change before reveal or submission invalidates the episode.

## Final artifact

After reveal, create `submission/final_submission.json` following
`schemas/final_submission.schema.json`, cite evidence files that really exist,
and call `submit` once. Use stable `diagnostic_codes` and a
`next_action_type`; explanatory prose is retained for audit but is not used as
a keyword score. If no failure applies, use `"failure_mode": "none"` and
`"diagnostic_codes": ["none"]`.

## Analyst interaction

You may call `ask_analyst` at most three times, using one exact topic per call:
`cohort_endpoint`, `platform_processing`, or `intended_use`. Responses are
fixed, structured task evidence. They do not reveal sealed samples.

## Evidence and safety expectations

- Treat discovery performance as optimistic; preserve an untouched
  development replication whenever the condition supplies data.
- A mucosal-healing predictor is not automatically a clinical-response
  predictor, even within the same drug class.
- Report small-cohort uncertainty. The validation AUC is diagnostic, not the
  headline reward.
- Do not claim clinical validity or use the result for treatment selection.
- If evidence is insufficient, localize why, contain the claim, preserve what
  remains valid, and propose a resolving experiment. Empty caution receives no
  credit, and abstention is penalized when evidence is sufficient.

The `data_withheld` condition intentionally omits development matrices and
outcomes. It measures how much of an agent's behavior is supported by supplied
data versus remembered literature. The task and action contract remain the
same.

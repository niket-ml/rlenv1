# Integrating the separately developed anti-TNF predictor

The engineer's baseline-biopsy transcriptomic predictor is useful as an
additional diligence artifact, not as a replacement for UC-Bench and not as
the headline story.

## Safe integration paths

1. If the predictor can be exported exactly as the supported linear logistic
   model over within-sample gene ranks, convert it to `model.json` and provide
   a complete `predictor_manifest.json`.
2. If it is more complex, do **not** load its pickle, joblib, notebook, or
   arbitrary code in the grader. Host it behind a separately isolated,
   immutable prediction adapter. The adapter should accept only a versioned
   feature matrix, return probabilities, and emit a model/version digest.

In either case, require an attestation that GSE92415 outcomes—and any derivative
labels or evaluation outputs—were never used for feature selection, fitting,
tuning, threshold selection, or calibration. Verify sample-role manifests
against the private sealed identifiers before evaluation.

## Useful ablation

Run the same sealed evaluator and decision policy for:

- agent without the specialist predictor;
- specialist predictor without agent diligence; and
- agent with the immutable specialist predictor.

This tests whether the agent adds value by checking provenance, endpoint fit,
platform transfer, calibration, and uncertainty rather than merely inheriting
a higher AUC. Keep this ablation secondary to the core graceful-failure result.

## Non-goals

- Do not change the primary reward to predictor AUC.
- Do not allow the engineer's model to make the task clinically framed.
- Do not weaken the one-shot commit/reveal boundary.
- Do not let a model-specific failure mode become the only failure state.

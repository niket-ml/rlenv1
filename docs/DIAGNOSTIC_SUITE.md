# UC-Bench v0 diagnostic task family

## Decision

The existing authentic end-to-end episode remains the anchor. It is not, by
itself, a model-ranking benchmark: the first clean smoke produced a ceiling for
one model and a completion floor for another. UC-Bench therefore expands within
the same repository and scientific decision chain rather than adding unrelated
biology trivia or selecting tasks merely because a preferred model wins them.

The ten task cards are defined in `configs/diagnostic_suite.json`. Shorter
milestone and post-reveal tasks isolate capabilities; the complete episode
tests whether an agent can compose those capabilities over a long horizon.

## What a gradient means

A useful gradient is prespecified, repeatable separation across difficulty
levels. Release date is not a grading input and a task is never retained solely
because newer models score higher. Calibration may reject or revise a task when
more than half of attempts are at the floor or ceiling. Held-out variant levels
are frozen before a ranking run.

The primary curves are:

- completion and contract-valid rates across workflow horizon;
- detection probability versus observable defect strength;
- correct decision probability versus AUC, interval width, p-value, and n;
- containment before commitment versus after reveal;
- full-data minus data-withheld performance;
- base minus expert-playbook performance; and
- correct recovery action versus diagnosed failure.

## Causal interpretation

The benchmark can directly demonstrate that a biological training or
validation cohort is small, unstable, confounded, or cross-platform. It cannot
deduce that an LLM's pretraining corpus was undersampled from one failed run.
That stronger hypothesis requires paired interventions.

- A full-data versus data-withheld difference measures data grounding and
  contamination risk.
- A base versus expert-playbook difference measures a promptable procedural
  expertise gap. It does not prove a pretraining cause.
- A short-task versus end-to-end difference separates local scientific
  reasoning from long-horizon planning and tool-use failure.
- Improvement only after actual targeted fine-tuning would support an SFT
  intervention; RLHF-specific causation requires a separately controlled
  training experiment.

## Anti-gimmick requirements

Every graded planted defect must be observable from supplied evidence or have
an observable aggregate consequence. Exact hidden label flips are never a
required answer. Authentic and controlled results are reported separately,
infrastructure failures are excluded, and unsubmitted agent attempts score zero
in reliability-inclusive comparisons. Abstention, advancement, and stopping
all have symmetric positive and negative controls.

All ten task cards are now runnable. T03–T06 use generated CSV workspaces and
private graders that recompute the expected result from those same visible
files. Their 20 scenarios cover exact identity conflicts, required-feature
dropout, measured outcome–batch association, sample-size uncertainty, and
aggregate label-noise degradation. Sample size and label noise are separate
one-factor ladders.

The suite is still `specified_not_frozen` for headline use. The packet and
executable-data calibrations each failed their predeclared floor/ceiling gate,
even though their combined 14-cell means formed a strict directional temporal
gradient. One attempt per cell, calibration-visible variants, and frontier
ceiling effects are insufficient for a ranking claim. See
`reports/generated/combined_calibration.md` for the exact limitations.

# Biomarker data-audit diagnostic

You are reviewing one data-integrity or validation-stability problem from a
biomarker diligence workflow. This is a short executable analysis task.

1. Inspect `task.json`, the files under `data/`, and the public schema.
2. Use Python to compute every metric requested by `task.json`. Do not estimate
   values by eye and do not invent unavailable evidence.
3. Apply the decision policy and controlled vocabularies in `task.json`.
4. Write `submission/final_submission.json` using
   `schemas/final_submission.schema.json`.
5. Call `submit_data_audit` exactly once. A usable attempt that does not submit
   scores zero.

All thresholds, metric definitions, tolerances, and component weights are
public in `task.json`. The private grader independently recomputes the answer
from the supplied files. For directly observable identity duplicates and
missing required features, report the exact affected IDs. For aggregate batch
confounding and label-noise/stability tasks, do not guess latent affected
samples.

This is a research advancement decision, not permission for clinical use.

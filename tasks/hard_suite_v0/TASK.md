# Composed biomarker-diligence case

You are performing pre-licensing diligence on a locked anti-TNF response
predictor. The objective is not to maximize AUC at any cost. It is to identify
what the evidence can support, contain invalid claims, and choose the smallest
resource or experiment that resolves the live uncertainty.

Read `task.json`, `evidence_manifest.json`, every listed pre-reveal file, and the
JSON schemas before acting. The case deliberately combines identity, endpoint,
platform, drug, label, power, and provenance evidence. Several explanations may
be plausible at once.

1. Compute the pre-reveal metrics. Write `submission/commitment.json`. Rank at
   least two hypotheses, predeclare at least four metric IDs, choose the
   smallest discriminating experiment, and state conditional decisions.
2. Call `commit_plan`. This records the file hash and is irreversible.
3. Call `reveal_evidence` exactly once. Inspect every newly revealed file and
   recompute the full metric set from data; do not copy narrative claims.
4. Write `submission/final_submission.json`, validate it with the provided
   schema, and call `submit_hard_suite` successfully. A usable attempt that does
   not submit scores zero.

The public contract gives exact metric definitions, tolerances, decision rules,
controlled values, and score weights. Tool validation returns actionable schema
errors. The private grader independently recomputes answers from the CSVs. Extra
citations to genuine manifest evidence are not penalized. Confidence is retained
for calibration analysis but is not compared with a hidden confidence band.

Do not infer that prompting, retrieval, SFT, RL, or another model adaptation is
needed unless that intervention was actually supplied and paired in the case.
This is a research-diligence decision, not a clinical-use decision.

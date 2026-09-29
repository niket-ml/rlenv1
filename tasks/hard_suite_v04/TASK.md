# Quantitative biomarker-diligence case

You are auditing a locked anti-TNF response predictor. This is a statistical
decision task, not an AUC-calculation exercise. You must choose the scientifically
relevant estimand, use a dependence-aware uncertainty analysis, distinguish
competing explanations, and select the smallest resource with positive value of
information.

1. Inspect `task.json`, `analysis_contract.json`, every file under `case/` and
   `data/`, `resources/resource_catalog.json`, the evidence manifest, and both
   schemas.
2. Explore the data with Python. Decide which unit of analysis and uncertainty
   method answer the intended-use question. Candidate methods are documented,
   but the task does not tell you which one is valid for this case.
3. Write `submission/commitment.json`. Rank at least two live explanations,
   choose a primary estimand and analysis method, predeclare at least four
   metrics, and request R1, R2, R3, or `none`.
4. Call `commit_plan`. The commitment and resource choice are hashed and cannot
   be changed. A factually unavailable resource is rejected before the hash so
   you may correct that availability mistake.
5. Call `reveal_evidence` once. Only the packet for your committed resource is
   revealed. Recompute the requested metrics from `evidence/analysis.csv`; use
   the fixed resampling/permutation settings in `analysis_contract.json`.
6. Write `submission/final_submission.json`, validate it, and call
   `submit_hard_suite`. Finish only after that tool succeeds.

Metric definitions and tolerances are public. The private grader independently
recomputes every number. Credit separates estimand choice, method choice,
computation, interpretation, diagnosis, decision, resource selection, and
recovery. Extra real evidence citations are harmless. A usable unsubmitted
attempt scores zero.

The horizon is deliberately generous. Do not infer that prompting, retrieval,
SFT, RL, experts, or more data is the remedy unless the selected evidence
actually tests that intervention. This is research diligence, not a clinical-use
decision.

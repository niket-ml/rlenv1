# Resource-selection biomarker diligence case

You are evaluating a locked anti-TNF response predictor. The goal is to make
the strongest decision supported by the current evidence and to select the
smallest resource that can distinguish the live explanations.

The public baseline contains multiple plausible scientific and execution
failures. `resources/resource_catalog.json` lists three concrete follow-up
resources; some may be unavailable. You may irreversibly request at most one,
or request `none` when no available option can resolve the evidence.

1. Inspect `task.json`, all baseline files, the evidence manifest, the resource
   catalog, and both schemas. Compute the pre-reveal metrics.
2. Write `submission/commitment.json`: rank at least two hypotheses, predeclare
   at least four metrics, choose the smallest discriminating experiment, and
   set `requested_resource_id` to `R1`, `R2`, `R3`, or `none`.
3. Call `commit_plan`. The environment rejects unavailable resources before it
   creates the irreversible hash, allowing a factual availability mistake to be
   corrected without consuming the commitment.
4. Call `reveal_evidence` once. Only the packet for the committed resource is
   revealed. Recompute from CSVs; do not substitute a narrative memo for outcome
   evidence.
5. Write and validate `submission/final_submission.json`, then call
   `submit_hard_suite` successfully. A usable unsubmitted attempt scores zero.

The 32-turn horizon is intentionally generous. Tool validation returns precise
schema errors. Metric definitions, tolerances, decisions, and score weights are
public. Extra citations to real evidence are not penalized. The private grader
recomputes the evidence and tests resource choice; it does not score keywords.

Do not claim retrieval, SFT, RL, or tool training is required unless that exact
model intervention is experimentally paired. This is research diligence, not a
clinical-use decision.


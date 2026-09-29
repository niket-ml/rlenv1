# UC-Bench

An agent environment for computational-biology diligence.

A research team receives a predictor intended to estimate response to infliximab in ulcerative colitis. The predictor has promising reported performance. The team must establish whether the evidence justifies funding its next study.

UC-Bench gives that investigation to an AI agent. The agent works with patient records and the files behind the reported analysis. It commits a validation plan before seeing outcomes, calculates performance from the underlying data and decides whether further evidence would change the investment decision.

## What the environment tests

The challenge is to carry a scientific argument through a complete investigation. A correct calculation has to use the right patient population. A follow-up study has to answer the unresolved question. The final recommendation has to remain within what the evidence supports.

| Investigation | Central question |
|---|---|
| Evidence sufficiency | When does the available evidence justify further research? |
| Study-site effects | Does apparent performance survive analysis within individual sites? |
| Execution provenance | Can the prediction file be linked to a procedure the team can verify? |
| Probability use | Are the predicted probabilities suitable for the proposed decision? |

Earlier choices affect what can validly be concluded later. The agent has room to choose a supported analysis and decide whether additional evidence is worth obtaining. An evidence-backed decision to stop can complete the task successfully.

## Evaluation

The verifier independently recomputes important results from saved artifacts and checks the order of consequential actions. Complete mission success requires a supported evidence chain through the final submission. Partial credit records the valid work completed along the way.

The environment includes alternative-workflow controls and altered-input tests that challenge copied answers. Saved trajectories support replay and inspection of the first consequential failure. Provider faults are recorded separately from scientific errors.

Initial runs across multiple model families produced incomplete investigations and failures in analysis commitments and evidence handling. These are pilot observations; repeated evaluations are needed to estimate failure rates.

Cases 1 and 2 have completed initial model evaluation. Case 3 has passed local validation, with model evaluation on its current version pending. Case 4 remains at an earlier development stage.

## Repository

- [Technical reports](reports/README.md)
- [Case 2 environment runbook](docs/CASE2_MMMVP_V1_RUNBOOK.md)
- [Case 3 implementation](reports/CASE3_MMMVP_IMPLEMENTATION_SPEC.md)

Environment code is in `src/uc_bench/`, with evaluation commands in `scripts/` and controls in `tests/`. Public case inputs live in `tasks/`.

This checkout contains source and documentation. Private evidence and model-run artifacts are stored separately and are required for full release verification. Reports contain case answers and belong outside agent evaluation workspaces.

For the existing local setup, use `.venv.nosync/`. Credentials stay in the ignored `.env` file.

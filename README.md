# UC-Bench

UC-Bench tests whether an AI agent can assess a predictor that estimates response to infliximab in ulcerative colitis. The agent checks the patient records, reproduces the analysis and decides whether another study is worth funding. It can request more evidence when that would help resolve the decision.

## Project status

| Case | Question | Status |
|---|---|---|
| 1 | Is there enough evidence to fund the next research stage? | Complete: final RC6 pilot |
| 2 | Does the predictor work within each study site? | Complete: frozen MMMVP release and initial model runs |
| 3 | Can the predictions be reproduced through a documented procedure? | Local checks passed; model runs on the current version are pending |
| 4 | Are the predicted probabilities useful for the proposed decision? | Historical work exists; release review is pending |

Case 3 has two versions with the same starting files. The follow-up result retains predictive signal in one version and falls close to chance in the other.

## Where to start

- [Results](docs/CURRENT_RESULTS.md): model names, scores and what failed.
- [Reports](reports/README.md): detailed reports and LaTeX files.
- [Case 2 runbook](docs/CASE2_MMMVP_V1_RUNBOOK.md): how to use the packaged environment.

## Files

Code is in `src/uc_bench/`, with commands in `scripts/` and tests in `tests/`. Case inputs live in `tasks/`; hidden evidence lives in `grader_private/`.

Saved runs and release records are in `artifacts/` and `build/`. These folders contain the evidence behind the results. Development work lives in `development/`, and the build history is in `audit/`.

Use the existing Python environment at `.venv.nosync/`. Credentials stay in the ignored local `.env` file.

A Git checkout contains the source and documentation. Private grader data, model-run
artifacts and generated development workspaces stay local, so release verification and
evidence-dependent tests also need those preserved bundles. Reports contain case answers;
keep this repository private while the evaluation cases are in use.

This is a small pilot with one retained attempt per model in the displayed comparison. Repeated attempts are needed to establish a reliable ranking.

The [previous README](docs/history/README_before_2026-09-28.md) documents earlier versions. The [cleanup record](audit/WORKSPACE_CLEANUP_2026-09-28.md) lists what was changed and checked.

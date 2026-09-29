# UC-Bench

UC-Bench is a contamination-aware reinforcement-learning environment for a
realistic ulcerative-colitis biomarker diligence workflow. An agent inherits a
research repository, audits and repairs an anti-TNF response analysis, commits
its method and expected external performance, receives a one-time blinded
validation result, and submits an `advance`, `stop`, or
`insufficient_evidence` decision.

The prediction model is an artifact inside the workflow. The benchmark's
primary metric is evidence-backed graceful failure: whether the agent detects,
contains, diagnoses, and recovers from scientific evidence failures while
preserving integrity, uncertainty calibration, and reproducibility. The frozen
contract is in [`docs/BENCHMARK_CONTRACT.md`](docs/BENCHMARK_CONTRACT.md), with
its anti-cheating and anti-reward-hacking analysis in
[`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md).

## Current status

This repository contains a working v0 environment core:

- Pinned, verified GSE16879, GSE73661, and GSE92415 data assembly with a
  patient-overlap and platform audit.
- Reproducible full-data and matched data-withheld agent start states.
- A safe, inspectable JSON predictor contract and private sealed evaluator.
- An irreversible commit/reveal state machine with artifact hashes and
  provenance-based sealed-sample exclusion.
- Evidence-backed deterministic scoring that independently recomputes the
  committed development claims, including expert/mediocre, keyword-only,
  structured-forgery, hard-invalid, and universal-policy controls.
- Four symmetric evidence states and five graded private variant ladders.
- A controlled v0.4 hard suite with five quantitative biomedical-statistical
  intervention pairs, separately sealed development/held-out variants,
  deterministic breaking curves, and a failure/intervention report rather than
  a leaderboard-first output.
- A structurally separate v0.5 MVP: one ten-milestone locked-predictor
  diligence episode with six causal workflow states, claim-level state
  propagation, two irreversible reveals, resource counterfactuals, and
  milestone/capability scoring.
- An unfrozen v0.6 successor with ten independently graded semantic artifacts,
  new development and held-out instances, non-cascading dependency scoring,
  and a pre-scientific cross-provider compatibility gate.
- A Verifiers 0.3.1 four-tool adapter plus deterministic infrastructure smoke.
- Repeated-evaluation statistics and a self-contained pre-result report.
- Unit tests for the critical scientific, state-transition, reporting, and
  integrity guarantees.
- A visual product walkthrough in
  [`notebooks/00_uc_bench_v0_workflow.ipynb`](notebooks/00_uc_bench_v0_workflow.ipynb).

Stages 1–7 pass their audited gates. Stage 8 is in progress: earlier packet and
data suites are preserved as ceiling failures, hard-suite v0.2 is preserved as
an execution-horizon floor, and v0.3 is paused as a quantitative ceiling failure
with its raw checkpoint preserved. v0.4 passed all zero-cost gates and completed
its bounded development calibration at 80.50, 77.65, and 70.35, but is an
explicit no-go: one family explains 43.6% of the gap and Sol's quantitative
component remains at 99.59. Astra was not run. No stable ranking is claimed.
Large processed matrices, private labels, generated rollouts, and provider
credentials remain uncommitted.

v0.5 now passes its zero-cost construction controls. Reference and
alternative-method expert-equivalent workflows score 100; a deliberately
mediocre workflow is lower at every milestone; universal advance, stop,
abstain, and request-more-data policies average 39–41; outcome leakage and
post-commit mutation controls pass. The six development cases and six held-out
instances were created before any v0.5 model call. The frozen 18-episode
development pilot completed for $7.53252860 with zero infrastructure failures
and zero Astra or held-out requests. Its one-seed means were 76.77, 75.08, and
60.04 for Sol, GPT-5.4, and GPT-5.2, respectively, but the result is an explicit
no-go rather than a ranking: the underpowered/irreducible state explains 67.25%
of the observed gap and two valid Sol descriptions were missed by frozen
vocabulary matchers. The original scores are preserved unchanged.

v0.6 scientific tasks produced no model trajectory. All zero-cost
construct controls pass: reference and alternate valid workflows score 100,
professional paraphrases are score-invariant, the deliberately mediocre
workflow is lower in every artifact family, universal decision policies remain
below 42, and committed-artifact tampering is rejected. Authenticated read-only
OpenRouter checks found all five proposed models and exact canonical pins. The
authorized non-scored compatibility stage then passed 5/5 after two documented
provider-adapter corrections: Kimi requires automatic tool choice while
thinking, and Claude's ordinary workflow must avoid policy-triggering
conformance-test wording. Conservative response-reported spend was $0.04574225
under the $3 cap.

The stricter v0.6 ceiling contract was then documented and frozen before the
balanced ten-cell development sentinel. The probe stopped in its first cell
after two zero-cost gateway failures: first a missing authentication header,
then a 404 parameter-routing rejection caused by a mismatch between the exact
scientific payload and the cheaper compatibility payload. No endpoint returned
a model response, so there is no scientific score or ranking. Frozen v0.6 is
preserved as an infrastructure no-go; do not resume it. Incremental probe spend,
held-out requests, and Astra requests were all zero.

Separately versioned v0.6.1-v0.6.3 repaired the execution path without changing
the frozen scientific construct. The complete v0.6.3 ten-cell sentinel is also
an explicit no-go: accepted model means remained above 80, generic policies
received excessive artifact credit, and the grader rejected many defensible
scientific alternatives. Its results and 152-file freeze are preserved and are
never rescored. The remaining development cells, held-out cases, and Astra were
not run.

The current v0.7 is a design reset, not another score patch. It is one compact
four-case predictor-diligence environment with row-level evidence, five
decision-critical checkpoints, an irreversible plan/reveal/purchase sequence,
separate work-quality and full-mission outcomes, and paired clean-replay
mechanisms. Two valid local solvers score 100; empty, generic, and keyword
controls score at most 15; and tamper, universal-policy, buy-everything, and
counterfactual controls pass. v0.7 remains unfrozen and has made zero model
calls. No paid runner or held-out case exists. Its pre-approval report is in
[`reports/generated/hard_suite_v07_preapproval.md`](reports/generated/hard_suite_v07_preapproval.md).

The v0.5 specification is in
[`docs/HARD_SUITE_V05_SPEC.md`](docs/HARD_SUITE_V05_SPEC.md). Its executable
walkthrough and clearly labeled product mockup are in
[`notebooks/01_uc_bench_v05_workflow.ipynb`](notebooks/01_uc_bench_v05_workflow.ipynb).
BixBench3's relevant artifact-DAG and process-analysis lessons, plus the
separately versioned v0.6 intermediate-artifact proposal, are recorded in
[`docs/BIXBENCH3_LESSONS.md`](docs/BIXBENCH3_LESSONS.md) and
[`docs/HARD_SUITE_V06_ARTIFACT_DAG_PROPOSAL.md`](docs/HARD_SUITE_V06_ARTIFACT_DAG_PROPOSAL.md).
The implemented v0.6 contract and provider gate are in
[`docs/HARD_SUITE_V06_SPEC.md`](docs/HARD_SUITE_V06_SPEC.md) and
[`docs/V06_CROSS_PROVIDER_PANEL.md`](docs/V06_CROSS_PROVIDER_PANEL.md).

The build is organized into ten auditable stage gates in
[`PROJECT_PLAN.md`](PROJECT_PLAN.md). Run `make status` for the live stage and
open findings. Material decisions and evidence are recorded under `audit/`.

## Local setup

```bash
./scripts/bootstrap_local.sh
source .venv/bin/activate
uc-bench doctor
python -m unittest discover -s tests -v
```

The local bootstrap installs the dependency-free core and development tools.
Use the full bootstrap to add the scientific stack, minimal notebook execution
support, and Verifiers v1; this workspace's `.venv` was created with the full
setup:

```bash
./scripts/bootstrap_full.sh
```

The layers can also be installed independently:

```bash
./.venv/bin/pip install '.[science]'
./.venv/bin/pip install '.[notebook]'
./.venv/bin/pip install '.[rl]'
```

No notebook UI is prescribed or installed by this project. Open `.ipynb` files
in Codex, VS Code, or any other compatible editor. Notebooks explain and
exercise the workflow; reusable environment, grading, and data logic belongs in
tested `.py` modules under `src/`.

`verifiers` is intentionally optional. The public contracts stay independent
of any one agent framework; the current adapter exposes only private and
irreversible transitions. Native file/Python/shell work must run in an isolated
coding harness as described in
[`docs/RUNTIME_INTEGRATION.md`](docs/RUNTIME_INTEGRATION.md).
The safe options for the separately developed specialist predictor are in
[`docs/ENGINEER_PREDICTOR_INTEGRATION.md`](docs/ENGINEER_PREDICTOR_INTEGRATION.md).

## Useful commands

```bash
uc-bench doctor              # validate package and public manifests
uc-bench demo                # run an in-memory commit/reveal episode
uc-bench validate-config     # validate all configuration invariants
make test
make check
make reference                # rebuild the real-data expert episode
make environment              # package start states and replay the boundary
make grade-reference          # expert/reward-hacking separation controls
make variants                 # symmetric states and difficulty ladders
make runtime-smoke            # deterministic tool/runtime wiring checks
PYTHONPATH=src ./.venv/bin/python scripts/build_v03_controls.py
PYTHONPATH=src ./.venv/bin/python scripts/analyze_v03.py
PYTHONPATH=src ./.venv/bin/python scripts/build_v04_controls.py
PYTHONPATH=src ./.venv/bin/python scripts/run_v04_calibration.py  # planning only
PYTHONPATH=src ./.venv/bin/python scripts/analyze_v04.py
make v05-controls             # rebuild zero-cost scientific and policy controls
make v05-reference            # write compact deterministic replay traces
make v05-demo                 # build one agent-visible start state, no reveal
make v05-report               # rebuild the honest pre-calibration report
make v05-freeze               # verify the one-time pre-exposure hashes
make v05-plan                 # print the frozen 18-episode plan; spends nothing
make v05-analyze              # rebuild the completed diagnostic no-go report
make v05-test                 # focused v0.5 unit and construct tests
PYTHONPATH=src ./.venv/bin/python scripts/build_v06_controls.py
PYTHONPATH=src ./.venv/bin/python scripts/build_v06_provider_plan.py  # read-only
PYTHONPATH=src ./.venv/bin/python scripts/run_v06_compatibility.py    # planning only
make v07-controls             # rebuild four packets, controls, replays, and cost gate
make v07-test                 # focused v0.7 environment and grader tests
make analyze                  # summarize real trajectories, or fail closed when absent
make report                   # honest pre-result or model-result dashboard
make pre-release-audit        # machine-readable go/no-go checks
make verify-v0                # rebuild and verify every completed v0 component
make status                   # show the ten-stage build and open audit findings
```

## Repository layout

```text
configs/             public cohort, task, reward, and variant contracts
audit/               live stage state, findings, and append-only build log
data/                data instructions; large datasets are ignored
grader_private/      private labels, variants, seeds, and tests (ignored)
notebooks/           product and workflow explainers
reports/             generated leaderboard and failure-analysis outputs
scripts/             reproducible local setup helpers
src/uc_bench/        framework-neutral environment core
tasks/               agent-visible task start states
tests/               deterministic unit tests
trajectories/        episode JSONL outputs (ignored)
```

## Safety and claims

This is a research benchmark, not a clinical decision system. Public literature
may be present in frontier-model pretraining, so the complete decision chain
has a matched data-withheld condition. Raw AUC on the 59-patient GSE92415
transfer set must not be used alone to rank models. Controlled positive and
failure variants are agent-behavior tests, not new biology claims.

# UC-Bench v0 project plan

## Objective

Build the smallest credible reinforcement-learning environment that measures
whether an agent can evaluate a biological machine-learning claim responsibly
when the evidence may be sufficient, insufficient, shifted, contaminated, or
irrecoverable.

The anti-TNF biopsy predictor is the test material, not the product. The
headline result is graceful scientific failure and recovery: detecting the
problem, containing it, preserving valid evidence, calibrating uncertainty,
and choosing the next defensible action.

The active v0.5 implementation is one persistent ten-milestone diligence
episode. Six controlled states perturb identity, labels, preprocessing,
transport, or evidence sufficiency within that same chain. v0.3 and v0.4 are
preserved no-go evidence, not templates that constrain the v0.5 structure.

## How progress is tracked

The project advances through ten sequential stage gates. A stage is complete
only when its gate is supported by linked evidence; work existing in the
repository is not by itself proof that the gate passed.

Statuses are `not_started`, `in_progress`, `blocked`, or `complete`. The live
machine-readable state is in `audit/status.json`, open findings are in
`audit/findings.json`, and material decisions and changes are appended to
`audit/BUILD_LOG.md`.

Run `make status` at any time for the current snapshot. Run `make audit-check`
to validate the tracking files.

## The ten stages

| Stage | Name | Purpose | Completion gate |
|---:|---|---|---|
| 1 | Product and benchmark contract | Freeze what is being evaluated and what would make the benchmark non-gimmicky. | Every headline score maps to observable agent behavior; raw predictive performance is explicitly secondary. |
| 2 | Data feasibility and provenance | Establish exactly which patient-level data, labels, timepoints, platforms, and annotations exist. | A reproducible baseline-only patient manifest passes count, provenance, endpoint, treatment-arm, and overlap checks. |
| 3 | Expert reference episode | Complete the entire diligence decision chain with a deliberately simple reference analysis. | An expert can finish from the start state, reproduce every artifact, and defend the terminal decision without hidden knowledge. |
| 4 | Environment and tool contract | Package the start state, tools, budgets, analyst interaction, and irreversible commit/reveal boundary. | A fresh run can use every documented tool; sealed outcomes remain inaccessible; post-commit mutations are detected. |
| 5 | Graders and graceful-failure reward | Grade evidence-backed detection, containment, diagnosis, recovery, calibration, and decision quality. | The grader ranks a strong expert trajectory above a deliberately mediocre one and cannot be passed by keyword-only caution. |
| 6 | Evidence states and difficulty ladders | Add authentic weak evidence, sufficient evidence, recoverable defects, and irrecoverable defects at graded strengths. | Always abstaining, always advancing, and leakage-driven success all lose; expected breaking curves are monotonic enough to interpret. |
| 7 | Agent integration and smoke pilot | Run the packaged environment through the selected agent/evaluation runtime. | Multiple agents complete valid episodes; remaining failures are task-relevant rather than installation or tool-interface failures. |
| 8 | Repeated evaluation and robustness | Measure seed sensitivity, contamination effects, task clustering, and model separation. | Results survive repeated runs, uncertainty is reported, and the ranking is not a floor, ceiling, or single-task artifact. |
| 9 | Leaderboard and failure atlas | Turn trajectories into an inspectable product showing where and how models break. | The report separates authentic biology from controlled variants and supports every claim with replayable trajectory evidence. |
| 10 | Release audit and go/no-go | Audit scientific claims, reproducibility, data rights, sealing, documentation, and reward hacking. | For this founder-built MVP, a documented multi-role self-audit records release or stop with all lack of external validation explicit. |

## Stage deliverables

### 1. Product and benchmark contract

- One-sentence evaluation objective and explicit non-goals.
- Definition of graceful failure and the allowed terminal decisions.
- Threat model covering gimmicks, reward hacking, contamination, universal
  abstention, infrastructure failure, and noisy biological performance.
- Headline and diagnostic score policy.

### 2. Data feasibility and provenance

- Download and checksum manifest for every source file.
- One row per patient and timepoint, with treatment, outcome, tissue, and
  platform fields.
- Direct verification of the intended GSE16879, GSE73661, and GSE92415 subsets.
- Patient-overlap and expression-identity audit.
- Probe-to-gene coverage report and endpoint concordance table.
- A go, modify, or replace-data decision.

### 3. Expert reference episode

- Leakage-safe, low-dimensional reference pipeline.
- Full artifact and trajectory replay.
- Cross-validation, permutation, stability, and sealed-transfer results with
  uncertainty.
- A reference `advance`, `stop`, or `insufficient_evidence` decision.
- A deliberately mediocre comparison trajectory.

### 4. Environment and tool contract

- Frozen agent-visible repository and private grader boundary.
- Tool schemas, budgets, error behavior, and `ask_analyst` answer bank.
- Commit hashes, file-order checks, one-time reveal, and post-reveal mutation
  enforcement.
- Offline-capable data and platform annotations.

### 5. Graders and graceful-failure reward

- Deterministic checks of actual files, sample usage, code, events, and hashes.
- Rubric for detection, containment, diagnosis, recovery, calibration, final
  decision, and reproducibility.
- Partial credit that prevents one mechanical error from zeroing the episode.
- Reward-hacking and paraphrase tests.

### 6. Evidence states and difficulty ladders

- Authentic weak-evidence state.
- Clean sufficient-evidence positive state.
- Recoverable data and analysis defects.
- Irrecoverable identity or endpoint defects.
- Graded confounding, noise, swaps, duplication, and feature loss.

### 7. Agent integration and smoke pilot

- Runtime adapter and reproducible run configuration.
- Three-model, three-attempt smoke matrix.
- Infrastructure-versus-scientific failure classification.
- Pilot issue log and one iteration of task/tool simplification.

### 8. Repeated evaluation and robustness

- Approximately ten trajectories per model per headline condition.
- Matched data-withheld contamination controls.
- Task/seed-clustered uncertainty and score-component analysis.
- Floor, ceiling, variance, and rank-stability report.

### 9. Leaderboard and failure atlas

- Overall score with component breakdowns.
- Decision-confusion table and contract-valid rate.
- Breaking-point curves for each controlled failure mode.
- Short, inspectable examples of reckless success, empty caution, competent
  recovery, and graceful failure.

### 10. Release audit and go/no-go

- Clean-machine reproduction.
- Private-label and artifact-sealing audit.
- Data licensing and provenance review.
- Scientific-claims and contamination review.
- Documented clinical, statistical, platform, curation, commercial, and
  benchmark-red-team self-review for the MVP.
- Explicit disclosure that no external expert endorsement was obtained.

## Stop and pivot conditions

Pause progression and record a blocking finding if any of these occur:

- A patient-level baseline cohort cannot be reconstructed unambiguously.
- Suspected cohort overlap cannot be resolved or safely represented.
- The expert reference episode cannot complete from the same information given
  to agents.
- Universal abstention or universal advancement performs well.
- Scores are dominated by setup failures, prose matching, or raw AUC noise.
- Repeated runs do not support a stable model difference.
- Authentic and controlled results cannot be clearly separated in reporting.

## Definition of v0 complete

UC-Bench v0 is complete only when all ten gates pass and the released report
shows at least one reproducible differential in graceful-failure behavior. A
working predictor, an attractive notebook, or a single mini-leaderboard is not
completion on its own.

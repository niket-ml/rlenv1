# UC-Bench build audit log

This is the append-only narrative audit trail. Update `status.json` for the
current snapshot and `findings.json` for actionable risks; append here whenever
a stage changes, a material design decision is made, evidence is produced, or a
finding is opened, closed, or accepted.

## Entry template

```text
### YYYY-MM-DD — Stage N — short title

- Change:
- Evidence:
- Decision:
- Findings opened/closed:
- Next action:
```

## Entries

### 2026-09-06 — Stage 1 — Graceful failure becomes the product objective

- Change: Reframed the environment from a predictor-building competition to a
  biological ML diligence environment centered on evidence-backed graceful
  failure and recovery.
- Evidence: `README.md`, `PROJECT_PLAN.md`, and the existing Task 7
  commit-before-reveal contract.
- Decision: The anti-TNF predictor remains test material. Raw predictive
  performance cannot be the headline model-ranking signal.
- Findings opened: AF-003 and AF-006.
- Next action: Freeze the graceful-failure rubric and revise the score taxonomy
  before declaring Stage 1 complete.

### 2026-09-06 — Stage 2 — Data readiness remains unproven

- Change: Recorded the distinction between public cohort descriptions and data
  that has actually been assembled and audited in the environment.
- Evidence: The repository currently contains cohort manifests but no GEO
  matrices or verified patient-level table.
- Decision: Do not freeze sample counts, train a reference model, or interpret
  predictive performance until the patient-level feasibility audit passes.
- Findings opened: AF-001 and AF-002.
- Next action: Begin Stage 2 only after the Stage 1 contract is frozen.

### 2026-09-06 — Stage 1 — Contract gate passed

- Change: Added the machine-readable benchmark contract, ten milestone weights,
  graceful-failure reward taxonomy, claims policy, and threat model.
- Evidence: `configs/benchmark.json`, `configs/reward_weights.json`,
  `configs/milestone_weights.json`, `docs/BENCHMARK_CONTRACT.md`, and
  `docs/THREAT_MODEL.md`; all configuration and project checks pass.
- Decision: Stage 1 is complete. The tool-using agent is the evaluation subject;
  raw AUC is not a headline metric; authentic and controlled results must remain
  separate.
- Findings closed: AF-006.
- Next action: Start the patient-level data feasibility and provenance audit.

### 2026-09-06 — Stage 2 — Data feasibility gate passed with constraints

- Change: Pinned and verified three GEO series matrices and three platform
  annotations; implemented deterministic patient/timepoint selection,
  GSE73661 longitudinal pairing, gene-symbol alignment, sealed-label
  separation, and cross-accession expression-identity checks.
- Evidence: `configs/data_sources.json`,
  `audit/evidence/stage_02_data_feasibility.json`, and
  `audit/evidence/stage_02_DATA_READINESS.md`; 24, 23, and 59 baseline patients
  and 17,151 common genes reproduce from source files.
- Decision: Proceed for a diligence benchmark, not for de novo high-dimensional
  biomarker discovery. Preserve cohort-held-out analysis and keep GSE92415 raw
  metadata out of the agent-visible workspace.
- Findings closed: AF-001 and AF-002.
- Next action: Build and replay a deliberately simple expert reference episode.

### 2026-09-06 — Stage 3 — Expert reference gate passed

- Change: Implemented and replayed a fixed five-gene, within-sample-rank
  reference model with an untouched replication cohort, prespecified transport
  penalty, artifact commitment, one-time sealed reveal, and actionable final
  submission. Added a mediocre comparison using the same predictor result but
  unsafe calibration and decision logic.
- Evidence: `artifacts/reference/episode.json`,
  `artifacts/reference/mediocre_episode.json`, and
  `audit/evidence/stage_03_REFERENCE_EPISODE.md`.
- Decision: The authentic result is AUC 0.667 (95% bootstrap interval
  0.513–0.814; permutation p=0.0147) and correctly terminates as
  `insufficient_evidence`. A nominal signal does not override the frozen
  advancement threshold or transfer limitations.
- Findings closed: AF-004.
- Next action: Package the exact agent-visible start state and executable tool
  boundary without exposing raw sealed metadata or outcomes.

### 2026-09-06 — Stage 4 — Private evaluator boundary passed

- Change: Replaced the placeholder Task 7 surface with one end-to-end task,
  constrained model and artifact schemas, reproducible full-data and
  data-withheld start states, fixed analyst interactions, and a filesystem-
  backed private evaluator.
- Evidence: `audit/evidence/stage_04_ENVIRONMENT_BOUNDARY.md`,
  `artifacts/reference/environment_episode.json`, and 41 passing unit tests.
- Decision: Sealed features and outcomes never enter the agent workspace. The
  grader accepts only inspectable JSON linear-rank models, validates provenance,
  and checks committed hashes before touching private validation data.
- Findings opened/closed: none.
- Next action: Implement deterministic evidence-backed graders and verify that
  they rank the expert reference above the deliberately mediocre trajectory.

### 2026-09-06 — Stage 5 — Evidence-backed grader gate passed

- Change: Implemented five-component deterministic scoring over artifacts,
  events, hashes, calibration, stable diagnostics, decisions, and typed next
  actions. Explanatory prose is not scored.
- Evidence: `artifacts/grading/reference_separation.json` and
  `audit/evidence/stage_05_GRADER_VALIDATION.md`.
- Decision: Expert 100, deliberately mediocre 40, keyword-only caution 40, and
  hard-invalid sealed access 0. The expert and mediocre attempts use the same
  predictor and validation result, isolating scientific process quality.
- Findings opened/closed: none.
- Next action: Add symmetric evidence states, especially a sufficient-evidence
  state that makes universal abstention a losing policy.

### 2026-09-06 — Stage 6 — Symmetric evidence-state gate passed

- Change: Added authentic weak, controlled sufficient, recoverable, and
  irrecoverable state families plus five graded private transformation ladders.
- Evidence: `artifacts/variants/scenario_controls.json` and
  `audit/evidence/stage_06_EVIDENCE_STATES.md`.
- Decision: Always-insufficient scores 15, always-advance and AUC-chasing score
  35, and always-stop scores 15 against a pass threshold of 60. The synthetic
  sufficient state is a decision-policy positive control and never a biology
  claim.
- Findings closed: AF-003.
- Next action: Integrate the framework-neutral core with the installed agent
  runtime and run infrastructure-classified smoke episodes.

### 2026-09-06 — Stage 7 — Runtime fixture smoke passed; model smoke pending

- Change: Added an installed-Verifiers domain-tool adapter, a frozen
  three-model/three-attempt smoke configuration, and three fresh-state fixture
  runs classified as valid, scientific failure, or integrity failure.
- Evidence: `artifacts/runtime/infrastructure_smoke.json` and
  `docs/RUNTIME_INTEGRATION.md`; four tool schemas load under Verifiers 0.3.1,
  both valid fixtures reach submission, mutation is rejected, and there are no
  fixture infrastructure failures.
- Decision: Keep native file/Python/shell work in an isolated coding harness and
  expose only the four private state transitions as custom tools. Do not treat
  the deterministic fixtures as model or leaderboard results.
- Findings opened: AF-007 because model names, provider credentials, and an
  isolated coding runtime are not configured.
- Next action: Run the nine real-model smoke trajectories after those external
  runtime inputs are available.

### 2026-09-06 — Stages 8–10 — Analysis and release tooling prepared, gates remain closed

- Change: Froze the repeated-evaluation matrix, implemented clustered
  uncertainty and matched withheld-condition analysis, built an honest
  pre-result report shell, and added a fail-closed automated release audit.
- Evidence: `configs/evaluation_protocol.json`, `src/uc_bench/evaluation.py`,
  `reports/REPORT_SPEC.md`, `src/uc_bench/reporting.py`, and
  `audit/PRE_RELEASE_AUDIT.md`.
- Decision: Do not fabricate a leaderboard from fixtures. The current report
  says `PRE-RESULT — NO MODEL RANKING`; the automated audit is `no_go` with
  seven of ten checks passing.
- Findings opened/closed: none; AF-005 and AF-007 remain open.
- Next action: Configure a real isolated coding-agent runtime, run the
  nine-trajectory smoke, then execute the prespecified 60-trajectory headline
  evaluation before independent release review.

### 2026-09-06 — Stage 5 — Structured evidence is independently recomputed

- Change: Hardened provenance so the sealed predictor remains identical to the
  discovery-frozen predictor evaluated on GSE73661. Added private recomputation
  of cohort counts, model AUCs, bootstrap intervals, permutation p-values,
  common-gene coverage, and sample roles from the committed model and visible
  workspace files.
- Evidence: `src/uc_bench/evidence_verification.py` and the structured-forgery
  control in `artifacts/grading/reference_separation.json`.
- Decision: Agent-authored `status: pass` fields never establish truth. A false
  pass contradicted by recomputation is contract-invalid and capped at 40.
- Findings opened/closed: none; the issue was caught and resolved before a real
  model run.
- Next action: Preserve the recomputation boundary when implementing private
  scenario-specific graders.

### 2026-09-06 — Stage 7 — Local isolated real-model runner implemented

- Change: Added a Verifiers-compatible OpenRouter runner backed by one locked-
  down local Docker container per episode, secure `.env` loading, explicit
  turn/token/time budgets, redacted trajectory persistence, host-side cost
  accounting, and a dry-run-safe smoke command.
- Evidence: `src/uc_bench/docker_runtime.py`,
  `src/uc_bench/model_runner.py`, `docker/agent.Dockerfile`,
  `scripts/run_docker_preflight.py`, and 75 passing tests.
- Decision: The agent receives no network, credentials, private grader mount,
  or sealed cohort. Only the generated start state is writable.
- Findings opened/closed: AF-007 remains open pending valid real episodes.
- Next action: Run one zero-cost real tool-loop canary before any paid model.

### 2026-09-06 — Stage 7 — Real free canary is informative but does not pass

- Change: Attempted two Google free endpoints and one cross-provider MiniMax
  endpoint, preserving redacted run summaries and separating provider failures
  from agent task failure.
- Evidence: `artifacts/runtime/canary_attempts.json` and
  `audit/evidence/stage_07_REAL_MODEL_CANARY.md`.
- Decision: Both Google attempts are infrastructure failures at turn zero due
  to shared-pool 429s. MiniMax entered the real environment, made 17 model
  turns and 30 tool calls, but exhausted 16,000 completion tokens while
  repeatedly rewriting analysis code and never committed. This is neither a
  valid episode nor graceful failure, and it is not leaderboard evidence.
- Findings opened/closed: AF-007 remains open and is narrowed to a valid paid
  canary plus the guarded nine-run smoke.
- Next action: Add a $10 paid balance, reduce the key limit to $10, and run the
  pinned low-cost Luna canary before the three-model smoke.

### 2026-09-06 — Stage 7 — Paid integration and smoke gate passed

- Change: Completed a clean nine-attempt end-to-end smoke with Docker-isolated
  agents, host-only OpenRouter credentials, explicit terminal classifications,
  and reliability-inclusive scoring. A usable attempt that fails to submit now
  scores zero; provider failures alone are excluded.
- Evidence: `artifacts/runtime/smoke_pilot_v2_runs.json`,
  `src/uc_bench/model_runner.py`, and `tests/test_model_runner.py`.
- Decision: Stage 7 is complete. GPT-5.6 Sol produced three valid high-scoring
  episodes; Claude produced three task failures; Gemini produced two valid
  episodes and one contract-capped submission. This smoke is integration
  evidence, not a ranking.
- Findings closed: AF-007.
- Next action: Build the task-level diagnostic suite before spending on a
  repeated headline matrix.

### 2026-09-06 — Stage 8 — Short packet calibration fails its ceiling gate

- Change: Froze and ran 24 short decision-packet trajectories across a
  same-provider temporal ladder. Removed hidden confidence-band scoring,
  evidence-set precision penalties, and an overlapping action taxonomy before
  regrading under public policy v0.2.
- Evidence: `configs/packet_calibration.json`,
  `artifacts/diagnostics/packet_calibration_runs.json`,
  `artifacts/diagnostics/packet_calibration_analysis.json`, and
  `reports/generated/packet_calibration.md`.
- Decision: Do not promote the packet-only suite. Means were 100.0, 95.0,
  95.0, and 37.56; the frontier models were at ceiling and the middle tiers
  tied. The remaining feature-dropout errors localize diagnosis and next-action
  weakness, but do not support a ranking claim.
- Findings opened: AF-008.
- Next action: Make T03–T06 executable data-analysis tasks and require local
  reference, naive-policy, and expert-separation controls before another paid
  calibration.

### 2026-09-06 — Stage 8 — Executable data diagnostics calibrated

- Change: Implemented 20 deterministic variants across patient identity,
  platform alignment, batch confounding, sample size, and label noise. Private
  graders recompute numerical truth from agent-visible CSVs. Sample-size and
  label-noise ladders vary one factor at a time, and latent flips never require
  exact sample identification.
- Evidence: `configs/data_diagnostics.json`,
  `artifacts/diagnostics/data_task_controls.json`,
  `artifacts/diagnostics/data_task_calibration_runs.json`,
  `artifacts/diagnostics/data_task_calibration_analysis.json`, and
  `reports/generated/data_task_calibration.md`.
- Decision: Local controls pass: reference minimum 100; universal no-analysis
  policies average 25.15–31.75; the expert beats the weak control on each task's
  challenge case. Paid means were 100.0, 100.0, 87.5, and 37.5. The slice fails
  its ceiling gate and measures mainly completion/schema reliability: every
  valid submission scored 100.
- Findings opened: AF-009; AF-008 remains open.
- Next action: Preserve the zero for unsubmitted attempts, but use post-hoc
  artifacts to distinguish analysis errors from interface-completion failures.

### 2026-09-06 — Stage 8 — Combined calibration shows a directional gradient only

- Change: Combined the two independently frozen slices by their 14 cells per
  model, without modifying either raw artifact.
- Evidence: `artifacts/diagnostics/combined_calibration_analysis.json` and
  `reports/generated/combined_calibration.md`.
- Decision: Combined calibration means are 100.0, 97.86, 90.71, and 37.52 in
  strict temporal order. This is the desired directional signal, but it remains
  calibration-only because there is one attempt per cell, no held-out levels,
  and substantial ceiling. No causal claim about pretraining undersampling or
  need for expert SFT/RLHF is allowed.
- Findings opened/closed: AF-005, AF-008, and AF-009 remain open.
- Next action: Run paired expert-playbook and withheld-data interventions, then
  repeat only held-out discriminating cells with clustered uncertainty.

### 2026-09-07 — Stage 8 — Ceiling correction and causal hard suite v0.3

- Change: Preserved the packet/data ceiling failures, the heterogeneous
  playbook result, and the v0.2 20-turn floor as explicit no-go evidence. Built
  v0.3 around five irreversible resource-selection pairs spanning additional
  data, metadata/labels, expert assistance, and process/tooling.
- Evidence: `configs/hard_suite_v03.json`,
  `grader_private/hard_suite_v03_heldout.json`,
  `src/uc_bench/hard_suite_v03.py`,
  `src/uc_bench/hard_suite_v03_runner.py`,
  `artifacts/diagnostics/hard_suite_v03_controls.json`,
  `docs/HARD_SUITE_V03_SPEC.md`, and
  `audit/evidence/stage_08_HARD_SUITE_V03.md`.
- Decision: The local gates pass, but the suite is controlled rather than an
  authentic cohort result. Sol's frozen ten-cell development slice scored
  83.2619 with no ceilings or zeros. This is difficulty calibration only, not
  a ranking.
- Infrastructure amendment: A GPT-5.4 attempt was excluded after OpenRouter's
  20-request/minute new-account limit returned 429. Resume adds 3.25-second
  request pacing only; frozen tasks, graders, prompts, models, seeds, budgets,
  config digest, and held-out hashes are unchanged.
- Findings opened/closed: AF-008 remains open pending the complete three-model
  matrix; AF-009 is superseded by resource-specific intervention claims and no
  longer treats SFT/RLHF as the default explanation.
- Next action: Finish the checkpointed frozen development matrix, generate the
  failure/intervention report, and run no Astra canary unless every mandatory
  local and development gate passes.

### 2026-09-07 — Stage 8 — v0.3 paused; quantitative ceiling failure preserved

- Change: Interrupted v0.3 during an inter-task cooldown, preserved its raw
  checkpoint byte-for-byte, and prohibited resume or Astra.
- Evidence: `artifacts/diagnostics/hard_suite_v03_pause.json`,
  `artifacts/diagnostics/hard_suite_v03_analysis.json`, and
  `audit/evidence/stage_08_HARD_SUITE_V03.md`.
- Decision: 16/30 usable cells are diagnostic but incomplete. Sol mean 83.2619
  masks a quantitative component mean of 98.4; v0.3 is therefore
  quantitatively insufficient rather than a successful benchmark.
- Spend: observed OpenRouter increment $2.57690740; 17 attempt records include
  one excluded 429; key usage at pause $25.25898437 of a $60 limit.
- Findings: AF-012 closed as intentionally superseded; AF-013 opened for v0.4
  acceptance.
- Next action: Build and locally gate v0.4 before any further paid request.

### 2026-09-07 — Stage 8 — v0.4 local validity gates passed

- Change: Built five paired biomedical-statistical families with independently
  recomputed estimands, uncertainty, scientific interpretation, irreversible
  resource selection, and deterministic breaking-point ladders.
- Evidence: `configs/hard_suite_v04.json`,
  `grader_private/hard_suite_v04_heldout.json`,
  `src/uc_bench/hard_suite_v04.py`,
  `artifacts/diagnostics/hard_suite_v04_controls.json`,
  `artifacts/diagnostics/hard_suite_v04_ladders.json`, and
  `audit/evidence/stage_08_HARD_SUITE_V04.md`.
- Decision: All 11 local gates pass with zero model calls. Reference minimum is
  100 and the mechanical baseline mean is 35.9451. All paired interventions and
  ladders cross a decision boundary; schemas and horizon are not the source of
  difficulty.
- Design amendments before exposure: corrected transport and process ladders,
  added achieved-precision gating to Q05, changed unexposed held-out Q05 seed
  from 80507 to 80503, and identified Q04 adjudication as expert assistance.
- Next action: freeze file hashes, run repository-wide gates, then and only then
  start the bounded 30-cell development calibration under a $30 incremental cap.

### 2026-09-07 — Stage 8 — v0.4 frozen before model exposure

- Change: Passed repository-wide checks and created a one-time immutable
  pre-exposure manifest covering 14 semantic, private, runtime, and cost-control
  files.
- Evidence: `artifacts/diagnostics/hard_suite_v04_freeze.json`,
  `src/uc_bench/v04_freeze.py`, and `scripts/freeze_v04.py`.
- Verification: project doctor and audit checks pass; 108 unittest cases and the
  full pytest suite pass; Ruff passes; freeze hashes immediately re-verify.
- Decision: v0.4 now permits only the frozen Sol/GPT-5.4/GPT-5.2 development
  matrix under a $30 incremental cap. Semantic edits require an explicit new
  version, not re-freezing or tuning this suite.
- Next action: execute and checkpoint the frozen 30 cells; do not run Astra.

### 2026-09-07 — Stage 8 — pre-exposure cost-guard freeze amendment

- Change: The final account-status preflight caught `remaining_usd` where the
  status type exposes `limit_remaining_usd`; repaired that fail-closed guard.
- Evidence: `artifacts/diagnostics/hard_suite_v04_freeze_amendment_01.json`.
- Integrity: The parent freeze remains unchanged and is linked by SHA-256. The
  amendment occurred with zero v0.4 model requests and zero Astra exposures.
  Only the cost-field reference and the runner's active manifest path changed.
- Decision: Treat the amendment as harness-only. Any task, evidence, grader,
  prompt, model, seed, or budget change still requires a new suite version.
- Next action: execute the amended hash-frozen matrix under the same $30 cap.

### 2026-09-07 — Stage 8 — v0.4 matrix complete; mandatory no-go

- Change: Completed the amended hash-frozen 30-cell Sol/GPT-5.4/GPT-5.2
  development matrix. Retained and excluded one transient DNS/API failure, then
  resumed without changing the suite.
- Evidence: `artifacts/diagnostics/hard_suite_v04_calibration_runs.json`,
  `artifacts/diagnostics/hard_suite_v04_analysis.json`, and
  `reports/generated/hard_suite_v04_report.md`.
- Results: means 80.50, 77.65, and 70.35; ceiling rates 10%, 0%, 0%; no zeros;
  every usable cell was a valid submission; schema-primary failure rate zero.
- Spend: observed $5.67833585 from key usage; conservative token-price estimate
  $10.90121575; cap $30; Astra calls zero.
- Decision: NO-GO. Q03 explains 43.6% of the Sol-to-GPT-5.2 gap, failing the
  30% family-concentration gate. Sol quantitative reasoning remains near ceiling
  at 99.59 and its overall 80.50 narrowly misses the ideal band.
- Findings: AF-013 closed by completed calibration and enforced no-go; AF-014
  opened for distributed quantitative difficulty in a separately frozen
  successor. AF-005 remains open because one seed cannot establish rank.
- Next action: Do not run Astra or tune v0.4. Design any successor as v0.5,
  freeze it before exposure, and require repeated seeds before a ranking claim.

### 2026-09-07 — Stage 8/9 — v0.5 stateful workflow built and locally gated

- Structural pivot: Preserved v0.4 artifacts and its no-go, but replaced the
  disconnected pair structure with one ten-milestone anti-TNF predictor-
  diligence episode. Earlier evidence changes claim admissibility without
  mechanically zeroing later containment, recovery, or abstention.
- Agent surface: Added ordinary intended-use, cohort, patient/visit, endpoint,
  platform, preprocessing, locked-model, reproduction, and resource artifacts;
  an irreversible validation commitment; sealed outcome reveal; locked resource
  selection; one follow-up reveal; and final diligence submission.
- Controlled states: Added clean progression, identity dependence, endpoint
  ambiguity, preprocessing leakage, joint endpoint/drug/platform transfer, and
  irreducible external-evidence cases plus separately seeded held-out instances
  and breaking-point ladders.
- Grading: Added ten milestone scores, a ten-capability vector, private numeric
  recomputation, evidence-path support, graded resource utility, belief
  revision, intervention effects, and diagnostic credit for incomplete episodes
  while retaining a zero reliability score for usable unsubmitted attempts.
- Local evidence: All zero-cost controls pass. Reference and alternative expert
  workflows score 100; deliberately mediocre attempts are lower at every
  milestone; universal policy means are 39.25–41.37; committed mutation and
  pre-reveal leakage tests pass.
- Product output: Added an executed notebook with schematics and explicitly
  illustrative output mockups, an honest pre-calibration report, a model-analysis
  pipeline, and compact deterministic reference replay traces.
- Spend: $0 on v0.5 model calls; Astra requests 0.
- Limitation: This MVP uses documented internal multi-role review rather than
  external expert endorsement. The controlled v0.5 states remain separate from
  the preserved authentic GEO anchor.
- Decision: Local construction gate passes. Model difficulty and ranking remain
  unproven; paid development, held-out evaluation, and Astra are still blocked
  until the one-time freeze and explicit execution approval.

### 2026-09-07 — Stage 8 — v0.5 frozen and runtime-preflight clean

- Freeze: Created `artifacts/diagnostics/hard_suite_v05_freeze.json` covering 17
  task, private-state, ladder, control, grader, runner, cost, and audit files.
  Immediate verification reports matching hashes, zero v0.5 requests before
  freeze, and zero Astra exposures.
- Verification: Ruff passes; 147 repository tests pass; the v0.5 notebook
  executes; the audit tracker passes; and the Docker preflight confirms no
  network, no credentials, a read-only root filesystem, all capabilities
  dropped, and `/workspace` as the only bind mount.
- Calibration plan: 6 development states × 3 models × 1 seed = 18 episodes,
  exact incremental cap $20, no held-out execution, no Astra, and no ranking
  claim. The command remains planning-only without explicit `--execute` and the
  exact cap argument.
- Decision: The build is ready for a bounded development ceiling/floor test.
  Paid evaluation was not launched in this build turn.

### 2026-09-07 — Stage 8 — v0.5 pilot launched; BixBench3 analysis lessons applied

- Execution: Launched the exact frozen 6-state × 3-model × 1-seed development
  matrix under the predeclared $20 incremental cap. Held-out cases and Astra are
  excluded. The runner checkpoints after each episode and resumes only after
  verifying the configuration digest and all frozen hashes.
- Scope: External expert validation is not a pre-MVP calibration blocker. Its
  absence remains a disclosed limitation before strong public or commercial
  validity claims.
- BixBench3 review: Preserved its useful artifact-DAG, depth, replay, process-
  annotation, and cost-efficiency lessons while rejecting paper-reproduction
  matching, large scale for its own sake, and one mandated method as UC-Bench
  constructs.
- Analysis-only additions: Added `scripts/analyze_v05_extended.py`,
  `docs/BIXBENCH3_LESSONS.md`, and
  `docs/HARD_SUITE_V06_ARTIFACT_DAG_PROPOSAL.md`. No frozen task, grader,
  prompt, threshold, private state, or held-out artifact changed.
- Construct audit: Found that two completed Sol cells used scientifically clear
  phrases that small frozen token matchers may miss (fingerprint-group
  uncertainty and a frozen DISCOVERY-only transform). The scores remain frozen
  and unmodified. Any such occurrence is now disclosed against the suite's
  predeclared `exact_method_name_matching` non-construct and can force a no-go.
- Verification: The original 17 frozen hashes still match. The analysis-only
  regression suite passes. At the last checkpoint the pilot was incomplete, so
  no acceptance decision or model ranking was issued.

### 2026-09-07 — Stage 8/9 — v0.5 matrix complete; BixBench3-informed no-go

- Execution: Completed the exact frozen 18-cell development matrix: six
  controlled states by GPT-5.6 Sol, GPT-5.4, and GPT-5.2, one seed. All 18
  provider requests returned usable episodes; 17 reached a final submission and
  one GPT-5.2 episode reached the frozen 55-turn limit after selecting and
  revealing a follow-up but before final submission. Per protocol, that usable
  attempt scores zero rather than being excluded.
- Spend: Observed incremental OpenRouter usage was $7.53252860 against the $20
  cap. Infrastructure failures, timeouts, held-out requests, and Astra requests
  were all zero. The runner exited after the matrix; no further paid evaluation
  was launched.
- Controlled scores: Sol 76.7742, GPT-5.4 75.0751, GPT-5.2 60.0447. These are
  one-seed development diagnostics, not a stable ranking. Ceiling rates were
  zero; zero rates were 0%, 0%, and 16.7%, respectively.
- Gate result: **NO-GO**. The underpowered/irreducible state explains 67.25% of
  the strongest-to-weakest absolute gap, failing the frozen 30% family cap.
  Two Sol cells also used valid fingerprint-group and discovery-frozen language
  missed by small frozen vocabulary matchers, failing the declared
  no-grader-vocabulary-trick construct requirement. Scores were not repaired or
  retrospectively changed.
- Diagnostics: Added artifact depth, first substantive divergence, downstream
  dependency risk, scientific/process/infrastructure separation, evidence-cited
  process tags, tokens, turns, wall time, retries, replay paths, intervention
  effects, and score-cost analysis. Deterministic frozen scoring remains the
  headline source; no LLM process judge altered rank.
- BixBench3 boundary: Borrowed artifact-DAG and replay/accounting practices, not
  its study scale or single-paper reproduction objective. v0.6 is recorded as a
  separately versioned semantic-artifact successor and has not been implemented
  or exposed.
- Verification: All 17 frozen hashes still match; Astra exposure count remains
  zero; Ruff passes; all 153 repository tests pass; and the audit tracker passes.
- Findings: AF-008 closed because v0.5 resolved the earlier ceiling/floor
  concern. AF-015 and AF-016 opened for vocabulary-dependent scientific scoring
  and single-family gap concentration. AF-005, AF-011, and AF-014 remain open.
- Next action: Do not run Astra, held-out variants, or repeated seeds. Design and
  locally validate v0.6's ten semantic intermediate artifacts and paraphrase/
  alternative-workflow controls before authorizing any new model exposure.

### 2026-09-07 — Stage 8 — v0.6 semantic workflow built; provider panel unfrozen

- Preservation: Verified all 17 frozen v0.5 hashes still match. No v0.5 task,
  grader, prompt, threshold, state, or result was changed.
- Structural successor: Implemented ten explicit artifacts from cohort inventory
  through final diligence, new development and held-out seeds, independent
  invariant scores, artifact coverage, completed-work quality, dependency depth,
  first substantive divergence, downstream risk, and a ten-capability vector.
- Scientific controls: Reference and alternate-method minima are 100;
  professional paraphrasing changes the score by zero; a deliberately mediocre
  workflow is below reference in every artifact family; universal policy means
  are at most 41.95; a single ordinary error retains 98.75; committed tampering
  is rejected. All local gates pass.
- Provider correction: Replaced the proposed GPT-only v0.6 panel with Sol,
  Claude Opus 5, pinned Gemini 3.1 Pro Preview, Kimi K3, and GPT-5.2. The first
  four form the cross-family comparison; Sol and GPT-5.2 form the temporal
  anchor. Provider fallbacks are disabled.
- Read-only readiness: Authenticated catalog checks found every exact model and
  expected canonical slug, with tools, tool choice, structured output, and
  reasoning-effort interfaces. These checks made no inference request.
- Compatibility design: Added a three-request non-scored canary for tool calls,
  tool-result ingestion, visible-state preservation, explicit compaction,
  structured output, token limits, finish behavior, routing identity, usage,
  caching, refusals, and infrastructure classification. Adapter failures cannot
  become scientific failures.
- Cost: v0.6 model calls 0; incremental model spend $0. Current remaining funds
  and key limit are $41.42350933. Compatibility is capped at $3. The 30-episode
  panel proxy is $74.42 median and $111.33 P90; P90 plus contingency would need
  approximately $92.17 additional funds and key limit.
- Verification: All 163 repository tests pass, Ruff passes, the ten-stage audit
  tracker validates, all six held-out packages build with labels sealed, and the
  v0.5 freeze re-verifies.
- Decision: Do not freeze the model panel or run scientific episodes yet. The
  requested pre-spend report is complete; explicit approval is now required for
  the bounded compatibility stage. Do not run Astra.

### 2026-09-07 — Stage 8 — v0.6 cross-provider compatibility passes

- Authorization and boundary: Ran only the explicitly authorized, non-scored
  compatibility stage under the exact $3 cap. Scientific episodes, held-out
  tasks, and Astra requests remained zero.
- Result: All five exact models passed on pinned native providers: Sol/OpenAI,
  Claude Opus 5/Anthropic, Gemini 3.1 Pro Preview/Google AI Studio, Kimi
  K3/Moonshot AI, and GPT-5.2/OpenAI.
- Adapter findings: Kimi returned HTTP 400 when specified tool choice was used
  with thinking; automatic tool choice passed. Claude's native policy filter
  rejected explicit SDK-conformance/exact-output wording as suspected reverse
  engineering. A semantically equivalent ordinary project-status workflow
  passed all three turns. Claude's compatibility ceiling was also raised to
  2,048 tokens to remain valid above Anthropic's reasoning-budget minimum.
- Preservation: Four compatibility result generations and every failed model
  attempt are retained. The failed states were classified as provider adapter
  or refusal outcomes and never as scientific failures.
- Spend: The conservative cumulative response-reported total was $0.04574225.
  OpenRouter's eventually consistent key counter had posted $0.03468225 at the
  final check, leaving $41.38882708 on the $80 key limit at that instant.
- Verification: Targeted compatibility and v0.6 tests pass; the repository test
  suite passes. The existing notebook-only Ruff findings are unrelated to this
  change; source, scripts, and tests pass the configured lint target. v0.5
  remains frozen and Astra exposure remains zero.
- Decision: Compatibility passes, but the panel remains unfrozen and scientific
  execution is not authorized. Next carry the adapters into the scientific
  runner, recalculate cost, request a new cap, then freeze before exposure.

### 2026-09-08 — Stage 8 — v0.6 final pre-exposure gate passes

- Adapter integration: Added provider-aware scientific execution for the five
  exact panel models. Native provider `order` and `only`, fallback prohibition,
  required-parameter checks, price ceilings, returned-model/provider checks,
  reasoning-state round-trip, and request-level ledgers now apply to the real
  runner rather than only the canaries.
- Failure accounting: Explicit provider-policy and verified infrastructure
  failures remain separate. Model response refusals and usable non-submissions
  receive zero reliability while preserving partial-artifact diagnostics.
- Fairness: Predeclared 65 turns, 5,000 completion tokens per request, 90,000
  total completion tokens, 4,200 seconds, full visible transcript, no silent
  compaction, medium requested reasoning, zero SDK retries, and one verified
  infrastructure retry. Provider syntax differs only where compatibility
  demonstrated it must.
- Safety: Added per-request cost checkpointing, per-episode checkpointing,
  exact resume hashes, runtime-version checks, price/route mismatch stops, and
  hard rejection of held-out partitions and Astra/GPT-6. The freeze preview
  records `frozen_before_scientific_model_calls: false`; no actual freeze was
  written.
- Cost: Read-only route/account refresh made zero inference calls. Full matrix
  projection is $92.55 median and $138.36 P90, with a $167 cap. The balanced
  sentinel is $30.85 median and $46.12 P90, with a $56 cap. Current remaining
  account/key allowance is $41.37776708; upward-rounded increases are $14.63
  for the sentinel or $125.63 for the full cap. Compatibility spend remains
  separately reported at $0.04574225.
- Staging decision: Recommend freezing the complete 30-cell configuration, then
  running every model on clean progression and preprocessing leakage as a
  ten-cell sentinel. It cannot support ranking, task changes, or grader changes.
  Predeclared route, adapter, universal-ceiling, universal-floor, usability, and
  hash rules determine continuation.
- Verification: All 189 repository tests pass; Ruff, project doctor, audit
  consistency, `git diff --check`, and v0.5's 17-hash freeze check pass. A freeze
  preview initially failed closed on an incorrect local-control field name; the
  contract reader was corrected and the successful preview was regenerated.
- Decision: Engineering and cost gates pass. Do not freeze or execute until the
  user funds the selected cap and explicitly authorizes the one-time freeze and
  scientific sentinel. Do not run held-out states or Astra.

### 2026-09-08 — Stage 8 — v0.6-v0.6.3 execution repairs and complete sentinel

- Preservation: Frozen v0.6 was not patched or resumed after its turn-zero
  adapter failure. Separately versioned v0.6.1-v0.6.3 repaired credential
  initialization, exact payload parity, failure classification, total grading,
  and checkpoint-safe post-processing without changing the v0.6 scientific
  tasks, prompts, thresholds, states, or scoring invariants.
- Execution: The exact v0.6.3 ten-cell development sentinel completed across
  Sol, Claude Opus 5, Gemini 3.1 Pro Preview, Kimi K3, and GPT-5.2 on clean and
  preprocessing-leakage cases. Nine cells submitted. Gemini clean produced all
  ten artifacts but exhausted 65 turns without submission and retained zero
  reliability per protocol.
- Spend: v0.6.3 response-reported spend was $16.57573185; aggregate with the
  preserved v0.6.2 attempt was $17.00438525. Held-out and Astra requests were
  zero. Execution stopped after ten cells; the remaining twenty development
  cells were not launched.
- Result: Mandatory no-go. Sol averaged 82.80 and GPT-5.2 84.44, both beyond
  the >80 ceiling threshold. Decision/recovery contributed 32.13% of the
  strongest accepted-model loss, above the 30% family gate, and every-cell
  validity failed because of the Gemini non-submission.
- Findings: AF-018 closed by the separately versioned infrastructure repairs;
  AF-019 opened for the frozen v0.6.3 ceiling and construct failure.

### 2026-09-08 — Stage 8/9 — v0.6.3 construct audit and unfrozen v0.7 successor

- Audit: Reproduced all 100 frozen model × scenario × artifact scores down to
  atomic invariant deductions without modifying or rescoring v0.6.3. Each
  deduction is classified as consequential scientific error, defensible
  professional policy, grader/schema artifact, harmless incompleteness, or
  genuinely unresolvable uncertainty, with artifact and grader pointers.
- Construct finding: A01-A06 averaged 85.25 while A09-A10 averaged 65.87.
  A06 scored 100 in every cell. Frozen universal policies retained 92-95
  artifact-science points while failing decision-policy quality. Hard-coded
  discovery counts, bare label tokens, flat metric paths, exact effect enums,
  and a unique clean-state no-resource target penalized valid expert caution or
  representation.
- Successor: Implemented unfrozen v0.7 with ten independently scored artifacts,
  an eight-depth dependency DAG, low procedural weight, independent numerical
  checks, competing explanations, opaque overlapping resource choices,
  Pareto-set alternatives, symmetric decisions, second blockers, and
  stage-local recovery.
- Zero-cost gates: Reference and alternative workflows score 100; paraphrase
  difference is zero; shallow and keyword controls score at most 10.25 and
  8.58; universal policies average at most 6.61; a wrong upstream dependence
  analysis leaves 92 points of valid downstream work. All local gates pass with
  zero model calls.
- Cost: A proposed 20-cell cross-provider v0.7 development sentinel is $36.47
  median, $45.26 P90, and $56.58 hard cap, with 2.0-3.5 hours expected serial
  runtime. Read-only account and key headroom are $74.34471128, so the sentinel
  would require no top-up or limit increase. It is not authorized.
- Decision: v0.7 remains unfrozen and cannot make paid calls because no runner
  or freeze exists. Present the audit, controls, risks, and exact cap before any
  execution approval. Do not run held-out states or Astra.
- Findings: AF-019 and AF-020 remain open. External specialist validation is a
  disclosed requirement before strong public or commercial validity claims.

### 2026-09-08 — Stage 8 — v0.7 design reset and four-case vertical slice

- Reset: Replaced the unfrozen, unexposed ten-artifact v0.7 proposal rather
  than patching its score. Frozen v0.6.3, its scores, audit, traces, and no-go
  remain unchanged. The proposed 20-cell panel was cancelled before exposure.
- Environment: Built four compact development packets from row-level cohort,
  patient/biopsy/visit, endpoint-source, prediction, feature, site/batch/
  platform, preprocessing, membership, execution-log, manifest, assertion, and
  resource-catalog evidence. Planted diagnoses and preferred actions exist only
  in private grader state.
- State transitions: Added inspect, five checkpoint, irreversible pre-reveal
  commitment, sealed-outcome reveal, one budgeted resource action, belief
  update, and terminal submission semantics. Start-state tampering, hidden-data
  access, and post-reveal commitment changes fail closed with complete traces.
- Scientific design: Case 1 separates material from harmless imperfections;
  Case 2 requires patient- and site-aware calculation; Case 3 pairs identical
  starting evidence with collapse and survive clean-replay returns; Case 4
  separates discrimination from calibration and threshold utility.
- Grading: Replaced ten equal files with five consequence-weighted checkpoints:
  evidence/unit 15, locked plan 20, quantitative execution 25, diagnosis/VOI
  20, and belief/final decision 20. Work quality and full-mission success are
  separate; unsubmitted work retains diagnostics and receives zero reliability.
- Controls: Two different valid approaches score 100 on every case/variant;
  nested results do not change scores; empty, generic, and keyword controls are
  at most 15; universal decisions fail the suite; buy-everything fails; an
  ordinary early error retains 94; counterfactual replay changes the correct
  final decision; and the reference completes in at most 18 of 80 tool calls.
  Both internally authored computational-biology and RL-environment reviews
  pass. Model calls and incremental API spend are zero.
- Calibration proposal: Only Sol and GPT-5.2 across four cases, one attempt per
  cell, eight episodes. Expected cached spend is $5.83; reconstructed no-cache
  P90 is $35.32; proposed hard cap is $40.00 with no recorded top-up or key
  increase required. No runner or freeze exists, so execution is impossible
  without a new explicit approval and implementation step.
- Boundary: v0.7 remains unfrozen and uncalibrated. No held-out case or Astra
  configuration was created. One seed cannot support rankings; intervention
  and training-cause claims require paired evidence; strong public/commercial
  claims require independent expert review.

### 2026-09-08 — Stage 8 — v0.7 final amendment and pre-freeze engineering

- Authorization: Recorded the user's explicit ten-cell amendment: Sol and
  GPT-5.2 each receive Case 1, Case 2, both sealed Case 3 replay returns, and
  Case 4. The visible Case 3 packet is identical across returns. No held-out or
  Astra configuration was added.
- Dependencies: Added ten named tests covering contaminated shortcuts,
  commitment/execution consistency, resource isolation, correction timing,
  counterfactual Case 3 decisions, patient/site structure, claim ceilings,
  Case 1 alternatives, guessed labels, and reliability separation. All ten
  pass. Correct calculations now retain partial credit but cannot support a
  mission when they violate the locked plan or patient/site structure.
- Runner: Added two exact OpenAI native pins, disabled fallback, preserved
  reasoning/tool state, recorded every response and route field atomically,
  separated provider/process failures, rejected held-out and Astra, and added
  safe scratch space without weakening source-evidence tamper checks.
- Payload: Locally serialized the exact scientific prompt and all nine tool
  schemas through both provider adapters. Both inherit the prior live exact-
  payload and full-stack passes. New provider requests and scientific spend
  remain zero.
- Cost: The amended ten cells project to $7.28 with observed cache behaviour,
  $44.15 reconstructed no-cache P90, and a $45 hard cap. A live headroom check
  and one immutable freeze are still required before the first paid call.
- Verification: Full repository tests, source/scripts/tests lint, project
  doctor, and network-disabled Docker scientific-Python preflight pass. Public
  packets, private truths, checkpoint weights, and accepted alternatives were
  not changed by the amendment.

### 2026-09-08 — Stage 8 — frozen v0.7 infrastructure no-go

- Freeze: Locked 169 task, truth, tool, prompt, grader, control, route, cost,
  test, runner, and analysis files under digest
  `31e3b57634e1aa2e2b9463b889ab3924e65ec6352076c08150766f9953c9118d`.
  Scientific, held-out, and Astra exposure counts were zero at freeze.
- Attempt: Launched only the first authorized Sol/Case 1 cell. The first API
  request returned HTTP 401 `Missing Authentication header`; no model response,
  completion token, tool turn, scientific score, or provider identity exists.
  Response-reported spend and key-usage delta are both $0.00.
- Fail-fast: Classified the attempt as an unknown harness failure, excluded it
  from scientific matrices, and stopped. No automatic retry, remaining Sol
  cell, GPT-5.2 cell, held-out state, or Astra call occurred.
- Root cause: Frozen `v07_runner.py` creates the audited API client before
  entering `_temporary_environment` for `OPENROUTER_API_KEY`. The exact-payload
  test exercised body and tool-schema serialization but not credential use by
  the client constructor. This regressed a lifecycle repair already present in
  the v0.6.3 wrapper.
- Decision: Frozen v0.7 is a versioned infrastructure no-go and has no
  scientific interpretation. It was not patched or retried. A successor is not
  authorized; a future proposal would need a constructor-level fake-client
  test, one non-scored full-lifecycle canary, a new freeze, and explicit
  execution approval.

### 2026-09-08 — Stage 8 — frozen v0.7.2 two-case grader/ceiling no-go

- Scope: Ran exactly the approved Sol Case 1 and Case 3 signal-collapse
  development checks under the frozen v0.7.2 protocol, then stopped at mandatory
  review. No remaining Sol, GPT-5.2, held-out, or Astra request ran.
- Infrastructure: Both episodes were valid, submitted through the pinned OpenAI
  route, and had no authentication, provider, container, timeout, or
  infrastructure failure. The run used 39 requests, 37 assistant turns, and
  438 seconds of runner wall time.
- Spend: Response-reported spend was $0.6688983; key usage increased by
  $0.6021325 from $57.87355802 to $58.47569052. The $5 stage cap was respected.
- Frozen results: Case 1 reported 73 with no mission and zero reliability; Case
  3 signal-collapse reported 97 with mission success and 97 reliability. These
  values are preserved but are not valid ranking or capability estimates.
- Grader failures: An immaterial alternative site summary invalidated all Case
  1 artifact credit; follow-up verification ignored the committed ECE-bin count
  in both cases; a rejected-then-corrected C5 save was falsely classified as an
  event/action disagreement; and Case 3 was simultaneously labelled as having a
  decision-critical failure and strict mission success. A hidden preference for
  `MODEST_INCREASE` over semantically apt `INCREASE_AFTER_VALID_REPLAY`, plus an
  underdefined ADVANCE versus CONDITIONAL_ADVANCE distinction, added label-based
  deductions.
- Ceiling: Sol correctly completed the full leakage, contamination containment,
  clean-replay, belief-revision, STOP, and claim-bounding chain in the hard
  signal-collapse case. Case 1's lower score is dominated by grader artifacts,
  so the desired 60-70 frontier band and interpretable scientific failure
  gradient were not established.
- Decision: Mandatory no-go. Preserve v0.7.2 without patching or rescoring. Do
  not run remaining Sol, GPT-5.2, held-out states, or Astra. AF-023 is closed by
  the completed check and AF-024 records the live construct and ceiling failure.

### 2026-09-08 — Stage 8 — v0.8 zero-cost verifier repair and portfolio design

- Interpretation correction: Archived v0.7.2 as a development diagnostic. Its
  grader-validity finding remains, but the one-run ceiling conclusion is
  withdrawn. One correct Sol completion establishes tractability; saturation
  requires repeated success across models and cases.
- Verifier: Added independent scoring for every primary and follow-up
  calculation, optional-sensitivity isolation, committed ECE-bin recomputation,
  latest-valid checkpoint authority, internally consistent mission logic,
  numeric belief change, and an explicit stage/scope/gates decision object.
- Replay: Replayed only the two preserved v0.7.2 trajectories at zero API cost.
  Case 1 and Case 3 signal-collapse each receive 100 partial scientific quality,
  complete mission success and 100 reliability under v0.8. These are verifier
  diagnostics, not retroactive v0.7.2 scores or ranking evidence.
- Portfolio: Wrote pre-implementation validity cards for eight investigations
  and sixteen paired states. Case 3 remains the clean-replay tractability
  anchor; seven new investigations cover repeated biopsies, site confounding,
  endpoint/visit integrity, cross-platform transport, calibration/utility,
  sample/label identity and constrained value of information with a sufficient-
  evidence anti-abstention branch.
- Construct controls: Every case divides mission-critical science, accepted
  alternatives and diagnostic-only information; requires saved-artifact
  calculations and a consequential choice; and rejects exact prose, hidden
  filenames, a privileged statistical method and undisclosed necessary
  evidence. Paired intervention claims remain hypotheses until tested.
- Cost: Design spend and requests are zero. A future four-state × three-attempt
  Sol sentinel is estimated at $5.02 cached median and $32.60 no-cache P90 with
  a proposed $40 cap. A future sixteen-state × three-attempt Sol matrix is
  estimated at $20.07 cached median and $130.39 no-cache P90 with a proposed
  $140 cumulative cap. Neither has a runner, command or authorization.
- Verification: Fourteen targeted tests and v0.8 lint pass. AF-024 closes the
  archived v0.7.2 interpretation issue; AF-025 tracks the unimplemented cases,
  final-case separation and missing repeated calibration.

### 2026-09-08 — Stage 8 — v0.8 narrowed five-condition MVP gate

- Scope: Narrowed the active v0.8 MVP to one environment reusing the original
  four v0.7 case packets and five conditions. The eight-investigation design is
  retained as post-MVP roadmap only; no new case dataset was implemented.
- Mapping: Recorded hashes for every reused public packet, private truth,
  sealed outcome and the two Case 3 X31 mechanism returns. No source-science
  file changed, v0.8 remains unfrozen, and model spend/requests are zero.
- Replay: Replayed all five preserved v0.7.1 trajectories through their audited
  semantic maps. Case 1 scores 95 and fails belief revision/final decision;
  Case 2 scores 100 and passes; Case 3 collapse scores 93.333333 and fails the
  mechanism-resolving resource choice; Case 3 remains scores 95 and fails
  belief revision/final decision; Case 4 scores 100 and passes. All five match
  manual adjudications tied to hashed saved work.
- Controls: Thirty-five local cells pass. Each condition accepts a reference,
  a different valid workflow and an incorrect optional sensitivity, while
  rejecting a plausible scientific error, hard-coded results without
  artifacts, altered inputs and a correct decision unsupported by analysis.
- Scoring: Optional calculations, presentation and latest-save bookkeeping are
  diagnostic only. Mission failures are limited to declared scientific
  properties with professional consequences and actionable remedies.
- Cost: Proposed, but did not authorize, one Sol attempt each on Case 2, Case 3
  signal-remains and Case 4. Expected cost is $1.69, reconstructed no-cache P90
  is $6.52 and the proposed hard incremental cap is $8, followed by mandatory
  review. No other model, held-out condition or Astra is in scope.

### 2026-09-08 — Stage 8 — v0.8 live mandatory grader-contamination stop

- Local gate: Implemented the native v0.8 contract and runner, then passed 502
  tests, lint, doctor, audit consistency, Docker isolation, credential checks,
  all five legacy replays and all 35 controls at zero API cost.
- Snapshot: Created a 145-file development execution snapshot with digest
  `eefc1b99d687a61e619d51b28fd588f37e5c1e89bdf017cd95d4b01d899698d8`.
  It is not a release freeze and still verifies unchanged.
- Case 2: Completed on the pinned OpenAI Sol route in 19 requests and 18 turns.
  Raw scoring was 95 with C1-C4 at 100 and C5 at 75, but the failed mission is
  invalid for model interpretation.
- Fault: The agent supplied a complete professional-language PAUSE scope and
  separately supplied every exact machine claim ID. `claim_scope` passed, but
  `explicit_bounded_decision` failed because the verifier silently exact-matched
  private claim IDs inside a field documented as semantic. Recorded as AF-026.
- Stop: Interrupted the already-started Case 3 signal-remains run after 14
  error-free requests, after X31 purchase and before C5 or submit; partial work
  and the ledger are preserved. Case 4 did not start.
  No retry or successor version was created.
- Spend: $0.5771534 response-reported; conservative key usage delta $0.6288614
  from $58.54245632 to $59.17131772, below the $8 cap. No held-out or Astra
  request ran.
- Decision: Do not report the Case 2 raw score as model performance or produce a
  combined five-condition result. No additional model call is authorized until
  the exact grader fault is reviewed.

### 2026-09-09 — Stage 8 — v0.8 zero-cost verifier-architecture repair

- Preservation: Kept execution snapshot 01 at manifest SHA-256
  `6e114b0c26dd4be39501c07173c1ea5fb55b907a97d409bf0e643a5837481d93`,
  kept the Case 2 raw summary at
  `e9f711b61d99609982499695fd49cdc769d0c6ccc94ad94677d81ec0b2470111`,
  and retained the interrupted Case 3 workspace and ledger unchanged.
- Architecture: Audited all mission requirements and removed nine
  duplicate/prose paths. Metrics now come only from independently checked saved
  artifacts; actions and timing come only from events; claims come only from
  disclosed claim-ID fields; stage/disposition come only from their enums; and
  professional decision prose is audit-only.
- Replay: The exact Case 2 submission now scores 100 and passes in a development
  verifier replay. The raw 95/fail remains historical execution output and is
  not retroactively replaced.
- Controls: All 35 original controls, four naturalistic-language fixtures, 511
  repository tests, full lint, project doctor, audit consistency and Docker
  isolation passed. No API request or spend occurred.
- Resume review: Case 3 cannot be resumed exactly because message bodies, tool
  results, environment events and serialized in-memory state are incomplete.
  Its visible C1-C4 work, reveal and X31 return remain useful diagnostic
  artifacts only.
- Snapshot: Created development snapshot 02—not a release freeze—with 228 files
  and digest
  `937bc7d08e74e7f7fd8b718761e96ca1b1989ff7a1aa5caaa9cf9ce66fbc5730`.
  No scientific version, case, truth, prompt or raw result changed.
- Next cost: A fresh Case 3 signal-remains plus Case 4 is expected to cost about
  $0.900223; the minimum responsible combined hard cap under the existing guard
  is $4.78. No paid continuation is authorized by this repair.

### 2026-09-11 — Case 1 RC6 causal verifier and lifecycle closure

- Preservation: RC4 revalidated at
  `d9a79a6f1d29248bad2c3b71a3d0546aea1b5ac9920007ae69445242f397ee66`;
  RC5 remains immutable at its declared digest
  `b07643c08c05fa09c599e077112c1f8519a0b7c5733928b26974182ed834f762`.
  The complete 40-file agent-visible RC5 and RC6 workspaces are byte-identical
  at digest `ac76e0c9bcd393c91087ed78e2e8034f846f165e7d86a1dd65b522514c4d5cf3`.
- Causal adjudication: Sonnet's hidden X24 relevance defect was real but changed
  neither its 37 score nor mission failure. Its missing calculation-output
  manifest/links, two invalid calculation parameter keys and false X24
  materiality declaration are genuine authored errors. Opus is reclassified
  forensically as an isolated provider timeout after 47 exact responses, with
  no score or reliability value; RC5's official records remain unchanged.
- Architecture: RC6 uses the immutable public resource recomputation as the one
  semantic engine consumed by hidden grading, adds property-level causal
  predicates, and implements atomic request states with identity adjudication
  only for completed responses. Provider timeout, 429 and 503 cells are
  contained; shared corruption remains a global stop.
- Local gates: All RC6 controls, seven-resource public/hidden parity checks,
  exact Sonnet/Opus fixtures, timeout/retry, malformed-response, replay,
  Docker, credential, lint, doctor, project-status, broad-audit execution and
  clean-stage gates passed. The full historical suite had only the same two
  pre-existing RC1.4 immutability failures already accepted by RC5; no new
  failure was waived.
- Freeze: RC6 froze once at
  `a1795f1be20b02bb02d86516a664a3d62aed7d6ca716bdd45cb277b4c1ea6d19`.
- Scientific exposure: Under the authorized $8 cap, Gemini 3.1 Pro Preview
  reached the 65-response boundary without submitting ($1.05476480) and is a
  model-completion failure with reliability zero. GPT-5.1 submitted a clean
  100/100 mission pass in 48 requests ($0.78701125). Incremental key-usage
  spend was $1.84177605. No global fault and no Case 2, other-case, Opus, Sol or
  Astra request occurred.
- Common grader: Reused RC5 GPT-5 is 100/pass; reused RC5 Sonnet is 37/fail;
  fresh GPT-5.1 is 100/pass; Gemini has no scientific score because it did not
  submit. This is genuine one-attempt separation but not a stable ranking.
- Decision: Go for porting the tested evaluator/lifecycle architecture to Cases
  2-4, without claiming their scientific validity or authorizing inference.
  A future fresh Opus attempt has a planning no-cache P90 cap of $31.91825625;
  current account and key-limit headroom are $34.282023553 each, so the current
  top-up requirement is $0.00. No Opus call was made.

### 2026-09-12 — Case 2 pilot v1 RC1 zero-spend pre-freeze candidate

- Preservation: Case 1 RC6 remains accepted at digest
  `a1795f1be20b02bb02d86516a664a3d62aed7d6ca716bdd45cb277b4c1ea6d19`.
  Original Case 2 public data, locked predictions, sealed outcomes, preprocessing
  evidence, resource packages, historical trajectories, scores and reports were
  not changed. No candidate freeze was created.
- Construct repair: Published neutral identity semantics for biopsy records,
  outcome-blind provisional linkage units and unverified reported identifiers.
  Added public site-weighted/worst-site non-vacuity floors and an action-scope
  invariant that accepts evidence-supported PAUSE, STOP, INSUFFICIENT_EVIDENCE,
  targeted CONTINUE and general CONTINUE without a private disposition whitelist.
- Semantic engine: Public and hidden validation now share one Case 2 engine for
  cohort, dependence, identity, calculations, site robustness, resource effect,
  belief revision and bounded decisions. Scientific numbers are recomputed from
  saved artifacts; purchased empirical calculations must be bound to the chosen
  purchased table; ineffective purchases receive no decision-relevant credit.
- Controls: 53 Case 2 tests and 11 preservation/readiness tests pass. The broad
  repository run passes 991 tests with four disclosed legacy RC1.4/Case-1
  archive/preflight checks isolated. Lint over `src`, `tests` and `scripts`,
  project doctor and audit consistency pass.
- Reviews: The blind computational-biology reviewer approved the answer-neutral
  public packet and found two materially different valid workflows. The RL
  scientific red team found and verified repairs for generic-action, malformed
  payload, causal-cascade, purchased-lineage, X31-materiality and ineffective-
  purchase defects; no blocker or high finding remains.
- Provenance: Candidate sources, original scientific fixtures, agent-visible
  start state, five exact RC1.6 submissions/summaries and two provider-failure
  ledgers are hashed under a new self-contained candidate root. The compromised
  RC1.4 archive is explicitly not release authority.
- Cost: Two read-only funding checks made zero model calls. Account and key
  headroom are both `$34.282023553`. The proposed three-model sentinel has a
  `$12` cap and is covered. The five-model `$52` cap requires `$17.717976447`
  additional account credit and the same API-key limit increase. No inference or
  compatibility call ran; paid spend was `$0`.
- Decision: Candidate status is `PREFREEZE_REVIEW_READY`. Stop for user review;
  runner/freeze closure and any paid sentinel require separate authorization.

### 2026-09-13 — Frozen Case 2 calibration and separated Case 3 local port

- Case 2 completed first, before any Case 3 source edit, because the paid runner imports
  working-tree infrastructure. Candidate `d8415797...`, 323-file closure `a681bf89...`,
  fixed GPT-5.1 → Sonnet 4 → Gemini order, routes and limits remained unchanged.
- Exactly three inference episodes cost $7.2195348 of the authorized $36. All reconstruct,
  reproduce their original canonical grades twice, and have separate manual artifact
  adjudications. No provider exclusion/retry, shared infrastructure fault or credential breach.
- All three frozen missions fail at zero partial score. This is not a scientific ranking:
  cohort-manifest/registration errors and GPT noncompletion obscure independently correct
  work. Sonnet also missed committed uncertainty and miscomputed ECE; Gemini submitted a
  placeholder primary table despite separately correct weighted calculations. Original
  scores are preserved; correct diagnostic work is documented without retroactive rescoring.
- Post-panel live funding at 22:34:11 UTC: $116.764114303 account, $86.764114303 key remainder.
  The key-usage delta independently matches the request-ledger sum. No further inference ran.
- Case 3 is a new unfrozen, zero-cost port of the existing modern executable X31 generation,
  explicitly separated from original static returns. Two independent read-only initial
  specifications were locked/hashed before implementation; reviewers saw no historical answers
  or desired scores. All original and modern scientific source hashes remain unchanged.
- Local changes are confined to `development/case3_mmmvp` and new evidence/reports. The
  standalone Case 3 scientific core does not instantiate Case 2-specific scientific classes.
  Both public starts match; private verifier/returns/host records remain outside the agent
  workspace. Live Case 3 execution is disabled.
- Independent references pass for both conditions and three estimands. Focused science,
  adversarial, altered-input, exact fake-provider/Docker and restart suite: 102 passed.
  Read-only review caught and verified fixes for malformed-field containment, independent
  calculation credit, endpoint-source/window checks, threshold-sensitive utility, resume
  identity, fail-closed replay and provider-exclusion reporting. No scientific data changed.
- Lint, formatting, project doctor and audit consistency pass. The full historical repository
  regression remains pending at this log entry; the separate Case 3 final acceptance receipt
  must establish no new failure before the locally-validated label is used.
- Reports: `UC_BENCH_CASE2_MMMVP_THREE_MODEL_RESULTS.md`,
  `UC_BENCH_CASE3_MMMVP_LOCAL_READINESS.md`, `UC_BENCH_FOUR_CASE_EOD_STATUS.md`.
  Proposed—not authorized—Case 3 first tranche: two Gemini conditions under $10; six-cell
  three-model extension within $40 only after review/authorization and fresh funding checks.
- Case 1 RC6 remains accepted and unchanged; Case 4 was not started. No Sol, Astra, held-out
  case, replacement model, additional seed or Case 3 paid call was run.

#### Final local acceptance

- Full historical repository completed: 1,178 passed, exactly two known RC1.4 provenance
  failures, zero new failures. Focused Case 3 suite: 102 passed. No archived repair performed.
- Candidate execution closure `2083d5fd4380b3da933dc78e39bbcadb883eb18ce9bda66e4c3247a3ad5ab9ae`
  is unchanged after testing. Case 1 RC6 and frozen Case 2 revalidate; 38 archived Case 3
  scientific/generator hashes and the raw Case 2 run summaries remain unchanged.
- Final label: `CASE 3 LOCALLY VALIDATED — MODEL CALIBRATION PENDING`. This is a hashed
  development candidate only, not a release freeze. The real-call entry point remains disabled.
  No additional API spend. Final acceptance and evidence hashes are recorded under
  `artifacts/uc_bench_case3_mmmvp/local_validation_01/`.

### 2026-09-13 — Case 2 graceful-failure successor — zero-cost local GO

- Created exactly one successor, `uc-bench-case2-graceful-failure-v1`, under
  `development/case2_graceful`. Two fresh read-only reviewers received model-blind
  public/synthetic inputs; their specifications and admission decisions were hashed
  before historical fixture inspection. Both completed bounded closure reviews.
- Only four categories changed: precommit manifest validation, recoverable
  preterminal artifact-graph validation, causal diagnostic artifact quality, and
  provider-neutral explicit-length continuation. Strict scientific mission grading,
  source data, hidden outcomes, resources, thresholds, accepted scientific methods,
  routes and original episode budgets remain inherited and unchanged.
- No archived attempt was resumed, modified or assigned a successor score. The
  report identifies counterfactual feedback boundaries without assuming future
  model correction. Missing uncertainty, incorrect ECE, unsupported resource/claim
  conclusions and unrepaired conflicting artifacts remain failures.
- Focused successor tests: 63 passed. Inherited Case 2 controls: 273 passed.
  One final repository run: 1,239 passed, two known RC1.4 provenance failures,
  two temporary-directory setup errors. The latter were caused by an absent parent
  for the chosen test output directory; the two affected tests passed a targeted
  recheck without code changes. Raw XML results remain preserved. No second full
  repository run and no new unresolved product failure.
- Lint, doctor and audit consistency pass. Twenty-one fake-provider production-path
  summaries are retained, including exact restart/replay, structural correction,
  legitimate scientific failure, incomplete work and provider exclusion controls.
  No real inference was used. The Wi-Fi pause was respected; local tests blocked
  outbound Python networking and the later read-only refresh followed reconnection.
- Preservation checks match 2,472 files in 11 protected trees and all six locked
  inputs/specification hashes. Case 1 RC6, frozen Case 2 and Cases 3/4 remain unchanged.
- Sealed 345-file closure:
  `1276e91e322b2e84c0a008b24b41add487dcdd2a5faea211ab7d837fb5db3aa4`.
  Manifest SHA-256:
  `eb0ac67a8688af49bcfffac4c14581daf9fb44075225c01425205eb9eb3db1d7`.
  Label: `CASE 2 GRACEFUL-FAILURE SUCCESSOR — CALIBRATION PENDING`.
- Read-only OpenRouter refresh at 2026-09-14 00:48:55 UTC confirmed Gemini/Google
  AI Studio, GPT-5.1/OpenAI and Sonnet 4/Amazon Bedrock on their exact pinned routes.
  Account $116.764114303; key remaining $86.764114303; key limit $300. No account edits.
- Proposed, not authorized: Gemini first under $15, then GPT-5.1 and Sonnet 4 only
  if technically clean, all within a $44 cumulative cap. Central no-cache planning
  estimate $23.41128775; 1.5× stress estimate $35.116931625, not empirical quantiles.
  Required account/key funding increases: $0/$0. Original $36 authority is closed.
- Actual inference and compatibility spend this task: $0. Next action requires fresh
  approval. Evidence: `reports/UC_BENCH_CASE2_GRACEFUL_FAILURE_SUCCESSOR.md`,
  `development/case2_graceful/validation_receipt.json`, frozen manifest, route/funding
  receipt, cost plan and adjacent test XMLs. No ranking or demonstrated model-rescue
  claim is made.

### 2026-09-13 — Case 2 graceful staged calibration — prelaunch budget stop

- Received explicit $44 cumulative scientific authorization, Gemini first under $15,
  followed by GPT-5.1 and Sonnet 4 only after technical review. No inference launched.
- Verified the sealed closure, validation/test receipt hashes, protected trees,
  documented historical exceptions, two passing setup-error rechecks and installed
  Docker image. No full repository rerun, scientific review expansion or source edit.
- Found an unresolved-billing accounting gap in the frozen request path. A narrow
  local fault injection through the exact production runner allowed two timed-out
  fake requests, each bounded at $0.069454, against a $0.10 test cap. Both were
  recorded as zero reported cost, so the retry retained the full $0.10 allowance.
  The $0.138908 combined unresolved bound violates the required conservative rule.
- This is a new prelaunch budget-safety finding, not a model/provider observation
  or a scientific-grader finding. Existing reported-cost tests did not cover it.
  Global stop applied before funding/route refresh or any real API request.
- Preserved the release and all historical data/grades. No repair, version, model
  substitution, extra scientific attempt or account change was made. Actual API
  spend: $0; all three scheduled cells remain not launched, with no scientific score.
- Evidence: `reports/UC_BENCH_CASE2_GRACEFUL_CALIBRATION_PRELAUNCH.md` and the local
  fault-injection ledger/lifecycle/trajectory under
  `artifacts/uc_bench_case2_graceful_calibration/prelaunch/`.
- Required next decision: authorize a budget-reservation-only repair, or keep
  execution blocked. The current request explicitly does not authorize development.

### 2026-09-13 — Case 2 graceful three-model calibration — completed; diagnostic-score no-go

- Created and sealed the infrastructure-only cost-accounting successor
  `uc-bench-case2-graceful-failure-v1-budget1`, digest
  `3233cff94612fa75d80ebbe80468df5a4c73a0ead64d8d7327c01825d3436b4c`.
  All 345 predecessor files remain hash-identical; only nine host-side reservation
  and budget-reporting files were added.
- Local gates passed: 70 focused and 335 broader tests, 398 unique tests; lint,
  doctor, audit consistency, fake-provider production rehearsal, restart/replay,
  credential redaction, unresolved-cost persistence, and pre-transport retry blocking.
- Ran exactly Gemini 3.1 Pro Preview, GPT-5.1, and Claude Sonnet 4 on Case 2.
  All 183 provider responses were usable with exact pinned identities, no fallbacks,
  no provider/infrastructure failures, and deterministic replay/regrade.
- Strict missions: 0/3. Gemini and Sonnet reached the 65-turn limit without final
  submission; GPT-5.1 submitted but failed prospective integrity, uncertainty,
  resource-binding, and decision-support requirements. The trajectories show
  materially different workflow failure modes.
- Actual spend was $9.4419394 of the authorized $50. Final settled key headroom was
  $77.322174903 and account headroom $107.322174903. No other cases, Sol, or Astra
  were called.
- Manual adjudication found a diagnostic partial-score contradiction: Sonnet's
  rounded outputs are inside the disclosed tolerance, are `scientific_valid`, and
  pass the strict probability/calibration and utility properties, but the graceful
  scorer promotes `saved_output_rounding_binding` warnings to fatal binding errors.
  Strict mission outcomes are unaffected; numerical partial-score comparison is a
  no-go. Frozen code and raw trajectories were preserved without automatic repair.
- Evidence: `reports/UC_BENCH_CASE2_GRACEFUL_CALIBRATION_RESULTS.md`, the three run
  summaries, `science/panel_state.json`, `science/final_reconciliation.json`, and
  `audit/evidence/case2_graceful_budget_calibration.json`.

### 2026-09-13 — Case 2 diagnostic partial-scoring repair — zero-cost validated

- Locked a model-independent repair policy before implementation or historical replay,
  SHA-256 `74bf65ff82247f4d53dde873f61b70efaedbabf9d0aea98cc07f1f3475f0cc9d`.
  Synthetic controls contain no model IDs, run IDs, historical paths or historical
  numerical values.
- Preserved frozen `uc-bench-case2-graceful-failure-v1-budget1`, digest
  `3233cff94612fa75d80ebbe80468df5a4c73a0ead64d8d7327c01825d3436b4c`.
  No frozen scientific/verifier file or raw trajectory was modified; the 915-file raw
  trajectory digest remained
  `1c6f78ae7cb7d1dc2a3b769e4565303483f88343c635ffd8fd172242463b1f70`.
- Implemented a separate development diagnostic scorer. Independent numerical
  verification owns arithmetic; representation warnings remain visible and non-failing;
  genuine source/output errors affect saved-chain provenance only. Strict mission,
  completion, reliability, resources and decisions are unchanged.
- New controls: 33 passed. Complete Case 2 closure: 449 passed with local Docker
  permission. Lint and JSON validation pass. The first sandboxed Docker invocation
  failed only because the socket was denied and was not treated as a product failure.
- Accepted diagnostic replays: Gemini 16.129032→16.129032; GPT-5.1
  65.909091→65.909091; Sonnet 43.010753→61.290323. All strict missions remain fail;
  all strict property statuses, reliability and completion classifications are unchanged.
  Sonnet gains correct point credit but loses saved-chain credit for real missing
  source-table links; uncertainty, context-audit, follow-up and completion failures remain.
- One initial replay stopped on a GPT uncertainty-alias mismatch. Root cause was use of
  a normalized summary copy instead of the immutable accepted host save; the generic
  replay loader was corrected and exact strict-grade agreement restored.
- Actual API/network calls and spend: zero. Proposed only: one fresh Sonnet 4 Case 2
  attempt, expected ~$7.40, hard cap $12, requiring new explicit authorization.
- Evidence: `reports/UC_BENCH_CASE2_DIAGNOSTIC_SCORING_REPAIR.md`,
  `development/case2_diagnostic_repair/`, and
  `artifacts/uc_bench_case2_diagnostic_repair/replays.json`.

### 2026-09-14 — Case 2 fresh diagnostic canary — strict-verifier no-go

- Reverified frozen `uc-bench-case2-graceful-failure-v1-budget1`, digest
  `3233cff94612fa75d80ebbe80468df5a4c73a0ead64d8d7327c01825d3436b4c`.
- Passed 33/33 repair controls and 449/449 complete Case 2 closure tests. The first
  449-test invocation was denied the Docker socket; its 412-pass/37-Docker-failure XML
  is preserved separately and the identical invocation passed with local Docker access.
- Reran the anti-overfitting search with zero model/provider, run-ID, historical-path,
  historical-value or score-target hits. Sealed diagnostic execution snapshot digest
  `1b9c5b425bdf6742386105f9615b82a2c15e4c9f1c16a1c41ebe5db4d29a1658`.
- Ran exactly one fresh `anthropic/claude-sonnet-4` Case 2 attempt on pinned Amazon
  Bedrock with no fallback. All 65 responses had exact identity and clean lifecycle;
  replay and grader consistency passed. Cost was $8.803284 of the $12 cap.
- The model reached 65 turns without submission. Frozen and repaired partial quality
  were both 77.419355, strict mission failed, reliability was zero, and no diagnostic
  item changed. All six natural rounding warnings remained visible without erasing
  correct point credit; no scientific failure was rescued.
- Manual adjudication exposed a distinct frozen strict-verifier contradiction: the
  public contract marks per-calculation uncertainty optional and diagnostic, but valid
  Brier and utility point properties fail when their optional interval objects are
  present. Removing only those objects in memory flips the two strict properties to
  pass without changing any scientific point value. This violates the locked optional-
  work containment invariant.
- Genuine independent failures remain: wrong per-site source-row counts, no committed
  mixed X46 contingency, incomplete resource binding, missed negative external utility,
  and non-submission. No new version or repair was created and Case 3 was not started.
- Evidence: `reports/UC_BENCH_CASE2_DIAGNOSTIC_CANARY.md`,
  `development/case2_diagnostic_repair/execution_snapshot_01.json`, and
  `artifacts/uc_bench_case2_diagnostic_canary/canary_adjudication.json`.

### 2026-09-14 — Case 2 strict-verifier optionality repair — zero-cost validated

- Locked the general optionality policy and ten-case metamorphic control matrix before
  implementation or trajectory replay. The rule is selected only from public contract
  metadata and causal machine references; required discrimination uncertainty remains
  strict.
- Audited 80 optional/required-false/diagnostic/dynamic fields: 61 diagnostic-only and
  19 conditionally causal. Published a single-authority table for every mission-critical
  property. Free text has no strict scoring path.
- Added a separate development scorer that retains invalid optional intervals as local
  diagnostics while preventing them from invalidating independently correct required
  point estimates. Frozen science, verifier, cases, trajectories and scores were not
  edited.
- Final zero-cost closure: 503/503 passed, including 54 new optionality controls and the
  inherited 449-test Case 2 closure with Docker isolation. Ruff, project doctor, audit
  consistency and anti-overfit search passed. Two restricted-shell attempts hit only
  the denied Docker socket and are preserved as infrastructure evidence.
- Development replays: Gemini 16.129032/fail; GPT-5.1 65.909091/fail; historical Sonnet
  61.290323/fail; fresh Sonnet 77.419355/fail. Optionality corrected strict probability/
  calibration and utility statuses for GPT-5.1 and fresh Sonnet, but changed no partial
  score or mission outcome. Required uncertainty, context, follow-up, commitment and
  completion failures remain. No genuine scientific failure was rescued.
- Frozen release digest remains
  `3233cff94612fa75d80ebbe80468df5a4c73a0ead64d8d7327c01825d3436b4c`;
  both raw trajectory-tree digests are unchanged. Model/network calls and spend: zero.
- Status: `CASE 2 MMMVP LOCALLY VALIDATED — REPEATED-SEED CALIBRATION DEFERRED`.
  Next recommended action is Case 3's zero-cost audit.

### 2026-09-14 — Case 2 MMMVP final packaging and freeze

- Packaged final release `uc-bench-case2-mmmvp-v1` with aggregate digest
  `0037e04cbbef71bbe4f50063cb7b62ca68a043824f0fd2f15d6cf79ae605c6bf`.
- Preserved the 354-file predecessor closure byte-for-byte at digest
  `3233cff94612fa75d80ebbe80468df5a4c73a0ead64d8d7327c01825d3436b4c`,
  plus all four raw trajectory trees, accepted/rejected replays and repair records.
- Production grading now has one entry point composing only the two locked general
  corrections: non-failing within-tolerance representation warnings and causal
  containment of optional diagnostics. Required discrimination uncertainty remains
  strict.
- Exact final package: 6/6 packaging tests and 15/15 lifecycle/scientific/security
  checks passed. Locked controls remain 33/33 and 54/54; the accepted full Case 2
  closure remains 503/503. All four replay results match accepted development replays.
- Public/host/evidence artifacts are separate. Two clean builds and the final build
  were byte-identical; leakage, archive, filesystem, network, environment and
  credential checks passed. Active-grader history/model search found zero unexplained
  hits.
- Two broad diagnostic reruns exposed only obsolete self-expanding legacy freeze
  validators; their failures/interruption are retained rather than rewritten or
  counted as science. The exact final runner's immutable-record path passed.
- Model calls, network calls and API spend: zero. Repeated-seed calibration remains
  deferred; no stable ranking is claimed and Case 3 was not started.
- Status: `CASE 2 MMMVP PACKAGED AND FROZEN — REPEATED-SEED CALIBRATION DEFERRED`.

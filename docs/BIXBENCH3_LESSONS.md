# BixBench3 lessons for UC-Bench

Status: analysis/reporting amendment only. The frozen v0.5 task, evidence,
prompt, grader, thresholds, model matrix, and held-out cases are unchanged.

Sources reviewed:

- [Koch et al., *BixBench3: Benchmarking AI agents on research-study-scale
  computational biology tasks*](https://arxiv.org/html/2608.25286v1),
  arXiv:2608.25286v1.
- [Edison Advances research summary](https://advances.edisonscientific.com/research/bixbench3-benchmarking-study-scale-computational-biology/),
  26 August 2026.
- [EdisonScientific/BixBench3 public runner and deterministic grader
  repository](https://github.com/EdisonScientific/BixBench3).

## The useful result

BixBench3 decomposes research-scale analyses into dependency graphs of
scientific artifacts. It reports lower performance at downstream analysis depth
for many models and retains exact run artifacts and traces. Its process judge
uses a closed failure vocabulary, requires concrete evidence for every tag, and
does not replace deterministic artifact grading. It also reports score against
cost, tokens, turns, and wall time rather than treating greater expenditure as
greater sophistication.

Its scale is useful context, not a target for this MVP: the paper reports 20
tasks and 138 graded artifacts, with a mean attempt taking 6.8 hours, consuming
102 million tokens, and costing $43. UC-Bench borrows the diagnostic structure
while keeping the current experiment deliberately bounded.

These are strong design lessons for UC-Bench. They support explicit dependency
depth, independently interpretable intermediate outputs, trace-backed process
annotation, replayability, and model-specific failure profiles.

## The boundary

BixBench3 gives the agent a research objective, method guidance, raw data, and
exact output contracts, then measures correspondence to artifacts in a source
paper. The authors explicitly state that this evaluates execution of a
specified methodological plan rather than deciding which analyses or questions
are worth pursuing. Exact paper-derived grading also constrains valid
alternative methods.

UC-Bench has a different construct:

> BixBench3 evaluates whether agents can execute specified study-scale
> computational analyses. UC-Bench evaluates whether agents can audit the
> validity of a biomedical evidence chain, contain invalid claims, revise
> beliefs and select the next decision-relevant experiment.

UC-Bench therefore grades scientific invariants, supported claim scope,
prospective commitment, value of information, recovery, and justified
abstention. It must continue to accept different valid statistical methods and
workflows.

## Changes applied to v0.5 reporting

The post-run analysis now projects the existing ten milestones onto an explicit
artifact DAG and reports:

- model performance by milestone and artifact depth;
- the first milestone below the existing 75-point capability-alert threshold;
- downstream artifacts placed at risk by an upstream divergence;
- scientific, process, and infrastructure annotations separately;
- incomplete analysis, input misinterpretation, invalid uncertainty unit,
  placeholder work, premature termination, repetitive retry behaviour,
  belief-revision failure, unsupported claim scope, schema failure, and tool
  timeout when a deterministic rule has concrete evidence;
- tokens, turns, wall time, completion, estimated episode cost, total observed
  pilot spend, and a score-versus-cost frontier;
- replay paths for every selected representative trace.

The depth threshold is analysis-only. It does not alter the score, acceptance
thresholds, task, prompt, or grader. A low upstream artifact marks descendants
as at risk; it does not mechanically zero them because v0.5 intentionally
grades containment and recovery.

## What v0.5 cannot support

The three structured submissions preserve the major state transitions:

1. prospective commitment;
2. post-reveal validation assessment and resource choice;
3. final decision after intervention.

They are sufficient for coarse dependency analysis and scientific replay.
They are not sufficient for uniform independent grading of every intermediate
artifact. Agents often create useful analysis files, but v0.5 does not require
consistent names or semantic contracts for them. This is disclosed rather than
retrofitted after exposure.

Post-exposure review also found a potential v0.5 construct issue that must be
quantified rather than repaired: some frozen grader properties use small text
vocabularies such as `patient|subject|cluster` or `training|train_only`. An agent
can describe a scientifically valid fingerprint-group bootstrap or a frozen
transform fitted only on the discovery cohort without using those exact words.
The original deterministic score remains authoritative for this version, but
the calibration report must disclose affected cells and treat material score
dependence on this vocabulary as a no-go signal. v0.6 should grade parsed
scientific properties rather than token presence.

## Deferred rather than borrowed

UC-Bench does not add large raw datasets, very long runtimes, more tokens, one
mandatory statistical method, or paper-reproduction matching merely to imitate
BixBench3. Study scale is evidence that long dependency chains are valuable;
it is not a reason to expand the pre-MVP before its decision-audit construct is
calibrated.

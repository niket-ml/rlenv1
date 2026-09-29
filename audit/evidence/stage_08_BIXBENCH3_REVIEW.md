# Stage 8 evidence — BixBench3 review and bounded incorporation

Date: 2026-09-07

## Constraint

The frozen v0.5 development pilot had already begun. No frozen task, evidence,
prompt, grader, threshold, model, seed, budget, or held-out artifact was changed.
The pilot was not interrupted and Astra remained excluded.

## Review finding

BixBench3 supplies strong evidence for artifact dependency graphs, depth-aware
reporting, complete trace retention, evidence-backed process tags, and
score-versus-cost frontiers. It deliberately measures execution of prescribed
study-scale analyses against source-paper artifacts. UC-Bench instead measures
whether an agent identifies which evidence and claims are valid and selects the
next decision-relevant experiment.

## Immediate changes

Only the unfrozen post-run analysis/reporting surface changed:

- `scripts/analyze_v05_extended.py` adds artifact-depth and first-divergence
  analysis, deterministic trace-cited process tags, operational accounting, and
  a score-cost frontier.
- `scripts/analyze_v05.py` delegates its command-line entry point to the extended
  analysis.
- `docs/BIXBENCH3_LESSONS.md` records the construct comparison.
- `docs/HARD_SUITE_V06_ARTIFACT_DAG_PROPOSAL.md` records structural successor
  changes rather than retrofitting v0.5.

## Evidence sufficiency

The v0.5 commitment, validation assessment, and final submission are sufficient
for coarse milestone/dependency analysis. They are insufficient for uniform
independent grading of every intermediate artifact because auxiliary audit
files are optional and non-standardized. v0.6 therefore proposes ten compact
semantic artifacts with invariant-based grading and alternative valid methods.

## Claim limits

This review does not supply external expert validation. Internally authored
expert-equivalence controls remain an internal construction check. BixBench3's
published scale and results are used as design evidence only, not as validation
of UC-Bench or as a reason to expand the pre-MVP.

## Completed-pilot result

The unchanged pilot subsequently completed all 18 episodes for $7.53252860 in
incremental OpenRouter usage, with zero infrastructure failures and zero Astra
requests. The BixBench3-informed analysis did not rescore any episode. It adds:

- milestone-to-artifact depth and first-divergence tables;
- descendant-at-risk records without mechanically zeroing recovery work;
- deterministic scientific, process, and infrastructure annotations with an
  evidence path and JSON pointer for every tag;
- tokens, turns, wall time, tool failures, retry behaviour, and a score-cost
  frontier; and
- a v0.6 successor proposal because v0.5's three structured submissions are
  insufficient for uniform independent artifact grading.

The pilot decision is **no-go**. The underpowered/irreducible state explains
67.25% of the strongest-to-weakest absolute gap, above the frozen 30% limit.
Two Sol cells also expose scientifically valid descriptions missed by frozen
vocabulary matchers. The original scores remain authoritative for v0.5; these
construct findings prohibit an Astra canary and any ranking claim.

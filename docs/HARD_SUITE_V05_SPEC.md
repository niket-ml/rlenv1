# UC-Bench v0.5: stateful anti-TNF predictor diligence

Status: **constructed and locally gated; no v0.5 model results**.

## Construct

UC-Bench v0.5 measures whether a coding agent can audit a locked baseline-biopsy
anti-TNF response predictor, preserve the validity of its evidence chain, and
make a commercially meaningful next-investment decision. Predictor optimization
is not rewarded. Correctly establishing that the evidence cannot support
advancement is a successful outcome.

The workflow is occupationally in-distribution for a cross-functional technical
diligence lead. Exact case instances and resource effects are held out. The hard
part is composition: familiar statistical, clinical, platform, provenance, and
experimental-design work must remain coherent across irreversible evidence
reveals.

## Persistent workflow

```text
locked predictor + public data room
  -> intended-use contract
  -> provenance and independence
  -> patient/visit identity and missingness
  -> endpoint construction
  -> platform and preprocessing
  -> baseline reproduction
  -> irreversible validation commitment
  -> sealed external outcome reveal and validation
  -> one follow-up resource selection and reveal
  -> final diligence decision and recovery plan
```

The agent writes three structured records:

1. `submission/commitment.json`: the pre-reveal claim-eligibility ledger and
   validation plan;
2. `submission/validation_assessment.json`: the initial external analysis and
   one resource request;
3. `submission/final_submission.json`: the post-resource decision, belief
   revision, limitations, and smallest next action.

The schemas exist to make state transitions auditable. Explanations and methods
remain open. The grader does not require a particular test name or prose string.

## Agent-visible evidence

Each episode contains:

- an intended-use and utility contract;
- a three-cohort registry and integrity manifest;
- patient-, visit-, site-, batch-, platform-, and fingerprint-level records;
- visible internal outcomes and sealed external outcomes;
- two independent endpoint reviewers;
- a preprocessing history with fit scope and outcome access;
- a locked five-feature model, manifest, reproduction inputs, and reference
  predictions;
- a public metric contract; and
- six costed follow-up resources.

The agent can use any shell or Python workflow inside a network-isolated Docker
workspace. The host alone owns sealed outcomes, resource counterfactuals, grader
truth, and provider credentials.

## Irreversible state transitions

`commit_validation_plan` hashes the prospective commitment and all named
analysis artifacts, including the locked predictor. `reveal_validation` verifies
those hashes before exposing external labels. `request_followup` then hashes the
initial assessment and resource choice before revealing exactly one evidence
packet. `submit_diligence` verifies both earlier records again.

Changing the predictor, commitment, or resource choice after its boundary is a
contract failure. Ordinary scientific mistakes do not invalidate unrelated
milestones.

## Six workflow states

| State | Initial problem | Highest-VOI choice | Designed result | Final action |
|---|---|---|---|---|
| Clean-enough progression | No material blocker | None | Current evidence sufficient for the bounded gate | Conditional advance |
| Patient identity/dependence | Aliased repeated biopsies and uncertain independence | Source-record reconciliation | Resolves the blocker | Conditional advance |
| Endpoint ambiguity | Reviewer disagreement changes the target estimate | Blinded IBD adjudication | Resolves labels, exposes limited evidence | Insufficient evidence |
| Preprocessing leakage | External data and outcomes affected fitted transformations | Leakage-safe locked rerun | Execution is repaired; apparent signal collapses | Stop |
| Endpoint × drug × platform transfer | External cohort is jointly mismatched | Fully matched bridge cohort | Resolves the intended-use transport blocker | Conditional advance |
| Underpowered/irreducible external evidence | Wide uncertainty around modest performance | Larger independent replication | Narrows uncertainty without resolving it | Insufficient evidence |

Wrong resources can be ineffective or misleading. For example, adding more rows
does not reconcile patient identity; enlarging a jointly mismatched cohort does
not establish transport; and expert review without new source evidence cannot
adjudicate patient labels or rerun a leaky pipeline.

## Milestones and professional justification

| Milestone | Professional role | Artifact and decision | Failure consequence | Valid alternatives and invariant | Paired remedy | Why substantive |
|---|---|---|---|---|---|---|
| M01 intended use | Clinical-development lead and biostatistician | Estimand/utility charter; defines relevant evidence | Correct analysis answers wrong clinical question | Different endpoints are allowed only when deployment and error costs remain coherent | Clinical clarification | Product definition changes the estimand |
| M02 provenance | Data curator and ML auditor | Cohort lineage and manifest; establishes independence | Contaminated or duplicated evidence | Hashes, metadata, or fingerprints may establish lineage; counts and roles must reconcile | Source documentation | Independence determines admissibility |
| M03 identity | Curator and biostatistician | Patient–visit map and analysis unit | Pseudoreplication and optimistic uncertainty | Grouped bootstrap, mixed models, GEE, or one-visit rules are valid if dependence is respected | Patient/visit crosswalk | Infers the unit of evidence |
| M04 endpoint | IBD clinician and statistician | Executable endpoint and discrepancy analysis | Label bias or endpoint mismatch | Adjudication, sensitivity sets, or probabilistic labels; timing must precede the measured outcome | Blinded adjudication | Phenotype is a scientific construct |
| M05 assay/process | Platform specialist and ML engineer | Raw-to-feature lineage and fit scope | Batch signal or target leakage | Platform-specific or rank-based methods are accepted when fit only on permitted data | Safe rerun or bridge | Separates technical from biological signal |
| M06 reproduction | Independent validation engineer | Prediction comparison and artifact hash | Validation measures an altered asset | Container replay or independent implementation within justified tolerance | Correct package or stop | Establishes asset identity |
| M07 commitment | Lead statistician | Hashed analysis plan | Hindsight selection and metric shopping | Frequentist, Bayesian, and resampling plans are valid when suited to dependence and use | Amend only before reveal | Makes evidence prospective |
| M08 validation | Statistician and ML auditor | Discrimination, uncertainty, calibration, and utility | Optimistic or irrelevant evidence | Equivalent dependence-aware methods accepted; claims must respect blocked domains | Clean process or matched evidence | Combines quantitative and scientific reasoning |
| M09 VOI | Experimental-design lead | Resource memo and belief update | Spend cannot distinguish live hypotheses | One resource, a defensible substitute, or none; cost and decision impact matter | Evidence matched to active blocker | Tests causal diagnosis and revision |
| M10 diligence | Cross-functional committee | Claim–evidence decision and recovery plan | Unsafe advance or unjustified rejection | Advance, conditional advance, pause, stop, or insufficiency can pass | Smallest unresolved action | Commercial synthesis under uncertainty |

## Conditional scoring

Milestones carry 8–14 points; no milestone exceeds 15. An error restricts the
claims it affects rather than zeroing the episode. For example, unresolved
identity prevents patient-level performance claims but does not prevent endpoint
or platform auditing. An agent that detects and contains the problem can still
score on validation planning, VOI, belief revision, and final diligence.

At runtime, an agent that receives a usable episode but never submits retains a
diagnostic milestone profile while its reliability-inclusive comparison score
is zero. Provider and network failures alone are excluded.

The public capability vector reports:

- data integrity;
- endpoint reasoning;
- statistical validity;
- leakage prevention;
- transportability;
- calibration and decision utility;
- experimental design/value of information;
- belief revision;
- reproducibility; and
- graceful abstention.

## Authentic and controlled evidence

The six v0.5 workflow states are controlled and are labeled as such. They use
realistic cohort sizes, endpoint disagreement, repeated biopsies, platform
metadata, preprocessing histories, and decision thresholds, but they are not
clinical evidence.

The separately preserved authentic GEO anchor uses GSE16879, GSE73661, and the
sealed GSE92415 cohort. Its locked five-gene rank model achieved sealed AUC
0.667 with a 95% bootstrap interval of 0.513–0.814 at n=59 and correctly yielded
`insufficient_evidence`. Authentic and controlled results must never be pooled.
The engineer's predictor can replace the locked candidate later only through
the documented immutable adapter contract.

## Local gates

`scripts/build_v05_controls.py` builds fresh episodes and verifies:

- the reference and a statistically different expert-equivalent workflow score
  at least 90;
- a deliberately mediocre workflow is lower at every milestone;
- universal advance, stop, abstain, and request-more-data policies average below
  50;
- a single ordinary early error leaves more than 50 points recoverable;
- validation outcomes and private answer fields are absent before commitment;
- mutation of committed artifacts is rejected;
- terminal decisions are symmetric; and
- at least four intervention-effect types occur.

These gates validate construction, not model difficulty. Model separation
remains unobserved until bounded development calibration.

## Paid calibration gate

The frozen development pilot contains 18 episodes: six states by Sol, GPT-5.4,
and GPT-5.2, one seed each, with an exact $20 incremental cap. It is a
ceiling/floor check, not a stable ranking. Astra is absent and prohibited.

The pilot is a no-go if the strongest model is at least 85, more than 25% of
opportunities are at ceiling, the weakest model universally fails, fewer than
three substantive failure modes appear, infrastructure/schema errors dominate,
or one failure family explains more than 30% of the observed gap. Repeated seeds
and uncertainty are required before any ranking claim.


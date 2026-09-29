# UC-Bench v0 benchmark contract

## Evaluation question

Can a tool-using agent responsibly evaluate a biological machine-learning
claim when the evidence may be sufficient, insufficient, shifted,
contaminated, or irrecoverable?

The agent is the evaluation subject. The predictor it builds or repairs is an
artifact used to expose the agent's scientific process; it is not assumed to be
clinically useful.

## Unit of evaluation

One episode is one end-to-end diligence decision chain with ten scored
milestones. The agent receives a repository containing public development
evidence, an analysis claim, tool documentation, and no validation outcomes. It
must reconstruct the cohort, audit or repair the analysis, run safeguards,
freeze its artifacts and expectations, receive one aggregate sealed-validation
result, and submit exactly one terminal decision.

The terminal decisions are:

- `advance`: the prespecified evidence threshold is met;
- `stop`: a validity failure makes the current claim or package unusable; or
- `insufficient_evidence`: the analysis is valid enough to interpret, but the
  evidence cannot resolve the decision.

## Graceful failure

A failure is graceful only when the trajectory demonstrates all applicable
parts of this chain:

1. Detect the problem from executed checks or supplied evidence.
2. Localize the affected samples, features, endpoint, analysis step, or claim.
3. Contain it before it contaminates model selection or validation.
4. Repair it when the repair is prespecified and auditable.
5. Preserve and clearly delimit conclusions that remain valid.
6. Quantify the uncertainty that remains.
7. Choose the terminal decision supported by the evidence.
8. Name the smallest next action that could resolve the uncertainty.

Saying “insufficient evidence,” listing generic caveats, or repeating rubric
language is not graceful failure without corresponding trajectory and artifact
evidence.

## Evidence states

The same task contract is evaluated under four state families:

| Family | Required behavior |
|---|---|
| Authentic weak evidence | Complete valid analysis and usually return `insufficient_evidence`. |
| Sufficient evidence | Recognize the prespecified positive evidence and return `advance`. |
| Recoverable defect | Detect, repair without leakage, and then decide from repaired evidence. |
| Irrecoverable defect | Contain the damage, preserve valid findings, and return `stop`. |

This symmetry makes universal abstention and universal advancement losing
strategies.

## Headline score

The graceful-failure score has five equally inspectable components:

- 25% failure detection and diagnosis;
- 25% evidence integrity and containment;
- 20% uncertainty and decision calibration;
- 15% recovery and next action; and
- 15% reproducibility and contract compliance.

Realized predictive discrimination may contribute at most 10% inside an
episode-specific rubric and is never the headline ranking metric. Contract-valid
rate is reported separately rather than hidden inside the mean score.

## Hard invalidation

The episode receives zero if the agent accesses sealed outcomes, uses sealed
samples during development, modifies committed artifacts after commitment, or
tampers with grader state. A claimed `status: pass` that contradicts private
recomputation is contract-invalid and capped at 40; an independently observed
attempt to fabricate or tamper with execution evidence is a hard invalidation.
This separates a wrong calculation from deliberate integrity abuse without
allowing either to pass.

## Claims policy

Authentic-cohort results and controlled-variant results must appear in separate
report sections. Controlled variants support claims about agent behavior, not
new claims about ulcerative-colitis biology. No result from v0 is represented
as a clinically validated predictor.

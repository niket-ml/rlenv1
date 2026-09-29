# UC-Bench v0.8 MVP development design

v0.8 is an unfrozen development workspace. It is not a release candidate and
has no paid model results. v0.7.2 is retained as an archived development
diagnostic; its original scores and artifacts are not overwritten.

## Measurement objective

UC-Bench tests whether an agent can audit a biomedical predictor evidence chain,
perform the calculations needed to support its conclusions, contain invalid
claims, choose a decision-relevant follow-up, and revise a bounded development
decision when new evidence arrives.

Complete mission success is the headline result. Partial scientific quality is
reported only to identify what was completed and where the first consequential
failure occurred. There is no target range for partial quality.

A single success establishes tractability. Difficulty is classified only after
three attempts on identical case-state hashes:

- 3/3: reliably solved;
- 1–2/3: useful frontier or RL case;
- 0/3: review for excess difficulty or possible demonstration-based training.

The eventual 35–65% target applies to the strongest model's complete-mission
rate across the case set. It is not a reason to manufacture deductions.

## Requirement classes

Every case card and verifier check belongs to exactly one class:

1. `mission_critical_science`: an error changes the valid claim, analysis unit,
   evidence eligibility, resource choice or development action;
2. `accepted_professional_alternative`: a scientifically defensible route that
   must receive equivalent credit;
3. `diagnostic_only`: useful information that can explain behaviour but cannot
   fail a mission.

Primary calculations are independent checks. One wrong calculation loses only
its own credit unless it crosses a declared decision rule. Optional sensitivity
outputs never invalidate correct primary evidence.

## v0.8 decision and belief contracts

Belief revision records a named hypothesis, numeric support before and after,
and the evidence responsible. The verifier checks direction and decision
consistency; it does not demand a hidden case-specific adjective.

The final decision is an object containing:

- development stage;
- disposition;
- allowed use;
- unresolved gates;
- prohibited use;
- required next evidence.

This distinguishes continuing research validation from clinical deployment and
allows conditional, terminal and insufficient-evidence decisions to be graded
by their scientific scope.

## Active MVP scope

The active MVP is one environment containing the original four v0.7 case
packets and five controlled conditions: Case 1, Case 2, Case 3 signal-collapse,
Case 3 signal-remains and Case 4. The public packets, sealed outcomes and
scientific purposes are reused rather than regenerated. Their mapping and
evidence-conditioned acceptance rules are declared in
`configs/hard_suite_v08_mvp.json`.

Case 3 retains the paired clean-replay outcomes with the same public starting
state and opposite supported belief updates. The other cases retain their
existing resource returns; professional alternatives are judged by whether the
chosen evidence resolves the stated diligence decision, not by one privileged
resource ID.

The eight-investigation portfolio in
`configs/hard_suite_v08_case_portfolio.json` is a post-MVP roadmap only. None of
its proposed new investigations is being implemented in this MVP.

## Local validation

All five conditions have a correct reference, a different valid workflow, a
plausible scientific-error control, a hard-coded-without-artifacts control, an
altered-input control, a correct-but-unsupported decision control and an
incorrect optional-diagnostic control. The first two workflows and the
optional-diagnostic control must pass; the four substantive attacks must fail.

All five preserved v0.7.1 trajectories are replayed through their audited
v0.7.2 semantic maps. A manual adjudication identifies the expected mission
status and failures from saved patient tables, calculation outputs and
follow-up analyses before the replay result is accepted. This development
replay is not a retroactive change to frozen v0.7.1 or v0.7.2 scores.

## Development and release separation

The five MVP conditions may be edited after diagnostic model runs. Every attempt must
record the case, prompt, tool, verifier and data hashes. Results with different
hashes are never pooled, and any edited case requires three fresh attempts for
difficulty classification.

Only a release candidate is frozen. Untouched final cases, repeated attempts,
cross-provider evaluation and uncertainty analysis are required before stable
rankings. Training-data, SFT, expert-demonstration, prompting or RL causes are
not claimed without paired intervention evidence.

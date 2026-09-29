# Stage 8 evidence — hard suite v0.7.2

Interpretation update: the grader-validity no-go below remains correct, but the
one-run ceiling characterization is withdrawn. One successful Sol completion
establishes tractability; saturation requires repeated success across models and
cases. The zero-cost successor analysis is recorded in
`audit/evidence/stage_08_HARD_SUITE_V08.md`.

v0.7.2 is a narrowly scoped interface-and-grader successor to frozen v0.7.1.
Frozen v0.7 remains a zero-spend infrastructure no-go, and v0.7.1 remains an
infrastructure success but scientific construct no-go. Neither was modified or
rescored.

The v0.7.2 freeze proves equality for all 169 v0.7 scientific hashes. Public
case packets, private truths, both Case 3 returns, actions, tools, checkpoint
weights, mission rules, model panel, execution budgets, stopping rules, and the
$45 global scientific cap are unchanged. The new freeze digest is
`f17ce1ffe7e3986fe63f70644b55a3d624325ad55792e078f43a58708c26c328`.

The repair replaces prose extraction with a fully disclosed typed submission
contract. Scientific facts come from explicit fields; actions and timing come
from the environment event record. Primary metrics are controlled by the
committed plan. Free text cannot create a fact, decision, claim, or belief.
Contract, parsing, completion, provider, infrastructure, and scientific failures
are reported separately.

The hidden verifier requires saved patient mapping/prediction/label/split,
preprocessing-fit, and calculated-output artifacts. It recomputes important
results from raw evidence using the agent's declared bootstrap seed and replicate
count. Altered-label and altered-prediction controls invalidate copied values.
The oracle and grader remain host-only; the Docker agent has network mode none,
a read-only root, only `/workspace` mounted, and no credential environment.

Zero-cost gates passed:

- 469 repository tests, lint, project doctor, audit consistency, and Docker
  isolation preflight;
- semantic invariance for flat, nested, reordered, annotated, and paraphrased
  submissions;
- reference and alternative workflows at least 90 with strict mission success;
- generic, keyword, and guessed-final attacks at most 20;
- all universal decision policies fail;
- graceful recovery preserves later-stage credit;
- missing-artifact and altered-input copied-answer controls fail;
- exact pinned OpenRouter payload compatibility for Sol and GPT-5.2, with no
  fallbacks and no provider request;
- no credential leakage;
- five v0.7.1 traces replayed at zero cost with scores spanning 87.666667 to
  94.382653 and zero strict missions, rather than a uniform 15-point cap.

The replay is only a grader-validation fixture. It is not a new model result and
does not retroactively correct frozen v0.7.1. Each mapped field records its source
artifact and JSON pointer; mapping never awards scientific correctness.

The authorized two-case check is now complete. Exactly Case 1 and Case 3
signal-collapses ran on Sol, both as valid provider episodes. The runner stopped
at the mandatory review with no remaining Sol, GPT-5.2, held-out, or Astra
request. Response-reported spend was $0.6688983 against the $5 cap; key usage
increased by $0.6021325.

The mandatory review is a no-go. Case 1's primary numerical artifacts were
independently correct, but a 0.000787 alternative site-sensitivity convention
invalidated the entire artifact and erased primary credit. Both cases used their
committed ten-bin ECE method after follow-up, while the verifier silently used
five bins and zeroed the whole follow-up property. Case 1 corrected a visible
invalid C5 save, but the event grader compared the rejected historical digest
with the final valid payload and falsely set reliability to zero. Case 3's
grader simultaneously reported a decision-critical follow-up failure and strict
mission success. These are construct-invalid grader behaviours.

There is also insufficient headroom. Sol correctly diagnosed leakage, excluded
contaminated evidence, ran the clean signal-collapse replay, revised belief,
stopped the asset, and bounded claims in Case 3, scoring 97. Case 1's apparent
73 is dominated by grader artifacts and an underdefined ADVANCE versus
CONDITIONAL_ADVANCE distinction, so the two scores cannot support the desired
60-70 frontier range or a failure gradient.

Frozen v0.7.2 is therefore preserved as a grader/construct and ceiling no-go.
It is not patched or rescored. The full manual finding record is
`artifacts/diagnostics/hard_suite_v072_two_case_review.json`, and the narrative
report is `reports/generated/hard_suite_v072_two_case_no_go.md`. Remaining Sol,
GPT-5.2, held-out states, additional seeds, and Astra remain blocked.

This is a calibrated pilot environment/case study, not a broad computational-
biology benchmark. Stable rankings require more independent cases and repeated
attempts reporting always/sometimes/never mission success, partial work quality,
cost, turns, and completion failures.

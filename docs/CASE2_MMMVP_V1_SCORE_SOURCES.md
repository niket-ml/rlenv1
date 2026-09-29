# Case 2 MMMVP v1 score-source table

The sole production entry point is
`uc_bench.case2_mmmvp_v1_verifier.grade_case2_submission`. Scientific prose is
never an authority for a machine-scored fact.

| Reported output | Single authority | Verification | Separation rule |
|---|---|---|---|
| Strict mission success | All mission-critical requirement booleans plus host-accepted completion | Required facts are independently reconstructed; mission passes only when every requirement passes and completion is accepted | Cannot be inferred from the partial score |
| Direct partial scientific quality | Property-local verified evidence items and fixed weights | Saved tables and calculation outputs are recomputed from source evidence | Dependency failures do not erase independently correct upstream work |
| Dependency consequences | Published property dependency DAG | First failed consequential property is propagated only to declared descendants | Consequence is reported separately from direct work quality |
| Completion | Host action lifecycle and accepted terminal submission | Event order, state, hashes and durable records | Model noncompletion is not a scientific failure |
| Reliability | Host-accepted completion state | 100 only for accepted completion; otherwise 0 | Never substituted for scientific quality |
| Contract failure | Disclosed machine fields and schemas | Enum, conditional-field and artifact-contract validation | Prose and optional presentation cannot fail the contract |
| Scientific failure | Required saved artifacts, machine fields and independent recomputation | Patient unit, cohort, split, threshold, uncertainty, context, follow-up and decision properties | Optional diagnostic faults remain local unless causally promoted by a disclosed rule |
| Provider exclusion | Pinned request/response identity and request lifecycle | Route, provider, fallback, response and retry evidence | Excluded from scientific scoring |
| Infrastructure exclusion | Shared runner, persistence, integrity, credential and protected-data checks | Deterministic replay, hashes, boundaries and lifecycle state | Excluded from scientific scoring |

Representation or rounding warnings cannot erase scientific credit when the
authoritative recomputation is within the disclosed tolerance. Required
discrimination uncertainty remains strict. An optional sub-result is causal only
through a disclosed machine-readable reference; the verifier never infers reliance
from prose.

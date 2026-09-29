# UC-Bench v0.7.2 submission and verification contract

v0.7.2 is an interface-and-grader successor to frozen v0.7.1. Its cases,
outcomes, resource returns, scientific thresholds, checkpoint weights, mission
rules, tools, model panel, and execution budgets are unchanged. It repairs the
failed prose extractor by making scientific facts explicit and actions
event-authoritative.

The complete machine-enforced contract is the `V072_AGENT_CONTRACT` constant in
`src/uc_bench/v072_interface.py`. That exact text is appended to the unchanged
v0.7 scientific system prompt on every v0.7.2 episode. The hidden verifier adds
no undisclosed filename, key-name, method-name, or workflow convention.

Key properties:

- Facts use documented JSON fields and exact enums; free text is retained but
  never mined for answers.
- Flat fields and the same fields nested under `facts` are equivalent.
- The committed validation plan determines the primary metric set. Sensitivity
  values cannot replace missing primary results.
- Irreversible actions come from the environment event record only.
- The agent declares artifact paths instead of obeying arbitrary filenames.
- A patient-table column contract records patient mapping, predictions, labels,
  validation split, and contributing sample IDs. Separate fit-membership and
  calculated-output artifacts are also required.
- The hidden verifier recomputes important results from raw mounted evidence and
  checks the saved artifacts. Copied constants without supporting artifacts do
  not earn numeric credit.
- Exact matching is limited to disclosed enum, resource, metric, and column
  contracts, including the complete concept/claim registry and evidence groups
  printed in the agent prompt. Alternative valid statistical methods remain
  accepted.
- Strict mission success is the headline outcome. Partial work quality and
  reliability/failure class remain separate diagnostic outputs.
- Altered-input controls change labels or predictions while holding a submitted
  answer fixed. The verifier must reject the copied metrics and fixed decision.
- Every failed mission records the first decision-critical property failure,
  trace evidence, its professional consequence, and the smallest stated remedy.
- Scientific, harmless contract, model-completion, provider, infrastructure,
  and parsing failures are distinct fields and are never pooled into one zero.
- The oracle, private outcomes, resource variants, and grader stay on the host.
  The agent container receives only `/workspace`, has network mode `none`, and
  receives no provider credential.

This remains a calibrated pilot environment/case study, not a broad
computational-biology benchmark. The initial two Sol executions are infrastructure
and grader checks, not ranking evidence. Any later publication must use repeated
attempts and report always/sometimes/never successful missions, mean partial work
quality, cost, turns, and completion failures. No stable model ranking follows
from the current few cases or a single attempt.

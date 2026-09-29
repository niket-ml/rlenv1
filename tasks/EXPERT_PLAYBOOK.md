# Expert biomarker-diligence playbook

This playbook is a general procedural scaffold. It does not contain a scenario
answer, hidden threshold, expected metric value, or planted-item identity.

## Evidence and decision checklist

- Translate every public decision rule into a checklist before deciding.
- Distinguish a null result, inadequate sample size, wide uncertainty, data
  integrity failure, endpoint mismatch, drug transfer, platform shift, and
  missing required features. Do not substitute one diagnosis for another.
- Report every independently supported failure needed to explain the decision,
  and cite the evidence or computed metric that establishes it.
- A hard unresolved identity or integrity conflict is qualitatively different
  from merely insufficient statistical evidence.
- Choose the smallest next experiment or repair that directly resolves the
  dominant uncertainty. Do not request generic new data when a targeted repair
  is available.

## Tool and submission checklist

- Read both the task contract and the JSON schema before writing the artifact.
- Compute requested metrics with executable code and retain full precision
  until the final serialization step.
- Reserve at least two turns for schema validation and the terminal submit
  call. The task is not complete when a correct file merely exists.
- Validate the final JSON locally against the supplied schema. Required keys
  must be at the documented level, enumerated values must be exact, numerical
  fields must be numbers, and additional prose keys are not allowed.
- If submission fails, make the smallest correction indicated by the tool
  error, revalidate, and submit again. Do not redesign a correct analysis while
  repairing the interface contract.

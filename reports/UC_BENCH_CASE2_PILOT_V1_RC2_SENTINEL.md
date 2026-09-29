# UC-Bench Case 2 RC1 — three-model sentinel

Release digest: `f45dd99d4359c3de78e2e7ceb5b8115eaf35483bb82aa0c97316b1260fa03291`
Status: **completed**
Scientific spend: **$10.298374**

This is a one-attempt development sentinel, not a stable model ranking.

| Model | Class | Mission | Partial | Reliability | Requests | Cost |
|---|---|---:|---:|---:|---:|---:|
| google/gemini-3.1-pro-preview | model_completion_failure | None | None | 0.0 | 65 | $1.0269612 |
| openai/gpt-5.1 | model_completion_failure | None | None | 0.0 | 17 | $0.21169225 |
| anthropic/claude-sonnet-4 | valid_episode | False | 0.0 | 100.0 | 56 | $9.059721 |

## Interpretation

```json
{
  "artificial_completion_or_contract_floor": true,
  "ceiling_warning": false,
  "failure_concentrated_on_one_workflow_step": true,
  "genuine_scientific_separation": false,
  "insufficient_evidence": true,
  "one_attempt_per_model_not_a_stable_ranking": true
}
```

## Funding for a separate $52 stage

```json
{
  "additional_account_balance_required_usd": 28.0163509,
  "additional_key_limit_required_usd": 28.0163509,
  "covered": false,
  "minimum_resulting_key_limit_usd": 258.0163509,
  "required_scientific_headroom_usd": 52.0
}
```

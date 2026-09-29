# UC-Bench Case 1 pilot RC2 — mandatory pre-inference stop report

Date: 2026-09-10

## Outcome

RC2 froze successfully but the Case 1 pilot did not begin scientific inference. The
Gemini sentinel stopped in the shared production harness before the OpenRouter client
was constructed. No provider request was made, no scientific evidence was exposed to a
model, and reported scientific spend was $0.

The scientifically correct interpretation is **insufficient evidence**. There are no
model results and no capability separation to report.

## Immutable release evidence

- RC1 release digest: `efcd42455279ae6601a7c11493e7c7b194478a6cad5e633a76785b25c48c31ec`
- RC2 release digest: `2e73ad89d00b55daed1c13c5361bacacca3e91b6176e56456d3b35c433dd1a77`
- RC2 closure: 177 files
- RC1 scientific closure retained byte-for-byte: 111/111 files
- RC2 behavioral delta declared and frozen: exact identity adjudication only
- Preserved RC1 compatibility classifications: five shared-checker failures
- Offline RC2 re-adjudication: five technically compatible routes, zero requests, $0

RC1, its release freeze, and all five raw compatibility ledgers remain unchanged.

## Zero-cost gate results

All release gates passed before freeze:

- exact-identity regression cases;
- replay of all five preserved compatibility ledgers;
- 36 scientific controls, including eight valid alternative workflows and 16 rejected
  attacks;
- lint, doctor, project audit, and repository tests;
- Docker workspace isolation;
- clean-stage import and replay tests;
- credential-literal scan;
- RC1 evidence immutability before and after preparation.

The repository test command retained its predeclared release-policy exception for the
two historical RC1.4 checksum tests. No new unexpected test failure was accepted.

## Funding gate

The read-only post-freeze check independently reported:

- account credit remaining: `$115.621609303`;
- API-key limit: `$230.00`;
- API-key usage: `$114.378390697`;
- key-limit headroom: `$115.621609303`;
- effective headroom: `$115.621609303`;
- required Case 1 cap: `$52.00`;
- account shortfall: `$0.00`;
- key-limit shortfall: `$0.00`.

Funding was therefore not the blocker.

## First production failure

The first decision-critical event was a shared harness failure before inference:

`ConfigurationError: Production tool surface differs from the frozen request`

The frozen agent-visible request contains descriptions for five state-changing tools:

- `commit_validation_plan`;
- `reveal_validation`;
- `commit_followup_plan`;
- `purchase_resource`;
- `submit`.

The production durable wrappers generated the same tool names, argument schemas, strict
flags, and order, but their function descriptions were empty. The production runner's
byte-equality assertion therefore failed before client construction.

This is a genuine shared harness/schema inconsistency. It is not a model scientific
failure, contract failure, completion failure, provider failure, or identity failure.

## Classification audit

The immutable run summary correctly records `infrastructure_failure` and zero provider
requests. The orchestration state additionally records `grader_contradiction`; that tag
is a downstream misclassification caused by treating the absence of a durable provider
boundary as failed grader consistency. There was no submission and no grade, so no
grader contradiction occurred. Both raw fields are preserved; this report supplies the
manual forensic adjudication rather than rewriting them.

## Per-model result

| Model | Technical result | Requests | Turns | Cost | Mission | Partial score | Ten properties | Resource / belief / final decision |
|---|---:|---:|---:|---:|---:|---:|---|---|
| Gemini 3.1 Pro Preview | Shared harness failure before client construction | 0 | 0 | $0 | Not scored | Not scored | All not assessed | None |
| Claude Opus 4.1 | Not launched after global stop | 0 | 0 | $0 | Not scored | Not scored | All not assessed | None |
| GPT-5 | Not launched after global stop | 0 | 0 | $0 | Not scored | Not scored | All not assessed | None |
| Claude Sonnet 4 | Not launched after global stop | 0 | 0 | $0 | Not scored | Not scored | All not assessed | None |
| GPT-5.1 | Not launched after global stop | 0 | 0 | $0 | Not scored | Not scored | All not assessed | None |

The ten scientific properties—prospective design and integrity, saved artifact chain,
entity/dependence analysis, discrimination/uncertainty, calibration, utility, context
robustness, decision-relevant follow-up, belief revision, and bounded claims—were never
evaluated.

## Scope and stop decision

- Case 2 requests: 0
- Other-case requests: 0
- Sol requests: 0
- Astra requests: 0
- Replacement models: 0
- Scientific API requests: 0

The authorized global-stop rule was followed. RC2 remains frozen and is not modified or
retried. The Case 1 pilot provides insufficient evidence: it shows neither a ceiling,
scientific separation, concentrated scientific failure, nor a model completion floor.
It exposes one shared pre-inference harness defect that the zero-cost production-path
gate failed to exercise.

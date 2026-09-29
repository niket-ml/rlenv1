# UC-Bench v0.6 artifact-DAG proposal

Status: historical successor design record, now implemented by
`docs/HARD_SUITE_V06_SPEC.md`. v0.6 remains unfrozen and unexposed to any model.
It does not modify v0.5.

## Objective

Retain the v0.5 anti-TNF predictor-diligence decision chain while requiring a
small set of meaningful intermediate artifacts. Each artifact should expose a
scientific state transition and be independently gradable without forcing one
reference implementation.

## Proposed artifact DAG

| Depth | Artifact | Depends on | Scientific decision exposed |
|---:|---|---|---|
| 1 | `cohort_inventory.csv` | source data room | Which cohorts, visits, drugs, endpoints, platforms, and missing fields exist? |
| 1 | `provenance_audit.json` | manifests and source metadata | Which evidence is authentic, intact, licensed, and decision-eligible? |
| 2 | `patient_visit_map.csv` | cohort inventory and provenance | What is the independent analysis unit and which rows may be linked? |
| 2 | `endpoint_audit.json` | cohort inventory and source labels | What outcome is actually measured and where is adjudication uncertain? |
| 2 | `preprocessing_lineage.json` | assay records and predictor contract | Which transformations were fitted where, and could outcomes contaminate them? |
| 2 | `reproduction_predictions.csv` | locked predictor and supplied inputs | Does the immutable predictor reproduce independently? |
| 3 | `committed_validation_plan.json` | all depth-1 and depth-2 audits | Which estimand, unit, uncertainty procedure, sensitivity analyses, and gates are fixed before reveal? |
| 4 | `validation_results.json` | committed plan and sealed outcomes | Which estimates are valid and which claims remain conditional or invalid? |
| 5 | `resource_value_memo.json` | validation results and resource catalog | Which smallest investment distinguishes the live hypotheses? |
| 6 | `final_diligence_report.json` | follow-up evidence and all prior artifacts | Should the asset advance, pause, stop, or remain unresolved, and why? |

## Grader contract

The grader should evaluate semantic and scientific invariants, not exact rows
from one preferred pipeline:

- all source rows are accounted for or explicitly excluded with reasons;
- patient and visit mappings are internally consistent and preserve uncertainty
  at the independent unit;
- endpoint meaning, timing, adjudication, and missingness are explicit;
- preprocessing lineage identifies fit cohorts, outcome visibility, platform
  transfer, and immutable transforms;
- reproduction predictions preserve sample identity and agree numerically within
  a declared tolerance;
- the committed plan is hashed before outcomes are available;
- validation estimates follow the committed estimand and uncertainty unit;
- claim statuses are no stronger than the evidence permits;
- resource value compares live hypotheses and opportunity cost;
- final belief revision follows the revealed evidence;
- alternative valid estimators and workflows receive full credit when they
  preserve these properties.

Exact filenames are a collection interface, not the scientific challenge.
Formatting mistakes should be reported separately and should not dominate the
scientific score.

## Dependency scoring

Each artifact receives an independent property vector and a validity state:
`valid`, `conditionally_valid`, `invalid`, or `missing`. The analysis records
the first invalid dependency and the descendants whose claims become invalid or
conditional. Descendants may still receive credit for correctly detecting the
upstream problem, containing claims, performing unaffected work, or recovering
after a remedy.

No early artifact mechanically zeroes the episode. The final report must show:

- raw artifact quality;
- conditional score given valid parents;
- containment and recovery credit;
- the first substantive divergence;
- descendants invalidated versus merely placed at risk.

## Process annotation

Deterministic scientific grading remains primary. A separate evidence-backed
process layer may annotate incomplete work, input misinterpretation, invalid
units, placeholder outputs, premature termination, repetitive retries, tool
failure, and unsupported claims. Every tag requires an artifact path, JSON
pointer, trace message, or command result. An LLM judge may suggest candidates,
but cannot silently alter scores or the headline order.

## Scope discipline

v0.6 should remain one workflow with approximately ten artifacts. It should not
add BixBench3-scale raw data or a paper-reproduction objective. The additional
structure is justified only because it improves diagnosis of evidence-chain
validity and recovery.

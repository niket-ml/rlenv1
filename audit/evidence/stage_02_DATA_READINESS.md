# Stage 2 data-readiness decision

Decision: **proceed for diligence, not biomarker discovery**.

The pinned GEO series matrices and platform annotations reproduce the intended
patient-level subsets:

| Cohort | Role | Baseline patients | Response split | Platform |
|---|---|---:|---:|---|
| GSE16879 | infliximab discovery | 24 | 8 / 16 | GPL570 |
| GSE73661 | infliximab replication | 23 | 8 / 15 | GPL6244 |
| GSE92415 | sealed golimumab transfer | 59 | 32 / 27 | GPL13158 |

All selected records are unique at sample and derived-patient level. GSE73661
outcomes are derived by pairing each W0 biopsy to its W4/W6 biopsy and applying
the deposited Mayo endoscopic healing definition. GSE92415 agent-visible
metadata omits `wk6response`; its labels are written only to ignored
grader-private storage.

After retaining only unambiguous probe-to-symbol annotations and collapsing
duplicate probes by median, 17,151 genes are common to all three platforms.
This is ample alignment coverage but not license for high-dimensional feature
discovery with 47 visible patients.

The cross-platform expression identity audit found no near-identity pattern
between GSE16879 and GSE73661 (assigned correlation median 0.322, maximum
0.583). Outcome concordance among expression-matched samples was high, which is
consistent with shared response biology and is not treated as proof of patient
identity. The cohorts remain separate discovery and replication evidence; they
must not be described as 47 exchangeable independent training rows during
model selection.

Constraints carried into Stage 3:

- use a prespecified low-dimensional reference analysis;
- preserve cohort-held-out evaluation before any final refit;
- treat endpoint and platform transfer as explicit uncertainty;
- keep raw GSE92415 files outside the agent-visible workspace; and
- make no clinical-validity claim from these sample sizes.

Machine-readable evidence, including hashes and the full identity-pair table,
is in `stage_02_data_feasibility.json`.

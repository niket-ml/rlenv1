# UC-Bench v0 threat model

## Protected claims

UC-Bench may claim that one evaluated agent handled the packaged diligence
workflow more reliably than another under specified conditions. It may not
claim that the resulting predictor is clinically useful or that a controlled
variant represents new biology.

## Threats and required controls

| Threat | Failure mode | Required control |
|---|---|---|
| Literature contamination | Agent recalls published signatures or outcomes. | Matched data-withheld runs; score executed process; never expose per-patient sealed outcomes. |
| Validation leakage | Validation samples influence feature selection or tuning. | Sample-role manifest, filesystem boundary, one-time reveal, artifact hashes. |
| Post-hoc adaptation | Agent changes model after seeing aggregate validation. | Commit ordered artifact paths and hashes; reject any mutation. |
| Universal abstention | Agent earns credit by always saying evidence is insufficient. | Sufficient-evidence states and symmetric decision scoring. |
| Universal advancement | Agent chases high AUC and ignores validity. | Null, contaminated, and irrecoverable states with hard integrity penalties. |
| Keyword or structured-claim reward hacking | Agent narrates checks or writes false `status: pass` fields without running them. | Independently recompute cohort counts, sample roles, model statistics, hashes, and event order; contradicted pass claims hit the contract ceiling. |
| Synthetic puzzle artifacts | Planted defect is obvious or biologically implausible. | Use source-preserving transformations, hidden strengths, and expert realism review. |
| Infrastructure dominance | Agents fail on missing packages or undocumented tools. | Frozen offline image, tool contract tests, and separate infrastructure failure labels. |
| Small-sample ranking noise | Raw AUC drives model order. | Cap discrimination weight, report intervals, repeat seeds, and emphasize process components. |
| Grader overfitting | Public tests disclose exact private checks. | Publish contracts and representative tests, retain independent private cases. |
| Sample-count inflation | Repeated biopsies are treated as independent patients. | Patient/timepoint manifest and patient-level split assertions. |
| Cross-platform shortcut | Cohort identity substitutes for biology. | Gene-space coverage checks, cohort-held-out evaluation, and platform-aware variants. |
| Canned analyst oracle | A magic question reveals the intended answer. | Evidence-limited answer bank, question-equivalence tests, graded pushback, and turn budget. |

## Audit rule

Every headline failure claim must resolve to a replayable trajectory event and
at least one grader-observed artifact or state transition. If it cannot, it is
reported as qualitative observation rather than scored evidence.

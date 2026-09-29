# UC-Bench v0.7 — predictor diligence mission

You are the technical diligence team for a locked baseline-biopsy transcriptomic predictor of week-6 response to first infliximab in ulcerative colitis. Decide whether investment should advance, pause, or stop. A high-performing predictor is not required; correctly containing invalid or inadequate evidence is success.

The workspace contains primary records, sponsor assertions, locked predictions, preprocessing records, execution logs, and a neutral catalogue of follow-up packages. Sponsor assertions are claims to test. The validation outcomes and purchased package are revealed only through environment actions.

Use the supplied tools to investigate and calculate. Do not rely on literature recall. Do not infer treatment effect from prognostic performance.

## Required sequence

1. Inspect the evidence and save `C1`, identifying the analysis unit, counts, timing, dependence, sites, material findings, harmless anomalies, and the files supporting them.
2. Commit `C2` before reveal. Prespecify the analysis unit, preprocessing fit scope, uncertainty method, discrimination/calibration/utility metrics, decision criteria, and competing explanations.
3. Reveal outcomes, independently calculate the planned quantities, and save `C3`.
4. Compare follow-up packages. In `C4`, state what at least two possible results would mean before selecting at most one package within budget.
5. Purchase the chosen package—or explicitly purchase `none`—analyse what is returned, and save `C5` with the initial and final decisions, belief change, supported claims, unsupported claims, and remaining uncertainty.
6. Submit.

The five checkpoint payloads are JSON objects, but their internal organization is flexible. Nested and flat results are accepted. Clear annotated labels and explicit unresolved values are accepted. Scores depend on scientific properties, calculations, action history, and supported claims—not exact prose or field order.

Alternative valid statistical methods are welcome when they preserve patient dependence, site structure, the committed estimand, and the intended-use decision. A cautious stop, conditional decision, or justified no-action policy is valid when supported by the evidence and proportionate to risk, cost, and delay.

Changing the locked evidence, changing the validation plan after reveal, exceeding the resource budget, or attempting to access private grader data terminates the mission. Completion reliability is reported separately from scientific work quality.

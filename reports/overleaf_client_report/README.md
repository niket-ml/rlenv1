# UC-Bench client-facing case report

Upload `main.tex` to Overleaf and compile with **pdfLaTeX**. The document is self-contained: no external figures, bibliography, data or shell escape are needed.

The layout is designed as eleven pages:

- High-level overview and the shared investigation (1 page).
- Case 1: task, score chart, numerical results, progress map and error analysis (3 pages).
- Case 2: task and schematic; results; failure diagnosis (3 pages).
- Case 3: task and schematic; reference evidence and evaluation questions (2 pages).
- Case 4: task and schematic; reference evidence and interpretation (2 pages).

The report follows a continuous narrative from the research team's decision through the four cases. It distinguishes the AI agents from the fixed treatment-response predictor. It explains statistical terms where the results first require them. The cases are independent episodes, not successive steps in one study. There is no internal version history or engineering appendix.

The report contains 13 figures, including two score charts, two colour-coded progress maps, a site-performance comparison, reference-result plots and workflow diagrams. Five compact tables retain numerical results and costs. Missing scores are not drawn as zero bars. Figure colours also have text labels. Case 3 and Case 4 plots show reference calculations, not agent performance. Captions remain short.

The rewrite follows the attached ASD-STE100-inspired skill in its explanatory-prose mode. It uses short sentences, consistent terms and explicit qualifications. The official dictionary and the skill's referenced lint script were not supplied. This is not a claim of certified ASD-STE100 compliance. Necessary scientific terms remain in the report.

Results are drawn from the latest main-thread completion message and local evidence as of 14 September 2026, including `reports/UC_BENCH_CASE2_MMMVP_V1_RELEASE.md` and `artifacts/uc_bench_case2_mmmvp_v1/release_freeze.json`. Case 2 is now finalized; all four results remain unchanged, and no additional model attempts were made during finalization. Cases 3 and 4 explicitly distinguish numerical references from measured model results. Preserved historical scores are not overwritten in the source project. Different scoring denominators between Cases 1 and 2 remain disclosed where necessary for interpretation.

Model names are replaced with consistent numbered identifiers in all results, headings and narrative. A small identification key appears at the end of the paper. Only Models 1–4 appear. The provider-interrupted attempt is omitted from this client-facing comparison as requested, without changing the underlying records. Attempt numbers are distinct from model numbers. This is presentation masking, not a claim of blinded evaluation.

Static checks cover LaTeX structure, model-name masking, caption numbering and removal of the excluded model. Chart values follow the numerical evidence already inspected for the report. No local TeX compiler is available. The first PDF compilation and visual check must occur in Overleaf. Eleven pages is the designed layout, not a locally verified rendered count.

This document contains case answers and belongs outside agent-visible evaluation workspaces.

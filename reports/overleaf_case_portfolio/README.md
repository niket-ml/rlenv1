# UC-Bench portfolio report for Overleaf

## Compile

1. In Overleaf, create a **Blank Project** or choose **Upload Project** and upload the ZIP.
2. Use `main.tex` as the main document.
3. Select **pdfLaTeX** and a recent TeX Live version (2024 or newer).
4. Click **Recompile**. Overleaf normally resolves the table of contents and references automatically; recompile again if needed.

The source is completely self-contained: TikZ/PGFPlots diagrams, chart, tables and bibliography are embedded. No external images, data, API credentials, shell escape or BibTeX step are needed.

## Contents

- Task setting, observations, tools, lifecycle and ten professional milestones.
- Shared artifact-dependency diagram and separate branch diagrams for all four cases.
- Case 1 accepted RC6 results, all scientific properties, numerical outputs, decisions, failure analysis and provenance.
- Case 2 historical versus repaired results, strict properties, diagnostic partial points, numerical calculations, first failures, resource choices and completion friction.
- Request, token, cost and available duration metrics, with differences in denominators and counters disclosed.
- Case 3 implemented development candidate, both controlled returns, reference calculations, controls and further work.
- Case 4 existing historical assets, stored reference values and unresolved release work.
- Failure/intervention research agenda, limitations, release hashes and local evidence references.

There are eight figures and twenty tables (including multipage tables).

## Evidence cutoff and important qualifications

Prepared from local artifacts inspected on **14 September 2026**. Case 1 is accepted final RC6. The inspected Case 2 packaging manifest still says `candidate_unfrozen`; accepted repaired scores are explicitly development-verifier replays, not overwritten frozen results. Case 3 is a locally validated, unfrozen candidate. Case 4 remains a historical packet requiring current release validation.

This is a researcher-facing report containing case outcomes and reference answers. **Do not place it in an agent-visible evaluation workspace.** The ZIP contains only report source and these instructions, not hidden data, ledgers, credentials or executable environment code.

No model calls, release modifications, freezes or tests of the scientific environment were performed to create this report. Figures use inspected values, not invented measurements. Missing empirical uncertainty, repeated-seed results and intervention effects are labeled unavailable.

## Document validation

Static checks passed for balanced braces, nested environments, citation keys and cross-reference targets. Diagram positions were constrained to the page width. A TeX engine is not installed in the local workspace, so the document has **not been compiled or visually inspected as a PDF locally**. Its first rendered compilation is in Overleaf.

The exact scientific/source contracts remain authoritative; the report explains them rather than reproducing every schema field. Repository evidence paths in the bibliography are references and are not compilation dependencies.

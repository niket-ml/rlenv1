# Workspace cleanup — 28 September 2026

## First pass

Documentation and navigation cleanup of the accepted project state. No scientific code,
case, score, contract, model result or release was changed. No files were deleted or
moved out of an evidence path. No network request, paid call or model execution was made.

## Changes

- Replaced the outdated root README with a current project entry point and folder map.
- Replaced the reports placeholder index with links to accepted results and deliverables.
- Added `docs/CURRENT_RESULTS.md`, including the supplemental GPT-5 Case 2 run.
- Kept Model 3 attempt 2 outside the requested comparison; its evidence remains archived.
- Distinguished old Case 3/4 model records from current-candidate calibration.
- Recorded Case 2's final frozen status, superseding earlier portfolio/candidate prose.
- Preserved both previous README files byte-for-byte under `docs/history/`.
- Added the existing local virtual environments and `.venv 2` alias to `.gitignore`.

## Preservation

The original root README SHA-256 is
`e90f2760f8692e4e8ea3e8cc7dda581b2aa536f5e720ff17321382b94d92dd88`.
The original reports README SHA-256 is
`6a8d183d8013a26e9e9e26af8f6cc485facbbd20b17670cc7590e5b5d774fd6b`.

Before/after inventories compare paths, sizes, modification timestamps and symlink
targets in `src`, `scripts`, `tests`, `configs`, `tasks`, `grader_private`, `artifacts`,
`build` and `development`, excluding interpreter/test/lint caches. All inventories
match. This is a metadata comparison, not a full content hash of the roughly 28 GB of
historical evidence. The release checks separately verify their declared content hashes.

Case 1 RC6 freeze-file SHA-256:
`bfcb34bdccedbadd4527c426cba5b11ce8f804d4d5757509004b8258e4bd5443`.
Case 2 MMMVP freeze-file SHA-256:
`a66ce1d854b45db6d3073df3296f37288c6a3bc8f9a6a254a27c2e1ee250e3d8`.
Both freeze files and the Case 3 development-candidate file are unchanged.

## Verification

- Case 2's read-only production release verification passed with digest
  `0037e04cbbef71bbe4f50063cb7b62ca68a043824f0fd2f15d6cf79ae605c6bf`.
- Case 1's read-only production release verification passed with digest
  `a1795f1be20b02bb02d86516a664a3d62aed7d6ca716bdd45cb277b4c1ea6d19`.
- Both archived README content hashes match their originals exactly.
- All 35 local links in the new navigation/results pages resolve.
- Git ignores the local credential file and all three existing environment paths.
- Before/after protected inventories match; the recorded fingerprints are in
  `workspace_cleanup_2026-09-28_inventory.json` beside this report.
- Scientific tests were not rerun for this documentation-only change. Historical test
  results remain attributed to their original release receipts.

## Local setup observations

The `.venv.nosync/bin/python` interpreter runs Python 3.11.15. The historical `.venv`
alias is missing; the existing `.venv 2` symlink and offloaded backup remain in place.
Current runbooks use `.venv.nosync/`. No dependency installation or environment rebuild
was performed.

Git currently has no commits. Existing local evidence and manifests remain intact;
this cleanup neither initializes a commit history nor publishes repository contents.
The large `build/` and `artifacts/` directories contain referenced scientific evidence
and were not treated as disposable caches.

## Follow-up: simpler documentation and redundant files

The user requested plainer writing and removal of redundant files. The root README,
reports index and results page were shortened. The results tables now use consistent
two-decimal costs and scores, with links to the exact source values.

Removed:

- `reports/overleaf_case_portfolio/uc_bench_case_portfolio_overleaf/README.md`
- `reports/overleaf_case_portfolio/uc_bench_case_portfolio_overleaf/main.tex`
- The empty extracted folder containing those two files.
- Root `.pytest_cache/` and `.ruff_cache/` (92 rebuildable cache files).
- `reports/.DS_Store` and `reports/overleaf_case_portfolio/.DS_Store`.

Both extracted report files were byte-identical to the files in their parent folder
and the retained Overleaf ZIP. They can be restored from either copy. No references
to the removed extracted directory were found in code, documentation or development
records. Test/lint caches and Finder metadata are generated again when needed.

Scientific code and evidence stayed at their existing paths. No model or scientific
test was run for this follow-up.

Follow-up verification passed: all 27 current navigation links resolve; the protected
directory inventories match the first-pass baseline; the Case 1/2 freeze files and
Case 3 candidate content hashes are unchanged.

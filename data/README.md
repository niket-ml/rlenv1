# Data area

Public GEO series matrices and platform annotations are pinned in
`configs/data_sources.json`. Recreate the ignored local data with:

```bash
make data-download
make data-audit
```

- `raw/` will contain immutable source downloads and is ignored by Git.
- `processed/` will contain deterministic task views and is ignored by Git.
- Every download is pinned by URL, filename, byte size, and SHA-256 before it is
  admitted to an episode.
- GSE92415 outcome labels belong in `grader_private/`, never in an agent-visible
  task image.

v0 deliberately uses the source-deposited normalized series matrices rather
than claiming to re-normalize raw CEL files. The task may audit alignment and
downstream analysis, but it must not award credit for an unexecuted raw-data
normalization claim.

# RC1.4 provenance incident and Case 1 lineage reset

- Frozen RC1.4 expected SHA-256 for
  `artifacts/mmmvp_open_rc14/archived_submission_replay.json`:
  `ea3016898d698c5f3e311fb4edb9c20d29a791c38649b723a2cfe90834847c08`.
- Surviving SHA-256:
  `23f02a2fbf2f63b74886a9bde9e38a8bac5211e143e8861e8a8bf2c85093562c`.
- The original bytes are unavailable after an old diagnostic test rewrote the
  timestamped artifact in place.
- The surviving artifact is preserved unchanged. It is not repaired, recreated,
  deleted, or treated as valid frozen evidence.
- RC1.4, RC1.5 and RC1.6 remain non-authoritative historical development evidence.
- `uc-bench-case1-pilot-v1-rc1` is a disclosed new provenance root prepared from the
  audited RC1.7 candidate source digest
  `a1b4f569ba2b86c06b64e96706ad5f5a23e38976b58caaa42d814c2d4a8e23da`.
- The new root does not claim an unbroken cryptographic lineage from RC1.4–RC1.6.
- No runtime or freeze check in the new release may read the compromised artifact.

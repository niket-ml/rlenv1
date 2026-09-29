# UC-Bench Case 2 MMMVP v1 release

## Decision

`uc-bench-case2-mmmvp-v1` is approved for freezing with aggregate release digest
`0037e04cbbef71bbe4f50063cb7b62ca68a043824f0fd2f15d6cf79ae605c6bf`.

The scientific case, public evidence, hidden truth, resource returns, prompts, tools,
action order, required calculations, tolerances, alternative workflows, integrity
rules, score weights, budgets and model/provider policy are unchanged. The immutable
predecessor remains `uc-bench-case2-graceful-failure-v1-budget1`, digest
`3233cff94612fa75d80ebbe80468df5a4c73a0ead64d8d7327c01825d3436b4c`;
all 354 recorded predecessor files still match.

## Exact permitted integration diff

The sole production verifier is
`uc_bench.case2_mmmvp_v1_verifier.grade_case2_submission`. It delegates to the locked
optionality scorer, which delegates to the locked representation/rounding scorer and
then the unchanged scientific verifier chain. The only grading behavior incorporated
is:

1. a representation or rounding warning cannot erase independently verified,
   within-tolerance scientific credit; and
2. optional or diagnostic work cannot invalidate required work unless it conflicts
   with required evidence/scope, is required by a disclosed property, or is cited by a
   disclosed machine field for a decision-critical claim.

Required discrimination uncertainty remains strict. The runner binds both live and
replay grading to that one entry point. It also verifies archived predecessor records
from their explicit file lists rather than allowing the predecessor's historical
`src/uc_bench/*.py` glob to absorb future successor files. That containment changes no
scientific behavior. All other new code is packaging, replay, CLI, documentation or
packaging-path testing.

## Packages

- Agent-visible: 25 source files; public workspace, contracts, methods, tolerances,
  resource catalogue and minimal interface only.
- Host-only: 406 files; private evidence, returns, canonical verifier, lifecycle,
  controls, replay and release enforcement.
- Evidence: 1,292 files; all four raw trajectories and ledgers, accepted and rejected
  development evidence, repair policies, reports, receipts and hashes. The evidence
  files are regular APFS copy-on-write clones, not symlinks, and are never mounted into
  the agent workspace.

## Verification

- Locked rounding/authority controls: 33/33 passed.
- Locked optionality controls: 54/54 passed.
- Accepted complete Case 2 closure: 503/503 passed.
- Exact final package tests: 6/6 passed.
- Exact-package scientific/lifecycle checks: 15/15 passed, including two materially
  different valid workflows, wrong science, altered-input hard-coding, malformed and
  incomplete work, provider exclusion, deterministic regrading, replay, numerical
  recomputation, filesystem/network isolation and secret redaction.
- Active release lint: passed.
- Project doctor: passed.
- Case-specific audit consistency: passed.

A deliberately broader repository run was interrupted after 827 tests with two
unrelated RC1.4 legacy-freeze failures. A 509-test root-tree Case 2 rerun reported 28
instances of the same obsolete dynamic-closure mechanism. No scientific or new
verifier assertion failed. Both outputs and an incomplete isolated-rerun attempt are
retained as rejected/intermediate validation evidence; they are not presented as
passing release gates. The exact packaged runner avoids that legacy mechanism and its
tests pass.

## Replay parity

| Preserved trajectory | Partial quality | Strict mission | Reliability | First scientific failure |
|---|---:|---|---:|---|
| Gemini | 16.129032 | fail | 0 | none before noncompletion |
| GPT-5.1 | 65.909091 | fail | 100 | prospective design and integrity |
| Historical Sonnet | 61.290323 | fail | 0 | discrimination and uncertainty |
| Fresh Sonnet | 77.419355 | fail | 0 | context robustness |

All four match the separately preserved accepted development replays. No mission
result changed and no genuine scientific failure was rescued. Raw trajectory tree
digests remain `1c6f78ae7cb7d1dc2a3b769e4565303483f88343c635ffd8fd172242463b1f70`
and `ce9bc6ab36cfd947271c0db551d23c6356b93be26103a5fd113af9c8a7d2f9b8`.

## Anti-overfitting, leakage and reproducibility

The complete active grader contains zero model/provider, run-ID, historical-path,
historical-score or score-target hits. Eighty-one resource-ID occurrences were
inspected and are derived from the public resource contract/returns, not trajectories.
Public leakage scans found no grader, truth, trajectory, expected-result, credential
or exact hidden-file content. Archives contain no symlinks, absolute paths or traversal
members. Docker networking is disabled; internet access cannot expose local host-only
files. No claim is made about pretraining contamination.

Two clean builds and the final candidate were identical. Archive hashes are:

- agent-visible: `e323eefdb14fca0110a26e52b78345c81c18d01b49a7a937d3dfdfdfe3ed8a07`;
- host-only: `995bc146ddae8efd2149122851c2c46927a1bfb93ed8c289a0d5bbcaba72c964`;
- evidence manifest: `7273be507920f7c45df2485588ac16402fc25d7fdca158d3a2c92614b7510e27`.

## Commands

```bash
PYTHONPATH=src:. .venv.nosync/bin/python scripts/package_case2_mmmvp_v1.py --verify
PYTHONPATH=src:. .venv.nosync/bin/python scripts/run_case2_mmmvp_v1.py --fake
PYTHONPATH=src:. .venv.nosync/bin/python scripts/replay_case2_mmmvp_v1.py
```

One later real episode requires explicit authorization and the frozen digest:

```bash
PYTHONPATH=src:. .venv.nosync/bin/python scripts/run_case2_mmmvp_v1.py \
  --execute --model-id MODEL_ID --maximum-incremental-cost-usd CAP \
  --authorization-digest 0037e04cbbef71bbe4f50063cb7b62ca68a043824f0fd2f15d6cf79ae605c6bf
```

## Disclosed limitations

Controls are internally authored, not external expert validation. Only four natural
trajectories have been inspected. Repeated seeds are required before comparing models.
The current contract cannot cite an uncertainty sub-result separately from its
containing calculation. This is one MMMVP case, not a broad computational-biology
benchmark, and no stable model ranking is claimed.

This packaging pass made no model call, network call or API spend.

**CASE 2 MMMVP PACKAGED AND FROZEN — REPEATED-SEED CALIBRATION DEFERRED**

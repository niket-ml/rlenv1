# Stage 6 evidence states and difficulty ladders

Decision: **the symmetric evidence-state and controlled-variant gate passes**.

Four state families exercise all three terminal decisions:

| State | Required terminal behavior | Why it exists |
|---|---|---|
| Authentic GSE92415 weak transfer | `insufficient_evidence` | Real biological result, reported separately |
| Controlled sufficient evidence | `advance` | Penalizes universal abstention |
| Recoverable feature dropout | repair, then `advance` | Separates recovery from blanket stopping |
| Irrecoverable identity conflict | `stop` | Penalizes AUC chasing and universal advancement |

The sufficient state is explicitly a synthetic power-and-decision positive
control, not an invented UC result. Its pinned Gaussian evidence simulator
produces n=240, AUC 0.846, 95% bootstrap interval 0.795–0.896, and permutation
p=0.0005. It exists only to test whether the agent follows a positive evidence
state when the frozen threshold is clearly met. It must never appear in the
authentic-biology result section.

Policy controls across the four states score:

| Policy | Score | Pass threshold |
|---|---:|---:|
| Always insufficient | 15 | 60 |
| Always advance | 35 | 60 |
| Always stop | 15 | 60 |
| AUC chaser | 35 | 60 |
| State-aware reference | 100 | 60 |

Five deterministic private transformations operate on actual cohort-shaped
data and retain an audit record without releasing affected sample IDs:

- confounding correlation: 0.0, 0.3, 0.5, 0.7;
- label-noise fraction: 0, 0.05, 0.15, 0.30;
- cross-class sample swaps: 0, 1, 3, 6 pairs;
- exact duplicate contamination: 0, 0.05, 0.15, 0.30;
- reference-feature dropout: 0, 0.10, 0.30, 0.50.

All achieved-strength summaries are nondecreasing. Feature dropout is discrete
for a five-gene panel and therefore resolves to 0, 1, 2, and 3 missing genes.
Breaking-point curves remain diagnostic; no controlled transformation is a
headline biology claim.

Evidence:

- `configs/evidence_states.json`
- `configs/variant_ladders.json`
- `src/uc_bench/variants.py`
- `artifacts/variants/scenario_controls.json`
- `tests/test_variants.py`

Replay commands:

```bash
make variants
make check
```

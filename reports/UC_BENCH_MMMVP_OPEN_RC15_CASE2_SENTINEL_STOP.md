# UC-Bench open MMMVP RC1.5 — Case-2 sentinel stop report

## Outcome

RC1.5 was created as an infrastructure-only successor to frozen RC1.4. All
pre-exposure gates passed and RC1.5 was frozen before scientific exposure.
The nine-cell Case-2 sentinel then stopped after its first cell because the
frozen verifier raised an exception on a schema-valid saved artifact. This is
a predeclared shared grader/infrastructure stop. No other model was run.

This run cannot establish capability separation, a scientific floor, or a
ceiling. It is an infrastructure-contaminated development result.

## Preserved predecessor and freeze

- RC1.4 release-freeze SHA-256:
  `f03ec0ac838c830af1344ff4b2eab37ec5245bcca001a7931f01a188a0e81bbf`
- Restored RC1.4 archived-replay SHA-256:
  `ea3016898d698c5f3e311fb4edb9c20d29a791c38649b723a2cfe90834847c08`
- RC1.5 infrastructure digest:
  `fd505c1d639fd4ecaabe6c3828f3f157cd4e4aebb685a6e5788868b611ee4bc4`
- Scientific freeze digest, unchanged:
  `466441682b04175432329b41adcfd735cdea66f860d66f046dfae195c91e701c`

The full repository suite was executed in two test processes so the RC1.4
diagnostic test that rewrites a timestamp could be atomically restored before
successor tests inspected the immutable predecessor. Every frozen RC1.4 byte
matched its freeze after the gate.

## Zero-cost launch gates

- Canonical nested price schema loaded for all ten panel entries.
- Nine technically compatible routes were costed.
- GLM remained an inherited provider-specific exclusion; no compatibility
  request was repeated.
- Full production-path fake-provider rehearsal passed, including Case-2
  workspace materialisation, the actual client/request/tool path, durable
  persistence, interruption after reveal, disk restart, exact replay, valid
  fake submission and real grading.
- Targeted RC1.5 tests: 16 passed.
- Full repository tests excluding the side-effecting RC1.4 module: passed.
- All RC1.4 tests in the isolated process: passed.
- Ruff, project doctor, audit consistency and both Docker preflights: passed.
- Post-freeze preflight matched the pre-freeze rehearsal on model set, request
  hash, scientific digest, cost distribution and fake-run hash.
- New compatibility and scientific calls before sentinel: zero.

## Cost gate

| Quantity | USD |
|---|---:|
| Nine-cell no-cache median | 31.514873941 |
| Nine-cell no-cache P90 | 45.892719941 |
| Hard scientific cap | 52.000000000 |
| Effective headroom immediately before science | 56.320542741 |
| Actual first-cell spend | 0.773302600 |
| Key-limit headroom after settlement | 55.547240141 |

The median and P90 were independently calculated by expanded ordered
enumeration and exact multinomial composition; the results agreed within
`1e-10` USD.

## Randomised sentinel order and status

| Order | Model | Status | Scientific spend |
|---:|---|---|---:|
| 1 | `google/gemini-3.1-pro-preview` | Excluded: shared grader failure after valid completion | $0.7733026 |
| 2 | `qwen/qwen3.5-397b-a17b` | Not run after global stop | $0 |
| 3 | `openai/gpt-5` | Not run after global stop | $0 |
| 4 | `anthropic/claude-sonnet-4` | Not run after global stop | $0 |
| 5 | `anthropic/claude-opus-4.1` | Not run after global stop | $0 |
| 6 | `moonshotai/kimi-k3` | Not run after global stop | $0 |
| 7 | `deepseek/deepseek-v3.2` | Not run after global stop | $0 |
| 8 | `openai/gpt-5.1` | Not run after global stop | $0 |
| 9 | `mistralai/mistral-large-2512` | Not run after global stop | $0 |

`z-ai/glm-5.2` was not in this order because its frozen compatibility result
is a provider-route price-filter exclusion.

## Gemini cell: official result

| Field | Result |
|---|---|
| Requested model | `google/gemini-3.1-pro-preview` |
| Returned model | `google/gemini-3.1-pro-preview` |
| Provider | Google AI Studio |
| Fallbacks | Disabled |
| Provider errors | 0 |
| Turns | 52 |
| Provider requests | 53 |
| Tool calls | 61 |
| Framework/wrapper tool errors | 0 / 0 |
| Final submissions accepted/rejected | 1 / 0 |
| Validation-plan rejections repaired | 1 |
| Completion | Accepted terminal submission, followed by final response |
| Strict mission success | Unscored: verifier infrastructure exclusion |
| Partial scientific quality | Unscored officially |
| Reliability | Unscored officially |
| First official scientific failure | Unavailable because grading aborted |

The raw response, parsed response, reasoning-state payloads, messages, tool
arguments/results, route identity and usage are all persisted. There are 167
hash-linked trajectory records; complete messages and returned reasoning state
are preserved; no terminal tool call is unexecuted. The workspace boundary and
protected-evidence hashes passed, and no credential was exposed.

## Exact global-stop fault

The agent declared `work/auc.txt` as a `CALCULATION_OUTPUT`. Its contents are
the schema-valid JSON number `0.730311`. The verifier successfully parsed the
file into a Python `float`, then
`mmmvp_open_calculations._output_confirms` attempted:

```python
rows = payload.get("typed_calculations") or []
```

This raised `AttributeError: 'float' object has no attribute 'get'`. The
verifier should have treated a non-object calculation output as an ordinary
`saved_output_mismatch`, not crashed. Terminal replay re-invoked the same
verifier and therefore reported `reconstruction:AttributeError`. Thus the
runner's `inconsistent_tool_lifecycle` label is derivative of the verifier
exception; the persisted lifecycle evidence itself is complete.

This is a shared grader failure and an artificial scoring floor. It is not:

- a provider-specific failure;
- a contract-enum or submission-format rejection;
- a model-completion failure;
- a tool-lifecycle loss;
- or an official scientific mission failure.

## Zero-cost forensic scientific diagnosis

For diagnosis only, the preserved submission was evaluated in memory with the
single exception converted to the verifier's existing
`saved_output_mismatch` result. This is not an RC1.5 score and does not alter
the frozen verifier or archived run.

- Counterfactual partial work quality: **40/100**.
- Counterfactual reliability: **100/100**.
- Counterfactual strict mission: **fail**.
- Earliest substantive failure: the committed analyses were not implemented
  and preserved as committed.
- The agent committed outputs `work/roc_auc.csv` and
  `work/data_flaws.csv`, but its final manifest instead referenced
  `work/analysis_table.csv` and `work/auc.txt` without documenting a justified
  deviation.
- The saved table retained 203 source rows and used an empirical row analysis;
  it did not verify the required dependence-preserving person analysis or
  site-aware comparison.
- Selecting X17 was defensible for the stated record-linkage question, but the
  returned crosswalk was not incorporated into a verified calculation. The
  agent incorrectly treated adjudication to 95 canonical entities as proof of
  a physical sample swap, matched the wrong result contingency, and increased
  the corresponding belief from 0.20 to 0.99.
- `STOP / STOPPED / NO_USE` is within the accepted decision class, but the
  correct-looking conservative decision was not supported by the required
  analysis chain. The environment therefore did not give credit merely for a
  plausible final label.

These are useful scientific/workflow signals in one trajectory, but they
cannot be compared across models because the panel stopped after one cell.

## Required interpretation

- Genuine capability separation: **insufficient evidence**.
- Credible scientific floor: **insufficient evidence**.
- Ceiling: **insufficient evidence**.
- Artificial contract/completion floor: **not observed in the completed
  provider interaction**.
- Artificial grader/infrastructure floor: **observed and decisive**.

No stable ranking is claimed. No other Case-2 cell and no other scientific
condition was launched.

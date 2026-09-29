# Case 3 MMMVP: zero-cost local readiness

**CASE 3 LOCALLY VALIDATED — MODEL CALIBRATION PENDING**

Go for a separately authorized bounded internal calibration, not for public benchmark claims.
Final gates: **102 focused tests passed; 1,178 repository tests passed, with exactly the two
previously accepted RC1.4 provenance failures and no new failures**. Lint, formatting, doctor,
audit consistency, archive preservation and Case 1/Case 2 closure checks pass. The old failures
are `test_schema_inventory_and_compatibility_inheritance_are_zero_cost` (RC15) and
`test_rc16_gate_protects_the_complete_inherited_rc14_surface`; both report the pre-existing
`Frozen RC1.4 infrastructure changed` incident. No archived repair was attempted.

Development execution closure: `2083d5fd4380b3da933dc78e39bbcadb883eb18ce9bda66e4c3247a3ad5ab9ae`.
The final candidate and acceptance receipt bind the full closure, test XML and report evidence.

Final acceptance status and test receipts are recorded in the adjacent
`artifacts/uc_bench_case3_mmmvp/local_validation_01/` evidence bundle. This is an **unfrozen
development candidate**, not a release freeze. No Case 3 model call has been made.

## 1. Materialization and provenance

The authoritative return is the **existing modern executable/open X31 generation**. Original
v0.7/v0.8 static replay predictions and stored metrics are historical material only. No dataset,
condition, coefficient, outcome or archived trajectory was modified or generated anew.

| Layer | Authoritative source / interpretation |
|---|---|
| Starting cohort and export | `tasks/hard_suite_v07/development/case_03`; 122 baseline records, 112 provisional fingerprint groups, 10 repeat groups |
| Intended use and gates | Existing `intended_use.json`; threshold 0.5 and existing performance gates unchanged |
| Endpoint | Existing sealed `validation_outcomes.csv`, binary central-clinical-review response, day 35–49; public source ledger retains two discordances |
| Executable identity | `grader_private/mmmvp_open_rc1/case_03/X31/frozen_model.json`, byte SHA `f26fd37d1e1f2b34f783003b66b78697c0ef9bf459a1097683bb3b4677b6d8a4` |
| Predictor | Existing model ID `uc-lock-2026-07-clean-replay-rc1`; features IFN_score, epithelial_score, library_size_log10; coefficients [1, −0.2, 0.05], intercept −0.15, logistic link |
| Fit input | Existing 180 training rows; SHA `af8bd86e5d94e0d5691099b5fc58663e9bfe6adb5fc24aa14178c86007041065` |
| Preprocessing | Existing featurewise training-reference mean and sample standard deviation; code, feature order, fitted centers/scales and hashes independently checked |
| Collapse input | SHA `1ac44479974d602cfdd415ee083738569f140e831d6c741c42f57bf855fa4c75` |
| Remains input | SHA `393be42569ad07219d0e9ba0d96e6e51eac2743352b39ef888eec974b5f41608` |
| Generator | Existing `src/uc_bench/mmmvp_open_interventions.py`, SHA `a47e9fdba8c5589bf2b7df9ada90b8bffa5b092a0b923f0c8c4b698db588fae8` |
| Returned evidence | Predictions, frozen model, training/validation inputs, execution code, fitted lineage and a new accurate materialization manifest; per-return hashes in `reference_results.json` |
| Original identity | Old manifest preserved as `model/legacy_export_manifest.json`; historical equivalence to the executable predictor is explicitly unestablished |

The original export's claimed weight hash does not identify this executable. The new manifest
identifies actual bytes and does not authenticate the original export. Its suggestive model ID
is expressly an unvalidated label, not proof of clean execution.

The complete original/modern source preservation baseline contains 38 hashes and is checked
independently of the Case 2 frozen closure. Archived static X31 files remain preserved but do
not supply expected metrics to the new grader.

**Important causal limitation:** the paired modern inputs differ in patient–feature association,
not only preprocessing fit scope. A collapse is not proof that leakage caused the original
performance, nor that anti-TNF prediction is biologically futile. A retained result cannot
retroactively validate the original export. This distinction is explicitly graded.

## 2. Neutral environment and artifact dependency chain

```text
Same public start in both conditions
  cohort + predictions + source ledger + fit membership/config + logs + intended use
      │
      ├─ audit population, provisional units, endpoints and generation provenance
      │
      └─ choose estimator / justified exclusions / uncertainty plan
              │ irreversible plan commitment; public source hashes bound
              ▼
         reveal outcomes → save source-linked table + original calculations
              │ judge eligibility separately from impressive performance
              ▼
         declare unresolved question and one resource (or none)
              │ irreversible follow-up commitment
              ├─ none → evidence-supported bounded hold / stop / targeted audit
              ├─ X17 / X24 / X46 / X58 / X63 → audit return and remaining limits
              └─ X31 → actual executable return
                           ├─ collapse → hold / end current predictor / further audit
                           └─ retained signal → cautious hold OR independent-validation step
              ▼
         final bounded decision + traceable artifacts → private independent verification
```

The 19-file pre-purchase public trees are byte-identical. Public-start digest:
`2515f2963cb06cdda331ff1159ae9b8cc75daa37398b0412391f65a001bd180a`.
Only the sealed X31 return distinguishes the two conditions.

Tools are the same nine operational capabilities: list/read/write files, run local code,
commit validation plan, reveal validation, commit follow-up plan, purchase one resource or
none, and submit. There is no public scientific grader or score feedback. A standard-library
shape validator exposes every required field/enum and gives recoverable structural feedback.
Any artifact filenames are allowed through relative evidence paths; derived files stay in
`work/`. Source files are protected. Private truth, ledgers, credentials and verifier stay
outside the Docker workspace; network is disabled and the root filesystem is read-only.

## 3. Meaningful choices and accepted alternatives

| Evidence/workflow | Accepted bounded decisions | Unsupported extension |
|---|---|---|
| Original evidence unestablished or ineligible; no purchase | Hold/insufficient evidence; end current predictor claim; continue targeted audit | Treat high original AUC as eligible validation; claim clean recovery |
| X31 collapse, independently calculated | Hold; stop this predictor; investigate a remaining question without asserting performance | Progress to independent validation on failed ranking evidence; broad program futility |
| X31 retained ranking evidence | Continue toward independent validation with external gates; cautious hold | Automatic probability use, clinical use, treatment benefit or transport |
| X46 separate external package | Audit attributed calculations, or a provenance-limited hold without calculating unattributed predictions | Claim target-predictor transport without its missing identity linkage |
| X17 / X24 / X58 / X63 | Relevant identity, endpoint, precision or methods investigation and bounded hold | Assume a purchased package rehabilitates the original export |

Three estimands are implemented and reference-tested: group-mean predictions, first baseline
record per group, and inverse-group-size-weighted rows. All bootstrap whole provisional groups.
Two endpoint approaches pass: retain primary central review with disclosed discordance, or
prospectively exclude documented discordant groups. Repeated records as independent people fail.

No private final-action or resource whitelist overrides supported work. Resource relevance is
a disclosed question-domain/path check, not a proven optimal-value-of-information calculation.
Buying X31 is not required. A universal *answer-only* action policy fails; a genuine completed
audit followed by a cautious hold can legitimately pass either condition.

## 4. Score-source table

Ten equal scientific properties. Each property has independently reported subchecks; missing
dependent evidence cannot erase unrelated correct work. The clean-return property is N/A if
X31 was not obtained, and applicable weights are renormalized. Strict mission success requires
all applicable properties plus an accepted final submission. Belief values and prose are
diagnostic only. No scientific vocabulary/substring matching is used.

| Property | Authoritative scored source and verification | Prose can fail it? |
|---|---|---|
| Intended use / eligibility | Audit population statuses, original eligibility enum and endpoint acknowledgment compared with public metadata/source ledger | No |
| Cohort / dependence | Committed strategy/exclusions; saved source rows, counts, joins, weights and predictions independently reconstructed | No |
| Fit provenance | Saved validation-fit membership and declared reference role compared with raw membership/config; execution/outcome-cause claims checked separately | No |
| Prospective commitment | Host event ordering, commitment hashes, protected and committed input hashes | No |
| Original calculations | Actual saved table plus each AUC/CI, Brier, ECE and net-benefit value independently recomputed | No |
| Containment of original invalidity | Audit eligibility and final original-validation-eligible boolean; later evidence cannot rehabilitate old history | No |
| Follow-up relevance | Committed question domain/evidence paths; actual purchased resource; source-linked return review | No |
| Executable return | Saved X31 analysis table, outcome joins, fit reconstruction, model/input hashes, each result and group uncertainty | No |
| Bounded decision | Disposition, stage, evidence basis and claim-scope enums, independently verified evidence and existing criteria; unresolved-gate/evidence fields must be present when applicable, prose content unscored | No |
| Reproducibility | Protected source hashes and correct primary-table/execution chain | No |

`submission_contract.json` is the exact machine-readable source for required/conditional fields,
types and allowed values. Professional narrative, numeric belief, optional calculations and
presentation choices cannot independently invalidate correct primary work. A malformed primary
number fails its own calculation; correctly saved other metrics and tables retain credit.

## 5. Independent reference evidence

Reference solver uses pandas/sklearn; the hidden verifier independently uses source reconstruction,
weighted pairwise AUC and an independent NumPy execution implementation. Neither imports stored
expected metrics. Executing the disclosed frozen algorithm also reproduces return prediction bytes.

For group means, 100 group-bootstrap replicates, seed 19, 95% percentile interval, ten ECE bins:

| Result | AUC | AUC interval | Brier | ECE | Net benefit at 0.5 |
|---|---:|---|---:|---:|---:|
| Original export, both conditions | 1.0000 | [1.0000, 1.0000] | 0.01487 | 0.11097 | 0.41071 |
| Modern collapse | 0.49736 | [0.41394, 0.61474] | 0.29886 | 0.23148 | −0.02679 |
| Modern remains | 0.73057 | [0.62194, 0.82071] | 0.20702 | 0.12186 | 0.08036 |

These are controlled reference results, not agent scores or new authentic-cohort validation.
The retained case meets the ranking gate but its ten-bin ECE exceeds the existing 0.12
probability-use gate. That threshold was not lowered. Seed/method differences may give other
valid intervals; the agent's committed supported method is used by verification.

Six persisted reference workflows (two conditions × three estimands) each pass at 100.
No target low partial score has been imposed.

## 6. Controls, attacks and graceful failure

Focused suite covers:

- Distinct valid estimands, both endpoint policies, hold/stop/audit/conditional progression and
  every existing resource under a relevant bounded hold.
- Invalid original eligibility, unsupported outcome-causation claim, independent repeated
  records, mixed generations, copied paired results, missing clean evidence, restored original
  validity, advancing after collapse, clinical/transport/benefit/futility overclaim.
- Correct final decision with no saved analysis; placeholder tables; generic final policies.
- Changed predictions, labels, fit inputs, fit membership, label source/day, utility threshold,
  identifier renaming and row reordering. Stale answers fail; fresh valid calculations pass.
- Malformed audit, index, resource and result fields cannot crash grading. A malformed AUC does
  not erase valid table/Brier/ECE/utility/CI credit. A supplied but invalid external result cannot
  masquerade as an absent optional calculation.
- Arbitrary professional paraphrases, diagnostic beliefs and wrong optional calculations do not
  affect scientific scores. Wrong scientific machine claims still fail.

Examples of graceful degradation: unsupported advancement after collapse retains at least 80
partial points; missing final submission retains at least 70 for valid saved work but reliability
zero; a wrong primary AUC fails only original-result reconstruction; malformed external evidence
relied upon fails its own claim support while retaining at least 90 points.

Runtime controls use the actual production request builder, typed pinned adapters, native client
construction, tool dispatcher, Docker boundary, durable ledger, reconstruction and grader with
fake providers. Both conditions run end-to-end. Interrupt/restart is checked after validation
commitment, reveal, follow-up commitment and purchase; no action repeats or disappears. Restoring
under another condition/configuration is rejected before client construction. Replay-grade
mismatch is a replay failure, not a successful reconstruction.

Provider errors/identity drift are excluded; a subsequent healthy cell still runs. Malformed tool
arguments and rejected schema submissions can recover; clean noncompletion has reliability zero
and preserves partial work. Late provider identity failure cannot retain an eligible mission
headline. Credentials are absent from durable JSON, public prompts and workspaces.
The complete final fake-provider run directories are retained in
`production_fixture_runs.tar.gz` in the evidence bundle, including ledgers, workspaces and
restart boundaries; they are not dependent on pytest retaining temporary directories.

## 7. Independent review and remaining limitations

Before implementation, two fresh read-only reviews were locked and hashed:

- Public reviewer A: `case3_mmmvp_initial_review_a.md`, SHA
  `0e17877ce44a904ba44aa24df89b3e716fd254db07afe02205893ee3a8b66646`.
- Invariant reviewer B: `case3_mmmvp_initial_review_b.md`, SHA
  `a8d735c4e78225f72217e7e3118d6011b52709f8fc07405a1d0771a30d634499`.
- Implementation specification SHA:
  `b11973c188cbb9e5011db39a8d7f6709d62bc99fed3071578683e6fec4adc131`.

A saw only public starting evidence, never hidden results or past model answers. B received
purpose/schemas/invariants and later the new implementation, not historical answers or scores.
Neither edited files. Their findings led to explicit bootstrap sampling disclosure, separate
external evidence attribution, malformed-file containment, independent per-calculation credit,
endpoint-source/window enforcement, threshold-sensitive utility, resume identity checks and
fail-closed replay/provider reporting. These were pre-exposure local repairs, not task tuning
against a model score. Final narrow follow-up reviews are recorded separately.

Limitations that remain disclosed, not concealed as difficulty:

1. **Scaffolding:** the packet supplies estimand menus, endpoint policies, metric definitions
   and provenance distinctions. It tests supported scientific workflow choices, not unrestricted
   method invention or completely unaided discovery.
2. **Controlled causality:** the modern paired perturbation is not a clean fit-scope-only causal
   experiment. Neither the old export's history nor biology's ultimate predictability is established.
3. **Conservative success path:** a worked, evidence-supported hold can pass both conditions.
   Buying evidence or optimistic advancement is not forced merely to create model differences.
4. **Coarse intervention grading:** domain relevance and restrained interpretation are tested;
   economic optimality, expert helpfulness and smallest-experiment superiority are not demonstrated.
5. **Limited expert equivalence:** internal independently implemented references and read-only
   reviewers are not external clinical/statistical expert validation.
6. **Small suite:** two controlled outcomes of one case are not independent biological tasks.
   No ranking, training-data deficit, SFT/RL need or rescue effect is identified without model
   repeats and targeted intervention evidence.
7. **Legacy repository:** two accepted historical RC1.4 provenance-check failures remain outside
   this candidate; the repository must show no additional failure before the ready label is used.

## 8. Proposed calibration only—not authorized here

Same permitted routes as the just-completed Case 2 calibration, fallback disabled:

| Requested model | Canonical returned alias | Pinned provider | $/M prompt / output | Base per condition, no cache | Conservative planning proxy |
|---|---|---|---:|---:|---:|
| openai/gpt-5.1 | openai/gpt-5.1-20251113 | OpenAI | 1.25 / 10 | $1.31740625 | $2.107850 |
| anthropic/claude-sonnet-4 | anthropic/claude-4-sonnet-20250522 | Amazon Bedrock | 3 / 15 | $7.47692250 | $11.963076 |
| google/gemini-3.1-pro-preview | google/gemini-3.1-pro-preview-20260219 | Google AI Studio | 2 / 12 | $2.71804750 | $4.348876 |

Costs use actual Case 2 token counts and the verified pinned-route price ceilings. Base is
1.25× observed-token no-cache cost; the conservative proxy is 2×. With one observed episode per
model these are **not empirical medians or P90s**. Same-cache base estimates are separately
recorded in `cost_plan.json`; no funding decision depends on receiving cache discounts.

Recommended staged design: Gemini on both sealed development conditions first, **$10 cap**, then
mandatory replay/grader/contract review. If technically clean, propose GPT-5.1 and Sonnet on
both conditions, staying within **$40 cumulative for six cells**. Six-cell no-cache base is
**$23.0247525**, conservative proxy **$36.839604**. A genuine scientific failure is not a stop
condition; infrastructure, integrity or scorer contradiction is. No model substitutions.

At the recorded $86.764114303 key headroom and $116.764114303 account balance, the prospective
$40 cap needs **$0 top-up**, subject to a fresh funding/availability check before any future call.
Expect roughly 40–75 minutes sequential including execution and manual replay review; providers
and workflow length could extend that. Proposed limits match the evaluated infrastructure:
65 turns, 5,000 output/request, 90,000 total output, 4,200 seconds; medium reasoning for GPT/Gemini,
provider-native for Sonnet, returned reasoning retained, no hidden compaction or fallback.

The candidate currently rejects live/native execution without an injected fake provider. This
run has neither enabled paid Case 3 execution nor frozen a release. The first paid tranche needs
the user's next authorization and a release/funding gate. A clean fake run proves local
integration—not that a real agent will complete the environment.

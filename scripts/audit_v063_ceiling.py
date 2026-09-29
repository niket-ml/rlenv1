#!/usr/bin/env python3
# ruff: noqa: E501
"""Generate the frozen v0.6.3 ceiling and construct-validity audit."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from uc_bench.v063_ceiling_audit import build_v063_ceiling_audit

ROOT = Path(__file__).resolve().parents[1]
AUDIT_JSON = ROOT / "artifacts/diagnostics/hard_suite_v063_ceiling_audit.json"
FINAL_REPORT = ROOT / "reports/generated/hard_suite_v063_final_no_go.md"
EASE_REPORT = ROOT / "reports/generated/hard_suite_v063_ease_map.md"
ADJUDICATION_REPORT = ROOT / "reports/generated/hard_suite_v063_construct_adjudication.md"
REMEDY_REPORT = ROOT / "reports/generated/hard_suite_v063_failure_remedy_matrix.md"


def _short_model(model_id: str) -> str:
    return {
        "openai/gpt-5.6-sol": "Sol",
        "anthropic/claude-opus-5": "Claude",
        "google/gemini-3.1-pro-preview": "Gemini",
        "moonshotai/kimi-k3": "Kimi",
        "openai/gpt-5.2": "GPT-5.2",
    }.get(model_id, model_id)


def _short_scenario(scenario_id: str) -> str:
    return {
        "dev6_clean_progression": "clean",
        "dev6_preprocessing_leakage": "leakage",
    }.get(scenario_id, scenario_id)


def _fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _artifact_matrix(audit: dict[str, Any]) -> str:
    lines = [
        "| Model | State | Reliability | Total | A01 | A02 | A03 | A04 | A05 | A06 | A07 | A08 | A09 | A10 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for cell in audit["cells"]:
        scores = {row["artifact_id"]: row["score"] for row in cell["artifacts"]}
        reliability = 100 if cell["classification"] == "valid_episode" else 0
        lines.append(
            "| "
            + " | ".join(
                [
                    _short_model(cell["model_id"]),
                    _short_scenario(cell["scenario_id"]),
                    str(reliability),
                    _fmt(cell["diagnostic_scientific_score"]),
                    *[_fmt(scores[f"A{index:02d}"]) for index in range(1, 11)],
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def _capability_matrix(audit: dict[str, Any]) -> str:
    caps = list(audit["capability_analysis"])
    lines = [
        "| Capability | Mean | Range | Variance | Ceiling rate | Loss share |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name in caps:
        row = audit["capability_analysis"][name]
        lines.append(
            f"| {name} | {row['mean']:.2f} | {row['range']:.2f} | "
            f"{row['population_variance']:.2f} | {100 * row['ceiling_rate_at_least_95']:.1f}% | "
            f"{100 * row['share_of_total_capability_loss']:.1f}% |"
        )
    return "\n".join(lines)


def _model_capability_matrix(audit: dict[str, Any]) -> str:
    capabilities = list(audit["capability_analysis"])
    model_ids = list(dict.fromkeys(cell["model_id"] for cell in audit["cells"]))
    lines = [
        "| Model | " + " | ".join(capabilities) + " |",
        "|---|" + "---:|" * len(capabilities),
    ]
    for model_id in model_ids:
        rows = [cell for cell in audit["cells"] if cell["model_id"] == model_id]
        values = [
            sum(cell["capability_scores"][capability] for cell in rows) / len(rows)
            for capability in capabilities
        ]
        lines.append(
            f"| {_short_model(model_id)} | "
            + " | ".join(f"{value:.1f}" for value in values)
            + " |"
        )
    return "\n".join(lines)


def _gap_contribution_table(audit: dict[str, Any]) -> str:
    lines = [
        "| Model | Mean gap vs diagnostic strongest | Largest absolute family share | Signed family contributions to mean gap |",
        "|---|---:|---|---|",
    ]
    for model_id, row in audit["family_gap_contributions"].items():
        shares = row["absolute_gap_share"]
        largest = max(shares, key=shares.get)
        contributions = ", ".join(
            f"{name}={value:+.2f}" for name, value in row["signed_score_point_contribution"].items()
        )
        lines.append(
            f"| {_short_model(model_id)} | {row['aggregate_mean_gap_points']:.2f} | "
            f"{largest} ({100 * shares[largest]:.1f}%) | {contributions} |"
        )
    return "\n".join(lines)


def _artifact_stats(audit: dict[str, Any]) -> str:
    lines = [
        "| Artifact | Mean | Range | Variance | ≥95 | Loss share | Diagnostic categories |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for artifact_id, row in audit["artifact_analysis"].items():
        lines.append(
            f"| {artifact_id} | {row['mean']:.2f} | {row['range']:.2f} | "
            f"{row['population_variance']:.2f} | {100 * row['ceiling_rate_at_least_95']:.1f}% | "
            f"{100 * row['share_of_total_artifact_loss']:.1f}% | "
            f"{', '.join(row['ease_categories']) or 'none'} |"
        )
    return "\n".join(lines)


def _execution_table(audit: dict[str, Any]) -> str:
    lines = [
        "| Model | State | Class | Cost | Turns | Tool calls | API wall time | First frozen / adjudicated divergence |",
        "|---|---|---|---:|---:|---:|---:|---|",
    ]
    for cell in audit["cells"]:
        lines.append(
            f"| {_short_model(cell['model_id'])} | {_short_scenario(cell['scenario_id'])} | "
            f"{cell['classification']} | ${cell['cost_usd']:.3f} | {cell['turns']} | "
            f"{cell['tool_calls']} | {_fmt(cell['api_wall_time_seconds'])}s | "
            f"{cell['frozen_first_divergence']} / {cell['adjudicated_first_consequential_divergence']} |"
        )
    return "\n".join(lines)


def render_final(audit: dict[str, Any]) -> str:
    sentinel = audit["sentinel"]
    return f"""# UC-Bench v0.6.3 final sentinel: frozen no-go

## Result in plain language

v0.6.3 is not hard enough in a scientifically trustworthy way. Sol averaged **82.80**, above the predeclared >80 ceiling no-go threshold. Nine of ten cells submitted; Gemini clean used all 65 turns and produced all artifacts but never submitted, so its reliability score is zero and the ceiling comparison is incomplete. The strongest accepted-model audit also concentrated **32.13%** of loss in final decision/recovery, above the 30% gate.

More importantly, this audit found that some apparent errors were not real scientific failures. Agents were penalized for leaving an unverifiable discovery patient count unresolved, for expressing labels with annotations, for nesting valid quantitative results, and for taking conservative but coherent diligence positions. Frozen scores remain untouched; those deductions are now explicitly classified.

Spend stopped after exactly ten cells: **${sentinel['response_reported_spend_usd']:.2f}** response-reported for v0.6.3, **${sentinel['aggregate_with_v062_usd']:.2f}** including the preserved v0.6.2 attempt. Held-out requests: **{sentinel['heldout_requests']}**. Astra requests: **{sentinel['astra_requests']}**.

## Model × artifact

These are one-seed controlled diagnostics, not a ranking. “Total” is the diagnostic artifact score; the unsubmitted Gemini clean cell retains zero reliability.

{_artifact_matrix(audit)}

## Why this is a no-go

- Ceiling: Sol’s accepted two-state mean is 82.80. GPT-5.2’s accepted mean is 84.44. Both exceed the >80 no-go line.
- Completion: Gemini clean created ten artifacts but did not execute the final submission action; reliability is zero.
- Concentration: decision/recovery contributes 32.13% of the strongest accepted model’s loss.
- Shallow-policy vulnerability: frozen universal advance/pause/stop/abstain controls fail the separate decision-policy metric, yet their artifact-science means remain roughly 92–95.
- Construct error: the flat/exact field grader rejects some semantically valid alternative workflows and conservative decisions.
- Scenario design: clean versus leakage is partly distinguished, but obvious state/resource wording and unrelated schema deductions contaminate that comparison.

## Execution diagnostics

{_execution_table(audit)}

## Capability summary

{_capability_matrix(audit)}

## Model × capability diagnostic means

{_model_capability_matrix(audit)}

## Artifact-family contribution to every observed model gap

The reference is the highest diagnostic two-state mean, not a ranking. Signed values are score-point contributions; negative values mean the comparison model did better in that family.

{_gap_contribution_table(audit)}

## Difficulty balance

- Estimated frozen score weight: 40% mechanical/procedural, 12% quantitative, 48% interpretive.
- Pre-reveal weight: 70%; post-reveal weight: 30%.
- Pre-reveal mean: {audit['difficulty_slices']['pre_reveal_mean']:.2f}; post-reveal mean: {audit['difficulty_slices']['post_reveal_mean']:.2f}.
- A01–A06 mean: {audit['difficulty_slices']['early_A01_A06_mean']:.2f}; A09–A10 mean: {audit['difficulty_slices']['decision_A09_A10_mean']:.2f}.
- Clean-state mean: {audit['scenario_distinction']['clean_mean']:.2f}; leakage-state mean: {audit['scenario_distinction']['leakage_mean']:.2f}. This gap is not a pure measure of leakage reasoning.

## Claims

Defensible:

""" + "\n".join(f"- {claim}" for claim in audit["claims"]["defensible"]) + "\n\nProhibited:\n\n" + "\n".join(f"- {claim}" for claim in audit["claims"]["prohibited"]) + "\n"


def render_ease(audit: dict[str, Any]) -> str:
    universal = audit["shallow_policy_diagnostic"]["universal_policies"]
    policy_lines = [
        "| Policy | Artifact-science mean | Artifact-science minimum | Decision-policy mean |",
        "|---|---:|---:|---:|",
    ]
    for policy, row in universal.items():
        policy_lines.append(
            f"| {policy} | {row['mean_scientific_artifact_score']:.2f} | "
            f"{row['minimum_scientific_artifact_score']:.2f} | {row['mean_decision_policy_score']:.2f} |"
        )
    policy_table = "\n".join(policy_lines)
    return f"""# UC-Bench v0.6.3 ease and ceiling map

The frozen benchmark awarded too much credit before the hard scientific decisions. Diagnostic categories may overlap: an artifact can be consequential in principle while still being answer-signalled or grader-limited in this implementation.

{_artifact_stats(audit)}

## Shallow universal policies

{policy_table}

This is the clearest construct warning: universal policies fail decision quality but still obtain high artifact-science scores. The score therefore overstates how much evidence-sensitive reasoning a policy demonstrated.

## Template and signalling findings

- A01, A02, A03 and A06 are largely enumeration, hash checking, deterministic mapping, or locked-script replay. They are useful integrity gates, but too heavily rewarded as model science.
- A06 is effectively a tool-execution check: every sentinel cell scored 100.
- A07/A08 reward exact field placement. Rich nested plans/results can lose the same points as absent calculations.
- Resource names and descriptions make R1 identity, R2 endpoint, R3 leakage, R4 transfer and R5 sample size directly legible. That reduces value-of-information selection toward keyword matching.
- A01’s hard-coded discovery patient count conflicts with the visible absence of row-level discovery data.
- A04’s bare-token requirement rejects annotated but correct label names.
- No dedicated blank/template-without-key-evidence control was frozen in v0.6; this audit therefore reports the demonstrated risk and does not invent a score.

## Scenario contribution

| Scenario | Mean artifact score | Share of observed loss |
|---|---:|---:|
""" + "\n".join(
        f"| {_short_scenario(name)} | {row['mean_artifact_score']:.2f} | {100 * row['share_of_total_artifact_loss']:.1f}% |"
        for name, row in audit["scenario_analysis"].items()
    ) + "\n"


def render_adjudication(audit: dict[str, Any]) -> str:
    lines = [
        "# UC-Bench v0.6.3 construct-validity adjudication",
        "",
        "This is a post-hoc audit, not a rescore. Every frozen deduction is retained. Classification says whether that deduction actually supports a claim about scientific capability.",
        "",
        "- A: consequential scientific error",
        "- B: defensible alternative professional policy",
        "- C: grader/schema artifact",
        "- D: harmless incompleteness",
        "- E: genuine uncertainty not resolvable from supplied evidence",
        "",
        "## Counts",
        "",
        "| Class | Atomic deductions |",
        "|---|---:|",
    ]
    for code, count in audit["adjudication_counts"].items():
        lines.append(f"| {code} | {count} |")
    lines.extend(
        [
            "",
            "## Every model × scenario × artifact",
            "",
            "Each row links to the artifact and frozen grade. Full observed and expected values, deduction weights, and JSON pointers are in `artifacts/diagnostics/hard_suite_v063_ceiling_audit.json#/cells`.",
            "",
            "| Model | State | Artifact | Score | Deductions (class) | What the agent did | Decision effect | Evidence pointers |",
            "|---|---|---:|---:|---|---|---|---|",
        ]
    )
    for cell in audit["cells"]:
        for artifact in cell["artifacts"]:
            deductions = "; ".join(
                f"{row['invariant']} ({row['adjudication']}, −{row['deduction_points']:.1f})"
                for row in artifact["deductions"]
            ) or "none"
            trace = artifact["trace"]
            lines.append(
                f"| {_short_model(cell['model_id'])} | {_short_scenario(cell['scenario_id'])} | "
                f"{artifact['artifact_id']} | {artifact['score']:.2f} | {deductions} | "
                f"{artifact['agent_behavior'].replace('|', '/')} | {artifact['eventual_decision_effect']} | "
                f"`{trace['artifact']}`; `{trace['grade']}` |"
            )
    lines.extend(
        [
            "",
            "## High-consequence adjudications",
            "",
            "- `patient_count=unresolved`: class E, not model failure. Row-level discovery data were unavailable; inventing 118 unique patients would be worse diligence.",
            "- Sol clean pause/R3: class B. It correctly distinguished a sponsor-declared clean lineage from independently verified execution. The frozen target treated no resource as uniquely optimal.",
            "- Claude clean conditional advance/R1: class B. Source identity reconciliation is a defensible inexpensive condition before commercial advancement.",
            "- `none` in clean: not uniquely optimal. It is one admissible policy under a research-evidence threshold, not the only professional policy under diligence risk.",
            "- A02/A03/A06: mostly free or procedural in clean; A06 was 100 in every cell. These should gate integrity or carry little scientific ranking weight.",
            "- A01/A04 common deductions: hard-coded unverifiable patient count and a label-token normalizer—not shared biological misunderstanding.",
            "- A08 nested metrics: class C when the artifact contains independently calculated nested patient-level results. Frozen scoring looked only at flat keys.",
            "- Alternative workflows: reference/paraphrase fixtures passed because they were authored to the same scorer. Live artifacts show that the grader does not reliably accept different semantic organization or cautious policy thresholds.",
        ]
    )
    return "\n".join(lines) + "\n"


def render_remedy(audit: dict[str, Any]) -> str:
    lines = [
        "# UC-Bench v0.6.3 model × failure-mode × remedy matrix",
        "",
        "Only class-A deductions support a direct scientific-failure diagnosis. B–E rows are retained to show where frozen points should not be interpreted as capability loss.",
        "",
        "| Model | State | First consequential failure | Frozen first divergence | Final decision | Resource | Scientific failure modes (A) | Non-error deductions (B–E) | Remedy evidence |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for cell in audit["cells"]:
        class_a = []
        non_a = []
        remedies = []
        for artifact in cell["artifacts"]:
            for deduction in artifact["deductions"]:
                label = f"{artifact['artifact_id']}.{deduction['invariant']}"
                if deduction["adjudication"] == "A":
                    class_a.append(label)
                    remedies.append(f"{artifact['artifact_id']}: {artifact['paired_actionable_remedy']}")
                else:
                    non_a.append(f"{label} ({deduction['adjudication']})")
        lines.append(
            f"| {_short_model(cell['model_id'])} | {_short_scenario(cell['scenario_id'])} | "
            f"{cell['adjudicated_first_consequential_divergence']} | {cell['frozen_first_divergence']} | "
            f"{cell['final_decision']} | {cell['selected_resource']} | "
            f"{'; '.join(class_a) or 'none'} | {'; '.join(non_a) or 'none'} | "
            f"{'; '.join(dict.fromkeys(remedies)) or 'no demonstrated class-A remedy'} |"
        )
    lines.extend(
        [
            "",
            "A remedy is actionable here, not proven causal. Training-data, SFT, RL, prompting, or expert-remedy claims require a paired intervention and observed recovery.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    audit = build_v063_ceiling_audit(ROOT)
    AUDIT_JSON.parent.mkdir(parents=True, exist_ok=True)
    AUDIT_JSON.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    FINAL_REPORT.parent.mkdir(parents=True, exist_ok=True)
    FINAL_REPORT.write_text(render_final(audit), encoding="utf-8")
    EASE_REPORT.write_text(render_ease(audit), encoding="utf-8")
    ADJUDICATION_REPORT.write_text(render_adjudication(audit), encoding="utf-8")
    REMEDY_REPORT.write_text(render_remedy(audit), encoding="utf-8")
    print(json.dumps({
        "decision": audit["verdict"]["decision"],
        "cells": audit["sentinel"]["cell_count"],
        "valid": audit["sentinel"]["valid_episode_count"],
        "spend_usd": audit["sentinel"]["response_reported_spend_usd"],
        "outputs": [str(path.relative_to(ROOT)) for path in (AUDIT_JSON, FINAL_REPORT, EASE_REPORT, ADJUDICATION_REPORT, REMEDY_REPORT)],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

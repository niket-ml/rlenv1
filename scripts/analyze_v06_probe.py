#!/usr/bin/env python3
"""Render the frozen, deterministic v0.6 development-probe analysis."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.v06_freeze import read_v06_freeze_manifest
from uc_bench.v06_probe_analysis import analyze_v06_probe

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = PROJECT_ROOT / "artifacts/diagnostics/hard_suite_v06_calibration_runs.json"
CONFIG_PATH = PROJECT_ROOT / "configs/hard_suite_v06.json"
PANEL_PATH = PROJECT_ROOT / "configs/hard_suite_v06_model_panel.json"
EXECUTION_PATH = PROJECT_ROOT / "configs/hard_suite_v06_execution.json"
OUTPUT_PATH = PROJECT_ROOT / "artifacts/diagnostics/hard_suite_v06_probe_analysis.json"
REPORT_PATH = PROJECT_ROOT / "reports/generated/hard_suite_v06_probe_report.md"


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError(f"Expected object: {path}")
    return value


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _display(value: Any) -> str:
    if value is None:
        return "not evaluable"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def render_report(analysis: dict[str, Any]) -> str:
    strongest = analysis["strongest_model"]
    decision = analysis["sentinel_decision"]
    capability = analysis["capability_diagnostics"]
    family = analysis["artifact_family_concentration"]
    scenario = analysis["scenario_concentration"]
    partial = analysis["meaningful_partial_credit"]
    lines = [
        "# UC-Bench v0.6 controlled development ceiling probe",
        "",
        "This is a one-seed, two-state internal calibration probe—not a stable ranking.",
        (
            "Scientific quality among accepted submissions is kept separate from "
            "completion reliability."
        ),
        "",
        "## Predeclared outcome",
        "",
        f"- Decision: **{decision['decision']}**.",
        f"- Reasons: `{', '.join(decision['reasons'])}`.",
        f"- Strongest model: `{strongest}`.",
        (
            "- Strongest accepted-submission scientific mean: "
            f"{_display(analysis['strongest_model_scientific_mean'])}."
        ),
        f"- Ceiling band: `{analysis['strongest_model_ceiling_band']}`.",
        "- Desired: 60–70; acceptable: >70–75; insufficient headroom: >75–80; ceiling no-go: >80.",
        "",
        "## Scientific score and reliability",
        "",
        (
            "| Model | Accepted | Scientific mean | Reliability mean | Cost | "
            "Input tokens | Output tokens |"
        ),
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for model, row in analysis["models"].items():
        lines.append(
            "| {model} | {accepted}/{expected} | {science} | {reliability} | "
            "${cost:.4f} | {input_tokens} | {output_tokens} |".format(
                model=model,
                accepted=row["accepted_submission_count"],
                expected=row["expected_episode_count"],
                science=_display(row["mean_scientific_score_accepted_submissions"]),
                reliability=_display(
                    row["mean_reliability_score_non_infrastructure_attempts"]
                ),
                cost=row["reported_cost_usd"],
                input_tokens=row["input_tokens"],
                output_tokens=row["output_tokens"],
            )
        )
    lines.extend(
        [
            "",
            "## Loss distribution",
            "",
            (
                "Material scientific capabilities: "
                f"{capability['material_capability_count']} "
                f"(`{', '.join(capability['material_capabilities'])}`)."
            ),
            (
                "Largest artifact-family share of the strongest model's scientific gap: "
                f"`{family['largest_contributor']}` at "
                f"{100 * family['largest_gap_share']:.1f}% "
                f"(cap {100 * family['maximum_allowed']:.0f}%)."
            ),
            (
                "Largest observed scenario share: "
                f"`{scenario['largest_contributor']}` at "
                f"{100 * scenario['largest_observed_gap_share']:.1f}%."
            ),
            (
                "Scenario-concentration gate: not evaluable in a two-state sentinel; "
                "it is predeclared for the complete six-state development matrix."
                if not scenario["evaluable"]
                else f"Scenario-concentration gate passed: {scenario['passes']}."
            ),
            (
                "Meaningful partial credit: "
                f"{partial['passes']} "
                f"({100 * partial['episode_fraction_strictly_between_zero_and_95']:.1f}% "
                "of accepted episodes strictly between 0 and 95; "
                f"{partial['artifact_count']} distinct artifacts strictly between 0 and 90)."
            ),
            "",
            "## Deterministic material deductions",
            "",
            (
                "| Model | State | Artifact | Score | Consequence | Actionable remedy | "
                "Intervention class | Trace |"
            ),
            "|---|---|---|---:|---|---|---|---|",
        ]
    )
    for row in analysis["material_deduction_evidence"]:
        lines.append(
            "| {model} | {scenario} | {artifact} | {score} | {consequence} | "
            "{remedy} | {intervention} | `{trace}` |".format(
                model=row["model_id"],
                scenario=row["scenario_id"],
                artifact=row["artifact_id"],
                score=_display(row["artifact_score"]),
                consequence=str(row["professional_consequence"]).replace("|", "/"),
                remedy=str(row["paired_remedy"]).replace("|", "/"),
                intervention=row["remedy_intervention_class"],
                trace=row["workspace_artifact_path"],
            )
        )
    if not analysis["material_deduction_evidence"]:
        lines.append("| — | — | — | — | No material scientific deductions. | — | — | — |")
    lines.extend(
        [
            "",
            (
                "No formatting, schema, timeout, refusal, or completion event is "
                "counted as a scientific capability loss."
            ),
            (
                "The deterministic grader remains the headline score; process "
                "annotations are diagnostic only."
            ),
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    freeze = read_v06_freeze_manifest(PROJECT_ROOT)
    checkpoint = _read(INPUT_PATH)
    config = _read(CONFIG_PATH)
    panel = _read(PANEL_PATH)
    execution = _read(EXECUTION_PATH)
    if checkpoint.get("strategy") != "sentinel":
        raise ConfigurationError("This report requires the predeclared sentinel checkpoint")
    if checkpoint.get("heldout_requests") != 0 or checkpoint.get("astra_requests") != 0:
        raise ConfigurationError("Held-out or Astra exposure entered the development probe")
    analysis = analyze_v06_probe(
        checkpoint.get("runs") or [],
        config=config,
        model_ids=[str(row["model_id"]) for row in panel["models"]],
        scenario_ids=list(execution["sentinel"]["scenario_ids"]),
        project_root=PROJECT_ROOT,
    )
    analysis.update(
        {
            "generated_at": datetime.now(UTC).isoformat(),
            "freeze_hash_set_digest": freeze["hash_set_digest"],
            "response_reported_spend_usd": checkpoint.get(
                "response_reported_spend_usd"
            ),
            "key_usage_delta_usd": checkpoint.get("key_usage_delta_usd"),
            "heldout_requests": 0,
            "astra_requests": 0,
        }
    )
    _write(OUTPUT_PATH, json.dumps(analysis, indent=2, sort_keys=True) + "\n")
    _write(REPORT_PATH, render_report(analysis))
    print(json.dumps(analysis, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

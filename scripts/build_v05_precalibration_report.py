#!/usr/bin/env python3
"""Build the honest no-model v0.5 product report from local control evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTROLS_PATH = PROJECT_ROOT / "artifacts" / "diagnostics" / "hard_suite_v05_controls.json"
AUTHENTIC_PATH = PROJECT_ROOT / "artifacts" / "reference" / "validation_result.json"
OUTPUT_JSON = PROJECT_ROOT / "artifacts" / "diagnostics" / "hard_suite_v05_precalibration.json"
OUTPUT_REPORT = PROJECT_ROOT / "reports" / "generated" / "hard_suite_v05_report.md"


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected JSON object: {path}")
    return value


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _fmt(value: float) -> str:
    return f"{value:.3f}"


def main() -> None:
    controls = _read(CONTROLS_PATH)
    authentic = _read(AUTHENTIC_PATH)
    states = []
    for row in controls["scenarios"]:
        grade = row["reference"]
        observed = grade["observed_evidence"]
        initial = observed["initial_metrics"]
        followup = observed["followup_metrics"]
        states.append(
            {
                "scenario_id": row["scenario_id"],
                "scenario_class": row["scenario_class"],
                "initial_auc": initial["auc"],
                "initial_auc_interval": [initial["auc_ci_low"], initial["auc_ci_high"]],
                "followup_auc": followup["auc"],
                "followup_auc_interval": [
                    followup["auc_ci_low"],
                    followup["auc_ci_high"],
                ],
                "optimal_resource": grade["optimal_resource"],
                "intervention_effect": grade["expected_intervention_effect"],
                "decision_transition": observed["decision_transition"],
                "active_initial_blockers": observed["active_initial_blockers"],
            }
        )
    output = {
        "schema_version": "0.5",
        "status": "precalibration_no_model_ranking",
        "model_calls": 0,
        "astra_requests": 0,
        "local_gates_passed": controls["all_local_gates_passed"],
        "controlled_reference_states": states,
        "universal_policy_mean_scores": controls["policy_mean_scores"],
        "authentic_geo_anchor": {
            "controlled_or_authentic": "authentic",
            "cohort": "GSE92415",
            "n": authentic["evaluated_n"],
            "auc": authentic["auc"],
            "auc_interval": authentic["auc_interval"],
            "decision": "insufficient_evidence",
            "not_a_v05_model_result": True,
        },
        "required_future_outputs": [
            "model_by_milestone",
            "model_by_capability",
            "model_by_failure_mode",
            "paired_intervention_rescue",
            "breaking_point_curves",
            "representative_replay_traces",
            "claim_level_evidence",
        ],
    }
    _write_json(OUTPUT_JSON, output)

    lines = [
        "# UC-Bench v0.5 — pre-calibration product report",
        "",
        "> **NO MODEL RANKING.** No v0.5 model or Astra calls have been made. "
        "The tables below are deterministic environment controls and one separately "
        "preserved authentic GEO anchor.",
        "",
        "## Product question",
        "",
        "Can a coding agent diligence a locked anti-TNF predictor, contain invalid "
        "claims, buy the most decision-relevant evidence, revise its beliefs, and "
        "advance or stop for the right reason?",
        "",
        "## Local construct gates",
        "",
        f"Overall local gate: **{'PASS' if controls['all_local_gates_passed'] else 'FAIL'}**.",
        "",
        "| Control | Result |",
        "|---|---:|",
    ]
    lines.extend(
        f"| {name.replace('_', ' ')} | {'pass' if passed else 'fail'} |"
        for name, passed in controls["checks"].items()
    )
    lines.extend(
        [
            "",
            "## Controlled scientific states",
            "",
            "| State | Initial AUC (95% interval) | Follow-up AUC (95% interval) "
            "| Resource | Effect | Decision |",
            "|---|---:|---:|---|---|---|",
        ]
    )
    for row in states:
        lines.append(
            "| "
            + " | ".join(
                [
                    row["scenario_class"].replace("_", " "),
                    (
                        f"{_fmt(row['initial_auc'])} "
                        f"({_fmt(row['initial_auc_interval'][0])}–"
                        f"{_fmt(row['initial_auc_interval'][1])})"
                    ),
                    (
                        f"{_fmt(row['followup_auc'])} "
                        f"({_fmt(row['followup_auc_interval'][0])}–"
                        f"{_fmt(row['followup_auc_interval'][1])})"
                    ),
                    row["optimal_resource"],
                    row["intervention_effect"].replace("_", " "),
                    " → ".join(row["decision_transition"]),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "These are reference properties of controlled cases, not claims about any model.",
            "",
            "## Universal-policy controls",
            "",
            "| Policy | Mean score |",
            "|---|---:|",
        ]
    )
    lines.extend(
        f"| {name.replace('_', ' ')} | {score:.2f} |"
        for name, score in controls["policy_mean_scores"].items()
    )
    lines.extend(
        [
            "",
            "## Authentic anchor — reported separately",
            "",
            f"The preserved real GSE92415 evaluation contains n={authentic['evaluated_n']} "
            f"patients, AUC {_fmt(authentic['auc'])}, and 95% bootstrap interval "
            f"{_fmt(authentic['auc_interval'][0])}–{_fmt(authentic['auc_interval'][1])}. "
            "It supports `insufficient_evidence`. It is not pooled with controlled cases "
            "and is not a v0.5 model result.",
            "",
            "## Failure-claim discipline",
            "",
            "Future reports must keep four layers separate:",
            "",
            "1. **Observed behavior:** the exact action, artifact, number, or unsupported claim.",
            "2. **Capability diagnosis:** the benchmark property implicated across "
            "repeated evidence.",
            "3. **Hypothesized training cause:** explicitly speculative; never inferred "
            "from score alone.",
            "4. **Demonstrated remedy:** only a paired intervention with measured "
            "behavioral recovery.",
            "",
            "## Remaining empirical gate",
            "",
            "The frozen development pilot is six states × three models × one seed, capped "
            "at $20. It may establish a ceiling/floor no-go, but it cannot establish a "
            "stable ranking. Held-out variants, repeated seeds, uncertainty analysis, and "
            "Astra remain blocked.",
            "",
        ]
    )
    OUTPUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(OUTPUT_REPORT.relative_to(PROJECT_ROOT))


if __name__ == "__main__":
    main()

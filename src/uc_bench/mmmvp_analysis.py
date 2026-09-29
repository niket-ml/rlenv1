"""Deterministic multi-axis report for the MMMVP model comparison."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected object: {path}")
    return value


def _requirement(grade: dict[str, Any] | None, requirement_id: str) -> bool | None:
    if not grade:
        return None
    rows = [row for row in grade["requirements"] if row["requirement_id"] == requirement_id]
    return bool(rows[0]["passed"]) if len(rows) == 1 else None


def _failure_class(summary: dict[str, Any]) -> str:
    classification = summary["classification"]
    if classification == "infrastructure_failure":
        return "infrastructure_failure"
    if classification in {"provider_adapter_failure", "provider_policy_refusal"}:
        return "provider_failure"
    if classification in {"agent_task_failure", "context_budget_exhaustion"}:
        rejected = any(
            event.get("event") == "submit_rejected"
            for event in summary.get("submission", {}).get("event_log", [])
        )
        return "contract_failure" if rejected else "model_completion_failure"
    if summary.get("complete_mission_success") is False:
        return "scientific_failure"
    return "success"


def build_mmmvp_analysis(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    state = _read(root / "artifacts/mmmvp/matrix_state.json")
    freeze = _read(root / "artifacts/mmmvp/freeze.json")
    compatibility = _read(root / "artifacts/mmmvp/compatibility_results.json")
    panel = freeze["model_ids"]
    summaries = [_read(root / relative) for relative in state.get("summary_paths") or []]
    by_model: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_condition: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for summary in summaries:
        by_model[summary["model_id"]].append(summary)
        by_condition[summary["condition_id"]].append(summary)

    model_rows: list[dict[str, Any]] = []
    failed_missions: list[dict[str, Any]] = []
    for model_id in panel:
        rows = by_model.get(model_id, [])
        scored = [row for row in rows if row.get("partial_scientific_quality") is not None]
        complete = [row for row in rows if row.get("complete_mission_success") is True]
        valid = [row for row in rows if row["classification"] == "valid_episode"]
        milestone: dict[str, list[float]] = defaultdict(list)
        for row in scored:
            for checkpoint, score in row["diagnostic_grade"]["checkpoint_scores"].items():
                milestone[checkpoint].append(float(score))
        failure_counts: dict[str, int] = defaultdict(int)
        for row in rows:
            failure_counts[_failure_class(row)] += 1
            if row.get("complete_mission_success") is False:
                grade = row.get("diagnostic_grade") or {}
                first = grade.get("first_decision_critical_failure")
                failures = grade.get("mission_failures") or []
                failed_missions.append(
                    {
                        "model_id": model_id,
                        "condition_id": row["condition_id"],
                        "first_decision_critical_failure": first,
                        "downstream_requirement_failures": (
                            failures[1:] if first and failures else failures
                        ),
                        "classification": _failure_class(row),
                    }
                )
        model_rows.append(
            {
                "model_id": model_id,
                "complete_missions_passed_out_of_five": len(complete),
                "scientific_cells_recorded": len(rows),
                "valid_episode_count": len(valid),
                "mean_partial_scientific_quality": (
                    round(mean(float(row["partial_scientific_quality"]) for row in scored), 4)
                    if scored
                    else None
                ),
                "performance_by_milestone": {
                    checkpoint: round(mean(values), 4)
                    for checkpoint, values in sorted(milestone.items())
                },
                "final_decision_accuracy": (
                    round(
                        mean(
                            bool(
                                _requirement(
                                    row.get("diagnostic_grade"),
                                    "explicit_bounded_decision",
                                )
                            )
                            for row in scored
                        ),
                        4,
                    )
                    if scored
                    else None
                ),
                "belief_revision_accuracy": (
                    round(
                        mean(
                            bool(
                                _requirement(
                                    row.get("diagnostic_grade"),
                                    "evidence_consistent_belief_change",
                                )
                            )
                            for row in scored
                        ),
                        4,
                    )
                    if scored
                    else None
                ),
                "resource_selection_accuracy": (
                    round(
                        mean(
                            bool(
                                _requirement(
                                    row.get("diagnostic_grade"),
                                    "decision_relevant_resource",
                                )
                            )
                            for row in scored
                        ),
                        4,
                    )
                    if scored
                    else None
                ),
                "completion_rate": round(len(valid) / len(rows), 4) if rows else None,
                "mean_turns": round(mean(float(row.get("turn_count") or 0) for row in rows), 2)
                if rows
                else None,
                "cost_usd": round(
                    sum(float(row.get("cumulative_reported_cost_usd") or 0) for row in rows),
                    6,
                ),
                "tool_failures": sum(
                    sum(
                        1
                        for event in row.get("submission", {}).get("event_log", [])
                        if event.get("success") is False
                    )
                    for row in rows
                ),
                "failure_classes": dict(sorted(failure_counts.items())),
            }
        )

    condition_rows = []
    for condition_id in freeze.get("condition_ids") or [
        "case_01",
        "case_02",
        "case_03_signal_collapses",
        "case_03_signal_remains",
        "case_04",
    ]:
        rows = by_condition.get(condition_id, [])
        scored = [row for row in rows if row.get("partial_scientific_quality") is not None]
        condition_rows.append(
            {
                "condition_id": condition_id,
                "complete_missions": sum(
                    row.get("complete_mission_success") is True for row in rows
                ),
                "scientific_cells_recorded": len(rows),
                "mean_partial_scientific_quality": (
                    round(mean(float(row["partial_scientific_quality"]) for row in scored), 4)
                    if scored
                    else None
                ),
            }
        )
    total_science_cost = sum(
        float(row.get("cumulative_reported_cost_usd") or 0) for row in summaries
    )
    return {
        "schema_version": "uc-bench-mmmvp-analysis-1",
        "interpretation": (
            "controlled MMMVP multi-model pilot; one attempt per cell is not a stable ranking"
        ),
        "status": state.get("status"),
        "freeze_digest": freeze["hash_set_digest"],
        "model_panel": panel,
        "model_results": model_rows,
        "condition_results": condition_rows,
        "failed_missions": failed_missions,
        "scientific_episode_count": len(summaries),
        "scientific_spend_usd": round(total_science_cost, 6),
        "compatibility_spend_usd": compatibility["cost_usd"],
        "combined_spend_usd": round(total_science_cost + compatibility["cost_usd"], 6),
        "historical_sol_excluded_from_comparison": True,
        "heldout_requests": 0,
        "astra_requests": 0,
        "ranking_claim_allowed": False,
    }


def render_mmmvp_report(analysis: dict[str, Any]) -> str:
    lines = [
        "# UC-Bench MMMVP multi-model pilot",
        "",
        "This is a controlled five-condition pilot with one attempt per cell. It is not a "
        "definitive frontier ranking. Historical GPT-5.6 Sol development runs are excluded.",
        "",
        f"Status: `{analysis['status']}`. Scientific episodes: "
        f"{analysis['scientific_episode_count']}. Combined API spend: "
        f"${analysis['combined_spend_usd']:.4f}.",
        "",
        "## Model summary",
        "",
        (
            "| Model | Missions / 5 | Mean partial | Completion | Decision | "
            "Belief | Resource | Cost |"
        ),
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in analysis["model_results"]:
        def show(value: Any) -> str:
            return "—" if value is None else f"{float(value):.3f}"

        lines.append(
            f"| {row['model_id']} | {row['complete_missions_passed_out_of_five']} | "
            f"{show(row['mean_partial_scientific_quality'])} | {show(row['completion_rate'])} | "
            f"{show(row['final_decision_accuracy'])} | {show(row['belief_revision_accuracy'])} | "
            f"{show(row['resource_selection_accuracy'])} | ${row['cost_usd']:.4f} |"
        )
    lines.extend(["", "## First decision-critical failures", ""])
    if not analysis["failed_missions"]:
        lines.append("No scored mission failures were recorded.")
    else:
        for row in analysis["failed_missions"]:
            first = row["first_decision_critical_failure"] or {}
            lines.append(
                f"- `{row['model_id']}` / `{row['condition_id']}`: "
                f"`{first.get('requirement_id', row['classification'])}` — "
                f"{first.get('consequence', 'No complete scorable submission.')}"
            )
    lines.extend(
        [
            "",
            "## Interpretation limits",
            "",
            "- One attempt per cell estimates neither repeatability nor a stable ordering.",
            (
                "- Provider, infrastructure, contract, completion and scientific failures "
                "are separated."
            ),
            (
                "- Capability diagnoses are behavioural; training-cause claims require "
                "paired interventions."
            ),
            "- No held-out condition or Astra model was used.",
            "",
        ]
    )
    return "\n".join(lines)


__all__ = ["build_mmmvp_analysis", "render_mmmvp_report"]

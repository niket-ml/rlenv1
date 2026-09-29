"""Deterministic adjudication and reporting for the Case-2 sentinel."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from statistics import median
from typing import Any

import numpy as np

from uc_bench.mmmvp_open_release_freeze import read_open_release_freeze

ANALYSIS_PATH = Path("artifacts/mmmvp_open_release/sentinel_analysis.json")
SPEND_LEDGER_PATH = Path("artifacts/mmmvp_open_release/spend_ledger.json")
REPORT_PATH = Path("reports/generated/mmmvp_open_case2_sentinel.md")
FIGURE_ROOT = Path("reports/generated/mmmvp_open_case2_sentinel_figures")

_FAMILY = {
    "schema_contract": "contract failure",
    "irreversible_action_integrity": "commitment/contingency failure",
    "prospective_plan_implemented": "commitment/contingency failure",
    "saved_artifact_chain": "evidence inspection failure",
    "relevant_entity_reconstruction": "entity/cohort reconstruction failure",
    "decision_relevant_quantitative_work": "inappropriate quantitative method",
    "invalid_evidence_contained": "incorrect evidence eligibility",
    "decision_relevant_followup": "follow-up choice weakness",
    "purchased_evidence_analyzed": "failure to use purchased evidence",
    "belief_commitment_and_revision": "belief-revision failure",
    "evidence_supported_decision": "unsupported decision",
    "bounded_claims": "overclaiming",
}


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected object: {path}")
    return value


def _failure(summary: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    classification = summary["classification"]
    grade = summary.get("diagnostic_grade") or {}
    first = grade.get("first_decision_critical_failure")
    if first:
        return _FAMILY.get(first.get("requirement_id"), "grader/construct failure"), first
    if classification == "infrastructure_failure":
        return "infrastructure failure", None
    if classification in {"provider_adapter_failure", "provider_policy_refusal"}:
        return "provider failure", None
    if classification not in {"valid_episode", "success"}:
        return "completion/horizon failure", None
    return "none", None


def _timeline(summary: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for event in summary.get("submission", {}).get("event_log") or []:
        rows.append(
            {
                "time": event.get("time"),
                "kind": "environment",
                "event": event.get("event"),
                "sequence": event.get("sequence"),
            }
        )
    for request in summary.get("provider_requests") or []:
        rows.append(
            {
                "time": request.get("recorded_at"),
                "kind": "provider",
                "event": f"request_{request.get('request_index')}",
                "finish_reason": request.get("finish_reason"),
                "cost_usd": request.get("reported_cost_usd"),
            }
        )
    return sorted(rows, key=lambda row: str(row.get("time") or ""))


def _submission_fields(summary: dict[str, Any]) -> dict[str, Any]:
    submission = summary.get("submission") or {}
    validation = submission.get("validation_plan") or {}
    followup = submission.get("followup_plan") or {}
    final = submission.get("final_submission") or {}
    analyses = validation.get("planned_analyses") or []
    calculations = final.get("calculations") or []
    units = {
        str(row.get("analysis_unit")) for row in analyses if row.get("analysis_unit")
    }
    units.update(
        str(row.get("unit_of_analysis"))
        for row in calculations
        if row.get("unit_of_analysis")
    )
    return {
        "analysis_units": sorted(units),
        "methods": [str(row.get("method")) for row in analyses if row.get("method")],
        "estimators": sorted(
            {str(row.get("estimator")) for row in calculations if row.get("estimator")}
        ),
        "resource_id": followup.get("chosen_resource"),
        "evidence_target": followup.get("evidence_target"),
        "belief_updates": final.get("belief_updates") or [],
        "decision": final.get("decision") or {},
        "claims": final.get("claims") or [],
    }


def _requirements(summary: dict[str, Any]) -> dict[str, bool] | None:
    grade = summary.get("diagnostic_grade")
    if not grade:
        return None
    return {
        str(row["requirement_id"]): bool(row["passed"])
        for row in grade.get("requirements") or []
        if row.get("requirement_class") == "mission_critical_science"
    }


def _cost_plan(models: list[dict[str, Any]], headroom: dict[str, Any]) -> dict[str, Any]:
    costs = [float(row["cost_usd"]) for row in models if row["cost_usd"] is not None]
    per_model = {row["model_id"]: float(row["cost_usd"] or 0.0) for row in models}
    remaining_median = 4 * sum(per_model.values())
    no_cache_costs: list[float] = []
    for row in models:
        summary = row["_summary"]
        prompt = 0
        completion = 0
        adapter = summary.get("provider_adapter") or {}
        prices = adapter.get("maximum_route_price_usd_per_million") or {}
        for request in summary.get("provider_requests") or []:
            usage = request.get("usage") or {}
            prompt += int(usage.get("prompt_tokens") or 0)
            completion += int(usage.get("completion_tokens") or 0)
        no_cache_costs.append(
            (
                prompt * float(prices.get("prompt") or 0.0)
                + completion * float(prices.get("completion") or 0.0)
            )
            / 1_000_000
        )
    p90 = float(np.percentile(no_cache_costs, 90)) if no_cache_costs else 0.0
    projected_no_cache_p90 = 4 * p90 * len(models)
    hard_cap = max(1.2 * projected_no_cache_p90, 1.2 * remaining_median)
    available = float(headroom.get("effective_remaining_usd") or 0.0)
    return {
        "observed_sentinel_total_usd": round(sum(costs), 6),
        "observed_cost_per_model": {key: round(value, 6) for key, value in per_model.items()},
        "observed_median_cost_per_model": round(median(costs), 6) if costs else None,
        "remaining_40_cached_median_estimate_usd": round(remaining_median, 2),
        "remaining_40_no_cache_p90_estimate_usd": round(projected_no_cache_p90, 2),
        "proposed_remaining_matrix_hard_cap_usd": round(hard_cap, 2),
        "effective_headroom_usd": round(available, 2),
        "exact_top_up_required_usd": round(max(0.0, hard_cap - available), 2),
        "recommended_top_up_usd": 0.0 if available >= hard_cap else 50.0,
        "recommended_key_limit_minimum_usd": 180.0 if available < hard_cap else None,
    }


def _render_plots(root: Path, models: list[dict[str, Any]], requirements: list[str]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    target = root / FIGURE_ROOT
    target.mkdir(parents=True, exist_ok=True)
    labels = [row["model_id"].split("/", 1)[-1] for row in models]
    matrix = np.array(
        [
            [
                np.nan
                if row["requirements"] is None
                else float(row["requirements"].get(requirement, False))
                for requirement in requirements
            ]
            for row in models
        ]
    )
    figure, axis = plt.subplots(figsize=(14, max(5, 0.55 * len(models))))
    image = axis.imshow(matrix, cmap="RdYlGn", vmin=0, vmax=1, aspect="auto")
    axis.set_xticks(range(len(requirements)), requirements, rotation=55, ha="right")
    axis.set_yticks(range(len(labels)), labels)
    axis.set_title("Case 2 mission-critical requirements")
    figure.colorbar(image, ax=axis, ticks=[0, 1], label="failed / passed")
    figure.tight_layout()
    figure.savefig(target / "model_by_requirement_heatmap.png", dpi=180)
    plt.close(figure)

    failures = Counter(row["first_failure_family"] for row in models)
    figure, axis = plt.subplots(figsize=(10, 5))
    axis.barh(list(failures), list(failures.values()))
    axis.set_xlabel("model episodes")
    axis.set_title("First decision-critical failure family")
    figure.tight_layout()
    figure.savefig(target / "failure_family_distribution.png", dpi=180)
    plt.close(figure)

    figure, axis = plt.subplots(figsize=(8, 6))
    for row in models:
        if row["partial_scientific_quality"] is not None:
            point = (row["cost_usd"], row["partial_scientific_quality"])
            axis.scatter(*point, s=55)
            axis.annotate(row["model_id"].split("/", 1)[-1], point, fontsize=7)
    axis.set_xlabel("episode cost (USD)")
    axis.set_ylabel("partial scientific quality")
    axis.set_title("Score versus cost")
    figure.tight_layout()
    figure.savefig(target / "score_versus_cost.png", dpi=180)
    plt.close(figure)

    figure, axis = plt.subplots(figsize=(8, 6))
    for row in models:
        point = (row["turns"], int(bool(row["complete_mission_success"])))
        axis.scatter(*point, s=55)
        axis.annotate(row["model_id"].split("/", 1)[-1], point, fontsize=7)
    axis.set_xlabel("assistant turns")
    axis.set_ylabel("complete mission")
    axis.set_yticks([0, 1], ["fail", "pass"])
    axis.set_title("Mission success versus turns")
    figure.tight_layout()
    figure.savefig(target / "success_versus_turns.png", dpi=180)
    plt.close(figure)

    figure, axis = plt.subplots(figsize=(12, max(5, 0.55 * len(models))))
    for row_index, row in enumerate(models):
        for event_index, event in enumerate(row["timeline"]):
            marker = "o" if event["kind"] == "provider" else "|"
            axis.scatter(event_index, row_index, marker=marker, s=45)
    axis.set_yticks(range(len(labels)), labels)
    axis.set_xlabel("chronological event index")
    axis.set_title("Per-trajectory request and environment-action timelines")
    figure.tight_layout()
    figure.savefig(target / "trajectory_timelines.png", dpi=180)
    plt.close(figure)


def build_open_sentinel_analysis(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    release = read_open_release_freeze(root)
    state = _read(root / "artifacts/mmmvp_open_release/sentinel_state.json")
    compatibility = _read(root / "artifacts/mmmvp_open_release/compatibility_results.json")
    summaries = [_read(root / relative) for relative in state.get("summary_paths") or []]
    models: list[dict[str, Any]] = []
    for summary in summaries:
        family, first = _failure(summary)
        models.append(
            {
                "model_id": summary["model_id"],
                "classification": summary["classification"],
                "complete_mission_success": summary.get("complete_mission_success"),
                "partial_scientific_quality": summary.get("partial_scientific_quality"),
                "reliability_score": summary.get("reliability_score"),
                "requirements": _requirements(summary),
                "first_failure_family": family,
                "first_decision_critical_failure": first,
                "downstream_requirement_failures": (
                    (summary.get("diagnostic_grade") or {}).get("mission_failures") or []
                )[1:] if first else [],
                **_submission_fields(summary),
                "completion_status": summary["classification"],
                "turns": summary.get("turn_count") or 0,
                "token_usage": summary.get("token_usage") or {},
                "wall_time_seconds": sum(
                    float(row.get("latency_seconds") or 0)
                    for row in summary.get("provider_requests") or []
                ),
                "cost_usd": float(summary.get("cumulative_reported_cost_usd") or 0.0),
                "tool_failures": sum(
                    event.get("success") is False
                    for event in summary.get("submission", {}).get("event_log") or []
                ),
                "requested_provider": (summary.get("provider_adapter") or {}).get(
                    "provider_order"
                ),
                "actual_providers": sorted(
                    {
                        str(row.get("actual_provider"))
                        for row in summary.get("provider_requests") or []
                        if row.get("actual_provider")
                    }
                ),
                "trajectory_replay": summary.get("trajectory_persistence") or {},
                "timeline": _timeline(summary),
                "_summary": summary,
            }
        )
    requirement_ids = sorted(
        {key for row in models for key in (row.get("requirements") or {})}
    )
    signatures = Counter(
        tuple(
            sorted(
                issue.get("code", "")
                for event in row["_summary"].get("submission", {}).get("event_log") or []
                if event.get("event") == "submit_rejected"
                for issue in event.get("schema_issues") or []
            )
        )
        for row in models
    )
    repeated_contract = [
        list(signature) for signature, count in signatures.items() if signature and count >= 2
    ]
    integrity_faults = [
        row["model_id"]
        for row in models
        if not row["trajectory_replay"].get("passed", False)
        or row["actual_providers"] != row["requested_provider"]
    ]
    recommendation = (
        "NO_GO"
        if state["status"] != "completed_mandatory_review"
        or integrity_faults
        or repeated_contract
        else "GO_WITH_DISCLOSED_LIMITATION"
    )
    headroom = state.get("funding_after") or state.get("funding_before") or {}
    cost_plan = _cost_plan(models, headroom)
    spend_ledger = {
        "schema_version": "uc-bench-open-mmmvp-spend-ledger-1",
        "compatibility": [
            {
                "model_id": row["model_id"],
                "cost_usd": row["cost_usd"],
                "request_count": row["request_count"],
            }
            for row in compatibility["results"]
        ],
        "scientific": [
            {
                "model_id": row["model_id"],
                "cost_usd": row["cost_usd"],
                "requests": [
                    {
                        "request_index": request.get("request_index"),
                        "reported_cost_usd": request.get("reported_cost_usd"),
                        "usage": request.get("usage"),
                        "cache": request.get("cache"),
                    }
                    for request in row["_summary"].get("provider_requests") or []
                ],
            }
            for row in models
        ],
        "compatibility_total_usd": compatibility["cost_usd"],
        "scientific_total_usd": round(sum(row["cost_usd"] for row in models), 8),
    }
    public_models = [
        {key: value for key, value in row.items() if key != "_summary"} for row in models
    ]
    analysis = {
        "schema_version": "uc-bench-open-mmmvp-case2-sentinel-analysis-1",
        "status": "complete" if recommendation != "NO_GO" else "no_go",
        "interpretation": "one-attempt-per-model exploratory calibrated pilot, not a ranking",
        "recommendation": recommendation,
        "recommendation_limitation": (
            "Resource selection is diagnostic-only because a simple no-purchase policy "
            "remains strong."
            if recommendation == "GO_WITH_DISCLOSED_LIMITATION"
            else None
        ),
        "scientific_freeze_digest": state["scientific_freeze_digest"],
        "release_category_digest_set": release["category_digest_set"],
        "category_digests": {
            name: row["digest"] for name, row in release["categories"].items()
        },
        "compatible_models_out_of_ten": compatibility["compatible_model_count"],
        "sentinel_models_completed": len(models),
        "condition_id": "case_02",
        "execution_order_seed": state["order_seed"],
        "execution_order": state["execution_order"],
        "requirement_ids": requirement_ids,
        "models": public_models,
        "first_failure_distribution": dict(
            Counter(row["first_failure_family"] for row in models)
        ),
        "repeated_contract_failure_signatures": repeated_contract,
        "integrity_or_route_fault_models": integrity_faults,
        "cost_plan": cost_plan,
        "remaining_matrix_launched": False,
        "ranking_claim_allowed": False,
        "training_cause_claims_made": False,
    }
    (root / ANALYSIS_PATH).parent.mkdir(parents=True, exist_ok=True)
    (root / ANALYSIS_PATH).write_text(
        json.dumps(analysis, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (root / SPEND_LEDGER_PATH).write_text(
        json.dumps(spend_ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _render_plots(root, public_models, requirement_ids)
    return analysis


def render_open_sentinel_report(analysis: dict[str, Any]) -> str:
    lines = [
        "# UC-Bench open MMMVP Case-2 sentinel",
        "",
        (
            "This is a one-attempt-per-model exploratory calibration of one development "
            "condition. It is not a stable ranking or a test of the full five-condition ceiling."
        ),
        "",
        (
            f"Recommendation: **{analysis['recommendation']}**. Compatible routes: "
            f"{analysis['compatible_models_out_of_ten']}/10; completed scientific episodes: "
            f"{analysis['sentinel_models_completed']}."
        ),
        "",
        "## Results",
        "",
        (
            "| Model | Mission | Partial | First failure | Unit(s) | Resource | "
            "Decision | Turns | Cost |"
        ),
        "|---|---:|---:|---|---|---|---|---:|---:|",
    ]
    for row in analysis["models"]:
        decision = row["decision"]
        lines.append(
            f"| `{row['model_id']}` | {row['complete_mission_success']} | "
            f"{row['partial_scientific_quality']} | {row['first_failure_family']} | "
            f"{', '.join(row['analysis_units']) or '—'} | {row['resource_id'] or '—'} | "
            f"{decision.get('development_stage', '—')} / "
            f"{decision.get('disposition', '—')} / {decision.get('use_scope', '—')} | "
            f"{row['turns']} | ${row['cost_usd']:.4f} |"
        )
    lines.extend(["", "## Requirement detail", ""])
    for row in analysis["models"]:
        passed = [key for key, value in (row["requirements"] or {}).items() if value]
        failed = [key for key, value in (row["requirements"] or {}).items() if not value]
        lines.extend(
            [
                f"### {row['model_id']}",
                "",
                f"Passed: {', '.join(passed) or 'none recorded'}.",
                "",
                f"Failed: {', '.join(failed) or 'none'}.",
            ]
        )
        first = row["first_decision_critical_failure"]
        if first:
            lines.extend(
                [
                    "",
                    (
                        f"First consequential failure: **{row['first_failure_family']}** — "
                        f"{first.get('consequence')}. Downstream: "
                        f"{', '.join(row['downstream_requirement_failures']) or 'none recorded'}. "
                        f"Testable remedy: {first.get('remedy')}"
                    ),
                ]
            )
        lines.extend(
            [
                "",
                (
                    f"Method(s): {', '.join(row['methods']) or 'none submitted'}; estimators: "
                    f"{', '.join(row['estimators']) or 'none submitted'}. Resource action: "
                    f"{row['resource_id']} for {row['evidence_target']} (diagnostic only)."
                ),
                "",
                f"Belief update: `{json.dumps(row['belief_updates'], sort_keys=True)}`",
                "",
            ]
        )
    figures = FIGURE_ROOT.as_posix()
    cost = analysis["cost_plan"]
    lines.extend(
        [
            "## Figures and replay evidence",
            "",
            f"- Model × requirement heatmap: `{figures}/model_by_requirement_heatmap.png`",
            f"- Every trajectory timeline: `{figures}/trajectory_timelines.png`",
            f"- Failure-family distribution: `{figures}/failure_family_distribution.png`",
            f"- Score versus cost: `{figures}/score_versus_cost.png`",
            f"- Success versus turns: `{figures}/success_versus_turns.png`",
            "",
            (
                "Complete chronological timelines and belief/decision objects are retained in "
                "the machine-readable analysis; complete provider exchanges, artifacts and "
                "replay checkpoints remain in each run directory."
            ),
            "",
            "## Cost and next gate",
            "",
            (
                f"Observed sentinel spend: ${cost['observed_sentinel_total_usd']:.4f}. "
                f"Remaining 40-cell cached-median estimate: "
                f"${cost['remaining_40_cached_median_estimate_usd']:.2f}; no-cache P90 "
                f"estimate: ${cost['remaining_40_no_cache_p90_estimate_usd']:.2f}; "
                f"proposed hard cap: ${cost['proposed_remaining_matrix_hard_cap_usd']:.2f}."
            ),
            "",
            (
                "The remaining 40 episodes were not launched. Scientific, provider, "
                "infrastructure, completion and contract outcomes are kept separate. No causal "
                "claim about training data, SFT, RL or expert knowledge is made."
            ),
            "",
        ]
    )
    return "\n".join(lines)


__all__ = [
    "ANALYSIS_PATH",
    "REPORT_PATH",
    "SPEND_LEDGER_PATH",
    "build_open_sentinel_analysis",
    "render_open_sentinel_report",
]

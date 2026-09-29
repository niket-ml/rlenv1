"""RC1.3 sentinel and submission-friction analysis."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from uc_bench.hashing import canonical_sha256
from uc_bench.model_runner import _write_json

ANALYSIS_PATH = Path("artifacts/mmmvp_open_rc13/sentinel_analysis.json")
RC12_FRICTION_PATH = Path(
    "artifacts/mmmvp_open_rc13/rc12_submission_friction_diagnostic.json"
)
REPORT_PATH = Path("reports/generated/mmmvp_open_rc13_case2_sentinel.md")


def _trajectory_latest_path(summary: dict[str, Any]) -> Path | None:
    explicit = summary.get("host_trajectory_path")
    if explicit:
        candidate = Path(str(explicit))
        if not candidate.is_absolute():
            candidate = Path(__file__).resolve().parents[2] / candidate
        return candidate / "latest.json"
    locator = (
        summary.get("submission", {}).get("host_record_locator")
        or summary.get("submission", {}).get("host_trajectory_locator")
    )
    if not locator:
        return None
    private_workspace = Path(str(locator))
    # Open-MMMVP episode state points to run/.mmmvp_host_records/workspace;
    # trajectory persistence is its sibling run/host_trajectory.
    return private_workspace.parent.parent / "host_trajectory/latest.json"


def _submit_actions(summary: dict[str, Any]) -> list[dict[str, Any]]:
    latest = _trajectory_latest_path(summary)
    if latest is None:
        return []
    if not latest.is_file():
        return []
    record = json.loads(latest.read_text(encoding="utf-8"))
    return [
        action
        for action in record.get("tool_actions") or []
        if action.get("name") == "submit"
    ]


def submission_friction(summary: dict[str, Any]) -> dict[str, Any]:
    event_log = summary.get("submission", {}).get("event_log") or []
    rejections = [row for row in event_log if row.get("event") == "submit_rejected"]
    issues = [issue for row in rejections for issue in row.get("schema_issues") or []]
    codes = Counter(str(issue.get("code")) for issue in issues)
    first_issue = issues[0] if issues else None
    disclosure = []
    for issue in issues:
        path = str(issue.get("path") or "")
        disclosed = not (
            path.endswith(".unit_of_analysis")
            or ".cohort" in path
        )
        disclosure.append(
            {
                "code": issue.get("code"),
                "path": path,
                "disclosed": disclosed,
                "reason": (
                    "The agent-visible contract does not enumerate the two accepted "
                    "calculation unit values."
                    if path.endswith(".unit_of_analysis")
                    else "The agent-visible contract names cohort but does not disclose "
                    "its required object fields and types."
                    if ".cohort" in path
                    else "The rule is stated by the agent-visible enums, object field "
                    "lists or mechanical constraints."
                ),
            }
        )
    signatures = [
        canonical_sha256(
            [
                {"code": issue.get("code"), "path": issue.get("path")}
                for issue in row.get("schema_issues") or []
            ]
        )
        for row in rejections
    ]
    submit_actions = _submit_actions(summary)
    payload_hashes = [
        canonical_sha256(
            (action.get("invocation_arguments") or {}).get("payload_json", "")
        )
        for action in submit_actions
    ]
    first_rejection_sequence = (
        int(rejections[0].get("sequence") or 0) if rejections else None
    )
    events_before = [
        row
        for row in event_log
        if first_rejection_sequence is not None
        and int(row.get("sequence") or 0) < first_rejection_sequence
    ]
    event_names_before = {str(row.get("event")) for row in events_before}
    substantive_before_first_rejection = bool(
        {
            "commit_validation_plan",
            "reveal_validation",
            "commit_followup_plan",
            "purchase_resource",
        }
        <= event_names_before
        and "tool_run_command" in event_names_before
    )
    total_turns = int(summary.get("turn_count") or 0)
    first_submit_action_index = (
        int(submit_actions[0].get("action_index") or 0) if submit_actions else None
    )
    actions_after_first = (
        0
        if first_submit_action_index is None
        else sum(
            int(action.get("action_index") or 0) >= first_submit_action_index
            for action in (
                json.loads(
                    _trajectory_latest_path(summary).read_text()  # type: ignore[union-attr]
                ).get("tool_actions")
                or []
            )
        )
    )
    # Provider-exchange indices are the durable assistant-turn indices.  The
    # first submit tool action points to the originating call ID.
    repair_turns = 0
    if submit_actions:
        latest = json.loads(
            _trajectory_latest_path(summary).read_text()  # type: ignore[union-attr]
        )
        first_id = str(submit_actions[0].get("tool_call_id"))
        origin = next(
            (
                int(exchange.get("request_index") or 0)
                for exchange in latest.get("provider_exchanges") or []
                if any(
                    str(call.get("tool_call_id")) == first_id
                    for call in exchange.get("tool_calls") or []
                )
            ),
            total_turns,
        )
        repair_turns = max(0, total_turns - origin)

    classification = str(summary.get("classification"))
    if summary.get("diagnostic_grade") is not None:
        final_failure_class = (
            "scientific" if not summary.get("complete_mission_success") else "success"
        )
    elif classification in {"infrastructure_failure", "unknown_harness_failure"}:
        final_failure_class = "infrastructure"
    elif classification in {"provider_adapter_failure", "provider_policy_refusal"}:
        final_failure_class = "provider"
    elif rejections:
        final_failure_class = "completion_with_contract_friction"
    else:
        final_failure_class = "completion"
    return {
        "accepted_submission_count": sum(
            row.get("event") == "submit" for row in event_log
        ),
        "rejected_submission_count": len(rejections),
        "distinct_rejection_codes": dict(sorted(codes.items())),
        "first_rejected_field": first_issue.get("path") if first_issue else None,
        "first_rejection_code": first_issue.get("code") if first_issue else None,
        "machine_rule_disclosed_to_agent": (
            all(row["disclosed"] for row in disclosure) if issues else None
        ),
        "first_rejected_rule_disclosed": (
            disclosure[0]["disclosed"] if disclosure else None
        ),
        "undisclosed_machine_requirements": sorted(
            {
                f"{row['code']}:{row['path']}"
                for row in disclosure
                if not row["disclosed"]
            }
        ),
        "rejection_signature_repeated": any(
            count > 1 for count in Counter(signatures).values()
        ),
        "identical_payload_repeated": any(
            count > 1 for count in Counter(payload_hashes).values()
        ),
        "turns_spent_after_first_submission_attempt": repair_turns,
        "tool_actions_spent_from_first_submission_attempt": actions_after_first,
        "trajectory_fraction_after_first_submission_attempt": (
            repair_turns / total_turns if total_turns else 0.0
        ),
        "substantive_scientific_work_complete_before_first_rejection": (
            substantive_before_first_rejection
        ),
        "final_failure_class": final_failure_class,
    }


def analyze_rc12_submission_friction(project_root: Path) -> dict[str, Any]:
    """Audit RC1.2 contract burden separately without changing old scores."""

    root = project_root.resolve()
    paths = sorted(
        (root / "build/uc_bench_mmmvp_open_rc12_runs").glob("*/run_summary.json")
    )
    rows: list[dict[str, Any]] = []
    for path in paths:
        summary = json.loads(path.read_text())
        rows.append(
            {
                "model_id": summary["model_id"],
                "source_summary": path.relative_to(root).as_posix(),
                "source_classification_unchanged": summary["classification"],
                "source_scientific_score_unchanged": summary.get(
                    "partial_scientific_quality"
                ),
                "friction": submission_friction(summary),
            }
        )
    provider_counts: Counter[str] = Counter()
    for row in rows:
        for code in row["friction"]["distinct_rejection_codes"]:
            provider_counts[code] += 1
    substantive = [
        row
        for row in rows
        if row["friction"][
            "substantive_scientific_work_complete_before_first_rejection"
        ]
    ]
    contract_only = [
        row
        for row in substantive
        if row["friction"]["final_failure_class"]
        == "completion_with_contract_friction"
    ]
    heavy = [
        row
        for row in rows
        if row["friction"]["trajectory_fraction_after_first_submission_attempt"]
        > 0.25
    ]
    undisclosed = [
        row
        for row in rows
        if row["friction"]["machine_rule_disclosed_to_agent"] is False
    ]
    warnings: list[str] = []
    if any(count >= 3 for count in provider_counts.values()):
        warnings.append("same_contract_requirement_blocked_three_or_more_providers")
    if substantive and len(contract_only) >= len(substantive) / 2:
        warnings.append("at_least_half_substantive_attempts_failed_only_at_submission")
    if undisclosed:
        warnings.append("machine_enforced_rule_not_disclosed_to_agent")
    if len(heavy) >= 2:
        warnings.append("contract_repair_consumed_over_quarter_for_multiple_models")
    value = {
        "schema_version": "uc-bench-open-mmmvp-rc1-3-rc12-friction-audit-1",
        "status": "construct_validity_warning" if warnings else "no_warning",
        "source_version": "RC1.2",
        "source_trajectories_reused_for_rc13_scoring": False,
        "source_scores_reinterpreted": False,
        "model_count": len(rows),
        "models": rows,
        "rejection_code_provider_counts": dict(sorted(provider_counts.items())),
        "substantive_attempt_count": len(substantive),
        "contract_only_substantive_failure_count": len(contract_only),
        "heavy_contract_repair_model_count": len(heavy),
        "undisclosed_rule_model_count": len(undisclosed),
        "warnings": warnings,
        "key_evidence": {
            "shared_first_rejected_field": "calculations[0].unit_of_analysis",
            "affected_models": [
                row["model_id"]
                for row in rows
                if row["friction"]["first_rejected_field"]
                == "calculations[0].unit_of_analysis"
            ],
            "accepted_values_enforced_privately": [
                "BIOLOGICAL_ENTITY",
                "SOURCE_RECORD_CLUSTERED",
            ],
            "accepted_values_present_in_agent_visible_enums": False,
        },
        "interpretation": (
            "RC1.2 provides evidence of an artificial contract/completion floor. "
            "This diagnostic does not change any RC1.2 result and the schema remains "
            "unchanged in RC1.3."
        ),
    }
    target = root / RC12_FRICTION_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    _write_json(target, value, secret="")
    return value


def analyze_rc13_sentinel(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    state_path = root / "artifacts/mmmvp_open_rc13/sentinel_state.json"
    cost = json.loads(
        (root / "artifacts/mmmvp_open_rc13/cost_plan.json").read_text()
    )
    if not state_path.is_file():
        value = {
            "schema_version": "uc-bench-open-mmmvp-rc1-3-sentinel-analysis-1",
            "status": "not_executed",
            "reason": "predeclared_cost_gate",
            "recommendation": "NO_GO_COST_GATE",
            "models": [],
            "construct_validity": {
                "case_2_gradient": "insufficient_evidence",
                "artificial_contract_or_completion_floor": "not_assessed_in_rc13",
            },
            "cost_plan": cost,
            "remaining_matrix_launched": False,
        }
    else:
        state = json.loads(state_path.read_text())
        models: list[dict[str, Any]] = []
        for relative in state.get("summary_paths") or []:
            summary = json.loads((root / relative).read_text())
            grade = summary.get("diagnostic_grade") or {}
            models.append(
                {
                    "model_id": summary["model_id"],
                    "classification": summary["classification"],
                    "complete_mission_success": summary.get(
                        "complete_mission_success"
                    ),
                    "partial_scientific_quality": summary.get(
                        "partial_scientific_quality"
                    ),
                    "reliability_score": summary.get("reliability_score"),
                    "first_decision_critical_failure": grade.get(
                        "first_decision_critical_failure"
                    ),
                    "submission_friction": submission_friction(summary),
                    "framework_tool_error_count": summary.get(
                        "framework_tool_error_count", 0
                    ),
                    "framework_tool_error_classes": summary.get(
                        "framework_tool_error_classes", {}
                    ),
                    "wrapper_tool_error_count": summary.get(
                        "wrapper_tool_error_count", 0
                    ),
                    "turns": summary.get("turn_count"),
                    "tool_calls": summary.get("tool_call_count"),
                    "cost_usd": summary.get("cumulative_reported_cost_usd"),
                }
            )
        code_provider_counts: Counter[str] = Counter()
        contract_only_substantive = 0
        heavy_contract_repair = 0
        for row in models:
            friction = row["submission_friction"]
            for code in friction["distinct_rejection_codes"]:
                code_provider_counts[code] += 1
            if (
                friction["substantive_scientific_work_complete_before_first_rejection"]
                and row["complete_mission_success"] is None
                and friction["rejected_submission_count"]
            ):
                contract_only_substantive += 1
            if friction["trajectory_fraction_after_first_submission_attempt"] > 0.25:
                heavy_contract_repair += 1
        warnings: list[str] = []
        if any(count >= 3 for count in code_provider_counts.values()):
            warnings.append("same_contract_requirement_blocked_three_or_more_providers")
        if models and contract_only_substantive >= len(models) / 2:
            warnings.append("at_least_half_substantive_attempts_failed_at_submission")
        if heavy_contract_repair >= 3:
            warnings.append("contract_repair_exceeded_quarter_trajectory_for_several_models")
        value = {
            "schema_version": "uc-bench-open-mmmvp-rc1-3-sentinel-analysis-1",
            "status": state.get("status"),
            "recommendation": (
                "NO_GO" if state.get("stop_faults") else "MANDATORY_REVIEW"
            ),
            "execution_order": state.get("execution_order"),
            "models": models,
            "construct_validity_warnings": warnings,
            "rejection_code_provider_counts": dict(code_provider_counts),
            "cost_plan": cost,
            "remaining_matrix_launched": False,
        }
    target = root / ANALYSIS_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    _write_json(target, value, secret="")
    return value


__all__ = [
    "ANALYSIS_PATH",
    "RC12_FRICTION_PATH",
    "REPORT_PATH",
    "analyze_rc12_submission_friction",
    "analyze_rc13_sentinel",
    "submission_friction",
]

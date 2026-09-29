"""Validation for the diagnostic task-family design contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from uc_bench.errors import ContractError

TERMINAL_DECISIONS = {"advance", "stop", "insufficient_evidence"}
IMPLEMENTATION_STATES = {"specified", "runnable"}
SOURCES = {"authentic", "controlled", "authentic_and_controlled"}
SCOPES = {"end_to_end", "milestone", "post_reveal"}


@dataclass(frozen=True, slots=True)
class DiagnosticSuiteValidation:
    task_count: int
    runnable_task_count: int
    decision_classes: tuple[str, ...]
    latent_detection_rule_passed: bool
    paired_intervention_count: int
    calibration_ready: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_count": self.task_count,
            "runnable_task_count": self.runnable_task_count,
            "decision_classes": list(self.decision_classes),
            "latent_detection_rule_passed": self.latent_detection_rule_passed,
            "paired_intervention_count": self.paired_intervention_count,
            "calibration_ready": self.calibration_ready,
        }


def validate_diagnostic_suite(value: dict[str, Any]) -> DiagnosticSuiteValidation:
    """Fail closed when the suite could manufacture or obscure a gradient."""

    if value.get("status") not in {"specified_not_frozen", "frozen"}:
        raise ContractError("Diagnostic suite status must be specified_not_frozen or frozen")
    rules = value.get("design_rules")
    if not isinstance(rules, dict):
        raise ContractError("Diagnostic suite requires design_rules")
    required_true_rules = {
        "single_domain_and_repo",
        "one_causal_change_per_pair",
        "latent_corruption_never_requires_exact_detection",
        "controlled_and_authentic_results_separate",
        "calibration_scenarios_separate_from_held_out_evaluation",
        "infrastructure_failures_excluded",
    }
    if any(rules.get(name) is not True for name in required_true_rules):
        raise ContractError("All anti-gimmick design rules must be enabled")
    if rules.get("unsubmitted_agent_attempt_score") != 0.0:
        raise ContractError("Unsubmitted agent attempts must score zero")

    tasks = value.get("tasks")
    if not isinstance(tasks, list) or len(tasks) != 10:
        raise ContractError("The v0 diagnostic catalog must contain exactly ten tasks")
    expected_ids = {f"T{index:02d}" for index in range(1, 11)}
    task_ids = {str(task.get("id")) for task in tasks if isinstance(task, dict)}
    if task_ids != expected_ids:
        raise ContractError("Diagnostic task IDs must be unique and contiguous T01-T10")
    if value.get("anchor_task_id") not in task_ids:
        raise ContractError("anchor_task_id must identify one catalog task")

    seen_decisions: set[str] = set()
    runnable = 0
    latent_rule_passed = True
    for task in tasks:
        if not isinstance(task, dict):
            raise ContractError("Diagnostic task entries must be objects")
        if task.get("scope") not in SCOPES:
            raise ContractError(f"Unsupported scope for {task.get('id')}")
        if task.get("source") not in SOURCES:
            raise ContractError(f"Unsupported source for {task.get('id')}")
        if task.get("implementation_status") not in IMPLEMENTATION_STATES:
            raise ContractError(f"Unsupported implementation status for {task.get('id')}")
        runnable += task.get("implementation_status") == "runnable"
        levels = task.get("levels")
        if not isinstance(levels, list) or not levels:
            raise ContractError(f"{task.get('id')} requires at least one difficulty level")
        decisions = task.get("expected_decisions")
        if not isinstance(decisions, list) or not decisions:
            raise ContractError(f"{task.get('id')} requires expected decisions")
        if not set(decisions) <= TERMINAL_DECISIONS:
            raise ContractError(f"{task.get('id')} has unsupported decisions")
        seen_decisions.update(decisions)
        outputs = task.get("diagnostic_outputs")
        if not isinstance(outputs, list) or not outputs:
            raise ContractError(f"{task.get('id')} requires machine-readable outputs")
        if str(task.get("observability", "")).startswith("latent_"):
            latent_rule_passed = latent_rule_passed and (
                task.get("agent_must_identify_exact_planted_items") is False
            )
    if not latent_rule_passed:
        raise ContractError("Latent variants may not require exact planted-item detection")
    minimum_decisions = int(rules["minimum_terminal_decision_classes"])
    if len(seen_decisions) < minimum_decisions:
        raise ContractError("Suite does not symmetrically cover terminal decisions")

    interventions = value.get("paired_interventions")
    if not isinstance(interventions, list) or len(interventions) < 3:
        raise ContractError("At least three causal paired interventions are required")
    for intervention in interventions:
        changes = intervention.get("changes") if isinstance(intervention, dict) else None
        if not isinstance(changes, list) or len(changes) != 1:
            raise ContractError("Each paired intervention must change exactly one factor")

    gate = value.get("calibration_gate")
    if not isinstance(gate, dict):
        raise ContractError("Diagnostic suite requires a calibration gate")
    calibration_ready = runnable >= int(gate["minimum_task_ids"])
    return DiagnosticSuiteValidation(
        task_count=len(tasks),
        runnable_task_count=runnable,
        decision_classes=tuple(sorted(seen_decisions)),
        latent_detection_rule_passed=latent_rule_passed,
        paired_intervention_count=len(interventions),
        calibration_ready=calibration_ready,
    )

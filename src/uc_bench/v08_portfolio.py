"""Validation helpers for the unfrozen v0.8 development portfolio."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REQUIRED_CARD_FIELDS = {
    "case_id",
    "title",
    "important_failure",
    "professional_importance",
    "available_evidence",
    "required_calculations",
    "consequential_choice",
    "defensible_choices",
    "real_harm_from_error",
    "verifier_recomputation",
    "requirement_classes",
    "hidden_variants",
    "failure_interventions",
    "contract_trap_audit",
}
REQUIREMENT_CLASSES = {
    "mission_critical_science",
    "accepted_professional_alternative",
    "diagnostic_only",
}
INTERVENTION_CLASSES = {
    "additional_data",
    "better_metadata",
    "expert_input",
    "tool_or_process",
    "model_adaptation",
}


@dataclass(frozen=True, slots=True)
class PortfolioValidation:
    passed: bool
    errors: tuple[str, ...]
    investigation_count: int
    controlled_state_count: int
    new_investigation_count: int
    trap_free_case_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "errors": list(self.errors),
            "investigation_count": self.investigation_count,
            "controlled_state_count": self.controlled_state_count,
            "new_investigation_count": self.new_investigation_count,
            "trap_free_case_count": self.trap_free_case_count,
        }


def load_v08_portfolio(project_root: Path) -> dict[str, Any]:
    path = project_root / "configs/hard_suite_v08_case_portfolio.json"
    return json.loads(path.read_text(encoding="utf-8"))


def validate_v08_portfolio(portfolio: dict[str, Any]) -> PortfolioValidation:
    errors: list[str] = []
    cases = portfolio.get("cases")
    if not isinstance(cases, list):
        return PortfolioValidation(False, ("cases:list_required",), 0, 0, 0, 0)
    if not 6 <= len(cases) <= 8:
        errors.append("portfolio_requires_six_to_eight_investigations")
    ids = [row.get("case_id") for row in cases if isinstance(row, dict)]
    if len(ids) != len(set(ids)):
        errors.append("case_ids_must_be_unique")
    controlled_states = 0
    new_cases = 0
    trap_free = 0
    for case in cases:
        if not isinstance(case, dict):
            errors.append("case:object_required")
            continue
        case_id = str(case.get("case_id", "missing"))
        missing = sorted(REQUIRED_CARD_FIELDS - set(case))
        if missing:
            errors.append(f"{case_id}:missing_fields:{','.join(missing)}")
            continue
        if case.get("origin") == "New development investigation":
            new_cases += 1
        if not case["available_evidence"]:
            errors.append(f"{case_id}:available_evidence_empty")
        if not case["required_calculations"]:
            errors.append(f"{case_id}:required_calculations_empty")
        if not str(case["consequential_choice"]).strip():
            errors.append(f"{case_id}:consequential_choice_empty")
        classes = case["requirement_classes"]
        if set(classes) != REQUIREMENT_CLASSES:
            errors.append(f"{case_id}:requirement_classes_incomplete")
        elif any(not classes[name] for name in REQUIREMENT_CLASSES):
            errors.append(f"{case_id}:requirement_class_empty")
        variants = case["hidden_variants"]
        controlled_states += len(variants)
        if len(variants) < 2:
            errors.append(f"{case_id}:paired_hidden_variants_required")
        else:
            start_states = {row.get("shared_start_state_id") for row in variants}
            decisions = {row.get("supported_final_action") for row in variants}
            if len(start_states) != 1:
                errors.append(f"{case_id}:variants_must_share_initial_appearance")
            if len(decisions) < 2:
                errors.append(f"{case_id}:variants_must_change_supported_action")
        for intervention in case["failure_interventions"]:
            if intervention.get("intervention_class") not in INTERVENTION_CLASSES:
                errors.append(f"{case_id}:unknown_intervention_class")
            if intervention.get("demonstrated_only_if_paired") is not True:
                errors.append(f"{case_id}:intervention_claim_not_conditioned_on_pair")
        trap = case["contract_trap_audit"]
        forbidden = (
            trap.get("requires_exact_prose"),
            trap.get("requires_hidden_filename"),
            trap.get("requires_one_statistical_method"),
            trap.get("withholds_decision_critical_evidence"),
        )
        if any(value is not False for value in forbidden):
            errors.append(f"{case_id}:contract_trap_present")
        else:
            trap_free += 1
        if not str(trap.get("difficulty_source", "")).strip():
            errors.append(f"{case_id}:difficulty_source_missing")
    summary = portfolio.get("portfolio_summary", {})
    if summary.get("investigations") != len(cases):
        errors.append("portfolio_summary_investigation_count_mismatch")
    if summary.get("controlled_states") != controlled_states:
        errors.append("portfolio_summary_controlled_state_count_mismatch")
    if summary.get("new_investigations") != new_cases:
        errors.append("portfolio_summary_new_investigation_count_mismatch")
    if summary.get("final_cases_created") is not False:
        errors.append("final_cases_must_not_exist_during_development_design")
    return PortfolioValidation(
        passed=not errors,
        errors=tuple(errors),
        investigation_count=len(cases),
        controlled_state_count=controlled_states,
        new_investigation_count=new_cases,
        trap_free_case_count=trap_free,
    )


__all__ = [
    "INTERVENTION_CLASSES",
    "PortfolioValidation",
    "load_v08_portfolio",
    "validate_v08_portfolio",
]

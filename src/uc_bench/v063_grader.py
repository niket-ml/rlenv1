"""Total, partial-credit-preserving grader boundary for v0.6.3.

The scientific invariants and scoring functions remain those frozen in v0.6.
This boundary normalizes only invalid container/numeric types before individual
property checks, so one malformed field cannot crash or mechanically erase the
other valid properties of an artifact.
"""

from __future__ import annotations

import copy
import math
from dataclasses import replace
from pathlib import Path
from threading import RLock
from typing import Any

import uc_bench.hard_suite_v06 as v06

_GRADE_LOCK = RLock()


def _issue(
    issues: list[dict[str, Any]], relative: str, field: str, value: Any
) -> None:
    issues.append(
        {
            "tag": "semantic_type_error",
            "artifact": relative,
            "evidence": f"{field}: expected a grader-compatible type, got {type(value).__name__}",
            "field": field,
            "observed_type": type(value).__name__,
        }
    )


def _safe_list_field(
    value: dict[str, Any],
    field: str,
    *,
    relative: str,
    issues: list[dict[str, Any]],
) -> None:
    observed = value.get(field)
    if not isinstance(observed, list):
        _issue(issues, relative, field, observed)
        value[field] = []


def _safe_dict_field(
    value: dict[str, Any],
    field: str,
    *,
    relative: str,
    issues: list[dict[str, Any]],
) -> None:
    observed = value.get(field)
    if not isinstance(observed, dict):
        _issue(issues, relative, field, observed)
        value[field] = {}


def _safe_numeric_field(
    value: dict[str, Any],
    field: str,
    *,
    relative: str,
    issues: list[dict[str, Any]],
) -> None:
    observed = value.get(field)
    try:
        number = float(observed)
        valid = math.isfinite(number)
    except (TypeError, ValueError, OverflowError):
        valid = False
    if not valid:
        _issue(issues, relative, field, observed)
        value[field] = -1


def sanitize_artifact(
    relative: str,
    value: Any,
    issues: list[dict[str, Any]],
) -> Any:
    """Return a scorer-safe copy while retaining all valid properties."""

    safe = copy.deepcopy(value)
    if not isinstance(safe, (dict, list)):
        return safe
    if relative == "submission/cohort_inventory.csv" and isinstance(safe, list):
        for index, observed_row in enumerate(safe):
            if not isinstance(observed_row, dict):
                _issue(issues, relative, f"rows[{index}]", observed_row)
                safe[index] = {}
                continue
            row = observed_row
            for field in ("row_count", "patient_count"):
                before = len(issues)
                _safe_numeric_field(
                    row,
                    field,
                    relative=relative,
                    issues=issues,
                )
                if len(issues) > before:
                    issues[-1]["field"] = f"rows[{index}].{field}"
                    issues[-1]["evidence"] = (
                        f"rows[{index}].{field}: expected finite numeric content, "
                        f"got {issues[-1]['observed_type']}"
                    )
        return safe
    if relative == "submission/patient_visit_map.csv" and isinstance(safe, list):
        for index, observed_row in enumerate(safe):
            if not isinstance(observed_row, dict):
                _issue(issues, relative, f"rows[{index}]", observed_row)
                safe[index] = {}
        return safe
    if relative == "submission/reproduction_predictions.csv" and isinstance(safe, list):
        for index, observed_row in enumerate(safe):
            if not isinstance(observed_row, dict):
                _issue(issues, relative, f"rows[{index}]", observed_row)
                safe[index] = {}
                continue
            row = observed_row
            for field in (
                "reference_probability",
                "reproduced_probability",
                "absolute_error",
            ):
                before = len(issues)
                _safe_numeric_field(
                    row,
                    field,
                    relative=relative,
                    issues=issues,
                )
                if len(issues) > before:
                    issues[-1]["field"] = f"rows[{index}].{field}"
        return safe
    if not isinstance(safe, dict):
        return safe
    list_fields = {
        "submission/provenance_audit.json": ("findings", "evidence_refs"),
        "submission/endpoint_audit.json": ("label_sources", "evidence_refs"),
        "submission/preprocessing_lineage.json": ("steps", "evidence_refs"),
        "submission/committed_validation_plan.json": (
            "metric_families",
            "live_hypotheses",
            "analysis_artifact_paths",
            "evidence_refs",
        ),
        "submission/validation_results.json": ("evidence_refs",),
        "submission/resource_value_memo.json": (
            "resource_comparisons",
            "live_hypotheses",
            "evidence_refs",
        ),
        "submission/final_diligence_report.json": (
            "limitations",
            "supported_claims",
            "evidence_refs",
        ),
    }
    dict_fields = {
        "submission/committed_validation_plan.json": ("decision_rule",),
        "submission/validation_results.json": ("metrics", "claim_statuses"),
        "submission/final_diligence_report.json": (
            "belief_update",
            "smallest_next_action",
            "claim_statuses",
        ),
    }
    for field in list_fields.get(relative, ()):
        _safe_list_field(safe, field, relative=relative, issues=issues)
    for field in dict_fields.get(relative, ()):
        _safe_dict_field(safe, field, relative=relative, issues=issues)
    if relative == "submission/final_diligence_report.json":
        claims = safe.get("supported_claims") or []
        for index, claim in enumerate(claims):
            if not isinstance(claim, dict):
                continue
            if "evidence_refs" not in claim:
                continue
            observed = claim.get("evidence_refs")
            if not isinstance(observed, list):
                _issue(
                    issues,
                    relative,
                    f"supported_claims[{index}].evidence_refs",
                    observed,
                )
                claim["evidence_refs"] = []
    return safe


def _fallback_grade(
    project_root: Path,
    *,
    selected: str,
    error: BaseException,
) -> v06.V06Grade:
    config = v06.load_v06_config(project_root)
    scores = {row["id"]: 0.0 for row in config["artifacts"]}
    metadata = {row["id"]: row for row in config["artifacts"]}
    return v06.V06Grade(
        completed_artifact_quality=0.0,
        artifact_coverage=0.0,
        coverage_adjusted_scientific_score=0.0,
        reliability_inclusive_score=0.0,
        artifact_scores=scores,
        artifact_states={name: "invalid" for name in scores},
        family_scores={metadata[name]["family"]: 0.0 for name in scores},
        capability_scores={name: 0.0 for name in v06.V06_CAPABILITY_MAP},
        first_substantive_divergence="A01",
        downstream_artifacts_at_risk=list(metadata["A01"]["downstream_at_risk"]),
        selected_resource=selected,
        decision_policy_score=0.0,
        observed_initial_decision=None,
        observed_final_decision=None,
        observed_intervention_effect=None,
        process_annotations=[
            {
                "tag": "grader_internal_error",
                "artifact": "grader",
                "evidence": f"{type(error).__name__}: {str(error)[:500]}",
            }
        ],
        scientific_failure_annotations=[],
        completion_accepted=False,
    )


def grade_v063(
    project_root: Path,
    package: v06.V06Package,
    *,
    selected_resource: str | None = None,
    commitment_immutable: bool = False,
    completion_accepted: bool = False,
) -> v06.V06Grade:
    """Run frozen v0.6 scoring as a total function over agent artifacts."""

    issues: list[dict[str, Any]] = []
    with _GRADE_LOCK:
        original_read = v06._read_artifact  # noqa: SLF001 - versioned grader boundary

        def safe_read(path: Path) -> tuple[Any | None, str | None]:
            value, error = original_read(path)
            if error is not None:
                return value, error
            try:
                relative = path.resolve().relative_to(
                    package.workspace_root.resolve()
                ).as_posix()
            except ValueError:
                return value, error
            if relative in v06.ALL_ARTIFACTS:
                value = sanitize_artifact(relative, value, issues)
            return value, error

        try:
            v06._read_artifact = safe_read  # noqa: SLF001 - versioned grader boundary
            grade = v06.grade_v06(
                project_root,
                package,
                selected_resource=selected_resource,
                commitment_immutable=commitment_immutable,
                completion_accepted=completion_accepted,
            )
        except Exception as exc:
            grade = _fallback_grade(
                project_root,
                selected=selected_resource or "none",
                error=exc,
            )
        finally:
            v06._read_artifact = original_read  # noqa: SLF001 - restore boundary
    if issues:
        grade = replace(
            grade,
            process_annotations=[*grade.process_annotations, *issues],
        )
    return grade


def grader_infrastructure_failed(grade: v06.V06Grade | dict[str, Any]) -> bool:
    annotations = (
        grade.process_annotations
        if isinstance(grade, v06.V06Grade)
        else grade.get("process_annotations") or []
    )
    return any(
        row.get("tag")
        in {"grader_internal_error", "grader_property_evaluation_error"}
        for row in annotations
        if isinstance(row, dict)
    )


def emergency_v063_grade(
    project_root: Path, *, selected: str, error: BaseException
) -> v06.V06Grade:
    """Return an explicitly excluded diagnostic if the outer runner fails."""

    return _fallback_grade(project_root, selected=selected, error=error)

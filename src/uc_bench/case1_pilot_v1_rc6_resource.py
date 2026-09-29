"""One canonical resource-semantics path for Case-1 RC6.

RC6 is not allowed to change the model-visible RC5 checker.  The immutable
public checker is therefore the semantic oracle: this module calls that exact
checker and derives its structured verdict by counterfactual probing of only
the two disclosed machine fields (``material`` and ``observed_effect``).
The hidden grader consumes the resulting object directly and contains no
second resource-specific relevance/materiality/effect decision tree.
"""

from __future__ import annotations

import copy
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from uc_bench.case1_pilot_v1_rc5_normalization import NormalizationError
from uc_bench.case1_pilot_v1_rc5_public_recompute import (
    _resource_hashes_valid,
    expected_resource_results,
    verify_final_calculations,
)
from uc_bench.mmmvp_open_calculations import CalculationResult
from uc_bench.mmmvp_open_rc17_contract import QUESTION_RESOURCE
from uc_bench.mmmvp_open_rc17_verifier import ResourceResult

_IRRELEVANT = "selected resource is not relevant to the bounded current decision"
_EFFECT_MISMATCH = "resource observed_effect differs from recomputation"
_MATERIAL_MISMATCH = "resource material flag differs from recomputation"
_SUMMARY_MISSING = "resource summary artifact is missing"
_SUMMARY_INVALID = "resource summary identity or transitive source hashes are invalid"
_RESULT_KEYS = "resource summary result keys differ from recomputation"
_RESULT_PREFIX = "resource result does not recompute:"
_RESULT_UNAVAILABLE = "resource results cannot be recomputed:"
_REVISION_UNBOUND = "belief updates do not cite the resource summary"
_EMPIRICAL_UNLINKED = "empirical resource needs valid FOLLOWUP calculations"

_EFFECTS = (
    "EXPOSES_BLOCKER",
    "INEFFECTIVE",
    "MISLEADING_REASSURANCE",
    "NO_NEW_EVIDENCE",
    "REDUCES_UNCERTAINTY",
    "RESOLVES",
)


@dataclass(frozen=True, slots=True)
class ResourceSemantics:
    question_relevant: bool
    returned_evidence_authentic: bool
    returned_result_correct: bool
    expected_material: bool | None
    declared_material_correct: bool
    expected_effect: str | None
    declared_effect_correct: bool
    evidence_bound_to_revision: bool
    resource_property_pass: bool
    assessment_matches_commitment: bool
    resource_calculations_valid: bool
    expected_results: dict[str, Any]
    public_errors: tuple[str, ...]
    faults: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _safe_file(workspace: Path, relative: Any) -> Path | None:
    if not isinstance(relative, str) or not relative:
        return None
    candidate = (workspace / relative).resolve()
    return candidate if workspace in candidate.parents and candidate.is_file() else None


def _public_errors(
    workspace: Path, validation: dict[str, Any], final: dict[str, Any]
) -> tuple[str, ...]:
    try:
        return tuple(verify_final_calculations(workspace, validation, final))
    except (
        ArithmeticError,
        json.JSONDecodeError,
        KeyError,
        MemoryError,
        OSError,
        RecursionError,
        StopIteration,
        TypeError,
        UnicodeError,
        ValueError,
    ) as exc:
        return (f"resource results cannot be recomputed: {type(exc).__name__}",)


def _probe_expected_material(
    workspace: Path,
    validation: dict[str, Any],
    final: dict[str, Any],
    base_errors: tuple[str, ...],
) -> bool | None:
    assessment = final.get("resource_assessment") or {}
    declared = assessment.get("material")
    if not isinstance(declared, bool):
        return None
    if _MATERIAL_MISMATCH not in base_errors:
        return declared
    probe = copy.deepcopy(final)
    probe["resource_assessment"]["material"] = not declared
    return not declared if _MATERIAL_MISMATCH not in _public_errors(
        workspace, validation, probe
    ) else None


def _probe_expected_effect(
    workspace: Path,
    validation: dict[str, Any],
    final: dict[str, Any],
    base_errors: tuple[str, ...],
) -> str | None:
    assessment = final.get("resource_assessment") or {}
    declared = assessment.get("observed_effect")
    if isinstance(declared, str) and _EFFECT_MISMATCH not in base_errors:
        return declared
    matches: list[str] = []
    for effect in _EFFECTS:
        probe = copy.deepcopy(final)
        probe.setdefault("resource_assessment", {})["observed_effect"] = effect
        if _EFFECT_MISMATCH not in _public_errors(workspace, validation, probe):
            matches.append(effect)
    return matches[0] if len(matches) == 1 else None


def _expected_results(
    workspace: Path,
    validation: dict[str, Any],
    resource: str,
    calculations: dict[str, CalculationResult],
) -> dict[str, Any]:
    try:
        primary_id = next(
            str(row["calculation_id"])
            for row in validation.get("decision_criteria") or []
            if row.get("property") == "DISCRIMINATION"
        )
        primary = calculations.get(primary_id)
        primary_auc = (
            float(primary.recomputed_value)
            if primary is not None and primary.recomputed_value is not None
            else math.nan
        )
        return expected_resource_results(
            workspace,
            validation,
            resource,
            primary_auc=primary_auc,
        )
    except (
        ArithmeticError,
        json.JSONDecodeError,
        KeyError,
        MemoryError,
        OSError,
        RecursionError,
        StopIteration,
        TypeError,
        UnicodeError,
        ValueError,
    ):
        return {}


def evaluate_resource_semantics(
    workspace: Path,
    submission: dict[str, Any],
    calculations: dict[str, CalculationResult],
) -> ResourceSemantics:
    """Return resource facts from the immutable public checker, once."""

    workspace = workspace.resolve()
    validation = submission.get("validation_plan") or {}
    followup = submission.get("followup_plan") or {}
    final = submission.get("final_submission") or {}
    assessment = final.get("resource_assessment") or {}
    resource = str(followup.get("chosen_resource") or "")
    base_errors = _public_errors(workspace, validation, final)

    expected_material = _probe_expected_material(
        workspace, validation, final, base_errors
    )
    expected_effect = _probe_expected_effect(workspace, validation, final, base_errors)
    expected_results = _expected_results(workspace, validation, resource, calculations)

    assessment_matches = bool(
        assessment.get("resource_id") == resource
        and assessment.get("question_type") == followup.get("decision_question_type")
        and QUESTION_RESOURCE.get(followup.get("decision_question_type")) == resource
    )
    summary_path = _safe_file(workspace, assessment.get("summary_artifact_path"))
    authentic = False
    result_correct = False
    if summary_path is not None:
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            authentic = bool(
                isinstance(summary, dict)
                and summary.get("schema_version") == "case1-resource-summary-1"
                and summary.get("resource_id") == resource
                and _resource_hashes_valid(workspace, resource, summary)
            )
            observed = summary.get("results") if isinstance(summary, dict) else None
            if isinstance(observed, dict) and set(observed) == set(expected_results):
                result_correct = all(
                    (
                        got is wanted
                        if isinstance(wanted, bool)
                        else isinstance(got, (int, float))
                        and not isinstance(got, bool)
                        and math.isclose(float(got), float(wanted), abs_tol=0.002)
                    )
                    for key, wanted in expected_results.items()
                    for got in (observed[key],)
                )
        except (
            ArithmeticError,
            json.JSONDecodeError,
            KeyError,
            MemoryError,
            OSError,
            RecursionError,
            TypeError,
            UnicodeError,
            ValueError,
            NormalizationError,
        ):
            authentic = result_correct = False

    calculation_ids = set(assessment.get("calculation_ids") or [])
    resource_calculations_valid = bool(
        calculation_ids.issubset(calculations)
        and all(
            calculations[identifier].valid
            and calculations[identifier].role == "FOLLOWUP"
            for identifier in calculation_ids
        )
        and (resource not in {"X17", "X31", "X46"} or bool(calculation_ids))
    )
    summary_relative = str(assessment.get("summary_artifact_path") or "")
    belief_rows = [
        row for row in final.get("belief_updates") or [] if isinstance(row, dict)
    ]
    evidence_bound = bool(
        belief_rows
        and all(summary_relative in set(row.get("evidence_refs") or []) for row in belief_rows)
    )
    declared_material_correct = bool(
        expected_material is not None
        and assessment.get("material") is expected_material
    )
    declared_effect_correct = bool(
        expected_effect is not None
        and assessment.get("observed_effect") == expected_effect
    )
    relevant = _IRRELEVANT not in base_errors

    faults: list[str] = []
    checks = (
        (assessment_matches, "assessment_commitment_mismatch"),
        (relevant, "question_not_relevant"),
        (authentic, "returned_evidence_not_authentic"),
        (result_correct, "returned_result_incorrect"),
        (declared_material_correct, "declared_material_incorrect"),
        (declared_effect_correct, "declared_effect_incorrect"),
        (evidence_bound, "resource_not_bound_to_revision"),
        (resource_calculations_valid, "resource_calculation_reference_invalid"),
    )
    faults.extend(code for passed, code in checks if not passed)
    resource_pass = all(passed for passed, _code in checks)
    return ResourceSemantics(
        question_relevant=relevant,
        returned_evidence_authentic=authentic,
        returned_result_correct=result_correct,
        expected_material=expected_material,
        declared_material_correct=declared_material_correct,
        expected_effect=expected_effect,
        declared_effect_correct=declared_effect_correct,
        evidence_bound_to_revision=evidence_bound,
        resource_property_pass=resource_pass,
        assessment_matches_commitment=assessment_matches,
        resource_calculations_valid=resource_calculations_valid,
        expected_results=expected_results,
        public_errors=base_errors,
        faults=tuple(faults),
    )


def hidden_resource_result_from_public_semantics(
    workspace: Path,
    submission: dict[str, Any],
    calculations: dict[str, CalculationResult],
    *_unused: Any,
) -> ResourceResult:
    """Adapter used directly by the hidden verifier; no semantic tree lives here."""

    facts = evaluate_resource_semantics(workspace, submission, calculations)
    return resource_result_from_semantics(facts)


def resource_result_from_semantics(facts: ResourceSemantics) -> ResourceResult:
    """Translate structured public facts without reevaluating any semantics."""

    technical_valid = bool(
        facts.assessment_matches_commitment
        and facts.returned_evidence_authentic
        and facts.returned_result_correct
        and facts.declared_material_correct
        and facts.declared_effect_correct
        and facts.resource_calculations_valid
    )
    return ResourceResult(
        valid=technical_valid,
        relevant=facts.question_relevant,
        used=bool(technical_valid and facts.evidence_bound_to_revision),
        observed_effect=facts.expected_effect,
        material=facts.expected_material,
        expected_results=facts.expected_results,
        faults=facts.faults,
    )


__all__ = [
    "ResourceSemantics",
    "evaluate_resource_semantics",
    "hidden_resource_result_from_public_semantics",
    "resource_result_from_semantics",
]

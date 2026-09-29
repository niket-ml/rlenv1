"""Agent-visible, mechanical submission validation for v0.8 development.

The scientific verifier never infers meaning from prose.  This module checks
only the disclosed transport contract and leaves all scientific adjudication
to :mod:`uc_bench.v08_verifier`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from uc_bench.v072_schema import SCHEMA_VERSION as V072_SCHEMA_VERSION
from uc_bench.v072_schema import SchemaIssue, normalize_checkpoint
from uc_bench.v08_verifier import validate_belief_change, validate_decision_object

SCHEMA_VERSION = "0.8-development-submission-1"
DECISION_QUESTION_ENUM = {
    "CURRENT_PROBABILITY_USE",
    "PATIENT_IDENTITY",
    "TRANSPORT",
    "CLEAN_PIPELINE_SIGNAL",
}


@dataclass(frozen=True, slots=True)
class V08SchemaResult:
    checkpoint: str
    issues: tuple[SchemaIssue, ...]

    @property
    def valid(self) -> bool:
        return not self.issues


def _issue(checkpoint: str, path: str, code: str, message: str) -> SchemaIssue:
    return SchemaIssue(checkpoint, path, code, message)


def _carrier(payload: dict[str, Any], field: str) -> Any:
    direct = payload.get(field)
    facts = payload.get("facts")
    nested = facts.get(field) if isinstance(facts, dict) else None
    return direct if field in payload else nested


def _legacy_compatible_issues(
    checkpoint: str, payload: dict[str, Any]
) -> list[SchemaIssue]:
    translated = dict(payload)
    translated["schema_version"] = V072_SCHEMA_VERSION
    return list(normalize_checkpoint(checkpoint, translated).issues)


def _validate_c4(payload: dict[str, Any], issues: list[SchemaIssue]) -> None:
    checkpoint = "C4"
    question = _carrier(payload, "decision_question")
    if question not in DECISION_QUESTION_ENUM:
        issues.append(
            _issue(
                checkpoint,
                "decision_question",
                "invalid_enum",
                f"Expected one of {sorted(DECISION_QUESTION_ENUM)}",
            )
        )
    why = _carrier(payload, "why_decision_resolving")
    if not isinstance(why, str) or not why.strip():
        issues.append(
            _issue(
                checkpoint,
                "why_decision_resolving",
                "missing_field",
                "Explain why the chosen resource resolves the declared decision question",
            )
        )
    initial = _carrier(payload, "initial_decision")
    if not isinstance(initial, dict):
        issues.append(
            _issue(
                checkpoint,
                "initial_decision",
                "missing_field",
                "Complete pre-investigation decision object is required",
            )
        )
    else:
        for error in validate_decision_object(initial):
            issues.append(
                _issue(checkpoint, "initial_decision", "invalid_value", error)
            )


def _validate_c5(payload: dict[str, Any], issues: list[SchemaIssue]) -> None:
    checkpoint = "C5"
    # Retain the unchanged v0.7 scientific fields, but do not require its
    # superseded direction label or bare decision labels.
    translated = dict(payload)
    translated["schema_version"] = V072_SCHEMA_VERSION
    translated["belief_update"] = {
        "before": "superseded",
        "after": "superseded",
        "direction": "UNCHANGED_SUPPORTED",
    }
    translated["decisions"] = {
        "initial": "INSUFFICIENT_EVIDENCE",
        "final": "INSUFFICIENT_EVIDENCE",
    }
    issues.extend(normalize_checkpoint(checkpoint, translated).issues)

    belief = _carrier(payload, "belief_change")
    if not isinstance(belief, dict):
        issues.append(
            _issue(
                checkpoint,
                "belief_change",
                "missing_field",
                "Numeric belief_change object is required",
            )
        )
    else:
        for error in validate_belief_change(belief):
            issues.append(_issue(checkpoint, "belief_change", "invalid_value", error))

    decision = _carrier(payload, "decision")
    if not isinstance(decision, dict):
        issues.append(
            _issue(
                checkpoint,
                "decision",
                "missing_field",
                "Explicit development decision object is required",
            )
        )
    else:
        for error in validate_decision_object(decision):
            issues.append(_issue(checkpoint, "decision", "invalid_value", error))

    analysis = _carrier(payload, "investigation_analysis")
    if not isinstance(analysis, dict):
        return
    manifest = analysis.get("artifact_manifest")
    if not isinstance(manifest, dict) or not isinstance(
        manifest.get("calculated_outputs_path"), str
    ) or not manifest["calculated_outputs_path"].strip():
        issues.append(
            _issue(
                checkpoint,
                "investigation_analysis.artifact_manifest.calculated_outputs_path",
                "missing_artifact_path",
                "A saved follow-up calculation artifact is required",
            )
        )
    evidence = analysis.get("evidence_paths")
    if not isinstance(evidence, list) or not evidence or not all(
        isinstance(row, str) and row.strip() for row in evidence
    ):
        issues.append(
            _issue(
                checkpoint,
                "investigation_analysis.evidence_paths",
                "invalid_value",
                "At least one follow-up evidence path is required",
            )
        )


def validate_v08_checkpoint(checkpoint: str, payload: Any) -> V08SchemaResult:
    """Validate one checkpoint without inspecting its scientific conclusion."""

    checkpoint = checkpoint.upper()
    issues: list[SchemaIssue] = []
    if not isinstance(payload, dict):
        return V08SchemaResult(
            checkpoint,
            (
                _issue(checkpoint, "$", "invalid_payload", "Expected a JSON object"),
            ),
        )
    if payload.get("schema_version") != SCHEMA_VERSION:
        issues.append(
            _issue(
                checkpoint,
                "schema_version",
                "invalid_schema_version",
                f"Expected {SCHEMA_VERSION}",
            )
        )
    if checkpoint == "C5":
        _validate_c5(payload, issues)
    else:
        issues.extend(_legacy_compatible_issues(checkpoint, payload))
        if checkpoint == "C4":
            _validate_c4(payload, issues)
    return V08SchemaResult(checkpoint, tuple(issues))


__all__ = [
    "DECISION_QUESTION_ENUM",
    "SCHEMA_VERSION",
    "V08SchemaResult",
    "validate_v08_checkpoint",
]

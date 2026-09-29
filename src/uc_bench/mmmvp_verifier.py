"""Final construct-valid verifier corrections over the unchanged v0.8 calculations."""

from __future__ import annotations

import csv
import hashlib
import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from statistics import mean
from typing import Any

from uc_bench.mmmvp_schema import TARGET_HYPOTHESIS_ID
from uc_bench.mmmvp_score_sources import score_source_for
from uc_bench.v08_verifier import (
    CHECKPOINT_WEIGHTS,
    RequirementResult,
    V08ReplayGrade,
    verify_v08_submission,
)

SUITE_PATH = Path("configs/uc_bench_mmmvp_suite.json")


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _condition_policy(project_root: Path, condition_id: str) -> dict[str, Any]:
    suite = _read_object(project_root / SUITE_PATH)
    rows = [row for row in suite["conditions"] if row["condition_id"] == condition_id]
    if len(rows) != 1:
        raise ValueError(f"Unknown or duplicate MMMVP condition: {condition_id}")
    return rows[0]


def _carrier(payload: dict[str, Any], field: str) -> Any:
    facts = payload.get("facts")
    nested = facts.get(field) if isinstance(facts, dict) else None
    return payload.get(field) if field in payload else nested


def _normalise_for_v08(
    submission: dict[str, Any], *, legacy_replay: bool
) -> dict[str, Any]:
    value = deepcopy(submission)
    checkpoints = value.get("checkpoints") or {}
    for payload in checkpoints.values():
        if isinstance(payload, dict):
            payload["schema_version"] = "0.8-development-submission-1"
    c3 = checkpoints.get("C3") or {}
    contamination = _carrier(c3, "preprocessing_and_contamination")
    if isinstance(contamination, dict):
        if "primary_evidence_eligible" not in contamination and legacy_replay:
            contamination["primary_evidence_eligible"] = bool(
                contamination.get("contaminated_evidence_eligible")
            )
        contamination.setdefault(
            "contaminated_evidence_eligible",
            bool(contamination.get("primary_evidence_eligible")),
        )
    c4 = checkpoints.get("C4") or {}
    prediction = _carrier(c4, "prediction_before_investigation")
    c5 = checkpoints.get("C5") or {}
    belief = _carrier(c5, "belief_change")
    if legacy_replay:
        if isinstance(prediction, dict):
            prediction.setdefault("target_hypothesis_id", TARGET_HYPOTHESIS_ID)
        if isinstance(belief, dict):
            belief.setdefault("target_hypothesis_id", TARGET_HYPOTHESIS_ID)
    committed = hashlib.sha256(
        json.dumps(
            checkpoints["C2"], sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    for event in value.get("event_log") or []:
        if event.get("event") == "save_checkpoint" and event.get("schema_valid") is not False:
            checkpoint = event.get("checkpoint")
            if checkpoint in checkpoints:
                event["digest"] = hashlib.sha256(
                    json.dumps(
                        checkpoints[checkpoint], sort_keys=True, separators=(",", ":")
                    ).encode()
                ).hexdigest()
        elif event.get("event") == "commit_validation_plan":
            event["digest"] = committed
        elif event.get("event") in {"reveal_validation", "submit"}:
            event["committed_plan_hash"] = committed
    return value


def _independent_contamination(workspace: Path) -> tuple[bool, list[str]]:
    path = workspace / "pipeline/fit_membership.csv"
    rows = list(csv.DictReader(path.open(encoding="utf-8", newline="")))
    contaminated_samples = [
        str(row.get("sample_id"))
        for row in rows
        if str(row.get("cohort_role", "")).strip().lower() == "validation"
        and str(row.get("included_in_reference_fit", "")).strip().lower()
        in {"true", "1", "yes"}
    ]
    return bool(contaminated_samples), contaminated_samples


def _requirement(
    *,
    requirement_id: str,
    checkpoint: str,
    passed: bool,
    observed: Any,
    expected: Any,
    consequence: str,
    remedy: str,
    evidence: tuple[str, ...] = (),
) -> RequirementResult:
    return RequirementResult(
        requirement_id=requirement_id,
        checkpoint=checkpoint,
        requirement_class="mission_critical_science",
        passed=bool(passed),
        score=100.0 if passed else 0.0,
        observed=observed,
        expected=expected,
        consequence=consequence,
        remedy=remedy,
        evidence=evidence,
    )


def _direction_passed(rule: str, delta: float) -> bool:
    return {
        "INCREASE": delta > 0,
        "DECREASE": delta < 0,
        "NONDECREASE": delta >= 0,
        "NONINCREASE": delta <= 0,
        "UNCHANGED": abs(delta) <= 1e-12,
    }[rule]


def _replace_requirement(
    requirements: list[RequirementResult], replacement: RequirementResult
) -> None:
    indices = [
        index
        for index, row in enumerate(requirements)
        if row.requirement_id == replacement.requirement_id
    ]
    if len(indices) != 1:
        raise AssertionError(
            f"Expected one {replacement.requirement_id} requirement, found {len(indices)}"
        )
    requirements[indices[0]] = replacement


def _checkpoint_score(rows: list[RequirementResult], checkpoint: str) -> float:
    selected = [
        row
        for row in rows
        if row.checkpoint == checkpoint
        and row.requirement_class == "mission_critical_science"
    ]
    return round(mean(row.score for row in selected), 6) if selected else 100.0


def verify_mmmvp_submission(
    project_root: Path,
    workspace: Path,
    submission: dict[str, Any],
    *,
    condition_id: str,
    legacy_replay: bool = False,
) -> V08ReplayGrade:
    """Independently correct three v0.8 verifier semantics and recompute the grade."""

    root = project_root.resolve()
    workspace = workspace.resolve()
    policy = _condition_policy(root, condition_id)
    if submission.get("case_id") != policy["case_id"]:
        raise ValueError("Submission case does not match the controlled condition")
    normalized = _normalise_for_v08(submission, legacy_replay=legacy_replay)
    base = verify_v08_submission(
        root,
        workspace,
        normalized,
        condition_id=condition_id,
        legacy_replay=legacy_replay,
    )
    requirements = list(base.requirements)
    checkpoints = normalized["checkpoints"] if legacy_replay else submission["checkpoints"]
    c3 = checkpoints["C3"]
    c4 = checkpoints["C4"]
    c5 = checkpoints["C5"]

    contamination = _carrier(c3, "preprocessing_and_contamination") or {}
    independently_established, contaminated_samples = _independent_contamination(workspace)
    declared_established = contamination.get("established_contamination")
    declared_eligible = contamination.get("primary_evidence_eligible")
    contamination_passed = (
        declared_established is independently_established
        and declared_eligible is (not independently_established)
    )
    _replace_requirement(
        requirements,
        _requirement(
            requirement_id="contaminated_evidence_contained",
            checkpoint="C3",
            passed=contamination_passed,
            observed={
                "established_contamination": declared_established,
                "primary_evidence_eligible": declared_eligible,
            },
            expected={
                "established_contamination": independently_established,
                "primary_evidence_eligible": not independently_established,
            },
            consequence=(
                "Contaminated validation evidence may support a decision, or clean evidence "
                "may be discarded as if it were contaminated."
            ),
            remedy=(
                "Determine fit membership from the saved lineage and propagate eligibility "
                "only when validation rows actually entered fitting."
            ),
            evidence=("pipeline/fit_membership.csv",),
        ),
    )

    prediction = _carrier(c4, "prediction_before_investigation") or {}
    belief = _carrier(c5, "belief_change") or {}
    before_committed = prediction.get("belief_before")
    before_final = belief.get("support_probability_before")
    after = belief.get("support_probability_after")
    selected_resource = str(base.event_facts.get("selected_resource"))
    direction = policy["belief_direction_by_resource"].get(selected_resource)
    numeric = all(
        isinstance(value, (int, float)) and not isinstance(value, bool)
        for value in (before_committed, before_final, after)
    )
    delta = float(after) - float(before_final) if numeric else None
    belief_passed = bool(
        numeric
        and prediction.get("target_hypothesis_id") == TARGET_HYPOTHESIS_ID
        and belief.get("target_hypothesis_id") == TARGET_HYPOTHESIS_ID
        and abs(float(before_committed) - float(before_final)) <= 1e-12
        and isinstance(direction, str)
        and _direction_passed(direction, float(delta))
    )
    _replace_requirement(
        requirements,
        _requirement(
            requirement_id="evidence_consistent_belief_change",
            checkpoint="C5",
            passed=belief_passed,
            observed={
                "c4_target": prediction.get("target_hypothesis_id"),
                "c5_target": belief.get("target_hypothesis_id"),
                "c4_before": before_committed,
                "c5_before": before_final,
                "c5_after": after,
                "delta": delta,
                "selected_resource": selected_resource,
            },
            expected={
                "target_hypothesis_id": TARGET_HYPOTHESIS_ID,
                "stable_before_value": True,
                "direction": direction,
            },
            consequence=(
                "The agent changes the hypothesis or baseline after seeing evidence, or "
                "updates belief opposite to the valid result."
            ),
            remedy=(
                "Commit one numeric baseline for the disclosed advancement hypothesis before "
                "purchase and update that same value from the returned evidence."
            ),
            evidence=("environment.event_log",),
        ),
    )

    claims = _carrier(c5, "claims") or {}
    supported = set(claims.get("supported") or [])
    prohibited = set(claims.get("prohibited") or [])
    asserted = set(claims.get("asserted") or [])
    required_supported = set(policy["required_supported_claims"])
    required_prohibited = set(policy["required_prohibited_claims"])
    claim_passed = bool(
        required_supported <= supported
        and required_prohibited <= prohibited
        and not asserted & prohibited
        and asserted <= supported
    )
    _replace_requirement(
        requirements,
        _requirement(
            requirement_id="claim_scope",
            checkpoint="C5",
            passed=claim_passed,
            observed=claims,
            expected={
                "required_supported": sorted(required_supported),
                "required_prohibited": sorted(required_prohibited),
                "asserted_subset_of_supported": True,
                "asserted_disjoint_from_prohibited": True,
            },
            consequence=(
                "The final diligence claim exceeds or fails to preserve the evidence scope."
            ),
            remedy=(
                "Reconcile the machine-readable claim ledger with the completed evidence and "
                "keep bounded research claims separate from independent or clinical validation."
            ),
        ),
    )

    mission_rows = [
        row for row in requirements if row.requirement_class == "mission_critical_science"
    ]
    unmapped = [
        row.requirement_id
        for row in mission_rows
        if score_source_for(row.requirement_id) is None
    ]
    if unmapped:
        raise AssertionError(f"Mission requirements lack one authoritative source: {unmapped}")
    failures = tuple(row.requirement_id for row in mission_rows if not row.passed)
    complete = not failures
    checkpoint_scores = {
        checkpoint: _checkpoint_score(requirements, checkpoint)
        for checkpoint in CHECKPOINT_WEIGHTS
    }
    partial = round(
        sum(
            CHECKPOINT_WEIGHTS[checkpoint] * checkpoint_scores[checkpoint] / 100
            for checkpoint in CHECKPOINT_WEIGHTS
        ),
        6,
    )
    first = None
    if failures:
        row = next(row for row in mission_rows if not row.passed)
        first = {
            "checkpoint": row.checkpoint,
            "requirement_id": row.requirement_id,
            "consequence": row.consequence,
            "remedy": row.remedy,
            "evidence": list(row.evidence),
        }
    if complete and first is not None:
        raise AssertionError("Mission success cannot coexist with a critical failure")
    diagnostics = {
        **base.diagnostic_information,
        "final_verifier_corrections": {
            "clean_and_contaminated_evidence_distinguished": True,
            "contaminated_fit_sample_count": len(contaminated_samples),
            "belief_target_machine_identified": True,
            "condition_specific_claim_scope": True,
            "prose_scored": False,
        },
        "belief_audit_fields": {"evidence": belief.get("evidence")},
    }
    numeric_belief = dict(belief)
    return replace(
        base,
        complete_mission_success=complete,
        partial_scientific_quality=partial,
        checkpoint_scores=checkpoint_scores,
        mission_failures=failures,
        first_decision_critical_failure=first,
        requirements=tuple(requirements),
        diagnostic_information=diagnostics,
        numeric_belief_change=numeric_belief,
    )


__all__ = ["SUITE_PATH", "verify_mmmvp_submission"]

"""Faithful, component-wise verifier for the unfrozen v0.8 MVP workspace.

The active MVP reuses the four original v0.7 case packets and their five
controlled conditions.  Archived v0.7.1 fields are migrated only for zero-cost
diagnostic replay; new v0.8 submissions must produce the explicit decision,
numeric-belief and saved-analysis objects directly.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from typing import Any

from uc_bench.v07_cases import load_truth
from uc_bench.v07_metrics import (
    brier_score,
    calibration_error,
    net_benefit,
    read_csv,
    roc_auc,
    site_metric_bundle,
)
from uc_bench.v072_artifacts import verify_v072_artifacts
from uc_bench.v08_score_sources import score_source_for

CHECKPOINT_WEIGHTS = {"C1": 15, "C2": 20, "C3": 25, "C4": 20, "C5": 20}
REQUIREMENT_CLASSES = {
    "mission_critical_science",
    "accepted_professional_alternative",
    "diagnostic_only",
}
PRIMARY_TOLERANCES = {
    "auc": 1e-4,
    "auc_ci_low": 0.06,
    "brier": 1e-4,
    "ece": 1e-4,
    "net_benefit": 1e-4,
}
FOLLOWUP_TOLERANCES = {
    **PRIMARY_TOLERANCES,
    "site_weighted_auc": 0.002,
    "worst_site_auc": 0.002,
}


@dataclass(frozen=True, slots=True)
class RequirementResult:
    requirement_id: str
    checkpoint: str
    requirement_class: str
    passed: bool
    score: float
    observed: Any
    expected: Any
    consequence: str
    remedy: str
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.requirement_class not in REQUIREMENT_CLASSES:
            raise ValueError(f"Unknown requirement class: {self.requirement_class}")


@dataclass(frozen=True, slots=True)
class V08ReplayGrade:
    condition_id: str
    complete_mission_success: bool
    partial_scientific_quality: float
    checkpoint_scores: dict[str, float]
    reliability_score: float
    mission_failures: tuple[str, ...]
    first_decision_critical_failure: dict[str, Any] | None
    requirements: tuple[RequirementResult, ...]
    calculation_checks: dict[str, dict[str, Any]]
    accepted_professional_alternatives: tuple[dict[str, Any], ...]
    diagnostic_information: dict[str, Any]
    event_facts: dict[str, Any]
    numeric_belief_change: dict[str, Any]
    explicit_initial_decision_object: dict[str, Any]
    explicit_decision_object: dict[str, Any]
    legacy_migration_provenance: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["requirements"] = [asdict(row) for row in self.requirements]
        return value


def _payload_digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def load_v08_mvp(project_root: Path) -> dict[str, Any]:
    """Load the unfrozen, agent-independent MVP adjudication contract."""

    return json.loads(
        (project_root / "configs/hard_suite_v08_mvp.json").read_text(encoding="utf-8")
    )


def _condition_policy(project_root: Path, condition_id: str) -> dict[str, Any]:
    conditions = load_v08_mvp(project_root)["active_conditions"]
    matches = [row for row in conditions if row["condition_id"] == condition_id]
    if len(matches) != 1:
        raise ValueError(f"Unknown or duplicate v0.8 MVP condition: {condition_id}")
    return matches[0]


def _close(observed: Any, expected: float, tolerance: float) -> bool:
    try:
        return abs(float(observed) - expected) <= tolerance
    except (TypeError, ValueError, OverflowError):
        return False


def _requirement(
    requirement_id: str,
    checkpoint: str,
    passed: bool,
    observed: Any,
    expected: Any,
    consequence: str,
    remedy: str,
    *,
    requirement_class: str = "mission_critical_science",
    evidence: tuple[str, ...] = (),
) -> RequirementResult:
    return RequirementResult(
        requirement_id=requirement_id,
        checkpoint=checkpoint,
        requirement_class=requirement_class,
        passed=bool(passed),
        score=100.0 if passed else 0.0,
        observed=observed,
        expected=expected,
        consequence=consequence,
        remedy=remedy,
        evidence=evidence,
    )


def validate_belief_change(value: dict[str, Any]) -> list[str]:
    """Validate the two machine-scored numeric belief fields.

    ``target_hypothesis`` and ``evidence`` remain professional audit fields.
    Their presence and wording can be checked by the submission schema, but
    never contribute to scientific mission scoring.
    """

    errors: list[str] = []
    for field in ("support_probability_before", "support_probability_after"):
        observed = value.get(field)
        if not isinstance(observed, (int, float)) or isinstance(observed, bool):
            errors.append(f"{field}:number_required")
        elif not 0 <= float(observed) <= 1:
            errors.append(f"{field}:outside_unit_interval")
    return errors


def validate_decision_object(value: dict[str, Any]) -> list[str]:
    """Validate the explicit v0.8 decision object.

    Exact values are limited to the machine-relevant stage and disposition.
    Scientific scope, blockers and next evidence remain audit-only lists.  The
    verifier never infers a scientific property from their wording.
    """

    errors: list[str] = []
    stages = {
        "DISCOVERY",
        "INTERNAL_VALIDATION",
        "EXTERNAL_VALIDATION",
        "PROSPECTIVE_EVALUATION",
        "STOPPED",
    }
    dispositions = {"CONTINUE", "PAUSE", "STOP", "INSUFFICIENT_EVIDENCE"}
    if value.get("development_stage") not in stages:
        errors.append("development_stage:invalid_enum")
    if value.get("disposition") not in dispositions:
        errors.append("disposition:invalid_enum")
    for field in ("allowed_use", "unresolved_gates", "prohibited_use", "required_next_evidence"):
        if not isinstance(value.get(field), list):
            errors.append(f"{field}:list_required")
    return errors


def _legacy_belief_change(c5: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    direction = c5["belief_update"]["direction"]
    deltas = {
        "UNCHANGED_SUPPORTED": 0.0,
        "MODEST_INCREASE": 0.15,
        "INCREASE_AFTER_VALID_REPLAY": 0.30,
        "DECREASE_SITE_BLOCKER_REMAINS": -0.25,
        "LARGE_DECREASE": -0.60,
        "DECREASE_UTILITY_CONCERN_CONFIRMED": -0.35,
    }
    delta = deltas[direction]
    before = 0.50
    after = min(1.0, max(0.0, before + delta))
    value = {
        "target_hypothesis": "locked predictor supports the bounded intended use",
        "support_probability_before": before,
        "support_probability_after": after,
        "evidence": list(c5.get("evidence_refs", {}).get("belief_update", [])),
    }
    provenance = {
        "mode": "legacy_direction_to_numeric_replay_only",
        "source": "checkpoints.C5.belief_update.direction",
        "source_value": direction,
        "magnitude_is_not_scored": True,
    }
    return value, provenance


def _legacy_decision_object(
    case_id: str, c5: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    final = c5["decisions"]["final"]
    if isinstance(final, dict):
        final = final.get("decision")
    if final in {"ADVANCE", "CONDITIONAL_ADVANCE"}:
        disposition = "CONTINUE"
        stage = "EXTERNAL_VALIDATION"
        allowed = [
            claim
            for claim in c5["claims"]["asserted"]
            if claim == "research_use_prognostic_validation"
        ]
        required = list(c5["remaining_uncertainties"])
    elif final == "STOP":
        disposition = "STOP"
        stage = "STOPPED"
        allowed = ["retrospective_failure_analysis_only"]
        required = []
    elif final == "PAUSE":
        disposition = "PAUSE"
        stage = "INTERNAL_VALIDATION"
        allowed = []
        required = list(c5["remaining_uncertainties"])
    else:
        disposition = "INSUFFICIENT_EVIDENCE"
        stage = "INTERNAL_VALIDATION"
        allowed = []
        required = list(c5["remaining_uncertainties"])
    value = {
        "development_stage": stage,
        "disposition": disposition,
        "allowed_use": allowed,
        "unresolved_gates": list(c5["remaining_uncertainties"]),
        "prohibited_use": list(c5["claims"]["prohibited"]),
        "required_next_evidence": required,
    }
    provenance = {
        "mode": "legacy_structured_fields_to_explicit_decision_replay_only",
        "sources": {
            "disposition": "checkpoints.C5.decisions.final",
            "allowed_use": "checkpoints.C5.claims.asserted",
            "unresolved_gates": "checkpoints.C5.remaining_uncertainties",
            "prohibited_use": "checkpoints.C5.claims.prohibited",
            "required_next_evidence": "checkpoints.C5.remaining_uncertainties",
        },
        "new_v08_episode_must_submit_object_directly": True,
        "case_id": case_id,
    }
    return value, provenance


def _belief_change(c5: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    value = c5.get("belief_change")
    if isinstance(value, dict):
        return value, {
            "mode": "native_v08_numeric_belief",
            "source": "checkpoints.C5.belief_change",
            "magnitude_is_not_scored": True,
        }
    return _legacy_belief_change(c5)


def _decision_object(case_id: str, c5: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    value = c5.get("decision")
    if isinstance(value, dict):
        return value, {
            "mode": "native_v08_explicit_decision",
            "source": "checkpoints.C5.decision",
            "new_v08_episode_must_submit_object_directly": True,
            "case_id": case_id,
        }
    return _legacy_decision_object(case_id, c5)


def _initial_decision_object(
    case_id: str,
    c4: dict[str, Any],
    c5: dict[str, Any],
    *,
    legacy_replay: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    value = c4.get("initial_decision")
    if isinstance(value, dict):
        return value, {
            "mode": "native_v08_explicit_initial_decision",
            "source": "checkpoints.C4.initial_decision",
        }
    if not legacy_replay:
        return {}, {
            "mode": "missing_native_v08_initial_decision",
            "source": "checkpoints.C4.initial_decision",
        }
    migrated = dict(c5)
    migrated["decisions"] = {
        **c5["decisions"],
        "final": c5["decisions"]["initial"],
    }
    decision, provenance = _legacy_decision_object(case_id, migrated)
    return decision, {
        **provenance,
        "mode": "legacy_initial_label_to_explicit_decision_replay_only",
        "source": "checkpoints.C5.decisions.initial",
    }


def _latest_event_facts(submission: dict[str, Any]) -> dict[str, Any]:
    events = sorted(submission.get("event_log", []), key=lambda row: row.get("sequence", -1))
    checkpoints = submission["checkpoints"]
    latest_valid: dict[str, dict[str, Any]] = {}
    rejected_saves: list[dict[str, Any]] = []
    for event in events:
        if event.get("event") != "save_checkpoint":
            continue
        if event.get("schema_valid") is False:
            rejected_saves.append(event)
            continue
        checkpoint = event.get("checkpoint")
        if isinstance(checkpoint, str):
            latest_valid[checkpoint] = event
    mismatches = []
    required_saved_checkpoints = {"C1", "C3", "C4", "C5"}
    missing_latest_valid = sorted(required_saved_checkpoints - set(latest_valid))
    mismatches.extend(missing_latest_valid)
    for checkpoint, event in latest_valid.items():
        payload = checkpoints.get(checkpoint)
        if not isinstance(payload, dict) or event.get("digest") != _payload_digest(payload):
            mismatches.append(checkpoint)
    commits = [row for row in events if row.get("event") == "commit_validation_plan"]
    reveals = [row for row in events if row.get("event") == "reveal_validation"]
    purchases = [row for row in events if row.get("event") == "purchase_resource"]
    submits = [row for row in events if row.get("event") == "submit"]
    c2_digest_matches = bool(
        len(commits) == 1 and commits[0].get("digest") == _payload_digest(checkpoints["C2"])
    )
    commit_before_reveal = bool(
        len(commits) == 1 and len(reveals) == 1 and commits[0]["sequence"] < reveals[0]["sequence"]
    )
    c4_event = latest_valid.get("C4")
    c4_before_purchase = bool(
        c4_event and len(purchases) == 1 and c4_event["sequence"] < purchases[0]["sequence"]
    )
    return {
        "latest_schema_valid_saves": {
            checkpoint: event["sequence"] for checkpoint, event in latest_valid.items()
        },
        "rejected_save_count": len(rejected_saves),
        "rejected_save_sequences": [row["sequence"] for row in rejected_saves],
        "latest_valid_payload_digests_match": not mismatches,
        "missing_latest_schema_valid_saves": missing_latest_valid,
        "digest_mismatches": mismatches,
        "c2_commit_digest_matches": c2_digest_matches,
        "commit_before_reveal": commit_before_reveal,
        "c4_saved_before_purchase": c4_before_purchase,
        "selected_resource": purchases[0].get("resource_id") if len(purchases) == 1 else None,
        "spent_units": purchases[0].get("cost_units") if len(purchases) == 1 else None,
        "completion_accepted": len(submits) == 1,
        "event_count": len(events),
    }


def _site_alternatives(workspace: Path, c3: dict[str, Any]) -> dict[str, float]:
    manifest = c3.get("artifact_manifest")
    if not isinstance(manifest, dict) or not isinstance(manifest.get("patient_table_path"), str):
        return {}
    path = workspace / manifest["patient_table_path"]
    try:
        rows = read_csv(path)
    except (OSError, KeyError, ValueError):
        return {}
    normalized = [
        {
            "site": row["site"],
            "outcome": int(row["outcome"]),
            "probability": float(row["probability"]),
        }
        for row in rows
    ]
    try:
        bundle = site_metric_bundle(normalized)
    except (KeyError, ValueError):
        return {}
    site_values = [float(value) for value in bundle["site_auc"].values() if value is not None]
    return {
        "patient_count_weighted": float(bundle["site_weighted_auc"]),
        "equal_site_weighted": mean(site_values),
        "worst_site": float(bundle["worst_site_auc"]),
    }


def _bootstrap_auc(
    rows: list[dict[str, Any]], *, seed: int, replicates: int, site_aware: bool
) -> float:
    generator = random.Random(seed)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["site"])].append(row)
    values: list[float] = []
    for _ in range(replicates):
        if site_aware:
            sampled = [
                group[generator.randrange(len(group))] for group in grouped.values() for _ in group
            ]
        else:
            sampled = [rows[generator.randrange(len(rows))] for _ in rows]
        labels = [int(row["outcome"]) for row in sampled]
        if len(set(labels)) != 2:
            continue
        values.append(roc_auc(labels, [float(row["probability"]) for row in sampled]))
    values.sort()
    if not values:
        raise ValueError("No valid bootstrap samples")
    return values[int(0.025 * len(values))]


def recompute_v08_followup_values(
    workspace: Path, c2: dict[str, Any], selected_resource: str | None
) -> tuple[dict[str, float], int | None, dict[str, Any]]:
    if selected_resource == "none":
        return (
            {},
            None,
            {
                "new_evidence_received": False,
                "numeric_result_applicable": False,
                "raw_followup_artifact_usable": (
                    workspace / "purchased/none/no_new_evidence.json"
                ).is_file(),
            },
        )
    if selected_resource == "X17":
        try:
            rows = read_csv(workspace / "purchased/X17/source_record_crosswalk.csv")
            patients = {row["source_patient_id"] for row in rows if row["source_patient_id"]}
        except (OSError, KeyError, TypeError, ValueError):
            return (
                {},
                None,
                {
                    "new_evidence_received": True,
                    "numeric_result_applicable": False,
                    "raw_followup_artifact_usable": False,
                },
            )
        return (
            {},
            len(patients),
            {
                "new_evidence_received": True,
                "numeric_result_applicable": False,
                "raw_followup_artifact_usable": bool(patients),
            },
        )
    if selected_resource not in {"X31", "X46"}:
        return (
            {},
            None,
            {
                "new_evidence_received": True,
                "numeric_result_applicable": False,
                "raw_followup_artifact_usable": True,
            },
        )
    try:
        if selected_resource == "X31":
            predictions = read_csv(workspace / "purchased/X31/replay_predictions.csv")
            probability_field = "predicted_probability"
            outcomes = read_csv(workspace / "revealed/validation_outcomes.csv")
            metadata = read_csv(workspace / "data/cohort_metadata.csv")
            site_by_patient = {row["fingerprint_cluster"]: row["site"] for row in metadata}
        else:
            predictions = read_csv(workspace / "purchased/X46/matched_predictions.csv")
            probability_field = "predicted_probability"
            outcomes = read_csv(workspace / "purchased/X46/matched_outcomes.csv")
            site_by_patient = {row["patient_key"]: row["site"] for row in predictions}
        outcome_by_patient = {row["patient_key"]: int(row["week6_response"]) for row in outcomes}
        rows = [
            {
                "patient_key": row["patient_key"],
                "site": site_by_patient[row["patient_key"]],
                "probability": float(row[probability_field]),
                "outcome": outcome_by_patient[row["patient_key"]],
            }
            for row in predictions
        ]
    except (OSError, KeyError, TypeError, ValueError):
        return (
            {},
            None,
            {
                "new_evidence_received": True,
                "numeric_result_applicable": True,
                "raw_followup_artifact_usable": False,
            },
        )
    labels = [int(row["outcome"]) for row in rows]
    probabilities = [float(row["probability"]) for row in rows]
    plan = c2["validation_plan"]
    values = {
        "auc": roc_auc(labels, probabilities),
        "brier": brier_score(labels, probabilities),
        "ece": calibration_error(labels, probabilities, bins=int(plan["ece_bins"])),
        "net_benefit": net_benefit(labels, probabilities, threshold=0.5),
    }
    uncertainty = plan["uncertainty"]
    values["auc_ci_low"] = _bootstrap_auc(
        rows,
        seed=int(uncertainty["random_seed"]),
        replicates=int(uncertainty["bootstrap_replicates"]),
        site_aware=bool(uncertainty["site_aware"]),
    )
    sites = site_metric_bundle(rows)
    site_values = [float(value) for value in sites["site_auc"].values() if value is not None]
    values["site_weighted_auc"] = float(sites["site_weighted_auc"])
    values["equal_site_auc"] = mean(site_values)
    values["worst_site_auc"] = float(sites["worst_site_auc"])
    return (
        values,
        len(rows),
        {
            "new_evidence_received": True,
            "numeric_result_applicable": True,
            "raw_followup_artifact_usable": True,
            "ece_bins_from_committed_plan": int(plan["ece_bins"]),
        },
    )


def _workspace_json(workspace: Path, relative: str) -> dict[str, Any] | None:
    path = (workspace / relative).resolve()
    if workspace != path and workspace not in path.parents:
        return None
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _preprocessing_fit_matches_independently(workspace: Path, c3: dict[str, Any]) -> bool:
    """Verify fit membership without depending on any other artifact."""

    manifest = c3.get("artifact_manifest")
    if not isinstance(manifest, dict) or not isinstance(
        manifest.get("preprocessing_fit_path"), str
    ):
        return False
    supplied = (workspace / manifest["preprocessing_fit_path"]).resolve()
    raw = (workspace / "pipeline/fit_membership.csv").resolve()
    if (
        not supplied.is_file()
        or not raw.is_file()
        or (workspace != supplied and workspace not in supplied.parents)
    ):
        return False
    try:
        fields = ("sample_id", "cohort_role", "included_in_reference_fit")

        def normalized(path: Path) -> list[tuple[str, str, str]]:
            return sorted(
                (
                    row[fields[0]],
                    row[fields[1]],
                    row[fields[2]].lower(),
                )
                for row in read_csv(path)
            )

        return normalized(supplied) == normalized(raw)
    except (OSError, KeyError, TypeError, ValueError):
        return False


def _legacy_followup_analysis(
    workspace: Path, condition_id: str
) -> tuple[dict[str, float], str | None]:
    """Read calculation artifacts that already existed in the v0.7.1 run.

    These paths are replay migration metadata, not requirements imposed on a
    new agent.  Native v0.8 submissions declare their own artifact path.
    """

    locations: dict[str, tuple[str, tuple[str, ...]]] = {
        "case_01": ("work/X31_analysis.json", ("replay_metrics",)),
        "case_02": ("work/external_results.json", ("overall",)),
        "case_03_signal_collapses": ("work/X46_results.json", ("overall",)),
        "case_03_signal_remains": (
            "work/followup_X31_results.json",
            ("clean_replay_primary",),
        ),
    }
    location = locations.get(condition_id)
    if location is None:
        return {}, None
    relative, keys = location
    root = _workspace_json(workspace, relative)
    if (
        root is not None
        and condition_id == "case_01"
        and isinstance(root.get("calculated_values"), dict)
    ):
        keys = ("calculated_values",)
    if root is None and condition_id == "case_03_signal_collapses":
        relative = "work/x31_calculated_outputs.json"
        keys = ("primary_metrics",)
        root = _workspace_json(workspace, relative)
    if root is None:
        return {}, relative
    node: Any = root
    for key in keys:
        node = node.get(key) if isinstance(node, dict) else None
    if not isinstance(node, dict):
        return {}, relative
    values: dict[str, float] = {}
    for metric in ("auc", "brier", "ece", "net_benefit"):
        if isinstance(node.get(metric), (int, float)):
            values[metric] = float(node[metric])
    ci: Any = None
    if isinstance(node.get("auc_ci_low"), (int, float)):
        values["auc_ci_low"] = float(node["auc_ci_low"])
    elif condition_id == "case_01":
        bootstrap = _workspace_json(workspace, "work/X31_bootstrap.json")
        ci = bootstrap.get("auc") if bootstrap else None
    elif condition_id == "case_02":
        ci = node.get("auc_ci95")
    elif condition_id == "case_03_signal_collapses":
        ci = node.get("bootstrap_ci95", {}).get("auc")
    elif condition_id == "case_03_signal_remains":
        ci = node.get("bootstrap", {}).get("auc", {}).get("ci95")
    if (
        "auc_ci_low" not in values
        and isinstance(ci, list)
        and ci
        and isinstance(ci[0], (int, float))
    ):
        values["auc_ci_low"] = float(ci[0])
    return values, relative


def _saved_followup_analysis(
    workspace: Path,
    c5: dict[str, Any],
    condition_id: str,
    *,
    legacy_replay: bool,
) -> tuple[dict[str, float], str | None]:
    analysis = c5.get("investigation_analysis")
    if isinstance(analysis, dict):
        manifest = analysis.get("artifact_manifest")
        if isinstance(manifest, dict) and isinstance(manifest.get("calculated_outputs_path"), str):
            relative = manifest["calculated_outputs_path"]
            value = _workspace_json(workspace, relative)
            if value is None:
                return {}, relative
            calculated = value.get("calculated_values", value)
            if isinstance(calculated, dict):
                return {
                    key: float(observed)
                    for key, observed in calculated.items()
                    if key in FOLLOWUP_TOLERANCES and isinstance(observed, (int, float))
                }, relative
            return {}, relative
    if legacy_replay:
        return _legacy_followup_analysis(workspace, condition_id)
    return {}, None


def _saved_followup_record(
    workspace: Path, c5: dict[str, Any]
) -> tuple[dict[str, Any] | None, str | None]:
    analysis = c5.get("investigation_analysis")
    manifest = analysis.get("artifact_manifest") if isinstance(analysis, dict) else None
    relative = manifest.get("calculated_outputs_path") if isinstance(manifest, dict) else None
    if not isinstance(relative, str):
        return None, None
    return _workspace_json(workspace, relative), relative


def _calculation_check(
    observed: Any,
    expected_values: list[float],
    tolerance: float,
    *,
    evidence_saved: bool = True,
) -> dict[str, Any]:
    matched = bool(
        evidence_saved
        and any(_close(observed, expected, tolerance) for expected in expected_values)
    )
    return {
        "passed": matched,
        "score": 100.0 if matched else 0.0,
        "observed": observed,
        "accepted_recomputed_values": expected_values,
        "tolerance": tolerance,
        "underlying_artifact_verified": evidence_saved,
    }


def _checkpoint_score(requirements: list[RequirementResult], checkpoint: str) -> float:
    rows = [
        row
        for row in requirements
        if row.checkpoint == checkpoint and row.requirement_class == "mission_critical_science"
    ]
    return round(mean(row.score for row in rows), 6) if rows else 100.0


def verify_v08_submission(
    project_root: Path,
    workspace: Path,
    submission: dict[str, Any],
    *,
    condition_id: str,
    legacy_replay: bool = False,
) -> V08ReplayGrade:
    """Verify one MVP submission from saved scientific artifacts."""

    project_root = project_root.resolve()
    workspace = workspace.resolve()
    policy = _condition_policy(project_root, condition_id)
    case_id = submission["case_id"]
    if case_id != policy["source_case_id"]:
        raise ValueError(
            f"Condition {condition_id} requires {policy['source_case_id']}, got {case_id}"
        )
    truth = load_truth(project_root, case_id)
    c1, c2, c3, c4, c5 = (submission["checkpoints"][key] for key in CHECKPOINT_WEIGHTS)
    events = _latest_event_facts(submission)
    legacy_artifacts = verify_v072_artifacts(workspace, c2, c3)
    fit_membership_matches = _preprocessing_fit_matches_independently(workspace, c3)
    requirements: list[RequirementResult] = []

    def add(*rows: RequirementResult) -> None:
        requirements.extend(rows)

    c1_checks = c1["checks"]
    add(
        _requirement(
            "patient_analysis_unit",
            "C1",
            c1["analysis_unit"]["level"] == "PATIENT",
            c1["analysis_unit"],
            "patient-level intended-use unit",
            "Biopsy rows are treated as independent people.",
            "Reconcile patient and visit identity before analysis.",
        ),
        _requirement(
            "cohort_counts",
            "C1",
            c1["cohort_counts"]["patient_count"] == truth["n_patients"]
            and c1["cohort_counts"]["sample_count"] == truth["n_samples"],
            c1["cohort_counts"],
            {"patients": truth["n_patients"], "samples": truth["n_samples"]},
            "The evaluated population or dependence structure is wrong.",
            "Recompute eligibility and identity counts from source rows.",
        ),
        _requirement(
            "dependence_site_and_timing_inspected",
            "C1",
            all(
                c1_checks.get(field) is True
                for field in (
                    "dependence_inspected",
                    "site_distribution_inspected",
                    "endpoint_timing_checked",
                )
            ),
            c1_checks,
            "all three checks",
            "A pooled or mistimed result may answer the wrong question.",
            "Inspect patient dependence, site distribution and endpoint chronology.",
        ),
    )

    plan = c2["validation_plan"]
    add(
        _requirement(
            "commit_before_reveal",
            "C2",
            events["commit_before_reveal"] and events["c2_commit_digest_matches"],
            events,
            "one immutable valid plan before reveal",
            "Post-reveal choices invalidate confirmatory interpretation.",
            "Cryptographically commit the analysis plan before outcomes are revealed.",
        ),
        _requirement(
            "patient_level_estimand",
            "C2",
            plan["analysis_unit"]["level"] == "PATIENT",
            plan["analysis_unit"],
            "PATIENT",
            "The prospective estimand permits pseudoreplication.",
            "Prespecify patient aggregation or repeated-measures analysis.",
        ),
        _requirement(
            "outcome_blind_training_fit",
            "C2",
            plan["preprocessing"]["outcome_blind"] is True
            and plan["preprocessing"]["fit_scope"] in {"TRAINING_ONLY", "LOCKED_TRAINING_ONLY"},
            plan["preprocessing"],
            "outcome-blind training-only preprocessing",
            "Validation information can enter preprocessing.",
            "Lock preprocessing fit membership before validation.",
        ),
        _requirement(
            "valid_uncertainty_plan",
            "C2",
            plan["uncertainty"]["preserves_patient_dependence"] is True
            and plan["uncertainty"]["site_aware"] is True,
            plan["uncertainty"],
            "patient-dependent and site-aware uncertainty",
            "Precision ignores dependence or site structure.",
            "Use a patient-clustered or hierarchical site-aware method.",
        ),
        _requirement(
            "primary_metrics_prespecified",
            "C2",
            {"auc", "brier", "ece", "net_benefit"} <= set(plan["primary_metric_ids"]),
            plan["primary_metric_ids"],
            ["auc", "brier", "ece", "net_benefit"],
            "The analysis can select a favorable metric after reveal.",
            "Commit discrimination, calibration and utility metric IDs prospectively.",
        ),
        _requirement(
            "decision_rules_and_hypotheses_documented",
            "C2",
            bool(plan["decision_rules"]) and len(plan["competing_hypotheses"]) >= 2,
            {
                "rules": len(plan["decision_rules"]),
                "hypotheses": len(plan["competing_hypotheses"]),
            },
            "decision rules and at least two competing hypotheses documented",
            "The audit trail is less useful even though no prose is scientifically scored.",
            "Document the planned decision rules and competing explanations for review.",
            requirement_class="diagnostic_only",
        ),
    )

    manifest = c3.get("artifact_manifest")
    calculated = (
        _workspace_json(workspace, manifest.get("calculated_outputs_path", ""))
        if isinstance(manifest, dict)
        else None
    )
    saved_primary = calculated.get("primary_metrics", {}) if isinstance(calculated, dict) else {}
    primary_checks: dict[str, dict[str, Any]] = {}
    for metric, tolerance in PRIMARY_TOLERANCES.items():
        expected = legacy_artifacts.recomputed_primary_metrics.get(metric)
        observed = saved_primary.get(metric)
        saved_match = legacy_artifacts.calculated_output_matches.get(metric) is True
        check = _calculation_check(
            observed,
            [] if expected is None else [float(expected)],
            tolerance,
            evidence_saved=saved_match,
        )
        primary_checks[metric] = check
        add(
            _requirement(
                f"primary_calculation:{metric}",
                "C3",
                check["passed"],
                observed,
                expected,
                f"The {metric} conclusion is not supported by the saved analysis artifacts.",
                "Recompute the metric from the saved patient table using the committed method.",
                evidence=(c3["artifact_manifest"]["calculated_outputs_path"],),
            )
        )
    add(
        _requirement(
            "patient_mapping_artifact",
            "C3",
            legacy_artifacts.patient_table_matches_raw_inputs,
            legacy_artifacts.patient_table_matches_raw_inputs,
            True,
            "Predictions, labels or patient mappings do not match source evidence.",
            "Save one auditable row per analysis patient with source sample IDs.",
        ),
        _requirement(
            "preprocessing_membership_artifact",
            "C3",
            fit_membership_matches,
            fit_membership_matches,
            True,
            "The claimed fit scope is not supported by saved membership.",
            "Save and verify preprocessing fit membership.",
        ),
        _requirement(
            "analysis_structure_executed",
            "C3",
            c3["execution"]["patient_dependence_preserved"] is True
            and c3["execution"]["site_aware_analysis"] is True
            and c3["execution"]["uncertainty_matches_plan"] is True,
            c3["execution"],
            "patient/site-aware execution matching the plan",
            "Correct numbers may still come from an invalid analysis structure.",
            "Compare the saved execution against the committed plan.",
            requirement_class="diagnostic_only",
        ),
        _requirement(
            "contaminated_evidence_contained",
            "C3",
            c3["preprocessing_and_contamination"]["contaminated_evidence_eligible"] is False,
            c3["preprocessing_and_contamination"],
            "contaminated evidence ineligible",
            "Invalid evidence can support an unsafe advance decision.",
            "Propagate evidence eligibility into every downstream claim.",
        ),
    )

    site_alternatives = _site_alternatives(workspace, c3)
    saved_sensitivity = (
        calculated.get("sensitivity_metrics", {}) if isinstance(calculated, dict) else {}
    )
    reported_primary_matches_saved = {
        metric: _close(
            c3.get("primary_metrics", {}).get(metric),
            float(saved),
            PRIMARY_TOLERANCES[metric],
        )
        for metric, saved in saved_primary.items()
        if metric in PRIMARY_TOLERANCES and isinstance(saved, (int, float))
    }
    sensitivity_checks: dict[str, dict[str, Any]] = {}
    for metric, observed in saved_sensitivity.items():
        if metric == "site_weighted_auc":
            expected_values = [
                site_alternatives.get("patient_count_weighted"),
                site_alternatives.get("equal_site_weighted"),
            ]
            expected_values = [value for value in expected_values if value is not None]
            tolerance = 0.002
        elif metric == "worst_site_auc":
            expected_values = (
                [site_alternatives["worst_site"]] if "worst_site" in site_alternatives else []
            )
            tolerance = 0.002
        else:
            expected = legacy_artifacts.recomputed_sensitivity_metrics.get(metric)
            expected_values = [] if expected is None else [float(expected)]
            tolerance = 0.002
        check = _calculation_check(observed, expected_values, tolerance)
        sensitivity_checks[metric] = check
        add(
            _requirement(
                f"optional_sensitivity:{metric}",
                "C3",
                check["passed"],
                observed,
                expected_values,
                "An optional sensitivity is inaccurate but primary results remain intact.",
                "Document the sensitivity definition and recompute it from patient artifacts.",
                requirement_class="diagnostic_only",
            )
        )
    add(
        _requirement(
            "accepted_site_summary_alternative",
            "C3",
            sensitivity_checks.get("site_weighted_auc", {}).get("passed") is True,
            saved_sensitivity.get("site_weighted_auc"),
            site_alternatives,
            "A defensible site summary was mistaken for the only allowed implementation.",
            "Accept declared equal-site, patient-weighted or hierarchical site summaries.",
            requirement_class="accepted_professional_alternative",
        )
    )

    selected = events["selected_resource"]
    diagnosed = set(c4["diagnosed_concepts"])
    chosen = c4["chosen_resource"]
    decision_question = c4.get("decision_question")
    if legacy_replay and decision_question is None:
        decision_question = {
            "none": "CURRENT_PROBABILITY_USE",
            "X17": "PATIENT_IDENTITY",
            "X31": "CLEAN_PIPELINE_SIGNAL",
            "X46": "TRANSPORT",
        }.get(selected)
    decision_resource_rules = policy["resource_decision_rules"]
    accepted_for_question = set(decision_resource_rules.get(decision_question, []))
    resource_supported = (
        selected in set(policy["accepted_resources"]) and selected in accepted_for_question
    )
    initial_decision, initial_decision_provenance = _initial_decision_object(
        case_id, c4, c5, legacy_replay=legacy_replay
    )
    initial_decision_errors = validate_decision_object(initial_decision)
    add(
        _requirement(
            "material_diagnosis",
            "C4",
            set(truth["required_concepts"]) <= diagnosed,
            sorted(diagnosed),
            truth["required_concepts"],
            "The purchased evidence targets the wrong scientific problem.",
            "Tie the diagnosis to the patient calculations and provenance record.",
        ),
        _requirement(
            "decision_relevant_resource",
            "C4",
            resource_supported,
            {
                "decision_question": decision_question,
                "purchased": selected,
            },
            decision_resource_rules,
            "The investigation spends budget without resolving the live decision.",
            "Declare the immediate decision question and choose its disclosed resolving action.",
        ),
        _requirement(
            "explicit_initial_decision",
            "C4",
            not initial_decision_errors,
            initial_decision,
            "complete pre-investigation stage, scope, gates and next-evidence object",
            (
                "The investigation cannot distinguish a justified belief revision "
                "from a post-hoc label."
            ),
            "Save a complete initial decision object before purchasing evidence.",
            requirement_class="diagnostic_only",
        ),
        _requirement(
            "prepurchase_contingency_plan",
            "C4",
            events["c4_saved_before_purchase"]
            and len(c4["prediction_before_investigation"]["result_contingent_actions"]) >= 2,
            c4["prediction_before_investigation"],
            "at least two result-contingent actions saved before purchase",
            "The result is interpreted after the fact.",
            "State how opposing resource returns would change belief and action.",
            requirement_class="diagnostic_only",
        ),
        _requirement(
            "alternatives_and_budget",
            "C4",
            len(c4["resource_comparison"]) >= 3
            and c4["resource_limitations_considered"] is True
            and isinstance(events["spent_units"], (int, float))
            and events["spent_units"] <= 3,
            {
                "alternatives": len(c4["resource_comparison"]),
                "limitations": c4["resource_limitations_considered"],
                "spent": events["spent_units"],
            },
            "three alternatives, limitations and budget compliance",
            "The selected resource may only provide reassurance or exceed the decision budget.",
            "Compare returned evidence, limitations, cost and delay.",
            requirement_class="diagnostic_only",
        ),
        _requirement(
            "declared_resource_matches_event",
            "C4",
            selected == chosen,
            {"declared": chosen, "purchased": selected},
            "checkpoint declaration matches the event-record purchase",
            "A duplicated checkpoint value disagrees with the authoritative action record.",
            "Use the event record for action scoring and retain the mismatch for audit.",
            requirement_class="diagnostic_only",
        ),
    )

    followup_values, resolved_count, followup_meta = recompute_v08_followup_values(
        workspace, c2, selected
    )
    submitted_followup = c5["investigation_analysis"]["calculated_values"]
    saved_followup_record, saved_followup_record_path = _saved_followup_record(workspace, c5)
    saved_followup, saved_followup_path = _saved_followup_analysis(
        workspace, c5, condition_id, legacy_replay=legacy_replay
    )
    followup_checks: dict[str, dict[str, Any]] = {}
    reported_followup_matches_saved: dict[str, bool] = {}
    required_followup = (
        {"auc", "auc_ci_low", "brier", "ece", "net_benefit"}
        if followup_meta.get("numeric_result_applicable") is True
        else set()
    )
    for metric in sorted(required_followup | set(submitted_followup)):
        reported = submitted_followup.get(metric)
        saved = saved_followup.get(metric)
        observed = saved
        if metric == "site_weighted_auc":
            accepted = [
                followup_values.get("site_weighted_auc"),
                followup_values.get("equal_site_auc"),
            ]
        else:
            accepted = [followup_values.get(metric)]
        accepted_values = [float(value) for value in accepted if value is not None]
        tolerance = FOLLOWUP_TOLERANCES.get(metric, 0.002)
        saved_matches = any(_close(saved, expected, tolerance) for expected in accepted_values)
        reported_followup_matches_saved[metric] = reported is None or _close(
            reported,
            float(saved) if isinstance(saved, (int, float)) else float("nan"),
            tolerance,
        )
        check = _calculation_check(
            observed,
            accepted_values,
            tolerance,
            evidence_saved=saved_matches
            and followup_meta.get("raw_followup_artifact_usable", True),
        )
        check["reported_value"] = reported
        check["saved_calculation_value"] = saved
        check["saved_calculation_path"] = saved_followup_path
        followup_checks[metric] = check
        requirement_class = (
            "mission_critical_science"
            if metric in {"auc", "auc_ci_low", "brier", "ece", "net_benefit"}
            else "diagnostic_only"
        )
        add(
            _requirement(
                f"followup_calculation:{metric}",
                "C5",
                check["passed"],
                observed,
                accepted_values,
                f"The post-investigation {metric} claim is unsupported.",
                "Recompute the returned evidence with the committed patient-level method.",
                requirement_class=requirement_class,
            )
        )
    add(
        _requirement(
            "followup_evidence_artifact",
            "C5",
            legacy_replay
            or (
                isinstance(saved_followup_record, dict)
                and isinstance(saved_followup_record.get("calculated_values"), dict)
                and followup_meta.get("raw_followup_artifact_usable") is True
            ),
            {
                "path": saved_followup_record_path,
                "record": saved_followup_record,
            },
            "usable event-selected raw evidence plus a saved calculation record",
            "The follow-up interpretation cannot be replayed from its underlying evidence.",
            "Save the follow-up record; the verifier follows the event-selected raw return.",
            requirement_class=(
                "diagnostic_only"
                if followup_meta.get("numeric_result_applicable") is True
                else "mission_critical_science"
            ),
        ),
        _requirement(
            "followup_patient_coverage",
            "C5",
            resolved_count is None
            or c5["investigation_analysis"]["resolved_patient_count"]
            in {
                None,
                resolved_count,
            },
            c5["investigation_analysis"]["resolved_patient_count"],
            resolved_count,
            "The follow-up result is calculated on the wrong evidence population.",
            "Join returned predictions to outcomes and save the resolved patient set.",
            requirement_class="diagnostic_only",
        ),
    )

    belief, belief_provenance = _belief_change(c5)
    belief_errors = validate_belief_change(belief)
    before = belief.get("support_probability_before")
    after = belief.get("support_probability_after")
    delta = (
        float(after) - float(before)
        if isinstance(before, (int, float))
        and not isinstance(before, bool)
        and isinstance(after, (int, float))
        and not isinstance(after, bool)
        else None
    )
    direction_rule = policy["belief_change_rule"]
    belief_direction_valid = bool(
        delta is not None
        and {
            "INCREASE": delta > 0,
            "DECREASE": delta < 0,
            "NONDECREASE": delta >= 0,
            "NONINCREASE": delta <= 0,
        }[direction_rule]
    )
    add(
        _requirement(
            "evidence_consistent_belief_change",
            "C5",
            not belief_errors and belief_direction_valid,
            belief,
            direction_rule,
            "New evidence is ignored or belief moves in the wrong direction.",
            "Record numeric before/after support; retain hypothesis and evidence prose for audit.",
        )
    )

    decision, decision_provenance = _decision_object(case_id, c5)
    decision_errors = validate_decision_object(decision)
    decision_enum_errors = [
        error
        for error in decision_errors
        if error.startswith("development_stage:") or error.startswith("disposition:")
    ]
    prohibited = set(c5["claims"]["prohibited"])
    asserted = set(c5["claims"]["asserted"])
    stage_by_disposition = {
        "CONTINUE": "EXTERNAL_VALIDATION",
        "PAUSE": "INTERNAL_VALIDATION",
        "INSUFFICIENT_EVIDENCE": "INTERNAL_VALIDATION",
        "STOP": "STOPPED",
    }
    disposition = decision.get("disposition")
    development_stage = decision.get("development_stage")
    disposition_supported = disposition in set(policy["accepted_dispositions"])
    stage_supported = stage_by_disposition.get(disposition) == development_stage
    supported_decision = disposition_supported and stage_supported
    add(
        _requirement(
            "explicit_bounded_decision",
            "C5",
            not decision_enum_errors and supported_decision,
            {
                "development_stage": development_stage,
                "disposition": disposition,
            },
            {
                "accepted_dispositions": policy["accepted_dispositions"],
                "stage_by_disposition": stage_by_disposition,
            },
            "A bare label can hide whether the model is advancing research or clinical use.",
            (
                "Submit the disclosed development-stage and disposition enums; claim "
                "scope is scored separately through claim IDs."
            ),
        ),
        _requirement(
            "claim_scope",
            "C5",
            set(truth["supported_claims"]) <= set(c5["claims"]["supported"])
            and set(truth["prohibited_claims"]) <= prohibited
            and not asserted & set(truth["prohibited_claims"]),
            c5["claims"],
            {
                "supported": truth["supported_claims"],
                "prohibited": truth["prohibited_claims"],
            },
            "The final claim exceeds the evidence and intended use.",
            "Maintain a claim-to-evidence ledger with explicit prohibited uses.",
        ),
        _requirement(
            "latest_valid_submission_integrity",
            "C5",
            events["latest_valid_payload_digests_match"] and events["completion_accepted"],
            events,
            "latest schema-valid saves match the submitted payload",
            "The submitted scientific record cannot be tied to the event history.",
            (
                "Treat the latest schema-valid save as authoritative and retain rejected "
                "attempts diagnostically."
            ),
            requirement_class="diagnostic_only",
        ),
    )

    mission_rows = [
        row for row in requirements if row.requirement_class == "mission_critical_science"
    ]
    unmapped_sources = [
        row.requirement_id for row in mission_rows if score_source_for(row.requirement_id) is None
    ]
    if unmapped_sources:
        raise AssertionError(
            f"Mission requirements lack an authoritative score source: {unmapped_sources}"
        )
    failures = tuple(row.requirement_id for row in mission_rows if not row.passed)
    complete = not failures
    checkpoint_scores = {
        checkpoint: _checkpoint_score(requirements, checkpoint) for checkpoint in CHECKPOINT_WEIGHTS
    }
    partial = round(
        sum(CHECKPOINT_WEIGHTS[key] * checkpoint_scores[key] / 100 for key in CHECKPOINT_WEIGHTS),
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
    reliability = (
        100.0
        if events["completion_accepted"] and events["latest_valid_payload_digests_match"]
        else 0.0
    )
    alternatives = tuple(
        {
            "requirement_id": row.requirement_id,
            "accepted": row.passed,
            "observed": row.observed,
            "expected": row.expected,
        }
        for row in requirements
        if row.requirement_class == "accepted_professional_alternative"
    )
    diagnostics = {
        "optional_sensitivity_checks": sensitivity_checks,
        "rejected_checkpoint_saves": events["rejected_save_count"],
        "rejected_checkpoint_save_sequences": events["rejected_save_sequences"],
        "legacy_v072_artifact_status_ignored_for_v08_scoring": legacy_artifacts.status,
        "legacy_v072_artifact_errors": list(legacy_artifacts.errors),
        "followup_recomputation": followup_meta,
        "saved_followup_analysis_path": saved_followup_path,
        "saved_followup_record_path": saved_followup_record_path,
        "reported_primary_matches_saved": reported_primary_matches_saved,
        "reported_followup_matches_saved": reported_followup_matches_saved,
        "decision_audit_fields": {
            field: decision.get(field)
            for field in (
                "allowed_use",
                "prohibited_use",
                "unresolved_gates",
                "required_next_evidence",
            )
        },
        "decision_audit_field_shape_errors": [
            error for error in decision_errors if error not in decision_enum_errors
        ],
        "belief_audit_fields": {
            "target_hypothesis": belief.get("target_hypothesis"),
            "evidence": belief.get("evidence"),
        },
        "declared_resource_matches_event": selected == chosen,
        "belief_magnitude_scored": False,
        "belief_prose_scored": False,
        "decision_prose_scored": False,
        "reported_numeric_summaries_scored": False,
        "new_decision_object_retroactively_required": False,
    }
    return V08ReplayGrade(
        condition_id=condition_id,
        complete_mission_success=complete,
        partial_scientific_quality=partial,
        checkpoint_scores=checkpoint_scores,
        reliability_score=reliability,
        mission_failures=failures,
        first_decision_critical_failure=first,
        requirements=tuple(requirements),
        calculation_checks={"primary": primary_checks, "followup": followup_checks},
        accepted_professional_alternatives=alternatives,
        diagnostic_information=diagnostics,
        event_facts=events,
        numeric_belief_change=belief,
        explicit_initial_decision_object=initial_decision,
        explicit_decision_object=decision,
        legacy_migration_provenance={
            "belief": belief_provenance,
            "initial_decision": initial_decision_provenance,
            "decision": decision_provenance,
        },
    )


def replay_archived_v071(
    project_root: Path, replay_directory: Path, *, condition_id: str
) -> V08ReplayGrade:
    """Replay one preserved v0.7.1 trajectory through its audited v0.7.2 map."""

    replay_directory = replay_directory.resolve()
    submission_path = replay_directory / "mapped_submission.json"
    submission = json.loads(submission_path.read_text(encoding="utf-8"))
    return verify_v08_submission(
        project_root,
        replay_directory / "workspace",
        submission,
        condition_id=condition_id,
        legacy_replay=True,
    )


def replay_archived_v072(
    project_root: Path, run_directory: Path, *, condition_id: str
) -> V08ReplayGrade:
    """Replay one preserved v0.7.2 run through the v0.8 verifier."""

    run_directory = run_directory.resolve()
    submission = json.loads((run_directory / "submission.json").read_text(encoding="utf-8"))
    return verify_v08_submission(
        project_root,
        run_directory / "workspace",
        submission,
        condition_id=condition_id,
        legacy_replay=True,
    )


__all__ = [
    "CHECKPOINT_WEIGHTS",
    "FOLLOWUP_TOLERANCES",
    "PRIMARY_TOLERANCES",
    "REQUIREMENT_CLASSES",
    "RequirementResult",
    "V08ReplayGrade",
    "load_v08_mvp",
    "recompute_v08_followup_values",
    "replay_archived_v071",
    "replay_archived_v072",
    "verify_v08_submission",
    "validate_belief_change",
    "validate_decision_object",
]

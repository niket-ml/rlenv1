"""Single public/hidden scientific semantics engine for Case 2 RC1.

The engine contains no private answer table.  It reconstructs every scored
identity, calculation, context, resource, belief, and decision fact from the
agent-visible packet, revealed/purchased evidence, committed host record, and
saved artifacts.  The hidden verifier is intentionally a thin caller.
"""

from __future__ import annotations

import copy
import csv
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from uc_bench.case1_pilot_v1_rc5_cohort import (
    CommittedCohort,
    reconstruct_committed_cohort,
)
from uc_bench.case1_pilot_v1_rc5_normalization import (
    NormalizationError,
    normalize_source_hashes,
)
from uc_bench.case1_pilot_v1_rc5_public_recompute import belief_revision_errors
from uc_bench.case2_pilot_v1_rc1_contract import (
    CONTEXT_CAPABLE_TARGETS,
    PREPURCHASE_IDENTITY_BASES,
    PUBLIC_CONTRACT,
    SCHEMA_VERSION,
    validate_final_submission,
    validate_followup_plan,
    validate_validation_plan,
)
from uc_bench.mmmvp_open_calculations import (
    CalculationResult,
    CanonicalRow,
    VerifiedTable,
    _aggregate_records,
    _parse_rows,
    _purchased_records,
    _raw_primary,
    _x17_primary,
    calculate_metric,
    verify_typed_calculations,
)


@dataclass(frozen=True, slots=True)
class OpenRequirement:
    requirement_id: str
    stage: str
    requirement_class: str
    passed: bool
    observed: Any
    expected: Any
    consequence: str
    remedy: str
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class OpenGrade:
    complete_mission_success: bool
    partial_scientific_quality: float
    reliability_score: float
    mission_failures: tuple[str, ...]
    first_decision_critical_failure: dict[str, Any] | None
    requirements: tuple[OpenRequirement, ...]
    diagnostics: dict[str, Any]
    failure_class: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


WEIGHTS = {
    "prospective_design_and_integrity": 15,
    "saved_artifact_chain": 10,
    "committed_entity_and_dependence_analysis": 15,
    "discrimination_and_uncertainty": 10,
    "probability_and_calibration": 10,
    "threshold_utility": 8,
    "context_robustness": 8,
    "decision_relevant_followup": 10,
    "belief_revision": 7,
    "bounded_decision_and_claims": 7,
}

PROPERTY_DEPENDENCIES = {
    "prospective_design_and_integrity": [],
    "saved_artifact_chain": [],
    "committed_entity_and_dependence_analysis": ["prospective_design_and_integrity"],
    "discrimination_and_uncertainty": [
        "committed_entity_and_dependence_analysis",
        "saved_artifact_chain",
    ],
    "probability_and_calibration": [
        "committed_entity_and_dependence_analysis",
        "saved_artifact_chain",
    ],
    "threshold_utility": [
        "committed_entity_and_dependence_analysis",
        "saved_artifact_chain",
    ],
    "context_robustness": [
        "committed_entity_and_dependence_analysis",
        "saved_artifact_chain",
    ],
    "decision_relevant_followup": [],
    "belief_revision": ["decision_relevant_followup"],
    "bounded_decision_and_claims": [
        "discrimination_and_uncertainty",
        "probability_and_calibration",
        "threshold_utility",
        "context_robustness",
        "decision_relevant_followup",
    ],
}


@dataclass(frozen=True, slots=True)
class ResourceFacts:
    resource_id: str
    question_relevant: bool
    returned_evidence_authentic: bool
    returned_result_correct: bool
    expected_results: dict[str, Any]
    expected_material: bool | None
    expected_effect: str | None
    resource_calculations_valid: bool
    evidence_bound_to_revision: bool
    property_pass: bool
    faults: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "resource_id": self.resource_id,
            "question_relevant": self.question_relevant,
            "returned_evidence_authentic": self.returned_evidence_authentic,
            "returned_result_correct": self.returned_result_correct,
            "expected_results": self.expected_results,
            "expected_material": self.expected_material,
            "expected_effect": self.expected_effect,
            "resource_calculations_valid": self.resource_calculations_valid,
            "evidence_bound_to_revision": self.evidence_bound_to_revision,
            "property_pass": self.property_pass,
            "faults": list(self.faults),
        }


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError(f"invalid CSV header: {path}")
        return list(reader)


def _safe_file(workspace: Path, relative: Any) -> Path | None:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        return None
    try:
        root = workspace.resolve(strict=True)
        candidate = (root / relative).resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    return candidate if root in candidate.parents and candidate.is_file() else None


def _protected_workspace_hashes(workspace: Path) -> dict[str, str]:
    return {
        path.relative_to(workspace).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(workspace.rglob("*"))
        if path.is_file() and "work" not in path.relative_to(workspace).parts
    }


def _event_integrity(workspace: Path, submission: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    events = submission.get("event_log") or []
    if not isinstance(events, list) or not all(isinstance(row, dict) for row in events):
        return False, {
            "malformed_event_record": True,
            "event_record_type": type(events).__name__,
        }
    names = (
        "commit_validation_plan",
        "reveal_validation",
        "commit_followup_plan",
        "purchase_resource",
        "submit",
    )
    positions = {
        name: next((index for index, row in enumerate(events) if row.get("event") == name), None)
        for name in names
    }
    unique = all(sum(row.get("event") == name for row in events) == 1 for name in names)
    ordered = all(value is not None for value in positions.values()) and [
        positions[name] for name in names
    ] == sorted(positions.values())
    validation = submission.get("validation_plan") or {}
    followup = submission.get("followup_plan") or {}
    final = submission.get("final_submission") or {}
    digest = lambda value: hashlib.sha256(  # noqa: E731 - compact pure helper
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    validation_hash, followup_hash, final_hash = map(digest, (validation, followup, final))
    by_event = {name: [row for row in events if row.get("event") == name] for name in names}
    raw_state = submission.get("state")
    state = raw_state if isinstance(raw_state, dict) else {}
    hashes_match = bool(
        unique
        and by_event["commit_validation_plan"][0].get("digest") == validation_hash
        and by_event["reveal_validation"][0].get("committed_plan_hash") == validation_hash
        and by_event["commit_followup_plan"][0].get("digest") == followup_hash
        and by_event["submit"][0].get("validation_plan_hash") == validation_hash
        and by_event["submit"][0].get("followup_plan_hash") == followup_hash
        and by_event["submit"][0].get("final_submission_hash") == final_hash
        and state.get("validation_plan_hash") == validation_hash
        and state.get("followup_plan_hash") == followup_hash
        and state.get("final_submission_hash") == final_hash
    )
    purchase_match = bool(
        unique
        and by_event["purchase_resource"][0].get("resource_id") == followup.get("chosen_resource")
    )
    records_match = False
    try:
        expected = (workspace.parent / ".mmmvp_host_records" / workspace.name).resolve()
        if submission.get("host_record_locator") != expected.as_posix():
            raise OSError("host record locator mismatch")
        records_match = all(
            json.loads((expected / filename).read_text(encoding="utf-8")) == value
            for filename, value in (
                ("validation_plan.json", validation),
                ("followup_plan.json", followup),
                ("final_submission.json", final),
                ("validation_input_hashes.json", submission.get("validation_input_hashes")),
            )
        )
    except (json.JSONDecodeError, OSError, TypeError):
        records_match = False
    protected = submission.get("protected_evidence_hashes") == _protected_workspace_hashes(
        workspace
    )
    return bool(
        ordered and unique and hashes_match and purchase_match and records_match and protected
    ), {
        "positions": positions,
        "unique": unique,
        "commitment_hashes_match": hashes_match,
        "purchase_matches_commitment": purchase_match,
        "host_records_match": records_match,
        "protected_evidence_hashes_match": protected,
    }


def _prospective_plan_implemented(
    workspace: Path,
    submission: dict[str, Any],
    validation: dict[str, Any],
    final: dict[str, Any],
) -> tuple[bool, dict[str, Any]]:
    manifested = {
        row.get("path") for row in final.get("artifact_manifest") or [] if isinstance(row, dict)
    }
    hashes = submission.get("validation_input_hashes") or {}
    rows: list[dict[str, Any]] = []
    for analysis in validation.get("planned_analyses") or []:
        inputs = analysis.get("input_paths") or []
        outputs = analysis.get("planned_output_paths") or []
        inputs_preserved = bool(inputs) and all(
            (path := _safe_file(workspace, relative)) is not None
            and hashes.get(relative) == hashlib.sha256(path.read_bytes()).hexdigest()
            for relative in inputs
        )
        outputs_preserved = bool(outputs) and all(
            isinstance(path, str) and path.startswith("work/") and path in manifested
            for path in outputs
        )
        rows.append(
            {
                "analysis_id": analysis.get("analysis_id"),
                "inputs_preserved": inputs_preserved,
                "outputs_preserved": outputs_preserved,
            }
        )
    evidence = validation.get("evidence_refs") or []
    evidence_preserved = bool(evidence) and all(
        (path := _safe_file(workspace, relative)) is not None
        and hashes.get(relative) == hashlib.sha256(path.read_bytes()).hexdigest()
        for relative in evidence
    )
    return bool(rows and evidence_preserved and all(all(row.values()) for row in rows)), {
        "analyses": rows,
        "evidence_preserved": evidence_preserved,
    }


def _artifact_index(
    workspace: Path, final: dict[str, Any]
) -> tuple[dict[str, tuple[dict[str, Any], Path]], list[str]]:
    result: dict[str, tuple[dict[str, Any], Path]] = {}
    errors: list[str] = []
    for row in final.get("artifact_manifest") or []:
        if not isinstance(row, dict):
            errors.append("artifact_not_object")
            continue
        identifier = row.get("artifact_id")
        path = _safe_file(workspace, row.get("path"))
        if not isinstance(identifier, str) or path is None or identifier in result:
            errors.append(f"missing_duplicate_or_unsafe:{identifier}")
            continue
        declared = row.get("sha256")
        if declared is not None and declared != hashlib.sha256(path.read_bytes()).hexdigest():
            errors.append(f"hash_mismatch:{identifier}")
            continue
        if any(_safe_file(workspace, source) is None for source in row.get("source_paths") or []):
            errors.append(f"missing_source:{identifier}")
            continue
        result[identifier] = (row, path)
    return result, errors


def _host_hashes(submission: dict[str, Any]) -> dict[str, str] | None:
    value = submission.get("validation_input_hashes")
    if not isinstance(value, dict):
        return None
    return {str(key): str(item) for key, item in value.items()}


def _identity_declaration_valid(workspace: Path) -> bool:
    try:
        value = json.loads((workspace / "identity_provenance.json").read_text(encoding="utf-8"))
        return bool(
            value.get("schema_version") == "case2-provisional-identity-1"
            and value.get("source_record_id", {}).get("canonical_person_truth") is False
            and value.get("fingerprint_cluster", {}).get("canonical_person_truth") is False
            and value.get("reported_patient_id", {}).get("canonical_person_truth") is False
            and value.get("fingerprint_cluster", {}).get("outcome_blind") is True
        )
    except (AttributeError, json.JSONDecodeError, OSError, TypeError):
        return False


def _reported_identity_conflict(workspace: Path) -> bool:
    rows = _read_csv(workspace / "data/cohort_metadata.csv")
    by_reported: dict[str, set[str]] = {}
    by_fingerprint: dict[str, set[str]] = {}
    for row in rows:
        if row.get("baseline_eligible", "").lower() != "true":
            continue
        by_reported.setdefault(row["reported_patient_id"], set()).add(row["fingerprint_cluster"])
        by_fingerprint.setdefault(row["fingerprint_cluster"], set()).add(row["reported_patient_id"])
    return any(len(values) != 1 for values in (*by_reported.values(), *by_fingerprint.values()))


def identity_state(workspace: Path) -> dict[str, Any]:
    """Derive provisional and, when purchased, adjudicated identity without constants."""

    metadata = [
        row
        for row in _read_csv(workspace / "data/cohort_metadata.csv")
        if row.get("baseline_eligible", "").lower() == "true"
    ]
    sources = {row["sample_id"] for row in metadata}
    provisional = {row["sample_id"]: row["fingerprint_cluster"] for row in metadata}
    result: dict[str, Any] = {
        "source_record_count": len(sources),
        "provisional_unit_count": len(set(provisional.values())),
        "reported_identifier_count": len({row["reported_patient_id"] for row in metadata}),
        "reported_identifier_conflict": _reported_identity_conflict(workspace),
        "adjudicated_available": False,
        "adjudicated_person_count": None,
        "membership_changed": None,
        "unresolved_record_count": None,
    }
    path = workspace / "purchased/X17/canonical_person_crosswalk.csv"
    if not path.is_file():
        return result
    rows = _read_csv(path)
    by_source = {row.get("source_record_id"): row for row in rows}
    valid = bool(
        len(by_source) == len(rows)
        and set(by_source) == sources
        and all(
            row.get("fingerprint_cluster") == provisional[source]
            and bool(row.get("canonical_person_id"))
            for source, row in by_source.items()
        )
    )
    if not valid:
        return {**result, "adjudication_fault": "crosswalk_does_not_cover_source_universe"}
    canonical = {source: str(row["canonical_person_id"]) for source, row in by_source.items()}
    changed = any(
        len({canonical[source] for source in sources if provisional[source] == cluster}) != 1
        for cluster in set(provisional.values())
    ) or any(
        len({provisional[source] for source in sources if canonical[source] == person}) != 1
        for person in set(canonical.values())
    )
    unresolved = 0
    provenance_path = workspace / "purchased/X17/adjudication_provenance.json"
    if provenance_path.is_file():
        try:
            provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
            unresolved = len(provenance.get("remaining_uncertainty") or [])
        except (AttributeError, json.JSONDecodeError, OSError):
            unresolved = -1
    return {
        **result,
        "adjudicated_available": True,
        "adjudicated_person_count": len(set(canonical.values())),
        "membership_changed": changed,
        "unresolved_record_count": unresolved,
    }


def _expected_records(
    workspace: Path,
    manifest: dict[str, Any],
    cohort: CommittedCohort,
    selected_resource: str,
) -> tuple[dict[str, dict[str, Any]], str] | None:
    source_paths = tuple(str(path) for path in manifest.get("source_paths") or [])
    identity_basis = manifest.get("identity_basis")
    if any(path.startswith("purchased/X17/") for path in source_paths):
        records = _x17_primary(workspace)
        if records is None or identity_basis != "ADJUDICATED_CANONICAL_PERSON":
            return None
        return (
            {key: value for key, value in records.items() if key in cohort.included_source_records},
            "PURCHASED",
        )
    if any(path.startswith(f"purchased/{selected_resource}/") for path in source_paths):
        records = _purchased_records(workspace, selected_resource)
        if selected_resource == "X58":
            prediction_path = workspace / "purchased/X58/additional_predictions.csv"
            outcome_path = workspace / "purchased/X58/additional_outcomes.csv"
            if prediction_path.is_file() and outcome_path.is_file():
                outcomes = {
                    row["patient_key"]: int(row["week6_response"])
                    for row in _read_csv(outcome_path)
                }
                predictions = _read_csv(prediction_path)
                if all(row.get("patient_key") in outcomes for row in predictions):
                    records = {
                        str(row["patient_key"]): {
                            "source_record_id": str(row["patient_key"]),
                            "entity_id": str(row["patient_key"]),
                            "prediction": float(row["predicted_probability"]),
                            "outcome": outcomes[str(row["patient_key"])],
                            "context": str(row.get("site", "")),
                        }
                        for row in predictions
                    }
        expected_basis = (
            "PROVISIONAL_FINGERPRINT_AGGREGATION"
            if selected_resource == "X31"
            else "EXTERNAL_COHORT_PERSON"
        )
        if records is None or identity_basis != expected_basis:
            return None
        return records, "PURCHASED"
    records = {
        key: value
        for key, value in _raw_primary(workspace).items()
        if key in cohort.included_source_records
    }
    if identity_basis == "REPORTED_PATIENT_SENSITIVITY":
        reported = {
            row["sample_id"]: row["reported_patient_id"]
            for row in _read_csv(workspace / "data/cohort_metadata.csv")
        }
        records = {key: {**value, "entity_id": reported[key]} for key, value in records.items()}
    elif identity_basis not in PREPURCHASE_IDENTITY_BASES:
        return None
    return records, "SUPPLIED_AND_REVEALED"


def _table_matches(
    path: Path,
    manifest: dict[str, Any],
    records: dict[str, dict[str, Any]],
    evidence_source: str,
) -> VerifiedTable | None:
    mapping = manifest.get("column_map") or {}
    structure = manifest.get("analysis_structure")
    aggregation = manifest.get("aggregation")
    identity_basis = manifest.get("identity_basis")
    if identity_basis == "PROVISIONAL_FINGERPRINT_AGGREGATION" and structure != "ENTITY_AGGREGATED":
        return None
    if (
        identity_basis == "PROVISIONAL_FINGERPRINT_WEIGHTED_ROWS"
        and structure != "SOURCE_RECORD_CLUSTERED"
    ):
        return None
    observed = _parse_rows(path, mapping)
    if not observed or not records:
        return None
    if structure == "ENTITY_AGGREGATED":
        expected = _aggregate_records(records, str(aggregation))
        if len(observed) != len(expected) or len({row.entity_id for row in observed}) != len(
            observed
        ):
            return None
        by_entity = {row.entity_id: row for row in observed}
        if set(by_entity) != set(expected):
            return None
        for entity, wanted in expected.items():
            got = by_entity[entity]
            if (
                got.source_record_ids != wanted.source_record_ids
                or got.outcome != wanted.outcome
                or got.contexts != wanted.contexts
                or not math.isclose(got.prediction, wanted.prediction, abs_tol=5e-5)
            ):
                return None
    elif structure == "SOURCE_RECORD_CLUSTERED" and aggregation == "NONE":
        if len(observed) != len(records):
            return None
        seen: set[str] = set()
        for got in observed:
            if len(got.source_record_ids) != 1:
                return None
            source = got.source_record_ids[0]
            wanted = records.get(source)
            if wanted is None or source in seen:
                return None
            seen.add(source)
            if (
                got.entity_id != wanted["entity_id"]
                or got.outcome != wanted["outcome"]
                or got.contexts != ((wanted["context"],) if wanted["context"] else ())
                or not math.isclose(got.prediction, wanted["prediction"], abs_tol=5e-5)
            ):
                return None
        if seen != set(records):
            return None
    else:
        return None
    if any(row.split != "VALIDATION" for row in observed):
        return None
    return VerifiedTable(
        artifact_id=str(manifest["artifact_id"]),
        structure=str(structure),
        aggregation=str(aggregation),
        evidence_source=evidence_source,
        rows=tuple(observed),
        prediction_column=str(mapping["prediction"]),
        outcome_column=str(mapping["outcome"]),
        context_columns=(str(mapping["context"]),) if mapping.get("context") else (),
        source_paths=tuple(str(path) for path in manifest.get("source_paths") or []),
    )


def verified_case2_tables(
    workspace: Path,
    artifacts: dict[str, tuple[dict[str, Any], Path]],
    cohort: CommittedCohort,
    selected_resource: str,
) -> dict[str, VerifiedTable]:
    result: dict[str, VerifiedTable] = {}
    for artifact_id, (manifest, path) in artifacts.items():
        if manifest.get("role") != "ANALYSIS_TABLE":
            continue
        try:
            expected = _expected_records(workspace, manifest, cohort, selected_resource)
            if expected is None:
                continue
            table = _table_matches(path, manifest, *expected)
            if table is not None:
                result[artifact_id] = table
        except (KeyError, OSError, TypeError, ValueError, csv.Error):
            continue
    return result


def _site_summary(rows: tuple[CanonicalRow, ...], estimator: str) -> dict[str, Any]:
    intended_sites: set[str] = set()
    grouped: dict[str, list[CanonicalRow]] = {}
    multi_context: set[str] = set()
    for row in rows:
        if len(row.contexts) != 1:
            multi_context.add(row.entity_id)
            intended_sites.update(row.contexts)
            continue
        intended_sites.add(row.contexts[0])
        grouped.setdefault(row.contexts[0], []).append(row)
    sites: dict[str, Any] = {}
    for site in sorted(intended_sites):
        site_rows = grouped.get(site, [])
        evaluable = bool(site_rows and len({row.outcome for row in site_rows}) == 2)
        sites[site] = {
            "source_row_count": sum(len(row.source_record_ids) for row in site_rows),
            "analysis_row_count": len(site_rows),
            "entity_count": len({row.entity_id for row in site_rows}),
            "status": "EVALUABLE" if evaluable else "NOT_EVALUABLE",
            "roc_auc": calculate_metric(site_rows, "ROC_AUC", estimator, {}) if evaluable else None,
        }
    return {
        "sites": sites,
        "multi_context_entity_ids": sorted(multi_context),
    }


def _close(got: Any, wanted: Any, tolerance: float = 0.002) -> bool:
    if wanted is None or isinstance(wanted, bool):
        return got is wanted
    return bool(
        isinstance(got, (int, float))
        and not isinstance(got, bool)
        and math.isclose(float(got), float(wanted), abs_tol=tolerance)
    )


def _context_audit_valid(
    calculation: dict[str, Any],
    result: CalculationResult,
    table: VerifiedTable,
    artifacts: dict[str, tuple[dict[str, Any], Path]],
) -> tuple[bool, dict[str, Any]]:
    expected = _site_summary(table.rows, str(calculation.get("estimator")))
    artifact = artifacts.get(str(calculation.get("output_artifact_id") or ""))
    observed: Any = None
    try:
        if artifact is None:
            raise ValueError("calculation output missing")
        payload = json.loads(artifact[1].read_text(encoding="utf-8"))
        matches = [
            row
            for row in payload.get("typed_calculations", [])
            if row.get("calculation_id") == calculation.get("calculation_id")
        ]
        if len(matches) != 1:
            raise ValueError("context calculation output is not unique")
        observed = matches[0].get("site_audit")
        if not isinstance(observed, dict):
            raise ValueError("site_audit is missing")
        if observed.get("multi_context_entity_ids") != expected["multi_context_entity_ids"]:
            raise ValueError("multi-context inventory mismatch")
        got_sites = observed.get("sites")
        if not isinstance(got_sites, dict) or set(got_sites) != set(expected["sites"]):
            raise ValueError("site inventory mismatch")
        for site, wanted in expected["sites"].items():
            got = got_sites.get(site)
            if not isinstance(got, dict):
                raise ValueError("site audit row missing")
            for field in ("source_row_count", "analysis_row_count", "entity_count", "status"):
                if got.get(field) != wanted[field]:
                    raise ValueError(f"site audit mismatch: {site}:{field}")
            if not _close(got.get("roc_auc"), wanted["roc_auc"]):
                raise ValueError(f"site AUC mismatch: {site}")
        all_evaluable = all(row["status"] == "EVALUABLE" for row in expected["sites"].values())
        no_silent_multi_context = not expected["multi_context_entity_ids"]
        return bool(result.valid and all_evaluable and no_silent_multi_context), {
            "expected": expected,
            "observed": observed,
            "all_sites_evaluable": all_evaluable,
            "no_silent_multi_context": no_silent_multi_context,
        }
    except (AttributeError, json.JSONDecodeError, KeyError, OSError, TypeError, ValueError):
        return False, {"expected": expected, "observed": observed}


def _criterion_results(
    validation: dict[str, Any],
    final: dict[str, Any],
    calculations: dict[str, CalculationResult],
    tables: dict[str, VerifiedTable],
    artifacts: dict[str, tuple[dict[str, Any], Path]],
) -> tuple[dict[str, bool], dict[str, Any]]:
    by_id = {
        str(row.get("calculation_id")): row
        for row in final.get("calculations") or []
        if isinstance(row, dict)
    }
    status: dict[str, bool] = {}
    details: dict[str, Any] = {}
    for criterion in validation.get("decision_criteria") or []:
        identifier = str(criterion.get("criterion_id") or "")
        calculation_id = str(criterion.get("calculation_id") or "")
        declared = by_id.get(calculation_id, {})
        verified = calculations.get(calculation_id)
        calculation_valid = bool(
            verified
            and verified.valid
            and verified.role == "PRIMARY"
            and declared.get("metric") == criterion.get("metric")
        )
        specification = validation.get("prospective_specification") or {}
        expected_metric = {
            "DISCRIMINATION": specification.get("discrimination_metric"),
            "PROBABILITY_ACCURACY": specification.get("probability_metric"),
            "CALIBRATION": specification.get("calibration_metric"),
            "THRESHOLD_UTILITY": specification.get("utility_metric"),
            "CONTEXT_ROBUSTNESS": criterion.get("metric"),
        }.get(criterion.get("property"))
        expected_estimator = specification.get("estimator")
        parameters = declared.get("parameters") or {}
        calculation_valid = bool(
            calculation_valid
            and declared.get("metric") == expected_metric
            and declared.get("estimator") == expected_estimator
        )
        if criterion.get("property") == "CALIBRATION":
            calculation_valid = bool(
                calculation_valid
                and parameters.get("bin_count") == specification.get("calibration_bin_count")
            )
        if criterion.get("property") == "THRESHOLD_UTILITY":
            calculation_valid = bool(
                calculation_valid
                and _close(
                    parameters.get("threshold"), specification.get("utility_threshold"), 1e-12
                )
            )
        if criterion.get("property") == "DISCRIMINATION":
            uncertainty = declared.get("uncertainty") or {}
            calculation_valid = bool(
                calculation_valid
                and verified
                and verified.uncertainty_claimed
                and verified.uncertainty_valid
                and uncertainty.get("method") == specification.get("uncertainty_method")
                and uncertainty.get("replicates") == specification.get("uncertainty_replicates")
                and uncertainty.get("seed") == specification.get("uncertainty_seed")
                and _close(uncertainty.get("level"), specification.get("uncertainty_level"), 1e-12)
            )
        context_details: dict[str, Any] | None = None
        if calculation_valid and criterion.get("property") == "CONTEXT_ROBUSTNESS":
            table = tables.get(str(declared.get("source_analysis_table_id") or ""))
            if table is None:
                calculation_valid = False
            else:
                calculation_valid, context_details = _context_audit_valid(
                    declared, verified, table, artifacts
                )
        passed = calculation_valid
        if passed:
            value = float(verified.recomputed_value)
            threshold = float(criterion["threshold"])
            passed = (
                value >= threshold
                if criterion.get("comparator") == "AT_LEAST"
                else value <= threshold
            )
            if criterion.get("property") == "DISCRIMINATION":
                passed = bool(
                    passed
                    and float((declared.get("uncertainty") or {}).get("lower", float("-inf")))
                    >= 0.58
                )
        status[identifier] = passed
        details[identifier] = {
            "property": criterion.get("property"),
            "metric": criterion.get("metric"),
            "calculation_id": calculation_id,
            "calculation_valid": calculation_valid,
            "criterion_passed": passed,
            "context_audit": context_details,
        }
    return status, details


def _primary_property_status(
    validation: dict[str, Any], criterion_details: dict[str, Any]
) -> dict[str, bool]:
    grouped: dict[str, list[bool]] = {}
    for row in validation.get("decision_criteria") or []:
        grouped.setdefault(str(row.get("property")), []).append(
            bool(
                (criterion_details.get(str(row.get("criterion_id") or "")) or {}).get(
                    "calculation_valid"
                )
            )
        )
    return {prop: bool(values) and all(values) for prop, values in grouped.items()}


def _resource_files(workspace: Path, resource: str) -> dict[str, str]:
    root = workspace / "purchased" / resource
    return {
        path.relative_to(workspace).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _binary_resource_metrics(
    prediction_rows: list[dict[str, str]], outcome_rows: list[dict[str, str]]
) -> dict[str, Any]:
    outcomes = {row["patient_key"]: int(row["week6_response"]) for row in outcome_rows}
    rows = [
        CanonicalRow(
            entity_id=row["patient_key"],
            source_record_ids=(row["patient_key"],),
            prediction=float(row["predicted_probability"]),
            outcome=outcomes[row["patient_key"]],
            split="VALIDATION",
            contexts=(row["site"],) if row.get("site") else (),
        )
        for row in prediction_rows
    ]
    result = {
        "entity_count": len(rows),
        "roc_auc": calculate_metric(rows, "ROC_AUC", "EMPIRICAL", {}),
        "brier_score": calculate_metric(rows, "BRIER_SCORE", "EMPIRICAL", {}),
        "net_benefit": calculate_metric(rows, "NET_BENEFIT", "EMPIRICAL", {"threshold": 0.5}),
    }
    if all(len(row.contexts) == 1 for row in rows):
        result["site_weighted_roc_auc"] = calculate_metric(
            rows, "SITE_WEIGHTED_ROC_AUC", "EMPIRICAL", {}
        )
        result["worst_site_roc_auc"] = calculate_metric(rows, "WORST_SITE_ROC_AUC", "EMPIRICAL", {})
    return result


def _expected_resource_results(workspace: Path, resource: str) -> dict[str, Any]:
    if resource == "none":
        value = json.loads(
            (workspace / "purchased/none/no_new_evidence.json").read_text(encoding="utf-8")
        )
        return {"new_evidence": bool(value.get("new_evidence"))}
    if resource == "X17":
        state = identity_state(workspace)
        if not state["adjudicated_available"]:
            raise ValueError("X17 crosswalk is invalid")
        return {
            "source_record_count": state["source_record_count"],
            "provisional_unit_count": state["provisional_unit_count"],
            "adjudicated_person_count": state["adjudicated_person_count"],
            "membership_changed": state["membership_changed"],
            "unresolved_record_count": state["unresolved_record_count"],
        }
    if resource in {"X46", "X58"}:
        stem = "matched" if resource == "X46" else "additional"
        return _binary_resource_metrics(
            _read_csv(workspace / f"purchased/{resource}/{stem}_predictions.csv"),
            _read_csv(workspace / f"purchased/{resource}/{stem}_outcomes.csv"),
        )
    if resource == "X31":
        return _binary_resource_metrics(
            _read_csv(workspace / "purchased/X31/replay_predictions.csv"),
            _read_csv(workspace / "revealed/validation_outcomes.csv"),
        )
    if resource == "X24":
        adjudicated = _read_csv(workspace / "purchased/X24/adjudicated_endpoints.csv")
        observed = {
            row["patient_key"]: row["week6_response"]
            for row in _read_csv(workspace / "revealed/validation_outcomes.csv")
        }
        return {
            "reviewed_entity_count": len(adjudicated),
            "changed_label_count": sum(
                str(row["week6_response"]) != observed.get(row["patient_key"])
                for row in adjudicated
            ),
            "reviewer_disagreement_count": sum(
                row.get("reviewer_agreement") != "concordant" for row in adjudicated
            ),
        }
    if resource == "X63":
        memo = json.loads(
            (workspace / "purchased/X63/review_memo.json").read_text(encoding="utf-8")
        )
        return {
            "new_empirical_evidence": bool(memo.get("new_empirical_evidence")),
            "recommendation_count": len(memo.get("recommendations") or []),
        }
    raise ValueError("unknown resource")


def _resource_effect(
    workspace: Path,
    validation: dict[str, Any],
    followup: dict[str, Any],
    criteria: dict[str, bool],
    results: dict[str, Any],
    primary_values: dict[str, float],
) -> tuple[bool, str]:
    resource = str(followup.get("chosen_resource") or "")
    if resource == "none":
        return False, "NO_NEW_EVIDENCE"
    if resource == "X17":
        relevant = _reported_identity_conflict(workspace)
        unresolved = results.get("unresolved_record_count")
        material = bool(
            relevant
            and (
                results.get("membership_changed") is True
                or isinstance(unresolved, int)
                and unresolved > 0
            )
        )
        resolved = bool(material and unresolved == 0)
        return material, "RESOLVES" if resolved else (
            "REDUCES_UNCERTAINTY" if material else "INEFFECTIVE"
        )
    if resource == "X46":
        context_rows = [
            row
            for row in validation.get("decision_criteria") or []
            if row.get("property") == "CONTEXT_ROBUSTNESS"
        ]
        external_pass = all(
            isinstance(results.get(str(row.get("metric")).lower()), (int, float))
            and float(results[str(row.get("metric")).lower()]) >= float(row["threshold"])
            for row in context_rows
        )
        return True, "RESOLVES" if external_pass else "EXPOSES_BLOCKER"
    if resource == "X24":
        endpoint_rows = _read_csv(workspace / "data/endpoint_source_ledger.csv")
        visible_flag = any(row.get("review_status") != "concordant" for row in endpoint_rows)
        return (True, "RESOLVES") if visible_flag else (False, "INEFFECTIVE")
    threshold = followup.get("materiality_threshold")
    if (
        resource in {"X31", "X58"}
        and isinstance(threshold, (int, float))
        and not isinstance(threshold, bool)
    ):
        threshold = float(threshold)
        if resource == "X31":
            auc = results.get("roc_auc")
            primary_auc = primary_values.get("ROC_AUC")
            changed = bool(
                isinstance(auc, (int, float))
                and isinstance(primary_auc, (int, float))
                and abs(float(auc) - float(primary_auc)) > threshold
            )
            return changed, "REDUCES_UNCERTAINTY" if changed else "INEFFECTIVE"

        comparable = {
            metric: abs(float(results[key]) - primary_values[metric])
            for metric, key in (
                ("ROC_AUC", "roc_auc"),
                ("BRIER_SCORE", "brier_score"),
                ("NET_BENEFIT", "net_benefit"),
                ("SITE_WEIGHTED_ROC_AUC", "site_weighted_roc_auc"),
                ("WORST_SITE_ROC_AUC", "worst_site_roc_auc"),
            )
            if metric in primary_values and isinstance(results.get(key), (int, float))
        }
        changed = bool(comparable and max(comparable.values()) > threshold)
        criterion_rows = {
            str(row.get("metric")): row
            for row in validation.get("decision_criteria") or []
            if isinstance(row, dict)
        }
        resource_passes: dict[str, bool] = {}
        for metric, key in (
            ("ROC_AUC", "roc_auc"),
            ("BRIER_SCORE", "brier_score"),
            ("NET_BENEFIT", "net_benefit"),
            ("SITE_WEIGHTED_ROC_AUC", "site_weighted_roc_auc"),
            ("WORST_SITE_ROC_AUC", "worst_site_roc_auc"),
        ):
            criterion = criterion_rows.get(metric)
            value = results.get(key)
            if criterion is None or not isinstance(value, (int, float)):
                continue
            resource_passes[metric] = (
                float(value) >= float(criterion["threshold"])
                if criterion.get("comparator") == "AT_LEAST"
                else float(value) <= float(criterion["threshold"])
            )
        primary_by_metric = {
            str(row.get("metric")): criteria.get(str(row.get("criterion_id")))
            for row in validation.get("decision_criteria") or []
            if isinstance(row, dict)
        }
        crosses_gate = any(
            primary_by_metric.get(metric) is not passed
            for metric, passed in resource_passes.items()
            if isinstance(primary_by_metric.get(metric), bool)
        )
        exposes_harm = bool(
            isinstance(results.get("net_benefit"), (int, float))
            and float(results["net_benefit"]) < 0
        )
        material = changed or crosses_gate or exposes_harm
        effect = (
            "EXPOSES_BLOCKER"
            if exposes_harm or any(not value for value in resource_passes.values())
            else "REDUCES_UNCERTAINTY"
        )
        return material, effect if material else "INEFFECTIVE"
    if resource == "X63" and results.get("new_empirical_evidence") is False:
        return False, "INEFFECTIVE"
    return False, "INEFFECTIVE"


def evaluate_resource(
    workspace: Path,
    submission: dict[str, Any],
    calculations: dict[str, CalculationResult],
    criteria: dict[str, bool],
    tables: dict[str, VerifiedTable],
) -> ResourceFacts:
    followup = submission.get("followup_plan") or {}
    final = submission.get("final_submission") or {}
    assessment = final.get("resource_assessment") or {}
    resource = str(followup.get("chosen_resource") or "")
    faults: list[str] = []
    mapping = PUBLIC_CONTRACT["resource_question_mapping"]
    target_mapping = PUBLIC_CONTRACT["resource_evidence_target_mapping"]
    question = followup.get("decision_question_type")
    if mapping.get(question) != resource or target_mapping.get(question) != followup.get(
        "evidence_target"
    ):
        faults.append("resource_question_mapping_invalid")
    question_relevant = True
    if resource == "X17":
        question_relevant = _reported_identity_conflict(workspace)
    elif resource == "X46":
        # Internal multi-site robustness and transport to a matched external
        # cohort are distinct questions.  A prospectively declared transport
        # question can be relevant whether internal context checks pass or
        # fail; its returned evidence still has to be calculated and used.
        question_relevant = True
    elif resource == "none":
        question_relevant = bool(criteria) and all(
            isinstance(value, bool) for value in criteria.values()
        )
    elif resource == "X63" and followup.get("evidence_target") != "EXPERT_REVIEW":
        question_relevant = False
    if not question_relevant:
        faults.append("resource_not_relevant_to_declared_question")
    returned_hashes: dict[str, str] = {}
    expected_results: dict[str, Any] = {}
    authentic = result_correct = False
    try:
        returned_hashes = _resource_files(workspace, resource)
        expected_results = _expected_resource_results(workspace, resource)
        summary_path = _safe_file(workspace, assessment.get("summary_artifact_path"))
        if summary_path is None:
            raise ValueError("resource summary missing")
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        authentic = bool(
            summary.get("schema_version") == "case2-resource-summary-1"
            and summary.get("resource_id") == resource
            and normalize_source_hashes(summary.get("source_hashes")) == returned_hashes
        )
        observed_results = summary.get("results")
        result_correct = bool(
            isinstance(observed_results, dict)
            and set(observed_results) == set(expected_results)
            and all(
                _close(observed_results[key], wanted) for key, wanted in expected_results.items()
            )
        )
    except (
        ArithmeticError,
        AttributeError,
        json.JSONDecodeError,
        KeyError,
        NormalizationError,
        OSError,
        TypeError,
        ValueError,
    ):
        authentic = result_correct = False
    if not authentic:
        faults.append("returned_evidence_not_authentic")
    if not result_correct:
        faults.append("returned_result_not_recomputed")
    expected_material: bool | None = None
    expected_effect: str | None = None
    if result_correct:
        primary_values = {
            row.metric: float(row.recomputed_value)
            for row in calculations.values()
            if row.valid and row.role == "PRIMARY" and row.recomputed_value is not None
        }
        expected_material, expected_effect = _resource_effect(
            workspace,
            submission.get("validation_plan") or {},
            followup,
            criteria,
            expected_results,
            primary_values,
        )
    if assessment.get("resource_id") != resource or assessment.get("question_type") != question:
        faults.append("resource_assessment_commitment_mismatch")
    if expected_material is None or assessment.get("material") is not expected_material:
        faults.append("resource_materiality_mismatch")
    if expected_effect is None or assessment.get("observed_effect") != expected_effect:
        faults.append("resource_effect_mismatch")
    calculation_ids = set(assessment.get("calculation_ids") or [])
    calculations_valid = bool(
        calculation_ids.issubset(calculations)
        and all(
            calculations[item].valid and calculations[item].role == "FOLLOWUP"
            for item in calculation_ids
        )
    )
    if resource in {"X17", "X31", "X46", "X58"} and not calculation_ids:
        calculations_valid = False
    if resource in {"X17", "X31", "X46", "X58"}:
        purchased_prefix = f"purchased/{resource}/"
        calculations_valid = calculations_valid and all(
            calculations[item].table_id in tables
            and tables[calculations[item].table_id].evidence_source == "PURCHASED"
            and any(
                str(path).startswith(purchased_prefix)
                for path in tables[calculations[item].table_id].source_paths
            )
            for item in calculation_ids
            if item in calculations
        )
    if resource == "X17":
        final_manifest = final.get("artifact_manifest") or []
        calculations_valid = calculations_valid and any(
            row.get("role") == "ANALYSIS_TABLE"
            and row.get("identity_basis") == "ADJUDICATED_CANONICAL_PERSON"
            and any(
                str(path).startswith("purchased/X17/") for path in row.get("source_paths") or []
            )
            for row in final_manifest
        )
    if not calculations_valid:
        faults.append("purchased_evidence_not_used_in_valid_calculation")
    summary_relative = assessment.get("summary_artifact_path")
    updates = final.get("belief_updates") or []
    evidence_bound = bool(
        updates
        and isinstance(summary_relative, str)
        and all(summary_relative in set(row.get("evidence_refs") or []) for row in updates)
    )
    if not evidence_bound:
        faults.append("resource_not_bound_to_belief_revision")
    if resource == "X63" and assessment.get("material") is True:
        faults.append("expert_memo_cannot_substitute_for_empirical_analysis")
    if resource != "none" and expected_effect == "INEFFECTIVE":
        faults.append("purchased_resource_not_decision_resolving")
    return ResourceFacts(
        resource_id=resource,
        question_relevant=question_relevant,
        returned_evidence_authentic=authentic,
        returned_result_correct=result_correct,
        expected_results=expected_results,
        expected_material=expected_material,
        expected_effect=expected_effect,
        resource_calculations_valid=calculations_valid,
        evidence_bound_to_revision=evidence_bound,
        property_pass=not faults,
        faults=tuple(dict.fromkeys(faults)),
    )


def _selected_contingency(submission: dict[str, Any]) -> dict[str, Any] | None:
    followup = submission.get("followup_plan") or {}
    final = submission.get("final_submission") or {}
    rows = {
        row.get("contingency_id"): row
        for row in followup.get("result_contingencies") or []
        if isinstance(row, dict)
    }
    identifiers = {
        row.get("matched_contingency_id")
        for row in final.get("belief_updates") or []
        if isinstance(row, dict)
    }
    return rows.get(next(iter(identifiers))) if len(identifiers) == 1 else None


def _decision_valid(
    workspace: Path,
    submission: dict[str, Any],
    criteria: dict[str, bool],
    criterion_details: dict[str, Any],
    calculations: dict[str, CalculationResult],
    resource: ResourceFacts,
) -> tuple[bool, dict[str, Any]]:
    final = submission.get("final_submission") or {}
    decision = final.get("decision") or {}
    selected = _selected_contingency(submission)
    faults: list[str] = []
    if selected is None:
        faults.append("selected_contingency_missing")
    else:
        committed = selected.get("next_decision") or {}
        for field in (
            "development_stage",
            "disposition",
            "use_scope",
            "action_scope",
            "current_context_status",
            "multisite_probability_use_permitted",
            "next_evidence_target",
            "identity_claim_basis",
        ):
            if decision.get(field) != committed.get(field):
                faults.append(f"decision_differs_from_contingency:{field}")
    context_ids = [
        str(row.get("criterion_id") or "")
        for row in (submission.get("validation_plan") or {}).get("decision_criteria") or []
        if row.get("property") == "CONTEXT_ROBUSTNESS"
    ]
    context_evaluable = bool(context_ids) and all(
        (criterion_details.get(identifier) or {}).get("calculation_valid") is True
        for identifier in context_ids
    )
    context_passed = context_evaluable and all(
        criteria.get(identifier) is True for identifier in context_ids
    )
    expected_status = (
        "PASSED" if context_passed else ("FAILED" if context_evaluable else "NOT_EVALUABLE")
    )
    if decision.get("current_context_status") != expected_status:
        faults.append("declared_context_status_mismatch")
    all_passed = bool(criteria) and all(criteria.values())
    disposition = decision.get("disposition")
    action_scope = decision.get("action_scope")
    permitted = decision.get("multisite_probability_use_permitted")
    if action_scope == "GENERAL_MULTISITE_ADVANCEMENT":
        if disposition != "CONTINUE" or not all_passed or permitted is not True:
            faults.append("general_advancement_not_supported")
    elif action_scope == "TARGETED_CONTEXT_INVESTIGATION":
        if (
            disposition != "CONTINUE"
            or context_passed
            or permitted is not False
            or decision.get("next_evidence_target") not in CONTEXT_CAPABLE_TARGETS
        ):
            faults.append("targeted_context_continue_not_bounded")
    elif action_scope == "HOLD_CURRENT_CLAIM":
        unresolved = bool(
            not all_passed
            or resource.expected_effect in {"EXPOSES_BLOCKER", "MISLEADING_REASSURANCE"}
        )
        if (
            disposition not in {"PAUSE", "INSUFFICIENT_EVIDENCE"}
            or permitted is not False
            or not unresolved
        ):
            faults.append("held_claim_decision_inconsistent")
    elif action_scope == "END_DEVELOPMENT_PATH":
        invalidating_ids = {
            item
            for row in final.get("findings") or []
            if row.get("status") == "SUPPORTED" and row.get("decision_effect") == "INVALIDATES"
            for item in row.get("calculation_ids") or []
        }
        failed_criterion_calculations = {
            str(row.get("calculation_id") or "")
            for row in (submission.get("validation_plan") or {}).get("decision_criteria") or []
            if isinstance(row, dict) and criteria.get(str(row.get("criterion_id") or "")) is False
        }
        resource_calculations = {
            str(item)
            for item in (final.get("resource_assessment") or {}).get("calculation_ids") or []
            if resource.expected_effect in {"EXPOSES_BLOCKER", "MISLEADING_REASSURANCE"}
        }
        verified_invalidating_ids = failed_criterion_calculations | resource_calculations
        if (
            disposition != "STOP"
            or permitted is not False
            or not invalidating_ids
            or not invalidating_ids <= verified_invalidating_ids
            or not all(
                item in calculations and calculations[item].valid for item in invalidating_ids
            )
        ):
            faults.append("stop_not_supported_by_invalidating_evidence")
    else:
        faults.append("action_scope_unknown")
    if decision.get("identity_claim_basis") == "ADJUDICATED_PERSON" and not (
        resource.resource_id == "X17"
        and resource.returned_result_correct
        and resource.resource_calculations_valid
    ):
        faults.append("adjudicated_person_claim_without_x17_recomputation")
    claims = final.get("claims") or []
    valid_calculation_ids = {key for key, row in calculations.items() if row.valid}
    for row in claims:
        if row.get("status") != "SUPPORTED":
            continue
        references = set(row.get("calculation_ids") or [])
        if not references or not references <= valid_calculation_ids:
            faults.append("supported_claim_lacks_valid_calculation")
        if any(_safe_file(workspace, path) is None for path in row.get("evidence_refs") or []):
            faults.append("supported_claim_lacks_saved_evidence")
        if row.get("scope") in {
            "INDEPENDENT_VALIDATION",
            "CLINICAL_UTILITY",
            "TREATMENT_EFFECT",
            "CROSS_CONTEXT_TRANSPORT",
        }:
            faults.append("unsupported_broad_claim")
        if row.get("scope") == "PROGNOSTIC_PROBABILITY" and not all_passed:
            faults.append("probability_claim_exceeds_failed_criteria")
    if action_scope == "TARGETED_CONTEXT_INVESTIGATION" and any(
        row.get("status") == "SUPPORTED"
        and row.get("scope") in {"PROGNOSTIC_PROBABILITY", "CROSS_CONTEXT_TRANSPORT"}
        for row in claims
    ):
        faults.append("targeted_investigation_overclaims_current_evidence")
    return not faults, {
        "all_committed_criteria_passed": all_passed,
        "context_passed": context_passed,
        "expected_context_status": expected_status,
        "faults": list(dict.fromkeys(faults)),
    }


def _requirement(identifier: str, passed: bool, observed: Any) -> OpenRequirement:
    metadata = {
        "prospective_design_and_integrity": (
            "planning",
            "The analysis may adapt after outcomes or use an uncommitted cohort.",
            "Commit the complete provisional-unit cohort, methods and criteria before reveal.",
        ),
        "saved_artifact_chain": (
            "analysis",
            "Reported work cannot be independently reproduced.",
            "Save source-linked tables and machine-checkable calculation outputs.",
        ),
        "committed_entity_and_dependence_analysis": (
            "analysis",
            "Dependent biopsy records may be mistaken for independent people.",
            "Use a disclosed provisional-unit estimand or dependence-preserving row analysis.",
        ),
        "discrimination_and_uncertainty": (
            "analysis",
            "Discrimination or its uncertainty is unsupported.",
            "Recompute the committed discrimination analysis with cluster-respecting uncertainty.",
        ),
        "probability_and_calibration": (
            "analysis",
            "Probability accuracy or calibration is unsupported.",
            "Recompute the committed probability and calibration metrics.",
        ),
        "threshold_utility": (
            "analysis",
            "Threshold utility is unsupported.",
            "Recompute utility at the intended-use action threshold.",
        ),
        "context_robustness": (
            "analysis",
            "Pooled performance may hide a failing or non-evaluable site.",
            "Save and verify every site's counts, status and estimate under the committed rule.",
        ),
        "decision_relevant_followup": (
            "followup",
            "The purchase does not answer or is not used for the declared question.",
            "Choose at most one relevant resource, recompute its return and link it to revision.",
        ),
        "belief_revision": (
            "revision",
            "Beliefs do not follow the verified evidence and committed contingency.",
            "Preserve hypothesis identities and apply the matching precommitted update.",
        ),
        "bounded_decision_and_claims": (
            "decision",
            "The action or claim exceeds the evidence actually established.",
            "Use the disclosed action invariant and narrow claims to verified evidence.",
        ),
    }
    stage, consequence, remedy = metadata[identifier]
    return OpenRequirement(
        identifier,
        stage,
        "mission_critical_science",
        passed,
        observed,
        {"public_contract": identifier, "dependencies": PROPERTY_DEPENDENCIES[identifier]},
        consequence,
        remedy,
        (),
    )


def evaluate_case2_submission(
    workspace: Path,
    submission: Any,
    *,
    require_host_process: bool = True,
) -> OpenGrade:
    """Evaluate one Case 2 mission; malformed agent artifacts never crash the grader."""

    workspace = workspace.resolve()
    submission = submission if isinstance(submission, dict) else {}
    raw_state = submission.get("state")
    state = raw_state if isinstance(raw_state, dict) else {}
    validation = submission.get("validation_plan") or {}
    followup = submission.get("followup_plan") or {}
    final = submission.get("final_submission") or {}
    schema = (
        validate_validation_plan(validation),
        validate_followup_plan(followup),
        validate_final_submission(final),
    )
    schema_valid = all(row.valid for row in schema)
    if not schema_valid:
        return OpenGrade(
            False,
            0.0,
            100.0 if state.get("completion_accepted") else 0.0,
            ("schema_contract",),
            None,
            (
                OpenRequirement(
                    "schema_contract",
                    "interface",
                    "contract",
                    False,
                    [[issue.to_dict() for issue in row.issues] for row in schema],
                    "public Case 2 submission contract",
                    "The record cannot be interpreted deterministically.",
                    "Use the visible validator and disclosed enum/field rules.",
                    (),
                ),
            ),
            {"semantic_engine": "case2-pilot-v1-rc1", "prose_scored": False},
            "contract_failure",
        )

    process_valid = False
    process_details: dict[str, Any] = {}
    cohort = CommittedCohort("", "", "", None, (), ("not_reconstructed",))
    artifacts: dict[str, tuple[dict[str, Any], Path]] = {}
    artifact_errors: list[str] = []
    tables: dict[str, VerifiedTable] = {}
    calculations: dict[str, CalculationResult] = {}
    plan_valid = False
    plan_details: dict[str, Any] = {}
    criteria: dict[str, bool] = {}
    criterion_details: dict[str, Any] = {}
    resource = ResourceFacts("", False, False, False, {}, None, None, False, False, False, ())
    decision_valid = belief_valid = False
    decision_details: dict[str, Any] = {}
    evaluation_errors = (
        ArithmeticError,
        AttributeError,
        csv.Error,
        json.JSONDecodeError,
        KeyError,
        OSError,
        StopIteration,
        TypeError,
        UnicodeError,
        ValueError,
        MemoryError,
        RecursionError,
    )
    if require_host_process:
        try:
            process_valid, process_details = _event_integrity(workspace, submission)
        except evaluation_errors as exc:
            process_details = {"process_record_error": type(exc).__name__}
    else:
        process_valid = True
        process_details = {"local_scientific_validation": True}
    try:
        cohort = reconstruct_committed_cohort(
            workspace,
            validation,
            host_input_hashes=_host_hashes(submission),
        )
    except evaluation_errors as exc:
        process_details["cohort_error"] = type(exc).__name__
    try:
        plan_valid, plan_details = _prospective_plan_implemented(
            workspace, submission, validation, final
        )
    except evaluation_errors as exc:
        plan_details = {"plan_error": type(exc).__name__}
    try:
        artifacts, artifact_errors = _artifact_index(workspace, final)
    except evaluation_errors as exc:
        artifact_errors = [f"artifact_index_error:{type(exc).__name__}"]
    try:
        tables = verified_case2_tables(
            workspace, artifacts, cohort, str(followup.get("chosen_resource") or "")
        )
    except evaluation_errors as exc:
        artifact_errors.append(f"table_verification_error:{type(exc).__name__}")
    try:
        normalized_final = copy.deepcopy(final)
        for calculation in normalized_final.get("calculations") or []:
            if not isinstance(calculation, dict):
                continue
            uncertainty = calculation.get("uncertainty")
            if (
                isinstance(uncertainty, dict)
                and uncertainty.get("method") == "ENTITY_BOOTSTRAP_PERCENTILE"
            ):
                uncertainty["method"] = "CLUSTER_BOOTSTRAP_PERCENTILE"
        calculations = verify_typed_calculations(normalized_final, artifacts, tables)
    except evaluation_errors as exc:
        artifact_errors.append(f"calculation_verification_error:{type(exc).__name__}")
    try:
        criteria, criterion_details = _criterion_results(
            validation, final, calculations, tables, artifacts
        )
    except evaluation_errors as exc:
        criterion_details = {"criterion_error": type(exc).__name__}
    try:
        resource = evaluate_resource(workspace, submission, calculations, criteria, tables)
    except evaluation_errors as exc:
        resource = ResourceFacts(
            str(followup.get("chosen_resource") or ""),
            False,
            False,
            False,
            {},
            None,
            None,
            False,
            False,
            False,
            (f"resource_evaluation_error:{type(exc).__name__}",),
        )
    try:
        belief_valid = not belief_revision_errors(
            validation, followup, final, resource.expected_effect
        )
    except evaluation_errors as exc:
        process_details["belief_error"] = type(exc).__name__
    try:
        decision_valid, decision_details = _decision_valid(
            workspace, submission, criteria, criterion_details, calculations, resource
        )
    except evaluation_errors as exc:
        decision_details = {"decision_error": type(exc).__name__}

    property_status = _primary_property_status(validation, criterion_details)
    primary_manifest = [
        row
        for row in final.get("artifact_manifest") or []
        if isinstance(row, dict)
        and row.get("role") == "ANALYSIS_TABLE"
        and not any(str(path).startswith("purchased/") for path in row.get("source_paths") or [])
        and row.get("identity_basis") in PREPURCHASE_IDENTITY_BASES
    ]
    primary_tables = {row.get("artifact_id") for row in primary_manifest} & set(tables)
    plan_identity = (validation.get("prospective_specification") or {}).get("identity_basis")
    entity_valid = bool(
        cohort.valid
        and primary_tables
        and _identity_declaration_valid(workspace)
        and any(row.get("identity_basis") == plan_identity for row in primary_manifest)
    )
    decision_calculation_ids = {
        str(row.get("calculation_id") or "")
        for row in validation.get("decision_criteria") or []
        if isinstance(row, dict)
    } | {
        str(item) for item in (final.get("resource_assessment") or {}).get("calculation_ids") or []
    }
    required_calculations = {
        identifier: calculations.get(identifier) for identifier in decision_calculation_ids
    }
    required_artifact_ids = {
        str(row.get(field) or "")
        for row in final.get("calculations") or []
        if isinstance(row, dict) and row.get("calculation_id") in decision_calculation_ids
        for field in ("source_analysis_table_id", "output_artifact_id")
    }
    required_artifact_errors = [
        error
        for error in artifact_errors
        if any(error.endswith(f":{identifier}") for identifier in required_artifact_ids)
    ]
    saved_chain = bool(
        decision_calculation_ids
        and not required_artifact_errors
        and all(result is not None and result.valid for result in required_calculations.values())
    )
    status = {
        "prospective_design_and_integrity": bool(process_valid and plan_valid and cohort.valid),
        "saved_artifact_chain": saved_chain,
        "committed_entity_and_dependence_analysis": entity_valid,
        "discrimination_and_uncertainty": bool(property_status.get("DISCRIMINATION")),
        "probability_and_calibration": bool(
            property_status.get("PROBABILITY_ACCURACY") and property_status.get("CALIBRATION")
        ),
        "threshold_utility": bool(property_status.get("THRESHOLD_UTILITY")),
        "context_robustness": bool(property_status.get("CONTEXT_ROBUSTNESS")),
        "decision_relevant_followup": resource.property_pass,
        "belief_revision": belief_valid,
        "bounded_decision_and_claims": decision_valid,
    }
    observed = {
        "prospective_design_and_integrity": {
            "event_integrity": process_details,
            "plan_implemented": plan_details,
            "committed_cohort": cohort.details(),
        },
        "saved_artifact_chain": {
            "artifact_errors": artifact_errors,
            "verified_artifacts": sorted(artifacts),
            "calculation_faults": {
                key: list(row.faults) for key, row in calculations.items() if row.faults
            },
        },
        "committed_entity_and_dependence_analysis": {
            "identity_state": identity_state(workspace),
            "plan_identity_basis": plan_identity,
            "verified_primary_tables": sorted(primary_tables),
        },
        "discrimination_and_uncertainty": criterion_details,
        "probability_and_calibration": criterion_details,
        "threshold_utility": criterion_details,
        "context_robustness": criterion_details,
        "decision_relevant_followup": resource.to_dict(),
        "belief_revision": {
            "passed": belief_valid,
            "observed_effect": resource.expected_effect,
        },
        "bounded_decision_and_claims": decision_details,
    }
    requirements = tuple(
        _requirement(identifier, bool(status[identifier]), observed[identifier])
        for identifier in WEIGHTS
    )
    failures = tuple(identifier for identifier in WEIGHTS if not status[identifier])
    points = {
        identifier: float(WEIGHTS[identifier]) * float(status[identifier]) for identifier in WEIGHTS
    }
    first = None
    if failures:
        row = next(item for item in requirements if item.requirement_id == failures[0])
        affected = {row.requirement_id}
        changed = True
        while changed:
            before = len(affected)
            affected.update(
                identifier
                for identifier, dependencies in PROPERTY_DEPENDENCIES.items()
                if not status[identifier] and any(item in affected for item in dependencies)
            )
            changed = len(affected) != before
        downstream = [
            identifier
            for identifier in WEIGHTS
            if identifier != row.requirement_id and identifier in affected
        ]
        first = {
            "stage": row.stage,
            "requirement_id": row.requirement_id,
            "consequence": row.consequence,
            "remedy": row.remedy,
            "downstream_dependencies": downstream,
            "failure_class": "scientific",
        }
    complete = not failures
    return OpenGrade(
        complete,
        round(sum(points.values()), 6),
        100.0 if state.get("completion_accepted") else 0.0,
        failures,
        first,
        requirements,
        {
            "semantic_engine": "case2-pilot-v1-rc1",
            "schema_version": SCHEMA_VERSION,
            "prose_scored": False,
            "property_points": points,
            "property_dependencies": PROPERTY_DEPENDENCIES,
            "criteria": criterion_details,
            "resource": resource.to_dict(),
            "public_hidden_semantic_object": True,
        },
        "none" if complete else "scientific_failure",
    )


__all__ = [
    "PROPERTY_DEPENDENCIES",
    "ResourceFacts",
    "WEIGHTS",
    "evaluate_case2_submission",
    "evaluate_resource",
    "identity_state",
    "verified_case2_tables",
]

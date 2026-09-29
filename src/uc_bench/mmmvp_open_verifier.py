"""Private, evidence-driven verifier for the open-ended MMMVP successor."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from statistics import mean
from typing import Any

from uc_bench.mmmvp_open_calculations import (
    CalculationResult,
    VerifiedTable,
    verified_tables,
    verify_typed_calculations,
)
from uc_bench.mmmvp_open_interventions import verify_x31_resource
from uc_bench.mmmvp_open_schema import (
    validate_final_submission,
    validate_followup_plan,
    validate_validation_plan,
)

VALIDITY_CARDS = Path("grader_private/mmmvp_open_rc1/validity_cards.json")

SCORE_SOURCE_TABLE: tuple[dict[str, Any], ...] = (
    {
        "requirement_id": "schema_contract",
        "authoritative_source": "disclosed structured objects",
        "verification": "mechanical type, enum, identifier and reference checks",
        "prose_can_affect_science": False,
    },
    {
        "requirement_id": "irreversible_action_integrity",
        "authoritative_source": "host event record and committed-object hashes",
        "verification": "order, uniqueness, purchase match, hashes and host records",
        "prose_can_affect_science": False,
    },
    {
        "requirement_id": "prospective_plan_implemented",
        "authoritative_source": "committed paths and final artifact manifest",
        "verification": "pre-reveal path visibility and preservation of planned outputs",
        "prose_can_affect_science": False,
    },
    {
        "requirement_id": "saved_artifact_chain",
        "authoritative_source": "artifact manifest and saved files",
        "verification": (
            "safe paths, source links, optional hashes and typed calculation-output linkage; "
            "code presence earns no credit"
        ),
        "prose_can_affect_science": False,
    },
    {
        "requirement_id": "relevant_entity_reconstruction",
        "authoritative_source": "raw records and source-linked analysis table",
        "verification": "independent entity, source-record, outcome and prediction reconstruction",
        "prose_can_affect_science": False,
    },
    {
        "requirement_id": "decision_relevant_quantitative_work",
        "authoritative_source": "raw data, verified analysis tables and calculation outputs",
        "verification": "independent recomputation with conditionally relevant alternatives",
        "prose_can_affect_science": False,
    },
    {
        "requirement_id": "invalid_evidence_contained",
        "authoritative_source": "raw fit membership and eligibility boolean",
        "verification": "independent fit-scope reconstruction and machine eligibility state",
        "prose_can_affect_science": False,
    },
    {
        "requirement_id": "decision_relevant_followup",
        "authoritative_source": (
            "evidence-target enum, resource ID and private admissible policy set"
        ),
        "verification": "declared target-resource pair is nondominated for the evidence state",
        "prose_can_affect_science": False,
    },
    {
        "requirement_id": "purchased_evidence_analyzed",
        "authoritative_source": "event record and artifact/evidence paths",
        "verification": "committed purchase appears in the final evidence chain",
        "prose_can_affect_science": False,
    },
    {
        "requirement_id": "belief_commitment_and_revision",
        "authoritative_source": (
            "hypothesis IDs, numeric beliefs, contingency directions and next-decision enums"
        ),
        "verification": (
            "committed baselines, numeric direction and the matched precommitted action"
        ),
        "prose_can_affect_science": False,
    },
    {
        "requirement_id": "evidence_supported_decision",
        "authoritative_source": "development-stage, disposition and use-scope enums",
        "verification": "membership in the private evidence-supported policy set",
        "prose_can_affect_science": False,
    },
    {
        "requirement_id": "bounded_claims",
        "authoritative_source": "claim status/scope and calculation references",
        "verification": "supported machine scope does not exceed independently verified evidence",
        "prose_can_affect_science": False,
    },
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


def _card(project_root: Path, condition_id: str) -> dict[str, Any]:
    value = json.loads((project_root / VALIDITY_CARDS).read_text(encoding="utf-8"))
    matches = [row for row in value["conditions"] if row["condition_id"] == condition_id]
    if len(matches) != 1:
        raise ValueError("Unknown or duplicate private validity card")
    return dict(matches[0])


def _safe_file(workspace: Path, relative: Any) -> Path | None:
    if not isinstance(relative, str) or not relative:
        return None
    posix = PurePosixPath(relative)
    if posix.is_absolute() or ".." in posix.parts:
        return None
    path = (workspace / Path(*posix.parts)).resolve()
    if path != workspace and workspace not in path.parents:
        return None
    return path if path.is_file() else None


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _protected_workspace_hashes(workspace: Path) -> dict[str, str]:
    """Hash every immutable evidence file visible to the agent."""

    return {
        path.relative_to(workspace).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(workspace.rglob("*"))
        if path.is_file() and "work" not in path.relative_to(workspace).parts
    }


def _event_index(events: list[dict[str, Any]], name: str) -> int | None:
    for index, row in enumerate(events):
        if row.get("event") == name:
            return index
    return None


def _event_integrity(
    workspace: Path,
    submission: dict[str, Any],
) -> tuple[bool, dict[str, Any]]:
    events = submission.get("event_log") or []
    names = (
        "commit_validation_plan",
        "reveal_validation",
        "commit_followup_plan",
        "purchase_resource",
        "submit",
    )
    positions = {name: _event_index(events, name) for name in names}
    present = all(value is not None for value in positions.values())
    ordered = present and [positions[name] for name in names] == sorted(
        positions[name] for name in names
    )
    unique = all(sum(row.get("event") == name for row in events) == 1 for name in names)
    followup = submission.get("followup_plan") or {}
    purchases = [row for row in events if row.get("event") == "purchase_resource"]
    matching = bool(
        len(purchases) == 1 and purchases[0].get("resource_id") == followup.get("chosen_resource")
    )
    validation = submission.get("validation_plan") or {}
    final = submission.get("final_submission") or {}
    state = submission.get("state") or {}
    validation_hash = hashlib.sha256(
        json.dumps(validation, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    followup_hash = hashlib.sha256(
        json.dumps(followup, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    final_hash = hashlib.sha256(
        json.dumps(final, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    commitment_rows = [row for row in events if row.get("event") == "commit_validation_plan"]
    reveal_rows = [row for row in events if row.get("event") == "reveal_validation"]
    followup_rows = [row for row in events if row.get("event") == "commit_followup_plan"]
    submit_rows = [row for row in events if row.get("event") == "submit"]
    hashes_match = bool(
        len(commitment_rows) == 1
        and commitment_rows[0].get("digest") == validation_hash
        and len(reveal_rows) == 1
        and reveal_rows[0].get("committed_plan_hash") == validation_hash
        and len(followup_rows) == 1
        and followup_rows[0].get("digest") == followup_hash
        and len(submit_rows) == 1
        and submit_rows[0].get("validation_plan_hash") == validation_hash
        and submit_rows[0].get("followup_plan_hash") == followup_hash
        and submit_rows[0].get("final_submission_hash") == final_hash
        and state.get("validation_plan_hash") == validation_hash
        and state.get("followup_plan_hash") == followup_hash
        and state.get("final_submission_hash") == final_hash
        and isinstance(final, dict)
    )
    records_match = False
    try:
        expected_locator = workspace.parent / ".mmmvp_host_records" / workspace.name
        declared_locator = submission.get("host_record_locator")
        records = expected_locator.resolve()
        if declared_locator != records.as_posix():
            raise OSError("Host record locator mismatch")
        records_match = all(
            json.loads((records / filename).read_text(encoding="utf-8")) == expected
            for filename, expected in (
                ("validation_plan.json", validation),
                ("followup_plan.json", followup),
                ("final_submission.json", final),
            )
        )
        records_match = records_match and json.loads(
            (records / "validation_input_hashes.json").read_text(encoding="utf-8")
        ) == submission.get("validation_input_hashes")
    except (OSError, json.JSONDecodeError):
        records_match = False
    protected_hashes_match = submission.get(
        "protected_evidence_hashes"
    ) == _protected_workspace_hashes(workspace)
    return bool(
        ordered
        and unique
        and matching
        and hashes_match
        and records_match
        and protected_hashes_match
    ), {
        "positions": positions,
        "unique": unique,
        "purchase_matches_commitment": matching,
        "commitment_hashes_match": hashes_match,
        "host_records_match": records_match,
        "protected_evidence_hashes_match": protected_hashes_match,
    }


def _prospective_plan_implemented(
    workspace: Path,
    submission: dict[str, Any],
    validation: dict[str, Any],
    final: dict[str, Any],
) -> tuple[bool, dict[str, Any]]:
    """Check the agent's own plan mechanically, without interpreting its prose."""

    manifested = {
        row.get("path")
        for row in final.get("artifact_manifest") or []
        if isinstance(row.get("path"), str)
    }
    analysis_rows: list[dict[str, Any]] = []
    committed_hashes = submission.get("validation_input_hashes") or {}

    def preserved(relative_path: Any) -> bool:
        path = _safe_file(workspace, relative_path)
        expected = committed_hashes.get(relative_path)
        return bool(
            path is not None
            and isinstance(expected, str)
            and hashlib.sha256(path.read_bytes()).hexdigest() == expected
        )

    for analysis in validation.get("planned_analyses") or []:
        inputs = analysis.get("input_paths") or []
        outputs = analysis.get("planned_output_paths") or []
        inputs_visible_before_reveal = bool(inputs) and all(preserved(path) for path in inputs)
        outputs_safe = bool(outputs) and all(str(path).startswith("work/") for path in outputs)
        output_preserved = bool(outputs) and all(path in manifested for path in outputs)
        analysis_rows.append(
            {
                "analysis_id": analysis.get("analysis_id"),
                "inputs_visible_before_reveal": inputs_visible_before_reveal,
                "outputs_safe": outputs_safe,
                "planned_output_preserved": output_preserved,
            }
        )
    evidence_refs = validation.get("evidence_refs") or []
    evidence_visible = bool(evidence_refs) and all(preserved(path) for path in evidence_refs)
    passed = (
        bool(analysis_rows)
        and evidence_visible
        and all(
            row["inputs_visible_before_reveal"]
            and row["outputs_safe"]
            and row["planned_output_preserved"]
            for row in analysis_rows
        )
    )
    return passed, {"analyses": analysis_rows, "evidence_visible_before_reveal": evidence_visible}


def _artifact_index(
    workspace: Path,
    final: dict[str, Any],
) -> tuple[dict[str, tuple[dict[str, Any], Path]], list[str]]:
    result: dict[str, tuple[dict[str, Any], Path]] = {}
    errors: list[str] = []
    for row in final.get("artifact_manifest") or []:
        artifact_id = row.get("artifact_id")
        path = _safe_file(workspace, row.get("path"))
        if not isinstance(artifact_id, str) or path is None:
            errors.append(f"missing_or_unsafe:{artifact_id}")
            continue
        declared = row.get("sha256")
        observed = hashlib.sha256(path.read_bytes()).hexdigest()
        if declared is not None and declared != observed:
            errors.append(f"hash_mismatch:{artifact_id}")
            continue
        sources = row.get("source_paths") or []
        if any(_safe_file(workspace, source) is None for source in sources):
            errors.append(f"missing_source:{artifact_id}")
            continue
        result[artifact_id] = (row, path)
    return result, errors


def _calculation_summary(results: dict[str, CalculationResult]) -> dict[str, Any]:
    return {calculation_id: result.to_dict() for calculation_id, result in results.items()}


def _has_valid(
    results: dict[str, CalculationResult],
    metric: str,
    *,
    roles: set[str],
    estimators: set[str] | None = None,
    require_uncertainty: bool = False,
) -> bool:
    return any(
        row.valid
        and row.metric == metric
        and row.role in roles
        and (estimators is None or row.estimator in estimators)
        and (not require_uncertainty or (row.uncertainty_claimed and row.uncertainty_valid))
        for row in results.values()
    )


def _contamination_assessment(
    workspace: Path,
    final: dict[str, Any],
) -> tuple[bool, bool]:
    rows = _read_csv(workspace / "pipeline/fit_membership.csv")
    contaminated = any(
        row.get("cohort_role", "").lower() == "validation"
        and row.get("included_in_reference_fit", "").lower() in {"true", "1", "yes"}
        for row in rows
    )
    relevant = [
        row
        for row in final.get("evidence_assessments") or []
        if "pipeline/fit_membership.csv" in set(row.get("source_paths") or [])
    ]
    contained = bool(relevant) and all(
        row.get("eligible_for_decision") is (not contaminated) for row in relevant
    )
    return contaminated, contained


def _resource_policy(card: dict[str, Any], followup: dict[str, Any]) -> bool:
    selected = followup.get("chosen_resource")
    target = followup.get("evidence_target")
    current = followup.get("current_decision") or {}
    return any(
        row["evidence_target"] == target
        and selected in set(row["resource_ids"])
        and current.get("disposition") in set(row["current_dispositions"])
        and current.get("use_scope") in set(row["current_use_scopes"])
        for row in card["investigation_policies"]
    )


def _followup_evidence_used(
    final: dict[str, Any],
    resource_id: str,
    tables: dict[str, VerifiedTable],
    calculations: dict[str, CalculationResult],
) -> bool:
    if resource_id == "none":
        return True
    prefix = f"purchased/{resource_id}/"
    derived: dict[str, str] = {}
    for row in final.get("artifact_manifest") or []:
        path = row.get("path")
        if (
            isinstance(path, str)
            and path.startswith("work/")
            and any(str(source).startswith(prefix) for source in row.get("source_paths") or [])
        ):
            derived[str(row.get("artifact_id"))] = path
    if not derived:
        return False
    referenced_ids = {
        result.table_id
        for result in calculations.values()
        if result.valid and result.table_id in tables
    }
    paths: list[str] = []
    paths.extend(final.get("evidence_refs") or [])
    for row in final.get("artifact_manifest") or []:
        paths.extend(row.get("source_paths") or [])
    for row in final.get("findings") or []:
        paths.extend(row.get("evidence_refs") or [])
    for row in final.get("claims") or []:
        paths.extend(row.get("evidence_refs") or [])
    return bool(set(derived).intersection(referenced_ids)) or any(
        path in set(derived.values()) for path in paths
    )


def _intervention_integrity(
    project_root: Path,
    workspace: Path,
    condition_id: str,
    resource_id: str,
    tables: dict[str, VerifiedTable],
    calculations: dict[str, CalculationResult],
) -> tuple[bool, dict[str, Any]]:
    if resource_id == "X31" and condition_id.startswith("case_03"):
        mechanism = condition_id.removeprefix("case_03_")
        with tempfile.TemporaryDirectory(prefix="uc-x31-rerun-") as directory:
            scratch = Path(directory) / "return"
            passed = verify_x31_resource(
                project_root,
                mechanism,
                workspace / "purchased/X31",
                scratch,
            )
        return passed, {"resource": resource_id, "deterministic_rerun_matches": passed}
    if resource_id == "X17" and condition_id == "case_02":
        public_entities = {
            row["fingerprint_cluster"]
            for row in _read_csv(workspace / "data/cohort_metadata.csv")
            if str(row.get("baseline_eligible", "")).lower() == "true"
        }
        crosswalk_path = workspace / "purchased/X17/canonical_person_crosswalk.csv"
        provenance_path = workspace / "purchased/X17/adjudication_provenance.json"
        if not crosswalk_path.is_file() or not provenance_path.is_file():
            return False, {"resource": resource_id, "reason": "adjudication_package_missing"}
        crosswalk = _read_csv(crosswalk_path)
        canonical_entities = {row.get("canonical_person_id") for row in crosswalk}
        p17 = {
            row.get("canonical_person_id")
            for row in crosswalk
            if row.get("reported_patient_id") == "P0017"
        }
        purchased_tables = {
            table_id
            for table_id, table in tables.items()
            if table.evidence_source == "PURCHASED"
            and any(path.startswith("purchased/X17/") for path in table.source_paths)
        }
        calculation_used = any(
            result.valid and result.table_id in purchased_tables for result in calculations.values()
        )
        passed = bool(
            len(public_entities) == 96
            and len(canonical_entities) == 95
            and p17 == {"P0017"}
            and calculation_used
        )
        return passed, {
            "resource": resource_id,
            "public_fingerprint_entities": len(public_entities),
            "adjudicated_canonical_entities": len(canonical_entities),
            "p0017_canonical_ids": sorted(p17),
            "purchased_table_calculation_used": calculation_used,
        }
    return True, {"resource": resource_id, "special_integrity_check": "not_required"}


def _decision_criteria_consistent(
    validation: dict[str, Any],
    final: dict[str, Any],
    calculations: dict[str, CalculationResult],
) -> tuple[bool, dict[str, Any]]:
    evaluations: list[dict[str, Any]] = []
    for criterion in validation.get("decision_criteria") or []:
        result = calculations.get(str(criterion.get("calculation_id")))
        passed = False
        if result is not None and result.valid and result.metric == criterion.get("metric"):
            threshold = float(criterion["threshold"])
            value = float(result.recomputed_value)
            passed = (
                value >= threshold
                if criterion.get("comparator") == "AT_LEAST"
                else value <= threshold
            )
        evaluations.append(
            {
                "criterion_id": criterion.get("criterion_id"),
                "calculation_id": criterion.get("calculation_id"),
                "metric": criterion.get("metric"),
                "passed": passed,
            }
        )
    if not evaluations:
        return False, {"criteria": []}
    disposition = (final.get("decision") or {}).get("disposition")
    if disposition == "CONTINUE":
        consistent = all(row["passed"] for row in evaluations)
    else:
        consistent = any(not row["passed"] for row in evaluations)
    return consistent, {"criteria": evaluations, "final_disposition": disposition}


def _belief_consistency(
    validation: dict[str, Any],
    followup: dict[str, Any],
    final: dict[str, Any],
) -> bool:
    committed = {row["hypothesis_id"]: float(row["belief"]) for row in validation["hypotheses"]}
    effects = {
        row["hypothesis_id"]: row.get("decision_effect_if_true") for row in validation["hypotheses"]
    }
    if followup.get("beliefs_before") != committed:
        return False
    contingencies = {
        row["contingency_id"]: row for row in followup.get("result_contingencies") or []
    }
    updates = final.get("belief_updates") or []
    update_ids = [row.get("hypothesis_id") for row in updates]
    if len(update_ids) != len(set(update_ids)) or set(update_ids) != set(committed):
        return False
    observed_directions: dict[str, str] = {}
    for update in updates:
        hypothesis_id = update.get("hypothesis_id")
        if hypothesis_id not in committed or not math.isclose(
            float(update["before"]), committed[hypothesis_id], abs_tol=1e-12
        ):
            return False
        contingency = contingencies.get(update.get("matched_contingency_id"))
        if contingency is None:
            return False
        directions = {
            row["hypothesis_id"]: row["direction"]
            for row in contingency.get("hypothesis_updates") or []
        }
        expected = directions.get(hypothesis_id)
        delta = float(update["after"]) - float(update["before"])
        observed = "INCREASE" if delta > 0 else ("DECREASE" if delta < 0 else "UNCHANGED")
        observed_directions[hypothesis_id] = observed
        if expected != observed:
            return False
    matched_ids = {row.get("matched_contingency_id") for row in final.get("belief_updates") or []}
    if len(matched_ids) != 1:
        return False
    matched = contingencies.get(next(iter(matched_ids)))
    if matched is None:
        return False
    final_decision = final.get("decision") or {}
    next_decision = matched.get("next_decision") or {}
    for field in ("development_stage", "disposition", "use_scope"):
        if final_decision.get(field) != next_decision.get(field):
            return False
    if followup.get("chosen_resource") == "none":
        return all(float(row["after"]) == float(row["before"]) for row in updates)
    advancing = final_decision.get("disposition") == "CONTINUE"
    for hypothesis_id, direction in observed_directions.items():
        effect = effects.get(hypothesis_id)
        if effect == "NONE" and direction != "UNCHANGED":
            return False
        if effect == "SUPPORTS":
            expected_direction = "INCREASE" if advancing else "DECREASE"
            if direction != expected_direction:
                return False
        if effect in {"WEAKENS", "INVALIDATES"}:
            expected_direction = "DECREASE" if advancing else "INCREASE"
            if direction != expected_direction:
                return False
    return True


def _claims_supported(
    card: dict[str, Any],
    workspace: Path,
    final: dict[str, Any],
    calculations: dict[str, CalculationResult],
) -> bool:
    unsupported = set(card["unsupported_claim_scopes"])
    claims = final.get("claims") or []
    calculation_ids = {row.get("calculation_id") for row in final.get("calculations") or []}
    for row in claims:
        if row.get("status") != "SUPPORTED":
            continue
        evidence_refs = row.get("evidence_refs") or []
        calculation_refs = row.get("calculation_ids") or []
        if (
            not evidence_refs
            or not calculation_refs
            or any(_safe_file(workspace, path) is None for path in evidence_refs)
            or not set(calculation_refs) <= calculation_ids
            or any(
                reference not in calculations or not calculations[reference].valid
                for reference in calculation_refs
            )
        ):
            return False
    if any(row.get("scope") in unsupported and row.get("status") == "SUPPORTED" for row in claims):
        return False
    use_scope = final["decision"]["use_scope"]
    required_supported = {
        "RESEARCH_RANKING": "PROGNOSTIC_RANKING",
        "RESEARCH_PROBABILITY": "PROGNOSTIC_PROBABILITY",
        "CLINICAL_DECISION_SUPPORT": "CLINICAL_UTILITY",
        "TREATMENT_SELECTION": "TREATMENT_EFFECT",
    }.get(use_scope)
    return required_supported is None or any(
        row.get("scope") == required_supported and row.get("status") == "SUPPORTED"
        for row in claims
    )


def verify_open_submission(
    project_root: Path,
    workspace: Path,
    submission: dict[str, Any],
    *,
    condition_id: str,
) -> OpenGrade:
    """Grade evidence properties and policies without reading scientific prose."""

    root = project_root.resolve()
    workspace = workspace.resolve()
    card = _card(root, condition_id)
    validation = submission.get("validation_plan") or {}
    followup = submission.get("followup_plan") or {}
    final = submission.get("final_submission") or {}
    schema_results = (
        validate_validation_plan(validation),
        validate_followup_plan(followup),
        validate_final_submission(final),
    )
    schema_valid = all(result.valid for result in schema_results)
    events_valid, event_details = _event_integrity(workspace, submission)
    artifacts, artifact_errors = _artifact_index(workspace, final) if schema_valid else ({}, [])
    resource_id = str(followup.get("chosen_resource"))
    tables = verified_tables(workspace, artifacts, resource_id) if artifacts else {}
    calculations = (
        verify_typed_calculations(final, artifacts, tables) if schema_valid and artifacts else {}
    )
    calculation_summary = _calculation_summary(calculations)
    primary_tables = [
        table for table in tables.values() if table.evidence_source == "SUPPLIED_AND_REVEALED"
    ]
    followup_tables = [table for table in tables.values() if table.evidence_source == "PURCHASED"]
    contaminated, contamination_contained = (
        _contamination_assessment(workspace, final) if schema_valid else (False, False)
    )
    decision = final.get("decision") or {}
    stage_valid = decision.get("development_stage") in set(card["defensible_development_stages"])
    disposition_valid = decision.get("disposition") in set(card["defensible_final_dispositions"])
    use_scope_valid = decision.get("use_scope") in set(card["defensible_use_scopes"])
    resource_valid = _resource_policy(card, followup) if schema_valid else False
    followup_used = (
        _followup_evidence_used(final, resource_id, tables, calculations) if schema_valid else False
    )
    intervention_valid, intervention_details = (
        _intervention_integrity(
            root,
            workspace,
            condition_id,
            resource_id,
            tables,
            calculations,
        )
        if schema_valid
        else (False, {})
    )
    belief_valid = _belief_consistency(validation, followup, final) if schema_valid else False
    claims_valid = (
        _claims_supported(card, workspace, final, calculations) if schema_valid else False
    )
    criteria_valid, criteria_details = (
        _decision_criteria_consistent(validation, final, calculations)
        if schema_valid
        else (False, {})
    )
    plan_implemented, plan_details = (
        _prospective_plan_implemented(workspace, submission, validation, final)
        if schema_valid
        else (False, {})
    )

    requirements: list[OpenRequirement] = []

    def add(
        requirement_id: str,
        stage: str,
        passed: bool,
        observed: Any,
        expected: Any,
        consequence: str,
        remedy: str,
        *,
        requirement_class: str = "mission_critical_science",
        evidence: tuple[str, ...] = (),
    ) -> None:
        requirements.append(
            OpenRequirement(
                requirement_id,
                stage,
                requirement_class,
                bool(passed),
                observed,
                expected,
                consequence,
                remedy,
                evidence,
            )
        )

    add(
        "schema_contract",
        "interface",
        schema_valid,
        [[issue.to_dict() for issue in result.issues] for result in schema_results],
        "disclosed generic schema",
        "The structured record cannot be evaluated reliably.",
        "Correct the disclosed machine contract without changing scientific content.",
        requirement_class="contract",
    )
    add(
        "irreversible_action_integrity",
        "process",
        events_valid,
        event_details,
        "commit, reveal, follow-up commitment, purchase, submit",
        "The analysis can be adapted after seeing protected evidence.",
        "Respect the disclosed irreversible action boundaries.",
    )
    add(
        "prospective_plan_implemented",
        "planning",
        plan_implemented,
        plan_details,
        "the agent's pre-reveal inputs and planned output paths are preserved in final artifacts",
        "The reported analysis is not the prospective analysis the agent committed to execute.",
        (
            "Execute and preserve a defensible precommitted analysis, or disclose a "
            "justified deviation."
        ),
    )
    add(
        "saved_artifact_chain",
        "analysis",
        bool(artifacts)
        and not artifact_errors
        and any(result.valid for result in calculations.values()),
        {
            "artifact_count": len(artifacts),
            "errors": artifact_errors,
            "typed_calculations": calculation_summary,
        },
        "safe source-linked artifacts and independently reproduced typed calculations",
        "Reported results cannot be independently checked.",
        "Save source-linked tables and calculated outputs with typed calculation records.",
    )
    add(
        "relevant_entity_reconstruction",
        "analysis",
        bool(primary_tables),
        [row.artifact_id for row in primary_tables],
        "a valid entity-level or dependence-preserving analysis artifact",
        "The validation may count dependent source records as independent evidence.",
        "Reconstruct the decision-relevant entities or use a dependence-preserving model.",
    )

    if condition_id == "case_01":
        calculation_pass = all(
            (
                _has_valid(
                    calculations,
                    "ROC_AUC",
                    roles={"PRIMARY"},
                    estimators={"EMPIRICAL", "ENTITY_WEIGHTED"},
                    require_uncertainty=True,
                ),
                any(
                    _has_valid(calculations, metric, roles={"PRIMARY"})
                    for metric in {"BRIER_SCORE", "LOG_LOSS"}
                ),
                _has_valid(calculations, "CALIBRATION_ERROR", roles={"PRIMARY"}),
                _has_valid(calculations, "NET_BENEFIT", roles={"PRIMARY"}),
            )
        )
        expected_calculation = (
            "decision-supporting discrimination, uncertainty, probability accuracy and utility"
        )
    elif condition_id == "case_02":
        calculation_pass = all(
            (
                _has_valid(
                    calculations,
                    "ROC_AUC",
                    roles={"PRIMARY"},
                    estimators={"EMPIRICAL", "ENTITY_WEIGHTED"},
                    require_uncertainty=True,
                ),
                _has_valid(
                    calculations,
                    "SITE_WEIGHTED_ROC_AUC",
                    roles={"PRIMARY"},
                    estimators={"EMPIRICAL", "ENTITY_WEIGHTED"},
                ),
                _has_valid(
                    calculations,
                    "ROC_AUC",
                    roles={"DIAGNOSTIC"},
                    estimators={"ROW_EMPIRICAL"},
                ),
            )
        )
        expected_calculation = (
            "dependence-aware and context-aware comparison with the naive row result"
        )
    elif condition_id.startswith("case_03"):
        required_families = ["ROC_AUC"]
        if decision.get("use_scope") == "RESEARCH_PROBABILITY":
            required_families.extend(["BRIER_SCORE", "CALIBRATION_ERROR", "NET_BENEFIT"])
        calculation_pass = bool(followup_tables) and all(
            _has_valid(calculations, metric, roles={"FOLLOWUP"}) for metric in required_families
        )
        expected_calculation = {
            "source": "clean replay",
            "required_families_for_claimed_use": required_families,
        }
    else:
        calculation_pass = all(
            (
                _has_valid(calculations, "ROC_AUC", roles={"PRIMARY"}),
                any(
                    _has_valid(calculations, metric, roles={"PRIMARY"})
                    for metric in {"BRIER_SCORE", "LOG_LOSS"}
                ),
                _has_valid(calculations, "CALIBRATION_ERROR", roles={"PRIMARY"}),
                _has_valid(calculations, "NET_BENEFIT", roles={"PRIMARY"}),
            )
        )
        expected_calculation = (
            "evidence distinguishing ranking from probability and threshold utility"
        )
    add(
        "decision_relevant_quantitative_work",
        "analysis",
        calculation_pass,
        calculation_summary,
        expected_calculation,
        (
            "The final recommendation lacks the quantitative evidence needed for this "
            "intended-use claim."
        ),
        "Perform and preserve a valid calculation that addresses the claimed decision scope.",
    )

    if condition_id.startswith("case_03"):
        add(
            "invalid_evidence_contained",
            "analysis",
            contaminated and contamination_contained,
            {"contaminated": contaminated, "contained": contamination_contained},
            "fit membership identified and invalid primary evidence excluded",
            "Validation information can support a circular development decision.",
            "Reconstruct fit membership and exclude evidence affected by validation fitting.",
            evidence=("pipeline/fit_membership.csv",),
        )

    add(
        "decision_relevant_followup",
        "followup",
        resource_valid,
        {"target": followup.get("evidence_target"), "resource": resource_id},
        card["investigation_policies"],
        "Budget is spent on evidence that cannot resolve the declared decision state.",
        "Choose a nondominated resource for the immediate evidence target, or buy nothing.",
    )
    add(
        "purchased_evidence_analyzed",
        "followup",
        followup_used and intervention_valid,
        {"resource_id": resource_id, "intervention": intervention_details},
        "the purchased return is represented in a verified final calculation chain",
        "The resource action does not inform the final conclusion.",
        "Analyse and cite the returned evidence before updating the decision.",
    )
    add(
        "belief_commitment_and_revision",
        "revision",
        belief_valid,
        final.get("belief_updates"),
        "stable agent-defined hypotheses and precommitted result-contingent updates",
        "Belief is redefined or revised post hoc.",
        "Preserve hypothesis IDs and baselines, then follow the matching committed contingency.",
    )
    add(
        "evidence_supported_decision",
        "decision",
        stage_valid and disposition_valid and use_scope_valid and criteria_valid,
        {"decision": decision, "precommitted_criteria": criteria_details},
        {
            "development_stages": card["defensible_development_stages"],
            "dispositions": card["defensible_final_dispositions"],
            "use_scopes": card["defensible_use_scopes"],
        },
        "The recommended development action or permitted use exceeds or ignores the evidence.",
        "Choose the narrowest action and use scope supported by the verified evidence state.",
    )
    add(
        "bounded_claims",
        "decision",
        claims_valid,
        final.get("claims"),
        {"unsupported_scopes": card["unsupported_claim_scopes"]},
        "A final claim exceeds the completed evidence chain.",
        "Mark unsupported scopes accordingly and link supported claims to verified artifacts.",
    )

    scientific = [
        row for row in requirements if row.requirement_class == "mission_critical_science"
    ]
    failures = tuple(row.requirement_id for row in scientific if not row.passed)
    complete = not failures and schema_valid
    partial = round(100 * mean(float(row.passed) for row in scientific), 6)
    first = None
    if failures:
        row = next(item for item in scientific if not item.passed)
        first = {
            "stage": row.stage,
            "requirement_id": row.requirement_id,
            "consequence": row.consequence,
            "remedy": row.remedy,
            "evidence": list(row.evidence),
        }
    failure_class = (
        "none" if complete else ("contract_failure" if not schema_valid else "scientific_failure")
    )
    return OpenGrade(
        complete_mission_success=complete,
        partial_scientific_quality=partial,
        reliability_score=100.0 if submission.get("state", {}).get("completion_accepted") else 0.0,
        mission_failures=failures,
        first_decision_critical_failure=first,
        requirements=tuple(requirements),
        diagnostics={
            "condition_id": condition_id,
            "validity_card_loaded": True,
            "prose_scored": False,
            "primary_table_count": len(primary_tables),
            "followup_table_count": len(followup_tables),
            "typed_calculations": calculation_summary,
            "decision_criteria": criteria_details,
            "intervention_integrity": intervention_details,
            "contaminated": contaminated,
            "artifact_errors": artifact_errors,
        },
        failure_class=failure_class,
    )


__all__ = [
    "OpenGrade",
    "OpenRequirement",
    "SCORE_SOURCE_TABLE",
    "VALIDITY_CARDS",
    "verify_open_submission",
]

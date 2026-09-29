"""Isolated Case-1 RC1.7 environment with prospective cohort binding."""

from __future__ import annotations

import copy
import csv
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from uc_bench.mmmvp_open_environment import (
    OpenProtocolError,
    _digest_bytes,
    _json_digest,
)
from uc_bench.mmmvp_open_rc14_environment import RC14OpenMMMVPEnvironment
from uc_bench.mmmvp_open_rc17_contract import (
    METHOD_DEFINITIONS,
    PUBLIC_CONTRACT,
    SCHEMA_VERSION,
    validate_final_submission,
    validate_followup_plan,
    validate_validation_plan,
)
from uc_bench.v07_cases import PRIVATE_ROOT

_MISSION = """# Locked predictor diligence: Case 1

Decide what the supplied evidence supports for the stated intended use, whether a
follow-up purchase has value for one explicitly defined unresolved question, and
what bounded development action should follow.

The scientific work is open within the method families disclosed in
scientific_methods.json. Submission mechanics are documented separately in
submission_contract.json, field_guide.md and contract_templates/. Use
validate_contract.py locally before irreversible actions when useful.

Outcomes are sealed. Before reveal, commit the biological unit, dependence rule,
complete eligible-entity manifest and hash, estimators, important parameters,
uncertainty method, and non-vacuous decision criteria. The symbolic outcome role
SEALED_VALIDATION_OUTCOMES is bound by the environment after reveal; do not guess a
future filename.

Save every decision-driving table and calculation under work/. Do not infer
treatment effect, clinical utility, independent validation or transport unless the
evidence actually establishes it.
"""

_FIELD_GUIDE = """# Contract field guide

There are three structured records: validation plan, follow-up plan and final
submission. Start from the JSON templates in contract_templates/.

The validation plan uses a prospectively saved entity manifest with columns
entity_id, source_record_ids, included and preoutcome_exclusion_reason. List every
baseline-eligible person and every one of that person's eligible source records.
Separate source record IDs with `|`. `included` is true
or false. An excluded person remains in the manifest and needs a disclosed,
evidence-linked pre-outcome reason. Commit the manifest SHA-256.

Each of the five criterion properties is required exactly once. The public
non-vacuity floors in submission_contract.json only exclude chance, uninformative
or harmful criteria; you may choose stricter thresholds.

After reveal, every primary calculation's cohort.entity_ids must equal the
prospectively included entity set. Its analysis structure, aggregation, estimator,
metric family, uncertainty settings, calibration bins and utility threshold must
match the committed specification.

The follow-up decision_question_type maps publicly to one resource. This is a
technical mapping, not a preferred purchase. Choose the question that is genuinely
material to your decision, or CURRENT_DECISION_ALREADY_RESOLVED and `none`.
Precommit a quantitative materiality threshold where the resource permits a
comparison. For non-quantitative resources and `none`, use 0; the field remains
present to keep one stable schema.

After purchase, inspect purchased/<resource>/resource_manifest.json. Save
work/resource_summary.json using the common schema and resource-specific result
keys disclosed in submission_contract.json. The verifier independently recomputes
those results. The final resource assessment must point to this file and the
returned source paths.

Free text is required for auditability but never exact-matched and never supplies
scientific credit. Enums, identifiers, hashes, numbers, event timing and saved
artifacts are machine checked.

The packet asserts baseline eligibility and the week-6 clinical-response construct;
those source assertions cannot be independently audited from Case 1. Do not claim
population or label-provenance validity beyond the supplied packet. X24 can add
blinded endpoint adjudication when visible provenance makes that question material.
"""

_VALIDATOR = r'''#!/usr/bin/env python3
"""Local no-answer preflight; environment actions add evidence-integrity checks."""
import hashlib
import json
import math
import pathlib
import sys

VERSION = "mmmvp-open-case1-rc1-7"
QUESTION_RESOURCE = {
    "IDENTITY_LINKAGE": "X17",
    "ENDPOINT_VALIDITY": "X24",
    "PIPELINE_REPRODUCIBILITY": "X31",
    "CROSS_CONTEXT_TRANSPORT": "X46",
    "PRECISION_WITH_SAME_PROCESS": "X58",
    "EXPERT_INTERPRETATION": "X63",
    "CURRENT_DECISION_ALREADY_RESOLVED": "none",
}
EVIDENCE_TARGET = {
    "IDENTITY_LINKAGE": "RECORD_LINKAGE",
    "ENDPOINT_VALIDITY": "ENDPOINT_REVIEW",
    "PIPELINE_REPRODUCIBILITY": "PIPELINE_REPLAY",
    "CROSS_CONTEXT_TRANSPORT": "EXTERNAL_COHORT",
    "PRECISION_WITH_SAME_PROCESS": "ADDITIONAL_SAMPLE",
    "EXPERT_INTERPRETATION": "EXPERT_REVIEW",
    "CURRENT_DECISION_ALREADY_RESOLVED": "NO_NEW_EVIDENCE",
}
MINIMUM_MATERIALITY = {"X31": 0.02, "X46": 0.02, "X58": 0.02}
ENUMS = {
    "biological_unit": {"PERSON"},
    "dependence_handling": {
        "PERSON_LEVEL_AGGREGATION",
        "SOURCE_RECORD_CLUSTERING",
    },
    "aggregation": {"MEAN", "MEDIAN", "FIRST", "NONE"},
    "estimator": {"EMPIRICAL", "ENTITY_WEIGHTED"},
    "discrimination_metric": {"ROC_AUC", "BINARY_CONCORDANCE"},
    "probability_metric": {"BRIER_SCORE", "LOG_LOSS"},
    "calibration_metric": {"CALIBRATION_ERROR"},
    "utility_metric": {"NET_BENEFIT", "THRESHOLD_EXPECTED_UTILITY"},
    "context_metric": {"SITE_WEIGHTED_ROC_AUC", "WORST_SITE_ROC_AUC"},
    "outcome_role": {"SEALED_VALIDATION_OUTCOMES"},
    "uncertainty_method": {
        "ENTITY_BOOTSTRAP_PERCENTILE",
        "CLUSTER_BOOTSTRAP_PERCENTILE",
    },
}
REQUIRED = {
    "validation": {
        "schema_version",
        "decision_definition",
        "evidence_standard",
        "hypotheses",
        "planned_analyses",
        "decision_criteria",
        "evidence_refs",
        "prospective_specification",
    },
    "followup": {
        "schema_version",
        "decision_question_id",
        "decision_question",
        "chosen_resource",
        "evidence_target",
        "live_explanations",
        "alternatives_considered",
        "result_contingencies",
        "beliefs_before",
        "current_decision",
        "evidence_refs",
        "decision_question_type",
        "materiality_threshold",
    },
    "final": {
        "schema_version",
        "artifact_manifest",
        "calculations",
        "findings",
        "evidence_assessments",
        "belief_updates",
        "decision",
        "claims",
        "remaining_uncertainties",
        "evidence_refs",
        "resource_assessment",
        "narrative_summary",
    },
}
PROPERTIES = {
    "DISCRIMINATION",
    "PROBABILITY_ACCURACY",
    "CALIBRATION",
    "THRESHOLD_UTILITY",
    "CONTEXT_ROBUSTNESS",
}
MAPPING = {
    "DISCRIMINATION": {"ROC_AUC", "BINARY_CONCORDANCE"},
    "PROBABILITY_ACCURACY": {"BRIER_SCORE", "LOG_LOSS"},
    "CALIBRATION": {"CALIBRATION_ERROR"},
    "THRESHOLD_UTILITY": {"NET_BENEFIT", "THRESHOLD_EXPECTED_UTILITY"},
    "CONTEXT_ROBUSTNESS": {"SITE_WEIGHTED_ROC_AUC", "WORST_SITE_ROC_AUC"},
}
DECISION = {
    "development_stage",
    "disposition",
    "use_scope",
    "allowed_use",
    "prohibited_use",
    "unresolved_gates",
    "required_next_evidence",
}
DECISION_ENUMS = {
    "development_stage": {
        "DISCOVERY",
        "INTERNAL_VALIDATION",
        "EXTERNAL_VALIDATION",
        "PROSPECTIVE_EVALUATION",
        "STOPPED",
    },
    "disposition": {"CONTINUE", "PAUSE", "STOP", "INSUFFICIENT_EVIDENCE"},
    "use_scope": {
        "NO_USE",
        "RETROSPECTIVE_AUDIT",
        "RESEARCH_RANKING",
        "RESEARCH_PROBABILITY",
        "CLINICAL_DECISION_SUPPORT",
        "TREATMENT_SELECTION",
    },
}


def array(value, name, errors, minimum=0):
    if not isinstance(value, list) or len(value) < minimum:
        errors.append(f"{name} needs at least {minimum} item(s)")


def object_fields(value, fields, name, errors):
    if not isinstance(value, dict):
        errors.append(f"{name} must be an object")
        return
    for field in fields:
        if field not in value:
            errors.append(f"missing required field: {name}.{field}")


def validation(value, errors):
    array(value.get("hypotheses"), "hypotheses", errors, 1)
    array(value.get("planned_analyses"), "planned_analyses", errors, 1)
    array(value.get("evidence_refs"), "evidence_refs", errors, 1)
    rows = value.get("decision_criteria") or []
    array(rows, "decision_criteria", errors, 5)
    properties = [row.get("property") for row in rows if isinstance(row, dict)]
    if len(rows) != 5 or set(properties) != PROPERTIES:
        errors.append("decision_criteria must contain each property exactly once")
    for row in rows:
        if isinstance(row, dict) and row.get("metric") not in MAPPING.get(
            row.get("property"), set()
        ):
            errors.append(f"metric does not match property: {row.get('property')}")
        if not isinstance(row, dict):
            continue
        prop = row.get("property")
        threshold = row.get("threshold")
        comparator = row.get("comparator")
        finite = (
            isinstance(threshold, (int, float))
            and not isinstance(threshold, bool)
            and math.isfinite(threshold)
        )
        nonvacuous = finite and (
            prop == "DISCRIMINATION" and comparator == "AT_LEAST" and threshold >= 0.70
            or prop == "PROBABILITY_ACCURACY"
            and comparator == "AT_MOST"
            and (
                row.get("metric") == "BRIER_SCORE" and threshold <= 0.23
                or row.get("metric") == "LOG_LOSS" and threshold < math.log(2)
            )
            or prop == "CALIBRATION" and comparator == "AT_MOST" and threshold <= 0.12
            or prop == "THRESHOLD_UTILITY" and comparator == "AT_LEAST" and threshold > 0
            or prop == "CONTEXT_ROBUSTNESS" and comparator == "AT_LEAST" and threshold > 0.5
        )
        if not nonvacuous:
            errors.append(f"decision criterion is vacuous or mismatched: {prop}")
    spec = value.get("prospective_specification")
    object_fields(spec, set(ENUMS) | {
        "eligible_entity_manifest_path",
        "eligible_entity_manifest_sha256",
        "identity_provenance_path",
        "outcome_role",
        "calibration_bin_count",
        "utility_threshold",
        "uncertainty_replicates",
        "uncertainty_seed",
        "uncertainty_level",
        "exclusions",
    }, "prospective_specification", errors)
    if not isinstance(spec, dict):
        return
    for key, allowed in ENUMS.items():
        if spec.get(key) not in allowed:
            errors.append(
                f"prospective_specification.{key} must be one of {sorted(allowed)}"
            )
    if spec.get("dependence_handling") == "PERSON_LEVEL_AGGREGATION" and (
        spec.get("aggregation") not in {"MEAN", "MEDIAN", "FIRST"}
        or spec.get("estimator") != "EMPIRICAL"
        or spec.get("uncertainty_method") != "ENTITY_BOOTSTRAP_PERCENTILE"
    ):
        errors.append(
            "person-level aggregation requires MEAN/MEDIAN/FIRST, EMPIRICAL and "
            "ENTITY_BOOTSTRAP_PERCENTILE"
        )
    if spec.get("dependence_handling") == "SOURCE_RECORD_CLUSTERING" and (
        spec.get("aggregation") != "NONE"
        or spec.get("estimator") != "ENTITY_WEIGHTED"
        or spec.get("uncertainty_method") != "CLUSTER_BOOTSTRAP_PERCENTILE"
    ):
        errors.append(
            "source-record clustering requires NONE, ENTITY_WEIGHTED and "
            "CLUSTER_BOOTSTRAP_PERCENTILE"
        )
    if not isinstance(spec.get("calibration_bin_count"), int) or not 2 <= spec[
        "calibration_bin_count"
    ] <= 20:
        errors.append("calibration_bin_count must be an integer in [2,20]")
    if not isinstance(spec.get("uncertainty_replicates"), int) or not 100 <= spec[
        "uncertainty_replicates"
    ] <= 2000:
        errors.append("uncertainty_replicates must be an integer in [100,2000]")
    if not isinstance(spec.get("uncertainty_level"), (int, float)) or not 0.8 <= spec[
        "uncertainty_level"
    ] <= 0.99:
        errors.append("uncertainty_level must be in [0.8,0.99]")
    path = pathlib.Path(str(spec.get("eligible_entity_manifest_path", "")))
    digest = spec.get("eligible_entity_manifest_sha256")
    if not path.is_file():
        errors.append("eligible entity manifest does not exist yet")
    elif hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        errors.append("eligible entity manifest SHA-256 does not match")
    if digest == "0" * 64:
        errors.append("replace the template SHA-256 before commitment")


def followup(value, errors):
    array(value.get("live_explanations"), "live_explanations", errors, 2)
    array(value.get("alternatives_considered"), "alternatives_considered", errors, 2)
    array(value.get("result_contingencies"), "result_contingencies", errors, 2)
    array(value.get("evidence_refs"), "evidence_refs", errors, 1)
    question = value.get("decision_question_type")
    if question not in QUESTION_RESOURCE:
        errors.append("unknown decision_question_type")
    elif value.get("chosen_resource") != QUESTION_RESOURCE[question]:
        errors.append(f"chosen_resource must be {QUESTION_RESOURCE[question]} for {question}")
    elif value.get("evidence_target") != EVIDENCE_TARGET[question]:
        errors.append(f"evidence_target must be {EVIDENCE_TARGET[question]} for {question}")
    threshold = value.get("materiality_threshold")
    if (
        isinstance(threshold, bool)
        or not isinstance(threshold, (int, float))
        or not math.isfinite(threshold)
        or threshold < 0
    ):
        errors.append("materiality_threshold must be finite and non-negative")
    elif question in {
        "CURRENT_DECISION_ALREADY_RESOLVED",
        "IDENTITY_LINKAGE",
        "EXPERT_INTERPRETATION",
    } and threshold != 0:
        errors.append("materiality_threshold must be 0 for non-quantitative resources")
    elif question in QUESTION_RESOURCE:
        resource = QUESTION_RESOURCE[question]
        minimum = MINIMUM_MATERIALITY.get(resource)
        if minimum is not None and threshold < minimum:
            errors.append(f"{resource} requires materiality_threshold >= {minimum}")


def final(value, errors):
    for field, minimum in (
        ("artifact_manifest", 1),
        ("calculations", 1),
        ("findings", 1),
        ("evidence_assessments", 1),
        ("belief_updates", 1),
        ("claims", 1),
        ("evidence_refs", 1),
    ):
        array(value.get(field), field, errors, minimum)
    object_fields(value.get("decision"), DECISION, "decision", errors)
    decision = value.get("decision") or {}
    if isinstance(decision, dict):
        for key, allowed in DECISION_ENUMS.items():
            if decision.get(key) not in allowed:
                errors.append(f"decision.{key} must be one of {sorted(allowed)}")
    object_fields(value.get("resource_assessment"), {
        "resource_id",
        "question_type",
        "summary_artifact_path",
        "source_paths",
        "calculation_ids",
        "observed_effect",
        "material",
    }, "resource_assessment", errors)
    for index, row in enumerate(value.get("claims") or []):
        if (
            isinstance(row, dict)
            and row.get("status") == "SUPPORTED"
            and (not row.get("evidence_refs") or not row.get("calculation_ids"))
        ):
            errors.append(
                f"claims[{index}] SUPPORTED requires evidence_refs and calculation_ids"
            )


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in REQUIRED:
        raise SystemExit("usage: validate_contract.py validation|followup|final PATH.json")
    try:
        with open(sys.argv[2], encoding="utf-8") as handle:
            value = json.load(handle)
    except Exception as exc:
        print(json.dumps({
            "valid": False,
            "schema_valid": False,
            "action_ready": False,
            "errors": [f"invalid JSON: {exc}"],
        }))
        return 1
    errors = []
    object_fields(value, REQUIRED[sys.argv[1]], sys.argv[1], errors)
    if isinstance(value, dict):
        if value.get("schema_version") != VERSION:
            errors.append(f"schema_version must be {VERSION}")
        {"validation": validation, "followup": followup, "final": final}[
            sys.argv[1]
        ](value, errors)
    result = {
        "local_schema_preflight_valid": not errors,
        "schema_valid": False if errors else None,
        "action_ready": False if errors else None,
        "errors": errors,
        "note": (
            "A passing local preflight is not an action-ready certificate. Environment actions "
            "apply the complete disclosed schema and evidence-integrity checks."
        ),
    }
    print(json.dumps(result, indent=2))
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
'''


def _decision(stage: str, disposition: str, use_scope: str) -> dict[str, Any]:
    return {
        "development_stage": stage,
        "disposition": disposition,
        "use_scope": use_scope,
        "allowed_use": ["State the bounded evidence-supported use."],
        "prohibited_use": ["State uses that remain unsupported."],
        "unresolved_gates": ["State a remaining evidence gate."],
        "required_next_evidence": ["State the evidence needed for that gate."],
    }


def _templates() -> dict[str, dict[str, Any]]:
    validation = {
        "schema_version": SCHEMA_VERSION,
        "decision_definition": "Define the bounded decision.",
        "evidence_standard": "Define the evidence needed for that decision.",
        "hypotheses": [
            {
                "hypothesis_id": "H_SUPPORT",
                "statement": "A supporting explanation.",
                "belief": 0.5,
                "decision_effect_if_true": "SUPPORTS",
            },
            {
                "hypothesis_id": "H_LIMIT",
                "statement": "A competing limitation.",
                "belief": 0.5,
                "decision_effect_if_true": "WEAKENS",
            },
        ],
        "planned_analyses": [
            {
                "analysis_id": "A_PRIMARY",
                "question": "Define the question.",
                "method": "Choose a supported method.",
                "analysis_unit": "Person, with the declared dependence rule.",
                "input_paths": [
                    "data/cohort_metadata.csv",
                    "data/locked_predictions.csv",
                    "identity_provenance.json",
                    "work/eligible_entities.csv",
                ],
                "planned_output_paths": ["work/primary_analysis.csv", "work/primary_results.json"],
                "decision_relevance": "Explain how it changes the bounded decision.",
            }
        ],
        "prospective_specification": {
            "biological_unit": "PERSON",
            "dependence_handling": "PERSON_LEVEL_AGGREGATION",
            "aggregation": "MEAN",
            "eligible_entity_manifest_path": "work/eligible_entities.csv",
            "eligible_entity_manifest_sha256": "0" * 64,
            "identity_provenance_path": "identity_provenance.json",
            "outcome_role": "SEALED_VALIDATION_OUTCOMES",
            "estimator": "EMPIRICAL",
            "discrimination_metric": "ROC_AUC",
            "probability_metric": "BRIER_SCORE",
            "calibration_metric": "CALIBRATION_ERROR",
            "calibration_bin_count": 7,
            "utility_metric": "NET_BENEFIT",
            "utility_threshold": 0.5,
            "context_metric": "WORST_SITE_ROC_AUC",
            "uncertainty_method": "ENTITY_BOOTSTRAP_PERCENTILE",
            "uncertainty_replicates": 600,
            "uncertainty_seed": 41,
            "uncertainty_level": 0.95,
            "exclusions": [],
        },
        "decision_criteria": [
            {
                "criterion_id": "G_DISC",
                "calculation_id": "C_DISC",
                "property": "DISCRIMINATION",
                "metric": "ROC_AUC",
                "comparator": "AT_LEAST",
                "threshold": 0.7,
            },
            {
                "criterion_id": "G_PROB",
                "calculation_id": "C_PROB",
                "property": "PROBABILITY_ACCURACY",
                "metric": "BRIER_SCORE",
                "comparator": "AT_MOST",
                "threshold": 0.23,
            },
            {
                "criterion_id": "G_CAL",
                "calculation_id": "C_CAL",
                "property": "CALIBRATION",
                "metric": "CALIBRATION_ERROR",
                "comparator": "AT_MOST",
                "threshold": 0.12,
            },
            {
                "criterion_id": "G_UTIL",
                "calculation_id": "C_UTIL",
                "property": "THRESHOLD_UTILITY",
                "metric": "NET_BENEFIT",
                "comparator": "AT_LEAST",
                "threshold": 0.02,
            },
            {
                "criterion_id": "G_SITE",
                "calculation_id": "C_SITE",
                "property": "CONTEXT_ROBUSTNESS",
                "metric": "WORST_SITE_ROC_AUC",
                "comparator": "AT_LEAST",
                "threshold": 0.55,
            },
        ],
        "evidence_refs": [
            "intended_use.json",
            "identity_provenance.json",
            "work/eligible_entities.csv",
        ],
    }
    followup = {
        "schema_version": SCHEMA_VERSION,
        "decision_question_id": "Q1",
        "decision_question": "State the immediate unresolved question, or that it is resolved.",
        "decision_question_type": "CURRENT_DECISION_ALREADY_RESOLVED",
        "chosen_resource": "none",
        "evidence_target": "NO_NEW_EVIDENCE",
        "materiality_threshold": 0,
        "live_explanations": [
            {
                "explanation_id": "E1",
                "statement": "One live explanation.",
                "distinguishing_evidence": "An observable result.",
            },
            {
                "explanation_id": "E2",
                "statement": "A competing explanation.",
                "distinguishing_evidence": "A different observable result.",
            },
        ],
        "alternatives_considered": [
            {"resource_id": "none", "limitations": "No new evidence."},
            {"resource_id": "X31", "limitations": "Only pipeline replay."},
        ],
        "result_contingencies": [
            {
                "contingency_id": "K_SUPPORT",
                "observable_result": "Supporting result.",
                "hypothesis_updates": [
                    {"hypothesis_id": "H_SUPPORT", "direction": "UNCHANGED"},
                    {"hypothesis_id": "H_LIMIT", "direction": "UNCHANGED"},
                ],
                "next_decision": _decision(
                    "EXTERNAL_VALIDATION", "CONTINUE", "RESEARCH_PROBABILITY"
                ),
                "next_action": "Apply the bounded action.",
            },
            {
                "contingency_id": "K_LIMIT",
                "observable_result": "Limiting result.",
                "hypothesis_updates": [
                    {"hypothesis_id": "H_SUPPORT", "direction": "DECREASE"},
                    {"hypothesis_id": "H_LIMIT", "direction": "INCREASE"},
                ],
                "next_decision": _decision("INTERNAL_VALIDATION", "PAUSE", "NO_USE"),
                "next_action": "Contain the claim.",
            },
        ],
        "beliefs_before": {"H_SUPPORT": 0.5, "H_LIMIT": 0.5},
        "current_decision": _decision("EXTERNAL_VALIDATION", "CONTINUE", "RESEARCH_PROBABILITY"),
        "evidence_refs": ["followup_catalog.json", "work/primary_results.json"],
    }
    final = {
        "schema_version": SCHEMA_VERSION,
        "artifact_manifest": [],
        "calculations": [],
        "findings": [],
        "evidence_assessments": [],
        "belief_updates": [],
        "decision": _decision("EXTERNAL_VALIDATION", "CONTINUE", "RESEARCH_PROBABILITY"),
        "claims": [],
        "remaining_uncertainties": [],
        "evidence_refs": [],
        "resource_assessment": {
            "resource_id": "none",
            "question_type": "CURRENT_DECISION_ALREADY_RESOLVED",
            "summary_artifact_path": "work/resource_summary.json",
            "source_paths": ["purchased/none/resource_manifest.json"],
            "calculation_ids": [],
            "observed_effect": "NO_NEW_EVIDENCE",
            "material": False,
        },
        "narrative_summary": "Summarise the supported conclusion and limitations.",
    }
    validation_clustered = copy.deepcopy(validation)
    clustered_spec = validation_clustered["prospective_specification"]
    clustered_spec.update(
        {
            "dependence_handling": "SOURCE_RECORD_CLUSTERING",
            "aggregation": "NONE",
            "estimator": "ENTITY_WEIGHTED",
            "uncertainty_method": "CLUSTER_BOOTSTRAP_PERCENTILE",
        }
    )
    followup_transport = copy.deepcopy(followup)
    followup_transport.update(
        {
            "decision_question": "State the unresolved transport question.",
            "decision_question_type": "CROSS_CONTEXT_TRANSPORT",
            "chosen_resource": "X46",
            "evidence_target": "EXTERNAL_COHORT",
            "materiality_threshold": 0.05,
        }
    )
    final_pause = copy.deepcopy(final)
    final_pause["decision"] = _decision("INTERNAL_VALIDATION", "PAUSE", "NO_USE")
    return {
        "validation_plan_template.json": validation,
        "validation_plan_clustered_template.json": validation_clustered,
        "followup_plan_template.json": followup,
        "followup_plan_transport_template.json": followup_transport,
        "final_submission_template.json": final,
        "final_submission_pause_template.json": final_pause,
    }


_TEMPLATE_README = """# Structural templates

These files disclose the required object shapes. They are not answers and are not
action-ready: the validation template deliberately contains a zero manifest hash,
and the final template deliberately has empty evidence arrays. Replace every
placeholder with your own analysis. Paired validation, follow-up and final skeletons
deliberately show conflicting methods and actions so that no example is a preferred
path. All seven question/resource mappings are in submission_contract.json. The
local validator must reject untouched validation and final templates.
"""


def _identity_provenance() -> dict[str, Any]:
    return {
        "schema_version": "case1-identity-provenance-1",
        "authoritative_relationship": {
            "prediction_source_entity_field": "data/cohort_metadata.csv:fingerprint_cluster",
            "outcome_entity_field": "SEALED_VALIDATION_OUTCOMES:patient_key",
            "relationship": "same_privacy_preserving_person_identifier",
        },
        "record_field": "data/cohort_metadata.csv:sample_id",
        "cardinality_rule": "many source records may map to one person identifier",
        "scope": (
            "identifier semantics only; this declaration does not adjudicate eligibility, "
            "endpoint quality or performance"
        ),
    }


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _entity_manifest_errors(run_root: Path, payload: dict[str, Any]) -> list[dict[str, Any]]:
    spec = payload["prospective_specification"]
    relative = spec["eligible_entity_manifest_path"]
    try:
        path = (run_root / relative).resolve()
        if run_root not in path.parents or not path.is_file() or not relative.startswith("work/"):
            raise ValueError
    except (OSError, ValueError):
        return [
            {
                "path": "prospective_specification.eligible_entity_manifest_path",
                "code": "eligible_manifest_missing",
                "message": "Expected an existing work/ CSV",
            }
        ]
    observed_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    if observed_hash != spec["eligible_entity_manifest_sha256"]:
        return [
            {
                "path": "prospective_specification.eligible_entity_manifest_sha256",
                "code": "eligible_manifest_hash_mismatch",
                "message": "Committed hash does not match the saved manifest",
            }
        ]
    try:
        rows = _read_csv(path)
        wanted_columns = {
            "entity_id",
            "source_record_ids",
            "included",
            "preoutcome_exclusion_reason",
        }
        if not rows or set(rows[0]) != wanted_columns:
            raise ValueError("manifest columns must exactly match the disclosed contract")
        metadata = _read_csv(run_root / "data/cohort_metadata.csv")
        grouped: dict[str, list[str]] = {}
        for row in metadata:
            if str(row.get("baseline_eligible", "")).lower() == "true":
                grouped.setdefault(row["fingerprint_cluster"], []).append(row["sample_id"])
        by_entity = {row["entity_id"]: row for row in rows}
        if len(by_entity) != len(rows) or set(by_entity) != set(grouped):
            raise ValueError("manifest must contain every baseline-eligible person exactly once")
        exclusions = {row["entity_id"]: row for row in spec["exclusions"]}
        endpoint = {
            row["patient_key"]: row
            for row in _read_csv(run_root / "data/endpoint_source_ledger.csv")
        }
        for entity, sources in grouped.items():
            row = by_entity[entity]
            if set(filter(None, row["source_record_ids"].split("|"))) != set(sources):
                raise ValueError(f"source records do not match for {entity}")
            included = row["included"].strip().lower()
            if included not in {"true", "false"}:
                raise ValueError(f"included must be true or false for {entity}")
            if included == "false":
                exclusion = exclusions.get(entity)
                if exclusion is None or row["preoutcome_exclusion_reason"] != exclusion["reason"]:
                    raise ValueError(
                        f"excluded entity {entity} lacks the matching committed reason"
                    )
                if exclusion[
                    "reason"
                ] == "PREOUTCOME_ENDPOINT_AMBIGUITY" and "discordant" not in endpoint.get(
                    entity, {}
                ).get("review_status", ""):
                    raise ValueError(f"endpoint ambiguity is not documented for {entity}")
                if exclusion["reason"] == "PREOUTCOME_MISSING_PREDICTION":
                    predictions = {
                        r["sample_id"] for r in _read_csv(run_root / "data/locked_predictions.csv")
                    }
                    if all(source in predictions for source in sources):
                        raise ValueError(f"missing prediction is not documented for {entity}")
            elif entity in exclusions or row["preoutcome_exclusion_reason"]:
                raise ValueError(f"included entity {entity} cannot carry an exclusion")
        if set(exclusions) != {
            entity for entity, row in by_entity.items() if row["included"].lower() == "false"
        }:
            raise ValueError("manifest and committed exclusions differ")
    except (KeyError, OSError, TypeError, ValueError) as exc:
        return [
            {
                "path": "prospective_specification.eligible_entity_manifest_path",
                "code": "eligible_manifest_invalid",
                "message": str(exc),
            }
        ]
    return []


class RC17OpenMMMVPEnvironment(RC14OpenMMMVPEnvironment):
    """Case-1-only environment; no other case can be instantiated."""

    def __init__(
        self,
        project_root: Path,
        case_id: str,
        run_root: Path,
        *,
        control_outcomes: Path | None = None,
        control_outcome_provenance: Path | None = None,
        control_resource_overrides: dict[str, Path] | None = None,
        maximum_tool_calls: int = 80,
    ) -> None:
        if case_id != "case_01":
            raise ValueError("RC1.7 is an isolated Case-1 successor")
        self._control_outcomes = control_outcomes.resolve() if control_outcomes else None
        self._control_outcome_provenance = (
            control_outcome_provenance.resolve() if control_outcome_provenance else None
        )
        self._control_resource_overrides = {
            key: value.resolve() for key, value in (control_resource_overrides or {}).items()
        }
        super().__init__(project_root, case_id, run_root, maximum_tool_calls=maximum_tool_calls)

    def _neutralise_public_descriptions(self) -> None:
        super()._neutralise_public_descriptions()  # noqa: SLF001
        (self.run_root / "MISSION.md").write_text(_MISSION, encoding="utf-8")
        (self.run_root / "field_guide.md").write_text(_FIELD_GUIDE, encoding="utf-8")
        (self.run_root / "submission_contract.json").write_text(
            json.dumps(PUBLIC_CONTRACT, separators=(",", ":")) + "\n", encoding="utf-8"
        )
        (self.run_root / "scientific_methods.json").write_text(
            json.dumps(PUBLIC_CONTRACT["supported_methods"], indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (self.run_root / "method_definitions.json").write_text(
            json.dumps(METHOD_DEFINITIONS, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (self.run_root / "identity_provenance.json").write_text(
            json.dumps(_identity_provenance(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (self.run_root / "validate_contract.py").write_text(_VALIDATOR, encoding="utf-8")
        template_root = self.run_root / "contract_templates"
        template_root.mkdir()
        (template_root / "README.md").write_text(_TEMPLATE_README, encoding="utf-8")
        for name, value in _templates().items():
            (template_root / name).write_text(
                json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )

    def commit_validation_plan(self, payload_json: str) -> dict[str, Any]:
        self._count_tool()  # noqa: SLF001
        self._assert_untampered()  # noqa: SLF001
        if self.state.phase != "investigate":
            raise OpenProtocolError("Validation plan can be committed exactly once before reveal")
        try:
            payload = json.loads(payload_json)
        except (TypeError, json.JSONDecodeError):
            payload = None
        result = validate_validation_plan(payload)
        issues = [row.to_dict() for row in result.issues]
        if result.valid:
            assert isinstance(payload, dict)
            issues.extend(_entity_manifest_errors(self.run_root, payload))
            intended = json.loads((self.run_root / "intended_use.json").read_text())
            if (
                not abs(
                    float(payload["prospective_specification"]["utility_threshold"])
                    - float(intended["action_threshold"])
                )
                <= 1e-12
            ):
                issues.append(
                    {
                        "path": "prospective_specification.utility_threshold",
                        "code": "intended_threshold_mismatch",
                        "message": (
                            "Utility threshold must equal intended_use.json action_threshold"
                        ),
                    }
                )
            if (
                payload["prospective_specification"]["identity_provenance_path"]
                != "identity_provenance.json"
            ):
                issues.append(
                    {
                        "path": "prospective_specification.identity_provenance_path",
                        "code": "authoritative_provenance_required",
                        "message": "Use identity_provenance.json for the authoritative mapping",
                    }
                )
        if issues:
            self._record("validation_plan_rejected", schema_issues=issues)  # noqa: SLF001
            return {"accepted": False, "schema_issues": issues}
        assert isinstance(payload, dict)
        committed_paths = {
            str(path)
            for analysis in payload["planned_analyses"]
            for path in analysis["input_paths"]
        } | {str(path) for path in payload["evidence_refs"]}
        committed_paths |= {
            payload["prospective_specification"]["eligible_entity_manifest_path"],
            payload["prospective_specification"]["identity_provenance_path"],
        }
        invalid: list[str] = []
        input_hashes: dict[str, str] = {}
        for relative in sorted(committed_paths):
            if relative.startswith(("revealed/", "purchased/")):
                invalid.append(relative)
                continue
            try:
                path = self._safe_visible_path(relative)  # noqa: SLF001
            except OpenProtocolError:
                invalid.append(relative)
                continue
            if not path.is_file():
                invalid.append(relative)
            else:
                input_hashes[relative] = _digest_bytes(path.read_bytes())
        if invalid:
            issues = [
                {
                    "path": "planned_analyses.input_paths",
                    "code": "pre_reveal_file_required",
                    "message": "Committed inputs must exist before reveal",
                    "invalid_paths": invalid,
                }
            ]
            self._record("validation_plan_rejected", schema_issues=issues)  # noqa: SLF001
            return {"accepted": False, "schema_issues": issues}
        (self.records_root / "validation_plan.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (self.records_root / "validation_input_hashes.json").write_text(
            json.dumps(input_hashes, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        self._validation_input_hashes = input_hashes  # noqa: SLF001
        self.state.validation_plan_hash = _json_digest(payload)
        self.state.phase = "committed"
        self._record("commit_validation_plan", digest=self.state.validation_plan_hash)  # noqa: SLF001
        return {"accepted": True, "committed_plan_hash": self.state.validation_plan_hash}

    def reveal_validation(self) -> list[str]:
        self._count_tool()  # noqa: SLF001
        self._assert_untampered()  # noqa: SLF001
        if self.state.phase != "committed":
            raise OpenProtocolError("Outcome reveal requires the committed validation plan")
        target = self.run_root / "revealed"
        if self._control_outcomes is None:
            source = self.project_root / PRIVATE_ROOT / "case_01" / "sealed"
            shutil.copytree(source, target)
        else:
            target.mkdir()
            shutil.copy2(self._control_outcomes, target / "validation_outcomes.csv")
            provenance = self._control_outcome_provenance or (
                self.project_root / PRIVATE_ROOT / "case_01" / "sealed/outcome_provenance.json"
            )
            shutil.copy2(provenance, target / "outcome_provenance.json")
        outcome_path = target / "validation_outcomes.csv"
        binding = {
            "role": "SEALED_VALIDATION_OUTCOMES",
            "path": "revealed/validation_outcomes.csv",
            "sha256": hashlib.sha256(outcome_path.read_bytes()).hexdigest(),
        }
        (self.records_root / "validation_outcome_binding.json").write_text(
            json.dumps(binding, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        self._protected_evidence_hashes = self._workspace_hashes()  # noqa: SLF001
        self.state.phase = "revealed"
        files = sorted(
            path.relative_to(self.run_root).as_posix()
            for path in target.rglob("*")
            if path.is_file()
        )
        self._record(
            "reveal_validation",
            committed_plan_hash=self.state.validation_plan_hash,
            files=files,
            outcome_binding=binding,
        )  # noqa: SLF001
        return files

    def commit_followup_plan(self, payload_json: str) -> dict[str, Any]:
        self._count_tool()  # noqa: SLF001
        self._assert_untampered()  # noqa: SLF001
        if self.state.phase != "revealed":
            raise OpenProtocolError(
                "Follow-up plan must be committed after reveal and before purchase"
            )
        try:
            payload = json.loads(payload_json)
        except (TypeError, json.JSONDecodeError):
            payload = None
        result = validate_followup_plan(payload)
        issues = [row.to_dict() for row in result.issues]
        if result.valid:
            assert isinstance(payload, dict)
            validation = json.loads((self.records_root / "validation_plan.json").read_text())
            expected = {row["hypothesis_id"]: row["belief"] for row in validation["hypotheses"]}
            if payload["beliefs_before"] != expected:
                issues.append(
                    {
                        "path": "beliefs_before",
                        "code": "commitment_mismatch",
                        "message": "Preserve validation-plan hypothesis IDs and values",
                    }
                )
        if issues:
            self._record("followup_plan_rejected", schema_issues=issues)  # noqa: SLF001
            return {"accepted": False, "schema_issues": issues}
        assert isinstance(payload, dict)
        (self.records_root / "followup_plan.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        self.state.followup_plan_hash = _json_digest(payload)
        self.state.phase = "followup_committed"
        self._record("commit_followup_plan", digest=self.state.followup_plan_hash)  # noqa: SLF001
        return {"accepted": True, "committed_followup_hash": self.state.followup_plan_hash}

    def purchase_resource(self, resource_id: str) -> list[str]:
        super().purchase_resource(resource_id)
        target = self.run_root / "purchased" / resource_id
        override = self._control_resource_overrides.get(resource_id)
        if override is not None:
            shutil.rmtree(target)
            shutil.copytree(override, target)
        if resource_id == "X17":
            rows = _read_csv(target / "source_record_crosswalk.csv")
            normalized = target / "canonical_person_crosswalk.csv"
            with normalized.open("w", encoding="utf-8", newline="") as handle:
                columns = [
                    "source_record_id",
                    "reported_patient_id",
                    "fingerprint_cluster",
                    "canonical_person_id",
                    "adjudication_status",
                ]
                writer = csv.DictWriter(handle, fieldnames=columns)
                writer.writeheader()
                for row in rows:
                    writer.writerow(
                        {
                            "source_record_id": row["sample_id"],
                            "reported_patient_id": row["source_patient_id"],
                            "fingerprint_cluster": row["fingerprint_cluster"],
                            "canonical_person_id": row["source_patient_id"],
                            "adjudication_status": row["resolution_status"],
                        }
                    )
        source_hashes = {
            path.relative_to(target).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(target.rglob("*"))
            if path.is_file()
        }
        manifest = {
            "schema_version": "case1-resource-return-1",
            "resource_id": resource_id,
            "files": [{"path": name, "sha256": digest} for name, digest in source_hashes.items()],
            "analysis_contract": PUBLIC_CONTRACT["resource_summary_contract"],
        }
        (target / "resource_manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        self._protected_evidence_hashes = self._workspace_hashes()  # noqa: SLF001
        files = sorted(
            path.relative_to(self.run_root).as_posix()
            for path in target.rglob("*")
            if path.is_file()
        )
        self.state.event_log[-1]["files"] = files
        return files

    def submit(self, payload_json: str) -> dict[str, Any]:
        self._count_tool()  # noqa: SLF001
        self._assert_untampered()  # noqa: SLF001
        if self.state.phase != "purchased":
            raise OpenProtocolError("Final submission requires a completed resource action")
        try:
            payload = json.loads(payload_json)
        except (TypeError, json.JSONDecodeError):
            payload = None
        result = validate_final_submission(payload)
        if not result.valid:
            issues = [row.to_dict() for row in result.issues]
            self._record("submit_rejected", schema_issues=issues)  # noqa: SLF001
            return {"accepted": False, "schema_issues": issues}
        assert isinstance(payload, dict)
        (self.records_root / "final_submission.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        self.state.final_submission_hash = _json_digest(payload)
        self.state.completion_accepted = True
        self.state.phase = "terminal"
        self.state.terminal_reason = "submitted"
        self._record(
            "submit",
            validation_plan_hash=self.state.validation_plan_hash,
            followup_plan_hash=self.state.followup_plan_hash,
            final_submission_hash=self.state.final_submission_hash,
        )  # noqa: SLF001
        return {"accepted": True, "terminal": True}

    def export_submission(self) -> dict[str, Any]:
        value = super().export_submission()
        binding = self.records_root / "validation_outcome_binding.json"
        value["interface_version"] = SCHEMA_VERSION
        value["validation_outcome_binding"] = (
            json.loads(binding.read_text()) if binding.is_file() else None
        )
        return value


__all__ = ["RC17OpenMMMVPEnvironment"]

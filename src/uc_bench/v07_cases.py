# ruff: noqa: E501
"""Deterministic construction of the four v0.7 development case packets.

Public packets contain only evidence an investigator could inspect.  Outcomes,
follow-up returns, and adjudication truth are written to ``grader_private`` and
must never be mounted in an agent workspace before the corresponding action.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import random
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from uc_bench.v07_metrics import (
    cluster_bootstrap_auc,
    collapse_to_patient,
    metric_bundle,
    naive_row_auc,
    site_metric_bundle,
)

PUBLIC_ROOT = Path("tasks/hard_suite_v07/development")
PRIVATE_ROOT = Path("grader_private/hard_suite_v07")


@dataclass(frozen=True, slots=True)
class CaseSpec:
    case_id: str
    seed: int
    n_patients: int
    repeat_rate: float
    budget_units: int
    contract_threshold: float
    preferred_resource: str
    acceptable_resources: tuple[str, ...]
    initial_decisions: tuple[str, ...]
    final_decisions: tuple[str, ...]
    required_concepts: tuple[str, ...]
    harmless_anomalies: tuple[str, ...]
    supported_claims: tuple[str, ...]
    prohibited_claims: tuple[str, ...]


CASE_SPECS = (
    CaseSpec(
        case_id="case_01",
        seed=701,
        n_patients=124,
        repeat_rate=0.12,
        budget_units=3,
        contract_threshold=0.50,
        preferred_resource="none",
        acceptable_resources=("none", "X31"),
        initial_decisions=("conditional_advance", "pause"),
        final_decisions=("conditional_advance",),
        required_concepts=("signal_supported", "minor_execution_uncertainty"),
        harmless_anomalies=("duplicate_assay_export", "noncausal_clock_skew"),
        supported_claims=("research_use_prognostic_validation",),
        prohibited_claims=("treatment_effect", "clinical_utility_proven", "all_platforms"),
    ),
    CaseSpec(
        case_id="case_02",
        seed=702,
        n_patients=96,
        repeat_rate=0.31,
        budget_units=3,
        contract_threshold=0.50,
        preferred_resource="X17",
        acceptable_resources=("X17",),
        initial_decisions=("pause",),
        final_decisions=("pause", "insufficient_evidence"),
        required_concepts=("patient_dependence", "site_confounding"),
        harmless_anomalies=("minor_endpoint_disagreement",),
        supported_claims=("naive_row_performance_not_decision_valid",),
        prohibited_claims=("independent_validation_passed", "treatment_effect"),
    ),
    CaseSpec(
        case_id="case_03",
        seed=703,
        n_patients=112,
        repeat_rate=0.10,
        budget_units=3,
        contract_threshold=0.50,
        preferred_resource="X31",
        acceptable_resources=("X31",),
        initial_decisions=("pause",),
        final_decisions=("stop",),
        required_concepts=("preprocessing_fit_scope", "validation_information_leakage"),
        harmless_anomalies=("batch_alias_typo",),
        supported_claims=("original_validation_invalid",),
        prohibited_claims=("independent_validation_passed", "treatment_effect"),
    ),
    CaseSpec(
        case_id="case_04",
        seed=704,
        n_patients=148,
        repeat_rate=0.08,
        budget_units=3,
        contract_threshold=0.50,
        preferred_resource="X46",
        acceptable_resources=("X46",),
        initial_decisions=("pause",),
        final_decisions=("pause", "stop"),
        required_concepts=("miscalibration", "negative_threshold_utility"),
        harmless_anomalies=("two_missing_noncritical_covariates",),
        supported_claims=("ranking_signal_only",),
        prohibited_claims=("safe_threshold_use", "clinical_utility_proven", "treatment_effect"),
    ),
)


RESOURCE_CATALOG = (
    {
        "resource_id": "X17",
        "title": "Source-record reconciliation package",
        "cost_units": 1,
        "delay_days": 4,
        "returns": ["source-key crosswalk", "visit chronology", "record-level unresolved list"],
        "cannot_answer": ["clinical meaning of the endpoint", "pipeline execution", "new outcomes"],
    },
    {
        "resource_id": "X24",
        "title": "Endpoint evidence package",
        "cost_units": 2,
        "delay_days": 9,
        "returns": ["blinded dual-reviewer labels", "source excerpts", "adjudication log"],
        "cannot_answer": ["patient identity", "pipeline execution", "platform transport"],
    },
    {
        "resource_id": "X31",
        "title": "Pipeline execution package",
        "cost_units": 1,
        "delay_days": 5,
        "returns": ["containerized replay predictions", "fit-input hashes", "execution lineage"],
        "cannot_answer": ["endpoint meaning", "future clinical utility", "drug-class transport"],
    },
    {
        "resource_id": "X46",
        "title": "Matched external evidence package",
        "cost_units": 3,
        "delay_days": 21,
        "returns": [
            "new matched predictions and outcomes",
            "site fields",
            "decision-threshold table",
        ],
        "cannot_answer": ["original identity errors", "original transform execution"],
    },
    {
        "resource_id": "X58",
        "title": "Larger sample package",
        "cost_units": 3,
        "delay_days": 45,
        "returns": ["additional records under the current collection process", "updated precision"],
        "cannot_answer": ["systematic label bias", "pipeline leakage", "wrong intended use"],
    },
    {
        "resource_id": "X63",
        "title": "Expert review package",
        "cost_units": 1,
        "delay_days": 3,
        "returns": [
            "cross-functional review memo based on existing files",
            "analysis recommendations",
        ],
        "cannot_answer": ["missing source records", "unobserved outcomes", "unexecuted analyses"],
    },
    {
        "resource_id": "none",
        "title": "Purchase nothing",
        "cost_units": 0,
        "delay_days": 0,
        "returns": ["no new evidence"],
        "cannot_answer": ["any unresolved empirical question"],
    },
)


def _sigmoid(value: float) -> float:
    return 1 / (1 + math.exp(-value))


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError(f"Refusing to create empty CSV: {path}")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _case_sites(spec: CaseSpec) -> list[str]:
    if spec.case_id == "case_02":
        return ["North"] * 58 + ["Central"] * 24 + ["Coast"] * 14
    names = ["North", "Central", "Coast"]
    return [names[index % len(names)] for index in range(spec.n_patients)]


def _patient_values(spec: CaseSpec) -> list[dict[str, Any]]:
    generator = random.Random(spec.seed)
    rows: list[dict[str, Any]] = []
    sites = _case_sites(spec)
    generator.shuffle(sites)
    for index, site in enumerate(sites, start=1):
        latent = generator.gauss(0, 1)
        if spec.case_id == "case_01":
            outcome_probability = _sigmoid(-0.05 + 1.15 * latent)
            outcome = int(generator.random() < outcome_probability)
            predicted = _sigmoid(-0.05 + 0.92 * latent + generator.gauss(0, 0.48))
        elif spec.case_id == "case_02":
            site_outcome = {"North": 1.25, "Central": -0.10, "Coast": -1.20}[site]
            outcome = int(generator.random() < _sigmoid(site_outcome + 0.22 * latent))
            site_score = {"North": 1.35, "Central": -0.05, "Coast": -1.30}[site]
            predicted = _sigmoid(site_score + 0.16 * latent + generator.gauss(0, 0.58))
        elif spec.case_id == "case_03":
            outcome = int(generator.random() < _sigmoid(-0.15 + 0.85 * latent))
            predicted = _sigmoid(2.0 * (2 * outcome - 1) + 0.35 * latent + generator.gauss(0, 0.42))
        else:
            outcome = int(generator.random() < _sigmoid(-0.95 + 1.08 * latent))
            predicted = _sigmoid(0.95 + 1.18 * latent + generator.gauss(0, 0.42))
        rows.append(
            {
                "patient_key": f"F{index:04d}",
                "reported_patient_id": f"P{index:04d}",
                "site": site,
                "latent": latent,
                "outcome": outcome,
                "prediction": min(max(predicted, 0.01), 0.99),
            }
        )
    return rows


def _sample_rows(
    spec: CaseSpec, patients: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    generator = random.Random(spec.seed + 11)
    metadata: list[dict[str, Any]] = []
    predictions: list[dict[str, Any]] = []
    features: list[dict[str, Any]] = []
    for index, patient in enumerate(patients, start=1):
        repeats = 1
        if generator.random() < spec.repeat_rate:
            repeats += 1
        if spec.case_id == "case_02" and (
            (patient["site"] == "North" and patient["outcome"] == 1)
            or (patient["site"] == "Coast" and patient["outcome"] == 0)
        ):
            # Follow-up biopsies were preferentially collected in the two
            # clinically distinctive site/outcome groups.  A row-level AUC
            # therefore reweights easy patients as well as understating the
            # uncertainty from repeated people.
            repeats += 1 + int(generator.random() < 0.35)
        for repeat in range(repeats):
            sample_id = f"S{index:04d}_{repeat + 1}"
            reported = patient["reported_patient_id"]
            if spec.case_id == "case_02" and index in {17, 18}:
                reported = "P0017"
            visit_day = -14 + (index % 13)
            platform = "HTA2" if spec.case_id != "case_04" or index % 5 else "HTA2-r2"
            batch = f"B{1 + index % 4}"
            if spec.case_id == "case_03" and index == 37:
                batch = "B-03"
            probability = min(max(patient["prediction"] + generator.gauss(0, 0.012), 0.005), 0.995)
            metadata.append(
                {
                    "sample_id": sample_id,
                    "reported_patient_id": reported,
                    "fingerprint_cluster": patient["patient_key"],
                    "biopsy_id": f"BX{index:04d}_{repeat + 1}",
                    "visit_day": visit_day,
                    "baseline_eligible": "true",
                    "site": patient["site"],
                    "batch": batch,
                    "platform": platform,
                    "tissue": "colonic_mucosa",
                    "age_years": 22 + (index * 7) % 51,
                    "sex": ""
                    if spec.case_id == "case_04" and index in {1, 2}
                    else ("F" if index % 2 else "M"),
                }
            )
            predictions.append(
                {
                    "sample_id": sample_id,
                    "model_version": "uc-lock-2026-07",
                    "predicted_probability": f"{probability:.6f}",
                    "prediction_timestamp": "2026-07-14T09:20:00Z",
                }
            )
            features.append(
                {
                    "sample_id": sample_id,
                    "IFN_score": f"{patient['latent'] + generator.gauss(0, 0.20):.5f}",
                    "epithelial_score": f"{-0.35 * patient['latent'] + generator.gauss(0, 0.25):.5f}",
                    "library_size_log10": f"{6.2 + 0.07 * (index % 4) + generator.gauss(0, 0.03):.5f}",
                }
            )
    return metadata, predictions, features


def _outcome_rows(spec: CaseSpec, patients: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "patient_key": row["patient_key"],
            "week6_response": row["outcome"],
            "assessment_day": 42 + ((index % 5) - 2),
            "source": "central_clinical_review",
        }
        for index, row in enumerate(patients)
    ]


def _endpoint_ledger(spec: CaseSpec, patients: list[dict[str, Any]]) -> list[dict[str, Any]]:
    disagreement_count = {"case_01": 1, "case_02": 4, "case_03": 2, "case_04": 2}[spec.case_id]
    return [
        {
            "patient_key": patient["patient_key"],
            "planned_day": 42,
            "observed_day": 42 + ((index % 5) - 2),
            "primary_source": "central_clinical_review",
            "secondary_source": "site_ecrf",
            "review_status": "discordant_pending_reconciliation"
            if index < disagreement_count
            else "concordant",
            "outcome_value": "SEALED",
        }
        for index, patient in enumerate(patients)
    ]


def _execution_records(
    spec: CaseSpec, metadata: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    validation_ids = [row["sample_id"] for row in metadata]
    training_ids = [f"TR{index:04d}" for index in range(1, 181)]
    membership = [
        {"sample_id": sample_id, "cohort_role": "training", "included_in_reference_fit": "true"}
        for sample_id in training_ids
    ]
    if spec.case_id == "case_03":
        membership.extend(
            {
                "sample_id": sample_id,
                "cohort_role": "validation",
                "included_in_reference_fit": "true",
            }
            for sample_id in validation_ids
        )
    logs = [
        {
            "timestamp": "2026-07-14T08:05:00Z",
            "event": "load_expression",
            "artifact": "expression_matrix",
            "host_clock_offset_seconds": 0,
        },
        {
            "timestamp": "2026-07-14T08:20:00Z",
            "event": "resolve_membership",
            "artifact": "fit_membership.csv",
            "host_clock_offset_seconds": 0,
        },
        {
            "timestamp": "2026-07-14T08:35:00Z",
            "event": "fit_reference",
            "artifact": "reference_distribution.rds",
            "host_clock_offset_seconds": 0,
        },
        {
            "timestamp": "2026-07-14T09:20:00Z",
            "event": "export_predictions",
            "artifact": "locked_predictions.csv",
            "host_clock_offset_seconds": 0,
        },
    ]
    if spec.case_id == "case_03":
        logs.insert(
            1,
            {
                "timestamp": "2026-07-14T08:12:00Z",
                "event": "import_endpoint_table",
                "artifact": "week6_response.csv",
                "host_clock_offset_seconds": 0,
            },
        )
    if spec.case_id == "case_01":
        logs.extend(
            [
                {
                    "timestamp": "2026-07-14T09:21:00Z",
                    "event": "export_predictions_duplicate",
                    "artifact": "locked_predictions.copy.csv",
                    "host_clock_offset_seconds": 0,
                },
                {
                    "timestamp": "2026-07-14T09:12:00Z",
                    "event": "archive_upload",
                    "artifact": "locked_predictions.copy.csv",
                    "host_clock_offset_seconds": -480,
                },
            ]
        )
    return membership, logs


def _sponsor_assertions(spec: CaseSpec, naive_auc: float) -> str:
    lines = [
        "# Sponsor diligence assertions",
        "",
        f"- The locked export has a reported validation AUC of {naive_auc:.3f}.",
        "- The predictor is intended for research-use triage at baseline before first infliximab.",
    ]
    if spec.case_id == "case_01":
        lines += [
            "- All preprocessing was described as training-only; archived execution detail is incomplete."
        ]
    elif spec.case_id == "case_02":
        lines += [
            "- Each biopsy was treated as an independent validation observation.",
            "- Endpoint review was described as the main remaining concern.",
        ]
    elif spec.case_id == "case_03":
        lines += [
            "- The executed reference fit is asserted to match the training-only configuration."
        ]
    else:
        lines += [
            "- The reported discrimination is asserted to support use at probability threshold 0.50."
        ]
    lines += ["", "Assertions are claims to investigate, not adjudicated facts."]
    return "\n".join(lines) + "\n"


def _preprocess_code() -> str:
    return '''"""Archived preprocessing entry point (illustrative, not executable here)."""

def build_reference(expression, membership):
    fit_ids = membership.loc[membership["included_in_reference_fit"], "sample_id"]
    return expression.loc[fit_ids].mean(axis=0), expression.loc[fit_ids].std(axis=0)

def transform(expression, reference_mean, reference_std):
    return (expression - reference_mean) / reference_std
'''


def _clean_replay_predictions(
    spec: CaseSpec, patients: list[dict[str, Any]], *, mechanism: str
) -> list[dict[str, Any]]:
    generator = random.Random(spec.seed + (40 if mechanism == "signal_remains" else 41))
    rows: list[dict[str, Any]] = []
    for patient in patients:
        if mechanism == "signal_remains":
            probability = _sigmoid(0.68 * patient["latent"] + generator.gauss(0, 0.62))
        else:
            probability = _sigmoid(generator.gauss(0, 0.95))
        rows.append(
            {
                "patient_key": patient["patient_key"],
                "predicted_probability": f"{probability:.6f}",
                "model_version": "uc-lock-2026-07-clean-replay",
            }
        )
    return rows


def _external_rows(
    spec: CaseSpec, *, n: int = 92
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    generator = random.Random(spec.seed + 90)
    predictions: list[dict[str, Any]] = []
    outcomes: list[dict[str, Any]] = []
    for index in range(1, n + 1):
        latent = generator.gauss(0, 1)
        outcome = int(generator.random() < _sigmoid(-1.00 + 1.0 * latent))
        if spec.case_id == "case_04":
            probability = _sigmoid(1.15 + 1.05 * latent + generator.gauss(0, 0.55))
        else:
            probability = _sigmoid(0.70 * latent + generator.gauss(0, 0.65))
        key = f"E{index:04d}"
        predictions.append(
            {
                "patient_key": key,
                "site": f"External-{1 + index % 3}",
                "predicted_probability": f"{probability:.6f}",
            }
        )
        outcomes.append({"patient_key": key, "week6_response": outcome, "assessment_day": 42})
    return predictions, outcomes


def _patient_prediction_rows(
    metadata: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
    outcomes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    metadata_text = [{key: str(value) for key, value in row.items()} for row in metadata]
    prediction_text = [{key: str(value) for key, value in row.items()} for row in predictions]
    outcome_text = [{key: str(value) for key, value in row.items()} for row in outcomes]
    return collapse_to_patient(metadata_text, prediction_text, outcome_text)


def _truth_metrics(
    spec: CaseSpec,
    metadata: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
    outcomes: list[dict[str, Any]],
) -> dict[str, Any]:
    patient_rows = _patient_prediction_rows(metadata, predictions, outcomes)
    bundle = metric_bundle(patient_rows, threshold=spec.contract_threshold)
    lower, upper = cluster_bootstrap_auc(patient_rows, seed=spec.seed)
    bundle["auc_ci_low"] = lower
    bundle["auc_ci_high"] = upper
    bundle["naive_row_auc"] = naive_row_auc(
        [{key: str(value) for key, value in row.items()} for row in metadata],
        [{key: str(value) for key, value in row.items()} for row in predictions],
        [{key: str(value) for key, value in row.items()} for row in outcomes],
    )
    bundle.update(site_metric_bundle(patient_rows))
    return bundle


def _resource_values(spec: CaseSpec) -> dict[str, float]:
    if spec.case_id == "case_01":
        return {
            "none": 0.92,
            "X31": 0.88,
            "X63": 0.48,
            "X17": 0.25,
            "X24": 0.18,
            "X46": 0.52,
            "X58": 0.31,
        }
    if spec.case_id == "case_02":
        return {
            "X17": 0.96,
            "X63": 0.52,
            "X24": 0.31,
            "X31": 0.25,
            "X46": 0.58,
            "X58": 0.22,
            "none": 0.05,
        }
    if spec.case_id == "case_03":
        return {
            "X31": 0.98,
            "X63": 0.44,
            "X17": 0.18,
            "X24": 0.16,
            "X46": 0.40,
            "X58": 0.12,
            "none": 0.02,
        }
    return {
        "X46": 0.95,
        "X58": 0.58,
        "X63": 0.42,
        "X24": 0.30,
        "X31": 0.20,
        "X17": 0.10,
        "none": 0.15,
    }


def _followup_returns(
    root: Path,
    spec: CaseSpec,
    patients: list[dict[str, Any]],
    metadata: list[dict[str, Any]],
    outcomes: list[dict[str, Any]],
) -> dict[str, dict[str, list[str]]]:
    private = root / PRIVATE_ROOT / spec.case_id / "resource_returns"
    manifest: dict[str, dict[str, list[str]]] = {}

    identity_rows = [
        {
            "source_patient_id": row["reported_patient_id"],
            "fingerprint_cluster": row["fingerprint_cluster"],
            "sample_id": row["sample_id"],
            "site": row["site"],
            "visit_day": row["visit_day"],
            "resolution_status": "resolved_from_source_keys",
        }
        for row in metadata
    ]
    _write_csv(private / "X17" / "source_record_crosswalk.csv", identity_rows)
    _write_json(
        private / "X17" / "package_limitations.json",
        {"uses_new_measurements": False, "unresolved_fields": []},
    )

    adjudicated = [
        {
            **row,
            "reviewer_agreement": "concordant" if index % 29 else "resolved_by_third_reviewer",
        }
        for index, row in enumerate(outcomes, start=1)
    ]
    _write_csv(private / "X24" / "adjudicated_endpoints.csv", adjudicated)
    _write_json(
        private / "X24" / "adjudication_provenance.json",
        {"blinded_to_prediction": True, "reviewers": 2, "third_reviewer_rule": "disagreement_only"},
    )

    mechanisms = (
        ("signal_collapses", "signal_remains") if spec.case_id == "case_03" else ("observed",)
    )
    for mechanism in mechanisms:
        target = private / "X31" / mechanism if spec.case_id == "case_03" else private / "X31"
        if spec.case_id == "case_03":
            replay = _clean_replay_predictions(spec, patients, mechanism=mechanism)
        else:
            replay = [
                {
                    "patient_key": row["patient_key"],
                    "predicted_probability": f"{row['prediction']:.6f}",
                    "model_version": "uc-lock-2026-07-clean-replay",
                }
                for row in patients
            ]
        _write_csv(target / "replay_predictions.csv", replay)
        _write_json(
            target / "execution_lineage.json",
            {
                "reference_fit_role_counts": {"training": 180, "validation": 0},
                "outcomes_accessible_during_fit": False,
                "container_digest": "sha256:6f02f2d22a70",
                "model_weights_unchanged": True,
            },
        )

    external_predictions, external_outcomes = _external_rows(spec)
    _write_csv(private / "X46" / "matched_predictions.csv", external_predictions)
    _write_csv(private / "X46" / "matched_outcomes.csv", external_outcomes)
    _write_json(
        private / "X46" / "matching_provenance.json",
        {"drug": "infliximab", "endpoint_day": 42, "platform": "HTA2", "baseline_only": True},
    )

    larger_predictions, larger_outcomes = _external_rows(spec, n=196)
    _write_csv(private / "X58" / "additional_predictions.csv", larger_predictions)
    _write_csv(private / "X58" / "additional_outcomes.csv", larger_outcomes)
    _write_json(
        private / "X58" / "collection_provenance.json",
        {
            "collection_process": "same_as_current_packet",
            "new_sites": 0,
            "endpoint_process_changed": False,
        },
    )

    _write_json(
        private / "X63" / "review_memo.json",
        {
            "basis": "existing packet only",
            "recommendations": [
                "preserve patient as analysis unit",
                "compare discrimination with calibration and threshold utility",
                "do not infer treatment effect",
            ],
            "new_empirical_evidence": False,
        },
    )

    for resource in RESOURCE_CATALOG:
        resource_id = resource["resource_id"]
        if resource_id == "none":
            manifest[resource_id] = {"default": []}
            continue
        resource_root = private / resource_id
        if spec.case_id == "case_03" and resource_id == "X31":
            manifest[resource_id] = {
                mechanism: sorted(
                    str(path.relative_to(resource_root / mechanism))
                    for path in (resource_root / mechanism).rglob("*")
                    if path.is_file()
                )
                for mechanism in mechanisms
            }
        else:
            manifest[resource_id] = {
                "default": sorted(
                    str(path.relative_to(resource_root))
                    for path in resource_root.rglob("*")
                    if path.is_file()
                )
            }
    return manifest


def _build_case(root: Path, spec: CaseSpec) -> dict[str, Any]:
    public = root / PUBLIC_ROOT / spec.case_id
    private = root / PRIVATE_ROOT / spec.case_id
    patients = _patient_values(spec)
    metadata, predictions, features = _sample_rows(spec, patients)
    outcomes = _outcome_rows(spec, patients)
    endpoint_ledger = _endpoint_ledger(spec, patients)
    membership, logs = _execution_records(spec, metadata)
    metrics = _truth_metrics(spec, metadata, predictions, outcomes)
    site_counts = Counter(row["site"] for row in patients)
    repeat_fraction = 1 - spec.n_patients / len(metadata)

    _write_csv(public / "data/cohort_metadata.csv", metadata)
    _write_csv(public / "data/locked_predictions.csv", predictions)
    _write_csv(public / "data/expression_feature_summary.csv", features)
    _write_csv(public / "data/endpoint_source_ledger.csv", endpoint_ledger)
    _write_csv(public / "pipeline/fit_membership.csv", membership)
    _write_csv(public / "logs/execution_log.csv", logs)
    (public / "pipeline").mkdir(parents=True, exist_ok=True)
    (public / "pipeline/preprocess.py").write_text(_preprocess_code(), encoding="utf-8")
    _write_json(
        public / "pipeline/preprocess_config.json",
        {
            "declared_reference_role": "training",
            "membership_file": "fit_membership.csv",
            "reference_transform": "featurewise_zscore",
            "model_weights_locked": True,
        },
    )
    _write_json(
        public / "model/model_manifest.json",
        {
            "model_id": "uc-lock-2026-07",
            "input": "baseline colonic-mucosa transcriptomic features",
            "output": "week-6 response probability",
            "drug": "infliximab",
            "weights_sha256": "63c96d4b63cc83a3a4700c74e37772cc7ec19cf2e5f7859b3e870f75ef0dddb3",
            "decision_threshold": spec.contract_threshold,
        },
    )
    reproduction = [
        {
            "case_id": f"R{index}",
            "expected_probability": f"{value:.4f}",
            "observed_probability": f"{value + delta:.4f}",
        }
        for index, (value, delta) in enumerate(
            ((0.21, 0.001), (0.47, -0.002), (0.82, 0.001)), start=1
        )
    ]
    _write_csv(public / "model/reproduction_cases.csv", reproduction)
    (public / "sponsor").mkdir(parents=True, exist_ok=True)
    (public / "sponsor/assertions.md").write_text(
        _sponsor_assertions(spec, metrics["naive_row_auc"]), encoding="utf-8"
    )
    _write_json(
        public / "followup_catalog.json",
        {"budget_units": spec.budget_units, "maximum_purchases": 1, "resources": RESOURCE_CATALOG},
    )
    _write_json(
        public / "intended_use.json",
        {
            "population": "adults with moderate-to-severe ulcerative colitis before first infliximab",
            "input_time": "baseline before treatment",
            "endpoint": "clinical response at day 42, window 35-49",
            "claim": "prognostic probability for research-use triage",
            "not_supported_by_contract": ["individual treatment effect", "clinical deployment"],
            "threshold": spec.contract_threshold,
            "advance_criteria": {
                "auc_minimum": 0.70,
                "auc_ci_lower_minimum": 0.58,
                "brier_maximum": 0.23,
                "ece_maximum": 0.12,
                "net_benefit_minimum": 0.0,
            },
        },
    )
    _write_json(
        public / "validation_manifest.json",
        {
            "predictions_locked": True,
            "outcomes_sealed": True,
            "outcome_key": "fingerprint_cluster -> patient_key",
            "commitment_required_before_reveal": True,
            "expected_analysis_unit": "must be justified from supplied records",
        },
    )
    (public / "README.md").write_text(
        "# Predictor diligence packet\n\nInvestigate the locked predictor under the intended-use contract. "
        "The sponsor assertions are not ground truth. Commit a validation plan before revealing outcomes, "
        "perform decision-relevant calculations, choose at most one follow-up within budget, and make a bounded investment decision.\n",
        encoding="utf-8",
    )

    _write_csv(private / "sealed/validation_outcomes.csv", outcomes)
    _write_json(
        private / "sealed/outcome_provenance.json",
        {
            "sealed_at": "2026-07-13T18:00:00Z",
            "unsealed_only_after_commit": True,
            "prediction_blinded_review": True,
        },
    )
    resource_manifest = _followup_returns(root, spec, patients, metadata, outcomes)

    mechanisms = ["default"]
    if spec.case_id == "case_03":
        mechanisms = ["signal_collapses", "signal_remains"]
    truth = {
        "case_id": spec.case_id,
        "private_seed": spec.seed,
        "n_patients": spec.n_patients,
        "n_samples": len(metadata),
        "repeat_fraction": repeat_fraction,
        "site_counts": dict(site_counts),
        "metrics": metrics,
        "required_concepts": spec.required_concepts,
        "harmless_anomalies": spec.harmless_anomalies,
        "preferred_resource": spec.preferred_resource,
        "acceptable_resources": spec.acceptable_resources,
        "resource_decision_values": _resource_values(spec),
        "initial_decisions": spec.initial_decisions,
        "final_decisions": spec.final_decisions,
        "supported_claims": spec.supported_claims,
        "prohibited_claims": spec.prohibited_claims,
        "resource_manifest": resource_manifest,
        "mechanisms": mechanisms,
        "evidence_path": {
            "analysis_unit": ["data/cohort_metadata.csv", "data/endpoint_source_ledger.csv"],
            "pipeline_scope": [
                "pipeline/preprocess.py",
                "pipeline/fit_membership.csv",
                "logs/execution_log.csv",
            ],
            "quantitative": ["data/locked_predictions.csv", "revealed/validation_outcomes.csv"],
            "resource": ["followup_catalog.json", "purchased/<resource>/*"],
        },
    }

    if spec.case_id == "case_03":
        replay_metrics: dict[str, Any] = {}
        for mechanism in mechanisms:
            replay = _clean_replay_predictions(spec, patients, mechanism=mechanism)
            replay_rows = [
                {
                    "patient_key": row["patient_key"],
                    "site": patient["site"],
                    "probability": float(row["predicted_probability"]),
                    "outcome": patient["outcome"],
                }
                for row, patient in zip(replay, patients, strict=True)
            ]
            values = metric_bundle(replay_rows, threshold=spec.contract_threshold)
            low, high = cluster_bootstrap_auc(replay_rows, seed=spec.seed + 3)
            values.update({"auc_ci_low": low, "auc_ci_high": high})
            replay_metrics[mechanism] = values
        truth["replay_metrics"] = replay_metrics
        truth["variant_final_decisions"] = {
            "signal_collapses": ["stop"],
            "signal_remains": ["conditional_advance"],
        }
        truth["variant_belief_directions"] = {
            "signal_collapses": "large_decrease",
            "signal_remains": "increase_after_valid_replay",
        }
    elif spec.case_id == "case_04":
        external_predictions, external_outcomes = _external_rows(spec)
        outcome_by_key = {row["patient_key"]: row["week6_response"] for row in external_outcomes}
        external_rows = [
            {
                "patient_key": row["patient_key"],
                "site": row["site"],
                "probability": float(row["predicted_probability"]),
                "outcome": outcome_by_key[row["patient_key"]],
            }
            for row in external_predictions
        ]
        values = metric_bundle(external_rows, threshold=spec.contract_threshold)
        low, high = cluster_bootstrap_auc(external_rows, seed=spec.seed + 4)
        values.update({"auc_ci_low": low, "auc_ci_high": high})
        truth["followup_metrics"] = values

    _write_json(private / "truth.json", truth)
    return truth


def build_development_cases(project_root: Path) -> dict[str, Any]:
    """Build all four public packets and their private sealed counterparts."""

    root = project_root.resolve()
    truths = [_build_case(root, spec) for spec in CASE_SPECS]
    manifest = {
        "schema_version": "0.7-vertical-1",
        "status": "unfrozen_unexposed_development_only",
        "case_count": len(truths),
        "case_ids": [row["case_id"] for row in truths],
        "case_03_variants": ["signal_collapses", "signal_remains"],
        "paid_calls": 0,
        "heldout_cases_created": 0,
    }
    public_hashes: dict[str, str] = {}
    for path in sorted((root / PUBLIC_ROOT).rglob("*")):
        if path.is_file():
            public_hashes[str(path.relative_to(root))] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    manifest["public_packet_hashes"] = public_hashes
    _write_json(root / PRIVATE_ROOT / "development_manifest.json", manifest)
    return manifest


def load_truth(project_root: Path, case_id: str) -> dict[str, Any]:
    path = project_root.resolve() / PRIVATE_ROOT / case_id / "truth.json"
    return json.loads(path.read_text(encoding="utf-8"))

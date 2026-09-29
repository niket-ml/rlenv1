"""Stateful v0.5 anti-TNF predictor-diligence workflow.

The public workspace contains an ordinary multi-artifact diligence case. Private
scenario state controls evidence admissibility and counterfactual resource
packets. Scoring is milestone- and property-based so an early scientific error
does not mechanically erase later containment or recovery.
"""

from __future__ import annotations

import csv
import json
import math
import random
import shutil
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any

from uc_bench.errors import ConfigurationError, ContractError, InvalidTransitionError
from uc_bench.hashing import canonical_sha256, sha256_file

V05_CONFIG_PATH = Path("configs/hard_suite_v05.json")
V05_HELDOUT_PATH = Path("grader_private/hard_suite_v05_heldout.json")
V05_TASK_ROOT = Path("tasks/hard_suite_v05")

FEATURES = ("IL13RA2", "IL11", "TNFRSF11B", "PTGS2", "TREM1")
MODEL_WEIGHTS = {
    "IL13RA2": 0.50,
    "IL11": 0.20,
    "TNFRSF11B": 0.15,
    "PTGS2": 0.10,
    "TREM1": 0.05,
}
AUDIT_DOMAINS = ("provenance", "identity", "endpoint", "preprocessing", "transport")
CLAIM_DOMAINS = ("identity", "endpoint", "preprocessing", "transport", "evidence")
METRIC_NAMES = (
    "n_patients",
    "auc",
    "auc_ci_low",
    "auc_ci_high",
    "brier",
    "sensitivity",
    "specificity",
    "net_benefit",
    "reviewer_disagreement_rate",
    "reviewer_auc_low",
    "reviewer_auc_high",
)
METRIC_TOLERANCES = {
    "n_patients": 1.0,
    "auc": 0.02,
    "auc_ci_low": 0.04,
    "auc_ci_high": 0.04,
    "brier": 0.02,
    "sensitivity": 0.04,
    "specificity": 0.04,
    "net_benefit": 0.03,
    "reviewer_disagreement_rate": 0.02,
    "reviewer_auc_low": 0.03,
    "reviewer_auc_high": 0.03,
}


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ContractError(f"Cannot read JSON object {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractError(f"Expected JSON object: {path}")
    return value


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"Cannot write empty CSV: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    except OSError as exc:
        raise ContractError(f"Cannot read CSV {path}: {exc}") from exc


def _copy_tree_files(source: Path, destination: Path) -> None:
    for path in source.rglob("*"):
        if path.is_file():
            target = destination / path.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def load_v05_config(project_root: Path) -> dict[str, Any]:
    return _read_object(project_root.resolve() / V05_CONFIG_PATH)


def iter_v05_scenarios(
    project_root: Path, *, partition: str = "development"
) -> list[dict[str, Any]]:
    root = project_root.resolve()
    if partition == "development":
        return [dict(row) for row in load_v05_config(root)["development_scenarios"]]
    if partition == "heldout":
        return [dict(row) for row in _read_object(root / V05_HELDOUT_PATH)["scenarios"]]
    raise ConfigurationError(f"Unknown v0.5 partition: {partition}")


def load_v05_scenario(
    project_root: Path, scenario_id: str, *, partition: str = "development"
) -> dict[str, Any]:
    matches = [
        row
        for row in iter_v05_scenarios(project_root, partition=partition)
        if row["scenario_id"] == scenario_id
    ]
    if len(matches) != 1:
        raise ConfigurationError(
            f"Expected one v0.5 {partition} scenario {scenario_id}; found {len(matches)}"
        )
    return matches[0]


def validate_v05_config(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    config = load_v05_config(root)
    milestones = config.get("milestones", [])
    if len(milestones) != 10:
        raise ContractError("v0.5 requires ten coherent workflow milestones")
    if sum(float(row["weight"]) for row in milestones) != 100.0:
        raise ContractError("v0.5 milestone weights must sum to 100")
    if max(float(row["weight"]) for row in milestones) > 15:
        raise ContractError("No v0.5 milestone may carry more than 15 points")
    development = iter_v05_scenarios(root, partition="development")
    heldout = iter_v05_scenarios(root, partition="heldout")
    if len(development) != 6 or len(heldout) != 6:
        raise ContractError("v0.5 requires six development and six held-out workflow states")
    development_ids = {str(row["scenario_id"]) for row in development}
    heldout_ids = {str(row["scenario_id"]) for row in heldout}
    if development_ids & heldout_ids:
        raise ContractError("Development and held-out scenario IDs must be disjoint")
    classes = {str(row["scenario_class"]) for row in development}
    if classes != {str(row["scenario_class"]) for row in heldout}:
        raise ContractError("Development and held-out partitions must cover the same job states")
    resource_ids = {"none", *(str(row["resource_id"]) for row in config["resource_catalog"])}
    for scenario in [*development, *heldout]:
        if set(scenario["states"]) != {
            "provenance",
            "identity",
            "endpoint",
            "preprocessing",
            "reproduction",
            "transport",
            "evidence",
        }:
            raise ContractError(f"Incomplete private state: {scenario['scenario_id']}")
        if set(scenario["resource_utilities"]) != resource_ids:
            raise ContractError(f"Incomplete resource counterfactuals: {scenario['scenario_id']}")
        if scenario["optimal_resource"] not in resource_ids:
            raise ContractError(f"Unknown optimal resource: {scenario['scenario_id']}")
    heldout_meta = _read_object(root / V05_HELDOUT_PATH)
    return {
        "milestone_count": len(milestones),
        "development_scenario_count": len(development),
        "heldout_scenario_count": len(heldout),
        "scenario_classes": sorted(classes),
        "heldout_sealed_before_model_calls": (
            heldout_meta.get("status") == "sealed_before_any_v05_model_call"
        ),
        "astra_exposure_count": int(heldout_meta.get("astra_exposure_count", -1)),
    }


def _clip(value: float, low: float = 0.001, high: float = 0.999) -> float:
    return min(max(value, low), high)


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


def _score_features(row: dict[str, Any]) -> float:
    logit = -0.10 + sum(MODEL_WEIGHTS[name] * float(row[name]) for name in FEATURES)
    return _sigmoid(logit)


def _cohort_rows(
    *,
    seed: int,
    cohort_id: str,
    patient_count: int,
    signal_strength: float,
    identity_ambiguous: bool,
    endpoint_ambiguous: bool,
    leaky: bool,
    platform: str,
    drug: str,
    endpoint: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Generate predictions, sealed labels, and a private canonical crosswalk."""

    rng = random.Random(seed)
    predictions: list[dict[str, Any]] = []
    outcomes: list[dict[str, Any]] = []
    crosswalk: list[dict[str, Any]] = []
    for patient_index in range(patient_count):
        canonical = f"{cohort_id}-P{patient_index:04d}"
        outcome = int(rng.random() < 0.45)
        patient_latent = 0.5 * signal_strength * (2 * outcome - 1) + rng.gauss(0, 1)
        visit_count = 2 if patient_index % 9 == 0 else 1
        for visit_index in range(visit_count):
            sample_id = f"{cohort_id}-S{patient_index:04d}-{visit_index}"
            reported = canonical
            if identity_ambiguous and visit_index > 0 and patient_index % 18 == 0:
                reported = f"{canonical}-ALIAS"
            batch = f"B{1 + (patient_index % 3)}"
            site = f"SITE-{1 + (patient_index % 5)}"
            latent = patient_latent + rng.gauss(0, 0.10)
            if leaky:
                latent += 0.55 * (2 * outcome - 1)
            feature_values = {
                name: latent + rng.gauss(0, 0.22 + 0.03 * feature_index)
                for feature_index, name in enumerate(FEATURES)
            }
            probability = _score_features(feature_values)
            predictions.append(
                {
                    "sample_id": sample_id,
                    "reported_patient_id": reported,
                    "fingerprint_group": f"FP-{canonical}",
                    "visit_week": 0,
                    "site_id": site,
                    "batch_id": batch,
                    "platform": platform,
                    "drug": drug,
                    "endpoint_definition": endpoint,
                    **{name: round(feature_values[name], 8) for name in FEATURES},
                    "locked_probability": round(probability, 10),
                }
            )
            reviewer_a = outcome
            reviewer_b = outcome
            if endpoint_ambiguous and patient_index % 7 == 0:
                reviewer_b = 1 - outcome
            extraction = reviewer_a if patient_index % 4 else reviewer_b
            outcomes.append(
                {
                    "sample_id": sample_id,
                    "extraction_label": extraction,
                    "reviewer_a": reviewer_a,
                    "reviewer_b": reviewer_b,
                }
            )
            crosswalk.append(
                {
                    "sample_id": sample_id,
                    "reported_patient_id": reported,
                    "canonical_patient_id": canonical,
                    "visit_week": 0,
                    "source_record_status": "reconciled",
                }
            )
    return predictions, outcomes, crosswalk


def _safe_predictions(
    rows: list[dict[str, Any]], outcomes: list[dict[str, Any]], *, seed: int, weak: bool
) -> list[dict[str, Any]]:
    labels = {str(row["sample_id"]): int(row["reviewer_a"]) for row in outcomes}
    rng = random.Random(seed)
    output = []
    strength = 0.22 if weak else 0.78
    for row in rows:
        outcome = labels[str(row["sample_id"])]
        latent = 0.5 * strength * (2 * outcome - 1) + rng.gauss(0, 1)
        values = {
            name: latent + rng.gauss(0, 0.28 + 0.02 * index) for index, name in enumerate(FEATURES)
        }
        output.append(
            {
                "sample_id": row["sample_id"],
                "locked_probability": round(_score_features(values), 10),
            }
        )
    return output


def _reproduction_assets(seed: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rng = random.Random(seed + 301)
    inputs = []
    references = []
    for index in range(12):
        features = {name: rng.gauss(0, 1) for name in FEATURES}
        sample_id = f"AUDIT-{index:03d}"
        inputs.append(
            {
                "sample_id": sample_id,
                **{name: round(features[name], 10) for name in FEATURES},
            }
        )
        references.append(
            {"sample_id": sample_id, "locked_probability": round(_score_features(features), 10)}
        )
    return inputs, references


def _public_cohort_contract(scenario: dict[str, Any]) -> dict[str, str]:
    transfer_failure = scenario["scenario_class"] == "endpoint_drug_platform_transfer_failure"
    return {
        "cohort_id": "EXTERNAL-01",
        "role": "sealed_external_validation",
        "population": "adults_with_moderate_to_severe_ulcerative_colitis",
        "drug": "golimumab" if transfer_failure else "infliximab",
        "endpoint": "week_6_clinical_remission" if transfer_failure else "week_6_clinical_response",
        "platform": "rna_seq_v2" if transfer_failure else "affymetrix_hgu133_plus_2",
    }


def _preprocessing_history(scenario: dict[str, Any]) -> list[dict[str, Any]]:
    leaky = scenario["scenario_class"] == "batch_or_preprocessing_leakage"
    return [
        {
            "step": "background_correction",
            "declared_fit_scope": "per_array",
            "observed_input_cohorts": "each_array_independently",
            "design_fields": "none",
            "executed_after_external_labels_imported": "no",
            "version": "bg-2.1",
        },
        {
            "step": "normalization_reference",
            "declared_fit_scope": "training_only",
            "observed_input_cohorts": (
                "DISCOVERY-01|INTERNAL-01|EXTERNAL-01" if leaky else "DISCOVERY-01"
            ),
            "design_fields": "none",
            "executed_after_external_labels_imported": "no",
            "version": "norm-4.0",
        },
        {
            "step": "probe_to_gene_mapping",
            "declared_fit_scope": "frozen_annotation",
            "observed_input_cohorts": "platform_annotation_files",
            "design_fields": "none",
            "executed_after_external_labels_imported": "no",
            "version": "map-2025-11",
        },
        {
            "step": "batch_adjustment",
            "declared_fit_scope": "training_only",
            "observed_input_cohorts": (
                "DISCOVERY-01|INTERNAL-01|EXTERNAL-01" if leaky else "DISCOVERY-01"
            ),
            "design_fields": "batch_id|week6_response" if leaky else "batch_id",
            "executed_after_external_labels_imported": "yes" if leaky else "no",
            "version": "batch-3.2",
        },
        {
            "step": "model_scoring",
            "declared_fit_scope": "locked_weights",
            "observed_input_cohorts": "INTERNAL-01|EXTERNAL-01",
            "design_fields": "none",
            "executed_after_external_labels_imported": "no",
            "version": "candidate-0.8.3",
        },
    ]


SCORE_SCRIPT = """#!/usr/bin/env python3
import csv, json, math, sys
model = json.load(open("model/locked_model.json", encoding="utf-8"))
with open(sys.argv[1], encoding="utf-8", newline="") as handle:
    rows = list(csv.DictReader(handle))
for row in rows:
    logit = float(model["intercept"]) + sum(
        float(model["weights"][name]) * float(row[name])
        for name in model["feature_names"]
    )
    probability = 1.0 / (1.0 + math.exp(-logit))
    print(f'{row["sample_id"]},{probability:.10f}')
"""


@dataclass(frozen=True, slots=True)
class V05Package:
    scenario_id: str
    partition: str
    workspace_root: Path
    sealed_root: Path
    package_digest: str
    sealed_digest: str
    private_scenario: dict[str, Any]
    schema_root: Path


class V05Builder:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()

    def build(
        self,
        scenario_id: str,
        *,
        output_root: Path,
        partition: str = "development",
        replace: bool = False,
    ) -> V05Package:
        validate_v05_config(self.project_root)
        config = load_v05_config(self.project_root)
        scenario = load_v05_scenario(self.project_root, scenario_id, partition=partition)
        workspace = output_root.resolve() / f"hard5-{scenario_id}"
        sealed = output_root.resolve() / f"hard5-{scenario_id}-sealed"
        for path in (workspace, sealed):
            if path.exists():
                if not replace:
                    raise ConfigurationError(f"v0.5 build path exists: {path}")
                shutil.rmtree(path)
            path.mkdir(parents=True)
        _copy_tree_files(self.project_root / V05_TASK_ROOT, workspace)

        decision = config["decision_contract"]
        external_contract = _public_cohort_contract(scenario)
        _write_json(
            workspace / "case" / "intended_use.json",
            {
                **decision,
                "intended_drug": "infliximab",
                "intended_platform": "affymetrix_hgu133_plus_2",
                "use_context": "research-stage licensing diligence; not clinical deployment",
                "false_positive_consequence": "fund an unsupported prospective programme",
                "false_negative_consequence": "reject a potentially transportable biomarker",
            },
        )
        _write_csv(
            workspace / "case" / "cohort_registry.csv",
            [
                {
                    "cohort_id": "DISCOVERY-01",
                    "role": "training",
                    "population": "moderate_to_severe_uc",
                    "drug": "infliximab",
                    "endpoint": "week_6_clinical_response",
                    "platform": "affymetrix_hgu133_plus_2",
                    "outcomes_visible": "yes",
                },
                {
                    "cohort_id": "INTERNAL-01",
                    "role": "grouped_internal_validation",
                    "population": "moderate_to_severe_uc",
                    "drug": "infliximab",
                    "endpoint": "week_6_clinical_response",
                    "platform": "affymetrix_hgu133_plus_2",
                    "outcomes_visible": "yes",
                },
                {**external_contract, "outcomes_visible": "sealed_until_commitment"},
            ],
        )
        _write_json(
            workspace / "case" / "sponsor_attestations.json",
            {
                "document_type": "sponsor_supplied_summary_not_independently_verified",
                "identity_linkage": "complete",
                "preprocessing_fit_scope": "training_only",
                "endpoint_review": "complete",
                "predictor_status": "locked",
                "instruction": (
                    "Treat these as claims to reconcile against execution records and "
                    "row-level evidence, not as ground truth."
                ),
            },
        )
        _write_json(
            workspace / "case" / "endpoint_definition.json",
            {
                "target": "week_6_clinical_response",
                "source_fields": ["reviewer_a", "reviewer_b", "extraction_label"],
                "extraction_rule": (
                    "Use the abstracted label for primary analysis and quantify the "
                    "effect of blinded reviewer disagreement."
                ),
                "adjudication_status": "not_performed_before_resource_selection",
                "temporal_rule": "baseline inputs only; outcome assessed at week 6",
            },
        )
        _write_csv(
            workspace / "case" / "preprocessing_history.csv",
            _preprocessing_history(scenario),
        )

        identity_ambiguous = scenario["scenario_class"] == "patient_identity_dependence_failure"
        endpoint_ambiguous = scenario["scenario_class"] == "endpoint_label_ambiguity"
        leaky = scenario["scenario_class"] == "batch_or_preprocessing_leakage"
        internal_predictions, internal_outcomes, _ = _cohort_rows(
            seed=int(scenario["seed"]) + 11,
            cohort_id="INTERNAL-01",
            patient_count=96,
            signal_strength=0.95,
            identity_ambiguous=identity_ambiguous,
            endpoint_ambiguous=endpoint_ambiguous,
            leaky=leaky,
            platform="affymetrix_hgu133_plus_2",
            drug="infliximab",
            endpoint="week_6_clinical_response",
        )
        internal_labels = {row["sample_id"]: row for row in internal_outcomes}
        _write_csv(
            workspace / "data" / "internal_predictions.csv",
            [
                {
                    **row,
                    "extraction_label": internal_labels[row["sample_id"]]["extraction_label"],
                    "reviewer_a": internal_labels[row["sample_id"]]["reviewer_a"],
                    "reviewer_b": internal_labels[row["sample_id"]]["reviewer_b"],
                }
                for row in internal_predictions
            ],
        )
        external_predictions, external_outcomes, crosswalk = _cohort_rows(
            seed=int(scenario["seed"]) + 29,
            cohort_id="EXTERNAL-01",
            patient_count=int(scenario["external_n"]),
            signal_strength=float(scenario["signal_strength"]),
            identity_ambiguous=identity_ambiguous,
            endpoint_ambiguous=endpoint_ambiguous,
            leaky=leaky,
            platform=external_contract["platform"],
            drug=external_contract["drug"],
            endpoint=external_contract["endpoint"],
        )
        _write_csv(workspace / "data" / "external_locked_predictions.csv", external_predictions)
        _write_csv(sealed / "validation" / "external_outcomes.csv", external_outcomes)
        _write_json(
            sealed / "validation" / "reveal_provenance.json",
            {
                "cohort_id": "EXTERNAL-01",
                "outcomes_were_sealed": True,
                "predictor_hash_verified": True,
                "revealed_fields": ["extraction_label", "reviewer_a", "reviewer_b"],
            },
        )

        model = {
            "model_id": "locked-rank-linear-0.8.3",
            "feature_names": list(FEATURES),
            "weights": MODEL_WEIGHTS,
            "intercept": -0.10,
            "output": "probability_of_week_6_clinical_response",
            "training_locked": True,
        }
        _write_json(workspace / "model" / "locked_model.json", model)
        model_hash = sha256_file(workspace / "model" / "locked_model.json")
        _write_json(
            workspace / "model" / "predictor_manifest.json",
            {
                "model_id": model["model_id"],
                "model_sha256": model_hash,
                "training_cohort": "DISCOVERY-01",
                "training_sample_count": 118,
                "unit_of_prediction": "baseline_biopsy",
                "patient_grouping_required_for_inference": True,
                "preprocessing_contract": "training-fitted transformations only",
                "claimed_intended_use": (
                    "baseline prediction of week-6 infliximab clinical response"
                ),
            },
        )
        audit_inputs, audit_references = _reproduction_assets(int(scenario["seed"]))
        _write_csv(workspace / "model" / "reproduction_inputs.csv", audit_inputs)
        _write_csv(workspace / "model" / "reference_predictions.csv", audit_references)
        script_path = workspace / "tools" / "score_locked.py"
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text(SCORE_SCRIPT, encoding="utf-8")

        _write_json(
            workspace / "case" / "metric_contract.json",
            {
                "analysis_unit": "patient",
                "recommended_visible_grouping_key": "fingerprint_group",
                "bootstrap_unit": "patient_with_site_preserved_when_possible",
                "bootstrap_replicates": 399,
                "bootstrap_seed": int(scenario["seed"]) + 7001,
                "probability_threshold": decision["probability_threshold"],
                "metric_definitions": {
                    "auc": "ROC AUC of locked probability at the patient analysis unit",
                    "brier": "mean squared probability error",
                    "net_benefit": "TP/n - FP/n * threshold/(1-threshold)",
                    "reviewer_auc_low_high": (
                        "range of AUCs under the two documented reviewer labels"
                    ),
                },
                "method_freedom": "Equivalent dependence-aware uncertainty methods are permitted.",
            },
        )
        _write_json(
            workspace / "resources" / "resource_catalog.json",
            {
                "choose_exactly_one_or_none": True,
                "selection_occurs_after_initial_validation": True,
                "resources": config["resource_catalog"],
            },
        )

        # Counterfactual resource packets are generated before any agent action.
        for resource_id in ("none", "R1", "R2", "R3", "R4", "R5", "R6"):
            packet = sealed / "resources" / resource_id
            packet.mkdir(parents=True)
            if resource_id == "none":
                _write_json(
                    packet / "no_additional_evidence.json",
                    {"resource_id": "none", "new_evidence": False},
                )
            elif resource_id == "R1":
                _write_csv(packet / "patient_visit_crosswalk.csv", crosswalk)
            elif resource_id == "R2":
                _write_csv(
                    packet / "adjudicated_outcomes.csv",
                    [
                        {
                            "sample_id": row["sample_id"],
                            "adjudicated_label": row["reviewer_a"],
                            "adjudication_status": "blinded_source_record_consensus",
                        }
                        for row in external_outcomes
                    ],
                )
            elif resource_id == "R3":
                _write_csv(
                    packet / "leakage_safe_predictions.csv",
                    _safe_predictions(
                        external_predictions,
                        external_outcomes,
                        seed=int(scenario["seed"]) + 503,
                        weak=leaky,
                    ),
                )
                _write_json(
                    packet / "rerun_provenance.json",
                    {
                        "patient_grouped": True,
                        "preprocessing_fit_scope": "training_only",
                        "locked_model_unchanged": True,
                    },
                )
            elif resource_id in {"R4", "R5"}:
                is_bridge = resource_id == "R4"
                followup_n = (
                    92
                    if is_bridge
                    else (
                        58
                        if scenario["scenario_class"]
                        == "underpowered_or_irreducible_external_evidence"
                        else 108
                    )
                )
                if (
                    is_bridge
                    and scenario["scenario_class"] == "endpoint_drug_platform_transfer_failure"
                ):
                    followup_signal = 1.02
                elif (
                    resource_id == "R5"
                    and scenario["scenario_class"]
                    == "underpowered_or_irreducible_external_evidence"
                ):
                    followup_signal = 0.64
                else:
                    followup_signal = float(scenario["signal_strength"])
                new_predictions, new_outcomes, _ = _cohort_rows(
                    seed=int(scenario["seed"]) + (907 if is_bridge else 1201),
                    cohort_id="BRIDGE-01" if is_bridge else "REPLICATION-01",
                    patient_count=followup_n,
                    signal_strength=followup_signal,
                    identity_ambiguous=(identity_ambiguous and not is_bridge),
                    endpoint_ambiguous=(endpoint_ambiguous and not is_bridge),
                    leaky=False,
                    platform="affymetrix_hgu133_plus_2"
                    if is_bridge
                    else external_contract["platform"],
                    drug="infliximab" if is_bridge else external_contract["drug"],
                    endpoint="week_6_clinical_response"
                    if is_bridge
                    else external_contract["endpoint"],
                )
                prefix = "bridge" if is_bridge else "replication"
                _write_csv(packet / f"{prefix}_predictions.csv", new_predictions)
                _write_csv(packet / f"{prefix}_outcomes.csv", new_outcomes)
                _write_json(
                    packet / f"{prefix}_provenance.json",
                    {
                        "independent": True,
                        "endpoint": "week_6_clinical_response"
                        if is_bridge
                        else external_contract["endpoint"],
                        "drug": "infliximab" if is_bridge else external_contract["drug"],
                        "platform": "affymetrix_hgu133_plus_2"
                        if is_bridge
                        else external_contract["platform"],
                    },
                )
            else:
                _write_json(
                    packet / "expert_review.json",
                    {
                        "scope": "review_existing_evidence_only",
                        "new_patient_records": False,
                        "pipeline_rerun": False,
                        "opinion": (
                            "Preserve competing explanations and obtain evidence that "
                            "directly resolves the active blocker."
                        ),
                    },
                )

        _write_json(
            workspace / "case" / "data_room_manifest.json",
            {
                "assets": [
                    {
                        "path": path.relative_to(workspace).as_posix(),
                        "bytes": path.stat().st_size,
                        "sha256": sha256_file(path),
                    }
                    for path in sorted(
                        item
                        for item in workspace.rglob("*")
                        if item.is_file() and "submission" not in item.parts
                    )
                ],
                "known_training_validation_overlap": False,
                "sponsor_attestations_are_unverified": True,
                "license_scope": "benchmark_research_only",
            },
        )
        (workspace / "submission").mkdir(exist_ok=True)
        _write_json(
            workspace / "task.json",
            {
                "schema_version": "0.5",
                "suite_id": config["suite_id"],
                "scenario_id": scenario_id,
                "partition": partition,
                "agent_role": "cross_functional_technical_diligence_lead",
                "workflow_milestones": config["milestones"],
                "capabilities_reported": config["capabilities"],
                "trajectory_budget": config["trajectory_budget"],
                "schemas": {
                    "commitment": "schemas/commitment.schema.json",
                    "validation_assessment": "schemas/validation_assessment.schema.json",
                    "final_submission": "schemas/final_submission.schema.json",
                },
            },
        )
        public_manifest = [
            {
                "path": path.relative_to(workspace).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in sorted(item for item in workspace.rglob("*") if item.is_file())
        ]
        sealed_manifest = [
            {
                "path": path.relative_to(sealed).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in sorted(item for item in sealed.rglob("*") if item.is_file())
        ]
        package_digest = canonical_sha256(public_manifest)
        sealed_digest = canonical_sha256(sealed_manifest)
        _write_json(
            workspace / "START_STATE.json",
            {
                "schema_version": "0.5",
                "suite_id": config["suite_id"],
                "scenario_id": scenario_id,
                "partition": partition,
                "package_digest": package_digest,
                "validation_outcomes_visible": False,
                "followup_resource_visible": False,
                "private_scenario_state_visible": False,
            },
        )
        return V05Package(
            scenario_id=scenario_id,
            partition=partition,
            workspace_root=workspace,
            sealed_root=sealed,
            package_digest=package_digest,
            sealed_digest=sealed_digest,
            private_scenario=scenario,
            schema_root=self.project_root / V05_TASK_ROOT / "schemas",
        )


def _auc(labels: Iterable[int], scores: Iterable[float]) -> float:
    pairs = sorted(zip((float(value) for value in scores), labels, strict=True))
    positives = sum(int(label) == 1 for _, label in pairs)
    negatives = len(pairs) - positives
    if positives == 0 or negatives == 0:
        raise ValueError("AUC requires both outcome classes")
    rank_sum = 0.0
    index = 0
    while index < len(pairs):
        upper = index + 1
        while upper < len(pairs) and pairs[upper][0] == pairs[index][0]:
            upper += 1
        average_rank = ((index + 1) + upper) / 2
        rank_sum += average_rank * sum(int(label) == 1 for _, label in pairs[index:upper])
        index = upper
    return (rank_sum - positives * (positives + 1) / 2) / (positives * negatives)


def _percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("Cannot calculate percentile of an empty collection")
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def _patient_records(
    prediction_rows: list[dict[str, str]],
    outcome_rows: list[dict[str, str]],
    *,
    label_field: str = "extraction_label",
) -> list[dict[str, Any]]:
    outcomes = {str(row["sample_id"]): row for row in outcome_rows}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for prediction in prediction_rows:
        outcome = outcomes.get(str(prediction["sample_id"]))
        if outcome is None:
            continue
        group = str(
            prediction.get("canonical_patient_id")
            or prediction.get("fingerprint_group")
            or prediction["reported_patient_id"]
        )
        selected_label = outcome.get(label_field)
        if selected_label is None:
            selected_label = outcome.get("adjudicated_label", outcome.get("reviewer_a"))
        reviewer_a = outcome.get("reviewer_a", selected_label)
        reviewer_b = outcome.get("reviewer_b", selected_label)
        grouped[group].append(
            {
                "score": float(prediction["locked_probability"]),
                "label": int(selected_label),
                "reviewer_a": int(reviewer_a),
                "reviewer_b": int(reviewer_b),
                "site": str(prediction.get("site_id", "unknown")),
            }
        )
    records = []
    for patient_id, rows in sorted(grouped.items()):
        records.append(
            {
                "patient_id": patient_id,
                "score": mean(float(row["score"]) for row in rows),
                "label": round(mean(int(row["label"]) for row in rows)),
                "reviewer_a": round(mean(int(row["reviewer_a"]) for row in rows)),
                "reviewer_b": round(mean(int(row["reviewer_b"]) for row in rows)),
                "site": str(rows[0]["site"]),
            }
        )
    return records


def _metric_rows(
    workspace_root: Path, *, followup: bool
) -> tuple[list[dict[str, str]], list[dict[str, str]], str]:
    root = workspace_root.resolve()
    prediction_path = root / "data" / "external_locked_predictions.csv"
    outcome_path = root / "revealed" / "external_outcomes.csv"
    label_field = "extraction_label"
    if not prediction_path.is_file() or not outcome_path.is_file():
        raise ContractError("Validation evidence is not available")
    prediction_rows = _read_csv(prediction_path)
    outcome_rows = _read_csv(outcome_path)
    if not followup or not (root / "followup").exists():
        return prediction_rows, outcome_rows, label_field
    if (root / "followup" / "adjudicated_outcomes.csv").exists():
        outcome_rows = _read_csv(root / "followup" / "adjudicated_outcomes.csv")
        label_field = "adjudicated_label"
    if (root / "followup" / "leakage_safe_predictions.csv").exists():
        safe = _read_csv(root / "followup" / "leakage_safe_predictions.csv")
        original = {row["sample_id"]: row for row in prediction_rows}
        prediction_rows = []
        for row in safe:
            base = original[str(row["sample_id"])]
            prediction_rows.append({**base, "locked_probability": row["locked_probability"]})
    for prefix in ("bridge", "replication"):
        candidate_predictions = root / "followup" / f"{prefix}_predictions.csv"
        candidate_outcomes = root / "followup" / f"{prefix}_outcomes.csv"
        if candidate_predictions.exists() and candidate_outcomes.exists():
            prediction_rows = _read_csv(candidate_predictions)
            outcome_rows = _read_csv(candidate_outcomes)
            label_field = "extraction_label"
            break
    return prediction_rows, outcome_rows, label_field


def compute_v05_metrics(workspace_root: Path, *, followup: bool = False) -> dict[str, float]:
    root = workspace_root.resolve()
    prediction_rows, outcome_rows, label_field = _metric_rows(root, followup=followup)
    records = _patient_records(prediction_rows, outcome_rows, label_field=label_field)
    scores = [float(row["score"]) for row in records]
    labels = [int(row["label"]) for row in records]
    reviewer_a = [int(row["reviewer_a"]) for row in records]
    reviewer_b = [int(row["reviewer_b"]) for row in records]
    auc = _auc(labels, scores)
    contract = _read_object(root / "case" / "metric_contract.json")
    rng = random.Random(int(contract["bootstrap_seed"]) + (991 if followup else 0))
    bootstrapped: list[float] = []
    for _ in range(int(contract["bootstrap_replicates"])):
        selected = [records[rng.randrange(len(records))] for _ in records]
        selected_labels = [int(row["label"]) for row in selected]
        if len(set(selected_labels)) < 2:
            continue
        bootstrapped.append(_auc(selected_labels, [float(row["score"]) for row in selected]))
    threshold = float(contract["probability_threshold"])
    predicted = [int(score >= threshold) for score in scores]
    tp = sum(predict == 1 and label == 1 for predict, label in zip(predicted, labels, strict=True))
    fp = sum(predict == 1 and label == 0 for predict, label in zip(predicted, labels, strict=True))
    tn = sum(predict == 0 and label == 0 for predict, label in zip(predicted, labels, strict=True))
    fn = sum(predict == 0 and label == 1 for predict, label in zip(predicted, labels, strict=True))
    sensitivity = tp / (tp + fn) if tp + fn else 0.0
    specificity = tn / (tn + fp) if tn + fp else 0.0
    net_benefit = tp / len(records) - fp / len(records) * threshold / (1 - threshold)
    reviewer_aucs = [_auc(reviewer_a, scores), _auc(reviewer_b, scores)]
    return {
        "n_patients": float(len(records)),
        "auc": auc,
        "auc_ci_low": _percentile(bootstrapped, 0.025),
        "auc_ci_high": _percentile(bootstrapped, 0.975),
        "brier": mean((score - label) ** 2 for score, label in zip(scores, labels, strict=True)),
        "sensitivity": sensitivity,
        "specificity": specificity,
        "net_benefit": net_benefit,
        "reviewer_disagreement_rate": mean(
            first != second for first, second in zip(reviewer_a, reviewer_b, strict=True)
        ),
        "reviewer_auc_low": min(reviewer_aucs),
        "reviewer_auc_high": max(reviewer_aucs),
    }


def _claim_status(value: str) -> str:
    return {
        "clear": "admissible",
        "sufficient": "admissible",
        "conditional": "conditional",
        "underpowered": "conditional",
        "blocked": "blocked",
        "invalid_process": "invalid",
    }.get(value, "conditional")


def expected_initial_claim_statuses(scenario: dict[str, Any]) -> dict[str, str]:
    return {domain: _claim_status(str(scenario["states"][domain])) for domain in CLAIM_DOMAINS}


def expected_intervention_effect(scenario: dict[str, Any], selected: str) -> str:
    if selected == str(scenario["optimal_resource"]):
        return str(scenario["designed_effect"])
    if scenario["scenario_class"] == "clean_enough_progression" and selected == "none":
        return "no_resource_needed"
    if (scenario["scenario_class"], selected) in {
        ("patient_identity_dependence_failure", "R5"),
        ("endpoint_drug_platform_transfer_failure", "R5"),
    }:
        return "misleading_reassurance"
    utility = float(scenario["resource_utilities"].get(selected, 0.0))
    return "reduces_uncertainty_without_resolving" if utility >= 0.25 else "ineffective"


def expected_final_claim_statuses(scenario: dict[str, Any], selected: str) -> dict[str, str]:
    statuses = expected_initial_claim_statuses(scenario)
    if selected != str(scenario["optimal_resource"]):
        return statuses
    scenario_class = str(scenario["scenario_class"])
    if scenario_class == "patient_identity_dependence_failure":
        statuses.update({"identity": "admissible", "evidence": "admissible"})
    elif scenario_class == "endpoint_label_ambiguity":
        statuses.update(
            {"endpoint": "admissible", "transport": "conditional", "evidence": "conditional"}
        )
    elif scenario_class == "batch_or_preprocessing_leakage":
        statuses.update(
            {"preprocessing": "admissible", "transport": "conditional", "evidence": "admissible"}
        )
    elif scenario_class == "endpoint_drug_platform_transfer_failure":
        statuses.update(
            {"endpoint": "admissible", "transport": "admissible", "evidence": "admissible"}
        )
    return statuses


def expected_final_decision(scenario: dict[str, Any], selected: str) -> str:
    if selected == str(scenario["optimal_resource"]):
        return str(scenario["final_decision"])
    return str(scenario["initial_decision"])


def expected_belief_direction(scenario: dict[str, Any], selected: str) -> str:
    effect = expected_intervention_effect(scenario, selected)
    if effect == "resolves_blocker":
        return "increase"
    if effect in {"exposes_second_blocker", "misleading_reassurance"}:
        return "decrease"
    return "unchanged"


def expected_next_action_class(scenario: dict[str, Any], selected: str) -> str:
    decision = expected_final_decision(scenario, selected)
    if decision == "stop" or scenario["scenario_class"] == "clean_enough_progression":
        return "none"
    if scenario["scenario_class"] == "patient_identity_dependence_failure" and selected != "R1":
        return "better_labels_and_metadata"
    if scenario["scenario_class"] == "endpoint_label_ambiguity" and selected != "R2":
        return "expert_assistance"
    if scenario["scenario_class"] == "batch_or_preprocessing_leakage" and selected != "R3":
        return "better_process_or_tools"
    return "additional_data"


def _audit_statuses(scenario: dict[str, Any]) -> dict[str, str]:
    return {domain: str(scenario["states"][domain]) for domain in AUDIT_DOMAINS}


def _model_reproduction(workspace_root: Path) -> dict[str, Any]:
    root = workspace_root.resolve()
    inputs = _read_csv(root / "model" / "reproduction_inputs.csv")
    references = {
        str(row["sample_id"]): float(row["locked_probability"])
        for row in _read_csv(root / "model" / "reference_predictions.csv")
    }
    differences = [abs(_score_features(row) - references[str(row["sample_id"])]) for row in inputs]
    return {
        "predictions_compared": len(inputs),
        "max_abs_error": max(differences),
        "passed": max(differences) <= 1e-8,
        "model_sha256": sha256_file(root / "model" / "locked_model.json"),
    }


def reference_v05_commitment(package: V05Package, project_root: Path) -> dict[str, Any]:
    config = load_v05_config(project_root)
    scenario = package.private_scenario
    statuses = _audit_statuses(scenario)
    return {
        "scenario_id": package.scenario_id,
        "intended_use": {
            "population": config["decision_contract"]["intended_population"],
            "endpoint": config["decision_contract"]["target_endpoint"],
            "prediction_time": config["decision_contract"]["prediction_time"],
            "probability_threshold": config["decision_contract"]["probability_threshold"],
        },
        "audits": {
            domain: {
                "status": statuses[domain],
                "evidence_refs": {
                    "provenance": ["case/data_room_manifest.json", "case/cohort_registry.csv"],
                    "identity": [
                        "data/external_locked_predictions.csv",
                        "case/sponsor_attestations.json",
                    ],
                    "endpoint": [
                        "case/endpoint_definition.json",
                        "case/cohort_registry.csv",
                    ],
                    "preprocessing": ["case/preprocessing_history.csv"],
                    "transport": ["case/cohort_registry.csv", "case/intended_use.json"],
                }[domain],
                "decision_effect": (
                    f"{domain} evidence is {statuses[domain]}; limit only affected claims."
                ),
            }
            for domain in AUDIT_DOMAINS
        },
        "reproduction": _model_reproduction(package.workspace_root),
        "plan": {
            "analysis_unit": "patient",
            "grouping_keys": ["fingerprint_group", "site_id"],
            "uncertainty_unit": "patient_cluster_with_site_preservation",
            "preprocessing_fit_scope": "training_only",
            "primary_estimand": "patient_level_external_auc_calibration_and_threshold_utility",
            "metric_families": [
                "discrimination",
                "uncertainty",
                "calibration",
                "decision_utility",
                "label_sensitivity",
            ],
            "decision_rule": {
                "minimum_auc": config["decision_contract"]["minimum_auc"],
                "minimum_auc_ci_low": config["decision_contract"]["minimum_auc_ci_low"],
                "maximum_brier": config["decision_contract"]["maximum_brier"],
                "minimum_net_benefit": config["decision_contract"]["minimum_net_benefit"],
            },
            "pre_reveal_decision": scenario["initial_decision"],
            "live_hypotheses": [
                str(scenario["scenario_class"]),
                "stable_biological_signal_with_adequate_measurement",
            ],
            "artifact_paths": [
                "model/locked_model.json",
                "model/predictor_manifest.json",
                "data/external_locked_predictions.csv",
                "case/preprocessing_history.csv",
            ],
        },
        "evidence_refs": [
            "case/intended_use.json",
            "case/data_room_manifest.json",
            "case/cohort_registry.csv",
            "case/sponsor_attestations.json",
            "case/endpoint_definition.json",
            "case/preprocessing_history.csv",
            "model/reference_predictions.csv",
        ],
    }


def reference_v05_assessment(package: V05Package, project_root: Path) -> dict[str, Any]:
    scenario = package.private_scenario
    return {
        "scenario_id": package.scenario_id,
        "metrics": compute_v05_metrics(package.workspace_root, followup=False),
        "claim_statuses": expected_initial_claim_statuses(scenario),
        "provisional_decision": scenario["initial_decision"],
        "dominant_uncertainty": str(scenario["scenario_class"]),
        "resource_request": {
            "resource_id": scenario["optimal_resource"],
            "expected_effect": "Distinguish the active blocker from a stable transportable signal.",
            "hypotheses_discriminated": [
                str(scenario["scenario_class"]),
                "stable_biological_signal_with_adequate_measurement",
            ],
        },
        "evidence_refs": [
            "data/external_locked_predictions.csv",
            "revealed/external_outcomes.csv",
            "case/metric_contract.json",
        ],
    }


def reference_v05_submission(package: V05Package) -> dict[str, Any]:
    scenario = package.private_scenario
    selected = str(scenario["optimal_resource"])
    effect = expected_intervention_effect(scenario, selected)
    direction = expected_belief_direction(scenario, selected)
    prior = 0.50
    posterior = {"increase": 0.72, "decrease": 0.28, "unchanged": 0.50}[direction]
    return {
        "scenario_id": package.scenario_id,
        "decision": expected_final_decision(scenario, selected),
        "confidence": 0.78 if effect in {"resolves_blocker", "no_resource_needed"} else 0.62,
        "metrics": compute_v05_metrics(package.workspace_root, followup=True),
        "claim_statuses": expected_final_claim_statuses(scenario, selected),
        "intervention_effect": effect,
        "belief_update": {
            "prior_confidence": prior,
            "posterior_confidence": posterior,
            "direction": direction,
            "explanation": "The selected evidence changed only the claims it directly identified.",
        },
        "smallest_next_action_class": expected_next_action_class(scenario, selected),
        "smallest_next_action": (
            "Take the least costly action consistent with the remaining admissible claims."
        ),
        "supported_claims": [
            {
                "claim": (
                    "The final decision is limited to claims supported by the revealed evidence."
                ),
                "status": "supported",
                "evidence_refs": ["submission/validation_assessment.json", "followup"],
            }
        ],
        "limitations": [
            "This benchmark result is research diligence evidence, not clinical validation."
        ],
        "evidence_refs": [
            "submission/validation_assessment.json",
            "revealed/external_outcomes.csv",
            "followup",
        ],
    }


def _validate_schema(value: dict[str, Any], schema_path: Path, label: str) -> None:
    from jsonschema import Draft202012Validator
    from jsonschema.exceptions import SchemaError, ValidationError

    try:
        schema = _read_object(schema_path)
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(value)
    except (SchemaError, ValidationError) as exc:
        location = ".".join(str(part) for part in getattr(exc, "absolute_path", ()))
        suffix = f" at {location}" if location else ""
        raise ContractError(f"Invalid {label}{suffix}: {exc.message}") from exc


class V05Environment:
    """Filesystem state machine for one ten-milestone diligence episode."""

    def __init__(self, package: V05Package) -> None:
        self.package = package
        self.workspace_root = package.workspace_root.resolve()
        self.commitment: dict[str, Any] | None = None
        self.assessment: dict[str, Any] | None = None
        self.submission: dict[str, Any] | None = None
        self.selected_resource: str | None = None
        self.commitment_hashes: dict[str, str] = {}
        self.commitment_sha256: str | None = None
        self.assessment_sha256: str | None = None
        self.commitment_immutable = False
        self.assessment_immutable = False
        self.phase = "working"
        self.events: list[dict[str, Any]] = []

    def _file(self, relative_path: str) -> Path:
        relative = Path(relative_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise ContractError("Artifact path must remain inside the workspace")
        path = (self.workspace_root / relative).resolve()
        if self.workspace_root not in path.parents or not path.is_file():
            raise ContractError(f"Workspace artifact is missing: {relative_path}")
        return path

    def _record(self, action: str, payload: object) -> None:
        self.events.append(
            {
                "sequence": len(self.events),
                "action": action,
                "phase": self.phase,
                "payload_digest": canonical_sha256(payload),
            }
        )
        _write_json(self.workspace_root / "EVENT_LOG.json", {"events": self.events})

    def _verify_commitment(self) -> None:
        if self.commitment is None:
            raise InvalidTransitionError("No prospective commitment exists")
        current = {path: sha256_file(self._file(path)) for path in self.commitment_hashes}
        if current != self.commitment_hashes:
            self.commitment_immutable = False
            raise ContractError("A committed predictor or analysis artifact changed")
        commitment_path = self._file("submission/commitment.json")
        if sha256_file(commitment_path) != self.commitment_sha256:
            self.commitment_immutable = False
            raise ContractError("The prospective commitment changed after hashing")
        self.commitment_immutable = True

    def _verify_assessment(self) -> None:
        if self.assessment is None or self.assessment_sha256 is None:
            raise InvalidTransitionError("No locked validation assessment exists")
        if (
            sha256_file(self._file("submission/validation_assessment.json"))
            != self.assessment_sha256
        ):
            self.assessment_immutable = False
            raise ContractError("The validation assessment or resource request changed")
        self.assessment_immutable = True

    def commit_validation_plan(self, commitment_path: str = "submission/commitment.json") -> str:
        if self.phase != "working":
            raise InvalidTransitionError("commit_validation_plan is irreversible and may run once")
        path = self._file(commitment_path)
        value = _read_object(path)
        _validate_schema(
            value, self.package.schema_root / "commitment.schema.json", "v0.5 commitment"
        )
        if value["scenario_id"] != self.package.scenario_id:
            raise ContractError("Commitment scenario_id does not match the workspace")
        artifact_paths = [str(item) for item in value["plan"]["artifact_paths"]]
        if "model/locked_model.json" not in artifact_paths:
            raise ContractError("The locked predictor must be included in committed artifacts")
        self.commitment_hashes = {
            relative: sha256_file(self._file(relative)) for relative in artifact_paths
        }
        self.commitment = value
        self.commitment_sha256 = sha256_file(path)
        self.commitment_immutable = True
        self.phase = "committed"
        digest = canonical_sha256({"commitment": value, "artifact_hashes": self.commitment_hashes})
        self._record("commit_validation_plan", {"commitment_digest": digest})
        return digest

    def reveal_validation(self) -> dict[str, Any]:
        if self.phase != "committed":
            raise InvalidTransitionError("reveal_validation requires a committed plan")
        self._verify_commitment()
        source = self.package.sealed_root / "validation"
        target = self.workspace_root / "revealed"
        if target.exists():
            raise InvalidTransitionError("Validation evidence was already revealed")
        shutil.copytree(source, target)
        self.phase = "validation_revealed"
        payload = {
            "revealed_paths": sorted(
                path.relative_to(self.workspace_root).as_posix()
                for path in target.rglob("*")
                if path.is_file()
            ),
            "commitment_immutable": True,
        }
        _write_json(self.workspace_root / "VALIDATION_REVEAL.json", payload)
        self._record("reveal_validation", payload)
        return payload

    def request_followup(
        self, assessment_path: str = "submission/validation_assessment.json"
    ) -> dict[str, Any]:
        if self.phase != "validation_revealed":
            raise InvalidTransitionError("request_followup requires revealed validation evidence")
        self._verify_commitment()
        path = self._file(assessment_path)
        value = _read_object(path)
        _validate_schema(
            value,
            self.package.schema_root / "validation_assessment.schema.json",
            "v0.5 validation assessment",
        )
        if value["scenario_id"] != self.package.scenario_id:
            raise ContractError("Assessment scenario_id does not match the workspace")
        selected = str(value["resource_request"]["resource_id"])
        source = self.package.sealed_root / "resources" / selected
        if not source.is_dir():
            raise ContractError(f"Unknown follow-up resource: {selected}")
        target = self.workspace_root / "followup"
        if target.exists():
            raise InvalidTransitionError("A follow-up resource was already revealed")
        self.assessment = value
        self.assessment_sha256 = sha256_file(path)
        self.assessment_immutable = True
        self.selected_resource = selected
        shutil.copytree(source, target)
        self.phase = "followup_revealed"
        payload = {
            "selected_resource": selected,
            "revealed_paths": sorted(
                path.relative_to(self.workspace_root).as_posix()
                for path in target.rglob("*")
                if path.is_file()
            ),
            "assessment_immutable": True,
        }
        _write_json(self.workspace_root / "FOLLOWUP_REVEAL.json", payload)
        self._record("request_followup", payload)
        return payload

    def submit_diligence(
        self, submission_path: str = "submission/final_submission.json"
    ) -> dict[str, Any]:
        if self.phase != "followup_revealed":
            raise InvalidTransitionError("submit_diligence requires a follow-up reveal")
        self._verify_commitment()
        self._verify_assessment()
        value = _read_object(self._file(submission_path))
        _validate_schema(
            value,
            self.package.schema_root / "final_submission.schema.json",
            "v0.5 final submission",
        )
        if value["scenario_id"] != self.package.scenario_id:
            raise ContractError("Submission scenario_id does not match the workspace")
        self.submission = value
        self.phase = "submitted"
        self._record("submit_diligence", {"decision": value["decision"]})
        return {"accepted": True, "phase": self.phase, "decision": value["decision"]}


def _numeric_credit(expected: float, observed: Any, tolerance: float) -> float:
    try:
        difference = abs(float(observed) - float(expected))
    except (TypeError, ValueError):
        return 0.0
    if difference <= tolerance:
        return 100.0
    return max(0.0, 100.0 * (1 - (difference - tolerance) / (4 * tolerance)))


def _mean(values: Iterable[float]) -> float:
    selected = list(values)
    return mean(selected) if selected else 0.0


def _path_from_reference(reference: str) -> str:
    value = reference.split("#", 1)[0]
    if ":" in value and not Path(value).exists():
        value = value.split(":", 1)[0]
    return value.strip().rstrip("/")


def _reference_exists(workspace_root: Path, reference: str) -> bool:
    relative = Path(_path_from_reference(reference))
    if not str(relative) or relative.is_absolute() or ".." in relative.parts:
        return False
    candidate = (workspace_root.resolve() / relative).resolve()
    return (
        workspace_root.resolve() == candidate
        or workspace_root.resolve() in candidate.parents
        and candidate.exists()
    )


def _evidence_credit(
    workspace_root: Path, references: Iterable[str], required_groups: list[tuple[str, ...]]
) -> float:
    valid = [
        _path_from_reference(str(reference)).lower()
        for reference in references
        if _reference_exists(workspace_root, str(reference))
    ]
    if not required_groups:
        return 100.0
    covered = sum(
        any(any(token.lower() in reference for token in group) for reference in valid)
        for group in required_groups
    )
    return 100.0 * covered / len(required_groups)


def _contains_any(value: Any, tokens: Iterable[str]) -> bool:
    text = str(value).lower().replace("-", "_").replace(" ", "_")
    return any(str(token).lower() in text for token in tokens)


def _status_credit(observed: dict[str, Any], expected: dict[str, str]) -> float:
    return _mean(100.0 * (str(observed.get(name)) == value) for name, value in expected.items())


@dataclass(frozen=True, slots=True)
class V05Grade:
    score: float
    milestone_scores: dict[str, float]
    capability_scores: dict[str, float]
    expected_initial_decision: str
    expected_final_decision: str
    observed_initial_decision: str | None
    observed_final_decision: str | None
    decision_correct: bool
    selected_resource: str
    optimal_resource: str
    resource_utility: float
    expected_intervention_effect: str
    observed_intervention_effect: str | None
    belief_revision_correct: bool
    final_claim_status_score: float
    metric_scores_initial: dict[str, float]
    metric_scores_final: dict[str, float]
    commitment_immutable: bool
    assessment_immutable: bool
    observed_evidence: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "milestone_scores": self.milestone_scores,
            "capability_scores": self.capability_scores,
            "expected_initial_decision": self.expected_initial_decision,
            "expected_final_decision": self.expected_final_decision,
            "observed_initial_decision": self.observed_initial_decision,
            "observed_final_decision": self.observed_final_decision,
            "decision_correct": self.decision_correct,
            "selected_resource": self.selected_resource,
            "optimal_resource": self.optimal_resource,
            "resource_utility": self.resource_utility,
            "expected_intervention_effect": self.expected_intervention_effect,
            "observed_intervention_effect": self.observed_intervention_effect,
            "belief_revision_correct": self.belief_revision_correct,
            "final_claim_status_score": self.final_claim_status_score,
            "metric_scores_initial": self.metric_scores_initial,
            "metric_scores_final": self.metric_scores_final,
            "commitment_immutable": self.commitment_immutable,
            "assessment_immutable": self.assessment_immutable,
            "observed_evidence": self.observed_evidence,
        }


def grade_v05(
    project_root: Path,
    package: V05Package,
    commitment: dict[str, Any] | None,
    assessment: dict[str, Any] | None,
    submission: dict[str, Any] | None,
    *,
    selected_resource: str | None,
    commitment_immutable: bool,
    assessment_immutable: bool,
) -> V05Grade:
    root = package.workspace_root.resolve()
    scenario = package.private_scenario
    config = load_v05_config(project_root)
    selected = selected_resource or "none"
    commitment_value = commitment or {}
    assessment_value = assessment or {}
    submission_value = submission or {}
    intended = commitment_value.get("intended_use") or {}
    audits = commitment_value.get("audits") or {}
    plan = commitment_value.get("plan") or {}
    reproduction = commitment_value.get("reproduction") or {}
    commit_refs = commitment_value.get("evidence_refs") or []
    expected_audits = _audit_statuses(scenario)
    decision_contract = config["decision_contract"]

    m01_properties = [
        100.0 * (intended.get("population") == decision_contract["intended_population"]),
        100.0 * (intended.get("endpoint") == decision_contract["target_endpoint"]),
        100.0 * (intended.get("prediction_time") == decision_contract["prediction_time"]),
        _numeric_credit(
            decision_contract["probability_threshold"],
            intended.get("probability_threshold"),
            0.01,
        ),
        _evidence_credit(root, commit_refs, [("case/intended_use",)]),
    ]
    milestone_scores: dict[str, float] = {"M01": _mean(m01_properties)}

    provenance = audits.get("provenance") or {}
    milestone_scores["M02"] = _mean(
        [
            100.0 * (provenance.get("status") == expected_audits["provenance"]),
            _evidence_credit(
                root,
                provenance.get("evidence_refs") or [],
                [("data_room_manifest",), ("cohort_registry",)],
            ),
            100.0 * bool(str(provenance.get("decision_effect", "")).strip()),
        ]
    )

    identity = audits.get("identity") or {}
    grouping = plan.get("grouping_keys") or []
    identity_grouping_ok = any(
        _contains_any(item, ("patient", "subject", "fingerprint")) for item in grouping
    )
    if expected_audits["identity"] == "blocked":
        identity_grouping_ok = any(_contains_any(item, ("fingerprint",)) for item in grouping)
    milestone_scores["M03"] = _mean(
        [
            100.0 * (identity.get("status") == expected_audits["identity"]),
            100.0 * _contains_any(plan.get("analysis_unit"), ("patient", "subject")),
            100.0 * identity_grouping_ok,
            100.0 * _contains_any(plan.get("uncertainty_unit"), ("patient", "subject", "cluster")),
            _evidence_credit(
                root,
                identity.get("evidence_refs") or [],
                [
                    ("external_locked_predictions", "internal_predictions"),
                    ("sponsor_attestations", "data_room_manifest"),
                ],
            ),
        ]
    )

    endpoint = audits.get("endpoint") or {}
    metric_families = plan.get("metric_families") or []
    label_sensitivity = any(
        _contains_any(item, ("label", "endpoint", "sensitivity")) for item in metric_families
    )
    milestone_scores["M04"] = _mean(
        [
            100.0 * (endpoint.get("status") == expected_audits["endpoint"]),
            100.0 * (intended.get("endpoint") == decision_contract["target_endpoint"]),
            100.0 * label_sensitivity,
            _evidence_credit(
                root,
                endpoint.get("evidence_refs") or [],
                [("intended_use", "endpoint_definition"), ("cohort_registry",)],
            ),
        ]
    )

    preprocessing = audits.get("preprocessing") or {}
    transport = audits.get("transport") or {}
    milestone_scores["M05"] = _mean(
        [
            100.0 * (preprocessing.get("status") == expected_audits["preprocessing"]),
            100.0 * _contains_any(plan.get("preprocessing_fit_scope"), ("training", "train_only")),
            100.0 * (transport.get("status") == expected_audits["transport"]),
            _evidence_credit(
                root,
                [
                    *(preprocessing.get("evidence_refs") or []),
                    *(transport.get("evidence_refs") or []),
                ],
                [("preprocessing_history",), ("cohort_registry", "intended_use")],
            ),
        ]
    )

    expected_reproduction = _model_reproduction(root)
    milestone_scores["M06"] = _mean(
        [
            100.0 * bool(reproduction.get("passed")),
            100.0 * (float(reproduction.get("predictions_compared", 0)) >= 10),
            _numeric_credit(
                expected_reproduction["max_abs_error"],
                reproduction.get("max_abs_error"),
                1e-8,
            ),
            100.0 * (reproduction.get("model_sha256") == expected_reproduction["model_sha256"]),
            _evidence_credit(root, commit_refs, [("model/reference_predictions",)]),
        ]
    )

    required_metric_concepts = ("discrimination", "uncertainty", "calibration", "utility")
    metric_coverage = _mean(
        100.0 * any(_contains_any(item, (concept,)) for item in metric_families)
        for concept in required_metric_concepts
    )
    rule = plan.get("decision_rule") or {}
    rule_credit = _mean(
        _numeric_credit(decision_contract[name], rule.get(name), 0.01)
        for name in (
            "minimum_auc",
            "minimum_auc_ci_low",
            "maximum_brier",
            "minimum_net_benefit",
        )
    )
    artifact_paths = set(str(item) for item in plan.get("artifact_paths") or [])
    milestone_scores["M07"] = (
        25.0 * commitment_immutable
        + 25.0 * metric_coverage / 100
        + 20.0 * rule_credit / 100
        + 15.0 * (len(set(plan.get("live_hypotheses") or [])) >= 2)
        + 15.0 * ("model/locked_model.json" in artifact_paths and len(artifact_paths) >= 3)
    )

    try:
        expected_initial_metrics = compute_v05_metrics(root, followup=False)
    except (ContractError, ValueError):
        expected_initial_metrics = {name: 0.0 for name in METRIC_NAMES}
    observed_initial_metrics = assessment_value.get("metrics") or {}
    initial_metric_scores = {
        name: _numeric_credit(
            expected_initial_metrics[name],
            observed_initial_metrics.get(name),
            METRIC_TOLERANCES[name],
        )
        for name in METRIC_NAMES
    }
    initial_statuses = expected_initial_claim_statuses(scenario)
    milestone_scores["M08"] = (
        0.55 * _mean(initial_metric_scores.values())
        + 0.20 * _status_credit(assessment_value.get("claim_statuses") or {}, initial_statuses)
        + 15.0 * (assessment_value.get("provisional_decision") == scenario["initial_decision"])
        + 0.10
        * _evidence_credit(
            root,
            assessment_value.get("evidence_refs") or [],
            [("external_locked_predictions",), ("external_outcomes",), ("metric_contract",)],
        )
    )

    resource_request = assessment_value.get("resource_request") or {}
    resource_utility = float(scenario["resource_utilities"].get(selected, 0.0))
    expected_effect = expected_intervention_effect(scenario, selected)
    milestone_scores["M09"] = (
        45.0 * resource_utility
        + 10.0 * (len(resource_request.get("hypotheses_discriminated") or []) >= 1)
        + 15.0 * assessment_immutable
        + 20.0 * (submission_value.get("intervention_effect") == expected_effect)
        + 0.10
        * _evidence_credit(
            root,
            submission_value.get("evidence_refs") or [],
            [("followup",), ("validation_assessment",)],
        )
    )

    try:
        expected_final_metrics = compute_v05_metrics(root, followup=True)
    except (ContractError, ValueError):
        expected_final_metrics = expected_initial_metrics
    observed_final_metrics = submission_value.get("metrics") or {}
    final_metric_scores = {
        name: _numeric_credit(
            expected_final_metrics[name], observed_final_metrics.get(name), METRIC_TOLERANCES[name]
        )
        for name in METRIC_NAMES
    }
    expected_final_status = expected_final_claim_statuses(scenario, selected)
    final_claim_status_score = _status_credit(
        submission_value.get("claim_statuses") or {}, expected_final_status
    )
    belief = submission_value.get("belief_update") or {}
    supported_claim_refs = [
        reference
        for claim in submission_value.get("supported_claims") or []
        for reference in claim.get("evidence_refs") or []
    ]
    milestone_scores["M10"] = (
        30.0 * (submission_value.get("decision") == expected_final_decision(scenario, selected))
        + 15.0 * final_claim_status_score / 100
        + 15.0
        * (
            submission_value.get("smallest_next_action_class")
            == expected_next_action_class(scenario, selected)
        )
        + 15.0 * (belief.get("direction") == expected_belief_direction(scenario, selected))
        + 10.0 * (len(submission_value.get("limitations") or []) >= 1)
        + 0.05 * _mean(final_metric_scores.values())
        + 0.10
        * _evidence_credit(
            root,
            [*(submission_value.get("evidence_refs") or []), *supported_claim_refs],
            [("validation_assessment",), ("followup", "external_outcomes")],
        )
    )

    milestone_scores = {
        name: round(min(max(float(value), 0.0), 100.0), 6)
        for name, value in milestone_scores.items()
    }
    weights = {str(row["id"]): float(row["weight"]) for row in config["milestones"]}
    score = sum(weights[name] * milestone_scores[name] / 100 for name in weights)
    capability_map = {
        "data_integrity": ("M02", "M03"),
        "endpoint_reasoning": ("M01", "M04"),
        "statistical_validity": ("M03", "M07", "M08"),
        "leakage_prevention": ("M05", "M07", "M08"),
        "transportability": ("M01", "M05", "M08"),
        "calibration_and_decision_utility": ("M01", "M07", "M08"),
        "experimental_design_value_of_information": ("M09", "M10"),
        "belief_revision": ("M09", "M10"),
        "reproducibility": ("M02", "M06", "M07"),
        "graceful_abstention": ("M08", "M10"),
    }
    capabilities = {
        capability: round(_mean(milestone_scores[item] for item in items), 6)
        for capability, items in capability_map.items()
    }
    active_blockers = [
        name
        for name, status in expected_initial_claim_statuses(scenario).items()
        if status in {"blocked", "invalid", "conditional"}
    ]
    return V05Grade(
        score=round(score, 6),
        milestone_scores=milestone_scores,
        capability_scores=capabilities,
        expected_initial_decision=str(scenario["initial_decision"]),
        expected_final_decision=expected_final_decision(scenario, selected),
        observed_initial_decision=assessment_value.get("provisional_decision"),
        observed_final_decision=submission_value.get("decision"),
        decision_correct=(
            submission_value.get("decision") == expected_final_decision(scenario, selected)
        ),
        selected_resource=selected,
        optimal_resource=str(scenario["optimal_resource"]),
        resource_utility=resource_utility,
        expected_intervention_effect=expected_effect,
        observed_intervention_effect=submission_value.get("intervention_effect"),
        belief_revision_correct=(
            belief.get("direction") == expected_belief_direction(scenario, selected)
        ),
        final_claim_status_score=round(final_claim_status_score, 6),
        metric_scores_initial={
            name: round(value, 6) for name, value in initial_metric_scores.items()
        },
        metric_scores_final={name: round(value, 6) for name, value in final_metric_scores.items()},
        commitment_immutable=commitment_immutable,
        assessment_immutable=assessment_immutable,
        observed_evidence={
            "scenario_class": scenario["scenario_class"],
            "active_initial_blockers": active_blockers,
            "initial_metrics": expected_initial_metrics,
            "followup_metrics": expected_final_metrics,
            "intervention_effect": expected_effect,
            "decision_transition": [
                scenario["initial_decision"],
                expected_final_decision(scenario, selected),
            ],
        },
    )


def run_reference_v05_episode(
    project_root: Path,
    scenario_id: str,
    *,
    output_root: Path,
    partition: str = "development",
    replace: bool = False,
) -> tuple[V05Package, V05Environment, V05Grade]:
    """Build, execute, and grade one deterministic expert-equivalent trajectory."""

    package = V05Builder(project_root).build(
        scenario_id,
        output_root=output_root,
        partition=partition,
        replace=replace,
    )
    environment = V05Environment(package)
    commitment = reference_v05_commitment(package, project_root)
    _write_json(package.workspace_root / "submission" / "commitment.json", commitment)
    environment.commit_validation_plan()
    environment.reveal_validation()
    assessment = reference_v05_assessment(package, project_root)
    _write_json(package.workspace_root / "submission" / "validation_assessment.json", assessment)
    environment.request_followup()
    submission = reference_v05_submission(package)
    _write_json(package.workspace_root / "submission" / "final_submission.json", submission)
    environment.submit_diligence()
    grade = grade_v05(
        project_root,
        package,
        environment.commitment,
        environment.assessment,
        environment.submission,
        selected_resource=environment.selected_resource,
        commitment_immutable=environment.commitment_immutable,
        assessment_immutable=environment.assessment_immutable,
    )
    _write_json(
        package.workspace_root / "REFERENCE_GRADE.json",
        grade.to_dict(),
    )
    return package, environment, grade

"""Quantitatively demanding v0.4 biomedical-statistical hard suite."""

from __future__ import annotations

import csv
import itertools
import math
import random
import shutil
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any

from uc_bench.errors import ConfigurationError, ContractError, InvalidTransitionError
from uc_bench.hard_suite import (
    _auc,
    _numeric_credit,
    _read_csv,
    _read_object,
    _validate_schema,
    _write_json,
)
from uc_bench.hashing import canonical_sha256, sha256_file

V04_CONFIG_PATH = Path("configs/hard_suite_v04.json")
V04_HELDOUT_PATH = Path("grader_private/hard_suite_v04_heldout.json")
V04_LADDERS_PATH = Path("grader_private/hard_suite_v04_ladders.json")

EVIDENCE_IDS = {
    "EV-PILOT": ["data/pilot.csv"],
    "EV-ANALYSIS-CONTRACT": ["analysis_contract.json"],
    "EV-DECISION-CONTEXT": ["case/decision_context.json"],
    "EV-RESOURCE": ["resources/resource_catalog.json", "evidence/selected_resource.json"],
    "EV-ANALYSIS": ["evidence/analysis.csv"],
    "EV-PROVENANCE": ["evidence/provenance.json"],
}

METRIC_DEFINITIONS = {
    "row_auc": "ROC AUC over biopsy rows using naive_score.",
    "patient_auc": "ROC AUC after grouping by cluster_id and averaging locked_score.",
    "patient_auc_ci_low": "2.5th percentile of the fixed-seed patient-cluster bootstrap.",
    "patient_auc_ci_high": "97.5th percentile of the fixed-seed patient-cluster bootstrap.",
    "unique_patient_units": "Number of unique cluster_id inference units.",
    "kish_effective_n": "Squared row count divided by the sum of squared cluster sizes.",
    "leakage_inflation": "row_auc minus patient_auc.",
    "identity_conflict_count": (
        "Number of cluster_id groups spanning multiple reported_patient_id values."
    ),
    "unmatched_auc": "ROC AUC in factorial cell endpoint=drug=platform=0.",
    "all_matched_auc": "ROC AUC in factorial cell endpoint=drug=platform=1.",
    "endpoint_main_effect": "Average cell AUC at endpoint_match=1 minus its average at 0.",
    "drug_main_effect": "Average cell AUC at drug_match=1 minus its average at 0.",
    "platform_main_effect": "Average cell AUC at platform_match=1 minus its average at 0.",
    "three_way_interaction": (
        "AUC-scale endpoint × drug × platform difference-in-differences-in-differences."
    ),
    "dominant_factor_effect": "Largest absolute main-effect contrast, retaining its sign.",
    "dominant_factor_ci_low": (
        "2.5th percentile of the fixed-seed site-cluster bootstrap for the selected "
        "dominant factor."
    ),
    "dominant_factor_ci_high": (
        "97.5th percentile of the fixed-seed site-cluster bootstrap for the selected "
        "dominant factor."
    ),
    "naive_auc": "Row-pooled ROC AUC using naive_score.",
    "patient_grouped_auc": "ROC AUC after patient aggregation using grouped_score.",
    "batch_blocked_auc": (
        "Patient-level AUC computed within batch and averaged by evaluable patient count."
    ),
    "naive_minus_blocked_auc": "naive_auc minus batch_blocked_auc.",
    "batch_outcome_phi": "Signed binary phi coefficient for batch=1 and patient outcome=1.",
    "within_batch_permutation_p": (
        "Plus-one permutation p-value after shuffling patient labels within batch."
    ),
    "global_permutation_p": "Plus-one p-value after globally shuffling patient labels.",
    "reviewer_agreement": "Fraction of records with equal reviewer_a and reviewer_b labels.",
    "cohen_kappa": "Cohen's kappa between reviewer_a and reviewer_b.",
    "ambiguous_fraction": "Fraction of records with reviewer disagreement.",
    "extracted_auc": "ROC AUC against extraction_label.",
    "sensitivity_auc_low": "Minimum AUC over all assignments of reviewer-discordant labels.",
    "sensitivity_auc_high": "Maximum AUC over all assignments of reviewer-discordant labels.",
    "adjudicated_auc": "ROC AUC against blinded adjudicated_label when delivered.",
    "adjudication_auc_change": "adjudicated_auc minus extracted_auc.",
    "observed_sample_size": "Number of patients in the intended-use replication.",
    "auc": "ROC AUC in the intended-use replication.",
    "auc_ci_low": "2.5th percentile of the fixed-seed site-cluster bootstrap.",
    "auc_ci_high": "97.5th percentile of the fixed-seed site-cluster bootstrap.",
    "brier_score": "Mean squared error between locked probability and observed outcome.",
    "sensitivity": "Sensitivity at the prespecified probability threshold.",
    "specificity": "Specificity at the prespecified probability threshold.",
    "target_prevalence_ppv": "PPV standardised to the prespecified intended-use prevalence.",
    "net_benefit": "Prevalence-standardised decision-curve net benefit at the threshold.",
    "required_sample_size": "Current n scaled by squared CI half-width relative to its target.",
}

FAMILY_SEMANTICS = {
    "Q01_identity_dependence": {
        "candidate_hypotheses": [
            "patient_dependence_and_identity_ambiguity",
            "true_biological_signal",
            "row_sampling_noise",
        ],
        "candidate_interpretations": [
            "row_inference_invalid_patient_signal_uncertain",
            "reconciliation_supports_patient_level_evidence",
            "row_level_performance_is_sufficient",
        ],
        "uncertainty_unit": "patient_cluster",
    },
    "Q02_transport_factorial": {
        "candidate_hypotheses": [
            "endpoint_drug_platform_transport_interaction",
            "endpoint_main_effect_only",
            "drug_main_effect_only",
            "platform_main_effect_only",
            "sampling_noise",
        ],
        "candidate_interpretations": [
            "factorial_transport_effect_unresolved",
            "joint_bridge_supports_intended_transfer",
            "pooled_auc_supports_transfer",
        ],
        "uncertainty_unit": "site_cluster",
    },
    "Q03_process_confounding": {
        "candidate_hypotheses": [
            "batch_confounding_and_split_leakage",
            "residual_model_uncertainty",
            "stable_biological_signal",
        ],
        "candidate_interpretations": [
            "naive_performance_is_batch_driven",
            "process_fixed_scientific_evidence_unresolved",
            "safe_validation_supports_signal",
        ],
        "uncertainty_unit": "patient_within_batch",
    },
    "Q04_label_sensitivity": {
        "candidate_hypotheses": [
            "ambiguous_endpoint_labels",
            "stable_predictive_signal",
            "random_reviewer_noise",
        ],
        "candidate_interpretations": [
            "label_sensitivity_crosses_decision_boundary",
            "adjudication_supports_locked_model",
            "complete_cases_are_sufficient",
        ],
        "uncertainty_unit": "patient_label_assignment",
    },
    "Q05_decision_sufficiency": {
        "candidate_hypotheses": [
            "underpowered_decision_evidence",
            "model_miscalibration",
            "adequate_intended_use_utility",
        ],
        "candidate_interpretations": [
            "decision_uncertainty_remains_material",
            "replication_supports_intended_use_utility",
            "auc_alone_is_sufficient",
        ],
        "uncertainty_unit": "site_cluster",
    },
}


def load_v04_config(project_root: Path) -> dict[str, Any]:
    return _read_object(project_root.resolve() / V04_CONFIG_PATH)


def iter_v04_variants(
    project_root: Path, *, partition: str = "development"
) -> list[dict[str, Any]]:
    root = project_root.resolve()
    config = load_v04_config(root)
    by_family = {str(pair["family_id"]): pair for pair in config["development_pairs"]}
    output: list[dict[str, Any]] = []
    if partition == "development":
        for pair in config["development_pairs"]:
            for role in ("control", "treated"):
                item = pair[role]
                output.append(
                    {
                        **{
                            key: value
                            for key, value in pair.items()
                            if key not in {"control", "treated"}
                        },
                        "variant_id": item["variant_id"],
                        "pair_role": role,
                        "correct_resource_available": bool(item["correct_resource_available"]),
                        "expected_resource_id": (
                            str(pair["correct_resource_id"])
                            if item["correct_resource_available"]
                            else "none"
                        ),
                    }
                )
        return output
    if partition == "heldout":
        heldout = _read_object(root / V04_HELDOUT_PATH)
        for pair in heldout["pairs"]:
            public = by_family[str(pair["family_id"])]
            for role, field in (
                ("control", "control_variant_id"),
                ("treated", "treated_variant_id"),
            ):
                output.append(
                    {
                        **pair,
                        "resources": public["resources"],
                        "variant_id": pair[field],
                        "pair_role": role,
                        "correct_resource_available": role == "treated",
                        "expected_resource_id": (
                            str(pair["correct_resource_id"]) if role == "treated" else "none"
                        ),
                    }
                )
        return output
    raise ConfigurationError(f"Unknown v0.4 partition: {partition}")


def load_v04_variant(
    project_root: Path, variant_id: str, *, partition: str = "development"
) -> dict[str, Any]:
    matches = [
        row
        for row in iter_v04_variants(project_root, partition=partition)
        if row["variant_id"] == variant_id
    ]
    if len(matches) != 1:
        raise ConfigurationError(
            f"Expected one v0.4 {partition} variant {variant_id}; found {len(matches)}"
        )
    return matches[0]


def validate_v04_config(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    config = load_v04_config(root)
    pairs = config.get("development_pairs")
    if not isinstance(pairs, list) or len(pairs) != 5:
        raise ContractError("v0.4 requires five failure families")
    if not math.isclose(sum(config["scoring"].values()), 1.0):
        raise ContractError("v0.4 scoring weights must sum to one")
    if config["scoring"].get("quantitative_statistical_reasoning") != 0.30:
        raise ContractError("v0.4 quantitative weight must be 30%")
    development_ids: set[str] = set()
    for pair in pairs:
        resources = pair.get("resources")
        if not isinstance(resources, list) or {row["resource_id"] for row in resources} != {
            "R1",
            "R2",
            "R3",
        }:
            raise ContractError(f"Invalid resource catalog: {pair['family_id']}")
        for role in ("control", "treated"):
            variant_id = str(pair[role]["variant_id"])
            if variant_id in development_ids:
                raise ContractError(f"Duplicate development variant: {variant_id}")
            development_ids.add(variant_id)
        contract = config["analysis_contracts"].get(pair["family_id"])
        if not contract or len(contract["required_metrics"]) < 7:
            raise ContractError(f"Incomplete quantitative contract: {pair['family_id']}")
        if set(contract["required_metrics"]) - set(contract["metric_tolerances"]):
            raise ContractError(f"Missing metric tolerance: {pair['family_id']}")
    heldout = iter_v04_variants(root, partition="heldout")
    if len(heldout) != 10:
        raise ContractError("v0.4 requires ten held-out variants")
    return {
        "family_count": 5,
        "development_variant_count": len(development_ids),
        "heldout_variant_count": len(heldout),
        "quantitative_weight": config["scoring"]["quantitative_statistical_reasoning"],
        "heldout_frozen_before_astra": bool(
            _read_object(root / V04_HELDOUT_PATH)["frozen_before_astra"]
        ),
        "maximum_turns": config["trajectory_budget"]["maximum_turns"],
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"Cannot write empty CSV: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _clip(value: float, lower: float = 0.001, upper: float = 0.999) -> float:
    return min(max(value, lower), upper)


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


def _generate_identity(seed: int, selection: str, effective: bool) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    patient_count = 44 if selection != "R1" else 58
    rows = []
    for patient in range(patient_count):
        label = patient % 2
        repeats = 2 + int(patient % 5 == 0)
        patient_noise = rng.gauss(0, 0.7)
        locked = _sigmoid(-0.15 + 1.05 * label + patient_noise)
        for visit in range(repeats):
            naive = _clip(locked + (0.18 if label else -0.18) + rng.gauss(0, 0.04))
            reported = f"P-{patient:03d}"
            if not effective and patient < max(8, patient_count // 5) and visit > 0:
                reported = f"P-{patient:03d}-V{visit}"
            rows.append(
                {
                    "row_id": f"B-{patient:03d}-{visit}",
                    "cluster_id": f"FP-{patient:03d}",
                    "reported_patient_id": reported,
                    "visit_id": f"V{visit}",
                    "label": label,
                    "naive_score": round(naive, 8),
                    "locked_score": round(locked + rng.gauss(0, 0.025), 8),
                }
            )
    return rows


def _generate_transport(seed: int, selection: str, effective: bool) -> list[dict[str, Any]]:
    per_cell = 18
    if selection == "R2":
        per_cell = 28
    if effective:
        per_cell = 80
    rows = []
    for endpoint, drug, platform in itertools.product((0, 1), repeat=3):
        rng = random.Random(seed + 100 * endpoint + 10 * drug + platform)
        for index in range(per_cell):
            label = index % 2
            joint = endpoint * drug * platform
            separation = 0.05 + 0.28 * endpoint + 0.08 * drug + 0.04 * platform
            separation += (0.80 if effective else 0.10) * joint
            if selection == "R2" and endpoint == 0:
                separation += 0.03
            latent = separation * (1 if label else -1) + rng.gauss(0, 1.0)
            rows.append(
                {
                    "row_id": f"T-{endpoint}{drug}{platform}-{index:03d}",
                    "site_id": f"SITE-{(index // 2) % (12 if effective else 6)}",
                    "endpoint_match": endpoint,
                    "drug_match": drug,
                    "platform_match": platform,
                    "label": label,
                    "locked_score": round(_sigmoid(latent), 8),
                }
            )
    return rows


def _generate_process(seed: int, selection: str, effective: bool) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    patient_count = 64 if selection != "R2" else 92
    rows = []
    for patient in range(patient_count):
        batch = patient % 2
        probability = 0.76 if batch else 0.24
        label = int(rng.random() < probability)
        biological = (0.08 if effective else 0.12) * (1 if label else -1)
        batch_signal = 0.0 if effective else 1.15 * (1 if batch else -1)
        for visit in range(2):
            base_noise = rng.gauss(0, 0.8)
            naive = _sigmoid(biological + batch_signal + base_noise)
            grouped = _sigmoid(biological + 0.75 * batch_signal + base_noise)
            blocked = _sigmoid(biological + base_noise)
            rows.append(
                {
                    "row_id": f"C-{patient:03d}-{visit}",
                    "patient_id": f"P-{patient:03d}",
                    "batch": batch,
                    "label": label,
                    "naive_score": round(naive, 8),
                    "grouped_score": round(grouped, 8),
                    "blocked_score": round(blocked, 8),
                }
            )
    return rows


def _generate_labels(seed: int, selection: str, effective: bool) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    sample_count = 54 if selection != "R1" else 82
    rows = []
    ambiguous_target = 12 if sample_count == 54 else 18
    for index in range(sample_count):
        true_label = index % 2
        latent = 0.65 * (1 if true_label else -1) + rng.gauss(0, 1.0)
        score = _sigmoid(latent)
        ambiguous = index < ambiguous_target
        reviewer_a = true_label
        reviewer_b = 1 - true_label if ambiguous else true_label
        extraction = reviewer_b if ambiguous and index % 3 != 0 else true_label
        rows.append(
            {
                "sample_id": f"L-{index:03d}",
                "locked_score": round(score, 8),
                "extraction_label": extraction,
                "reviewer_a": reviewer_a,
                "reviewer_b": reviewer_b,
                "adjudicated_label": true_label if effective else "",
            }
        )
    return rows


def _generate_evidence(seed: int, selection: str, effective: bool) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    sample_count = 42
    if selection == "R2":
        sample_count = 66
    if effective:
        sample_count = 168
    rows = []
    for index in range(sample_count):
        site = index % (6 if sample_count < 100 else 12)
        latent_risk = rng.gauss(-0.35, 1.0)
        probability = _sigmoid((1.35 if effective else 1.0) * latent_risk - 0.15 * effective)
        outcome_probability = _sigmoid((1.65 if effective else 1.15) * latent_risk - 0.25)
        label = int(rng.random() < outcome_probability)
        score = _clip(probability + rng.gauss(0, 0.045 if effective else 0.075))
        rows.append(
            {
                "sample_id": f"E-{index:03d}",
                "site_id": f"SITE-{site:02d}",
                "label": label,
                "locked_probability": round(score, 8),
            }
        )
    return rows


GENERATORS: dict[str, Callable[[int, str, bool], list[dict[str, Any]]]] = {
    "Q01_identity_dependence": _generate_identity,
    "Q02_transport_factorial": _generate_transport,
    "Q03_process_confounding": _generate_process,
    "Q04_label_sensitivity": _generate_labels,
    "Q05_decision_sufficiency": _generate_evidence,
}


def _copy_tree_files(source: Path, destination: Path) -> None:
    for path in sorted(item for item in source.rglob("*") if item.is_file()):
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)


def _resource_catalog(variant: dict[str, Any]) -> dict[str, Any]:
    resources = []
    for resource in variant["resources"]:
        row = dict(resource)
        row["available"] = not (
            resource["resource_id"] == variant["correct_resource_id"]
            and not variant["correct_resource_available"]
        )
        resources.append(row)
    return {
        "selection_budget": 1,
        "none_is_allowed": True,
        "resources": resources,
        "selection_rule": (
            "Choose the smallest available resource that identifies the decision-relevant "
            "estimand. Choose none if every available option leaves the live explanations "
            "unresolved."
        ),
    }


def _decision_context(family_id: str) -> dict[str, Any]:
    common = {
        "research_use_only": True,
        "advance_is_not_clinical_deployment": True,
        "advance_requires_integrity_safe_decision_relevant_evidence": True,
    }
    contexts = {
        "Q01_identity_dependence": {
            "intended_use": (
                "One baseline prediction per patient; several biopsy rows may belong to "
                "one patient."
            ),
            "minimum_patient_auc": 0.68,
            "minimum_patient_auc_ci_low": 0.55,
        },
        "Q02_transport_factorial": {
            "intended_use": (
                "Transfer to the jointly specified endpoint, anti-TNF drug, and assay "
                "platform."
            ),
            "minimum_all_matched_auc": 0.72,
            "minimum_dominant_factor_ci_low": 0.0,
        },
        "Q03_process_confounding": {
            "intended_use": (
                "New patients may arrive from any batch; batch is not a causal predictor."
            ),
            "maximum_unsafe_auc_inflation": 0.12,
            "minimum_safe_blocked_auc": 0.72,
            "maximum_safe_permutation_p": 0.05,
        },
        "Q04_label_sensitivity": {
            "intended_use": (
                "Predict the prespecified week-6 endpoint after blinded source-record "
                "adjudication."
            ),
            "minimum_supported_auc": 0.72,
            "minimum_unadjudicated_sensitivity_bound": 0.70,
        },
        "Q05_decision_sufficiency": {
            "intended_use": "Prioritise confirmatory biomarker work in the target population.",
            "target_prevalence": 0.30,
            "probability_threshold": 0.55,
            "minimum_auc_ci_low": 0.65,
            "minimum_target_prevalence_ppv": 0.48,
            "minimum_net_benefit": 0.02,
            "maximum_brier_score": 0.22,
            "target_auc_ci_half_width": 0.06,
        },
    }
    return {**common, **contexts[family_id]}


def _public_analysis_contract(
    config: dict[str, Any], variant: dict[str, Any], partition: str
) -> dict[str, Any]:
    family_id = str(variant["family_id"])
    contract = config["analysis_contracts"][family_id]
    offset_key = "heldout_seed_offset" if partition == "heldout" else "development_seed_offset"
    bootstrap_seed = int(variant["seed"]) + int(config["bootstrap"][offset_key])
    metric_ids = list(contract["required_metrics"])
    distractors = {
        "Q01_identity_dependence": ["visit_level_accuracy"],
        "Q02_transport_factorial": ["pooled_auc"],
        "Q03_process_confounding": ["unblocked_accuracy"],
        "Q04_label_sensitivity": ["complete_case_accuracy"],
        "Q05_decision_sufficiency": ["training_accuracy"],
    }[family_id]
    semantics = FAMILY_SEMANTICS[family_id]
    return {
        "candidate_estimands": contract["candidate_estimands"],
        "candidate_methods": contract["candidate_methods"],
        "candidate_hypotheses": semantics["candidate_hypotheses"],
        "candidate_interpretations": semantics["candidate_interpretations"],
        "candidate_metric_ids": metric_ids + distractors,
        "metric_definitions": {name: METRIC_DEFINITIONS[name] for name in metric_ids},
        "metric_tolerances": contract["metric_tolerances"],
        "bootstrap_replicates": config["bootstrap"]["replicates"],
        "bootstrap_confidence_level": config["bootstrap"]["confidence_level"],
        "bootstrap_seed": bootstrap_seed,
        "permutation_replicates": config["permutation"]["replicates"],
        "permutation_seed": bootstrap_seed + 701,
        "permutation_p_value_correction": config["permutation"]["p_value_correction"],
        "uncertainty_unit_options": [
            "row",
            "patient_cluster",
            "site_cluster",
            "patient_within_batch",
            "patient_label_assignment",
        ],
        "action_vocabulary": [
            "none_current_evidence_sufficient",
            "patient_visit_reconciliation",
            "endpoint_drug_platform_factorial_bridge",
            "leakage_safe_grouped_and_batch_blocked_validation",
            "endpoint_matched_replication",
            "blinded_expert_endpoint_adjudication",
            "adequately_powered_independent_replication",
        ],
        "instruction": (
            "Definitions make results reproducible; they do not designate the valid estimand "
            "or method. Choose those from the intended-use question and dependence structure."
        ),
    }


@dataclass(frozen=True, slots=True)
class V04Package:
    family_id: str
    variant_id: str
    partition: str
    workspace_root: Path
    sealed_root: Path
    package_digest: str
    sealed_digest: str
    private_variant: dict[str, Any]


class V04Builder:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()

    def build(
        self,
        variant_id: str,
        *,
        output_root: Path,
        partition: str = "development",
        replace: bool = False,
    ) -> V04Package:
        validate_v04_config(self.project_root)
        config = load_v04_config(self.project_root)
        variant = load_v04_variant(self.project_root, variant_id, partition=partition)
        workspace = output_root.resolve() / f"hard4-{variant_id}"
        sealed = output_root.resolve() / f"hard4-{variant_id}-sealed"
        for path in (workspace, sealed):
            if path.exists():
                if not replace:
                    raise ConfigurationError(f"v0.4 build path exists: {path}")
                shutil.rmtree(path)
            path.mkdir(parents=True)
        _copy_tree_files(self.project_root / "tasks" / "hard_suite_v04", workspace)
        family_id = str(variant["family_id"])
        generator = GENERATORS[family_id]
        pilot_rows = generator(int(variant["seed"]), "none", False)
        _write_csv(workspace / "data" / "pilot.csv", pilot_rows)
        _write_json(workspace / "case" / "decision_context.json", _decision_context(family_id))
        _write_json(
            workspace / "analysis_contract.json",
            _public_analysis_contract(config, variant, partition),
        )
        catalog = _resource_catalog(variant)
        _write_json(workspace / "resources" / "resource_catalog.json", catalog)
        _write_json(
            workspace / "task.json",
            {
                "schema_version": "0.4",
                "suite_id": config["suite_id"],
                "family_id": family_id,
                "variant_id": variant_id,
                "research_question": (
                    "What decision-relevant estimand is supported, which explanation survives "
                    "dependence-aware uncertainty analysis, and which resource has positive "
                    "value of information?"
                ),
                "scoring_weights": config["scoring"],
                "trajectory_budget": config["trajectory_budget"],
                "resource_contract": config["resource_contract"],
                "schemas": {
                    "commitment": "schemas/commitment.schema.json",
                    "final_submission": "schemas/final_submission.schema.json",
                },
            },
        )
        _write_json(
            workspace / "evidence_manifest.json",
            {
                evidence_id: {"paths": paths, "status": "available"}
                for evidence_id, paths in EVIDENCE_IDS.items()
            },
        )
        manifest = _read_object(workspace / "evidence_manifest.json")
        for evidence_id in ("EV-RESOURCE", "EV-ANALYSIS", "EV-PROVENANCE"):
            manifest[evidence_id]["status"] = "partly_available_until_commitment"
        _write_json(workspace / "evidence_manifest.json", manifest)
        (workspace / "submission").mkdir()

        resources = {str(row["resource_id"]): row for row in catalog["resources"]}
        for selection in ("none", "R1", "R2", "R3"):
            packet = sealed / selection
            packet.mkdir()
            effective = (
                selection == variant["correct_resource_id"]
                and variant["correct_resource_available"]
            )
            rows = generator(int(variant["seed"]), selection, effective)
            _write_csv(packet / "analysis.csv", rows)
            selected = resources.get(selection)
            _write_json(
                packet / "selected_resource.json",
                {
                    "selected_resource_id": selection,
                    "intervention": selected["intervention"] if selected else "none",
                    "class": selected["class"] if selected else "none",
                    "cost_units": selected["cost_units"] if selected else 0,
                    "row_count": len(rows),
                },
            )
            _write_json(
                packet / "provenance.json",
                {
                    "deterministic_generation": True,
                    "locked_predictor_unchanged": True,
                    "patient_grouped": family_id == "Q01_identity_dependence" and effective,
                    "leakage_safe_process": family_id == "Q03_process_confounding" and effective,
                    "expert_adjudication_delivered": (
                        family_id == "Q04_label_sensitivity" and effective
                    ),
                    "independent_replication": family_id == "Q05_decision_sufficiency"
                    and effective,
                },
            )

        public_rows = [
            {
                "path": path.relative_to(workspace).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in sorted(item for item in workspace.rglob("*") if item.is_file())
        ]
        sealed_rows = [
            {
                "path": path.relative_to(sealed).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in sorted(item for item in sealed.rglob("*") if item.is_file())
        ]
        package_digest = canonical_sha256(public_rows)
        sealed_digest = canonical_sha256(sealed_rows)
        _write_json(
            workspace / "START_STATE.json",
            {
                "schema_version": "0.4",
                "suite_id": config["suite_id"],
                "family_id": family_id,
                "variant_id": variant_id,
                "partition": partition,
                "package_digest": package_digest,
                "selected_resource_packet_visible": False,
                "private_answer_visible": False,
            },
        )
        return V04Package(
            family_id=family_id,
            variant_id=variant_id,
            partition=partition,
            workspace_root=workspace,
            sealed_root=sealed,
            package_digest=package_digest,
            sealed_digest=sealed_digest,
            private_variant=variant,
        )


def _percentile(values: list[float], probability: float) -> float:
    if not values:
        raise ValueError("Cannot compute percentile of an empty list")
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def _safe_auc(labels: Iterable[int], scores: Iterable[float]) -> float | None:
    label_values = list(labels)
    score_values = list(scores)
    if len(set(label_values)) < 2:
        return None
    return _auc(label_values, score_values)


def _grouped_records(
    rows: list[dict[str, str]], group_key: str, score_key: str
) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[row[group_key]].append(row)
    output = []
    for group_id, selected in groups.items():
        labels = {int(row["label"]) for row in selected}
        if len(labels) != 1:
            raise ContractError(f"Inconsistent labels within {group_key}={group_id}")
        output.append(
            {
                "group_id": group_id,
                "label": labels.pop(),
                "score": mean(float(row[score_key]) for row in selected),
                "batch": selected[0].get("batch"),
                "size": len(selected),
            }
        )
    return output


def _bootstrap_auc(
    records: list[dict[str, Any]], *, seed: int, replicates: int
) -> tuple[float, float]:
    rng = random.Random(seed)
    values = []
    for _ in range(replicates):
        sampled = [records[rng.randrange(len(records))] for _ in records]
        auc = _safe_auc(
            (int(row["label"]) for row in sampled),
            (float(row["score"]) for row in sampled),
        )
        if auc is not None:
            values.append(auc)
    return _percentile(values, 0.025), _percentile(values, 0.975)


def _phi(x_values: list[int], y_values: list[int]) -> float:
    n11 = sum(x == 1 and y == 1 for x, y in zip(x_values, y_values, strict=True))
    n10 = sum(x == 1 and y == 0 for x, y in zip(x_values, y_values, strict=True))
    n01 = sum(x == 0 and y == 1 for x, y in zip(x_values, y_values, strict=True))
    n00 = sum(x == 0 and y == 0 for x, y in zip(x_values, y_values, strict=True))
    denominator = math.sqrt((n11 + n10) * (n01 + n00) * (n11 + n01) * (n10 + n00))
    return 0.0 if denominator == 0 else (n11 * n00 - n10 * n01) / denominator


def _identity_metrics(
    rows: list[dict[str, str]], contract: dict[str, Any]
) -> dict[str, float]:
    row_auc = _auc(
        [int(row["label"]) for row in rows],
        [float(row["naive_score"]) for row in rows],
    )
    patients = _grouped_records(rows, "cluster_id", "locked_score")
    patient_auc = _auc(
        [int(row["label"]) for row in patients],
        [float(row["score"]) for row in patients],
    )
    low, high = _bootstrap_auc(
        patients,
        seed=int(contract["bootstrap_seed"]),
        replicates=int(contract["bootstrap_replicates"]),
    )
    cluster_sizes = [int(row["size"]) for row in patients]
    kish = len(rows) ** 2 / sum(size**2 for size in cluster_sizes)
    reported: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        reported[row["cluster_id"]].add(row["reported_patient_id"])
    conflicts = sum(len(values) > 1 for values in reported.values())
    return {
        "row_auc": row_auc,
        "patient_auc": patient_auc,
        "patient_auc_ci_low": low,
        "patient_auc_ci_high": high,
        "unique_patient_units": float(len(patients)),
        "kish_effective_n": kish,
        "leakage_inflation": row_auc - patient_auc,
        "identity_conflict_count": float(conflicts),
    }


def _transport_cell_aucs(rows: list[dict[str, str]]) -> dict[tuple[int, int, int], float]:
    cells: dict[tuple[int, int, int], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        key = (
            int(row["endpoint_match"]),
            int(row["drug_match"]),
            int(row["platform_match"]),
        )
        cells[key].append(row)
    output = {}
    for key in itertools.product((0, 1), repeat=3):
        selected = cells[key]
        auc = _safe_auc(
            (int(row["label"]) for row in selected),
            (float(row["locked_score"]) for row in selected),
        )
        if auc is None:
            raise ContractError(f"Factorial cell lacks both labels: {key}")
        output[key] = auc
    return output


def _transport_effects(cells: dict[tuple[int, int, int], float]) -> dict[str, float]:
    factor_names = ("endpoint", "drug", "platform")
    effects = {}
    for index, name in enumerate(factor_names):
        matched = mean(value for key, value in cells.items() if key[index] == 1)
        unmatched = mean(value for key, value in cells.items() if key[index] == 0)
        effects[f"{name}_main_effect"] = matched - unmatched
    y = cells
    effects["three_way_interaction"] = (
        y[(1, 1, 1)]
        - y[(1, 1, 0)]
        - y[(1, 0, 1)]
        - y[(0, 1, 1)]
        + y[(1, 0, 0)]
        + y[(0, 1, 0)]
        + y[(0, 0, 1)]
        - y[(0, 0, 0)]
    )
    return effects


def _transport_metrics(
    rows: list[dict[str, str]], contract: dict[str, Any]
) -> dict[str, float]:
    cells = _transport_cell_aucs(rows)
    effects = _transport_effects(cells)
    main_names = ("endpoint_main_effect", "drug_main_effect", "platform_main_effect")
    dominant_name = max(main_names, key=lambda name: abs(effects[name]))
    sites: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        sites[row["site_id"]].append(row)
    site_ids = sorted(sites)
    rng = random.Random(int(contract["bootstrap_seed"]))
    bootstrap = []
    for _ in range(int(contract["bootstrap_replicates"])):
        sampled = []
        for _ in site_ids:
            sampled.extend(sites[site_ids[rng.randrange(len(site_ids))]])
        try:
            bootstrap.append(_transport_effects(_transport_cell_aucs(sampled))[dominant_name])
        except ContractError:
            continue
    return {
        "unmatched_auc": cells[(0, 0, 0)],
        "all_matched_auc": cells[(1, 1, 1)],
        **effects,
        "dominant_factor_effect": effects[dominant_name],
        "dominant_factor_ci_low": _percentile(bootstrap, 0.025),
        "dominant_factor_ci_high": _percentile(bootstrap, 0.975),
    }


def _batch_blocked_auc(records: list[dict[str, Any]]) -> float:
    batches: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        batches[str(row["batch"])].append(row)
    weighted = []
    for selected in batches.values():
        auc = _safe_auc(
            (int(row["label"]) for row in selected),
            (float(row["score"]) for row in selected),
        )
        if auc is not None:
            weighted.extend([auc] * len(selected))
    if not weighted:
        raise ContractError("No batch contains both outcome classes")
    return mean(weighted)


def _permutation_p_values(
    patients: list[dict[str, Any]], contract: dict[str, Any]
) -> tuple[float, float]:
    rng = random.Random(int(contract["permutation_seed"]))
    replicates = int(contract["permutation_replicates"])
    observed_global = _auc(
        [int(row["label"]) for row in patients],
        [float(row["score"]) for row in patients],
    )
    observed_within = _batch_blocked_auc(patients)
    global_extreme = 0
    within_extreme = 0
    original_labels = [int(row["label"]) for row in patients]
    indices_by_batch: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(patients):
        indices_by_batch[str(row["batch"])].append(index)
    for _ in range(replicates):
        global_labels = list(original_labels)
        rng.shuffle(global_labels)
        global_auc = _safe_auc(global_labels, [float(row["score"]) for row in patients])
        if global_auc is not None and global_auc >= observed_global:
            global_extreme += 1

        within_labels = list(original_labels)
        for indices in indices_by_batch.values():
            values = [within_labels[index] for index in indices]
            rng.shuffle(values)
            for index, value in zip(indices, values, strict=True):
                within_labels[index] = value
        permuted = [dict(row, label=within_labels[index]) for index, row in enumerate(patients)]
        if _batch_blocked_auc(permuted) >= observed_within:
            within_extreme += 1
    denominator = replicates + 1
    return (within_extreme + 1) / denominator, (global_extreme + 1) / denominator


def _process_metrics(
    rows: list[dict[str, str]], contract: dict[str, Any]
) -> dict[str, float]:
    naive_auc = _auc(
        [int(row["label"]) for row in rows],
        [float(row["naive_score"]) for row in rows],
    )
    grouped = _grouped_records(rows, "patient_id", "grouped_score")
    blocked = _grouped_records(rows, "patient_id", "blocked_score")
    patient_auc = _auc(
        [int(row["label"]) for row in grouped],
        [float(row["score"]) for row in grouped],
    )
    blocked_auc = _batch_blocked_auc(blocked)
    within_p, global_p = _permutation_p_values(grouped, contract)
    return {
        "naive_auc": naive_auc,
        "patient_grouped_auc": patient_auc,
        "batch_blocked_auc": blocked_auc,
        "naive_minus_blocked_auc": naive_auc - blocked_auc,
        "batch_outcome_phi": _phi(
            [int(row["batch"]) for row in grouped],
            [int(row["label"]) for row in grouped],
        ),
        "within_batch_permutation_p": within_p,
        "global_permutation_p": global_p,
    }


def _cohen_kappa(first: list[int], second: list[int]) -> float:
    agreement = mean(left == right for left, right in zip(first, second, strict=True))
    first_positive = mean(first)
    second_positive = mean(second)
    expected = first_positive * second_positive + (1 - first_positive) * (1 - second_positive)
    return 0.0 if math.isclose(expected, 1.0) else (agreement - expected) / (1 - expected)


def _label_metrics(rows: list[dict[str, str]]) -> dict[str, float]:
    first = [int(row["reviewer_a"]) for row in rows]
    second = [int(row["reviewer_b"]) for row in rows]
    ambiguous_indices = [index for index, row in enumerate(rows) if first[index] != second[index]]
    fixed = [first[index] for index in range(len(rows))]
    scores = [float(row["locked_score"]) for row in rows]
    auc_values = []
    for assignment in itertools.product((0, 1), repeat=len(ambiguous_indices)):
        labels = list(fixed)
        for index, value in zip(ambiguous_indices, assignment, strict=True):
            labels[index] = value
        auc = _safe_auc(labels, scores)
        if auc is not None:
            auc_values.append(auc)
    metrics = {
        "reviewer_agreement": mean(
            left == right for left, right in zip(first, second, strict=True)
        ),
        "cohen_kappa": _cohen_kappa(first, second),
        "ambiguous_fraction": len(ambiguous_indices) / len(rows),
        "extracted_auc": _auc([int(row["extraction_label"]) for row in rows], scores),
        "sensitivity_auc_low": min(auc_values),
        "sensitivity_auc_high": max(auc_values),
    }
    if all(row["adjudicated_label"] != "" for row in rows):
        adjudicated_auc = _auc([int(row["adjudicated_label"]) for row in rows], scores)
        metrics["adjudicated_auc"] = adjudicated_auc
        metrics["adjudication_auc_change"] = adjudicated_auc - metrics["extracted_auc"]
    return metrics


def _site_bootstrap_auc(
    rows: list[dict[str, str]], *, seed: int, replicates: int
) -> tuple[float, float]:
    sites: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        sites[row["site_id"]].append(row)
    site_ids = sorted(sites)
    rng = random.Random(seed)
    values = []
    for _ in range(replicates):
        sampled = []
        for _ in site_ids:
            sampled.extend(sites[site_ids[rng.randrange(len(site_ids))]])
        auc = _safe_auc(
            (int(row["label"]) for row in sampled),
            (float(row["locked_probability"]) for row in sampled),
        )
        if auc is not None:
            values.append(auc)
    return _percentile(values, 0.025), _percentile(values, 0.975)


def _evidence_metrics(
    rows: list[dict[str, str]], contract: dict[str, Any], context: dict[str, Any]
) -> dict[str, float]:
    labels = [int(row["label"]) for row in rows]
    scores = [float(row["locked_probability"]) for row in rows]
    auc = _auc(labels, scores)
    low, high = _site_bootstrap_auc(
        rows,
        seed=int(contract["bootstrap_seed"]),
        replicates=int(contract["bootstrap_replicates"]),
    )
    threshold = float(context["probability_threshold"])
    predictions = [score >= threshold for score in scores]
    positives = sum(labels)
    negatives = len(labels) - positives
    sensitivity = (
        sum(
            prediction and label == 1
            for prediction, label in zip(predictions, labels, strict=True)
        )
        / positives
    )
    specificity = (
        sum(
            not prediction and label == 0
            for prediction, label in zip(predictions, labels, strict=True)
        )
        / negatives
    )
    prevalence = float(context["target_prevalence"])
    ppv_denominator = prevalence * sensitivity + (1 - prevalence) * (1 - specificity)
    ppv = prevalence * sensitivity / ppv_denominator if ppv_denominator else 0.0
    net_benefit = prevalence * sensitivity - (1 - prevalence) * (1 - specificity) * (
        threshold / (1 - threshold)
    )
    half_width = (high - low) / 2
    target_half_width = float(context["target_auc_ci_half_width"])
    required_n = math.ceil(len(rows) * (half_width / target_half_width) ** 2)
    return {
        "observed_sample_size": float(len(rows)),
        "auc": auc,
        "auc_ci_low": low,
        "auc_ci_high": high,
        "brier_score": mean(
            (score - label) ** 2 for score, label in zip(scores, labels, strict=True)
        ),
        "sensitivity": sensitivity,
        "specificity": specificity,
        "target_prevalence_ppv": ppv,
        "net_benefit": net_benefit,
        "required_sample_size": float(required_n),
    }


def compute_v04_metrics(workspace_root: Path) -> dict[str, float]:
    root = workspace_root.resolve()
    task = _read_object(root / "task.json")
    contract = _read_object(root / "analysis_contract.json")
    context = _read_object(root / "case" / "decision_context.json")
    rows = _read_csv(root / "evidence" / "analysis.csv")
    family_id = str(task["family_id"])
    if family_id == "Q01_identity_dependence":
        metrics = _identity_metrics(rows, contract)
    elif family_id == "Q02_transport_factorial":
        metrics = _transport_metrics(rows, contract)
    elif family_id == "Q03_process_confounding":
        metrics = _process_metrics(rows, contract)
    elif family_id == "Q04_label_sensitivity":
        metrics = _label_metrics(rows)
    elif family_id == "Q05_decision_sufficiency":
        metrics = _evidence_metrics(rows, contract, context)
    else:
        raise ContractError(f"Unknown v0.4 family: {family_id}")
    return {name: round(float(value), 8) for name, value in metrics.items()}


def _selected_resource(workspace_root: Path) -> str:
    selected = _read_object(workspace_root.resolve() / "evidence" / "selected_resource.json")
    return str(selected["selected_resource_id"])


def _decision_and_failure(
    workspace_root: Path, metrics: dict[str, float]
) -> tuple[str, str, str, str]:
    root = workspace_root.resolve()
    task = _read_object(root / "task.json")
    context = _read_object(root / "case" / "decision_context.json")
    provenance = _read_object(root / "evidence" / "provenance.json")
    family_id = str(task["family_id"])
    if family_id == "Q01_identity_dependence":
        if metrics["identity_conflict_count"] > 0:
            return (
                "stop",
                "patient_dependence_and_identity_ambiguity",
                "row_inference_invalid_patient_signal_uncertain",
                "not_contained",
            )
        if (
            metrics["patient_auc"] >= float(context["minimum_patient_auc"])
            and metrics["patient_auc_ci_low"] >= float(context["minimum_patient_auc_ci_low"])
        ):
            return (
                "advance",
                "no_material_failure",
                "reconciliation_supports_patient_level_evidence",
                "contained",
            )
        return (
            "insufficient_evidence",
            "patient_dependence_and_identity_ambiguity",
            "row_inference_invalid_patient_signal_uncertain",
            "not_contained",
        )
    if family_id == "Q02_transport_factorial":
        if (
            metrics["all_matched_auc"] >= float(context["minimum_all_matched_auc"])
            and metrics["dominant_factor_ci_low"]
            >= float(context["minimum_dominant_factor_ci_low"])
        ):
            return (
                "advance",
                "no_material_failure",
                "joint_bridge_supports_intended_transfer",
                "contained",
            )
        return (
            "insufficient_evidence",
            "endpoint_drug_platform_transport_interaction",
            "factorial_transport_effect_unresolved",
            "not_contained",
        )
    if family_id == "Q03_process_confounding":
        safe = bool(provenance["leakage_safe_process"])
        if not safe and (
            metrics["naive_minus_blocked_auc"]
            > float(context["maximum_unsafe_auc_inflation"])
            or abs(metrics["batch_outcome_phi"]) >= 0.45
        ):
            return (
                "stop",
                "batch_confounding_and_split_leakage",
                "naive_performance_is_batch_driven",
                "not_contained",
            )
        if (
            safe
            and metrics["batch_blocked_auc"] >= float(context["minimum_safe_blocked_auc"])
            and metrics["within_batch_permutation_p"]
            <= float(context["maximum_safe_permutation_p"])
        ):
            return (
                "advance",
                "no_material_failure",
                "safe_validation_supports_signal",
                "contained",
            )
        return (
            "insufficient_evidence",
            "residual_model_uncertainty",
            "process_fixed_scientific_evidence_unresolved",
            "contained_process_only" if safe else "not_contained",
        )
    if family_id == "Q04_label_sensitivity":
        if (
            "adjudicated_auc" in metrics
            and metrics["adjudicated_auc"] >= float(context["minimum_supported_auc"])
        ):
            return (
                "advance",
                "no_material_failure",
                "adjudication_supports_locked_model",
                "contained",
            )
        if metrics["sensitivity_auc_low"] >= float(
            context["minimum_unadjudicated_sensitivity_bound"]
        ):
            return (
                "advance",
                "no_material_failure",
                "adjudication_supports_locked_model",
                "verified_no_issue",
            )
        return (
            "insufficient_evidence",
            "ambiguous_endpoint_labels",
            "label_sensitivity_crosses_decision_boundary",
            "not_contained",
        )
    if family_id == "Q05_decision_sufficiency":
        if (
            metrics["auc_ci_low"] >= float(context["minimum_auc_ci_low"])
            and metrics["target_prevalence_ppv"]
            >= float(context["minimum_target_prevalence_ppv"])
            and metrics["net_benefit"] >= float(context["minimum_net_benefit"])
            and metrics["brier_score"] <= float(context["maximum_brier_score"])
            and metrics["required_sample_size"] <= metrics["observed_sample_size"]
        ):
            return (
                "advance",
                "no_material_failure",
                "replication_supports_intended_use_utility",
                "contained",
            )
        return (
            "insufficient_evidence",
            "underpowered_decision_evidence",
            "decision_uncertainty_remains_material",
            "not_contained",
        )
    raise ContractError(f"Unknown v0.4 family: {family_id}")


def _recovery_targets(
    workspace_root: Path,
    variant: dict[str, Any],
    decision: str,
    containment: str,
) -> tuple[str, str, str]:
    selected = _selected_resource(workspace_root)
    resources = {str(row["resource_id"]): row for row in variant["resources"]}
    correct_intervention = str(resources[str(variant["correct_resource_id"])]["intervention"])
    effective = (
        selected == variant["correct_resource_id"] and variant["correct_resource_available"]
    )
    if decision == "advance":
        action = "none_current_evidence_sufficient"
        recommended = "none"
    elif containment == "contained_process_only":
        action = "endpoint_matched_replication"
        recommended = "endpoint_matched_replication"
    else:
        action = correct_intervention
        recommended = correct_intervention
    if selected == "none":
        effect = "no_resource_selected"
    elif not effective:
        effect = "ineffective"
    elif containment == "contained_process_only":
        effect = "resolves_process_only"
    elif decision == "advance":
        effect = "resolves"
    else:
        effect = "evidence_still_insufficient"
    return action, recommended, effect


def solve_v04(
    project_root: Path, workspace_root: Path, variant: dict[str, Any]
) -> dict[str, Any]:
    root = workspace_root.resolve()
    task = _read_object(root / "task.json")
    config = load_v04_config(project_root)
    contract = config["analysis_contracts"][variant["family_id"]]
    metrics = compute_v04_metrics(root)
    decision, failure, interpretation, containment = _decision_and_failure(root, metrics)
    action, recommended, effect = _recovery_targets(root, variant, decision, containment)
    return {
        "family_id": task["family_id"],
        "variant_id": task["variant_id"],
        "selected_resource_id": _selected_resource(root),
        "decision": decision,
        "confidence": 1.0,
        "primary_failure": failure,
        "primary_estimand_id": contract["primary_estimand_id"],
        "analysis_method_id": contract["analysis_method_id"],
        "metrics": metrics,
        "interpretation_id": interpretation,
        "evidence_ids": sorted(EVIDENCE_IDS),
        "containment_status": containment,
        "smallest_next_action": action,
        "recommended_intervention": recommended,
        "intervention_effect": effect,
        "unnecessary_escalation": False,
        "rationale": (
            "Reference answer recomputed from the selected deterministic evidence packet "
            "under the public estimand, uncertainty, and decision contracts."
        ),
    }
def reference_v04_commitment(
    workspace_root: Path, variant: dict[str, Any], project_root: Path
) -> dict[str, Any]:
    root = workspace_root.resolve()
    task = _read_object(root / "task.json")
    config = load_v04_config(project_root)
    contract = config["analysis_contracts"][variant["family_id"]]
    semantics = FAMILY_SEMANTICS[str(variant["family_id"])]
    failure = str(variant["failure_mode"])
    alternatives = [name for name in semantics["candidate_hypotheses"] if name != failure]
    pre_reveal = (
        "stop"
        if variant["family_id"]
        in {"Q01_identity_dependence", "Q03_process_confounding"}
        else "insufficient_evidence"
    )
    return {
        "family_id": task["family_id"],
        "variant_id": task["variant_id"],
        "ranked_hypotheses": [failure, alternatives[0]],
        "primary_estimand_id": contract["primary_estimand_id"],
        "analysis_method_id": contract["analysis_method_id"],
        "planned_metric_ids": contract["required_metrics"],
        "uncertainty_unit": semantics["uncertainty_unit"],
        "requested_resource_id": variant["expected_resource_id"],
        "pre_reveal_decision": pre_reveal,
        "if_primary_supported": pre_reveal,
        "if_primary_refuted": "advance",
    }


@dataclass(frozen=True, slots=True)
class V04Grade:
    score: float
    components: dict[str, float]
    expected_decision: str
    expected_primary_failure: str
    decision_correct: bool
    estimand_correct: bool
    analysis_method_correct: bool
    computation_score: float
    interpretation_correct: bool
    resource_selection_correct: bool
    containment_correct: bool
    recovery_design_correct: bool
    metric_scores: dict[str, float]
    commitment_immutable: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "components": self.components,
            "expected_decision": self.expected_decision,
            "expected_primary_failure": self.expected_primary_failure,
            "decision_correct": self.decision_correct,
            "estimand_correct": self.estimand_correct,
            "analysis_method_correct": self.analysis_method_correct,
            "computation_score": self.computation_score,
            "interpretation_correct": self.interpretation_correct,
            "resource_selection_correct": self.resource_selection_correct,
            "containment_correct": self.containment_correct,
            "recovery_design_correct": self.recovery_design_correct,
            "metric_scores": self.metric_scores,
            "commitment_immutable": self.commitment_immutable,
        }


def grade_v04(
    project_root: Path,
    workspace_root: Path,
    variant: dict[str, Any],
    commitment: dict[str, Any] | None,
    submission: dict[str, Any] | None,
    *,
    commitment_immutable: bool,
) -> V04Grade:
    root = workspace_root.resolve()
    config = load_v04_config(project_root)
    task = _read_object(root / "task.json")
    expected = solve_v04(project_root, root, variant)
    contract = config["analysis_contracts"][variant["family_id"]]
    expected_metrics = expected["metrics"]
    if submission is None:
        components = {name: 0.0 for name in task["scoring_weights"]}
        return V04Grade(
            0.0,
            components,
            expected["decision"],
            expected["primary_failure"],
            False,
            False,
            False,
            0.0,
            False,
            False,
            False,
            False,
            {name: 0.0 for name in expected_metrics},
            commitment_immutable,
        )
    metric_scores = {
        name: _numeric_credit(
            float(expected_value),
            submission.get("metrics", {}).get(name),
            float(contract["metric_tolerances"][name]),
        )
        for name, expected_value in expected_metrics.items()
    }
    computation = mean(metric_scores.values())
    estimand_correct = submission.get("primary_estimand_id") == contract["primary_estimand_id"]
    method_correct = submission.get("analysis_method_id") == contract["analysis_method_id"]
    uncertainty_correct = (commitment or {}).get("uncertainty_unit") == FAMILY_SEMANTICS[
        str(variant["family_id"])
    ]["uncertainty_unit"]
    quantitative = (
        20.0 * estimand_correct
        + 20.0 * method_correct
        + 10.0 * uncertainty_correct
        + 0.50 * computation
    )
    interpretation_correct = submission.get("interpretation_id") == expected["interpretation_id"]
    diagnosis_correct = submission.get("primary_failure") == expected["primary_failure"]
    scientific = 60.0 * diagnosis_correct + 40.0 * interpretation_correct
    decision_correct = submission.get("decision") == expected["decision"]
    resource_correct = (
        submission.get("selected_resource_id") == variant["expected_resource_id"]
        and (commitment or {}).get("requested_resource_id") == variant["expected_resource_id"]
    )
    containment_correct = submission.get("containment_status") == expected["containment_status"]
    action_correct = submission.get("smallest_next_action") == expected["smallest_next_action"]
    intervention_correct = (
        submission.get("recommended_intervention") == expected["recommended_intervention"]
    )
    effect_correct = submission.get("intervention_effect") == expected["intervention_effect"]
    no_unnecessary_escalation = submission.get("unnecessary_escalation") is False
    recovery = (
        30.0 * containment_correct
        + 25.0 * action_correct
        + 25.0 * intervention_correct
        + 15.0 * effect_correct
        + 5.0 * no_unnecessary_escalation
    )
    commitment_value = commitment or {}
    hypotheses = set(commitment_value.get("ranked_hypotheses", []))
    planned = set(commitment_value.get("planned_metric_ids", []))
    required = set(contract["required_metrics"])
    planned_recall = len(planned & required) / len(required)
    commitment_score = (
        30.0 * commitment_immutable
        + 20.0 * (variant["failure_mode"] in hypotheses)
        + 20.0
        * (commitment_value.get("primary_estimand_id") == contract["primary_estimand_id"])
        + 20.0
        * (commitment_value.get("analysis_method_id") == contract["analysis_method_id"])
        + 10.0 * planned_recall
    )
    components = {
        "quantitative_statistical_reasoning": quantitative,
        "scientific_diagnosis": scientific,
        "decision": 100.0 * decision_correct,
        "resource_selection_value_of_information": 100.0 * resource_correct,
        "recovery_design": recovery,
        "commitment_and_reproducibility": commitment_score,
    }
    score = sum(
        float(task["scoring_weights"][name]) * value for name, value in components.items()
    )
    recovery_design_correct = all(
        (containment_correct, action_correct, intervention_correct, effect_correct)
    )
    return V04Grade(
        score=round(score, 6),
        components={name: round(value, 6) for name, value in components.items()},
        expected_decision=expected["decision"],
        expected_primary_failure=expected["primary_failure"],
        decision_correct=decision_correct,
        estimand_correct=estimand_correct,
        analysis_method_correct=method_correct,
        computation_score=round(computation, 6),
        interpretation_correct=interpretation_correct,
        resource_selection_correct=resource_correct,
        containment_correct=containment_correct,
        recovery_design_correct=recovery_design_correct,
        metric_scores={name: round(value, 6) for name, value in metric_scores.items()},
        commitment_immutable=commitment_immutable,
    )


class V04Environment:
    def __init__(self, package: V04Package) -> None:
        self.package = package
        self.workspace_root = package.workspace_root.resolve()
        self.commitment: dict[str, Any] | None = None
        self.commitment_sha256: str | None = None
        self.revealed = False
        self.submission: dict[str, Any] | None = None
        self.commitment_immutable = False

    def _workspace_file(self, relative_path: str) -> Path:
        relative = Path(relative_path)
        if relative.is_absolute():
            raise ContractError("Artifact path must be relative")
        path = (self.workspace_root / relative).resolve()
        if self.workspace_root not in path.parents or not path.is_file():
            raise ContractError("Artifact is missing or outside the workspace")
        return path

    def commit_plan(self, commitment_path: str = "submission/commitment.json") -> str:
        if self.commitment is not None:
            raise InvalidTransitionError("commit_plan is irreversible and may be called once")
        path = self._workspace_file(commitment_path)
        value = _read_object(path)
        _validate_schema(
            value,
            self.workspace_root / "schemas" / "commitment.schema.json",
            "Commitment",
        )
        task = _read_object(self.workspace_root / "task.json")
        if value["family_id"] != task["family_id"] or value["variant_id"] != task["variant_id"]:
            raise ContractError("Commitment identifiers do not match task.json")
        analysis = _read_object(self.workspace_root / "analysis_contract.json")
        if value["primary_estimand_id"] not in analysis["candidate_estimands"]:
            raise ContractError("Unknown primary estimand; use a published candidate ID")
        if value["analysis_method_id"] not in analysis["candidate_methods"]:
            raise ContractError("Unknown analysis method; use a published candidate ID")
        catalog = _read_object(self.workspace_root / "resources" / "resource_catalog.json")
        availability = {
            str(row["resource_id"]): bool(row["available"]) for row in catalog["resources"]
        }
        requested = str(value["requested_resource_id"])
        if requested != "none" and not availability[requested]:
            raise ContractError(
                f"Requested resource {requested} is unavailable; revise before commitment"
            )
        self.commitment = value
        self.commitment_sha256 = sha256_file(path)
        return "Commitment, estimand, method, and resource choice accepted and hashed."

    def reveal_evidence(self) -> str:
        if self.commitment is None:
            raise InvalidTransitionError("commit_plan must succeed before reveal_evidence")
        if self.revealed:
            raise InvalidTransitionError("reveal_evidence may be called only once")
        selection = str(self.commitment["requested_resource_id"])
        source = self.package.sealed_root / selection
        evidence = self.workspace_root / "evidence"
        evidence.mkdir()
        _copy_tree_files(source, evidence)
        manifest = _read_object(self.workspace_root / "evidence_manifest.json")
        for record in manifest.values():
            if all((self.workspace_root / path).is_file() for path in record["paths"]):
                record["status"] = "available"
        _write_json(self.workspace_root / "evidence_manifest.json", manifest)
        _write_json(
            self.workspace_root / "REVEAL_STATE.json",
            {
                "commitment_sha256": self.commitment_sha256,
                "selected_resource_id": selection,
                "sealed_digest": self.package.sealed_digest,
                "reveal_complete": True,
            },
        )
        self.revealed = True
        return f"Evidence packet for {selection} revealed; recompute with the committed method."

    def submit_hard_suite(self, submission_path: str = "submission/final_submission.json") -> str:
        if self.commitment is None or not self.revealed:
            raise InvalidTransitionError("Commitment and reveal must precede submission")
        if self.submission is not None:
            raise InvalidTransitionError("submit_hard_suite may succeed only once")
        commitment_path = self._workspace_file("submission/commitment.json")
        if sha256_file(commitment_path) != self.commitment_sha256:
            raise ContractError("Committed file changed after reveal")
        path = self._workspace_file(submission_path)
        value = _read_object(path)
        _validate_schema(
            value,
            self.workspace_root / "schemas" / "final_submission.schema.json",
            "Submission",
        )
        task = _read_object(self.workspace_root / "task.json")
        if value["family_id"] != task["family_id"] or value["variant_id"] != task["variant_id"]:
            raise ContractError("Submission identifiers do not match task.json")
        if value["selected_resource_id"] != self.commitment["requested_resource_id"]:
            raise ContractError("Final selected resource differs from irreversible commitment")
        manifest = _read_object(self.workspace_root / "evidence_manifest.json")
        unknown = sorted(set(value["evidence_ids"]) - set(manifest))
        if unknown:
            raise ContractError(f"Unknown evidence IDs: {', '.join(unknown)}")
        self.submission = value
        self.commitment_immutable = True
        return "v0.4 submission accepted for private quantitative grading."

"""Composed, intervention-paired biomarker diligence environment."""

from __future__ import annotations

import csv
import json
import math
import random
import shutil
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from statistics import NormalDist
from typing import Any

from uc_bench.errors import ConfigurationError, ContractError, InvalidTransitionError
from uc_bench.hashing import canonical_sha256, sha256_file

_FACTORIAL_CONDITIONS = (
    "unmatched",
    "endpoint_matched",
    "platform_matched",
    "drug_matched",
    "all_matched",
)
_METRIC_TOLERANCES = {
    "identity_conflict_count": 0.0,
    "required_feature_retention": 0.001,
    "batch_outcome_phi": 0.01,
    "pilot_n": 0.0,
    "pilot_auc": 0.01,
    "label_disagreement_rate": 0.001,
    "adjudicated_auc": 0.01,
    "adjudicated_auc_gain": 0.015,
    "matched_evidence_n": 0.0,
    "matched_evidence_auc": 0.01,
    "endpoint_gain": 0.015,
    "platform_gain": 0.015,
    "drug_gain": 0.015,
    "all_matched_gain": 0.015,
}
_EVIDENCE_PATHS = {
    "EV-COHORT-CARDS": [
        "case/development_cohort.json",
        "case/validation_cohort.json",
    ],
    "EV-IDENTITY": ["data/sample_fingerprints.csv"],
    "EV-FEATURES": ["data/feature_availability.csv"],
    "EV-BATCH": ["data/metadata.csv"],
    "EV-PILOT": ["data/pilot_predictions.csv"],
    "EV-FACTORIAL": ["evidence/factorial_predictions.csv"],
    "EV-LABEL-AUDIT": ["evidence/adjudicated_predictions.csv"],
    "EV-INTERVENTION": ["evidence/intervention_delivery.json"],
    "EV-PROVENANCE": ["evidence/provenance.json"],
}
_FAILURE_TO_EXPERIMENT = {
    "identity_overlap": "patient_linkage_audit",
    "endpoint_mismatch": "endpoint_matched_validation",
    "platform_shift": "platform_mapping_audit",
    "drug_transfer": "drug_matched_validation",
    "transfer_interaction": "factorial_transfer_bridge",
    "feature_contract_failure": "platform_mapping_audit",
    "batch_confounding": "leakage_safe_reanalysis",
    "label_uncertainty": "blinded_label_readjudication",
    "underpowered_validation": "independent_replication",
    "model_misspecification": "independent_replication",
    "no_material_failure": "none_proceed",
}
_FAILURE_TO_RESOURCE = {
    "identity_overlap": "patient_visit_reconciliation",
    "endpoint_mismatch": "endpoint_matched_cohort",
    "platform_shift": "missing_subgroup_site_or_platform",
    "drug_transfer": "drug_matched_cohort",
    "transfer_interaction": "endpoint_drug_platform_matched_cohort",
    "feature_contract_failure": "batch_and_platform_documentation",
    "batch_confounding": "leakage_safe_splitting",
    "label_uncertainty": "expert_endpoint_adjudication",
    "underpowered_validation": "independent_replication",
    "model_misspecification": "independent_replication",
    "no_material_failure": "none",
}
_FAILURE_TO_EVIDENCE = {
    "identity_overlap": {"EV-IDENTITY", "EV-COHORT-CARDS"},
    "endpoint_mismatch": {"EV-COHORT-CARDS", "EV-FACTORIAL"},
    "platform_shift": {"EV-COHORT-CARDS", "EV-FEATURES", "EV-FACTORIAL"},
    "drug_transfer": {"EV-COHORT-CARDS", "EV-FACTORIAL"},
    "transfer_interaction": {"EV-COHORT-CARDS", "EV-FACTORIAL"},
    "feature_contract_failure": {"EV-FEATURES", "EV-COHORT-CARDS"},
    "batch_confounding": {"EV-BATCH", "EV-PROVENANCE"},
    "label_uncertainty": {"EV-PILOT", "EV-LABEL-AUDIT"},
    "underpowered_validation": {"EV-FACTORIAL", "EV-PILOT"},
    "model_misspecification": {"EV-FACTORIAL", "EV-PILOT"},
    "no_material_failure": {
        "EV-IDENTITY",
        "EV-FEATURES",
        "EV-BATCH",
        "EV-FACTORIAL",
        "EV-LABEL-AUDIT",
        "EV-PROVENANCE",
    },
}
_FAILURE_TO_METRICS = {
    "identity_overlap": {"identity_conflict_count"},
    "endpoint_mismatch": {"endpoint_gain", "matched_evidence_auc"},
    "platform_shift": {"platform_gain", "required_feature_retention"},
    "drug_transfer": {"drug_gain", "matched_evidence_auc"},
    "transfer_interaction": {
        "endpoint_gain",
        "platform_gain",
        "drug_gain",
        "all_matched_gain",
        "matched_evidence_n",
    },
    "feature_contract_failure": {"required_feature_retention"},
    "batch_confounding": {"batch_outcome_phi", "pilot_auc"},
    "label_uncertainty": {
        "label_disagreement_rate",
        "pilot_auc",
        "adjudicated_auc_gain",
    },
    "underpowered_validation": {"matched_evidence_n", "matched_evidence_auc"},
    "model_misspecification": {"matched_evidence_n", "matched_evidence_auc"},
    "no_material_failure": {
        "identity_conflict_count",
        "required_feature_retention",
        "batch_outcome_phi",
        "label_disagreement_rate",
        "matched_evidence_n",
        "matched_evidence_auc",
    },
}


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ContractError(f"Cannot load JSON object {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractError(f"Expected JSON object: {path}")
    return value


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    except FileNotFoundError as exc:
        raise ContractError(f"Missing evidence file: {path}") from exc


def load_hard_suite_config(project_root: Path) -> dict[str, Any]:
    return _read_object(project_root.resolve() / "configs" / "hard_suite.json")


def iter_hard_suite_variants(
    project_root: Path, *, partition: str = "development"
) -> list[dict[str, Any]]:
    """Return private variant specs without exposing them to an agent workspace."""

    project_root = project_root.resolve()
    if partition == "development":
        config = load_hard_suite_config(project_root)
        output = []
        for family in config["failure_families"]:
            shared = {
                key: family[key]
                for key in (
                    "family_id",
                    "failure_mode",
                    "observable_problem",
                    "scored_detection_and_containment",
                    "smallest_correct_next_action",
                    "resolving_intervention",
                    "causal_contrast",
                )
            }
            output.extend({**shared, **variant} for variant in family["variants"])
        return output
    if partition == "heldout":
        value = _read_object(project_root / "grader_private" / "hard_suite_heldout.json")
        return list(value["variants"])
    if partition == "ladder":
        return iter_hard_suite_ladder_variants(project_root)
    raise ConfigurationError(f"Unknown hard-suite partition: {partition}")


def iter_hard_suite_ladder_variants(project_root: Path) -> list[dict[str, Any]]:
    """Materialize controlled development ladders from predeclared templates."""

    config = load_hard_suite_config(project_root)
    development = iter_hard_suite_variants(project_root, partition="development")
    by_family: dict[str, list[dict[str, Any]]] = {}
    for variant in development:
        by_family.setdefault(str(variant["family_id"]), []).append(variant)
    output = []
    eligible_roles = {
        "resolving_intervention",
        "sufficient_evidence",
        "uncontained_control",
        "ineffective_control",
    }
    for ladder in config["breaking_point_ladders"]:
        family_id = str(ladder["family_id"])
        templates = by_family[family_id]
        template = next(
            (row for row in templates if row["pair_role"] in eligible_roles),
            templates[0],
        )
        for index, level in enumerate(ladder["levels"]):
            variant = deepcopy(template)
            variant["variant_id"] = f"ladder_{ladder['ladder_id']}_{index}"
            variant["pair_role"] = "breaking_point"
            variant["ladder_id"] = ladder["ladder_id"]
            variant["ladder_parameter"] = ladder["parameter"]
            variant["ladder_level"] = level
            variant["seed"] = int(template["seed"]) + 5_000 + index
            if ladder["parameter"] == "matched_auc":
                variant["generation"]["factorial_aucs"][-1] = float(level)
            else:
                variant["generation"][str(ladder["parameter"])] = level
            output.append(variant)
    return output


def load_hard_suite_variant(
    project_root: Path, variant_id: str, *, partition: str = "development"
) -> dict[str, Any]:
    matches = [
        row
        for row in iter_hard_suite_variants(project_root, partition=partition)
        if row["variant_id"] == variant_id
    ]
    if len(matches) != 1:
        raise ConfigurationError(
            f"Expected one {partition} hard-suite variant {variant_id}; found {len(matches)}"
        )
    return matches[0]


def validate_hard_suite_config(project_root: Path) -> dict[str, Any]:
    config = load_hard_suite_config(project_root)
    families = config.get("failure_families")
    if not isinstance(families, list) or len(families) != 5:
        raise ContractError("Hard suite must contain five failure families")
    weights = config.get("family_weights")
    if not isinstance(weights, dict) or not math.isclose(sum(weights.values()), 1.0):
        raise ContractError("Hard-suite family weights must sum to one")
    seen: set[str] = set()
    pair_roles: dict[str, set[str]] = {}
    for family in families:
        family_id = str(family["family_id"])
        if family_id not in weights:
            raise ContractError(f"Missing family weight: {family_id}")
        required = {
            "observable_problem",
            "scored_detection_and_containment",
            "smallest_correct_next_action",
            "resolving_intervention",
            "causal_contrast",
        }
        if not required <= set(family):
            raise ContractError(f"Incomplete failure contract for {family_id}")
        variants = family.get("variants")
        if not isinstance(variants, list) or len(variants) != 2:
            raise ContractError(f"{family_id} must have one predeclared intervention pair")
        pair_roles[family_id] = set()
        for variant in variants:
            variant_id = str(variant["variant_id"])
            if variant_id in seen:
                raise ContractError(f"Duplicate hard-suite variant: {variant_id}")
            seen.add(variant_id)
            pair_roles[family_id].add(str(variant["pair_role"]))
            generation = variant.get("generation")
            if not isinstance(generation, dict) or len(generation.get("factorial_aucs", [])) != 5:
                raise ContractError(f"Invalid generation contract: {variant_id}")
    heldout = iter_hard_suite_variants(project_root, partition="heldout")
    heldout_families = {str(row["family_id"]) for row in heldout}
    if heldout_families != set(weights) or len(heldout) != 10:
        raise ContractError("Held-out suite must contain a separate pair for every family")
    return {
        "family_count": len(families),
        "development_variant_count": len(seen),
        "heldout_variant_count": len(heldout),
        "equal_family_weights": len(set(weights.values())) == 1,
        "intervention_pairs_predeclared": True,
        "pair_roles": {family: sorted(roles) for family, roles in pair_roles.items()},
    }


def _auc(labels: list[int], scores: list[float]) -> float:
    positives = [score for label, score in zip(labels, scores, strict=True) if label == 1]
    negatives = [score for label, score in zip(labels, scores, strict=True) if label == 0]
    if not positives or not negatives:
        raise ContractError("AUC requires both outcome classes")
    wins = 0.0
    for positive in positives:
        for negative in negatives:
            if positive > negative:
                wins += 1.0
            elif positive == negative:
                wins += 0.5
    return wins / (len(positives) * len(negatives))


def _scores_for_auc(sample_count: int, target_auc: float, seed: int) -> list[dict[str, Any]]:
    negative_count = sample_count // 2
    positive_count = sample_count - negative_count
    total_wins = round(target_auc * positive_count * negative_count)
    base_wins, remainder = divmod(total_wins, positive_count)
    positive_scores = [
        min(negative_count, base_wins + (index < remainder)) - 0.5
        for index in range(positive_count)
    ]
    rows = [{"label": 0, "score": float(index)} for index in range(negative_count)] + [
        {"label": 1, "score": float(score)} for score in positive_scores
    ]
    random.Random(seed).shuffle(rows)
    return rows


def _pilot_rows(generation: dict[str, Any], seed: int) -> list[dict[str, Any]]:
    sample_count = int(generation["n"])
    signal = float(generation["pilot_signal"])
    target_auc = NormalDist().cdf(signal / math.sqrt(2.0))
    generated = _scores_for_auc(sample_count, target_auc, seed)
    flip_count = round(float(generation["label_disagreement"]) * sample_count)
    flip_order = list(range(sample_count))
    random.Random(seed + 41).shuffle(flip_order)
    flipped = set(flip_order[:flip_count])
    rows = []
    for index, row in enumerate(generated):
        true_label = int(row["label"])
        rows.append(
            {
                "sample_id": f"BIOPSY-{seed}-{index:04d}",
                "observed_label": true_label ^ int(index in flipped),
                "adjudicated_label": true_label,
                "locked_score": round(float(row["score"]), 8),
            }
        )
    return rows


def _batch_values(outcomes: list[int], target_phi: float, seed: int) -> list[int]:
    desired_agreement = (1.0 + target_phi) / 2.0
    batch = [0] * len(outcomes)
    rng = random.Random(seed)
    for outcome in (0, 1):
        indices = [index for index, value in enumerate(outcomes) if value == outcome]
        rng.shuffle(indices)
        agreement_count = round(desired_agreement * len(indices))
        for rank, index in enumerate(indices):
            batch[index] = outcome if rank < agreement_count else 1 - outcome
    return batch


def _generate_public_files(workspace: Path, variant: dict[str, Any]) -> list[dict[str, Any]]:
    generation = variant["generation"]
    seed = int(variant["seed"])
    development = {
        "cohort_id": f"DEV-{seed}",
        "endpoint": generation["development_endpoint"],
        "platform": generation["development_platform"],
        "drug": generation["development_drug"],
        "predictor_status": "locked_before_external_evidence",
    }
    validation = {
        "cohort_id": f"VAL-{seed}",
        "endpoint": generation["validation_endpoint"],
        "platform": generation["validation_platform"],
        "drug": generation["validation_drug"],
        "nominal_sample_count": generation["n"],
    }
    _write_json(workspace / "case" / "development_cohort.json", development)
    _write_json(workspace / "case" / "validation_cohort.json", validation)

    pilot_rows = _pilot_rows(generation, seed)
    identities = []
    for index, row in enumerate(pilot_rows):
        identities.append(
            {
                "sample_id": row["sample_id"],
                "patient_id": f"PATIENT-{seed}-{index:04d}",
                "visit_id": f"VISIT-{index % 3}",
                "expression_fingerprint": f"FP-{seed}-{index:04d}",
            }
        )
    for pair_index in range(int(generation["duplicate_pairs"])):
        left = 2 * pair_index
        right = left + 1
        identities[right]["expression_fingerprint"] = identities[left]["expression_fingerprint"]
    _write_csv(
        workspace / "data" / "sample_fingerprints.csv",
        ["sample_id", "patient_id", "visit_id", "expression_fingerprint"],
        identities,
    )

    required_count = 20
    retained = round((1.0 - float(generation["feature_dropout"])) * required_count)
    feature_rows = [
        {
            "gene_symbol": f"GENE-{index:03d}",
            "required_by_locked_model": 1,
            "available_on_validation_platform": int(index < retained),
        }
        for index in range(required_count)
    ]
    _write_csv(
        workspace / "data" / "feature_availability.csv",
        ["gene_symbol", "required_by_locked_model", "available_on_validation_platform"],
        feature_rows,
    )

    outcomes = [int(row["observed_label"]) for row in pilot_rows]
    batches = _batch_values(outcomes, float(generation["target_phi"]), seed + 11)
    metadata_rows = [
        {
            "sample_id": row["sample_id"],
            "site": f"SITE-{index % 3 + 1}",
            "batch": batches[index],
            "outcome": outcomes[index],
        }
        for index, row in enumerate(pilot_rows)
    ]
    _write_csv(
        workspace / "data" / "metadata.csv",
        ["sample_id", "site", "batch", "outcome"],
        metadata_rows,
    )
    _write_csv(
        workspace / "data" / "pilot_predictions.csv",
        ["sample_id", "observed_label", "locked_score"],
        [
            {
                "sample_id": row["sample_id"],
                "observed_label": row["observed_label"],
                "locked_score": row["locked_score"],
            }
            for row in pilot_rows
        ],
    )
    _write_json(
        workspace / "resources" / "resource_offer.json",
        {
            "provided_resource": variant["provided_intervention"],
            "delivery_status": "sealed_until_commitment",
            "scope_note": (
                "A supplied expert opinion explains plausibility but is not outcome evidence."
                if "expert" in str(variant["provided_intervention"])
                else "The resource must be verified from its post-commit evidence artifact."
            ),
        },
    )
    return pilot_rows


def _generate_sealed_files(
    sealed_root: Path, variant: dict[str, Any], pilot_rows: list[dict[str, Any]]
) -> None:
    generation = variant["generation"]
    seed = int(variant["seed"])
    factorial_rows = []
    for condition_index, (condition, target_auc) in enumerate(
        zip(_FACTORIAL_CONDITIONS, generation["factorial_aucs"], strict=True)
    ):
        rows = _scores_for_auc(
            int(generation["factorial_n"]), float(target_auc), seed + 100 + condition_index
        )
        for row_index, row in enumerate(rows):
            factorial_rows.append(
                {
                    "condition": condition,
                    "sample_id": f"BRIDGE-{seed}-{condition_index}-{row_index:04d}",
                    "label": row["label"],
                    "locked_score": row["score"],
                }
            )
    _write_csv(
        sealed_root / "factorial_predictions.csv",
        ["condition", "sample_id", "label", "locked_score"],
        factorial_rows,
    )
    _write_csv(
        sealed_root / "adjudicated_predictions.csv",
        ["sample_id", "observed_label", "adjudicated_label", "locked_score"],
        pilot_rows,
    )
    process_fixed = variant["provided_intervention"] == "leakage_safe_splitting"
    _write_json(
        sealed_root / "provenance.json",
        {
            "locked_model_sha256": canonical_sha256(
                {"model": "locked-linear-signature", "seed": seed}
            ),
            "feature_fit_scope": "training_only" if process_fixed else "not_documented",
            "patient_grouped_split": process_fixed,
            "leakage_safe_split_demonstrated": process_fixed,
        },
    )
    _write_json(
        sealed_root / "intervention_delivery.json",
        {
            "resource_id": variant["provided_intervention"],
            "delivered_after_commitment": True,
            "independent_of_locked_model": True,
            "outcome_evidence_included": variant["provided_intervention"]
            in {
                "endpoint_drug_platform_matched_cohort",
                "independent_replication",
                "expert_endpoint_adjudication",
                "patient_visit_reconciliation",
            },
        },
    )
    if variant["provided_intervention"] == "patient_visit_reconciliation":
        _write_csv(
            sealed_root / "patient_visit_reconciliation.csv",
            ["sample_id", "curated_patient_id", "curated_visit_id", "status"],
            [
                {
                    "sample_id": row["sample_id"],
                    "curated_patient_id": f"CURATED-{seed}-{index:04d}",
                    "curated_visit_id": f"VISIT-{index % 3}",
                    "status": "verified",
                }
                for index, row in enumerate(pilot_rows)
            ],
        )


def _public_task_contract(config: dict[str, Any], variant: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "0.2",
        "suite_id": config["suite_id"],
        "family_id": variant["family_id"],
        "variant_id": variant["variant_id"],
        "provided_intervention": variant["provided_intervention"],
        "research_question": (
            "Does the locked predictor have sufficient, integrity-safe evidence to advance, "
            "and what is the smallest next resource if it does not?"
        ),
        "metric_contract": {
            name: {"absolute_tolerance": tolerance, "definition": definition}
            for name, tolerance, definition in (
                (
                    "identity_conflict_count",
                    0.0,
                    "Count fingerprint groups spanning more than one patient_id or visit_id.",
                ),
                (
                    "required_feature_retention",
                    0.001,
                    "Available required features divided by all required features.",
                ),
                (
                    "batch_outcome_phi",
                    0.01,
                    "Signed binary phi coefficient for batch=1 and outcome=1.",
                ),
                ("pilot_n", 0.0, "Number of locked pilot predictions."),
                ("pilot_auc", 0.01, "Pairwise ROC AUC against observed labels."),
                (
                    "label_disagreement_rate",
                    0.001,
                    "Fraction of observed labels changed by blinded adjudication.",
                ),
                (
                    "adjudicated_auc",
                    0.01,
                    "Pairwise ROC AUC against adjudicated labels.",
                ),
                (
                    "adjudicated_auc_gain",
                    0.015,
                    "Adjudicated AUC minus pilot AUC.",
                ),
                (
                    "matched_evidence_n",
                    0.0,
                    "Number of all_matched factorial-bridge predictions.",
                ),
                (
                    "matched_evidence_auc",
                    0.01,
                    "ROC AUC in the all_matched factorial condition.",
                ),
                (
                    "endpoint_gain",
                    0.015,
                    "endpoint_matched AUC minus unmatched AUC.",
                ),
                (
                    "platform_gain",
                    0.015,
                    "platform_matched AUC minus unmatched AUC.",
                ),
                ("drug_gain", 0.015, "drug_matched AUC minus unmatched AUC."),
                (
                    "all_matched_gain",
                    0.015,
                    "all_matched AUC minus unmatched AUC.",
                ),
            )
        },
        "analysis_rules": {
            "roc_auc": (
                "Pairwise probability that a positive score exceeds a negative score; "
                "ties count 0.5."
            ),
            "transfer_interaction": (
                "all_matched_gain >= 0.10 while every individual matched gain is < 0.06"
            ),
            "factor_specific_transfer": "A mismatched factor with its individual gain >= 0.06.",
            "label_uncertainty": (
                "label_disagreement_rate >= 0.15 and adjudicated_auc_gain >= 0.08"
            ),
            "underpowered_validation": "matched_evidence_n < 50",
            "model_misspecification": ("matched_evidence_n >= 50 and matched_evidence_auc < 0.70"),
        },
        "decision_policy": config["public_decision_policy"],
        "metric_tolerances": _METRIC_TOLERANCES,
        "scoring_weights": config["scoring"],
        "schemas": {
            "commitment": "schemas/commitment.schema.json",
            "final_submission": "schemas/final_submission.schema.json",
        },
        "workflow": {
            "commitment_path": "submission/commitment.json",
            "final_submission_path": "submission/final_submission.json",
            "commitment_is_immutable": True,
            "reveal_is_single_use": True,
            "usable_unsubmitted_attempt_score": 0.0,
        },
    }


@dataclass(frozen=True, slots=True)
class HardSuitePackage:
    family_id: str
    variant_id: str
    partition: str
    workspace_root: Path
    sealed_root: Path
    package_digest: str
    sealed_digest: str
    private_variant: dict[str, Any]


class HardSuiteBuilder:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()

    def build(
        self,
        variant_id: str,
        *,
        output_root: Path,
        partition: str = "development",
        replace: bool = False,
    ) -> HardSuitePackage:
        config = load_hard_suite_config(self.project_root)
        validate_hard_suite_config(self.project_root)
        variant = load_hard_suite_variant(self.project_root, variant_id, partition=partition)
        destination = output_root / f"hard-{variant_id}"
        sealed_root = output_root / f"hard-{variant_id}-sealed"
        for path in (destination, sealed_root):
            if path.exists():
                if not replace:
                    raise ConfigurationError(f"Hard-suite build path exists: {path}")
                shutil.rmtree(path)
            path.mkdir(parents=True)
        task_root = self.project_root / "tasks" / "hard_suite_v0"
        for source in sorted(path for path in task_root.rglob("*") if path.is_file()):
            target = destination / source.relative_to(task_root)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        pilot_rows = _generate_public_files(destination, variant)
        _generate_sealed_files(sealed_root, variant, pilot_rows)
        manifest = {
            evidence_id: {
                "paths": paths,
                "status": "available"
                if all((destination / path).is_file() for path in paths)
                else "sealed_until_commitment",
            }
            for evidence_id, paths in _EVIDENCE_PATHS.items()
        }
        _write_json(destination / "evidence_manifest.json", manifest)
        _write_json(destination / "task.json", _public_task_contract(config, variant))
        (destination / "submission").mkdir()
        public_rows = [
            {
                "path": path.relative_to(destination).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in sorted(path for path in destination.rglob("*") if path.is_file())
        ]
        sealed_rows = [
            {
                "path": path.relative_to(sealed_root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in sorted(path for path in sealed_root.rglob("*") if path.is_file())
        ]
        package_digest = canonical_sha256(public_rows)
        sealed_digest = canonical_sha256(sealed_rows)
        _write_json(
            destination / "START_STATE.json",
            {
                "schema_version": "0.2",
                "family_id": variant["family_id"],
                "variant_id": variant_id,
                "partition": partition,
                "package_digest": package_digest,
                "sealed_evidence_visible": False,
                "private_answer_visible": False,
            },
        )
        return HardSuitePackage(
            family_id=str(variant["family_id"]),
            variant_id=variant_id,
            partition=partition,
            workspace_root=destination,
            sealed_root=sealed_root,
            package_digest=package_digest,
            sealed_digest=sealed_digest,
            private_variant=variant,
        )


def _binary_phi(rows: list[dict[str, str]]) -> float:
    counts = {(batch, outcome): 0 for batch in (0, 1) for outcome in (0, 1)}
    for row in rows:
        counts[(int(row["batch"]), int(row["outcome"]))] += 1
    n11 = counts[(1, 1)]
    n10 = counts[(1, 0)]
    n01 = counts[(0, 1)]
    n00 = counts[(0, 0)]
    denominator = math.sqrt((n11 + n10) * (n01 + n00) * (n11 + n01) * (n10 + n00))
    if denominator == 0:
        raise ContractError("Phi coefficient is undefined for a constant variable")
    return (n11 * n00 - n10 * n01) / denominator


def compute_hard_suite_metrics(workspace_root: Path) -> dict[str, float]:
    root = workspace_root.resolve()
    identities = _read_csv(root / "data" / "sample_fingerprints.csv")
    groups: dict[str, list[dict[str, str]]] = {}
    for row in identities:
        groups.setdefault(row["expression_fingerprint"], []).append(row)
    identity_conflicts = sum(
        len(group) > 1
        and (
            len({row["patient_id"] for row in group}) > 1
            or len({row["visit_id"] for row in group}) > 1
        )
        for group in groups.values()
    )
    features = _read_csv(root / "data" / "feature_availability.csv")
    required = [row for row in features if int(row["required_by_locked_model"]) == 1]
    retention = sum(int(row["available_on_validation_platform"]) for row in required) / len(
        required
    )
    metadata = _read_csv(root / "data" / "metadata.csv")
    pilot = _read_csv(root / "data" / "pilot_predictions.csv")
    pilot_auc = _auc(
        [int(row["observed_label"]) for row in pilot],
        [float(row["locked_score"]) for row in pilot],
    )
    adjudicated = _read_csv(root / "evidence" / "adjudicated_predictions.csv")
    disagreement = sum(
        int(row["observed_label"]) != int(row["adjudicated_label"]) for row in adjudicated
    ) / len(adjudicated)
    adjudicated_auc = _auc(
        [int(row["adjudicated_label"]) for row in adjudicated],
        [float(row["locked_score"]) for row in adjudicated],
    )
    factorial = _read_csv(root / "evidence" / "factorial_predictions.csv")
    factorial_aucs = {}
    factorial_counts = {}
    for condition in _FACTORIAL_CONDITIONS:
        selected = [row for row in factorial if row["condition"] == condition]
        factorial_counts[condition] = len(selected)
        factorial_aucs[condition] = _auc(
            [int(row["label"]) for row in selected],
            [float(row["locked_score"]) for row in selected],
        )
    unmatched = factorial_aucs["unmatched"]
    return {
        "identity_conflict_count": float(identity_conflicts),
        "required_feature_retention": retention,
        "batch_outcome_phi": _binary_phi(metadata),
        "pilot_n": float(len(pilot)),
        "pilot_auc": pilot_auc,
        "label_disagreement_rate": disagreement,
        "adjudicated_auc": adjudicated_auc,
        "adjudicated_auc_gain": adjudicated_auc - pilot_auc,
        "matched_evidence_n": float(factorial_counts["all_matched"]),
        "matched_evidence_auc": factorial_aucs["all_matched"],
        "endpoint_gain": factorial_aucs["endpoint_matched"] - unmatched,
        "platform_gain": factorial_aucs["platform_matched"] - unmatched,
        "drug_gain": factorial_aucs["drug_matched"] - unmatched,
        "all_matched_gain": factorial_aucs["all_matched"] - unmatched,
    }


def _diagnoses(workspace_root: Path, metrics: dict[str, float]) -> list[str]:
    root = workspace_root.resolve()
    development = _read_object(root / "case" / "development_cohort.json")
    validation = _read_object(root / "case" / "validation_cohort.json")
    diagnoses = []
    if metrics["identity_conflict_count"] > 0:
        diagnoses.append("identity_overlap")
    if abs(metrics["batch_outcome_phi"]) >= 0.30:
        diagnoses.append("batch_confounding")
    if metrics["label_disagreement_rate"] >= 0.15 and metrics["adjudicated_auc_gain"] >= 0.08:
        diagnoses.append("label_uncertainty")
    if metrics["required_feature_retention"] < 0.80:
        diagnoses.append("feature_contract_failure")
    individual = {
        "endpoint_mismatch": "endpoint_gain",
        "platform_shift": "platform_gain",
        "drug_transfer": "drug_gain",
    }
    mismatched = {
        "endpoint_mismatch": development["endpoint"] != validation["endpoint"],
        "platform_shift": development["platform"] != validation["platform"],
        "drug_transfer": development["drug"] != validation["drug"],
    }
    gains = [metrics[name] for name in ("endpoint_gain", "platform_gain", "drug_gain")]
    if metrics["all_matched_gain"] >= 0.10 and max(gains) < 0.06:
        diagnoses.append("transfer_interaction")
    else:
        diagnoses.extend(
            failure
            for failure, metric_name in individual.items()
            if mismatched[failure] and metrics[metric_name] >= 0.06
        )
    if metrics["matched_evidence_n"] < 50:
        diagnoses.append("underpowered_validation")
    elif metrics["matched_evidence_auc"] < 0.70:
        diagnoses.append("model_misspecification")
    return diagnoses or ["no_material_failure"]


def _decision(workspace_root: Path, metrics: dict[str, float]) -> str:
    provenance = _read_object(workspace_root.resolve() / "evidence" / "provenance.json")
    identity_stop = metrics["identity_conflict_count"] > 0
    batch_stop = (
        abs(metrics["batch_outcome_phi"]) >= 0.50
        and not provenance["leakage_safe_split_demonstrated"]
    )
    if identity_stop or batch_stop:
        return "stop"
    advance = (
        metrics["identity_conflict_count"] == 0
        and metrics["required_feature_retention"] >= 0.80
        and abs(metrics["batch_outcome_phi"]) < 0.30
        and metrics["label_disagreement_rate"] < 0.15
        and metrics["matched_evidence_n"] >= 50
        and metrics["matched_evidence_auc"] >= 0.70
    )
    return "advance" if advance else "insufficient_evidence"


def _expected_intervention_assessment(variant: dict[str, Any]) -> str:
    effect = str(variant["expected_resource_effect"])
    if effect == "resolves_execution_not_scientific_judgment":
        return "resolves_process_only"
    if effect == "does_not_resolve_evidence_abstention_correct":
        return "evidence_still_insufficient"
    if effect.startswith("resolves"):
        return "resolves"
    return "does_not_resolve"


def solve_hard_suite(workspace_root: Path, variant: dict[str, Any]) -> dict[str, Any]:
    root = workspace_root.resolve()
    task = _read_object(root / "task.json")
    metrics = compute_hard_suite_metrics(root)
    decision = _decision(root, metrics)
    diagnoses = _diagnoses(root, metrics)
    primary = diagnoses[0]
    if decision == "advance":
        primary = "no_material_failure"
        secondary: list[str] = []
    else:
        secondary = diagnoses[1:]
    evidence = set(_FAILURE_TO_EVIDENCE[primary])
    evidence.add("EV-INTERVENTION")
    experiment = _FAILURE_TO_EXPERIMENT[primary]
    resource = _FAILURE_TO_RESOURCE[primary]
    return {
        "family_id": task["family_id"],
        "variant_id": task["variant_id"],
        "decision": decision,
        "confidence": 1.0,
        "primary_failure": primary,
        "secondary_failures": secondary,
        "metrics": metrics,
        "evidence_ids": sorted(evidence),
        "containment_status": ("verified_no_issue" if decision == "advance" else "contained"),
        "smallest_resolving_experiment": experiment,
        "recommended_resource": resource,
        "provided_intervention_assessment": _expected_intervention_assessment(variant),
        "unnecessary_escalation": False,
        "rationale": (
            "Reference solution recomputed from the visible evidence under the public rules."
        ),
    }


def reference_commitment(workspace_root: Path, variant: dict[str, Any]) -> dict[str, Any]:
    task = _read_object(workspace_root.resolve() / "task.json")
    family_failure = str(variant["failure_mode"])
    alternate = {
        "identity_overlap": "batch_confounding",
        "transfer_interaction": "endpoint_mismatch",
        "batch_confounding": "endpoint_mismatch",
        "label_uncertainty": "underpowered_validation",
        "underpowered_validation": "transfer_interaction",
    }[family_failure]
    return {
        "family_id": task["family_id"],
        "variant_id": task["variant_id"],
        "ranked_hypotheses": [family_failure, alternate],
        "planned_metric_ids": sorted(
            _FAILURE_TO_METRICS[family_failure]
            | {
                "identity_conflict_count",
                "pilot_auc",
                "matched_evidence_auc",
                "matched_evidence_n",
            }
        ),
        "selected_discriminating_experiment": variant["smallest_correct_next_action"],
        "pre_reveal_decision": "insufficient_evidence",
        "if_leading_supported": "stop"
        if family_failure in {"identity_overlap", "batch_confounding"}
        else "insufficient_evidence",
        "if_leading_refuted": "advance",
    }


@dataclass(frozen=True, slots=True)
class HardSuiteGrade:
    score: float
    components: dict[str, float]
    expected_decision: str
    expected_primary_failure: str
    decision_correct: bool
    detection_correct: bool
    containment_correct: bool
    smallest_action_correct: bool
    intervention_assessment_correct: bool
    metric_scores: dict[str, float]
    commitment_immutable: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "components": self.components,
            "expected_decision": self.expected_decision,
            "expected_primary_failure": self.expected_primary_failure,
            "decision_correct": self.decision_correct,
            "detection_correct": self.detection_correct,
            "containment_correct": self.containment_correct,
            "smallest_action_correct": self.smallest_action_correct,
            "intervention_assessment_correct": self.intervention_assessment_correct,
            "metric_scores": self.metric_scores,
            "commitment_immutable": self.commitment_immutable,
        }


def _numeric_credit(expected: float, submitted: Any, tolerance: float) -> float:
    try:
        value = float(submitted)
    except (TypeError, ValueError):
        return 0.0
    error = abs(value - expected)
    if error <= tolerance + 1e-12:
        return 100.0
    scale = max(tolerance * 5.0, abs(expected) * 0.10, 0.02)
    return max(0.0, 100.0 * (1.0 - error / scale))


def grade_hard_suite(
    workspace_root: Path,
    variant: dict[str, Any],
    commitment: dict[str, Any] | None,
    submission: dict[str, Any] | None,
    *,
    commitment_immutable: bool,
) -> HardSuiteGrade:
    expected = solve_hard_suite(workspace_root, variant)
    if submission is None:
        return HardSuiteGrade(
            score=0.0,
            components={name: 0.0 for name in load_hard_suite_config_from_task(workspace_root)},
            expected_decision=expected["decision"],
            expected_primary_failure=expected["primary_failure"],
            decision_correct=False,
            detection_correct=False,
            containment_correct=False,
            smallest_action_correct=False,
            intervention_assessment_correct=False,
            metric_scores={name: 0.0 for name in _METRIC_TOLERANCES},
            commitment_immutable=commitment_immutable,
        )
    metric_scores = {
        name: _numeric_credit(
            float(expected["metrics"][name]),
            submission.get("metrics", {}).get(name),
            tolerance,
        )
        for name, tolerance in _METRIC_TOLERANCES.items()
    }
    quantitative = sum(metric_scores.values()) / len(metric_scores)
    decision_correct = submission.get("decision") == expected["decision"]
    detection_correct = submission.get("primary_failure") == expected["primary_failure"]
    submitted_failures = set(submission.get("secondary_failures", []))
    expected_secondary = set(expected["secondary_failures"])
    secondary_recall = (
        1.0
        if not expected_secondary
        else len(submitted_failures & expected_secondary) / len(expected_secondary)
    )
    diagnosis = 60.0 * detection_correct + 40.0 * secondary_recall
    submitted_evidence = set(submission.get("evidence_ids", []))
    expected_evidence = set(expected["evidence_ids"])
    evidence = 100.0 * len(submitted_evidence & expected_evidence) / len(expected_evidence)
    containment_correct = submission.get("containment_status") == expected["containment_status"]
    smallest_action_correct = (
        submission.get("smallest_resolving_experiment") == expected["smallest_resolving_experiment"]
        and submission.get("recommended_resource") == expected["recommended_resource"]
    )
    intervention_correct = (
        submission.get("provided_intervention_assessment")
        == expected["provided_intervention_assessment"]
    )
    recovery = (
        30.0 * containment_correct
        + 45.0 * smallest_action_correct
        + 20.0 * intervention_correct
        + 5.0 * (submission.get("unnecessary_escalation") is False)
    )
    family_failure = str(variant["failure_mode"])
    commitment = commitment or {}
    hypotheses = set(commitment.get("ranked_hypotheses", []))
    planned = set(commitment.get("planned_metric_ids", []))
    required_planned = _FAILURE_TO_METRICS[family_failure]
    planned_recall = len(planned & required_planned) / len(required_planned)
    commitment_score = (
        30.0 * commitment_immutable
        + 25.0 * (family_failure in hypotheses)
        + 25.0 * planned_recall
        + 20.0
        * (
            commitment.get("selected_discriminating_experiment")
            == variant["smallest_correct_next_action"]
        )
    )
    components = {
        "decision": 100.0 * decision_correct,
        "quantitative_analysis": quantitative,
        "scientific_diagnosis": diagnosis,
        "evidence_integration": evidence,
        "recovery_design": recovery,
        "commitment_and_reproducibility": commitment_score,
    }
    weights = load_hard_suite_config_from_task(workspace_root)
    score = sum(components[name] * float(weights[name]) for name in components)
    return HardSuiteGrade(
        score=round(score, 6),
        components={name: round(value, 6) for name, value in components.items()},
        expected_decision=expected["decision"],
        expected_primary_failure=expected["primary_failure"],
        decision_correct=decision_correct,
        detection_correct=detection_correct,
        containment_correct=containment_correct,
        smallest_action_correct=smallest_action_correct,
        intervention_assessment_correct=intervention_correct,
        metric_scores={name: round(value, 6) for name, value in metric_scores.items()},
        commitment_immutable=commitment_immutable,
    )


def load_hard_suite_config_from_task(workspace_root: Path) -> dict[str, float]:
    task = _read_object(workspace_root.resolve() / "task.json")
    return {name: float(value) for name, value in task["scoring_weights"].items()}


def _validate_schema(value: dict[str, Any], schema_path: Path, label: str) -> None:
    from jsonschema import Draft202012Validator

    schema = _read_object(schema_path)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(value),
        key=lambda item: list(item.path),
    )
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.absolute_path)
        suffix = f" at {location}" if location else ""
        raise ContractError(f"{label} violates public schema{suffix}: {first.message}")


class HardSuiteEnvironment:
    def __init__(self, package: HardSuitePackage) -> None:
        self.package = package
        self.workspace_root = package.workspace_root.resolve()
        self.sealed_root = package.sealed_root.resolve()
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
        self.commitment = value
        self.commitment_sha256 = sha256_file(path)
        return "Commitment accepted and hashed. You may now call reveal_evidence once."

    def reveal_evidence(self) -> str:
        if self.commitment is None:
            raise InvalidTransitionError("commit_plan must succeed before reveal_evidence")
        if self.revealed:
            raise InvalidTransitionError("reveal_evidence may be called only once")
        evidence_root = self.workspace_root / "evidence"
        evidence_root.mkdir()
        for source in sorted(path for path in self.sealed_root.rglob("*") if path.is_file()):
            target = evidence_root / source.relative_to(self.sealed_root)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        manifest = _read_object(self.workspace_root / "evidence_manifest.json")
        for record in manifest.values():
            if all((self.workspace_root / path).is_file() for path in record["paths"]):
                record["status"] = "available"
        _write_json(self.workspace_root / "evidence_manifest.json", manifest)
        _write_json(
            self.workspace_root / "REVEAL_STATE.json",
            {
                "commitment_sha256": self.commitment_sha256,
                "sealed_digest": self.package.sealed_digest,
                "reveal_complete": True,
            },
        )
        self.revealed = True
        return "Sealed evidence revealed. Recompute the full metric set before submission."

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
        manifest = _read_object(self.workspace_root / "evidence_manifest.json")
        unknown = sorted(set(value["evidence_ids"]) - set(manifest))
        if unknown:
            raise ContractError(f"Unknown evidence IDs: {unknown}")
        self.commitment_immutable = True
        self.submission = value
        return "Submission accepted. The sealed grader will recompute all metrics."

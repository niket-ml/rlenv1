"""Deterministic quantitative breaking-point ladders for hard suite v0.4."""

from __future__ import annotations

import math
import random
from pathlib import Path
from typing import Any

from uc_bench.hard_suite_v04 import (
    V04_LADDERS_PATH,
    _decision_context,
    _evidence_metrics,
    _generate_evidence,
    _generate_identity,
    _generate_labels,
    _generate_transport,
    _identity_metrics,
    _label_metrics,
    _process_metrics,
    _read_object,
    _sigmoid,
    _transport_metrics,
    load_v04_config,
)


def _contract(seed: int, config: dict[str, Any]) -> dict[str, Any]:
    return {
        "bootstrap_seed": seed + int(config["bootstrap"]["development_seed_offset"]),
        "bootstrap_replicates": int(config["bootstrap"]["replicates"]),
        "permutation_seed": seed + int(config["bootstrap"]["development_seed_offset"]) + 701,
        "permutation_replicates": int(config["permutation"]["replicates"]),
    }


def _identity_rows(seed: int, mean_rows: float) -> list[dict[str, Any]]:
    base = _generate_identity(seed, "none", False)
    by_cluster: dict[str, list[dict[str, Any]]] = {}
    for row in base:
        by_cluster.setdefault(str(row["cluster_id"]), []).append(row)
    output = []
    extra_target = round(len(by_cluster) * (mean_rows - 1.0))
    for patient_index, rows in enumerate(by_cluster.values()):
        first = dict(rows[0])
        first["reported_patient_id"] = f"P-{patient_index:03d}"
        output.append(first)
    cluster_ids = list(by_cluster)
    for extra_index in range(extra_target):
        cluster_id = cluster_ids[extra_index % len(cluster_ids)]
        source = output[extra_index % len(output)]
        duplicate = dict(source)
        duplicate["row_id"] = f"{source['row_id']}-X{extra_index:03d}"
        duplicate["cluster_id"] = cluster_id
        duplicate["visit_id"] = f"VX{extra_index:03d}"
        duplicate["reported_patient_id"] = f"{source['reported_patient_id']}-X{extra_index:03d}"
        output.append(duplicate)
    return output


def _transport_rows(seed: int, joint_bonus: float) -> list[dict[str, Any]]:
    rows = _generate_transport(seed, "none", False)
    output = []
    for row in rows:
        value = dict(row)
        if all(int(row[name]) == 1 for name in ("endpoint_match", "drug_match", "platform_match")):
            score = float(row["locked_score"])
            logit = math.log(score / (1 - score))
            direction = 1 if int(row["label"]) else -1
            value["locked_score"] = round(_sigmoid(logit + joint_bonus * direction), 8)
        output.append(value)
    return output


def _process_rows(seed: int, correlation: float) -> list[dict[str, Any]]:
    rng = random.Random(seed + round(correlation * 1000))
    rows = []
    for patient in range(120):
        batch = patient % 2
        probability = 0.5 + (correlation / 2 if batch else -correlation / 2)
        label = int(rng.random() < probability)
        biological = 0.22 * (1 if label else -1)
        batch_signal = 1.05 * (1 if batch else -1)
        for visit in range(2):
            noise = rng.gauss(0, 0.85)
            rows.append(
                {
                    "row_id": f"LC-{patient:03d}-{visit}",
                    "patient_id": f"LP-{patient:03d}",
                    "batch": batch,
                    "label": label,
                    "naive_score": round(_sigmoid(biological + batch_signal + noise), 8),
                    "grouped_score": round(
                        _sigmoid(biological + 0.75 * batch_signal + noise), 8
                    ),
                    "blocked_score": round(_sigmoid(biological + noise), 8),
                }
            )
    return rows


def _label_rows(seed: int, ambiguity: float) -> list[dict[str, Any]]:
    rows = _generate_labels(seed, "none", False)
    ambiguous = round(len(rows) * ambiguity)
    for index, row in enumerate(rows):
        label = int(row["reviewer_a"])
        row["reviewer_b"] = 1 - label if index < ambiguous else label
        row["extraction_label"] = 1 - label if index < ambiguous and index % 3 else label
    return rows


def build_v04_ladder_rows(project_root: Path) -> list[dict[str, Any]]:
    root = project_root.resolve()
    config = load_v04_config(root)
    ladder_config = _read_object(root / V04_LADDERS_PATH)
    family_seed = {
        str(pair["family_id"]): int(pair["seed"]) + 6000
        for pair in config["development_pairs"]
    }
    output = []
    for ladder in ladder_config["ladders"]:
        family_id = str(ladder["family_id"])
        seed = family_seed[family_id]
        contract = _contract(seed, config)
        context = _decision_context(family_id)
        for level in ladder["levels"]:
            if family_id == "Q01_identity_dependence":
                metrics = _identity_metrics(_identity_rows(seed, float(level)), contract)
                decision = "stop" if metrics["identity_conflict_count"] > 0 else "advance"
                key_metrics = {
                    "identity_conflict_count": metrics["identity_conflict_count"],
                    "kish_effective_n": metrics["kish_effective_n"],
                    "leakage_inflation": metrics["leakage_inflation"],
                }
            elif family_id == "Q02_transport_factorial":
                metrics = _transport_metrics(_transport_rows(seed, float(level)), contract)
                decision = (
                    "advance"
                    if metrics["all_matched_auc"] >= context["minimum_all_matched_auc"]
                    else "insufficient_evidence"
                )
                key_metrics = {
                    "all_matched_auc": metrics["all_matched_auc"],
                    "three_way_interaction": metrics["three_way_interaction"],
                }
            elif family_id == "Q03_process_confounding":
                metrics = _process_metrics(_process_rows(seed, float(level)), contract)
                decision = (
                    "stop"
                    if metrics["naive_minus_blocked_auc"]
                    > context["maximum_unsafe_auc_inflation"]
                    or abs(metrics["batch_outcome_phi"]) >= 0.45
                    else "insufficient_evidence"
                )
                key_metrics = {
                    "batch_outcome_phi": metrics["batch_outcome_phi"],
                    "naive_minus_blocked_auc": metrics["naive_minus_blocked_auc"],
                    "within_batch_permutation_p": metrics["within_batch_permutation_p"],
                }
            elif family_id == "Q04_label_sensitivity":
                metrics = _label_metrics(_label_rows(seed, float(level)))
                decision = (
                    "advance"
                    if metrics["sensitivity_auc_low"]
                    >= context["minimum_unadjudicated_sensitivity_bound"]
                    else "insufficient_evidence"
                )
                key_metrics = {
                    "ambiguous_fraction": metrics["ambiguous_fraction"],
                    "sensitivity_auc_low": metrics["sensitivity_auc_low"],
                    "sensitivity_auc_high": metrics["sensitivity_auc_high"],
                }
            else:
                master = _generate_evidence(seed, "R3", True)
                rows = master[: int(level)]
                metrics = _evidence_metrics(rows, contract, context)
                decision = (
                    "advance"
                    if metrics["auc_ci_low"] >= context["minimum_auc_ci_low"]
                    and metrics["target_prevalence_ppv"]
                    >= context["minimum_target_prevalence_ppv"]
                    and metrics["net_benefit"] >= context["minimum_net_benefit"]
                    and metrics["brier_score"] <= context["maximum_brier_score"]
                    and metrics["required_sample_size"]
                    <= metrics["observed_sample_size"]
                    else "insufficient_evidence"
                )
                key_metrics = {
                    "auc_ci_low": metrics["auc_ci_low"],
                    "net_benefit": metrics["net_benefit"],
                    "observed_sample_size": metrics["observed_sample_size"],
                    "required_sample_size": metrics["required_sample_size"],
                }
            output.append(
                {
                    "ladder_id": ladder["ladder_id"],
                    "family_id": family_id,
                    "parameter": ladder["parameter"],
                    "level": level,
                    "reference_decision": decision,
                    "key_metrics": {
                        name: round(float(value), 8)
                        for name, value in key_metrics.items()
                    },
                }
            )
    return output

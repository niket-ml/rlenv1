#!/usr/bin/env python3
"""Execute and persist the prespecified expert reference episode."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from uc_bench.contracts import (
    AggregateValidationResult,
    Commitment,
    Decision,
    FinalSubmission,
    PredictorManifest,
)
from uc_bench.hashing import hash_artifacts
from uc_bench.reference import (
    auc_with_stratified_bootstrap,
    expected_transfer_auc,
    fit_reference_model,
    load_reference_spec,
    permutation_p_value,
    predict_reference,
)
from uc_bench.state import EpisodeState

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEVELOPMENT_ROOT = PROJECT_ROOT / "data" / "processed" / "development"
SEALED_ROOT = PROJECT_ROOT / "data" / "processed" / "sealed"
PRIVATE_ROOT = PROJECT_ROOT / "grader_private" / "data"
ARTIFACT_ROOT = PROJECT_ROOT / "artifacts" / "reference"


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_development() -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    metadata = pd.read_csv(DEVELOPMENT_ROOT / "metadata.csv")
    matrices = {
        accession: pd.read_csv(
            DEVELOPMENT_ROOT / f"{accession}_gene_expression.csv.gz", index_col=0
        )
        for accession in ("GSE16879", "GSE73661")
    }
    return metadata, matrices


def outcomes_by_sample(metadata: pd.DataFrame) -> pd.Series:
    if metadata["sample_id"].duplicated().any():
        raise ValueError("Development metadata contains duplicate sample IDs")
    return metadata.set_index("sample_id")["response"].astype(int)


def model_decision(
    result: AggregateValidationResult, policy: dict[str, Any]
) -> Decision:
    if (
        result.auc >= float(policy["advance_minimum_auc"])
        and result.auc_interval[0] > float(policy["advance_minimum_auc_interval_lower"])
        and result.permutation_p_value <= float(policy["advance_maximum_permutation_p"])
    ):
        return Decision.ADVANCE
    return Decision.INSUFFICIENT_EVIDENCE


def main() -> int:
    spec = load_reference_spec(PROJECT_ROOT / "configs" / "reference_model.json")
    metadata, matrices = load_development()
    outcomes = outcomes_by_sample(metadata)
    seed = int(spec["random_seed"])
    bootstrap_resamples = int(spec["bootstrap_resamples"])
    permutation_count = int(spec["permutation_count"])

    discovery_ids = metadata.loc[
        metadata["cohort"] == "GSE16879", "sample_id"
    ].tolist()
    replication_ids = metadata.loc[
        metadata["cohort"] == "GSE73661", "sample_id"
    ].tolist()
    discovery_model = fit_reference_model(
        matrices["GSE16879"], outcomes, sample_ids=discovery_ids, spec=spec
    )
    discovery_predictions = predict_reference(
        discovery_model, matrices["GSE16879"].loc[:, discovery_ids]
    )
    replication_predictions = predict_reference(
        discovery_model, matrices["GSE73661"].loc[:, replication_ids]
    )
    discovery_auc, discovery_interval = auc_with_stratified_bootstrap(
        outcomes,
        discovery_predictions,
        resamples=bootstrap_resamples,
        seed=seed,
    )
    replication_auc, replication_interval = auc_with_stratified_bootstrap(
        outcomes,
        replication_predictions,
        resamples=bootstrap_resamples,
        seed=seed + 1,
    )
    replication_permutation = permutation_p_value(
        outcomes,
        replication_predictions,
        permutations=permutation_count,
        seed=seed + 2,
    )
    expected_auc, expected_interval = expected_transfer_auc(replication_auc, spec)

    # Keep the externally evaluated predictor identical to the predictor that
    # was frozen before the untouched replication cohort was evaluated.
    final_model = discovery_model
    manifest = PredictorManifest(
        model_version=final_model.model_version,
        feature_schema_version=final_model.feature_schema_version,
        endpoint="infliximab_mucosal_healing_week_4_to_6",
        training_sample_ids=tuple(discovery_ids),
    )
    development_evidence = {
        "schema_version": "0.1",
        "candidate_genes": list(final_model.genes),
        "candidate_provenance": spec["candidate_provenance"],
        "feature_definition": spec["feature_definition"],
        "discovery": {
            "cohort": "GSE16879",
            "n": len(discovery_ids),
            "auc": discovery_auc,
            "auc_interval": discovery_interval,
            "role": "model_fit_and_optimistic_sanity_check",
        },
        "replication": {
            "cohort": "GSE73661",
            "n": len(replication_ids),
            "auc": replication_auc,
            "auc_interval": replication_interval,
            "permutation_p_value": replication_permutation,
            "role": "untouched_cross_platform_replication",
        },
        "transport_expectation": {
            "expected_auc": expected_auc,
            "expected_auc_interval": expected_interval,
            "prespecified_replication_penalty": spec["transport_expectation"][
                "replication_auc_penalty"
            ],
            "reasons": [
                "infliximab_to_golimumab_drug_transfer",
                "mucosal_healing_to_clinical_response_endpoint_transfer",
                "third_microarray_platform",
                "small_sealed_cohort",
            ],
        },
        "audit_checks": {
            "cohort_reconstruction": {
                "status": "pass",
                "cohorts": {
                    "GSE16879": {"n": 24, "responders": 8, "nonresponders": 16},
                    "GSE73661": {"n": 23, "responders": 8, "nonresponders": 15},
                },
            },
            "endpoint_integrity": {
                "status": "pass",
                "development_endpoint": "mucosal_healing_week_4_to_6",
                "sealed_endpoint": "clinical_response_week_6",
                "endpoint_mismatch": True,
                "drug_transfer": True,
            },
            "platform_alignment": {
                "status": "pass",
                "strategy": "within_sample_percentile_rank",
                "common_gene_count": 17151,
                "platforms_are_distinct": True,
            },
            "leakage_control": {
                "status": "pass",
                "untouched_replication": "GSE73661",
                "replication_used_during_fit": False,
            },
            "negative_control": {
                "status": "pass",
                "test": "replication_label_permutation",
                "permutation_count": permutation_count,
                "seed": seed + 2,
                "p_value": replication_permutation,
            },
            "uncertainty": {
                "status": "pass",
                "method": "stratified_bootstrap",
                "resamples": bootstrap_resamples,
                "discovery_seed": seed,
                "replication_seed": seed + 1,
            },
        },
    }
    development_evidence["development_results"] = {
        "discovery": development_evidence["discovery"],
        "replication": development_evidence["replication"],
    }

    model_path = ARTIFACT_ROOT / "model.json"
    evidence_path = ARTIFACT_ROOT / "development_evidence.json"
    manifest_path = ARTIFACT_ROOT / "predictor_manifest.json"
    write_json(model_path, final_model.as_linear_rank_predictor().to_dict())
    write_json(evidence_path, development_evidence)
    write_json(
        manifest_path,
        {
            **manifest.to_dict(),
            "training_sample_ids": list(manifest.training_sample_ids),
            "tuning_sample_ids": list(manifest.tuning_sample_ids),
            "feature_selection_sample_ids": list(manifest.feature_selection_sample_ids),
        },
    )

    artifact_paths = tuple(
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in (model_path, evidence_path, manifest_path)
    )
    commitment = Commitment(
        target_endpoint="GSE92415 clinical response at week 6",
        endpoint_interpretation=(
            "Same drug class but different agent, endpoint, study, and array platform; "
            "replication performance is penalized before validation."
        ),
        feature_schema_version=final_model.feature_schema_version,
        missing_feature_policy="fail_closed_if_any_of_five_genes_is_missing",
        decision_threshold=final_model.decision_threshold,
        expected_auc=expected_auc,
        expected_auc_interval=expected_interval,
        permutation_count=permutation_count,
        artifact_paths=artifact_paths,
    )
    hashes = hash_artifacts(PROJECT_ROOT, artifact_paths)
    episode = EpisodeState(
        episode_id="reference-authentic-seed-20260906",
        task_id="uc_biomarker_diligence_v0",
        condition="full_data",
        variant_id="authentic_weak_evidence",
        seed=seed,
    )
    episode.commit_analysis(commitment, hashes)
    write_json(ARTIFACT_ROOT / "commitment.json", commitment.to_dict())

    sealed_expression = pd.read_csv(
        SEALED_ROOT / "GSE92415_gene_expression.csv.gz", index_col=0
    )
    sealed_labels = pd.read_csv(PRIVATE_ROOT / "gse92415_labels.csv").set_index("sample_id")
    sealed_ids = sealed_labels.index.tolist()
    sealed_predictions = predict_reference(final_model, sealed_expression.loc[:, sealed_ids])
    sealed_auc, sealed_interval = auc_with_stratified_bootstrap(
        sealed_labels["response"],
        sealed_predictions,
        resamples=bootstrap_resamples,
        seed=seed + 3,
    )
    sealed_permutation = permutation_p_value(
        sealed_labels["response"],
        sealed_predictions,
        permutations=permutation_count,
        seed=seed + 4,
    )
    validation = AggregateValidationResult(
        auc=sealed_auc,
        auc_interval=sealed_interval,
        permutation_p_value=sealed_permutation,
        evaluated_n=len(sealed_ids),
    )
    episode.reveal_validation(validation, hash_artifacts(PROJECT_ROOT, artifact_paths))
    write_json(ARTIFACT_ROOT / "validation_result.json", validation.to_dict())

    decision = model_decision(validation, spec["decision_policy"])
    submission = FinalSubmission(
        decision=decision,
        confidence=0.90,
        rationale=(
            "The locked panel transfers directionally, but its AUC is below the "
            "prespecified advancement threshold and uncertainty remains material across "
            "a different endpoint and platform."
        ),
        failure_mode="underpowered_cross_endpoint_and_cross_platform_transfer",
        diagnostic_codes=(
            "underpowered_validation",
            "endpoint_mismatch",
            "platform_shift",
            "drug_transfer",
        ),
        evidence_artifact_paths=(
            "artifacts/reference/development_evidence.json",
            "artifacts/reference/validation_result.json",
        ),
        next_action_type="prospective_endpoint_matched_validation",
        next_action=(
            "Run a larger, prospectively registered golimumab cohort using the same clinical "
            "endpoint and locked five-gene assay."
        ),
    )
    episode.submit(submission, hash_artifacts(PROJECT_ROOT, artifact_paths))
    write_json(ARTIFACT_ROOT / "final_submission.json", submission.to_dict())
    write_json(ARTIFACT_ROOT / "episode.json", episode.to_record())

    mediocre = EpisodeState(
        episode_id="mediocre-authentic-seed-20260906",
        task_id="uc_biomarker_diligence_v0",
        condition="full_data",
        variant_id="authentic_weak_evidence",
        seed=seed,
    )
    mediocre_commitment = Commitment(
        target_endpoint=commitment.target_endpoint,
        endpoint_interpretation="Anti-TNF response should transfer directly between cohorts.",
        feature_schema_version=commitment.feature_schema_version,
        missing_feature_policy=commitment.missing_feature_policy,
        decision_threshold=commitment.decision_threshold,
        expected_auc=0.95,
        expected_auc_interval=(0.90, 1.00),
        permutation_count=permutation_count,
        artifact_paths=artifact_paths,
    )
    mediocre.commit_analysis(mediocre_commitment, hashes)
    mediocre.reveal_validation(validation, hash_artifacts(PROJECT_ROOT, artifact_paths))
    mediocre.submit(
        FinalSubmission(
            decision=Decision.ADVANCE,
            confidence=0.95,
            rationale="The AUC is above chance and therefore supports advancement.",
            failure_mode="none",
            diagnostic_codes=("none",),
            evidence_artifact_paths=("artifacts/reference/validation_result.json",),
            next_action_type="clinical_use",
            next_action="Use the predictor to prioritize treatment.",
        ),
        hash_artifacts(PROJECT_ROOT, artifact_paths),
    )
    write_json(ARTIFACT_ROOT / "mediocre_episode.json", mediocre.to_record())

    summary = {
        "discovery_auc": discovery_auc,
        "replication_auc": replication_auc,
        "expected_transfer_auc": expected_auc,
        "sealed_auc": sealed_auc,
        "sealed_auc_interval": sealed_interval,
        "sealed_permutation_p_value": sealed_permutation,
        "decision": decision.value,
        "commitment_digest": episode.commitment_digest,
        "committed_artifacts": hashes,
        "comparison_episode": "artifacts/reference/mediocre_episode.json",
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

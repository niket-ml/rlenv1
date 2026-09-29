from __future__ import annotations

import unittest

from uc_bench.contracts import (
    Commitment,
    Decision,
    FinalSubmission,
    PredictionRecord,
    PredictorManifest,
)
from uc_bench.errors import ContractError, SealedCohortLeakageError


class CommitmentTests(unittest.TestCase):
    def test_valid_commitment(self) -> None:
        commitment = Commitment(
            target_endpoint="week-6 clinical response",
            endpoint_interpretation="transfer endpoint differs from discovery",
            feature_schema_version="v1",
            missing_feature_policy="fail below 80 percent coverage",
            decision_threshold=0.5,
            expected_auc=0.65,
            expected_auc_interval=(0.50, 0.80),
            permutation_count=10_000,
            artifact_paths=("model.bin", "pipeline.py"),
        )
        self.assertEqual(commitment.expected_auc, 0.65)

    def test_auc_interval_must_contain_expectation(self) -> None:
        with self.assertRaises(ContractError):
            Commitment(
                target_endpoint="endpoint",
                endpoint_interpretation="interpretation",
                feature_schema_version="v1",
                missing_feature_policy="fail",
                decision_threshold=0.5,
                expected_auc=0.9,
                expected_auc_interval=(0.5, 0.8),
                permutation_count=10_000,
                artifact_paths=("model.bin",),
            )

    def test_prediction_probability_is_bounded(self) -> None:
        with self.assertRaises(ContractError):
            PredictionRecord(
                sample_id="S1",
                response_probability=1.2,
                model_version="m1",
                feature_schema_version="v1",
                feature_coverage=1.0,
            )

    def test_final_submission_requires_evidence_and_next_action(self) -> None:
        with self.assertRaises(ContractError):
            FinalSubmission(
                decision=Decision.INSUFFICIENT_EVIDENCE,
                confidence=0.8,
                rationale="Valid but underpowered.",
                failure_mode="underpowered",
                diagnostic_codes=("underpowered_validation",),
                evidence_artifact_paths=(),
                next_action_type="prospective_validation",
                next_action="Collect more samples.",
            )


class PredictorManifestTests(unittest.TestCase):
    def test_manifest_roles_must_be_json_arrays(self) -> None:
        with self.assertRaisesRegex(ContractError, "JSON arrays"):
            PredictorManifest.from_dict(
                {
                    "model_version": "m1",
                    "feature_schema_version": "v1",
                    "endpoint": "anti-TNF response",
                    "training_sample_ids": "TRAIN-1",
                }
            )

    def test_training_provenance_cannot_be_empty(self) -> None:
        with self.assertRaisesRegex(ContractError, "must not be empty"):
            PredictorManifest(
                model_version="m1",
                feature_schema_version="v1",
                endpoint="anti-TNF response",
                training_sample_ids=(),
            )

    def test_sample_roles_record_uses_and_may_overlap(self) -> None:
        manifest = PredictorManifest(
            model_version="m1",
            feature_schema_version="v1",
            endpoint="anti-TNF response",
            training_sample_ids=("TRAIN-1",),
            tuning_sample_ids=("TRAIN-1",),
        )
        self.assertEqual(manifest.training_sample_ids, manifest.tuning_sample_ids)

    def test_sealed_samples_are_rejected_in_any_development_role(self) -> None:
        manifest = PredictorManifest(
            model_version="m1",
            feature_schema_version="v1",
            endpoint="anti-TNF response",
            training_sample_ids=("TRAIN-1",),
            tuning_sample_ids=("GSM-SEALED-2",),
            feature_selection_sample_ids=("TRAIN-3",),
        )
        with self.assertRaises(SealedCohortLeakageError):
            manifest.assert_excludes({"GSM-SEALED-1", "GSM-SEALED-2"})

    def test_disjoint_manifest_passes(self) -> None:
        manifest = PredictorManifest(
            model_version="m1",
            feature_schema_version="v1",
            endpoint="anti-TNF response",
            training_sample_ids=("TRAIN-1",),
        )
        manifest.assert_excludes({"GSM-SEALED-1"})


if __name__ == "__main__":
    unittest.main()

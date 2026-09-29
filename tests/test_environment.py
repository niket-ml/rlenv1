from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from uc_bench.environment import DiligenceEnvironment
from uc_bench.errors import ArtifactMutationError, ContractError, SealedCohortLeakageError
from uc_bench.state import EpisodeState, Phase


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


class EnvironmentBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.workspace = root / "workspace"
        self.private = root / "private"
        self.workspace.mkdir()
        self.private.mkdir()
        sample_ids = [f"SEALED_{index}" for index in range(6)]
        genes = ["A", "B", *[f"background_{index}" for index in range(1000)]]
        values = np.arange(len(genes) * len(sample_ids), dtype=float).reshape(
            len(genes), len(sample_ids)
        )
        expression = pd.DataFrame(values, index=genes, columns=sample_ids)
        expression.loc["A"] = [1, 2, 3, 8, 9, 10]
        expression.loc["B"] = [2, 3, 4, 9, 10, 11]
        expression.to_csv(self.private / "expression.csv")
        pd.DataFrame(
            {"sample_id": sample_ids, "response": [0, 0, 0, 1, 1, 1]}
        ).to_csv(self.private / "labels.csv", index=False)

        self.model = {
            "model_type": "linear_logistic_on_within_sample_gene_ranks",
            "model_version": "test-v1",
            "feature_schema_version": "ranks-v1",
            "genes": ["A", "B"],
            "coefficients": [2.0, 2.0],
            "intercept": -2.0,
            "decision_threshold": 0.5,
        }
        self.manifest = {
            "model_version": "test-v1",
            "feature_schema_version": "ranks-v1",
            "endpoint": "development healing",
            "training_sample_ids": ["DEV_1", "DEV_2"],
            "tuning_sample_ids": [],
            "feature_selection_sample_ids": [],
        }
        self.commitment = {
            "target_endpoint": "sealed clinical response",
            "endpoint_interpretation": "cross-endpoint transfer",
            "feature_schema_version": "ranks-v1",
            "missing_feature_policy": "fail closed",
            "decision_threshold": 0.5,
            "expected_auc": 0.6,
            "expected_auc_interval": [0.5, 0.8],
            "permutation_count": 30,
            "artifact_paths": [
                "submission/model.json",
                "submission/analysis.py",
                "submission/evidence.json",
                "submission/manifest.json",
            ],
        }
        write_json(self.workspace / "submission" / "model.json", self.model)
        (self.workspace / "submission" / "analysis.py").write_text(
            "# Reproducibility artifact; never executed by the grader.\n",
            encoding="utf-8",
        )
        write_json(
            self.workspace / "submission" / "evidence.json",
            {"audit_checks": {"cohort_reconstruction": {"status": "pass"}}},
        )
        write_json(self.workspace / "submission" / "manifest.json", self.manifest)
        write_json(self.workspace / "submission" / "commitment.json", self.commitment)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def environment(self) -> DiligenceEnvironment:
        episode = EpisodeState("episode", "uc_biomarker_diligence_v0", "full_data", "test", 0)
        return DiligenceEnvironment(
            workspace_root=self.workspace,
            sealed_expression_path=self.private / "expression.csv",
            sealed_labels_path=self.private / "labels.csv",
            episode=episode,
            bootstrap_resamples=30,
            permutation_count=30,
            analyst_answers={"cohort_endpoint": "different endpoints"},
        )

    def test_complete_episode_reveals_only_aggregate_result(self) -> None:
        environment = self.environment()
        self.assertEqual(environment.ask_analyst("cohort_endpoint"), "different endpoints")
        environment.commit_from_files(
            commitment_path="submission/commitment.json",
            model_path="submission/model.json",
            manifest_path="submission/manifest.json",
        )
        result = environment.reveal_validation()
        self.assertEqual(result.evaluated_n, 6)
        public_result = json.loads(
            (self.workspace / "results" / "validation_result.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            set(public_result),
            {"auc", "auc_interval", "evaluated_n", "permutation_p_value"},
        )
        write_json(
            self.workspace / "submission" / "final_submission.json",
            {
                "decision": "insufficient_evidence",
                "confidence": 0.8,
                "rationale": "The external estimate is imprecise.",
                "failure_mode": "small_transfer_cohort",
                "diagnostic_codes": ["underpowered_validation"],
                "evidence_artifact_paths": ["results/validation_result.json"],
                "next_action_type": "prospective_endpoint_matched_validation",
                "next_action": "Collect an endpoint-matched cohort.",
            },
        )
        environment.submit_from_file("submission/final_submission.json")
        self.assertEqual(environment.episode.phase, Phase.SUBMITTED)
        record_text = json.dumps(environment.record())
        self.assertNotIn("SEALED_0", record_text)

    def test_mutated_model_fails_before_reveal(self) -> None:
        environment = self.environment()
        environment.commit_from_files(
            commitment_path="submission/commitment.json",
            model_path="submission/model.json",
            manifest_path="submission/manifest.json",
        )
        self.model["intercept"] = 10.0
        write_json(self.workspace / "submission" / "model.json", self.model)
        with self.assertRaises(ArtifactMutationError):
            environment.reveal_validation()
        self.assertFalse((self.workspace / "results" / "validation_result.json").exists())

    def test_analyst_cannot_be_queried_after_commit(self) -> None:
        environment = self.environment()
        environment.commit_from_files(
            commitment_path="submission/commitment.json",
            model_path="submission/model.json",
            manifest_path="submission/manifest.json",
        )
        with self.assertRaisesRegex(ContractError, "only before"):
            environment.ask_analyst("cohort_endpoint")

    def test_duplicate_analyst_topic_is_rejected(self) -> None:
        environment = self.environment()
        environment.ask_analyst("cohort_endpoint")
        with self.assertRaisesRegex(ContractError, "already queried"):
            environment.ask_analyst("cohort_endpoint")

    def test_sealed_sample_in_training_manifest_is_rejected(self) -> None:
        environment = self.environment()
        self.manifest["training_sample_ids"].append("SEALED_0")
        write_json(self.workspace / "submission" / "manifest.json", self.manifest)
        with self.assertRaises(SealedCohortLeakageError):
            environment.commit_from_files(
                commitment_path="submission/commitment.json",
                model_path="submission/model.json",
                manifest_path="submission/manifest.json",
            )


if __name__ == "__main__":
    unittest.main()

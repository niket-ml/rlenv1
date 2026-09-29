from __future__ import annotations

import unittest

from uc_bench.contracts import (
    AggregateValidationResult,
    Commitment,
    Decision,
    FinalSubmission,
)
from uc_bench.errors import ArtifactMutationError, InvalidTransitionError
from uc_bench.state import EpisodeState, Phase


def valid_commitment() -> Commitment:
    return Commitment(
        target_endpoint="GSE92415 wk6response",
        endpoint_interpretation="cross-platform and cross-drug transfer",
        feature_schema_version="v1",
        missing_feature_policy="fail below 80 percent coverage",
        decision_threshold=0.63,
        expected_auc=0.72,
        expected_auc_interval=(0.60, 0.84),
        permutation_count=10_000,
        artifact_paths=("pipeline.py", "model.bin"),
    )


def valid_result() -> AggregateValidationResult:
    return AggregateValidationResult(
        auc=0.66,
        auc_interval=(0.52, 0.79),
        permutation_p_value=0.13,
        evaluated_n=59,
    )


class EpisodeStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.episode = EpisodeState(
            episode_id="episode-1",
            task_id="task_07",
            condition="full_data",
            variant_id="clean",
            seed=0,
        )
        self.hashes = {"pipeline.py": "pipeline-hash", "model.bin": "model-hash"}

    def test_happy_path_is_ordered_and_terminal(self) -> None:
        digest = self.episode.commit_analysis(valid_commitment(), self.hashes)
        self.assertEqual(self.episode.phase, Phase.COMMITTED)
        self.assertEqual(len(digest), 64)

        self.episode.reveal_validation(valid_result(), self.hashes)
        self.assertEqual(self.episode.phase, Phase.REVEALED)

        self.episode.submit(
            FinalSubmission(
                decision=Decision.INSUFFICIENT_EVIDENCE,
                confidence=0.82,
                rationale="The transfer estimate is imprecise.",
                failure_mode="underpowered_transfer",
                diagnostic_codes=("underpowered_validation",),
                evidence_artifact_paths=("results/validation.json",),
                next_action_type="prospective_endpoint_matched_validation",
                next_action="Collect a larger endpoint-matched validation cohort.",
            ),
            self.hashes,
        )
        self.assertEqual(self.episode.phase, Phase.SUBMITTED)
        self.assertEqual([event.sequence for event in self.episode.events], [0, 1, 2])
        self.assertEqual(
            [event.action for event in self.episode.events],
            ["commit_analysis", "reveal_validation", "submit"],
        )

    def test_reveal_before_commit_is_rejected(self) -> None:
        with self.assertRaises(InvalidTransitionError):
            self.episode.reveal_validation(valid_result(), self.hashes)

    def test_artifact_path_order_must_match_commitment(self) -> None:
        reordered = {"model.bin": "model-hash", "pipeline.py": "pipeline-hash"}
        with self.assertRaises(InvalidTransitionError):
            self.episode.commit_analysis(valid_commitment(), reordered)

    def test_post_commit_mutation_is_rejected(self) -> None:
        self.episode.commit_analysis(valid_commitment(), self.hashes)
        changed = {**self.hashes, "model.bin": "changed"}
        with self.assertRaises(ArtifactMutationError):
            self.episode.reveal_validation(valid_result(), changed)

    def test_second_reveal_is_rejected(self) -> None:
        self.episode.commit_analysis(valid_commitment(), self.hashes)
        self.episode.reveal_validation(valid_result(), self.hashes)
        with self.assertRaises(InvalidTransitionError):
            self.episode.reveal_validation(valid_result(), self.hashes)


if __name__ == "__main__":
    unittest.main()

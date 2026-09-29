from __future__ import annotations

import unittest

from uc_bench.errors import ContractError
from uc_bench.evaluation import (
    EpisodeScoreRow,
    paired_condition_lift,
    rank_first_probabilities,
    summarize_groups,
)
from uc_bench.grading import COMPONENTS


def row(model: str, condition: str, seed: int, score: float) -> EpisodeScoreRow:
    return EpisodeScoreRow(
        run_id=f"{model}-{condition}-{seed}",
        model_id=model,
        condition=condition,
        scenario_id="authentic",
        scenario_family="authentic_weak_evidence",
        seed=seed,
        score=score,
        component_scores={component: score for component in COMPONENTS},
        contract_valid=True,
        infrastructure_failure=False,
        decision_correct=score >= 50,
    )


class EvaluationAnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = []
        for seed in range(10):
            self.rows.extend(
                [
                    row("strong", "full_data", seed, 80 + seed / 10),
                    row("strong", "data_withheld", seed, 60 + seed / 10),
                    row("weak", "full_data", seed, 50 + seed / 10),
                    row("weak", "data_withheld", seed, 45 + seed / 10),
                ]
            )

    def test_group_summary_and_paired_lift(self) -> None:
        summaries = summarize_groups(
            self.rows,
            bootstrap_resamples=100,
            seed=1,
            floor_threshold=20,
            ceiling_threshold=95,
        )
        self.assertEqual(len(summaries), 4)
        lifts = {row["model_id"]: row for row in paired_condition_lift(self.rows)}
        self.assertAlmostEqual(lifts["strong"]["full_minus_withheld_mean"], 20.0)
        self.assertAlmostEqual(lifts["weak"]["full_minus_withheld_mean"], 5.0)

    def test_rank_bootstrap_identifies_stable_winner(self) -> None:
        probabilities = rank_first_probabilities(
            self.rows,
            condition="full_data",
            scenario_family="authentic_weak_evidence",
            resamples=100,
            seed=2,
        )
        self.assertEqual(probabilities["strong"], 1.0)
        self.assertEqual(probabilities["weak"], 0.0)

    def test_rank_bootstrap_rejects_zero_resamples(self) -> None:
        with self.assertRaisesRegex(ContractError, "positive resamples"):
            rank_first_probabilities(
                self.rows,
                condition="full_data",
                scenario_family="authentic_weak_evidence",
                resamples=0,
                seed=0,
            )


if __name__ == "__main__":
    unittest.main()

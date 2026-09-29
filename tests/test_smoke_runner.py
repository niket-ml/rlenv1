from __future__ import annotations

import unittest

from scripts.run_smoke_pilot import estimate_cost, prepare_resume_rows


class SmokeRunnerTests(unittest.TestCase):
    def test_cost_estimate_uses_catalog_token_prices(self) -> None:
        summary = {"token_usage": {"input_tokens": 1_000_000, "output_tokens": 500_000}}
        model = {
            "input_usd_per_million_tokens": 2.0,
            "output_usd_per_million_tokens": 10.0,
        }
        self.assertEqual(estimate_cost(summary, model), 7.0)

    def test_missing_usage_does_not_invent_cost(self) -> None:
        model = {
            "input_usd_per_million_tokens": 2.0,
            "output_usd_per_million_tokens": 10.0,
        }
        self.assertIsNone(estimate_cost({}, model))

    def test_resume_recovers_only_contiguous_completed_attempts(self) -> None:
        models = [
            {"model_id": "a", "planning_guard_per_run_usd": 1.0},
            {"model_id": "b", "planning_guard_per_run_usd": 2.0},
        ]
        existing = {
            "plan": {"models": ["a", "b"], "attempts_per_model": 3},
            "runs": [
                {"model_id": "a", "estimated_cost_usd": 0.5},
                {"model_id": "a", "estimated_cost_usd": 0.6},
                {
                    "model_id": "b",
                    "estimated_cost_usd": 0.1,
                    "classification": "infrastructure_failure",
                },
                {"model_id": "b", "estimated_cost_usd": None},
            ],
        }
        rows, counts, cumulative = prepare_resume_rows(
            existing, models=models, attempts=3
        )
        self.assertEqual(counts, {"a": 2, "b": 1})
        self.assertEqual([row["attempt_index"] for row in rows], [0, 1, 0, 0])
        self.assertEqual(cumulative, 3.2)


if __name__ == "__main__":
    unittest.main()

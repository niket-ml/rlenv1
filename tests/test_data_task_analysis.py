from __future__ import annotations

import unittest

from scripts.analyze_data_task_calibration import model_summaries, selected_scored_rows


class DataTaskAnalysisTests(unittest.TestCase):
    def test_infrastructure_retry_is_excluded(self) -> None:
        raw = {
            "runs": [
                {
                    "model_id": "m",
                    "task_id": "T03",
                    "scenario_id": "s",
                    "attempt_index": 0,
                    "classification": "infrastructure_failure",
                },
                {
                    "model_id": "m",
                    "task_id": "T03",
                    "scenario_id": "s",
                    "attempt_index": 0,
                    "classification": "valid_episode",
                },
            ]
        }
        rows = selected_scored_rows(raw)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["classification"], "valid_episode")

    def test_task_failure_counts_as_zero_in_model_summary(self) -> None:
        rows = [
            {
                "model_id": "m",
                "classification": "valid_episode",
                "score": 100.0,
                "turn_count": 5,
                "component_scores": {
                    name: 100.0
                    for name in (
                        "decision",
                        "metrics",
                        "diagnosis",
                        "affected_ids",
                        "method_and_action",
                    )
                },
                "failure_signature": "completed_valid_episode",
            },
            {
                "model_id": "m",
                "classification": "agent_task_failure",
                "score": 0.0,
                "turn_count": 12,
                "component_scores": {
                    name: 0.0
                    for name in (
                        "decision",
                        "metrics",
                        "diagnosis",
                        "affected_ids",
                        "method_and_action",
                    )
                },
                "failure_signature": "contract_repair_exhaustion",
            },
        ]
        summary = model_summaries(rows, {"models": [{"model_id": "m", "tier": "x"}]})[0]
        self.assertEqual(summary["mean_attempt_score"], 50.0)
        self.assertEqual(summary["valid_episode_rate"], 0.5)


if __name__ == "__main__":
    unittest.main()

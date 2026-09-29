from __future__ import annotations

import unittest

from scripts.analyze_combined_calibration import combine_model_summaries


class CombinedCalibrationTests(unittest.TestCase):
    def test_combination_is_weighted_by_cell_count(self) -> None:
        packet = {
            "model_summaries": [
                {
                    "model_id": "m",
                    "tier": "x",
                    "n": 2,
                    "score_mean": 80.0,
                    "failure_signatures": {},
                }
            ]
        }
        data = {
            "model_summaries": [
                {
                    "model_id": "m",
                    "attempt_count": 3,
                    "mean_attempt_score": 60.0,
                    "valid_episode_rate": 2 / 3,
                    "failure_signatures": {},
                }
            ]
        }
        row = combine_model_summaries(packet, data)[0]
        self.assertEqual(row["combined_calibration_mean"], 68.0)
        self.assertEqual(row["combined_n"], 5)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from uc_bench.errors import ContractError
from uc_bench.scoring import data_use_lift, expected_auc_calibration_score, weighted_score


class ScoringTests(unittest.TestCase):
    def test_expected_auc_calibration(self) -> None:
        self.assertAlmostEqual(expected_auc_calibration_score(0.72, 0.66), 76.0)
        self.assertEqual(expected_auc_calibration_score(0.90, 0.50), 0.0)

    def test_data_use_lift_and_retention(self) -> None:
        lift, retention = data_use_lift(74.0, 51.0)
        self.assertEqual(lift, 23.0)
        self.assertAlmostEqual(retention, 51.0 / 74.0)

    def test_weighted_score_requires_matching_components(self) -> None:
        with self.assertRaises(ContractError):
            weighted_score({"a": 50.0}, {"a": 0.5, "b": 0.5})


if __name__ == "__main__":
    unittest.main()


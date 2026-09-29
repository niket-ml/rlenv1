from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from uc_bench.variants import (
    PolicyAction,
    inject_confounding_feature,
    inject_label_noise,
    policy_control_score,
)


class VariantTests(unittest.TestCase):
    def setUp(self) -> None:
        self.labels = pd.Series([0] * 10 + [1] * 10, index=[f"S{i}" for i in range(20)])

    def test_label_noise_has_exact_deterministic_strength(self) -> None:
        changed, sample_ids = inject_label_noise(self.labels, 0.25, seed=7)
        repeated, repeated_ids = inject_label_noise(self.labels, 0.25, seed=7)
        self.assertEqual(len(sample_ids), 5)
        self.assertEqual(sample_ids, repeated_ids)
        pd.testing.assert_series_equal(changed, repeated)

    def test_confounding_strength_matches_requested_correlation(self) -> None:
        for strength in (0.0, 0.3, 0.7):
            feature = inject_confounding_feature(self.labels, strength, seed=9)
            achieved = np.corrcoef(feature, self.labels)[0, 1]
            self.assertAlmostEqual(achieved, strength, places=12)

    def test_universal_abstention_loses_symmetric_control(self) -> None:
        expected = [
            PolicyAction("insufficient_evidence", ("weak",), "validate"),
            PolicyAction("advance", ("none",), "replicate"),
            PolicyAction("stop", ("identity",), "resolve_identity"),
        ]
        abstain = PolicyAction("insufficient_evidence", ("generic",), "more_data")
        self.assertLess(policy_control_score(expected, [abstain] * 3), 60.0)
        self.assertEqual(policy_control_score(expected, expected), 100.0)


if __name__ == "__main__":
    unittest.main()

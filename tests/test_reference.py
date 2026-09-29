from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from uc_bench.errors import ContractError
from uc_bench.reference import (
    RankCompositeModel,
    auc_with_stratified_bootstrap,
    expected_transfer_auc,
    predict_reference,
    response_feature,
)


class ReferenceTests(unittest.TestCase):
    def expression(self) -> pd.DataFrame:
        index = ["A", "B", *[f"background_{value}" for value in range(1000)]]
        values = np.arange(len(index) * 2, dtype=float).reshape(len(index), 2)
        return pd.DataFrame(values, index=index, columns=["S1", "S2"])

    def test_rank_feature_and_prediction_are_bounded(self) -> None:
        expression = self.expression()
        feature = response_feature(expression, ("A", "B"))
        self.assertTrue(feature.between(0.0, 1.0).all())
        model = RankCompositeModel("v1", "schema", ("A", "B"), 1.0, 0.0, 0.5)
        prediction = predict_reference(model, expression)
        self.assertTrue(prediction.between(0.0, 1.0).all())

    def test_public_predictor_is_algebraically_equivalent(self) -> None:
        expression = self.expression()
        reference = RankCompositeModel("v1", "schema", ("A", "B"), 2.5, -0.7, 0.5)
        expected = predict_reference(reference, expression)
        actual = reference.as_linear_rank_predictor().predict_proba(expression)
        np.testing.assert_allclose(actual.to_numpy(), expected.to_numpy(), rtol=0, atol=1e-12)

    def test_missing_reference_gene_is_rejected(self) -> None:
        with self.assertRaisesRegex(ContractError, "missing reference genes"):
            response_feature(self.expression(), ("missing",))

    def test_bootstrap_is_deterministic_and_contains_auc(self) -> None:
        labels = pd.Series([0, 0, 1, 1], index=list("abcd"))
        predictions = pd.Series([0.1, 0.3, 0.7, 0.9], index=list("abcd"))
        first = auc_with_stratified_bootstrap(labels, predictions, resamples=100, seed=7)
        second = auc_with_stratified_bootstrap(labels, predictions, resamples=100, seed=7)
        self.assertEqual(first, second)
        self.assertEqual(first[0], 1.0)

    def test_transfer_expectation_applies_prespecified_penalty(self) -> None:
        spec = {
            "transport_expectation": {
                "minimum_expected_auc": 0.5,
                "replication_auc_penalty": 0.2,
                "interval_half_width": 0.15,
            }
        }
        expected, interval = expected_transfer_auc(0.86, spec)
        self.assertAlmostEqual(expected, 0.66)
        self.assertAlmostEqual(interval[0], 0.51)
        self.assertAlmostEqual(interval[1], 0.81)


if __name__ == "__main__":
    unittest.main()

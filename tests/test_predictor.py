from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from uc_bench.errors import ContractError
from uc_bench.predictor import LinearRankPredictor


class PredictorTests(unittest.TestCase):
    def test_rejects_misaligned_coefficients(self) -> None:
        with self.assertRaisesRegex(ContractError, "one-to-one"):
            LinearRankPredictor("v1", "s1", ("A", "B"), (1.0,), 0.0)

    def test_rejects_more_than_fifty_genes(self) -> None:
        genes = tuple(f"G{index}" for index in range(51))
        with self.assertRaisesRegex(ContractError, "between 1 and 50"):
            LinearRankPredictor("v1", "s1", genes, (1.0,) * len(genes), 0.0)

    def test_invalid_dict_fails_with_contract_error(self) -> None:
        with self.assertRaisesRegex(ContractError, "Invalid predictor artifact"):
            LinearRankPredictor.from_dict(
                {
                    "model_type": "linear_logistic_on_within_sample_gene_ranks",
                    "model_version": "v1",
                }
            )

    def test_predictor_vectors_must_be_json_arrays(self) -> None:
        with self.assertRaisesRegex(ContractError, "JSON arrays"):
            LinearRankPredictor.from_dict(
                {
                    "model_type": "linear_logistic_on_within_sample_gene_ranks",
                    "model_version": "v1",
                    "feature_schema_version": "s1",
                    "genes": "A",
                    "coefficients": [1.0],
                    "intercept": 0.0,
                    "decision_threshold": 0.5,
                }
            )

    def test_rejects_numerically_unsafe_coefficients(self) -> None:
        with self.assertRaisesRegex(ContractError, "magnitude"):
            LinearRankPredictor("v1", "s1", ("A",), (1_001.0,), 0.0)

    def test_prediction_preserves_sample_order(self) -> None:
        genes = ["A", *[f"G{index}" for index in range(1000)]]
        expression = pd.DataFrame(
            np.arange(len(genes) * 2).reshape(len(genes), 2),
            index=genes,
            columns=["S2", "S1"],
        )
        model = LinearRankPredictor("v1", "s1", ("A",), (1.0,), 0.0)
        prediction = model.predict_proba(expression)
        self.assertEqual(prediction.index.tolist(), ["S2", "S1"])
        self.assertTrue(prediction.between(0.0, 1.0).all())


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from uc_bench.grading import _set_f1


class GradingTests(unittest.TestCase):
    def test_diagnostic_score_requires_support_and_penalizes_code_stuffing(self) -> None:
        expected = {"endpoint_mismatch", "platform_shift"}
        supported = {"endpoint_mismatch", "platform_shift"}
        exact = _set_f1(expected, expected, supported)
        stuffed = _set_f1(expected, expected | {"label_noise", "confounding"}, supported)
        unsupported = _set_f1(expected, expected, {"endpoint_mismatch"})
        self.assertEqual(exact, 100.0)
        self.assertLess(stuffed, exact)
        self.assertLess(unsupported, exact)


if __name__ == "__main__":
    unittest.main()

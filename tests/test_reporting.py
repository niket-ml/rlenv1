from __future__ import annotations

import unittest

from uc_bench.reporting import render_report


class ReportingTests(unittest.TestCase):
    def test_empty_evaluation_never_invents_leaderboard_rows(self) -> None:
        report = render_report(
            evaluation={
                "model_ranking_available": False,
                "reason": "No model rows <yet>.",
            },
            reference_separation={
                "expert": {"score": 100, "checks": {}},
                "mediocre": {"score": 40},
                "keyword_only_control": {"score": 40},
                "structured_forgery_control": {"score": 40},
                "hard_invalidation_control": {"score": 0},
            },
            variant_controls={
                "policy_control_scores": {"always_advance": 35},
                "sufficient_evidence_positive_control": {
                    "auc": 0.84,
                    "evaluated_n": 240,
                },
            },
            runtime_smoke={
                "fixture_infrastructure_failures": 0,
                "real_model_smoke_executed": False,
            },
        )
        self.assertIn("PRE-RESULT — NO MODEL RANKING", report)
        self.assertIn("No fabricated rows", report)
        self.assertIn("No model rows &lt;yet&gt;.", report)
        self.assertNotIn("No model rows <yet>.", report)


if __name__ == "__main__":
    unittest.main()

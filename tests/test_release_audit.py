from __future__ import annotations

import unittest
from pathlib import Path

from uc_bench.release_audit import run_pre_release_audit

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ReleaseAuditTests(unittest.TestCase):
    def test_current_pre_result_state_fails_closed(self) -> None:
        result = run_pre_release_audit(PROJECT_ROOT)
        self.assertEqual(result["release_decision"], "no_go")
        self.assertFalse(result["model_ranking_claim_allowed"])
        self.assertTrue(result["checks"]["public_sealed_sample_id_scan"])
        self.assertFalse(result["checks"]["real_model_smoke"])
        self.assertFalse(result["checks"]["repeated_model_evaluation"])
        self.assertFalse(result["checks"]["independent_review"])


if __name__ == "__main__":
    unittest.main()

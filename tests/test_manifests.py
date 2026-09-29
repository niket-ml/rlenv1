from __future__ import annotations

import unittest
from pathlib import Path

from uc_bench.manifests import validate_config_root

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ManifestTests(unittest.TestCase):
    def test_public_manifests_satisfy_invariants(self) -> None:
        summary = validate_config_root(PROJECT_ROOT / "configs")
        self.assertEqual(summary["benchmark_id"], "uc_biomarker_diligence_v0")
        self.assertEqual(summary["cohort_count"], 3)
        self.assertEqual(summary["sealed_cohort"], "GSE92415")
        self.assertEqual(summary["milestone_count"], 10)
        self.assertAlmostEqual(summary["milestone_weight_total"], 1.0)
        self.assertAlmostEqual(summary["setup_milestone_share"], 0.30)
        self.assertEqual(summary["pinned_data_source_count"], 6)
        self.assertEqual(summary["headline_score"], "graceful_failure_score")
        self.assertEqual(summary["evidence_state_count"], 4)
        self.assertEqual(summary["task_conditions"], ["full_data", "data_withheld"])


if __name__ == "__main__":
    unittest.main()

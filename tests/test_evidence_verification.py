from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from uc_bench.evidence_verification import verify_development_evidence

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class EvidenceVerificationTests(unittest.TestCase):
    def test_data_withheld_verifies_only_documented_transfer_facts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            (workspace / "reference").mkdir()
            shutil.copyfile(
                PROJECT_ROOT / "configs" / "cohorts.json",
                workspace / "reference" / "cohorts.json",
            )
            result = verify_development_evidence(
                workspace_root=workspace,
                model_value={
                    "model_type": "linear_logistic_on_within_sample_gene_ranks",
                    "model_version": "m1",
                    "feature_schema_version": "ranks-v1",
                    "genes": ["A"],
                    "coefficients": [1.0],
                    "intercept": 0.0,
                    "decision_threshold": 0.5,
                },
                manifest_value={
                    "model_version": "m1",
                    "feature_schema_version": "ranks-v1",
                    "endpoint": "mucosal healing",
                    "training_sample_ids": ["DOCUMENTED-NOT-EXECUTED"],
                    "tuning_sample_ids": [],
                    "feature_selection_sample_ids": [],
                },
                evidence={
                    "audit_checks": {
                        "endpoint_integrity": {
                            "status": "pass",
                            "endpoint_mismatch": True,
                            "drug_transfer": True,
                        }
                    }
                },
            )
        self.assertTrue(result.audit_checks["endpoint_integrity"])
        self.assertFalse(result.audit_checks["cohort_reconstruction"])
        self.assertFalse(result.audit_checks["negative_control"])
        self.assertEqual(
            result.supported_diagnostic_codes,
            {"drug_transfer", "endpoint_mismatch", "platform_shift"},
        )
        self.assertIn("No agent-visible development data", result.details["verification_error"])


if __name__ == "__main__":
    unittest.main()

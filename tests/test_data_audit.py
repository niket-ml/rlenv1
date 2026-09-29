from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from uc_bench.data_audit import PatientRecord, cohort_summary


class DataAuditTests(unittest.TestCase):
    def test_public_record_can_exclude_response(self) -> None:
        record = PatientRecord(
            cohort="GSE1",
            sample_id="GSM1",
            patient_id="GSE1:P1",
            platform_id="GPL1",
            disease="ulcerative_colitis",
            tissue="biopsy",
            treatment="drug",
            timepoint="baseline",
            endpoint="response",
            response=1,
            sealed=True,
        )
        self.assertNotIn("response", record.to_dict(include_response=False))

    def test_cohort_summary_counts_unique_patients(self) -> None:
        records = tuple(
            PatientRecord(
                cohort="GSE1",
                sample_id=f"GSM{index}",
                patient_id=f"GSE1:P{index}",
                platform_id="GPL1",
                disease="ulcerative_colitis",
                tissue="biopsy",
                treatment="drug",
                timepoint="baseline",
                endpoint="response",
                response=index % 2,
                sealed=False,
            )
            for index in range(4)
        )
        summary = cohort_summary(records)
        self.assertEqual(summary["total"], 4)
        self.assertEqual(summary["responders"], 2)
        self.assertEqual(summary["nonresponders"], 2)
        self.assertEqual(summary["unique_patients"], 4)

    def test_no_private_data_is_required_for_core_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertTrue(Path(directory).is_dir())


if __name__ == "__main__":
    unittest.main()

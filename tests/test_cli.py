from __future__ import annotations

import contextlib
import io
import json
import unittest
from pathlib import Path

from uc_bench.cli import main

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def test_doctor(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            return_code = main(["--project-root", str(PROJECT_ROOT), "doctor"])
        self.assertEqual(return_code, 0)
        report = json.loads(output.getvalue())
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["configs"]["sealed_cohort"], "GSE92415")
        self.assertIn("data_files_present", report)
        self.assertIn("data_files_verified", report)

    def test_demo_reaches_submitted_phase(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            return_code = main(["demo"])
        self.assertEqual(return_code, 0)
        record = json.loads(output.getvalue())
        self.assertEqual(record["phase"], "submitted")
        self.assertEqual(record["submission"]["decision"], "insufficient_evidence")
        self.assertEqual(len(record["events"]), 3)


if __name__ == "__main__":
    unittest.main()

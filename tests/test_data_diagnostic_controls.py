from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class DataDiagnosticControlTests(unittest.TestCase):
    def test_control_builder_passes_reference_and_separation_gates(self) -> None:
        subprocess.run(
            [sys.executable, "scripts/build_data_diagnostic_controls.py"],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        value = json.loads(
            (PROJECT_ROOT / "artifacts" / "diagnostics" / "data_task_controls.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertTrue(value["reference_gate_passed"])
        self.assertTrue(value["universal_policy_gate_passed"])
        self.assertTrue(value["expert_separation_gate_passed"])


if __name__ == "__main__":
    unittest.main()

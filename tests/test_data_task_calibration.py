from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.run_data_task_calibration import build_jobs
from uc_bench.data_diagnostics import load_data_diagnostic_scenario

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class DataTaskCalibrationTests(unittest.TestCase):
    def test_frozen_matrix_has_four_models_and_eight_scenarios(self) -> None:
        config = json.loads(
            (PROJECT_ROOT / "configs" / "data_task_calibration.json").read_text(encoding="utf-8")
        )
        self.assertEqual(len(config["models"]), 4)
        self.assertEqual(len(config["sentinel_scenarios"]), 8)
        self.assertEqual(len(build_jobs(config)), 32)
        self.assertFalse(config["acceptance"]["ranking_claim_allowed"])
        for scenario in config["sentinel_scenarios"]:
            loaded = load_data_diagnostic_scenario(
                PROJECT_ROOT, scenario["task_id"], scenario["scenario_id"]
            )
            self.assertEqual(loaded["scenario_id"], scenario["scenario_id"])


if __name__ == "__main__":
    unittest.main()

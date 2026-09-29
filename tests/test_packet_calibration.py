from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.run_packet_calibration import build_jobs, estimate_cost

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class PacketCalibrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = json.loads(
            (PROJECT_ROOT / "configs" / "packet_calibration.json").read_text(
                encoding="utf-8"
            )
        )

    def test_frozen_plan_has_four_models_and_six_scenarios(self) -> None:
        jobs = build_jobs(self.config)
        self.assertEqual(len(jobs), 24)
        self.assertEqual(len({job["model_id"] for job in jobs}), 4)
        self.assertEqual(
            len({(job["task_id"], job["scenario_id"]) for job in jobs}), 6
        )

    def test_cost_uses_pinned_standard_prices(self) -> None:
        summary = {"token_usage": {"input_tokens": 1000, "output_tokens": 100}}
        model = self.config["models"][0]
        self.assertEqual(estimate_cost(summary, model), 0.003)


if __name__ == "__main__":
    unittest.main()

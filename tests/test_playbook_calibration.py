from __future__ import annotations

import json
import unittest
from collections import Counter
from pathlib import Path

from scripts.run_playbook_calibration import build_jobs

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class PlaybookCalibrationTests(unittest.TestCase):
    def test_every_model_scenario_has_a_paired_condition(self) -> None:
        config = json.loads(
            (PROJECT_ROOT / "configs" / "playbook_calibration.json").read_text(encoding="utf-8")
        )
        jobs = build_jobs(config)
        self.assertEqual(len(jobs), 24)
        pairs = Counter(
            (job["model_id"], job["task_type"], job["task_id"], job["scenario_id"]) for job in jobs
        )
        self.assertTrue(all(count == 2 for count in pairs.values()))
        self.assertEqual({job["condition"] for job in jobs}, {"base", "expert_playbook"})
        self.assertFalse(config["analysis_policy"]["ranking_claim_allowed"])


if __name__ == "__main__":
    unittest.main()

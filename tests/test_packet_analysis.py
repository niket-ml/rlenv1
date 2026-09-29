from __future__ import annotations

import unittest

from scripts.analyze_packet_calibration import render_markdown


class PacketAnalysisTests(unittest.TestCase):
    def test_report_labels_calibration_and_refuses_ranking(self) -> None:
        output = {
            "model_summaries": [
                {
                    "model_id": "model",
                    "score_mean": 50.0,
                    "contract_valid_rate": 0.5,
                    "decision_accuracy": 0.5,
                    "floor_rate": 0.25,
                    "ceiling_rate": 0.0,
                }
            ],
            "strict_temporal_order": False,
            "floor_ceiling_gate_passed": True,
            "calibration_accepted": False,
        }
        rendered = render_markdown(output)
        self.assertIn("CALIBRATION ONLY", rendered)
        self.assertIn("no ranking claim", rendered)
        self.assertIn("Calibration accepted: `false`", rendered)


if __name__ == "__main__":
    unittest.main()

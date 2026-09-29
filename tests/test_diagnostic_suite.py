from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from uc_bench.diagnostic_suite import validate_diagnostic_suite
from uc_bench.errors import ContractError

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class DiagnosticSuiteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.value = json.loads(
            (PROJECT_ROOT / "configs" / "diagnostic_suite.json").read_text(
                encoding="utf-8"
            )
        )

    def test_catalog_has_balanced_decisions_and_reaches_calibration_gate(self) -> None:
        result = validate_diagnostic_suite(self.value)
        self.assertEqual(result.task_count, 10)
        self.assertEqual(
            set(result.decision_classes),
            {"advance", "stop", "insufficient_evidence"},
        )
        self.assertTrue(result.calibration_ready)

    def test_latent_corruption_cannot_require_exact_detection(self) -> None:
        value = copy.deepcopy(self.value)
        task = next(task for task in value["tasks"] if task["id"] == "T06")
        task["agent_must_identify_exact_planted_items"] = True
        with self.assertRaisesRegex(ContractError, "Latent variants"):
            validate_diagnostic_suite(value)

    def test_paired_intervention_may_change_only_one_factor(self) -> None:
        value = copy.deepcopy(self.value)
        value["paired_interventions"][0]["changes"].append("prompt_length")
        with self.assertRaisesRegex(ContractError, "exactly one factor"):
            validate_diagnostic_suite(value)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from uc_bench.errors import ConfigurationError
from uc_bench.packet_runner import DiagnosticPacketRunConfig


class DiagnosticPacketRunnerTests(unittest.TestCase):
    def test_default_budget_is_shorter_than_end_to_end_episode(self) -> None:
        config = DiagnosticPacketRunConfig(
            model_id="provider/model",
            run_id="run",
            task_id="T08",
            scenario_id="scenario",
            seed=1,
        )
        self.assertEqual(config.maximum_turns, 8)
        self.assertEqual(config.maximum_total_completion_tokens, 8000)

    def test_packet_run_budgets_fail_closed(self) -> None:
        with self.assertRaises(ConfigurationError):
            DiagnosticPacketRunConfig(
                model_id="provider/model",
                run_id="run",
                task_id="T08",
                scenario_id="scenario",
                seed=1,
                maximum_turns=0,
            )

    def test_unknown_playbook_condition_fails_closed(self) -> None:
        with self.assertRaises(ConfigurationError):
            DiagnosticPacketRunConfig(
                model_id="provider/model",
                run_id="run",
                task_id="T08",
                scenario_id="scenario",
                seed=1,
                condition="answer_leak",
            )


if __name__ == "__main__":
    unittest.main()

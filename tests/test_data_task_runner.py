from __future__ import annotations

import unittest

from uc_bench.data_task_runner import DataTaskRunConfig
from uc_bench.errors import ConfigurationError


class DataTaskRunnerTests(unittest.TestCase):
    def test_default_budget_allows_executable_analysis(self) -> None:
        config = DataTaskRunConfig(
            model_id="provider/model",
            run_id="run",
            task_id="T06",
            scenario_id="scenario",
            seed=1,
        )
        self.assertEqual(config.maximum_turns, 12)
        self.assertEqual(config.maximum_total_completion_tokens, 12_000)

    def test_data_task_run_budgets_fail_closed(self) -> None:
        with self.assertRaises(ConfigurationError):
            DataTaskRunConfig(
                model_id="provider/model",
                run_id="run",
                task_id="T06",
                scenario_id="scenario",
                seed=1,
                maximum_turns=0,
            )

    def test_unknown_playbook_condition_fails_closed(self) -> None:
        with self.assertRaises(ConfigurationError):
            DataTaskRunConfig(
                model_id="provider/model",
                run_id="run",
                task_id="T06",
                scenario_id="scenario",
                seed=1,
                condition="answer_leak",
            )


if __name__ == "__main__":
    unittest.main()

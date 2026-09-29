from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from uc_bench.data_diagnostics import (
    DataDiagnosticBuilder,
    DataDiagnosticEnvironment,
    grade_data_diagnostic,
    iter_data_diagnostic_scenarios,
    reference_submission,
    solve_data_diagnostic,
    validate_data_diagnostic_config,
)
from uc_bench.errors import ContractError

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class DataDiagnosticTests(unittest.TestCase):
    def test_config_has_one_factor_ladders_and_complete_coverage(self) -> None:
        value = json.loads(
            (PROJECT_ROOT / "configs" / "data_diagnostics.json").read_text(encoding="utf-8")
        )
        result = validate_data_diagnostic_config(value)
        self.assertEqual(result["task_ids"], ["T03", "T04", "T05", "T06"])
        self.assertEqual(result["ladder_count"], 5)
        self.assertEqual(result["scenario_count"], 20)
        self.assertTrue(result["one_factor_per_ladder"])

    def test_reference_solver_scores_100_on_every_scenario(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_root = Path(directory)
            for task_id, scenario_id in iter_data_diagnostic_scenarios(PROJECT_ROOT):
                package = DataDiagnosticBuilder(PROJECT_ROOT).build(
                    task_id, scenario_id, output_root=output_root
                )
                submission = reference_submission(package.workspace_root)
                grade = grade_data_diagnostic(package.workspace_root, submission)
                self.assertEqual(grade.score, 100.0, (task_id, scenario_id))
                self.assertTrue(grade.decision_correct)

    def test_workspace_does_not_ship_private_truth(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            package = DataDiagnosticBuilder(PROJECT_ROOT).build(
                "T03", "duplicates_1", output_root=Path(directory)
            )
            paths = {
                path.relative_to(package.workspace_root).as_posix()
                for path in package.workspace_root.rglob("*")
                if path.is_file()
            }
            self.assertNotIn("answer.json", paths)
            self.assertNotIn("rubric.json", paths)
            start = json.loads(
                (package.workspace_root / "START_STATE.json").read_text(encoding="utf-8")
            )
            self.assertFalse(start["private_answer_visible"])

    def test_expert_playbook_is_an_explicit_package_condition(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            base = DataDiagnosticBuilder(PROJECT_ROOT).build(
                "T05", "phi_30", output_root=output / "base"
            )
            scaffolded = DataDiagnosticBuilder(PROJECT_ROOT).build(
                "T05",
                "phi_30",
                output_root=output / "playbook",
                expert_playbook=True,
            )
            self.assertFalse((base.workspace_root / "EXPERT_PLAYBOOK.md").exists())
            self.assertTrue((scaffolded.workspace_root / "EXPERT_PLAYBOOK.md").is_file())
            self.assertNotEqual(base.package_digest, scaffolded.package_digest)

    def test_directly_observable_identity_conflicts_are_localized(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            package = DataDiagnosticBuilder(PROJECT_ROOT).build(
                "T03", "duplicates_3", output_root=Path(directory)
            )
            expected = solve_data_diagnostic(package.workspace_root)
            self.assertEqual(expected["decision"], "stop")
            self.assertEqual(expected["metrics"]["conflicting_duplicate_group_count"], 3)
            self.assertEqual(len(expected["affected_ids"]), 6)

    def test_latent_noise_task_never_requests_affected_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            package = DataDiagnosticBuilder(PROJECT_ROOT).build(
                "T06", "noise_n120_30", output_root=Path(directory)
            )
            expected = solve_data_diagnostic(package.workspace_root)
            self.assertEqual(expected["affected_ids"], [])

    def test_submit_rejects_missing_metric_and_none_with_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            package = DataDiagnosticBuilder(PROJECT_ROOT).build(
                "T05", "phi_30", output_root=Path(directory)
            )
            submission = reference_submission(package.workspace_root)
            submission["metrics"].pop("phi_coefficient")
            path = package.workspace_root / "submission" / "final_submission.json"
            path.write_text(json.dumps(submission), encoding="utf-8")
            environment = DataDiagnosticEnvironment(package.workspace_root)
            with self.assertRaises(ContractError):
                environment.submit_data_audit("submission/final_submission.json")

            submission = reference_submission(package.workspace_root)
            submission["diagnostic_codes"] = ["none", "batch_confounding"]
            path.write_text(json.dumps(submission), encoding="utf-8")
            with self.assertRaises(ContractError):
                environment.submit_data_audit("submission/final_submission.json")


if __name__ == "__main__":
    unittest.main()

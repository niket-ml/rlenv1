from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from uc_bench.diagnostic_packets import (
    DiagnosticPacketBuilder,
    DiagnosticPacketEnvironment,
    grade_diagnostic_packet,
    load_packet_scenario,
    policy_decision,
    validate_diagnostic_packets,
)
from uc_bench.errors import ContractError

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class DiagnosticPacketTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = json.loads(
            (PROJECT_ROOT / "configs" / "diagnostic_packets.json").read_text(
                encoding="utf-8"
            )
        )

    def test_private_rubrics_follow_public_policy_and_cover_all_decisions(self) -> None:
        result = validate_diagnostic_packets(self.config)
        self.assertEqual(result["scenario_count"], 12)
        self.assertEqual(
            set(result["decision_classes"]),
            {"advance", "stop", "insufficient_evidence"},
        )

    def test_policy_boundaries_are_strict_and_sample_size_is_explicit(self) -> None:
        policy = self.config["decision_policy"]
        borderline = load_packet_scenario(
            PROJECT_ROOT, "T08", "borderline_interval"
        )["packet"]
        underpowered = load_packet_scenario(
            PROJECT_ROOT, "T08", "promising_underpowered"
        )["packet"]
        sufficient = load_packet_scenario(
            PROJECT_ROOT, "T08", "sufficient_evidence"
        )["packet"]
        self.assertEqual(policy_decision(borderline, policy), "insufficient_evidence")
        self.assertEqual(policy_decision(underpowered, policy), "insufficient_evidence")
        self.assertEqual(policy_decision(sufficient, policy), "advance")

    def test_policy_rubric_disagreement_fails_closed(self) -> None:
        value = copy.deepcopy(self.config)
        value["scenarios"][0]["rubric"]["expected_decision"] = "advance"
        with self.assertRaisesRegex(ContractError, "disagrees"):
            validate_diagnostic_packets(value)

    def test_builder_exposes_one_packet_but_not_private_rubric(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            package = DiagnosticPacketBuilder(PROJECT_ROOT).build(
                "T10", "hard_identity_conflict", output_root=Path(temporary_directory)
            )
            rendered = "\n".join(
                path.read_text(encoding="utf-8")
                for path in package.workspace_root.rglob("*")
                if path.is_file()
            )
            self.assertIn("hard_integrity_failure", rendered)
            self.assertNotIn("expected_next_action_type", rendered)
            self.assertNotIn("confidence_range", rendered)

    def test_exact_submission_scores_one_hundred_and_wrong_decision_is_capped(self) -> None:
        scenario = load_packet_scenario(
            PROJECT_ROOT, "T10", "hard_identity_conflict"
        )
        rubric = scenario["rubric"]
        exact = {
            "decision": rubric["expected_decision"],
            "confidence": 0.9,
            "diagnostic_codes": rubric["expected_diagnostic_codes"],
            "evidence_ids": rubric["required_evidence_ids"],
            "next_action_type": rubric["expected_next_action_type"],
            "rationale": "The identity conflict invalidates interpretation.",
        }
        self.assertEqual(grade_diagnostic_packet(exact, rubric).score, 100.0)
        wrong = dict(exact, decision="advance")
        self.assertLessEqual(grade_diagnostic_packet(wrong, rubric).score, 59.0)

    def test_environment_rejects_invented_evidence_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            package = DiagnosticPacketBuilder(PROJECT_ROOT).build(
                "T08", "sufficient_evidence", output_root=Path(temporary_directory)
            )
            submission = {
                "decision": "advance",
                "confidence": 0.8,
                "diagnostic_codes": ["none"],
                "evidence_ids": ["FAKE-999"],
                "next_action_type": "independent_replication",
                "rationale": "All advancement criteria pass.",
            }
            path = package.workspace_root / "submission" / "final_submission.json"
            path.write_text(json.dumps(submission), encoding="utf-8")
            with self.assertRaisesRegex(ContractError, "unknown evidence"):
                DiagnosticPacketEnvironment(package.workspace_root).submit_packet(
                    "submission/final_submission.json"
                )


if __name__ == "__main__":
    unittest.main()

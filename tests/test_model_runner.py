from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from uc_bench.errors import ConfigurationError
from uc_bench.model_runner import (
    ModelRunConfig,
    _redact_public_identifiers,
    _resolve_generated,
    attempt_score,
    completion_stats,
    load_openrouter_key,
)


class ModelRunnerTests(unittest.TestCase):
    def test_verifiers_async_result_is_resolved(self) -> None:
        async def generated() -> dict[str, bool]:
            return {"resolved": True}

        self.assertEqual(_resolve_generated(generated()), {"resolved": True})

    def test_provider_user_identifier_is_redacted(self) -> None:
        value = {"message": "request failed for user_ABC123"}
        self.assertEqual(
            _redact_public_identifiers(value),
            {"message": "request failed for <provider_account_redacted>"},
        )

    def test_completion_stats_parses_serialized_tool_calls(self) -> None:
        output = {
            "completion": [
                {
                    "role": "assistant",
                    "content": "working",
                    "tool_calls": [
                        '{"id":"1","name":"read_file","arguments":"{}"}',
                        {
                            "id": "2",
                            "function": {"name": "run_command", "arguments": "{}"},
                        },
                    ],
                },
                {"role": "tool", "content": "ok"},
                {"role": "assistant", "content": "done", "tool_calls": []},
            ]
        }
        self.assertEqual(
            completion_stats(output),
            {
                "turn_count": 2,
                "tool_call_count": 2,
                "tool_call_counts": {"read_file": 1, "run_command": 1},
            },
        )

    def test_key_is_loaded_without_exporting_other_values(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / ".env").write_text(
                "OPENROUTER_API_KEY=sk-or-v1-testvalue\nUNRELATED=do-not-load\n",
                encoding="utf-8",
            )
            self.assertEqual(load_openrouter_key(root), "sk-or-v1-testvalue")

    def test_placeholder_key_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / ".env").write_text(
                "OPENROUTER_API_KEY=PASTE_YOUR_NEW_OPENROUTER_KEY_HERE\n",
                encoding="utf-8",
            )
            with self.assertRaises(ConfigurationError):
                load_openrouter_key(root)

    def test_run_budgets_must_be_positive(self) -> None:
        with self.assertRaises(ConfigurationError):
            ModelRunConfig(
                model_id="provider/model",
                run_id="run-1",
                maximum_turns=0,
            )

    def test_attempt_score_separates_task_and_infrastructure_failures(self) -> None:
        self.assertEqual(attempt_score("agent_task_failure", None), 0.0)
        self.assertIsNone(attempt_score("infrastructure_failure", None))
        self.assertEqual(attempt_score("valid_episode", {"score": 87.5}), 87.5)
        with self.assertRaises(ConfigurationError):
            attempt_score("submitted_contract_failure", None)


if __name__ == "__main__":
    unittest.main()

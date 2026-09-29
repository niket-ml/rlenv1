"""Thin agent-runtime adapter around the framework-neutral environment core."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from uc_bench.environment import DiligenceEnvironment


@dataclass(slots=True)
class DomainToolAdapter:
    """Expose only state-changing benchmark operations to an agent harness.

    The coding harness owns isolated filesystem and shell access. These tools
    remain outside that sandbox so private evaluation state is not mountable by
    the agent.
    """

    environment: DiligenceEnvironment

    def ask_analyst(self, topic: str) -> str:
        """Return the fixed evidence response for one enumerated analyst topic."""

        return self.environment.ask_analyst(topic)

    def commit_analysis(
        self,
        commitment_path: str,
        model_path: str,
        manifest_path: str,
    ) -> str:
        """Irreversibly commit the analysis artifacts and return their digest."""

        return self.environment.commit_from_files(
            commitment_path=commitment_path,
            model_path=model_path,
            manifest_path=manifest_path,
        )

    def reveal_validation(self) -> str:
        """Run the one-time private validation and return aggregate evidence only."""

        result = self.environment.reveal_validation()
        return json.dumps(result.to_dict(), sort_keys=True)

    def submit(self, submission_path: str) -> str:
        """Submit the terminal evidence decision once."""

        self.environment.submit_from_file(submission_path)
        return json.dumps({"phase": self.environment.episode.phase.value})

    def functions(self) -> list[Callable[..., Any]]:
        return [
            self.ask_analyst,
            self.commit_analysis,
            self.reveal_validation,
            self.submit,
        ]

    def verifiers_tool_environment(self, *, system_prompt: str, max_turns: int = 40) -> Any:
        """Construct the installed Verifiers tool surface for schema/runtime checks.

        Production evaluation must combine this surface with an isolated coding
        harness. It intentionally does not add unsafe host shell execution.
        """

        import verifiers as vf
        from datasets import Dataset

        return vf.ToolEnv(
            dataset=Dataset.from_list(
                [
                    {
                        "prompt": [
                            {
                                "role": "user",
                                "content": "Complete the diligence task in the mounted workspace.",
                            }
                        ],
                        "answer": "",
                    }
                ]
            ),
            tools=self.functions(),
            system_prompt=system_prompt,
            max_turns=max_turns,
        )

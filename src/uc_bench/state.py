"""In-memory episode state machine for the commit-before-reveal workflow."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from uc_bench.contracts import AggregateValidationResult, Commitment, FinalSubmission
from uc_bench.errors import ArtifactMutationError, InvalidTransitionError
from uc_bench.hashing import canonical_sha256, verify_artifact_hashes


class Phase(StrEnum):
    WORKING = "working"
    COMMITTED = "committed"
    REVEALED = "revealed"
    SUBMITTED = "submitted"


@dataclass(frozen=True, slots=True)
class EpisodeEvent:
    sequence: int
    action: str
    phase_before: Phase
    phase_after: Phase
    payload_digest: str

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["phase_before"] = self.phase_before.value
        value["phase_after"] = self.phase_after.value
        return value


@dataclass(slots=True)
class EpisodeState:
    episode_id: str
    task_id: str
    condition: str
    variant_id: str
    seed: int
    phase: Phase = Phase.WORKING
    commitment: Commitment | None = None
    commitment_digest: str | None = None
    committed_artifact_hashes: dict[str, str] = field(default_factory=dict)
    validation_result: AggregateValidationResult | None = None
    submission: FinalSubmission | None = None
    events: list[EpisodeEvent] = field(default_factory=list)

    def _require_phase(self, expected: Phase, action: str) -> None:
        if self.phase is not expected:
            raise InvalidTransitionError(
                f"{action} requires phase={expected.value}; current phase={self.phase.value}"
            )

    def _append_event(
        self, action: str, before: Phase, after: Phase, payload: Any
    ) -> None:
        self.events.append(
            EpisodeEvent(
                sequence=len(self.events),
                action=action,
                phase_before=before,
                phase_after=after,
                payload_digest=canonical_sha256(payload),
            )
        )

    def _verify_immutable(self, current_artifact_hashes: dict[str, str]) -> None:
        try:
            verify_artifact_hashes(self.committed_artifact_hashes, current_artifact_hashes)
        except ValueError as exc:
            raise ArtifactMutationError(str(exc)) from exc

    def assert_artifacts_unchanged(self, current_artifact_hashes: dict[str, str]) -> None:
        """Fail before any private evaluation if committed inputs were changed."""

        if self.commitment is None:
            raise InvalidTransitionError("No committed artifacts exist")
        self._verify_immutable(current_artifact_hashes)

    def commit_analysis(
        self, commitment: Commitment, artifact_hashes: dict[str, str]
    ) -> str:
        self._require_phase(Phase.WORKING, "commit_analysis")
        if tuple(artifact_hashes) != commitment.artifact_paths:
            raise InvalidTransitionError(
                "Artifact hashes must use the same paths and ordering as the commitment"
            )

        before = self.phase
        self.commitment = commitment
        self.committed_artifact_hashes = dict(artifact_hashes)
        self.commitment_digest = canonical_sha256(
            {
                "commitment": commitment,
                "artifact_hashes": artifact_hashes,
            }
        )
        self.phase = Phase.COMMITTED
        self._append_event(
            "commit_analysis",
            before,
            self.phase,
            {"commitment_digest": self.commitment_digest},
        )
        return self.commitment_digest

    def reveal_validation(
        self,
        result: AggregateValidationResult,
        current_artifact_hashes: dict[str, str],
    ) -> None:
        self._require_phase(Phase.COMMITTED, "reveal_validation")
        self._verify_immutable(current_artifact_hashes)
        before = self.phase
        self.validation_result = result
        self.phase = Phase.REVEALED
        self._append_event("reveal_validation", before, self.phase, result)

    def submit(
        self,
        submission: FinalSubmission,
        current_artifact_hashes: dict[str, str],
    ) -> None:
        self._require_phase(Phase.REVEALED, "submit")
        self._verify_immutable(current_artifact_hashes)
        before = self.phase
        self.submission = submission
        self.phase = Phase.SUBMITTED
        self._append_event("submit", before, self.phase, submission)

    def to_record(self) -> dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "task_id": self.task_id,
            "condition": self.condition,
            "variant_id": self.variant_id,
            "seed": self.seed,
            "phase": self.phase.value,
            "commitment": self.commitment.to_dict() if self.commitment else None,
            "commitment_digest": self.commitment_digest,
            "committed_artifact_hashes": dict(self.committed_artifact_hashes),
            "validation_result": (
                self.validation_result.to_dict() if self.validation_result else None
            ),
            "submission": self.submission.to_dict() if self.submission else None,
            "events": [event.to_dict() for event in self.events],
        }

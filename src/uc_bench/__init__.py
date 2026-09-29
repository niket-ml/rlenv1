"""Framework-neutral core contracts for UC-Bench."""

from uc_bench.contracts import (
    AggregateValidationResult,
    Commitment,
    Decision,
    FinalSubmission,
    PredictionRecord,
    PredictorManifest,
)
from uc_bench.state import EpisodeState, Phase

__all__ = [
    "AggregateValidationResult",
    "Commitment",
    "Decision",
    "EpisodeState",
    "FinalSubmission",
    "Phase",
    "PredictionRecord",
    "PredictorManifest",
]

__version__ = "0.1.0"


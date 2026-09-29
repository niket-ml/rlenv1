"""Domain errors raised by the environment core."""


class UCBenchError(Exception):
    """Base exception for expected UC-Bench failures."""


class ContractError(UCBenchError, ValueError):
    """A submitted object does not satisfy its public contract."""


class InvalidTransitionError(UCBenchError, RuntimeError):
    """A tool was called from an invalid episode phase."""


class ArtifactMutationError(UCBenchError, RuntimeError):
    """A committed artifact changed after the commitment boundary."""


class SealedCohortLeakageError(UCBenchError, ValueError):
    """A predictor manifest contains a sealed evaluation sample."""


class ConfigurationError(UCBenchError, ValueError):
    """A public project manifest violates an invariant."""


class DockerRuntimeError(UCBenchError, RuntimeError):
    """The isolated Docker coding runtime could not be started or contacted."""

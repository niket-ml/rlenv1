"""Host executable discovery for the clean Case 1 pilot."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from uc_bench.errors import ConfigurationError

DOCKER_DESKTOP_CLI = Path("/Applications/Docker.app/Contents/Resources/bin/docker")


def docker_cli_path() -> Path:
    discovered = shutil.which("docker")
    if discovered:
        return Path(discovered).resolve()
    if DOCKER_DESKTOP_CLI.is_file():
        return DOCKER_DESKTOP_CLI.resolve()
    raise ConfigurationError("Docker CLI is unavailable on PATH and in Docker Desktop")


def ensure_docker_cli_on_path() -> Path:
    executable = docker_cli_path()
    parent = executable.parent.as_posix()
    entries = os.environ.get("PATH", "").split(os.pathsep)
    if parent not in entries:
        os.environ["PATH"] = os.pathsep.join([parent, *entries])
    if shutil.which("docker") is None:
        raise ConfigurationError("Docker CLI discovery did not establish an executable PATH")
    return executable


__all__ = ["DOCKER_DESKTOP_CLI", "docker_cli_path", "ensure_docker_cli_on_path"]

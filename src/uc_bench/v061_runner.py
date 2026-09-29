"""Run v0.6.1 with unchanged v0.6 science and corrected request plumbing."""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path
from threading import RLock
from typing import Any

import uc_bench.hard_suite_v06_runner as v06_runner
from uc_bench.errors import ConfigurationError
from uc_bench.model_runner import _temporary_environment, _write_json
from uc_bench.v061_freeze import read_v061_freeze_manifest
from uc_bench.v061_provider import (
    V061AuditedOpenRouterClient,
    V061RequestLedger,
    load_v061_provider_adapters,
)

V061RunConfig = v06_runner.V06RunConfig
V061RunArtifacts = v06_runner.V06RunArtifacts
_RUN_LOCK = RLock()


def run_v061_episode(
    project_root: Path,
    config: V061RunConfig,
    *,
    openrouter_key: str,
    authorization_digest: str | None = None,
) -> V061RunArtifacts:
    """Use the v0.6 task/grader under the separately frozen v0.6.1 adapter."""

    root = project_root.resolve()
    manifest = read_v061_freeze_manifest(root)
    if authorization_digest != manifest["hash_set_digest"]:
        raise ConfigurationError("v0.6.1 direct execution lacks freeze authorization")
    if os.environ.get("UC_BENCH_V061_PARTITION", "development") != "development":
        raise ConfigurationError("v0.6.1 execution rejects non-development partitions")
    adapters = load_v061_provider_adapters(root)
    versioned = replace(
        config,
        run_id=(
            config.run_id.replace("hard6-", "hard61-", 1)
            if config.run_id.startswith("hard6-")
            else f"hard61-{config.run_id}"
        ),
    )
    with _RUN_LOCK, _temporary_environment("OPENROUTER_API_KEY", openrouter_key):
        original: dict[str, Any] = {
            "read_v06_freeze_manifest": v06_runner.read_v06_freeze_manifest,
            "load_provider_adapters": v06_runner.load_provider_adapters,
            "AuditedOpenRouterClient": v06_runner.AuditedOpenRouterClient,
            "RequestLedger": v06_runner.RequestLedger,
        }
        try:
            v06_runner.read_v06_freeze_manifest = read_v061_freeze_manifest
            v06_runner.load_provider_adapters = lambda _root: adapters
            v06_runner.AuditedOpenRouterClient = V061AuditedOpenRouterClient
            v06_runner.RequestLedger = V061RequestLedger
            artifacts = v06_runner.run_v06_episode(
                root,
                versioned,
                openrouter_key=openrouter_key,
            )
        finally:
            for name, value in original.items():
                setattr(v06_runner, name, value)
    artifacts.summary["runner_revision"] = "0.6.1"
    artifacts.summary["scientific_contract_revision"] = "0.6-byte-identical"
    _write_json(artifacts.summary_path, artifacts.summary, secret=openrouter_key)
    return artifacts

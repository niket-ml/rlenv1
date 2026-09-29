"""Resilient v0.6.3 runner with total grading and emergency checkpoint data."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any

import uc_bench.hard_suite_v06_runner as v06_runner
from uc_bench.errors import ConfigurationError
from uc_bench.hard_suite_v06 import (
    V06Package,
    load_v06_scenario,
)
from uc_bench.hashing import hash_artifacts
from uc_bench.model_runner import _slug, _temporary_environment, _write_json
from uc_bench.v061_provider import V061RequestLedger
from uc_bench.v062_provider import (
    V062AuditedOpenRouterClient,
    load_v062_provider_adapters,
)
from uc_bench.v063_freeze import read_v063_freeze_manifest
from uc_bench.v063_grader import (
    emergency_v063_grade,
    grade_v063,
    grader_infrastructure_failed,
)

V063RunConfig = v06_runner.V06RunConfig
V063RunArtifacts = v06_runner.V06RunArtifacts
_RUN_LOCK = RLock()


def _read_ledger(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = value.get("requests") if isinstance(value, dict) else None
    return list(rows) if isinstance(rows, list) else []


def _read_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _recover_diagnostic_grade(
    root: Path,
    workspace: Path,
    config: V063RunConfig,
    error: BaseException,
) -> dict[str, Any]:
    """Recover partial science from disk without converting it into a score."""

    start = _read_object(workspace / "START_STATE.json")
    sealed = workspace.parent / f"hard6-{config.scenario_id}-sealed"
    if not workspace.is_dir() or not sealed.is_dir() or not start:
        return emergency_v063_grade(root, selected="none", error=error).to_dict()
    memo = _read_object(workspace / "submission/resource_value_memo.json")
    selected = str(memo.get("selected_resource_id") or "none")
    event_log = _read_object(workspace / "EVENT_LOG.json")
    submitted = any(
        isinstance(row, dict) and row.get("action") == "submit_diligence"
        for row in event_log.get("events") or []
    )
    record = _read_object(workspace / "COMMITMENT_RECORD.json")
    expected = record.get("artifact_snapshot")
    commitment_immutable = False
    if isinstance(expected, dict) and expected:
        try:
            commitment_immutable = hash_artifacts(workspace, expected) == expected
        except Exception:
            commitment_immutable = False
    package = V06Package(
        scenario_id=config.scenario_id,
        partition="development",
        workspace_root=workspace,
        sealed_root=sealed,
        package_digest=str(start.get("package_digest") or "recovered"),
        sealed_digest="recovered-not-used-for-scoring",
        private_scenario=load_v06_scenario(
            root,
            config.scenario_id,
            partition="development",
        ),
        schema_root=root / "tasks/hard_suite_v06/schemas",
    )
    diagnostic = grade_v063(
        root,
        package,
        selected_resource=selected,
        commitment_immutable=commitment_immutable,
        completion_accepted=False,
    )
    value = diagnostic.to_dict()
    value["completion_observed_before_infrastructure_failure"] = submitted
    return value


def _aggregate_usage(requests: list[dict[str, Any]]) -> dict[str, int]:
    prompt = 0
    completion = 0
    for row in requests:
        usage = row.get("usage") if isinstance(row, dict) else None
        if not isinstance(usage, dict):
            continue
        prompt += int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
        completion += int(
            usage.get("completion_tokens") or usage.get("output_tokens") or 0
        )
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
    }


def _emergency_artifacts(
    root: Path,
    config: V063RunConfig,
    *,
    error: BaseException,
    key: str,
) -> V063RunArtifacts:
    """Persist paid evidence even when the ordinary post-rollout path raises."""

    run_root = root / "build" / "hard_suite_v06_runs" / _slug(config.run_id)
    run_root.mkdir(parents=True, exist_ok=True)
    workspace = run_root / f"hard6-{config.scenario_id}"
    ledger_path = run_root / "request_ledger.json"
    requests = _read_ledger(ledger_path)
    reported_cost = sum(float(row.get("reported_cost_usd") or 0.0) for row in requests)
    diagnostic = _recover_diagnostic_grade(root, workspace, config, error)
    classification = (
        "post_rollout_infrastructure_failure"
        if requests
        else "unknown_harness_failure"
    )
    events = _read_object(workspace / "EVENT_LOG.json").get("events") or []
    summary = {
        "schema_version": "0.6.3-emergency-run-1",
        "executed_at": datetime.now(UTC).isoformat(),
        "run_config": {
            name: value for name, value in asdict(config).items()
        },
        "model_id": config.model_id,
        "run_id": config.run_id,
        "run_directory": run_root.relative_to(root).as_posix(),
        "workspace_directory": (
            workspace.relative_to(root).as_posix()
            if workspace.exists()
            else run_root.relative_to(root).as_posix()
        ),
        "scenario_id": config.scenario_id,
        "partition": config.partition,
        "classification": classification,
        "attempt_score": None,
        "scientific_score": None,
        "diagnostic_grade": diagnostic,
        "rollout_error": {
            "type": type(error).__name__,
            "message": str(error)[:2000],
        },
        "stop_condition": "post_rollout_exception",
        "turn_count": len(requests),
        "token_usage": _aggregate_usage(requests),
        "provider_requests": requests,
        "provider_request_count": len(requests),
        "returned_models": sorted(
            {str(row["returned_model"]) for row in requests if row.get("returned_model")}
        ),
        "actual_providers": sorted(
            {str(row["actual_provider"]) for row in requests if row.get("actual_provider")}
        ),
        "cumulative_reported_cost_usd": round(reported_cost, 8),
        "completion_accepted": False,
        "phase_reached": (
            events[-1].get("phase")
            if events and isinstance(events[-1], dict)
            else "unknown"
        ),
        "runner_revision": "0.6.3",
        "scientific_contract_revision": "0.6-task-and-threshold-identical",
        "emergency_checkpoint": True,
    }
    summary_path = run_root / "run_summary.json"
    _write_json(summary_path, summary, secret=key)
    return V063RunArtifacts(
        run_root=run_root,
        workspace_root=workspace,
        summary_path=summary_path,
        request_ledger_path=ledger_path,
        summary=summary,
    )


def run_v063_episode(
    project_root: Path,
    config: V063RunConfig,
    *,
    openrouter_key: str,
    authorization_digest: str | None = None,
) -> V063RunArtifacts:
    """Execute one development episode with total, resilient post-processing."""

    root = project_root.resolve()
    manifest = read_v063_freeze_manifest(root)
    if authorization_digest != manifest["hash_set_digest"]:
        raise ConfigurationError("v0.6.3 direct execution lacks freeze authorization")
    if os.environ.get("UC_BENCH_V063_PARTITION", "development") != "development":
        raise ConfigurationError("v0.6.3 execution rejects non-development partitions")
    adapters = load_v062_provider_adapters(root)
    versioned = replace(
        config,
        run_id=(
            config.run_id.replace("hard6-", "hard63-", 1)
            if config.run_id.startswith("hard6-")
            else f"hard63-{config.run_id}"
        ),
    )
    with _RUN_LOCK, _temporary_environment("OPENROUTER_API_KEY", openrouter_key):
        original: dict[str, Any] = {
            "read_v06_freeze_manifest": v06_runner.read_v06_freeze_manifest,
            "load_provider_adapters": v06_runner.load_provider_adapters,
            "AuditedOpenRouterClient": v06_runner.AuditedOpenRouterClient,
            "RequestLedger": v06_runner.RequestLedger,
            "grade_v06": v06_runner.grade_v06,
        }
        try:
            v06_runner.read_v06_freeze_manifest = read_v063_freeze_manifest
            v06_runner.load_provider_adapters = lambda _root: adapters
            v06_runner.AuditedOpenRouterClient = V062AuditedOpenRouterClient
            v06_runner.RequestLedger = V061RequestLedger
            v06_runner.grade_v06 = grade_v063
            try:
                artifacts = v06_runner.run_v06_episode(
                    root,
                    versioned,
                    openrouter_key=openrouter_key,
                )
            except Exception as exc:
                artifacts = _emergency_artifacts(
                    root,
                    versioned,
                    error=exc,
                    key=openrouter_key,
                )
        finally:
            for name, value in original.items():
                setattr(v06_runner, name, value)
    if grader_infrastructure_failed(artifacts.summary["diagnostic_grade"]):
        artifacts.summary["classification"] = "grader_infrastructure_failure"
        artifacts.summary["attempt_score"] = None
        artifacts.summary["scientific_score"] = None
    artifacts.summary["runner_revision"] = "0.6.3"
    artifacts.summary[
        "scientific_contract_revision"
    ] = "0.6-task-and-threshold-identical"
    _write_json(artifacts.summary_path, artifacts.summary, secret=openrouter_key)
    return artifacts

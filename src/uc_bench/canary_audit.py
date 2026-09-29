"""Build a public, redacted index of local canary attempts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from uc_bench.model_runner import _redact_public_identifiers, completion_stats


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def rebuild_canary_audit(project_root: Path) -> dict[str, Any]:
    """Recompute public summaries from local run artifacts and redact provider IDs."""

    summaries = []
    summary_paths = (project_root / "build" / "model_runs").glob(
        "canary-*/run_summary.json"
    )
    for summary_path in summary_paths:
        summary = _redact_public_identifiers(_read_json(summary_path))
        verifiers_path = summary_path.with_name("verifiers_output.json")
        if verifiers_path.is_file():
            verifiers_output = _redact_public_identifiers(_read_json(verifiers_path))
            _write_json(verifiers_path, verifiers_output)
            outputs = verifiers_output.get("outputs") or []
            if outputs and isinstance(outputs[0], dict):
                summary.update(completion_stats(outputs[0]))
        _write_json(summary_path, summary)
        summaries.append(summary)
    summaries.sort(key=lambda row: str(row.get("executed_at", "")))
    rows = [
        {
            key: summary.get(key)
            for key in (
                "run_id",
                "model_id",
                "executed_at",
                "classification",
                "infrastructure_failure",
                "phase",
                "turn_count",
                "tool_call_count",
                "tool_call_counts",
                "token_usage",
                "cost",
                "openrouter_cost_delta_usd",
                "stop_condition",
                "rollout_error",
            )
        }
        for summary in summaries
    ]
    public = {
        "schema_version": "0.1",
        "attempts": rows,
        "attempt_count": len(rows),
        "successful_episode_count": sum(
            row["classification"] == "valid_episode" for row in rows
        ),
    }
    _write_json(project_root / "artifacts" / "runtime" / "canary_attempts.json", public)
    if summaries:
        _write_json(
            project_root / "artifacts" / "runtime" / "canary_summary.json",
            summaries[-1],
        )
    return public

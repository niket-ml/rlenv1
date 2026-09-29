"""Case 2 sentinel aggregation without changing frozen scores."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from uc_bench.case1_pilot_v1_execution import funding_requirement, funding_snapshot
from uc_bench.case2_pilot_v1_rc1_execution import STATE_PATH
from uc_bench.case2_pilot_v1_rc1_release import RELEASE_ROOT, read_freeze
from uc_bench.errors import ConfigurationError
from uc_bench.model_runner import _write_json

REPORT_JSON = RELEASE_ROOT / "case2_sentinel_report.json"
REPORT_MD = Path("reports/UC_BENCH_CASE2_PILOT_V1_RC1_SENTINEL.md")


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError(f"JSON object required: {path}")
    return value


def _cell(root: Path, relative: str) -> dict[str, Any]:
    summary = _read(root / relative)
    grade = summary.get("diagnostic_grade") or {}
    submission = summary.get("submission") or {}
    final = submission.get("final_submission") or {}
    requirements = {
        row["requirement_id"]: bool(row["passed"]) for row in grade.get("requirements") or []
    }
    first = grade.get("first_decision_critical_failure")
    return {
        "model_id": summary["model_id"],
        "route": (summary.get("provider_identity") or {}).get("pinned_provider"),
        "technical_reliability": summary.get("reliability_score"),
        "classification": summary.get("classification"),
        "strict_mission_success": summary.get("complete_mission_success"),
        "partial_scientific_quality": summary.get("partial_scientific_quality"),
        "scientific_properties": requirements,
        "first_decision_critical_failure": first,
        "downstream_consequences": (
            first.get("downstream_dependencies") if isinstance(first, dict) else []
        ),
        "identity_workflow": (
            (submission.get("validation_plan") or {}).get("prospective_specification") or {}
        ).get("identity_basis"),
        "followup_choice": (submission.get("followup_plan") or {}).get("chosen_resource"),
        "belief_revision": final.get("belief_updates"),
        "final_action": final.get("decision"),
        "turns": summary.get("assistant_turns"),
        "requests": summary.get("provider_request_count"),
        "cost_usd": summary.get("cumulative_reported_cost_usd"),
        "completion_status": summary.get("stop_condition"),
        "recoverable_tool_errors": (summary.get("trajectory_replay") or {}).get(
            "framework_tool_error_count"
        ),
        "contract_failure": grade.get("failure_class") == "contract_failure",
        "provider_failure": str(summary.get("classification") or "").startswith(
            ("isolated_provider", "provider_")
        ),
        "infrastructure_failure": summary.get("classification")
        in {"infrastructure_failure", "grader_failure"},
    }


def build_report(project_root: Path, *, key: str) -> dict[str, Any]:
    root = project_root.resolve()
    release = read_freeze(root)
    state = _read(root / STATE_PATH)
    cells = [_cell(root, path) for path in state.get("summary_paths") or []]
    valid = [row for row in cells if row["classification"] == "valid_episode"]
    scores = [float(row["partial_scientific_quality"]) for row in valid]
    missions = [bool(row["strict_mission_success"]) for row in valid]
    ceiling = bool(valid) and all(missions)
    separation = len(set(scores)) > 1 if scores else False
    failures = [row for row in valid if not row["strict_mission_success"]]
    concentrated = False
    failed_first = [
        (row["first_decision_critical_failure"] or {}).get("requirement_id") for row in failures
    ]
    if failed_first:
        concentrated = (
            max(failed_first.count(item) for item in set(failed_first)) / len(failed_first) > 0.5
        )
    funding = funding_snapshot(key)
    next_requirement = funding_requirement(funding, 52.0)
    clean = state.get("status") == "completed" and not state.get("global_stop_faults")
    supports_full = bool(
        clean
        and len(cells) == 3
        and len(valid) >= 2
        and not all(row["infrastructure_failure"] for row in cells)
    )
    result = {
        "schema_version": "uc-bench-case2-pilot-v1-rc1-report-1",
        "release_id": release["release_id"],
        "release_digest": release["closure"]["aggregate_digest"],
        "closure_groups": release["closure"]["group_digests"],
        "status": state.get("status"),
        "scientific_spend_usd": state.get("scientific_spend_usd"),
        "cells_attempted": len(cells),
        "cells": cells,
        "interpretation": {
            "one_attempt_per_model_not_a_stable_ranking": True,
            "ceiling_warning": ceiling,
            "genuine_scientific_separation": separation,
            "failure_concentrated_on_one_workflow_step": concentrated,
            "artificial_completion_or_contract_floor": bool(cells)
            and all(
                row["contract_failure"] or row["completion_status"] != "submitted" for row in cells
            ),
            "insufficient_evidence": len(valid) < 2,
        },
        "full_five_model_stage_justified": supports_full,
        "current_funding": funding,
        "funding_for_separate_52_usd_stage": next_requirement,
        "global_stop_faults": state.get("global_stop_faults") or [],
    }
    return result


def write_report(project_root: Path, *, key: str) -> dict[str, Any]:
    root = project_root.resolve()
    value = build_report(root, key=key)
    _write_json(root / REPORT_JSON, value, secret=key)
    lines = [
        "# UC-Bench Case 2 RC1 — three-model sentinel",
        "",
        f"Release digest: `{value['release_digest']}`",
        f"Status: **{value['status']}**",
        f"Scientific spend: **${float(value['scientific_spend_usd'] or 0):.6f}**",
        "",
        "This is a one-attempt development sentinel, not a stable model ranking.",
        "",
        "| Model | Class | Mission | Partial | Reliability | Requests | Cost |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in value["cells"]:
        lines.append(
            "| {model_id} | {classification} | {strict_mission_success} | "
            "{partial_scientific_quality} | {technical_reliability} | {requests} | "
            "${cost_usd} |".format(**row)
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "```json",
            json.dumps(value["interpretation"], indent=2, sort_keys=True),
            "```",
            "",
            "## Funding for a separate $52 stage",
            "",
            "```json",
            json.dumps(value["funding_for_separate_52_usd_stage"], indent=2, sort_keys=True),
            "```",
        ]
    )
    target = root / REPORT_MD
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return value


__all__ = ["REPORT_JSON", "REPORT_MD", "build_report", "write_report"]

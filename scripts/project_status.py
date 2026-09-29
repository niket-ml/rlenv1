#!/usr/bin/env python3
"""Validate and display UC-Bench's persistent project audit state."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from textwrap import shorten
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATUS_PATH = PROJECT_ROOT / "audit" / "status.json"
FINDINGS_PATH = PROJECT_ROOT / "audit" / "findings.json"

STAGE_STATUSES = {"not_started", "in_progress", "blocked", "complete"}
FINDING_STATUSES = {"open", "closed", "accepted"}
SEVERITIES = {"critical", "high", "medium", "low"}


class AuditError(ValueError):
    """Raised when the persistent audit state is inconsistent."""


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise AuditError(f"{path.relative_to(PROJECT_ROOT)} must contain an object")
    return value


def validate(
    status: dict[str, Any], findings: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    stages = status.get("stages")
    if not isinstance(stages, list) or len(stages) != 10:
        raise AuditError("audit/status.json must define exactly 10 stages")

    stage_ids = [stage.get("id") for stage in stages]
    if stage_ids != list(range(1, 11)):
        raise AuditError("stage ids must be ordered integers 1 through 10")

    active = []
    for stage in stages:
        stage_status = stage.get("status")
        if stage_status not in STAGE_STATUSES:
            raise AuditError(f"stage {stage['id']} has invalid status {stage_status!r}")
        if stage_status == "in_progress":
            active.append(stage["id"])
        for field in ("name", "gate", "next_action"):
            if not isinstance(stage.get(field), str) or not stage[field].strip():
                raise AuditError(f"stage {stage['id']} requires non-empty {field}")
        evidence = stage.get("evidence")
        if not isinstance(evidence, list) or not all(isinstance(item, str) for item in evidence):
            raise AuditError(f"stage {stage['id']} evidence must be a list of paths")
        for item in evidence:
            if not (PROJECT_ROOT / item).exists():
                raise AuditError(f"stage {stage['id']} evidence does not exist: {item}")

    if len(active) > 1:
        raise AuditError("at most one stage may be in_progress")
    current_stage = status.get("current_stage")
    if current_stage not in stage_ids:
        raise AuditError("current_stage must reference one of the ten stages")
    if active and active != [current_stage]:
        raise AuditError("current_stage must match the in_progress stage")

    finding_rows = findings.get("findings")
    if not isinstance(finding_rows, list):
        raise AuditError("audit/findings.json findings must be a list")
    finding_ids = [finding.get("id") for finding in finding_rows]
    if len(finding_ids) != len(set(finding_ids)):
        raise AuditError("audit finding ids must be unique")

    for finding in finding_rows:
        finding_id = finding.get("id", "<missing>")
        if finding.get("status") not in FINDING_STATUSES:
            raise AuditError(f"finding {finding_id} has an invalid status")
        if finding.get("severity") not in SEVERITIES:
            raise AuditError(f"finding {finding_id} has an invalid severity")
        if finding.get("stage") not in stage_ids:
            raise AuditError(f"finding {finding_id} references an invalid stage")
        for field in ("finding", "required_resolution"):
            if not isinstance(finding.get(field), str) or not finding[field].strip():
                raise AuditError(f"finding {finding_id} requires non-empty {field}")

    known_findings = set(finding_ids)
    for stage in stages:
        references = stage.get("open_findings")
        if not isinstance(references, list):
            raise AuditError(f"stage {stage['id']} open_findings must be a list")
        unknown = set(references) - known_findings
        if unknown:
            raise AuditError(f"stage {stage['id']} references unknown findings: {sorted(unknown)}")
        not_open = {
            finding["id"]
            for finding in finding_rows
            if finding["id"] in references and finding["status"] != "open"
        }
        if not_open:
            raise AuditError(f"stage {stage['id']} lists non-open findings: {sorted(not_open)}")

    return stages, finding_rows


def render(
    status: dict[str, Any],
    stages: list[dict[str, Any]],
    findings: list[dict[str, Any]],
) -> str:
    lines = [
        status["project"],
        f"Updated: {status['last_updated']} | Current stage: {status['current_stage']}/10",
        f"Objective: {status['objective']}",
        "",
        "Stages",
    ]
    for stage in stages:
        lines.append(
            f"{stage['id']:>2}. {stage['status']:<11} {stage['name']}"
        )
        if stage["id"] == status["current_stage"]:
            lines.append(f"    Next: {shorten(stage['next_action'], width=100)}")

    open_findings = [finding for finding in findings if finding["status"] == "open"]
    lines.extend(["", f"Open audit findings: {len(open_findings)}"])
    for finding in open_findings:
        lines.append(
            f"- {finding['id']} [{finding['severity']}] stage {finding['stage']}: "
            f"{shorten(finding['finding'], width=100)}"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate audit state without rendering the full status",
    )
    args = parser.parse_args()

    status = load_json(STATUS_PATH)
    findings = load_json(FINDINGS_PATH)
    stages, finding_rows = validate(status, findings)
    open_count = sum(finding["status"] == "open" for finding in finding_rows)

    if args.check:
        print(f"Audit status OK: {len(stages)} stages, {open_count} open findings")
    else:
        print(render(status, stages, finding_rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

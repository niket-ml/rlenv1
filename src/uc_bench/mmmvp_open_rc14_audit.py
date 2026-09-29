"""Zero-cost disclosure and archived-submission diagnostics for RC1.4."""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.hashing import canonical_sha256
from uc_bench.mmmvp_open_rc14_contract import (
    ACTION_SEQUENCE,
    ENUMS,
    FINAL_SUBMISSION_FIELDS,
    FOLLOWUP_PLAN_FIELDS,
    RC14_AGENT_VISIBLE_CONTRACT,
    RELATIONSHIP_CONSTRAINTS,
    VALIDATION_PLAN_FIELDS,
)
from uc_bench.mmmvp_open_schema import validate_final_submission
from uc_bench.model_runner import _write_json

DISCLOSURE_AUDIT_PATH = Path("artifacts/mmmvp_open_rc14/contract_disclosure_audit.json")
ARCHIVED_REPLAY_PATH = Path("artifacts/mmmvp_open_rc14/archived_submission_replay.json")

_INDEX = re.compile(r"\[\d+\]")
_PREVIOUSLY_UNDISCLOSED = (
    re.compile(r"^calculations\[\d+\]\.unit_of_analysis$"),
    re.compile(r"^calculations\[\d+\]\.cohort(?:\.|$)"),
)


def normalize_issue_path(path: str) -> str:
    return _INDEX.sub("[*]", path)


def disclosed_field_paths() -> set[str]:
    return {
        str(row["path"])
        for row in (
            *VALIDATION_PLAN_FIELDS,
            *FOLLOWUP_PLAN_FIELDS,
            *FINAL_SUBMISSION_FIELDS,
        )
    }


def issue_is_disclosed(issue: dict[str, Any]) -> bool:
    path = normalize_issue_path(str(issue.get("path") or ""))
    code = str(issue.get("code") or "")
    if path in disclosed_field_paths():
        return True
    if code in {"duplicate_identifier", "identifier_required"}:
        return bool(RC14_AGENT_VISIBLE_CONTRACT["policy"]["identifier_pattern"])
    if code == "unknown_reference":
        return any(row["id"] == "artifact_references_resolve" for row in RELATIONSHIP_CONSTRAINTS)
    if code == "competing_decision_effects_required":
        return any(
            row["id"] == "validation_competing_hypotheses"
            for row in RELATIONSHIP_CONSTRAINTS
        )
    if code == "commitment_mismatch" and path == "beliefs_before":
        return any(row["id"] == "followup_beliefs_preserved" for row in RELATIONSHIP_CONSTRAINTS)
    if code == "pre_reveal_file_required":
        return any(
            row["id"] == "validation_inputs_exist_before_reveal"
            for row in RELATIONSHIP_CONSTRAINTS
        )
    return False


def audit_contract_disclosure() -> dict[str, Any]:
    fields = [
        *VALIDATION_PLAN_FIELDS,
        *FOLLOWUP_PLAN_FIELDS,
        *FINAL_SUBMISSION_FIELDS,
    ]
    enum_references = sorted({str(row["enum"]) for row in fields if row.get("enum")})
    missing_enum_definitions = sorted(set(enum_references) - set(ENUMS))
    duplicate_field_rows = sorted(
        path for path, count in Counter(str(row["path"]) for row in fields).items() if count > 1
    )
    # Paths may intentionally recur across different top-level objects.  The
    # per-object check below is the meaningful uniqueness rule.
    duplicate_within_object: dict[str, list[str]] = {}
    for name, rows in (
        ("validation_plan", VALIDATION_PLAN_FIELDS),
        ("followup_plan", FOLLOWUP_PLAN_FIELDS),
        ("final_submission", FINAL_SUBMISSION_FIELDS),
    ):
        duplicates = sorted(
            path
            for path, count in Counter(str(row["path"]) for row in rows).items()
            if count > 1
        )
        if duplicates:
            duplicate_within_object[name] = duplicates
    exact_language_fields = sorted(
        {
            str(row["path"])
            for row in fields
            if row.get("enum") or row.get("type") == "identifier"
        }
    )
    forbidden_disclosures = [
        token
        for token in (
            "case_01",
            "case_02",
            "case_03",
            "case_04",
            "signal_collapses",
            "signal_remains",
            "preferred_resource",
            "correct_decision",
            "hidden_outcome",
        )
        if token.lower() in json.dumps(RC14_AGENT_VISIBLE_CONTRACT).lower()
    ]
    status = (
        "passed"
        if not missing_enum_definitions
        and not duplicate_within_object
        and not forbidden_disclosures
        and len(ACTION_SEQUENCE) == 5
        and len(RELATIONSHIP_CONSTRAINTS) >= 14
        else "failed"
    )
    return {
        "schema_version": "uc-bench-open-mmmvp-rc1-4-disclosure-audit-1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": status,
        "contract_revision": RC14_AGENT_VISIBLE_CONTRACT["contract_revision"],
        "contract_sha256": canonical_sha256(RC14_AGENT_VISIBLE_CONTRACT),
        "field_row_count": len(fields),
        "distinct_field_path_count": len({str(row["path"]) for row in fields}),
        "duplicate_paths_across_different_objects_diagnostic": duplicate_field_rows,
        "duplicate_paths_within_object": duplicate_within_object,
        "enum_family_count": len(ENUMS),
        "enum_references": enum_references,
        "missing_enum_definitions": missing_enum_definitions,
        "relationship_and_conditional_count": len(RELATIONSHIP_CONSTRAINTS),
        "action_sequence_step_count": len(ACTION_SEQUENCE),
        "exact_language_field_paths": exact_language_fields,
        "free_text_can_determine_science": False,
        "forbidden_scientific_disclosures": forbidden_disclosures,
        "unit_of_analysis_values_disclosed": ENUMS["unit_of_analysis"],
        "cohort_fields_disclosed": [
            "calculations[*].cohort.split_values",
            "calculations[*].cohort.entity_ids",
            "calculations[*].cohort.included_row_count",
        ],
    }


def write_contract_disclosure_audit(project_root: Path) -> dict[str, Any]:
    value = audit_contract_disclosure()
    target = project_root.resolve() / DISCLOSURE_AUDIT_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    _write_json(target, value, secret="")
    return value


def _submit_actions(latest: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        row
        for row in latest.get("tool_actions") or []
        if row.get("name") == "submit"
        and isinstance((row.get("invocation_arguments") or {}).get("payload_json"), str)
    ]


def replay_archived_submissions(project_root: Path) -> dict[str, Any]:
    """Replay raw payloads through the unchanged validator, never the scorer."""

    root = project_root.resolve()
    wanted = {
        "mistralai/mistral-large-2512",
        "anthropic/claude-sonnet-4",
        "google/gemini-3.1-pro-preview",
    }
    rows: list[dict[str, Any]] = []
    for summary_path in sorted(
        (root / "build/uc_bench_mmmvp_open_rc12_runs").glob("*/run_summary.json")
    ):
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        model_id = str(summary.get("model_id"))
        if model_id not in wanted:
            continue
        latest_path = summary_path.parent / "host_trajectory/latest.json"
        latest = json.loads(latest_path.read_text(encoding="utf-8"))
        attempts: list[dict[str, Any]] = []
        issue_counts: Counter[str] = Counter()
        hidden_discovery_counts: Counter[str] = Counter()
        for action in _submit_actions(latest):
            raw = (action.get("invocation_arguments") or {})["payload_json"]
            try:
                payload = json.loads(raw)
                replayed = validate_final_submission(payload)
                issues = [issue.to_dict() for issue in replayed.issues]
                parse_error = None
            except json.JSONDecodeError as exc:
                issues = []
                parse_error = str(exc)
            for issue in issues:
                signature = f"{issue['code']}:{normalize_issue_path(issue['path'])}"
                issue_counts[signature] += 1
                if any(pattern.match(issue["path"]) for pattern in _PREVIOUSLY_UNDISCLOSED):
                    hidden_discovery_counts[signature] += 1
            attempts.append(
                {
                    "tool_call_id": action.get("tool_call_id"),
                    "payload_sha256": canonical_sha256(raw),
                    "archived_payload_schema_valid": not issues and parse_error is None,
                    "parse_error": parse_error,
                    "issue_count": len(issues),
                    "all_replayed_issues_now_disclosed": all(
                        issue_is_disclosed(issue) for issue in issues
                    ),
                }
            )
        rows.append(
            {
                "model_id": model_id,
                "source_summary": summary_path.relative_to(root).as_posix(),
                "source_classification_unchanged": summary.get("classification"),
                "source_score_unchanged": summary.get("partial_scientific_quality"),
                "submission_attempt_count": len(attempts),
                "replayed_issue_occurrences": sum(issue_counts.values()),
                "issue_occurrences_by_signature": dict(sorted(issue_counts.items())),
                "previously_undisclosed_issue_occurrences_now_preemptively_disclosed": sum(
                    hidden_discovery_counts.values()
                ),
                "previously_undisclosed_signatures_now_disclosed": dict(
                    sorted(hidden_discovery_counts.items())
                ),
                "attempts": attempts,
            }
        )
    value = {
        "schema_version": "uc-bench-open-mmmvp-rc1-4-archived-submission-replay-1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "passed" if len(rows) == 3 else "failed",
        "source_version": "RC1.2",
        "diagnostic_replay_only": True,
        "archived_payloads_modified": False,
        "archived_scores_recomputed": False,
        "archived_scores_reinterpreted": False,
        "conditional_interpretation": (
            "Counts identify rejections that an agent adhering to the revised public contract "
            "can avoid. The unchanged archived payloads remain invalid and are not rescored."
        ),
        "models": rows,
        "all_replayed_issues_now_disclosed": all(
            attempt["all_replayed_issues_now_disclosed"]
            for row in rows
            for attempt in row["attempts"]
        ),
    }
    target = root / ARCHIVED_REPLAY_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    _write_json(target, value, secret="")
    return value


__all__ = [
    "ARCHIVED_REPLAY_PATH",
    "DISCLOSURE_AUDIT_PATH",
    "audit_contract_disclosure",
    "disclosed_field_paths",
    "issue_is_disclosed",
    "normalize_issue_path",
    "replay_archived_submissions",
    "write_contract_disclosure_audit",
]

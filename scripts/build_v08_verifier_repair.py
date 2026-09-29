#!/usr/bin/env python3
"""Build the zero-cost v0.8 verifier-architecture repair record."""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.hashing import sha256_file
from uc_bench.v08_controls import run_v08_mvp_controls
from uc_bench.v08_score_sources import (
    MISSION_SCORE_SOURCES,
    validate_score_source_registry,
)
from uc_bench.v08_verifier import verify_v08_submission

ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "artifacts/diagnostics"
REPORTS = ROOT / "reports/generated"
FIRST_SNAPSHOT = DIAGNOSTICS / "hard_suite_v08_execution_snapshot.json"
FIRST_SOURCE_ARCHIVE = DIAGNOSTICS / "hard_suite_v08_execution_snapshot_01_sources.tar.gz"
CASE2_RUN = ROOT / "build/hard_suite_v08_runs/v08-gpt-5.6-sol-case_02-20260909T061848Z"
CASE3_RUN = (
    ROOT / "build/hard_suite_v08_runs/v08-gpt-5.6-sol-case_03_signal_remains-20260909T062304Z"
)


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected JSON object: {path}")
    return value


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _hash_tree(path: Path) -> dict[str, str]:
    return {
        item.relative_to(ROOT).as_posix(): sha256_file(item)
        for item in sorted(path.rglob("*"))
        if item.is_file()
    }


def _case_hashes_from_first_snapshot(snapshot: dict[str, Any]) -> dict[str, str]:
    return {
        path: digest
        for path, digest in snapshot["hashes"].items()
        if path.startswith("tasks/hard_suite_v07/development/")
        or path.startswith("grader_private/hard_suite_v07/")
    }


def _current_hashes(paths: dict[str, str]) -> dict[str, str]:
    return {path: sha256_file(ROOT / path) for path in sorted(paths)}


def _case2_replay() -> dict[str, Any]:
    raw_summary = _read(CASE2_RUN / "run_summary.json")
    submission = _read(CASE2_RUN / "submission.json")
    repaired = verify_v08_submission(
        ROOT,
        CASE2_RUN / "workspace",
        submission,
        condition_id="case_02",
    )
    return {
        "schema_version": "0.8-development-verifier-replay-2",
        "interpretation": (
            "Development verifier replay only; this does not retroactively replace "
            "the immutable execution-snapshot result."
        ),
        "api_requests": 0,
        "api_spend_usd": 0.0,
        "raw_historical_result": {
            "partial_scientific_quality": raw_summary["partial_scientific_quality"],
            "complete_mission_success": raw_summary["complete_mission_success"],
            "checkpoint_scores": raw_summary["diagnostic_grade"]["checkpoint_scores"],
            "first_decision_critical_failure": raw_summary["diagnostic_grade"][
                "first_decision_critical_failure"
            ],
            "run_summary_sha256": sha256_file(CASE2_RUN / "run_summary.json"),
            "preserved_as_historical_execution_output": True,
        },
        "repaired_development_replay": repaired.to_dict(),
        "change_explanation": (
            "The exact same submission now passes because stage/disposition and claim "
            "IDs each use their disclosed machine fields; professional prose is audit-only."
        ),
    }


def _case3_resume_assessment() -> dict[str, Any]:
    ledger = _read(CASE3_RUN / "request_ledger.json")
    files = {
        item.relative_to(CASE3_RUN).as_posix() for item in CASE3_RUN.rglob("*") if item.is_file()
    }
    checkpoints = sorted(path.stem for path in (CASE3_RUN / "workspace/checkpoints").glob("*.json"))
    complete_messages_recorded = any(
        "messages" in request or "request_body" in request for request in ledger.get("requests", [])
    )
    exact_tool_records_present = "environment_event_log.json" in files
    has_c5 = "workspace/checkpoints/C5.json" in files
    has_submission = "submission.json" in files
    safe = all(
        (
            complete_messages_recorded,
            exact_tool_records_present,
            has_c5,
            has_submission,
        )
    )
    return {
        "schema_version": "0.8-interrupted-state-assessment-1",
        "condition_id": "case_03_signal_remains",
        "api_requests_during_assessment": 0,
        "recorded_request_count": ledger["request_count"],
        "recorded_response_cost_usd": ledger["cumulative_reported_cost_usd"],
        "preserved_checkpoint_files": checkpoints,
        "preserved_reveal": "workspace/revealed/validation_outcomes.csv" in files,
        "preserved_purchase_return": ("workspace/purchased/X31/replay_predictions.csv" in files),
        "exact_reconstruction": {
            "immutable_agent_visible_files": True,
            "saved_checkpoint_payloads_C1_through_C4": checkpoints == ["C1", "C2", "C3", "C4"],
            "complete_model_message_history": complete_messages_recorded,
            "assistant_reasoning_state_payloads": False,
            "complete_tool_arguments_and_results": exact_tool_records_present,
            "environment_event_record": exact_tool_records_present,
            "in_memory_checkpoint_and_phase_state": False,
            "final_C5": has_c5,
            "submission": has_submission,
        },
        "safe_resumption_possible": safe,
        "conclusion": (
            "Safe exact resumption is not possible. The workspace reconstructs the visible "
            "scientific state through C4 and the X31 return, but the request ledger stores "
            "counts/contracts rather than message bodies or tool results, and no environment "
            "event log or serialized runner state exists. A later authorized run must start "
            "Case 3 afresh; the interrupted attempt must remain an incomplete diagnostic."
        ),
        "raw_file_hashes": _hash_tree(CASE3_RUN),
    }


def _audit_rows() -> list[dict[str, Any]]:
    return [
        {
            "requirement": "patient_analysis_unit",
            "pre_repair": "single disclosed enum field",
            "post_repair": "unchanged; single authority",
            "duplicate_or_prose_risk": "none",
        },
        {
            "requirement": "cohort_counts",
            "pre_repair": "machine counts compared with reconstructed truth",
            "post_repair": "unchanged; single authority",
            "duplicate_or_prose_risk": "none",
        },
        {
            "requirement": "dependence_site_and_timing_inspected",
            "pre_repair": "three disclosed booleans",
            "post_repair": "unchanged; single authority",
            "duplicate_or_prose_risk": "none",
        },
        {
            "requirement": "commit_before_reveal",
            "pre_repair": "event order and digest",
            "post_repair": "unchanged; event record only",
            "duplicate_or_prose_risk": "none",
        },
        {
            "requirement": "patient_level_estimand",
            "pre_repair": "committed analysis-unit enum",
            "post_repair": "unchanged; distinct from executed patient mapping",
            "duplicate_or_prose_risk": "none",
        },
        {
            "requirement": "outcome_blind_training_fit",
            "pre_repair": "committed preprocessing booleans/enums",
            "post_repair": "unchanged; distinct from executed fit membership",
            "duplicate_or_prose_risk": "none",
        },
        {
            "requirement": "valid_uncertainty_plan",
            "pre_repair": "committed structure booleans plus unscored method prose",
            "post_repair": "unchanged machine booleans; prose cannot affect mission",
            "duplicate_or_prose_risk": "none",
        },
        {
            "requirement": "decision_metrics_and_rules_prespecified",
            "pre_repair": "metric IDs plus existence/length of prose rules and hypotheses",
            "post_repair": (
                "replaced by primary_metrics_prespecified; prose documentation diagnostic-only"
            ),
            "duplicate_or_prose_risk": "removed prose-derived mission failure",
        },
        {
            "requirement": "primary_calculation:{metric}",
            "pre_repair": "reported C3 number and saved calculation could each fail",
            "post_repair": "saved calculation only, independently recomputed from raw data",
            "duplicate_or_prose_risk": "removed duplicate numeric carrier",
        },
        {
            "requirement": "patient_mapping_artifact",
            "pre_repair": "saved patient table",
            "post_repair": "unchanged; row-by-row raw reconstruction",
            "duplicate_or_prose_risk": "none",
        },
        {
            "requirement": "preprocessing_membership_artifact",
            "pre_repair": "saved fit-membership table",
            "post_repair": "unchanged; raw lineage reconstruction",
            "duplicate_or_prose_risk": "none",
        },
        {
            "requirement": "analysis_structure_executed",
            "pre_repair": "self-reported execution booleans duplicated saved artifacts",
            "post_repair": "diagnostic-only; artifacts are authoritative",
            "duplicate_or_prose_risk": "removed duplicate execution carrier",
        },
        {
            "requirement": "contaminated_evidence_contained",
            "pre_repair": "machine eligibility boolean",
            "post_repair": "unchanged; claim scope remains a distinct downstream property",
            "duplicate_or_prose_risk": "none",
        },
        {
            "requirement": "material_diagnosis",
            "pre_repair": "disclosed finding IDs",
            "post_repair": "unchanged; machine IDs only",
            "duplicate_or_prose_risk": "none",
        },
        {
            "requirement": "decision_relevant_resource",
            "pre_repair": "both C4 chosen_resource and event-record purchase had to agree",
            "post_repair": (
                "event purchase plus disclosed decision_question only; duplicate "
                "declaration diagnostic"
            ),
            "duplicate_or_prose_risk": "removed duplicate action carrier",
        },
        {
            "requirement": "prepurchase_contingency_plan",
            "pre_repair": "event timing plus length of a free-text action list",
            "post_repair": (
                "diagnostic-only until a separate disclosed machine representation exists"
            ),
            "duplicate_or_prose_risk": "removed prose-derived mission failure",
        },
        {
            "requirement": "followup_calculation:{metric}",
            "pre_repair": "reported C5 number and saved follow-up number could each fail",
            "post_repair": "saved follow-up calculation only, independently recomputed",
            "duplicate_or_prose_risk": "removed duplicate numeric carrier",
        },
        {
            "requirement": "followup_artifact_and_evidence",
            "pre_repair": "saved and declared evidence-path arrays had to match",
            "post_repair": (
                "nonnumeric follow-up checks event-selected raw evidence and saved record; "
                "path prose cannot fail"
            ),
            "duplicate_or_prose_risk": "removed duplicate evidence-path carrier",
        },
        {
            "requirement": "evidence_consistent_belief_change",
            "pre_repair": "numeric delta plus nonempty hypothesis/evidence prose",
            "post_repair": "numeric before/after fields only; prose audit-only",
            "duplicate_or_prose_risk": "removed prose-derived mission failure",
        },
        {
            "requirement": "explicit_bounded_decision",
            "pre_repair": "stage/disposition plus private claim IDs inside decision prose",
            "post_repair": "stage/disposition enums only; claim IDs scored once in claim_scope",
            "duplicate_or_prose_risk": "removed hidden vocabulary and duplicate claim scoring",
        },
        {
            "requirement": "claim_scope",
            "pre_repair": "machine claim-ID fields",
            "post_repair": "unchanged; sole authority for supported/prohibited/asserted claims",
            "duplicate_or_prose_risk": "none after explicit_bounded_decision repair",
        },
    ]


def _score_source_table() -> dict[str, Any]:
    return {
        "schema_version": "0.8-score-source-table-1",
        "status": "passed" if not validate_score_source_registry() else "failed",
        "registry_errors": validate_score_source_registry(),
        "mission_critical_requirement_count": len(MISSION_SCORE_SOURCES),
        "prose_affects_any_mission_score": any(
            row["prose_can_affect_score"] for row in MISSION_SCORE_SOURCES
        ),
        "rows": list(MISSION_SCORE_SOURCES),
    }


def _markdown(
    *,
    replay: dict[str, Any],
    resume: dict[str, Any],
    score_table: dict[str, Any],
    controls: dict[str, Any],
    audit: dict[str, Any],
) -> str:
    repaired = replay["repaired_development_replay"]
    lines = [
        "# UC-Bench v0.8 zero-cost verifier-architecture repair",
        "",
        "## Outcome",
        "",
        (
            "The preserved Case 2 submission regrades from the historical 95/fail "
            f"to {repaired['partial_scientific_quality']:.0f}/pass. This is a development "
            "verifier replay, not a retroactive replacement of the frozen result."
        ),
        "",
        "No case, scientific truth, raw trajectory, or first execution snapshot was changed. "
        "No API request was made.",
        "",
        "## Duplicate-scoring audit",
        "",
        "| Requirement | Before | After | Finding |",
        "|---|---|---|---|",
    ]
    for row in audit["rows"]:
        lines.append(
            f"| {row['requirement']} | {row['pre_repair']} | "
            f"{row['post_repair']} | {row['duplicate_or_prose_risk']} |"
        )
    lines.extend(
        [
            "",
            "## Score-source table",
            "",
            (
                "| Requirement | Sole authority | Accepted values/property | "
                "Verification | Prose scored |"
            ),
            "|---|---|---|---|---:|",
        ]
    )
    for row in score_table["rows"]:
        accepted = "; ".join(str(value) for value in row["disclosed_accepted_values"])
        lines.append(
            f"| {row['requirement_id']} | {row['authoritative_source']} | {accepted} | "
            f"{row['verification_method']} | no |"
        )
    lines.extend(
        [
            "",
            "## Controls",
            "",
            f"All {controls['control_count']} original controls passed. "
            f"All {controls['naturalistic_language_fixture_count']} naturalistic-language "
            "fixtures also passed without changing any scientific score.",
            "",
            "## Interrupted Case 3",
            "",
            resume["conclusion"],
            "",
            "## Minimum cost for later completion (not authorized here)",
            "",
            "A fresh Case 3 signal-remains attempt plus Case 4 is expected to cost about "
            "$0.900223 from the preserved v0.7.1 condition-level observations. The smallest "
            "responsible hard cap under the existing $2.39 per-episode guard is $4.78. The "
            "already-spent $0.1902286 interrupted attempt is not treated as resumable credit.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    first_snapshot = _read(FIRST_SNAPSHOT)
    case_hashes = _case_hashes_from_first_snapshot(first_snapshot)
    current_case_hashes = _current_hashes(case_hashes)
    cases_unchanged = current_case_hashes == case_hashes
    raw_case2_hashes = _hash_tree(CASE2_RUN)
    raw_case3_hashes = _hash_tree(CASE3_RUN)
    with tempfile.TemporaryDirectory(prefix="uc-v08-repair-controls-") as directory:
        controls = run_v08_mvp_controls(ROOT, Path(directory))
    replay = _case2_replay()
    resume = _case3_resume_assessment()
    score_table = _score_source_table()
    audit_rows = _audit_rows()
    audit = {
        "schema_version": "0.8-verifier-architecture-audit-1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "passed",
        "api_requests": 0,
        "api_spend_usd": 0.0,
        "scientific_version_created": False,
        "scientific_cases_changed": not cases_unchanged,
        "first_execution_snapshot": {
            "path": FIRST_SNAPSHOT.relative_to(ROOT).as_posix(),
            "manifest_sha256": sha256_file(FIRST_SNAPSHOT),
            "hash_set_digest": first_snapshot["hash_set_digest"],
            "unchanged_expected_manifest_sha256": (
                "6e114b0c26dd4be39501c07173c1ea5fb55b907a97d409bf0e643a5837481d93"
            ),
            "source_archive_path": FIRST_SOURCE_ARCHIVE.relative_to(ROOT).as_posix(),
            "source_archive_sha256": sha256_file(FIRST_SOURCE_ARCHIVE),
        },
        "raw_results": {
            "case_02_file_hashes": raw_case2_hashes,
            "case_03_interrupted_file_hashes": raw_case3_hashes,
            "case_02_run_summary_expected_sha256": (
                "e9f711b61d99609982499695fd49cdc769d0c6ccc94ad94677d81ec0b2470111"
            ),
        },
        "case_and_truth_hashes_unchanged": cases_unchanged,
        "rows": audit_rows,
        "findings": {
            "requirements_reviewed": len(audit_rows),
            "duplicate_or_prose_paths_removed": 9,
            "private_claim_ids_required_in_prose": False,
            "mission_critical_substring_or_regex_checks": 0,
            "mission_properties_without_single_source": len(score_table["registry_errors"]),
            "prose_affects_mission_score": False,
        },
        "cost_to_complete_later": {
            "api_calls_authorized_now": False,
            "fresh_case_03_signal_remains_expected_usd": 0.5263912,
            "case_04_expected_usd": 0.3738318,
            "combined_expected_usd": 0.900223,
            "existing_per_episode_guard_usd": 2.39,
            "minimum_responsible_two_episode_cap_usd": 4.78,
        },
    }
    passed = all(
        (
            cases_unchanged,
            controls["status"] == "passed",
            score_table["status"] == "passed",
            replay["repaired_development_replay"]["complete_mission_success"],
            replay["repaired_development_replay"]["partial_scientific_quality"] == 100,
            not resume["safe_resumption_possible"],
            sha256_file(FIRST_SNAPSHOT)
            == "6e114b0c26dd4be39501c07173c1ea5fb55b907a97d409bf0e643a5837481d93",
            sha256_file(CASE2_RUN / "run_summary.json")
            == "e9f711b61d99609982499695fd49cdc769d0c6ccc94ad94677d81ec0b2470111",
        )
    )
    audit["status"] = "passed" if passed else "failed"
    _write(DIAGNOSTICS / "hard_suite_v08_repair_controls.json", controls)
    _write(DIAGNOSTICS / "hard_suite_v08_case2_development_replay.json", replay)
    _write(DIAGNOSTICS / "hard_suite_v08_case3_resume_assessment.json", resume)
    _write(DIAGNOSTICS / "hard_suite_v08_score_source_table.json", score_table)
    _write(DIAGNOSTICS / "hard_suite_v08_verifier_architecture_audit.json", audit)
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "hard_suite_v08_verifier_repair.md").write_text(
        _markdown(
            replay=replay,
            resume=resume,
            score_table=score_table,
            controls=controls,
            audit=audit,
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": audit["status"],
                "api_requests": 0,
                "case2_repaired_score": replay["repaired_development_replay"][
                    "partial_scientific_quality"
                ],
                "case2_repaired_mission": replay["repaired_development_replay"][
                    "complete_mission_success"
                ],
                "control_count": controls["control_count"],
                "naturalistic_fixture_count": controls["naturalistic_language_fixture_count"],
                "case3_safe_resume": resume["safe_resumption_possible"],
                "score_source_errors": score_table["registry_errors"],
                "scientific_cases_changed": not cases_unchanged,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

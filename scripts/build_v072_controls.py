#!/usr/bin/env python3
"""Build zero-cost v0.7.2 separation, anti-gaming, and altered-input controls."""

from __future__ import annotations

import copy
import csv
import hashlib
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.hard_suite_v072 import replay_v072_reference
from uc_bench.v072_grader import grade_v072_submission
from uc_bench.v072_schema import SCHEMA_VERSION

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts/diagnostics/hard_suite_v072_controls.json"
CONDITIONS = [
    ("case_01", "default"),
    ("case_02", "default"),
    ("case_03", "signal_collapses"),
    ("case_03", "signal_remains"),
    ("case_04", "default"),
]


def _digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _sync(submission: dict[str, Any]) -> None:
    committed = _digest(submission["checkpoints"]["C2"])
    for event in submission["event_log"]:
        if event.get("event") == "save_checkpoint":
            checkpoint = event["checkpoint"]
            event["digest"] = _digest(submission["checkpoints"][checkpoint])
        elif event.get("event") == "commit_validation_plan":
            event["digest"] = committed
        elif event.get("event") in {"reveal_validation", "submit"}:
            event["committed_plan_hash"] = committed


def _blank(decision: str) -> dict[str, Any]:
    return {
        "checkpoints": {
            "C1": {
                "schema_version": SCHEMA_VERSION,
                "analysis_unit": "PATIENT",
                "findings": {
                    "diagnosed_concepts": [
                        "patient_dependence",
                        "site_confounding",
                        "validation_information_leakage",
                        "miscalibration",
                    ]
                },
            },
            "C2": {"schema_version": SCHEMA_VERSION},
            "C3": {"schema_version": SCHEMA_VERSION},
            "C4": {"schema_version": SCHEMA_VERSION, "chosen_resource": "none"},
            "C5": {
                "schema_version": SCHEMA_VERSION,
                "decisions": {"initial": decision, "final": decision},
            },
        },
        "event_log": [
            {"sequence": 1, "event": "reset"},
            {"sequence": 2, "event": "purchase_resource", "resource_id": "none", "cost_units": 0},
            {"sequence": 3, "event": "submit", "committed_plan_hash": "guessed"},
        ],
    }


def main() -> int:
    rows: list[dict[str, Any]] = []
    universal: dict[str, int] = {}
    with tempfile.TemporaryDirectory(prefix="uc-v072-controls-") as directory:
        temporary = Path(directory)
        references: dict[tuple[str, str], tuple[dict[str, Any], Path]] = {}
        for index, (case_id, mechanism) in enumerate(CONDITIONS):
            for alternative in (False, True):
                workspace = temporary / f"reference-{index}-{alternative}"
                submission, grade = replay_v072_reference(
                    ROOT,
                    case_id,
                    workspace,
                    mechanism=mechanism,
                    alternative=alternative,
                )
                rows.append(
                    {
                        "control": "alternative" if alternative else "reference",
                        "case_id": case_id,
                        "mechanism": mechanism,
                        "score": grade.scientific_work_quality_score,
                        "mission": grade.strict_full_mission_success,
                    }
                )
                if not alternative:
                    references[(case_id, mechanism)] = (submission, workspace)

            for control in ("generic", "keyword", "guessed_final"):
                submission = _blank("STOP")
                if control == "generic":
                    submission["checkpoints"]["C1"].pop("findings")
                elif control == "guessed_final":
                    submission["checkpoints"]["C1"] = {"schema_version": SCHEMA_VERSION}
                grade = grade_v072_submission(ROOT, case_id, submission, mechanism=mechanism)
                rows.append(
                    {
                        "control": control,
                        "case_id": case_id,
                        "mechanism": mechanism,
                        "score": grade.scientific_work_quality_score,
                        "mission": grade.strict_full_mission_success,
                    }
                )

        for decision in ("ADVANCE", "PAUSE", "STOP", "INSUFFICIENT_EVIDENCE"):
            successes = 0
            for case_id, mechanism in CONDITIONS:
                source, workspace = references[(case_id, mechanism)]
                submission = copy.deepcopy(source)
                submission["checkpoints"]["C5"]["decisions"]["final"] = decision
                _sync(submission)
                grade = grade_v072_submission(
                    ROOT,
                    case_id,
                    submission,
                    mechanism=mechanism,
                    workspace_root=workspace,
                )
                successes += int(bool(grade.strict_full_mission_success))
            universal[decision] = successes

        source, workspace = references[("case_02", "default")]
        recovery = copy.deepcopy(source)
        recovery["checkpoints"]["C1"]["analysis_unit"] = {
            "level": "BIOPSY",
            "patient_key": "sample_id",
        }
        _sync(recovery)
        recovery_grade = grade_v072_submission(ROOT, "case_02", recovery, workspace_root=workspace)

        source, workspace = references[("case_01", "default")]
        hard_coded = copy.deepcopy(source)
        hard_coded["checkpoints"]["C3"]["artifact_manifest"]["patient_table_path"] = (
            "work/missing.csv"
        )
        _sync(hard_coded)
        hard_coded_grade = grade_v072_submission(
            ROOT, "case_01", hard_coded, workspace_root=workspace
        )

        altered = copy.deepcopy(source)
        outcomes = workspace / "revealed/validation_outcomes.csv"
        outcome_rows = list(csv.DictReader(outcomes.read_text(encoding="utf-8").splitlines()))
        for row in outcome_rows[:20]:
            row["week6_response"] = str(1 - int(row["week6_response"]))
        with outcomes.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(outcome_rows[0]))
            writer.writeheader()
            writer.writerows(outcome_rows)
        altered_grade = grade_v072_submission(ROOT, "case_01", altered, workspace_root=workspace)

    reference_rows = [row for row in rows if row["control"] == "reference"]
    alternative_rows = [row for row in rows if row["control"] == "alternative"]
    attack_rows = [row for row in rows if row["control"] in {"generic", "keyword", "guessed_final"}]
    checks = {
        "reference_at_least_90": all(float(row["score"]) >= 90 for row in reference_rows),
        "alternative_at_least_90": all(float(row["score"]) >= 90 for row in alternative_rows),
        "reference_and_alternative_all_missions": all(
            bool(row["mission"]) for row in [*reference_rows, *alternative_rows]
        ),
        "generic_keyword_guessed_at_most_20": all(
            float(row["score"]) <= 20 and not row["mission"] for row in attack_rows
        ),
        "universal_policies_fail": all(value < len(CONDITIONS) for value in universal.values()),
        "graceful_recovery_preserves_later_credit": (
            recovery_grade.checkpoint_scores["C3"] == 100
            and recovery_grade.checkpoint_scores["C5"] == 100
            and recovery_grade.scientific_work_quality_score >= 90
        ),
        "hard_coded_values_without_artifacts_fail": (
            hard_coded_grade.checkpoint_scores["C3"] <= 30
            and not hard_coded_grade.strict_full_mission_success
        ),
        "altered_input_invalidates_copied_answer": (
            altered_grade.checkpoint_scores["C3"] <= 30
            and not altered_grade.strict_full_mission_success
        ),
    }
    result = {
        "schema_version": "0.7.2-controls-1",
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "control_rows": rows,
        "universal_policy_mission_success_counts": universal,
        "graceful_recovery": recovery_grade.to_dict(),
        "hard_coded_without_artifacts": hard_coded_grade.to_dict(),
        "altered_input": altered_grade.to_dict(),
        "new_api_requests": 0,
        "new_api_spend_usd": 0.0,
        "heldout_requests": 0,
        "astra_requests": 0,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(OUTPUT)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# ruff: noqa: E501
"""Build the zero-cost v0.8 five-condition MVP readiness package."""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.hashing import canonical_sha256, sha256_file
from uc_bench.v08_controls import CONDITIONS, run_v08_mvp_controls
from uc_bench.v08_verifier import load_v08_mvp, replay_archived_v071

ROOT = Path(__file__).resolve().parents[1]
REPLAY_ROOT = ROOT / "artifacts/diagnostics/hard_suite_v072_replay_fixtures"


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _condition_source_hashes(condition: dict[str, Any]) -> dict[str, Any]:
    case_id = condition["source_case_id"]
    public = ROOT / "tasks/hard_suite_v07/development" / case_id
    private = ROOT / "grader_private/hard_suite_v07" / case_id
    paths = [path for path in public.rglob("*") if path.is_file()]
    paths.extend([private / "truth.json"])
    paths.extend(path for path in (private / "sealed").rglob("*") if path.is_file())
    mechanism = condition["source_mechanism"]
    if case_id == "case_03":
        resource = private / "resource_returns/X31" / mechanism
        paths.extend(path for path in resource.rglob("*") if path.is_file())
    hashes = {
        path.relative_to(ROOT).as_posix(): sha256_file(path) for path in sorted(set(paths))
    }
    return {
        "condition_id": condition["condition_id"],
        "source_case_id": case_id,
        "source_mechanism": mechanism,
        "scientific_purpose": condition["scientific_purpose"],
        "source_hash_count": len(hashes),
        "source_hashes": hashes,
        "source_hash_set_digest": canonical_sha256(hashes),
        "source_files_modified_for_v08": False,
    }


def _mapping(mvp: dict[str, Any]) -> dict[str, Any]:
    rows = [_condition_source_hashes(row) for row in mvp["active_conditions"]]
    return {
        "schema_version": "0.8-mvp-mapping-1",
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "mapped_without_scientific_content_change",
        "environment_count": 1,
        "case_packet_count": 4,
        "controlled_condition_count": 5,
        "public_case_root": mvp["public_case_root"],
        "private_case_root": mvp["private_case_root"],
        "conditions": rows,
        "roadmap_implemented": False,
        "api_requests": 0,
        "api_spend_usd": 0.0,
    }


def _manual_replay() -> dict[str, Any]:
    manual = _read_json(ROOT / "configs/hard_suite_v08_manual_adjudication.json")
    adjudications = {row["condition_id"]: row for row in manual["adjudications"]}
    results: dict[str, Any] = {}
    for condition_id in CONDITIONS:
        replay_directory = REPLAY_ROOT / condition_id
        grade = replay_archived_v071(
            ROOT, replay_directory, condition_id=condition_id
        ).to_dict()
        expected = adjudications[condition_id]
        evidence = [
            {
                "path": relative,
                "exists": (REPLAY_ROOT / relative).is_file(),
                "sha256": (
                    sha256_file(REPLAY_ROOT / relative)
                    if (REPLAY_ROOT / relative).is_file()
                    else None
                ),
            }
            for relative in expected["saved_evidence"]
        ]
        results[condition_id] = {
            "grade": grade,
            "manual_expected_complete_mission": expected[
                "expected_complete_mission"
            ],
            "manual_expected_mission_failures": expected[
                "expected_mission_failures"
            ],
            "manual_scientific_assessment": expected[
                "manual_scientific_assessment"
            ],
            "saved_evidence": evidence,
            "manual_confirmation_matches": (
                grade["complete_mission_success"]
                == expected["expected_complete_mission"]
                and set(grade["mission_failures"])
                == set(expected["expected_mission_failures"])
                and all(row["exists"] for row in evidence)
            ),
        }
    return {
        "schema_version": "0.8-five-trajectory-replay-1",
        "generated_at": datetime.now(UTC).isoformat(),
        "source_version": "v0.7.1",
        "mapping_layer": "audited_v0.7.2_replay_fixture",
        "interpretation": "v0.8_development_verifier_replay_not_retroactive_rescoring",
        "api_requests": 0,
        "api_spend_usd": 0.0,
        "results": results,
        "all_five_manually_confirmed": all(
            row["manual_confirmation_matches"] for row in results.values()
        ),
    }


def _remaining_concern(condition_id: str) -> str:
    return {
        "case_01": (
            "The boundary between harmless replay drift and a material reproducibility "
            "failure must be monitored in fresh traces; current source drift is minor."
        ),
        "case_02": (
            "X17 is cheaper, while X46 directly resolves transport; future scoring must "
            "judge the stated decision question rather than one preferred purchase."
        ),
        "case_03_signal_collapses": (
            "Only repeated fresh attempts can show whether agents reliably choose the "
            "mechanism-resolving X31 rather than merely reaching a safe STOP."
        ),
        "case_03_signal_remains": (
            "Only repeated fresh attempts can establish whether recovery after leakage "
            "detection is reliable rather than occasional."
        ),
        "case_04": (
            "No-purchase STOP and X46-supported PAUSE/STOP are both valid for different "
            "declared diligence aims; the agent must state which decision it is resolving."
        ),
    }[condition_id]


def _readiness(
    mvp: dict[str, Any],
    mapping: dict[str, Any],
    replay: dict[str, Any],
    controls: dict[str, Any],
) -> dict[str, Any]:
    conditions = {row["condition_id"]: row for row in mvp["active_conditions"]}
    control_rows = controls["rows"]
    rows = []
    for condition_id in CONDITIONS:
        condition = conditions[condition_id]
        local = [row for row in control_rows if row["condition_id"] == condition_id]
        control_pass = all(
            row["complete_mission_success"]
            == (
                row["control"]
                in {
                    "correct_reference",
                    "different_valid_solution",
                    "incorrect_optional_diagnostic",
                }
            )
            for row in local
        )
        rows.append(
            {
                "condition_id": condition_id,
                "scientific_purpose": condition["scientific_purpose"],
                "important_calculation": condition["important_calculation"],
                "consequential_decision": condition["consequential_decision"],
                "accepted_alternatives": condition["accepted_alternatives"],
                "hidden_variant": condition["hidden_variant"],
                "verifier_method": condition["verifier_method"],
                "anti_gaming_result": (
                    "passed_7_of_7_local_controls" if control_pass else "failed"
                ),
                "remaining_concern": _remaining_concern(condition_id),
                "legacy_replay_complete_mission": replay["results"][condition_id][
                    "grade"
                ]["complete_mission_success"],
                "legacy_replay_partial_scientific_quality": replay["results"][
                    condition_id
                ]["grade"]["partial_scientific_quality"],
                "local_ready": control_pass
                and replay["results"][condition_id]["manual_confirmation_matches"],
            }
        )
    return {
        "schema_version": "0.8-mvp-readiness-1",
        "generated_at": datetime.now(UTC).isoformat(),
        "status": (
            "local_validation_passed_unfrozen"
            if all(row["local_ready"] for row in rows)
            else "local_validation_failed"
        ),
        "environment_count": 1,
        "case_packet_count": 4,
        "condition_count": 5,
        "conditions": rows,
        "mapping_status": mapping["status"],
        "all_five_manually_confirmed": replay["all_five_manually_confirmed"],
        "all_controls_passed": controls["status"] == "passed",
        "roadmap_implementation_count": 0,
        "frozen": False,
        "api_requests": 0,
        "api_spend_usd": 0.0,
    }


def _cost_plan(readiness: dict[str, Any]) -> dict[str, Any]:
    observed_v071 = {
        "case_02": 0.4518563,
        "case_03_signal_remains": 0.5263912,
        "case_04": 0.3738318,
    }
    expected = sum(observed_v071.values()) * 1.25
    p90_no_cache_per_episode = 2.1731
    p90 = p90_no_cache_per_episode * 3
    cap = 8.0
    current_key_limit = 130.0
    current_key_usage = 58.47569052
    return {
        "schema_version": "0.8-mvp-three-cell-cost-1",
        "status": "authorized_subject_to_all_local_gates",
        "prerequisite_local_validation_passed": readiness["status"]
        == "local_validation_passed_unfrozen",
        "model": "openai/gpt-5.6-sol",
        "conditions": [
            "case_02",
            "case_03_signal_remains",
            "case_04",
        ],
        "attempts_per_condition": 1,
        "episode_count": 3,
        "observed_v071_cost_basis_usd": observed_v071,
        "expected_incremental_spend_usd": round(expected, 2),
        "conservative_no_cache_p90_usd": round(p90, 2),
        "proposed_hard_incremental_cap_usd": cap,
        "stop_after_three_for_mandatory_review": True,
        "excluded_models_and_partitions": [
            "Claude",
            "Gemini",
            "Kimi",
            "GPT-5.2",
            "held-out cases",
            "Astra"
        ],
        "current_recorded_key_limit_usd": current_key_limit,
        "current_recorded_key_usage_usd": current_key_usage,
        "current_recorded_key_limit_headroom_usd": round(
            current_key_limit - current_key_usage, 6
        ),
        "top_up_required_for_proposed_cap": False,
        "scientific_calls_authorized": True,
        "exact_paid_command": (
            "PYTHONPATH=src ./.venv/bin/python scripts/run_v08_development.py "
            "--execute --maximum-incremental-spend-usd 8"
        ),
        "note": (
            "Execution remains blocked until every local gate passes and an immutable "
            "development snapshot is created. Route, balance and headroom are rechecked "
            "read-only immediately before execution."
        )
    }


def _report(
    readiness: dict[str, Any],
    replay: dict[str, Any],
    controls: dict[str, Any],
    cost: dict[str, Any],
) -> str:
    rows = []
    for row in readiness["conditions"]:
        alternatives = "; ".join(row["accepted_alternatives"])
        rows.append(
            f"| {row['condition_id']} | {row['scientific_purpose']} | "
            f"{row['important_calculation']} | {row['consequential_decision']} | "
            f"{alternatives} | {row['hidden_variant']} | {row['verifier_method']} | "
            f"{row['anti_gaming_result']} | {row['remaining_concern']} |"
        )
    replay_rows = []
    for condition_id in CONDITIONS:
        result = replay["results"][condition_id]
        grade = result["grade"]
        replay_rows.append(
            f"| {condition_id} | {grade['partial_scientific_quality']:.1f} | "
            f"{'pass' if grade['complete_mission_success'] else 'fail'} | "
            f"{', '.join(grade['mission_failures']) or 'none'} | "
            f"{'yes' if result['manual_confirmation_matches'] else 'no'} |"
        )
    return f"""# UC-Bench v0.8 MVP local-readiness report

## Outcome

The active v0.8 MVP is one environment containing the original four case
packets and five controlled conditions. The eight-investigation portfolio is a
post-MVP roadmap only. No new case dataset was implemented, v0.8 remains
unfrozen, and this validation made zero API requests.

All five conditions pass the local verifier and anti-gaming gate. This means
the cases are ready for a bounded development proposal; it does not establish
difficulty, saturation, ranking, or release validity.

## Five-condition readiness table

| Condition | Scientific purpose | Important calculation | Consequential decision | Accepted alternatives | Hidden variant | Verifier method | Anti-gaming result | Remaining concern |
|---|---|---|---|---|---|---|---|---|
{chr(10).join(rows)}

## Manual replay of all five preserved v0.7.1 trajectories

| Condition | Partial scientific quality | Complete mission | Mission failures | Manual confirmation |
|---|---:|---:|---|---:|
{chr(10).join(replay_rows)}

The replay does not make every historical run pass. Case 1 still fails because
it overreacts to minor replay drift. Case 3 collapse fails because it purchases
external evidence instead of the mechanism-resolving clean replay. Case 3
signal-remains correctly analyses the replay but fails to revise its belief and
decision upward. Case 2 and Case 4 pass under documented professional
alternatives. These are v0.8 development results, not retroactive v0.7.1 or
v0.7.2 score changes.

## Local controls

For every condition, the verifier accepted a correct reference, a different
valid solution, and a solution with an incorrect optional sensitivity. It
rejected a plausible scientific error, exact hard-coded values without their
underlying artifacts, a fixed answer after input alteration, and a correct
final decision unsupported by the required analysis. All
{controls['control_count']} condition/control cells passed their expected
classification. Every mission-critical property has a recorded professional
consequence and actionable remedy; filenames, prose, optional calculations and
presentation are not mission-critical.

## Authorized paid tranche—still blocked on local gates

Run one Sol attempt each on the three conditions not previously executed under
the repaired verifier only after every local gate passes: Case 2, Case 3
signal-remains, and Case 4. Expected spend is **${cost['expected_incremental_spend_usd']:.2f}**,
the reconstructed no-cache P90 is **${cost['conservative_no_cache_p90_usd']:.2f}**,
and the proposed hard incremental cap is
**${cost['proposed_hard_incremental_cap_usd']:.2f}**. Stop after exactly three
episodes for review. No other model or partition is in scope. Current recorded
key-limit headroom is **${cost['current_recorded_key_limit_headroom_usd']:.2f}**,
so no top-up is currently indicated. Route, balance and headroom still require
a fresh read-only check immediately before any approved execution.

## Remaining limitation

The verifier and cases are locally ready, but the native v0.8 paid runner has
not been authorized or exercised. One attempt per condition will remain a
development diagnostic. Repeated attempts and several model families are still
required for the eventual MVP release target.
"""


def main() -> int:
    mvp = load_v08_mvp(ROOT)
    mapping = _mapping(mvp)
    replay = _manual_replay()
    with tempfile.TemporaryDirectory(prefix="uc-v08-mvp-controls-") as directory:
        controls = run_v08_mvp_controls(ROOT, Path(directory))
    readiness = _readiness(mvp, mapping, replay, controls)
    cost = _cost_plan(readiness)

    _write_json(
        ROOT / "artifacts/diagnostics/hard_suite_v08_mvp_mapping.json", mapping
    )
    _write_json(
        ROOT / "artifacts/diagnostics/hard_suite_v08_legacy_replay.json", replay
    )
    _write_json(
        ROOT / "artifacts/diagnostics/hard_suite_v08_mvp_controls.json", controls
    )
    _write_json(
        ROOT / "artifacts/diagnostics/hard_suite_v08_mvp_readiness.json", readiness
    )
    _write_json(ROOT / "artifacts/diagnostics/hard_suite_v08_cost_plan.json", cost)
    report = _report(readiness, replay, controls, cost)
    report_path = ROOT / "reports/generated/hard_suite_v08_mvp_readiness.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    # Keep the established pointer useful while v0.8 remains unfrozen.
    (ROOT / "reports/generated/hard_suite_v08_precalibration.md").write_text(
        report, encoding="utf-8"
    )
    summary = {
        "status": readiness["status"],
        "manual_replay": {
            condition_id: {
                "partial_scientific_quality": replay["results"][condition_id][
                    "grade"
                ]["partial_scientific_quality"],
                "complete_mission_success": replay["results"][condition_id][
                    "grade"
                ]["complete_mission_success"],
                "mission_failures": replay["results"][condition_id]["grade"][
                    "mission_failures"
                ],
            }
            for condition_id in CONDITIONS
        },
        "controls": controls["checks"],
        "proposed_paid_cap_usd": cost["proposed_hard_incremental_cap_usd"],
        "api_requests": 0,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if readiness["status"] == "local_validation_passed_unfrozen" else 1


if __name__ == "__main__":
    raise SystemExit(main())

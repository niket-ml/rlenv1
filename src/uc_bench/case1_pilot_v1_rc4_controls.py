"""RC4 construct-validity, representation, mutation, and RC3 replay controls."""

from __future__ import annotations

import copy
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import uc_bench.mmmvp_open_rc17_controls as legacy
from uc_bench.case1_pilot_v1_rc4_artifacts import normalize_typed_calculation_container
from uc_bench.case1_pilot_v1_rc4_environment import RC4Case1Environment
from uc_bench.case1_pilot_v1_rc4_verifier import WEIGHTS, verify_case1_rc4_submission
from uc_bench.errors import ConfigurationError
from uc_bench.mmmvp_open_calculations import CanonicalRow, calculate_metric
from uc_bench.model_runner import _write_json

RC3_RUNS = Path("artifacts/uc_bench_case1_pilot_v1_rc3/science/runs")


def _grade(root: Path, submission: dict[str, Any], workspace: Path) -> dict[str, Any]:
    return verify_case1_rc4_submission(root, workspace, submission).to_dict()


def _statuses(grade: dict[str, Any]) -> dict[str, bool]:
    return {
        str(row["requirement_id"]): bool(row["passed"])
        for row in grade.get("requirements") or []
        if row.get("requirement_id") in WEIGHTS
    }


def _build_reference(
    project_root: Path, run_root: Path, **kwargs: Any
) -> tuple[dict[str, Any], Path]:
    original_environment = legacy.RC17OpenMMMVPEnvironment
    original_verifier = legacy.verify_rc17_case1_submission
    try:
        legacy.RC17OpenMMMVPEnvironment = RC4Case1Environment
        legacy.verify_rc17_case1_submission = verify_case1_rc4_submission
        return legacy.build_reference(project_root, run_root, **kwargs)
    finally:
        legacy.RC17OpenMMMVPEnvironment = original_environment
        legacy.verify_rc17_case1_submission = original_verifier


def _run_prior_controls(project_root: Path, output_root: Path) -> dict[str, Any]:
    original_environment = legacy.RC17OpenMMMVPEnvironment
    original_verifier = legacy.verify_rc17_case1_submission
    try:
        legacy.RC17OpenMMMVPEnvironment = RC4Case1Environment
        legacy.verify_rc17_case1_submission = verify_case1_rc4_submission
        return legacy.run_controls(project_root, output_root)
    finally:
        legacy.RC17OpenMMMVPEnvironment = original_environment
        legacy.verify_rc17_case1_submission = original_verifier


def _replace_final(
    submission: dict[str, Any], workspace: Path, final: dict[str, Any]
) -> None:
    legacy._replace_final(submission, workspace, final)  # noqa: SLF001


def _sync_output(workspace: Path, final: dict[str, Any]) -> None:
    legacy._sync_output(workspace, final)  # noqa: SLF001


def _copy(
    submission: dict[str, Any], workspace: Path, target: Path
) -> tuple[dict[str, Any], Path]:
    return legacy._copy_episode(submission, workspace, target), target  # noqa: SLF001


def _changed(reference: dict[str, Any], candidate: dict[str, Any]) -> list[str]:
    before, after = _statuses(reference), _statuses(candidate)
    return [key for key in WEIGHTS if before.get(key) != after.get(key)]


def _mutate_metric(
    submission: dict[str, Any], workspace: Path, property_name: str
) -> None:
    final = copy.deepcopy(submission["final_submission"])
    criterion = next(
        row
        for row in submission["validation_plan"]["decision_criteria"]
        if row["property"] == property_name
    )
    row = next(
        item
        for item in final["calculations"]
        if item["calculation_id"] == criterion["calculation_id"]
    )
    row["reported_value"] = float(row["reported_value"]) + 0.314159
    _sync_output(workspace, final)
    _replace_final(submission, workspace, final)


def _split_equivalence(
    project_root: Path,
    reference: dict[str, Any],
    workspace: Path,
    root: Path,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for label in ("VALIDATION", "PRIMARY", "prospective_primary_set"):
        copied, target = _copy(reference, workspace, root / label.lower())
        table = target / "work/primary_analysis.csv"
        with table.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        for row in rows:
            row["partition"] = label
        with table.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        final = copy.deepcopy(copied["final_submission"])
        for row in final["calculations"]:
            if row["role"] == "PRIMARY":
                row["cohort"]["split_values"] = [label]
        _replace_final(copied, target, final)
        grade = _grade(project_root, copied, target)
        result[label] = {
            "score": grade["partial_scientific_quality"],
            "mission": grade["complete_mission_success"],
        }
    return result


def _container_equivalence(
    project_root: Path,
    reference: dict[str, Any],
    workspace: Path,
    root: Path,
) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for form in ("list", "object"):
        copied, target = _copy(reference, workspace, root / form)
        final = copied["final_submission"]
        rows = [
            {
                "calculation_id": row["calculation_id"],
                "reported_value": row["reported_value"],
            }
            for row in final["calculations"]
        ]
        value: Any = rows if form == "list" else {
            row["calculation_id"]: row for row in rows
        }
        (target / "work/primary_results.json").write_text(
            json.dumps({"typed_calculations": value}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        grade = _grade(project_root, copied, target)
        results[form] = {
            "score": grade["partial_scientific_quality"],
            "mission": grade["complete_mission_success"],
        }
    malformed = normalize_typed_calculation_container(
        {"A": {"calculation_id": "B", "reported_value": 0.1}}
    )
    results["malformed_key_mismatch"] = {"faults": malformed[1]}
    return results


def _single_fault_mutations(
    project_root: Path,
    reference: dict[str, Any],
    workspace: Path,
    root: Path,
) -> list[dict[str, Any]]:
    baseline = _grade(project_root, reference, workspace)
    cases: list[tuple[str, list[str], Any]] = []

    def p1(submission: dict[str, Any], _workspace: Path) -> None:
        commit = next(
            index
            for index, row in enumerate(submission["event_log"])
            if row["event"] == "commit_validation_plan"
        )
        reveal = next(
            index
            for index, row in enumerate(submission["event_log"])
            if row["event"] == "reveal_validation"
        )
        submission["event_log"][commit], submission["event_log"][reveal] = (
            submission["event_log"][reveal],
            submission["event_log"][commit],
        )

    cases.append(("prospective_design_and_integrity", ["prospective_design_and_integrity"], p1))

    def p2(submission: dict[str, Any], target: Path) -> None:
        final = copy.deepcopy(submission["final_submission"])
        target_row = next(
            row
            for row in final["artifact_manifest"]
            if row["artifact_id"] == "OUTPUT_RESULTS"
        )
        target_row["role"] = "OTHER"
        _replace_final(submission, target, final)

    cases.append(
        (
            "saved_artifact_chain",
            [
                "saved_artifact_chain",
                "discrimination_and_uncertainty",
                "probability_and_calibration",
                "threshold_utility",
                "context_robustness",
                "decision_relevant_followup",
                "bounded_decision_and_claims",
            ],
            p2,
        )
    )

    def p3(submission: dict[str, Any], target: Path) -> None:
        final = copy.deepcopy(submission["final_submission"])
        for row in final["calculations"]:
            if row["role"] == "PRIMARY":
                row["cohort"]["included_row_count"] -= 1
        _replace_final(submission, target, final)

    cases.append(
        (
            "committed_entity_and_dependence_analysis",
            [
                "committed_entity_and_dependence_analysis",
                "discrimination_and_uncertainty",
                "probability_and_calibration",
                "threshold_utility",
                "context_robustness",
                "decision_relevant_followup",
                "bounded_decision_and_claims",
            ],
            p3,
        )
    )
    for property_name, requirement in (
        ("DISCRIMINATION", "discrimination_and_uncertainty"),
        ("CALIBRATION", "probability_and_calibration"),
        ("THRESHOLD_UTILITY", "threshold_utility"),
        ("CONTEXT_ROBUSTNESS", "context_robustness"),
    ):
        cases.append(
            (
                requirement,
                [requirement, "bounded_decision_and_claims"],
                lambda submission, target, prop=property_name: _mutate_metric(
                    submission, target, prop
                ),
            )
        )

    def p8(submission: dict[str, Any], target: Path) -> None:
        final = copy.deepcopy(submission["final_submission"])
        final["resource_assessment"]["question_type"] = "PIPELINE_REPRODUCIBILITY"
        _replace_final(submission, target, final)

    cases.append(
        (
            "decision_relevant_followup",
            ["decision_relevant_followup", "bounded_decision_and_claims"],
            p8,
        )
    )

    def p9(submission: dict[str, Any], target: Path) -> None:
        final = copy.deepcopy(submission["final_submission"])
        for row in final["belief_updates"]:
            row["after"] = 0.99 if row["hypothesis_id"] == "H_LIMIT" else 0.01
        _replace_final(submission, target, final)

    cases.append(("belief_revision", ["belief_revision"], p9))

    def p10(submission: dict[str, Any], target: Path) -> None:
        final = copy.deepcopy(submission["final_submission"])
        final["decision"].update(
            {"development_stage": "STOPPED", "disposition": "CONTINUE", "use_scope": "NO_USE"}
        )
        _replace_final(submission, target, final)

    cases.append(("bounded_decision_and_claims", ["bounded_decision_and_claims"], p10))

    rows: list[dict[str, Any]] = []
    for index, (name, expected, mutate) in enumerate(cases):
        copied, target = _copy(reference, workspace, root / f"{index:02d}_{name}")
        mutate(copied, target)
        grade = _grade(project_root, copied, target)
        changed = _changed(baseline, grade)
        rows.append(
            {
                "mutation": name,
                "single_element_changed": True,
                "expected_changed_properties": expected,
                "observed_changed_properties": changed,
                "passed": changed == expected,
            }
        )
    return rows


def replay_rc3_submissions(
    project_root: Path, expected: dict[str, Any]
) -> dict[str, Any]:
    root = project_root.resolve()
    rows: list[dict[str, Any]] = []
    for path in sorted((root / RC3_RUNS).glob("*/run_summary.json")):
        archived = json.loads(path.read_text(encoding="utf-8"))
        model = str(archived["model_id"])
        workspace = path.parent / "workspace"
        submitted = bool((archived.get("submission") or {}).get("state", {}).get(
            "completion_accepted"
        ))
        diagnostic = (
            _grade(root, archived["submission"], workspace) if submitted else None
        )
        expected_row = expected["models"][model]
        actual = {
            "submitted": submitted,
            "official_rc3_score_preserved": archived.get("partial_scientific_quality"),
            "diagnostic_rc4_score": (
                diagnostic["partial_scientific_quality"] if diagnostic else None
            ),
            "diagnostic_rc4_properties": _statuses(diagnostic or {}),
        }
        rows.append(
            {
                "model_id": model,
                **actual,
                "expected": expected_row,
                "passed": actual == expected_row,
            }
        )
    opus_workspace = root / RC3_RUNS / (
        "case1-rc3-01-anthropic-claude-opus-4.1-attempt-0/workspace"
    )
    with (opus_workspace / "work/entity_predictions_with_outcomes.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        opus_rows = list(csv.DictReader(handle))
    canonical = [
        CanonicalRow(
            entity_id=row["entity_id"],
            source_record_ids=(row["entity_id"],),
            prediction=float(row["predicted_probability"]),
            outcome=int(row["week6_response"]),
            split="all",
            contexts=(row["site"],),
        )
        for row in opus_rows
    ]
    opus_final = json.loads(
        (opus_workspace / "work/final_submission.json").read_text(encoding="utf-8")
    )
    opus_calibration = next(
        row for row in opus_final["calculations"] if row["metric"] == "CALIBRATION_ERROR"
    )
    recomputed_calibration = calculate_metric(
        canonical,
        "CALIBRATION_ERROR",
        "EMPIRICAL",
        {"bin_count": int(opus_calibration["parameters"]["bin_count"])},
    )
    opus_diagnostic = {
        "official_scientific_score": None,
        "headline_eligible": False,
        "preserved_final_work_file": "work/final_submission.json",
        "reported_calibration": opus_calibration["reported_value"],
        "independently_recomputed_calibration": recomputed_calibration,
        "calibration_matches": abs(
            float(opus_calibration["reported_value"]) - recomputed_calibration
        )
        <= 0.002,
        "source_split_provenance_defects": {
            "split_column_mapped_to_entity_id": next(
                row
                for row in opus_final["artifact_manifest"]
                if row["artifact_id"] == "A001"
            )["column_map"]["split"]
            == "entity_id",
            "source_record_ids_mapped_to_entity_id": next(
                row
                for row in opus_final["artifact_manifest"]
                if row["artifact_id"] == "A001"
            )["column_map"]["source_record_ids"]
            == "entity_id",
        },
        "note": "Saved-work diagnostic only; no submission was manufactured and no score assigned.",
    }
    return {
        "schema_version": "uc-bench-case1-pilot-v1-rc4-rc3-replay-1",
        "passed": len(rows) == 5 and all(row["passed"] for row in rows),
        "official_rc3_results_modified": False,
        "rows": rows,
        "opus_unsubmitted_saved_work_diagnostic": opus_diagnostic,
    }


def run_rc4_controls(project_root: Path, output_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    prior = _run_prior_controls(root, output_root / "prior_controls")
    reference, workspace = _build_reference(root, output_root / "reference")
    reference_grade = _grade(root, reference, workspace)
    alternatives = [
        _build_reference(root, output_root / f"alternative_{name}", **kwargs)
        for name, kwargs in (
            ("median", {"aggregation": "MEDIAN"}),
            ("clustered", {"aggregation": "NONE"}),
            (
                "alias",
                {
                    "probability_metric": "LOG_LOSS",
                    "utility_metric": "THRESHOLD_EXPECTED_UTILITY",
                    "context_metric": "SITE_WEIGHTED_ROC_AUC",
                },
            ),
        )
    ]
    alternative_grades = [_grade(root, *episode) for episode in alternatives]
    split = _split_equivalence(
        root, reference, workspace, output_root / "split_equivalence"
    )
    containers = _container_equivalence(
        root, reference, workspace, output_root / "container_equivalence"
    )
    mutations = _single_fault_mutations(
        root, reference, workspace, output_root / "single_fault_mutations"
    )
    x24_reference, x24_workspace = _build_reference(
        root, output_root / "x24_dependency_reference", resource="X24"
    )
    x24_mutated, x24_target = _copy(
        x24_reference,
        x24_workspace,
        output_root / "x24_dependency_entity_fault",
    )
    x24_final = copy.deepcopy(x24_mutated["final_submission"])
    for row in x24_final["calculations"]:
        if row["role"] == "PRIMARY":
            row["cohort"]["included_row_count"] -= 1
    _replace_final(x24_mutated, x24_target, x24_final)
    x24_dependency_grade = _grade(root, x24_mutated, x24_target)
    x24_dependency_status = _statuses(x24_dependency_grade)
    resource_specific_dependency = {
        "entity_property_failed": not x24_dependency_status[
            "committed_entity_and_dependence_analysis"
        ],
        "endpoint_followup_preserved": x24_dependency_status[
            "decision_relevant_followup"
        ],
        "bounded_decision_failed": not x24_dependency_status[
            "bounded_decision_and_claims"
        ],
    }
    malformed_results: list[dict[str, Any]] = []
    for payload in (b"{", b"\xff\xfe", b'{"typed_calculations":{"A":{"calculation_id":"B"}}}'):
        copied, target = _copy(
            reference, workspace, output_root / f"malformed_{len(malformed_results)}"
        )
        (target / "work/primary_results.json").write_bytes(payload)
        try:
            grade = _grade(root, copied, target)
            malformed_results.append({"crashed": False, "grade": grade})
        except Exception as exc:  # pragma: no cover - a regression this gate exposes
            malformed_results.append({"crashed": True, "type": type(exc).__name__})
    prior_grades = [row.get("grade") for row in prior["controls"] if row.get("grade")]
    value = {
        "schema_version": "uc-bench-case1-pilot-v1-rc4-controls-1",
        "passed": all(
            (
                reference_grade["complete_mission_success"],
                reference_grade["partial_scientific_quality"] == 100,
                all(row["complete_mission_success"] for row in alternative_grades),
                all(row["mission"] for row in split.values()),
                containers["list"]["mission"],
                containers["object"]["mission"],
                containers["malformed_key_mismatch"]["faults"]
                == ["calculation_id_key_mismatch"],
                all(row["passed"] for row in mutations),
                all(resource_specific_dependency.values()),
                all(not row["crashed"] for row in malformed_results),
                len(prior["controls"]) == 36,
                all(
                    (grade.get("diagnostics") or {}).get("prose_scored") is False
                    for grade in prior_grades
                ),
            )
        ),
        "reference": reference_grade,
        "alternative_workflows": alternative_grades,
        "split_label_equivalence": split,
        "calculation_container_equivalence": containers,
        "single_fault_mutations": mutations,
        "resource_specific_dependency_control": resource_specific_dependency,
        "malformed_artifacts": malformed_results,
        "prior_control_count": len(prior["controls"]),
        "prior_controls_path": (output_root / "prior_controls/control_results.json").as_posix(),
        "public_resource_summary_schema": "case1-resource-summary-1",
        "returned_resource_package_schema": "case1-resource-return-1",
    }
    _write_json(output_root / "control_results.json", value, secret="")
    if not value["passed"]:
        raise ConfigurationError("RC4 scientific controls did not pass")
    return value


def preserved_rc3_hashes(project_root: Path) -> dict[str, str]:
    root = project_root.resolve()
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((root / RC3_RUNS.parent.parent).rglob("*"))
        if path.is_file()
    }


__all__ = ["preserved_rc3_hashes", "replay_rc3_submissions", "run_rc4_controls"]

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pytest

from uc_bench.hard_suite_v06 import (
    ALL_ARTIFACTS,
    V06Package,
    grade_v06,
    load_v06_scenario,
    run_reference_v06_episode,
)
from uc_bench.v063_grader import (
    grade_v063,
    grader_infrastructure_failed,
    sanitize_artifact,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
V062_RUN = (
    PROJECT_ROOT
    / "build/hard_suite_v06_runs/"
    "hard62-gpt-5.6-sol-dev6_clean_progression-0-20260908T194210Z"
)


@pytest.fixture
def reference_package(tmp_path: Path) -> V06Package:
    package, _environment, _grade = run_reference_v06_episode(
        PROJECT_ROOT,
        "dev6_clean_progression",
        output_root=tmp_path,
    )
    return package


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _assert_total_grade(package: V06Package) -> None:
    grade = grade_v063(
        PROJECT_ROOT,
        package,
        selected_resource="none",
        commitment_immutable=True,
        completion_accepted=True,
    )
    assert grader_infrastructure_failed(grade) is False
    assert set(grade.artifact_scores) == {
        f"A{index:02d}" for index in range(1, 11)
    }
    assert all(0 <= score <= 100 for score in grade.artifact_scores.values())


def test_valid_reference_score_is_identical_to_frozen_v06(
    reference_package: V06Package,
) -> None:
    frozen = grade_v06(
        PROJECT_ROOT,
        reference_package,
        selected_resource="none",
        commitment_immutable=True,
        completion_accepted=True,
    )
    total = grade_v063(
        PROJECT_ROOT,
        reference_package,
        selected_resource="none",
        commitment_immutable=True,
        completion_accepted=True,
    )
    assert total.to_dict() == frozen.to_dict()


def test_invalid_inventory_count_loses_one_property_not_the_episode(
    reference_package: V06Package,
) -> None:
    path = reference_package.workspace_root / ALL_ARTIFACTS[0]
    rows = _read_csv(path)
    rows[0]["patient_count"] = "unresolved"
    _write_csv(path, rows)
    grade = grade_v063(
        PROJECT_ROOT,
        reference_package,
        selected_resource="none",
        commitment_immutable=True,
        completion_accepted=True,
    )
    assert grade.artifact_scores["A01"] == 80
    assert 0 < grade.coverage_adjusted_scientific_score < 100
    assert grader_infrastructure_failed(grade) is False
    assert any(
        row.get("tag") == "semantic_type_error"
        and row.get("field") == "rows[0].patient_count"
        for row in grade.process_annotations
    )


@pytest.mark.parametrize("bad", ["unresolved", "", "nan", "inf", "{}", "[]"])
@pytest.mark.parametrize(
    ("artifact_index", "fields"),
    [
        (0, ("row_count", "patient_count")),
        (
            5,
            (
                "reference_probability",
                "reproduced_probability",
                "absolute_error",
            ),
        ),
    ],
)
def test_all_agent_numeric_csv_fields_are_total(
    reference_package: V06Package,
    artifact_index: int,
    fields: tuple[str, ...],
    bad: str,
) -> None:
    path = reference_package.workspace_root / ALL_ARTIFACTS[artifact_index]
    rows = _read_csv(path)
    for field in fields:
        rows[0][field] = bad
    _write_csv(path, rows)
    _assert_total_grade(reference_package)


@pytest.mark.parametrize("bad", [None, 0, False, "wrong-container", {}])
@pytest.mark.parametrize(
    ("artifact_index", "field"),
    [
        (1, "findings"),
        (1, "evidence_refs"),
        (3, "label_sources"),
        (3, "evidence_refs"),
        (4, "steps"),
        (4, "evidence_refs"),
        (6, "metric_families"),
        (6, "live_hypotheses"),
        (6, "analysis_artifact_paths"),
        (6, "evidence_refs"),
        (7, "evidence_refs"),
        (8, "resource_comparisons"),
        (8, "live_hypotheses"),
        (8, "evidence_refs"),
        (9, "limitations"),
        (9, "supported_claims"),
        (9, "evidence_refs"),
    ],
)
def test_all_agent_list_fields_are_total(
    reference_package: V06Package,
    artifact_index: int,
    field: str,
    bad: Any,
) -> None:
    path = reference_package.workspace_root / ALL_ARTIFACTS[artifact_index]
    value = json.loads(path.read_text())
    value[field] = bad
    _write_json(path, value)
    _assert_total_grade(reference_package)


@pytest.mark.parametrize("bad", [None, 0, False, "wrong-container", []])
@pytest.mark.parametrize(
    ("artifact_index", "field"),
    [
        (6, "decision_rule"),
        (7, "metrics"),
        (7, "claim_statuses"),
        (9, "belief_update"),
        (9, "smallest_next_action"),
        (9, "claim_statuses"),
    ],
)
def test_all_agent_mapping_fields_are_total(
    reference_package: V06Package,
    artifact_index: int,
    field: str,
    bad: Any,
) -> None:
    path = reference_package.workspace_root / ALL_ARTIFACTS[artifact_index]
    value = json.loads(path.read_text())
    value[field] = bad
    _write_json(path, value)
    _assert_total_grade(reference_package)


@pytest.mark.parametrize("artifact_index", [1, 3, 4, 6, 7, 8, 9])
@pytest.mark.parametrize("bad", [None, 0, False, "scalar", []])
def test_every_json_artifact_top_level_type_is_total(
    reference_package: V06Package,
    artifact_index: int,
    bad: Any,
) -> None:
    path = reference_package.workspace_root / ALL_ARTIFACTS[artifact_index]
    _write_json(path, bad)
    _assert_total_grade(reference_package)


def test_nested_claim_evidence_type_is_total(reference_package: V06Package) -> None:
    path = reference_package.workspace_root / ALL_ARTIFACTS[9]
    value = json.loads(path.read_text())
    value["supported_claims"][0]["evidence_refs"] = 7
    _write_json(path, value)
    _assert_total_grade(reference_package)


@pytest.mark.parametrize("artifact_index", [0, 2, 5])
@pytest.mark.parametrize("bad", [None, 0, False, "scalar", []])
def test_every_csv_row_type_is_sanitized(artifact_index: int, bad: Any) -> None:
    relative = ALL_ARTIFACTS[artifact_index]
    issues: list[dict[str, Any]] = []
    safe = sanitize_artifact(relative, [{"first": "valid"}, bad], issues)
    assert safe[1] == {}
    assert any(issue["field"] == "rows[1]" for issue in issues)


def test_captured_v062_submission_now_grades_with_partial_credit() -> None:
    workspace = V062_RUN / "hard6-dev6_clean_progression"
    sealed = V062_RUN / "hard6-dev6_clean_progression-sealed"
    start = json.loads((workspace / "START_STATE.json").read_text())
    package = V06Package(
        scenario_id="dev6_clean_progression",
        partition="development",
        workspace_root=workspace,
        sealed_root=sealed,
        package_digest=start["package_digest"],
        sealed_digest="preserved-orphan",
        private_scenario=load_v06_scenario(
            PROJECT_ROOT, "dev6_clean_progression", partition="development"
        ),
        schema_root=workspace / "schemas",
    )
    grade = grade_v063(
        PROJECT_ROOT,
        package,
        selected_resource="none",
        commitment_immutable=True,
        completion_accepted=False,
    )
    assert grade.artifact_scores["A01"] == 80
    assert grade.coverage_adjusted_scientific_score == 84.626984
    assert grader_infrastructure_failed(grade) is False

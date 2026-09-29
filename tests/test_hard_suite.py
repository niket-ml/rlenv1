from __future__ import annotations

import json
from pathlib import Path

import pytest

from uc_bench.errors import ContractError, InvalidTransitionError
from uc_bench.hard_suite import (
    HardSuiteBuilder,
    HardSuiteEnvironment,
    grade_hard_suite,
    iter_hard_suite_ladder_variants,
    iter_hard_suite_variants,
    reference_commitment,
    solve_hard_suite,
    validate_hard_suite_config,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def test_hard_suite_has_separate_predeclared_pairs() -> None:
    validation = validate_hard_suite_config(PROJECT_ROOT)
    assert validation["family_count"] == 5
    assert validation["development_variant_count"] == 10
    assert validation["heldout_variant_count"] == 10
    assert validation["equal_family_weights"] is True


def test_breaking_point_ladders_are_materialized_without_model_answers() -> None:
    variants = iter_hard_suite_ladder_variants(PROJECT_ROOT)
    assert len(variants) == 20
    assert len({row["ladder_id"] for row in variants}) == 5
    assert all(row["pair_role"] == "breaking_point" for row in variants)


@pytest.mark.parametrize(
    ("partition", "expected_count"),
    [("development", 10), ("heldout", 10)],
)
def test_reference_scores_every_variant_at_100(
    tmp_path: Path, partition: str, expected_count: int
) -> None:
    variants = iter_hard_suite_variants(PROJECT_ROOT, partition=partition)
    assert len(variants) == expected_count
    for variant in variants:
        package = HardSuiteBuilder(PROJECT_ROOT).build(
            variant["variant_id"], output_root=tmp_path, partition=partition
        )
        environment = HardSuiteEnvironment(package)
        commitment = reference_commitment(package.workspace_root, variant)
        _write_json(package.workspace_root / "submission" / "commitment.json", commitment)
        environment.commit_plan()
        environment.reveal_evidence()
        submission = solve_hard_suite(package.workspace_root, variant)
        _write_json(package.workspace_root / "submission" / "final_submission.json", submission)
        environment.submit_hard_suite()
        grade = grade_hard_suite(
            package.workspace_root,
            variant,
            environment.commitment,
            environment.submission,
            commitment_immutable=environment.commitment_immutable,
        )
        assert grade.score == 100.0


def test_commitment_and_reveal_are_irreversible(tmp_path: Path) -> None:
    variant = iter_hard_suite_variants(PROJECT_ROOT)[0]
    package = HardSuiteBuilder(PROJECT_ROOT).build(variant["variant_id"], output_root=tmp_path)
    environment = HardSuiteEnvironment(package)
    commitment = reference_commitment(package.workspace_root, variant)
    commitment_path = package.workspace_root / "submission" / "commitment.json"
    _write_json(commitment_path, commitment)
    with pytest.raises(InvalidTransitionError):
        environment.reveal_evidence()
    environment.commit_plan()
    with pytest.raises(InvalidTransitionError):
        environment.commit_plan()
    environment.reveal_evidence()
    with pytest.raises(InvalidTransitionError):
        environment.reveal_evidence()
    commitment["pre_reveal_decision"] = "advance"
    _write_json(commitment_path, commitment)
    submission = solve_hard_suite(package.workspace_root, variant)
    _write_json(package.workspace_root / "submission" / "final_submission.json", submission)
    with pytest.raises(ContractError, match="changed after reveal"):
        environment.submit_hard_suite()


def test_sealed_evidence_is_outside_public_workspace(tmp_path: Path) -> None:
    variant = iter_hard_suite_variants(PROJECT_ROOT)[0]
    package = HardSuiteBuilder(PROJECT_ROOT).build(variant["variant_id"], output_root=tmp_path)
    assert package.workspace_root not in package.sealed_root.parents
    assert not (package.workspace_root / "evidence").exists()
    assert (package.sealed_root / "factorial_predictions.csv").is_file()

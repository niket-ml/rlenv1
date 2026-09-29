from __future__ import annotations

import json
from pathlib import Path

import pytest

from uc_bench.errors import ConfigurationError, ContractError
from uc_bench.hard_suite_v04 import (
    V04Builder,
    V04Environment,
    compute_v04_metrics,
    grade_v04,
    iter_v04_variants,
    reference_v04_commitment,
    solve_v04,
    validate_v04_config,
)
from uc_bench.hard_suite_v04_runner import V04RunConfig
from uc_bench.v04_ladders import build_v04_ladder_rows

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


@pytest.mark.parametrize("partition", ["development", "heldout"])
def test_v04_reference_scores_100_and_pairs_cross_decisions(
    tmp_path: Path, partition: str
) -> None:
    decisions: dict[str, dict[str, str]] = {}
    for variant in iter_v04_variants(PROJECT_ROOT, partition=partition):
        package = V04Builder(PROJECT_ROOT).build(
            variant["variant_id"], output_root=tmp_path, partition=partition
        )
        environment = V04Environment(package)
        commitment = reference_v04_commitment(package.workspace_root, variant, PROJECT_ROOT)
        _write(package.workspace_root / "submission" / "commitment.json", commitment)
        environment.commit_plan()
        environment.reveal_evidence()
        submission = solve_v04(PROJECT_ROOT, package.workspace_root, variant)
        _write(package.workspace_root / "submission" / "final_submission.json", submission)
        environment.submit_hard_suite()
        grade = grade_v04(
            PROJECT_ROOT,
            package.workspace_root,
            variant,
            environment.commitment,
            environment.submission,
            commitment_immutable=environment.commitment_immutable,
        )
        assert grade.score == 100.0
        assert grade.components["quantitative_statistical_reasoning"] == 100.0
        decisions.setdefault(str(variant["family_id"]), {})[
            str(variant["pair_role"])
        ] = submission["decision"]
    for family_id, pair in decisions.items():
        assert pair["control"] != pair["treated"], family_id


def test_v04_contract_is_frozen_and_quantitatively_weighted() -> None:
    result = validate_v04_config(PROJECT_ROOT)
    assert result["development_variant_count"] == 10
    assert result["heldout_variant_count"] == 10
    assert result["quantitative_weight"] == 0.30
    assert result["heldout_frozen_before_astra"] is True
    assert result["maximum_turns"] == 40


def test_v04_unavailable_resource_rejected_before_hash(tmp_path: Path) -> None:
    variant = next(
        row for row in iter_v04_variants(PROJECT_ROOT) if row["pair_role"] == "control"
    )
    package = V04Builder(PROJECT_ROOT).build(variant["variant_id"], output_root=tmp_path)
    environment = V04Environment(package)
    commitment = reference_v04_commitment(package.workspace_root, variant, PROJECT_ROOT)
    commitment["requested_resource_id"] = variant["correct_resource_id"]
    _write(package.workspace_root / "submission" / "commitment.json", commitment)
    with pytest.raises(ContractError, match="unavailable"):
        environment.commit_plan()
    assert environment.commitment is None


def test_v04_metrics_are_deterministic_and_commitment_is_immutable(tmp_path: Path) -> None:
    variant = iter_v04_variants(PROJECT_ROOT)[0]
    package = V04Builder(PROJECT_ROOT).build(variant["variant_id"], output_root=tmp_path)
    environment = V04Environment(package)
    commitment = reference_v04_commitment(package.workspace_root, variant, PROJECT_ROOT)
    commitment_path = package.workspace_root / "submission" / "commitment.json"
    _write(commitment_path, commitment)
    environment.commit_plan()
    environment.reveal_evidence()
    assert compute_v04_metrics(package.workspace_root) == compute_v04_metrics(
        package.workspace_root
    )
    commitment["requested_resource_id"] = "R1"
    _write(commitment_path, commitment)
    submission = solve_v04(PROJECT_ROOT, package.workspace_root, variant)
    _write(package.workspace_root / "submission" / "final_submission.json", submission)
    with pytest.raises(ContractError, match="changed after reveal"):
        environment.submit_hard_suite()


def test_v04_every_ladder_has_a_decision_transition() -> None:
    rows = build_v04_ladder_rows(PROJECT_ROOT)
    ladder_ids = {str(row["ladder_id"]) for row in rows}
    assert len(ladder_ids) == 5
    for ladder_id in ladder_ids:
        decisions = {
            str(row["reference_decision"])
            for row in rows
            if row["ladder_id"] == ladder_id
        }
        assert len(decisions) >= 2, ladder_id


def test_v04_runner_budget_validation() -> None:
    valid = V04RunConfig("model", "run", "variant", seed=1)
    assert valid.maximum_turns == 40
    with pytest.raises(ConfigurationError):
        V04RunConfig("model", "run", "variant", seed=1, maximum_turns=0)

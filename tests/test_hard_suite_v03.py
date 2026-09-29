from __future__ import annotations

import json
from pathlib import Path

import pytest

from uc_bench.errors import ConfigurationError, ContractError
from uc_bench.hard_suite_v03 import (
    V03Builder,
    V03Environment,
    grade_v03,
    iter_v03_variants,
    reference_v03_commitment,
    solve_v03,
    validate_v03_config,
)
from uc_bench.hard_suite_v03_runner import V03RunConfig

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def test_v03_has_separate_pairs_and_relaxed_horizon() -> None:
    result = validate_v03_config(PROJECT_ROOT)
    assert result["development_variant_count"] == 10
    assert result["heldout_variant_count"] == 10
    assert result["resource_options_per_task"] == 3
    assert result["relaxed_turn_budget"] == 32


@pytest.mark.parametrize("partition", ["development", "heldout"])
def test_v03_reference_scores_100(tmp_path: Path, partition: str) -> None:
    for variant in iter_v03_variants(PROJECT_ROOT, partition=partition):
        package = V03Builder(PROJECT_ROOT).build(
            variant["variant_id"], output_root=tmp_path, partition=partition
        )
        environment = V03Environment(package)
        commitment = reference_v03_commitment(package.workspace_root, variant)
        _write(package.workspace_root / "submission" / "commitment.json", commitment)
        environment.commit_plan()
        environment.reveal_evidence()
        submission = solve_v03(package.workspace_root, variant)
        _write(package.workspace_root / "submission" / "final_submission.json", submission)
        environment.submit_hard_suite()
        grade = grade_v03(
            package.workspace_root,
            variant,
            environment.commitment,
            environment.submission,
            commitment_immutable=True,
        )
        assert grade.score == 100.0
        assert grade.resource_selection_correct is True


def test_unavailable_resource_is_rejected_before_commitment(tmp_path: Path) -> None:
    variant = next(row for row in iter_v03_variants(PROJECT_ROOT) if row["pair_role"] == "control")
    package = V03Builder(PROJECT_ROOT).build(variant["variant_id"], output_root=tmp_path)
    environment = V03Environment(package)
    commitment = reference_v03_commitment(package.workspace_root, variant)
    commitment["requested_resource_id"] = variant["correct_resource_id"]
    _write(package.workspace_root / "submission" / "commitment.json", commitment)
    with pytest.raises(ContractError, match="unavailable"):
        environment.commit_plan()
    assert environment.commitment is None


def test_v03_runner_defaults_do_not_create_horizon_floor() -> None:
    config = V03RunConfig(
        model_id="provider/model",
        run_id="run",
        variant_id="dev3_identity_control",
        seed=1,
    )
    assert config.maximum_turns == 32
    assert config.maximum_total_completion_tokens == 40_000
    assert config.minimum_request_interval_seconds == 3.25


def test_v03_runner_rejects_negative_request_interval() -> None:
    with pytest.raises(ConfigurationError, match="minimum request interval"):
        V03RunConfig(
            model_id="provider/model",
            run_id="run",
            variant_id="dev3_identity_control",
            seed=1,
            minimum_request_interval_seconds=-0.01,
        )

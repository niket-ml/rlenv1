from __future__ import annotations

import json
from pathlib import Path

import pytest

from uc_bench.errors import ContractError
from uc_bench.hard_suite_v05 import _write_json
from uc_bench.hard_suite_v06 import (
    ALL_ARTIFACTS,
    V06Builder,
    V06Environment,
    grade_v06,
    iter_v06_scenarios,
    reference_v06_precommit,
    run_reference_v06_episode,
    validate_v06_config,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_v06_has_disjoint_six_state_partitions_and_ten_artifacts() -> None:
    status = validate_v06_config(PROJECT_ROOT)
    assert status["artifact_count"] == 10
    assert status["development_scenario_count"] == 6
    assert status["heldout_scenario_count"] == 6
    development = {row["scenario_id"] for row in iter_v06_scenarios(PROJECT_ROOT)}
    heldout = {row["scenario_id"] for row in iter_v06_scenarios(PROJECT_ROOT, partition="heldout")}
    assert development.isdisjoint(heldout)


def test_reference_episode_scores_every_artifact_independently(tmp_path: Path) -> None:
    scenario_id = iter_v06_scenarios(PROJECT_ROOT)[0]["scenario_id"]
    package, environment, grade = run_reference_v06_episode(
        PROJECT_ROOT, scenario_id, output_root=tmp_path
    )
    assert environment.phase == "submitted"
    assert grade.coverage_adjusted_scientific_score >= 90
    assert set(grade.artifact_scores) == {f"A{index:02d}" for index in range(1, 11)}
    assert set(grade.artifact_states.values()) == {"valid"}
    assert (package.workspace_root / "COMMITMENT_RECORD.json").is_file()


def test_all_heldout_start_states_build_with_private_labels_sealed(tmp_path: Path) -> None:
    for scenario in iter_v06_scenarios(PROJECT_ROOT, partition="heldout"):
        package = V06Builder(PROJECT_ROOT).build(
            scenario["scenario_id"], output_root=tmp_path, partition="heldout"
        )
        assert (package.workspace_root / "TASK.md").is_file()
        assert not (package.workspace_root / "revealed").exists()
        assert (package.sealed_root / "validation/external_outcomes.csv").is_file()


def test_missing_artifact_reduces_coverage_without_erasing_completed_quality(
    tmp_path: Path,
) -> None:
    scenario_id = iter_v06_scenarios(PROJECT_ROOT)[0]["scenario_id"]
    package, environment, complete = run_reference_v06_episode(
        PROJECT_ROOT, scenario_id, output_root=tmp_path
    )
    (package.workspace_root / ALL_ARTIFACTS[-1]).unlink()
    incomplete = grade_v06(
        PROJECT_ROOT,
        package,
        selected_resource=environment.selected_resource,
        commitment_immutable=True,
        completion_accepted=False,
    )
    assert incomplete.completed_artifact_quality == complete.completed_artifact_quality
    assert incomplete.artifact_coverage == 90
    assert incomplete.coverage_adjusted_scientific_score == 90
    assert incomplete.reliability_inclusive_score == 0
    assert incomplete.first_substantive_divergence == "A10"


def test_commitment_hashes_presence_and_absence_of_every_pre_reveal_artifact(
    tmp_path: Path,
) -> None:
    scenario_id = iter_v06_scenarios(PROJECT_ROOT)[0]["scenario_id"]
    package = V06Builder(PROJECT_ROOT).build(scenario_id, output_root=tmp_path)
    reference_v06_precommit(package, PROJECT_ROOT)
    missing = package.workspace_root / ALL_ARTIFACTS[1]
    saved = json.loads(missing.read_text(encoding="utf-8"))
    missing.unlink()
    environment = V06Environment(package)
    environment.commit_validation_plan()
    assert environment.committed_snapshot[ALL_ARTIFACTS[1]] == "MISSING"
    _write_json(missing, saved)
    with pytest.raises(ContractError, match="changed"):
        environment.reveal_validation()


def test_panel_contains_cross_provider_and_temporal_comparisons_without_ceiling_probe() -> None:
    panel = json.loads(
        (PROJECT_ROOT / "configs/hard_suite_v06_model_panel.json").read_text(encoding="utf-8")
    )
    model_ids = {row["model_id"] for row in panel["models"]}
    assert model_ids == {
        "openai/gpt-5.6-sol",
        "openai/gpt-5.2",
        "anthropic/claude-opus-5",
        "google/gemini-3.1-pro-preview",
        "moonshotai/kimi-k3",
    }
    assert panel["status"] == "authorized_for_one_time_pre_exposure_freeze"
    assert panel["scientific_execution_authorized"] is True
    assert panel["freeze_authorized"] is True
    assert panel["heldout_ceiling_probe_configured"] is False

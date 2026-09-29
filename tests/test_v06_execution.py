from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from scripts.run_v06_pilot import (
    all_jobs,
    attempt_control,
    select_jobs,
    sentinel_decision,
    validate_resume_checkpoint,
)
from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256
from uc_bench.v06_freeze import (
    v06_frozen_hashes,
    v06_runtime_versions,
    validate_v06_freeze_manifest,
)
from uc_bench.v06_probe_analysis import analyze_v06_probe, ceiling_band

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _config(name: str) -> dict:
    return json.loads((PROJECT_ROOT / "configs" / name).read_text(encoding="utf-8"))


def _diagnostic(score: float, *, completion_accepted: bool = True) -> dict:
    config = _config("hard_suite_v06.json")
    artifact_scores = {row["id"]: score for row in config["artifacts"]}
    annotations = [
        {
            "artifact": row["id"],
            "artifact_path": f"submission/{row['filename']}",
            "artifact_score": score,
            "artifact_state": "conditionally_valid" if score >= 50 else "invalid",
            "properties_evaluated": row["invariants"],
            "professional_consequence": row["consequence_of_error"],
            "paired_remedy": row["paired_remedy"],
            "remedy_intervention_class": row["remedy_intervention_class"],
        }
        for row in config["artifacts"]
        if score < 90
    ]
    return {
        "completion_accepted": completion_accepted,
        "coverage_adjusted_scientific_score": score,
        "artifact_scores": artifact_scores,
        "family_scores": {row["family"]: score for row in config["artifacts"]},
        "capability_scores": {name: score for name in config["capabilities"]},
        "scientific_failure_annotations": annotations,
    }


def _row(model: str, scenario: str, score: float) -> dict:
    return {
        "model_id": model,
        "scenario_id": scenario,
        "classification": "valid_episode",
        "score": score,
        "identity_violation": False,
        "diagnostic_grade": _diagnostic(score),
    }


def test_full_and_balanced_sentinel_job_sets_are_predeclared() -> None:
    panel = _config("hard_suite_v06_model_panel.json")
    execution = _config("hard_suite_v06_execution.json")
    jobs = all_jobs(panel)
    full = select_jobs(jobs, execution, "full")
    sentinel = select_jobs(jobs, execution, "sentinel")
    assert len(full) == 30
    assert len(sentinel) == 10
    assert {row["seed"] for row in full} == {
        61107,
        62213,
        63317,
        64421,
        65527,
        66631,
    }
    assert {row["scenario_id"] for row in sentinel} == {
        "dev6_clean_progression",
        "dev6_preprocessing_leakage",
    }
    counts = {
        model["model_id"]: sum(row["model_id"] == model["model_id"] for row in sentinel)
        for model in panel["models"]
    }
    assert set(counts.values()) == {2}


def test_sentinel_rules_do_not_create_a_ranking_claim() -> None:
    models = ["m1", "m2"]
    scenarios = ["clean", "leakage"]
    rows = [
        _row(model, scenario, 68 + index)
        for index, (model, scenario) in enumerate(
            (model, scenario) for model in models for scenario in scenarios
        )
    ]
    decision = sentinel_decision(rows, models, scenarios)
    assert decision["decision"] == "continue"
    assert decision["ranking_claim_allowed"] is False


def test_sentinel_stops_on_adapter_failure_ceiling_or_floor() -> None:
    models = ["m1", "m2"]
    scenarios = ["clean", "leakage"]
    adapter_rows = [
        {
            "model_id": model,
            "scenario_id": scenario,
            "classification": (
                "provider_adapter_failure"
                if model == "m1" and scenario == "clean"
                else "valid_episode"
            ),
            "score": 70,
            "identity_violation": False,
        }
        for model in models
        for scenario in scenarios
    ]
    assert sentinel_decision(adapter_rows, models, scenarios)["decision"] == "stop"
    ceiling = [_row(model, scenario, 85) for model in models for scenario in scenarios]
    assert sentinel_decision(ceiling, models, scenarios)["reasons"] == [
        "ceiling_band_allows_continuation",
    ]
    floor = [_row(model, scenario, 50) for model in models for scenario in scenarios]
    assert sentinel_decision(floor, models, scenarios)["reasons"] == [
        "ceiling_band_allows_continuation",
    ]


def test_probe_uses_science_only_after_accepted_submission_and_defers_scenario_cap() -> None:
    config = _config("hard_suite_v06.json")
    models = ["m1", "m2"]
    scenarios = ["clean", "leakage"]
    rows = [_row(model, scenario, 68) for model in models for scenario in scenarios]
    result = analyze_v06_probe(
        rows,
        config=config,
        model_ids=models,
        scenario_ids=scenarios,
    )
    assert result["sentinel_decision"]["decision"] == "continue"
    assert result["strongest_model_scientific_mean"] == 68
    assert result["capability_diagnostics"]["material_capability_count"] == 10
    assert result["artifact_family_concentration"]["largest_gap_share"] == 0.1
    assert result["scenario_concentration"]["largest_observed_gap_share"] == 0.5
    assert result["scenario_concentration"]["evaluable"] is False
    assert result["scenario_concentration"]["passes"] is None
    assert result["meaningful_partial_credit"]["passes"] is True

    unsubmitted = deepcopy(rows)
    unsubmitted[0]["diagnostic_grade"] = _diagnostic(
        68, completion_accepted=False
    )
    unsubmitted[0]["score"] = 0
    rejected = analyze_v06_probe(
        unsubmitted,
        config=config,
        model_ids=models,
        scenario_ids=scenarios,
    )
    assert rejected["gate_results"]["valid_submission_in_every_cell"] is False
    assert rejected["sentinel_decision"]["decision"] == "stop"


def test_ceiling_bands_are_exactly_predeclared() -> None:
    gates = _config("hard_suite_v06.json")["development_acceptance_gates"]
    assert ceiling_band(59.99, gates) == "overhard_no_go"
    assert ceiling_band(60, gates) == "desired_60_to_70"
    assert ceiling_band(70, gates) == "desired_60_to_70"
    assert ceiling_band(75, gates) == "acceptable_70_to_75"
    assert ceiling_band(80, gates) == "insufficient_headroom_75_to_80"
    assert ceiling_band(80.01, gates) == "ceiling_no_go_above_80"


def test_resume_rejects_any_frozen_or_execution_contract_change() -> None:
    panel = _config("hard_suite_v06_model_panel.json")
    execution = _config("hard_suite_v06_execution.json")
    hashes = {"task": "abc", "grader": "def"}
    checkpoint = {
        "frozen_hashes": hashes,
        "panel_digest": canonical_sha256(panel),
        "execution_digest": canonical_sha256(execution),
    }
    validate_resume_checkpoint(
        checkpoint,
        frozen_hashes=hashes,
        panel=panel,
        execution=execution,
    )
    changed = deepcopy(hashes)
    changed["grader"] = "changed"
    with pytest.raises(ConfigurationError, match="frozen hashes changed"):
        validate_resume_checkpoint(
            checkpoint,
            frozen_hashes=changed,
            panel=panel,
            execution=execution,
        )
    modified_execution = deepcopy(execution)
    modified_execution["episode_budget"]["maximum_turns"] += 1
    with pytest.raises(ConfigurationError, match="execution contract changed"):
        validate_resume_checkpoint(
            checkpoint,
            frozen_hashes=hashes,
            panel=panel,
            execution=modified_execution,
        )


def test_proposed_freeze_contract_checks_hashes_runtime_and_zero_exposure() -> None:
    hashes = v06_frozen_hashes(PROJECT_ROOT)
    manifest = {
        "schema_version": "0.6-freeze-1",
        "frozen_before_scientific_model_calls": True,
        "astra_exposure_count": 0,
        "heldout_exposure_count": 0,
        "hashes": hashes,
        "runtime_versions": v06_runtime_versions(),
    }
    validate_v06_freeze_manifest(PROJECT_ROOT, manifest)
    manifest["heldout_exposure_count"] = 1
    with pytest.raises(ConfigurationError, match="held-out exposure"):
        validate_v06_freeze_manifest(PROJECT_ROOT, manifest)


def test_infrastructure_retry_is_same_cell_once_and_adapter_failure_stops() -> None:
    assert attempt_control(
        "infrastructure_failure", execution_attempt=0, retry_limit=1
    ) == ("retry_same_cell", None)
    assert attempt_control(
        "infrastructure_failure", execution_attempt=1, retry_limit=1
    ) == ("stop", "infrastructure_retry_limit")
    assert attempt_control(
        "provider_adapter_failure", execution_attempt=0, retry_limit=1
    ) == ("stop", "provider_adapter_failure")
    assert attempt_control("agent_task_failure", execution_attempt=0, retry_limit=1) == (
        "advance",
        None,
    )

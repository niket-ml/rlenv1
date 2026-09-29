from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

import uc_bench.hard_suite_v06 as v06
from uc_bench.errors import ConfigurationError
from uc_bench.hard_suite_v06 import run_reference_v06_episode
from uc_bench.v062_freeze import read_v062_freeze_manifest
from uc_bench.v063_grader import grade_v063, grader_infrastructure_failed
from uc_bench.v063_runner import (
    V063RunConfig,
    _aggregate_usage,
    _emergency_artifacts,
    run_v063_episode,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PARENT_V062_DIGEST = (
    "aaee94c7bc94f4944990fdfa6bfbb3b8f413a4f50235091a1dde491627a264b4"
)


def _read(relative: str) -> dict:
    return json.loads((PROJECT_ROOT / relative).read_text(encoding="utf-8"))


def test_parent_v062_freeze_remains_valid() -> None:
    assert read_v062_freeze_manifest(PROJECT_ROOT)["hash_set_digest"] == (
        PARENT_V062_DIGEST
    )


def test_v063_changes_no_scientific_opportunity_or_gate() -> None:
    parent = _read("configs/hard_suite_v062_execution.json")
    successor = _read("configs/hard_suite_v063_execution.json")
    assert successor["episode_budget"] == parent["episode_budget"]
    assert successor["full_matrix"] == parent["full_matrix"]
    parent_sentinel = dict(parent["sentinel"])
    successor_sentinel = dict(successor["sentinel"])
    parent_sentinel.pop("maximum_incremental_spend_usd")
    successor_sentinel.pop("maximum_incremental_spend_usd")
    successor_sentinel.pop("aggregate_authorized_scientific_cap_usd")
    successor_sentinel.pop("predecessor_v062_spend_usd")
    assert successor_sentinel == parent_sentinel
    assert successor["sentinel"]["maximum_incremental_spend_usd"] == 55.57
    assert (
        successor["sentinel"]["maximum_incremental_spend_usd"]
        + successor["sentinel"]["predecessor_v062_spend_usd"]
        <= successor["sentinel"]["aggregate_authorized_scientific_cap_usd"]
    )


def test_unexpected_grader_bug_is_explicitly_excluded(tmp_path: Path) -> None:
    package, _environment, _grade = run_reference_v06_episode(
        PROJECT_ROOT,
        "dev6_clean_progression",
        output_root=tmp_path,
    )
    with patch.object(v06, "grade_v06", side_effect=RuntimeError("injected grader bug")):
        grade = grade_v063(
            PROJECT_ROOT,
            package,
            selected_resource="none",
            commitment_immutable=True,
            completion_accepted=True,
        )
    assert grader_infrastructure_failed(grade) is True
    assert grade.completion_accepted is False
    assert grade.process_annotations[0]["tag"] == "grader_internal_error"


def test_emergency_usage_preserves_paid_request_accounting() -> None:
    usage = _aggregate_usage(
        [
            {"usage": {"prompt_tokens": 100, "completion_tokens": 20}},
            {"usage": {"input_tokens": 50, "output_tokens": 5}},
            {"error": {"type": "network"}},
        ]
    )
    assert usage == {
        "prompt_tokens": 150,
        "completion_tokens": 25,
        "total_tokens": 175,
    }


def test_post_rollout_exception_writes_replayable_cost_checkpoint(
    tmp_path: Path,
) -> None:
    config = V063RunConfig(
        model_id="openai/gpt-5.6-sol",
        run_id="hard63-emergency-test",
        scenario_id="dev6_clean_progression",
        seed=61107,
    )
    run_root = tmp_path / "build/hard_suite_v06_runs/hard63-emergency-test"
    run_root.mkdir(parents=True)
    (run_root / "request_ledger.json").write_text(
        json.dumps(
            {
                "requests": [
                    {
                        "reported_cost_usd": 0.125,
                        "returned_model": "openai/gpt-5.6-sol",
                        "actual_provider": "OpenAI",
                        "usage": {
                            "prompt_tokens": 100,
                            "completion_tokens": 20,
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    diagnostic = {
        "coverage_adjusted_scientific_score": 72.5,
        "process_annotations": [],
    }
    with patch(
        "uc_bench.v063_runner._recover_diagnostic_grade",
        return_value=diagnostic,
    ):
        artifacts = _emergency_artifacts(
            tmp_path,
            config,
            error=RuntimeError("post-rollout failure"),
            key="not-live",
        )
    persisted = json.loads(artifacts.summary_path.read_text(encoding="utf-8"))
    assert persisted["classification"] == "post_rollout_infrastructure_failure"
    assert persisted["attempt_score"] is None
    assert persisted["scientific_score"] is None
    assert persisted["diagnostic_grade"] == diagnostic
    assert persisted["cumulative_reported_cost_usd"] == 0.125
    assert persisted["provider_request_count"] == 1
    assert persisted["token_usage"]["total_tokens"] == 120


def test_direct_execution_fails_closed_without_freeze_authorization() -> None:
    config = V063RunConfig(
        model_id="openai/gpt-5.6-sol",
        run_id="hard63-local-auth-test",
        scenario_id="dev6_clean_progression",
        seed=61107,
    )
    with pytest.raises(ConfigurationError, match="freeze"):
        run_v063_episode(
            PROJECT_ROOT,
            config,
            openrouter_key="not-live",
            authorization_digest="wrong",
        )


def test_astra_is_rejected_before_any_execution() -> None:
    with pytest.raises(ConfigurationError, match="Astra"):
        V063RunConfig(
            model_id="openai/gpt-6-astra",
            run_id="hard63-forbidden",
            scenario_id="dev6_clean_progression",
            seed=61107,
        )

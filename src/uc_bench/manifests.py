"""Load and validate the public JSON manifests shipped with the project."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError


def find_project_root(start: Path | None = None) -> Path:
    candidate = (start or Path.cwd()).resolve()
    for path in (candidate, *candidate.parents):
        if (path / "pyproject.toml").is_file() and (path / "configs").is_dir():
            return path
    raise ConfigurationError("Could not locate project root containing pyproject.toml and configs/")


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigurationError(f"Missing manifest: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ConfigurationError(f"Manifest must contain a JSON object: {path}")
    return value


def _assert_close(actual: float, expected: float, label: str) -> None:
    if abs(actual - expected) > 1e-9:
        raise ConfigurationError(f"{label} must equal {expected}; found {actual}")


def validate_config_root(config_root: Path) -> dict[str, Any]:
    benchmark = load_json(config_root / "benchmark.json")
    cohorts = load_json(config_root / "cohorts.json")
    data_sources = load_json(config_root / "data_sources.json")
    reward = load_json(config_root / "reward_weights.json")
    milestones = load_json(config_root / "milestone_weights.json")
    variants = load_json(config_root / "variant_ladders.json")
    evidence_states = load_json(config_root / "evidence_states.json")
    evaluation = load_json(config_root / "evaluation_protocol.json")
    smoke = load_json(config_root / "smoke_pilot.json")
    task = load_json(config_root / "tasks" / "uc_biomarker_diligence_v0.json")

    if benchmark.get("evaluation_subject") != "tool_using_agent":
        raise ConfigurationError("The evaluation subject must be the tool-using agent")
    headline = benchmark.get("headline_policy", {})
    if headline.get("primary_metric") != "graceful_failure_score":
        raise ConfigurationError("The primary metric must be graceful_failure_score")
    if headline.get("raw_auc_is_headline") is not False:
        raise ConfigurationError("Raw AUC must not be a headline metric")
    if set(benchmark.get("terminal_decisions", [])) != {
        "advance",
        "stop",
        "insufficient_evidence",
    }:
        raise ConfigurationError("Benchmark must define exactly three terminal decisions")

    source_rows = data_sources.get("sources", [])
    if not source_rows:
        raise ConfigurationError("At least one pinned data source is required")
    source_ids = [row.get("id") for row in source_rows]
    source_paths = [row.get("path") for row in source_rows]
    if len(source_ids) != len(set(source_ids)) or len(source_paths) != len(set(source_paths)):
        raise ConfigurationError("Pinned data source IDs and paths must be unique")
    for row in source_rows:
        if not str(row.get("url", "")).startswith("https://"):
            raise ConfigurationError(f"Pinned source must use HTTPS: {row.get('id')}")
        if int(row.get("bytes", 0)) <= 0 or len(str(row.get("sha256", ""))) != 64:
            raise ConfigurationError(f"Pinned source has invalid size or digest: {row.get('id')}")

    reward_weights = reward.get("weights", {})
    _assert_close(sum(reward_weights.values()), 1.0, "Reward weights")
    if reward.get("headline_score") != "graceful_failure_score":
        raise ConfigurationError("Reward headline must be graceful_failure_score")
    if float(reward.get("realized_discrimination_maximum_within_episode_weight", 1.0)) > 0.10:
        raise ConfigurationError("Realized discrimination may contribute at most 10 percent")
    anti_hacking = reward.get("anti_hacking_rules", {})
    if any(anti_hacking.get(key) is not False for key in (
        "unsupported_caution_receives_detection_credit",
        "universal_abstention_can_pass",
        "universal_advancement_can_pass",
        "narrated_but_unexecuted_checks_receive_credit",
        "post_hoc_model_changes_receive_credit",
    )):
        raise ConfigurationError("All anti-hacking permissions must be explicitly false")

    milestone_rows = milestones.get("milestones", [])
    if len(milestone_rows) != 10:
        raise ConfigurationError(
            f"Exactly 10 episode milestones are required; found {len(milestone_rows)}"
        )
    milestone_ids = [row["id"] for row in milestone_rows]
    if milestone_ids != [f"M{index:02d}" for index in range(1, 11)]:
        raise ConfigurationError("Milestone IDs must be ordered M01 through M10")
    total_milestone_weight = sum(float(row["weight"]) for row in milestone_rows)
    _assert_close(
        total_milestone_weight,
        float(milestones["expected_total"]),
        "Milestone weights",
    )
    setup_ids = set(milestones["setup_milestone_ids"])
    setup_weight = sum(
        float(row["weight"]) for row in milestone_rows if row["id"] in setup_ids
    )
    setup_share = setup_weight / total_milestone_weight
    if setup_share > float(milestones["maximum_setup_share"]) + 1e-9:
        raise ConfigurationError(
            f"Setup milestones exceed maximum headline share: {setup_share:.3f}"
        )

    cohort_rows = cohorts.get("cohorts", [])
    accessions = [row["accession"] for row in cohort_rows]
    if len(accessions) != len(set(accessions)):
        raise ConfigurationError("Cohort accessions must be unique")
    sealed = [row for row in cohort_rows if row.get("role") == "sealed_transfer"]
    if len(sealed) != 1:
        raise ConfigurationError("Exactly one sealed_transfer cohort is required")
    if sealed[0]["agent_access"]["outcomes"] != "never_visible":
        raise ConfigurationError("Sealed cohort outcomes must never be agent-visible")

    if task.get("task_id") != benchmark.get("benchmark_id"):
        raise ConfigurationError("Task and benchmark IDs must match")
    if task.get("conditions") != ["full_data", "data_withheld"]:
        raise ConfigurationError("Task must define full_data and data_withheld conditions")
    if task.get("terminal_decisions") != benchmark.get("terminal_decisions"):
        raise ConfigurationError("Task and benchmark terminal decisions must match")
    if task["evaluation"].get("raw_auc_is_headline_ranking_metric") is not False:
        raise ConfigurationError("Task raw AUC must not be a headline ranking metric")
    if task["predictor_contract"].get("sealed_features_visible_to_agent") is not False:
        raise ConfigurationError("Sealed expression must never be agent-visible")
    if task["predictor_contract"].get("arbitrary_serialized_code_allowed") is not False:
        raise ConfigurationError("The grader must not execute arbitrary agent code")
    if task["post_reveal"].get("agent_receives_individual_predictions") is not False:
        raise ConfigurationError("Individual validation predictions must remain private")
    required_one_shot_tools = {"commit_analysis", "reveal_validation", "submit"}
    if any(task["tool_limits"].get(tool) != 1 for tool in required_one_shot_tools):
        raise ConfigurationError("Commit, reveal, and submit tools must each be one-shot")

    ladders = variants.get("ladders", {})
    if not ladders:
        raise ConfigurationError("At least one private variant ladder must be declared")
    for name, levels in ladders.items():
        if len(levels) < 2 or levels != sorted(levels) or len(levels) != len(set(levels)):
            raise ConfigurationError(f"Variant ladder {name!r} must be sorted and unique")

    state_rows = evidence_states.get("states", [])
    state_families = {row.get("family") for row in state_rows}
    if state_families != {
        "authentic_weak_evidence",
        "sufficient_evidence",
        "recoverable_defect",
        "irrecoverable_defect",
    }:
        raise ConfigurationError("Evidence states must include all four symmetric families")
    state_decisions = {row.get("expected_decision") for row in state_rows}
    if state_decisions != set(benchmark["terminal_decisions"]):
        raise ConfigurationError("Evidence states must exercise all terminal decisions")
    reporting = evidence_states.get("reporting_policy", {})
    if reporting.get("authentic_and_controlled_separate") is not True:
        raise ConfigurationError("Authentic and controlled evidence states must remain separate")
    if reporting.get("controlled_states_support_biology_claims") is not False:
        raise ConfigurationError("Controlled evidence states cannot support biology claims")

    model_variables = smoke.get("model_environment_variables", [])
    if len(model_variables) != 3 or len(model_variables) != len(set(model_variables)):
        raise ConfigurationError("Smoke pilot must declare three unique model variables")
    attempts_per_model = int(smoke.get("attempts_per_model", 0))
    if attempts_per_model != 3:
        raise ConfigurationError("Smoke pilot must run three attempts per model")
    if smoke.get("smoke_trajectory_count") != len(model_variables) * attempts_per_model:
        raise ConfigurationError("Smoke trajectory count must match models times attempts")
    if smoke.get("scripted_fixtures_are_model_results") is not False:
        raise ConfigurationError("Scripted fixtures must never be represented as model results")
    if smoke.get("isolation_backend_environment_variable") != "UC_BENCH_ISOLATION_BACKEND":
        raise ConfigurationError("Smoke pilot must use the declared isolation selector")
    if set(smoke.get("allowed_isolation_backends", [])) != {"docker", "prime", "modal"}:
        raise ConfigurationError("Smoke pilot must require a supported isolated runtime")

    evaluation_models = evaluation.get("models", [])
    if evaluation_models != model_variables:
        raise ConfigurationError("Evaluation and smoke pilot model variables must match")
    headline_conditions = evaluation.get("headline_conditions", [])
    if headline_conditions != task.get("conditions"):
        raise ConfigurationError("Evaluation conditions must match the task conditions")
    seeds_per_condition = int(evaluation.get("seeds_per_model_per_headline_condition", 0))
    if seeds_per_condition < 10:
        raise ConfigurationError("Headline evaluation requires at least ten seeds per condition")
    expected_trajectories = len(evaluation_models) * len(headline_conditions) * seeds_per_condition
    if evaluation.get("headline_trajectory_count") != expected_trajectories:
        raise ConfigurationError("Headline trajectory count does not match the run matrix")
    if evaluation.get("primary_metric") != benchmark["headline_policy"]["primary_metric"]:
        raise ConfigurationError("Evaluation and benchmark primary metrics must match")
    if evaluation.get("controlled_results_are_headline") is not False:
        raise ConfigurationError("Controlled results must remain outside the headline ranking")

    return {
        "cohort_count": len(cohort_rows),
        "benchmark_id": benchmark["benchmark_id"],
        "sealed_cohort": sealed[0]["accession"],
        "milestone_count": len(milestone_rows),
        "milestone_weight_total": total_milestone_weight,
        "setup_milestone_share": setup_share,
        "pinned_data_source_count": len(source_rows),
        "headline_score": reward["headline_score"],
        "reward_weight_total": sum(reward_weights.values()),
        "variant_ladder_count": len(ladders),
        "evidence_state_count": len(state_rows),
        "task_conditions": task["conditions"],
        "smoke_trajectory_count": smoke["smoke_trajectory_count"],
        "headline_trajectory_count": evaluation["headline_trajectory_count"],
    }

#!/usr/bin/env python3
"""Exercise framework tool schemas and three deterministic runtime fixtures."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from uc_bench.docker_runtime import find_docker_binary
from uc_bench.environment import DiligenceEnvironment
from uc_bench.errors import ArtifactMutationError, ConfigurationError, DockerRuntimeError
from uc_bench.model_runner import load_openrouter_key
from uc_bench.packaging import StartStateBuilder
from uc_bench.runtime_adapter import DomainToolAdapter
from uc_bench.state import EpisodeState

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_ROOT = PROJECT_ROOT / "artifacts" / "reference"


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def prepare_fixture(name: str) -> tuple[Path, DomainToolAdapter]:
    root = PROJECT_ROOT / "build" / "runtime_smoke" / name
    package = StartStateBuilder(PROJECT_ROOT).build(
        "full_data", output_root=root, replace=True
    )
    workspace = package.workspace_root
    for filename in ("model.json", "development_evidence.json", "predictor_manifest.json"):
        shutil.copyfile(REFERENCE_ROOT / filename, workspace / "submission" / filename)
    commitment = read_json(REFERENCE_ROOT / "commitment.json")
    commitment["artifact_paths"] = [
        "submission/model.json",
        "submission/development_evidence.json",
        "submission/predictor_manifest.json",
    ]
    write_json(workspace / "submission" / "commitment.json", commitment)
    answers = read_json(workspace / "analyst_answers.json")
    core = DiligenceEnvironment(
        workspace_root=workspace,
        sealed_expression_path=(
            PROJECT_ROOT / "data" / "processed" / "sealed" / "GSE92415_gene_expression.csv.gz"
        ),
        sealed_labels_path=PROJECT_ROOT / "grader_private" / "data" / "gse92415_labels.csv",
        episode=EpisodeState(
            f"runtime-smoke-{name}",
            "uc_biomarker_diligence_v0",
            "full_data",
            "authentic_weak_evidence",
            20260906,
        ),
        bootstrap_resamples=100,
        permutation_count=10000,
        evaluation_seed=20260909,
        analyst_answers={str(key): str(value) for key, value in answers.items()},
        task_schema_root=(
            PROJECT_ROOT / "tasks" / "uc_biomarker_diligence_v0" / "schemas"
        ),
    )
    return workspace, DomainToolAdapter(core)


def run_valid_fixture(name: str, *, reckless: bool) -> dict[str, Any]:
    workspace, adapter = prepare_fixture(name)
    adapter.ask_analyst("cohort_endpoint")
    adapter.commit_analysis(
        "submission/commitment.json",
        "submission/model.json",
        "submission/predictor_manifest.json",
    )
    adapter.reveal_validation()
    if reckless:
        final = {
            "decision": "advance",
            "confidence": 0.95,
            "rationale": "The AUC is above chance.",
            "failure_mode": "none",
            "diagnostic_codes": ["none"],
            "evidence_artifact_paths": ["results/validation_result.json"],
            "next_action_type": "independent_replication",
            "next_action": "Use the predictor for treatment prioritization.",
        }
    else:
        final = read_json(REFERENCE_ROOT / "final_submission.json")
        final["evidence_artifact_paths"] = [
            "submission/development_evidence.json",
            "results/validation_result.json",
        ]
    write_json(workspace / "submission" / "final_submission.json", final)
    adapter.submit("submission/final_submission.json")
    return {
        "fixture": name,
        "phase": adapter.environment.episode.phase.value,
        "classification": "task_scientific_failure" if reckless else "valid_reference",
        "infrastructure_failure": False,
    }


def run_mutation_fixture() -> dict[str, Any]:
    workspace, adapter = prepare_fixture("post_commit_mutation")
    adapter.commit_analysis(
        "submission/commitment.json",
        "submission/model.json",
        "submission/predictor_manifest.json",
    )
    model = read_json(workspace / "submission" / "model.json")
    model["intercept"] = float(model["intercept"]) + 1.0
    write_json(workspace / "submission" / "model.json", model)
    rejected = False
    try:
        adapter.reveal_validation()
    except ArtifactMutationError:
        rejected = True
    if not rejected:
        raise RuntimeError("Post-commit mutation fixture was not rejected")
    return {
        "fixture": "post_commit_mutation",
        "phase": adapter.environment.episode.phase.value,
        "classification": "task_integrity_failure",
        "infrastructure_failure": False,
        "mutation_rejected": True,
    }


def main() -> int:
    import verifiers as vf

    _, adapter = prepare_fixture("tool_schema")
    system_prompt = (PROJECT_ROOT / "tasks" / "uc_biomarker_diligence_v0" / "TASK.md").read_text(
        encoding="utf-8"
    )
    vf_environment = adapter.verifiers_tool_environment(
        system_prompt=system_prompt, max_turns=40
    )
    tool_names = [tool.name for tool in vf_environment.tool_defs or []]
    expected_tools = ["ask_analyst", "commit_analysis", "reveal_validation", "submit"]
    if tool_names != expected_tools:
        raise RuntimeError(f"Unexpected Verifiers tool schema: {tool_names}")

    smoke_config = read_json(PROJECT_ROOT / "configs" / "smoke_pilot.json")
    key_presence = {
        name: bool(os.environ.get(name))
        for name in smoke_config["provider_key_environment_variables"]
    }
    if not key_presence.get("OPENROUTER_API_KEY"):
        try:
            load_openrouter_key(PROJECT_ROOT)
        except ConfigurationError:
            pass
        else:
            key_presence["OPENROUTER_API_KEY"] = True
    model_presence = {
        name: bool(os.environ.get(name))
        for name in smoke_config["model_environment_variables"]
    }
    pinned_models = read_json(PROJECT_ROOT / "configs" / "smoke_models.json")["models"]
    pinned_model_ids = [str(row["model_id"]) for row in pinned_models]
    allowed_backends = smoke_config["allowed_isolation_backends"]
    selected_backend = os.environ.get(
        smoke_config["isolation_backend_environment_variable"], "docker"
    ).lower()
    isolation_credentials = smoke_config["isolation_credential_environment_variables"]
    try:
        find_docker_binary()
        docker_ready = True
    except DockerRuntimeError:
        docker_ready = False
    isolation_backend_ready = {
        "docker": docker_ready,
        "prime": all(bool(os.environ.get(name)) for name in isolation_credentials["prime"]),
        "modal": all(bool(os.environ.get(name)) for name in isolation_credentials["modal"]),
    }
    selected_isolation_ready = (
        selected_backend in allowed_backends
        and isolation_backend_ready.get(selected_backend, False)
    )
    readiness_path = PROJECT_ROOT / "artifacts" / "runtime" / "openrouter_readiness.json"
    account_readiness = read_json(readiness_path) if readiness_path.is_file() else {}
    credits = account_readiness.get("credits") or {}
    remaining_credits = credits.get("remaining_usd")
    funding_ready = isinstance(remaining_credits, int | float) and remaining_credits > 0
    required_key_limit = float(
        read_json(PROJECT_ROOT / "configs" / "smoke_models.json")["cost_planning"][
            "required_provider_key_limit_usd"
        ]
    )
    current_key_limit = account_readiness.get("key_limit_usd")
    key_limit_ready = (
        isinstance(current_key_limit, int | float)
        and 0 < current_key_limit <= required_key_limit
    )
    fixtures = [
        run_valid_fixture("reference", reckless=False),
        run_valid_fixture("reckless", reckless=True),
        run_mutation_fixture(),
    ]
    output = {
        "schema_version": "0.1",
        "verifiers_version": vf.__version__,
        "domain_tool_names": tool_names,
        "fixture_smoke": fixtures,
        "fixture_infrastructure_failures": sum(
            bool(row["infrastructure_failure"]) for row in fixtures
        ),
        "provider_key_presence": key_presence,
        "model_environment_configuration_presence": model_presence,
        "pinned_model_ids": pinned_model_ids,
        "pinned_model_configuration_ready": len(pinned_model_ids) == 3,
        "selected_isolation_backend": selected_backend or None,
        "isolation_backend_ready": isolation_backend_ready,
        "selected_isolation_ready": selected_isolation_ready,
        "real_model_smoke_executed": False,
        "real_model_smoke_structurally_ready": (
            (all(model_presence.values()) or len(pinned_model_ids) == 3)
            and any(key_presence.values())
            and selected_isolation_ready
        ),
        "openrouter_funding_ready": funding_ready,
        "openrouter_key_limit_ready": key_limit_ready,
        "real_model_smoke_ready": (
            (all(model_presence.values()) or len(pinned_model_ids) == 3)
            and any(key_presence.values())
            and selected_isolation_ready
            and funding_ready
            and key_limit_ready
        ),
        "fixtures_are_leaderboard_evidence": False,
    }
    output_path = PROJECT_ROOT / "artifacts" / "runtime" / "infrastructure_smoke.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

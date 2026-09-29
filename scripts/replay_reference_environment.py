#!/usr/bin/env python3
"""Replay the expert solution through a fresh public start state and private evaluator."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from uc_bench.environment import DiligenceEnvironment
from uc_bench.packaging import StartStateBuilder
from uc_bench.state import EpisodeState, Phase

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


def main() -> int:
    replay_root = PROJECT_ROOT / "build" / "reference_replay"
    package = StartStateBuilder(PROJECT_ROOT).build(
        "full_data", output_root=replay_root, replace=True
    )
    workspace = package.workspace_root
    submission_root = workspace / "submission"

    for name in ("model.json", "development_evidence.json", "predictor_manifest.json"):
        shutil.copyfile(REFERENCE_ROOT / name, submission_root / name)

    commitment = read_json(REFERENCE_ROOT / "commitment.json")
    commitment["artifact_paths"] = [
        "submission/model.json",
        "submission/development_evidence.json",
        "submission/predictor_manifest.json",
    ]
    write_json(submission_root / "commitment.json", commitment)

    answers = read_json(workspace / "analyst_answers.json")
    episode = EpisodeState(
        episode_id="reference-packaged-authentic-seed-20260906",
        task_id="uc_biomarker_diligence_v0",
        condition="full_data",
        variant_id="authentic_weak_evidence",
        seed=20260906,
    )
    environment = DiligenceEnvironment(
        workspace_root=workspace,
        sealed_expression_path=(
            PROJECT_ROOT / "data" / "processed" / "sealed" / "GSE92415_gene_expression.csv.gz"
        ),
        sealed_labels_path=(
            PROJECT_ROOT / "grader_private" / "data" / "gse92415_labels.csv"
        ),
        episode=episode,
        bootstrap_resamples=2000,
        permutation_count=10000,
        evaluation_seed=20260909,
        analyst_answers={str(key): str(value) for key, value in answers.items()},
        analyst_turn_limit=3,
        task_schema_root=(
            PROJECT_ROOT / "tasks" / "uc_biomarker_diligence_v0" / "schemas"
        ),
    )
    environment.ask_analyst("cohort_endpoint")
    environment.ask_analyst("platform_processing")
    environment.commit_from_files(
        commitment_path="submission/commitment.json",
        model_path="submission/model.json",
        manifest_path="submission/predictor_manifest.json",
    )
    result = environment.reveal_validation()

    expected_result = read_json(REFERENCE_ROOT / "validation_result.json")
    normalized_result = json.loads(json.dumps(result.to_dict()))
    if normalized_result != expected_result:
        raise RuntimeError(
            "Packaged environment did not reproduce the direct reference validation"
        )

    final_submission = read_json(REFERENCE_ROOT / "final_submission.json")
    final_submission["evidence_artifact_paths"] = [
        "submission/development_evidence.json",
        "results/validation_result.json",
    ]
    write_json(submission_root / "final_submission.json", final_submission)
    environment.submit_from_file("submission/final_submission.json")
    if episode.phase is not Phase.SUBMITTED:
        raise RuntimeError("Reference replay did not reach the terminal submitted phase")

    record = environment.record()
    record["start_state"] = {
        "condition": package.condition,
        "file_count": package.file_count,
        "package_digest": package.package_digest,
    }
    write_json(REFERENCE_ROOT / "environment_episode.json", record)
    print(
        json.dumps(
            {
                "phase": episode.phase.value,
                "commitment_digest": episode.commitment_digest,
                "start_state_digest": package.package_digest,
                "validation_result": result.to_dict(),
                "public_record_contains_individual_validation_rows": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

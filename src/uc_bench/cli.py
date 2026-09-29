"""Command-line entry points for local environment development."""

from __future__ import annotations

import argparse
import importlib.util
import json
import platform
import sys
from collections.abc import Sequence
from pathlib import Path

from uc_bench.contracts import (
    AggregateValidationResult,
    Commitment,
    Decision,
    FinalSubmission,
)
from uc_bench.downloads import load_pinned_sources, source_is_valid
from uc_bench.errors import UCBenchError
from uc_bench.manifests import find_project_root, validate_config_root
from uc_bench.state import EpisodeState


def _project_root(value: str | None) -> Path:
    return Path(value).resolve() if value else find_project_root()


def _doctor(project_root: Path) -> int:
    summary = validate_config_root(project_root / "configs")
    required_dirs = ["data", "grader_private", "notebooks", "reports", "tasks", "trajectories"]
    missing_dirs = [name for name in required_dirs if not (project_root / name).is_dir()]
    if missing_dirs:
        raise UCBenchError(f"Missing project directories: {missing_dirs}")

    pinned_sources = load_pinned_sources(project_root)
    data_files_present = all(
        (project_root / source.relative_path).is_file() for source in pinned_sources
    )
    data_files_verified = data_files_present and all(
        source_is_valid(project_root, source) for source in pinned_sources
    )
    report = {
        "status": "ok",
        "python": platform.python_version(),
        "project_root": str(project_root),
        "core_dependency_count": 0,
        "verifiers_installed": importlib.util.find_spec("verifiers") is not None,
        "configs": summary,
        "data_files_present": data_files_present,
        "data_files_verified": data_files_verified,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def _demo() -> int:
    commitment = Commitment(
        target_endpoint="GSE92415 wk6response",
        endpoint_interpretation=(
            "Cross-drug and cross-platform transfer to week-6 clinical response"
        ),
        feature_schema_version="gene-symbol-v1",
        missing_feature_policy="fail below 0.80 coverage; otherwise use training median",
        decision_threshold=0.63,
        expected_auc=0.72,
        expected_auc_interval=(0.60, 0.84),
        permutation_count=10_000,
        artifact_paths=("analyses/pipeline.py", "results/model.bin", "results/sample_order.txt"),
    )
    hashes = {
        "analyses/pipeline.py": "7ec3",
        "results/model.bin": "1a9f",
        "results/sample_order.txt": "493b",
    }
    episode = EpisodeState(
        episode_id="demo-task-07-full-seed-0",
        task_id="task_07",
        condition="full_data",
        variant_id="clean",
        seed=0,
    )
    episode.commit_analysis(commitment, hashes)
    episode.reveal_validation(
        AggregateValidationResult(
            auc=0.66,
            auc_interval=(0.52, 0.79),
            permutation_p_value=0.13,
            evaluated_n=59,
        ),
        hashes,
    )
    episode.submit(
        FinalSubmission(
            decision=Decision.INSUFFICIENT_EVIDENCE,
            confidence=0.82,
            rationale="The transfer estimate is imprecise and the endpoint differs.",
            failure_mode="underpowered_cross_endpoint_transfer",
            diagnostic_codes=("underpowered_validation", "endpoint_mismatch"),
            evidence_artifact_paths=("results/validation.json",),
            next_action_type="prospective_endpoint_matched_validation",
            next_action="Run a larger endpoint-matched prospective validation cohort.",
        ),
        hashes,
    )
    print(json.dumps(episode.to_record(), indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="uc-bench")
    parser.add_argument("--project-root", help="Override automatic project-root discovery")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("doctor", help="Validate the local package and public manifests")
    subparsers.add_parser("validate-config", help="Validate and print manifest invariants")
    subparsers.add_parser("demo", help="Run a deterministic in-memory Task 7 episode")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            return _demo()
        project_root = _project_root(args.project_root)
        if args.command == "doctor":
            return _doctor(project_root)
        if args.command == "validate-config":
            summary = validate_config_root(project_root / "configs")
            print(json.dumps(summary, indent=2, sort_keys=True))
            return 0
    except UCBenchError as exc:
        print(f"uc-bench: {exc}", file=sys.stderr)
        return 2
    parser.error(f"Unknown command: {args.command}")
    return 2

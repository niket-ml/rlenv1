"""Final Case 2 runner with the canonical release verifier injected once."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any

from development.case2_graceful import release as scientific_release
from development.case2_graceful import runner as scientific_runner
from development.case2_graceful import trajectory as scientific_replay
from development.case2_graceful_budget import runner as budget_runner

from .case2_mmmvp_v1_verifier import grade_case2_submission
from .errors import ConfigurationError
from .model_runner import _write_json

Case2RunConfig = budget_runner.Case2RunConfig
Case2RunArtifacts = budget_runner.Case2RunArtifacts
PREFLIGHT_AUTHORIZATION = "case2-mmmvp-v1-fake-provider-preflight"


@contextmanager
def _canonical_release_runtime(root: Path):
    """Bind one verifier and the exact archived predecessor records."""

    from .case2_mmmvp_v1_release import (
        immutable_predecessor_record,
        immutable_release_record,
    )

    old_live = scientific_runner.verify_case2_rc1_submission
    old_replay = scientific_replay.verify_case2_rc1_submission
    old_budget_candidate = budget_runner.candidate_manifest
    old_budget_freeze = budget_runner.read_freeze
    old_predecessor_candidate = budget_runner.predecessor_candidate
    old_predecessor_freeze = budget_runner.predecessor_freeze
    old_scientific_candidate = scientific_release.candidate_manifest
    old_scientific_freeze = scientific_release.read_freeze
    budget = immutable_predecessor_record(root)
    graceful = immutable_release_record(
        root,
        Path("development/case2_graceful/release_candidate.json"),
        expected_digest=budget["predecessor_digest"],
    )
    scientific_runner.verify_case2_rc1_submission = grade_case2_submission
    scientific_replay.verify_case2_rc1_submission = grade_case2_submission
    budget_runner.candidate_manifest = lambda _root: budget
    budget_runner.read_freeze = lambda _root: budget
    budget_runner.predecessor_candidate = lambda _root: graceful
    budget_runner.predecessor_freeze = lambda _root: graceful
    scientific_release.candidate_manifest = lambda _root: graceful
    scientific_release.read_freeze = lambda _root: graceful
    try:
        yield
    finally:
        scientific_runner.verify_case2_rc1_submission = old_live
        scientific_replay.verify_case2_rc1_submission = old_replay
        budget_runner.candidate_manifest = old_budget_candidate
        budget_runner.read_freeze = old_budget_freeze
        budget_runner.predecessor_candidate = old_predecessor_candidate
        budget_runner.predecessor_freeze = old_predecessor_freeze
        scientific_release.candidate_manifest = old_scientific_candidate
        scientific_release.read_freeze = old_scientific_freeze


def run_case2_episode(
    project_root: Path,
    config: Case2RunConfig,
    *,
    adapter: Any,
    openrouter_key: str,
    authorization_digest: str,
    remaining_cost_cap_usd: float,
    output_root: Path,
    attempt_seed: int,
    provider_seed: int | None,
    native_client_factory: Any = None,
    preflight_mode: bool = False,
    resume: bool = False,
    preflight_interrupt_after_phase: str | None = None,
    scientific_authorization: str | None = None,
) -> Case2RunArtifacts:
    """Run unchanged Case 2 science and lifecycle with the final verifier."""

    root = project_root.resolve()
    from .case2_mmmvp_v1_release import immutable_predecessor_record

    predecessor = immutable_predecessor_record(root)
    if preflight_mode:
        if authorization_digest != PREFLIGHT_AUTHORIZATION:
            raise ConfigurationError("Case 2 MMMVP fake preflight authorization is invalid")
    else:
        from .case2_mmmvp_v1_release import read_release_freeze

        release = read_release_freeze(root)
        expected = release["aggregate_release_digest"]
        if authorization_digest != expected or scientific_authorization != expected:
            raise ConfigurationError(
                "Explicit Case 2 MMMVP authorization must match the frozen release"
            )

    with _canonical_release_runtime(root):
        result = budget_runner.run_case2_episode(
            root,
            config,
            adapter=adapter,
            openrouter_key=openrouter_key,
            authorization_digest=(
                budget_runner.PREFLIGHT_AUTHORIZATION
                if preflight_mode
                else predecessor["closure"]["aggregate_digest"]
            ),
            remaining_cost_cap_usd=remaining_cost_cap_usd,
            output_root=output_root,
            attempt_seed=attempt_seed,
            provider_seed=provider_seed,
            native_client_factory=native_client_factory,
            preflight_mode=preflight_mode,
            resume=resume,
            preflight_interrupt_after_phase=preflight_interrupt_after_phase,
            scientific_authorization=(
                budget_runner.PREFLIGHT_AUTHORIZATION
                if preflight_mode
                else predecessor["closure"]["aggregate_digest"]
            ),
        )

    summary = dict(result.summary)
    summary["scientific_predecessor_release_id"] = summary.get("release_id")
    summary["scientific_predecessor_release_digest"] = summary.get("release_digest")
    summary["release_id"] = "uc-bench-case2-mmmvp-v1"
    if preflight_mode:
        summary["release_digest"] = PREFLIGHT_AUTHORIZATION
    else:
        summary["release_digest"] = authorization_digest
    summary["canonical_verifier"] = (
        "uc_bench.case2_mmmvp_v1_verifier.grade_case2_submission"
    )
    _write_json(result.summary_path, summary, secret=openrouter_key)
    return replace(result, summary=summary)


__all__ = [
    "Case2RunArtifacts",
    "Case2RunConfig",
    "PREFLIGHT_AUTHORIZATION",
    "run_case2_episode",
]

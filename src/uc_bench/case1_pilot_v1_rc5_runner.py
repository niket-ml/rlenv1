"""RC5 execution through the already-tested RC4 production harness.

RC4 is immutable.  This narrow adapter injects RC5's release identity,
environment, verifier and replay function into the same production entry point,
then replaces convenience-field reporting with durable-state reconstruction.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import uc_bench.case1_pilot_v1_rc4_runner as inherited
from uc_bench.case1_pilot_v1_rc5_environment import RC5Case1Environment
from uc_bench.case1_pilot_v1_rc5_lock import INHERITED_EXTENSION_LOCK
from uc_bench.case1_pilot_v1_rc5_reporting import (
    CorruptTrajectoryError,
    reconstruct_lifecycle_or_empty,
)
from uc_bench.case1_pilot_v1_rc5_trajectory import rc5_trajectory_replay_check
from uc_bench.case1_pilot_v1_rc5_verifier import WEIGHTS, verify_case1_rc5_submission
from uc_bench.case1_pilot_v1_runner import Case1PilotRunArtifacts, Case1PilotRunConfig
from uc_bench.model_runner import _write_json

RC5_PREFLIGHT_AUTHORIZATION = "rc5-unfrozen-fake-provider-preflight"


def finalize_rc5_run_summary(run_root: Path, *, key: str) -> dict[str, Any]:
    """Idempotently replace inherited convenience fields with durable RC5 state."""

    summary_path = run_root.resolve() / "run_summary.json"
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CorruptTrajectoryError("RC5 run summary cannot be reconstructed") from exc
    if not isinstance(summary, dict):
        raise CorruptTrajectoryError("RC5 run summary must be an object")
    try:
        lifecycle = reconstruct_lifecycle_or_empty(run_root)
    except CorruptTrajectoryError as exc:
        lifecycle = {
            "status": "corrupt",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
        summary["classification"] = "infrastructure_failure"
        summary["failure_subtype"] = "durable_trajectory_corruption"
    summary.update(
        {
            "schema_version": "uc-bench-case1-pilot-v1-rc5-run-1",
            "authoritative_lifecycle": lifecycle,
        }
    )
    if lifecycle.get("status") != "corrupt":
        summary.update(
            {
                "turn_count": lifecycle["turn_count"],
                "provider_request_count": lifecycle["provider_request_count"],
                "completion_state": lifecycle["completion_state"],
                "validation_committed": lifecycle["validation_committed"],
                "validation_revealed": lifecycle["validation_revealed"],
                "resource_purchased": lifecycle["resource_purchased"],
                "submission_accepted": lifecycle["submission_accepted"],
                "checkpointed_spend_usd": lifecycle["checkpointed_spend_usd"],
                "final_provider_ledger_spend_usd": lifecycle["final_provider_ledger_spend_usd"],
                "budget_enforcement_spend_usd": lifecycle["budget_enforcement_spend_usd"],
            }
        )
    if summary.get("classification") not in {
        "provider_adapter_failure",
        "provider_identity_failure",
        "provider_policy_refusal",
        "infrastructure_failure",
        "grader_failure",
        "cost_cap_reached",
    }:
        summary["reliability_score"] = lifecycle.get("reliability_score", 0.0)
    _write_json(summary_path, summary, secret=key)
    return summary


@contextmanager
def _rc5_production_context() -> Iterator[None]:
    """Swap only versioned extension points; always restore RC4 module state."""

    from uc_bench.case1_pilot_v1_rc5_release import read_rc5_freeze

    names = {
        "RC4Case1Environment": RC5Case1Environment,
        "verify_case1_rc4_submission": verify_case1_rc5_submission,
        "rc4_trajectory_replay_check": rc5_trajectory_replay_check,
        "read_rc4_freeze": read_rc5_freeze,
        "RC4_PREFLIGHT_AUTHORIZATION": RC5_PREFLIGHT_AUTHORIZATION,
        "WEIGHTS": WEIGHTS,
    }
    with INHERITED_EXTENSION_LOCK:
        originals = {name: getattr(inherited, name) for name in names}
        try:
            for name, value in names.items():
                setattr(inherited, name, value)
            yield
        finally:
            for name, value in originals.items():
                setattr(inherited, name, value)


def run_case1_pilot_rc5_episode(
    project_root: Path,
    config: Case1PilotRunConfig,
    *,
    adapter: Any,
    openrouter_key: str,
    authorization_digest: str,
    remaining_cost_cap_usd: float,
    output_root: Path,
    attempt_seed: int,
    provider_seed: int | None,
    native_client_factory: Callable[..., Any] | None = None,
    preflight_mode: bool = False,
) -> Case1PilotRunArtifacts:
    with _rc5_production_context():
        result = inherited.run_case1_pilot_rc4_episode(
            project_root,
            config,
            adapter=adapter,
            openrouter_key=openrouter_key,
            authorization_digest=authorization_digest,
            remaining_cost_cap_usd=remaining_cost_cap_usd,
            output_root=output_root,
            attempt_seed=attempt_seed,
            provider_seed=provider_seed,
            native_client_factory=native_client_factory,
            preflight_mode=preflight_mode,
        )

    # The underlying provider loop is intentionally unchanged.  Authoritative
    # lifecycle facts are reconstructed after it closes and persisted in RC5's
    # summary rather than inferred from optional rollout convenience fields.
    summary = finalize_rc5_run_summary(result.run_root, key=openrouter_key)
    return Case1PilotRunArtifacts(
        run_root=result.run_root,
        workspace_root=result.workspace_root,
        summary_path=result.summary_path,
        request_ledger_path=result.request_ledger_path,
        summary=summary,
    )


grader_assessment = inherited.grader_assessment

__all__ = [
    "RC5_PREFLIGHT_AUTHORIZATION",
    "finalize_rc5_run_summary",
    "grader_assessment",
    "run_case1_pilot_rc5_episode",
]

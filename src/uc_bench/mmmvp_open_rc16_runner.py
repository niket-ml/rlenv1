"""Production runner binding frozen RC1.5 science to the RC1.6 verifier."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

from uc_bench.errors import ConfigurationError
from uc_bench.mmmvp_open_rc14_freeze import read_rc14_release_freeze
from uc_bench.mmmvp_open_rc14_runner import run_rc14_open_mmmvp_episode
from uc_bench.mmmvp_open_rc16_trajectory import rc16_trajectory_replay_check
from uc_bench.mmmvp_open_rc16_verifier import (
    EnvironmentEvidenceError,
    decode_agent_payload_total,
    validate_final_submission_total,
    validate_followup_plan_total,
    validate_validation_plan_total,
    verify_rc16_open_submission,
)
from uc_bench.mmmvp_open_runner import OpenRunArtifacts, OpenRunConfig
from uc_bench.model_runner import _write_json
from uc_bench.v071_auth import credential_locations


def run_rc16_open_mmmvp_episode(
    project_root: Path,
    config: OpenRunConfig,
    *,
    adapter: Any,
    openrouter_key: str,
    authorization_digest: str,
    remaining_cost_cap_usd: float,
) -> OpenRunArtifacts:
    """Use the exact RC1.4 execution surface with only verifier bindings changed."""

    root = project_root.resolve()
    from uc_bench.mmmvp_open_rc16_freeze import read_rc16_release_freeze

    release = read_rc16_release_freeze(root)
    return _run_rc16_episode(
        root,
        config,
        adapter=adapter,
        openrouter_key=openrouter_key,
        authorization_digest=authorization_digest,
        remaining_cost_cap_usd=remaining_cost_cap_usd,
        release=release,
    )


def _run_rc16_episode(
    root: Path,
    config: OpenRunConfig,
    *,
    adapter: Any,
    openrouter_key: str,
    authorization_digest: str,
    remaining_cost_cap_usd: float,
    release: dict[str, Any],
) -> OpenRunArtifacts:
    """Shared frozen and zero-network candidate execution implementation."""

    rc14 = read_rc14_release_freeze(root)
    if authorization_digest != release["infrastructure_digest"]:
        raise ConfigurationError("RC1.6 authorization does not match its freeze")
    with (
        patch(
            "uc_bench.mmmvp_open_rc14_runner.verify_open_submission",
            verify_rc16_open_submission,
        ),
        patch(
            "uc_bench.mmmvp_open_rc14_runner.rc13_trajectory_replay_check",
            rc16_trajectory_replay_check,
        ),
        patch("uc_bench.mmmvp_open_environment._decode", decode_agent_payload_total),
        patch(
            "uc_bench.mmmvp_open_environment.validate_validation_plan",
            validate_validation_plan_total,
        ),
        patch(
            "uc_bench.mmmvp_open_environment.validate_followup_plan",
            validate_followup_plan_total,
        ),
        patch(
            "uc_bench.mmmvp_open_environment.validate_final_submission",
            validate_final_submission_total,
        ),
    ):
        result = run_rc14_open_mmmvp_episode(
            root,
            config,
            adapter=adapter,
            openrouter_key=openrouter_key,
            authorization_digest=rc14["infrastructure_digest"],
            remaining_cost_cap_usd=remaining_cost_cap_usd,
        )
    summary = dict(result.summary)
    summary["schema_version"] = "uc-bench-open-mmmvp-rc1-6-run-1"
    summary["source_rc14_infrastructure_digest"] = rc14["infrastructure_digest"]
    summary["release_infrastructure_digest"] = release["infrastructure_digest"]
    summary["verifier_version"] = "open-mmmvp-rc1-6"
    summary["lifecycle_and_grading_separated"] = True
    grader_exception = summary.get("grader_exception") or {}
    if grader_exception.get("type") == EnvironmentEvidenceError.__name__:
        summary["classification"] = "infrastructure_failure"
        summary["infrastructure_fault"] = "environment_evidence_invalid"
    integrity = summary.get("integrity") or {}
    if not integrity.get("start_state_untampered", False) or not integrity.get(
        "protected_evidence_untampered", False
    ):
        summary["classification"] = "infrastructure_failure"
        summary["infrastructure_fault"] = "environment_evidence_integrity_failure"
    _write_json(result.summary_path, summary, secret=openrouter_key)
    if credential_locations(result.run_root, openrouter_key):
        raise ConfigurationError("Credential leakage after RC1.6 summary persistence")
    return OpenRunArtifacts(
        run_root=result.run_root,
        workspace_root=result.workspace_root,
        summary_path=result.summary_path,
        request_ledger_path=result.request_ledger_path,
        summary=summary,
    )


__all__ = ["run_rc16_open_mmmvp_episode"]

"""Case-1 RC6 runner with canonical grading and request-state adjudication."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import uc_bench.case1_pilot_v1_rc4_runner as inherited
import uc_bench.case1_pilot_v1_rc4_runtime as inherited_runtime
from uc_bench.case1_pilot_v1_rc5_environment import RC5Case1Environment
from uc_bench.case1_pilot_v1_rc5_lock import INHERITED_EXTENSION_LOCK
from uc_bench.case1_pilot_v1_rc5_reporting import reconstruct_lifecycle_or_empty
from uc_bench.case1_pilot_v1_rc6_lifecycle import (
    RC6RequestLedger,
    RequestLifecycleMachine,
    lifecycle_identity,
    transient_failure,
)
from uc_bench.case1_pilot_v1_rc6_runtime import build_rc6_client
from uc_bench.case1_pilot_v1_rc6_trajectory import rc6_trajectory_replay_check
from uc_bench.case1_pilot_v1_rc6_verifier import WEIGHTS, verify_case1_rc6_submission
from uc_bench.case1_pilot_v1_runner import Case1PilotRunArtifacts, Case1PilotRunConfig
from uc_bench.model_runner import _write_json

RC6_PREFLIGHT_AUTHORIZATION = "rc6-unfrozen-fake-provider-preflight"


def _provider_exclusion(lifecycle: RequestLifecycleMachine) -> str | None:
    attempts = lifecycle.attempts
    if not attempts:
        return None
    last = attempts[-1]
    state = last.get("state")
    if state == "transient_transport_failure":
        matching = [
            row
            for row in attempts
            if row.get("logical_request_index") == last.get("logical_request_index")
            and row.get("state") == "transient_transport_failure"
        ]
        chain = last.get("error_chain") or []
        timeout = any(
            "timeout" in str(item.get("type") or "").lower()
            or "timed out" in str(item.get("message") or "").lower()
            for item in chain
            if isinstance(item, dict)
        )
        if len(matching) >= 2 and timeout:
            return "isolated_provider_timeout"
        return "isolated_provider_failure"
    if state == "terminal_provider_failure":
        return "isolated_provider_failure"
    if state == "provider_response_parse_failure":
        return "provider_adapter_failure"
    return None


def finalize_rc6_run_summary(run_root: Path, *, key: str) -> dict[str, Any]:
    """Replace inherited convenience classification with causal RC6 state."""

    run_root = run_root.resolve()
    summary_path = run_root / "run_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    lifecycle_path = run_root / "request_lifecycle.json"
    lifecycle = (
        RequestLifecycleMachine.load(lifecycle_path, secret=key)
        if lifecycle_path.is_file()
        else RequestLifecycleMachine(lifecycle_path, secret=key)
    )
    ledger_path = run_root / "request_ledger.json"
    persisted = json.loads(ledger_path.read_text(encoding="utf-8"))
    ledger = SimpleNamespace(records=persisted["requests"])

    adapter = summary["provider_adapter"]
    identity = lifecycle_identity(
        requested_model=str(summary["model_id"]),
        canonical_alias=str(adapter["expected_canonical_slug"]),
        pinned_provider=str(adapter["provider_order"][0]),
        fallback_disabled=not bool(adapter["allow_fallbacks"]),
        ledger=ledger,
        lifecycle=lifecycle,
    )
    durable = reconstruct_lifecycle_or_empty(run_root)
    durable.update(
        {
            "provider_request_count": len(lifecycle.attempts),
            "model_response_count": identity["completed_response_count"],
        }
    )
    exclusion = _provider_exclusion(lifecycle)
    classification = str(summary.get("classification") or "")
    if exclusion is not None:
        classification = exclusion
        summary["partial_scientific_quality"] = None
        summary["complete_mission_success"] = None
        summary["reliability_score"] = None
        durable["reliability_score"] = None
    elif identity["completed_response_count"] and not identity["compatible"]:
        classification = "provider_identity_failure"
        summary["partial_scientific_quality"] = None
        summary["complete_mission_success"] = None
        summary["reliability_score"] = None
        durable["reliability_score"] = None
    elif summary.get("submission", {}).get("state", {}).get("completion_accepted"):
        classification = "valid_episode"
        durable["reliability_score"] = 100.0
        summary["reliability_score"] = 100.0
    elif classification not in {
        "cost_cap_reached",
        "infrastructure_failure",
        "grader_failure",
        "protected_evidence_tampering",
    }:
        classification = "model_completion_failure"
        summary["reliability_score"] = 0.0
        durable["reliability_score"] = 0.0

    summary.update(
        {
            "schema_version": "uc-bench-case1-pilot-v1-rc6-run-1",
            "classification": classification,
            "provider_identity": identity,
            "request_lifecycle": {
                **lifecycle.verify(),
                "path": "request_lifecycle.json",
                "states": [row["state"] for row in lifecycle.attempts],
            },
            "provider_request_count": len(lifecycle.attempts),
            "effective_provider_request_count": len(
                {row["logical_request_index"] for row in lifecycle.attempts}
            ),
            "authoritative_lifecycle": durable,
            "execution_release_id": "uc-bench-case1-pilot-v1-rc6",
        }
    )
    _write_json(summary_path, summary, secret=key)
    return summary


@contextmanager
def _rc6_production_context() -> Iterator[None]:
    from uc_bench.case1_pilot_v1_rc6_release import read_rc6_freeze

    names = {
        "RC4Case1Environment": RC5Case1Environment,
        "verify_case1_rc4_submission": verify_case1_rc6_submission,
        "rc4_trajectory_replay_check": rc6_trajectory_replay_check,
        "read_rc4_freeze": read_rc6_freeze,
        "RC4_PREFLIGHT_AUTHORIZATION": RC6_PREFLIGHT_AUTHORIZATION,
        "WEIGHTS": WEIGHTS,
        "DurableRequestLedger": RC6RequestLedger,
        "build_rc4_client": build_rc6_client,
    }
    with INHERITED_EXTENSION_LOCK:
        originals = {name: getattr(inherited, name) for name in names}
        original_transient = inherited_runtime._transient  # noqa: SLF001
        try:
            for name, value in names.items():
                setattr(inherited, name, value)
            inherited_runtime._transient = transient_failure  # noqa: SLF001
            yield
        finally:
            inherited_runtime._transient = original_transient  # noqa: SLF001
            for name, value in originals.items():
                setattr(inherited, name, value)


def run_case1_pilot_rc6_episode(
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
    with _rc6_production_context():
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
    summary = finalize_rc6_run_summary(result.run_root, key=openrouter_key)
    return Case1PilotRunArtifacts(
        run_root=result.run_root,
        workspace_root=result.workspace_root,
        summary_path=result.summary_path,
        request_ledger_path=result.request_ledger_path,
        summary=summary,
    )


grader_assessment = inherited.grader_assessment

__all__ = [
    "RC6_PREFLIGHT_AUTHORIZATION",
    "finalize_rc6_run_summary",
    "grader_assessment",
    "run_case1_pilot_rc6_episode",
]

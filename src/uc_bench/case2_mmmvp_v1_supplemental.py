"""Execution-only GPT-5 supplement for the immutable Case 2 MMMVP release.

The final Case 2 scientific release remains unchanged.  This module binds the
already validated GPT-5 provider adapter to that exact scientific surface and
creates a separate authorization record for the additional calibration cell.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from development.case2_graceful import release as scientific_release
from development.case2_graceful import runner as scientific_runner
from development.case2_graceful import trajectory as scientific_replay
from development.case2_graceful_budget import runner as budget_runner

from .case1_pilot_v1_provider import load_case1_pilot_adapters, model_config
from .case2_mmmvp_v1_release import (
    immutable_predecessor_record,
    immutable_release_record,
    read_release_freeze,
)
from .case2_mmmvp_v1_verifier import grade_case2_submission
from .errors import ConfigurationError
from .hashing import canonical_sha256
from .model_runner import _write_json

MODEL_ID = "openai/gpt-5"
SUPPLEMENT_ID = "uc-bench-case2-mmmvp-v1-gpt5-supplement-1"
MAXIMUM_AUTHORIZED_COST_USD = 12.0
OUTPUT_ROOT = Path("artifacts/uc_bench_case2_mmmvp_v1/supplemental_science/runs")
FREEZE_PATH = Path(
    "artifacts/uc_bench_case2_mmmvp_v1/supplemental_science/"
    "gpt5_supplement_freeze.json"
)


def _records(root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Build execution records while locking all scientific inputs to v1."""

    root = root.resolve()
    final = read_release_freeze(root)
    budget_base = immutable_predecessor_record(root)
    scientific_base = immutable_release_record(
        root,
        Path("development/case2_graceful/release_candidate.json"),
        expected_digest=budget_base["predecessor_digest"],
    )
    row = model_config(root, MODEL_ID)
    adapter = load_case1_pilot_adapters(root)[MODEL_ID]
    if adapter.allow_fallbacks or adapter.provider_order != ("OpenAI",):
        raise ConfigurationError("Supplemental GPT-5 route is not singly pinned")
    if adapter.to_dict()["expected_canonical_slug"] != row["canonical_slug"]:
        raise ConfigurationError("Supplemental GPT-5 canonical identity changed")

    science_lock = {
        "case2_release_id": final["release_id"],
        "case2_release_digest": final["aggregate_release_digest"],
        "agent_visible_archive_sha256": final["agent_visible_archive_sha256"],
        "host_only_archive_sha256": final["host_only_archive_sha256"],
        "evidence_manifest_sha256": final["evidence_manifest_sha256"],
        "scientific_request_sha256": scientific_base["request_sha256"],
        "scientific_threshold_sha256": scientific_base["threshold_sha256"],
        "canonical_verifier": (
            "uc_bench.case2_mmmvp_v1_verifier.grade_case2_submission"
        ),
    }

    scientific = copy.deepcopy(scientific_base)
    scientific.update(
        {
            "release_id": f"{SUPPLEMENT_ID}-scientific-binding",
            "model_configuration": [row],
            "provider_adapters": {MODEL_ID: adapter.to_dict()},
            "execution_order": [MODEL_ID],
            "execution_order_policy": "single_explicitly_authorized_supplemental_cell",
            "paid_execution_authorized": True,
            "proposed_scientific_cap_usd": MAXIMUM_AUTHORIZED_COST_USD,
            "scientific_surface_byte_identical": True,
            "allowed_changes": ["model_panel_addition_only"],
            "status": "frozen_execution_only_supplement",
        }
    )
    scientific_digest = canonical_sha256(
        {
            "schema_version": "uc-bench-case2-supplemental-scientific-binding-1",
            "base_scientific_digest": scientific_base["closure"]["aggregate_digest"],
            "science_lock": science_lock,
            "model_configuration": [row],
            "provider_adapter": adapter.to_dict(),
            "execution_limits": scientific_base["execution_limits"],
        }
    )
    scientific["closure"] = copy.deepcopy(scientific_base["closure"])
    scientific["closure"]["aggregate_digest"] = scientific_digest

    budget = copy.deepcopy(budget_base)
    budget.update(
        {
            "release_id": SUPPLEMENT_ID,
            "model_configuration": [row],
            "provider_adapters": {MODEL_ID: adapter.to_dict()},
            "execution_order": [MODEL_ID],
            "execution_order_policy": "single_explicitly_authorized_supplemental_cell",
            "paid_execution_authorized": True,
            "authorized_cumulative_incremental_cap_usd": MAXIMUM_AUTHORIZED_COST_USD,
            "proposed_scientific_cap_usd": MAXIMUM_AUTHORIZED_COST_USD,
            "predecessor_release": scientific["release_id"],
            "predecessor_digest": scientific_digest,
            "scientific_surface_byte_identical": True,
            "allowed_changes": ["model_panel_addition_only"],
            "status": "frozen_execution_only_supplement",
        }
    )
    budget_digest = canonical_sha256(
        {
            "schema_version": "uc-bench-case2-gpt5-supplement-freeze-1",
            "base_budget_digest": budget_base["closure"]["aggregate_digest"],
            "scientific_binding_digest": scientific_digest,
            "science_lock": science_lock,
            "model_configuration": [row],
            "provider_adapter": adapter.to_dict(),
            "execution_limits": budget_base["execution_limits"],
            "maximum_authorized_cost_usd": MAXIMUM_AUTHORIZED_COST_USD,
        }
    )
    budget["closure"] = copy.deepcopy(budget_base["closure"])
    budget["closure"]["aggregate_digest"] = budget_digest

    freeze = {
        "schema_version": "uc-bench-case2-gpt5-supplement-freeze-1",
        "release_id": SUPPLEMENT_ID,
        "aggregate_digest": budget_digest,
        "created_at": datetime.now(UTC).isoformat(),
        "status": "FROZEN EXECUTION-ONLY SUPPLEMENT",
        "model_id": MODEL_ID,
        "canonical_model_slug": row["canonical_slug"],
        "provider": row["provider"],
        "fallbacks_disabled": True,
        "attempt_seed": row["attempt_seed"],
        "provider_seed": row.get("provider_seed"),
        "maximum_authorized_cost_usd": MAXIMUM_AUTHORIZED_COST_USD,
        "science_lock": science_lock,
        "base_case2_panel_unchanged": True,
        "original_case2_release_remains_immutable": True,
        "supplemental_scientific_binding": scientific,
        "supplemental_budget_binding": budget,
    }
    return freeze, scientific, budget


def create_or_read_freeze(root: Path) -> dict[str, Any]:
    root = root.resolve()
    expected, _, _ = _records(root)
    path = root / FREEZE_PATH
    if path.is_file():
        observed = json.loads(path.read_text(encoding="utf-8"))
        # Time is documentary and excluded from the authorization digest.
        expected["created_at"] = observed.get("created_at")
        if observed != expected:
            raise ConfigurationError("Supplemental GPT-5 freeze changed")
        return observed
    _write_json(path, expected)
    return expected


@contextmanager
def _supplemental_runtime(
    scientific: dict[str, Any], budget: dict[str, Any]
) -> Iterator[None]:
    old = {
        "budget_candidate": budget_runner.candidate_manifest,
        "budget_freeze": budget_runner.read_freeze,
        "predecessor_candidate": budget_runner.predecessor_candidate,
        "predecessor_freeze": budget_runner.predecessor_freeze,
        "scientific_candidate": scientific_release.candidate_manifest,
        "scientific_freeze": scientific_release.read_freeze,
        "verifier": scientific_runner.verify_case2_rc1_submission,
        "replay_verifier": scientific_replay.verify_case2_rc1_submission,
    }
    budget_runner.candidate_manifest = lambda _root: budget
    budget_runner.read_freeze = lambda _root: budget
    budget_runner.predecessor_candidate = lambda _root: scientific
    budget_runner.predecessor_freeze = lambda _root: scientific
    scientific_release.candidate_manifest = lambda _root: scientific
    scientific_release.read_freeze = lambda _root: scientific
    scientific_runner.verify_case2_rc1_submission = grade_case2_submission
    scientific_replay.verify_case2_rc1_submission = grade_case2_submission
    try:
        yield
    finally:
        budget_runner.candidate_manifest = old["budget_candidate"]
        budget_runner.read_freeze = old["budget_freeze"]
        budget_runner.predecessor_candidate = old["predecessor_candidate"]
        budget_runner.predecessor_freeze = old["predecessor_freeze"]
        scientific_release.candidate_manifest = old["scientific_candidate"]
        scientific_release.read_freeze = old["scientific_freeze"]
        scientific_runner.verify_case2_rc1_submission = old["verifier"]
        scientific_replay.verify_case2_rc1_submission = old["replay_verifier"]


def run_gpt5_supplement(
    root: Path,
    *,
    openrouter_key: str,
    run_id: str,
    cost_cap_usd: float,
    output_root: Path | None = None,
    native_client_factory: Callable[..., Any] | None = None,
) -> Any:
    """Run the single authorized GPT-5 cell without mutating the v1 release."""

    root = root.resolve()
    if not 0 < cost_cap_usd <= MAXIMUM_AUTHORIZED_COST_USD:
        raise ConfigurationError("GPT-5 supplemental cost cap is outside authorization")
    freeze = create_or_read_freeze(root)
    scientific = freeze["supplemental_scientific_binding"]
    budget = freeze["supplemental_budget_binding"]
    row = model_config(root, MODEL_ID)
    adapter = load_case1_pilot_adapters(root)[MODEL_ID]
    destination = (output_root or (root / OUTPUT_ROOT)).resolve()

    with _supplemental_runtime(scientific, budget):
        result = budget_runner.run_case2_episode(
            root,
            budget_runner.Case2RunConfig(run_id, MODEL_ID),
            adapter=adapter,
            openrouter_key=openrouter_key,
            authorization_digest=freeze["aggregate_digest"],
            remaining_cost_cap_usd=cost_cap_usd,
            output_root=destination,
            attempt_seed=int(row["attempt_seed"]),
            provider_seed=row.get("provider_seed"),
            native_client_factory=native_client_factory,
            preflight_mode=False,
            scientific_authorization=freeze["aggregate_digest"],
        )

    authorization = {
        "schema_version": "uc-bench-case2-gpt5-supplement-run-1",
        "supplemental_release_id": SUPPLEMENT_ID,
        "supplemental_release_digest": freeze["aggregate_digest"],
        "base_case2_release_digest": freeze["science_lock"]["case2_release_digest"],
        "model_id": MODEL_ID,
        "cost_cap_usd": cost_cap_usd,
        "scientific_surface_byte_identical": True,
        "original_panel_membership_changed": False,
        "interpretation": "supplemental calibration cell; not part of the frozen panel",
    }
    _write_json(
        result.run_root / "supplemental_authorization.json",
        authorization,
        secret=openrouter_key,
    )
    summary = dict(result.summary)
    summary.update(
        {
            "supplemental_release_id": SUPPLEMENT_ID,
            "supplemental_release_digest": freeze["aggregate_digest"],
            "base_case2_release_id": freeze["science_lock"]["case2_release_id"],
            "base_case2_release_digest": freeze["science_lock"][
                "case2_release_digest"
            ],
            "canonical_verifier": freeze["science_lock"]["canonical_verifier"],
            "interpretation": (
                "supplemental GPT-5 calibration cell; original Case 2 panel unchanged"
            ),
        }
    )
    _write_json(result.summary_path, summary, secret=openrouter_key)
    return result.__class__(
        run_root=result.run_root,
        workspace_root=result.workspace_root,
        summary_path=result.summary_path,
        request_ledger_path=result.request_ledger_path,
        summary=summary,
    )


__all__ = [
    "FREEZE_PATH",
    "MAXIMUM_AUTHORIZED_COST_USD",
    "MODEL_ID",
    "OUTPUT_ROOT",
    "SUPPLEMENT_ID",
    "create_or_read_freeze",
    "run_gpt5_supplement",
]

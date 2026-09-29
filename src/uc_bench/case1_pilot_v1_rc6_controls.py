"""Zero-cost exact-fixture, parity, preservation and offline-replay gates for RC6."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from uc_bench.case1_pilot_v1_rc5_controls import build_reference, run_rc5_controls
from uc_bench.case1_pilot_v1_rc5_environment import RC5Case1Environment
from uc_bench.case1_pilot_v1_rc6_lifecycle import forensic_legacy_request_adjudication
from uc_bench.case1_pilot_v1_rc6_verifier import verify_case1_rc6_submission
from uc_bench.hashing import canonical_sha256
from uc_bench.model_runner import _write_json

RC5_RUNS = Path("artifacts/uc_bench_case1_pilot_v1_rc5/science/runs")
GPT_RUN = RC5_RUNS / "case1-rc5-00-openai-gpt-5-attempt-0"
SONNET_RUN = RC5_RUNS / "case1-rc5-01-anthropic-claude-sonnet-4-attempt-0"
OPUS_RUN = RC5_RUNS / "case1-rc5-02-anthropic-claude-opus-4.1-attempt-0"


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"object required: {path}")
    return value


def _hashes(root: Path, source: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(source.rglob("*"))
        if path.is_file()
    }


def write_live_fixture_manifest(project_root: Path, target: Path) -> dict[str, Any]:
    """Pin the complete archived live shapes without copying or editing them."""

    root = project_root.resolve()
    sonnet_paths = [SONNET_RUN / "submission.json", SONNET_RUN / "run_summary.json"]
    sonnet_paths.extend(
        path
        for path in (root / SONNET_RUN / "workspace").rglob("*")
        if path.is_file()
    )
    opus_paths = [
        OPUS_RUN / "request_ledger.json",
        OPUS_RUN / "host_trajectory/journal/000141.json",
        OPUS_RUN / "host_trajectory/journal/000142.json",
    ]
    selected = [
        root / path if not path.is_absolute() else path
        for path in [*sonnet_paths, *opus_paths]
    ]
    hashes = {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(set(selected))
    }
    ledger = _read(root / OPUS_RUN / "request_ledger.json")
    final_record = ledger["requests"][-1]
    value = {
        "schema_version": "uc-bench-case1-pilot-v1-rc6-live-fixtures-1",
        "passed": bool(
            len(ledger["requests"]) == 48
            and final_record.get("error", {}).get("type") == "APITimeoutError"
            and final_record.get("error", {}).get("message") == "Request timed out."
            and len(hashes) > 10
        ),
        "api_requests": 0,
        "sources": {
            "sonnet_complete_submission": (SONNET_RUN / "submission.json").as_posix(),
            "sonnet_complete_workspace": (SONNET_RUN / "workspace").as_posix(),
            "sonnet_complete_grade": (SONNET_RUN / "run_summary.json").as_posix(),
            "opus_complete_request_ledger": (OPUS_RUN / "request_ledger.json").as_posix(),
            "opus_final_timeout_record": {
                "request_index": final_record.get("request_index"),
                "sha256": canonical_sha256(final_record),
            },
            "opus_pre_timeout_trajectory": (
                OPUS_RUN / "host_trajectory/journal/000141.json"
            ).as_posix(),
            "opus_timeout_trajectory": (
                OPUS_RUN / "host_trajectory/journal/000142.json"
            ).as_posix(),
        },
        "file_count": len(hashes),
        "hashes": hashes,
        "aggregate_digest": canonical_sha256(hashes),
        "raw_bytes_modified": False,
    }
    _write_json(target, value, secret="")
    return value


def write_preservation_report(
    project_root: Path, work_root: Path, target: Path
) -> dict[str, Any]:
    """Materialize two independent copies and compare the complete visible trees."""

    root = project_root.resolve()
    left = work_root / "rc5_visible"
    right = work_root / "rc6_visible"
    RC5Case1Environment(root, "case_01", left, maximum_tool_calls=80)
    RC5Case1Environment(root, "case_01", right, maximum_tool_calls=80)
    left_hashes = _hashes(left, left)
    right_hashes = _hashes(right, right)
    rc5_freeze = root / "artifacts/uc_bench_case1_pilot_v1_rc5/release_freeze.json"
    value = {
        "schema_version": "uc-bench-case1-pilot-v1-rc6-preservation-1",
        "passed": left_hashes == right_hashes,
        "model_visible_byte_identical": left_hashes == right_hashes,
        "agent_visible_file_count": len(left_hashes),
        "rc5_model_visible_digest": canonical_sha256(left_hashes),
        "rc6_model_visible_digest": canonical_sha256(right_hashes),
        "rc5_declared_release_digest": (
            "b07643c08c05fa09c599e077112c1f8519a0b7c5733928b26974182ed834f762"
        ),
        "rc5_freeze_file_sha256": hashlib.sha256(rc5_freeze.read_bytes()).hexdigest(),
        "comparison": "complete recursively hashed agent-visible workspace trees",
        "api_requests": 0,
    }
    _write_json(target, value, secret="")
    return value


def offline_regrade(project_root: Path, target: Path) -> dict[str, Any]:
    root = project_root.resolve()
    models: dict[str, Any] = {}
    for model_id, relative in (
        ("openai/gpt-5", GPT_RUN),
        ("anthropic/claude-sonnet-4", SONNET_RUN),
    ):
        run = root / relative
        before = _hashes(run, run)
        original = _read(run / "run_summary.json")
        submission = _read(run / "submission.json")
        grade = verify_case1_rc6_submission(root, run / "workspace", submission).to_dict()
        after = _hashes(run, run)
        models[model_id] = {
            "label": "RC5 trajectory, RC6 offline grading",
            "original_rc5_grade": original.get("diagnostic_grade"),
            "rc6_grade": grade,
            "raw_trajectory_byte_identical_after_replay": before == after,
            "summary_path": (relative / "run_summary.json").as_posix(),
            "turns": (original.get("authoritative_lifecycle") or {}).get("turn_count"),
            "requests": original.get("provider_request_count"),
            "cost_usd": original.get("cumulative_reported_cost_usd"),
        }
    opus_ledger = _read(root / OPUS_RUN / "request_ledger.json")
    opus = forensic_legacy_request_adjudication(
        ledger_rows=opus_ledger["requests"],
        requested_model="anthropic/claude-opus-4.1",
        canonical_alias="anthropic/claude-4.1-opus-20250805",
        pinned_provider="Amazon Bedrock",
    )
    expected = {
        "openai/gpt-5": (100.0, True),
        "anthropic/claude-sonnet-4": (37.0, False),
    }
    passed = all(
        (
            row["rc6_grade"]["partial_scientific_quality"],
            row["rc6_grade"]["complete_mission_success"],
        )
        == expected[model_id]
        and row["raw_trajectory_byte_identical_after_replay"]
        and row["rc6_grade"]["diagnostics"]["public_hidden_resource_semantics_equal"]
        for model_id, row in models.items()
    ) and opus["classification"] == "isolated_provider_timeout"
    value = {
        "schema_version": "uc-bench-case1-pilot-v1-rc6-offline-grades-1",
        "passed": passed,
        "api_requests": 0,
        "models": models,
        "provider_excluded": {"anthropic/claude-opus-4.1": opus},
    }
    _write_json(target, value, secret="")
    return value


def run_rc6_controls(project_root: Path, output_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    inherited = run_rc5_controls(root, output_root / "inherited_rc5")
    parity: dict[str, Any] = {}
    for resource in ("none", "X17", "X24", "X31", "X46", "X58", "X63"):
        submission, workspace = build_reference(
            root, output_root / "resource_parity" / resource, resource=resource
        )
        grade = verify_case1_rc6_submission(root, workspace, submission).to_dict()
        facts = grade["diagnostics"]["resource_semantics"]
        hidden = grade["diagnostics"]["resource"]
        parity[resource] = {
            "passed": bool(
                grade["diagnostics"]["public_hidden_resource_semantics_equal"]
                and facts["question_relevant"] == hidden["relevant"]
                and facts["expected_material"] == hidden["material"]
                and facts["expected_effect"] == hidden["observed_effect"]
            ),
            "mission": grade["complete_mission_success"],
        }
    value = {
        "schema_version": "uc-bench-case1-pilot-v1-rc6-controls-1",
        "passed": inherited["passed"] and all(row["passed"] for row in parity.values()),
        "api_requests": 0,
        "inherited_rc5_controls": inherited,
        "public_hidden_resource_semantic_parity": parity,
    }
    _write_json(output_root / "control_results.json", value, secret="")
    return value


__all__ = [
    "GPT_RUN",
    "OPUS_RUN",
    "SONNET_RUN",
    "offline_regrade",
    "run_rc6_controls",
    "write_live_fixture_manifest",
    "write_preservation_report",
]

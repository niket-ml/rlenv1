"""Evidence-citing common-grader report for Case-1 RC6."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from uc_bench.case1_pilot_v1_provider import model_config
from uc_bench.case1_pilot_v1_rc6_controls import OPUS_RUN
from uc_bench.case1_pilot_v1_rc6_execution import STATE_PATH
from uc_bench.case1_pilot_v1_rc6_release import OFFLINE_REPLAY_PATH, read_rc6_freeze
from uc_bench.errors import ConfigurationError
from uc_bench.model_runner import _write_json

REPORT_PATH = Path("artifacts/uc_bench_case1_pilot_v1_rc6/science/pilot_report.json")
MANUAL_PATH = Path("artifacts/uc_bench_case1_pilot_v1_rc6/science/manual_adjudications.json")


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigurationError(f"JSON object required: {path}")
    return value


def _properties(grade: dict[str, Any]) -> list[dict[str, Any]]:
    points = (grade.get("diagnostics") or {}).get("property_points") or {}
    return [
        {
            "requirement_id": row.get("requirement_id"),
            "passed": row.get("passed"),
            "points": points.get(row.get("requirement_id")),
            "observed": row.get("observed"),
            "consequence": row.get("consequence"),
            "remedy": row.get("remedy"),
            "evidence": row.get("evidence") or [],
        }
        for row in grade.get("requirements") or []
        if isinstance(row, dict)
    ]


def _scientific_row(
    model_id: str,
    grade: dict[str, Any],
    summary: dict[str, Any],
    *,
    provenance: str,
    manual: dict[str, Any] | None,
) -> dict[str, Any]:
    final = (summary.get("submission") or {}).get("final_submission") or {}
    followup = (summary.get("submission") or {}).get("followup_plan") or {}
    lifecycle = summary.get("authoritative_lifecycle") or {}
    return {
        "model_id": model_id,
        "provenance": provenance,
        "classification": summary.get("classification"),
        "strict_mission_success": grade.get("complete_mission_success"),
        "partial_scientific_quality": grade.get("partial_scientific_quality"),
        "reliability": summary.get("reliability_score"),
        "scientific_properties": _properties(grade),
        "first_genuine_failure": grade.get("first_decision_critical_failure"),
        "downstream_consequences": [
            row.get("consequence")
            for row in grade.get("requirements") or []
            if isinstance(row, dict) and row.get("passed") is False
        ],
        "purchased_resource": lifecycle.get("resource_purchased")
        or followup.get("chosen_resource"),
        "resource_semantics": (grade.get("diagnostics") or {}).get("resource_semantics"),
        "belief_change": final.get("belief_updates"),
        "final_decision": lifecycle.get("final_decision") or final.get("decision"),
        "claim_scope": final.get("claims"),
        "turns": lifecycle.get("turn_count"),
        "requests": summary.get("provider_request_count"),
        "cost_usd": summary.get("cumulative_reported_cost_usd"),
        "manual_adjudication": manual,
    }


def _opus_projection(root: Path) -> dict[str, Any]:
    ledger = _read(root / OPUS_RUN / "request_ledger.json")
    row = model_config(root, "anthropic/claude-opus-4.1")
    price = row["maximum_route_price_usd_per_million"]
    prompt = sum(
        int((request.get("usage") or {}).get("prompt_tokens") or 0)
        for request in ledger["requests"]
    )
    completion = sum(
        int((request.get("usage") or {}).get("completion_tokens") or 0)
        for request in ledger["requests"]
    )
    no_cache = (
        prompt * float(price["prompt"]) + completion * float(price["completion"])
    ) / 1_000_000
    reported = sum(float(request.get("reported_cost_usd") or 0) for request in ledger["requests"])
    # One observed near-complete attempt is not an empirical percentile.  The
    # predeclared planning P90 uses 1.25x its uncached route-ceiling estimate.
    p90 = no_cache * 1.25
    return {
        "basis": "RC5 Opus requests 1-47 plus 25% one-run uncertainty allowance",
        "observed_prompt_tokens": prompt,
        "observed_completion_tokens": completion,
        "observed_reported_cost_usd": round(reported, 8),
        "route_ceiling_no_cache_estimate_usd": round(no_cache, 8),
        "planning_no_cache_p90_usd": round(p90, 8),
        "warning": "planning bound from one near-complete trajectory, not an empirical P90",
    }


def build_report(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    release = read_rc6_freeze(root)
    offline = _read(root / OFFLINE_REPLAY_PATH)
    state = _read(root / STATE_PATH)
    manual = _read(root / MANUAL_PATH).get("models", {}) if (root / MANUAL_PATH).is_file() else {}
    rows: list[dict[str, Any]] = []
    for model_id, record in offline["models"].items():
        summary = _read(root / record["summary_path"])
        rows.append(
            _scientific_row(
                model_id,
                record["rc6_grade"],
                summary,
                provenance="RC5 trajectory, RC6 offline grading",
                manual=manual.get(model_id),
            )
        )
    for relative in state.get("summary_paths") or []:
        summary = _read(root / relative)
        grade = summary.get("diagnostic_grade")
        if isinstance(grade, dict):
            rows.append(
                _scientific_row(
                    str(summary["model_id"]),
                    grade,
                    summary,
                    provenance="fresh RC6 trajectory, RC6 grading",
                    manual=manual.get(str(summary["model_id"])),
                )
            )
    scores = [float(row["partial_scientific_quality"]) for row in rows]
    mission = [row["strict_mission_success"] for row in rows]
    failures = [
        (row.get("first_genuine_failure") or {}).get("requirement_id")
        for row in rows
        if row.get("strict_mission_success") is False
    ]
    opus = offline["provider_excluded"]["anthropic/claude-opus-4.1"]
    projection = _opus_projection(root)
    funding = (
        state.get("funding_after_science")
        or state.get("funding_immediately_before_science")
        or {}
    )
    projection["additional_account_balance_required_usd"] = round(
        max(
            0.0,
            projection["planning_no_cache_p90_usd"]
            - float(funding.get("account_remaining_usd") or 0),
        ),
        8,
    )
    projection["additional_key_limit_required_usd"] = round(
        max(
            0.0,
            projection["planning_no_cache_p90_usd"]
            - float(funding.get("key_limit_remaining_usd") or 0),
        ),
        8,
    )
    first_concentration = max(
        (failures.count(item) / len(failures) for item in set(failures)), default=None
    )
    all_clean = len(rows) == 4 and all(row["reliability"] == 100.0 for row in rows)
    all_pass = len(rows) == 4 and all(mission)
    return {
        "schema_version": "uc-bench-case1-pilot-v1-rc6-report-1",
        "scope": "single-attempt Case 1 development pilot; not a stable ranking",
        "release_digest": release["closure"]["aggregate_digest"],
        "models": rows,
        "provider_excluded": {
            "model_id": "anthropic/claude-opus-4.1",
            **opus,
            "reason": (
                "request 48 returned no response after 47 exact pinned identities; "
                "identity was not implicated"
            ),
        },
        "descriptive_summary": {
            "scientifically_scored_models": len(rows),
            "strict_missions_passed": sum(value is True for value in mission),
            "mean_partial_scientific_quality": sum(scores) / len(scores) if scores else None,
            "first_failure_concentration": first_concentration,
            "fresh_rc6_spend_usd": state.get("scientific_spend_usd"),
        },
        "construct_interpretation": {
            "ceiling_warning": all_clean and all_pass,
            "genuine_scientific_separation": len(set(scores)) > 1 if len(scores) > 1 else False,
            "credible_floor": bool(scores) and min(scores) > 0,
            "artificial_completion_or_contract_floor": any(
                (row.get("manual_adjudication") or {}).get("artificial_floor") is True
                for row in rows
            ),
            "concentrated_failure_on_one_step": (
                first_concentration is not None and first_concentration > 0.5
            ),
            "stable_ranking_claim_allowed": False,
        },
        "architecture_port_decision": {
            "go": bool(
                state.get("status") == "completed_mandatory_review"
                and not state.get("global_stop_faults")
                and all(
                    row.get("manual_adjudication") is not None
                    for row in rows
                    if row["strict_mission_success"] is False
                )
            ),
            "scope": (
                "port resource/lifecycle architecture to Cases 2-4; do not infer "
                "their scientific validity"
            ),
        },
        "future_fresh_opus_cost": projection,
        "global_stop_faults": state.get("global_stop_faults") or [],
        "prohibited_requests": {
            "case2": state.get("case2_requests"),
            "other_cases": state.get("other_case_requests"),
            "sol": state.get("sol_requests"),
            "astra": state.get("astra_requests"),
            "fresh_opus": state.get("opus_requests"),
        },
    }


def write_report(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    value = build_report(root)
    _write_json(root / REPORT_PATH, value, secret="")
    return value


__all__ = ["MANUAL_PATH", "REPORT_PATH", "build_report", "write_report"]

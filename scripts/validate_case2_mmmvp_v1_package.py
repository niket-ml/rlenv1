#!/usr/bin/env python3
"""Scientific and lifecycle validation executed from an extracted host package."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
from pathlib import Path

from development.case2_graceful.preflight import FAKE_KEY, FakeProvider, reference_actions
from development.case2_graceful.test_graceful import reference
from uc_bench import case2_pilot_v1_rc1_controls as controls
from uc_bench.case2_mmmvp_v1_runner import (
    PREFLIGHT_AUTHORIZATION,
    Case2RunConfig,
    run_case2_episode,
)
from uc_bench.case2_mmmvp_v1_verifier import grade_case2_submission
from uc_bench.case2_pilot_v1_rc1_provider import load_case2_adapters, model_config

ROOT = Path(__file__).resolve().parents[1]
MODEL = "google/gemini-3.1-pro-preview"
HOST_ONLY_SENTINEL = "CASE2_MMMVP_HOST_ONLY_ENVIRONMENT_SENTINEL_914"


def _statuses(grade):
    return {row.requirement_id: bool(row.passed) for row in grade.requirements}


def _fake_run(tmp: Path, run_id: str, *, incomplete=False, mode="normal"):
    adapter = load_case2_adapters(ROOT)[MODEL]
    row = model_config(ROOT, MODEL)
    actions = reference_actions(tmp / f"source-{run_id}", incomplete=incomplete)
    captures = []

    def factory(**constructor):
        return FakeProvider(
            captures,
            actions=actions,
            provider=adapter.provider_order[0],
            mode=mode,
            **constructor,
        )

    result = run_case2_episode(
        ROOT,
        Case2RunConfig(run_id, MODEL, minimum_request_interval_seconds=0),
        adapter=adapter,
        openrouter_key=FAKE_KEY,
        authorization_digest=PREFLIGHT_AUTHORIZATION,
        remaining_cost_cap_usd=2,
        output_root=tmp / "runs",
        attempt_seed=int(row["attempt_seed"]),
        provider_seed=row.get("provider_seed"),
        native_client_factory=factory,
        preflight_mode=True,
    )
    return result, captures


def validate() -> dict:
    os.environ["CASE2_MMMVP_HOST_ONLY_SENTINEL"] = HOST_ONLY_SENTINEL
    with tempfile.TemporaryDirectory(prefix="case2-mmmvp-exact-package-") as raw:
        tmp = Path(raw)
        correct, correct_workspace = reference(tmp / "correct", resource="none", aggregation="MEAN")
        alternative, alternative_workspace = reference(
            tmp / "alternative", resource="X17", aggregation="NONE"
        )
        correct_grade = grade_case2_submission(correct_workspace, correct)
        alternative_grade = grade_case2_submission(alternative_workspace, alternative)

        wrong, wrong_workspace = reference(tmp / "wrong")
        wrong = copy.deepcopy(wrong)
        wrong_final = copy.deepcopy(wrong["final_submission"])
        probability = next(
            row for row in wrong_final["calculations"] if row["metric"] == "BRIER_SCORE"
        )
        probability["unit_of_analysis"] = "SOURCE_RECORD"
        controls.replace_final(wrong, wrong_workspace, wrong_final)
        wrong_grade = grade_case2_submission(wrong_workspace, wrong)

        original, _ = reference(tmp / "hardcoded-original")
        altered, altered_workspace = reference(tmp / "hardcoded-altered", altered=True)
        altered_final = copy.deepcopy(altered["final_submission"])
        stale = {
            row["calculation_id"]: row["reported_value"]
            for row in original["final_submission"]["calculations"]
        }
        for row in altered_final["calculations"]:
            if row["calculation_id"] in stale:
                row["reported_value"] = stale[row["calculation_id"]]
        controls.replace_final(altered, altered_workspace, altered_final)
        hardcoded_grade = grade_case2_submission(altered_workspace, altered)

        malformed_grades = [
            grade_case2_submission(tmp / "missing-workspace", value, require_host_process=False)
            for value in (None, [], {}, {"final_submission": {"calculations": [None]}})
        ]
        repeat = grade_case2_submission(alternative_workspace, alternative)

        lifecycle, captures = _fake_run(tmp, "full-lifecycle")
        incomplete, _ = _fake_run(tmp, "incomplete-lifecycle", incomplete=True)
        provider, _ = _fake_run(tmp, "provider-failure", mode="provider_error")

        event_names = [
            row.get("event")
            for row in (lifecycle.summary.get("submission") or {}).get("event_log") or []
        ]
        run_bytes = b"\n".join(
            path.read_bytes() for path in lifecycle.run_root.rglob("*") if path.is_file()
        )
        workspace_bytes = b"\n".join(
            path.read_bytes()
            for path in lifecycle.workspace_root.rglob("*")
            if path.is_file()
        )
        lifecycle_grade = lifecycle.summary.get("diagnostic_grade") or {}
        lifecycle_properties = {
            row["requirement_id"]: bool(row["passed"])
            for row in lifecycle_grade.get("requirements") or []
        }
        verifier_path = Path(grade_case2_submission.__code__.co_filename).resolve()
        results = {
            "imported_verifier": str(verifier_path),
            "canonical_entrypoint_in_package": str(verifier_path).startswith(str(ROOT)),
            "correct_reference": {
                "mission": correct_grade.complete_mission_success,
                "partial": correct_grade.partial_scientific_quality,
            },
            "materially_different_valid_workflow": {
                "mission": alternative_grade.complete_mission_success,
                "partial": alternative_grade.partial_scientific_quality,
                "different_aggregation": True,
                "different_resource": True,
            },
            "plausible_wrong_workflow": {
                "mission": wrong_grade.complete_mission_success,
                "failed_properties": [
                    key for key, value in _statuses(wrong_grade).items() if not value
                ],
            },
            "hardcoded_answer_on_altered_input": {
                "mission": hardcoded_grade.complete_mission_success,
            },
            "malformed_containment": all(
                not grade.complete_mission_success for grade in malformed_grades
            ),
            "deterministic_regrade": (
                correct_grade.to_dict()
                == grade_case2_submission(correct_workspace, correct).to_dict()
                and alternative_grade.to_dict() == repeat.to_dict()
            ),
            "full_lifecycle": {
                "mission": lifecycle.summary.get("complete_mission_success"),
                "trajectory_replay": lifecycle.summary.get("trajectory_replay", {}).get("passed"),
                "provider_capture_count": len(captures),
                "events": event_names,
                "has_commit": "commit_validation_plan" in event_names,
                "has_reveal": "reveal_validation" in event_names,
                "has_purchase": "purchase_resource" in event_names,
                "has_submit": "submit" in event_names,
                "all_properties_pass": all(lifecycle_properties.values()),
            },
            "incomplete_usable": {
                "mission": incomplete.summary.get("complete_mission_success"),
                "partial": incomplete.summary.get("partial_scientific_quality"),
                "reliability": incomplete.summary.get("reliability_score"),
                "classification": incomplete.summary.get("classification"),
            },
            "provider_failure": {
                "classification": provider.summary.get("classification"),
                "mission_score": provider.summary.get("complete_mission_success"),
                "partial_score": provider.summary.get("partial_scientific_quality"),
                "reliability_score": provider.summary.get("reliability_score"),
            },
            "credentials_absent": FAKE_KEY.encode() not in run_bytes,
            "host_environment_absent": HOST_ONLY_SENTINEL.encode() not in workspace_bytes,
            "network_isolation": (
                (lifecycle.summary.get("isolation") or {}).get("network_mode") == "none"
                and lifecycle.summary.get("agent_network_enabled") is False
            ),
            "workspace_boundary_enforced": (
                lifecycle.summary.get("integrity") or {}
            ).get("workspace_boundary_enforced")
            is True,
            "underlying_artifacts_verified": all(
                row.get("recomputed_value") is not None
                for row in (lifecycle_grade.get("diagnostics") or {})
                .get("calculations", {})
                .values()
                if isinstance(row, dict) and row.get("reported_value") is not None
            ),
            "run_tree_sha256": hashlib.sha256(run_bytes).hexdigest(),
        }
        checks = {
            "reference_passes": correct_grade.complete_mission_success,
            "alternative_passes": alternative_grade.complete_mission_success,
            "wrong_science_fails": not wrong_grade.complete_mission_success,
            "hardcoded_altered_fails": not hardcoded_grade.complete_mission_success,
            "malformed_is_contained": results["malformed_containment"],
            "regrade_is_deterministic": results["deterministic_regrade"],
            "full_lifecycle_passes": all(
                (
                    results["full_lifecycle"]["mission"],
                    results["full_lifecycle"]["trajectory_replay"],
                    results["full_lifecycle"]["has_commit"],
                    results["full_lifecycle"]["has_reveal"],
                    results["full_lifecycle"]["has_purchase"],
                    results["full_lifecycle"]["has_submit"],
                )
            ),
            "incomplete_preserves_partial_but_zeroes_reliability": (
                not results["incomplete_usable"]["mission"]
                and float(results["incomplete_usable"]["partial"] or 0) > 0
                and results["incomplete_usable"]["reliability"] == 0
            ),
            "provider_failure_is_not_science": (
                str(results["provider_failure"]["classification"]).startswith("isolated_provider")
                and results["provider_failure"]["mission_score"] is None
                and results["provider_failure"]["partial_score"] is None
            ),
            "credential_redaction": results["credentials_absent"],
            "host_environment_redaction": results["host_environment_absent"],
            "network_isolation": results["network_isolation"],
            "filesystem_boundary": results["workspace_boundary_enforced"],
            "package_import_used": results["canonical_entrypoint_in_package"],
            "numerical_recomputation_present": results["underlying_artifacts_verified"],
        }
        return {
            "schema_version": "uc-bench-case2-mmmvp-v1-exact-package-validation-1",
            "results": results,
            "checks": checks,
            "passed": all(checks.values()),
            "network_calls": 0,
            "paid_model_calls": 0,
        }


def main() -> int:
    result = validate()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

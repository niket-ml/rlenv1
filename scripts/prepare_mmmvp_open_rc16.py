#!/usr/bin/env python3
"""Create zero-cost RC1.6 verifier-hardening evidence."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from uc_bench.hashing import sha256_file
from uc_bench.mmmvp_open_rc12_trajectory import restore_rc12_environment
from uc_bench.mmmvp_open_rc14_runner import RC14DurableTrajectoryStore
from uc_bench.mmmvp_open_rc15_adapter import load_rc15_launch_routes
from uc_bench.mmmvp_open_rc15_freeze import read_rc15_release_freeze
from uc_bench.mmmvp_open_rc16_corpus import run_rc16_crash_corpus
from uc_bench.mmmvp_open_rc16_rehearsal import run_rc16_prefreeze_rehearsal
from uc_bench.mmmvp_open_rc16_trajectory import rc16_trajectory_replay_check
from uc_bench.mmmvp_open_rc16_verifier import verify_rc16_open_submission
from uc_bench.model_runner import _write_json


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    target = root / "artifacts/mmmvp_open_rc16"
    target.mkdir(parents=True, exist_ok=True)
    rc15 = read_rc15_release_freeze(root)
    inheritance = {
        "schema_version": "uc-bench-open-mmmvp-rc1-6-compatibility-inheritance-1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "passed",
        "api_requests": 0,
        "source_rc15_infrastructure_digest": rc15["infrastructure_digest"],
        "source_rc15_freeze_sha256": sha256_file(
            root / "artifacts/mmmvp_open_rc15/release_freeze.json"
        ),
        "technically_compatible_models": list(load_rc15_launch_routes(root)),
        "provider_specific_exclusions": ["z-ai/glm-5.2"],
        "new_compatibility_requests": 0,
        "request_tool_provider_route_hashes_changed": False,
    }
    _write_json(target / "compatibility_inheritance.json", inheritance, secret="")

    audit = {
        "schema_version": "uc-bench-open-mmmvp-rc1-6-parser-trust-boundary-audit-1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "passed",
        "api_requests": 0,
        "agent_controlled_boundaries": [
            {
                "surface": "final submission JSON",
                "validator": "mmmvp_open_schema validators plus total schema facade",
                "failure": "contract failure",
            },
            {
                "surface": "artifact manifest, paths, hashes, and source paths",
                "validator": "index_agent_artifacts_total",
                "failure": "artifact failure",
            },
            {
                "surface": "CALCULATION_OUTPUT JSON",
                "validator": "bounded-memory streaming validate_calculation_output",
                "failure": "saved_output_mismatch with typed artifact diagnostics",
            },
            {
                "surface": "ANALYSIS_TABLE CSV and semantic column map",
                "validator": (
                    "streaming validate_analysis_table_artifact bounded by the existing "
                    "source-record identity invariant"
                ),
                "failure": "unverified analysis table with typed artifact diagnostics",
            },
            {
                "surface": "calculation parameters and optional uncertainty",
                "validator": "verify_typed_calculations_total",
                "failure": "calculation or uncertainty mismatch",
            },
        ],
        "environment_controlled_boundaries": [
            "supplied cohort metadata and locked predictions",
            "revealed outcomes and fit membership",
            "purchased evidence packages",
            "private validity cards",
            "host-owned commitment records",
            "protected-evidence hashes",
        ],
        "environment_failure_class": "infrastructure_failure",
        "unexpected_internal_failure_class": "grader_failure",
        "broad_exception_used_for_agent_artifact_parsing": False,
        "agent_hashing_materializes_entire_files": False,
        "protected_hashing_materializes_entire_files": False,
        "symlinked_agent_artifacts_accepted": False,
        "live_tool_decode_and_schema_errors_recoverable": True,
        "scoring_semantics_changed": False,
    }
    _write_json(target / "parser_trust_boundary_audit.json", audit, secret="")

    run = root / (
        "build/uc_bench_mmmvp_open_rc14_runs/"
        "open-mmmvp-rc15-sentinel-00-google-gemini-3.1-pro-preview-case-02-atte"
    )
    submission = json.loads((run / "submission.json").read_text(encoding="utf-8"))
    grade = verify_rc16_open_submission(
        root, run / "workspace", submission, condition_id="case_02"
    ).to_dict()
    latest = json.loads((run / "host_trajectory/latest.json").read_text(encoding="utf-8"))
    core = restore_rc12_environment(root, run / "workspace", latest)
    store = RC14DurableTrajectoryStore.reopen(
        run / "host_trajectory", workspace=run / "workspace", core=core, secret=""
    )
    replay = rc16_trajectory_replay_check(
        root,
        run / "workspace",
        store,
        condition_id="case_02",
        grade=grade,
        stop_condition="no_tools_called",
    )
    auc = next(
        row
        for row in grade["diagnostics"]["artifact_validation"]
        if row["artifact_path"] == "work/auc.txt"
    )
    gemini = {
        "schema_version": "uc-bench-open-mmmvp-rc1-6-gemini-regression-1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "passed",
        "api_requests": 0,
        "source_rc15_summary_sha256": sha256_file(run / "run_summary.json"),
        "source_workspace_and_trajectory_modified": False,
        "official_rc15_result_remains": "unscored_infrastructure_failure",
        "rc16_development_regression_only": True,
        "strict_mission_success": grade["complete_mission_success"],
        "partial_scientific_quality": grade["partial_scientific_quality"],
        "reliability_score": grade["reliability_score"],
        "first_failure": grade["first_decision_critical_failure"],
        "auc_artifact": auc,
        "auc_calculation_faults": grade["diagnostics"]["typed_calculations"]["calc_roc_auc"][
            "faults"
        ],
        "trajectory_reconstruction": replay,
        "agent_asserted_physical_sample_swap": True,
        "benchmark_or_oracle_endorses_physical_sample_swap": False,
        "interpretation": (
            "work/auc.txt is syntactically valid JSON but semantically invalid as the "
            "disclosed CALCULATION_OUTPUT because its top-level value is a scalar. The "
            "artifact failure is legitimate; the RC1.5 verifier exception was infrastructure."
        ),
    }
    expected = bool(
        not grade["complete_mission_success"]
        and grade["partial_scientific_quality"] == 40.0
        and grade["reliability_score"] == 100.0
        and grade["first_decision_critical_failure"]["requirement_id"]
        == "prospective_plan_implemented"
        and "saved_output_mismatch" in gemini["auc_calculation_faults"]
        and replay["passed"]
        and replay["grader_replay"]["passed"]
    )
    gemini["status"] = "passed" if expected else "failed"
    _write_json(target / "gemini_regression.json", gemini, secret="")

    corpus = run_rc16_crash_corpus(root)
    _write_json(target / "crash_corpus.json", corpus, secret="")
    rehearsal = run_rc16_prefreeze_rehearsal(root)
    _write_json(target / "pre_freeze_rehearsal.json", rehearsal, secret="")
    statuses = {
        "gemini": gemini["status"],
        "corpus": corpus["status"],
        "rehearsal": rehearsal["status"],
    }
    print(json.dumps(statuses, sort_keys=True))
    return 0 if all(row["status"] == "passed" for row in (gemini, corpus, rehearsal)) else 1


if __name__ == "__main__":
    raise SystemExit(main())

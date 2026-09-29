"""Automated pre-release checks with an explicit, non-negotiable no-go path."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from uc_bench.downloads import load_pinned_sources, source_is_valid
from uc_bench.manifests import validate_config_root


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _public_sealed_id_scan(project_root: Path) -> dict[str, Any]:
    import pandas as pd

    labels = pd.read_csv(
        project_root / "grader_private" / "data" / "gse92415_labels.csv",
        usecols=["sample_id"],
    )
    sample_ids = tuple(labels["sample_id"].astype(str))
    public_roots = (
        "artifacts",
        "build/episodes",
        "configs",
        "docs",
        "notebooks",
        "reports",
        "scripts",
        "src",
        "tasks",
        "tests",
        "README.md",
        "PROJECT_PLAN.md",
        "Makefile",
        "pyproject.toml",
    )
    matches = []
    for relative_root in public_roots:
        root = project_root / relative_root
        candidates = [root] if root.is_file() else root.rglob("*")
        for path in candidates:
            if not path.is_file():
                continue
            content = path.read_bytes()
            found = [sample_id for sample_id in sample_ids if sample_id.encode() in content]
            if found:
                matches.append(
                    {
                        "path": path.relative_to(project_root).as_posix(),
                        "match_count": len(found),
                    }
                )
    return {
        "passed": not matches,
        "forbidden_id_count": len(sample_ids),
        "matching_files": matches,
    }


def run_pre_release_audit(project_root: Path) -> dict[str, Any]:
    config_summary = validate_config_root(project_root / "configs")
    sources = load_pinned_sources(project_root)
    data_valid = all(source_is_valid(project_root, source) for source in sources)
    reference = _read_json(project_root / "artifacts" / "reference" / "environment_episode.json")
    full_data_package = _read_json(
        project_root / "build" / "episodes" / "manifests" / "full_data.json"
    )
    grading = _read_json(project_root / "artifacts" / "grading" / "reference_separation.json")
    variants = _read_json(project_root / "artifacts" / "variants" / "scenario_controls.json")
    runtime = _read_json(project_root / "artifacts" / "runtime" / "infrastructure_smoke.json")
    evaluation = _read_json(
        project_root / "reports" / "generated" / "evaluation_summary.json"
    )
    independent_review = _read_json(project_root / "audit" / "independent_review.json")
    findings = _read_json(project_root / "audit" / "findings.json")["findings"]
    open_high_findings = [
        row["id"]
        for row in findings
        if row["status"] == "open" and row["severity"] in {"critical", "high"}
    ]
    public_scan = _public_sealed_id_scan(project_root)
    forgery_control = grading.get("structured_forgery_control", {})
    grader_controls_pass = (
        grading.get("passed") is True
        and grading.get("expert", {}).get("score") == 100.0
        and grading.get("keyword_only_control", {}).get("score", 101.0) <= 40.0
        and forgery_control.get("contract_valid") is False
        and forgery_control.get("score", 101.0) <= 40.0
        and {
            "negative_control",
            "platform_alignment",
            "uncertainty",
        }
        <= set(forgery_control.get("checks", {}).get("false_pass_claims", []))
    )
    checks = {
        "public_config_invariants": config_summary["benchmark_id"]
        == "uc_biomarker_diligence_v0",
        "pinned_source_files_verified": data_valid,
        "public_sealed_sample_id_scan": public_scan["passed"],
        "fresh_state_reference_submitted": (
            reference.get("phase") == "submitted"
            and reference.get("condition") == "full_data"
            and reference.get("start_state", {}).get("package_digest")
            == full_data_package.get("package_digest")
        ),
        "reference_grader_separation": grader_controls_pass,
        "symmetric_policy_controls": variants.get("all_universal_policies_fail") is True,
        "runtime_fixture_smoke": runtime.get("fixture_infrastructure_failures") == 0,
        "real_model_smoke": runtime.get("real_model_smoke_executed") is True,
        "repeated_model_evaluation": evaluation.get("status") == "complete",
        "no_open_high_findings": not open_high_findings,
        "independent_review": (
            independent_review.get("status") == "approved"
            and independent_review.get("scientific_claims_approved") is True
            and independent_review.get("reward_hacking_review_approved") is True
            and bool(independent_review.get("reviewer"))
            and bool(independent_review.get("reviewed_at"))
        ),
    }
    release_ready = all(checks.values())
    remaining_actions = []
    if not checks["real_model_smoke"]:
        remaining_actions.append(
            "Run the three-model, three-attempt isolated smoke and close AF-007."
        )
    if not checks["repeated_model_evaluation"]:
        remaining_actions.append(
            "Run the prespecified repeated evaluation and close AF-005."
        )
    if not checks["independent_review"]:
        remaining_actions.append(
            "Obtain independent scientific/reward-hacking review before release."
        )
    unresolved_other_checks = sorted(
        name
        for name, passed in checks.items()
        if not passed
        and name
        not in {
            "real_model_smoke",
            "repeated_model_evaluation",
            "independent_review",
            "no_open_high_findings",
        }
    )
    if unresolved_other_checks:
        remaining_actions.append(
            f"Resolve failed automated checks: {', '.join(unresolved_other_checks)}."
        )
    return {
        "schema_version": "0.1",
        "release_decision": "go" if release_ready else "no_go",
        "checks": checks,
        "passed_check_count": sum(checks.values()),
        "total_check_count": len(checks),
        "open_high_findings": open_high_findings,
        "public_sealed_id_scan": public_scan,
        "model_ranking_claim_allowed": release_ready,
        "independent_review_complete": checks["independent_review"],
        "remaining_actions": remaining_actions,
    }

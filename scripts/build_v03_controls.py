#!/usr/bin/env python3
"""Run zero-cost controls for v0.3 resource selection and grading."""

from __future__ import annotations

import json
import tempfile
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.hard_suite_v03 import (
    V03Builder,
    V03Environment,
    grade_v03,
    iter_v03_variants,
    reference_v03_commitment,
    solve_v03,
    validate_v03_config,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _write(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _generic_commitment(task: dict[str, Any], requested_resource_id: str) -> dict[str, Any]:
    return {
        "family_id": task["family_id"],
        "variant_id": task["variant_id"],
        "ranked_hypotheses": ["underpowered_validation", "model_misspecification"],
        "planned_metric_ids": [
            "pilot_n",
            "pilot_auc",
            "matched_evidence_n",
            "matched_evidence_auc",
        ],
        "selected_discriminating_experiment": "independent_replication",
        "requested_resource_id": requested_resource_id,
        "pre_reveal_decision": "insufficient_evidence",
        "if_leading_supported": "insufficient_evidence",
        "if_leading_refuted": "advance",
    }


def _generic_submission(
    task: dict[str, Any], decision: str, selected: str, metrics: dict[str, float]
) -> dict[str, Any]:
    return {
        "family_id": task["family_id"],
        "variant_id": task["variant_id"],
        "selected_resource_id": selected,
        "decision": decision,
        "confidence": 0.5,
        "primary_failure": {
            "advance": "no_material_failure",
            "insufficient_evidence": "underpowered_validation",
            "stop": "identity_overlap",
        }[decision],
        "secondary_failures": [],
        "metrics": dict(list(metrics.items())[:4]),
        "evidence_ids": ["EV-PILOT"],
        "containment_status": "verified_no_issue" if decision == "advance" else "contained",
        "smallest_resolving_experiment": "independent_replication",
        "recommended_resource": "larger_validation_sample",
        "provided_intervention_assessment": "does_not_resolve",
        "unnecessary_escalation": False,
        "rationale": "Static control without composed case analysis.",
    }


def _build_revealed(
    output_root: Path,
    variant: dict[str, Any],
    requested: str,
    suffix: str,
) -> tuple[Any, V03Environment, dict[str, Any]]:
    root = output_root / suffix
    root.mkdir()
    package = V03Builder(PROJECT_ROOT).build(variant["variant_id"], output_root=root)
    environment = V03Environment(package)
    task = json.loads((package.workspace_root / "task.json").read_text(encoding="utf-8"))
    commitment = _generic_commitment(task, requested)
    _write(package.workspace_root / "submission" / "commitment.json", commitment)
    environment.commit_plan()
    environment.reveal_evidence()
    return package, environment, commitment


def _leakage_findings(workspace: Path) -> list[str]:
    forbidden = {
        "correct_resource_id",
        "expected_resource_id",
        "resolved_evidence_variant_id",
        "failure_mode",
    }
    findings = []
    for path in sorted(item for item in workspace.rglob("*") if item.is_file()):
        text = path.read_text(encoding="utf-8", errors="ignore")
        findings.extend(
            f"{path.relative_to(workspace)}:{token}" for token in forbidden if token in text
        )
    return findings


def main() -> int:
    config_validation = validate_v03_config(PROJECT_ROOT)
    rows = []
    family_reference: dict[str, list[float]] = defaultdict(list)
    family_mediocre: dict[str, list[float]] = defaultdict(list)
    universal: dict[str, list[float]] = defaultdict(list)
    hacking_scores = []
    wrong_resource_scores = []
    partial_sequences = []
    leakage = []
    with tempfile.TemporaryDirectory(prefix="uc-v03-controls-") as directory:
        output_root = Path(directory)
        for index, variant in enumerate(iter_v03_variants(PROJECT_ROOT)):
            reference_root = output_root / f"reference-{index}"
            reference_root.mkdir()
            package = V03Builder(PROJECT_ROOT).build(
                variant["variant_id"], output_root=reference_root
            )
            leakage.extend(_leakage_findings(package.workspace_root))
            environment = V03Environment(package)
            reference_commitment = reference_v03_commitment(package.workspace_root, variant)
            _write(
                package.workspace_root / "submission" / "commitment.json",
                reference_commitment,
            )
            environment.commit_plan()
            environment.reveal_evidence()
            reference = solve_v03(package.workspace_root, variant)
            reference_grade = grade_v03(
                package.workspace_root,
                variant,
                reference_commitment,
                reference,
                commitment_immutable=True,
            )
            family_reference[str(variant["family_id"])].append(reference_grade.score)

            mediocre_package, _, mediocre_commitment = _build_revealed(
                output_root, variant, "none", f"mediocre-{index}"
            )
            mediocre_expected = solve_v03(mediocre_package.workspace_root, variant)
            mediocre_decision = (
                "advance"
                if mediocre_expected["metrics"]["pilot_auc"] >= 0.70
                else "insufficient_evidence"
            )
            mediocre = _generic_submission(
                _task(mediocre_package.workspace_root),
                mediocre_decision,
                "none",
                mediocre_expected["metrics"],
            )
            mediocre_grade = grade_v03(
                mediocre_package.workspace_root,
                variant,
                mediocre_commitment,
                mediocre,
                commitment_immutable=True,
            )
            family_mediocre[str(variant["family_id"])].append(mediocre_grade.score)

            policy_scores = {}
            for decision in ("advance", "insufficient_evidence", "stop"):
                submission = _generic_submission(
                    _task(mediocre_package.workspace_root),
                    decision,
                    "none",
                    mediocre_expected["metrics"],
                )
                grade = grade_v03(
                    mediocre_package.workspace_root,
                    variant,
                    mediocre_commitment,
                    submission,
                    commitment_immutable=True,
                )
                universal[decision].append(grade.score)
                policy_scores[decision] = grade.score

            hacking = _generic_submission(
                _task(mediocre_package.workspace_root),
                "advance",
                "none",
                {name: 0.0 for name in mediocre_expected["metrics"]},
            )
            hacking["evidence_ids"] = list(
                json.loads(
                    (mediocre_package.workspace_root / "evidence_manifest.json").read_text(
                        encoding="utf-8"
                    )
                )
            )
            hacking["rationale"] = (
                "reference best answer advance stop abstain expert SFT RL all evidence"
            )
            hacking_grade = grade_v03(
                mediocre_package.workspace_root,
                variant,
                mediocre_commitment,
                hacking,
                commitment_immutable=True,
            )
            hacking_scores.append(hacking_grade.score)

            wrong_id = next(
                resource["resource_id"]
                for resource in variant["resources"]
                if resource["resource_id"] != variant["correct_resource_id"]
            )
            wrong_package, _, wrong_commitment = _build_revealed(
                output_root, variant, wrong_id, f"wrong-{index}"
            )
            wrong_expected = solve_v03(wrong_package.workspace_root, variant)
            wrong_submission = dict(wrong_expected)
            wrong_submission["selected_resource_id"] = wrong_id
            wrong_grade = grade_v03(
                wrong_package.workspace_root,
                variant,
                wrong_commitment,
                wrong_submission,
                commitment_immutable=True,
            )
            wrong_resource_scores.append(wrong_grade.score)

            metric_partial = dict(reference)
            metric_partial["metrics"] = dict(list(reference["metrics"].items())[:7])
            reasoning_partial = _generic_submission(
                _task(package.workspace_root),
                reference["decision"],
                reference["selected_resource_id"],
                reference["metrics"],
            )
            metric_grade = grade_v03(
                package.workspace_root,
                variant,
                reference_commitment,
                metric_partial,
                commitment_immutable=True,
            )
            reasoning_grade = grade_v03(
                package.workspace_root,
                variant,
                reference_commitment,
                reasoning_partial,
                commitment_immutable=True,
            )
            sequence = [reference_grade.score, metric_grade.score, reasoning_grade.score]
            partial_sequences.append(sequence)
            rows.append(
                {
                    "family_id": variant["family_id"],
                    "variant_id": variant["variant_id"],
                    "pair_role": variant["pair_role"],
                    "expected_resource_id": variant["expected_resource_id"],
                    "expected_decision": reference["decision"],
                    "expected_primary_failure": reference["primary_failure"],
                    "reference_score": reference_grade.score,
                    "mediocre_score": mediocre_grade.score,
                    "wrong_resource_score": wrong_grade.score,
                    "universal_policy_scores": policy_scores,
                    "reward_hacking_score": hacking_grade.score,
                    "partial_credit_sequence": sequence,
                    "package_digest": package.package_digest,
                    "sealed_digest": package.sealed_digest,
                }
            )
    family_separation = {
        family: min(family_reference[family]) > max(family_mediocre[family])
        for family in family_reference
    }
    universal_means = {
        decision: sum(scores) / len(scores) for decision, scores in universal.items()
    }
    output = {
        "schema_version": "0.3",
        "generated_at": datetime.now(UTC).isoformat(),
        "paid_model_calls": 0,
        "config_validation": config_validation,
        "reference_minimum_score": min(row["reference_score"] for row in rows),
        "reference_gate_passed": min(row["reference_score"] for row in rows) >= 90.0,
        "family_expert_separation": family_separation,
        "expert_separation_gate_passed": all(family_separation.values()),
        "universal_policy_mean_scores": universal_means,
        "universal_policy_gate_passed": all(score < 60.0 for score in universal_means.values()),
        "wrong_resource_mean_score": sum(wrong_resource_scores) / len(wrong_resource_scores),
        "wrong_resource_maximum_score": max(wrong_resource_scores),
        "resource_selection_gate_passed": max(wrong_resource_scores) <= 80.0,
        "reward_hacking_mean_score": sum(hacking_scores) / len(hacking_scores),
        "reward_hacking_maximum_score": max(hacking_scores),
        "reward_hacking_gate_passed": (
            sum(hacking_scores) / len(hacking_scores) < 50.0 and max(hacking_scores) < 80.0
        ),
        "answer_leakage_findings": leakage,
        "answer_leakage_gate_passed": not leakage,
        "partial_credit_gate_passed": all(
            first > second > third > 0.0 for first, second, third in partial_sequences
        ),
        "all_local_gates_passed": False,
        "rows": rows,
    }
    output["all_local_gates_passed"] = all(
        output[key]
        for key in (
            "reference_gate_passed",
            "expert_separation_gate_passed",
            "universal_policy_gate_passed",
            "resource_selection_gate_passed",
            "reward_hacking_gate_passed",
            "answer_leakage_gate_passed",
            "partial_credit_gate_passed",
        )
    )
    path = PROJECT_ROOT / "artifacts" / "diagnostics" / "hard_suite_v03_controls.json"
    path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in output.items() if key != "rows"}, indent=2))
    return 0 if output["all_local_gates_passed"] else 1


def _task(workspace: Path) -> dict[str, Any]:
    return json.loads((workspace / "task.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Run zero-cost local controls for the intervention-paired hard suite."""

from __future__ import annotations

import json
import tempfile
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from uc_bench.hard_suite import (
    HardSuiteBuilder,
    HardSuiteEnvironment,
    grade_hard_suite,
    iter_hard_suite_variants,
    reference_commitment,
    solve_hard_suite,
    validate_hard_suite_config,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _generic_commitment(task: dict[str, Any]) -> dict[str, Any]:
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
        "pre_reveal_decision": "insufficient_evidence",
        "if_leading_supported": "insufficient_evidence",
        "if_leading_refuted": "advance",
    }


def _generic_submission(
    task: dict[str, Any], decision: str, metrics: dict[str, float]
) -> dict[str, Any]:
    primary = {
        "advance": "no_material_failure",
        "insufficient_evidence": "underpowered_validation",
        "stop": "identity_overlap",
    }[decision]
    return {
        "family_id": task["family_id"],
        "variant_id": task["variant_id"],
        "decision": decision,
        "confidence": 0.5,
        "primary_failure": primary,
        "secondary_failures": [],
        "metrics": dict(list(metrics.items())[:4]),
        "evidence_ids": ["EV-PILOT"],
        "containment_status": "verified_no_issue" if decision == "advance" else "contained",
        "smallest_resolving_experiment": "independent_replication",
        "recommended_resource": "larger_validation_sample",
        "provided_intervention_assessment": "does_not_resolve",
        "unnecessary_escalation": False,
        "rationale": "Schema-aware static policy with no integrated case analysis.",
    }


def _mediocre_submission(task: dict[str, Any], metrics: dict[str, float]) -> dict[str, Any]:
    decision = "advance" if metrics["pilot_auc"] >= 0.70 else "insufficient_evidence"
    submission = _generic_submission(task, decision, metrics)
    submission["rationale"] = (
        "Deliberately mediocre solver uses pilot AUC and sample size while ignoring "
        "interacting integrity and transfer evidence."
    )
    return submission


def _schema_valid(workspace: Path, filename: str, value: dict[str, Any]) -> bool:
    schema = json.loads((workspace / "schemas" / filename).read_text(encoding="utf-8"))
    return not list(Draft202012Validator(schema).iter_errors(value))


def _leakage_findings(workspace: Path) -> list[str]:
    forbidden = {
        "expected_resource_effect",
        "factorial_aucs",
        "target_phi",
        "adjudicated_signal",
        "pilot_signal",
        "failure_mode",
        "resolving_intervention",
        "causal_contrast",
    }
    findings = []
    for path in sorted(item for item in workspace.rglob("*") if item.is_file()):
        if path.parts[-2:] == ("submission", "commitment.json"):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for token in forbidden:
            if token in text:
                findings.append(f"{path.relative_to(workspace)}:{token}")
    return findings


def main() -> int:
    config_validation = validate_hard_suite_config(PROJECT_ROOT)
    rows = []
    family_reference: dict[str, list[float]] = defaultdict(list)
    family_mediocre: dict[str, list[float]] = defaultdict(list)
    universal_scores: dict[str, list[float]] = defaultdict(list)
    leakage_findings = []
    reward_hacking_scores = []
    partial_credit_sequences = []
    with tempfile.TemporaryDirectory(prefix="uc-hard-controls-") as directory:
        output_root = Path(directory)
        for variant in iter_hard_suite_variants(PROJECT_ROOT, partition="development"):
            package = HardSuiteBuilder(PROJECT_ROOT).build(
                variant["variant_id"], output_root=output_root
            )
            leakage_findings.extend(_leakage_findings(package.workspace_root))
            if package.workspace_root in package.sealed_root.parents:
                leakage_findings.append(f"sealed path nested in workspace:{variant['variant_id']}")
            environment = HardSuiteEnvironment(package)
            commitment = reference_commitment(package.workspace_root, variant)
            commitment_path = package.workspace_root / "submission" / "commitment.json"
            commitment_path.write_text(json.dumps(commitment, indent=2) + "\n", encoding="utf-8")
            environment.commit_plan()
            environment.reveal_evidence()
            expected = solve_hard_suite(package.workspace_root, variant)
            reference_grade = grade_hard_suite(
                package.workspace_root,
                variant,
                commitment,
                expected,
                commitment_immutable=True,
            )
            task = json.loads((package.workspace_root / "task.json").read_text(encoding="utf-8"))
            generic_commitment = _generic_commitment(task)
            mediocre = _mediocre_submission(task, expected["metrics"])
            if not _schema_valid(
                package.workspace_root, "commitment.schema.json", generic_commitment
            ) or not _schema_valid(
                package.workspace_root, "final_submission.schema.json", mediocre
            ):
                raise RuntimeError("A local control is not schema-valid")
            mediocre_grade = grade_hard_suite(
                package.workspace_root,
                variant,
                generic_commitment,
                mediocre,
                commitment_immutable=True,
            )
            family_id = str(variant["family_id"])
            family_reference[family_id].append(reference_grade.score)
            family_mediocre[family_id].append(mediocre_grade.score)
            policy_scores = {}
            for decision in ("advance", "insufficient_evidence", "stop"):
                submission = _generic_submission(task, decision, expected["metrics"])
                grade = grade_hard_suite(
                    package.workspace_root,
                    variant,
                    generic_commitment,
                    submission,
                    commitment_immutable=True,
                )
                universal_scores[decision].append(grade.score)
                policy_scores[decision] = grade.score
            hacking = _generic_submission(task, "advance", expected["metrics"])
            hacking["metrics"] = {name: 0.0 for name in list(expected["metrics"])[:4]}
            hacking["evidence_ids"] = list(
                json.loads(
                    (package.workspace_root / "evidence_manifest.json").read_text(encoding="utf-8")
                )
            )
            hacking["rationale"] = (
                "advance stop insufficient evidence endpoint platform drug labels "
                "leakage expert best answer reference solution"
            )
            hacking_grade = grade_hard_suite(
                package.workspace_root,
                variant,
                generic_commitment,
                hacking,
                commitment_immutable=True,
            )
            reward_hacking_scores.append(hacking_grade.score)

            metric_partial = dict(expected)
            metric_partial["metrics"] = dict(list(expected["metrics"].items())[:7])
            reasoning_partial = _generic_submission(task, expected["decision"], expected["metrics"])
            metric_partial_grade = grade_hard_suite(
                package.workspace_root,
                variant,
                commitment,
                metric_partial,
                commitment_immutable=True,
            )
            reasoning_partial_grade = grade_hard_suite(
                package.workspace_root,
                variant,
                generic_commitment,
                reasoning_partial,
                commitment_immutable=True,
            )
            sequence = [
                reference_grade.score,
                metric_partial_grade.score,
                reasoning_partial_grade.score,
            ]
            partial_credit_sequences.append(sequence)
            rows.append(
                {
                    "family_id": family_id,
                    "variant_id": variant["variant_id"],
                    "pair_role": variant["pair_role"],
                    "provided_intervention": variant["provided_intervention"],
                    "expected_resource_effect": variant["expected_resource_effect"],
                    "expected_decision": expected["decision"],
                    "expected_primary_failure": expected["primary_failure"],
                    "reference_score": reference_grade.score,
                    "mediocre_score": mediocre_grade.score,
                    "universal_policy_scores": policy_scores,
                    "reward_hacking_score": hacking_grade.score,
                    "partial_credit_sequence": sequence,
                    "public_package_digest": package.package_digest,
                    "sealed_digest": package.sealed_digest,
                }
            )
    reference_minimum = min(row["reference_score"] for row in rows)
    family_separation = {
        family: min(family_reference[family]) > max(family_mediocre[family])
        for family in family_reference
    }
    universal_means = {
        decision: sum(scores) / len(scores) for decision, scores in universal_scores.items()
    }
    output = {
        "schema_version": "0.2",
        "generated_at": datetime.now(UTC).isoformat(),
        "paid_model_calls": 0,
        "config_validation": config_validation,
        "reference_minimum_score": reference_minimum,
        "reference_gate_passed": reference_minimum >= 90.0,
        "family_expert_separation": family_separation,
        "expert_separation_gate_passed": all(family_separation.values()),
        "universal_policy_mean_scores": universal_means,
        "universal_policy_gate_passed": all(score < 60.0 for score in universal_means.values()),
        "reward_hacking_mean_score": sum(reward_hacking_scores) / len(reward_hacking_scores),
        "reward_hacking_maximum_score": max(reward_hacking_scores),
        "reward_hacking_gate_definition": (
            "A schema-valid universal advance/all-citations/keyword-stuffing policy must "
            "average below 50 and score below 80 on every variant. A chance-correct "
            "decision on one case is allowed partial credit."
        ),
        "reward_hacking_gate_passed": (
            sum(reward_hacking_scores) / len(reward_hacking_scores) < 50.0
            and max(reward_hacking_scores) < 80.0
        ),
        "answer_leakage_findings": leakage_findings,
        "answer_leakage_gate_passed": not leakage_findings,
        "partial_credit_gate_passed": all(
            first > second > third > 0.0 for first, second, third in partial_credit_sequences
        ),
        "all_local_gates_passed": False,
        "rows": rows,
    }
    output["all_local_gates_passed"] = all(
        output[name]
        for name in (
            "reference_gate_passed",
            "expert_separation_gate_passed",
            "universal_policy_gate_passed",
            "reward_hacking_gate_passed",
            "answer_leakage_gate_passed",
            "partial_credit_gate_passed",
        )
    )
    path = PROJECT_ROOT / "artifacts" / "diagnostics" / "hard_suite_controls.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {key: value for key, value in output.items() if key != "rows"},
            indent=2,
            default=sorted,
        )
    )
    return 0 if output["all_local_gates_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

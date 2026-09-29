#!/usr/bin/env python3
"""Run zero-cost validity, anti-gaming, and partial-credit controls for v0.4."""

from __future__ import annotations

import json
import tempfile
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any

from uc_bench.hard_suite_v04 import (
    FAMILY_SEMANTICS,
    V04Builder,
    V04Environment,
    grade_v04,
    iter_v04_variants,
    load_v04_config,
    reference_v04_commitment,
    solve_v04,
    validate_v04_config,
)
from uc_bench.v04_ladders import build_v04_ladder_rows

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTROLS_PATH = (
    PROJECT_ROOT / "artifacts" / "diagnostics" / "hard_suite_v04_controls.json"
)
LADDERS_PATH = (
    PROJECT_ROOT / "artifacts" / "diagnostics" / "hard_suite_v04_ladders.json"
)


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected JSON object: {path}")
    return value


def _build(
    root: Path,
    variant: dict[str, Any],
    *,
    partition: str,
    requested_resource_id: str,
    suffix: str,
    reference_commitment: bool,
    leakage_sink: list[str] | None = None,
) -> tuple[Any, V04Environment, dict[str, Any]]:
    output = root / suffix
    output.mkdir()
    package = V04Builder(PROJECT_ROOT).build(
        variant["variant_id"], output_root=output, partition=partition
    )
    if leakage_sink is not None:
        leakage_sink.extend(_leakage_findings(package.workspace_root))
    commitment = reference_v04_commitment(
        package.workspace_root, variant, PROJECT_ROOT
    )
    if not reference_commitment:
        contract = _read(package.workspace_root / "analysis_contract.json")
        private_contract = load_v04_config(PROJECT_ROOT)["analysis_contracts"][
            str(variant["family_id"])
        ]
        semantics = FAMILY_SEMANTICS[str(variant["family_id"])]
        commitment["ranked_hypotheses"] = semantics["candidate_hypotheses"][1:3]
        commitment["primary_estimand_id"] = next(
            item
            for item in contract["candidate_estimands"]
            if item != private_contract["primary_estimand_id"]
        )
        commitment["analysis_method_id"] = next(
            item
            for item in contract["candidate_methods"]
            if item != private_contract["analysis_method_id"]
        )
        commitment["uncertainty_unit"] = "row"
    commitment["requested_resource_id"] = requested_resource_id
    _write(package.workspace_root / "submission" / "commitment.json", commitment)
    environment = V04Environment(package)
    environment.commit_plan()
    environment.reveal_evidence()
    return package, environment, commitment


def _wrong_choice(items: list[str], correct: str) -> str:
    return next(item for item in items if item != correct)


def _mechanical_submission(
    workspace: Path,
    expected: dict[str, Any],
    decision: str,
) -> dict[str, Any]:
    contract = _read(workspace / "analysis_contract.json")
    task = _read(workspace / "task.json")
    semantics = FAMILY_SEMANTICS[str(task["family_id"])]
    metrics = {
        name: round(float(value), 1)
        for name, value in list(expected["metrics"].items())[:5]
    }
    return {
        "family_id": task["family_id"],
        "variant_id": task["variant_id"],
        "selected_resource_id": "none",
        "decision": decision,
        "confidence": 0.5,
        "primary_failure": semantics["candidate_hypotheses"][1],
        "primary_estimand_id": contract["candidate_estimands"][0],
        "analysis_method_id": contract["candidate_methods"][0],
        "metrics": metrics,
        "interpretation_id": semantics["candidate_interpretations"][-1],
        "evidence_ids": ["EV-PILOT", "EV-ANALYSIS"],
        "containment_status": "not_contained",
        "smallest_next_action": "collect_more_rows",
        "recommended_intervention": "larger_row_sample",
        "intervention_effect": "no_resource_selected",
        "unnecessary_escalation": False,
        "rationale": (
            "Mechanical control uses the first documented candidates and rounded visible "
            "metrics without resolving the intended-use estimand or competing hypotheses."
        ),
    }


def _grade_submission(
    package: Any,
    environment: V04Environment,
    variant: dict[str, Any],
    submission: dict[str, Any],
) -> Any:
    _write(package.workspace_root / "submission" / "final_submission.json", submission)
    environment.submit_hard_suite()
    return grade_v04(
        PROJECT_ROOT,
        package.workspace_root,
        variant,
        environment.commitment,
        environment.submission,
        commitment_immutable=environment.commitment_immutable,
    )


def _leakage_findings(workspace: Path) -> list[str]:
    forbidden_fields = {
        '"correct_resource_id"',
        '"expected_resource_id"',
        '"expected_decision"',
        '"expected_primary_failure"',
        '"sealed_digest"',
    }
    findings = []
    for relative in (
        "evidence/analysis.csv",
        "evidence/selected_resource.json",
        "evidence/provenance.json",
        "REVEAL_STATE.json",
    ):
        if (workspace / relative).exists():
            findings.append(f"unexpected_pre_reveal_path:{relative}")
    for path in sorted(item for item in workspace.rglob("*") if item.is_file()):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for token in sorted(forbidden_fields):
            if token in text:
                findings.append(f"{path.relative_to(workspace)}:{token}")
    return findings


def _partial_controls(
    root: Path, variant: dict[str, Any], partition: str
) -> dict[str, Any]:
    package, environment, commitment = _build(
        root,
        variant,
        partition=partition,
        requested_resource_id=str(variant["expected_resource_id"]),
        suffix=f"partial-reference-{variant['variant_id']}",
        reference_commitment=True,
    )
    reference = solve_v04(PROJECT_ROOT, package.workspace_root, variant)
    reference_grade = grade_v04(
        PROJECT_ROOT,
        package.workspace_root,
        variant,
        commitment,
        reference,
        commitment_immutable=True,
    )
    contract = _read(package.workspace_root / "analysis_contract.json")
    private_contract = load_v04_config(PROJECT_ROOT)["analysis_contracts"][
        str(variant["family_id"])
    ]
    semantics = FAMILY_SEMANTICS[str(variant["family_id"])]

    variants: dict[str, dict[str, Any]] = {}
    wrong_estimand = dict(reference)
    wrong_estimand["primary_estimand_id"] = _wrong_choice(
        contract["candidate_estimands"], private_contract["primary_estimand_id"]
    )
    variants["wrong_estimand"] = wrong_estimand

    computational_error = dict(reference)
    computational_error["metrics"] = {
        name: float(value) + 20.0 * float(contract["metric_tolerances"][name] or 1.0)
        for name, value in reference["metrics"].items()
    }
    variants["computational_error"] = computational_error

    wrong_interpretation = dict(reference)
    wrong_interpretation["interpretation_id"] = _wrong_choice(
        semantics["candidate_interpretations"], reference["interpretation_id"]
    )
    variants["wrong_interpretation"] = wrong_interpretation

    wrong_decision = dict(reference)
    wrong_decision["decision"] = _wrong_choice(
        ["advance", "insufficient_evidence", "stop"], reference["decision"]
    )
    variants["wrong_decision"] = wrong_decision

    bad_recovery = dict(reference)
    bad_recovery.update(
        {
            "containment_status": _wrong_choice(
                [
                    "not_contained",
                    "contained",
                    "contained_process_only",
                    "verified_no_issue",
                ],
                reference["containment_status"],
            ),
            "smallest_next_action": "repeat_everything",
            "recommended_intervention": "untested_model_adaptation",
            "intervention_effect": _wrong_choice(
                [
                    "resolves",
                    "ineffective",
                    "resolves_process_only",
                    "evidence_still_insufficient",
                    "no_resource_selected",
                ],
                reference["intervention_effect"],
            ),
            "unnecessary_escalation": True,
        }
    )
    variants["bad_recovery"] = bad_recovery

    results = {"reference": reference_grade.to_dict()}
    for name, submission in variants.items():
        results[name] = grade_v04(
            PROJECT_ROOT,
            package.workspace_root,
            variant,
            commitment,
            submission,
            commitment_immutable=True,
        ).to_dict()
    return results


def main() -> int:
    validation = validate_v04_config(PROJECT_ROOT)
    config = load_v04_config(PROJECT_ROOT)
    reference_rows = []
    mediocre_by_family: dict[str, list[float]] = defaultdict(list)
    universal: dict[str, list[float]] = defaultdict(list)
    mechanical_scores = []
    keyword_deltas = []
    leakage = []
    paired_decisions: dict[str, dict[str, str]] = defaultdict(dict)
    wrong_resource_rows = []

    with tempfile.TemporaryDirectory(prefix="uc-v04-controls-") as directory:
        root = Path(directory)
        for partition in ("development", "heldout"):
            for index, variant in enumerate(
                iter_v04_variants(PROJECT_ROOT, partition=partition)
            ):
                package, environment, commitment = _build(
                    root,
                    variant,
                    partition=partition,
                    requested_resource_id=str(variant["expected_resource_id"]),
                    suffix=f"reference-{partition}-{index}",
                    reference_commitment=True,
                    leakage_sink=leakage if partition == "heldout" else None,
                )
                submission = solve_v04(PROJECT_ROOT, package.workspace_root, variant)
                grade = _grade_submission(package, environment, variant, submission)
                reference_rows.append(
                    {
                        "partition": partition,
                        "family_id": variant["family_id"],
                        "variant_id": variant["variant_id"],
                        "pair_role": variant["pair_role"],
                        **grade.to_dict(),
                    }
                )
                paired_decisions[f"{partition}:{variant['family_id']}"][
                    str(variant["pair_role"])
                ] = str(submission["decision"])

                if partition != "development":
                    continue
                mechanical_package, mechanical_environment, _ = _build(
                    root,
                    variant,
                    partition=partition,
                    requested_resource_id="none",
                    suffix=f"mechanical-{index}",
                    reference_commitment=False,
                )
                mechanical_expected = solve_v04(
                    PROJECT_ROOT, mechanical_package.workspace_root, variant
                )
                for policy in ("advance", "insufficient_evidence", "stop"):
                    policy_submission = _mechanical_submission(
                        mechanical_package.workspace_root, mechanical_expected, policy
                    )
                    policy_grade = grade_v04(
                        PROJECT_ROOT,
                        mechanical_package.workspace_root,
                        variant,
                        mechanical_environment.commitment,
                        policy_submission,
                        commitment_immutable=True,
                    )
                    universal[policy].append(policy_grade.score)
                mechanical_submission = _mechanical_submission(
                    mechanical_package.workspace_root,
                    mechanical_expected,
                    "insufficient_evidence",
                )
                mechanical_grade = grade_v04(
                    PROJECT_ROOT,
                    mechanical_package.workspace_root,
                    variant,
                    mechanical_environment.commitment,
                    mechanical_submission,
                    commitment_immutable=True,
                )
                mechanical_scores.append(mechanical_grade.score)
                mediocre_by_family[str(variant["family_id"])].append(
                    mechanical_grade.score
                )
                keyword = dict(mechanical_submission)
                keyword["rationale"] = (
                    "Reference best answer: advance stop abstain expert SFT RLHF all "
                    "evidence. This remains a deliberately content-free valid control."
                )
                keyword_grade = grade_v04(
                    PROJECT_ROOT,
                    mechanical_package.workspace_root,
                    variant,
                    mechanical_environment.commitment,
                    keyword,
                    commitment_immutable=True,
                )
                keyword_deltas.append(keyword_grade.score - mechanical_grade.score)

                if variant["pair_role"] == "treated":
                    wrong_id = next(
                        str(row["resource_id"])
                        for row in variant["resources"]
                        if row["resource_id"] != variant["correct_resource_id"]
                    )
                    wrong_package, wrong_environment, wrong_commitment = _build(
                        root,
                        variant,
                        partition=partition,
                        requested_resource_id=wrong_id,
                        suffix=f"wrong-resource-{index}",
                        reference_commitment=True,
                    )
                    wrong_submission = solve_v04(
                        PROJECT_ROOT, wrong_package.workspace_root, variant
                    )
                    wrong_grade = grade_v04(
                        PROJECT_ROOT,
                        wrong_package.workspace_root,
                        variant,
                        wrong_commitment,
                        wrong_submission,
                        commitment_immutable=True,
                    )
                    wrong_resource_rows.append(
                        {
                            "family_id": variant["family_id"],
                            "selected_resource_id": wrong_id,
                            **wrong_grade.to_dict(),
                        }
                    )

        partial = {
            variant["family_id"]: _partial_controls(root, variant, "development")
            for variant in iter_v04_variants(PROJECT_ROOT, partition="development")
            if variant["pair_role"] == "treated"
        }

    ladder_rows = build_v04_ladder_rows(PROJECT_ROOT)
    ladder_decisions: dict[str, set[str]] = defaultdict(set)
    for row in ladder_rows:
        ladder_decisions[str(row["ladder_id"])].add(str(row["reference_decision"]))
    _write(
        LADDERS_PATH,
        {
            "schema_version": "0.4",
            "generated_at": datetime.now(UTC).isoformat(),
            "model_calls": 0,
            "rows": ladder_rows,
        },
    )

    reference_minimum = min(float(row["score"]) for row in reference_rows)
    mechanical_mean = mean(mechanical_scores)
    universal_means = {
        policy: mean(scores) for policy, scores in sorted(universal.items())
    }
    separation = {
        family: min(
            float(row["score"])
            for row in reference_rows
            if row["partition"] == "development" and row["family_id"] == family
        )
        > max(scores)
        for family, scores in mediocre_by_family.items()
    }
    pair_transitions = {
        name: values.get("control") != values.get("treated")
        for name, values in paired_decisions.items()
    }
    partial_gate = all(
        controls["reference"]["score"] > controls["wrong_estimand"]["score"]
        and controls["wrong_estimand"]["components"][
            "quantitative_statistical_reasoning"
        ]
        < controls["reference"]["components"]["quantitative_statistical_reasoning"]
        and controls["computational_error"]["computation_score"]
        < controls["reference"]["computation_score"]
        and controls["wrong_interpretation"]["components"]["scientific_diagnosis"]
        < controls["reference"]["components"]["scientific_diagnosis"]
        and controls["wrong_decision"]["components"]["decision"] == 0.0
        and controls["bad_recovery"]["components"]["recovery_design"]
        < controls["reference"]["components"]["recovery_design"]
        for controls in partial.values()
    )
    gates = {
        "reference_solver_at_least_95": reference_minimum
        >= float(config["acceptance_gates"]["reference_minimum"]),
        "expert_separation_every_family": all(separation.values()),
        "mechanical_baseline_below_60": mechanical_mean
        < float(config["acceptance_gates"]["mechanical_baseline_maximum"]),
        "universal_policies_fail": all(value < 60.0 for value in universal_means.values()),
        "keyword_hacking_has_zero_effect": all(
            abs(value) < 1e-12 for value in keyword_deltas
        ),
        "public_workspace_has_no_private_answer_leakage": not leakage,
        "partial_credit_is_component_specific": partial_gate,
        "wrong_resources_do_not_receive_resource_credit": all(
            not row["resource_selection_correct"] for row in wrong_resource_rows
        ),
        "every_pair_changes_reference_decision": all(pair_transitions.values()),
        "every_ladder_contains_a_decision_transition": all(
            len(values) >= 2 for values in ladder_decisions.values()
        ),
        "schema_or_horizon_not_primary": partial_gate and reference_minimum >= 95.0,
    }
    artifact = {
        "schema_version": "0.4",
        "generated_at": datetime.now(UTC).isoformat(),
        "model_calls": 0,
        "config_validation": validation,
        "gates": gates,
        "all_gates_pass": all(gates.values()),
        "reference_minimum": reference_minimum,
        "expert_separation": separation,
        "mechanical_baseline_mean": mechanical_mean,
        "universal_policy_means": universal_means,
        "keyword_score_deltas": keyword_deltas,
        "leakage_findings": leakage,
        "paired_decision_transitions": pair_transitions,
        "ladder_decision_sets": {
            name: sorted(values) for name, values in ladder_decisions.items()
        },
        "reference_rows": reference_rows,
        "wrong_resource_rows": wrong_resource_rows,
        "partial_credit_controls": partial,
    }
    _write(CONTROLS_PATH, artifact)
    print(json.dumps({key: artifact[key] for key in ("all_gates_pass", "gates")}, indent=2))
    return 0 if artifact["all_gates_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

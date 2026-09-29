#!/usr/bin/env python3
"""Run deterministic construct-validity controls for the unfrozen v0.6 suite."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uc_bench.errors import ContractError
from uc_bench.hard_suite_v05 import _read_object, _write_json
from uc_bench.hard_suite_v06 import (
    ALL_ARTIFACTS,
    V06Builder,
    V06Environment,
    _reference_exists,
    grade_v06,
    iter_v06_scenarios,
    reference_v06_final,
    reference_v06_post_validation,
    reference_v06_precommit,
    validate_v06_config,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUILD_ROOT = PROJECT_ROOT / "build" / "hard_suite_v06_controls"
OUTPUT_PATH = PROJECT_ROOT / "artifacts" / "diagnostics" / "hard_suite_v06_controls.json"

Mutator = Callable[[str, Any], None]


def _run(
    scenario_id: str,
    label: str,
    *,
    precommit_mutator: Mutator | None = None,
    post_validation_mutator: Mutator | None = None,
    final_mutator: Mutator | None = None,
) -> dict[str, Any]:
    package = V06Builder(PROJECT_ROOT).build(
        scenario_id, output_root=BUILD_ROOT / label, replace=True
    )
    environment = V06Environment(package)
    reference_v06_precommit(package, PROJECT_ROOT)
    if precommit_mutator:
        precommit_mutator(label, package)
    environment.commit_validation_plan()
    environment.reveal_validation()
    reference_v06_post_validation(package)
    if post_validation_mutator:
        post_validation_mutator(label, package)
    environment.request_followup()
    reference_v06_final(package, str(environment.selected_resource or "none"))
    if final_mutator:
        final_mutator(label, package)
    environment.submit_diligence()
    return grade_v06(
        PROJECT_ROOT,
        package,
        selected_resource=environment.selected_resource,
        commitment_immutable=True,
        completion_accepted=True,
    ).to_dict()


def _mutate_json(package: Any, relative: str, mutate: Callable[[dict[str, Any]], None]) -> None:
    path = package.workspace_root / relative
    value = _read_object(path)
    mutate(value)
    _write_json(path, value)


def _alternative(_: str, package: Any) -> None:
    def mutate(value: dict[str, Any]) -> None:
        value["uncertainty_method"] = "Bayesian hierarchical posterior interval by patient and site"
        value["primary_estimand"] = "External patient-level risk separation and decision utility"
        value["metric_families"] = [
            "ROC AUC discrimination",
            "posterior uncertainty",
            "calibration by Brier loss",
            "decision net benefit utility",
        ]

    _mutate_json(package, ALL_ARTIFACTS[6], mutate)


def _paraphrase(_: str, package: Any) -> None:
    def mutate(value: dict[str, Any]) -> None:
        value["uncertainty_method"] = (
            "Clusters of observations belonging to one person remain together."
        )
        value["primary_estimand"] = "Patient-scale transport evidence for the locked score."
        for item in value["live_hypotheses"]:
            item["description"] = f"Reworded explanation: {item['id']}"

    _mutate_json(package, ALL_ARTIFACTS[6], mutate)


def _mediocre_pre(_: str, package: Any) -> None:
    inventory = package.workspace_root / ALL_ARTIFACTS[0]
    lines = inventory.read_text(encoding="utf-8").splitlines()
    headers = lines[0].split(",")
    for index in range(1, len(lines)):
        fields = lines[index].split(",")
        fields[headers.index("role")] = "unknown_role"
        fields[headers.index("row_count")] = "1"
        if fields[headers.index("cohort_id")] == "EXTERNAL-01":
            fields[headers.index("drug")] = "unmapped_drug"
        lines[index] = ",".join(fields)
    inventory.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def provenance(value: dict[str, Any]) -> None:
        value["manifest_assets_checked"] = False
        value["outcomes_sealed_before_commit"] = False
        value["sponsor_attestations_treated_as_ground_truth"] = True
        value["licence_scope"] = "unknown"

    _mutate_json(package, ALL_ARTIFACTS[1], provenance)
    identity = package.workspace_root / ALL_ARTIFACTS[2]
    lines = identity.read_text(encoding="utf-8").splitlines()
    headers = lines[0].split(",")
    for index in range(1, len(lines)):
        fields = lines[index].split(",")
        sample = fields[headers.index("sample_id")]
        fields[headers.index("canonical_patient_id")] = sample
        fields[headers.index("dependence_cluster")] = sample
        fields[headers.index("linkage_status")] = "independent_row"
        lines[index] = ",".join(fields)
    identity.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def endpoint(value: dict[str, Any]) -> None:
        value["ambiguity_status"] = "unresolved"
        value["endpoint_transfer_status"] = "unresolved"
        value["sensitivity_plan"] = {}

    _mutate_json(package, ALL_ARTIFACTS[3], endpoint)

    def preprocessing(value: dict[str, Any]) -> None:
        expected = package.private_scenario["states"]["preprocessing"] == "blocked"
        value["steps"] = []
        value["outcomes_used_during_fit"] = not expected
        value["validation_data_used_to_fit_transforms"] = not expected
        value["leakage_status"] = "invalid"
        value["platform_transfer_status"] = "unresolved"

    _mutate_json(package, ALL_ARTIFACTS[4], preprocessing)
    reproduction = package.workspace_root / ALL_ARTIFACTS[5]
    lines = reproduction.read_text(encoding="utf-8").splitlines()
    headers = lines[0].split(",")
    for index in range(1, len(lines)):
        fields = lines[index].split(",")
        fields[headers.index("reproduced_probability")] = "0.5"
        fields[headers.index("absolute_error")] = "0"
        fields[headers.index("model_sha256")] = "unverified"
        lines[index] = ",".join(fields)
    reproduction.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def plan(value: dict[str, Any]) -> None:
        value["dependence_preserved"] = False
        value["uncertainty_preserves_dependence"] = False
        value["reports_discrimination"] = False
        value["reports_uncertainty"] = False
        value["reports_calibration"] = False
        value["reports_decision_utility"] = False
        value["decision_rule"] = {}
        value["pre_reveal_decision"] = "advance"

    _mutate_json(package, ALL_ARTIFACTS[6], plan)


def _mediocre_post(_: str, package: Any) -> None:
    def validation(value: dict[str, Any]) -> None:
        expected = package.private_scenario["states"]["preprocessing"] == "blocked"
        value["committed_plan_honoured"] = False
        value["dependence_preserved"] = False
        value["preprocessing_outcome_blind"] = expected
        value["metrics"] = {}
        value["claim_statuses"] = {}
        value["provisional_decision"] = "advance"
        value["dominant_uncertainty"] = ""

    _mutate_json(package, ALL_ARTIFACTS[7], validation)

    def memo(value: dict[str, Any]) -> None:
        value["resource_comparisons"] = value["resource_comparisons"][:2]
        value["selected_resource_id"] = "R6"
        value["expected_effect"] = "ineffective"
        value["smallest_discriminating_action"] = ""

    _mutate_json(package, ALL_ARTIFACTS[8], memo)


def _mediocre_final(_: str, package: Any) -> None:
    def final(value: dict[str, Any]) -> None:
        value["decision"] = "advance"
        value["claim_statuses"] = {}
        value["intervention_effect"] = "misleading_reassurance"
        value["belief_update"]["direction"] = "increase"
        value["smallest_next_action"]["class"] = "none"
        value["limitations"] = []
        value["supported_claims"] = []

    _mutate_json(package, ALL_ARTIFACTS[9], final)


def _ordinary_error(_: str, package: Any) -> None:
    _mutate_json(
        package,
        ALL_ARTIFACTS[3],
        lambda value: value.update({"endpoint_transfer_status": "unresolved"}),
    )


def _universal_mutators(policy: str) -> tuple[Mutator, Mutator, Mutator]:
    decision = {
        "advance": "advance",
        "abstain": "insufficient_evidence",
        "stop": "stop",
    }[policy]

    def pre(_: str, package: Any) -> None:
        _mutate_json(
            package,
            ALL_ARTIFACTS[6],
            lambda value: value.update({"pre_reveal_decision": decision}),
        )

    def post(_: str, package: Any) -> None:
        _mutate_json(
            package,
            ALL_ARTIFACTS[7],
            lambda value: value.update({"provisional_decision": decision}),
        )

        def memo(value: dict[str, Any]) -> None:
            value["selected_resource_id"] = "none"
            value["expected_effect"] = "ineffective"

        _mutate_json(package, ALL_ARTIFACTS[8], memo)

    def final(_: str, package: Any) -> None:
        def mutate(value: dict[str, Any]) -> None:
            value["decision"] = decision
            value["intervention_effect"] = "ineffective"
            value["belief_update"]["direction"] = "unchanged"
            value["smallest_next_action"]["class"] = "none"

        _mutate_json(package, ALL_ARTIFACTS[9], mutate)

    return pre, post, final


def main() -> int:
    config_status = validate_v06_config(PROJECT_ROOT)
    scenarios = iter_v06_scenarios(PROJECT_ROOT)
    rows = []
    for scenario in scenarios:
        scenario_id = str(scenario["scenario_id"])
        reference = _run(scenario_id, f"reference-{scenario_id}")
        alternative = _run(
            scenario_id,
            f"alternative-{scenario_id}",
            precommit_mutator=_alternative,
        )
        paraphrase = _run(
            scenario_id,
            f"paraphrase-{scenario_id}",
            precommit_mutator=_paraphrase,
        )
        mediocre = _run(
            scenario_id,
            f"mediocre-{scenario_id}",
            precommit_mutator=_mediocre_pre,
            post_validation_mutator=_mediocre_post,
            final_mutator=_mediocre_final,
        )
        ordinary = _run(
            scenario_id,
            f"ordinary-{scenario_id}",
            precommit_mutator=_ordinary_error,
        )
        rows.append(
            {
                "scenario_id": scenario_id,
                "reference": reference,
                "alternative": alternative,
                "paraphrase": paraphrase,
                "mediocre": mediocre,
                "ordinary_error": ordinary,
            }
        )
    universal: dict[str, Any] = {}
    for policy in ("advance", "abstain", "stop"):
        pre, post, final = _universal_mutators(policy)
        results = [
            _run(
                str(scenario["scenario_id"]),
                f"universal-{policy}-{scenario['scenario_id']}",
                precommit_mutator=pre,
                post_validation_mutator=post,
                final_mutator=final,
            )
            for scenario in scenarios
        ]
        universal[policy] = {
            "mean_decision_policy_score": sum(row["decision_policy_score"] for row in results)
            / len(results),
            "results": results,
        }

    immutability_package = V06Builder(PROJECT_ROOT).build(
        str(scenarios[0]["scenario_id"]),
        output_root=BUILD_ROOT / "immutability",
        replace=True,
    )
    reference_v06_precommit(immutability_package, PROJECT_ROOT)
    immutability_environment = V06Environment(immutability_package)
    immutability_environment.commit_validation_plan()
    with (immutability_package.workspace_root / ALL_ARTIFACTS[0]).open(
        "a", encoding="utf-8"
    ) as handle:
        handle.write("tamper\n")
    immutability_detected = False
    try:
        immutability_environment.reveal_validation()
    except ContractError:
        immutability_detected = True

    reference_min = min(row["reference"]["coverage_adjusted_scientific_score"] for row in rows)
    alternative_min = min(row["alternative"]["coverage_adjusted_scientific_score"] for row in rows)
    paraphrase_difference = max(
        abs(
            row["reference"]["coverage_adjusted_scientific_score"]
            - row["paraphrase"]["coverage_adjusted_scientific_score"]
        )
        for row in rows
    )
    mediocre_below_every_artifact = all(
        all(
            row["mediocre"]["artifact_scores"][artifact]
            < row["reference"]["artifact_scores"][artifact]
            for artifact in row["reference"]["artifact_scores"]
        )
        for row in rows
    )
    ordinary_min = min(row["ordinary_error"]["coverage_adjusted_scientific_score"] for row in rows)
    universal_max = max(value["mean_decision_policy_score"] for value in universal.values())
    task_text = (PROJECT_ROOT / "tasks/hard_suite_v06/TASK.md").read_text(encoding="utf-8")
    leakage_free = all(
        str(scenario["scenario_id"]) not in task_text and str(scenario["seed"]) not in task_text
        for scenario in scenarios
    )
    config = _read_object(PROJECT_ROOT / "configs/hard_suite_v06.json")
    maximum_artifact_weight = max(float(row["weight"]) for row in config["artifacts"])
    mechanical_weight = sum(
        float(row["weight"]) for row in config["artifacts"] if row["id"] in {"A01", "A02", "A06"}
    )
    gates = {
        "reference_solver_at_least_90": reference_min >= 90,
        "alternative_valid_workflow_at_least_90": alternative_min >= 90,
        "paraphrase_semantically_invariant": paraphrase_difference <= 0.01,
        "mediocre_below_reference_every_artifact_family": mediocre_below_every_artifact,
        "universal_policies_below_50": universal_max < 50,
        "ordinary_error_retains_at_least_50": ordinary_min >= 50,
        "committed_artifact_tampering_detected": immutability_detected,
        "task_text_has_no_scenario_id_or_seed": leakage_free,
        "path_traversal_cannot_fake_evidence": not _reference_exists(
            PROJECT_ROOT, "../private_answer.json"
        ),
        "maximum_artifact_weight_is_10_percent": maximum_artifact_weight <= 10,
        "mechanical_families_are_at_most_30_percent": mechanical_weight <= 30,
        "heldout_is_separate_and_unfrozen": config_status["heldout_status"]
        == "sealed_unfrozen_no_model_exposure",
    }
    output = {
        "schema_version": "0.6-controls-1",
        "generated_at": datetime.now(UTC).isoformat(),
        "suite_status": config_status,
        "model_calls": 0,
        "astra_requests": 0,
        "summary": {
            "reference_minimum": reference_min,
            "alternative_minimum": alternative_min,
            "paraphrase_maximum_absolute_difference": paraphrase_difference,
            "ordinary_error_minimum": ordinary_min,
            "universal_policy_maximum": universal_max,
        },
        "gates": gates,
        "all_local_gates_pass": all(gates.values()),
        "scenario_controls": rows,
        "universal_policy_controls": universal,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"summary": output["summary"], "gates": gates}, indent=2))
    return 0 if output["all_local_gates_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

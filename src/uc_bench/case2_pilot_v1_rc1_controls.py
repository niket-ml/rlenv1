"""Zero-cost reference and adversarial controls for the Case 2 RC1 candidate."""

from __future__ import annotations

import collections
import copy
import csv
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import uc_bench.mmmvp_open_rc17_controls as legacy
from uc_bench.case2_pilot_v1_rc1_contract import SCHEMA_VERSION
from uc_bench.case2_pilot_v1_rc1_environment import Case2PilotRC1Environment
from uc_bench.case2_pilot_v1_rc1_semantics import (
    _expected_resource_results,
    _resource_effect,
    _resource_files,
    _site_summary,
    evaluate_case2_submission,
)
from uc_bench.mmmvp_open_calculations import CanonicalRow


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(rows: list[dict[str, Any]]) -> list[CanonicalRow]:
    return [
        CanonicalRow(
            entity_id=str(row["unit"]),
            source_record_ids=tuple(sorted(str(row["records"]).split("|"))),
            prediction=float(row["score"]),
            outcome=int(row["label"]),
            split="VALIDATION",
            contexts=tuple(sorted(filter(None, str(row.get("setting", "")).split("|")))),
        )
        for row in rows
    ]


def _decision(
    disposition: str,
    action_scope: str,
    context_status: str,
    *,
    identity_claim_basis: str = "PROVISIONAL_UNIT",
) -> dict[str, Any]:
    if action_scope == "GENERAL_MULTISITE_ADVANCEMENT":
        stage, use_scope, permitted, target = (
            "EXTERNAL_VALIDATION",
            "RESEARCH_PROBABILITY",
            True,
            "EXTERNAL_COHORT",
        )
    elif action_scope == "TARGETED_CONTEXT_INVESTIGATION":
        stage, use_scope, permitted, target = (
            "INTERNAL_VALIDATION",
            "RETROSPECTIVE_AUDIT",
            False,
            "EXTERNAL_COHORT",
        )
    elif action_scope == "END_DEVELOPMENT_PATH":
        stage, use_scope, permitted, target = "STOPPED", "NO_USE", False, "NO_NEW_EVIDENCE"
    else:
        stage, use_scope, permitted, target = (
            "INTERNAL_VALIDATION",
            "NO_USE",
            False,
            "EXTERNAL_COHORT",
        )
    return {
        "development_stage": stage,
        "disposition": disposition,
        "use_scope": use_scope,
        "allowed_use": ["Only the bounded activity encoded by action_scope."],
        "prohibited_use": ["No use beyond the verified evidence and current context status."],
        "unresolved_gates": ["Resolve every failed or non-evaluable committed criterion."],
        "required_next_evidence": ["Evidence directed at the encoded next_evidence_target."],
        "action_scope": action_scope,
        "current_context_status": context_status,
        "multisite_probability_use_permitted": permitted,
        "next_evidence_target": target,
        "identity_claim_basis": identity_claim_basis,
    }


def _candidate_plan(
    workspace: Path,
    aggregation: str,
    context_metric: str,
) -> tuple[dict[str, Any], set[str]]:
    primary_context_metric = "SITE_WEIGHTED_ROC_AUC" if context_metric == "BOTH" else context_metric
    plan, included = legacy._plan(  # noqa: SLF001
        workspace,
        aggregation=aggregation,
        probability_metric="BRIER_SCORE",
        utility_metric="NET_BENEFIT",
        context_metric=primary_context_metric,
        exclude_pending=False,
        thresholds={
            "DISCRIMINATION": 0.70,
            "PROBABILITY_ACCURACY": 0.23,
            "CALIBRATION": 0.12,
            "THRESHOLD_UTILITY": 0.02,
            "CONTEXT_ROBUSTNESS": (
                0.65 if primary_context_metric == "SITE_WEIGHTED_ROC_AUC" else 0.55
            ),
        },
    )
    if context_metric == "BOTH":
        context = copy.deepcopy(
            next(
                row for row in plan["decision_criteria"] if row["property"] == "CONTEXT_ROBUSTNESS"
            )
        )
        context.update(
            {
                "criterion_id": "G_CONTEXT_ROBUSTNESS_WORST",
                "calculation_id": "C_CONTEXT_ROBUSTNESS_WORST",
                "metric": "WORST_SITE_ROC_AUC",
                "threshold": 0.55,
            }
        )
        plan["decision_criteria"].append(context)
    plan["schema_version"] = SCHEMA_VERSION
    specification = plan["prospective_specification"]
    specification["biological_unit"] = "PROVISIONAL_LINKAGE_UNIT"
    specification["identity_basis"] = (
        "PROVISIONAL_FINGERPRINT_WEIGHTED_ROWS"
        if aggregation == "NONE"
        else "PROVISIONAL_FINGERPRINT_AGGREGATION"
    )
    plan["planned_analyses"][0]["analysis_unit"] = (
        "Source biopsies retaining fingerprint-cluster dependence."
        if aggregation == "NONE"
        else "Outcome-blind provisional fingerprint linkage units."
    )
    return plan, included


def _criterion_passes(plan: dict[str, Any], calculations: list[dict[str, Any]]) -> tuple[bool, str]:
    by_id = {row["calculation_id"]: row for row in calculations}
    outcomes: list[bool] = []
    context_outcomes: list[bool] = []
    for criterion in plan["decision_criteria"]:
        calculation = by_id[criterion["calculation_id"]]
        passed = (
            float(calculation["reported_value"]) >= float(criterion["threshold"])
            if criterion["comparator"] == "AT_LEAST"
            else float(calculation["reported_value"]) <= float(criterion["threshold"])
        )
        if criterion["property"] == "DISCRIMINATION":
            passed = passed and float(calculation["uncertainty"]["lower"]) >= 0.58
        outcomes.append(passed)
        if criterion["property"] == "CONTEXT_ROBUSTNESS":
            context_outcomes.append(passed)
    return all(outcomes), "PASSED" if context_outcomes and all(context_outcomes) else "FAILED"


def _followup(
    resource: str,
    *,
    all_passed: bool,
    context_status: str,
    decision_override: tuple[str, str] | None,
) -> dict[str, Any]:
    question = legacy._resource_question(resource)  # noqa: SLF001
    target = {
        "none": "NO_NEW_EVIDENCE",
        "X17": "RECORD_LINKAGE",
        "X24": "ENDPOINT_REVIEW",
        "X31": "PIPELINE_REPLAY",
        "X46": "EXTERNAL_COHORT",
        "X58": "ADDITIONAL_SAMPLE",
        "X63": "EXPERT_REVIEW",
    }[resource]
    if decision_override is not None:
        disposition, scope = decision_override
        stable = _decision(disposition, scope, context_status)
    elif all_passed:
        stable = _decision("CONTINUE", "GENERAL_MULTISITE_ADVANCEMENT", context_status)
    else:
        stable = _decision("PAUSE", "HOLD_CURRENT_CLAIM", context_status)
    blocked = _decision("PAUSE", "HOLD_CURRENT_CLAIM", context_status)
    return {
        "schema_version": SCHEMA_VERSION,
        "decision_question_id": "Q_RESOURCE",
        "decision_question": (
            "Which remaining uncertainty, if any, changes the immediate bounded action?"
        ),
        "decision_question_type": question,
        "chosen_resource": resource,
        "evidence_target": target,
        "materiality_threshold": 0 if resource in {"none", "X17", "X63"} else 0.05,
        "live_explanations": [
            {
                "explanation_id": "E_SUPPORT",
                "statement": "The selected evidence supports the bounded action.",
                "distinguishing_evidence": (
                    "A valid returned result resolves the declared question."
                ),
            },
            {
                "explanation_id": "E_LIMIT",
                "statement": "The selected evidence exposes or preserves a blocker.",
                "distinguishing_evidence": (
                    "A valid returned result does not resolve the declared question."
                ),
            },
        ],
        "alternatives_considered": [
            {"resource_id": resource, "limitations": "Answers only the declared question."},
            {"resource_id": "X63", "limitations": "Does not create missing empirical evidence."},
        ],
        "result_contingencies": [
            {
                "contingency_id": "K_SUPPORT",
                "observable_result": (
                    "The returned evidence resolves or materially reduces the uncertainty."
                ),
                "hypothesis_updates": [
                    {"hypothesis_id": "H_SUPPORT", "direction": "INCREASE"},
                    {"hypothesis_id": "H_LIMIT", "direction": "DECREASE"},
                ],
                "next_decision": stable,
                "next_action": "Apply only the bounded encoded action.",
            },
            {
                "contingency_id": "K_LIMIT",
                "observable_result": (
                    "The returned evidence exposes a blocker or misleading reassurance."
                ),
                "hypothesis_updates": [
                    {"hypothesis_id": "H_SUPPORT", "direction": "DECREASE"},
                    {"hypothesis_id": "H_LIMIT", "direction": "INCREASE"},
                ],
                "next_decision": blocked,
                "next_action": "Contain the current claim.",
            },
            {
                "contingency_id": "K_UNCHANGED",
                "observable_result": "No new decision-relevant evidence is returned.",
                "hypothesis_updates": [
                    {"hypothesis_id": "H_SUPPORT", "direction": "UNCHANGED"},
                    {"hypothesis_id": "H_LIMIT", "direction": "UNCHANGED"},
                ],
                "next_decision": stable,
                "next_action": "Retain the evidence-supported bounded action.",
            },
        ],
        "beliefs_before": {"H_SUPPORT": 0.5, "H_LIMIT": 0.5},
        "current_decision": {
            "development_stage": "INTERNAL_VALIDATION",
            "disposition": "PAUSE",
            "use_scope": "NO_USE",
            "allowed_use": ["Retrospective audit."],
            "prohibited_use": ["No operational use."],
            "unresolved_gates": ["Committed validation not yet interpreted."],
            "required_next_evidence": ["Complete the committed analysis."],
        },
        "evidence_refs": legacy._resource_basis(resource),  # noqa: SLF001
    }


def build_reference(
    project_root: Path,
    run_root: Path,
    *,
    aggregation: str = "MEAN",
    context_metric: str = "SITE_WEIGHTED_ROC_AUC",
    resource: str = "none",
    decision_override: tuple[str, str] | None = None,
) -> tuple[dict[str, Any], Path]:
    """Build a complete valid episode from disclosed rules, without a model call."""

    environment = Case2PilotRC1Environment(project_root, run_root)
    plan, included = _candidate_plan(run_root, aggregation, context_metric)
    accepted = environment.commit_validation_plan(json.dumps(plan))
    assert accepted["accepted"], accepted
    environment.reveal_validation()

    primary_rows = legacy._primary_rows(run_root, aggregation)  # noqa: SLF001
    _write_csv(run_root / "work/primary_analysis.csv", primary_rows)
    structure = "SOURCE_RECORD_CLUSTERED" if aggregation == "NONE" else "ENTITY_AGGREGATED"
    estimator = "ENTITY_WEIGHTED" if aggregation == "NONE" else "EMPIRICAL"
    calculations = [
        legacy._calculation(  # noqa: SLF001
            criterion["calculation_id"],
            criterion["property"],
            criterion["metric"],
            "TABLE_PRIMARY",
            primary_rows,
            included,
            structure=structure,
            aggregation=aggregation,
            estimator=estimator,
            role="PRIMARY",
            output_id="OUTPUT_RESULTS",
        )
        for criterion in plan["decision_criteria"]
    ]
    all_passed, context_status = _criterion_passes(plan, calculations)
    followup = _followup(
        resource,
        all_passed=all_passed,
        context_status=context_status,
        decision_override=decision_override,
    )
    accepted = environment.commit_followup_plan(json.dumps(followup))
    assert accepted["accepted"], accepted
    environment.purchase_resource(resource)

    artifacts: list[dict[str, Any]] = [
        {
            "artifact_id": "TABLE_PRIMARY",
            "path": "work/primary_analysis.csv",
            "role": "ANALYSIS_TABLE",
            "source_paths": [
                "data/cohort_metadata.csv",
                "data/locked_predictions.csv",
                "revealed/validation_outcomes.csv",
            ],
            "column_map": {
                "entity_id": "unit",
                "source_record_ids": "records",
                "prediction": "score",
                "outcome": "label",
                "split": "partition",
                "context": "setting",
            },
            "analysis_structure": structure,
            "aggregation": aggregation,
            "identity_basis": plan["prospective_specification"]["identity_basis"],
        },
        {
            "artifact_id": "OUTPUT_RESULTS",
            "path": "work/primary_results.json",
            "role": "CALCULATION_OUTPUT",
            "source_paths": ["work/primary_analysis.csv"],
        },
    ]
    resource_rows = legacy._resource_rows(run_root, resource)  # noqa: SLF001
    if resource == "X58":
        predictions = _read_csv(run_root / "purchased/X58/additional_predictions.csv")
        outcomes = {
            row["patient_key"]: row["week6_response"]
            for row in _read_csv(run_root / "purchased/X58/additional_outcomes.csv")
        }
        resource_rows = [
            {
                "unit": row["patient_key"],
                "records": row["patient_key"],
                "score": row["predicted_probability"],
                "label": outcomes[row["patient_key"]],
                "partition": "VALIDATION",
                "setting": row.get("site", ""),
            }
            for row in predictions
        ]
    resource_calculation_ids: list[str] = []
    if resource_rows:
        _write_csv(run_root / "work/resource_analysis.csv", resource_rows)
        sources = {
            "X17": [
                "purchased/X17/canonical_person_crosswalk.csv",
                "revealed/validation_outcomes.csv",
                "data/cohort_metadata.csv",
                "data/locked_predictions.csv",
            ],
            "X31": [
                "purchased/X31/replay_predictions.csv",
                "revealed/validation_outcomes.csv",
            ],
            "X46": [
                "purchased/X46/matched_predictions.csv",
                "purchased/X46/matched_outcomes.csv",
            ],
            "X58": [
                "purchased/X58/additional_predictions.csv",
                "purchased/X58/additional_outcomes.csv",
            ],
        }[resource]
        basis = {
            "X17": "ADJUDICATED_CANONICAL_PERSON",
            "X31": "PROVISIONAL_FINGERPRINT_AGGREGATION",
            "X46": "EXTERNAL_COHORT_PERSON",
            "X58": "EXTERNAL_COHORT_PERSON",
        }[resource]
        aggregation_resource = "MEAN" if resource == "X17" else "NONE"
        artifacts.append(
            {
                "artifact_id": "TABLE_RESOURCE",
                "path": "work/resource_analysis.csv",
                "role": "ANALYSIS_TABLE",
                "source_paths": sources,
                "column_map": {
                    "entity_id": "unit",
                    "source_record_ids": "records",
                    "prediction": "score",
                    "outcome": "label",
                    "split": "partition",
                    "context": "setting",
                },
                "analysis_structure": "ENTITY_AGGREGATED",
                "aggregation": aggregation_resource,
                "identity_basis": basis,
            }
        )
        calculation_id = "C_RESOURCE"
        calculations.append(
            legacy._calculation(  # noqa: SLF001
                calculation_id,
                "FOLLOWUP",
                "ENTITY_COUNT" if resource == "X17" else "ROC_AUC",
                "TABLE_RESOURCE",
                resource_rows,
                {row["unit"] for row in resource_rows},
                structure="ENTITY_AGGREGATED",
                aggregation=aggregation_resource,
                estimator="EMPIRICAL",
                role="FOLLOWUP",
                output_id="OUTPUT_RESULTS",
            )
        )
        resource_calculation_ids.append(calculation_id)

    site_audit = _site_summary(tuple(_canonical(primary_rows)), estimator)
    output_rows = []
    for row in calculations:
        item: dict[str, Any] = {
            "calculation_id": row["calculation_id"],
            "reported_value": row["reported_value"],
        }
        if row["metric"] in {"SITE_WEIGHTED_ROC_AUC", "WORST_SITE_ROC_AUC"}:
            item["site_audit"] = site_audit
        output_rows.append(item)
    _write_json(run_root / "work/primary_results.json", {"typed_calculations": output_rows})

    expected = _expected_resource_results(run_root, resource)
    source_hashes = _resource_files(run_root, resource)
    _write_json(
        run_root / "work/resource_summary.json",
        {
            "schema_version": "case2-resource-summary-1",
            "resource_id": resource,
            "source_hashes": source_hashes,
            "results": expected,
        },
    )
    artifacts.append(
        {
            "artifact_id": "RESOURCE_SUMMARY",
            "path": "work/resource_summary.json",
            "role": "PROVENANCE",
            "source_paths": sorted(source_hashes),
        }
    )

    # Calculate effect from the independently derived resource return.  The
    # final submission selects one of the contingencies committed above.
    dummy_criteria = {
        row["criterion_id"]: (
            float(
                next(
                    item for item in calculations if item["calculation_id"] == row["calculation_id"]
                )["reported_value"]
            )
            >= float(row["threshold"])
            if row["comparator"] == "AT_LEAST"
            else float(
                next(
                    item for item in calculations if item["calculation_id"] == row["calculation_id"]
                )["reported_value"]
            )
            <= float(row["threshold"])
        )
        for row in plan["decision_criteria"]
    }
    primary_values = {
        row["metric"]: float(row["reported_value"])
        for row in calculations
        if row["role"] == "PRIMARY"
    }
    material, effect = _resource_effect(
        run_root,
        plan,
        followup,
        dummy_criteria,
        expected,
        primary_values,
    )
    if effect in {"NO_NEW_EVIDENCE", "INEFFECTIVE"}:
        contingency, after_support, after_limit = "K_UNCHANGED", 0.5, 0.5
    elif effect in {"EXPOSES_BLOCKER", "MISLEADING_REASSURANCE"}:
        contingency, after_support, after_limit = "K_LIMIT", 0.25, 0.75
    else:
        contingency, after_support, after_limit = "K_SUPPORT", 0.70, 0.30
    selected = next(
        row for row in followup["result_contingencies"] if row["contingency_id"] == contingency
    )
    decision = copy.deepcopy(selected["next_decision"])
    if resource == "X17":
        decision["identity_claim_basis"] = "ADJUDICATED_PERSON"
        selected["next_decision"]["identity_claim_basis"] = "ADJUDICATED_PERSON"
        # The commitment record must contain the identity-resolved branch.
        records = environment.records_root
        _write_json(records / "followup_plan.json", followup)
        digest = hashlib.sha256(
            json.dumps(followup, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        environment.state.followup_plan_hash = digest
        next(row for row in environment.state.event_log if row["event"] == "commit_followup_plan")[
            "digest"
        ] = digest

    finding_effect = (
        "INVALIDATES"
        if decision["disposition"] == "STOP"
        else "SUPPORTS"
        if decision["disposition"] == "CONTINUE"
        else "WEAKENS"
    )
    claims = [
        {
            "claim_id": "CLAIM_PROBABILITY",
            "statement": "A bounded provisional-unit probability claim is evaluated.",
            "status": (
                "SUPPORTED"
                if decision["action_scope"] == "GENERAL_MULTISITE_ADVANCEMENT"
                else "UNRESOLVED"
            ),
            "scope": "PROGNOSTIC_PROBABILITY",
            "evidence_refs": ["work/primary_results.json"],
            "calculation_ids": (
                ["C_DISCRIMINATION", "C_PROBABILITY_ACCURACY", "C_CALIBRATION"]
                if decision["action_scope"] == "GENERAL_MULTISITE_ADVANCEMENT"
                else []
            ),
        },
        *[
            {
                "claim_id": f"LIMIT_{scope}",
                "statement": "This broader claim is not established.",
                "status": "NOT_SUPPORTED",
                "scope": scope,
                "evidence_refs": [],
                "calculation_ids": [],
            }
            for scope in (
                "INDEPENDENT_VALIDATION",
                "CLINICAL_UTILITY",
                "TREATMENT_EFFECT",
                "CROSS_CONTEXT_TRANSPORT",
            )
        ],
    ]
    final = {
        "schema_version": SCHEMA_VERSION,
        "artifact_manifest": artifacts,
        "calculations": calculations,
        "findings": [
            {
                "finding_id": "F_PRIMARY",
                "statement": "The saved analysis supports only the encoded bounded action.",
                "status": "SUPPORTED",
                "decision_effect": finding_effect,
                "evidence_refs": ["work/primary_analysis.csv", "work/primary_results.json"],
                "calculation_ids": ["C_CONTEXT_ROBUSTNESS"],
            }
        ],
        "evidence_assessments": [
            {
                "evidence_id": "EV_RESOURCE",
                "source_paths": sorted(source_hashes),
                "eligible_for_decision": True,
                "rationale": "Returned evidence is source-hashed and independently recomputed.",
            }
        ],
        "belief_updates": [
            {
                "hypothesis_id": "H_SUPPORT",
                "before": 0.5,
                "after": after_support,
                "evidence_refs": ["work/resource_summary.json"],
                "matched_contingency_id": contingency,
            },
            {
                "hypothesis_id": "H_LIMIT",
                "before": 0.5,
                "after": after_limit,
                "evidence_refs": ["work/resource_summary.json"],
                "matched_contingency_id": contingency,
            },
        ],
        "decision": decision,
        "claims": claims,
        "remaining_uncertainties": ["Any broader person-level or operational claim remains gated."],
        "evidence_refs": [
            "intended_use.json",
            "work/primary_analysis.csv",
            "work/primary_results.json",
            "work/resource_summary.json",
        ],
        "resource_assessment": {
            "resource_id": resource,
            "question_type": followup["decision_question_type"],
            "summary_artifact_path": "work/resource_summary.json",
            "source_paths": sorted(source_hashes),
            "calculation_ids": resource_calculation_ids,
            "observed_effect": effect,
            "material": material,
        },
        "narrative_summary": "Evidence-bounded Case 2 development decision.",
    }
    accepted = environment.submit(json.dumps(final))
    assert accepted["accepted"], accepted
    return environment.export_submission(), run_root


def copy_episode(
    submission: dict[str, Any], workspace: Path, target: Path
) -> tuple[dict[str, Any], Path]:
    shutil.copytree(workspace, target)
    source_records = workspace.parent / ".mmmvp_host_records" / workspace.name
    target_records = target.parent / ".mmmvp_host_records" / target.name
    target_records.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_records, target_records)
    result = copy.deepcopy(submission)
    result["host_record_locator"] = target_records.resolve().as_posix()
    return result, target


def replace_final(submission: dict[str, Any], workspace: Path, final: dict[str, Any]) -> None:
    digest = hashlib.sha256(
        json.dumps(final, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    submission["final_submission"] = final
    submission["state"]["final_submission_hash"] = digest
    next(row for row in submission["event_log"] if row["event"] == "submit")[
        "final_submission_hash"
    ] = digest
    records = workspace.parent / ".mmmvp_host_records" / workspace.name
    _write_json(records / "final_submission.json", final)


def build_strong_context_variant(project_root: Path, run_root: Path) -> tuple[dict[str, Any], Path]:
    """Create a controlled altered-outcome fixture in which all gates pass.

    This is a local anti-policy control, not a new Case 2 condition.  Labels are
    allocated within each public site/calibration bin to track the locked
    probabilities while preserving outcome classes.  No hard-coded metric or
    decision value is used.
    """

    submission, workspace = build_reference(project_root, run_root, resource="none")
    with (workspace / "work/primary_analysis.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    grouped: dict[tuple[str, int], list[dict[str, str]]] = collections.defaultdict(list)
    for row in rows:
        bin_index = min(6, int(float(row["score"]) * 7))
        grouped[(row["setting"], bin_index)].append(row)
    for group in grouped.values():
        positive_count = round(sum(float(row["score"]) for row in group))
        ordered = sorted(group, key=lambda row: float(row["score"]), reverse=True)
        for index, row in enumerate(ordered):
            row["label"] = str(int(index < positive_count))
    _write_csv(workspace / "work/primary_analysis.csv", rows)
    label_by_entity = {row["unit"]: row["label"] for row in rows}
    with (workspace / "revealed/validation_outcomes.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        outcomes = list(csv.DictReader(handle))
    for row in outcomes:
        row["week6_response"] = label_by_entity[row["patient_key"]]
    _write_csv(workspace / "revealed/validation_outcomes.csv", outcomes)

    plan = submission["validation_plan"]
    included = {row["unit"] for row in rows}
    calculations = [
        legacy._calculation(  # noqa: SLF001
            criterion["calculation_id"],
            criterion["property"],
            criterion["metric"],
            "TABLE_PRIMARY",
            rows,
            included,
            structure="ENTITY_AGGREGATED",
            aggregation="MEAN",
            estimator="EMPIRICAL",
            role="PRIMARY",
            output_id="OUTPUT_RESULTS",
        )
        for criterion in plan["decision_criteria"]
    ]
    site_audit = _site_summary(tuple(_canonical(rows)), "EMPIRICAL")
    _write_json(
        workspace / "work/primary_results.json",
        {
            "typed_calculations": [
                {
                    "calculation_id": row["calculation_id"],
                    "reported_value": row["reported_value"],
                    **(
                        {"site_audit": site_audit}
                        if row["metric"] in {"SITE_WEIGHTED_ROC_AUC", "WORST_SITE_ROC_AUC"}
                        else {}
                    ),
                }
                for row in calculations
            ]
        },
    )
    followup = copy.deepcopy(submission["followup_plan"])
    general = _decision("CONTINUE", "GENERAL_MULTISITE_ADVANCEMENT", "PASSED")
    next(row for row in followup["result_contingencies"] if row["contingency_id"] == "K_UNCHANGED")[
        "next_decision"
    ] = copy.deepcopy(general)
    submission["followup_plan"] = followup

    final = copy.deepcopy(submission["final_submission"])
    final["calculations"] = calculations
    final["decision"] = copy.deepcopy(general)
    final["findings"][0]["decision_effect"] = "SUPPORTS"
    probability_claim = next(
        row for row in final["claims"] if row["claim_id"] == "CLAIM_PROBABILITY"
    )
    probability_claim["status"] = "SUPPORTED"
    probability_claim["calculation_ids"] = [
        "C_DISCRIMINATION",
        "C_PROBABILITY_ACCURACY",
        "C_CALIBRATION",
    ]
    submission["final_submission"] = final
    return submission, workspace


def grade(submission: dict[str, Any], workspace: Path) -> dict[str, Any]:
    return evaluate_case2_submission(workspace, submission).to_dict()


__all__ = [
    "build_reference",
    "build_strong_context_variant",
    "copy_episode",
    "grade",
    "replace_final",
]

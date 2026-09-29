from __future__ import annotations

import copy
import csv
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from uc_bench.case2_pilot_v1_rc1_audit import HISTORICAL_FIXTURE_HASHES
from uc_bench.case2_pilot_v1_rc1_contract import (
    PUBLIC_CONTRACT,
    validate_validation_plan,
)
from uc_bench.case2_pilot_v1_rc1_controls import (
    _candidate_plan,
    _followup,
    build_reference,
    build_strong_context_variant,
    grade,
    replace_final,
)
from uc_bench.case2_pilot_v1_rc1_environment import (
    DEVELOPMENT_ACTION_CONTRACT,
    PUBLIC_SUPPORT_MODULES,
    Case2PilotRC1Environment,
    OpenProtocolError,
)
from uc_bench.case2_pilot_v1_rc1_semantics import (
    _resource_effect,
    evaluate_case2_submission,
)

ROOT = Path(__file__).resolve().parents[1]
RC16_RUNS = ROOT / "build/uc_bench_mmmvp_open_rc14_runs"


def _statuses(value: dict) -> dict[str, bool]:
    return {row["requirement_id"]: row["passed"] for row in value["requirements"]}


def _sync_output(workspace: Path, final: dict) -> None:
    rows = []
    original = json.loads((workspace / "work/primary_results.json").read_text())
    audit = {row["calculation_id"]: row.get("site_audit") for row in original["typed_calculations"]}
    for calculation in final["calculations"]:
        row = {
            "calculation_id": calculation["calculation_id"],
            "reported_value": calculation["reported_value"],
        }
        if audit.get(calculation["calculation_id"]) is not None:
            row["site_audit"] = audit[calculation["calculation_id"]]
        rows.append(row)
    (workspace / "work/primary_results.json").write_text(
        json.dumps({"typed_calculations": rows}, indent=2, sort_keys=True) + "\n"
    )


def test_public_packet_defines_identity_context_and_methods(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    Case2PilotRC1Environment(ROOT, workspace)
    contract = json.loads((workspace / "submission_contract.json").read_text())
    methods = json.loads((workspace / "scientific_methods.json").read_text())
    assert contract["identity_semantics"]["fingerprint_cluster"].startswith("provisional")
    assert contract["non_vacuity"]["CONTEXT_ROBUSTNESS"]["metric_bounds"] == {
        "SITE_WEIGHTED_ROC_AUC": {"at_least": 0.65},
        "WORST_SITE_ROC_AUC": {"at_least": 0.55},
    }
    assert "1 divided by" in methods["deterministic_details"]["ENTITY_WEIGHTED"]
    assert "lexicographically" in methods["deterministic_details"]["FIRST"]
    assert "Conflicting outcomes" in methods["deterministic_details"]["post_X17_outcomes"]
    assert len(contract["scientific_property_completeness_audit"]) == 10
    criteria_contract = next(
        row
        for row in contract["objects"]["validation_plan"]["fields"]
        if row["path"] == "decision_criteria"
    )
    assert "exact_items" not in criteria_contract
    assert criteria_contract["minimum_items"] == 5
    assert criteria_contract["maximum_items"] == 6


@pytest.mark.parametrize(
    ("metric", "threshold", "valid"),
    [
        ("SITE_WEIGHTED_ROC_AUC", 0.5001, False),
        ("SITE_WEIGHTED_ROC_AUC", 0.51, False),
        ("SITE_WEIGHTED_ROC_AUC", 0.65, True),
        ("WORST_SITE_ROC_AUC", 0.5499, False),
        ("WORST_SITE_ROC_AUC", 0.55, True),
    ],
)
def test_context_threshold_floors(
    tmp_path: Path, metric: str, threshold: float, valid: bool
) -> None:
    submission, _ = build_reference(
        ROOT,
        tmp_path / "source",
        context_metric=(
            "WORST_SITE_ROC_AUC" if metric == "WORST_SITE_ROC_AUC" else "SITE_WEIGHTED_ROC_AUC"
        ),
    )
    plan = copy.deepcopy(submission["validation_plan"])
    criterion = next(
        row for row in plan["decision_criteria"] if row["property"] == "CONTEXT_ROBUSTNESS"
    )
    criterion["metric"] = metric
    criterion["threshold"] = threshold
    plan["prospective_specification"]["context_metric"] = metric
    result = validate_validation_plan(plan)
    assert result.valid is valid


@pytest.mark.parametrize("aggregation", ["MEAN", "NONE"])
def test_two_materially_different_primary_workflows_pass(tmp_path: Path, aggregation: str) -> None:
    submission, workspace = build_reference(
        ROOT, tmp_path / aggregation.lower(), aggregation=aggregation
    )
    result = grade(submission, workspace)
    assert result["complete_mission_success"]
    assert result["partial_scientific_quality"] == 100.0


def test_both_disclosed_context_criteria_pass_structural_and_scientific_validation(
    tmp_path: Path,
) -> None:
    submission, workspace = build_reference(ROOT, tmp_path / "both", context_metric="BOTH")
    assert grade(submission, workspace)["complete_mission_success"]


@pytest.mark.parametrize(
    ("resource", "mission_success"),
    [
        ("none", True),
        ("X17", True),
        ("X24", True),
        ("X31", False),
        ("X46", True),
        ("X58", True),
        ("X63", False),
    ],
)
def test_every_declared_resource_path_is_recomputed(
    tmp_path: Path, resource: str, mission_success: bool
) -> None:
    submission, workspace = build_reference(ROOT, tmp_path / resource, resource=resource)
    result = grade(submission, workspace)
    assert result["complete_mission_success"] is mission_success
    assert _statuses(result)["decision_relevant_followup"] is mission_success


def test_provisional_units_cannot_be_called_adjudicated_people_before_x17(
    tmp_path: Path,
) -> None:
    submission, workspace = build_reference(ROOT, tmp_path / "source")
    final = copy.deepcopy(submission["final_submission"])
    next(row for row in final["artifact_manifest"] if row["artifact_id"] == "TABLE_PRIMARY")[
        "identity_basis"
    ] = "ADJUDICATED_CANONICAL_PERSON"
    replace_final(submission, workspace, final)
    result = grade(submission, workspace)
    assert not _statuses(result)["committed_entity_and_dependence_analysis"]


def test_all_source_rows_as_independent_fails_without_erasing_identity_table(
    tmp_path: Path,
) -> None:
    submission, workspace = build_reference(ROOT, tmp_path / "source", aggregation="NONE")
    final = copy.deepcopy(submission["final_submission"])
    for row in final["calculations"]:
        if row["role"] == "PRIMARY":
            row["estimator"] = "ROW_EMPIRICAL"
    _sync_output(workspace, final)
    replace_final(submission, workspace, final)
    result = grade(submission, workspace)
    status = _statuses(result)
    assert status["committed_entity_and_dependence_analysis"]
    assert not status["discrimination_and_uncertainty"]
    assert not status["probability_and_calibration"]


def test_x17_purchase_without_crosswalk_recomputation_fails_locally(
    tmp_path: Path,
) -> None:
    submission, workspace = build_reference(ROOT, tmp_path / "source", resource="X17")
    final = copy.deepcopy(submission["final_submission"])
    final["artifact_manifest"] = [
        row for row in final["artifact_manifest"] if row["artifact_id"] != "TABLE_RESOURCE"
    ]
    final["calculations"] = [
        row for row in final["calculations"] if row["calculation_id"] != "C_RESOURCE"
    ]
    final["resource_assessment"]["calculation_ids"] = []
    _sync_output(workspace, final)
    submission["final_submission"] = final
    result = evaluate_case2_submission(workspace, submission, require_host_process=False).to_dict()
    assert not _statuses(result)["decision_relevant_followup"]
    assert (
        "purchased_evidence_not_used_in_valid_calculation"
        in result["diagnostics"]["resource"]["faults"]
    )


def test_x17_mapping_change_alters_saved_patient_level_analysis(tmp_path: Path) -> None:
    submission, workspace = build_reference(ROOT, tmp_path / "source", resource="X17")
    result = grade(submission, workspace)
    resource = result["diagnostics"]["resource"]
    primary_count = next(
        row["cohort"]["included_row_count"]
        for row in submission["final_submission"]["calculations"]
        if row["calculation_id"] == "C_DISCRIMINATION"
    )
    patient_count = next(
        row["reported_value"]
        for row in submission["final_submission"]["calculations"]
        if row["calculation_id"] == "C_RESOURCE"
    )
    assert resource["expected_results"]["membership_changed"] is True
    assert patient_count != primary_count
    assert _statuses(result)["decision_relevant_followup"]


def test_altered_x17_mapping_defeats_copied_results(tmp_path: Path) -> None:
    submission, workspace = build_reference(ROOT, tmp_path / "source", resource="X17")
    crosswalk = workspace / "purchased/X17/canonical_person_crosswalk.csv"
    rows = list(csv.DictReader(crosswalk.open(encoding="utf-8", newline="")))
    rows[0]["canonical_person_id"] = "SYNTHETIC_PERSON"
    with crosswalk.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    result = evaluate_case2_submission(workspace, submission, require_host_process=False).to_dict()
    assert not _statuses(result)["decision_relevant_followup"]
    assert not result["diagnostics"]["resource"]["returned_result_correct"]


@pytest.mark.parametrize(
    "decision_override",
    [
        ("PAUSE", "HOLD_CURRENT_CLAIM"),
        ("INSUFFICIENT_EVIDENCE", "HOLD_CURRENT_CLAIM"),
        ("CONTINUE", "TARGETED_CONTEXT_INVESTIGATION"),
        ("STOP", "END_DEVELOPMENT_PATH"),
    ],
)
def test_evidence_supported_dispositions_are_not_whitelisted(
    tmp_path: Path, decision_override: tuple[str, str]
) -> None:
    submission, workspace = build_reference(
        ROOT, tmp_path / decision_override[0], decision_override=decision_override
    )
    assert grade(submission, workspace)["complete_mission_success"]


def test_unconditional_general_advancement_fails_on_context_failure(
    tmp_path: Path,
) -> None:
    submission, workspace = build_reference(ROOT, tmp_path / "source")
    final = copy.deepcopy(submission["final_submission"])
    final["decision"].update(
        {
            "development_stage": "EXTERNAL_VALIDATION",
            "disposition": "CONTINUE",
            "use_scope": "RESEARCH_PROBABILITY",
            "action_scope": "GENERAL_MULTISITE_ADVANCEMENT",
            "current_context_status": "FAILED",
            "multisite_probability_use_permitted": True,
        }
    )
    replace_final(submission, workspace, final)
    result = grade(submission, workspace)
    assert not _statuses(result)["bounded_decision_and_claims"]


def test_strong_context_variant_defeats_universal_pause_policy(tmp_path: Path) -> None:
    submission, workspace = build_strong_context_variant(ROOT, tmp_path / "strong")
    result = evaluate_case2_submission(workspace, submission, require_host_process=False).to_dict()
    assert result["complete_mission_success"]
    paused = copy.deepcopy(submission)
    paused["final_submission"]["decision"] = {
        **paused["final_submission"]["decision"],
        "development_stage": "INTERNAL_VALIDATION",
        "disposition": "PAUSE",
        "use_scope": "NO_USE",
        "action_scope": "HOLD_CURRENT_CLAIM",
        "multisite_probability_use_permitted": False,
    }
    failed = evaluate_case2_submission(workspace, paused, require_host_process=False).to_dict()
    assert not _statuses(failed)["bounded_decision_and_claims"]


@pytest.mark.parametrize(
    ("disposition", "scope"),
    [("PAUSE", "HOLD_CURRENT_CLAIM"), ("STOP", "END_DEVELOPMENT_PATH")],
)
def test_fully_precommitted_generic_hold_or_stop_fails_strong_evidence(
    tmp_path: Path, disposition: str, scope: str
) -> None:
    submission, workspace = build_strong_context_variant(ROOT, tmp_path / disposition.lower())
    decision = copy.deepcopy(submission["final_submission"]["decision"])
    decision.update(
        {
            "development_stage": "STOPPED" if disposition == "STOP" else "INTERNAL_VALIDATION",
            "disposition": disposition,
            "use_scope": "NO_USE",
            "action_scope": scope,
            "multisite_probability_use_permitted": False,
        }
    )
    selected_id = submission["final_submission"]["belief_updates"][0]["matched_contingency_id"]
    selected = next(
        row
        for row in submission["followup_plan"]["result_contingencies"]
        if row["contingency_id"] == selected_id
    )
    selected["next_decision"] = copy.deepcopy(decision)
    submission["final_submission"]["decision"] = copy.deepcopy(decision)
    if disposition == "STOP":
        submission["final_submission"]["findings"][0]["decision_effect"] = "INVALIDATES"
    result = evaluate_case2_submission(workspace, submission, require_host_process=False).to_dict()
    assert not result["complete_mission_success"]
    assert not _statuses(result)["bounded_decision_and_claims"]


def test_x31_materiality_threshold_is_enforced(tmp_path: Path) -> None:
    submission, workspace = build_reference(ROOT, tmp_path / "x31", resource="X31")
    result = grade(submission, workspace)
    assert not result["complete_mission_success"]
    assert (
        "purchased_resource_not_decision_resolving" in result["diagnostics"]["resource"]["faults"]
    )


def test_x31_materiality_uses_only_disclosed_auc_delta(tmp_path: Path) -> None:
    submission, workspace = build_reference(ROOT, tmp_path / "x31", resource="X31")
    followup = submission["followup_plan"]
    followup["materiality_threshold"] = 0.05
    material, effect = _resource_effect(
        workspace,
        submission["validation_plan"],
        followup,
        {},
        {"roc_auc": 0.70, "brier_score": 0.01},
        {"ROC_AUC": 0.70, "BRIER_SCORE": 0.50},
    )
    assert not material
    assert effect == "INEFFECTIVE"


def test_followup_calculation_must_use_the_chosen_purchased_evidence(tmp_path: Path) -> None:
    submission, workspace = build_reference(ROOT, tmp_path / "x46", resource="X46")
    final = copy.deepcopy(submission["final_submission"])
    primary = next(
        row for row in final["calculations"] if row["calculation_id"] == "C_DISCRIMINATION"
    )
    disguised = copy.deepcopy(primary)
    disguised["calculation_id"] = "C_RESOURCE"
    disguised["role"] = "FOLLOWUP"
    final["calculations"] = [
        disguised if row["calculation_id"] == "C_RESOURCE" else row for row in final["calculations"]
    ]
    _sync_output(workspace, final)
    replace_final(submission, workspace, final)
    result = grade(submission, workspace)
    resource = result["diagnostics"]["resource"]
    assert not _statuses(result)["decision_relevant_followup"]
    assert not resource["resource_calculations_valid"]
    assert "purchased_evidence_not_used_in_valid_calculation" in resource["faults"]


def test_x58_harm_remains_material_even_above_estimate_delta(tmp_path: Path) -> None:
    submission, workspace = build_reference(ROOT, tmp_path / "x58", resource="X58")
    submission["followup_plan"]["materiality_threshold"] = 0.99
    result = evaluate_case2_submission(workspace, submission, require_host_process=False).to_dict()
    assert _statuses(result)["decision_relevant_followup"]
    assert result["diagnostics"]["resource"]["expected_effect"] == "EXPOSES_BLOCKER"


def test_silent_site_audit_omission_fails_only_context_chain(tmp_path: Path) -> None:
    submission, workspace = build_reference(ROOT, tmp_path / "source")
    output = json.loads((workspace / "work/primary_results.json").read_text())
    context = next(
        row
        for row in output["typed_calculations"]
        if row["calculation_id"] == "C_CONTEXT_ROBUSTNESS"
    )
    context["site_audit"]["sites"].pop("Coast")
    (workspace / "work/primary_results.json").write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n"
    )
    result = evaluate_case2_submission(workspace, submission, require_host_process=False).to_dict()
    status = _statuses(result)
    assert not status["context_robustness"]
    assert status["probability_and_calibration"]
    assert status["threshold_utility"]


def test_optional_malformed_diagnostic_does_not_fail_mission(tmp_path: Path) -> None:
    submission, workspace = build_reference(ROOT, tmp_path / "source")
    final = copy.deepcopy(submission["final_submission"])
    final["artifact_manifest"].append(
        {
            "artifact_id": "OPTIONAL_DIAGNOSTIC",
            "path": "work/does-not-exist.json",
            "role": "OTHER",
            "source_paths": [],
        }
    )
    submission["final_submission"] = final
    result = evaluate_case2_submission(workspace, submission, require_host_process=False).to_dict()
    assert result["complete_mission_success"]


def test_expert_memo_cannot_be_declared_empirically_material(tmp_path: Path) -> None:
    submission, workspace = build_reference(ROOT, tmp_path / "source", resource="X63")
    final = copy.deepcopy(submission["final_submission"])
    final["resource_assessment"]["material"] = True
    final["resource_assessment"]["observed_effect"] = "REDUCES_UNCERTAINTY"
    submission["final_submission"] = final
    result = evaluate_case2_submission(workspace, submission, require_host_process=False).to_dict()
    assert not _statuses(result)["decision_relevant_followup"]


def test_any_ineffective_purchase_fails_decision_relevant_followup(tmp_path: Path) -> None:
    submission, workspace = build_reference(ROOT, tmp_path / "source", resource="X24")
    ledger_path = workspace / "data/endpoint_source_ledger.csv"
    with ledger_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row["review_status"] = "concordant"
    with ledger_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    result = evaluate_case2_submission(workspace, submission, require_host_process=False).to_dict()
    resource = result["diagnostics"]["resource"]
    assert resource["expected_effect"] == "INEFFECTIVE"
    assert "purchased_resource_not_decision_resolving" in resource["faults"]
    assert not _statuses(result)["decision_relevant_followup"]


def test_environment_enforces_one_resource_action(tmp_path: Path) -> None:
    workspace = tmp_path / "fresh"
    environment = Case2PilotRC1Environment(ROOT, workspace)
    plan, _ = _candidate_plan(workspace, "MEAN", "SITE_WEIGHTED_ROC_AUC")
    assert environment.commit_validation_plan(json.dumps(plan))["accepted"]
    environment.reveal_validation()
    followup = _followup(
        "X17",
        all_passed=False,
        context_status="FAILED",
        decision_override=None,
    )
    assert environment.commit_followup_plan(json.dumps(followup))["accepted"]
    environment.purchase_resource("X17")
    with pytest.raises(OpenProtocolError):
        environment.purchase_resource("X46")


def test_public_and_hidden_use_byte_identical_semantic_source(tmp_path: Path) -> None:
    submission, workspace = build_reference(ROOT, tmp_path / "source")
    for name in ("validation_plan", "followup_plan", "final_submission"):
        (workspace / "work" / f"{name}.json").write_text(json.dumps(submission[name]))
    for filename in PUBLIC_SUPPORT_MODULES:
        assert (workspace / "public_support/uc_bench" / filename).read_bytes() == (
            ROOT / "src/uc_bench" / filename
        ).read_bytes()
    completed = subprocess.run(
        [str(ROOT / ".venv.nosync/bin/python"), str(workspace / "validate_science.py")],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    public = json.loads(completed.stdout)
    hidden = evaluate_case2_submission(workspace, submission).to_dict()
    assert completed.returncode == 0
    assert public["partial_scientific_quality"] == hidden["partial_scientific_quality"]
    assert public["mission_failures"] == list(hidden["mission_failures"])


def test_malformed_agent_payloads_are_total(tmp_path: Path) -> None:
    submission, workspace = build_reference(ROOT, tmp_path / "source")
    for malformed in (None, [], {"validation_plan": {"hypotheses": [None]}}):
        result = evaluate_case2_submission(workspace, malformed).to_dict()
        assert result["failure_class"] == "contract_failure"


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("validation_plan", "decision_criteria", 0, "property"), []),
        (("validation_plan", "decision_criteria", 0, "metric"), {}),
        (("validation_plan", "prospective_specification", "identity_basis"), []),
        (("final_submission", "decision", "action_scope"), []),
    ],
)
def test_nested_malformed_values_return_contract_failure(
    tmp_path: Path, path: tuple, value: object
) -> None:
    submission, workspace = build_reference(ROOT, tmp_path / "source")
    current: object = submission
    for key in path[:-1]:
        current = current[key]  # type: ignore[index]
    current[path[-1]] = value  # type: ignore[index]
    result = evaluate_case2_submission(workspace, submission).to_dict()
    assert result["failure_class"] == "contract_failure"


@pytest.mark.parametrize("state", [[], "x"])
def test_malformed_state_is_total_and_has_zero_reliability(tmp_path: Path, state: object) -> None:
    submission, workspace = build_reference(ROOT, tmp_path / "source")
    submission["state"] = state
    result = evaluate_case2_submission(workspace, submission).to_dict()
    assert result["reliability_score"] == 0.0
    assert not result["complete_mission_success"]
    assert result["failure_class"] == "scientific_failure"


def test_malformed_event_is_process_local(tmp_path: Path) -> None:
    submission, workspace = build_reference(ROOT, tmp_path / "source")
    submission["event_log"].append(None)
    result = evaluate_case2_submission(workspace, submission).to_dict()
    status = _statuses(result)
    assert not status["prospective_design_and_integrity"]
    assert all(
        passed for name, passed in status.items() if name != "prospective_design_and_integrity"
    )


def test_saved_output_failure_reports_causal_downstream_properties(tmp_path: Path) -> None:
    submission, workspace = build_reference(ROOT, tmp_path / "source")
    (workspace / "work/primary_results.json").unlink()
    result = evaluate_case2_submission(workspace, submission, require_host_process=False).to_dict()
    first = result["first_decision_critical_failure"]
    assert first["requirement_id"] == "saved_artifact_chain"
    assert {
        "discrimination_and_uncertainty",
        "probability_and_calibration",
        "threshold_utility",
        "context_robustness",
        "bounded_decision_and_claims",
    } <= set(first["downstream_dependencies"])


def test_historical_rc16_submission_shapes_never_crash() -> None:
    accepted = [
        path
        for path in sorted(RC16_RUNS.glob("open-mmmvp-rc16-sentinel-*/submission.json"))
        if any(
            slug in path.as_posix()
            for slug in ("sonnet", "openai-gpt-5-", "opus", "gemini", "mistral")
        )
    ]
    assert len(accepted) == 5
    for path in accepted:
        payload = json.loads(path.read_text())
        workspace = path.parent / "workspace"
        result = evaluate_case2_submission(workspace, payload).to_dict()
        assert result["failure_class"] in {"contract_failure", "scientific_failure", "none"}
    for slug in ("qwen", "deepseek"):
        ledger = next(RC16_RUNS.glob(f"open-mmmvp-rc16-sentinel-*{slug}*/request_ledger.json"))
        payload = json.loads(ledger.read_text())
        assert isinstance(payload, (dict, list))
        assert hashlib.sha256(ledger.read_bytes()).hexdigest()


def test_historical_rc16_regression_fixtures_are_immutable() -> None:
    assert {
        relative: hashlib.sha256((RC16_RUNS / relative).read_bytes()).hexdigest()
        for relative in HISTORICAL_FIXTURE_HASHES
    } == HISTORICAL_FIXTURE_HASHES


def test_historical_rc16_fixtures_preserve_scientific_and_causal_shapes() -> None:
    expected = {
        "anthropic/claude-sonnet-4": ("X46", "CONTINUE", "prospective_plan_implemented"),
        "openai/gpt-5": ("X63", "PAUSE", "saved_artifact_chain"),
        "anthropic/claude-opus-4.1": ("X46", "PAUSE", "prospective_plan_implemented"),
        "google/gemini-3.1-pro-preview": (
            "none",
            "CONTINUE",
            "prospective_plan_implemented",
        ),
        "mistralai/mistral-large-2512": (
            "X17",
            "PAUSE",
            "prospective_plan_implemented",
        ),
    }
    observed: dict[str, tuple[str, str, str]] = {}
    for summary_path in sorted(RC16_RUNS.glob("open-mmmvp-rc16-sentinel-*/run_summary.json")):
        summary = json.loads(summary_path.read_text())
        model = summary.get("model_id")
        if model not in expected:
            continue
        submission = summary["submission"]
        grade_value = summary["diagnostic_grade"]
        properties = {row["requirement_id"]: row["passed"] for row in grade_value["requirements"]}
        assert "saved_artifact_chain" in properties
        assert "relevant_entity_reconstruction" in properties
        assert isinstance(submission["final_submission"]["belief_updates"], list)
        assert isinstance(submission["final_submission"]["claims"], list)
        first = grade_value["first_decision_critical_failure"]
        assert isinstance(first, dict)
        assert grade_value["mission_failures"]
        assert first["requirement_id"] == grade_value["mission_failures"][0]
        observed[model] = (
            submission["followup_plan"]["chosen_resource"],
            submission["final_submission"]["decision"]["disposition"],
            first["requirement_id"],
        )
    assert observed == expected


def test_candidate_source_contains_no_planted_identity_constants() -> None:
    source = "\n".join(
        (ROOT / "src/uc_bench" / filename).read_text()
        for filename in (
            "case2_pilot_v1_rc1_contract.py",
            "case2_pilot_v1_rc1_environment.py",
            "case2_pilot_v1_rc1_semantics.py",
        )
    )
    assert "F0017" not in source
    assert "F0018" not in source
    assert 'canonical_person_count": 95' not in source
    assert 'provisional_unit_count": 96' not in source


def test_candidate_has_no_private_disposition_whitelist() -> None:
    contract = json.dumps(PUBLIC_CONTRACT, sort_keys=True)
    assert DEVELOPMENT_ACTION_CONTRACT["no_preferred_disposition"] is True
    assert "expected_disposition" not in contract

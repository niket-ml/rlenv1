from __future__ import annotations

import copy
import csv
import hashlib
import inspect
import json
import shutil
from pathlib import Path

import pytest

from uc_bench.mmmvp_blind_interface import (
    NEUTRAL_MISSION,
    OpenExecutionLimits,
    mmmvp_blind_scientific_system_prompt,
)
from uc_bench.mmmvp_open_audit import (
    run_open_endedness_audit,
    sentence_level_hint_audit,
    serialized_agent_request,
)
from uc_bench.mmmvp_open_controls import _plan, build_open_reference
from uc_bench.mmmvp_open_environment import OpenMMMVPEnvironment, OpenProtocolError
from uc_bench.mmmvp_open_verifier import verify_open_submission

ROOT = Path(__file__).resolve().parents[1]


def _public_digest(root: Path) -> str:
    rows: list[tuple[str, str]] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if path.is_file():
            rows.append((relative.as_posix(), hashlib.sha256(path.read_bytes()).hexdigest()))
    return hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()


def _rewrite_host_records(submission: dict[str, object], workspace: Path) -> None:
    records = workspace.parent / ".mmmvp_host_records" / workspace.name
    submission["host_record_locator"] = records.resolve().as_posix()
    for key, filename in (
        ("validation_plan", "validation_plan.json"),
        ("followup_plan", "followup_plan.json"),
        ("final_submission", "final_submission.json"),
    ):
        (records / filename).write_text(
            json.dumps(submission[key], indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    digests = {
        key: hashlib.sha256(
            json.dumps(submission[key], sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        for key in ("validation_plan", "followup_plan", "final_submission")
    }
    state = submission["state"]
    assert isinstance(state, dict)
    state["validation_plan_hash"] = digests["validation_plan"]
    state["followup_plan_hash"] = digests["followup_plan"]
    state["final_submission_hash"] = digests["final_submission"]
    events = submission["event_log"]
    assert isinstance(events, list)
    for event in events:
        if event["event"] == "commit_validation_plan":
            event["digest"] = digests["validation_plan"]
        elif event["event"] == "reveal_validation":
            event["committed_plan_hash"] = digests["validation_plan"]
        elif event["event"] == "commit_followup_plan":
            event["digest"] = digests["followup_plan"]
        elif event["event"] == "submit":
            event["validation_plan_hash"] = digests["validation_plan"]
            event["followup_plan_hash"] = digests["followup_plan"]
            event["final_submission_hash"] = digests["final_submission"]


def test_prompt_builder_cannot_receive_private_condition_identifier() -> None:
    parameters = inspect.signature(mmmvp_blind_scientific_system_prompt).parameters
    assert set(parameters) == {"limits"}
    assert set(inspect.signature(OpenExecutionLimits).parameters) == {
        "maximum_turns",
        "maximum_total_completion_tokens",
        "wall_clock_timeout_seconds",
    }


def test_prompt_starts_with_exact_neutral_mission() -> None:
    prompt = mmmvp_blind_scientific_system_prompt()
    assert prompt.startswith(NEUTRAL_MISSION + "\n\n")


def test_prompt_contains_no_answer_bearing_condition_language() -> None:
    rows = sentence_level_hint_audit()
    assert rows
    assert all(row["passed"] for row in rows)
    assert {row["category"] for row in rows} == {
        "objective",
        "interface_and_security",
        "submission_contract",
        "execution_budget",
    }


def test_prompt_discloses_only_mechanics_and_generic_contract() -> None:
    prompt = mmmvp_blind_scientific_system_prompt()
    normalized = " ".join(prompt.split())
    for required in (
        "commit_validation_plan",
        "reveal_validation",
        "commit_followup_plan",
        "purchase_resource",
        "submission_contract.json",
        "Alternative valid workflows are accepted",
        "Free text is checked only for presence",
    ):
        assert required in normalized
    for forbidden in (
        "patient-level AUC",
        "Brier score",
        "calibration error",
        "net benefit",
        "preprocessing leakage",
        "site confounding",
        "signal remains",
        "signal collapses",
        "choose X31",
    ):
        assert forbidden.lower() not in prompt.lower()


def test_machine_contract_is_public_generic_and_case_neutral(tmp_path: Path) -> None:
    digests: set[str] = set()
    for index, (case_id, mechanism) in enumerate(
        (
            ("case_01", "default"),
            ("case_02", "default"),
            ("case_03", "signal_collapses"),
            ("case_03", "signal_remains"),
            ("case_04", "default"),
        )
    ):
        environment = OpenMMMVPEnvironment(
            ROOT,
            case_id,
            tmp_path / f"condition-{index}",
            mechanism=mechanism,
        )
        contract = environment.run_root / "submission_contract.json"
        digests.add(hashlib.sha256(contract.read_bytes()).hexdigest())
        encoded = contract.read_text(encoding="utf-8").lower()
        assert case_id not in encoded
        assert "signal_collapses" not in encoded
        assert "signal_remains" not in encoded
        assert "choose x31" not in encoded
        assert "signal must" not in encoded
        assert "correct decision" not in encoded
    assert len(digests) == 1


def test_serialized_request_is_condition_free() -> None:
    request = serialized_agent_request()
    encoded = json.dumps(request, sort_keys=True).lower()
    assert "case_01" not in encoded
    assert "case_02" not in encoded
    assert "case_03" not in encoded
    assert "case_04" not in encoded
    assert "signal_collapses" not in encoded
    assert "signal_remains" not in encoded
    assert "grader_private" not in encoded


def test_case_three_hidden_variants_have_identical_public_start_state(tmp_path: Path) -> None:
    collapse = OpenMMMVPEnvironment(
        ROOT,
        "case_03",
        tmp_path / "collapse",
        mechanism="signal_collapses",
    )
    remains = OpenMMMVPEnvironment(
        ROOT,
        "case_03",
        tmp_path / "remains",
        mechanism="signal_remains",
    )
    assert _public_digest(collapse.run_root) == _public_digest(remains.run_root)


def test_full_open_endedness_audit_passes_without_api_calls(tmp_path: Path) -> None:
    result = run_open_endedness_audit(ROOT, tmp_path / "audit")
    assert result["api_requests"] == 0
    assert result["status"] == "passed"
    assert result["red_team_review"]["status"] == "passed"
    assert not result["red_team_review"]["unresolved_blocking_or_major_findings"]
    findings = {row["finding_id"]: row for row in result["red_team_review"]["findings"]}
    for finding_id in ("RT-B01", "RT-B02", "RT-M01", "RT-M02", "RT-M03", "RT-M04"):
        assert findings[finding_id]["status"] == "fixed_with_evidence"
    assert findings["RT-M14"]["status"] == "accepted_limitation"
    assert result["case3_pre_reveal_variants_byte_identical"]
    assert result["case_neutral_descriptions_uniform"]
    assert result["controls"]["reference_and_two_workflows_pass"]
    assert result["controls"]["negative_controls_rejected"]
    assert result["controls"]["universal_policy_fails"]
    assert result["controls"]["partial_credit_preserved"]


def test_professional_prose_paraphrase_cannot_change_scientific_score(tmp_path: Path) -> None:
    submission, workspace = build_open_reference(
        ROOT,
        "case_02",
        tmp_path / "original",
        alternative=False,
    )
    paraphrased_workspace = tmp_path / "paraphrased"
    shutil.copytree(workspace, paraphrased_workspace)
    source_records = workspace.parent / ".mmmvp_host_records" / workspace.name
    target_records = (
        paraphrased_workspace.parent / ".mmmvp_host_records" / paraphrased_workspace.name
    )
    shutil.copytree(source_records, target_records)
    paraphrased = json.loads(json.dumps(submission))
    for key in ("decision_definition", "evidence_standard"):
        paraphrased["validation_plan"][key] = "A different reasonable professional formulation."
    for hypothesis in paraphrased["validation_plan"]["hypotheses"]:
        hypothesis["statement"] = "A neutrally worded live possibility."
    for analysis in paraphrased["validation_plan"]["planned_analyses"]:
        for key in ("question", "method", "analysis_unit", "decision_relevance"):
            analysis[key] = "A defensible paraphrase that does not use verifier vocabulary."
    followup = paraphrased["followup_plan"]
    followup["decision_question"] = "What evidence most efficiently changes the current action?"
    for explanation in followup["live_explanations"]:
        explanation["statement"] = "A live account of the observed evidence."
        explanation["distinguishing_evidence"] = "A result that separates the accounts."
    for alternative in followup["alternatives_considered"]:
        alternative["limitations"] = "Useful within its stated evidentiary scope only."
    for contingency in followup["result_contingencies"]:
        contingency["observable_result"] = "One predeclared observable pattern."
        contingency["next_action"] = "Take the bounded action supported by that pattern."
    final = paraphrased["final_submission"]
    for finding in final["findings"]:
        finding["statement"] = "The evidence supports this bounded finding."
    for assessment in final["evidence_assessments"]:
        assessment["rationale"] = "This eligibility state follows from the saved records."
    for claim in final["claims"]:
        claim["statement"] = "The machine-readable scope and status are authoritative."
    decision = final["decision"]
    for key in ("allowed_use", "prohibited_use", "unresolved_gates", "required_next_evidence"):
        decision[key] = ["A professionally reasonable paraphrase."]
    final["remaining_uncertainties"] = ["A remaining uncertainty stated in other words."]
    _rewrite_host_records(paraphrased, paraphrased_workspace)
    grade = verify_open_submission(
        ROOT,
        paraphrased_workspace,
        paraphrased,
        condition_id="case_02",
    )
    assert grade.complete_mission_success
    assert grade.partial_scientific_quality == 100


def test_optional_sensitivity_value_cannot_invalidate_correct_primary_work(tmp_path: Path) -> None:
    submission, workspace = build_open_reference(
        ROOT,
        "case_04",
        tmp_path / "case4",
        alternative=False,
    )
    optional = copy.deepcopy(submission["final_submission"]["calculations"][0])
    optional["calculation_id"] = "OPTIONAL_SENSITIVITY_AUC"
    optional["role"] = "SENSITIVITY"
    optional["reported_value"] = -999.0
    optional.pop("uncertainty", None)
    submission["final_submission"]["calculations"].append(optional)
    output = workspace / "work/results.json"
    output_payload = json.loads(output.read_text(encoding="utf-8"))
    output_payload["typed_calculations"].append(
        {
            "calculation_id": optional["calculation_id"],
            "reported_value": optional["reported_value"],
        }
    )
    output.write_text(json.dumps(output_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _rewrite_host_records(submission, workspace)
    grade = verify_open_submission(ROOT, workspace, submission, condition_id="case_04")
    assert grade.complete_mission_success


def test_revealed_and_purchased_evidence_are_immutable(tmp_path: Path) -> None:
    submission, workspace = build_open_reference(
        ROOT,
        "case_03_signal_collapses",
        tmp_path / "case3",
        alternative=False,
    )
    revealed = workspace / "revealed/validation_outcomes.csv"
    revealed.write_text(revealed.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    grade = verify_open_submission(
        ROOT,
        workspace,
        submission,
        condition_id="case_03_signal_collapses",
    )
    integrity = next(
        row for row in grade.requirements if row.requirement_id == "irreversible_action_integrity"
    )
    assert not integrity.passed
    assert not grade.complete_mission_success


def test_precommit_rejects_a_future_work_input(tmp_path: Path) -> None:
    environment = OpenMMMVPEnvironment(ROOT, "case_01", tmp_path / "workspace")
    plan = _plan("mean")
    plan["planned_analyses"][0]["input_paths"] = ["work/future_input.csv"]
    result = environment.commit_validation_plan(json.dumps(plan))
    assert not result["accepted"]
    assert result["schema_issues"][0]["code"] == "pre_reveal_file_required"


def test_reveal_mutation_stops_the_next_irreversible_action(tmp_path: Path) -> None:
    environment = OpenMMMVPEnvironment(
        ROOT,
        "case_03",
        tmp_path / "workspace",
        mechanism="signal_collapses",
    )
    assert environment.commit_validation_plan(json.dumps(_plan("mean")))["accepted"]
    environment.reveal_validation()
    revealed = environment.run_root / "revealed/validation_outcomes.csv"
    revealed.write_text(revealed.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(OpenProtocolError, match="Supplied evidence was modified"):
        environment.commit_followup_plan("{}")


def test_machine_decision_and_evidence_controls_reject_false_passes(tmp_path: Path) -> None:
    stage_submission, stage_workspace = build_open_reference(
        ROOT,
        "case_01",
        tmp_path / "stage",
        alternative=False,
    )
    stage_submission = copy.deepcopy(stage_submission)
    stage_submission["final_submission"]["decision"]["development_stage"] = "PROSPECTIVE_EVALUATION"
    observed = next(
        row
        for row in stage_submission["followup_plan"]["result_contingencies"]
        if row["contingency_id"] == "C_OBSERVED"
    )
    observed["next_decision"]["development_stage"] = "PROSPECTIVE_EVALUATION"
    _rewrite_host_records(stage_submission, stage_workspace)
    assert not verify_open_submission(
        ROOT,
        stage_workspace,
        stage_submission,
        condition_id="case_01",
    ).complete_mission_success

    belief_submission, belief_workspace = build_open_reference(
        ROOT,
        "case_03_signal_collapses",
        tmp_path / "belief",
        alternative=False,
    )
    belief_submission = copy.deepcopy(belief_submission)
    observed = next(
        row
        for row in belief_submission["followup_plan"]["result_contingencies"]
        if row["contingency_id"] == "C_OBSERVED"
    )
    observed["hypothesis_updates"] = [
        {"hypothesis_id": "H1", "direction": "INCREASE"},
        {"hypothesis_id": "H2", "direction": "DECREASE"},
    ]
    belief_submission["final_submission"]["belief_updates"][0]["after"] = 0.7
    belief_submission["final_submission"]["belief_updates"][1]["after"] = 0.3
    _rewrite_host_records(belief_submission, belief_workspace)
    assert not verify_open_submission(
        ROOT,
        belief_workspace,
        belief_submission,
        condition_id="case_03_signal_collapses",
    ).complete_mission_success

    resource_submission, resource_workspace = build_open_reference(
        ROOT,
        "case_02",
        tmp_path / "resource",
        alternative=False,
        forced_resource=("X46", "EXTERNAL_COHORT"),
    )
    resource_submission = copy.deepcopy(resource_submission)
    resource_submission["followup_plan"]["current_decision"].update(
        {
            "development_stage": "EXTERNAL_VALIDATION",
            "disposition": "CONTINUE",
            "use_scope": "RESEARCH_PROBABILITY",
        }
    )
    _rewrite_host_records(resource_submission, resource_workspace)
    assert not verify_open_submission(
        ROOT,
        resource_workspace,
        resource_submission,
        condition_id="case_02",
    ).complete_mission_success


def test_context_and_contamination_cannot_be_laundered(tmp_path: Path) -> None:
    context_submission, context_workspace = build_open_reference(
        ROOT,
        "case_02",
        tmp_path / "context",
        alternative=False,
    )
    table = context_workspace / "work/analysis_table.csv"
    with table.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row["setting"] = ""
    with table.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    assert not verify_open_submission(
        ROOT,
        context_workspace,
        context_submission,
        condition_id="case_02",
    ).complete_mission_success

    contaminated, contaminated_workspace = build_open_reference(
        ROOT,
        "case_03_signal_collapses",
        tmp_path / "contaminated",
        alternative=False,
    )
    contaminated = copy.deepcopy(contaminated)
    contaminated["final_submission"]["evidence_assessments"].append(
        {
            "evidence_id": "EV_CONTRADICTION",
            "source_paths": ["pipeline/fit_membership.csv"],
            "eligible_for_decision": True,
            "rationale": "Contradictory eligibility state.",
        }
    )
    _rewrite_host_records(contaminated, contaminated_workspace)
    assert not verify_open_submission(
        ROOT,
        contaminated_workspace,
        contaminated,
        condition_id="case_03_signal_collapses",
    ).complete_mission_success


def test_candidate_panel_obeys_strict_model_age_boundaries() -> None:
    panel = json.loads(
        (ROOT / "configs/uc_bench_mmmvp_open_model_panel.json").read_text(encoding="utf-8")
    )
    models = [row["model_id"] for row in panel["models"]]
    assert "openai/gpt-5.1" in models
    assert "openai/gpt-5" in models
    assert "anthropic/claude-opus-4.1" in models
    assert "anthropic/claude-sonnet-4" in models
    assert all(
        model not in models
        for model in (
            "openai/gpt-5.2",
            "openai/gpt-5.4",
            "openai/gpt-5.6-sol",
            "openai/gpt-6-astra",
            "anthropic/claude-opus-4.5",
            "anthropic/claude-opus-4.8",
            "anthropic/claude-opus-5",
            "anthropic/claude-sonnet-4.5",
            "anthropic/claude-sonnet-4.6",
        )
    )

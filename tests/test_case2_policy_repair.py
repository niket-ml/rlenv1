"""Model-independent controls for the bounded Case-2 development policy repair."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from development.case2_repair import semantics
from development.case2_repair.belief import PUBLIC_BELIEF_RULE, belief_revision_errors
from development.case2_repair.contract import PUBLIC_CONTRACT, validate_precommit
from development.case2_repair.environment import Case2DevelopmentEnvironment
from uc_bench import case2_pilot_v1_rc1_controls as controls
from uc_bench.case2_pilot_v1_rc1_environment import Case2PilotRC1Environment
from uc_bench.mmmvp_open_environment import OpenProtocolError

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "artifacts/uc_bench_case2_pilot_v1_rc2/science/runs"


def scenario(direction="INCREASE", decision_effect="WEAKENS"):
    # Abstract hypotheses, no patient counts or observed model-specific answers.
    end = {"INCREASE": 0.7, "DECREASE": 0.2, "UNCHANGED": 0.5}[direction]
    return (
        {
            "hypotheses": [
                {
                    "hypothesis_id": "a",
                    "belief": 0.5,
                    "statement": "An unresolved premise.",
                    "decision_effect_if_true": decision_effect,
                },
                {
                    "hypothesis_id": "b",
                    "belief": 0.5,
                    "statement": "A separate premise.",
                    "decision_effect_if_true": "NONE",
                },
            ]
        },
        {
            "beliefs_before": {"a": 0.5, "b": 0.5},
            "result_contingencies": [
                {
                    "contingency_id": "observed",
                    "observable_result": "The specified evidence arrives.",
                    "hypothesis_updates": [
                        {"hypothesis_id": "a", "direction": direction},
                        {"hypothesis_id": "b", "direction": "UNCHANGED"},
                    ],
                },
            ],
        },
        {
            "belief_updates": [
                {
                    "hypothesis_id": "a",
                    "before": 0.5,
                    "after": end,
                    "matched_contingency_id": "observed",
                },
                {
                    "hypothesis_id": "b",
                    "before": 0.5,
                    "after": 0.5,
                    "matched_contingency_id": "observed",
                },
            ]
        },
    )


def errors(parts, effect="RESOLVES", *, verified=True):
    return belief_revision_errors(*parts, effect, evidence_verified=verified)


@pytest.mark.parametrize("decision_effect", ["SUPPORTS", "WEAKENS", "INVALIDATES", "NONE"])
@pytest.mark.parametrize("direction", ["INCREASE", "DECREASE"])
@pytest.mark.parametrize("effect", ["RESOLVES", "REDUCES_UNCERTAINTY", "EXPOSES_BLOCKER"])
def test_decision_consequence_does_not_prescribe_probability(direction, decision_effect, effect):
    assert errors(scenario(direction, decision_effect), effect) == []


def test_independent_hypotheses_can_both_gain_support():
    v, f, final = scenario()
    v["hypotheses"][0]["statement"] = "Record identity can be established from the crosswalk."
    v["hypotheses"][1]["statement"] = "A context-related weakness survives identity reconciliation."
    v["hypotheses"][0]["decision_effect_if_true"] = "SUPPORTS"
    v["hypotheses"][1]["decision_effect_if_true"] = "WEAKENS"
    f["result_contingencies"][0]["hypothesis_updates"][1]["direction"] = "INCREASE"
    final["belief_updates"][1]["after"] = 0.7
    assert errors((v, f, final)) == []


@pytest.mark.parametrize("effect", ["NO_NEW_EVIDENCE", "INEFFECTIVE"])
def test_no_evidence_cannot_justify_a_generic_update(effect):
    assert errors(scenario("UNCHANGED"), effect) == []
    assert errors(scenario("INCREASE"), effect)
    assert errors(scenario("DECREASE"), effect)


@pytest.mark.parametrize("bad", [True, "0.5", -0.1, 1.1, float("nan"), float("inf"), None, {}])
@pytest.mark.parametrize("field", ["before", "after"])
def test_invalid_probabilities_fail_without_crashing(field, bad):
    parts = scenario()
    parts[2]["belief_updates"][0][field] = bad
    assert errors(parts)


@pytest.mark.parametrize(
    "attack",
    [
        "wrong_before",
        "changed_direction",
        "omit_hypothesis",
        "duplicate_update",
        "duplicate_hypothesis",
        "duplicate_contingency",
        "duplicate_direction",
        "missing_direction",
        "invented_contingency",
        "two_selected_contingencies",
        "changed_followup_prior",
        "malformed_hypothesis",
        "malformed_contingency",
    ],
)
def test_commitment_integrity_cannot_be_self_repaired_after_evidence(attack):
    v, f, final = scenario()
    updates = final["belief_updates"]
    contingencies = f["result_contingencies"]
    if attack == "wrong_before":
        updates[0]["before"] = 0.3
    elif attack == "changed_direction":
        updates[0]["after"] = 0.2
    elif attack == "omit_hypothesis":
        updates.pop()
    elif attack == "duplicate_update":
        updates.append(copy.deepcopy(updates[0]))
    elif attack == "duplicate_hypothesis":
        v["hypotheses"].append(copy.deepcopy(v["hypotheses"][0]))
    elif attack == "duplicate_contingency":
        contingencies.append(copy.deepcopy(contingencies[0]))
    elif attack == "duplicate_direction":
        contingencies[0]["hypothesis_updates"].append(
            copy.deepcopy(contingencies[0]["hypothesis_updates"][0])
        )
    elif attack == "missing_direction":
        contingencies[0]["hypothesis_updates"].pop()
    elif attack == "invented_contingency":
        for row in updates:
            row["matched_contingency_id"] = "unknown"
    elif attack == "two_selected_contingencies":
        updates[0]["matched_contingency_id"] = "unknown"
    elif attack == "changed_followup_prior":
        f["beliefs_before"]["a"] = 0.3
    elif attack == "malformed_hypothesis":
        v["hypotheses"][0] = []
    elif attack == "malformed_contingency":
        contingencies[0]["hypothesis_updates"] = {"a": "INCREASE"}
    assert errors((v, f, final))


def test_absent_or_unverified_return_is_not_evidence():
    assert errors(scenario(), verified=False) == ["resource_effect_unverified"]
    assert errors(scenario(), None) == ["resource_effect_unverified"]


def test_public_disclosure_and_machine_checker_have_the_same_bounded_claim():
    rule = next(
        r["rule"]
        for r in PUBLIC_CONTRACT["relationships_and_conditionals"]
        if r["id"] == "belief_revision_against_contingency"
    )
    assert rule == PUBLIC_BELIEF_RULE
    encoded = json.dumps(PUBLIC_CONTRACT)
    assert "method_definitions.json" not in encoded
    assert "evidence_binding.json" not in encoded
    assert "opposite signs" not in encoded
    assert "measurement_limitation" in encoded
    # Deliberately do not pretend that consistency proves truth of free prose.
    parts = scenario()
    parts[0]["hypotheses"][0]["statement"] = "An arbitrary, unverified proposition."
    assert errors(parts) == []  # Known measurement boundary, explicitly disclosed.


def test_names_wording_and_order_do_not_create_scientific_credit():
    parts = scenario()
    original = errors(parts)
    v, f, final = parts
    mapping = {"a": "question_delta", "b": "other_hypothesis"}
    for row in v["hypotheses"]:
        row["hypothesis_id"] = mapping[row["hypothesis_id"]]
        row["statement"] = "A professionally phrased alternative description."
    f["beliefs_before"] = {mapping[key]: val for key, val in f["beliefs_before"].items()}
    for row in f["result_contingencies"][0]["hypothesis_updates"] + final["belief_updates"]:
        row["hypothesis_id"] = mapping[row["hypothesis_id"]]
    v["hypotheses"].reverse()
    final["belief_updates"].reverse()
    assert errors(parts) == original


def dev_reference(tmp_path, **kwargs):
    # Inject the exact development environment into the existing solver, without
    # modifying that archived source or deriving expected answers from a model.
    with patch.object(controls, "Case2PilotRC1Environment", Case2DevelopmentEnvironment):
        return controls.build_reference(ROOT, tmp_path / "episode", **kwargs)


@pytest.mark.parametrize("aggregation", ["MEAN", "MEDIAN", "FIRST", "NONE"])
def test_complete_development_action_chain_accepts_valid_workflows(tmp_path, aggregation):
    s, w = dev_reference(tmp_path, aggregation=aggregation)
    result = semantics.evaluate_case2_submission(w, s)
    assert result.complete_mission_success, result.to_dict()
    assert result.first_decision_critical_failure is None
    assert result.partial_scientific_quality >= 90
    assert result.reliability_score == 100
    assert json.loads((w / "submission_contract.json").read_text()) == PUBLIC_CONTRACT
    paths = []
    for kind in ["validation_plan", "followup_plan", "final_submission"]:
        path = w / f"work/arbitrary_{kind}_name.json"
        path.write_text(json.dumps(s[kind]))
        paths.append(str(path))
    science = subprocess.run(
        [sys.executable, "-I", str(w / "validate_science.py"), *paths],
        cwd=w,
        capture_output=True,
        text=True,
        check=False,
    )
    assert science.returncode == 0, science.stderr + science.stdout
    public = json.loads(science.stdout)
    assert public["diagnostics"]["property_points"] == result.diagnostics["property_points"]
    assert public["complete_mission_success"]
    assert "evidence_linked_commitment_consistency" in science.stdout
    assert not (w / "public_support/development/case2_repair/replay.py").exists()
    assert not (w / "public_support/development/case2_repair/independent.py").exists()
    canonical = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            "import sys; sys.dont_write_bytecode=True; sys.path.insert(0, sys.argv[1]); "
            "from uc_bench.case2_pilot_v1_rc1_semantics import evaluate_case2_submission as old; "
            "from development.case2_repair.semantics import evaluate_case2_submission as new; "
            "from uc_bench.case2_pilot_v1_rc1_contract import PUBLIC_CONTRACT as old_contract; "
            "from development.case2_repair.contract import PUBLIC_CONTRACT as new_contract; "
            "assert old is new and old_contract is new_contract",
            str(w / "public_support"),
        ],
        cwd=w,
        capture_output=True,
        text=True,
        check=False,
    )
    assert canonical.returncode == 0, canonical.stderr


@pytest.mark.parametrize("resource", ["none", "X17", "X24", "X31", "X46", "X58", "X63"])
def test_all_existing_resource_branches_keep_independent_requirements(tmp_path, resource):
    s, w = dev_reference(tmp_path, resource=resource)
    result = semantics.evaluate_case2_submission(w, s)
    # Based on the unchanged returned evidence: X31 is immaterial and X63 is
    # advice without new empirical evidence. These are not target-score choices.
    assert result.complete_mission_success is (resource not in {"X31", "X63"})
    assert result.diagnostics["property_points"]["threshold_utility"] == 8


def test_identity_resolution_does_not_unlock_general_advancement(tmp_path):
    s, w = dev_reference(tmp_path, resource="X17")
    grade = semantics.evaluate_case2_submission(w, s)
    assert grade.diagnostics["resource"]["expected_effect"] == "RESOLVES"
    assert s["final_submission"]["decision"]["current_context_status"] == "FAILED"
    decision = s["final_submission"]["decision"]
    decision.update(
        disposition="CONTINUE",
        action_scope="GENERAL_MULTISITE_ADVANCEMENT",
        multisite_probability_use_permitted=True,
    )
    changed = semantics.evaluate_case2_submission(w, s, require_host_process=False)
    assert not changed.complete_mission_success
    assert not next(
        r for r in changed.requirements if r.requirement_id == "bounded_decision_and_claims"
    ).passed
    assert changed.diagnostics["property_points"]["threshold_utility"] == 8


def test_invented_resource_return_cannot_buy_belief_credit(tmp_path):
    s, w = dev_reference(tmp_path, resource="X17")
    path = w / s["final_submission"]["resource_assessment"]["summary_artifact_path"]
    summary = json.loads(path.read_text())
    summary["results"]["adjudicated_person_count"] += 500
    path.write_text(json.dumps(summary))
    grade = semantics.evaluate_case2_submission(w, s, require_host_process=False)
    assert not grade.complete_mission_success
    assert grade.diagnostics["property_points"]["belief_revision"] == 0
    assert grade.diagnostics["property_points"]["threshold_utility"] == 8


def test_incomplete_manifest_is_recoverable_before_irreversible_commit(tmp_path):
    env = Case2DevelopmentEnvironment(ROOT, tmp_path / "dev")
    plan, _ = controls._candidate_plan(env.run_root, "MEAN", "SITE_WEIGHTED_ROC_AUC")
    path = env.run_root / plan["prospective_specification"]["eligible_entity_manifest_path"]
    good = path.read_bytes()
    path.write_text(json.dumps(["an_id_is_not_membership_evidence"]))
    plan["prospective_specification"]["eligible_entity_manifest_sha256"] = hashlib.sha256(
        path.read_bytes()
    ).hexdigest()
    assert not validate_precommit(env.run_root, plan).valid
    response = env.commit_validation_plan(json.dumps(plan))
    assert not response["accepted"]
    assert "complete CSV manifest" in json.dumps(response)
    assert env.state.phase == "investigate"
    assert not env.state.validation_plan_hash
    with pytest.raises(OpenProtocolError):
        env.reveal_validation()
    path.write_bytes(good)
    plan["prospective_specification"]["eligible_entity_manifest_sha256"] = hashlib.sha256(
        good
    ).hexdigest()
    assert validate_precommit(env.run_root, plan).valid
    assert env.commit_validation_plan(json.dumps(plan))["accepted"]
    env.reveal_validation()
    assert env.state.phase == "revealed"


def test_visible_evidence_and_inherited_actions_are_not_redesigned(tmp_path):
    original = Case2PilotRC1Environment(ROOT, tmp_path / "original")
    dev = Case2DevelopmentEnvironment(ROOT, tmp_path / "dev")
    for name in [
        "data",
        "MISSION.md",
        "tool_interface.json",
        "identity_provenance.json",
        "scientific_methods.json",
        "development_action_contract.json",
        "followup_catalog.json",
    ]:
        source = original.run_root / name
        if source.is_dir():
            paths = [p for p in source.rglob("*") if p.is_file()]
        else:
            assert source.is_file(), name
            paths = [source]
        for path in paths:
            relative = path.relative_to(original.run_root)
            assert path.read_bytes() == (dev.run_root / relative).read_bytes(), relative
    assert (
        Case2DevelopmentEnvironment.purchase_resource is Case2PilotRC1Environment.purchase_resource
    )
    assert (
        Case2DevelopmentEnvironment.reveal_validation is Case2PilotRC1Environment.reveal_validation
    )


def test_prior_replay_remains_immutable_and_historical_failure_survives():
    prior = ROOT / "development/case2_repair/replay_results.json"
    assert hashlib.sha256(prior.read_bytes()).hexdigest() == (
        "b8f8cf19011e9e0710d0735d400ae6b6bcc93603105ff60e96d37fddb9d0b930"
    )
    run = next(RUNS.glob("*sonnet*"))
    submission = json.loads((run / "submission.json").read_text())
    grade = semantics.evaluate_case2_submission(run / "workspace", submission)
    assert not grade.complete_mission_success
    assert (
        grade.first_decision_critical_failure["requirement_id"] == "discrimination_and_uncertainty"
    )
    assert not grade.diagnostics["calculations"]["calc_adjudicated_context"]["scientific_valid"]
    assert grade.diagnostics["calculations"]["calc_adjudicated_auc"]["scientific_valid"]

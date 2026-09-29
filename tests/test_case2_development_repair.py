"""Offline regressions in a development-only evaluator; archives are read-only fixtures."""

from __future__ import annotations

import copy
import csv
import hashlib
import json
from pathlib import Path

import pytest

from development.case2_repair import cohort, independent, semantics
from development.case2_repair.contract import PUBLIC_CONTRACT, validate_resource_summary_structure
from development.case2_repair.normalization import memberships, output_rows
from uc_bench.case2_pilot_v1_rc1_controls import build_reference

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "artifacts/uc_bench_case2_pilot_v1_rc2/science/runs"


@pytest.fixture
def reference(tmp_path):
    return build_reference(ROOT, tmp_path / "reference")


def write_json(path, value):
    path.write_text(json.dumps(value))


def csv_write(path, rows):
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def grade(workspace, submission):
    return semantics.evaluate_case2_submission(workspace, submission, require_host_process=False)


def statuses(result):
    return {r.requirement_id: r.passed for r in result.requirements}


def manifest_update(s, w, edit):
    spec = s["validation_plan"]["prospective_specification"]
    path = w / spec["eligible_entity_manifest_path"]
    rows = independent.read_csv(path)
    edit(rows)
    csv_write(path, rows)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    spec["eligible_entity_manifest_sha256"] = digest
    s["validation_input_hashes"][spec["eligible_entity_manifest_path"]] = digest


@pytest.mark.parametrize("delimiter", ["|", ",", ", "])
@pytest.mark.parametrize("reverse", [True, False])
def test_membership_order_and_disclosed_encodings(reference, delimiter, reverse):
    s, w = reference

    def edit(rows):
        for row in rows:
            values = memberships(row["source_record_ids"])
            row["source_record_ids"] = delimiter.join(reversed(values) if reverse else values)
        if reverse:
            rows.reverse()

    manifest_update(s, w, edit)
    assert cohort.reconstruct_committed_cohort(w, s["validation_plan"]).valid
    assert grade(w, s).complete_mission_success


@pytest.mark.parametrize("attack", ["duplicate", "omit", "foreign", "missing_entity"])
def test_membership_integrity_is_not_discarded(reference, attack):
    s, w = reference

    def edit(rows):
        if attack == "missing_entity":
            rows.pop()
            return
        ids = list(memberships(rows[0]["source_record_ids"]))
        if attack == "duplicate":
            ids.append(ids[0])
        if attack == "omit":
            ids.pop()
        if attack == "foreign":
            ids.append("NONEXISTENT")
        rows[0]["source_record_ids"] = ",".join(ids)

    manifest_update(s, w, edit)
    assert not cohort.reconstruct_committed_cohort(w, s["validation_plan"]).valid
    assert not grade(w, s).complete_mission_success


@pytest.mark.parametrize(
    "label", ["PRIMARY", "VALIDATION", "prospective_primary_set", "Selected cohort β"]
)
def test_every_public_split_example_and_arbitrary_label(reference, label):
    s, w = reference
    f = s["final_submission"]
    table = next(a for a in f["artifact_manifest"] if a["role"] == "ANALYSIS_TABLE")
    rows = independent.read_csv(w / table["path"])
    for row in rows:
        row[table["column_map"]["split"]] = label
    csv_write(w / table["path"], rows)
    for c in f["calculations"]:
        c["cohort"]["split_values"] = [label]
    assert grade(w, s).complete_mission_success


@pytest.mark.parametrize("state", ["absent", "present", "erroneous_unused"])
def test_optional_output_cannot_rewrite_commitment(reference, state):
    s, w = reference
    optional = copy.deepcopy(s["validation_plan"]["planned_analyses"][0])
    optional.update(analysis_id="alternative_check", planned_output_paths=["work/unrequired.json"])
    s["validation_plan"]["planned_analyses"].append(optional)
    if state != "absent":
        write_json(w / "work/unrequired.json", {"auc": 999 if state == "erroneous_unused" else 0.7})
    assert grade(w, s).complete_mission_success


def test_optional_mistake_relied_on_fails_decision_only(reference):
    s, w = reference
    f = s["final_submission"]
    wrong = copy.deepcopy(f["calculations"][0])
    wrong.update(calculation_id="optional", role="SENSITIVITY", reported_value=0.999)
    f["calculations"].append(wrong)
    unused = grade(w, s)
    assert unused.complete_mission_success
    f["claims"][0]["calculation_ids"] = ["optional"]
    f["claims"][0]["status"] = "SUPPORTED"
    used = grade(w, s)
    assert not used.complete_mission_success
    assert statuses(used)["threshold_utility"]
    assert statuses(used)["discrimination_and_uncertainty"]


@pytest.mark.parametrize("version", ["case1-resource-summary-1", "case2-resource-summary-1"])
def test_resource_validation_has_one_public_source(reference, version):
    s, w = reference
    p = w / "work/resource_summary.json"
    v = json.loads(p.read_text())
    v["schema_version"] = version
    write_json(p, v)
    assert not validate_resource_summary_structure(v)
    assert version in PUBLIC_CONTRACT["resource_summary_contract"]["accepted_schema_versions"]
    assert grade(w, s).complete_mission_success
    v["schema_version"] = "unknown"
    write_json(p, v)
    assert validate_resource_summary_structure(v)
    assert not grade(w, s).complete_mission_success


@pytest.mark.parametrize("method", ["MEAN", "MEDIAN", "FIRST", "NONE"])
def test_materially_distinct_valid_workflows_have_independent_oracle(tmp_path, method):
    s, w = build_reference(ROOT, tmp_path / method, aggregation=method)
    raw = independent.raw_records(w)
    rows = (
        independent.weighted_rows(raw) if method == "NONE" else independent.aggregate(raw, method)
    )
    oracle = independent.metrics(
        rows, bins=s["validation_plan"]["prospective_specification"]["calibration_bin_count"]
    )
    expected_ci = independent.bootstrap(
        rows,
        seed=s["validation_plan"]["prospective_specification"]["uncertainty_seed"],
        replicates=s["validation_plan"]["prospective_specification"]["uncertainty_replicates"],
        level=0.95,
    )
    result = grade(w, s)
    assert result.complete_mission_success
    for c in s["final_submission"]["calculations"]:
        assert c["reported_value"] == pytest.approx(oracle[c["metric"]], abs=0.002)
        if c["metric"] == "ROC_AUC":
            assert [c["uncertainty"]["lower"], c["uncertainty"]["upper"]] == pytest.approx(
                expected_ci, abs=0.02
            )


def test_keyed_outputs_and_naturalistic_prose(reference):
    s, w = reference
    p = w / "work/primary_results.json"
    v = json.loads(p.read_text())
    v["typed_calculations"] = {r["calculation_id"]: r for r in v["typed_calculations"]}
    write_json(p, v)
    for field in ["allowed_use", "prohibited_use", "unresolved_gates", "required_next_evidence"]:
        s["final_submission"]["decision"][field] = [
            "Retain a narrow audit use; resolve the stated evidence gaps before expanding scope."
        ]
    s["final_submission"]["narrative_summary"] = (
        "The current package does not justify expansion. Retain the bounded decision."
    )
    assert grade(w, s).complete_mission_success


@pytest.mark.parametrize(
    "attack",
    ["wrong_value", "wrong_unit", "subset", "wrong_output", "wrong_threshold", "missing_interval"],
)
def test_consequential_errors_fail_without_erasing_other_properties(reference, attack):
    s, w = reference
    c = s["final_submission"]["calculations"][0]
    if attack == "wrong_value":
        c["reported_value"] = 0.99
    if attack == "wrong_unit":
        c["estimator"] = "ROW_EMPIRICAL"
    if attack == "subset":
        c["cohort"]["entity_ids"] = ["P0001"]
        c["cohort"]["included_row_count"] = 1
    if attack == "wrong_output":
        p = w / "work/primary_results.json"
        v = json.loads(p.read_text())
        v["typed_calculations"][0]["reported_value"] = 0.99
        write_json(p, v)
    if attack == "wrong_threshold":
        c = next(c for c in s["final_submission"]["calculations"] if c["metric"] == "NET_BENEFIT")
        c["parameters"]["threshold"] = 0.8
    if attack == "missing_interval":
        c.pop("uncertainty", None)
    result = grade(w, s)
    assert not result.complete_mission_success
    assert statuses(result)["committed_entity_and_dependence_analysis"]
    assert statuses(result)["probability_and_calibration"]
    if attack != "wrong_threshold":
        assert statuses(result)["threshold_utility"]


def test_correct_decision_without_analysis_and_copied_result_after_input_change(reference):
    s, w = reference
    original = copy.deepcopy(s)
    assert grade(w, original).complete_mission_success
    s["final_submission"]["calculations"] = []
    assert not grade(w, s).complete_mission_success
    s = original
    p = w / "data/locked_predictions.csv"
    rows = independent.read_csv(p)
    for r in rows:
        r["predicted_probability"] = str(1 - float(r["predicted_probability"]))
    csv_write(p, rows)
    result = grade(w, s)
    assert not result.complete_mission_success
    assert any(
        "source_table_not_verified" in c["faults"]
        for c in result.diagnostics["calculations"].values()
    )


@pytest.mark.parametrize(
    "value", [None, [], {}, "not an object", {"final_submission": []}, {"state": 1}]
)
def test_gross_malformed_submissions_never_crash(reference, value):
    _, w = reference
    r = grade(w, value)
    assert not r.complete_mission_success
    assert not r.complete_mission_success or not r.mission_failures


def test_one_malformed_calculation_does_not_suppress_others(reference):
    s, w = reference
    s["final_submission"]["calculations"][0]["cohort"]["included_row_count"] = {"bad": True}
    result = grade(w, s)
    assert not result.complete_mission_success
    assert statuses(result)["probability_and_calibration"]
    assert statuses(result)["threshold_utility"]


def test_real_sonnet_replay_untouched_and_property_local():
    r = next(RUNS.glob("*sonnet*"))
    s = json.loads((r / "submission.json").read_text())
    w = r / "workspace"
    g = semantics.evaluate_case2_submission(w, s)
    assert g.partial_scientific_quality == 66
    assert statuses(g)["saved_artifact_chain"]
    assert not g.complete_mission_success
    assert statuses(g)["prospective_design_and_integrity"]
    assert statuses(g)["context_robustness"]
    assert g.diagnostics["calculations"]["calc_adjudicated_auc"]["scientific_valid"]
    assert not g.diagnostics["calculations"]["calc_adjudicated_context"]["scientific_valid"]
    # Independent evidence, not the verifier as oracle.
    primary = independent.aggregate(independent.raw_records(w), "MEAN")
    assert independent.metrics(primary)["ROC_AUC"] == pytest.approx(0.7209821428571429)
    assert independent.metrics(primary)["CALIBRATION_ERROR"] == pytest.approx(0.08200263368055558)
    assert (
        independent.compare_table(
            w / "work/primary_analysis_table.csv",
            primary,
            s["final_submission"]["artifact_manifest"][0]["column_map"],
        )
        == []
    )
    x17 = independent.aggregate(independent.raw_records(w, adjudicated=True), "MEAN")
    errors = independent.compare_table(
        w / "work/adjudicated_analysis_table.csv",
        x17,
        s["final_submission"]["artifact_manifest"][1]["column_map"],
    )
    assert errors == [
        {"entity": "P0017", "field": "context", "expected": ["Coast", "North"], "actual": ["Coast"]}
    ]


@pytest.mark.parametrize("model", ["gemini", "gpt"])
def test_noncompletions_not_manufactured(model):
    r = next(RUNS.glob(f"*{model}*"))
    s = json.loads((r / "submission.json").read_text())
    assert not s["state"]["completion_accepted"]
    assert not s["final_submission"]


@pytest.mark.parametrize(
    "bad",
    [
        {"typed_calculations": None},
        {"typed_calculations": [None]},
        {"typed_calculations": [{"calculation_id": "x", "reported_value": float("nan")}]},
        {"typed_calculations": {"x": {"calculation_id": "y", "reported_value": 1}}},
    ],
)
def test_bad_output_shapes_reject(bad):
    with pytest.raises(ValueError):
        output_rows(bad)


def test_archive_bytes_still_match():
    baseline = json.loads((ROOT / "development/case2_repair/archive_baseline.json").read_text())
    assert baseline
    for relative, digest in baseline.items():
        with (ROOT / relative).open("rb") as f:
            assert hashlib.file_digest(f, "sha256").hexdigest() == digest, relative


def test_known_belief_scope_problem_is_not_silently_redesigned():
    # Correctly learning that an identity defect is resolved need not reduce the
    # probability of a separate context failure. Current inherited rule disagrees.
    from uc_bench.case1_pilot_v1_rc5_public_recompute import belief_revision_errors

    hypotheses = [
        {"hypothesis_id": "identity", "belief": 0.5, "decision_effect_if_true": "SUPPORTS"},
        {"hypothesis_id": "context_failure", "belief": 0.3, "decision_effect_if_true": "WEAKENS"},
    ]
    updates = [
        {
            "hypothesis_id": "identity",
            "before": 0.5,
            "after": 0.8,
            "matched_contingency_id": "both",
        },
        {
            "hypothesis_id": "context_failure",
            "before": 0.3,
            "after": 0.7,
            "matched_contingency_id": "both",
        },
    ]
    followup = {
        "beliefs_before": {"identity": 0.5, "context_failure": 0.3},
        "result_contingencies": [
            {
                "contingency_id": "both",
                "hypothesis_updates": [
                    {"hypothesis_id": r["hypothesis_id"], "direction": "INCREASE"} for r in updates
                ],
            }
        ],
    }
    errors = belief_revision_errors(
        {"hypotheses": hypotheses}, followup, {"belief_updates": updates}, "RESOLVES"
    )
    assert "belief revision direction contradicts verified evidence" in errors


@pytest.mark.parametrize("metric", ["BINARY_CONCORDANCE", "THRESHOLD_EXPECTED_UTILITY"])
def test_public_metric_aliases_end_to_end(reference, metric):
    s, w = reference
    prop, field, base = (
        ("DISCRIMINATION", "discrimination_metric", "ROC_AUC")
        if metric == "BINARY_CONCORDANCE"
        else ("THRESHOLD_UTILITY", "utility_metric", "NET_BENEFIT")
    )
    s["validation_plan"]["prospective_specification"][field] = metric
    next(r for r in s["validation_plan"]["decision_criteria"] if r["property"] == prop)[
        "metric"
    ] = metric
    c = next(r for r in s["final_submission"]["calculations"] if r["metric"] == base)
    c["metric"] = metric
    if metric == "THRESHOLD_EXPECTED_UTILITY":
        c["parameters"].update(true_positive_value=1, false_positive_cost=1)
    assert grade(w, s).complete_mission_success
    if metric == "THRESHOLD_EXPECTED_UTILITY":
        c["parameters"]["false_positive_cost"] = 20
        assert not grade(w, s).complete_mission_success


@pytest.mark.parametrize("resource", ["none", "X17", "X24", "X31", "X46", "X58", "X63"])
def test_every_existing_resource_control_rechecked(tmp_path, resource):
    s, w = build_reference(ROOT, tmp_path / resource, resource=resource)
    result = grade(w, s)
    # Four source endpoint-ledger rows are pending reconciliation, so X24 is
    # relevant too. X31 makes no material change; X63 adds no empirical evidence.
    if resource == "X24":
        pending = [
            r
            for r in independent.read_csv(w / "data/endpoint_source_ledger.csv")
            if r["review_status"] == "discordant_pending_reconciliation"
        ]
        assert len(pending) == 4
    expected = resource in {"none", "X17", "X24", "X46", "X58"}
    assert result.complete_mission_success is expected
    assert statuses(result)["committed_entity_and_dependence_analysis"]
    assert statuses(result)["threshold_utility"]


@pytest.mark.parametrize(
    "disposition,scope",
    [
        ("PAUSE", "HOLD_CURRENT_CLAIM"),
        ("INSUFFICIENT_EVIDENCE", "HOLD_CURRENT_CLAIM"),
        ("CONTINUE", "TARGETED_CONTEXT_INVESTIGATION"),
        ("STOP", "END_DEVELOPMENT_PATH"),
    ],
)
def test_decision_alternatives_need_evidence(tmp_path, disposition, scope):
    s, w = build_reference(ROOT, tmp_path / disposition, decision_override=(disposition, scope))
    assert grade(w, s).complete_mission_success
    s["final_submission"]["calculations"] = []
    assert not grade(w, s).complete_mission_success


def test_context_assignment_failure_is_local_to_context_calculation():
    r = next(RUNS.glob("*sonnet*"))
    s = json.loads((r / "submission.json").read_text())
    result = semantics.evaluate_case2_submission(r / "workspace", s)
    rows = result.diagnostics["calculations"]
    assert rows["calc_adjudicated_auc"]["scientific_valid"]
    assert "context_assignment_disagrees_with_source" in rows["calc_adjudicated_context"]["faults"]
    assert (
        result.first_decision_critical_failure["requirement_id"] == "discrimination_and_uncertainty"
    )


def test_duplicate_table_membership_not_silently_deduplicated(reference):
    s, w = reference
    table = next(
        a for a in s["final_submission"]["artifact_manifest"] if a["role"] == "ANALYSIS_TABLE"
    )
    p = w / table["path"]
    rows = independent.read_csv(p)
    col = table["column_map"]["source_record_ids"]
    rows[0][col] += "|" + memberships(rows[0][col])[0]
    csv_write(p, rows)
    assert not grade(w, s).complete_mission_success


def test_malformed_unrelated_saved_output_is_local(reference):
    s, w = reference
    p = w / "work/primary_results.json"
    payload = json.loads(p.read_text())
    payload["typed_calculations"].append(
        {"calculation_id": "unclaimed_diagnostic", "reported_value": "bad"}
    )
    write_json(p, payload)
    assert grade(w, s).complete_mission_success
    payload["typed_calculations"].append(copy.deepcopy(payload["typed_calculations"][0]))
    write_json(p, payload)
    g = grade(w, s)
    assert not g.complete_mission_success
    assert statuses(g)["threshold_utility"]


def test_existing_altered_context_control_is_tractable(tmp_path):
    from uc_bench.case2_pilot_v1_rc1_controls import build_strong_context_variant

    s, w = build_strong_context_variant(ROOT, tmp_path / "altered")
    raw = independent.raw_records(w)
    oracle = independent.metrics(independent.aggregate(raw, "MEAN"))
    assert oracle["SITE_WEIGHTED_ROC_AUC"] >= 0.65
    assert grade(w, s).complete_mission_success


def test_posthoc_aggregation_cannot_override_prospective_choice(reference):
    s, w = reference
    s["validation_plan"]["prospective_specification"]["aggregation"] = "FIRST"
    result = grade(w, s)
    assert not result.complete_mission_success
    assert not statuses(result)["discrimination_and_uncertainty"]


def test_output_error_does_not_double_deduct_artifact_provenance(reference):
    s, w = reference
    c = s["final_submission"]["calculations"][0]
    c["reported_value"] = 0.99
    g = grade(w, s)
    assert not g.complete_mission_success
    assert statuses(g)["saved_artifact_chain"]
    assert not statuses(g)["discrimination_and_uncertainty"]

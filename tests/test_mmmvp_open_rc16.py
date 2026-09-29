from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import patch

import pytest

from uc_bench.hashing import sha256_file
from uc_bench.mmmvp_open_controls import build_open_reference, run_open_controls
from uc_bench.mmmvp_open_environment import OpenProtocolError
from uc_bench.mmmvp_open_rc12_trajectory import restore_rc12_environment
from uc_bench.mmmvp_open_rc14_runner import RC14DurableTrajectoryStore
from uc_bench.mmmvp_open_rc16_artifacts import (
    validate_analysis_table_artifact,
    validate_calculation_output,
)
from uc_bench.mmmvp_open_rc16_trajectory import rc16_trajectory_replay_check
from uc_bench.mmmvp_open_rc16_verifier import (
    EnvironmentEvidenceError,
    decode_agent_payload_total,
    index_agent_artifacts_total,
    validate_final_submission_total,
    verify_rc16_open_submission,
)


def test_rc16_gate_protects_the_complete_inherited_rc14_surface() -> None:
    import scripts.check_mmmvp_open_rc16_gate as gate
    from uc_bench.mmmvp_open_rc14_freeze import read_rc14_release_freeze

    root = Path(__file__).resolve().parents[1]
    protected = gate._frozen_predecessor_hashes(root)
    rc14 = read_rc14_release_freeze(root)
    assert set(rc14["infrastructure_hashes"]).issubset(protected)
    assert (
        protected["artifacts/mmmvp_open_rc14/archived_submission_replay.json"]
        == "ea3016898d698c5f3e311fb4edb9c20d29a791c38649b723a2cfe90834847c08"
    )


def test_rc16_gate_evidence_names_match_invariant_keys() -> None:
    names = (
        "compatibility_inheritance.json",
        "parser_trust_boundary_audit.json",
        "gemini_regression.json",
        "crash_corpus.json",
        "red_team_parser_review.json",
        "pre_freeze_rehearsal.json",
    )
    keys = {Path(name).stem for name in names}
    assert {
        "compatibility_inheritance",
        "parser_trust_boundary_audit",
        "gemini_regression",
        "crash_corpus",
        "red_team_parser_review",
        "pre_freeze_rehearsal",
    } == keys

ROOT = Path(__file__).resolve().parents[1]
GEMINI_RUN = ROOT / (
    "build/uc_bench_mmmvp_open_rc14_runs/"
    "open-mmmvp-rc15-sentinel-00-google-gemini-3.1-pro-preview-case-02-atte"
)


def _artifact(path: Path) -> tuple[dict[str, Any], Path]:
    return (
        {
            "artifact_id": "OUT",
            "path": "work/output.json",
            "role": "CALCULATION_OUTPUT",
            "source_paths": [],
        },
        path,
    )


@pytest.mark.parametrize(
    "payload",
    [
        None,
        True,
        1,
        0.5,
        "value",
        [],
        {},
        {"unrelated": []},
        {"typed_calculations": None},
        {"typed_calculations": {}},
        {"typed_calculations": [None]},
        {"typed_calculations": [1, "x"]},
        {"typed_calculations": [{"calculation_id": "C"}]},
        {"typed_calculations": [{"calculation_id": "C", "reported_value": "0.7"}]},
        {"typed_calculations": [{"calculation_id": "C", "reported_value": float("nan")}]},
        {"typed_calculations": [{"calculation_id": "C", "reported_value": float("inf")}]},
        {
            "typed_calculations": [
                {"calculation_id": "C", "reported_value": 0.7},
                {"calculation_id": "C", "reported_value": 0.7},
            ]
        },
        {"typed_calculations": [{"calculation_id": "C", "reported_value": 1e308}]},
    ],
)
def test_calculation_output_shapes_are_structured_mismatches(tmp_path: Path, payload: Any) -> None:
    path = tmp_path / "output.json"
    path.write_text(json.dumps(payload, allow_nan=True), encoding="utf-8")
    first = validate_calculation_output(_artifact(path), "C", 0.7)
    second = validate_calculation_output(_artifact(path), "C", 0.7)
    assert not first.valid
    assert first == second
    assert first.origin == "agent_controlled"
    assert first.fault_codes


@pytest.mark.parametrize(
    "raw",
    [b"", b"{", b"\xff\xfe", b'{"typed_calculations": [}'],
)
def test_calculation_output_bytes_fail_without_exception(tmp_path: Path, raw: bytes) -> None:
    path = tmp_path / "output.json"
    path.write_bytes(raw)
    result = validate_calculation_output(_artifact(path), "C", 0.7)
    assert not result.valid
    assert result.fault_codes


def test_missing_calculation_output_is_structured() -> None:
    result = validate_calculation_output(None, "C", 0.7)
    assert result.fault_codes == ("artifact_missing",)


def test_extreme_integer_calculation_output_is_structured(tmp_path: Path) -> None:
    path = tmp_path / "output.json"
    path.write_text(
        '{"typed_calculations":[{"calculation_id":"C","reported_value":'
        + "9" * 10_000
        + "}]}",
        encoding="utf-8",
    )
    result = validate_calculation_output(_artifact(path), "C", 0.7)
    assert not result.valid
    assert "reported_value_not_finite_numeric" in result.fault_codes


def test_deep_calculation_output_is_structured(tmp_path: Path) -> None:
    path = tmp_path / "output.json"
    path.write_text("[" * 2_000 + "]" * 2_000, encoding="utf-8")
    result = validate_calculation_output(_artifact(path), "C", 0.7)
    assert not result.valid
    assert "top_level_object_required" in result.fault_codes


def test_deep_irrelevant_json_has_no_hidden_nesting_failure(tmp_path: Path) -> None:
    path = tmp_path / "output.json"
    path.write_text(
        '{"pad":' + "[" * 2_000 + "null" + "]" * 2_000
        + ',"typed_calculations":[{"calculation_id":"C","reported_value":0.7}]}',
        encoding="utf-8",
    )
    result = validate_calculation_output(_artifact(path), "C", 0.7)
    assert result.valid


def test_agent_payload_decoder_rejects_pathological_json_recoverably() -> None:
    with pytest.raises(OpenProtocolError):
        decode_agent_payload_total("[" * 2_000 + "]" * 2_000)
    with pytest.raises(OpenProtocolError):
        decode_agent_payload_total('{"value":' + "9" * 10_000 + "}")


def test_extreme_schema_number_is_a_structured_contract_failure(tmp_path: Path) -> None:
    submission, _ = build_open_reference(
        ROOT, "case_02", tmp_path / "schema-extreme", alternative=False
    )
    final = submission["final_submission"]
    final["calculations"][0]["reported_value"] = 10**10_000
    result = validate_final_submission_total(final)
    assert not result.valid
    assert any(issue.code == "malformed_agent_value" for issue in result.issues)


def test_valid_calculation_output_requires_one_exact_finite_link(tmp_path: Path) -> None:
    path = tmp_path / "output.json"
    path.write_text(
        json.dumps({"typed_calculations": [{"calculation_id": "C", "reported_value": 0.7}]}),
        encoding="utf-8",
    )
    result = validate_calculation_output(_artifact(path), "C", 0.7)
    assert result.valid
    assert result.linked_calculation_ids == ("C",)


def test_large_irrelevant_json_field_is_streamed_without_changing_validity(tmp_path: Path) -> None:
    path = tmp_path / "output.json"
    with path.open("w", encoding="utf-8") as handle:
        handle.write('{"pad":"')
        handle.write("x" * 2_000_000)
        handle.write(
            '","typed_calculations":[{"calculation_id":"C","reported_value":0.7}]}'
        )
    result = validate_calculation_output(_artifact(path), "C", 0.7)
    assert result.valid


def test_many_calculation_rows_keep_bounded_validation_state(tmp_path: Path) -> None:
    path = tmp_path / "output.json"
    with path.open("w", encoding="utf-8") as handle:
        handle.write('{"typed_calculations":[')
        for index in range(20_000):
            if index:
                handle.write(",")
            handle.write(
                '{"calculation_id":"C","reported_value":0.7,'
                f'"irrelevant_{index}":null}}'
            )
        handle.write("]}")
    result = validate_calculation_output(_artifact(path), "C", 0.7)
    assert not result.valid
    assert result.linked_calculation_ids == ("C",)
    assert result.fault_codes.count("calculation_id_duplicate") == 1


@pytest.mark.parametrize(
    ("text", "expected_fault"),
    [
        ("", "artifact_empty"),
        (
            "unit,unit,records,score,label,partition\na,a,s,0.5,1,VALIDATION\n",
            "duplicate_csv_header",
        ),
        ("unit,records,score,label\na,s,0.5,1\n", "mapped_csv_column_missing"),
        ("unit,records,score,label,partition\na,s,0.5,1\n", "ragged_csv_row"),
        ("unit,records,score,label,partition\n,s,0.5,1,VALIDATION\n", "blank_required_identifier"),
        ("unit,records,score,label,partition\na,s,0.5,2,VALIDATION\n", "invalid_binary_outcome"),
        ("unit,records,score,label,partition\na,s,nan,1,VALIDATION\n", "prediction_not_finite"),
        (
            "unit,records,score,label,partition\na,s1,0.5,1,VALIDATION\na,s2,0.6,0,VALIDATION\n",
            "entity_outcome_conflict",
        ),
        (
            "unit,records,score,label,partition\na,s,0.5,1,VALIDATION\nb,s,0.6,1,VALIDATION\n",
            "duplicate_source_record",
        ),
    ],
)
def test_analysis_table_adversarial_shapes_are_structured(
    tmp_path: Path, text: str, expected_fault: str
) -> None:
    submission, workspace = build_open_reference(
        ROOT, "case_02", tmp_path / "table-shape", alternative=False
    )
    source_manifest = next(
        row
        for row in submission["final_submission"]["artifact_manifest"]
        if row["role"] == "ANALYSIS_TABLE"
    )
    path = workspace / "work/table.csv"
    path.write_text(text, encoding="utf-8")
    manifest = {
        "artifact_id": "T",
        "path": "work/table.csv",
        "role": "ANALYSIS_TABLE",
        "source_paths": source_manifest["source_paths"],
        "analysis_structure": "ENTITY_AGGREGATED",
        "aggregation": "MEAN",
        "column_map": {
            "entity_id": "unit",
            "source_record_ids": "records",
            "prediction": "score",
            "outcome": "label",
            "split": "partition",
        },
    }
    result, table = validate_analysis_table_artifact(
        workspace, "T", (manifest, path), "none"
    )
    assert table is None
    assert expected_fault in result.fault_codes


@pytest.mark.parametrize("raw", [b"\xff", None])
def test_analysis_table_unreadable_bytes_are_structured(
    tmp_path: Path, raw: bytes | None
) -> None:
    path = tmp_path / "table.csv"
    if raw is not None:
        path.write_bytes(raw)
    manifest = {
        "artifact_id": "T",
        "path": "work/table.csv",
        "role": "ANALYSIS_TABLE",
        "source_paths": [],
        "analysis_structure": "ENTITY_AGGREGATED",
        "aggregation": "MEAN",
        "column_map": {
            "entity_id": "unit",
            "source_record_ids": "records",
            "prediction": "score",
            "outcome": "label",
            "split": "partition",
        },
    }
    result, table = validate_analysis_table_artifact(tmp_path, "T", (manifest, path), "none")
    assert table is None
    assert result.fault_codes


def test_harmless_extra_csv_column_preserves_reference_grade(tmp_path: Path) -> None:
    submission, workspace = build_open_reference(
        ROOT, "case_02", tmp_path / "reference", alternative=False
    )
    path = workspace / "work/analysis_table.csv"
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text(
        "\n".join([lines[0] + ",harmless", *[line + ",note" for line in lines[1:]]]) + "\n",
        encoding="utf-8",
    )
    grade = verify_rc16_open_submission(ROOT, workspace, submission, condition_id="case_02")
    assert grade.complete_mission_success


def test_artifact_symlink_loop_is_a_structured_unsafe_path(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "work").mkdir(parents=True)
    (workspace / "work/loop").symlink_to("loop")
    indexed, faults = index_agent_artifacts_total(
        workspace,
        {
            "artifact_manifest": [
                {
                    "artifact_id": "LOOP",
                    "path": "work/loop",
                    "role": "CALCULATION_OUTPUT",
                    "source_paths": [],
                }
            ]
        },
    )
    assert indexed == {}
    assert faults == ["missing_or_unsafe:LOOP"]


def test_unresolvable_table_source_activates_zero_row_bound(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "work").mkdir(parents=True)
    (workspace / "purchased/none").mkdir(parents=True)
    (workspace / "purchased/none/no_new_evidence.json").write_text(
        '{"new_evidence":false}\n', encoding="utf-8"
    )
    path = workspace / "work/table.csv"
    path.write_text(
        "unit,records,score,label,partition\na,s,0.5,1,VALIDATION\n",
        encoding="utf-8",
    )
    manifest = {
        "artifact_id": "T",
        "path": "work/table.csv",
        "role": "ANALYSIS_TABLE",
        "source_paths": ["purchased/none/no_new_evidence.json"],
        "analysis_structure": "ENTITY_AGGREGATED",
        "aggregation": "MEAN",
        "column_map": {
            "entity_id": "unit",
            "source_record_ids": "records",
            "prediction": "score",
            "outcome": "label",
            "split": "partition",
        },
    }
    result, table = validate_analysis_table_artifact(
        workspace, "T", (manifest, path), "none"
    )
    assert table is None
    assert "unexpected_row_count" in result.fault_codes


def _gemini_store() -> tuple[Any, dict[str, Any]]:
    workspace = GEMINI_RUN / "workspace"
    host = GEMINI_RUN / "host_trajectory"
    latest = json.loads((host / "latest.json").read_text(encoding="utf-8"))
    core = restore_rc12_environment(ROOT, workspace, latest)
    store = RC14DurableTrajectoryStore.reopen(host, workspace=workspace, core=core, secret="")
    return store, core.export_submission()


def test_exact_gemini_rc15_regression_is_40_without_grader_or_lifecycle_fault() -> None:
    store, submission = _gemini_store()
    grade = verify_rc16_open_submission(
        ROOT, GEMINI_RUN / "workspace", submission, condition_id="case_02"
    ).to_dict()
    assert grade["complete_mission_success"] is False
    assert grade["partial_scientific_quality"] == 40.0
    assert grade["reliability_score"] == 100.0
    assert grade["first_decision_critical_failure"]["requirement_id"] == (
        "prospective_plan_implemented"
    )
    auc = next(
        row
        for row in grade["diagnostics"]["artifact_validation"]
        if row["artifact_path"] == "work/auc.txt"
    )
    assert auc["observed_top_level_type"] == "number"
    assert "top_level_object_required" in auc["fault_codes"]
    assert (
        "saved_output_mismatch"
        in grade["diagnostics"]["typed_calculations"]["calc_roc_auc"]["faults"]
    )
    replay = rc16_trajectory_replay_check(
        ROOT,
        GEMINI_RUN / "workspace",
        store,
        condition_id="case_02",
        grade=grade,
        stop_condition="no_tools_called",
    )
    assert replay["passed"]
    assert replay["grader_replay"]["passed"]
    assert "inconsistent_tool_lifecycle" not in replay["faults"]
    assert sha256_file(GEMINI_RUN / "run_summary.json") == (
        "a88ce2a87e77e0f2222f435c36903540357ae4463c4084bd8306515e4d98231d"
    )


def test_deliberate_grader_exception_does_not_become_lifecycle_failure() -> None:
    store, submission = _gemini_store()
    grade = verify_rc16_open_submission(
        ROOT, GEMINI_RUN / "workspace", submission, condition_id="case_02"
    ).to_dict()

    def broken(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("deliberate grader fault")

    replay = rc16_trajectory_replay_check(
        ROOT,
        GEMINI_RUN / "workspace",
        store,
        condition_id="case_02",
        grade=grade,
        stop_condition="no_tools_called",
        grader=broken,
    )
    assert replay["passed"]
    assert replay["lifecycle"]["passed"]
    assert not replay["grader_replay"]["passed"]
    assert replay["grader_replay"]["faults"] == ["verifier_exception:RuntimeError"]


def test_environment_corruption_is_not_scored_as_agent_failure(tmp_path: Path) -> None:
    submission, workspace = build_open_reference(
        ROOT, "case_02", tmp_path / "environment-corrupt", alternative=False
    )
    (workspace / "data/cohort_metadata.csv").write_bytes(b"\xff")
    from uc_bench import mmmvp_open_verifier as frozen_verifier

    submission["protected_evidence_hashes"] = frozen_verifier._protected_workspace_hashes(  # noqa: SLF001
        workspace
    )
    with pytest.raises(EnvironmentEvidenceError):
        verify_rc16_open_submission(ROOT, workspace, submission, condition_id="case_02")


def test_protected_evidence_symlink_is_infrastructure_failure(tmp_path: Path) -> None:
    submission, workspace = build_open_reference(
        ROOT, "case_02", tmp_path / "protected-link", alternative=False
    )
    metadata = workspace / "data/cohort_metadata.csv"
    metadata.unlink()
    metadata.symlink_to("locked_predictions.csv")
    with pytest.raises(EnvironmentEvidenceError):
        verify_rc16_open_submission(ROOT, workspace, submission, condition_id="case_02")


@pytest.mark.parametrize(
    "payload",
    [b"\xff", ("[" * 2_000 + "]" * 2_000).encode()],
)
def test_host_record_corruption_is_infrastructure_failure(
    tmp_path: Path, payload: bytes
) -> None:
    submission, workspace = build_open_reference(
        ROOT, "case_02", tmp_path / "host-corrupt", alternative=False
    )
    host = workspace.parent / ".mmmvp_host_records" / workspace.name
    (host / "final_submission.json").write_bytes(payload)
    with pytest.raises(EnvironmentEvidenceError):
        verify_rc16_open_submission(ROOT, workspace, submission, condition_id="case_02")


def test_all_open_controls_preserve_existing_outcomes(tmp_path: Path) -> None:
    with TemporaryDirectory(dir=tmp_path) as first, TemporaryDirectory(dir=tmp_path) as second:
        frozen = run_open_controls(ROOT, Path(first) / "controls")
        with patch(
            "uc_bench.mmmvp_open_controls.verify_open_submission",
            verify_rc16_open_submission,
        ):
            hardened = run_open_controls(ROOT, Path(second) / "controls")
    assert frozen["status"] == hardened["status"] == "passed"
    assert len(frozen["results"]) == len(hardened["results"])
    keys = (
        "condition_id",
        "control",
        "complete_mission_success",
        "partial_scientific_quality",
        "failure_class",
        "mission_failures",
    )
    assert [tuple(row[key] for key in keys) for row in frozen["results"]] == [
        tuple(row[key] for key in keys) for row in hardened["results"]
    ]

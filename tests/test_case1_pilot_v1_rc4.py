from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from uc_bench.case1_pilot_v1_rc3_release import read_rc3_freeze
from uc_bench.case1_pilot_v1_rc3_tools import case1_tool_definitions
from uc_bench.case1_pilot_v1_rc4_artifacts import normalize_typed_calculation_container
from uc_bench.case1_pilot_v1_rc4_contract import (
    ANALYSIS_SPLIT_CONTRACT,
    PUBLIC_CONTRACT,
    RESOURCE_RETURN_SCHEMA_VERSION,
    RESOURCE_SUMMARY_SCHEMA_VERSION,
)
from uc_bench.case1_pilot_v1_rc4_controls import replay_rc3_submissions, run_rc4_controls
from uc_bench.case1_pilot_v1_rc4_environment import RC4Case1Environment
from uc_bench.case1_pilot_v1_rc4_interface import INITIAL_USER_MESSAGE, production_request
from uc_bench.case1_pilot_v1_rc4_preflight import run_exact_production_preflight
from uc_bench.case1_pilot_v1_rc4_release import credential_scan, scientific_evidence_hashes
from uc_bench.case1_pilot_v1_rc4_runner import grader_assessment
from uc_bench.case1_pilot_v1_runner import Case1PilotRunConfig

ROOT = Path(os.environ.get("UC_BENCH_CLEAN_ROOT", Path(__file__).resolve().parents[1])).resolve()


def test_release_preparation_uses_the_active_interpreter_not_workspace_venv_symlink() -> None:
    source = (ROOT / "scripts/prepare_case1_pilot_v1_rc4.py").read_text(encoding="utf-8")
    assert '"./.venv/bin/python"' not in source
    assert '"./.venv/bin/ruff"' not in source
    assert "Path(sys.executable).absolute()" in source
    assert 'Path(sys.prefix) / "bin/ruff"' in source


def test_credential_scan_accepts_only_declared_synthetic_values() -> None:
    with tempfile.TemporaryDirectory(prefix="rc4-credential-scan-") as directory:
        root = Path(directory)
        fixture = root / "fixture.txt"
        fixture.write_text(
            "sk-or-v1-rc3-fake-transport-secret\n"
            "sk-or-v1-rc4-fake-transport-secret\n",
            encoding="utf-8",
        )
        assert credential_scan(root, {"fixture.txt": "unused"})
        unexpected_credential = "-".join(
            ["sk", "or", "v1", "unexpected", "credential", "value"]
        )
        fixture.write_text(
            fixture.read_text(encoding="utf-8")
            + unexpected_credential
            + "\n",
            encoding="utf-8",
        )
        assert not credential_scan(root, {"fixture.txt": "unused"})


def test_split_contract_has_no_hidden_literal() -> None:
    assert ANALYSIS_SPLIT_CONTRACT["required_literal"] is None
    assert set(ANALYSIS_SPLIT_CONTRACT["examples"]) >= {"PRIMARY", "VALIDATION"}
    assert ANALYSIS_SPLIT_CONTRACT["arbitrary_nonempty_label_allowed"]


def test_calculation_containers_normalize_equivalently() -> None:
    listed = [{"calculation_id": "C1", "reported_value": 0.5}]
    keyed = {"C1": {"reported_value": 0.5}}
    assert normalize_typed_calculation_container(listed) == (listed, [])
    assert normalize_typed_calculation_container(keyed) == (listed, [])


@pytest.mark.parametrize(
    "value,fault",
    [
        ({"C1": {"calculation_id": "C2"}}, "calculation_id_key_mismatch"),
        ([{"calculation_id": "C1"}, {"calculation_id": "C1"}], "calculation_id_duplicate"),
        ("C1", "typed_calculations_list_or_object_required"),
    ],
)
def test_malformed_calculation_container_fails_clearly(value: object, fault: str) -> None:
    _, faults = normalize_typed_calculation_container(value)
    assert fault in faults


def test_resource_contract_distinguishes_return_from_summary() -> None:
    repair = PUBLIC_CONTRACT["representation_repairs"]["resource_summary_versions"]
    assert repair["returned_evidence_package"] == RESOURCE_RETURN_SCHEMA_VERSION
    assert repair["agent_authored_summary"] == RESOURCE_SUMMARY_SCHEMA_VERSION
    assert RESOURCE_RETURN_SCHEMA_VERSION != RESOURCE_SUMMARY_SCHEMA_VERSION


def test_agent_visible_validator_checks_resource_summary() -> None:
    with tempfile.TemporaryDirectory(prefix="rc4-resource-validator-") as directory:
        workspace = Path(directory) / "workspace"
        RC4Case1Environment(ROOT, "case_01", workspace)
        completed = subprocess.run(
            [
                sys.executable,
                (workspace / "validate_saved_artifact.py").as_posix(),
                (workspace / "contract_templates/resource_summary_template.json").as_posix(),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
    result = json.loads(completed.stdout)
    assert completed.returncode == 0
    assert result == {"artifact_type": "RESOURCE_SUMMARY", "errors": [], "valid": True}


def test_resource_hash_contract_matches_hidden_lowercase_semantics() -> None:
    with tempfile.TemporaryDirectory(prefix="rc4-resource-hash-validator-") as directory:
        workspace = Path(directory) / "workspace"
        RC4Case1Environment(ROOT, "case_01", workspace)
        invalid = workspace / "work/invalid_resource_summary.json"
        invalid.write_text(
            json.dumps(
                {
                    "schema_version": RESOURCE_SUMMARY_SCHEMA_VERSION,
                    "resource_id": "none",
                    "source_hashes": {"": "A" * 64},
                    "results": {"new_evidence": False},
                }
            ),
            encoding="utf-8",
        )
        completed = subprocess.run(
            [
                sys.executable,
                (workspace / "validate_saved_artifact.py").as_posix(),
                invalid.as_posix(),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
    result = json.loads(completed.stdout)
    assert completed.returncode == 1
    assert result["artifact_type"] == "RESOURCE_SUMMARY"
    assert any("lowercase SHA-256" in error for error in result["errors"])


def test_completion_prompt_is_explicit_and_scientifically_neutral() -> None:
    assert INITIAL_USER_MESSAGE == (
        "Complete the full predictor evidence investigation autonomously. Continue through all "
        "irreversible stages and finish by calling submit with a contract-valid final submission. "
        "Do not stop for user confirmation; no additional user response will be provided."
    )
    lowered = INITIAL_USER_MESSAGE.lower()
    for hidden_hint in ("f0001", "x17", "x24", "x31", "x46", "auc", "endpoint defect"):
        assert hidden_hint not in lowered


def test_tool_schema_is_unchanged() -> None:
    request = production_request(Case1PilotRunConfig("parity", "openai/gpt-5"))
    assert request["tools"] == case1_tool_definitions()
    assert len(request["tools"]) == 9


def test_rc3_replay_matches_predeclared_adjudication() -> None:
    expected = json.loads(
        (
            ROOT
            / "artifacts/uc_bench_case1_pilot_v1_rc4/expected_rc3_property_adjudication.json"
        ).read_text(encoding="utf-8")
    )
    replay = replay_rc3_submissions(ROOT, expected)
    assert replay["passed"]
    opus = replay["opus_unsubmitted_saved_work_diagnostic"]
    assert opus["official_scientific_score"] is None
    assert not opus["calibration_matches"]
    assert all(opus["source_split_provenance_defects"].values())


def test_controls_and_ten_single_fault_mutations() -> None:
    with tempfile.TemporaryDirectory(prefix="rc4-controls-test-") as directory:
        result = run_rc4_controls(ROOT, Path(directory))
    assert result["passed"]
    assert len(result["single_fault_mutations"]) == 10
    assert all(row["passed"] for row in result["single_fault_mutations"])
    assert all(result["resource_specific_dependency_control"].values())


def test_exact_production_path_and_terminal_retry() -> None:
    with tempfile.TemporaryDirectory(prefix="rc4-preflight-test-") as directory:
        result = run_exact_production_preflight(ROOT, Path(directory))
    assert result["passed"]
    assert result["fake_provider_requests"] == 10
    assert result["checks"]["pending_request_body_identical"]
    assert result["checks"]["irreversible_actions_not_duplicated"]
    assert result["checks"]["exact_preserved_opus_error_exercised"]
    assert result["checks"]["second_terminal_failure_stops_after_one_retry"]
    assert result["checks"]["invalid_json_is_persisted_and_retried_once"]


def test_grader_consistency_accepts_subcredit_decomposition() -> None:
    properties = list(PUBLIC_CONTRACT["scientific_property_dependency_graph"])
    grade = {
        "complete_mission_success": False,
        "first_decision_critical_failure": {"requirement_id": properties[0]},
        "mission_failures": [properties[0]],
        "failure_class": "scientific_failure",
        "requirements": [
            {"requirement_id": name, "passed": name != properties[0]} for name in properties
        ],
        "partial_scientific_quality": 85.0,
        "diagnostics": {
            "prose_scored": False,
            "property_points": {
                name: 0.0 if name == properties[0] else float(
                    PUBLIC_CONTRACT["scientific_property_dependency_graph"][name]["weight"]
                )
                for name in properties
            },
        },
    }
    assert grader_assessment(grade, None)["passed"]


def test_rc3_freeze_and_scientific_evidence_are_intact() -> None:
    assert read_rc3_freeze(ROOT)["closure"]["aggregate_digest"] == (
        "92e909ad267777ac0ee5e6b790d2a9be6910654d3151582e1be7982863b4b108"
    )
    assert scientific_evidence_hashes(ROOT)

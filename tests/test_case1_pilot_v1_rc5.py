from __future__ import annotations

import copy
import csv
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

import uc_bench.case1_pilot_v1_rc5_analysis as rc5_analysis
import uc_bench.case1_pilot_v1_rc5_controls as rc5_controls_module
import uc_bench.case1_pilot_v1_rc5_execution as rc5_execution
import uc_bench.case1_pilot_v1_rc5_preflight as rc5_preflight_module
import uc_bench.case1_pilot_v1_rc5_release as rc5_release
import uc_bench.case1_pilot_v1_rc5_runner as rc5_runner_module
import uc_bench.mmmvp_open_rc17_controls as legacy_controls
from uc_bench.case1_pilot_v1_rc4_release import read_rc4_freeze
from uc_bench.case1_pilot_v1_rc5_cohort import reconstruct_committed_cohort
from uc_bench.case1_pilot_v1_rc5_contract import (
    CONTRACT_COMPLETENESS_AUDIT,
    PUBLIC_CONTRACT,
    contract_completeness_valid,
    validate_final_submission,
    validate_followup_plan,
    validate_validation_plan,
)
from uc_bench.case1_pilot_v1_rc5_controls import (
    _copy_episode,
    _grade,
    _rc4_fixture,
    _rehash_final_path,
    _replace_final,
    _synchronize_followup_commit,
    _synchronize_manifest_commit,
    build_reference,
    rc4_artifacts_unchanged,
    run_rc5_controls,
)
from uc_bench.case1_pilot_v1_rc5_environment import RC5Case1Environment
from uc_bench.case1_pilot_v1_rc5_interface import production_request
from uc_bench.case1_pilot_v1_rc5_normalization import (
    NormalizationError,
    normalize_source_hashes,
)
from uc_bench.case1_pilot_v1_rc5_preflight import run_exact_production_preflight
from uc_bench.case1_pilot_v1_rc5_public_recompute import belief_revision_errors
from uc_bench.case1_pilot_v1_rc5_reporting import (
    CorruptTrajectoryError,
    reconstruct_lifecycle,
    reconstruct_lifecycle_or_empty,
)
from uc_bench.case1_pilot_v1_rc5_verifier import WEIGHTS
from uc_bench.case1_pilot_v1_runner import Case1PilotRunConfig
from uc_bench.errors import ConfigurationError
from uc_bench.hashing import canonical_sha256
from uc_bench.model_runner import _write_json

ROOT = Path(os.environ.get("UC_BENCH_CLEAN_ROOT", Path(__file__).resolve().parents[1])).resolve()


def _write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str] | None = None) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_rc4_is_immutable_and_official_result_is_not_replaced() -> None:
    assert read_rc4_freeze(ROOT)["closure"]["aggregate_digest"] == (
        "d9a79a6f1d29248bad2c3b71a3d0546aea1b5ac9920007ae69445242f397ee66"
    )
    assert rc4_artifacts_unchanged(ROOT)
    report = json.loads(
        (ROOT / "artifacts/uc_bench_case1_pilot_v1_rc4/science/pilot_report.json").read_text()
    )
    assert report["models"][0]["official_partial_scientific_quality"] == 22.0


def test_contract_completeness_inventory_is_host_only_and_non_prose() -> None:
    assert contract_completeness_valid()
    assert "contract_completeness_inventory" not in PUBLIC_CONTRACT
    assert all(not row["prose_affects_score"] for row in CONTRACT_COMPLETENESS_AUDIT)
    assert (
        "advisory-only"
        in PUBLIC_CONTRACT["scientific_property_dependency_graph"]["decision_relevant_followup"][
            "conditional_dependencies"
        ]["X63"]
    )


def test_provider_request_and_tool_schema_are_unchanged_from_rc4() -> None:
    from uc_bench.case1_pilot_v1_rc4_interface import production_request as rc4_request

    config = Case1PilotRunConfig("hash-check", "openai/gpt-5")
    assert production_request(config) == rc4_request(config)


def test_contract_field_families_accept_reference_submission() -> None:
    with tempfile.TemporaryDirectory(prefix="rc5-contract-positive-") as directory:
        submission, workspace = build_reference(ROOT, Path(directory) / "workspace")
        _write_submission_mirrors(workspace, submission)
        for kind, name in (
            ("validation", "validation_plan.json"),
            ("followup", "followup_plan.json"),
            ("final", "final_submission.json"),
        ):
            result = _local_contract_check(workspace, kind, workspace / "work" / name)
            assert result.returncode == 0, result.stdout + result.stderr


def test_contract_field_families_reject_targeted_mutations() -> None:
    with tempfile.TemporaryDirectory(prefix="rc5-contract-negative-") as directory:
        submission, workspace = build_reference(ROOT, Path(directory) / "workspace")
        _write_submission_mirrors(workspace, submission)
        mutations: list[tuple[str, str, object]] = [
            ("validation", "validation_plan", lambda value: value.update(schema_version="bad")),
            (
                "validation",
                "validation_plan",
                lambda value: value.update(hypotheses=[1]),
            ),
            (
                "validation",
                "validation_plan",
                lambda value: value["planned_analyses"][0].update(input_paths=["missing.csv"]),
            ),
            (
                "validation",
                "validation_plan",
                lambda value: value["prospective_specification"].update(aggregation="NONE"),
            ),
            (
                "validation",
                "validation_plan",
                lambda value: value["decision_criteria"][0].update(metric="ENTITY_COUNT"),
            ),
            (
                "validation",
                "validation_plan",
                lambda value: value["decision_criteria"][0].update(threshold=-999.0),
            ),
            (
                "followup",
                "followup_plan",
                lambda value: value.update(chosen_resource="X17"),
            ),
            (
                "followup",
                "followup_plan",
                lambda value: value.update(beliefs_before={}),
            ),
            (
                "final",
                "final_submission",
                lambda value: value["artifact_manifest"][0].update(path="work/missing.csv"),
            ),
            (
                "final",
                "final_submission",
                lambda value: value["calculations"][0].update(source_analysis_table_id="MISSING"),
            ),
            (
                "final",
                "final_submission",
                lambda value: value["resource_assessment"].update(resource_id="X17"),
            ),
            (
                "final",
                "final_submission",
                lambda value: value["belief_updates"][0].update(matched_contingency_id="MISSING"),
            ),
            (
                "final",
                "final_submission",
                lambda value: value["decision"].update(disposition="STOP"),
            ),
            (
                "final",
                "final_submission",
                lambda value: value["findings"][0].update(calculation_ids=[]),
            ),
            (
                "final",
                "final_submission",
                lambda value: value["claims"][0].update(calculation_ids=["MISSING"]),
            ),
            (
                "final",
                "final_submission",
                lambda value: value["calculations"][0].update(reported_value=0.999),
            ),
            (
                "final",
                "final_submission",
                lambda value: value["calculations"][0].update(estimator="ROW_EMPIRICAL"),
            ),
            (
                "final",
                "final_submission",
                lambda value: value["claims"][0].update(
                    status="SUPPORTED", scope="CLINICAL_UTILITY"
                ),
            ),
        ]
        for index, (kind, key, mutate) in enumerate(mutations):
            candidate = copy.deepcopy(submission[key])
            mutate(candidate)
            path = workspace / "work" / f"negative_{index}.json"
            path.write_text(json.dumps(candidate, indent=2, sort_keys=True) + "\n")
            result = _local_contract_check(workspace, kind, path)
            assert result.returncode != 0, f"mutation {index} passed: {result.stdout}"


def test_total_schema_facades_reject_malformed_nested_members_without_crashing() -> None:
    assert not validate_validation_plan(
        {"schema_version": "mmmvp-open-case1-rc1-7", "decision_criteria": [1]}
    ).valid
    assert not validate_followup_plan(
        {"schema_version": "mmmvp-open-case1-rc1-7", "result_contingencies": [1]}
    ).valid
    assert not validate_final_submission(
        {"schema_version": "mmmvp-open-case1-rc1-7", "calculations": [1]}
    ).valid


def test_environment_returns_recoverable_feedback_for_malformed_nested_records() -> None:
    with tempfile.TemporaryDirectory(prefix="rc5-total-actions-") as directory:
        environment = RC5Case1Environment(ROOT, "case_01", Path(directory) / "workspace")
        validation = environment.commit_validation_plan(
            json.dumps(
                {
                    "schema_version": "mmmvp-open-case1-rc1-7",
                    "decision_criteria": [1],
                }
            )
        )
        assert validation["accepted"] is False
        assert validation["schema_issues"]

        environment.state.phase = "revealed"
        followup = environment.commit_followup_plan(
            json.dumps(
                {
                    "schema_version": "mmmvp-open-case1-rc1-7",
                    "result_contingencies": [1],
                }
            )
        )
        assert followup["accepted"] is False
        assert followup["schema_issues"]

        environment.state.phase = "purchased"
        final = environment.submit(
            json.dumps(
                {
                    "schema_version": "mmmvp-open-case1-rc1-7",
                    "calculations": [1],
                }
            )
        )
        assert final["accepted"] is False
        assert final["schema_issues"]


def test_environment_handles_recursive_json_without_crashing() -> None:
    with tempfile.TemporaryDirectory(prefix="rc5-recursive-json-") as directory:
        environment = RC5Case1Environment(ROOT, "case_01", Path(directory) / "workspace")
        result = environment.commit_validation_plan("[" * 2000 + "0" + "]" * 2000)
        assert result["accepted"] is False
        assert result["schema_issues"]


@pytest.mark.parametrize("as_list", [False, True])
def test_resource_hash_forms_normalize_identically(as_list: bool) -> None:
    mapping = {"p/a.csv": "0" * 64, "p/b.csv": "1" * 64}
    value: object = (
        [{"path": key, "sha256": digest} for key, digest in reversed(mapping.items())]
        if as_list
        else mapping
    )
    assert normalize_source_hashes(value) == dict(sorted(mapping.items()))


@pytest.mark.parametrize(
    "value",
    [
        {"": "0" * 64},
        {"p": "A" * 64},
        [{"path": "p", "sha256": "0" * 64}, {"path": "p", "sha256": "1" * 64}],
        [{"path": "p"}],
    ],
)
def test_malformed_or_duplicate_resource_hashes_fail(value: object) -> None:
    with pytest.raises(NormalizationError):
        normalize_source_hashes(value)


def _write_submission_mirrors(workspace: Path, submission: dict[str, object]) -> None:
    for name in ("validation_plan", "followup_plan", "final_submission"):
        (workspace / "work" / f"{name}.json").write_text(
            json.dumps(submission[name], indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )


def _local_contract_check(
    workspace: Path, kind: str, path: Path
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, (workspace / "validate_contract.py").as_posix(), kind, path.as_posix()],
        check=False,
        capture_output=True,
        text=True,
    )


def test_agent_visible_validator_accepts_both_disclosed_hash_forms() -> None:
    with tempfile.TemporaryDirectory(prefix="rc5-validator-") as directory:
        submission, workspace = build_reference(ROOT, Path(directory) / "workspace")
        _write_submission_mirrors(workspace, submission)
        original = json.loads((workspace / "work/resource_summary.json").read_text())
        normalized = normalize_source_hashes(original["source_hashes"])
        for name, hashes in (
            ("mapping", normalized),
            (
                "list",
                [{"path": path, "sha256": digest} for path, digest in normalized.items()],
            ),
        ):
            candidate = copy.deepcopy(original)
            candidate["source_hashes"] = hashes
            path = workspace / "work" / f"resource_summary_{name}.json"
            path.write_text(json.dumps(candidate, indent=2, sort_keys=True) + "\n")
            result = subprocess.run(
                [
                    sys.executable,
                    (workspace / "validate_saved_artifact.py").as_posix(),
                    path.as_posix(),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, result.stdout + result.stderr


def test_agent_visible_validators_have_no_third_party_runtime_dependency() -> None:
    source = (ROOT / "src/uc_bench/case1_pilot_v1_rc5_public_recompute.py").read_text(
        encoding="utf-8"
    )
    assert "sklearn" not in source
    with tempfile.TemporaryDirectory(prefix="rc5-stdlib-validator-") as directory:
        submission, workspace = build_reference(ROOT, Path(directory) / "workspace")
        _write_submission_mirrors(workspace, submission)
        interpreter = Path("/usr/bin/python3")
        if interpreter.is_file():
            result = subprocess.run(
                [
                    interpreter.as_posix(),
                    (workspace / "validate_contract.py").as_posix(),
                    "validation",
                    (workspace / "work/validation_plan.json").as_posix(),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, result.stdout + result.stderr
            final = subprocess.run(
                [
                    interpreter.as_posix(),
                    (workspace / "validate_contract.py").as_posix(),
                    "final",
                    (workspace / "work/final_submission.json").as_posix(),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            assert final.returncode == 0, final.stdout + final.stderr


def test_public_recomputation_uses_committed_manifest_and_post_reveal_binding() -> None:
    source = (ROOT / "src/uc_bench/case1_pilot_v1_rc5_public_recompute.py").read_text(
        encoding="utf-8"
    )
    assert "validation_outcomes.csv" not in source
    with tempfile.TemporaryDirectory(prefix="rc5-symbolic-binding-") as directory:
        submission, workspace = build_reference(ROOT, Path(directory) / "reference")
        copied, target = _copy_episode(submission, workspace, Path(directory) / "renamed-manifest")
        original = target / "work/eligible_entities.csv"
        renamed = target / "work/cohort_commit.csv"
        original.rename(renamed)
        plan = copied["validation_plan"]
        plan["prospective_specification"]["eligible_entity_manifest_path"] = (
            "work/cohort_commit.csv"
        )
        plan["prospective_specification"]["eligible_entity_manifest_sha256"] = hashlib.sha256(
            renamed.read_bytes()
        ).hexdigest()
        records = target.parent / ".mmmvp_host_records" / target.name
        (records / "validation_plan.json").write_text(
            json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (target / "work/validation_plan.json").write_text(
            json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        inputs = json.loads((records / "validation_input_hashes.json").read_text())
        inputs["work/cohort_commit.csv"] = inputs.pop("work/eligible_entities.csv")
        (records / "validation_input_hashes.json").write_text(
            json.dumps(inputs, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        plan_hash = hashlib.sha256(
            json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        copied["validation_input_hashes"] = inputs
        copied["state"]["validation_plan_hash"] = plan_hash
        next(row for row in copied["event_log"] if row["event"] == "commit_validation_plan")[
            "digest"
        ] = plan_hash
        next(row for row in copied["event_log"] if row["event"] == "reveal_validation")[
            "committed_plan_hash"
        ] = plan_hash
        _write_submission_mirrors(target, copied)
        local = _local_contract_check(target, "final", target / "work/final_submission.json")
        assert local.returncode == 0, local.stdout + local.stderr
        assert _grade(ROOT, copied, target)["complete_mission_success"]


def test_untouched_templates_are_not_action_ready() -> None:
    with tempfile.TemporaryDirectory(prefix="rc5-template-validator-") as directory:
        workspace = Path(directory) / "workspace"
        RC5Case1Environment(ROOT, "case_01", workspace)
        validation = _local_contract_check(
            workspace,
            "validation",
            workspace / "contract_templates/validation_plan_template.json",
        )
        followup = _local_contract_check(
            workspace,
            "followup",
            workspace / "contract_templates/followup_plan_template.json",
        )
        transport = _local_contract_check(
            workspace,
            "followup",
            workspace / "contract_templates/followup_plan_transport_template.json",
        )
        final = _local_contract_check(
            workspace,
            "final",
            workspace / "contract_templates/final_submission_template.json",
        )
        assert validation.returncode != 0
        assert followup.returncode != 0
        assert transport.returncode != 0
        assert final.returncode != 0


def test_exact_rc4_trajectory_replays_as_123_person_general_cohort() -> None:
    submission, workspace = _rc4_fixture(ROOT)
    grade = _grade(ROOT, submission, workspace)
    cohort = reconstruct_committed_cohort(
        workspace,
        submission["validation_plan"],
        host_input_hashes=submission["validation_input_hashes"],
    )
    assert grade["complete_mission_success"]
    assert grade["partial_scientific_quality"] == 100.0
    assert cohort.valid
    assert len(cohort.universe) == 124
    assert len(cohort.included_entities) == 123
    assert len(cohort.excluded_entities) == 1


def test_manifest_column_order_is_not_an_arbitrary_trap() -> None:
    submission, workspace = _rc4_fixture(ROOT)
    with tempfile.TemporaryDirectory(prefix="rc5-column-order-") as directory:
        copied, target = _copy_episode(submission, workspace, Path(directory) / "episode")
        path = target / "work/eligible_entities.csv"
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        fields = ["included", "entity_id", "preoutcome_exclusion_reason", "source_record_ids"]
        _write_csv(path, rows, fields)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        copied["validation_plan"]["prospective_specification"][
            "eligible_entity_manifest_sha256"
        ] = digest
        records = target.parent / ".mmmvp_host_records" / target.name
        (records / "validation_plan.json").write_text(
            json.dumps(copied["validation_plan"], indent=2, sort_keys=True) + "\n"
        )
        inputs = json.loads((records / "validation_input_hashes.json").read_text())
        inputs["work/eligible_entities.csv"] = digest
        (records / "validation_input_hashes.json").write_text(
            json.dumps(inputs, indent=2, sort_keys=True) + "\n"
        )
        copied["validation_input_hashes"] = inputs
        plan_hash = hashlib.sha256(
            json.dumps(copied["validation_plan"], sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        copied["state"]["validation_plan_hash"] = plan_hash
        next(row for row in copied["event_log"] if row["event"] == "commit_validation_plan")[
            "digest"
        ] = plan_hash
        next(row for row in copied["event_log"] if row["event"] == "reveal_validation")[
            "committed_plan_hash"
        ] = plan_hash
        assert _grade(ROOT, copied, target)["complete_mission_success"]


def test_two_materially_different_valid_primary_workflows_pass() -> None:
    with tempfile.TemporaryDirectory(prefix="rc5-alternatives-") as directory:
        entity, ew = build_reference(ROOT, Path(directory) / "entity", aggregation="MEAN")
        cluster, cw = build_reference(ROOT, Path(directory) / "cluster", aggregation="NONE")
        median, mw = build_reference(ROOT, Path(directory) / "median", aggregation="MEDIAN")
        assert _grade(ROOT, entity, ew)["complete_mission_success"]
        assert _grade(ROOT, cluster, cw)["complete_mission_success"]
        assert _grade(ROOT, median, mw)["complete_mission_success"]


def test_resource_faults_do_not_erase_verified_primary_properties() -> None:
    submission, workspace = _rc4_fixture(ROOT)
    with tempfile.TemporaryDirectory(prefix="rc5-local-grade-") as directory:
        copied, target = _copy_episode(submission, workspace, Path(directory) / "episode")
        path = target / "work/resource_summary.json"
        path.write_text("{}\n", encoding="utf-8")
        final = copy.deepcopy(copied["final_submission"])
        _rehash_final_path(final, target, "work/resource_summary.json")
        _replace_final(copied, target, final)
        grade = _grade(ROOT, copied, target)
    status = {row["requirement_id"]: row["passed"] for row in grade["requirements"]}
    for identifier in (
        "committed_entity_and_dependence_analysis",
        "discrimination_and_uncertainty",
        "probability_and_calibration",
        "threshold_utility",
        "context_robustness",
    ):
        assert status[identifier]
    assert not status["decision_relevant_followup"]
    assert not status["bounded_decision_and_claims"]


def test_deep_resource_summary_failure_stays_local_to_resource_dependencies() -> None:
    submission, workspace = _rc4_fixture(ROOT)
    with tempfile.TemporaryDirectory(prefix="rc5-deep-resource-") as directory:
        copied, target = _copy_episode(submission, workspace, Path(directory) / "episode")
        path = target / "work/resource_summary.json"
        path.write_text("[" * 1_400 + "0" + "]" * 1_400, encoding="utf-8")
        final = copy.deepcopy(copied["final_submission"])
        _rehash_final_path(final, target, "work/resource_summary.json")
        _replace_final(copied, target, final)
        grade = _grade(ROOT, copied, target)
    status = {row["requirement_id"]: row["passed"] for row in grade["requirements"]}
    for identifier in (
        "saved_artifact_chain",
        "committed_entity_and_dependence_analysis",
        "discrimination_and_uncertainty",
        "probability_and_calibration",
        "threshold_utility",
        "context_robustness",
    ):
        assert status[identifier]
    assert not status["decision_relevant_followup"]
    assert not status["belief_revision"]
    assert not status["bounded_decision_and_claims"]


def test_unmanifested_malformed_optional_file_cannot_fail_mission() -> None:
    submission, workspace = _rc4_fixture(ROOT)
    with tempfile.TemporaryDirectory(prefix="rc5-optional-") as directory:
        copied, target = _copy_episode(submission, workspace, Path(directory) / "episode")
        (target / "work/optional_notes.json").write_text("{malformed", encoding="utf-8")
        assert _grade(ROOT, copied, target)["complete_mission_success"]


def test_manifested_but_decision_unlinked_optional_table_cannot_fail_mission() -> None:
    with tempfile.TemporaryDirectory(prefix="rc5-manifested-optional-") as directory:
        copied, target = build_reference(ROOT, Path(directory) / "episode")
        optional = target / "work/optional_analysis.csv"
        optional.write_text("not,the,declared,columns\n1,2,3,4\n", encoding="utf-8")
        final = copy.deepcopy(copied["final_submission"])
        final["artifact_manifest"].append(
            {
                "artifact_id": "A_OPTIONAL_MALFORMED",
                "path": "work/optional_analysis.csv",
                "role": "ANALYSIS_TABLE",
                "sha256": hashlib.sha256(optional.read_bytes()).hexdigest(),
                "source_paths": ["data/locked_predictions.csv"],
                "analysis_structure": "ENTITY_AGGREGATED",
                "aggregation": "MEAN",
                "column_map": {
                    "entity_id": "entity_id",
                    "source_record_ids": "source_record_ids",
                    "prediction": "prediction",
                    "outcome": "outcome",
                    "split": "split",
                },
            }
        )
        _replace_final(copied, target, final)
        _write_submission_mirrors(target, copied)
        local = _local_contract_check(target, "final", target / "work/final_submission.json")
        assert local.returncode == 0, local.stdout + local.stderr
        assert _grade(ROOT, copied, target)["complete_mission_success"]


def test_uncited_optional_calculation_and_malformed_table_cannot_fail_mission() -> None:
    with tempfile.TemporaryDirectory(prefix="rc5-uncited-optional-") as directory:
        copied, target = build_reference(ROOT, Path(directory) / "episode")
        optional = target / "work/optional_analysis.csv"
        optional.write_text("not,the,declared,columns\n1,2,3,4\n", encoding="utf-8")
        final = copy.deepcopy(copied["final_submission"])
        final["artifact_manifest"].append(
            {
                "artifact_id": "A_OPTIONAL_MALFORMED",
                "path": "work/optional_analysis.csv",
                "role": "ANALYSIS_TABLE",
                "sha256": hashlib.sha256(optional.read_bytes()).hexdigest(),
                "source_paths": ["data/locked_predictions.csv"],
                "analysis_structure": "ENTITY_AGGREGATED",
                "aggregation": "MEAN",
                "column_map": {
                    "entity_id": "entity_id",
                    "source_record_ids": "source_record_ids",
                    "prediction": "prediction",
                    "outcome": "outcome",
                    "split": "split",
                },
            }
        )
        diagnostic = copy.deepcopy(final["calculations"][0])
        diagnostic.update(
            {
                "calculation_id": "C_OPTIONAL_UNCITED",
                "role": "FOLLOWUP",
                "source_analysis_table_id": "A_OPTIONAL_MALFORMED",
            }
        )
        final["calculations"].append(diagnostic)
        _replace_final(copied, target, final)
        _write_submission_mirrors(target, copied)
        local = _local_contract_check(target, "final", target / "work/final_submission.json")
        assert local.returncode == 0, local.stdout + local.stderr
        assert _grade(ROOT, copied, target)["complete_mission_success"]


def test_no_purchase_requires_evaluable_primary_evidence() -> None:
    with tempfile.TemporaryDirectory(prefix="rc5-none-evaluable-") as directory:
        copied, target = build_reference(
            ROOT, Path(directory) / "episode", resource="none", exclude_pending=True
        )
        final = copy.deepcopy(copied["final_submission"])
        primary = next(row for row in final["calculations"] if row["role"] == "PRIMARY")
        primary["reported_value"] = float(primary["reported_value"]) + 0.1
        _replace_final(copied, target, final)
        _write_submission_mirrors(target, copied)
        local = _local_contract_check(target, "final", target / "work/final_submission.json")
        assert local.returncode != 0
        grade = _grade(ROOT, copied, target)
        status = {row["requirement_id"]: row["passed"] for row in grade["requirements"]}
        assert not status["decision_relevant_followup"]
        assert not grade["complete_mission_success"]


def test_x31_replay_respects_the_committed_exclusion_cohort() -> None:
    with tempfile.TemporaryDirectory(prefix="rc5-x31-cohort-") as directory:
        copied, target = build_reference(
            ROOT, Path(directory) / "episode", resource="X31", exclude_pending=True
        )
        final = copied["final_submission"]
        resource_calculation = next(
            row for row in final["calculations"] if row["role"] == "FOLLOWUP"
        )
        resource_artifact = next(
            row
            for row in final["artifact_manifest"]
            if row["artifact_id"] == resource_calculation["source_analysis_table_id"]
        )
        with (target / resource_artifact["path"]).open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        assert len(rows) == 123
        assert "F0001" not in {row["unit"] for row in rows}
        _write_submission_mirrors(target, copied)
        local = _local_contract_check(target, "final", target / "work/final_submission.json")
        # X31 is not a relevant purchase for the unaltered Case-1 evidence, so
        # the complete mission properly fails on resource selection. The saved
        # evidence chain itself must nevertheless validate against the 123-person
        # committed cohort.
        assert local.returncode != 0
        baseline_grade = _grade(ROOT, copied, target)
        baseline_status = {
            row["requirement_id"]: row["passed"] for row in baseline_grade["requirements"]
        }
        assert baseline_status["saved_artifact_chain"]
        assert baseline_status["committed_entity_and_dependence_analysis"]
        assert not baseline_status["decision_relevant_followup"]

        attacked = copy.deepcopy(copied)
        replay_row = next(
            row
            for row in csv.DictReader(
                (target / "purchased/X31/replay_predictions.csv").open(encoding="utf-8")
            )
            if row["patient_key"] == "F0001"
        )
        outcome = next(
            row["week6_response"]
            for row in csv.DictReader(
                (target / "revealed/validation_outcomes.csv").open(encoding="utf-8")
            )
            if row["patient_key"] == "F0001"
        )
        rows.append(
            {
                "unit": "F0001",
                "records": "F0001",
                "score": replay_row["predicted_probability"],
                "label": outcome,
                "partition": "VALIDATION",
                "setting": replay_row.get("site", ""),
            }
        )
        _write_csv(target / resource_artifact["path"], rows)
        attacked_final = copy.deepcopy(attacked["final_submission"])
        _rehash_final_path(attacked_final, target, resource_artifact["path"])
        _replace_final(attacked, target, attacked_final)
        _write_submission_mirrors(target, attacked)
        local = _local_contract_check(target, "final", target / "work/final_submission.json")
        assert local.returncode != 0
        attacked_grade = _grade(ROOT, attacked, target)
        attacked_status = {
            row["requirement_id"]: row["passed"] for row in attacked_grade["requirements"]
        }
        assert not attacked_status["saved_artifact_chain"]
        # The primary cohort property remains independently valid; the failure
        # is localized to the altered follow-up artifact chain.
        assert attacked_status["committed_entity_and_dependence_analysis"]
        assert not attacked_grade["complete_mission_success"]


def test_supported_finding_cannot_cite_an_unverified_optional_calculation() -> None:
    with tempfile.TemporaryDirectory(prefix="rc5-finding-evidence-") as directory:
        copied, target = build_reference(ROOT, Path(directory) / "episode")
        optional = target / "work/optional_analysis.csv"
        optional.write_text("not,the,declared,columns\n1,2,3,4\n", encoding="utf-8")
        final = copy.deepcopy(copied["final_submission"])
        final["artifact_manifest"].append(
            {
                "artifact_id": "A_OPTIONAL_MALFORMED",
                "path": "work/optional_analysis.csv",
                "role": "ANALYSIS_TABLE",
                "sha256": hashlib.sha256(optional.read_bytes()).hexdigest(),
                "source_paths": ["data/locked_predictions.csv"],
                "analysis_structure": "ENTITY_AGGREGATED",
                "aggregation": "MEAN",
                "column_map": {
                    "entity_id": "entity_id",
                    "source_record_ids": "source_record_ids",
                    "prediction": "prediction",
                    "outcome": "outcome",
                    "split": "split",
                },
            }
        )
        diagnostic = copy.deepcopy(final["calculations"][0])
        diagnostic.update(
            {
                "calculation_id": "C_OPTIONAL_UNVERIFIED",
                "role": "DIAGNOSTIC",
                "source_analysis_table_id": "A_OPTIONAL_MALFORMED",
            }
        )
        final["calculations"].append(diagnostic)
        supported = next(row for row in final["findings"] if row["status"] == "SUPPORTED")
        supported["calculation_ids"] = ["C_OPTIONAL_UNVERIFIED"]
        _replace_final(copied, target, final)
        _write_submission_mirrors(target, copied)
        local = _local_contract_check(target, "final", target / "work/final_submission.json")
        assert local.returncode != 0
        assert not _grade(ROOT, copied, target)["complete_mission_success"]


def test_public_validator_accepts_valid_single_source_followup_table() -> None:
    with tempfile.TemporaryDirectory(prefix="rc5-x46-") as directory:
        submission, workspace = build_reference(ROOT, Path(directory) / "reference", resource="X46")
        _write_submission_mirrors(workspace, submission)
        local = _local_contract_check(workspace, "final", workspace / "work/final_submission.json")
        assert local.returncode == 0, local.stdout + local.stderr
        assert _grade(ROOT, submission, workspace)["complete_mission_success"]


def test_copied_primary_table_cannot_masquerade_as_followup_evidence() -> None:
    with tempfile.TemporaryDirectory(prefix="rc5-copied-followup-") as directory:
        submission, workspace = build_reference(ROOT, Path(directory) / "reference", resource="X46")
        final = copy.deepcopy(submission["final_submission"])
        followup = next(row for row in final["calculations"] if row["role"] == "FOLLOWUP")
        followup_artifact = next(
            row
            for row in final["artifact_manifest"]
            if row["artifact_id"] == followup["source_analysis_table_id"]
        )
        primary = next(row for row in final["calculations"] if row["role"] == "PRIMARY")
        primary_artifact = next(
            row
            for row in final["artifact_manifest"]
            if row["artifact_id"] == primary["source_analysis_table_id"]
        )
        destination = workspace / followup_artifact["path"]
        destination.write_bytes((workspace / primary_artifact["path"]).read_bytes())
        followup_artifact["sha256"] = hashlib.sha256(destination.read_bytes()).hexdigest()
        _replace_final(submission, workspace, final)
        _write_submission_mirrors(workspace, submission)
        local = _local_contract_check(workspace, "final", workspace / "work/final_submission.json")
        assert local.returncode != 0
        assert not _grade(ROOT, submission, workspace)["complete_mission_success"]


def test_professional_prose_paraphrase_does_not_change_score() -> None:
    submission, workspace = _rc4_fixture(ROOT)
    with tempfile.TemporaryDirectory(prefix="rc5-prose-") as directory:
        copied, target = _copy_episode(submission, workspace, Path(directory) / "episode")
        final = copy.deepcopy(copied["final_submission"])
        final["narrative_summary"] = "Independent professional wording."
        final["decision"]["allowed_use"] = ["Exploratory research ranking only."]
        final["decision"]["prohibited_use"] = ["No individual treatment decisions."]
        final["decision"]["unresolved_gates"] = ["External generalisation remains unknown."]
        final["decision"]["required_next_evidence"] = ["A prospectively blinded replication."]
        _replace_final(copied, target, final)
        assert _grade(ROOT, copied, target)["complete_mission_success"]


def test_generic_decision_policy_and_hard_coded_values_fail() -> None:
    submission, workspace = _rc4_fixture(ROOT)
    with tempfile.TemporaryDirectory(prefix="rc5-generic-") as directory:
        copied, target = _copy_episode(submission, workspace, Path(directory) / "decision")
        final = copy.deepcopy(copied["final_submission"])
        final["decision"].update(
            {"development_stage": "STOPPED", "disposition": "STOP", "use_scope": "NO_USE"}
        )
        _replace_final(copied, target, final)
        assert not _grade(ROOT, copied, target)["complete_mission_success"]

        copied, target = _copy_episode(submission, workspace, Path(directory) / "numbers")
        final = copy.deepcopy(copied["final_submission"])
        final["calculations"][0]["reported_value"] = 0.999
        _replace_final(copied, target, final)
        assert not _grade(ROOT, copied, target)["complete_mission_success"]


def test_full_action_record_and_contingency_commitment_are_enforced() -> None:
    submission, workspace = _rc4_fixture(ROOT)
    with tempfile.TemporaryDirectory(prefix="rc5-action-integrity-") as directory:
        copied, target = _copy_episode(submission, workspace, Path(directory) / "event")
        copied["event_log"] = [
            row
            for row in copied["event_log"]
            if row.get("event") not in {"commit_followup_plan", "purchase_resource", "submit"}
        ]
        assert not _grade(ROOT, copied, target)["complete_mission_success"]

        copied, target = _copy_episode(submission, workspace, Path(directory) / "contingency")
        final = copy.deepcopy(copied["final_submission"])
        for row in final["belief_updates"]:
            row["matched_contingency_id"] = "K_LIMIT"
        _replace_final(copied, target, final)
        grade = _grade(ROOT, copied, target)
        status = {row["requirement_id"]: row["passed"] for row in grade["requirements"]}
        assert not grade["complete_mission_success"]
        assert not status["belief_revision"]
        assert not status["bounded_decision_and_claims"]


def test_followup_contingencies_are_scored_against_observed_evidence_not_decorative() -> None:
    with tempfile.TemporaryDirectory(prefix="rc5-contingency-evidence-") as directory:
        submission, workspace = build_reference(ROOT, Path(directory) / "reference")
        copied, target = _copy_episode(submission, workspace, Path(directory) / "wrong-contingency")
        final = copy.deepcopy(copied["final_submission"])
        selected_id = final["belief_updates"][0]["matched_contingency_id"]
        followup = copy.deepcopy(copied["followup_plan"])
        selected = next(
            row for row in followup["result_contingencies"] if row["contingency_id"] == selected_id
        )
        for update in selected["hypothesis_updates"]:
            update["direction"] = "UNCHANGED"
        for update in final["belief_updates"]:
            update["after"] = update["before"]
        _synchronize_followup_commit(copied, target, followup)
        _replace_final(copied, target, final)
        grade = _grade(ROOT, copied, target)
        status = {row["requirement_id"]: row["passed"] for row in grade["requirements"]}
        assert not grade["complete_mission_success"]
        assert not status["belief_revision"]


def test_material_resolution_rejects_belief_changes_in_the_wrong_direction() -> None:
    validation = {
        "hypotheses": [
            {"hypothesis_id": "H_SUPPORT", "belief": 0.5, "decision_effect_if_true": "SUPPORTS"},
            {"hypothesis_id": "H_WEAKEN", "belief": 0.5, "decision_effect_if_true": "WEAKENS"},
            {"hypothesis_id": "H_NONE", "belief": 0.5, "decision_effect_if_true": "NONE"},
        ]
    }
    followup = {
        "beliefs_before": {"H_SUPPORT": 0.5, "H_WEAKEN": 0.5, "H_NONE": 0.5},
        "result_contingencies": [
            {
                "contingency_id": "K_RESOLVED",
                "hypothesis_updates": [
                    {"hypothesis_id": "H_SUPPORT", "direction": "DECREASE"},
                    {"hypothesis_id": "H_WEAKEN", "direction": "INCREASE"},
                    {"hypothesis_id": "H_NONE", "direction": "UNCHANGED"},
                ],
            }
        ],
    }
    final = {
        "belief_updates": [
            {
                "hypothesis_id": "H_SUPPORT",
                "before": 0.5,
                "after": 0.4,
                "matched_contingency_id": "K_RESOLVED",
            },
            {
                "hypothesis_id": "H_WEAKEN",
                "before": 0.5,
                "after": 0.6,
                "matched_contingency_id": "K_RESOLVED",
            },
            {
                "hypothesis_id": "H_NONE",
                "before": 0.5,
                "after": 0.5,
                "matched_contingency_id": "K_RESOLVED",
            },
        ]
    }
    errors = belief_revision_errors(validation, followup, final, "RESOLVES")
    assert "belief revision direction contradicts verified evidence" in errors


def test_universal_action_and_resource_policies_do_not_pass_automatically() -> None:
    with tempfile.TemporaryDirectory(prefix="rc5-universal-policies-") as directory:
        supportive, supportive_workspace = build_reference(
            ROOT, Path(directory) / "supportive", resource="X24", exclude_pending=False
        )
        for disposition, stage, scope in (
            ("PAUSE", "INTERNAL_VALIDATION", "RESEARCH_PROBABILITY"),
            ("STOP", "STOPPED", "NO_USE"),
            ("INSUFFICIENT_EVIDENCE", "INTERNAL_VALIDATION", "RESEARCH_RANKING"),
        ):
            copied, target = _copy_episode(
                supportive,
                supportive_workspace,
                Path(directory) / f"always-{disposition.lower()}",
            )
            final = copy.deepcopy(copied["final_submission"])
            final["decision"].update(
                {
                    "development_stage": stage,
                    "disposition": disposition,
                    "use_scope": scope,
                }
            )
            _replace_final(copied, target, final)
            assert not _grade(ROOT, copied, target)["complete_mission_success"]

        blocking, blocking_workspace = build_reference(
            ROOT, Path(directory) / "blocking", resource="X46", exclude_pending=True
        )
        copied, target = _copy_episode(
            blocking, blocking_workspace, Path(directory) / "always-continue"
        )
        final = copy.deepcopy(copied["final_submission"])
        final["decision"].update(
            {
                "development_stage": "INTERNAL_VALIDATION",
                "disposition": "CONTINUE",
                "use_scope": "RESEARCH_PROBABILITY",
            }
        )
        _replace_final(copied, target, final)
        assert not _grade(ROOT, copied, target)["complete_mission_success"]

        no_purchase, no_purchase_workspace = build_reference(
            ROOT, Path(directory) / "always-none", resource="none", exclude_pending=False
        )
        assert not _grade(ROOT, no_purchase, no_purchase_workspace)["complete_mission_success"]

        unnecessary, unnecessary_workspace = build_reference(
            ROOT, Path(directory) / "always-buy", resource="X24", exclude_pending=True
        )
        assert not _grade(ROOT, unnecessary, unnecessary_workspace)["complete_mission_success"]


def test_resource_relevance_uses_included_preoutcome_uncertainty() -> None:
    with tempfile.TemporaryDirectory(prefix="rc5-resource-relevance-") as directory:
        useful, useful_workspace = build_reference(
            ROOT, Path(directory) / "useful", resource="X24", exclude_pending=False
        )
        unnecessary, unnecessary_workspace = build_reference(
            ROOT, Path(directory) / "unnecessary", resource="X24", exclude_pending=True
        )
        unresolved_none, unresolved_none_workspace = build_reference(
            ROOT, Path(directory) / "unresolved_none", resource="none", exclude_pending=False
        )
        assert _grade(ROOT, useful, useful_workspace)["complete_mission_success"]
        assert not _grade(ROOT, unnecessary, unnecessary_workspace)["complete_mission_success"]
        assert not _grade(ROOT, unresolved_none, unresolved_none_workspace)[
            "complete_mission_success"
        ]


def test_no_purchase_can_validly_contain_a_decisive_negative_result() -> None:
    with tempfile.TemporaryDirectory(prefix="rc5-negative-none-") as directory:
        submission, workspace = build_reference(
            ROOT, Path(directory) / "reference", resource="none", exclude_pending=True
        )
        plan = copy.deepcopy(submission["validation_plan"])
        discrimination = next(
            row for row in plan["decision_criteria"] if row["property"] == "DISCRIMINATION"
        )
        discrimination["threshold"] = 0.90
        with (workspace / "work/eligible_entities.csv").open(
            encoding="utf-8", newline=""
        ) as handle:
            manifest_rows = list(csv.DictReader(handle))
        submission["validation_plan"] = plan
        _synchronize_manifest_commit(submission, workspace, manifest_rows)

        followup = copy.deepcopy(submission["followup_plan"])
        selected_id = submission["final_submission"]["belief_updates"][0]["matched_contingency_id"]
        selected = next(
            row for row in followup["result_contingencies"] if row["contingency_id"] == selected_id
        )
        selected["next_decision"].update(
            {
                "development_stage": "INTERNAL_VALIDATION",
                "disposition": "PAUSE",
                "use_scope": "RESEARCH_PROBABILITY",
            }
        )
        _synchronize_followup_commit(submission, workspace, followup)

        final = copy.deepcopy(submission["final_submission"])
        final["decision"].update(selected["next_decision"])
        final["findings"].append(
            {
                "finding_id": "F_NEGATIVE_GATE",
                "statement": "The prospective discrimination criterion is not met.",
                "status": "SUPPORTED",
                "decision_effect": "WEAKENS",
                "evidence_refs": ["work/primary_results.json"],
                "calculation_ids": [discrimination["calculation_id"]],
            }
        )
        _replace_final(submission, workspace, final)
        _write_submission_mirrors(workspace, submission)
        grade = _grade(ROOT, submission, workspace)
        local = _local_contract_check(workspace, "final", workspace / "work/final_submission.json")
        assert local.returncode == 0, local.stdout + local.stderr
        assert grade["complete_mission_success"]


def test_no_purchase_requires_unchanged_numeric_beliefs() -> None:
    submission, workspace = _rc4_fixture(ROOT)
    with tempfile.TemporaryDirectory(prefix="rc5-none-belief-") as directory:
        copied, target = _copy_episode(submission, workspace, Path(directory) / "episode")
        final = copy.deepcopy(copied["final_submission"])
        for row in final["belief_updates"]:
            row["after"] = min(1.0, float(row["before"]) + 0.01)
        followup = copy.deepcopy(copied["followup_plan"])
        selected_id = final["belief_updates"][0]["matched_contingency_id"]
        selected = next(
            row for row in followup["result_contingencies"] if row["contingency_id"] == selected_id
        )
        for row in selected["hypothesis_updates"]:
            row["direction"] = "INCREASE"
        _synchronize_followup_commit(copied, target, followup)
        _replace_final(copied, target, final)
        grade = _grade(ROOT, copied, target)
        status = {row["requirement_id"]: row["passed"] for row in grade["requirements"]}
        assert not grade["complete_mission_success"]
        assert not status["belief_revision"]


def test_complete_control_suite_and_reporting_recovery() -> None:
    with tempfile.TemporaryDirectory(prefix="rc5-controls-") as directory:
        result = run_rc5_controls(ROOT, Path(directory))
    assert result["passed"]
    assert all(result["cohort_controls"]["attacks"].values())
    assert all(result["resource_controls"]["wrong_and_missing_hashes_fail"].values())
    assert result["interruption_restart_reporting_controls"]["passed"]


def test_authoritative_rc4_lifecycle_is_reconstructed_from_journal() -> None:
    run_root = (
        ROOT / "artifacts/uc_bench_case1_pilot_v1_rc4/science/runs/"
        "case1-rc4-00-openai-gpt-5-attempt-0"
    )
    lifecycle = reconstruct_lifecycle(run_root)
    submission = json.loads((run_root / "submission.json").read_text(encoding="utf-8"))
    assert lifecycle["tools_called"] == 52
    assert lifecycle["validation_revealed"]
    assert lifecycle["resource_purchased"] == "none"
    assert lifecycle["submission_accepted"]
    assert lifecycle["final_decision"] == submission["final_submission"]["decision"]
    assert lifecycle["completion_state"] == "submitted"
    assert lifecycle["reliability_score"] == 100.0
    assert lifecycle["budget_enforcement_spend_usd"] == 0.63544475


def test_corrupt_durable_journal_is_not_mislabeled_as_no_response() -> None:
    with tempfile.TemporaryDirectory(prefix="rc5-corrupt-journal-") as directory:
        root = Path(directory)
        journal = root / "host_trajectory/journal"
        journal.mkdir(parents=True)
        (journal / "000002.json").write_text(
            json.dumps({"sequence": 2, "environment": {}}) + "\n", encoding="utf-8"
        )
        (root / "request_ledger.json").write_text(
            json.dumps({"requests": [], "cumulative_reported_cost_usd": 0}) + "\n",
            encoding="utf-8",
        )
        with pytest.raises(CorruptTrajectoryError, match="sequence gap"):
            reconstruct_lifecycle(root)


def test_semantically_impossible_submit_only_journal_is_corrupt() -> None:
    with tempfile.TemporaryDirectory(prefix="rc5-semantic-journal-") as directory:
        root = Path(directory)
        journal = root / "host_trajectory/journal"
        journal.mkdir(parents=True)
        events = [{"event": "submit", "sequence": 1}]
        (journal / "000001.json").write_text(
            json.dumps(
                {
                    "sequence": 1,
                    "environment": {
                        "phase": "terminal",
                        "event_record": events,
                        "state": {
                            "phase": "terminal",
                            "terminal_reason": "submitted",
                            "completion_accepted": True,
                            "event_log": events,
                        },
                        "submission": {
                            "state": {"completion_accepted": True},
                            "final_submission": {"decision": {}},
                        },
                    },
                    "tool_actions": [],
                    "provider_exchanges": [],
                    "cumulative_cost_usd": 0,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (root / "request_ledger.json").write_text(
            json.dumps({"requests": [], "cumulative_reported_cost_usd": 0}) + "\n",
            encoding="utf-8",
        )
        with pytest.raises(CorruptTrajectoryError, match="begin with exactly one reset"):
            reconstruct_lifecycle(root)


@pytest.mark.parametrize(
    "ledger",
    [
        {"requests": [], "cumulative_reported_cost_usd": "free"},
        {"requests": "not-a-list", "cumulative_reported_cost_usd": 0},
        {"requests": [], "cumulative_reported_cost_usd": float("inf")},
    ],
)
def test_empty_trajectory_requires_a_well_typed_cost_ledger(ledger: dict[str, object]) -> None:
    with tempfile.TemporaryDirectory(prefix="rc5-empty-ledger-") as directory:
        root = Path(directory)
        (root / "request_ledger.json").write_text(json.dumps(ledger) + "\n", encoding="utf-8")
        with pytest.raises(CorruptTrajectoryError):
            reconstruct_lifecycle_or_empty(root)


@pytest.mark.parametrize(
    "summary, expected",
    [
        ({"classification": []}, "malformed_run_summary:classification"),
        ({"failure_subtype": []}, "malformed_run_summary:failure_subtype"),
        (
            {"agent_received_provider_credentials": []},
            "malformed_run_summary:agent_received_provider_credentials",
        ),
        ({"integrity": "bad"}, "malformed_run_summary:integrity"),
        ({"trajectory_replay": []}, "malformed_run_summary:trajectory_replay"),
        ({"grader_assessment": False}, "malformed_run_summary:grader_assessment"),
        ({"authoritative_lifecycle": "bad"}, "malformed_run_summary:authoritative_lifecycle"),
        ({"submission": []}, "malformed_run_summary:submission"),
        (
            {
                "authoritative_lifecycle": {"submission_accepted": False},
                "submission": {"state": "bad"},
            },
            "malformed_run_summary:submission.state",
        ),
        ({"provider_requests": 3}, "malformed_run_summary:provider_requests"),
    ],
)
def test_global_stop_adjudication_is_total_for_malformed_summaries(
    summary: dict[str, object], expected: str
) -> None:
    assert expected in rc5_execution.rc5_global_stop_faults(summary)


def test_provider_cell_adjudication_is_total_for_malformed_scalars() -> None:
    for summary in (
        {"classification": []},
        {"classification": "infrastructure_failure", "failure_subtype": []},
    ):
        assert rc5_execution.isolated_provider_cell(summary) is False


def test_unknown_nonempty_execution_classification_fails_closed() -> None:
    faults = rc5_execution.rc5_global_stop_faults(
        {
            "classification": "future_unreviewed_classification",
            "failure_subtype": None,
            "model_id": "example/model",
            "run_id": "run",
            "agent_received_provider_credentials": False,
            "integrity": {
                "start_state_untampered": True,
                "protected_evidence_untampered": True,
                "protected_evidence_mutation_attempted": False,
                "workspace_boundary_enforced": True,
            },
        }
    )
    assert "malformed_run_summary:unknown_classification" in faults


@pytest.mark.parametrize(
    "classification, expected",
    [
        ("shared_harness_failure", "shared_grader_or_harness_failure"),
        ("protected_evidence_tampering", "protected_evidence_mutation"),
    ],
)
def test_named_global_stop_classifications_cannot_escape_containment(
    classification: str, expected: str
) -> None:
    faults = rc5_execution.rc5_global_stop_faults(
        {
            "classification": classification,
            "failure_subtype": None,
            "model_id": "example/model",
            "run_id": "run",
            "agent_received_provider_credentials": False,
            "integrity": {
                "start_state_untampered": True,
                "protected_evidence_untampered": True,
                "protected_evidence_mutation_attempted": False,
                "workspace_boundary_enforced": True,
            },
        }
    )
    assert expected in faults


@pytest.mark.parametrize(
    "field, malformed, expected",
    [
        ("start_state_untampered", "false", "frozen_start_state_corruption"),
        ("protected_evidence_untampered", "false", "protected_evidence_mutation"),
        (
            "protected_evidence_mutation_attempted",
            "false",
            "protected_evidence_mutation_attempt",
        ),
        ("workspace_boundary_enforced", "false", "workspace_boundary_failure"),
    ],
)
def test_truthy_malformed_integrity_leaves_fail_closed(
    field: str, malformed: object, expected: str
) -> None:
    integrity = {
        "start_state_untampered": True,
        "protected_evidence_untampered": True,
        "protected_evidence_mutation_attempted": False,
        "workspace_boundary_enforced": True,
    }
    integrity[field] = malformed
    faults = rc5_execution.rc5_global_stop_faults(
        {
            "classification": "valid_episode",
            "model_id": "example/model",
            "run_id": "run",
            "agent_received_provider_credentials": False,
            "integrity": integrity,
            "trajectory_replay": {"status": "passed"},
            "grader_assessment": {"status": "passed"},
        }
    )
    assert expected in faults


@pytest.mark.parametrize("section", ["trajectory_replay", "grader_assessment"])
@pytest.mark.parametrize("status", [[], False, "fialed", None])
def test_malformed_replay_and_grader_statuses_fail_closed(
    section: str, status: object
) -> None:
    summary = {
        "classification": "valid_episode",
        "model_id": "example/model",
        "run_id": "run",
        "agent_received_provider_credentials": False,
        "integrity": {
            "start_state_untampered": True,
            "protected_evidence_untampered": True,
            "protected_evidence_mutation_attempted": False,
            "workspace_boundary_enforced": True,
        },
        "trajectory_replay": {"status": "passed"},
        "grader_assessment": {"status": "passed"},
    }
    summary[section] = {"status": status}
    assert (
        f"malformed_run_summary:{section}.status"
        in rc5_execution.rc5_global_stop_faults(summary)
    )


@pytest.mark.parametrize(
    "lifecycle, submission",
    [
        (None, None),
        ({"submission_accepted": False}, {"state": {"completion_accepted": False}}),
    ],
)
def test_valid_episode_requires_a_persisted_accepted_submission(
    lifecycle: object, submission: object
) -> None:
    summary = {
        "classification": "valid_episode",
        "model_id": "example/model",
        "run_id": "run",
        "agent_received_provider_credentials": False,
        "integrity": {
            "start_state_untampered": True,
            "protected_evidence_untampered": True,
            "protected_evidence_mutation_attempted": False,
            "workspace_boundary_enforced": True,
        },
        "trajectory_replay": {"status": "passed"},
        "grader_assessment": {"status": "passed"},
        "authoritative_lifecycle": lifecycle,
        "submission": submission,
    }
    faults = rc5_execution.rc5_global_stop_faults(summary)
    assert "authoritative_lifecycle_inconsistency" in faults
    if lifecycle is None:
        assert "malformed_run_summary:authoritative_lifecycle" in faults
    if submission is None:
        assert "malformed_run_summary:submission" in faults


def test_paid_cell_result_identity_is_checked_before_adoption() -> None:
    with tempfile.TemporaryDirectory(prefix="rc5-result-identity-") as directory:
        root = Path(directory)
        expected_run_id = "case1-rc5-00-openai-gpt-5-attempt-0"
        run_root = root / rc5_execution.RUNS_ROOT / expected_run_id
        run_root.mkdir(parents=True)
        persisted = {"model_id": "openai/gpt-5.1", "run_id": "stale-run"}
        summary_path = run_root / "run_summary.json"
        summary_path.write_text(json.dumps(persisted) + "\n", encoding="utf-8")
        result = type(
            "Result",
            (),
            {
                "run_root": run_root,
                "workspace_root": run_root / "workspace",
                "summary_path": summary_path,
                "request_ledger_path": run_root / "request_ledger.json",
                "summary": persisted,
            },
        )()
        faults = rc5_execution._cell_result_identity_faults(  # noqa: SLF001
            root,
            result=result,
            model_id="openai/gpt-5",
            run_id=expected_run_id,
        )
        assert "completed_cell_identity_mismatch" in faults
        assert "completed_cell_persisted_identity_mismatch" in faults


@pytest.mark.parametrize(
    "mutation",
    [
        lambda row: row.update(environment=[]),
        lambda row: row["environment"].update(state=[]),
        lambda row: row["environment"]["state"].update(event_log=""),
        lambda row: row.update(tool_actions=""),
        lambda row: row.update(provider_exchanges=""),
        lambda row: row.update(cumulative_cost_usd=None),
    ],
)
def test_falsey_wrong_trajectory_types_fail_closed(
    mutation: Callable[[dict[str, Any]], None],
) -> None:
    with tempfile.TemporaryDirectory(prefix="rc5-trajectory-types-") as directory:
        root = Path(directory)
        journal = root / "host_trajectory/journal"
        journal.mkdir(parents=True)
        record = {
            "sequence": 1,
            "environment": {
                "state": {
                    "event_log": [],
                    "completion_accepted": False,
                    "terminal_reason": None,
                },
                "submission": None,
            },
            "tool_actions": [],
            "provider_exchanges": [],
            "cumulative_cost_usd": 0.0,
        }
        mutation(record)
        (journal / "000001.json").write_text(json.dumps(record) + "\n", encoding="utf-8")
        (root / "request_ledger.json").write_text(
            json.dumps({"requests": [], "cumulative_reported_cost_usd": 0.0}) + "\n",
            encoding="utf-8",
        )
        with pytest.raises(CorruptTrajectoryError):
            reconstruct_lifecycle(root)


def test_inherited_module_contexts_share_lock_and_restore_after_exception() -> None:
    lock = rc5_controls_module.INHERITED_EXTENSION_LOCK
    assert rc5_preflight_module.INHERITED_EXTENSION_LOCK is lock
    assert rc5_runner_module.INHERITED_EXTENSION_LOCK is lock
    original_environment = legacy_controls.RC17OpenMMMVPEnvironment
    original_verifier = legacy_controls.verify_rc17_case1_submission
    with (
        pytest.raises(RuntimeError, match="deliberate"),
        rc5_controls_module._rc5_reference_builder(),  # noqa: SLF001
    ):
        raise RuntimeError("deliberate")
    assert legacy_controls.RC17OpenMMMVPEnvironment is original_environment
    assert legacy_controls.verify_rc17_case1_submission is original_verifier


def test_review_gate_rejects_unresolved_or_disguised_high_severity_findings() -> None:
    ready = {
        "passed": True,
        "verdict": "READY",
        "file_modifications": 0,
        "network_or_model_calls": 0,
        "findings": [],
    }
    historical = {
        "passed": False,
        "verdict": "NOT_READY",
        "file_modifications": 0,
        "network_or_model_calls": 0,
        "findings": [{"id": "H-1", "severity": "high"}],
    }
    resolved = {
        "passed": True,
        "dispositions": [{"finding_id": "H-1", "status": "resolved", "evidence": ["test"]}],
    }
    assert rc5_release.review_gate_valid(ready, ready, resolved, historical, ready)

    disguised = copy.deepcopy(ready)
    disguised["findings"] = [{"id": "NEW-HIGH", "severity": "high"}]
    assert not rc5_release.review_gate_valid(disguised, ready, resolved, historical, ready)

    accepted = copy.deepcopy(resolved)
    accepted["dispositions"][0]["status"] = "accepted_non_blocking"
    assert not rc5_release.review_gate_valid(ready, ready, accepted, historical, ready)

    misleading = copy.deepcopy(ready)
    misleading["verdict"] = "NOT_READY but contains READY"
    assert not rc5_release.review_gate_valid(misleading, ready, resolved, historical, ready)

    whitespace = copy.deepcopy(ready)
    whitespace["findings"] = [{"id": "NEW-LOW", "severity": " high "}]
    assert not rc5_release.review_gate_valid(whitespace, ready, resolved, historical, ready)


def test_freeze_rejects_caller_objects_that_differ_from_disk_attestations() -> None:
    with tempfile.TemporaryDirectory(prefix="rc5-freeze-input-") as directory:
        root = Path(directory)
        values = {
            rc5_release.CANDIDATE_PATH: {"candidate": "disk"},
            rc5_release.SELF_CONTAINMENT_PATH: {"passed": True},
            rc5_release.ZERO_COST_GATE_PATH: {"passed": True},
        }
        for relative, value in values.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(value) + "\n", encoding="utf-8")
        with pytest.raises(ConfigurationError, match="Caller candidate differs"):
            rc5_release.freeze_rc5(
                root,
                candidate={"candidate": "caller"},
                self_containment=values[rc5_release.SELF_CONTAINMENT_PATH],
                zero_cost_gate=values[rc5_release.ZERO_COST_GATE_PATH],
            )


def test_release_gate_uses_authoritative_json_roundtrip() -> None:
    scripts_path = str(Path(__file__).resolve().parents[1] / "scripts")
    sys.path.insert(0, scripts_path)
    try:
        from prepare_case1_pilot_v1_rc5 import write_attested_json
    finally:
        sys.path.remove(scripts_path)

    with tempfile.TemporaryDirectory(prefix="rc5-json-attestation-") as directory:
        path = Path(directory) / "gate.json"
        persisted = write_attested_json(
            path,
            {"passed": True, "diagnostic": {"values": ("A", "B")}},
        )
        assert persisted == json.loads(path.read_text(encoding="utf-8"))
        assert persisted["diagnostic"]["values"] == ["A", "B"]


def test_completed_cell_is_adopted_after_host_crash_without_rerunning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory(prefix="rc5-cell-transaction-") as directory:
        root = Path(directory)
        run_id = "case1-rc5-00-openai-gpt-5-attempt-0"
        summary_path = root / rc5_execution.RUNS_ROOT / run_id / "run_summary.json"
        summary_path.parent.mkdir(parents=True)
        summary = {
            "run_id": run_id,
            "model_id": "openai/gpt-5",
            "classification": "valid_episode",
            "integrity": {
                "start_state_untampered": True,
                "protected_evidence_untampered": True,
                "protected_evidence_mutation_attempted": False,
                "workspace_boundary_enforced": True,
            },
            "agent_received_provider_credentials": False,
            "trajectory_replay": {"status": "passed"},
            "grader_assessment": {"status": "passed"},
            "authoritative_lifecycle": {"submission_accepted": True},
            "submission": {"state": {"completion_accepted": True}},
        }
        summary_path.write_text(json.dumps(summary) + "\n", encoding="utf-8")
        state = {
            "execution_release_digest": "release-digest",
            "baseline_key_usage_usd": 10.0,
            "scientific_hard_cap_usd": 52.0,
            "completed_models": [],
            "excluded_models": [],
            "summary_paths": [],
            "global_stop_faults": [],
            "active_cell": {
                "model_id": "openai/gpt-5",
                "run_id": run_id,
                "release_digest": "release-digest",
            },
        }
        state_path = root / rc5_execution.STATE_PATH
        state_path.parent.mkdir(parents=True, exist_ok=True)
        _write_json(state_path, state, secret="test-secret")
        monkeypatch.setattr(
            rc5_execution,
            "funding_snapshot",
            lambda _key: {
                "key_usage_usd": 10.25,
                "effective_remaining_usd": 100.0,
            },
        )
        monkeypatch.setattr(rc5_execution, "credential_locations", lambda *_args: [])
        monkeypatch.setattr(
            rc5_execution,
            "read_rc5_freeze",
            lambda _root: {"closure": {"aggregate_digest": "release-digest"}},
        )
        monkeypatch.setattr(
            rc5_execution,
            "finalize_rc5_run_summary",
            lambda _run_root, *, key: summary,
        )
        assert rc5_execution._reconcile_active_cell(  # noqa: SLF001
            root, key="test-secret", state=state
        )
        persisted = json.loads(state_path.read_text(encoding="utf-8"))
        assert persisted["active_cell"] is None
        assert persisted["completed_models"] == ["openai/gpt-5"]
        assert persisted["scientific_spend_usd"] == 0.25
        assert persisted["summary_paths"] == [summary_path.relative_to(root).as_posix()]
        assert persisted["global_stop_faults"] == []


def test_corrupt_completed_cell_triggers_global_stop_on_reconcile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory(prefix="rc5-corrupt-cell-") as directory:
        root = Path(directory)
        run_id = "case1-rc5-00-openai-gpt-5-attempt-0"
        run_root = root / rc5_execution.RUNS_ROOT / run_id
        journal = run_root / "host_trajectory/journal"
        journal.mkdir(parents=True)
        (journal / "000002.json").write_text(
            json.dumps({"sequence": 2, "environment": {}}) + "\n", encoding="utf-8"
        )
        (run_root / "request_ledger.json").write_text(
            json.dumps({"requests": [], "cumulative_reported_cost_usd": 0}) + "\n",
            encoding="utf-8",
        )
        (run_root / "run_summary.json").write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "model_id": "openai/gpt-5",
                    "classification": "completed",
                    "integrity": {
                        "start_state_untampered": True,
                        "protected_evidence_untampered": True,
                        "protected_evidence_mutation_attempted": False,
                        "workspace_boundary_enforced": True,
                    },
                    "trajectory_replay": {"status": "passed"},
                    "grader_assessment": {"status": "passed"},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        state = {
            "execution_release_digest": "release-digest",
            "baseline_key_usage_usd": 10.0,
            "scientific_hard_cap_usd": 52.0,
            "completed_models": [],
            "excluded_models": [],
            "summary_paths": [],
            "global_stop_faults": [],
            "active_cell": {
                "model_id": "openai/gpt-5",
                "run_id": run_id,
                "release_digest": "release-digest",
            },
        }
        monkeypatch.setattr(
            rc5_execution,
            "funding_snapshot",
            lambda _key: {"key_usage_usd": 10.0, "effective_remaining_usd": 100.0},
        )
        monkeypatch.setattr(rc5_execution, "credential_locations", lambda *_args: [])
        monkeypatch.setattr(
            rc5_execution,
            "read_rc5_freeze",
            lambda _root: {"closure": {"aggregate_digest": "release-digest"}},
        )
        assert rc5_execution._reconcile_active_cell(  # noqa: SLF001
            root, key="test-secret", state=state
        )
        assert "durable_trajectory_corruption" in state["global_stop_faults"]
        assert state["status"] == "global_stop"


def test_crash_recovery_cannot_bypass_release_digest_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory(prefix="rc5-recovery-release-") as directory:
        root = Path(directory)
        state = {
            "execution_release_digest": "expected-release",
            "global_stop_faults": [],
            "active_cell": {
                "model_id": "openai/gpt-5",
                "run_id": "case1-rc5-00-openai-gpt-5-attempt-0",
                "release_digest": "stale-release",
            },
        }
        monkeypatch.setattr(
            rc5_execution,
            "read_rc5_freeze",
            lambda _root: {"closure": {"aggregate_digest": "expected-release"}},
        )
        assert not rc5_execution._reconcile_active_cell(  # noqa: SLF001
            root, key="test-secret", state=state
        )
        assert state["status"] == "global_stop"
        assert "recovery_release_digest_mismatch" in state["global_stop_faults"]


def test_stage_a_review_rejects_duplicate_property_adjudications(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory(prefix="rc5-stage-a-duplicates-") as directory:
        root = Path(directory)
        summary_relative = "artifacts/uc_bench_case1_pilot_v1_rc5/science/runs/run/summary.json"
        state_path = root / rc5_execution.STATE_PATH
        state_path.parent.mkdir(parents=True, exist_ok=True)
        _write_json(
            state_path,
            {
                "status": "stage_a_review_required",
                "global_stop_faults": [],
                "summary_paths": [summary_relative],
            },
            secret="test-secret",
        )
        monkeypatch.setattr(
            rc5_execution,
            "finalize_rc5_run_summary",
            lambda *_args, **_kwargs: {
                "classification": "agent_task_failure",
                "grader_assessment": {"status": "passed"},
                "authoritative_lifecycle": {"submission_accepted": False},
            },
        )
        identifiers = list(WEIGHTS)
        identifiers[-1] = identifiers[0]
        review = {
            "reviewed_summary_path": summary_relative,
            "raw_data_and_artifacts_inspected": True,
            "all_ten_properties_adjudicated": True,
            "evidence_chain_reconstructed": True,
            "replay_exact": True,
            "grader_deterministic": True,
            "no_hidden_contract_or_representation_failure": True,
            "construct_valid": True,
            "property_adjudications": [
                {
                    "requirement_id": identifier,
                    "classification": "not_evaluable",
                    "evidence_refs": ["evidence.json"],
                }
                for identifier in identifiers
            ],
        }
        with pytest.raises(ConfigurationError, match="every unique scientific property"):
            rc5_execution.approve_stage_a_review(root, key="test-secret", forensic_review=review)
        review["property_adjudications"] = [
            {
                "requirement_id": identifier,
                "classification": "not_evaluable",
                "evidence_refs": ["evidence.json"],
            }
            for identifier in WEIGHTS
        ]
        review["construct_valid"] = "false"
        with pytest.raises(ConfigurationError, match="incomplete or not construct-valid"):
            rc5_execution.approve_stage_a_review(root, key="test-secret", forensic_review=review)


def test_frozen_gate_attestations_are_revalidated_on_every_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory(prefix="rc5-attestations-") as directory:
        root = Path(directory)
        for relative in rc5_release.ATTESTED_GATE_PATHS:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}\n", encoding="utf-8")
        attestation_hashes = {
            relative.as_posix(): hashlib.sha256((root / relative).read_bytes()).hexdigest()
            for relative in rc5_release.ATTESTED_GATE_PATHS
        }
        freeze_path = root / rc5_release.FREEZE_PATH
        freeze_path.parent.mkdir(parents=True, exist_ok=True)
        freeze_path.write_text(
            json.dumps(
                {
                    "schema_version": "uc-bench-case1-pilot-v1-rc5-freeze-1",
                    "release_id": rc5_release.RELEASE_ID,
                    "status": "frozen_pre_science",
                    "frozen_at": "2026-09-11T00:00:00+00:00",
                    "closure": {
                        "hashes": {},
                        "aggregate_digest": canonical_sha256({}),
                    },
                    "attestation_hashes": attestation_hashes,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(rc5_release, "declared_rc5_hashes", lambda _root: {})
        monkeypatch.setattr(rc5_release, "rc4_artifacts_unchanged", lambda _root: True)
        monkeypatch.setattr(rc5_release, "credential_scan", lambda *_args: True)
        assert rc5_release.read_rc5_freeze(root)["release_id"] == rc5_release.RELEASE_ID
        changed = root / rc5_release.CANDIDATE_PATH
        changed.write_text('{"changed":true}\n', encoding="utf-8")
        with pytest.raises(ConfigurationError, match="attestation changed"):
            rc5_release.read_rc5_freeze(root)


def test_freeze_internal_execution_policy_mutation_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory(prefix="rc5-freeze-policy-") as directory:
        root = Path(directory)
        candidate = {
            "release_id": rc5_release.RELEASE_ID,
            "execution_order": ["openai/gpt-5"],
            "budgets_usd": {"stage_a_cap": 2.0, "scientific_hard_cap": 52.0},
        }
        for relative in rc5_release.ATTESTED_GATE_PATHS:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = candidate if relative == rc5_release.CANDIDATE_PATH else {"passed": True}
            path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        attestation_hashes = {
            relative.as_posix(): hashlib.sha256((root / relative).read_bytes()).hexdigest()
            for relative in rc5_release.ATTESTED_GATE_PATHS
        }
        freeze_path = root / rc5_release.FREEZE_PATH
        freeze = {
            **candidate,
            "schema_version": "uc-bench-case1-pilot-v1-rc5-freeze-1",
            "status": "frozen_pre_science",
            "frozen_at": "2026-09-11T00:00:00+00:00",
            "closure": {"hashes": {}, "aggregate_digest": canonical_sha256({})},
            "attestation_hashes": attestation_hashes,
        }
        freeze_path.write_text(json.dumps(freeze) + "\n", encoding="utf-8")
        monkeypatch.setattr(rc5_release, "declared_rc5_hashes", lambda _root: {})
        monkeypatch.setattr(rc5_release, "rc4_artifacts_unchanged", lambda _root: True)
        monkeypatch.setattr(rc5_release, "credential_scan", lambda *_args: True)
        assert rc5_release.read_rc5_freeze(root)["budgets_usd"]["scientific_hard_cap"] == 52.0
        freeze["budgets_usd"]["scientific_hard_cap"] = 5_200.0
        freeze_path.write_text(json.dumps(freeze) + "\n", encoding="utf-8")
        with pytest.raises(ConfigurationError, match="execution policy differs"):
            rc5_release.read_rc5_freeze(root)


def test_truthy_nonboolean_release_gate_results_never_authorize_freeze(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert not rc5_release._release_prerequisites_passed(  # noqa: SLF001
        {"passed": "false"}, {"passed": True}
    )
    with tempfile.TemporaryDirectory(prefix="rc5-truthy-gate-") as directory:
        root = Path(directory)
        candidate: dict[str, object] = {}
        self_containment = {"passed": "false"}
        zero_cost = {"passed": True}
        for relative, payload in (
            (rc5_release.CANDIDATE_PATH, candidate),
            (rc5_release.SELF_CONTAINMENT_PATH, self_containment),
            (rc5_release.ZERO_COST_GATE_PATH, zero_cost),
        ):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        monkeypatch.setattr(rc5_release, "candidate_manifest", lambda _root: {})
        with pytest.raises(ConfigurationError, match="zero-cost release gate failed"):
            rc5_release.freeze_rc5(
                root,
                candidate=candidate,
                self_containment=self_containment,
                zero_cost_gate=zero_cost,
            )


def test_reporting_keeps_execution_and_verifier_failure_classes_separate() -> None:
    with tempfile.TemporaryDirectory(prefix="rc5-report-taxonomy-") as directory:
        root = Path(directory)
        summary_path = root / "summary.json"
        summary_path.write_text(
            json.dumps(
                {
                    "model_id": "example/model",
                    "classification": "completed",
                    "diagnostic_grade": {
                        "complete_mission_success": False,
                        "partial_scientific_quality": 75.0,
                        "failure_class": "scientific_failure",
                        "requirements": [],
                    },
                    "authoritative_lifecycle": {"submission_accepted": True},
                    "submission": {"state": {"completion_accepted": True}},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        row = rc5_analysis._model_row(root, "summary.json", None)  # noqa: SLF001
        assert row["execution_classification"] == "completed"
        assert row["verifier_failure_class"] == "scientific_failure"


@pytest.mark.parametrize(
    "execution_classification, verifier_class, mission_success, expected",
    [
        ("completed", "none", True, "success"),
        ("completed", "scientific_failure", False, "scientific"),
        ("completed", "integrity_failure", False, "integrity"),
        ("completed", "contract_failure", False, "contract"),
        ("protected_evidence_tampering", None, None, "integrity"),
        ("agent_task_failure", None, None, "model_completion"),
        ("agent_refusal", None, None, "model_completion"),
        ("context_budget_exhaustion", None, None, "model_completion"),
        ("cost_cap_reached", None, None, "model_completion"),
        ("provider_adapter_failure", None, None, "provider"),
        ("provider_policy_refusal", None, None, "provider"),
        ("grader_failure", None, None, "infrastructure"),
        ("infrastructure_failure", None, None, "infrastructure"),
        ("provider_identity_failure", None, None, "infrastructure"),
        ("unknown_harness_failure", None, None, "infrastructure"),
        ("new_unrecognized_class", None, None, "unclassified"),
    ],
)
def test_reporting_taxonomy_is_exhaustive_and_non_overlapping(
    execution_classification: str,
    verifier_class: str | None,
    mission_success: bool | None,
    expected: str,
) -> None:
    assert (
        rc5_analysis.execution_taxonomy_bucket(
            execution_classification, verifier_class, mission_success
        )
        == expected
    )


def test_verifier_contains_no_entity_specific_or_prose_matching_shortcut() -> None:
    source = (ROOT / "src/uc_bench/case1_pilot_v1_rc5_verifier.py").read_text()
    cohort = (ROOT / "src/uc_bench/case1_pilot_v1_rc5_cohort.py").read_text()
    assert "F0001" not in source + cohort
    assert "re.search(" not in source
    assert "substring" not in source.lower()


def test_exact_fake_provider_production_path_passes() -> None:
    with tempfile.TemporaryDirectory(prefix="rc5-preflight-") as directory:
        result = run_exact_production_preflight(ROOT, Path(directory))
    assert result["passed"]
    assert result["api_requests"] == 0
    assert result["checks"]["rc5_authoritative_lifecycle_present"]
    assert result["checks"]["replay_exact"]


def test_all_ten_properties_have_fixed_weights_summing_to_100() -> None:
    assert len(WEIGHTS) == 10
    assert sum(WEIGHTS.values()) == 100

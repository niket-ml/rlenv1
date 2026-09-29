"""Zero-cost scientific, adversarial and RC4-regression controls for RC5."""

from __future__ import annotations

import copy
import csv
import hashlib
import inspect
import json
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import uc_bench.mmmvp_open_rc17_controls as legacy
from uc_bench.case1_pilot_v1_rc5_cohort import reconstruct_committed_cohort
from uc_bench.case1_pilot_v1_rc5_contract import contract_completeness_valid
from uc_bench.case1_pilot_v1_rc5_environment import RC5Case1Environment
from uc_bench.case1_pilot_v1_rc5_lock import INHERITED_EXTENSION_LOCK
from uc_bench.case1_pilot_v1_rc5_normalization import (
    NormalizationError,
    normalize_source_hashes,
)
from uc_bench.case1_pilot_v1_rc5_reporting import reconstruct_lifecycle
from uc_bench.case1_pilot_v1_rc5_verifier import (
    WEIGHTS,
    verify_case1_rc5_submission,
)
from uc_bench.hashing import canonical_sha256
from uc_bench.model_runner import _write_json

RC4_RUN = Path(
    "artifacts/uc_bench_case1_pilot_v1_rc4/science/runs/case1-rc4-00-openai-gpt-5-attempt-0"
)
RC4_ARTIFACT_DIGEST = "1ad3edf50c70a9997253fbd929eebbbf1dcb74cbd5791e58399da3a579babca7"


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"object required: {path}")
    return value


def _hash_tree(root: Path, relative: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((root / relative).rglob("*"))
        if path.is_file()
    }


def rc4_artifacts_unchanged(project_root: Path) -> bool:
    hashes = _hash_tree(project_root.resolve(), Path("artifacts/uc_bench_case1_pilot_v1_rc4"))
    return len(hashes) == 246 and canonical_sha256(hashes) == RC4_ARTIFACT_DIGEST


@contextmanager
def _rc5_reference_builder() -> Iterator[None]:
    with INHERITED_EXTENSION_LOCK:
        original_environment = legacy.RC17OpenMMMVPEnvironment
        original_verifier = legacy.verify_rc17_case1_submission
        original_primary_rows = legacy._primary_rows  # noqa: SLF001
        original_resource_rows = legacy._resource_rows  # noqa: SLF001
        original_resource_expected = legacy._resource_expected  # noqa: SLF001

        def committed_primary_rows(workspace: Path, aggregation: str) -> list[dict[str, Any]]:
            rows = original_primary_rows(workspace, aggregation)
            manifest = workspace / "work/eligible_entities.csv"
            if not manifest.is_file():
                return rows
            with manifest.open(encoding="utf-8", newline="") as handle:
                included = {
                    row["entity_id"]
                    for row in csv.DictReader(handle)
                    if row["included"].lower() == "true"
                }
            return [row for row in rows if row["unit"] in included]

        def committed_resource_rows(workspace: Path, resource: str) -> list[dict[str, Any]]:
            rows = original_resource_rows(workspace, resource)
            if resource != "X31":
                return rows
            manifest = workspace / "work/eligible_entities.csv"
            with manifest.open(encoding="utf-8", newline="") as handle:
                included = {
                    row["entity_id"]
                    for row in csv.DictReader(handle)
                    if row["included"].lower() == "true"
                }
            return [row for row in rows if row["unit"] in included]

        def cohort_resource_expected(
            workspace: Path,
            resource: str,
            primary_auc: float,
            *,
            calibration_bin_count: int,
            validation_plan: dict[str, Any],
        ) -> dict[str, Any]:
            if resource != "X31":
                return original_resource_expected(
                    workspace,
                    resource,
                    primary_auc,
                    calibration_bin_count=calibration_bin_count,
                    validation_plan=validation_plan,
                )
            with (workspace / "work/resource_analysis.csv").open(
                encoding="utf-8", newline=""
            ) as handle:
                rows = list(csv.DictReader(handle))
            canonical = legacy._canonical(rows)  # noqa: SLF001
            result = {
                "roc_auc": legacy.calculate_metric(canonical, "ROC_AUC", "EMPIRICAL", {}),
                "brier_score": legacy.calculate_metric(
                    canonical, "BRIER_SCORE", "EMPIRICAL", {}
                ),
                "net_benefit": legacy.calculate_metric(
                    canonical, "NET_BENEFIT", "EMPIRICAL", {"threshold": 0.5}
                ),
            }
            result["primary_auc_absolute_delta"] = abs(result["roc_auc"] - primary_auc)
            return result

        legacy.RC17OpenMMMVPEnvironment = RC5Case1Environment
        legacy.verify_rc17_case1_submission = verify_case1_rc5_submission
        legacy._primary_rows = committed_primary_rows  # noqa: SLF001
        legacy._resource_rows = committed_resource_rows  # noqa: SLF001
        legacy._resource_expected = cohort_resource_expected  # noqa: SLF001
        try:
            yield
        finally:
            legacy.RC17OpenMMMVPEnvironment = original_environment
            legacy.verify_rc17_case1_submission = original_verifier
            legacy._primary_rows = original_primary_rows  # noqa: SLF001
            legacy._resource_rows = original_resource_rows  # noqa: SLF001
            legacy._resource_expected = original_resource_expected  # noqa: SLF001


def build_reference(
    project_root: Path, run_root: Path, **kwargs: Any
) -> tuple[dict[str, Any], Path]:
    resource = kwargs.setdefault("resource", "X24")
    if "exclude_pending" not in kwargs:
        kwargs["exclude_pending"] = resource != "X24"
    with _rc5_reference_builder():
        submission, workspace = legacy.build_reference(project_root, run_root, **kwargs)
    final_decision = submission["final_submission"]["decision"]
    matched = {
        row["matched_contingency_id"] for row in submission["final_submission"]["belief_updates"]
    }
    if len(matched) == 1:
        followup = copy.deepcopy(submission["followup_plan"])
        selected = next(
            row
            for row in followup["result_contingencies"]
            if row["contingency_id"] == next(iter(matched))
        )
        for field in ("development_stage", "disposition", "use_scope"):
            selected["next_decision"][field] = final_decision[field]
        observed_updates = {
            row["hypothesis_id"]: (
                "UNCHANGED"
                if float(row["after"]) == float(row["before"])
                else "INCREASE"
                if float(row["after"]) > float(row["before"])
                else "DECREASE"
            )
            for row in submission["final_submission"]["belief_updates"]
        }
        for row in selected["hypothesis_updates"]:
            row["direction"] = observed_updates[row["hypothesis_id"]]
        _synchronize_followup_commit(submission, workspace, followup)
    return submission, workspace


def _copy_episode(
    submission: dict[str, Any], workspace: Path, target: Path
) -> tuple[dict[str, Any], Path]:
    return legacy._copy_episode(submission, workspace, target), target  # noqa: SLF001


def _replace_final(submission: dict[str, Any], workspace: Path, final: dict[str, Any]) -> None:
    legacy._replace_final(submission, workspace, final)  # noqa: SLF001


def _rehash_final_path(final: dict[str, Any], workspace: Path, relative: str) -> None:
    digest = hashlib.sha256((workspace / relative).read_bytes()).hexdigest()
    next(row for row in final["artifact_manifest"] if row["path"] == relative)["sha256"] = digest


def _grade(root: Path, submission: dict[str, Any], workspace: Path) -> dict[str, Any]:
    return verify_case1_rc5_submission(root, workspace, submission).to_dict()


def _statuses(grade: dict[str, Any]) -> dict[str, bool]:
    return {
        str(row["requirement_id"]): bool(row["passed"])
        for row in grade.get("requirements") or []
        if row.get("requirement_id") in WEIGHTS
    }


def _synchronize_manifest_commit(
    submission: dict[str, Any], workspace: Path, rows: list[dict[str, str]]
) -> None:
    path = workspace / "work/eligible_entities.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    plan = copy.deepcopy(submission["validation_plan"])
    plan["prospective_specification"]["eligible_entity_manifest_sha256"] = digest
    records = workspace.parent / ".mmmvp_host_records" / workspace.name
    (records / "validation_plan.json").write_text(
        json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    inputs = _read(records / "validation_input_hashes.json")
    inputs["work/eligible_entities.csv"] = digest
    (records / "validation_input_hashes.json").write_text(
        json.dumps(inputs, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    plan_digest = hashlib.sha256(
        json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    submission["validation_plan"] = plan
    submission["validation_input_hashes"] = inputs
    submission["state"]["validation_plan_hash"] = plan_digest
    for event in submission["event_log"]:
        if event["event"] == "commit_validation_plan":
            event["digest"] = plan_digest
        elif event["event"] == "reveal_validation":
            event["committed_plan_hash"] = plan_digest


def _synchronize_followup_commit(
    submission: dict[str, Any], workspace: Path, followup: dict[str, Any]
) -> None:
    records = workspace.parent / ".mmmvp_host_records" / workspace.name
    (records / "followup_plan.json").write_text(
        json.dumps(followup, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (workspace / "work/followup_plan.json").write_text(
        json.dumps(followup, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    digest = hashlib.sha256(
        json.dumps(followup, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    submission["followup_plan"] = followup
    submission["state"]["followup_plan_hash"] = digest
    for event in submission["event_log"]:
        if event["event"] == "commit_followup_plan":
            event["digest"] = digest
        elif event["event"] == "submit":
            event["followup_plan_hash"] = digest


def _rc4_fixture(project_root: Path) -> tuple[dict[str, Any], Path]:
    run = project_root.resolve() / RC4_RUN
    return _read(run / "submission.json"), run / "workspace"


def _cohort_controls(root: Path, output: Path) -> dict[str, Any]:
    submission, workspace = _rc4_fixture(root)
    baseline = _grade(root, submission, workspace)
    baseline_cohort = reconstruct_committed_cohort(
        workspace,
        submission["validation_plan"],
        host_input_hashes=submission["validation_input_hashes"],
    )
    attacks: dict[str, bool] = {}
    for name, mutate, synchronized in (
        (
            "reintroduce_excluded",
            lambda rows: rows.__setitem__(
                next(i for i, row in enumerate(rows) if row["included"].strip().lower() == "false"),
                {
                    **next(row for row in rows if row["included"].strip().lower() == "false"),
                    "included": "true",
                    "preoutcome_exclusion_reason": "",
                },
            ),
            False,
        ),
        ("drop_included", lambda rows: rows.pop(1), True),
        (
            "add_uncommitted",
            lambda rows: rows.append(
                {
                    "entity_id": "SYNTHETIC_UNCOMMITTED",
                    "source_record_ids": "SYNTHETIC_SOURCE",
                    "included": "true",
                    "preoutcome_exclusion_reason": "",
                }
            ),
            True,
        ),
        (
            "change_exclusion_after_reveal",
            lambda rows: rows.__setitem__(
                next(i for i, row in enumerate(rows) if row["included"].strip().lower() == "false"),
                {
                    **next(row for row in rows if row["included"].strip().lower() == "false"),
                    "preoutcome_exclusion_reason": "PREOUTCOME_MISSING_PREDICTION",
                },
            ),
            False,
        ),
    ):
        copied, target = _copy_episode(submission, workspace, output / name)
        with (target / "work/eligible_entities.csv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        mutate(rows)
        if synchronized:
            _synchronize_manifest_commit(copied, target, rows)
        else:
            with (target / "work/eligible_entities.csv").open(
                "w", encoding="utf-8", newline=""
            ) as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
        attacks[name] = not _grade(root, copied, target)["complete_mission_success"]

    copied, target = _copy_episode(submission, workspace, output / "declared_hash_mutation")
    copied["validation_plan"]["prospective_specification"]["eligible_entity_manifest_sha256"] = (
        "0" * 64
    )
    attacks["declared_manifest_hash_mutation"] = not _grade(root, copied, target)[
        "complete_mission_success"
    ]

    entity_submission, entity_workspace = build_reference(
        root,
        output / "supported_exclusion_entity",
        exclude_pending=True,
        resource="X46",
    )
    clustered_submission, clustered_workspace = build_reference(
        root,
        output / "supported_exclusion_clustered",
        exclude_pending=True,
        aggregation="NONE",
        resource="X46",
    )
    entity_grade = _grade(root, entity_submission, entity_workspace)
    clustered_grade = _grade(root, clustered_submission, clustered_workspace)
    source_has_entity_special_case = "F0001" in inspect.getsource(reconstruct_committed_cohort)
    return {
        "rc4_123_passes": baseline["complete_mission_success"]
        and baseline_cohort.valid
        and len(baseline_cohort.included_entities) == 123,
        "attacks": attacks,
        "supported_exclusion_entity": entity_grade["complete_mission_success"],
        "supported_exclusion_clustered": clustered_grade["complete_mission_success"],
        "cohort_code_has_entity_special_case": source_has_entity_special_case,
        "passed": all(attacks.values())
        and entity_grade["complete_mission_success"]
        and clustered_grade["complete_mission_success"]
        and not source_has_entity_special_case,
    }


def _resource_controls(root: Path, output: Path) -> dict[str, Any]:
    submission, workspace = _rc4_fixture(root)
    expected_mapping = {
        "a": "0" * 64,
        "b": "1" * 64,
    }
    mapping = normalize_source_hashes(expected_mapping)
    listed = normalize_source_hashes(
        [
            {"path": "a", "sha256": "0" * 64},
            {"path": "b", "sha256": "1" * 64},
        ]
    )
    malformed_rejected = []
    for value in (
        [{"path": "a", "sha256": "0" * 64}, {"path": "a", "sha256": "0" * 64}],
        {"a": "bad"},
        [{"path": "a"}],
    ):
        try:
            normalize_source_hashes(value)
            malformed_rejected.append(False)
        except NormalizationError:
            malformed_rejected.append(True)

    baseline = _grade(root, submission, workspace)
    hash_attacks: dict[str, bool] = {}
    for name, mutate in (
        ("missing", lambda hashes: hashes.pop()),
        ("wrong", lambda hashes: hashes[0].__setitem__("sha256", "0" * 64)),
    ):
        copied, target = _copy_episode(submission, workspace, output / f"hash_{name}")
        path = target / "work/resource_summary.json"
        summary = _read(path)
        hashes = summary["source_hashes"]
        assert isinstance(hashes, list)
        mutate(hashes)
        path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        final = copy.deepcopy(copied["final_submission"])
        _rehash_final_path(final, target, "work/resource_summary.json")
        _replace_final(copied, target, final)
        hash_attacks[name] = not _grade(root, copied, target)["complete_mission_success"]
    role_results: list[bool] = []
    for role in ("OTHER", "PROVENANCE"):
        copied, target = _copy_episode(submission, workspace, output / f"role_{role.lower()}")
        final = copy.deepcopy(copied["final_submission"])
        next(
            row for row in final["artifact_manifest"] if row["path"] == "work/resource_summary.json"
        )["role"] = role
        _replace_final(copied, target, final)
        role_results.append(_grade(root, copied, target)["complete_mission_success"])

    x46_submission, x46_workspace = build_reference(root, output / "x46", resource="X46")
    unused, unused_workspace = _copy_episode(x46_submission, x46_workspace, output / "x46_unused")
    final = copy.deepcopy(unused["final_submission"])
    final["resource_assessment"]["calculation_ids"] = []
    _replace_final(unused, unused_workspace, final)
    unused_fails = not _grade(root, unused, unused_workspace)["complete_mission_success"]

    hard_coded, hard_workspace = _copy_episode(
        x46_submission, x46_workspace, output / "x46_altered_input"
    )
    predictions = hard_workspace / "purchased/X46/matched_predictions.csv"
    text = predictions.read_text(encoding="utf-8")
    predictions.write_text(text.replace("0.", "0.9", 1), encoding="utf-8")
    hard_coded_fails = not _grade(root, hard_coded, hard_workspace)["complete_mission_success"]
    return {
        "mapping_and_list_equal": mapping == listed,
        "malformed_rejected": malformed_rejected,
        "wrong_and_missing_hashes_fail": hash_attacks,
        "rc4_transitive_chain_passes": baseline["complete_mission_success"],
        "artifact_role_invariant": all(role_results),
        "none_branch_passes": baseline["complete_mission_success"],
        "unused_purchase_fails": unused_fails,
        "altered_resource_input_defeats_hard_coding": hard_coded_fails,
        "passed": mapping == listed
        and all(malformed_rejected)
        and all(hash_attacks.values())
        and baseline["complete_mission_success"]
        and all(role_results)
        and unused_fails
        and hard_coded_fails,
    }


def _lifecycle_recovery_controls(root: Path, output: Path) -> dict[str, Any]:
    source = root / RC4_RUN
    journal_paths = sorted((source / "host_trajectory/journal").glob("*.json"))
    journal = [_read(path) for path in journal_paths]

    def event_names(row: dict[str, Any]) -> list[str]:
        state = (row.get("environment") or {}).get("state") or {}
        events = state.get("event_log") or (row.get("environment") or {}).get("event_record") or []
        return [str(item.get("event")) for item in events if isinstance(item, dict)]

    cutpoints: dict[str, int] = {}
    for index, row in enumerate(journal, start=1):
        names = event_names(row)
        if "reveal_validation" in names and "purchase_resource" not in names:
            cutpoints["at_reveal"] = index
        if "purchase_resource" in names and "submit" not in names:
            cutpoints["at_purchase"] = index
        if "followup_plan" in str(row) and "submit" not in names:
            cutpoints["pre_submit"] = index
    final_lifecycle = reconstruct_lifecycle(source)
    resumed: dict[str, bool] = {}
    for name, count in cutpoints.items():
        target = output / name
        (target / "host_trajectory/journal").mkdir(parents=True, exist_ok=True)
        for path in journal_paths[:count]:
            shutil.copy2(path, target / "host_trajectory/journal" / path.name)
        shutil.copy2(source / "request_ledger.json", target / "request_ledger.json")
        interrupted = reconstruct_lifecycle(target)
        # Resume is modeled by atomically making later authoritative journal
        # records visible. A stale convenience latest.json is intentionally not
        # consulted by the reporting reconstruction.
        (target / "host_trajectory/latest.json").write_text(
            json.dumps(journal[max(0, count - 2)], indent=2) + "\n", encoding="utf-8"
        )
        for path in journal_paths[count:]:
            shutil.copy2(path, target / "host_trajectory/journal" / path.name)
        reconstructed = reconstruct_lifecycle(target)
        resumed[name] = bool(
            interrupted["journal_sequence"] == count
            and reconstructed == final_lifecycle
            and reconstructed["submission_accepted"]
        )
    return {
        "cutpoints_found": sorted(cutpoints),
        "resume_matches_uninterrupted": resumed,
        "stale_latest_cannot_override_journal": all(resumed.values()),
        "passed": set(cutpoints) == {"at_reveal", "at_purchase", "pre_submit"}
        and all(resumed.values()),
    }


def _scientific_controls(root: Path, output: Path) -> dict[str, Any]:
    submission, workspace = _rc4_fixture(root)
    baseline = _grade(root, submission, workspace)
    results = baseline["diagnostics"]["calculation_results"]
    observed = {
        row["metric"]: float(row["recomputed_value"])
        for row in results.values()
        if row["role"] == "PRIMARY"
    }
    expected = {
        "ROC_AUC": 0.7848806366047745,
        "BRIER_SCORE": 0.19134359526902642,
        "CALIBRATION_ERROR": 0.09581372764227644,
        "NET_BENEFIT": 0.17073170731707318,
        "WORST_SITE_ROC_AUC": 0.6941176470588235,
    }
    exact_values = all(abs(observed[key] - value) < 1e-12 for key, value in expected.items())
    altered: dict[str, bool] = {}
    for name, mutate in (
        (
            "prediction",
            lambda rows: rows[0].__setitem__("prediction", str(1 - float(rows[0]["prediction"]))),
        ),
        (
            "outcome",
            lambda rows: rows[0].__setitem__("outcome", str(1 - int(rows[0]["outcome"]))),
        ),
        ("membership", lambda rows: rows.pop()),
        ("site", lambda rows: rows[0].__setitem__("site", "ALTERED_SITE")),
    ):
        copied, target = _copy_episode(submission, workspace, output / f"alter_{name}")
        table = target / "work/primary_analysis.csv"
        with table.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        mutate(rows)
        with table.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        altered[name] = not _grade(root, copied, target)["complete_mission_success"]
    copied, target = _copy_episode(submission, workspace, output / "alter_bin_count")
    final = copy.deepcopy(copied["final_submission"])
    next(row for row in final["calculations"] if row["metric"] == "CALIBRATION_ERROR")[
        "parameters"
    ]["bin_count"] = 8
    _replace_final(copied, target, final)
    altered["bin_count"] = not _grade(root, copied, target)["complete_mission_success"]
    return {
        "independent_values": observed,
        "expected_values_match": exact_values,
        "altered_inputs_fail": altered,
        "passed": baseline["complete_mission_success"] and exact_values and all(altered.values()),
    }


def run_rc5_controls(project_root: Path, output_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    references = []
    for name, kwargs in (
        ("mean", {}),
        ("median", {"aggregation": "MEDIAN"}),
        ("clustered", {"aggregation": "NONE"}),
        (
            "aliases",
            {
                "probability_metric": "LOG_LOSS",
                "utility_metric": "THRESHOLD_EXPECTED_UTILITY",
                "context_metric": "SITE_WEIGHTED_ROC_AUC",
            },
        ),
    ):
        submission, workspace = build_reference(root, output_root / f"reference_{name}", **kwargs)
        references.append({"workflow": name, "grade": _grade(root, submission, workspace)})
    cohort = _cohort_controls(root, output_root / "cohort")
    resource = _resource_controls(root, output_root / "resource")
    science = _scientific_controls(root, output_root / "science")
    recovery = _lifecycle_recovery_controls(root, output_root / "lifecycle_recovery")
    rc4_submission, rc4_workspace = _rc4_fixture(root)
    rc4_grade = _grade(root, rc4_submission, rc4_workspace)
    lifecycle = reconstruct_lifecycle(root / RC4_RUN)
    lifecycle_passed = all(
        (
            lifecycle["tools_called"] == 52,
            lifecycle["validation_committed"],
            lifecycle["validation_revealed"],
            lifecycle["resource_purchased"] == "none",
            lifecycle["submission_accepted"],
            lifecycle["completion_state"] == "submitted",
            lifecycle["reliability_score"] == 100,
            lifecycle["budget_enforcement_spend_usd"] == 0.63544475,
        )
    )
    passed = all(
        (
            rc4_artifacts_unchanged(root),
            contract_completeness_valid(),
            all(row["grade"]["complete_mission_success"] for row in references),
            cohort["passed"],
            resource["passed"],
            science["passed"],
            rc4_grade["complete_mission_success"],
            rc4_grade["partial_scientific_quality"] == 100,
            lifecycle_passed,
            recovery["passed"],
        )
    )
    value = {
        "schema_version": "uc-bench-case1-pilot-v1-rc5-controls-1",
        "passed": passed,
        "api_requests": 0,
        "rc4_artifacts_unchanged": rc4_artifacts_unchanged(root),
        "contract_completeness_valid": contract_completeness_valid(),
        "reference_and_alternative_workflows": references,
        "cohort_controls": cohort,
        "resource_controls": resource,
        "scientific_recomputation_controls": science,
        "rc4_immutable_fixture_replay": {
            "official_rc4_score_preserved": 22.0,
            "development_rc5_replay_score": rc4_grade["partial_scientific_quality"],
            "development_rc5_replay_mission": rc4_grade["complete_mission_success"],
            "raw_bytes_modified": False,
        },
        "authoritative_lifecycle_replay": {**lifecycle, "passed": lifecycle_passed},
        "interruption_restart_reporting_controls": recovery,
    }
    _write_json(output_root / "control_results.json", value, secret="")
    return value


def write_rc4_fixture_manifest(project_root: Path, target: Path) -> dict[str, Any]:
    root = project_root.resolve()
    hashes = _hash_tree(root, RC4_RUN)
    value = {
        "schema_version": "uc-bench-case1-pilot-v1-rc5-rc4-fixture-1",
        "source": RC4_RUN.as_posix(),
        "file_count": len(hashes),
        "hashes": hashes,
        "aggregate_digest": canonical_sha256(hashes),
        "raw_bytes_modified": False,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    _write_json(target, value, secret="")
    return value


__all__ = [
    "RC4_ARTIFACT_DIGEST",
    "RC4_RUN",
    "build_reference",
    "rc4_artifacts_unchanged",
    "run_rc5_controls",
    "write_rc4_fixture_manifest",
]

"""UC-Bench v0.6 semantic-artifact predictor-diligence environment.

v0.6 preserves the coherent v0.5 job while exposing ten independently graded
scientific artifacts.  It imports deterministic evidence generators from v0.5
but uses new scenario seeds and a distinct state machine, task, and grader.
"""

from __future__ import annotations

import csv
import json
import shutil
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any

from uc_bench.errors import ConfigurationError, ContractError, InvalidTransitionError
from uc_bench.hard_suite_v05 import (
    FEATURES,
    METRIC_NAMES,
    METRIC_TOLERANCES,
    MODEL_WEIGHTS,
    SCORE_SCRIPT,
    _cohort_rows,
    _copy_tree_files,
    _preprocessing_history,
    _public_cohort_contract,
    _read_csv,
    _read_object,
    _reproduction_assets,
    _safe_predictions,
    _write_csv,
    _write_json,
    compute_v05_metrics,
    expected_belief_direction,
    expected_final_claim_statuses,
    expected_final_decision,
    expected_initial_claim_statuses,
    expected_intervention_effect,
    expected_next_action_class,
)
from uc_bench.hashing import canonical_sha256, sha256_file

V06_CONFIG_PATH = Path("configs/hard_suite_v06.json")
V06_HELDOUT_PATH = Path("grader_private/hard_suite_v06_heldout.json")
V06_TASK_ROOT = Path("tasks/hard_suite_v06")
PRECOMMIT_ARTIFACTS = (
    "submission/cohort_inventory.csv",
    "submission/provenance_audit.json",
    "submission/patient_visit_map.csv",
    "submission/endpoint_audit.json",
    "submission/preprocessing_lineage.json",
    "submission/reproduction_predictions.csv",
    "submission/committed_validation_plan.json",
)
ALL_ARTIFACTS = (
    *PRECOMMIT_ARTIFACTS,
    "submission/validation_results.json",
    "submission/resource_value_memo.json",
    "submission/final_diligence_report.json",
)
SCHEMA_BY_ARTIFACT = {
    "submission/provenance_audit.json": "provenance_audit.schema.json",
    "submission/endpoint_audit.json": "endpoint_audit.schema.json",
    "submission/preprocessing_lineage.json": "preprocessing_lineage.schema.json",
    "submission/committed_validation_plan.json": "committed_validation_plan.schema.json",
    "submission/validation_results.json": "validation_results.schema.json",
    "submission/resource_value_memo.json": "resource_value_memo.schema.json",
    "submission/final_diligence_report.json": "final_diligence_report.schema.json",
}
V06_CAPABILITY_MAP = {
    "data_integrity": ("A01", "A02", "A03"),
    "endpoint_reasoning": ("A01", "A04", "A08"),
    "statistical_validity": ("A03", "A07", "A08"),
    "leakage_prevention": ("A05", "A07", "A08"),
    "transportability": ("A01", "A04", "A05", "A08"),
    "calibration_and_decision_utility": ("A07", "A08", "A10"),
    "experimental_design_value_of_information": ("A09", "A10"),
    "belief_revision": ("A09", "A10"),
    "reproducibility": ("A02", "A06", "A07"),
    "graceful_abstention": ("A08", "A10"),
}


def load_v06_config(project_root: Path) -> dict[str, Any]:
    return _read_object(project_root.resolve() / V06_CONFIG_PATH)


def iter_v06_scenarios(
    project_root: Path, *, partition: str = "development"
) -> list[dict[str, Any]]:
    root = project_root.resolve()
    if partition == "development":
        rows = load_v06_config(root).get("development_scenarios")
    elif partition == "heldout":
        rows = _read_object(root / V06_HELDOUT_PATH).get("scenarios")
    else:
        raise ConfigurationError(f"Unknown v0.6 partition: {partition}")
    if not isinstance(rows, list):
        raise ConfigurationError(f"Invalid v0.6 {partition} scenario collection")
    return [dict(row) for row in rows]


def load_v06_scenario(
    project_root: Path, scenario_id: str, *, partition: str = "development"
) -> dict[str, Any]:
    rows = [
        row
        for row in iter_v06_scenarios(project_root, partition=partition)
        if row.get("scenario_id") == scenario_id
    ]
    if len(rows) != 1:
        raise ConfigurationError(
            f"Expected one v0.6 {partition} scenario {scenario_id}; found {len(rows)}"
        )
    return rows[0]


def validate_v06_config(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    config = load_v06_config(root)
    artifacts = config.get("artifacts") or []
    if len(artifacts) != 10:
        raise ContractError("v0.6 requires exactly ten scientific artifacts")
    if sum(float(row["weight"]) for row in artifacts) != 100.0:
        raise ContractError("v0.6 artifact weights must sum to 100")
    if max(float(row["weight"]) for row in artifacts) > 10.0:
        raise ContractError("No v0.6 artifact may exceed ten percent")
    if any(not row.get("remedy_intervention_class") for row in artifacts):
        raise ContractError("Every v0.6 artifact requires an actionable remedy class")
    allowed_remedies = set(
        (config.get("deduction_validity_contract") or {}).get(
            "allowed_remedy_classes", []
        )
    )
    if any(row["remedy_intervention_class"] not in allowed_remedies for row in artifacts):
        raise ContractError("A v0.6 artifact uses an undeclared remedy class")
    development = iter_v06_scenarios(root, partition="development")
    heldout = iter_v06_scenarios(root, partition="heldout")
    if len(development) != 6 or len(heldout) != 6:
        raise ContractError("v0.6 requires six development and six held-out states")
    if {row["scenario_id"] for row in development} & {row["scenario_id"] for row in heldout}:
        raise ContractError("v0.6 development and held-out IDs overlap")
    if {row["scenario_class"] for row in development} != {row["scenario_class"] for row in heldout}:
        raise ContractError("v0.6 partitions do not cover the same controlled states")
    expected_resources = {
        "none",
        *(str(row["resource_id"]) for row in config["resource_catalog"]),
    }
    for scenario in [*development, *heldout]:
        if set(scenario["resource_utilities"]) != expected_resources:
            raise ContractError(f"Incomplete resource utilities: {scenario['scenario_id']}")
    heldout_meta = _read_object(root / V06_HELDOUT_PATH)
    return {
        "artifact_count": len(artifacts),
        "development_scenario_count": len(development),
        "heldout_scenario_count": len(heldout),
        "heldout_status": heldout_meta.get("status"),
        "status": config.get("status"),
    }


@dataclass(frozen=True, slots=True)
class V06Package:
    scenario_id: str
    partition: str
    workspace_root: Path
    sealed_root: Path
    package_digest: str
    sealed_digest: str
    private_scenario: dict[str, Any]
    schema_root: Path


class V06Builder:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()

    def build(
        self,
        scenario_id: str,
        *,
        output_root: Path,
        partition: str = "development",
        replace: bool = False,
    ) -> V06Package:
        validate_v06_config(self.project_root)
        config = load_v06_config(self.project_root)
        scenario = load_v06_scenario(self.project_root, scenario_id, partition=partition)
        workspace = output_root.resolve() / f"hard6-{scenario_id}"
        sealed = output_root.resolve() / f"hard6-{scenario_id}-sealed"
        for path in (workspace, sealed):
            if path.exists():
                if not replace:
                    raise ConfigurationError(f"v0.6 build path exists: {path}")
                shutil.rmtree(path)
            path.mkdir(parents=True)
        _copy_tree_files(self.project_root / V06_TASK_ROOT, workspace)
        decision = config["decision_contract"]
        external_contract = _public_cohort_contract(scenario)
        _write_json(
            workspace / "case" / "intended_use.json",
            {
                **decision,
                "intended_drug": "infliximab",
                "intended_platform": "affymetrix_hgu133_plus_2",
                "use_context": "research-stage licensing diligence; not clinical deployment",
            },
        )
        registry = [
            {
                "cohort_id": "DISCOVERY-01",
                "role": "training",
                "population": "moderate_to_severe_uc",
                "drug": "infliximab",
                "endpoint": "week_6_clinical_response",
                "platform": "affymetrix_hgu133_plus_2",
                "outcomes_visible": "yes",
            },
            {
                "cohort_id": "INTERNAL-01",
                "role": "grouped_internal_validation",
                "population": "moderate_to_severe_uc",
                "drug": "infliximab",
                "endpoint": "week_6_clinical_response",
                "platform": "affymetrix_hgu133_plus_2",
                "outcomes_visible": "yes",
            },
            {**external_contract, "outcomes_visible": "sealed_until_commitment"},
        ]
        _write_csv(workspace / "case" / "cohort_registry.csv", registry)
        _write_json(
            workspace / "case" / "sponsor_attestations.json",
            {
                "document_type": "unverified_sponsor_summary",
                "identity_linkage": "complete",
                "preprocessing_fit_scope": "training_only",
                "endpoint_review": "complete",
                "predictor_status": "locked",
                "instruction": "Reconcile claims against row-level and execution evidence.",
            },
        )
        _write_json(
            workspace / "case" / "endpoint_definition.json",
            {
                "target": "week_6_clinical_response",
                "source_fields": ["reviewer_a", "reviewer_b", "extraction_label"],
                "extraction_rule": "Primary abstracted label plus reviewer sensitivity analysis.",
                "adjudication_status": "not_performed_before_resource_selection",
                "temporal_rule": "baseline input; week-6 outcome",
            },
        )
        _write_csv(
            workspace / "case" / "preprocessing_history.csv",
            _preprocessing_history(scenario),
        )
        identity = scenario["scenario_class"] == "patient_identity_dependence_failure"
        endpoint = scenario["scenario_class"] == "endpoint_label_ambiguity"
        leaky = scenario["scenario_class"] == "batch_or_preprocessing_leakage"
        internal_predictions, internal_outcomes, _ = _cohort_rows(
            seed=int(scenario["seed"]) + 11,
            cohort_id="INTERNAL-01",
            patient_count=96,
            signal_strength=0.95,
            identity_ambiguous=identity,
            endpoint_ambiguous=endpoint,
            leaky=leaky,
            platform="affymetrix_hgu133_plus_2",
            drug="infliximab",
            endpoint="week_6_clinical_response",
        )
        labels = {row["sample_id"]: row for row in internal_outcomes}
        _write_csv(
            workspace / "data" / "internal_predictions.csv",
            [{**row, **labels[row["sample_id"]]} for row in internal_predictions],
        )
        external_predictions, external_outcomes, crosswalk = _cohort_rows(
            seed=int(scenario["seed"]) + 29,
            cohort_id="EXTERNAL-01",
            patient_count=int(scenario["external_n"]),
            signal_strength=float(scenario["signal_strength"]),
            identity_ambiguous=identity,
            endpoint_ambiguous=endpoint,
            leaky=leaky,
            platform=external_contract["platform"],
            drug=external_contract["drug"],
            endpoint=external_contract["endpoint"],
        )
        _write_csv(workspace / "data" / "external_locked_predictions.csv", external_predictions)
        _write_csv(sealed / "validation" / "external_outcomes.csv", external_outcomes)
        _write_json(
            sealed / "validation" / "reveal_provenance.json",
            {
                "cohort_id": "EXTERNAL-01",
                "outcomes_were_sealed": True,
                "predictor_hash_verified": True,
            },
        )
        model = {
            "model_id": "locked-rank-linear-0.8.3",
            "feature_names": list(FEATURES),
            "weights": MODEL_WEIGHTS,
            "intercept": -0.10,
            "output": "probability_of_week_6_clinical_response",
            "training_locked": True,
        }
        _write_json(workspace / "model" / "locked_model.json", model)
        model_hash = sha256_file(workspace / "model" / "locked_model.json")
        _write_json(
            workspace / "model" / "predictor_manifest.json",
            {
                "model_id": model["model_id"],
                "model_sha256": model_hash,
                "training_cohort": "DISCOVERY-01",
                "training_sample_count": 118,
                "unit_of_prediction": "baseline_biopsy",
                "patient_grouping_required_for_inference": True,
                "preprocessing_contract": "training-fitted transformations only",
            },
        )
        audit_inputs, audit_references = _reproduction_assets(int(scenario["seed"]))
        _write_csv(workspace / "model" / "reproduction_inputs.csv", audit_inputs)
        _write_csv(workspace / "model" / "reference_predictions.csv", audit_references)
        script_path = workspace / "tools" / "score_locked.py"
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text(SCORE_SCRIPT, encoding="utf-8")
        _write_json(
            workspace / "case" / "metric_contract.json",
            {
                "analysis_unit": "patient",
                "recommended_visible_grouping_key": "fingerprint_group",
                "bootstrap_unit": "patient_with_site_preserved_when_possible",
                "bootstrap_replicates": 399,
                "bootstrap_seed": int(scenario["seed"]) + 7001,
                "probability_threshold": decision["probability_threshold"],
                "method_freedom": "Equivalent dependence-aware methods are permitted.",
            },
        )
        _write_json(
            workspace / "resources" / "resource_catalog.json",
            {"choose_exactly_one_or_none": True, "resources": config["resource_catalog"]},
        )
        self._build_resources(
            sealed,
            scenario,
            external_predictions,
            external_outcomes,
            crosswalk,
            external_contract,
        )
        _write_json(
            workspace / "case" / "data_room_manifest.json",
            {
                "assets": [
                    {
                        "path": path.relative_to(workspace).as_posix(),
                        "bytes": path.stat().st_size,
                        "sha256": sha256_file(path),
                    }
                    for path in sorted(workspace.rglob("*"))
                    if path.is_file() and "submission" not in path.parts
                ],
                "known_training_validation_overlap": False,
                "sponsor_attestations_are_unverified": True,
                "license_scope": "benchmark_research_only",
            },
        )
        (workspace / "submission").mkdir(exist_ok=True)
        _write_json(
            workspace / "task.json",
            {
                "schema_version": "0.6",
                "suite_id": config["suite_id"],
                "scenario_id": scenario_id,
                "partition": partition,
                "required_artifacts": list(ALL_ARTIFACTS),
                "artifact_dag": config["artifacts"],
                "trajectory_budget": config["trajectory_budget"],
            },
        )
        public_manifest = _manifest(workspace)
        sealed_manifest = _manifest(sealed)
        package_digest = canonical_sha256(public_manifest)
        sealed_digest = canonical_sha256(sealed_manifest)
        _write_json(
            workspace / "START_STATE.json",
            {
                "schema_version": "0.6",
                "scenario_id": scenario_id,
                "partition": partition,
                "package_digest": package_digest,
                "validation_outcomes_visible": False,
                "followup_resource_visible": False,
            },
        )
        return V06Package(
            scenario_id=scenario_id,
            partition=partition,
            workspace_root=workspace,
            sealed_root=sealed,
            package_digest=package_digest,
            sealed_digest=sealed_digest,
            private_scenario=scenario,
            schema_root=self.project_root / V06_TASK_ROOT / "schemas",
        )

    def _build_resources(
        self,
        sealed: Path,
        scenario: dict[str, Any],
        predictions: list[dict[str, Any]],
        outcomes: list[dict[str, Any]],
        crosswalk: list[dict[str, Any]],
        external_contract: dict[str, str],
    ) -> None:
        identity = scenario["scenario_class"] == "patient_identity_dependence_failure"
        endpoint = scenario["scenario_class"] == "endpoint_label_ambiguity"
        leaky = scenario["scenario_class"] == "batch_or_preprocessing_leakage"
        for resource_id in ("none", "R1", "R2", "R3", "R4", "R5", "R6"):
            packet = sealed / "resources" / resource_id
            packet.mkdir(parents=True)
            if resource_id == "none":
                _write_json(packet / "no_additional_evidence.json", {"new_evidence": False})
            elif resource_id == "R1":
                _write_csv(packet / "patient_visit_crosswalk.csv", crosswalk)
            elif resource_id == "R2":
                _write_csv(
                    packet / "adjudicated_outcomes.csv",
                    [
                        {
                            "sample_id": row["sample_id"],
                            "adjudicated_label": row["reviewer_a"],
                            "adjudication_status": "blinded_source_record_consensus",
                        }
                        for row in outcomes
                    ],
                )
            elif resource_id == "R3":
                _write_csv(
                    packet / "leakage_safe_predictions.csv",
                    _safe_predictions(
                        predictions,
                        outcomes,
                        seed=int(scenario["seed"]) + 503,
                        weak=leaky,
                    ),
                )
                _write_json(
                    packet / "rerun_provenance.json",
                    {
                        "patient_grouped": True,
                        "preprocessing_fit_scope": "training_only",
                        "locked_model_unchanged": True,
                    },
                )
            elif resource_id in {"R4", "R5"}:
                bridge = resource_id == "R4"
                followup_n = (
                    92
                    if bridge
                    else 58
                    if scenario["scenario_class"] == "underpowered_or_irreducible_external_evidence"
                    else 108
                )
                if (
                    bridge
                    and scenario["scenario_class"] == "endpoint_drug_platform_transfer_failure"
                ):
                    signal = 1.02
                elif (
                    not bridge
                    and scenario["scenario_class"]
                    == "underpowered_or_irreducible_external_evidence"
                ):
                    signal = 0.64
                else:
                    signal = float(scenario["signal_strength"])
                new_predictions, new_outcomes, _ = _cohort_rows(
                    seed=int(scenario["seed"]) + (907 if bridge else 1201),
                    cohort_id="BRIDGE-01" if bridge else "REPLICATION-01",
                    patient_count=followup_n,
                    signal_strength=signal,
                    identity_ambiguous=identity and not bridge,
                    endpoint_ambiguous=endpoint and not bridge,
                    leaky=False,
                    platform=(
                        "affymetrix_hgu133_plus_2" if bridge else external_contract["platform"]
                    ),
                    drug="infliximab" if bridge else external_contract["drug"],
                    endpoint=(
                        "week_6_clinical_response" if bridge else external_contract["endpoint"]
                    ),
                )
                prefix = "bridge" if bridge else "replication"
                _write_csv(packet / f"{prefix}_predictions.csv", new_predictions)
                _write_csv(packet / f"{prefix}_outcomes.csv", new_outcomes)
                _write_json(
                    packet / f"{prefix}_provenance.json",
                    {
                        "independent": True,
                        "endpoint": "week_6_clinical_response"
                        if bridge
                        else external_contract["endpoint"],
                        "drug": "infliximab" if bridge else external_contract["drug"],
                        "platform": "affymetrix_hgu133_plus_2"
                        if bridge
                        else external_contract["platform"],
                    },
                )
            else:
                _write_json(
                    packet / "expert_review.json",
                    {
                        "scope": "review_existing_evidence_only",
                        "new_patient_records": False,
                        "pipeline_rerun": False,
                        "opinion": "Obtain evidence that directly resolves the active blocker.",
                    },
                )


def _manifest(root: Path) -> list[dict[str, Any]]:
    return [
        {
            "path": path.relative_to(root).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in sorted(root.rglob("*"))
        if path.is_file()
    ]


def _validate_json(value: dict[str, Any], schema_path: Path) -> None:
    from jsonschema import Draft202012Validator
    from jsonschema.exceptions import SchemaError, ValidationError

    try:
        schema = _read_object(schema_path)
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(value)
    except (SchemaError, ValidationError) as exc:
        raise ContractError(f"Invalid v0.6 artifact {schema_path.name}: {exc.message}") from exc


class V06Environment:
    """Three irreversible transitions with artifact-level state preservation."""

    def __init__(self, package: V06Package) -> None:
        self.package = package
        self.workspace_root = package.workspace_root.resolve()
        self.phase = "working"
        self.committed_snapshot: dict[str, str] = {}
        self.committed_record_sha256: str | None = None
        self.resource_memo_sha256: str | None = None
        self.selected_resource: str | None = None
        self.submitted = False
        self.events: list[dict[str, Any]] = []

    def _resolve(self, relative: str, *, require_file: bool = True) -> Path:
        path_value = Path(relative)
        if path_value.is_absolute() or ".." in path_value.parts:
            raise ContractError("Artifact path must stay within the workspace")
        path = (self.workspace_root / path_value).resolve()
        if self.workspace_root not in path.parents:
            raise ContractError("Artifact path escaped the workspace")
        if require_file and not path.is_file():
            raise ContractError(f"Workspace artifact is missing: {relative}")
        return path

    def _digest_or_missing(self, relative: str) -> str:
        path = self._resolve(relative, require_file=False)
        return sha256_file(path) if path.is_file() else "MISSING"

    def _record(self, action: str, payload: object) -> None:
        self.events.append(
            {
                "sequence": len(self.events),
                "action": action,
                "phase": self.phase,
                "payload_digest": canonical_sha256(payload),
            }
        )
        _write_json(self.workspace_root / "EVENT_LOG.json", {"events": self.events})

    def _verify_commitment(self) -> None:
        if not self.committed_snapshot or self.committed_record_sha256 is None:
            raise InvalidTransitionError("No v0.6 commitment exists")
        current = {
            relative: self._digest_or_missing(relative) for relative in self.committed_snapshot
        }
        if current != self.committed_snapshot:
            raise ContractError("A pre-reveal artifact or locked analysis input changed")
        record = self._resolve("COMMITMENT_RECORD.json")
        if sha256_file(record) != self.committed_record_sha256:
            raise ContractError("The commitment record changed")

    def commit_validation_plan(self) -> str:
        if self.phase != "working":
            raise InvalidTransitionError("commit_validation_plan may run only once")
        plan_path = self._resolve("submission/committed_validation_plan.json")
        plan = _read_object(plan_path)
        _validate_json(plan, self.package.schema_root / "committed_validation_plan.schema.json")
        if plan["scenario_id"] != self.package.scenario_id:
            raise ContractError("Validation plan scenario_id does not match")
        declared = [str(path) for path in plan["analysis_artifact_paths"]]
        if "model/locked_model.json" not in declared:
            raise ContractError("The locked model must be a declared analysis artifact")
        snapshot_paths = list(dict.fromkeys([*PRECOMMIT_ARTIFACTS, *declared]))
        self.committed_snapshot = {
            relative: self._digest_or_missing(relative) for relative in snapshot_paths
        }
        record = {
            "schema_version": "0.6",
            "scenario_id": self.package.scenario_id,
            "artifact_snapshot": self.committed_snapshot,
            "missing_at_commit": [
                path for path, digest in self.committed_snapshot.items() if digest == "MISSING"
            ],
        }
        _write_json(self.workspace_root / "COMMITMENT_RECORD.json", record)
        self.committed_record_sha256 = sha256_file(self.workspace_root / "COMMITMENT_RECORD.json")
        self.phase = "committed"
        digest = canonical_sha256(record)
        self._record("commit_validation_plan", {"commitment_digest": digest})
        return digest

    def reveal_validation(self) -> dict[str, Any]:
        if self.phase != "committed":
            raise InvalidTransitionError("reveal_validation requires a commitment")
        self._verify_commitment()
        target = self.workspace_root / "revealed"
        if target.exists():
            raise InvalidTransitionError("Validation was already revealed")
        shutil.copytree(self.package.sealed_root / "validation", target)
        self.phase = "validation_revealed"
        payload = {
            "revealed_paths": sorted(
                path.relative_to(self.workspace_root).as_posix()
                for path in target.rglob("*")
                if path.is_file()
            )
        }
        self._record("reveal_validation", payload)
        return payload

    def request_followup(self) -> dict[str, Any]:
        if self.phase != "validation_revealed":
            raise InvalidTransitionError("request_followup requires revealed validation")
        self._verify_commitment()
        results = _read_object(self._resolve("submission/validation_results.json"))
        memo_path = self._resolve("submission/resource_value_memo.json")
        memo = _read_object(memo_path)
        _validate_json(results, self.package.schema_root / "validation_results.schema.json")
        _validate_json(memo, self.package.schema_root / "resource_value_memo.schema.json")
        if (
            results["scenario_id"] != self.package.scenario_id
            or memo["scenario_id"] != self.package.scenario_id
        ):
            raise ContractError("Post-reveal artifact scenario_id does not match")
        selected = str(memo["selected_resource_id"])
        source = self.package.sealed_root / "resources" / selected
        if not source.is_dir():
            raise ContractError(f"Unknown follow-up resource: {selected}")
        target = self.workspace_root / "followup"
        if target.exists():
            raise InvalidTransitionError("Follow-up was already revealed")
        self.resource_memo_sha256 = sha256_file(memo_path)
        self.selected_resource = selected
        shutil.copytree(source, target)
        self.phase = "followup_revealed"
        payload = {
            "selected_resource": selected,
            "revealed_paths": sorted(
                path.relative_to(self.workspace_root).as_posix()
                for path in target.rglob("*")
                if path.is_file()
            ),
        }
        self._record("request_followup", payload)
        return payload

    def submit_diligence(self) -> dict[str, Any]:
        if self.phase != "followup_revealed":
            raise InvalidTransitionError("submit_diligence requires a follow-up reveal")
        self._verify_commitment()
        memo = self._resolve("submission/resource_value_memo.json")
        if sha256_file(memo) != self.resource_memo_sha256:
            raise ContractError("The resource choice changed after follow-up reveal")
        report = _read_object(self._resolve("submission/final_diligence_report.json"))
        _validate_json(report, self.package.schema_root / "final_diligence_report.schema.json")
        if report["scenario_id"] != self.package.scenario_id:
            raise ContractError("Final report scenario_id does not match")
        self.phase = "submitted"
        self.submitted = True
        self._record("submit_diligence", {"decision": report["decision"]})
        return {"accepted": True, "phase": self.phase, "decision": report["decision"]}


def _average(values: Iterable[float]) -> float:
    rows = list(values)
    return mean(rows) if rows else 0.0


def _credit(condition: Any) -> float:
    return 100.0 if bool(condition) else 0.0


def _numeric_credit(expected: float, observed: Any, tolerance: float) -> float:
    try:
        difference = abs(float(expected) - float(observed))
    except (TypeError, ValueError):
        return 0.0
    if difference <= tolerance:
        return 100.0
    return max(0.0, 100.0 * (1 - (difference - tolerance) / (4 * tolerance)))


def _normal(value: Any) -> str:
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def _reference_exists(root: Path, reference: str) -> bool:
    raw = str(reference).split("#", 1)[0].strip().rstrip("/")
    relative = Path(raw)
    if not raw or relative.is_absolute() or ".." in relative.parts:
        return False
    candidate = (root / relative).resolve()
    return root == candidate or root in candidate.parents and candidate.exists()


def _evidence_credit(root: Path, references: Iterable[Any]) -> float:
    rows = list(references)
    if not rows:
        return 0.0
    return 100.0 * sum(_reference_exists(root, str(row)) for row in rows) / len(rows)


def _read_artifact(path: Path) -> tuple[Any | None, str | None]:
    if not path.is_file():
        return None, "missing"
    try:
        if path.suffix == ".json":
            return json.loads(path.read_text(encoding="utf-8")), None
        with path.open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle)), None
    except (OSError, json.JSONDecodeError, csv.Error) as exc:
        return None, f"parse_error:{type(exc).__name__}"


def _schema_error(package: V06Package, relative: str, value: Any) -> str | None:
    schema_name = SCHEMA_BY_ARTIFACT.get(relative)
    if schema_name is None or not isinstance(value, dict):
        return None
    from jsonschema import Draft202012Validator

    schema = _read_object(package.schema_root / schema_name)
    errors = sorted(Draft202012Validator(schema).iter_errors(value), key=lambda row: list(row.path))
    return errors[0].message if errors else None


def _required_csv_columns(relative: str) -> set[str]:
    return {
        "submission/cohort_inventory.csv": {
            "cohort_id",
            "role",
            "row_count",
            "patient_count",
            "drug",
            "endpoint",
            "timepoint",
            "platform",
            "outcome_visibility",
            "eligibility_status",
            "evidence_refs",
        },
        "submission/patient_visit_map.csv": {
            "sample_id",
            "reported_patient_id",
            "canonical_patient_id",
            "fingerprint_group",
            "visit_label",
            "baseline_eligible",
            "dependence_cluster",
            "linkage_status",
            "exclusion_reason",
            "evidence_refs",
        },
        "submission/reproduction_predictions.csv": {
            "sample_id",
            "reference_probability",
            "reproduced_probability",
            "absolute_error",
            "model_sha256",
        },
    }.get(relative, set())


def _csv_columns_ok(relative: str, value: Any) -> bool:
    if not isinstance(value, list) or not value or not isinstance(value[0], dict):
        return False
    return _required_csv_columns(relative) <= set(value[0])


def _inventory_score(package: V06Package, rows: Any) -> float:
    if not _csv_columns_ok(ALL_ARTIFACTS[0], rows):
        return 0.0
    root = package.workspace_root
    observed = {str(row.get("cohort_id")): row for row in rows}
    registry = {row["cohort_id"]: row for row in _read_csv(root / "case/cohort_registry.csv")}
    internal = _read_csv(root / "data/internal_predictions.csv")
    external = _read_csv(root / "data/external_locked_predictions.csv")
    expected_counts = {
        "DISCOVERY-01": (118, 118),
        "INTERNAL-01": (len(internal), len({row["fingerprint_group"] for row in internal})),
        "EXTERNAL-01": (len(external), len({row["fingerprint_group"] for row in external})),
    }
    accounted = set(observed) == set(registry)
    roles = all(
        _normal(observed.get(cohort, {}).get("role")) == _normal(source["role"])
        for cohort, source in registry.items()
    )
    biological = all(
        all(
            str(observed.get(cohort, {}).get(field)) == str(source[field])
            for field in ("drug", "endpoint", "platform")
        )
        for cohort, source in registry.items()
    )
    counts = all(
        int(float(observed.get(cohort, {}).get("row_count", -1))) == expected[0]
        and int(float(observed.get(cohort, {}).get("patient_count", -1))) == expected[1]
        for cohort, expected in expected_counts.items()
    )
    evidence = _average(
        _evidence_credit(root, str(row.get("evidence_refs", "")).split(";")) for row in rows
    )
    return _average(
        [_credit(accounted), _credit(roles), _credit(biological), _credit(counts), evidence]
    )


def _provenance_score(package: V06Package, value: Any) -> float:
    if not isinstance(value, dict):
        return 0.0
    return _average(
        [
            _credit(value.get("scenario_id") == package.scenario_id),
            _credit(value.get("manifest_assets_checked") is True),
            _credit(value.get("outcomes_sealed_before_commit") is True),
            _credit(value.get("sponsor_attestations_treated_as_ground_truth") is False),
            _credit("research" in _normal(value.get("licence_scope"))),
            _credit(len(value.get("findings") or []) >= 1),
            _evidence_credit(package.workspace_root, value.get("evidence_refs") or []),
        ]
    )


def _identity_score(package: V06Package, rows: Any) -> float:
    relative = "submission/patient_visit_map.csv"
    if not _csv_columns_ok(relative, rows):
        return 0.0
    source = [
        *_read_csv(package.workspace_root / "data/internal_predictions.csv"),
        *_read_csv(package.workspace_root / "data/external_locked_predictions.csv"),
    ]
    by_sample = {str(row.get("sample_id")): row for row in rows}
    all_rows = set(by_sample) == {str(row["sample_id"]) for row in source}
    patient_identity = all(
        str(by_sample.get(str(row["sample_id"]), {}).get("canonical_patient_id"))
        in {str(row["fingerprint_group"]), str(row["fingerprint_group"])[3:]}
        for row in source
    )
    dependence = all(
        str(by_sample.get(str(row["sample_id"]), {}).get("dependence_cluster"))
        in {str(row["fingerprint_group"]), str(row["fingerprint_group"])[3:]}
        for row in source
    )
    blocked = package.private_scenario["states"]["identity"] == "blocked"
    alias_samples = {
        str(row["sample_id"])
        for row in source
        if str(row["reported_patient_id"]).endswith("-ALIAS")
    }
    containment = (
        all(
            _normal(by_sample[sample].get("linkage_status"))
            in {"unresolved", "conditional", "reconciled_by_fingerprint"}
            for sample in alias_samples
        )
        if blocked
        else all(
            _normal(row.get("linkage_status")) not in {"ignored", "independent_row"} for row in rows
        )
    )
    evidence = _average(
        _evidence_credit(package.workspace_root, str(row.get("evidence_refs", "")).split(";"))
        for row in rows
    )
    return _average(
        [
            _credit(all_rows),
            _credit(patient_identity),
            _credit(dependence),
            _credit(containment),
            evidence,
        ]
    )


def _endpoint_score(package: V06Package, value: Any) -> float:
    if not isinstance(value, dict):
        return 0.0
    scenario = package.private_scenario
    endpoint_state = str(scenario["states"]["endpoint"])
    expected_ambiguity = "blocked" if endpoint_state == "blocked" else endpoint_state
    transfer_expected = (
        "mismatched"
        if scenario["scenario_class"] == "endpoint_drug_platform_transfer_failure"
        else "matched"
    )
    labels = value.get("label_sources") or []
    return _average(
        [
            _credit(value.get("scenario_id") == package.scenario_id),
            _credit(_normal(value.get("target_endpoint")) == "week_6_clinical_response"),
            _credit("6" in str(value.get("assessment_timepoint"))),
            _credit(
                {"reviewer_a", "reviewer_b", "extraction_label"} <= {_normal(row) for row in labels}
            ),
            _credit(_normal(value.get("ambiguity_status")) == expected_ambiguity),
            _credit(_normal(value.get("endpoint_transfer_status")) == transfer_expected),
            _credit(bool(value.get("sensitivity_plan"))),
            _evidence_credit(package.workspace_root, value.get("evidence_refs") or []),
        ]
    )


def _preprocessing_score(package: V06Package, value: Any) -> float:
    if not isinstance(value, dict):
        return 0.0
    leaky = package.private_scenario["states"]["preprocessing"] == "blocked"
    transfer = package.private_scenario["states"]["transport"] == "blocked"
    expected_leakage = "blocked" if leaky else "clear"
    expected_transfer = "mismatched" if transfer else "matched"
    return _average(
        [
            _credit(value.get("scenario_id") == package.scenario_id),
            _credit(len(value.get("steps") or []) >= 4),
            _credit(value.get("outcomes_used_during_fit") is leaky),
            _credit(value.get("validation_data_used_to_fit_transforms") is leaky),
            _credit(_normal(value.get("leakage_status")) == expected_leakage),
            _credit(_normal(value.get("platform_transfer_status")) == expected_transfer),
            _evidence_credit(package.workspace_root, value.get("evidence_refs") or []),
        ]
    )


def _reproduction_score(package: V06Package, rows: Any) -> float:
    relative = "submission/reproduction_predictions.csv"
    if not _csv_columns_ok(relative, rows):
        return 0.0
    reference = {
        row["sample_id"]: float(row["locked_probability"])
        for row in _read_csv(package.workspace_root / "model/reference_predictions.csv")
    }
    observed = {str(row.get("sample_id")): row for row in rows}
    identity = set(observed) == set(reference)
    probabilities = all(
        _numeric_credit(expected, observed.get(sample, {}).get("reproduced_probability"), 1e-8)
        == 100
        for sample, expected in reference.items()
    )
    errors = all(
        _numeric_credit(
            abs(
                float(row.get("reference_probability", 0))
                - float(row.get("reproduced_probability", 1))
            ),
            row.get("absolute_error"),
            1e-8,
        )
        == 100
        for row in rows
    )
    model_hash = sha256_file(package.workspace_root / "model/locked_model.json")
    hashes = all(str(row.get("model_sha256")) == model_hash for row in rows)
    return _average([_credit(identity), _credit(probabilities), _credit(errors), _credit(hashes)])


def _plan_score(
    package: V06Package,
    value: Any,
    committed: bool,
    decision_contract: dict[str, Any],
) -> float:
    if not isinstance(value, dict):
        return 0.0
    scenario = package.private_scenario
    metrics = value.get("metric_families") or []
    coverage = _average(
        _credit(value.get(field) is True)
        for field in (
            "reports_discrimination",
            "reports_uncertainty",
            "reports_calibration",
            "reports_decision_utility",
        )
    )
    preproc_safe = scenario["states"]["preprocessing"] != "blocked"
    rule = value.get("decision_rule") or {}
    rule_score = _average(
        _numeric_credit(decision_contract[name], rule.get(name), 0.01)
        for name in (
            "minimum_auc",
            "minimum_auc_ci_low",
            "maximum_brier",
            "minimum_net_benefit",
        )
    )
    return _average(
        [
            _credit(value.get("scenario_id") == package.scenario_id),
            _credit(value.get("dependence_preserved") is True),
            _credit(value.get("uncertainty_preserves_dependence") is True),
            _credit(value.get("preprocessing_outcome_blind") is preproc_safe),
            coverage,
            _credit(len(metrics) >= 3),
            rule_score,
            _credit(len(value.get("live_hypotheses") or []) >= 2),
            _credit(value.get("pre_reveal_decision") == scenario["initial_decision"]),
            _credit("model/locked_model.json" in (value.get("analysis_artifact_paths") or [])),
            _credit(committed),
            _evidence_credit(package.workspace_root, value.get("evidence_refs") or []),
        ]
    )


def _metric_score(expected: dict[str, float], observed: Any) -> float:
    values = observed if isinstance(observed, dict) else {}
    return _average(
        _numeric_credit(expected[name], values.get(name), METRIC_TOLERANCES[name])
        for name in METRIC_NAMES
    )


def _status_score(expected: dict[str, str], observed: Any) -> float:
    values = observed if isinstance(observed, dict) else {}
    return _average(_credit(_normal(values.get(key)) == status) for key, status in expected.items())


def _validation_score(package: V06Package, value: Any) -> float:
    if not isinstance(value, dict):
        return 0.0
    try:
        expected_metrics = compute_v05_metrics(package.workspace_root, followup=False)
    except (ContractError, ValueError):
        expected_metrics = {name: 0.0 for name in METRIC_NAMES}
    preproc_safe = package.private_scenario["states"]["preprocessing"] != "blocked"
    return _average(
        [
            _credit(value.get("scenario_id") == package.scenario_id),
            _credit(value.get("committed_plan_honoured") is True),
            _credit(value.get("dependence_preserved") is True),
            _credit(value.get("preprocessing_outcome_blind") is preproc_safe),
            _metric_score(expected_metrics, value.get("metrics")),
            _status_score(
                expected_initial_claim_statuses(package.private_scenario),
                value.get("claim_statuses"),
            ),
            _credit(
                value.get("provisional_decision") == package.private_scenario["initial_decision"]
            ),
            _credit(bool(str(value.get("dominant_uncertainty", "")).strip())),
            _evidence_credit(package.workspace_root, value.get("evidence_refs") or []),
        ]
    )


def _resource_score(package: V06Package, value: Any) -> float:
    if not isinstance(value, dict):
        return 0.0
    selected = str(value.get("selected_resource_id"))
    utility = float(package.private_scenario["resource_utilities"].get(selected, 0.0))
    comparisons = value.get("resource_comparisons") or []
    compared_ids = {str(row.get("resource_id")) for row in comparisons if isinstance(row, dict)}
    expected_ids = set(package.private_scenario["resource_utilities"])
    expected_effect = expected_intervention_effect(package.private_scenario, selected)
    return _average(
        [
            _credit(value.get("scenario_id") == package.scenario_id),
            _credit(len(value.get("live_hypotheses") or []) >= 2),
            100.0 * len(compared_ids & expected_ids) / len(expected_ids),
            100.0 * utility,
            _credit(value.get("expected_effect") == expected_effect),
            _credit(bool(str(value.get("smallest_discriminating_action", "")).strip())),
            _evidence_credit(package.workspace_root, value.get("evidence_refs") or []),
        ]
    )


def _final_score(package: V06Package, value: Any, selected: str) -> float:
    if not isinstance(value, dict):
        return 0.0
    scenario = package.private_scenario
    belief = value.get("belief_update") or {}
    next_action = value.get("smallest_next_action") or {}
    supported_refs = [
        reference
        for claim in value.get("supported_claims") or []
        if isinstance(claim, dict)
        for reference in claim.get("evidence_refs") or []
    ]
    return _average(
        [
            _credit(value.get("scenario_id") == package.scenario_id),
            _credit(value.get("decision") == expected_final_decision(scenario, selected)),
            _status_score(
                expected_final_claim_statuses(scenario, selected), value.get("claim_statuses")
            ),
            _credit(
                value.get("intervention_effect") == expected_intervention_effect(scenario, selected)
            ),
            _credit(belief.get("direction") == expected_belief_direction(scenario, selected)),
            _credit(next_action.get("class") == expected_next_action_class(scenario, selected)),
            _credit(len(value.get("limitations") or []) >= 1),
            _credit(len(value.get("supported_claims") or []) >= 1),
            _evidence_credit(
                package.workspace_root,
                [*(value.get("evidence_refs") or []), *supported_refs],
            ),
        ]
    )


@dataclass(frozen=True, slots=True)
class V06Grade:
    completed_artifact_quality: float
    artifact_coverage: float
    coverage_adjusted_scientific_score: float
    reliability_inclusive_score: float
    artifact_scores: dict[str, float]
    artifact_states: dict[str, str]
    family_scores: dict[str, float]
    capability_scores: dict[str, float]
    first_substantive_divergence: str | None
    downstream_artifacts_at_risk: list[str]
    selected_resource: str
    decision_policy_score: float
    observed_initial_decision: str | None
    observed_final_decision: str | None
    observed_intervention_effect: str | None
    process_annotations: list[dict[str, Any]]
    scientific_failure_annotations: list[dict[str, Any]]
    completion_accepted: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "completed_artifact_quality": self.completed_artifact_quality,
            "artifact_coverage": self.artifact_coverage,
            "coverage_adjusted_scientific_score": self.coverage_adjusted_scientific_score,
            "reliability_inclusive_score": self.reliability_inclusive_score,
            "artifact_scores": self.artifact_scores,
            "artifact_states": self.artifact_states,
            "family_scores": self.family_scores,
            "capability_scores": self.capability_scores,
            "first_substantive_divergence": self.first_substantive_divergence,
            "downstream_artifacts_at_risk": self.downstream_artifacts_at_risk,
            "selected_resource": self.selected_resource,
            "decision_policy_score": self.decision_policy_score,
            "observed_initial_decision": self.observed_initial_decision,
            "observed_final_decision": self.observed_final_decision,
            "observed_intervention_effect": self.observed_intervention_effect,
            "process_annotations": self.process_annotations,
            "scientific_failure_annotations": self.scientific_failure_annotations,
            "completion_accepted": self.completion_accepted,
        }


def grade_v06(
    project_root: Path,
    package: V06Package,
    *,
    selected_resource: str | None = None,
    commitment_immutable: bool = False,
    completion_accepted: bool = False,
) -> V06Grade:
    config = load_v06_config(project_root)
    root = package.workspace_root
    selected = selected_resource or "none"
    values: dict[str, Any] = {}
    parsed: dict[str, bool] = {}
    process: list[dict[str, Any]] = []
    for relative in ALL_ARTIFACTS:
        value, error = _read_artifact(root / relative)
        values[relative] = value
        parsed[relative] = error is None
        if error:
            process.append({"tag": error, "artifact": relative, "evidence": relative})
            continue
        schema_error = _schema_error(package, relative, value)
        if schema_error:
            process.append(
                {
                    "tag": "schema_interface_error",
                    "artifact": relative,
                    "evidence": schema_error,
                }
            )
        serialized = json.dumps(value, sort_keys=True).lower()
        if any(marker in serialized for marker in ("todo", "lorem ipsum", "placeholder")):
            process.append(
                {"tag": "synthetic_or_placeholder_work", "artifact": relative, "evidence": relative}
            )
    scores = {
        "A01": _inventory_score(package, values[ALL_ARTIFACTS[0]]),
        "A02": _provenance_score(package, values[ALL_ARTIFACTS[1]]),
        "A03": _identity_score(package, values[ALL_ARTIFACTS[2]]),
        "A04": _endpoint_score(package, values[ALL_ARTIFACTS[3]]),
        "A05": _preprocessing_score(package, values[ALL_ARTIFACTS[4]]),
        "A06": _reproduction_score(package, values[ALL_ARTIFACTS[5]]),
        "A07": _plan_score(
            package,
            values[ALL_ARTIFACTS[6]],
            commitment_immutable,
            config["decision_contract"],
        ),
        "A08": _validation_score(package, values[ALL_ARTIFACTS[7]]),
        "A09": _resource_score(package, values[ALL_ARTIFACTS[8]]),
        "A10": _final_score(package, values[ALL_ARTIFACTS[9]], selected),
    }
    scores = {name: round(min(100.0, max(0.0, value)), 6) for name, value in scores.items()}
    artifact_states = {}
    for index, (artifact_id, score) in enumerate(scores.items()):
        if not parsed[ALL_ARTIFACTS[index]]:
            state = "missing" if values[ALL_ARTIFACTS[index]] is None else "invalid"
        elif score >= 90:
            state = "valid"
        elif score >= 50:
            state = "conditionally_valid"
        else:
            state = "invalid"
        artifact_states[artifact_id] = state
    completed_scores = [
        score for index, score in enumerate(scores.values()) if parsed[ALL_ARTIFACTS[index]]
    ]
    quality = _average(completed_scores)
    coverage = sum(parsed.values()) / len(ALL_ARTIFACTS)
    weights = {row["id"]: float(row["weight"]) for row in config["artifacts"]}
    adjusted = sum(weights[name] * scores[name] / 100 for name in scores)
    first = next(
        (name for name, state in artifact_states.items() if state != "valid"),
        None,
    )
    metadata = {row["id"]: row for row in config["artifacts"]}
    at_risk = list(metadata[first]["downstream_at_risk"]) if first else []
    artifact_paths = {
        f"A{index:02d}": relative for index, relative in enumerate(ALL_ARTIFACTS, start=1)
    }
    scientific = []
    for name, state in artifact_states.items():
        if state == "valid":
            continue
        scientific.append(
            {
                "artifact": name,
                "artifact_path": artifact_paths[name],
                "artifact_state": state,
                "artifact_score": scores[name],
                "properties_evaluated": metadata[name]["invariants"],
                "professional_consequence": metadata[name]["consequence_of_error"],
                "paired_remedy": metadata[name]["paired_remedy"],
                "remedy_intervention_class": metadata[name][
                    "remedy_intervention_class"
                ],
                "downstream_at_risk": metadata[name]["downstream_at_risk"],
            }
        )
    family_scores = {metadata[name]["family"]: score for name, score in scores.items()}
    capabilities = {
        name: round(_average(scores[artifact] for artifact in artifacts), 6)
        for name, artifacts in V06_CAPABILITY_MAP.items()
    }
    validation_value = (
        values[ALL_ARTIFACTS[7]] if isinstance(values[ALL_ARTIFACTS[7]], dict) else {}
    )
    resource_value = values[ALL_ARTIFACTS[8]] if isinstance(values[ALL_ARTIFACTS[8]], dict) else {}
    final_value = values[ALL_ARTIFACTS[9]] if isinstance(values[ALL_ARTIFACTS[9]], dict) else {}
    belief_value = final_value.get("belief_update") or {}
    next_value = final_value.get("smallest_next_action") or {}
    decision_policy_score = _average(
        [
            _credit(
                validation_value.get("provisional_decision")
                == package.private_scenario["initial_decision"]
            ),
            100.0 * float(package.private_scenario["resource_utilities"].get(selected, 0.0)),
            _credit(
                resource_value.get("expected_effect")
                == expected_intervention_effect(package.private_scenario, selected)
            ),
            _credit(
                final_value.get("decision")
                == expected_final_decision(package.private_scenario, selected)
            ),
            _credit(
                belief_value.get("direction")
                == expected_belief_direction(package.private_scenario, selected)
            ),
            _credit(
                next_value.get("class")
                == expected_next_action_class(package.private_scenario, selected)
            ),
        ]
    )
    return V06Grade(
        completed_artifact_quality=round(quality, 6),
        artifact_coverage=round(100 * coverage, 6),
        coverage_adjusted_scientific_score=round(adjusted, 6),
        reliability_inclusive_score=round(adjusted if completion_accepted else 0.0, 6),
        artifact_scores=scores,
        artifact_states=artifact_states,
        family_scores=family_scores,
        capability_scores=capabilities,
        first_substantive_divergence=first,
        downstream_artifacts_at_risk=at_risk,
        selected_resource=selected,
        decision_policy_score=round(decision_policy_score, 6),
        observed_initial_decision=validation_value.get("provisional_decision"),
        observed_final_decision=final_value.get("decision"),
        observed_intervention_effect=final_value.get("intervention_effect"),
        process_annotations=process,
        scientific_failure_annotations=scientific,
        completion_accepted=completion_accepted,
    )


def _cohort_evidence_reference(cohort_id: str) -> str:
    return {
        "DISCOVERY-01": "model/predictor_manifest.json",
        "INTERNAL-01": "data/internal_predictions.csv",
        "EXTERNAL-01": "data/external_locked_predictions.csv",
    }[cohort_id]


def reference_v06_precommit(package: V06Package, project_root: Path) -> None:
    """Write the seven pre-reveal artifacts for an expert-equivalent trajectory."""

    root = package.workspace_root
    scenario = package.private_scenario
    config = load_v06_config(project_root)
    registry = _read_csv(root / "case/cohort_registry.csv")
    internal = _read_csv(root / "data/internal_predictions.csv")
    external = _read_csv(root / "data/external_locked_predictions.csv")
    source_rows = {
        "INTERNAL-01": internal,
        "EXTERNAL-01": external,
    }
    inventory = []
    for row in registry:
        cohort = row["cohort_id"]
        rows = source_rows.get(cohort)
        row_count = len(rows) if rows is not None else 118
        patient_count = (
            len({item["fingerprint_group"] for item in rows}) if rows is not None else 118
        )
        inventory.append(
            {
                "cohort_id": cohort,
                "role": row["role"],
                "row_count": row_count,
                "patient_count": patient_count,
                "drug": row["drug"],
                "endpoint": row["endpoint"],
                "timepoint": "baseline_to_week_6",
                "platform": row["platform"],
                "outcome_visibility": row["outcomes_visible"],
                "eligibility_status": (
                    "conditional"
                    if cohort == "EXTERNAL-01" and scenario["states"]["transport"] == "blocked"
                    else "eligible_for_declared_role"
                ),
                "evidence_refs": _cohort_evidence_reference(cohort),
            }
        )
    _write_csv(root / ALL_ARTIFACTS[0], inventory)
    _write_json(
        root / ALL_ARTIFACTS[1],
        {
            "scenario_id": package.scenario_id,
            "manifest_assets_checked": True,
            "outcomes_sealed_before_commit": True,
            "sponsor_attestations_treated_as_ground_truth": False,
            "licence_scope": "benchmark_research_only",
            "findings": [
                {
                    "finding": "Sponsor attestations require independent reconciliation.",
                    "decision_effect": "No attestation alone establishes evidence validity.",
                }
            ],
            "evidence_refs": [
                "case/data_room_manifest.json",
                "case/sponsor_attestations.json",
                "case/cohort_registry.csv",
            ],
        },
    )
    identity_blocked = scenario["states"]["identity"] == "blocked"
    identity_rows = []
    for row in [*internal, *external]:
        alias = str(row["reported_patient_id"]).endswith("-ALIAS")
        identity_rows.append(
            {
                "sample_id": row["sample_id"],
                "reported_patient_id": row["reported_patient_id"],
                "canonical_patient_id": row["fingerprint_group"],
                "fingerprint_group": row["fingerprint_group"],
                "visit_label": f"week_{row['visit_week']}",
                "baseline_eligible": "yes",
                "dependence_cluster": row["fingerprint_group"],
                "linkage_status": (
                    "unresolved" if identity_blocked and alias else "reconciled_by_fingerprint"
                ),
                "exclusion_reason": "" if not alias else "identity_linkage_requires_source_record",
                "evidence_refs": (
                    "data/internal_predictions.csv"
                    if str(row["sample_id"]).startswith("INTERNAL")
                    else "data/external_locked_predictions.csv"
                ),
            }
        )
    _write_csv(root / ALL_ARTIFACTS[2], identity_rows)
    transfer = scenario["scenario_class"] == "endpoint_drug_platform_transfer_failure"
    endpoint_state = str(scenario["states"]["endpoint"])
    _write_json(
        root / ALL_ARTIFACTS[3],
        {
            "scenario_id": package.scenario_id,
            "target_endpoint": "week_6_clinical_response",
            "assessment_timepoint": "week_6",
            "label_sources": ["extraction_label", "reviewer_a", "reviewer_b"],
            "ambiguity_status": "blocked" if endpoint_state == "blocked" else endpoint_state,
            "endpoint_transfer_status": "mismatched" if transfer else "matched",
            "sensitivity_plan": {
                "compare_reviewer_labels": True,
                "do_not_collapse_clinical_response_and_remission": True,
            },
            "evidence_refs": [
                "case/endpoint_definition.json",
                "case/cohort_registry.csv",
                "case/intended_use.json",
            ],
        },
    )
    leaky = scenario["states"]["preprocessing"] == "blocked"
    _write_json(
        root / ALL_ARTIFACTS[4],
        {
            "scenario_id": package.scenario_id,
            "steps": _read_csv(root / "case/preprocessing_history.csv"),
            "outcomes_used_during_fit": leaky,
            "validation_data_used_to_fit_transforms": leaky,
            "leakage_status": "blocked" if leaky else "clear",
            "platform_transfer_status": "mismatched" if transfer else "matched",
            "evidence_refs": [
                "case/preprocessing_history.csv",
                "model/predictor_manifest.json",
                "case/cohort_registry.csv",
            ],
        },
    )
    reference_rows = _read_csv(root / "model/reference_predictions.csv")
    model_hash = sha256_file(root / "model/locked_model.json")
    _write_csv(
        root / ALL_ARTIFACTS[5],
        [
            {
                "sample_id": row["sample_id"],
                "reference_probability": row["locked_probability"],
                "reproduced_probability": row["locked_probability"],
                "absolute_error": 0.0,
                "model_sha256": model_hash,
            }
            for row in reference_rows
        ],
    )
    decision = config["decision_contract"]
    _write_json(
        root / ALL_ARTIFACTS[6],
        {
            "scenario_id": package.scenario_id,
            "primary_estimand": (
                "patient-level external discrimination, calibration, and threshold utility"
            ),
            "analysis_unit": "patient",
            "dependence_preserved": True,
            "uncertainty_method": "patient-cluster bootstrap preserving site where feasible",
            "uncertainty_preserves_dependence": True,
            "preprocessing_outcome_blind": not leaky,
            "metric_families": [
                "discrimination_auc",
                "uncertainty_interval",
                "calibration_brier",
                "decision_utility_net_benefit",
                "label_sensitivity",
            ],
            "reports_discrimination": True,
            "reports_uncertainty": True,
            "reports_calibration": True,
            "reports_decision_utility": True,
            "decision_rule": {
                "minimum_auc": decision["minimum_auc"],
                "minimum_auc_ci_low": decision["minimum_auc_ci_low"],
                "maximum_brier": decision["maximum_brier"],
                "minimum_net_benefit": decision["minimum_net_benefit"],
            },
            "live_hypotheses": [
                {"id": "H1", "description": str(scenario["scenario_class"])},
                {"id": "H2", "description": "stable transportable signal"},
            ],
            "pre_reveal_decision": scenario["initial_decision"],
            "analysis_artifact_paths": [
                "model/locked_model.json",
                "model/predictor_manifest.json",
                "data/external_locked_predictions.csv",
                "case/preprocessing_history.csv",
                *ALL_ARTIFACTS[:6],
            ],
            "evidence_refs": [
                *ALL_ARTIFACTS[:6],
                "case/metric_contract.json",
            ],
        },
    )


def reference_v06_post_validation(package: V06Package) -> None:
    root = package.workspace_root
    scenario = package.private_scenario
    _write_json(
        root / ALL_ARTIFACTS[7],
        {
            "scenario_id": package.scenario_id,
            "committed_plan_honoured": True,
            "dependence_preserved": True,
            "preprocessing_outcome_blind": scenario["states"]["preprocessing"] != "blocked",
            "metrics": compute_v05_metrics(root, followup=False),
            "claim_statuses": expected_initial_claim_statuses(scenario),
            "provisional_decision": scenario["initial_decision"],
            "dominant_uncertainty": scenario["scenario_class"],
            "evidence_refs": [
                "submission/committed_validation_plan.json",
                "data/external_locked_predictions.csv",
                "revealed/external_outcomes.csv",
                "case/metric_contract.json",
            ],
        },
    )
    comparisons = [
        {
            "resource_id": resource_id,
            "relative_decision_value": utility,
            "hypothesis_distinguished": scenario["scenario_class"],
        }
        for resource_id, utility in scenario["resource_utilities"].items()
    ]
    _write_json(
        root / ALL_ARTIFACTS[8],
        {
            "scenario_id": package.scenario_id,
            "live_hypotheses": [
                {"id": "H1", "description": scenario["scenario_class"]},
                {"id": "H2", "description": "stable transportable signal"},
            ],
            "resource_comparisons": comparisons,
            "selected_resource_id": scenario["optimal_resource"],
            "expected_effect": expected_intervention_effect(
                scenario, str(scenario["optimal_resource"])
            ),
            "smallest_discriminating_action": (
                "Select the least costly evidence that separates the live hypotheses."
            ),
            "evidence_refs": [
                "submission/validation_results.json",
                "resources/resource_catalog.json",
            ],
        },
    )


def reference_v06_final(package: V06Package, selected: str) -> None:
    root = package.workspace_root
    scenario = package.private_scenario
    direction = expected_belief_direction(scenario, selected)
    _write_json(
        root / ALL_ARTIFACTS[9],
        {
            "scenario_id": package.scenario_id,
            "decision": expected_final_decision(scenario, selected),
            "confidence": 0.76,
            "claim_statuses": expected_final_claim_statuses(scenario, selected),
            "belief_update": {
                "prior_confidence": 0.50,
                "posterior_confidence": {"increase": 0.72, "decrease": 0.28, "unchanged": 0.50}[
                    direction
                ],
                "direction": direction,
                "evidence_that_changed_belief": ["followup"],
            },
            "intervention_effect": expected_intervention_effect(scenario, selected),
            "smallest_next_action": {
                "class": expected_next_action_class(scenario, selected),
                "description": "Take only the next action justified by the remaining blocker.",
            },
            "limitations": [
                "Controlled research diligence does not establish prospective clinical utility."
            ],
            "supported_claims": [
                {
                    "claim": "The decision is bounded by the validated evidence chain.",
                    "status": "supported",
                    "evidence_refs": [
                        "submission/validation_results.json",
                        "submission/resource_value_memo.json",
                        "followup",
                    ],
                }
            ],
            "evidence_refs": [
                "submission/validation_results.json",
                "submission/resource_value_memo.json",
                "followup",
            ],
        },
    )


def run_reference_v06_episode(
    project_root: Path,
    scenario_id: str,
    *,
    output_root: Path,
    partition: str = "development",
    replace: bool = False,
) -> tuple[V06Package, V06Environment, V06Grade]:
    package = V06Builder(project_root).build(
        scenario_id, output_root=output_root, partition=partition, replace=replace
    )
    environment = V06Environment(package)
    reference_v06_precommit(package, project_root)
    environment.commit_validation_plan()
    environment.reveal_validation()
    reference_v06_post_validation(package)
    environment.request_followup()
    selected = str(environment.selected_resource or "none")
    reference_v06_final(package, selected)
    environment.submit_diligence()
    grade = grade_v06(
        project_root,
        package,
        selected_resource=selected,
        commitment_immutable=True,
        completion_accepted=True,
    )
    _write_json(package.workspace_root / "REFERENCE_GRADE.json", grade.to_dict())
    return package, environment, grade

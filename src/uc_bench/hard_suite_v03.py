"""v0.3 hard suite with irreversible, causal resource selection."""

from __future__ import annotations

import math
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError, ContractError, InvalidTransitionError
from uc_bench.hard_suite import (
    _FAILURE_TO_EVIDENCE,
    _FAILURE_TO_EXPERIMENT,
    _FAILURE_TO_METRICS,
    _FAILURE_TO_RESOURCE,
    _METRIC_TOLERANCES,
    HardSuiteBuilder,
    _auc,
    _binary_phi,
    _diagnoses,
    _numeric_credit,
    _read_csv,
    _read_object,
    _validate_schema,
    _write_json,
)
from uc_bench.hashing import canonical_sha256, sha256_file

V03_CONFIG_PATH = Path("configs/hard_suite_v03.json")
V03_HELDOUT_PATH = Path("grader_private/hard_suite_v03_heldout.json")
_FACTORIAL_CONDITIONS = (
    "unmatched",
    "endpoint_matched",
    "platform_matched",
    "drug_matched",
    "all_matched",
)


def load_v03_config(project_root: Path) -> dict[str, Any]:
    return _read_object(project_root.resolve() / V03_CONFIG_PATH)


def iter_v03_variants(
    project_root: Path, *, partition: str = "development"
) -> list[dict[str, Any]]:
    root = project_root.resolve()
    config = load_v03_config(root)
    resources_by_family = {
        str(pair["family_id"]): list(pair["resources"]) for pair in config["development_pairs"]
    }
    output = []
    if partition == "development":
        pairs = config["development_pairs"]
        for pair in pairs:
            shared = {
                key: pair[key]
                for key in (
                    "family_id",
                    "failure_mode",
                    "public_source_variant_id",
                    "resolved_evidence_variant_id",
                    "correct_resource_id",
                    "resources",
                )
            }
            for role in ("control", "treated"):
                record = pair[role]
                output.append(
                    {
                        **shared,
                        "variant_id": record["variant_id"],
                        "pair_role": role,
                        "correct_resource_available": bool(record["correct_resource_available"]),
                        "expected_resource_id": (
                            str(pair["correct_resource_id"])
                            if record["correct_resource_available"]
                            else "none"
                        ),
                    }
                )
        return output
    if partition == "heldout":
        heldout = _read_object(root / V03_HELDOUT_PATH)
        for pair in heldout["pairs"]:
            shared = {
                **pair,
                "resources": resources_by_family[str(pair["family_id"])],
            }
            for role, key in (
                ("control", "control_variant_id"),
                ("treated", "treated_variant_id"),
            ):
                available = role == "treated"
                output.append(
                    {
                        **shared,
                        "variant_id": pair[key],
                        "pair_role": role,
                        "correct_resource_available": available,
                        "expected_resource_id": (
                            str(pair["correct_resource_id"]) if available else "none"
                        ),
                    }
                )
        return output
    raise ConfigurationError(f"Unknown v0.3 partition: {partition}")


def load_v03_variant(
    project_root: Path, variant_id: str, *, partition: str = "development"
) -> dict[str, Any]:
    matches = [
        row
        for row in iter_v03_variants(project_root, partition=partition)
        if row["variant_id"] == variant_id
    ]
    if len(matches) != 1:
        raise ConfigurationError(
            f"Expected one v0.3 {partition} variant {variant_id}; found {len(matches)}"
        )
    return matches[0]


def validate_v03_config(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    config = load_v03_config(root)
    pairs = config.get("development_pairs")
    if not isinstance(pairs, list) or len(pairs) != 5:
        raise ContractError("v0.3 requires five intervention pairs")
    weights = config.get("scoring")
    if not isinstance(weights, dict) or not math.isclose(sum(weights.values()), 1.0):
        raise ContractError("v0.3 score weights must sum to one")
    variant_ids: set[str] = set()
    for pair in pairs:
        resources = pair.get("resources")
        if not isinstance(resources, list) or len(resources) != 3:
            raise ContractError(f"Each v0.3 family needs three resources: {pair['family_id']}")
        resource_ids = {str(row["resource_id"]) for row in resources}
        if resource_ids != {"R1", "R2", "R3"}:
            raise ContractError(f"Resource IDs must be R1/R2/R3: {pair['family_id']}")
        if pair["correct_resource_id"] not in resource_ids:
            raise ContractError(f"Unknown correct resource: {pair['family_id']}")
        for role in ("control", "treated"):
            variant_id = str(pair[role]["variant_id"])
            if variant_id in variant_ids:
                raise ContractError(f"Duplicate v0.3 variant: {variant_id}")
            variant_ids.add(variant_id)
    heldout = iter_v03_variants(root, partition="heldout")
    if len(heldout) != 10:
        raise ContractError("v0.3 held-out suite requires ten variants")
    return {
        "family_count": len(pairs),
        "development_variant_count": len(variant_ids),
        "heldout_variant_count": len(heldout),
        "resource_options_per_task": 3,
        "relaxed_turn_budget": config["trajectory_budget"]["maximum_turns"],
        "heldout_frozen_before_astra": bool(
            _read_object(root / V03_HELDOUT_PATH)["frozen_before_astra"]
        ),
    }


def _copy_tree_files(source: Path, destination: Path) -> None:
    for path in sorted(item for item in source.rglob("*") if item.is_file()):
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)


def _resource_catalog(variant: dict[str, Any]) -> dict[str, Any]:
    resources = []
    for resource in variant["resources"]:
        record = dict(resource)
        record["available"] = not (
            resource["resource_id"] == variant["correct_resource_id"]
            and not variant["correct_resource_available"]
        )
        resources.append(record)
    return {
        "selection_budget": 1,
        "none_is_allowed": True,
        "resources": resources,
        "selection_rule": (
            "Choose the smallest available resource that distinguishes the leading "
            "hypotheses. Select none if no available resource can resolve the evidence."
        ),
    }


def _public_task(
    base_task: dict[str, Any], config: dict[str, Any], variant: dict[str, Any]
) -> dict[str, Any]:
    value = dict(base_task)
    value.update(
        {
            "schema_version": "0.3",
            "suite_id": config["suite_id"],
            "family_id": variant["family_id"],
            "variant_id": variant["variant_id"],
            "scoring_weights": config["scoring"],
            "resource_selection": config["resource_selection_contract"],
            "trajectory_budget": config["trajectory_budget"],
            "schemas": {
                "commitment": "schemas/commitment.schema.json",
                "final_submission": "schemas/final_submission.schema.json",
            },
        }
    )
    value.pop("provided_intervention", None)
    return value


@dataclass(frozen=True, slots=True)
class V03Package:
    family_id: str
    variant_id: str
    partition: str
    workspace_root: Path
    sealed_root: Path
    package_digest: str
    sealed_digest: str
    private_variant: dict[str, Any]


class V03Builder:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()

    def build(
        self,
        variant_id: str,
        *,
        output_root: Path,
        partition: str = "development",
        replace: bool = False,
    ) -> V03Package:
        validate_v03_config(self.project_root)
        config = load_v03_config(self.project_root)
        variant = load_v03_variant(self.project_root, variant_id, partition=partition)
        destination = output_root / f"hard3-{variant_id}"
        sealed_root = output_root / f"hard3-{variant_id}-sealed"
        scratch = output_root / f"hard3-{variant_id}-sources"
        for path in (destination, sealed_root, scratch):
            if path.exists():
                if not replace:
                    raise ConfigurationError(f"v0.3 build path exists: {path}")
                shutil.rmtree(path)
            path.mkdir(parents=True)
        source_partition = "heldout" if partition == "heldout" else "development"
        source_builder = HardSuiteBuilder(self.project_root)
        public_package = source_builder.build(
            variant["public_source_variant_id"],
            output_root=scratch,
            partition=source_partition,
        )
        resolved_package = source_builder.build(
            variant["resolved_evidence_variant_id"],
            output_root=scratch,
            partition=source_partition,
        )
        template_root = self.project_root / "tasks" / "hard_suite_v03"
        _copy_tree_files(template_root, destination)
        for folder in ("case", "data"):
            _copy_tree_files(public_package.workspace_root / folder, destination / folder)
        catalog = _resource_catalog(variant)
        _write_json(destination / "resources" / "resource_catalog.json", catalog)
        base_task = _read_object(public_package.workspace_root / "task.json")
        _write_json(destination / "task.json", _public_task(base_task, config, variant))
        manifest = _read_object(public_package.workspace_root / "evidence_manifest.json")
        manifest["EV-RESOURCE-SELECTION"] = {
            "paths": [
                "resources/resource_catalog.json",
                "evidence/selected_resource.json",
            ],
            "status": "partly_available_until_commitment",
        }
        _write_json(destination / "evidence_manifest.json", manifest)
        (destination / "submission").mkdir()

        resources = {str(row["resource_id"]): row for row in catalog["resources"]}
        for selection in ("none", "R1", "R2", "R3"):
            packet = sealed_root / selection
            packet.mkdir()
            use_resolved = (
                selection == variant["correct_resource_id"]
                and variant["correct_resource_available"]
            )
            source = resolved_package if use_resolved else public_package
            _copy_tree_files(source.sealed_root, packet)
            if use_resolved:
                for filename in (
                    "metadata.csv",
                    "pilot_predictions.csv",
                    "sample_fingerprints.csv",
                    "feature_availability.csv",
                ):
                    shutil.copyfile(
                        source.workspace_root / "data" / filename,
                        packet / f"reanalysis_{filename}",
                    )
            selected = resources.get(selection)
            _write_json(
                packet / "selected_resource.json",
                {
                    "selected_resource_id": selection,
                    "intervention": selected["intervention"] if selected else "none",
                    "class": selected["class"] if selected else "none",
                    "cost_units": selected["cost_units"] if selected else 0,
                    "outcome_evidence_changed": use_resolved,
                },
            )

        public_rows = [
            {
                "path": path.relative_to(destination).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in sorted(item for item in destination.rglob("*") if item.is_file())
        ]
        sealed_rows = [
            {
                "path": path.relative_to(sealed_root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in sorted(item for item in sealed_root.rglob("*") if item.is_file())
        ]
        package_digest = canonical_sha256(public_rows)
        sealed_digest = canonical_sha256(sealed_rows)
        _write_json(
            destination / "START_STATE.json",
            {
                "schema_version": "0.3",
                "suite_id": config["suite_id"],
                "family_id": variant["family_id"],
                "variant_id": variant_id,
                "partition": partition,
                "package_digest": package_digest,
                "selected_resource_packet_visible": False,
                "private_answer_visible": False,
            },
        )
        shutil.rmtree(scratch)
        return V03Package(
            family_id=str(variant["family_id"]),
            variant_id=variant_id,
            partition=partition,
            workspace_root=destination,
            sealed_root=sealed_root,
            package_digest=package_digest,
            sealed_digest=sealed_digest,
            private_variant=variant,
        )


def _effective_csv(root: Path, filename: str) -> Path:
    reanalysis = root / "evidence" / f"reanalysis_{filename}"
    return reanalysis if reanalysis.is_file() else root / "data" / filename


def compute_v03_metrics(workspace_root: Path) -> dict[str, float]:
    root = workspace_root.resolve()
    identities = _read_csv(_effective_csv(root, "sample_fingerprints.csv"))
    groups: dict[str, list[dict[str, str]]] = {}
    for row in identities:
        groups.setdefault(row["expression_fingerprint"], []).append(row)
    conflicts = sum(
        len(group) > 1
        and (
            len({row["patient_id"] for row in group}) > 1
            or len({row["visit_id"] for row in group}) > 1
        )
        for group in groups.values()
    )
    if (root / "evidence" / "patient_visit_reconciliation.csv").is_file():
        reconciled = _read_csv(root / "evidence" / "patient_visit_reconciliation.csv")
        if reconciled and all(row["status"] == "verified" for row in reconciled):
            conflicts = 0
    features = _read_csv(_effective_csv(root, "feature_availability.csv"))
    required = [row for row in features if int(row["required_by_locked_model"]) == 1]
    retention = sum(int(row["available_on_validation_platform"]) for row in required) / len(
        required
    )
    metadata = _read_csv(_effective_csv(root, "metadata.csv"))
    pilot = _read_csv(_effective_csv(root, "pilot_predictions.csv"))
    pilot_auc = _auc(
        [int(row["observed_label"]) for row in pilot],
        [float(row["locked_score"]) for row in pilot],
    )
    adjudicated = _read_csv(root / "evidence" / "adjudicated_predictions.csv")
    disagreement = sum(
        int(row["observed_label"]) != int(row["adjudicated_label"]) for row in adjudicated
    ) / len(adjudicated)
    adjudicated_auc = _auc(
        [int(row["adjudicated_label"]) for row in adjudicated],
        [float(row["locked_score"]) for row in adjudicated],
    )
    factorial = _read_csv(root / "evidence" / "factorial_predictions.csv")
    aucs = {}
    counts = {}
    for condition in _FACTORIAL_CONDITIONS:
        selected = [row for row in factorial if row["condition"] == condition]
        counts[condition] = len(selected)
        aucs[condition] = _auc(
            [int(row["label"]) for row in selected],
            [float(row["locked_score"]) for row in selected],
        )
    unmatched = aucs["unmatched"]
    return {
        "identity_conflict_count": float(conflicts),
        "required_feature_retention": retention,
        "batch_outcome_phi": _binary_phi(metadata),
        "pilot_n": float(len(pilot)),
        "pilot_auc": pilot_auc,
        "label_disagreement_rate": disagreement,
        "adjudicated_auc": adjudicated_auc,
        "adjudicated_auc_gain": adjudicated_auc - pilot_auc,
        "matched_evidence_n": float(counts["all_matched"]),
        "matched_evidence_auc": aucs["all_matched"],
        "endpoint_gain": aucs["endpoint_matched"] - unmatched,
        "platform_gain": aucs["platform_matched"] - unmatched,
        "drug_gain": aucs["drug_matched"] - unmatched,
        "all_matched_gain": aucs["all_matched"] - unmatched,
    }


def _v03_decision(workspace_root: Path, metrics: dict[str, float]) -> str:
    provenance = _read_object(workspace_root.resolve() / "evidence" / "provenance.json")
    if metrics["identity_conflict_count"] > 0:
        return "stop"
    if (
        abs(metrics["batch_outcome_phi"]) >= 0.50
        and not provenance["leakage_safe_split_demonstrated"]
    ):
        return "stop"
    advance = (
        metrics["required_feature_retention"] >= 0.80
        and abs(metrics["batch_outcome_phi"]) < 0.30
        and metrics["label_disagreement_rate"] < 0.15
        and metrics["matched_evidence_n"] >= 50
        and metrics["matched_evidence_auc"] >= 0.70
    )
    return "advance" if advance else "insufficient_evidence"


def solve_v03(workspace_root: Path, variant: dict[str, Any]) -> dict[str, Any]:
    root = workspace_root.resolve()
    task = _read_object(root / "task.json")
    metrics = compute_v03_metrics(root)
    decision = _v03_decision(root, metrics)
    diagnoses = _diagnoses(root, metrics)
    primary = diagnoses[0]
    secondary = diagnoses[1:]
    if decision == "advance":
        primary = "no_material_failure"
        secondary = []
    evidence = set(_FAILURE_TO_EVIDENCE[primary])
    evidence.update({"EV-INTERVENTION", "EV-RESOURCE-SELECTION"})
    selected = str(variant["expected_resource_id"])
    if selected == "none":
        assessment = (
            "evidence_still_insufficient"
            if variant["family_id"] == "H05_evidence_sufficiency"
            else "does_not_resolve"
        )
    elif variant["family_id"] == "H03_process_science":
        assessment = "resolves_process_only"
    else:
        assessment = "resolves"
    return {
        "family_id": task["family_id"],
        "variant_id": task["variant_id"],
        "selected_resource_id": selected,
        "decision": decision,
        "confidence": 1.0,
        "primary_failure": primary,
        "secondary_failures": secondary,
        "metrics": metrics,
        "evidence_ids": sorted(evidence),
        "containment_status": ("verified_no_issue" if decision == "advance" else "contained"),
        "smallest_resolving_experiment": _FAILURE_TO_EXPERIMENT[primary],
        "recommended_resource": _FAILURE_TO_RESOURCE[primary],
        "provided_intervention_assessment": assessment,
        "unnecessary_escalation": False,
        "rationale": "Reference recomputation under the public v0.3 resource contract.",
    }


def reference_v03_commitment(workspace_root: Path, variant: dict[str, Any]) -> dict[str, Any]:
    task = _read_object(workspace_root.resolve() / "task.json")
    failure = str(variant["failure_mode"])
    alternate = {
        "identity_overlap": "batch_confounding",
        "transfer_interaction": "endpoint_mismatch",
        "batch_confounding": "endpoint_mismatch",
        "label_uncertainty": "underpowered_validation",
        "underpowered_validation": "transfer_interaction",
    }[failure]
    experiment = _FAILURE_TO_EXPERIMENT[failure]
    return {
        "family_id": task["family_id"],
        "variant_id": task["variant_id"],
        "ranked_hypotheses": [failure, alternate],
        "planned_metric_ids": sorted(
            _FAILURE_TO_METRICS[failure]
            | {
                "identity_conflict_count",
                "pilot_auc",
                "matched_evidence_auc",
                "matched_evidence_n",
            }
        ),
        "selected_discriminating_experiment": experiment,
        "requested_resource_id": variant["expected_resource_id"],
        "pre_reveal_decision": "insufficient_evidence",
        "if_leading_supported": (
            "stop"
            if failure in {"identity_overlap", "batch_confounding"}
            else "insufficient_evidence"
        ),
        "if_leading_refuted": "advance",
    }


@dataclass(frozen=True, slots=True)
class V03Grade:
    score: float
    components: dict[str, float]
    expected_decision: str
    expected_primary_failure: str
    decision_correct: bool
    detection_correct: bool
    containment_correct: bool
    smallest_action_correct: bool
    intervention_assessment_correct: bool
    resource_selection_correct: bool
    metric_scores: dict[str, float]
    commitment_immutable: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "components": self.components,
            "expected_decision": self.expected_decision,
            "expected_primary_failure": self.expected_primary_failure,
            "decision_correct": self.decision_correct,
            "detection_correct": self.detection_correct,
            "containment_correct": self.containment_correct,
            "smallest_action_correct": self.smallest_action_correct,
            "intervention_assessment_correct": self.intervention_assessment_correct,
            "resource_selection_correct": self.resource_selection_correct,
            "metric_scores": self.metric_scores,
            "commitment_immutable": self.commitment_immutable,
        }


def grade_v03(
    workspace_root: Path,
    variant: dict[str, Any],
    commitment: dict[str, Any] | None,
    submission: dict[str, Any] | None,
    *,
    commitment_immutable: bool,
) -> V03Grade:
    expected = solve_v03(workspace_root, variant)
    task = _read_object(workspace_root.resolve() / "task.json")
    if submission is None:
        components = {name: 0.0 for name in task["scoring_weights"]}
        return V03Grade(
            0.0,
            components,
            expected["decision"],
            expected["primary_failure"],
            False,
            False,
            False,
            False,
            False,
            False,
            {name: 0.0 for name in _METRIC_TOLERANCES},
            commitment_immutable,
        )
    metric_scores = {
        name: _numeric_credit(
            float(expected["metrics"][name]),
            submission.get("metrics", {}).get(name),
            tolerance,
        )
        for name, tolerance in _METRIC_TOLERANCES.items()
    }
    quantitative = sum(metric_scores.values()) / len(metric_scores)
    decision_correct = submission.get("decision") == expected["decision"]
    detection_correct = submission.get("primary_failure") == expected["primary_failure"]
    submitted_secondary = set(submission.get("secondary_failures", []))
    expected_secondary = set(expected["secondary_failures"])
    secondary_recall = (
        1.0
        if not expected_secondary
        else len(submitted_secondary & expected_secondary) / len(expected_secondary)
    )
    diagnosis = 60.0 * detection_correct + 40.0 * secondary_recall
    submitted_evidence = set(submission.get("evidence_ids", []))
    expected_evidence = set(expected["evidence_ids"])
    evidence = 100.0 * len(submitted_evidence & expected_evidence) / len(expected_evidence)
    containment_correct = submission.get("containment_status") == expected["containment_status"]
    smallest_action_correct = (
        submission.get("smallest_resolving_experiment") == expected["smallest_resolving_experiment"]
        and submission.get("recommended_resource") == expected["recommended_resource"]
    )
    intervention_correct = (
        submission.get("provided_intervention_assessment")
        == expected["provided_intervention_assessment"]
    )
    resource_correct = (
        submission.get("selected_resource_id") == expected["selected_resource_id"]
        and (commitment or {}).get("requested_resource_id") == expected["selected_resource_id"]
    )
    recovery = (
        30.0 * containment_correct
        + 45.0 * smallest_action_correct
        + 20.0 * intervention_correct
        + 5.0 * (submission.get("unnecessary_escalation") is False)
    )
    commitment = commitment or {}
    failure = str(variant["failure_mode"])
    hypotheses = set(commitment.get("ranked_hypotheses", []))
    planned = set(commitment.get("planned_metric_ids", []))
    required_planned = _FAILURE_TO_METRICS[failure]
    planned_recall = len(planned & required_planned) / len(required_planned)
    commitment_score = (
        30.0 * commitment_immutable
        + 25.0 * (failure in hypotheses)
        + 25.0 * planned_recall
        + 20.0
        * (commitment.get("selected_discriminating_experiment") == _FAILURE_TO_EXPERIMENT[failure])
    )
    components = {
        "decision": 100.0 * decision_correct,
        "quantitative_analysis": quantitative,
        "scientific_diagnosis": diagnosis,
        "evidence_integration": evidence,
        "resource_selection": 100.0 * resource_correct,
        "recovery_design": recovery,
        "commitment_and_reproducibility": commitment_score,
    }
    score = sum(components[name] * float(task["scoring_weights"][name]) for name in components)
    return V03Grade(
        score=round(score, 6),
        components={name: round(value, 6) for name, value in components.items()},
        expected_decision=expected["decision"],
        expected_primary_failure=expected["primary_failure"],
        decision_correct=decision_correct,
        detection_correct=detection_correct,
        containment_correct=containment_correct,
        smallest_action_correct=smallest_action_correct,
        intervention_assessment_correct=intervention_correct,
        resource_selection_correct=resource_correct,
        metric_scores={name: round(value, 6) for name, value in metric_scores.items()},
        commitment_immutable=commitment_immutable,
    )


class V03Environment:
    def __init__(self, package: V03Package) -> None:
        self.package = package
        self.workspace_root = package.workspace_root.resolve()
        self.commitment: dict[str, Any] | None = None
        self.commitment_sha256: str | None = None
        self.revealed = False
        self.submission: dict[str, Any] | None = None
        self.commitment_immutable = False

    def _workspace_file(self, relative_path: str) -> Path:
        relative = Path(relative_path)
        if relative.is_absolute():
            raise ContractError("Artifact path must be relative")
        path = (self.workspace_root / relative).resolve()
        if self.workspace_root not in path.parents or not path.is_file():
            raise ContractError("Artifact is missing or outside the workspace")
        return path

    def commit_plan(self, commitment_path: str = "submission/commitment.json") -> str:
        if self.commitment is not None:
            raise InvalidTransitionError("commit_plan is irreversible and may be called once")
        path = self._workspace_file(commitment_path)
        value = _read_object(path)
        _validate_schema(
            value,
            self.workspace_root / "schemas" / "commitment.schema.json",
            "Commitment",
        )
        task = _read_object(self.workspace_root / "task.json")
        if value["family_id"] != task["family_id"] or value["variant_id"] != task["variant_id"]:
            raise ContractError("Commitment identifiers do not match task.json")
        catalog = _read_object(self.workspace_root / "resources" / "resource_catalog.json")
        availability = {
            str(row["resource_id"]): bool(row["available"]) for row in catalog["resources"]
        }
        requested = str(value["requested_resource_id"])
        if requested != "none" and not availability[requested]:
            raise ContractError(
                f"Requested resource {requested} is unavailable; revise before commitment"
            )
        self.commitment = value
        self.commitment_sha256 = sha256_file(path)
        return "Commitment and resource choice accepted and hashed."

    def reveal_evidence(self) -> str:
        if self.commitment is None:
            raise InvalidTransitionError("commit_plan must succeed before reveal_evidence")
        if self.revealed:
            raise InvalidTransitionError("reveal_evidence may be called only once")
        selection = str(self.commitment["requested_resource_id"])
        source = self.package.sealed_root / selection
        evidence_root = self.workspace_root / "evidence"
        evidence_root.mkdir()
        _copy_tree_files(source, evidence_root)
        manifest = _read_object(self.workspace_root / "evidence_manifest.json")
        for record in manifest.values():
            if all((self.workspace_root / path).is_file() for path in record["paths"]):
                record["status"] = "available"
        _write_json(self.workspace_root / "evidence_manifest.json", manifest)
        _write_json(
            self.workspace_root / "REVEAL_STATE.json",
            {
                "commitment_sha256": self.commitment_sha256,
                "selected_resource_id": selection,
                "sealed_digest": self.package.sealed_digest,
                "reveal_complete": True,
            },
        )
        self.revealed = True
        return f"Evidence packet for {selection} revealed. Recompute all metrics."

    def submit_hard_suite(self, submission_path: str = "submission/final_submission.json") -> str:
        if self.commitment is None or not self.revealed:
            raise InvalidTransitionError("Commitment and reveal must precede submission")
        if self.submission is not None:
            raise InvalidTransitionError("submit_hard_suite may succeed only once")
        commitment_path = self._workspace_file("submission/commitment.json")
        if sha256_file(commitment_path) != self.commitment_sha256:
            raise ContractError("Committed file changed after reveal")
        path = self._workspace_file(submission_path)
        value = _read_object(path)
        _validate_schema(
            value,
            self.workspace_root / "schemas" / "final_submission.schema.json",
            "Submission",
        )
        task = _read_object(self.workspace_root / "task.json")
        if value["family_id"] != task["family_id"] or value["variant_id"] != task["variant_id"]:
            raise ContractError("Submission identifiers do not match task.json")
        if value["selected_resource_id"] != self.commitment["requested_resource_id"]:
            raise ContractError("Final selected resource differs from the commitment")
        manifest = _read_object(self.workspace_root / "evidence_manifest.json")
        unknown = sorted(set(value["evidence_ids"]) - set(manifest))
        if unknown:
            raise ContractError(f"Unknown evidence IDs: {unknown}")
        self.commitment_immutable = True
        self.submission = value
        return "Submission accepted for independent v0.3 grading."

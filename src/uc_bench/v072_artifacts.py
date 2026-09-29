"""Hidden recomputation of v0.7.2 decision-critical numerical artifacts."""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from statistics import mean, median
from typing import Any

from uc_bench.v07_metrics import (
    calibration_error,
    cluster_bootstrap_auc,
    metric_bundle,
    naive_row_auc,
    read_csv,
    site_metric_bundle,
)

PATIENT_COLUMNS = {"patient_key", "site", "probability", "outcome", "split", "sample_ids"}
FIT_COLUMNS = {"sample_id", "cohort_role", "included_in_reference_fit"}


@dataclass(frozen=True, slots=True)
class ArtifactVerification:
    status: str
    usable: bool
    errors: tuple[str, ...]
    artifact_hashes: dict[str, str]
    recomputed_primary_metrics: dict[str, float]
    recomputed_sensitivity_metrics: dict[str, float]
    reported_metric_matches: dict[str, bool]
    calculated_output_matches: dict[str, bool]
    patient_table_matches_raw_inputs: bool
    preprocessing_fit_matches_raw_inputs: bool
    derived_primary_decision: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _safe_file(workspace_root: Path, relative: str | None) -> Path | None:
    if not isinstance(relative, str) or not relative:
        return None
    posix = PurePosixPath(relative)
    if posix.is_absolute() or ".." in posix.parts:
        return None
    path = (workspace_root / Path(*posix.parts)).resolve()
    if workspace_root != path and workspace_root not in path.parents:
        return None
    return path if path.is_file() else None


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("calculated output must be a JSON object")
    return value


def _aggregate(values: list[tuple[str, float]], method: str) -> float:
    ordered = sorted(values)
    probabilities = [value for _, value in ordered]
    if method == "MEAN":
        return mean(probabilities)
    if method == "MEDIAN":
        return median(probabilities)
    if method == "FIRST_LOCKED":
        return probabilities[0]
    raise ValueError("unsupported aggregation method")


def _expected_patient_rows(workspace: Path, method: str) -> dict[str, dict[str, Any]]:
    metadata = read_csv(workspace / "data/cohort_metadata.csv")
    predictions = read_csv(workspace / "data/locked_predictions.csv")
    outcomes = read_csv(workspace / "revealed/validation_outcomes.csv")
    metadata_by_sample = {row["sample_id"]: row for row in metadata}
    outcome_by_patient = {row["patient_key"]: int(row["week6_response"]) for row in outcomes}
    grouped: dict[str, list[tuple[str, float]]] = {}
    sites: dict[str, str] = {}
    for row in predictions:
        metadata_row = metadata_by_sample[row["sample_id"]]
        if metadata_row["baseline_eligible"].lower() != "true":
            continue
        patient = metadata_row["fingerprint_cluster"]
        grouped.setdefault(patient, []).append(
            (row["sample_id"], float(row["predicted_probability"]))
        )
        sites.setdefault(patient, metadata_row["site"])
    return {
        patient: {
            "patient_key": patient,
            "site": sites[patient],
            "probability": _aggregate(values, method),
            "outcome": outcome_by_patient[patient],
            "split": "VALIDATION",
            "sample_ids": "|".join(sample_id for sample_id, _ in sorted(values)),
        }
        for patient, values in sorted(grouped.items())
    }


def _read_patient_table(path: Path) -> tuple[dict[str, dict[str, Any]], list[str]]:
    errors: list[str] = []
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or [])
        if not fields >= PATIENT_COLUMNS:
            return {}, ["patient_table_column_contract_failed"]
        rows: dict[str, dict[str, Any]] = {}
        for index, row in enumerate(reader, start=2):
            try:
                patient = str(row["patient_key"])
                parsed = {
                    "patient_key": patient,
                    "site": str(row["site"]),
                    "probability": float(row["probability"]),
                    "outcome": int(row["outcome"]),
                    "split": str(row["split"]),
                    "sample_ids": str(row["sample_ids"]),
                }
            except (TypeError, ValueError):
                errors.append(f"patient_table_row_{index}_invalid")
                continue
            if patient in rows:
                errors.append(f"patient_table_duplicate_patient_{patient}")
            elif not 0 <= parsed["probability"] <= 1 or parsed["outcome"] not in {0, 1}:
                errors.append(f"patient_table_row_{index}_range_invalid")
            else:
                rows[patient] = parsed
    return rows, errors


def _patient_rows_match(
    observed: dict[str, dict[str, Any]], expected: dict[str, dict[str, Any]]
) -> tuple[bool, list[str]]:
    if set(observed) != set(expected):
        return False, ["patient_table_patient_set_mismatch"]
    errors: list[str] = []
    for patient in sorted(expected):
        left = observed[patient]
        right = expected[patient]
        if left["site"] != right["site"]:
            errors.append(f"patient_table_site_mismatch:{patient}")
        if left["outcome"] != right["outcome"]:
            errors.append(f"patient_table_outcome_mismatch:{patient}")
        if left["split"] != "VALIDATION":
            errors.append(f"patient_table_split_mismatch:{patient}")
        if set(left["sample_ids"].split("|")) != set(right["sample_ids"].split("|")):
            errors.append(f"patient_table_mapping_mismatch:{patient}")
        if abs(left["probability"] - right["probability"]) > 1e-9:
            errors.append(f"patient_table_prediction_mismatch:{patient}")
    return not errors, errors


def _fit_matches(workspace: Path, supplied_path: Path) -> tuple[bool, list[str]]:
    raw_path = workspace / "pipeline/fit_membership.csv"
    try:
        supplied = read_csv(supplied_path)
        raw = read_csv(raw_path)
    except (OSError, KeyError):
        return False, ["preprocessing_fit_unreadable"]
    if not supplied:
        return False, ["preprocessing_fit_empty"]
    if not set(supplied[0]) >= FIT_COLUMNS:
        return False, ["preprocessing_fit_column_contract_failed"]

    def normalize(rows: list[dict[str, str]]) -> list[tuple[str, str, str]]:
        return sorted(
            (
                row["sample_id"],
                row["cohort_role"],
                row["included_in_reference_fit"].lower(),
            )
            for row in rows
        )

    return (
        (True, [])
        if normalize(supplied) == normalize(raw)
        else (
            False,
            ["preprocessing_fit_does_not_match_supplied_lineage"],
        )
    )


def _metric_matches(observed: Any, expected: float, tolerance: float = 1e-6) -> bool:
    try:
        return abs(float(observed) - expected) <= tolerance
    except (TypeError, ValueError, OverflowError):
        return False


def verify_v072_artifacts(
    workspace_root: Path | None,
    c2: dict[str, Any],
    c3: dict[str, Any],
) -> ArtifactVerification:
    """Recompute results from raw evidence and declared saved artifacts."""

    errors: list[str] = []
    hashes: dict[str, str] = {}
    if workspace_root is None:
        return ArtifactVerification(
            "missing_workspace",
            False,
            ("workspace_root_not_provided",),
            {},
            {},
            {},
            {},
            {},
            False,
            False,
            None,
        )
    workspace = workspace_root.resolve()
    manifest = c3["artifact_manifest"]
    paths: dict[str, Path] = {}
    for artifact_id, relative in manifest.items():
        path = _safe_file(workspace, relative)
        if path is None:
            errors.append(f"{artifact_id}_missing_or_unsafe")
        else:
            paths[artifact_id] = path
            hashes[artifact_id] = _digest(path)
    required = {"patient_table_path", "preprocessing_fit_path", "calculated_outputs_path"}
    if set(paths) != required:
        return ArtifactVerification(
            "missing_or_unsafe_artifact",
            False,
            tuple(errors),
            hashes,
            {},
            {},
            {},
            {},
            False,
            False,
            None,
        )

    method = c2["validation_plan"]["aggregation_method"]
    try:
        expected_rows = _expected_patient_rows(workspace, method)
    except (OSError, KeyError, ValueError) as exc:
        errors.append(f"raw_evidence_recomputation_failed:{type(exc).__name__}")
        expected_rows = {}
    observed_rows, patient_errors = _read_patient_table(paths["patient_table_path"])
    errors.extend(patient_errors)
    patient_match, patient_match_errors = _patient_rows_match(observed_rows, expected_rows)
    errors.extend(patient_match_errors)
    fit_match, fit_errors = _fit_matches(workspace, paths["preprocessing_fit_path"])
    errors.extend(fit_errors)

    primary: dict[str, float] = {}
    sensitivity: dict[str, float] = {}
    if patient_match and observed_rows:
        rows = list(observed_rows.values())
        primary.update(metric_bundle(rows))
        primary["ece"] = calibration_error(
            [int(row["outcome"]) for row in rows],
            [float(row["probability"]) for row in rows],
            bins=int(c2["validation_plan"]["ece_bins"]),
        )
        uncertainty = c2["validation_plan"]["uncertainty"]
        seed = uncertainty.get("random_seed")
        replicates = uncertainty.get("bootstrap_replicates")
        if not isinstance(seed, int) or not isinstance(replicates, int):
            errors.append("declared_bootstrap_contract_incomplete")
        else:
            low, _ = cluster_bootstrap_auc(rows, seed=seed, replicates=replicates)
            primary["auc_ci_low"] = low
        sites = site_metric_bundle(rows)
        sensitivity["site_weighted_auc"] = float(sites["site_weighted_auc"])
        sensitivity["worst_site_auc"] = float(sites["worst_site_auc"])
        try:
            sensitivity["naive_row_auc"] = naive_row_auc(
                read_csv(workspace / "data/cohort_metadata.csv"),
                read_csv(workspace / "data/locked_predictions.csv"),
                read_csv(workspace / "revealed/validation_outcomes.csv"),
            )
        except (OSError, KeyError, ValueError):
            errors.append("naive_row_sensitivity_recomputation_failed")

    calculated_matches: dict[str, bool] = {}
    try:
        calculated = _read_json(paths["calculated_outputs_path"])
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        errors.append(f"calculated_outputs_unreadable:{type(exc).__name__}")
        calculated = {}
    saved_primary = calculated.get("primary_metrics")
    saved_sensitivity = calculated.get("sensitivity_metrics")
    for metric, expected in primary.items():
        observed = saved_primary.get(metric) if isinstance(saved_primary, dict) else None
        calculated_matches[metric] = _metric_matches(
            observed, expected, 0.06 if metric == "auc_ci_low" else 1e-6
        )
    for metric, expected in sensitivity.items():
        observed = saved_sensitivity.get(metric) if isinstance(saved_sensitivity, dict) else None
        calculated_matches[f"sensitivity:{metric}"] = _metric_matches(observed, expected)
    if calculated_matches and not all(calculated_matches.values()):
        errors.append("calculated_outputs_do_not_match_independent_recomputation")

    reported_matches = {
        metric: _metric_matches(
            c3["primary_metrics"].get(metric),
            expected,
            0.06 if metric == "auc_ci_low" else 1e-4,
        )
        for metric, expected in primary.items()
    }
    if reported_matches and not all(reported_matches.values()):
        errors.append("reported_primary_metrics_do_not_match_saved_artifacts")

    decision: str | None = None
    if primary:
        criteria = json.loads((workspace / "intended_use.json").read_text(encoding="utf-8"))[
            "advance_criteria"
        ]
        passes = (
            primary["auc"] >= float(criteria["auc_minimum"])
            and primary["auc_ci_low"] >= float(criteria["auc_ci_lower_minimum"])
            and primary["brier"] <= float(criteria["brier_maximum"])
            and primary["ece"] <= float(criteria["ece_maximum"])
            and primary["net_benefit"] >= float(criteria["net_benefit_minimum"])
        )
        decision = "CONDITIONAL_ADVANCE" if passes else "STOP_OR_PAUSE"
    required_primary = {"auc", "auc_ci_low", "brier", "ece", "net_benefit"}
    usable = (
        patient_match
        and fit_match
        and required_primary <= set(primary)
        and all(calculated_matches.values())
    )
    return ArtifactVerification(
        "verified" if usable else "invalid",
        usable,
        tuple(dict.fromkeys(errors)),
        hashes,
        primary,
        sensitivity,
        reported_matches,
        calculated_matches,
        patient_match,
        fit_match,
        decision,
    )


def write_canonical_analysis_artifacts(
    workspace_root: Path,
    *,
    aggregation_method: str,
    bootstrap_seed: int,
    bootstrap_replicates: int = 600,
    prefix: str = "v072",
    ece_bins: int = 5,
) -> tuple[dict[str, str], dict[str, float], dict[str, float]]:
    """Write disclosed-contract artifacts by recomputing only from visible evidence."""

    workspace = workspace_root.resolve()
    rows_by_patient = _expected_patient_rows(workspace, aggregation_method)
    rows = list(rows_by_patient.values())
    primary = metric_bundle(rows)
    primary["ece"] = calibration_error(
        [int(row["outcome"]) for row in rows],
        [float(row["probability"]) for row in rows],
        bins=ece_bins,
    )
    primary["auc_ci_low"] = cluster_bootstrap_auc(
        rows, seed=bootstrap_seed, replicates=bootstrap_replicates
    )[0]
    sites = site_metric_bundle(rows)
    sensitivity = {
        "naive_row_auc": naive_row_auc(
            read_csv(workspace / "data/cohort_metadata.csv"),
            read_csv(workspace / "data/locked_predictions.csv"),
            read_csv(workspace / "revealed/validation_outcomes.csv"),
        ),
        "site_weighted_auc": float(sites["site_weighted_auc"]),
        "worst_site_auc": float(sites["worst_site_auc"]),
    }
    work = workspace / "work"
    work.mkdir(parents=True, exist_ok=True)
    patient_path = work / f"{prefix}_patient_table.csv"
    with patient_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=sorted(PATIENT_COLUMNS))
        writer.writeheader()
        writer.writerows(rows)
    calculated_path = work / f"{prefix}_calculated_outputs.json"
    calculated_path.write_text(
        json.dumps(
            {"primary_metrics": primary, "sensitivity_metrics": sensitivity},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return (
        {
            "patient_table_path": patient_path.relative_to(workspace).as_posix(),
            "preprocessing_fit_path": "pipeline/fit_membership.csv",
            "calculated_outputs_path": calculated_path.relative_to(workspace).as_posix(),
        },
        primary,
        sensitivity,
    )


def recompute_followup_artifact(
    workspace_root: Path | None,
    *,
    case_id: str,
    selected_resource: str | None,
) -> dict[str, Any]:
    """Independently calculate the case-relevant purchased evidence result."""

    if workspace_root is None or selected_resource is None:
        return {"usable": False, "error": "followup_workspace_or_resource_missing"}
    workspace = workspace_root.resolve()
    if selected_resource == "none":
        path = workspace / "purchased/none/no_new_evidence.json"
        try:
            value = _read_json(path)
        except (OSError, json.JSONDecodeError, ValueError):
            return {"usable": False, "error": "no_evidence_artifact_unreadable"}
        return {
            "usable": value.get("new_evidence") is False,
            "new_evidence_received": value.get("new_evidence"),
            "calculated_values": {},
        }
    if selected_resource == "X31":
        try:
            predictions = read_csv(workspace / "purchased/X31/replay_predictions.csv")
            outcomes = read_csv(workspace / "revealed/validation_outcomes.csv")
            metadata = read_csv(workspace / "data/cohort_metadata.csv")
            outcome_by_patient = {
                row["patient_key"]: int(row["week6_response"]) for row in outcomes
            }
            site_by_patient = {row["fingerprint_cluster"]: row["site"] for row in metadata}
            rows = [
                {
                    "patient_key": row["patient_key"],
                    "site": site_by_patient[row["patient_key"]],
                    "probability": float(row["predicted_probability"]),
                    "outcome": outcome_by_patient[row["patient_key"]],
                }
                for row in predictions
            ]
            values = metric_bundle(rows)
        except (OSError, KeyError, ValueError):
            return {"usable": False, "error": "pipeline_replay_artifact_unreadable"}
        return {
            "usable": True,
            "new_evidence_received": True,
            "resolved_patient_count": len(rows),
            "calculated_values": values,
        }
    if selected_resource == "X46":
        try:
            predictions = read_csv(workspace / "purchased/X46/matched_predictions.csv")
            outcomes = read_csv(workspace / "purchased/X46/matched_outcomes.csv")
            outcome_by_patient = {
                row["patient_key"]: int(row["week6_response"]) for row in outcomes
            }
            rows = [
                {
                    "patient_key": row["patient_key"],
                    "site": row["site"],
                    "probability": float(row["predicted_probability"]),
                    "outcome": outcome_by_patient[row["patient_key"]],
                }
                for row in predictions
            ]
            values = metric_bundle(rows)
        except (OSError, KeyError, ValueError):
            return {"usable": False, "error": "external_evidence_artifact_unreadable"}
        return {
            "usable": True,
            "new_evidence_received": True,
            "resolved_patient_count": len(rows),
            "calculated_values": values,
        }
    if selected_resource == "X17" and case_id == "case_02":
        try:
            rows = read_csv(workspace / "purchased/X17/source_record_crosswalk.csv")
        except OSError:
            return {"usable": False, "error": "identity_crosswalk_unreadable"}
        patient_column = (
            "fingerprint_cluster" if rows and "fingerprint_cluster" in rows[0] else "patient_key"
        )
        patients = {row[patient_column] for row in rows if row.get(patient_column)}
        return {
            "usable": bool(patients),
            "new_evidence_received": True,
            "resolved_patient_count": len(patients),
            "calculated_values": {},
        }
    return {
        "usable": True,
        "new_evidence_received": True,
        "calculated_values": {},
        "note": "No checkpoint-weighted numeric result is defined for this resource/case pair.",
    }

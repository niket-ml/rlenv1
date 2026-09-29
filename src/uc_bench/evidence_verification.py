"""Independent verification of agent-authored development evidence."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from uc_bench.contracts import PredictorManifest
from uc_bench.errors import ContractError
from uc_bench.predictor import LinearRankPredictor
from uc_bench.reference import auc_with_stratified_bootstrap, permutation_p_value

AUDIT_CHECK_NAMES = (
    "cohort_reconstruction",
    "endpoint_integrity",
    "platform_alignment",
    "leakage_control",
    "negative_control",
    "uncertainty",
)


@dataclass(frozen=True, slots=True)
class EvidenceVerification:
    audit_checks: dict[str, bool]
    supported_diagnostic_codes: frozenset[str]
    details: dict[str, Any]


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ContractError(f"Expected a JSON object: {path}")
    return value


def _development_layout(workspace_root: Path) -> tuple[Path, Path, Path]:
    packaged_metadata = workspace_root / "data" / "metadata.csv"
    if packaged_metadata.is_file():
        return (
            packaged_metadata,
            workspace_root / "data",
            workspace_root / "reference" / "cohorts.json",
        )
    project_metadata = workspace_root / "data" / "processed" / "development" / "metadata.csv"
    if project_metadata.is_file():
        return (
            project_metadata,
            project_metadata.parent,
            workspace_root / "configs" / "cohorts.json",
        )
    raise ContractError("No agent-visible development data are present in this condition")


def _cohort_config_path(workspace_root: Path) -> Path:
    packaged = workspace_root / "reference" / "cohorts.json"
    if packaged.is_file():
        return packaged
    project = workspace_root / "configs" / "cohorts.json"
    if project.is_file():
        return project
    raise ContractError("Cohort documentation is missing")


def _close(actual: Any, claimed: Any, *, tolerance: float = 1e-10) -> bool:
    try:
        actual_float = float(actual)
        claimed_float = float(claimed)
    except (TypeError, ValueError):
        return False
    return (
        math.isfinite(actual_float)
        and math.isfinite(claimed_float)
        and abs(actual_float - claimed_float) <= tolerance
    )


def _interval_matches(actual: tuple[float, float], claimed: Any) -> bool:
    return (
        isinstance(claimed, list)
        and len(claimed) == 2
        and _close(actual[0], claimed[0])
        and _close(actual[1], claimed[1])
    )


def _bounded_integer(value: Any, *, minimum: int, maximum: int, name: str) -> int:
    if isinstance(value, bool):
        raise ContractError(f"{name} must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ContractError(f"{name} must be an integer") from exc
    if parsed != value or not minimum <= parsed <= maximum:
        raise ContractError(f"{name} must be within [{minimum}, {maximum}]")
    return parsed


def verify_development_evidence(
    *,
    workspace_root: Path,
    model_value: dict[str, Any],
    manifest_value: dict[str, Any],
    evidence: dict[str, Any],
) -> EvidenceVerification:
    """Recompute claims from visible files and the committed predictor.

    The agent's ``status: pass`` fields never establish truth on their own.
    Conditions without development data can verify documented transfer facts,
    but all claims that require matrices or outcomes fail closed.
    """

    import numpy as np
    import pandas as pd

    checks = dict.fromkeys(AUDIT_CHECK_NAMES, False)
    details: dict[str, Any] = {}
    supported: set[str] = set()
    try:
        model = LinearRankPredictor.from_dict(model_value)
        manifest = PredictorManifest.from_dict(manifest_value)
        if model.model_version != manifest.model_version:
            raise ContractError("Model and manifest versions differ")
        if model.feature_schema_version != manifest.feature_schema_version:
            raise ContractError("Model and manifest feature schemas differ")

        cohorts_config = _load_object(_cohort_config_path(workspace_root))
        config_rows = cohorts_config.get("cohorts", [])
        role_to_row = {str(row.get("role")): row for row in config_rows}
        discovery_id = str(role_to_row["discovery"]["accession"])
        replication_id = str(role_to_row["replication"]["accession"])
        sealed_row = role_to_row["sealed_transfer"]
        expected_cohorts = {discovery_id, replication_id}
        claimed_checks = evidence.get("audit_checks", {})

        development_endpoints = {
            str(role_to_row[role]["endpoint"]["name"])
            for role in ("discovery", "replication")
        }
        development_drugs = {
            str(role_to_row[role]["drug"]) for role in ("discovery", "replication")
        }
        endpoint_mismatch = str(sealed_row["endpoint"]["name"]) not in development_endpoints
        drug_transfer = str(sealed_row["drug"]) not in development_drugs
        endpoint_claim = claimed_checks.get("endpoint_integrity", {})
        checks["endpoint_integrity"] = (
            endpoint_claim.get("status") == "pass"
            and endpoint_claim.get("endpoint_mismatch") is endpoint_mismatch
            and endpoint_claim.get("drug_transfer") is drug_transfer
        )
        if endpoint_mismatch:
            supported.add("endpoint_mismatch")
        if drug_transfer:
            supported.add("drug_transfer")
        documented_platforms = {
            str(row["platform"]["geo_id"])
            for row in role_to_row.values()
            if isinstance(row.get("platform"), dict)
        }
        if len(documented_platforms) > 1:
            supported.add("platform_shift")

        metadata_path, data_root, _ = _development_layout(workspace_root)
        metadata = pd.read_csv(metadata_path)

        required_columns = {
            "cohort",
            "sample_id",
            "patient_id",
            "platform_id",
            "timepoint",
            "endpoint",
            "response",
            "sealed",
        }
        if not required_columns <= set(metadata):
            raise ContractError("Development metadata are missing required columns")
        if metadata.empty:
            raise ContractError("Development metadata are empty")
        metadata["sample_id"] = metadata["sample_id"].astype(str)
        metadata["patient_id"] = metadata["patient_id"].astype(str)
        metadata["response"] = pd.to_numeric(metadata["response"], errors="raise").astype(int)

        actual_counts: dict[str, dict[str, int]] = {}
        for cohort_id, frame in metadata.groupby("cohort"):
            actual_counts[str(cohort_id)] = {
                "n": int(len(frame)),
                "responders": int((frame["response"] == 1).sum()),
                "nonresponders": int((frame["response"] == 0).sum()),
            }
        basic_metadata_valid = (
            set(actual_counts) == expected_cohorts
            and not metadata["sample_id"].duplicated().any()
            and not metadata["patient_id"].duplicated().any()
            and set(metadata["response"].unique()) == {0, 1}
            and set(metadata["timepoint"].astype(str)) == {"baseline"}
            and not metadata["sealed"].astype(str).str.lower().isin({"true", "1"}).any()
        )
        cohort_claim = claimed_checks.get("cohort_reconstruction", {})
        checks["cohort_reconstruction"] = (
            basic_metadata_valid
            and cohort_claim.get("status") == "pass"
            and cohort_claim.get("cohorts") == actual_counts
        )
        details["actual_cohort_counts"] = actual_counts

        matrices = {}
        sample_ids_by_cohort = {}
        for cohort_id in sorted(expected_cohorts):
            path = data_root / f"{cohort_id}_gene_expression.csv.gz"
            matrix = pd.read_csv(path, index_col=0)
            if matrix.index.duplicated().any() or matrix.columns.duplicated().any():
                raise ContractError(f"{cohort_id} expression identifiers are not unique")
            try:
                numeric = matrix.to_numpy(dtype=float)
            except (TypeError, ValueError) as exc:
                raise ContractError(f"{cohort_id} expression must be numeric") from exc
            if not np.isfinite(numeric).all():
                raise ContractError(f"{cohort_id} expression contains non-finite values")
            matrix = pd.DataFrame(numeric, index=matrix.index, columns=matrix.columns)
            sample_ids = metadata.loc[
                metadata["cohort"].astype(str) == cohort_id, "sample_id"
            ].tolist()
            if not set(sample_ids) <= set(matrix.columns.astype(str)):
                raise ContractError(f"{cohort_id} expression is missing metadata samples")
            matrices[cohort_id] = matrix.loc[:, sample_ids]
            sample_ids_by_cohort[cohort_id] = sample_ids
        common_gene_count = len(
            set(matrices[discovery_id].index) & set(matrices[replication_id].index)
        )
        platforms_are_distinct = metadata["platform_id"].astype(str).nunique() > 1
        platform_claim = claimed_checks.get("platform_alignment", {})
        checks["platform_alignment"] = (
            platform_claim.get("status") == "pass"
            and platform_claim.get("strategy") == "within_sample_percentile_rank"
            and platform_claim.get("platforms_are_distinct") is platforms_are_distinct
            and platform_claim.get("common_gene_count") == common_gene_count
        )
        details["common_gene_count"] = common_gene_count
        discovery_ids = set(sample_ids_by_cohort[discovery_id])
        replication_ids = set(sample_ids_by_cohort[replication_id])
        manifest_roles = {
            "training": set(manifest.training_sample_ids),
            "tuning": set(manifest.tuning_sample_ids),
            "feature_selection": set(manifest.feature_selection_sample_ids),
        }
        declared_development_ids = set().union(*manifest_roles.values())
        replication_untouched = (
            bool(manifest_roles["training"])
            and declared_development_ids <= discovery_ids
            and declared_development_ids.isdisjoint(replication_ids)
        )
        leakage_claim = claimed_checks.get("leakage_control", {})
        checks["leakage_control"] = (
            leakage_claim.get("status") == "pass"
            and leakage_claim.get("untouched_replication") == replication_id
            and leakage_claim.get("replication_used_during_fit") is False
            and replication_untouched
        )
        details["manifest_role_counts"] = {
            role: len(sample_ids) for role, sample_ids in manifest_roles.items()
        }

        uncertainty_claim = claimed_checks.get("uncertainty", {})
        resamples = _bounded_integer(
            uncertainty_claim.get("resamples"),
            minimum=100,
            maximum=5_000,
            name="bootstrap resamples",
        )
        discovery_seed = _bounded_integer(
            uncertainty_claim.get("discovery_seed"),
            minimum=0,
            maximum=2**32 - 1,
            name="discovery bootstrap seed",
        )
        replication_seed = _bounded_integer(
            uncertainty_claim.get("replication_seed"),
            minimum=0,
            maximum=2**32 - 1,
            name="replication bootstrap seed",
        )
        outcomes = metadata.set_index("sample_id")["response"]
        development_results = evidence.get("development_results", {})
        computed_results = {}
        result_claims_match = {}
        for cohort_id, seed in (
            (discovery_id, discovery_seed),
            (replication_id, replication_seed),
        ):
            predictions = model.predict_proba(matrices[cohort_id])
            auc, interval = auc_with_stratified_bootstrap(
                outcomes,
                predictions,
                resamples=resamples,
                seed=seed,
            )
            role = "discovery" if cohort_id == discovery_id else "replication"
            claim = development_results.get(role, {})
            result_claims_match[role] = (
                claim.get("cohort") == cohort_id
                and claim.get("n") == len(sample_ids_by_cohort[cohort_id])
                and _close(auc, claim.get("auc"))
                and _interval_matches(interval, claim.get("auc_interval"))
            )
            computed_results[role] = {
                "auc": auc,
                "auc_interval": list(interval),
                "n": len(sample_ids_by_cohort[cohort_id]),
            }
        checks["uncertainty"] = (
            uncertainty_claim.get("status") == "pass"
            and uncertainty_claim.get("method") == "stratified_bootstrap"
            and all(result_claims_match.values())
        )

        negative_claim = claimed_checks.get("negative_control", {})
        permutations = _bounded_integer(
            negative_claim.get("permutation_count"),
            minimum=100,
            maximum=10_000,
            name="permutation count",
        )
        permutation_seed = _bounded_integer(
            negative_claim.get("seed"),
            minimum=0,
            maximum=2**32 - 1,
            name="permutation seed",
        )
        replication_predictions = model.predict_proba(matrices[replication_id])
        computed_p_value = permutation_p_value(
            outcomes,
            replication_predictions,
            permutations=permutations,
            seed=permutation_seed,
        )
        replication_claim = development_results.get("replication", {})
        checks["negative_control"] = (
            negative_claim.get("status") == "pass"
            and negative_claim.get("test") == "replication_label_permutation"
            and _close(computed_p_value, negative_claim.get("p_value"))
            and _close(computed_p_value, replication_claim.get("permutation_p_value"))
        )
        computed_results["replication"]["permutation_p_value"] = computed_p_value
        details["computed_development_results"] = computed_results
    except (ContractError, KeyError, OSError, TypeError, ValueError) as exc:
        details["verification_error"] = f"{type(exc).__name__}: {exc}"

    return EvidenceVerification(
        audit_checks=checks,
        supported_diagnostic_codes=frozenset(supported),
        details=details,
    )

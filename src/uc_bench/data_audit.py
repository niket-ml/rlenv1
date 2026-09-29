"""Deterministic patient-level assembly and feasibility checks for UC-Bench."""

from __future__ import annotations

import csv
import gzip
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, TextIO

from uc_bench.errors import ContractError
from uc_bench.geo import GeoSample, GeoSeriesMetadata
from uc_bench.hashing import sha256_file

EXPECTED_COUNTS = {
    "GSE16879": {"total": 24, "responders": 8, "nonresponders": 16},
    "GSE73661": {"total": 23, "responders": 8, "nonresponders": 15},
    "GSE92415": {"total": 59, "responders": 32, "nonresponders": 27},
}


@dataclass(frozen=True, slots=True)
class PatientRecord:
    """One baseline sample and its patient-level treatment outcome."""

    cohort: str
    sample_id: str
    patient_id: str
    platform_id: str
    disease: str
    tissue: str
    treatment: str
    timepoint: str
    endpoint: str
    response: int
    sealed: bool

    def to_dict(self, *, include_response: bool = True) -> dict[str, Any]:
        value = asdict(self)
        if not include_response:
            value.pop("response")
        return value


def _required(sample: GeoSample, key: str) -> str:
    value = sample.characteristic(key)
    if value is None or not value.strip():
        raise ContractError(f"Sample {sample.accession} is missing characteristic {key!r}")
    return value.strip()


def select_gse16879(series: GeoSeriesMetadata) -> tuple[PatientRecord, ...]:
    """Select baseline UC infliximab samples from GSE16879."""

    if series.accession != "GSE16879":
        raise ContractError(f"Expected GSE16879; found {series.accession}")
    records = []
    for sample in series.samples:
        if sample.characteristic("disease") != "UC":
            continue
        if sample.characteristic("before or after first infliximab treatment") != (
            "Before first infliximab treatment"
        ):
            continue
        response_text = _required(sample, "response to infliximab")
        if response_text not in {"Yes", "No"}:
            raise ContractError(
                f"Unexpected GSE16879 response for {sample.accession}: {response_text}"
            )
        patient_id, marker, suffix = sample.title.partition("_")
        if marker != "_" or suffix != "beforeT" or not patient_id:
            raise ContractError(f"Cannot derive GSE16879 patient from title {sample.title!r}")
        records.append(
            PatientRecord(
                cohort=series.accession,
                sample_id=sample.accession,
                patient_id=f"{series.accession}:{patient_id}",
                platform_id=sample.platform_id,
                disease="ulcerative_colitis",
                tissue="inflamed_colonic_mucosal_biopsy",
                treatment="infliximab",
                timepoint="baseline",
                endpoint="complete_endoscopic_and_histological_healing_week_4_to_6",
                response=int(response_text == "Yes"),
                sealed=False,
            )
        )
    return _validate_records(records, EXPECTED_COUNTS[series.accession])


def select_gse73661(series: GeoSeriesMetadata) -> tuple[PatientRecord, ...]:
    """Pair baseline and follow-up IFX samples to derive GSE73661 response."""

    if series.accession != "GSE73661":
        raise ContractError(f"Expected GSE73661; found {series.accession}")
    by_patient: dict[str, dict[str, GeoSample]] = defaultdict(dict)
    for sample in series.samples:
        if sample.characteristic("induction therapy maintenance therapy") != "IFX":
            continue
        week = _required(sample, "week w")
        if week not in {"W0", "W4_W6"}:
            raise ContractError(f"Unexpected IFX timepoint for {sample.accession}: {week}")
        patient = _required(sample, "study individual number")
        if week in by_patient[patient]:
            raise ContractError(f"Duplicate GSE73661 {week} sample for patient {patient}")
        by_patient[patient][week] = sample

    records = []
    for patient, visits in sorted(by_patient.items(), key=lambda item: int(item[0])):
        if set(visits) != {"W0", "W4_W6"}:
            raise ContractError(f"Incomplete IFX pair for GSE73661 patient {patient}: {visits}")
        baseline = visits["W0"]
        follow_up = visits["W4_W6"]
        mayo = _required(follow_up, "mayo endoscopic subscore")
        if mayo not in {"0", "1", "2", "3"}:
            raise ContractError(
                f"Unexpected GSE73661 follow-up Mayo score for patient {patient}: {mayo}"
            )
        records.append(
            PatientRecord(
                cohort=series.accession,
                sample_id=baseline.accession,
                patient_id=f"{series.accession}:{patient}",
                platform_id=baseline.platform_id,
                disease="ulcerative_colitis",
                tissue="inflamed_colonic_mucosal_biopsy",
                treatment="infliximab",
                timepoint="baseline",
                endpoint="endoscopic_mucosal_healing_week_4_to_6",
                response=int(int(mayo) <= 1),
                sealed=False,
            )
        )
    return _validate_records(records, EXPECTED_COUNTS[series.accession])


def select_gse92415(series: GeoSeriesMetadata) -> tuple[PatientRecord, ...]:
    """Select the sealed baseline golimumab subset from GSE92415."""

    if series.accession != "GSE92415":
        raise ContractError(f"Expected GSE92415; found {series.accession}")
    records = []
    for sample in series.samples:
        if sample.characteristic("disease") != "Ulcerative Colitis (UC)":
            continue
        if sample.characteristic("treatment") != "golimumab":
            continue
        if sample.characteristic("visit") != "Week 0":
            continue
        response_text = _required(sample, "wk6response")
        if response_text not in {"Yes", "No"}:
            raise ContractError(
                f"Unexpected GSE92415 response for {sample.accession}: {response_text}"
            )
        patient = _required(sample, "subject")
        records.append(
            PatientRecord(
                cohort=series.accession,
                sample_id=sample.accession,
                patient_id=f"{series.accession}:{patient}",
                platform_id=sample.platform_id,
                disease="ulcerative_colitis",
                tissue="colonic_mucosal_biopsy",
                treatment="golimumab",
                timepoint="baseline",
                endpoint="clinical_response_week_6",
                response=int(response_text == "Yes"),
                sealed=True,
            )
        )
    return _validate_records(records, EXPECTED_COUNTS[series.accession])


def _validate_records(
    records: list[PatientRecord], expected: dict[str, int]
) -> tuple[PatientRecord, ...]:
    sample_ids = [record.sample_id for record in records]
    patient_ids = [record.patient_id for record in records]
    if len(sample_ids) != len(set(sample_ids)):
        raise ContractError("Selected records contain duplicate sample IDs")
    if len(patient_ids) != len(set(patient_ids)):
        raise ContractError("Selected baseline records contain duplicate patient IDs")
    observed = Counter(record.response for record in records)
    actual = {
        "total": len(records),
        "responders": observed[1],
        "nonresponders": observed[0],
    }
    if actual != expected:
        raise ContractError(f"Cohort counts differ from contract: {actual} != {expected}")
    return tuple(records)


def load_platform_annotation(path: Path) -> dict[str, str]:
    """Return unambiguous probe-to-gene-symbol mappings from a GEO annotation."""

    with _open_annotation(path) as handle:
        for line in handle:
            if line.startswith("ID\t"):
                header = next(csv.reader([line], delimiter="\t"))
                break
        else:
            raise ContractError(f"Annotation has no ID header: {path}")
        reader = csv.DictReader(handle, fieldnames=header, delimiter="\t")
        mapping: dict[str, str] = {}
        for row in reader:
            probe = (row.get("ID") or "").strip()
            raw_symbol = (row.get("Gene symbol") or "").strip()
            symbols = tuple(
                dict.fromkeys(
                    symbol.strip()
                    for symbol in raw_symbol.split("///")
                    if symbol.strip() and symbol.strip() != "---"
                )
            )
            if probe and len(symbols) == 1:
                mapping[probe] = symbols[0]
    if not mapping:
        raise ContractError(f"Annotation produced no unambiguous mappings: {path}")
    return mapping


def _open_annotation(path: Path) -> TextIO:
    if path.suffix == ".gz":
        return gzip.open(path, mode="rt", encoding="utf-8", newline="")
    return path.open(encoding="utf-8", newline="")


def load_expression(path: Path) -> Any:
    """Load the numeric expression table; pandas is an optional science dependency."""

    try:
        import pandas as pd
    except ImportError as exc:  # pragma: no cover - exercised in minimal installations
        raise ContractError("Data assembly requires the project science dependencies") from exc
    expression = pd.read_csv(path, sep="\t", comment="!", index_col=0)
    expression.index = expression.index.astype(str)
    expression.columns = expression.columns.astype(str)
    if expression.empty or expression.index.has_duplicates or expression.columns.has_duplicates:
        raise ContractError(f"Malformed expression table: {path}")
    return expression


def collapse_to_genes(expression: Any, mapping: dict[str, str]) -> Any:
    """Collapse unambiguous mapped probes to genes by the within-sample median."""

    symbols = expression.index.to_series().map(mapping)
    retained = expression.loc[symbols.notna()].copy()
    retained.insert(0, "gene_symbol", symbols[symbols.notna()].to_numpy())
    collapsed = retained.groupby("gene_symbol", sort=True).median(numeric_only=True)
    if collapsed.empty:
        raise ContractError("No expression features survived probe-to-gene mapping")
    return collapsed


def cross_platform_identity_audit(
    left: Any,
    right: Any,
    left_records: tuple[PatientRecord, ...],
    right_records: tuple[PatientRecord, ...],
) -> dict[str, Any]:
    """Use within-cohort gene z-scores to flag likely re-profiled patients."""

    import numpy as np
    from scipy.optimize import linear_sum_assignment

    left_ids = [record.sample_id for record in left_records]
    right_ids = [record.sample_id for record in right_records]
    common = sorted(set(left.index) & set(right.index))
    if len(common) < 1000:
        raise ContractError(f"Too few common genes for identity audit: {len(common)}")

    left_values = left.loc[common, left_ids].to_numpy(dtype=float).T
    right_values = right.loc[common, right_ids].to_numpy(dtype=float).T
    left_sd = left_values.std(axis=0, ddof=1)
    right_sd = right_values.std(axis=0, ddof=1)
    informative = (left_sd > 1e-8) & (right_sd > 1e-8)
    left_values = (left_values[:, informative] - left_values[:, informative].mean(axis=0)) / (
        left_values[:, informative].std(axis=0, ddof=1)
    )
    right_values = (
        right_values[:, informative] - right_values[:, informative].mean(axis=0)
    ) / right_values[:, informative].std(axis=0, ddof=1)

    left_values -= left_values.mean(axis=1, keepdims=True)
    right_values -= right_values.mean(axis=1, keepdims=True)
    left_values /= np.linalg.norm(left_values, axis=1, keepdims=True)
    right_values /= np.linalg.norm(right_values, axis=1, keepdims=True)
    correlations = left_values @ right_values.T
    left_index, right_index = linear_sum_assignment(-correlations)

    left_outcomes = {record.sample_id: record.response for record in left_records}
    right_outcomes = {record.sample_id: record.response for record in right_records}
    pairs = []
    for left_position, right_position in zip(left_index, right_index, strict=True):
        left_id = left_ids[left_position]
        right_id = right_ids[right_position]
        pairs.append(
            {
                "left_sample_id": left_id,
                "right_sample_id": right_id,
                "correlation": float(correlations[left_position, right_position]),
                "outcome_concordant": left_outcomes[left_id] == right_outcomes[right_id],
            }
        )
    assigned = np.array([pair["correlation"] for pair in pairs])
    outcome_concordance = sum(pair["outcome_concordant"] for pair in pairs) / len(pairs)
    near_identity_signal = bool(
        float(np.median(assigned)) >= 0.80 and float(assigned.min()) >= 0.60
    )
    return {
        "common_gene_count": len(common),
        "informative_gene_count": int(informative.sum()),
        "assignment_pair_count": len(pairs),
        "assigned_correlation_min": float(assigned.min()),
        "assigned_correlation_median": float(np.median(assigned)),
        "assigned_correlation_max": float(assigned.max()),
        "outcome_concordance": outcome_concordance,
        "near_identity_signal": near_identity_signal,
        "interpretation": (
            "The expression audit found a near-identity pattern consistent with re-profiling."
            if near_identity_signal
            else "No near-identity expression pattern was found; outcome concordance alone does "
            "not establish sample identity."
        ),
        "pairs": sorted(pairs, key=lambda pair: pair["correlation"], reverse=True),
    }


def verify_sources(project_root: Path) -> list[dict[str, Any]]:
    """Verify size and SHA-256 for every pinned source file."""

    manifest_path = project_root / "configs" / "data_sources.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    verified = []
    for source in manifest["sources"]:
        path = project_root / source["path"]
        if not path.is_file():
            raise ContractError(f"Missing pinned source: {source['path']}")
        actual_size = path.stat().st_size
        actual_hash = sha256_file(path)
        if actual_size != source["bytes"] or actual_hash != source["sha256"]:
            raise ContractError(
                f"Pinned source mismatch for {source['id']}: "
                f"size={actual_size}, sha256={actual_hash}"
            )
        verified.append(
            {
                "id": source["id"],
                "path": source["path"],
                "bytes": actual_size,
                "sha256": actual_hash,
            }
        )
    return verified


def cohort_summary(records: tuple[PatientRecord, ...]) -> dict[str, Any]:
    """Return an aggregate summary safe for Stage 2 audit evidence."""

    return {
        "total": len(records),
        "responders": sum(record.response for record in records),
        "nonresponders": sum(not record.response for record in records),
        "unique_patients": len({record.patient_id for record in records}),
        "unique_samples": len({record.sample_id for record in records}),
        "platforms": sorted({record.platform_id for record in records}),
        "endpoints": sorted({record.endpoint for record in records}),
        "treatments": sorted({record.treatment for record in records}),
        "timepoints": sorted({record.timepoint for record in records}),
    }

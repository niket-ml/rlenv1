#!/usr/bin/env python3
"""Build processed cohort views and the Stage 2 feasibility report."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from uc_bench.data_audit import (
    PatientRecord,
    cohort_summary,
    collapse_to_genes,
    cross_platform_identity_audit,
    load_expression,
    load_platform_annotation,
    select_gse16879,
    select_gse73661,
    select_gse92415,
    verify_sources,
)
from uc_bench.geo import read_geo_series_metadata

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = PROJECT_ROOT / "data" / "raw" / "geo"
PROCESSED_ROOT = PROJECT_ROOT / "data" / "processed"
PRIVATE_ROOT = PROJECT_ROOT / "grader_private" / "data"
EVIDENCE_ROOT = PROJECT_ROOT / "audit" / "evidence"


def write_records(
    path: Path, records: tuple[PatientRecord, ...], *, include_response: bool
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [record.to_dict(include_response=include_response) for record in records]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    verified_sources = verify_sources(PROJECT_ROOT)
    series = {
        accession: read_geo_series_metadata(
            RAW_ROOT / f"{accession}_series_matrix.txt.gz"
        )
        for accession in ("GSE16879", "GSE73661", "GSE92415")
    }
    records = {
        "GSE16879": select_gse16879(series["GSE16879"]),
        "GSE73661": select_gse73661(series["GSE73661"]),
        "GSE92415": select_gse92415(series["GSE92415"]),
    }

    annotations = {
        platform: load_platform_annotation(RAW_ROOT / f"{platform}.annot.gz")
        for platform in ("GPL570", "GPL6244", "GPL13158")
    }
    platform_by_cohort = {
        "GSE16879": "GPL570",
        "GSE73661": "GPL6244",
        "GSE92415": "GPL13158",
    }
    genes = {}
    for accession, platform in platform_by_cohort.items():
        expression = load_expression(RAW_ROOT / f"{accession}_series_matrix.txt.gz")
        selected_ids = [record.sample_id for record in records[accession]]
        missing_ids = sorted(set(selected_ids) - set(expression.columns))
        if missing_ids:
            raise ValueError(f"Expression table for {accession} is missing {missing_ids}")
        genes[accession] = collapse_to_genes(
            expression.loc[:, selected_ids], annotations[platform]
        )

    identity = cross_platform_identity_audit(
        genes["GSE16879"],
        genes["GSE73661"],
        records["GSE16879"],
        records["GSE73661"],
    )
    common_genes = sorted(
        set(genes["GSE16879"].index)
        & set(genes["GSE73661"].index)
        & set(genes["GSE92415"].index)
    )

    development_records = records["GSE16879"] + records["GSE73661"]
    write_records(
        PROCESSED_ROOT / "development" / "metadata.csv",
        development_records,
        include_response=True,
    )
    write_records(
        PROCESSED_ROOT / "sealed" / "metadata.csv",
        records["GSE92415"],
        include_response=False,
    )
    write_records(
        PRIVATE_ROOT / "gse92415_labels.csv",
        records["GSE92415"],
        include_response=True,
    )
    for accession, matrix in genes.items():
        if accession == "GSE92415":
            output = PROCESSED_ROOT / "sealed" / f"{accession}_gene_expression.csv.gz"
        else:
            output = PROCESSED_ROOT / "development" / f"{accession}_gene_expression.csv.gz"
        output.parent.mkdir(parents=True, exist_ok=True)
        matrix.loc[common_genes].to_csv(output, compression="gzip", float_format="%.7g")

    source_gene_counts = {
        accession: int(matrix.shape[0]) for accession, matrix in genes.items()
    }
    report = {
        "schema_version": "0.1",
        "stage": 2,
        "source_verification": verified_sources,
        "cohorts": {
            accession: cohort_summary(cohort_records)
            for accession, cohort_records in records.items()
        },
        "features": {
            "unambiguous_annotation_mappings": {
                platform: len(mapping) for platform, mapping in annotations.items()
            },
            "gene_counts_before_intersection": source_gene_counts,
            "three_platform_common_gene_count": len(common_genes),
            "collapse_rule": "median_across_unambiguously_mapped_probes",
        },
        "cross_accession_identity_audit": identity,
        "sealed_data_policy": {
            "agent_visible_metadata_contains_response": False,
            "private_label_path": "grader_private/data/gse92415_labels.csv",
            "raw_gse92415_matrix_agent_visible": False,
        },
        "gate_decision": (
            "modify_design_due_to_reprofiled_development_patients"
            if identity["near_identity_signal"]
            else "proceed_for_diligence_not_biomarker_discovery"
        ),
    }
    write_json(EVIDENCE_ROOT / "stage_02_data_feasibility.json", report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

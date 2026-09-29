"""Strict, dependency-free readers for GEO series-matrix metadata."""

from __future__ import annotations

import csv
import gzip
import re
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from uc_bench.errors import ContractError

_NORMALIZE_KEY = re.compile(r"[^a-z0-9]+")


def normalize_metadata_key(value: str) -> str:
    """Normalize a GEO characteristic label without guessing its meaning."""

    return _NORMALIZE_KEY.sub("_", value.strip().lower()).strip("_")


def _open_text(path: Path) -> TextIO:
    if path.suffix == ".gz":
        return gzip.open(path, mode="rt", encoding="utf-8", newline="")
    return path.open(encoding="utf-8", newline="")


def _metadata_rows(path: Path) -> Iterator[list[str]]:
    with _open_text(path) as handle:
        for raw_line in handle:
            if raw_line.startswith("!series_matrix_table_begin"):
                return
            if not raw_line.startswith("!"):
                continue
            yield next(csv.reader([raw_line], delimiter="\t", quotechar='"'))


@dataclass(frozen=True, slots=True)
class GeoSample:
    """One sample's public metadata from a GEO series matrix."""

    accession: str
    title: str
    source: str
    platform_id: str
    characteristics: dict[str, tuple[str, ...]]

    def characteristic(self, key: str) -> str | None:
        """Return one characteristic value, rejecting ambiguous duplicates."""

        values = self.characteristics.get(normalize_metadata_key(key), ())
        if not values:
            return None
        unique = tuple(dict.fromkeys(values))
        if len(unique) != 1:
            raise ContractError(
                f"Sample {self.accession} has conflicting {key!r} values: {unique}"
            )
        return unique[0]


@dataclass(frozen=True, slots=True)
class GeoSeriesMetadata:
    """Series-level fields and ordered sample metadata."""

    accession: str
    title: str
    platform_ids: tuple[str, ...]
    samples: tuple[GeoSample, ...]


def _one_series_value(rows: dict[str, list[list[str]]], field: str) -> str:
    values = [value for row in rows.get(field, []) for value in row]
    unique = tuple(dict.fromkeys(values))
    if len(unique) != 1:
        raise ContractError(f"Expected one {field} value; found {unique}")
    return unique[0]


def read_geo_series_metadata(path: Path) -> GeoSeriesMetadata:
    """Read and validate the metadata prefix of a GEO series-matrix file."""

    if not path.is_file():
        raise ContractError(f"GEO series matrix does not exist: {path}")

    rows: dict[str, list[list[str]]] = defaultdict(list)
    for row in _metadata_rows(path):
        if row:
            rows[row[0]].append(row[1:])

    accessions_rows = rows.get("!Sample_geo_accession", [])
    if len(accessions_rows) != 1 or not accessions_rows[0]:
        raise ContractError("Expected one non-empty !Sample_geo_accession row")
    accessions = accessions_rows[0]
    if len(accessions) != len(set(accessions)):
        raise ContractError("GEO sample accessions must be unique")

    sample_count = len(accessions)
    for field, field_rows in rows.items():
        if not field.startswith("!Sample_"):
            continue
        for values in field_rows:
            if len(values) != sample_count:
                raise ContractError(
                    f"{field} has {len(values)} values for {sample_count} samples"
                )

    def required_sample_row(field: str) -> list[str]:
        field_rows = rows.get(field, [])
        if len(field_rows) != 1:
            raise ContractError(f"Expected exactly one {field} row")
        return field_rows[0]

    titles = required_sample_row("!Sample_title")
    sources = required_sample_row("!Sample_source_name_ch1")
    platforms = required_sample_row("!Sample_platform_id")
    characteristic_rows = rows.get("!Sample_characteristics_ch1", [])

    samples: list[GeoSample] = []
    for index, accession in enumerate(accessions):
        characteristics: dict[str, list[str]] = defaultdict(list)
        for values in characteristic_rows:
            raw = values[index].strip()
            if not raw:
                continue
            label, separator, value = raw.partition(":")
            key = normalize_metadata_key(label if separator else "unlabelled")
            characteristics[key].append(value.strip() if separator else raw)
        samples.append(
            GeoSample(
                accession=accession,
                title=titles[index],
                source=sources[index],
                platform_id=platforms[index],
                characteristics={
                    key: tuple(values) for key, values in sorted(characteristics.items())
                },
            )
        )

    platform_ids = tuple(dict.fromkeys(platforms))
    return GeoSeriesMetadata(
        accession=_one_series_value(rows, "!Series_geo_accession"),
        title=_one_series_value(rows, "!Series_title"),
        platform_ids=platform_ids,
        samples=tuple(samples),
    )

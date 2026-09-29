"""One authoritative prospective-cohort representation for Case-1 RC5."""

from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from uc_bench.mmmvp_open_rc17_contract import EXCLUSION_REASONS

MANIFEST_COLUMNS = (
    "entity_id",
    "source_record_ids",
    "included",
    "preoutcome_exclusion_reason",
)


def _read_csv(path: Path, *, exact_columns: tuple[str, ...] | None = None) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = tuple(reader.fieldnames or ())
        if exact_columns is not None and (
            len(fieldnames) != len(exact_columns) or set(fieldnames) != set(exact_columns)
        ):
            raise ValueError("eligible manifest columns must exactly match the public contract")
        return list(reader)


def _safe_visible_file(workspace: Path, relative: Any, *, work_only: bool = False) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ValueError("a nonempty relative path is required")
    path = (workspace / relative).resolve()
    if workspace.resolve() not in path.parents or not path.is_file():
        raise ValueError(f"visible file does not exist: {relative}")
    if work_only and not relative.startswith("work/"):
        raise ValueError("the eligible manifest must be saved under work/")
    if relative.startswith(("revealed/", "purchased/")):
        raise ValueError("prospective evidence cannot come from revealed or purchased files")
    return path


@dataclass(frozen=True)
class CohortEntity:
    entity_id: str
    source_record_ids: tuple[str, ...]
    included: bool
    exclusion_reason: str | None
    exclusion_evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class CommittedCohort:
    """Validated baseline universe and immutable pre-reveal membership decision."""

    manifest_path: str
    observed_sha256: str
    committed_sha256: str
    host_input_sha256: str | None
    universe: tuple[CohortEntity, ...]
    faults: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.faults

    @property
    def included_entities(self) -> frozenset[str]:
        return frozenset(row.entity_id for row in self.universe if row.included)

    @property
    def excluded_entities(self) -> frozenset[str]:
        return frozenset(row.entity_id for row in self.universe if not row.included)

    @property
    def source_records(self) -> dict[str, tuple[str, ...]]:
        return {row.entity_id: row.source_record_ids for row in self.universe}

    @property
    def included_source_records(self) -> frozenset[str]:
        return frozenset(
            source for row in self.universe if row.included for source in row.source_record_ids
        )

    def details(self) -> dict[str, Any]:
        return {
            "path": self.manifest_path,
            "observed_sha256": self.observed_sha256,
            "committed_sha256": self.committed_sha256,
            "host_input_sha256": self.host_input_sha256,
            "hashes_match": bool(
                self.observed_sha256
                and self.observed_sha256 == self.committed_sha256
                and (
                    self.host_input_sha256 is None or self.observed_sha256 == self.host_input_sha256
                )
            ),
            "listed_entity_count": len(self.universe),
            "included_entity_count": len(self.included_entities),
            "excluded_entity_count": len(self.excluded_entities),
            "faults": list(self.faults),
        }


def reconstruct_committed_cohort(
    workspace: Path,
    validation_plan: dict[str, Any],
    *,
    host_input_hashes: dict[str, str] | None = None,
) -> CommittedCohort:
    """Validate the complete manifest from only pre-outcome visible evidence."""

    workspace = workspace.resolve()
    faults: list[str] = []
    spec = validation_plan.get("prospective_specification") or {}
    relative = spec.get("eligible_entity_manifest_path")
    committed_hash = str(spec.get("eligible_entity_manifest_sha256") or "")
    observed_hash = ""
    rows: list[dict[str, str]] = []
    try:
        manifest_path = _safe_visible_file(workspace, relative, work_only=True)
        observed_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        rows = _read_csv(manifest_path, exact_columns=MANIFEST_COLUMNS)
    except (csv.Error, OSError, TypeError, UnicodeError, ValueError) as exc:
        faults.append(f"eligible_manifest_invalid:{type(exc).__name__}:{exc}")
    host_hash = None if host_input_hashes is None else host_input_hashes.get(str(relative))
    if not observed_hash or observed_hash != committed_hash:
        faults.append("eligible_manifest_hash_mismatch")
    if host_input_hashes is not None and observed_hash != host_hash:
        faults.append("eligible_manifest_host_hash_mismatch")

    try:
        metadata_path = _safe_visible_file(workspace, "data/cohort_metadata.csv")
        with metadata_path.open(encoding="utf-8", newline="") as handle:
            metadata = list(csv.DictReader(handle))
        grouped: dict[str, list[str]] = {}
        for row in metadata:
            if str(row.get("baseline_eligible", "")).strip().lower() == "true":
                entity, source = str(row["fingerprint_cluster"]), str(row["sample_id"])
                grouped.setdefault(entity, []).append(source)
        if not grouped:
            raise ValueError("baseline-eligible universe is empty")
        if len({source for values in grouped.values() for source in values}) != sum(
            len(values) for values in grouped.values()
        ):
            raise ValueError("one source record maps to multiple biological entities")
    except (csv.Error, KeyError, OSError, TypeError, UnicodeError, ValueError) as exc:
        grouped = {}
        faults.append(f"baseline_universe_invalid:{type(exc).__name__}:{exc}")

    exclusions: dict[str, dict[str, Any]] = {}
    for index, exclusion in enumerate(spec.get("exclusions") or []):
        if not isinstance(exclusion, dict):
            faults.append(f"exclusion_not_object:{index}")
            continue
        entity = exclusion.get("entity_id")
        if not isinstance(entity, str) or not entity or entity in exclusions:
            faults.append(f"exclusion_entity_invalid_or_duplicate:{index}")
            continue
        exclusions[entity] = exclusion

    by_entity: dict[str, dict[str, str]] = {}
    for index, row in enumerate(rows):
        entity = row.get("entity_id", "")
        if not entity or entity in by_entity:
            faults.append(f"manifest_entity_blank_or_duplicate:{index}")
            continue
        by_entity[entity] = row
    if set(by_entity) != set(grouped):
        faults.append("manifest_does_not_list_baseline_universe_exactly_once")

    try:
        endpoint_path = _safe_visible_file(workspace, "data/endpoint_source_ledger.csv")
        with endpoint_path.open(encoding="utf-8", newline="") as handle:
            endpoint = {row["patient_key"]: row for row in csv.DictReader(handle)}
        prediction_path = _safe_visible_file(workspace, "data/locked_predictions.csv")
        with prediction_path.open(encoding="utf-8", newline="") as handle:
            predicted_sources = {row["sample_id"] for row in csv.DictReader(handle)}
    except (csv.Error, KeyError, OSError, TypeError, UnicodeError, ValueError) as exc:
        endpoint, predicted_sources = {}, set()
        faults.append(f"preoutcome_evidence_invalid:{type(exc).__name__}:{exc}")

    entities: list[CohortEntity] = []
    for entity in sorted(grouped):
        row = by_entity.get(entity)
        if row is None:
            continue
        observed_sources = tuple(sorted(filter(None, row.get("source_record_ids", "").split("|"))))
        wanted_sources = tuple(sorted(grouped[entity]))
        if observed_sources != wanted_sources or len(set(observed_sources)) != len(
            observed_sources
        ):
            faults.append(f"source_membership_mismatch:{entity}")
        included_text = row.get("included", "").strip().lower()
        if included_text not in {"true", "false"}:
            faults.append(f"included_boolean_invalid:{entity}")
        included = included_text == "true"
        manifest_reason = row.get("preoutcome_exclusion_reason", "").strip()
        exclusion = exclusions.get(entity)
        evidence_refs: tuple[str, ...] = ()
        if included:
            if manifest_reason or exclusion is not None:
                faults.append(f"included_entity_has_exclusion:{entity}")
            if any(source not in predicted_sources for source in wanted_sources):
                faults.append(f"included_entity_missing_prediction:{entity}")
        else:
            if exclusion is None:
                faults.append(f"excluded_entity_missing_committed_exclusion:{entity}")
            else:
                reason = exclusion.get("reason")
                refs = exclusion.get("evidence_refs")
                if reason not in EXCLUSION_REASONS or manifest_reason != reason:
                    faults.append(f"exclusion_reason_invalid_or_mismatched:{entity}")
                if not isinstance(refs, list) or not refs:
                    faults.append(f"exclusion_evidence_missing:{entity}")
                    refs = []
                visible_refs: list[str] = []
                for ref in refs:
                    try:
                        _safe_visible_file(workspace, ref)
                        visible_refs.append(str(ref))
                    except (OSError, TypeError, ValueError):
                        faults.append(f"exclusion_evidence_not_preoutcome_visible:{entity}")
                evidence_refs = tuple(sorted(set(visible_refs)))
                if reason == "PREOUTCOME_ENDPOINT_AMBIGUITY":
                    status = str(endpoint.get(entity, {}).get("review_status", "")).lower()
                    if "data/endpoint_source_ledger.csv" not in evidence_refs or not any(
                        marker in status for marker in ("discordant", "pending", "ambiguous")
                    ):
                        faults.append(f"endpoint_ambiguity_not_supported:{entity}")
                elif reason == "PREOUTCOME_MISSING_PREDICTION":
                    if "data/locked_predictions.csv" not in evidence_refs or any(
                        source in predicted_sources for source in wanted_sources
                    ):
                        faults.append(f"missing_prediction_not_supported:{entity}")
        entities.append(
            CohortEntity(
                entity_id=entity,
                source_record_ids=wanted_sources,
                included=included,
                exclusion_reason=manifest_reason or None,
                exclusion_evidence_refs=evidence_refs,
            )
        )
    if set(exclusions) != {row.entity_id for row in entities if not row.included}:
        faults.append("manifest_and_committed_exclusions_differ")

    return CommittedCohort(
        manifest_path=str(relative or ""),
        observed_sha256=observed_hash,
        committed_sha256=committed_hash,
        host_input_sha256=host_hash,
        universe=tuple(entities),
        faults=tuple(dict.fromkeys(faults)),
    )


def cohort_issues(cohort: CommittedCohort) -> list[dict[str, Any]]:
    return [
        {
            "path": "prospective_specification.eligible_entity_manifest_path",
            "code": fault.split(":", 1)[0],
            "message": fault,
        }
        for fault in cohort.faults
    ]


__all__ = [
    "CohortEntity",
    "CommittedCohort",
    "MANIFEST_COLUMNS",
    "cohort_issues",
    "reconstruct_committed_cohort",
]

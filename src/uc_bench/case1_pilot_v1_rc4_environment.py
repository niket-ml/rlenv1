"""RC4 Case-1 environment with disclosed, representation-neutral artifacts."""

from __future__ import annotations

import copy
import json

from uc_bench.case1_pilot_v1_rc4_contract import (
    PUBLIC_CONTRACT,
    RESOURCE_RETURN_SCHEMA_VERSION,
    RESOURCE_SUMMARY_SCHEMA_VERSION,
)
from uc_bench.mmmvp_open_rc17_environment import RC17OpenMMMVPEnvironment

_COMPLETION_NOTE = """

The full investigation is one autonomous mission. Continue through every
irreversible stage and finish with a contract-valid submit call. No later user
confirmation will be provided.
"""

_FIELD_GUIDE_APPENDIX = f"""

## RC4 representation rules

Split names are semantic labels, not secret vocabulary. A primary analysis may
use PRIMARY, VALIDATION, or another nonempty label when the table uses it
consistently and each calculation names the same value in cohort.split_values.
Primary-cohort identity comes from the committed entity manifest, source-record
membership and hashes.

For a primary calculation, cohort.entity_ids may be an empty list to mean the
entire prospectively committed included cohort. If nonempty, it must equal that
complete cohort. In either form the verified analysis table itself must contain
exactly the complete committed cohort; an empty list never authorizes a subset.

CALCULATION_OUTPUT JSON files accept either a list in typed_calculations or an
object keyed by calculation ID. Run `python validate_saved_artifact.py <path>`
to check either form locally. The agent-authored resource summary uses schema
version `{RESOURCE_SUMMARY_SCHEMA_VERSION}`. The purchased resource manifest is
an environment-returned package and separately uses
`{RESOURCE_RETURN_SCHEMA_VERSION}`.

submission_contract.json publishes the ten-property dependency graph. A defect
in one calculation does not erase unrelated verified calculations, although a
genuinely shared upstream defect can affect its true downstream dependants.
"""

_ARTIFACT_VALIDATOR = r'''#!/usr/bin/env python3
"""No-answer validator for disclosed RC4 calculation-output containers."""
import json
import math
import pathlib
import sys


RESULT_KEYS = {
    "none": {"new_evidence"},
    "X17": {"canonical_entity_count", "unresolved_record_count"},
    "X24": {
        "changed_label_count", "reviewer_disagreement_count", "roc_auc",
        "binary_concordance", "brier_score", "log_loss", "calibration_error",
        "net_benefit", "threshold_expected_utility", "worst_site_roc_auc",
        "site_weighted_roc_auc",
    },
    "X31": {"roc_auc", "brier_score", "net_benefit", "primary_auc_absolute_delta"},
    "X46": {"entity_count", "roc_auc", "brier_score", "net_benefit"},
    "X58": {"entity_count", "roc_auc", "brier_score", "net_benefit"},
    "X63": {"new_empirical_evidence", "recommendation_count"},
}


class DuplicateKey(ValueError):
    pass


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKey(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def main():
    if len(sys.argv) != 2:
        print(json.dumps({"valid": False, "errors": ["usage: validate_saved_artifact.py PATH"]}))
        return 2
    path = pathlib.Path(sys.argv[1])
    errors = []
    try:
        value = json.loads(path.read_text(), object_pairs_hook=no_duplicates)
    except Exception as exc:
        print(json.dumps({"valid": False, "errors": [f"malformed_json:{type(exc).__name__}"]}))
        return 1
    if isinstance(value, dict) and "typed_calculations" not in value:
        required = {"schema_version", "resource_id", "source_hashes", "results"}
        missing = sorted(required - set(value))
        if missing:
            errors.extend(f"missing resource-summary field: {name}" for name in missing)
        if value.get("schema_version") != "case1-resource-summary-1":
            errors.append("resource summary schema_version must be case1-resource-summary-1")
        if not isinstance(value.get("resource_id"), str) or not value.get("resource_id"):
            errors.append("resource_id must be a nonempty string")
        elif value["resource_id"] not in RESULT_KEYS:
            errors.append("resource_id is not in the disclosed catalogue")
        hashes = value.get("source_hashes")
        if not isinstance(hashes, dict) or any(
            not isinstance(key, str)
            or not key
            or not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            for key, digest in (hashes.items() if isinstance(hashes, dict) else [])
        ):
            errors.append(
                "source_hashes must map nonempty paths to 64-character lowercase SHA-256 strings"
            )
        if not isinstance(value.get("results"), dict):
            errors.append("results must be an object")
        elif (
            value.get("resource_id") in RESULT_KEYS
            and set(value["results"]) != RESULT_KEYS[value["resource_id"]]
        ):
            errors.append("results keys must exactly match the disclosed keys for resource_id")
        result = {
            "valid": not errors,
            "artifact_type": "RESOURCE_SUMMARY",
            "errors": errors,
        }
        print(json.dumps(result, indent=2))
        return int(bool(errors))
    typed = value.get("typed_calculations") if isinstance(value, dict) else None
    rows = []
    if isinstance(typed, list):
        rows = typed
    elif isinstance(typed, dict):
        for key, item in typed.items():
            if not isinstance(item, dict):
                errors.append(f"{key}: value must be an object")
                continue
            row = dict(item)
            if row.get("calculation_id", key) != key:
                errors.append(f"{key}: calculation_id conflicts with object key")
            row["calculation_id"] = key
            rows.append(row)
    else:
        errors.append("typed_calculations must be a list or object")
    seen = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"item {index}: object required")
            continue
        identifier = row.get("calculation_id")
        if not isinstance(identifier, str) or not identifier:
            errors.append(f"item {index}: nonempty calculation_id required")
        elif identifier in seen:
            errors.append(f"item {index}: duplicate calculation_id {identifier}")
        else:
            seen.add(identifier)
        reported = row.get("reported_value")
        if (
            isinstance(reported, bool)
            or not isinstance(reported, (int, float))
            or not math.isfinite(reported)
        ):
            errors.append(f"item {index}: finite numeric reported_value required")
    result = {
        "valid": not errors,
        "artifact_type": "CALCULATION_OUTPUT",
        "normalized_calculation_ids": sorted(seen),
        "errors": errors,
    }
    print(json.dumps(result, indent=2))
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
'''


class RC4Case1Environment(RC17OpenMMMVPEnvironment):
    """Same scientific state machine with corrected visible artifact contracts."""

    def _neutralise_public_descriptions(self) -> None:
        super()._neutralise_public_descriptions()  # noqa: SLF001
        mission = (self.run_root / "MISSION.md").read_text(encoding="utf-8")
        (self.run_root / "MISSION.md").write_text(
            mission.rstrip() + _COMPLETION_NOTE,
            encoding="utf-8",
        )
        guide = (self.run_root / "field_guide.md").read_text(encoding="utf-8")
        (self.run_root / "field_guide.md").write_text(
            guide.rstrip() + _FIELD_GUIDE_APPENDIX,
            encoding="utf-8",
        )
        (self.run_root / "submission_contract.json").write_text(
            json.dumps(PUBLIC_CONTRACT, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        (self.run_root / "scientific_property_dependencies.json").write_text(
            json.dumps(
                PUBLIC_CONTRACT["scientific_property_dependency_graph"],
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        (self.run_root / "validate_saved_artifact.py").write_text(
            _ARTIFACT_VALIDATOR,
            encoding="utf-8",
        )
        templates = self.run_root / "contract_templates"
        list_form = {
            "typed_calculations": [
                {"calculation_id": "C_EXAMPLE", "reported_value": 0.0}
            ]
        }
        object_form = {
            "typed_calculations": {
                "C_EXAMPLE": {"calculation_id": "C_EXAMPLE", "reported_value": 0.0}
            }
        }
        resource_summary = {
            "schema_version": RESOURCE_SUMMARY_SCHEMA_VERSION,
            "resource_id": "none",
            "source_hashes": {},
            "results": {"new_evidence": False},
        }
        for name, value in {
            "calculation_output_list_template.json": list_form,
            "calculation_output_keyed_template.json": object_form,
            "resource_summary_template.json": resource_summary,
        }.items():
            (templates / name).write_text(
                json.dumps(value, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

    def purchase_resource(self, resource_id: str) -> list[str]:
        super().purchase_resource(resource_id)
        target = self.run_root / "purchased" / resource_id
        manifest_path = target / "resource_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["schema_version"] = RESOURCE_RETURN_SCHEMA_VERSION
        manifest["returned_evidence_package_schema_version"] = RESOURCE_RETURN_SCHEMA_VERSION
        manifest["agent_authored_summary_schema_version"] = RESOURCE_SUMMARY_SCHEMA_VERSION
        manifest["analysis_contract"] = copy.deepcopy(
            PUBLIC_CONTRACT["resource_summary_contract"]
        )
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        self._protected_evidence_hashes = self._workspace_hashes()  # noqa: SLF001
        return sorted(
            path.relative_to(self.run_root).as_posix()
            for path in target.rglob("*")
            if path.is_file()
        )


__all__ = ["RC4Case1Environment"]

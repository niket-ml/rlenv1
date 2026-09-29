# ruff: noqa: E501
"""Case-1 RC5 environment backed by the shared public contract objects."""

from __future__ import annotations

import copy
import json

from uc_bench.case1_pilot_v1_rc3_tools import case1_tool_definitions
from uc_bench.case1_pilot_v1_rc4_environment import RC4Case1Environment
from uc_bench.case1_pilot_v1_rc5_cohort import (
    cohort_issues,
    reconstruct_committed_cohort,
)
from uc_bench.case1_pilot_v1_rc5_contract import (
    CONTRACT_COMPLETENESS_AUDIT,
    PUBLIC_CONTRACT,
    RESOURCE_RETURN_SCHEMA_VERSION,
    RESOURCE_SUMMARY_SCHEMA_VERSION,
    validate_final_submission,
    validate_followup_plan,
    validate_validation_plan,
)
from uc_bench.mmmvp_open_environment import OpenProtocolError, _digest_bytes, _json_digest

_FIELD_GUIDE_APPENDIX = """

## RC5 cohort and evidence-graph rules

The committed eligible-entity manifest is the sole definition of the primary
cohort after reveal. It must list the complete baseline-eligible universe once,
including excluded people as `included=false`. Valid exclusions must be made
before reveal, use one of the published reasons, and cite the specific visible
pre-outcome file that establishes the reason. Primary tables contain exactly the
`included=true` entities and source records; excluded entities are not restored.

Resource evidence uses one transitive chain: `resource_assessment` names the
summary artifact, the summary binds returned files using SHA-256, and the saved
results are independently recomputed. `source_hashes` may be either a path-to-hash
object or a list of objects containing exactly `path` and `sha256`; duplicates,
conflicts and missing hashes fail. The resource summary needs no special artifact
role, and returned paths need not be repeated in `evidence_assessments`.

For a valid no-purchase branch, `no_new_evidence.json` contributes no new evidence
and numeric beliefs remain unchanged. An unresolved record excluded prospectively
from the bounded analysis may remain a future gate without forcing a purchase.

After reveal, `revealed/evidence_binding.json` identifies and hashes the actual
outcome file and its entity/outcome columns. Before reveal, only the symbolic
`SEALED_VALIDATION_OUTCOMES` role is available; do not guess a future filename.

The nine externally supplied action tools are also listed, byte-for-byte, in
tool_interface.json. Templates are structural examples, not ready-to-submit
answers; the local validators must pass the completed records and saved artifacts.
"""


def _contract_validator_source() -> str:
    """Generate the local validator from the same public contract object."""

    contract_json = json.dumps(PUBLIC_CONTRACT, sort_keys=True, separators=(",", ":"))
    template = r'''#!/usr/bin/env python3
"""Complete no-answer validator generated from submission_contract.json."""
import csv
import hashlib
import json
import math
import pathlib
import sys

sys.dont_write_bytecode = True
from public_recompute import verify_final_calculations

CONTRACT = json.loads(__CONTRACT_JSON__)
VERSION = CONTRACT["payload_schema_version"]
ENUMS = {key: set(value) for key, value in CONTRACT["enums"].items()}

def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)

def children(values, part):
    result = []
    wildcard = part.endswith("[*]")
    key = part[:-3] if wildcard else part
    for value in values:
        if not isinstance(value, dict) or key not in value:
            continue
        child = value[key]
        if wildcard:
            if isinstance(child, list):
                result.extend(child)
        else:
            result.append(child)
    return result

def at(value, path):
    if path == "$":
        return [value]
    values = [value]
    for part in path.split("."):
        values = children(values, part)
    return values

def type_ok(value, kind, enum_name=None):
    if kind == "object": return isinstance(value, dict)
    if kind == "string": return isinstance(value, str)
    if kind == "identifier": return isinstance(value, str) and bool(value.strip())
    if kind == "enum": return value in ENUMS.get(enum_name, set())
    if kind == "boolean": return isinstance(value, bool)
    if kind == "finite_number": return finite(value)
    if kind == "positive_integer": return isinstance(value, int) and not isinstance(value, bool) and value > 0
    if kind == "integer": return isinstance(value, int) and not isinstance(value, bool)
    if kind == "number[0,1]": return finite(value) and 0 <= value <= 1
    if kind == "sha256":
        return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)
    if kind.startswith("array"):
        if not isinstance(value, list): return False
        if kind in {"array<string>", "array<identifier>"}:
            return all(isinstance(item, str) and bool(item.strip()) for item in value)
        if kind == "array<object>": return all(isinstance(item, dict) for item in value)
        return True
    if kind.startswith("object<"):
        return isinstance(value, dict) and bool(value) and all(
            isinstance(key, str) and bool(key.strip()) and finite(item) and 0 <= item <= 1
            for key, item in value.items()
        )
    return True

def validate_declared_fields(kind, value, errors):
    definition = CONTRACT["objects"][kind]
    fields = [*definition["fields"], *definition.get("additional_required", [])]
    for spec in fields:
        path = spec["path"]
        values = at(value, path)
        parent_path = path.rsplit(".", 1)[0] if "." in path else "$"
        parents = at(value, parent_path)
        conditional = spec.get("required_when")
        required = bool(spec.get("required")) and not conditional
        if required and not values and ("[*]" not in path or parents):
            errors.append(f"missing required field: {path}")
            continue
        for item in values:
            kind_name = spec.get("type")
            if kind_name and not type_ok(item, kind_name, spec.get("enum")):
                errors.append(f"wrong type or value: {path}")
                continue
            if spec.get("nonempty") is True and hasattr(item, "__len__") and len(item) == 0:
                errors.append(f"must be nonempty: {path}")
            if isinstance(item, list):
                minimum = int(spec.get("minimum_items", 0))
                if len(item) < minimum:
                    errors.append(f"{path} needs at least {minimum} item(s)")
                if "exact_items" in spec and len(item) != int(spec["exact_items"]):
                    errors.append(f"{path} needs exactly {spec['exact_items']} item(s)")
                unique = spec.get("unique_by")
                if unique:
                    keys = [row.get(unique) for row in item if isinstance(row, dict)]
                    if len(keys) != len(set(keys)):
                        errors.append(f"{path} must be unique by {unique}")

def safe_path(workspace, relative):
    if not isinstance(relative, str) or not relative or pathlib.Path(relative).is_absolute():
        return None
    path = (workspace / relative).resolve()
    return path if workspace in path.parents and path.is_file() else None

def decision_tuple(decision, label, errors):
    if not isinstance(decision, dict): return
    stage, disposition, scope = (
        decision.get("development_stage"), decision.get("disposition"), decision.get("use_scope")
    )
    if disposition == "CONTINUE" and (stage == "STOPPED" or scope not in {"RESEARCH_RANKING", "RESEARCH_PROBABILITY"}):
        errors.append(f"{label} CONTINUE tuple is inconsistent")
    if disposition == "STOP" and (stage != "STOPPED" or scope != "NO_USE"):
        errors.append(f"{label} STOP tuple is inconsistent")
    if disposition in {"PAUSE", "INSUFFICIENT_EVIDENCE"} and (
        stage == "STOPPED" or scope in {"CLINICAL_DECISION_SUPPORT", "TREATMENT_SELECTION"}
    ):
        errors.append(f"{label} contained-decision tuple is inconsistent")

def numeric_direction(before, after):
    if not finite(before) or not finite(after): return None
    if math.isclose(before, after, abs_tol=1e-12): return "UNCHANGED"
    return "INCREASE" if after > before else "DECREASE"

def validate_manifest(workspace, plan, errors):
    spec = plan.get("prospective_specification") or {}
    relative = spec.get("eligible_entity_manifest_path")
    path = safe_path(workspace, relative)
    if path is None or not str(relative).startswith("work/"):
        errors.append("eligible entity manifest must be an existing work/ file")
        return
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if spec.get("eligible_entity_manifest_sha256") != digest:
        errors.append("eligible entity manifest SHA-256 does not match")
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = tuple(reader.fieldnames or ())
            rows = list(reader)
        required = {"entity_id", "source_record_ids", "included", "preoutcome_exclusion_reason"}
        if len(fields) != 4 or set(fields) != required:
            errors.append("eligible manifest columns differ from the disclosed four columns")
            return
        with (workspace / "data/cohort_metadata.csv").open(encoding="utf-8", newline="") as handle:
            metadata = list(csv.DictReader(handle))
        with (workspace / "data/endpoint_source_ledger.csv").open(encoding="utf-8", newline="") as handle:
            endpoint = {row["patient_key"]: row for row in csv.DictReader(handle)}
        with (workspace / "data/locked_predictions.csv").open(encoding="utf-8", newline="") as handle:
            predicted = {row["sample_id"] for row in csv.DictReader(handle)}
        grouped = {}
        for row in metadata:
            if row.get("baseline_eligible", "").lower() == "true":
                grouped.setdefault(row["fingerprint_cluster"], []).append(row["sample_id"])
        by_entity = {row["entity_id"]: row for row in rows if row.get("entity_id")}
        if len(by_entity) != len(rows) or set(by_entity) != set(grouped):
            errors.append("eligible manifest must list the complete baseline universe exactly once")
        exclusions = {row.get("entity_id"): row for row in spec.get("exclusions", []) if isinstance(row, dict)}
        for entity, sources in grouped.items():
            row = by_entity.get(entity, {})
            observed = sorted(filter(None, row.get("source_record_ids", "").split("|")))
            if observed != sorted(sources) or len(observed) != len(set(observed)):
                errors.append(f"source-record membership mismatch: {entity}")
            included = row.get("included", "").lower()
            if included not in {"true", "false"}:
                errors.append(f"included must be true or false: {entity}")
            exclusion = exclusions.get(entity)
            if included == "true" and (row.get("preoutcome_exclusion_reason") or exclusion):
                errors.append(f"included entity has an exclusion: {entity}")
            if included == "false" and (
                not exclusion or row.get("preoutcome_exclusion_reason") != exclusion.get("reason")
            ):
                errors.append(f"excluded entity lacks its matching committed exclusion: {entity}")
            if included == "false" and exclusion:
                refs = exclusion.get("evidence_refs") or []
                reason = exclusion.get("reason")
                if reason == "PREOUTCOME_ENDPOINT_AMBIGUITY":
                    status = str(endpoint.get(entity, {}).get("review_status", "")).lower()
                    if "data/endpoint_source_ledger.csv" not in refs or not any(
                        marker in status for marker in ("discordant", "pending", "ambiguous")
                    ):
                        errors.append(f"endpoint exclusion lacks supporting pre-outcome evidence: {entity}")
                elif reason == "PREOUTCOME_MISSING_PREDICTION" and (
                    "data/locked_predictions.csv" not in refs or any(source in predicted for source in sources)
                ):
                    errors.append(f"missing-prediction exclusion is unsupported: {entity}")
        if set(exclusions) != {row["entity_id"] for row in rows if row.get("included", "").lower() == "false"}:
            errors.append("manifest exclusions and committed exclusions differ")
    except Exception as exc:
        errors.append(f"eligible manifest cannot be checked: {type(exc).__name__}")

def validate_validation(value, workspace, errors):
    spec = value.get("prospective_specification") or {}
    rows = value.get("decision_criteria") or []
    required_properties = set(ENUMS["criterion_property"])
    properties = [row.get("property") for row in rows if isinstance(row, dict)]
    if len(rows) != len(required_properties) or set(properties) != required_properties:
        errors.append("decision_criteria must contain every required property exactly once")
    metric_fields = {
        "DISCRIMINATION": "discrimination_metric", "PROBABILITY_ACCURACY": "probability_metric",
        "CALIBRATION": "calibration_metric", "THRESHOLD_UTILITY": "utility_metric",
        "CONTEXT_ROBUSTNESS": "context_metric",
    }
    for row in rows:
        if not isinstance(row, dict):
            continue
        prop = row.get("property")
        metric = row.get("metric")
        if prop in metric_fields and metric != spec.get(metric_fields[prop]):
            errors.append(f"criterion metric does not match committed method: {prop}")
        if metric not in set(CONTRACT["criterion_metric_families"].get(prop, [])):
            errors.append(f"criterion metric is outside its property family: {prop}")
        threshold = row.get("threshold")
        comparator = row.get("comparator")
        rule = CONTRACT["non_vacuity"].get(prop, {})
        nonvacuous = finite(threshold) and comparator == rule.get("comparator")
        if nonvacuous and prop == "PROBABILITY_ACCURACY":
            bound = (rule.get("metric_bounds") or {}).get(metric, {})
            if "at_most" in bound:
                nonvacuous = threshold <= bound["at_most"]
            elif "less_than" in bound:
                nonvacuous = threshold < bound["less_than"]
            else:
                nonvacuous = False
        elif nonvacuous:
            bound = rule.get("threshold_bound") or rule.get("strict_threshold_bound") or {}
            if "at_least" in bound: nonvacuous = threshold >= bound["at_least"]
            elif "at_most" in bound: nonvacuous = threshold <= bound["at_most"]
            elif "greater_than" in bound: nonvacuous = threshold > bound["greater_than"]
            elif "less_than" in bound: nonvacuous = threshold < bound["less_than"]
            else: nonvacuous = False
        if not nonvacuous:
            errors.append(f"decision criterion is vacuous or mismatched: {prop}")
    calculation_ids = [row.get("calculation_id") for row in rows if isinstance(row, dict)]
    if len(calculation_ids) != len(set(calculation_ids)):
        errors.append("decision criteria must use unique calculation IDs")
    effects = {row.get("decision_effect_if_true") for row in value.get("hypotheses", []) if isinstance(row, dict)}
    if "SUPPORTS" not in effects or not effects.intersection({"WEAKENS", "INVALIDATES"}):
        errors.append("hypotheses must include competing decision effects")
    if spec.get("dependence_handling") == "PERSON_LEVEL_AGGREGATION" and (
        spec.get("aggregation") not in {"MEAN", "MEDIAN", "FIRST"}
        or spec.get("estimator") != "EMPIRICAL"
        or spec.get("uncertainty_method") != "ENTITY_BOOTSTRAP_PERCENTILE"
    ):
        errors.append("person aggregation requires a supported aggregation, EMPIRICAL and entity bootstrap")
    if spec.get("dependence_handling") == "SOURCE_RECORD_CLUSTERING" and (
        spec.get("aggregation") != "NONE" or spec.get("estimator") != "ENTITY_WEIGHTED"
        or spec.get("uncertainty_method") != "CLUSTER_BOOTSTRAP_PERCENTILE"
    ):
        errors.append("source-record clustering requires NONE, ENTITY_WEIGHTED and cluster bootstrap")
    for field, lower, upper in (
        ("calibration_bin_count", 2, 20), ("uncertainty_replicates", 100, 2000),
        ("uncertainty_level", 0.8, 0.99),
    ):
        item = spec.get(field)
        if not finite(item) or not lower <= item <= upper:
            errors.append(f"{field} is outside the disclosed range")
    try:
        intended = json.loads((workspace / "intended_use.json").read_text())
        if spec.get("utility_threshold") != intended.get("action_threshold"):
            errors.append("utility_threshold must match intended_use.json")
    except Exception: errors.append("intended_use.json cannot be read")
    if spec.get("identity_provenance_path") != "identity_provenance.json":
        errors.append("identity_provenance_path must name the disclosed authoritative file")
    for analysis in value.get("planned_analyses", []):
        if isinstance(analysis, dict):
            for relative in analysis.get("input_paths", []):
                if safe_path(workspace, relative) is None or str(relative).startswith(("revealed/", "purchased/")):
                    errors.append(f"planned input is not pre-outcome visible: {relative}")
            for relative in analysis.get("planned_output_paths", []):
                if not isinstance(relative, str) or not relative.startswith("work/") or ".." in pathlib.PurePosixPath(relative).parts:
                    errors.append(f"planned output must be a safe work/ path: {relative}")
    for relative in value.get("evidence_refs", []):
        if safe_path(workspace, relative) is None or str(relative).startswith(("revealed/", "purchased/")):
            errors.append(f"validation evidence is not pre-outcome visible: {relative}")
    for index, exclusion in enumerate(spec.get("exclusions", [])):
        if not isinstance(exclusion, dict): continue
        for relative in exclusion.get("evidence_refs", []):
            if safe_path(workspace, relative) is None or str(relative).startswith(("revealed/", "purchased/")):
                errors.append(f"exclusion evidence is not pre-outcome visible: {index}")
    validate_manifest(workspace, value, errors)

def validate_followup(value, workspace, errors):
    question = value.get("decision_question_type")
    mapping = CONTRACT["resource_question_mapping"]
    targets = CONTRACT["resource_evidence_target_mapping"]
    if question in mapping and value.get("chosen_resource") != mapping[question]:
        errors.append("chosen_resource does not answer decision_question_type")
    if question in targets and value.get("evidence_target") != targets[question]:
        errors.append("evidence_target does not match decision_question_type")
    threshold = value.get("materiality_threshold")
    if not finite(threshold) or threshold < 0:
        errors.append("materiality_threshold must be finite and non-negative")
    resource = value.get("chosen_resource")
    minimum = CONTRACT["resource_minimum_materiality_thresholds"].get(resource)
    if minimum is not None and finite(threshold) and threshold < minimum:
        errors.append(f"materiality_threshold is below the disclosed floor for {resource}")
    if question in {"CURRENT_DECISION_ALREADY_RESOLVED", "IDENTITY_LINKAGE", "EXPERT_INTERPRETATION"} and threshold != 0:
        errors.append("non-quantitative resource questions use materiality_threshold 0")
    decision_tuple(value.get("current_decision"), "current_decision", errors)
    for index, row in enumerate(value.get("result_contingencies", [])):
        if isinstance(row, dict): decision_tuple(row.get("next_decision"), f"result_contingencies[{index}].next_decision", errors)
    plan_path = workspace / "work/validation_plan.json"
    if plan_path.is_file():
        try:
            plan = json.loads(plan_path.read_text())
            expected = {row["hypothesis_id"]: row["belief"] for row in plan.get("hypotheses", [])}
            if value.get("beliefs_before") != expected:
                errors.append("beliefs_before differs from the saved validation hypotheses")
        except Exception: errors.append("saved validation plan cannot be checked")

def validate_final(value, workspace, errors):
    artifacts = value.get("artifact_manifest") or []
    by_artifact = {}
    for index, row in enumerate(artifacts):
        if not isinstance(row, dict): continue
        identifier = row.get("artifact_id")
        if identifier in by_artifact: errors.append(f"duplicate artifact_id: {identifier}")
        by_artifact[identifier] = row
        path = safe_path(workspace, row.get("path"))
        if path is None: errors.append(f"artifact path is missing or unsafe: {identifier}")
        elif row.get("sha256") and row["sha256"] != hashlib.sha256(path.read_bytes()).hexdigest():
            errors.append(f"artifact SHA-256 mismatch: {identifier}")
        for source in row.get("source_paths", []):
            if safe_path(workspace, source) is None: errors.append(f"artifact source path is missing: {identifier}")
        if row.get("role") == "ANALYSIS_TABLE":
            for field in ("analysis_structure", "aggregation", "column_map"):
                if field not in row: errors.append(f"ANALYSIS_TABLE requires {field}: {identifier}")
            mapping = row.get("column_map") or {}
            if not {"entity_id", "source_record_ids", "prediction", "outcome", "split"}.issubset(mapping):
                errors.append(f"ANALYSIS_TABLE column_map is incomplete: {identifier}")
            if set(mapping) - {"entity_id", "source_record_ids", "prediction", "outcome", "split", "context"}:
                errors.append(f"ANALYSIS_TABLE column_map has an unknown role: {identifier}")
    calculations = value.get("calculations") or []
    calculation_ids = {row.get("calculation_id") for row in calculations if isinstance(row, dict)}
    for row in calculations:
        if not isinstance(row, dict): continue
        if row.get("source_analysis_table_id") not in by_artifact or row.get("output_artifact_id") not in by_artifact:
            errors.append(f"calculation artifact reference does not resolve: {row.get('calculation_id')}")
        uncertainty = row.get("uncertainty")
        if uncertainty is not None and (
            not isinstance(uncertainty, dict)
            or not {"method", "level", "lower", "upper", "replicates", "seed"}.issubset(uncertainty)
        ):
            errors.append(f"uncertainty object is incomplete: {row.get('calculation_id')}")
    for family in ("findings", "claims"):
        for row in value.get(family, []):
            if not isinstance(row, dict): continue
            unknown = set(row.get("calculation_ids", [])) - calculation_ids
            if unknown: errors.append(f"{family} references unknown calculations: {sorted(unknown)}")
            if row.get("status") == "SUPPORTED" and (
                not row.get("evidence_refs") or not row.get("calculation_ids")
            ):
                errors.append(f"SUPPORTED {family} item needs evidence and calculations")
    decision_tuple(value.get("decision"), "decision", errors)
    assessment = value.get("resource_assessment") or {}
    followup_path = workspace / "work/followup_plan.json"
    if followup_path.is_file():
        try:
            followup = json.loads(followup_path.read_text())
            if assessment.get("resource_id") != followup.get("chosen_resource") or assessment.get("question_type") != followup.get("decision_question_type"):
                errors.append("resource assessment differs from saved follow-up commitment")
            contingencies = {
                row.get("contingency_id"): row
                for row in followup.get("result_contingencies", [])
                if isinstance(row, dict) and row.get("contingency_id")
            }
            updates = value.get("belief_updates") or []
            selected_ids = {
                row.get("matched_contingency_id") for row in updates if isinstance(row, dict)
            }
            if len(selected_ids) != 1 or next(iter(selected_ids), None) not in contingencies:
                errors.append("belief updates must select exactly one committed contingency")
            else:
                selected = contingencies[next(iter(selected_ids))]
                expected_updates = {
                    row.get("hypothesis_id"): row.get("direction")
                    for row in selected.get("hypothesis_updates", [])
                    if isinstance(row, dict)
                }
                observed_updates = {
                    row.get("hypothesis_id"): numeric_direction(row.get("before"), row.get("after"))
                    for row in updates if isinstance(row, dict)
                }
                if observed_updates != expected_updates:
                    errors.append("belief directions differ from the selected contingency")
                expected_decision = selected.get("next_decision") or {}
                observed_decision = value.get("decision") or {}
                machine = ("development_stage", "disposition", "use_scope")
                if any(observed_decision.get(key) != expected_decision.get(key) for key in machine):
                    errors.append("final machine decision differs from the selected contingency")
        except Exception: errors.append("saved follow-up plan cannot be checked")
    summary = safe_path(workspace, assessment.get("summary_artifact_path"))
    if summary is None: errors.append("resource summary artifact is missing")
    manifested = {row.get("path") for row in artifacts if isinstance(row, dict)}
    if assessment.get("summary_artifact_path") not in manifested:
        errors.append("resource summary must appear in artifact_manifest")
    plan_path = workspace / "work/validation_plan.json"
    if plan_path.is_file():
        try:
            plan = json.loads(plan_path.read_text())
            errors.extend(verify_final_calculations(workspace, plan, value))
        except Exception as exc:
            errors.append(f"local scientific recomputation failed safely: {type(exc).__name__}")
    else:
        errors.append("save the committed validation plan at work/validation_plan.json for local recomputation")

def main():
    aliases = {"validation": "validation_plan", "followup": "followup_plan", "final": "final_submission"}
    if len(sys.argv) != 3 or (sys.argv[1] not in aliases and sys.argv[1] not in CONTRACT["objects"]):
        raise SystemExit("usage: validate_contract.py validation|followup|final PATH.json")
    kind = sys.argv[1]
    kind = aliases.get(kind, kind)
    workspace = pathlib.Path(__file__).resolve().parent
    try:
        value = json.loads(pathlib.Path(sys.argv[2]).read_text())
    except Exception as exc:
        print(json.dumps({"valid": False, "errors": [f"invalid JSON: {type(exc).__name__}"]}))
        return 1
    errors = []
    if not isinstance(value, dict): errors.append("top-level JSON object required")
    else:
        validate_declared_fields(kind, value, errors)
        if value.get("schema_version") != VERSION: errors.append(f"schema_version must equal {VERSION}")
        {"validation_plan": validate_validation, "followup_plan": validate_followup, "final_submission": validate_final}[kind](value, workspace, errors)
    result = {
        "valid": not errors,
        "local_contract_valid": not errors,
        "environment_evidence_check_still_required": True,
        "errors": errors,
        "note": "This checks public representation and currently visible scientific evidence. The action tool independently authenticates irreversible timing, host records and protected-file hashes.",
    }
    print(json.dumps(result, indent=2))
    return int(bool(errors))

if __name__ == "__main__":
    raise SystemExit(main())
'''
    return template.replace("__CONTRACT_JSON__", repr(contract_json))


def _artifact_validator_source() -> str:
    result_keys = PUBLIC_CONTRACT["resource_summary_contract"]["result_keys"]
    return f'''#!/usr/bin/env python3
"""No-answer local validator generated from the public RC5 artifact contract."""
import json
import hashlib
import math
import pathlib
import sys

sys.dont_write_bytecode = True
from public_recompute import verify_final_calculations

RESULT_KEYS = {result_keys!r}

class DuplicateKey(ValueError):
    pass

def no_duplicates(pairs):
    result = {{}}
    for key, value in pairs:
        if key in result:
            raise DuplicateKey(f"duplicate JSON key: {{key}}")
        result[key] = value
    return result

def source_hashes(value):
    if isinstance(value, dict):
        pairs = list(value.items())
    elif isinstance(value, list):
        pairs = []
        for index, row in enumerate(value):
            if not isinstance(row, dict) or set(row) != {{"path", "sha256"}}:
                raise ValueError(f"source_hashes[{{index}}] must contain exactly path and sha256")
            pairs.append((row["path"], row["sha256"]))
    else:
        raise ValueError("source_hashes must be an object or list")
    normalized = {{}}
    for path, digest in pairs:
        if not isinstance(path, str) or not path or path in normalized:
            raise ValueError("source-hash paths must be nonempty and unique")
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(c not in "0123456789abcdef" for c in digest)
        ):
            raise ValueError("source hashes must be lower-case SHA-256 strings")
        normalized[path] = digest
    return dict(sorted(normalized.items()))

def main():
    if len(sys.argv) != 2:
        print(json.dumps({{"valid": False, "errors": ["usage: validate_saved_artifact.py PATH"]}}))
        return 2
    errors = []
    try:
        value = json.loads(pathlib.Path(sys.argv[1]).read_text(), object_pairs_hook=no_duplicates)
    except Exception as exc:
        print(json.dumps({{"valid": False, "errors": [f"malformed_json:{{type(exc).__name__}}"]}}))
        return 1
    if isinstance(value, dict) and "typed_calculations" not in value:
        resource = value.get("resource_id")
        if value.get("schema_version") != {RESOURCE_SUMMARY_SCHEMA_VERSION!r}:
            errors.append("resource summary schema_version is invalid")
        if resource not in RESULT_KEYS:
            errors.append("resource_id is not in the disclosed catalogue")
        try:
            normalized = source_hashes(value.get("source_hashes"))
        except ValueError as exc:
            normalized = {{}}
            errors.append(str(exc))
        workspace = pathlib.Path(__file__).resolve().parent
        manifest_relative = f"purchased/{{resource}}/resource_manifest.json"
        manifest_path = workspace / manifest_relative
        permitted = {{}}
        required = set()
        if not manifest_path.is_file():
            errors.append("purchased resource manifest is not present")
        else:
            try:
                manifest = json.loads(manifest_path.read_text(), object_pairs_hook=no_duplicates)
                for item in manifest.get("files", []):
                    relative = f"purchased/{{resource}}/{{item['path']}}"
                    returned = workspace / relative
                    digest = item["sha256"]
                    permitted[relative] = digest
                    required.add(relative)
                    if not returned.is_file() or hashlib.sha256(returned.read_bytes()).hexdigest() != digest:
                        errors.append(f"returned file does not match manifest: {{relative}}")
                permitted[manifest_relative] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
            except Exception as exc:
                errors.append(f"resource manifest is malformed: {{type(exc).__name__}}")
        if not required.issubset(normalized):
            errors.append("source_hashes must include every returned resource file")
        if not set(normalized).issubset(permitted):
            errors.append("source_hashes contains a path outside the returned resource package")
        for relative, digest in normalized.items():
            target = workspace / relative
            if not target.is_file() or permitted.get(relative) != digest or hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                errors.append(f"source hash mismatch: {{relative}}")
        if (
            not isinstance(value.get("results"), dict)
            or set(value.get("results") or {{}}) != set(RESULT_KEYS.get(resource, []))
        ):
            errors.append("results keys must exactly match the disclosed keys for resource_id")
        else:
            for key, item in value["results"].items():
                if key in {{"new_evidence", "new_empirical_evidence"}}:
                    if not isinstance(item, bool):
                        errors.append(f"{{key}} must be boolean")
                elif isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item):
                    errors.append(f"{{key}} must be finite numeric")
        plan_path = workspace / "work/validation_plan.json"
        final_path = workspace / "work/final_submission.json"
        if plan_path.is_file() and final_path.is_file():
            try:
                plan = json.loads(plan_path.read_text(), object_pairs_hook=no_duplicates)
                final = json.loads(final_path.read_text(), object_pairs_hook=no_duplicates)
                errors.extend(verify_final_calculations(workspace, plan, final))
            except Exception as exc:
                errors.append(f"full local recomputation failed safely: {{type(exc).__name__}}")
        result = {{
            "valid": not errors,
            "artifact_type": "RESOURCE_SUMMARY",
            "normalized_source_hashes": normalized,
            "errors": errors,
        }}
        print(json.dumps(result, indent=2))
        return int(bool(errors))
    typed = value.get("typed_calculations") if isinstance(value, dict) else None
    rows = []
    if isinstance(typed, list):
        rows = typed
    elif isinstance(typed, dict):
        for key, item in typed.items():
            if not isinstance(item, dict):
                errors.append(f"{{key}}: value must be an object")
                continue
            row = dict(item)
            if row.get("calculation_id", key) != key:
                errors.append(f"{{key}}: calculation_id conflicts with object key")
            row["calculation_id"] = key
            rows.append(row)
    else:
        errors.append("typed_calculations must be a list or object")
    seen = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"item {{index}}: object required")
            continue
        identifier = row.get("calculation_id")
        if not isinstance(identifier, str) or not identifier or identifier in seen:
            errors.append(f"item {{index}}: unique nonempty calculation_id required")
        else:
            seen.add(identifier)
        reported = row.get("reported_value")
        if (
            isinstance(reported, bool)
            or not isinstance(reported, (int, float))
            or not math.isfinite(reported)
        ):
            errors.append(f"item {{index}}: finite numeric reported_value required")
    result = {{
        "valid": not errors,
        "artifact_type": "CALCULATION_OUTPUT",
        "normalized_calculation_ids": sorted(seen),
        "errors": errors,
    }}
    print(json.dumps(result, indent=2))
    return int(bool(errors))

if __name__ == "__main__":
    raise SystemExit(main())
'''


class RC5Case1Environment(RC4Case1Environment):
    """Unchanged state machine with RC5's shared cohort commit check."""

    def _neutralise_public_descriptions(self) -> None:
        super()._neutralise_public_descriptions()  # noqa: SLF001
        guide = (self.run_root / "field_guide.md").read_text(encoding="utf-8")
        guide = guide.replace("python validate_", "python3 validate_")
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
                PUBLIC_CONTRACT["scientific_property_dependency_graph"], indent=2, sort_keys=True
            )
            + "\n",
            encoding="utf-8",
        )
        (self.run_root / "validate_saved_artifact.py").write_text(
            _artifact_validator_source(), encoding="utf-8"
        )
        (self.run_root / "validate_contract.py").write_text(
            _contract_validator_source(), encoding="utf-8"
        )
        (self.run_root / "tool_interface.json").write_text(
            json.dumps(case1_tool_definitions(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        public_recompute_source = (
            self.project_root / "src/uc_bench/case1_pilot_v1_rc5_public_recompute.py"
        ).read_text(encoding="utf-8")
        (self.run_root / "public_recompute.py").write_text(
            public_recompute_source, encoding="utf-8"
        )
        templates = self.run_root / "contract_templates"
        # Inherited examples previously contained valid resource/question enums
        # and could pass the standalone structural checker unchanged. Keep their
        # shape, but make their agent-choice fields explicit placeholders so a
        # template is never an action-ready generic policy or scientific hint.
        for template_name in (
            "followup_plan_template.json",
            "followup_plan_transport_template.json",
        ):
            template_path = templates / template_name
            template = json.loads(template_path.read_text(encoding="utf-8"))
            template.update(
                {
                    "chosen_resource": "REPLACE_WITH_RESOURCE_ID",
                    "decision_question_type": "REPLACE_WITH_QUESTION_TYPE",
                    "evidence_target": "REPLACE_WITH_EVIDENCE_TARGET",
                }
            )
            template_path.write_text(
                json.dumps(template, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
        mapping = {
            "schema_version": RESOURCE_SUMMARY_SCHEMA_VERSION,
            "resource_id": "none",
            "source_hashes": {},
            "results": {"new_evidence": False},
        }
        listed = copy.deepcopy(mapping)
        listed["source_hashes"] = []
        for name, value in {
            "resource_summary_mapping_template.json": mapping,
            "resource_summary_list_template.json": listed,
            "exclusion_item_examples.json": {
                "examples_only_not_a_submission": True,
                "items": [
                    {
                        "entity_id": "REPLACE_WITH_ENTITY_ID",
                        "reason": "PREOUTCOME_ENDPOINT_AMBIGUITY",
                        "evidence_refs": ["REPLACE_WITH_VISIBLE_PREOUTCOME_PATH"],
                    },
                    {
                        "entity_id": "REPLACE_WITH_ENTITY_ID",
                        "reason": "PREOUTCOME_MISSING_PREDICTION",
                        "evidence_refs": ["REPLACE_WITH_VISIBLE_PREOUTCOME_PATH"],
                    },
                ],
            },
        }.items():
            (templates / name).write_text(
                json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )

    def commit_validation_plan(self, payload_json: str) -> dict[str, object]:
        self._count_tool()  # noqa: SLF001
        self._assert_untampered()  # noqa: SLF001
        if self.state.phase != "investigate":
            raise OpenProtocolError("Validation plan can be committed exactly once before reveal")
        try:
            payload = json.loads(payload_json)
        except (TypeError, json.JSONDecodeError, RecursionError):
            payload = None
        result = validate_validation_plan(payload)
        issues = [row.to_dict() for row in result.issues]
        if result.valid:
            assert isinstance(payload, dict)
            cohort = reconstruct_committed_cohort(self.run_root, payload)
            issues.extend(cohort_issues(cohort))
            intended = json.loads((self.run_root / "intended_use.json").read_text())
            if (
                abs(
                    float(payload["prospective_specification"]["utility_threshold"])
                    - float(intended["action_threshold"])
                )
                > 1e-12
            ):
                issues.append(
                    {
                        "path": "prospective_specification.utility_threshold",
                        "code": "intended_threshold_mismatch",
                        "message": (
                            "Utility threshold must equal intended_use.json action_threshold"
                        ),
                    }
                )
            if (
                payload["prospective_specification"]["identity_provenance_path"]
                != "identity_provenance.json"
            ):
                issues.append(
                    {
                        "path": "prospective_specification.identity_provenance_path",
                        "code": "authoritative_provenance_required",
                        "message": "Use identity_provenance.json for the authoritative mapping",
                    }
                )
        if issues:
            self._record("validation_plan_rejected", schema_issues=issues)  # noqa: SLF001
            return {"accepted": False, "schema_issues": issues}
        assert isinstance(payload, dict)
        committed_paths = {
            str(path)
            for analysis in payload["planned_analyses"]
            for path in analysis["input_paths"]
        } | {str(path) for path in payload["evidence_refs"]}
        committed_paths |= {
            payload["prospective_specification"]["eligible_entity_manifest_path"],
            payload["prospective_specification"]["identity_provenance_path"],
        }
        invalid: list[str] = []
        input_hashes: dict[str, str] = {}
        for relative in sorted(committed_paths):
            if relative.startswith(("revealed/", "purchased/")):
                invalid.append(relative)
                continue
            try:
                path = self._safe_visible_path(relative)  # noqa: SLF001
            except OpenProtocolError:
                invalid.append(relative)
                continue
            if not path.is_file():
                invalid.append(relative)
            else:
                input_hashes[relative] = _digest_bytes(path.read_bytes())
        if invalid:
            issues = [
                {
                    "path": "planned_analyses.input_paths",
                    "code": "pre_reveal_file_required",
                    "message": "Committed inputs must exist before reveal",
                    "invalid_paths": invalid,
                }
            ]
            self._record("validation_plan_rejected", schema_issues=issues)  # noqa: SLF001
            return {"accepted": False, "schema_issues": issues}
        (self.records_root / "validation_plan.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (self.run_root / "work/validation_plan.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (self.records_root / "validation_input_hashes.json").write_text(
            json.dumps(input_hashes, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        self._validation_input_hashes = input_hashes  # noqa: SLF001
        self.state.validation_plan_hash = _json_digest(payload)
        self.state.phase = "committed"
        self._record("commit_validation_plan", digest=self.state.validation_plan_hash)  # noqa: SLF001
        return {"accepted": True, "committed_plan_hash": self.state.validation_plan_hash}

    def reveal_validation(self) -> list[str]:
        """Reveal evidence, then publish its non-secret binding only after reveal."""

        files = super().reveal_validation()
        outcomes = self.run_root / "revealed/validation_outcomes.csv"
        binding = self.run_root / "revealed/evidence_binding.json"
        binding.write_text(
            json.dumps(
                {
                    "schema_version": "case1-visible-outcome-binding-1",
                    "role": "SEALED_VALIDATION_OUTCOMES",
                    "path": "revealed/validation_outcomes.csv",
                    "entity_id_column": "patient_key",
                    "outcome_column": "week6_response",
                    "sha256": _digest_bytes(outcomes.read_bytes()),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        self._protected_evidence_hashes = self._workspace_hashes()  # noqa: SLF001
        relative = binding.relative_to(self.run_root).as_posix()
        return sorted([*files, relative])

    def commit_followup_plan(self, payload_json: str) -> dict[str, object]:
        self._count_tool()  # noqa: SLF001
        self._assert_untampered()  # noqa: SLF001
        if self.state.phase != "revealed":
            raise OpenProtocolError(
                "Follow-up plan must be committed after reveal and before purchase"
            )
        try:
            payload = json.loads(payload_json)
        except (TypeError, json.JSONDecodeError, RecursionError):
            payload = None
        result = validate_followup_plan(payload)
        issues = [row.to_dict() for row in result.issues]
        if result.valid:
            assert isinstance(payload, dict)
            validation = json.loads(
                (self.records_root / "validation_plan.json").read_text(encoding="utf-8")
            )
            expected = {row["hypothesis_id"]: row["belief"] for row in validation["hypotheses"]}
            if payload["beliefs_before"] != expected:
                issues.append(
                    {
                        "path": "beliefs_before",
                        "code": "commitment_mismatch",
                        "message": "Preserve validation-plan hypothesis IDs and values",
                    }
                )
        if issues:
            self._record("followup_plan_rejected", schema_issues=issues)  # noqa: SLF001
            return {"accepted": False, "schema_issues": issues}
        assert isinstance(payload, dict)
        (self.records_root / "followup_plan.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (self.run_root / "work/followup_plan.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        self.state.followup_plan_hash = _json_digest(payload)
        self.state.phase = "followup_committed"
        self._record("commit_followup_plan", digest=self.state.followup_plan_hash)  # noqa: SLF001
        return {"accepted": True, "committed_followup_hash": self.state.followup_plan_hash}

    def submit(self, payload_json: str) -> dict[str, object]:
        self._count_tool()  # noqa: SLF001
        self._assert_untampered()  # noqa: SLF001
        if self.state.phase != "purchased":
            raise OpenProtocolError("Final submission requires a completed resource action")
        try:
            payload = json.loads(payload_json)
        except (TypeError, json.JSONDecodeError, RecursionError):
            payload = None
        result = validate_final_submission(payload)
        if not result.valid:
            issues = [row.to_dict() for row in result.issues]
            self._record("submit_rejected", schema_issues=issues)  # noqa: SLF001
            return {"accepted": False, "schema_issues": issues}
        assert isinstance(payload, dict)
        (self.records_root / "final_submission.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        self.state.final_submission_hash = _json_digest(payload)
        self.state.completion_accepted = True
        self.state.phase = "terminal"
        self.state.terminal_reason = "submitted"
        self._record(
            "submit",
            validation_plan_hash=self.state.validation_plan_hash,
            followup_plan_hash=self.state.followup_plan_hash,
            final_submission_hash=self.state.final_submission_hash,
        )  # noqa: SLF001
        return {"accepted": True, "terminal": True}

    def purchase_resource(self, resource_id: str) -> list[str]:
        super().purchase_resource(resource_id)
        target = self.run_root / "purchased" / resource_id
        manifest_path = target / "resource_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["schema_version"] = RESOURCE_RETURN_SCHEMA_VERSION
        manifest["analysis_contract"] = copy.deepcopy(PUBLIC_CONTRACT["resource_summary_contract"])
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        self._protected_evidence_hashes = self._workspace_hashes()  # noqa: SLF001
        return sorted(
            path.relative_to(self.run_root).as_posix()
            for path in target.rglob("*")
            if path.is_file()
        )


__all__ = ["CONTRACT_COMPLETENESS_AUDIT", "RC5Case1Environment"]

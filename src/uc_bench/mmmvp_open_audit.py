"""Deterministic audit of the agent-visible open-ended successor interface."""

from __future__ import annotations

import ast
import csv
import hashlib
import inspect
import json
import re
import shutil
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from uc_bench.mmmvp_blind_interface import (
    NEUTRAL_MISSION,
    OpenExecutionLimits,
    mmmvp_blind_scientific_system_prompt,
    serialized_open_request,
)
from uc_bench.mmmvp_open_controls import CONDITIONS, run_open_controls
from uc_bench.mmmvp_open_environment import (
    OPEN_TOOL_SPECS,
    OpenMMMVPEnvironment,
    mmmvp_open_tool_functions,
)
from uc_bench.mmmvp_open_interventions import (
    RC_PRIVATE_ROOT,
    build_rc_private_assets,
    execute_frozen_x31,
    execute_x31_resource,
    verify_x31_resource,
)
from uc_bench.mmmvp_open_runner import OpenRunConfig, production_request
from uc_bench.mmmvp_open_verifier import SCORE_SOURCE_TABLE

_FORBIDDEN_PROMPT_PATTERNS = (
    r"case[_ -]?0?[1-4]",
    r"signal (?:collapse|remain)",
    r"patient(?:-level)? (?:auc|unit|analysis)",
    r"(?:must|required to|calculate) (?:auc|brier|calibration|net benefit)",
    r"(?:choose|buy|purchase) x(?:17|24|31|46|58|63)",
    r"(?:belief|probability) must (?:increase|decrease)",
    r"(?:final )?decision must",
    r"(?:material|planted|hidden) defect",
    r"signal_collapses|signal_remains",
)

_ALLOWED_SECTIONS = {
    "MISSION": "objective",
    "INTERFACE AND IRREVERSIBLE ACTIONS": "interface_and_security",
    "MACHINE-READABLE CONTRACT": "submission_contract",
    "EXECUTION BUDGET": "execution_budget",
}

_SCIENTIFIC_PROSE_FIELDS = {
    "statement",
    "rationale",
    "question",
    "method",
    "analysis_unit",
    "decision_relevance",
    "limitations",
    "observable_result",
    "next_action",
    "allowed_use",
    "prohibited_use",
    "unresolved_gates",
    "required_next_evidence",
    "remaining_uncertainties",
}


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _json_hash(value: Any) -> str:
    return _sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def _case(condition_id: str) -> tuple[str, str]:
    if condition_id.startswith("case_03_"):
        return "case_03", condition_id.removeprefix("case_03_")
    return condition_id, "default"


def serialized_agent_request(
    limits: OpenExecutionLimits | None = None,
) -> dict[str, Any]:
    """Compatibility alias for the shared audit/production serializer."""

    return serialized_open_request(limits)


def sentence_level_hint_audit() -> list[dict[str, Any]]:
    """Classify every nonempty prompt line and reject answer-bearing directions."""

    prompt = mmmvp_blind_scientific_system_prompt()
    lines = [line.strip() for line in prompt.splitlines() if line.strip()]
    rows: list[dict[str, Any]] = []
    section = "MISSION"
    for index, line in enumerate(lines, start=1):
        if line in _ALLOWED_SECTIONS:
            section = line
            continue
        matches = [
            pattern for pattern in _FORBIDDEN_PROMPT_PATTERNS if re.search(pattern, line, re.I)
        ]
        rows.append(
            {
                "line": index,
                "text": line,
                "category": _ALLOWED_SECTIONS[section],
                "answer_bearing_matches": matches,
                "passed": not matches,
            }
        )
    return rows


def _public_manifest(root: Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or "work" in path.parts:
            continue
        result.append(
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": _sha256(path.read_bytes()),
                "bytes": path.stat().st_size,
            }
        )
    return result


def _tool_implementation_audit() -> dict[str, Any]:
    class StubDocker:
        def inspect_workspace(self, relative_path: str = ".") -> str:
            return relative_path

        def read_file(self, relative_path: str) -> str:
            return relative_path

        def write_file(self, relative_path: str, content: str) -> str:
            return relative_path + content

        def run_command(self, command: str) -> str:
            return command

    class StubCore:
        def record_workspace_tool(self, *_args: Any, **_kwargs: Any) -> None:
            return None

        def commit_validation_plan(self, payload_json: str) -> dict[str, Any]:
            """Irreversibly commit an agent-chosen plan before outcomes are available."""

            return {"payload_json": payload_json}

        def reveal_validation(self) -> list[str]:
            """Reveal sealed outcomes after the validation plan has been committed."""

            return []

        def commit_followup_plan(self, payload_json: str) -> dict[str, Any]:
            """Commit a resource choice and result-contingent actions before purchase."""

            return {"payload_json": payload_json}

        def purchase_resource(self, resource_id: str) -> list[str]:
            """Irreversibly purchase one catalogue resource, including none."""

            return [resource_id]

        def submit(self, payload_json: str) -> dict[str, Any]:
            """Submit the evidence-linked final recommendation after the resource action."""

            return {"payload_json": payload_json}

    functions = mmmvp_open_tool_functions(StubDocker(), StubCore())  # type: ignore[arg-type]
    observed = [
        {
            "name": function.__name__,
            "description": (inspect.getdoc(function) or "").splitlines()[0],
            "parameters": [
                parameter.name
                for parameter in inspect.signature(function).parameters.values()
                if parameter.name not in {"self"}
            ],
        }
        for function in functions
    ]
    expected = [
        {
            "name": row["name"],
            "description": row["description"],
            "parameters": list(row["parameters"]["properties"]),
        }
        for row in OPEN_TOOL_SPECS
    ]
    return {"passed": observed == expected, "observed": observed, "expected": expected}


def _verifier_source_audit() -> dict[str, Any]:
    source = inspect.getsource(__import__("uc_bench.mmmvp_open_verifier", fromlist=["*"]))
    tree = ast.parse(source)
    accessed_prose_fields = sorted(
        {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value in _SCIENTIFIC_PROSE_FIELDS
        }
    )
    requirement_ids = [row["requirement_id"] for row in SCORE_SOURCE_TABLE]
    duplicate_requirements = sorted(
        {item for item in requirement_ids if requirement_ids.count(item) > 1}
    )
    prose_affects_science = [
        row["requirement_id"] for row in SCORE_SOURCE_TABLE if row["prose_can_affect_science"]
    ]
    recursive_number_harvesting_absent = all(
        token not in source for token in ("def _numbers", "def _numeric_evidence")
    )
    passed = (
        not accessed_prose_fields
        and not duplicate_requirements
        and not prose_affects_science
        and recursive_number_harvesting_absent
    )
    return {
        "passed": passed,
        "recursive_number_harvesting_absent": recursive_number_harvesting_absent,
        "typed_calculation_recomputation_used": "verify_typed_calculations" in source,
        "agent_code_presence_scored": False,
        "scientific_prose_fields_accessed": accessed_prose_fields,
        "duplicate_scoring_sources": duplicate_requirements,
        "requirements_where_prose_affects_science": prose_affects_science,
        "score_source_table": list(SCORE_SOURCE_TABLE),
    }


def _control_pass(
    controls: dict[str, Any],
    name: str,
    *,
    expected: bool,
    condition_id: str | None = None,
) -> bool:
    matches = [
        row
        for row in controls["results"]
        if row["control"] == name and (condition_id is None or row["condition_id"] == condition_id)
    ]
    return bool(matches) and all(row["complete_mission_success"] is expected for row in matches)


def _runner_wiring_audit() -> dict[str, Any]:
    import uc_bench.mmmvp_open_runner as runner_module

    request_hashes: list[str] = []
    requests: list[dict[str, Any]] = []
    for index, condition_id in enumerate(CONDITIONS):
        case_id, mechanism = _case(condition_id)
        request = production_request(
            OpenRunConfig(
                run_id=f"audit-{index}",
                model_id="audit/no-network",
                case_id=case_id,
                mechanism=mechanism,
            )
        )
        requests.append(request)
        request_hashes.append(_json_hash(request))
    encoded = json.dumps(requests, sort_keys=True).lower()
    source = inspect.getsource(runner_module)
    old_environment_absent = (
        "from uc_bench.mmmvp_environment" not in source
        and "MMMVPEnvironment(" not in source.replace("OpenMMMVPEnvironment(", "")
    )
    shared_serializer_used = "serialized_open_request" in source
    passed = bool(
        len(set(request_hashes)) == 1
        and requests[0] == serialized_open_request()
        and "grader_private" not in encoded
        and "signal_collapses" not in encoded
        and "signal_remains" not in encoded
        and old_environment_absent
        and shared_serializer_used
    )
    return {
        "passed": passed,
        "request_hashes": request_hashes,
        "same_request_for_all_conditions": len(set(request_hashes)) == 1,
        "matches_shared_audited_request": requests[0] == serialized_open_request(),
        "old_environment_absent": old_environment_absent,
        "shared_serializer_used": shared_serializer_used,
        "private_or_variant_identifier_absent": all(
            token not in encoded
            for token in ("grader_private", "signal_collapses", "signal_remains")
        ),
        "durable_restart_regression": "tests/test_mmmvp_open_repairs.py",
    }


def _intervention_audit(project_root: Path, temporary_root: Path) -> dict[str, Any]:
    private = project_root / RC_PRIVATE_ROOT
    x31_root = private / "case_03/X31"
    collapse = temporary_root / "x31-collapse"
    remains = temporary_root / "x31-remains"
    execute_x31_resource(project_root, "signal_collapses", collapse)
    execute_x31_resource(project_root, "signal_remains", remains)
    collapse_verified = verify_x31_resource(
        project_root,
        "signal_collapses",
        collapse,
        temporary_root / "x31-collapse-rerun",
    )
    remains_verified = verify_x31_resource(
        project_root,
        "signal_remains",
        remains,
        temporary_root / "x31-remains-rerun",
    )
    generated_hashes_differ = _sha256(
        (collapse / "replay_predictions.csv").read_bytes()
    ) != _sha256((remains / "replay_predictions.csv").read_bytes())

    altered_input = temporary_root / "altered-x31-input.csv"
    lines = (
        (x31_root / "validation_inputs_signal_remains.csv").read_text(encoding="utf-8").splitlines()
    )
    first = lines[1].split(",")
    first[1] = str(float(first[1]) + 4.0)
    altered_input.write_text(
        "\n".join([lines[0], ",".join(first), *lines[2:]]) + "\n",
        encoding="utf-8",
    )
    altered_output = temporary_root / "x31-altered"
    execute_frozen_x31(
        x31_root / "training_inputs.csv",
        altered_input,
        x31_root / "frozen_model.json",
        altered_output,
    )
    altered_changes_output = _sha256(
        (altered_output / "replay_predictions.csv").read_bytes()
    ) != _sha256((remains / "replay_predictions.csv").read_bytes())

    alternate_project = temporary_root / "altered-project"
    alternate_private = alternate_project / RC_PRIVATE_ROOT / "case_03/X31"
    alternate_private.mkdir(parents=True)
    shutil.copy2(x31_root / "training_inputs.csv", alternate_private / "training_inputs.csv")
    shutil.copy2(x31_root / "frozen_model.json", alternate_private / "frozen_model.json")
    shutil.copy2(
        altered_input,
        alternate_private / "validation_inputs_signal_remains.csv",
    )
    copied_output_rejected = not verify_x31_resource(
        alternate_project,
        "signal_remains",
        remains,
        temporary_root / "x31-copied-rerun",
    )

    x17 = private / "case_02/X17/canonical_person_crosswalk.csv"
    with x17.open(encoding="utf-8") as handle:
        x17_rows = list(csv.DictReader(handle))
    source_ids = {row["source_record_id"] for row in x17_rows}
    canonical_ids = {row["canonical_person_id"] for row in x17_rows}
    public_metadata = (
        project_root / "tasks/hard_suite_v07/development/case_02/data/cohort_metadata.csv"
    )
    with public_metadata.open(encoding="utf-8") as handle:
        metadata_rows = list(csv.DictReader(handle))
    public_entities = {
        row["fingerprint_cluster"]
        for row in metadata_rows
        if row.get("baseline_eligible", "").lower() == "true"
    }
    x17_resolves_conflict = (
        len(source_ids) == len(x17_rows)
        and len(public_entities) == 96
        and len(canonical_ids) == 95
        and {
            row["canonical_person_id"] for row in x17_rows if row["reported_patient_id"] == "P0017"
        }
        == {"P0017"}
    )
    generation_source = inspect.getsource(build_rc_private_assets)
    passed = all(
        (
            collapse_verified,
            remains_verified,
            generated_hashes_differ,
            altered_changes_output,
            copied_output_rejected,
            x17_resolves_conflict,
            "validation_outcomes" not in generation_source,
        )
    )
    return {
        "passed": passed,
        "x31_collapse_independent_rerun_matches": collapse_verified,
        "x31_remains_independent_rerun_matches": remains_verified,
        "x31_paired_outputs_differ": generated_hashes_differ,
        "x31_altered_input_changes_output": altered_changes_output,
        "x31_copied_output_rejected_after_input_change": copied_output_rejected,
        "x31_asset_generation_reads_outcomes": "validation_outcomes" in generation_source,
        "x17_source_record_count": len(source_ids),
        "x17_public_entity_count": len(public_entities),
        "x17_canonical_entity_count": len(canonical_ids),
        "x17_resolves_planted_conflict": x17_resolves_conflict,
    }


def _release_findings(
    controls: dict[str, Any],
    runner: dict[str, Any],
    verifier: dict[str, Any],
    interventions: dict[str, Any],
) -> list[dict[str, Any]]:
    fixed = {
        "RT-B01": (
            controls["status"] == "passed"
            and _control_pass(controls, "dense_unlabelled_numbers", expected=False)
            and _control_pass(controls, "correct_number_wrong_source_table", expected=False)
            and _control_pass(controls, "hard_coded_values_on_altered_input", expected=False)
        ),
        "RT-B02": runner["passed"],
        "RT-M01": (
            controls["reference_and_two_workflows_pass"]
            and _control_pass(controls, "row_independent_analysis", expected=False)
            and _control_pass(controls, "method_label_without_grouping", expected=False)
        ),
        "RT-M02": all(
            interventions[key]
            for key in (
                "x31_collapse_independent_rerun_matches",
                "x31_remains_independent_rerun_matches",
                "x31_altered_input_changes_output",
                "x31_copied_output_rejected_after_input_change",
            )
        ),
        "RT-M03": (
            interventions["x17_resolves_planted_conflict"]
            and controls["all_disclosed_case2_resource_policies_exercised"]
        ),
        "RT-M04": controls["case1_disclosed_action_alternatives_pass"],
        "RT-m15": controls["harmless_rounding_passes"],
    }
    descriptions = {
        "RT-B01": ("blocking", "Typed calculations replace recursive number harvesting."),
        "RT-B02": ("blocking", "Production and audit use one condition-blind serializer."),
        "RT-M01": ("major", "Entity aggregation and clustered alternatives are accepted."),
        "RT-M02": ("major", "X31 now executes and is independently rerun."),
        "RT-M03": ("major", "X17 adjudicates canonical identity and requires recomputation."),
        "RT-M04": ("major", "Case 1 applies immutable agent-committed criteria."),
        "RT-m15": ("minor", "Harmless numerical rounding is tolerated."),
    }
    results = [
        {
            "finding_id": finding_id,
            "severity": descriptions[finding_id][0],
            "status": "fixed_with_evidence" if passed else "still_unresolved",
            "summary": descriptions[finding_id][1],
        }
        for finding_id, passed in fixed.items()
    ]
    results.append(
        {
            "finding_id": "RT-M14",
            "severity": "major",
            "status": "accepted_limitation",
            "summary": (
                "A simple X31-for-visible-contamination/none-otherwise resource heuristic "
                "remains strong; resource selection is therefore explicitly diagnostic-only, "
                "not a headline benchmark capability. No artificial purchases were added."
            ),
        }
    )
    if verifier["passed"] is False:
        results.append(
            {
                "finding_id": "RC-SCORE-SOURCE",
                "severity": "blocking",
                "status": "still_unresolved",
                "summary": "Verifier has prose or duplicate authoritative scoring sources.",
            }
        )
    return results


def run_open_endedness_audit(
    project_root: Path, temporary_root: Path | None = None
) -> dict[str, Any]:
    """Run all zero-cost interface, public-state, and anti-gaming checks."""

    root = project_root.resolve()
    owned_temporary = temporary_root is None
    if temporary_root is None:
        temporary_root = Path(tempfile.mkdtemp(prefix="uc-open-audit-"))
    temporary_root.mkdir(parents=True, exist_ok=True)
    request = serialized_agent_request()
    request_hash = _json_hash(request)
    request_rows: list[dict[str, Any]] = []
    public_rows: list[dict[str, Any]] = []
    public_manifests: dict[str, list[dict[str, Any]]] = {}
    for index, condition_id in enumerate(CONDITIONS):
        case_id, mechanism = _case(condition_id)
        environment = OpenMMMVPEnvironment(
            root,
            case_id,
            temporary_root / f"visible-{index}",
            mechanism=mechanism,
        )
        public_manifest = _public_manifest(environment.run_root)
        public_manifests[condition_id] = public_manifest
        request_rows.append(
            {
                "condition_id_host_only": condition_id,
                "serialized_request_sha256": request_hash,
                "condition_identifier_in_request": condition_id in json.dumps(request),
                "private_path_in_request": "grader_private" in json.dumps(request),
            }
        )
        public_rows.append(
            {
                "condition_id_host_only": condition_id,
                "visible_files": [row["path"] for row in public_manifest],
                "public_file_manifest": public_manifest,
                "description_hashes": {
                    name: _sha256((environment.run_root / name).read_bytes())
                    for name in (
                        "README.md",
                        "sponsor/assertions.md",
                        "validation_manifest.json",
                        "followup_catalog.json",
                        "submission_contract.json",
                    )
                },
            }
        )
    case3_equal = (
        public_manifests["case_03_signal_collapses"] == public_manifests["case_03_signal_remains"]
    )
    descriptions_uniform = (
        len({json.dumps(row["description_hashes"], sort_keys=True) for row in public_rows}) == 1
    )
    sentence_rows = sentence_level_hint_audit()
    controls = run_open_controls(root, temporary_root / "controls")
    tool_audit = _tool_implementation_audit()
    verifier_audit = _verifier_source_audit()
    runner_audit = _runner_wiring_audit()
    intervention_audit = _intervention_audit(root, temporary_root / "interventions")
    findings = _release_findings(
        controls,
        runner_audit,
        verifier_audit,
        intervention_audit,
    )
    unresolved = [
        row
        for row in findings
        if row["status"] == "still_unresolved" and row["severity"] in {"blocking", "major"}
    ]
    passed = all(
        (
            all(row["passed"] for row in sentence_rows),
            len({row["serialized_request_sha256"] for row in request_rows}) == 1,
            not any(row["condition_identifier_in_request"] for row in request_rows),
            not any(row["private_path_in_request"] for row in request_rows),
            case3_equal,
            descriptions_uniform,
            tool_audit["passed"],
            verifier_audit["passed"],
            runner_audit["passed"],
            intervention_audit["passed"],
            controls["status"] == "passed",
            not unresolved,
        )
    )
    return {
        "schema_version": "uc-bench-open-endedness-audit-1",
        "status": "passed" if passed else "failed",
        "api_requests": 0,
        "neutral_mission_exact": NEUTRAL_MISSION,
        "execution_limits": asdict(OpenExecutionLimits()),
        "serialized_request": request,
        "serialized_request_sha256": request_hash,
        "request_uniformity": request_rows,
        "sentence_level_hint_audit": sentence_rows,
        "tool_implementation_audit": tool_audit,
        "production_runner_wiring_audit": runner_audit,
        "verifier_exact_match_and_duplicate_source_audit": verifier_audit,
        "intervention_execution_audit": intervention_audit,
        "public_interface_audit": public_rows,
        "case3_pre_reveal_variants_byte_identical": case3_equal,
        "case_neutral_descriptions_uniform": descriptions_uniform,
        "controls": controls,
        "red_team_review": {
            "status": "passed" if not unresolved else "failed",
            "findings": findings,
            "unresolved_blocking_or_major_findings": unresolved,
        },
        "temporary_root_was_created": owned_temporary,
    }


__all__ = [
    "run_open_endedness_audit",
    "sentence_level_hint_audit",
    "serialized_agent_request",
]

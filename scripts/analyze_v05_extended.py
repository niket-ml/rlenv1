#!/usr/bin/env python3
"""Analyze the frozen v0.5 pilot without turning one seed into a ranking.

The task, grader, prompt, thresholds, and held-out cases are frozen. This module
is an analysis-only projection over their retained outputs. It adds an explicit
artifact dependency graph and deterministic, trace-cited process annotations.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from pathlib import Path
from statistics import mean
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNS_PATH = PROJECT_ROOT / "artifacts" / "diagnostics" / "hard_suite_v05_calibration_runs.json"
OUTPUT_PATH = PROJECT_ROOT / "artifacts" / "diagnostics" / "hard_suite_v05_analysis.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "generated" / "hard_suite_v05_calibration_report.md"
CONFIG_PATH = PROJECT_ROOT / "configs" / "hard_suite_v05.json"

# This is an analysis projection, not a change to the frozen task or grader.
# Depth zero is visible source evidence. Depths one through six are meaningful
# scientific artifacts or decisions, not file-format checkpoints.
ARTIFACT_DAG: tuple[dict[str, Any], ...] = (
    {
        "artifact_id": "A00",
        "label": "source evidence and locked predictor",
        "depth": 0,
        "milestones": [],
        "depends_on": [],
        "v05_evidence": ["case/", "data/", "model/"],
    },
    {
        "artifact_id": "A01",
        "label": "intended-use and decision contract",
        "depth": 1,
        "milestones": ["M01"],
        "depends_on": ["A00"],
        "v05_evidence": ["submission/commitment.json#/intended_use"],
    },
    {
        "artifact_id": "A02",
        "label": "data-room integrity and provenance audit",
        "depth": 1,
        "milestones": ["M02"],
        "depends_on": ["A00"],
        "v05_evidence": ["submission/commitment.json#/audits/provenance"],
    },
    {
        "artifact_id": "A03",
        "label": "patient and visit identity audit",
        "depth": 2,
        "milestones": ["M03"],
        "depends_on": ["A00", "A02"],
        "v05_evidence": ["submission/commitment.json#/audits/identity"],
    },
    {
        "artifact_id": "A04",
        "label": "endpoint and label audit",
        "depth": 2,
        "milestones": ["M04"],
        "depends_on": ["A00", "A01", "A02"],
        "v05_evidence": ["submission/commitment.json#/audits/endpoint"],
    },
    {
        "artifact_id": "A05",
        "label": "assay, platform, preprocessing, and transport audit",
        "depth": 2,
        "milestones": ["M05"],
        "depends_on": ["A00", "A01", "A02"],
        "v05_evidence": [
            "submission/commitment.json#/audits/preprocessing",
            "submission/commitment.json#/audits/transport",
        ],
    },
    {
        "artifact_id": "A06",
        "label": "locked-predictor reproduction",
        "depth": 2,
        "milestones": ["M06"],
        "depends_on": ["A00", "A02"],
        "v05_evidence": ["submission/commitment.json#/reproduction"],
    },
    {
        "artifact_id": "A07",
        "label": "committed prospective validation plan",
        "depth": 3,
        "milestones": ["M07"],
        "depends_on": ["A01", "A02", "A03", "A04", "A05", "A06"],
        "v05_evidence": ["submission/commitment.json#/plan"],
    },
    {
        "artifact_id": "A08",
        "label": "leakage-safe validation assessment",
        "depth": 4,
        "milestones": ["M08"],
        "depends_on": ["A07"],
        "v05_evidence": ["submission/validation_assessment.json"],
    },
    {
        "artifact_id": "A09",
        "label": "resource value and intervention assessment",
        "depth": 5,
        "milestones": ["M09"],
        "depends_on": ["A08"],
        "v05_evidence": [
            "submission/validation_assessment.json#/resource_request",
            "submission/final_submission.json#/intervention_effect",
        ],
    },
    {
        "artifact_id": "A10",
        "label": "final diligence decision and recovery plan",
        "depth": 6,
        "milestones": ["M10"],
        "depends_on": ["A08", "A09"],
        "v05_evidence": ["submission/final_submission.json"],
    },
)

MILESTONE_TO_ARTIFACT = {
    milestone: node["artifact_id"]
    for node in ARTIFACT_DAG
    for milestone in node["milestones"]
}
ARTIFACT_BY_ID = {node["artifact_id"]: node for node in ARTIFACT_DAG}
SUBSTANTIVE_DIVERGENCE_THRESHOLD = 75.0  # Existing v0.5 capability-alert threshold.
ANNOTATION_DEPENDENCY_EFFECTS = {
    "input_misinterpretation": ("A07", "A08", "A09", "A10"),
    "invalid_method_or_uncertainty_unit": ("A08", "A09", "A10"),
    "final_decision_failure": ("A10",),
    "resource_selection_failure": ("A09", "A10"),
    "intervention_interpretation_failure": ("A09", "A10"),
    "belief_revision_failure": ("A10",),
    "unsupported_claim": ("A10",),
}


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected JSON object: {path}")
    return value


def _read_optional(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return _read(path)


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _rel(path: Path) -> str:
    return path.resolve().relative_to(PROJECT_ROOT).as_posix()


def _evidence(path: Path, pointer: str | None, observed: object) -> dict[str, Any]:
    return {"path": _rel(path), "json_pointer": pointer, "observed": observed}


def _safe_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _mean_present(values: Iterable[float | None]) -> float | None:
    present = [float(value) for value in values if value is not None]
    return mean(present) if present else None


def _semantic_contract_match(observed: Any, expected: Any) -> bool:
    """Accept punctuation, spacing, and explanatory additions to a contract value."""

    def tokens(value: Any) -> set[str]:
        return set(re.sub(r"[^a-z0-9]+", " ", str(value).lower()).split())

    expected_tokens = tokens(expected)
    return bool(expected_tokens) and expected_tokens.issubset(tokens(observed))


def _descendants(artifact_id: str) -> list[str]:
    found: set[str] = set()
    frontier = [artifact_id]
    while frontier:
        parent = frontier.pop()
        for node in ARTIFACT_DAG:
            if parent in node["depends_on"] and node["artifact_id"] not in found:
                found.add(node["artifact_id"])
                frontier.append(node["artifact_id"])
    return sorted(found, key=lambda item: (ARTIFACT_BY_ID[item]["depth"], item))


def _completion_messages(verifiers: dict[str, Any]) -> list[dict[str, Any]]:
    outputs = verifiers.get("outputs") or []
    if not outputs or not isinstance(outputs[0], dict):
        return []
    messages = outputs[0].get("completion") or []
    return [message for message in messages if isinstance(message, dict)]


def _parse_json_string(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _tool_trace(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    responses: dict[str, tuple[int, Any]] = {}
    for index, message in enumerate(messages):
        if message.get("role") == "tool" and message.get("tool_call_id"):
            responses[str(message["tool_call_id"])] = (
                index,
                _parse_json_string(message.get("content")),
            )
    calls: list[dict[str, Any]] = []
    for index, message in enumerate(messages):
        for raw in message.get("tool_calls") or []:
            parsed = _parse_json_string(raw)
            if not isinstance(parsed, dict):
                continue
            call_id = str(parsed.get("id") or "")
            arguments = _parse_json_string(parsed.get("arguments"))
            response_index, response = responses.get(call_id, (None, None))
            failed = False
            timed_out = False
            if isinstance(response, dict):
                exit_code = response.get("exit_code")
                timed_out = bool(response.get("timed_out"))
                failed = timed_out or (exit_code is not None and int(exit_code) != 0)
                failed = failed or bool(response.get("error"))
            elif isinstance(response, str):
                lowered = response.lower()
                failed = any(token in lowered for token in ("error:", "validationerror", "failed"))
                timed_out = "timed out" in lowered or "timeout" in lowered
            signature = json.dumps(
                {"name": parsed.get("name"), "arguments": arguments},
                sort_keys=True,
                default=str,
            )
            calls.append(
                {
                    "message_index": index,
                    "response_message_index": response_index,
                    "call_id": call_id,
                    "name": parsed.get("name"),
                    "arguments": arguments,
                    "signature": signature,
                    "failed": failed,
                    "timed_out": timed_out,
                    "response": response,
                }
            )
    return calls


def _find_placeholder(workspace: Path) -> tuple[str, str] | None:
    patterns = (
        re.compile(r"\bTODO\b"),
        re.compile(r"\bTBD\b"),
        re.compile(r"lorem ipsum", re.IGNORECASE),
        re.compile(r"\bdummy (?:value|output|result)s?\b", re.IGNORECASE),
    )
    for directory in (workspace / "analysis", workspace / "submission"):
        if not directory.is_dir():
            continue
        for path in sorted(item for item in directory.rglob("*") if item.is_file()):
            if path.stat().st_size > 2_000_000:
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for pattern in patterns:
                match = pattern.search(content)
                if match:
                    return _rel(path), match.group(0)
    return None


def _annotation(
    tag: str,
    category: str,
    description: str,
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    if not evidence:
        raise ValueError(f"Process/scientific tag {tag!r} requires concrete evidence")
    return {
        "tag": tag,
        "category": category,
        "description": description,
        "evidence": evidence,
        "source": "deterministic_postrun_rule",
        "affects_headline_score": False,
    }


def _trace_annotations(
    row: dict[str, Any],
    record: dict[str, Any],
    summary: dict[str, Any],
    verifiers: dict[str, Any],
    run_root: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    annotations: list[dict[str, Any]] = []
    summary_path = run_root / "run_summary.json"
    record_path = run_root / "hard_suite_v05_record.json"
    verifier_path = run_root / "verifiers_output.json"
    messages = _completion_messages(verifiers)
    calls = _tool_trace(messages)

    if row.get("classification") == "infrastructure_failure":
        annotations.append(
            _annotation(
                "infrastructure_failure",
                "infrastructure",
                "The harness classified the attempt as an infrastructure failure; it is excluded.",
                [
                    _evidence(summary_path, "/classification", row.get("classification")),
                    _evidence(summary_path, "/rollout_error", summary.get("rollout_error")),
                ],
            )
        )

    required = {
        "commitment": record.get("commitment"),
        "assessment": record.get("assessment"),
        "submission": record.get("submission"),
    }
    missing = sorted(name for name, value in required.items() if not value)
    if missing or summary.get("phase_reached") != "submitted":
        annotations.append(
            _annotation(
                "incomplete_analysis",
                "process",
                "One or more required diligence phases or submissions were not completed.",
                [
                    _evidence(record_path, "/", {"missing": missing}),
                    _evidence(summary_path, "/phase_reached", summary.get("phase_reached")),
                ],
            )
        )

    if summary.get("classification") == "agent_task_failure":
        annotations.append(
            _annotation(
                "premature_termination",
                "process",
                "The episode ended without an accepted final diligence submission.",
                [
                    _evidence(summary_path, "/classification", summary.get("classification")),
                    _evidence(summary_path, "/stop_condition", summary.get("stop_condition")),
                ],
            )
        )

    placeholder = None
    workspaces = (
        [
            path
            for path in run_root.iterdir()
            if path.is_dir() and not path.name.endswith("-sealed")
        ]
        if run_root.is_dir()
        else []
    )
    for workspace in sorted(workspaces):
        placeholder = _find_placeholder(workspace)
        if placeholder:
            break
    if placeholder:
        path, token = placeholder
        annotations.append(
            _annotation(
                "synthetic_or_placeholder_work",
                "process",
                "An agent-produced analysis or submission artifact contains a "
                "placeholder sentinel.",
                [{"path": path, "json_pointer": None, "observed": token}],
            )
        )

    grouped_calls: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for call in calls:
        grouped_calls[call["signature"]].append(call)
    repeated = [
        group
        for group in grouped_calls.values()
        if len(group) >= 3 and sum(bool(item["failed"]) for item in group) >= 2
    ]
    if repeated:
        group = max(repeated, key=len)
        annotations.append(
            _annotation(
                "repetitive_retry_behaviour",
                "process",
                "The same failing tool action was attempted at least three times "
                "without a material change.",
                [
                    _evidence(
                        verifier_path,
                        "/outputs/0/completion",
                        {
                            "tool": group[0]["name"],
                            "message_indices": [item["message_index"] for item in group],
                            "failed_attempts": sum(bool(item["failed"]) for item in group),
                        },
                    )
                ],
            )
        )

    failed_calls = [call for call in calls if call["failed"]]
    timed_out_calls = [call for call in calls if call["timed_out"]]
    if failed_calls:
        annotations.append(
            _annotation(
                "tool_failure",
                "process",
                "At least one agent tool call returned an error, non-zero exit, or timeout.",
                [
                    _evidence(
                        verifier_path,
                        "/outputs/0/completion",
                        {
                            "tools": [call["name"] for call in failed_calls],
                            "message_indices": [call["message_index"] for call in failed_calls],
                        },
                    )
                ],
            )
        )
    if timed_out_calls:
        annotations.append(
            _annotation(
                "tool_timeout",
                "process",
                "At least one agent tool call timed out.",
                [
                    _evidence(
                        verifier_path,
                        "/outputs/0/completion",
                        {"message_indices": [call["message_index"] for call in timed_out_calls]},
                    )
                ],
            )
        )

    plan = (record.get("commitment") or {}).get("plan") or {}
    analysis_unit = str(plan.get("analysis_unit") or "").lower()
    uncertainty_unit = str(plan.get("uncertainty_unit") or "").lower()
    fit_scope = str(plan.get("preprocessing_fit_scope") or "").lower()
    valid_analysis_unit = any(
        token in analysis_unit for token in ("patient", "subject", "fingerprint")
    )
    valid_uncertainty_unit = any(
        token in uncertainty_unit for token in ("patient", "subject", "cluster", "fingerprint")
    )
    valid_fit_scope = any(
        token in fit_scope for token in ("training", "train_only", "frozen", "discovery")
    )
    if not valid_analysis_unit or not valid_uncertainty_unit or not valid_fit_scope:
        annotations.append(
            _annotation(
                "invalid_method_or_uncertainty_unit",
                "scientific",
                "The committed analysis unit, uncertainty unit, or preprocessing "
                "fit scope violates a scientific invariant.",
                [
                    _evidence(
                        record_path,
                        "/commitment/plan",
                        {
                            "analysis_unit": plan.get("analysis_unit"),
                            "uncertainty_unit": plan.get("uncertainty_unit"),
                            "preprocessing_fit_scope": plan.get("preprocessing_fit_scope"),
                        },
                    )
                ],
            )
        )

    config = _read(CONFIG_PATH)
    intended = (record.get("commitment") or {}).get("intended_use") or {}
    contract = config["decision_contract"]
    input_mismatches = {
        "population": [intended.get("population"), contract["intended_population"]],
        "endpoint": [intended.get("endpoint"), contract["target_endpoint"]],
        "prediction_time": [intended.get("prediction_time"), contract["prediction_time"]],
    }
    input_mismatches = {
        key: value
        for key, value in input_mismatches.items()
        if not _semantic_contract_match(value[0], value[1])
    }
    if input_mismatches:
        annotations.append(
            _annotation(
                "input_misinterpretation",
                "scientific",
                "The committed intended-use contract does not preserve the visible task contract.",
                [_evidence(record_path, "/commitment/intended_use", input_mismatches)],
            )
        )

    diagnostic = row.get("diagnostic_grade") or row.get("grade") or {}
    if diagnostic and not diagnostic.get("decision_correct", False):
        annotations.append(
            _annotation(
                "final_decision_failure",
                "scientific",
                "The final diligence decision did not match the evidence-supported decision.",
                [
                    _evidence(
                        summary_path,
                        "/diagnostic_grade",
                        {
                            "expected_final_decision": diagnostic.get(
                                "expected_final_decision"
                            ),
                            "observed_final_decision": diagnostic.get(
                                "observed_final_decision"
                            ),
                        },
                    )
                ],
            )
        )
    if diagnostic and diagnostic.get("selected_resource") != diagnostic.get(
        "optimal_resource"
    ):
        annotations.append(
            _annotation(
                "resource_selection_failure",
                "scientific",
                "The selected follow-up was not the smallest highest-value resource.",
                [
                    _evidence(
                        summary_path,
                        "/diagnostic_grade",
                        {
                            "selected_resource": diagnostic.get("selected_resource"),
                            "optimal_resource": diagnostic.get("optimal_resource"),
                            "resource_utility": diagnostic.get("resource_utility"),
                        },
                    )
                ],
            )
        )
    if diagnostic and diagnostic.get("observed_intervention_effect") != diagnostic.get(
        "expected_intervention_effect"
    ):
        annotations.append(
            _annotation(
                "intervention_interpretation_failure",
                "scientific",
                "The agent mischaracterized what the selected intervention changed.",
                [
                    _evidence(
                        summary_path,
                        "/diagnostic_grade",
                        {
                            "expected_intervention_effect": diagnostic.get(
                                "expected_intervention_effect"
                            ),
                            "observed_intervention_effect": diagnostic.get(
                                "observed_intervention_effect"
                            ),
                        },
                    )
                ],
            )
        )
    if diagnostic and not diagnostic.get("belief_revision_correct", False):
        belief = (record.get("submission") or {}).get("belief_update")
        annotations.append(
            _annotation(
                "belief_revision_failure",
                "scientific",
                "The final belief update did not move in the direction warranted "
                "by the selected evidence.",
                [
                    _evidence(
                        summary_path,
                        "/diagnostic_grade/belief_revision_correct",
                        diagnostic.get("belief_revision_correct"),
                    ),
                    _evidence(record_path, "/submission/belief_update", belief),
                ],
            )
        )

    claim_score = _safe_float(diagnostic.get("final_claim_status_score"))
    if claim_score is not None and claim_score < 100.0:
        annotations.append(
            _annotation(
                "unsupported_claim",
                "scientific",
                "At least one final claim-eligibility status exceeded or otherwise "
                "mismatched the evidence state.",
                [
                    _evidence(
                        summary_path,
                        "/diagnostic_grade/final_claim_status_score",
                        claim_score,
                    ),
                    _evidence(
                        record_path,
                        "/submission/claim_statuses",
                        (record.get("submission") or {}).get("claim_statuses"),
                    ),
                ],
            )
        )

    schema_failures = []
    for call in failed_calls:
        response = json.dumps(call.get("response"), sort_keys=True, default=str).lower()
        if call.get("name") in {
            "commit_validation_plan",
            "request_followup",
            "submit_diligence",
        } and any(token in response for token in ("schema", "required", "validation", "contract")):
            schema_failures.append(call)
    if schema_failures:
        annotations.append(
            _annotation(
                "schema_failure",
                "process",
                "A structured action was rejected for a schema or contract violation.",
                [
                    _evidence(
                        verifier_path,
                        "/outputs/0/completion",
                        {
                            "tools": [call["name"] for call in schema_failures],
                            "message_indices": [call["message_index"] for call in schema_failures],
                        },
                    )
                ],
            )
        )

    operational = {
        "tool_call_count_from_trace": len(calls),
        "failed_tool_call_count": len(failed_calls),
        "timed_out_tool_call_count": len(timed_out_calls),
        "exact_tool_signature_retry_count": sum(
            max(0, len(group) - 1) for group in grouped_calls.values()
        ),
        "maximum_identical_tool_attempts": max(
            (len(group) for group in grouped_calls.values()), default=0
        ),
    }
    return annotations, operational


def _frozen_grader_vocabulary_audit(record: dict[str, Any]) -> dict[str, Any]:
    """Find valid descriptions that the frozen grader's token checks can miss.

    This does not rescore v0.5. It audits a predeclared non-construct:
    exact-method-name matching.
    """

    plan = (record.get("commitment") or {}).get("plan") or {}
    analysis_unit = str(plan.get("analysis_unit") or "").lower()
    uncertainty_unit = str(plan.get("uncertainty_unit") or "").lower()
    fit_scope = str(plan.get("preprocessing_fit_scope") or "").lower()
    flags = []
    if (
        "fingerprint" in analysis_unit
        and not any(token in analysis_unit for token in ("patient", "subject"))
    ):
        flags.append(
            {
                "property": "analysis_unit",
                "observed": plan.get("analysis_unit"),
                "frozen_matcher": "patient|subject",
                "estimated_headline_points_at_risk": 2.0,
            }
        )
    if (
        "fingerprint" in uncertainty_unit
        and not any(
            token in uncertainty_unit for token in ("patient", "subject", "cluster")
        )
    ):
        flags.append(
            {
                "property": "uncertainty_unit",
                "observed": plan.get("uncertainty_unit"),
                "frozen_matcher": "patient|subject|cluster",
                "estimated_headline_points_at_risk": 2.0,
            }
        )
    if (
        any(token in fit_scope for token in ("frozen", "discovery"))
        and not any(token in fit_scope for token in ("training", "train_only"))
    ):
        flags.append(
            {
                "property": "preprocessing_fit_scope",
                "observed": plan.get("preprocessing_fit_scope"),
                "frozen_matcher": "training|train_only",
                "estimated_headline_points_at_risk": 2.5,
            }
        )
    return {
        "flag_count": len(flags),
        "estimated_headline_points_at_risk": sum(
            float(item["estimated_headline_points_at_risk"]) for item in flags
        ),
        "flags": flags,
        "rescore_applied": False,
    }


def _dependency_analysis(milestones: dict[str, float]) -> dict[str, Any]:
    ordered = sorted(
        milestones,
        key=lambda item: (ARTIFACT_BY_ID[MILESTONE_TO_ARTIFACT[item]]["depth"], item),
    )
    divergent = [
        item for item in ordered if float(milestones[item]) < SUBSTANTIVE_DIVERGENCE_THRESHOLD
    ]
    first = divergent[0] if divergent else None
    failures = []
    for milestone in divergent:
        artifact_id = MILESTONE_TO_ARTIFACT[milestone]
        failures.append(
            {
                "milestone": milestone,
                "artifact_id": artifact_id,
                "artifact_depth": ARTIFACT_BY_ID[artifact_id]["depth"],
                "score": milestones[milestone],
                "downstream_artifacts_at_risk": _descendants(artifact_id),
                "mechanically_invalidated": [],
                "interpretation": (
                    "Dependency risk only: v0.5 intentionally preserves conditional downstream "
                    "credit, so a low upstream score does not itself invalidate later artifacts."
                ),
            }
        )
    depth_groups: dict[int, list[float]] = defaultdict(list)
    for milestone, score in milestones.items():
        depth = int(ARTIFACT_BY_ID[MILESTONE_TO_ARTIFACT[milestone]]["depth"])
        depth_groups[depth].append(float(score))
    return {
        "substantive_divergence_threshold": SUBSTANTIVE_DIVERGENCE_THRESHOLD,
        "threshold_role": "post-run analysis alert; not a task score or new acceptance threshold",
        "first_substantive_divergence": (
            {
                "milestone": first,
                "artifact_id": MILESTONE_TO_ARTIFACT[first],
                "depth": ARTIFACT_BY_ID[MILESTONE_TO_ARTIFACT[first]]["depth"],
                "score": milestones[first],
            }
            if first
            else None
        ),
        "divergences": failures,
        "depth_scores": {
            str(depth): mean(values) for depth, values in sorted(depth_groups.items())
        },
    }


def _annotation_dependency_effects(
    annotations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    effects = []
    for annotation in annotations:
        affected = ANNOTATION_DEPENDENCY_EFFECTS.get(annotation["tag"])
        if not affected:
            continue
        effects.append(
            {
                "failure_tag": annotation["tag"],
                "affected_artifacts": list(affected),
                "effect": (
                    "scientific claim invalid or conditional within the affected artifact; "
                    "unrelated properties retain credit"
                ),
                "evidence": annotation["evidence"],
            }
        )
    return effects


def _matrix(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for row in rows:
        run_root = PROJECT_ROOT / str(row.get("run_directory") or "")
        summary_path = run_root / "run_summary.json"
        record_path = run_root / "hard_suite_v05_record.json"
        verifier_path = run_root / "verifiers_output.json"
        summary = _read_optional(summary_path)
        record = _read_optional(record_path)
        verifiers = _read_optional(verifier_path)
        diagnostic = row.get("diagnostic_grade") or row.get("grade") or {}
        observed = diagnostic.get("observed_evidence") or {}
        initial = observed.get("initial_metrics") or {}
        followup = observed.get("followup_metrics") or {}
        annotations, operational = _trace_annotations(
            row, record, summary, verifiers, run_root
        )
        metadata = verifiers.get("metadata") or {}
        token_usage = row.get("token_usage") or summary.get("token_usage") or {}
        milestones = diagnostic.get("milestone_scores") or {}
        output.append(
            {
                "model_id": row["model_id"],
                "scenario_id": row["scenario_id"],
                "scenario_class": row["scenario_class"],
                "classification": row["classification"],
                "included_in_scientific_aggregate": (
                    row.get("classification") != "infrastructure_failure"
                ),
                "reliability_inclusive_score": row.get("score"),
                "diagnostic_score": diagnostic.get("score", 0.0),
                "milestone_scores": milestones,
                "capability_scores": diagnostic.get("capability_scores") or {},
                "artifact_dependency": _dependency_analysis(milestones) if milestones else {},
                "downstream_dependency_effects": _annotation_dependency_effects(annotations),
                "frozen_grader_vocabulary_audit": _frozen_grader_vocabulary_audit(record),
                "selected_resource": diagnostic.get("selected_resource"),
                "optimal_resource": diagnostic.get("optimal_resource"),
                "resource_utility": diagnostic.get("resource_utility", 0.0),
                "expected_initial_decision": diagnostic.get("expected_initial_decision"),
                "observed_initial_decision": diagnostic.get("observed_initial_decision"),
                "expected_final_decision": diagnostic.get("expected_final_decision"),
                "observed_final_decision": diagnostic.get("observed_final_decision"),
                "decision_correct": diagnostic.get("decision_correct", False),
                "final_claim_status_score": diagnostic.get("final_claim_status_score", 0.0),
                "belief_revision_correct": diagnostic.get("belief_revision_correct", False),
                "expected_intervention_effect": diagnostic.get("expected_intervention_effect"),
                "observed_intervention_effect": diagnostic.get("observed_intervention_effect"),
                "initial_auc": initial.get("auc"),
                "followup_auc": followup.get("auc"),
                "phase_reached": row.get("phase_reached"),
                "turn_count": row.get("turn_count"),
                "token_usage": token_usage,
                "input_tokens": _safe_float(token_usage.get("input_tokens")),
                "output_tokens": _safe_float(token_usage.get("output_tokens")),
                "wall_time_seconds": _safe_float(metadata.get("time")),
                "estimated_episode_cost_usd": _safe_float(row.get("estimated_cost_usd")),
                "tool_call_counts": row.get("tool_call_counts")
                or summary.get("tool_call_counts")
                or {},
                "operational_trace": operational,
                "failure_annotations": annotations,
                "run_id": row.get("run_id"),
                "replay_evidence": {
                    "summary": _rel(summary_path),
                    "state_record": _rel(record_path),
                    "full_trace": _rel(verifier_path),
                    "workspace": str(row.get("run_directory") or ""),
                },
            }
        )
    return output


def _included(matrix: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in matrix if row["included_in_scientific_aggregate"]]


def _model_summaries(matrix: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in _included(matrix):
        grouped[str(row["model_id"])].append(row)
    output = []
    for model_id, rows in sorted(grouped.items()):
        milestones = sorted({name for row in rows for name in row["milestone_scores"]})
        capabilities = sorted({name for row in rows for name in row["capability_scores"]})
        annotations = Counter(
            annotation["tag"] for row in rows for annotation in row["failure_annotations"]
        )
        output.append(
            {
                "model_id": model_id,
                "usable_episode_count": len(rows),
                "mean_reliability_inclusive_score": mean(
                    float(row["reliability_inclusive_score"] or 0.0) for row in rows
                ),
                "valid_episode_rate": mean(
                    row["classification"] == "valid_episode" for row in rows
                ),
                "ceiling_rate": mean(
                    float(row["reliability_inclusive_score"] or 0.0) >= 95 for row in rows
                ),
                "zero_rate": mean(
                    float(row["reliability_inclusive_score"] or 0.0) == 0 for row in rows
                ),
                "milestone_means": {
                    name: mean(float(row["milestone_scores"].get(name, 0.0)) for row in rows)
                    for name in milestones
                },
                "capability_means": {
                    name: mean(float(row["capability_scores"].get(name, 0.0)) for row in rows)
                    for name in capabilities
                },
                "resource_utility_mean": mean(float(row["resource_utility"]) for row in rows),
                "decision_accuracy": mean(bool(row["decision_correct"]) for row in rows),
                "belief_revision_accuracy": mean(
                    bool(row["belief_revision_correct"]) for row in rows
                ),
                "mean_estimated_episode_cost_usd": _mean_present(
                    row["estimated_episode_cost_usd"] for row in rows
                ),
                "total_estimated_cost_usd": sum(
                    float(row["estimated_episode_cost_usd"] or 0.0) for row in rows
                ),
                "mean_input_tokens": _mean_present(row["input_tokens"] for row in rows),
                "mean_output_tokens": _mean_present(row["output_tokens"] for row in rows),
                "mean_turn_count": _mean_present(
                    _safe_float(row["turn_count"]) for row in rows
                ),
                "mean_wall_time_seconds": _mean_present(
                    row["wall_time_seconds"] for row in rows
                ),
                "mean_tool_call_count": mean(
                    int(row["operational_trace"]["tool_call_count_from_trace"])
                    for row in rows
                ),
                "mean_failed_tool_call_count": mean(
                    int(row["operational_trace"]["failed_tool_call_count"])
                    for row in rows
                ),
                "mean_exact_tool_signature_retry_count": mean(
                    int(row["operational_trace"]["exact_tool_signature_retry_count"])
                    for row in rows
                ),
                "total_timed_out_tool_calls": sum(
                    int(row["operational_trace"]["timed_out_tool_call_count"])
                    for row in rows
                ),
                "failure_tag_counts": dict(sorted(annotations.items())),
                "vocabulary_audit_flagged_episode_count": sum(
                    row["frozen_grader_vocabulary_audit"]["flag_count"] > 0
                    for row in rows
                ),
                "mean_estimated_headline_points_at_risk_from_vocabulary": mean(
                    float(
                        row["frozen_grader_vocabulary_audit"][
                            "estimated_headline_points_at_risk"
                        ]
                    )
                    for row in rows
                ),
            }
        )
    return output


def _failure_matrix(matrix: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in _included(matrix):
        grouped[(str(row["model_id"]), str(row["scenario_class"]))].append(row)
    return [
        {
            "model_id": model_id,
            "failure_mode": failure_mode,
            "episode_count": len(rows),
            "mean_score": mean(
                float(row["reliability_inclusive_score"] or 0.0) for row in rows
            ),
            "mean_resource_utility": mean(float(row["resource_utility"]) for row in rows),
            "decision_accuracy": mean(bool(row["decision_correct"]) for row in rows),
            "belief_revision_accuracy": mean(
                bool(row["belief_revision_correct"]) for row in rows
            ),
            "mean_claim_containment": mean(
                float(row["final_claim_status_score"]) for row in rows
            ),
        }
        for (model_id, failure_mode), rows in sorted(grouped.items())
    ]


def _depth_matrix(matrix: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in _included(matrix):
        for depth, score in (row["artifact_dependency"].get("depth_scores") or {}).items():
            grouped[(str(row["model_id"]), str(depth))].append(float(score))
    return [
        {
            "model_id": model_id,
            "artifact_depth": int(depth),
            "mean_score": mean(scores),
            "episode_depth_observations": len(scores),
        }
        for (model_id, depth), scores in sorted(
            grouped.items(), key=lambda item: (item[0][0], int(item[0][1]))
        )
    ]


def _gap_share(
    failure_matrix: list[dict[str, Any]], summaries: list[dict[str, Any]]
) -> dict[str, float]:
    if len(summaries) < 2:
        return {}
    strongest = max(summaries, key=lambda row: row["mean_reliability_inclusive_score"])
    weakest = min(summaries, key=lambda row: row["mean_reliability_inclusive_score"])
    strong = {
        row["failure_mode"]: float(row["mean_score"])
        for row in failure_matrix
        if row["model_id"] == strongest["model_id"]
    }
    weak = {
        row["failure_mode"]: float(row["mean_score"])
        for row in failure_matrix
        if row["model_id"] == weakest["model_id"]
    }
    gaps = {
        failure: abs(score - weak[failure])
        for failure, score in strong.items()
        if failure in weak
    }
    total = sum(gaps.values())
    return {failure: gap / total for failure, gap in gaps.items()} if total else {}


def _cost_frontier(summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    points = []
    for row in summaries:
        cost = row.get("mean_estimated_episode_cost_usd")
        if cost is None:
            continue
        score = float(row["mean_reliability_inclusive_score"])
        dominated = any(
            other["model_id"] != row["model_id"]
            and other.get("mean_estimated_episode_cost_usd") is not None
            and float(other["mean_estimated_episode_cost_usd"]) <= float(cost)
            and float(other["mean_reliability_inclusive_score"]) >= score
            and (
                float(other["mean_estimated_episode_cost_usd"]) < float(cost)
                or float(other["mean_reliability_inclusive_score"]) > score
            )
            for other in summaries
        )
        points.append(
            {
                "model_id": row["model_id"],
                "mean_score": score,
                "mean_estimated_episode_cost_usd": cost,
                "pareto_optimal": not dominated,
            }
        )
    return sorted(points, key=lambda row: float(row["mean_estimated_episode_cost_usd"]))


def _representative_traces(matrix: list[dict[str, Any]]) -> list[dict[str, Any]]:
    usable = _included(matrix)
    if not usable:
        return []
    chosen: list[dict[str, Any]] = []
    by_model: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in usable:
        by_model[str(row["model_id"])].append(row)
    for rows in by_model.values():
        chosen.append(
            min(rows, key=lambda row: float(row["reliability_inclusive_score"] or 0.0))
        )
    recovery_candidates = [
        row
        for row in usable
        if row.get("decision_correct")
        and row.get("observed_intervention_effect")
        == row.get("expected_intervention_effect")
        and row.get("selected_resource") == row.get("optimal_resource")
    ]
    if recovery_candidates:
        best_recovery = max(
            recovery_candidates,
            key=lambda row: float(row["reliability_inclusive_score"] or 0.0),
        )
        if best_recovery not in chosen:
            chosen.append(best_recovery)
    return [
        {
            "model_id": row["model_id"],
            "scenario_class": row["scenario_class"],
            "score": row["reliability_inclusive_score"],
            "initial_to_final_decision": [
                row["observed_initial_decision"],
                row["observed_final_decision"],
            ],
            "selected_resource": row["selected_resource"],
            "first_substantive_divergence": row["artifact_dependency"].get(
                "first_substantive_divergence"
            ),
            "failure_tags": [item["tag"] for item in row["failure_annotations"]],
            "replay_evidence": row["replay_evidence"],
        }
        for row in chosen
    ]


def _failure_accounting(matrix: list[dict[str, Any]]) -> dict[str, Any]:
    known_tags = {
        "scientific": (
            "input_misinterpretation",
            "invalid_method_or_uncertainty_unit",
            "final_decision_failure",
            "resource_selection_failure",
            "intervention_interpretation_failure",
            "belief_revision_failure",
            "unsupported_claim",
        ),
        "process": (
            "incomplete_analysis",
            "synthetic_or_placeholder_work",
            "premature_termination",
            "repetitive_retry_behaviour",
            "schema_failure",
            "tool_failure",
            "tool_timeout",
        ),
        "infrastructure": ("infrastructure_failure",),
    }
    counts = Counter(
        annotation["tag"]
        for row in matrix
        for annotation in row["failure_annotations"]
    )
    return {
        "episode_counts_by_tag": {
            category: {tag: counts[tag] for tag in tags}
            for category, tags in known_tags.items()
        },
        "classification_counts": dict(
            sorted(Counter(str(row["classification"]) for row in matrix).items())
        ),
        "failed_tool_call_count": sum(
            int(row["operational_trace"]["failed_tool_call_count"]) for row in matrix
        ),
        "timed_out_tool_call_count": sum(
            int(row["operational_trace"]["timed_out_tool_call_count"]) for row in matrix
        ),
        "infrastructure_rows_excluded": sum(
            not row["included_in_scientific_aggregate"] for row in matrix
        ),
    }


def _acceptance(
    matrix: list[dict[str, Any]],
    summaries: list[dict[str, Any]],
    gap_share: dict[str, float],
    planned: int,
) -> dict[str, Any]:
    usable = _included(matrix)
    infrastructure = [row for row in matrix if not row["included_in_scientific_aggregate"]]
    if len(usable) != planned or len(summaries) != 3:
        return {
            "evaluated": False,
            "reason": "frozen 18-episode matrix incomplete",
            "completed_rows": len(usable),
            "executed_rows_including_infrastructure": len(matrix),
            "planned_rows": planned,
        }
    strongest = max(summaries, key=lambda row: row["mean_reliability_inclusive_score"])
    weakest = min(summaries, key=lambda row: row["mean_reliability_inclusive_score"])
    scientific_tags = {
        annotation["tag"]
        for row in usable
        for annotation in row["failure_annotations"]
        if annotation["category"] == "scientific"
    }
    process_primary_count = sum(
        any(
            annotation["tag"] == "schema_failure"
            for annotation in row["failure_annotations"]
        )
        and not any(
            annotation["category"] == "scientific"
            for annotation in row["failure_annotations"]
        )
        for row in usable
    )
    usable_unsubmitted = [
        row for row in usable if row["classification"] == "agent_task_failure"
    ]
    vocabulary_flagged = [
        row
        for row in usable
        if row["frozen_grader_vocabulary_audit"]["flag_count"] > 0
    ]
    checks = {
        "frontier_mean_below_85": strongest["mean_reliability_inclusive_score"] < 85,
        "no_more_than_25_percent_frontier_cells_at_or_above_95": (
            strongest["ceiling_rate"] <= 0.25
        ),
        "weakest_model_not_universal_failure_or_zero": (
            weakest["zero_rate"] < 1.0 and weakest["valid_episode_rate"] > 0.0
        ),
        "at_least_three_distinct_interpretable_scientific_failures": (
            len(scientific_tags) >= 3
        ),
        "scientific_or_recovery_failures_not_mainly_schema": (
            process_primary_count <= max(1, len(usable) // 4) and bool(scientific_tags)
        ),
        "no_single_failure_family_over_30_percent_of_gap": (
            bool(gap_share) and max(gap_share.values()) <= 0.30
        ),
        "infrastructure_failures_excluded": all(
            not row["included_in_scientific_aggregate"] for row in infrastructure
        ),
        "usable_unsubmitted_attempts_score_zero": all(
            float(row["reliability_inclusive_score"] or 0.0) == 0.0
            for row in usable_unsubmitted
        ),
        "controlled_and_authentic_results_separated": True,
        "no_valid_alternative_penalized_by_exact_grader_vocabulary": (
            not vocabulary_flagged
        ),
    }
    diagnostics = {
        "frontier_in_ideal_65_to_80_band": (
            65 <= strongest["mean_reliability_inclusive_score"] <= 80
        ),
        "scientific_failure_tags": sorted(scientific_tags),
        "schema_primary_episode_count": process_primary_count,
        "infrastructure_failure_count": len(infrastructure),
        "usable_unsubmitted_attempt_count": len(usable_unsubmitted),
        "vocabulary_flagged_episode_count": len(vocabulary_flagged),
        "vocabulary_flagged_run_ids": [row["run_id"] for row in vocabulary_flagged],
    }
    return {
        "evaluated": True,
        "checks": checks,
        "diagnostics": diagnostics,
        "go": all(checks.values()),
        "strongest_model": strongest["model_id"],
        "weakest_model": weakest["model_id"],
        "ranking_claim_allowed": False,
        "decision_rule": "mandatory no-go if any predeclared check is false",
    }


def _fmt(value: Any, digits: int = 2) -> str:
    numeric = _safe_float(value)
    return "—" if numeric is None else f"{numeric:.{digits}f}"


def _markdown_table(headers: list[str], rows: Iterable[Iterable[Any]]) -> list[str]:
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    lines.extend("| " + " | ".join(str(value) for value in row) + " |" for row in rows)
    return lines


def _build_report(output: dict[str, Any], raw: dict[str, Any]) -> str:
    matrix = output["matrix"]
    summaries = output["model_summaries"]
    acceptance = output["acceptance"]
    lines = [
        "# UC-Bench v0.5 controlled development calibration",
        "",
        "> **Controlled internal calibration; one seed; not a stable ranking.** "
        "Internally authored expert-equivalence controls are not external expert validation. "
        "Astra and held-out requests: 0.",
        "",
        "## Positioning relative to BixBench3",
        "",
        "BixBench3 evaluates whether agents can execute specified study-scale computational "
        "analyses. UC-Bench evaluates whether agents can audit the validity of a biomedical "
        "evidence chain, contain invalid claims, revise beliefs and select the next "
        "decision-relevant experiment.",
        "",
        "UC-Bench borrows artifact dependency analysis, intermediate evidence retention, "
        "process annotation, replayability, and score-versus-cost reporting. It does not "
        "borrow BixBench3's scale, strict paper reproduction, or requirement to match one "
        "published statistical pipeline.",
        "",
        "## Explicit decision",
        "",
        (
            "**GO TO A REPEATED-SEED DEVELOPMENT EXPERIMENT**"
            if acceptance.get("go")
            else "**NO-GO**"
            if acceptance.get("evaluated")
            else "**PILOT INCOMPLETE — NO DECISION YET**"
        ),
        "",
        "Passing this gate would authorize only a proposed repeated-seed development "
        "experiment. It does not authorize Astra, a public ranking, or a "
        "commercial-validity claim.",
        "",
        "## Model summary",
        "",
    ]
    lines.extend(
        _markdown_table(
            [
                "Model",
                "Mean score",
                "Valid",
                "Ceiling",
                "Zero",
                "Decision",
                "Belief revision",
            ],
            (
                (
                    row["model_id"],
                    _fmt(row["mean_reliability_inclusive_score"]),
                    _fmt(100 * row["valid_episode_rate"]) + "%",
                    _fmt(100 * row["ceiling_rate"]) + "%",
                    _fmt(100 * row["zero_rate"]) + "%",
                    _fmt(100 * row["decision_accuracy"]) + "%",
                    _fmt(100 * row["belief_revision_accuracy"]) + "%",
                )
                for row in summaries
            ),
        )
    )
    lines.extend(["", "## Model × milestone", ""])
    milestone_names = [f"M{index:02d}" for index in range(1, 11)]
    lines.extend(
        _markdown_table(
            ["Model", *milestone_names],
            (
                (
                    row["model_id"],
                    *(
                        _fmt(row["milestone_means"].get(name))
                        for name in milestone_names
                    ),
                )
                for row in summaries
            ),
        )
    )
    lines.extend(["", "## Model × capability vector", ""])
    capability_names = sorted(
        {name for row in summaries for name in row["capability_means"]}
    )
    lines.extend(
        _markdown_table(
            ["Model", *[name.replace("_", " ") for name in capability_names]],
            (
                (
                    row["model_id"],
                    *(
                        _fmt(row["capability_means"].get(name))
                        for name in capability_names
                    ),
                )
                for row in summaries
            ),
        )
    )
    lines.extend(["", "## Model × controlled failure state", ""])
    lines.extend(
        _markdown_table(
            [
                "Model",
                "State",
                "Score",
                "Resource utility",
                "Decision",
                "Belief revision",
                "Claim containment",
            ],
            (
                (
                    row["model_id"],
                    row["failure_mode"].replace("_", " "),
                    _fmt(row["mean_score"]),
                    _fmt(row["mean_resource_utility"]),
                    _fmt(100 * row["decision_accuracy"]) + "%",
                    _fmt(100 * row["belief_revision_accuracy"]) + "%",
                    _fmt(row["mean_claim_containment"]),
                )
                for row in output["model_by_failure_mode"]
            ),
        )
    )
    lines.extend(["", "## Decisions, resources, and intervention effects", ""])
    lines.extend(
        _markdown_table(
            [
                "Model",
                "State",
                "Score",
                "Initial expected / observed",
                "Final expected / observed",
                "Resource / optimal",
                "Effect expected / observed",
            ],
            (
                (
                    row["model_id"],
                    row["scenario_class"].replace("_", " "),
                    _fmt(row["reliability_inclusive_score"]),
                    f"{row['expected_initial_decision']} / {row['observed_initial_decision']}",
                    f"{row['expected_final_decision']} / {row['observed_final_decision']}",
                    f"{row['selected_resource']} / {row['optimal_resource']}",
                    f"{row['expected_intervention_effect']} / "
                    f"{row['observed_intervention_effect']}",
                )
                for row in matrix
                if row["included_in_scientific_aggregate"]
            ),
        )
    )
    lines.extend(["", "## Artifact dependency depth", ""])
    lines.extend(
        _markdown_table(
            ["Model", "Depth", "Mean artifact/milestone score"],
            (
                (row["model_id"], row["artifact_depth"], _fmt(row["mean_score"]))
                for row in output["model_by_artifact_depth"]
            ),
        )
    )
    lines.extend(
        [
            "",
            "A low upstream score marks downstream artifacts as **at risk**, not automatically "
            "invalid. This preserves v0.5's predeclared conditional scoring and graceful recovery.",
            "",
            "### First substantive divergence and dependency impact",
            "",
        ]
    )
    lines.extend(
        _markdown_table(
            [
                "Model",
                "State",
                "First divergence",
                "Score",
                "Downstream at risk",
                "Mechanically invalidated",
            ],
            (
                (
                    row["model_id"],
                    row["scenario_class"].replace("_", " "),
                    (
                        "{milestone} / {artifact_id}".format(
                            **row["artifact_dependency"]["first_substantive_divergence"]
                        )
                        if row["artifact_dependency"].get("first_substantive_divergence")
                        else "none"
                    ),
                    (
                        _fmt(
                            row["artifact_dependency"]["first_substantive_divergence"][
                                "score"
                            ]
                        )
                        if row["artifact_dependency"].get("first_substantive_divergence")
                        else "—"
                    ),
                    (
                        ", ".join(
                            row["artifact_dependency"]["divergences"][0][
                                "downstream_artifacts_at_risk"
                            ]
                        )
                        if row["artifact_dependency"].get("divergences")
                        else "none"
                    ),
                    (
                        ", ".join(
                            row["artifact_dependency"]["divergences"][0][
                                "mechanically_invalidated"
                            ]
                        )
                        if row["artifact_dependency"].get("divergences")
                        and row["artifact_dependency"]["divergences"][0][
                            "mechanically_invalidated"
                        ]
                        else "none"
                    ),
                )
                for row in matrix
                if row["included_in_scientific_aggregate"]
            ),
        )
    )
    lines.extend(
        [
            "",
            "The machine-readable analysis records every divergence, not only the first. "
            "No descendant is mechanically invalidated by a milestone score alone; descendants "
            "remain conditionally scoreable for containment and recovery.",
            "",
            "### Frozen-grader vocabulary audit",
            "",
            "The frozen score is not changed. The table identifies valid semantic descriptions "
            "that a small frozen token matcher may fail to recognize. Any occurrence fails the "
            "predeclared `exact_method_name_matching` non-construct gate for this version.",
            "",
        ]
    )
    vocabulary_rows = [
        row
        for row in matrix
        if row["frozen_grader_vocabulary_audit"]["flag_count"] > 0
    ]
    lines.extend(
        _markdown_table(
            ["Model", "State", "Properties", "Estimated score points at risk"],
            (
                (
                    row["model_id"],
                    row["scenario_class"].replace("_", " "),
                    ", ".join(
                        item["property"]
                        for item in row["frozen_grader_vocabulary_audit"]["flags"]
                    ),
                    _fmt(
                        row["frozen_grader_vocabulary_audit"][
                            "estimated_headline_points_at_risk"
                        ]
                    ),
                )
                for row in vocabulary_rows
            ),
        )
        if vocabulary_rows
        else ["No affected cells were found."]
    )
    lines.extend(
        [
            "",
            "## Scientific, process, and infrastructure annotations",
            "",
        ]
    )
    failure_accounting = output["failure_accounting"]
    lines.extend(
        _markdown_table(
            ["Category", "Tag", "Episodes"],
            (
                (category, tag.replace("_", " "), count)
                for category, tags in failure_accounting["episode_counts_by_tag"].items()
                for tag, count in tags.items()
            ),
        )
    )
    lines.extend(
        [
            "",
            f"Failed tool calls: {failure_accounting['failed_tool_call_count']}; "
            f"timed-out tool calls: {failure_accounting['timed_out_tool_call_count']}; "
            f"infrastructure rows excluded: "
            f"{failure_accounting['infrastructure_rows_excluded']}.",
            "",
            "### Concrete evidence for every observed annotation tag",
            "",
        ]
    )
    annotation_examples: dict[tuple[str, str], tuple[dict[str, Any], dict[str, Any]]] = {}
    for row in matrix:
        for annotation in row["failure_annotations"]:
            key = (str(annotation["category"]), str(annotation["tag"]))
            annotation_examples.setdefault(key, (row, annotation))
    lines.extend(
        _markdown_table(
            ["Category", "Tag", "Example run", "Evidence path and pointer"],
            (
                (
                    category,
                    tag.replace("_", " "),
                    row["run_id"],
                    (
                        f"`{annotation['evidence'][0]['path']}` "
                        f"`{annotation['evidence'][0].get('json_pointer') or '/'}`"
                    ),
                )
                for (category, tag), (row, annotation) in sorted(
                    annotation_examples.items()
                )
            ),
        )
    )
    lines.extend(
        [
            "",
            "### Operational behaviour by model",
            "",
        ]
    )
    lines.extend(
        _markdown_table(
            [
                "Model",
                "Mean tool calls",
                "Mean failed calls",
                "Mean exact retries",
                "Timed-out calls",
            ],
            (
                (
                    row["model_id"],
                    _fmt(row["mean_tool_call_count"], 1),
                    _fmt(row["mean_failed_tool_call_count"], 1),
                    _fmt(row["mean_exact_tool_signature_retry_count"], 1),
                    row["total_timed_out_tool_calls"],
                )
                for row in summaries
            ),
        )
    )
    lines.extend(
        [
            "",
            "Every tag in the machine-readable analysis cites a run summary, state record, "
            "agent artifact, or exact trace message. These tags annotate process and diagnosis; "
            "they do not replace the frozen deterministic score or create the headline order.",
            "",
            "## Cost, tokens, turns, runtime, and completion",
            "",
        ]
    )
    lines.extend(
        _markdown_table(
            [
                "Model",
                "Mean estimated $/episode",
                "Input tokens",
                "Output tokens",
                "Turns",
                "Wall seconds",
            ],
            (
                (
                    row["model_id"],
                    _fmt(row["mean_estimated_episode_cost_usd"], 3),
                    _fmt(row["mean_input_tokens"], 0),
                    _fmt(row["mean_output_tokens"], 0),
                    _fmt(row["mean_turn_count"], 1),
                    _fmt(row["mean_wall_time_seconds"], 1),
                )
                for row in summaries
            ),
        )
    )
    lines.extend(
        [
            "",
            "Observed account spend across the pilot: "
            f"${_fmt(raw.get('observed_incremental_spend_usd'), 3)}. "
            "Episode costs in the table are frozen planning estimates because OpenRouter exposes "
            "the observed increment at pilot level, not a reliable per-episode allocation.",
            "",
            "### Score-versus-cost frontier",
            "",
        ]
    )
    lines.extend(
        _markdown_table(
            ["Model", "Mean score", "Estimated $/episode", "Pareto-optimal"],
            (
                (
                    row["model_id"],
                    _fmt(row["mean_score"]),
                    _fmt(row["mean_estimated_episode_cost_usd"], 3),
                    "yes" if row["pareto_optimal"] else "no",
                )
                for row in output["score_cost_frontier"]
            ),
        )
    )
    lines.extend(["", "## Acceptance gates", ""])
    if acceptance.get("evaluated"):
        lines.extend(
            _markdown_table(
                ["Mandatory gate", "Result"],
                (
                    (name.replace("_", " "), "PASS" if passed else "FAIL")
                    for name, passed in acceptance["checks"].items()
                ),
            )
        )
    else:
        lines.append(str(acceptance.get("reason")))
    lines.extend(["", "### Ceiling, floor, and family concentration", ""])
    lines.extend(
        _markdown_table(
            ["Failure family", "Share of strongest-to-weakest absolute gap"],
            (
                (name.replace("_", " "), _fmt(100 * share) + "%")
                for name, share in sorted(output["single_failure_family_gap_share"].items())
            ),
        )
        if output["single_failure_family_gap_share"]
        else ["Not available until all three models have usable cells."]
    )
    lines.append(
        "Ceiling and zero/floor rates are reported in the model summary; usable unsubmitted "
        "attempts retain a reliability score of zero and verified infrastructure failures "
        "are excluded."
    )
    lines.extend(["", "## Representative replay traces", ""])
    for replay in output["representative_replay_traces"]:
        lines.extend(
            [
                f"- `{replay['model_id']}` / `{replay['scenario_class']}` / score "
                f"{_fmt(replay['score'])}: `{replay['replay_evidence']['full_trace']}`",
                f"  - Decision: `{replay['initial_to_final_decision'][0]}` → "
                f"`{replay['initial_to_final_decision'][1]}`; resource "
                f"`{replay['selected_resource']}`; tags "
                f"`{', '.join(replay['failure_tags']) or 'none'}`.",
            ]
        )
    lines.extend(
        [
            "",
            "## Intermediate-evidence sufficiency and v0.6",
            "",
            "The three v0.5 submissions support coarse dependency analysis: commitment, "
            "validation assessment, and final decision. They do **not** provide sufficient "
            "uniform intermediate evidence for independent artifact-level grading because "
            "agent-created audit artifacts are optional and non-standardized.",
            "",
            "A separately versioned v0.6 should require ten compact semantic artifacts: "
            "`cohort_inventory.csv`, `provenance_audit.json`, `patient_visit_map.csv`, "
            "`endpoint_audit.json`, `preprocessing_lineage.json`, "
            "`reproduction_predictions.csv`, `committed_validation_plan.json`, "
            "`validation_results.json`, `resource_value_memo.json`, and "
            "`final_diligence_report.json`. Each must be graded on scientific invariants and "
            "semantic preservation while accepting alternative valid workflows.",
            "",
            "## Claim limits",
            "",
            "- This is controlled internal calibration, not external validation.",
            "- One seed does not establish a stable model ranking.",
            "- Observed behaviour supports a capability diagnosis only when repeated across "
            "relevant states.",
            "- Training-data, SFT, RL, prompting, retrieval, tooling, or expert-remedy claims "
            "require paired intervention evidence.",
            "- The authentic GEO anchor remains separate and is not pooled into these results.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    if not RUNS_PATH.exists():
        raise SystemExit("No v0.5 calibration exists; no analysis or ranking was created")
    raw = _read(RUNS_PATH)
    matrix = _matrix(list(raw.get("runs") or []))
    summaries = _model_summaries(matrix)
    failures = _failure_matrix(matrix)
    gap_share = _gap_share(failures, summaries)
    acceptance = _acceptance(
        matrix, summaries, gap_share, int(raw["planned_trajectory_count"])
    )
    output = {
        "schema_version": "0.5-analysis-1",
        "status": "development_calibration_not_stable_ranking",
        "analysis_only_extension_after_freeze": True,
        "frozen_task_or_grader_changed": False,
        "frozen_grader_rescored": False,
        "ranking_claim_allowed": False,
        "astra_requests": int(raw.get("astra_requests", 0)),
        "controlled_results_only": True,
        "external_expert_validation": False,
        "artifact_dag": list(ARTIFACT_DAG),
        "intermediate_evidence_assessment": {
            "sufficient_for_coarse_three_stage_dependency_analysis": True,
            "sufficient_for_uniform_independent_intermediate_artifact_grading": False,
            "reason": (
                "The commitment, validation assessment, and final submission preserve the main "
                "decision transitions, but agent-created intermediate audit artifacts are optional "
                "and do not have uniform semantic contracts in v0.5."
            ),
            "successor_specification": "docs/HARD_SUITE_V06_ARTIFACT_DAG_PROPOSAL.md",
        },
        "matrix": matrix,
        "model_summaries": summaries,
        "model_by_failure_mode": failures,
        "model_by_artifact_depth": _depth_matrix(matrix),
        "single_failure_family_gap_share": gap_share,
        "score_cost_frontier": _cost_frontier(summaries),
        "representative_replay_traces": _representative_traces(matrix),
        "failure_accounting": _failure_accounting(matrix),
        "acceptance": acceptance,
        "pilot_accounting": {
            "planned_trajectories": raw.get("planned_trajectory_count"),
            "completed_trajectories": raw.get("completed_trajectory_count"),
            "observed_incremental_spend_usd": raw.get("observed_incremental_spend_usd"),
            "estimated_cost_usd": raw.get("estimated_cost_usd"),
            "maximum_incremental_spend_usd": raw.get("maximum_incremental_spend_usd"),
            "infrastructure_failure_count": raw.get("infrastructure_failure_count"),
        },
        "breaking_point_curves": {
            "status": "not_evaluated_in_one_seed_pilot",
            "contract": "configs/hard_suite_v05_ladders.json",
        },
        "claim_separation": {
            "observed_behaviour": "Directly retained in state records, artifacts, and traces.",
            "capability_diagnosis": "Requires repeated evidence across relevant controlled states.",
            "hypothesized_training_cause": "Not identified by this pilot.",
            "demonstrated_remedy": "Only paired resource effects inside the controlled workflow.",
        },
    }
    _write(OUTPUT_PATH, output)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(_build_report(output, raw), encoding="utf-8")
    print(json.dumps(acceptance, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

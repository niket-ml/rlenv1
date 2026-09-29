"""Leakage-safe packaging and deterministic grading for short diagnostic packets."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from uc_bench.errors import ConfigurationError, ContractError
from uc_bench.hashing import canonical_sha256, sha256_file

PACKET_COMPONENT_WEIGHTS = {
    "decision": 0.40,
    "diagnosis": 0.30,
    "next_action": 0.20,
    "required_evidence_recall": 0.10,
}
ACTION_ALIASES = {
    "expand_endpoint_matched_validation": "endpoint_matched_validation",
    "prospective_endpoint_matched_validation": "endpoint_matched_validation",
}


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ContractError(f"Cannot load JSON object {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractError(f"Expected JSON object: {path}")
    return value


def _set_f1(expected: set[str], submitted: set[str]) -> float:
    if not expected and not submitted:
        return 100.0
    correct = expected & submitted
    precision = len(correct) / len(submitted) if submitted else 0.0
    recall = len(correct) / len(expected) if expected else 0.0
    if precision + recall == 0:
        return 0.0
    return 100.0 * 2.0 * precision * recall / (precision + recall)


def _set_recall(required: set[str], submitted: set[str]) -> float:
    if not required:
        return 100.0
    return 100.0 * len(required & submitted) / len(required)


def policy_decision(packet: dict[str, Any], policy: dict[str, Any]) -> str:
    """Recompute the terminal decision from public numerical criteria."""

    context = packet["context"]
    validation = packet["validation"]
    if context.get("hard_integrity_failure") is True:
        return "stop"
    criteria = policy["advance_requires_all"]
    interval = validation["auc_interval"]
    advances = (
        float(validation["auc"]) >= float(criteria["auc_minimum"])
        and float(interval[0]) > float(criteria["auc_interval_lower_strictly_above"])
        and float(validation["permutation_p_value"]) <= float(criteria["permutation_p_maximum"])
        and int(validation["evaluated_n"]) >= int(criteria["evaluated_n_minimum"])
        and context.get("validation_usable_under_feature_contract", True)
        is criteria["validation_usable_under_feature_contract"]
        and criteria["no_hard_integrity_failure"] is True
    )
    return "advance" if advances else "insufficient_evidence"


def validate_diagnostic_packets(value: dict[str, Any]) -> dict[str, Any]:
    """Validate packet/rubric alignment without relying on prose answers."""

    policy = value.get("decision_policy")
    scoring = value.get("scoring_policy")
    scenarios = value.get("scenarios")
    if (
        not isinstance(policy, dict)
        or not isinstance(scoring, dict)
        or not isinstance(scenarios, list)
    ):
        raise ContractError("Diagnostic packet config requires policy, scoring, and scenarios")
    if scoring.get("weights") != PACKET_COMPONENT_WEIGHTS:
        raise ContractError("Public packet weights differ from deterministic grader")
    if scoring.get("confidence") != "reported_across_packets_not_scored_per_packet":
        raise ContractError("Packet confidence may not use hidden per-item scoring")
    if scoring.get("additional_valid_evidence_ids_are_penalized") is not False:
        raise ContractError("Additional valid packet evidence may not be penalized")
    keys: set[tuple[str, str]] = set()
    decisions: set[str] = set()
    task_counts: dict[str, int] = {}
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            raise ContractError("Diagnostic packet scenarios must be objects")
        key = (str(scenario.get("task_id")), str(scenario.get("scenario_id")))
        if key in keys:
            raise ContractError(f"Duplicate diagnostic packet scenario: {key}")
        keys.add(key)
        task_counts[key[0]] = task_counts.get(key[0], 0) + 1
        packet = scenario.get("packet")
        rubric = scenario.get("rubric")
        if not isinstance(packet, dict) or not isinstance(rubric, dict):
            raise ContractError(f"Packet and private rubric are required for {key}")
        recomputed = policy_decision(packet, policy)
        if rubric.get("expected_decision") != recomputed:
            raise ContractError(f"Private expected decision disagrees with public policy for {key}")
        decisions.add(recomputed)
        available = set(str(item) for item in packet.get("evidence_ids", []))
        required = set(str(item) for item in rubric.get("required_evidence_ids", []))
        if not required or not required <= available:
            raise ContractError(f"Rubric cites unavailable evidence for {key}")
        confidence = rubric.get("confidence_range")
        if (
            not isinstance(confidence, list)
            or len(confidence) != 2
            or not 0.0 <= float(confidence[0]) <= float(confidence[1]) <= 1.0
        ):
            raise ContractError(f"Invalid confidence range for {key}")
    if task_counts != {"T08": 4, "T09": 4, "T10": 4}:
        raise ContractError("T08-T10 must each have four diagnostic packets")
    if decisions != {"advance", "stop", "insufficient_evidence"}:
        raise ContractError("Diagnostic packets must cover all terminal decisions")
    return {
        "scenario_count": len(scenarios),
        "task_counts": task_counts,
        "decision_classes": sorted(decisions),
        "policy_alignment_passed": True,
    }


@dataclass(frozen=True, slots=True)
class DiagnosticPacketPackage:
    task_id: str
    scenario_id: str
    workspace_root: Path
    package_digest: str


@dataclass(frozen=True, slots=True)
class DiagnosticPacketGrade:
    score: float
    contract_valid: bool
    decision_correct: bool
    component_scores: dict[str, float]
    checks: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "contract_valid": self.contract_valid,
            "decision_correct": self.decision_correct,
            "component_scores": self.component_scores,
            "checks": self.checks,
        }


def load_packet_scenario(project_root: Path, task_id: str, scenario_id: str) -> dict[str, Any]:
    config = _read_object(project_root / "configs" / "diagnostic_packets.json")
    validate_diagnostic_packets(config)
    matches = [
        row
        for row in config.get("scenarios", [])
        if row.get("task_id") == task_id and row.get("scenario_id") == scenario_id
    ]
    if len(matches) != 1:
        raise ConfigurationError(
            f"Expected one diagnostic packet for {task_id}/{scenario_id}; found {len(matches)}"
        )
    return matches[0]


class DiagnosticPacketBuilder:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()

    def build(
        self,
        task_id: str,
        scenario_id: str,
        *,
        output_root: Path,
        replace: bool = False,
        expert_playbook: bool = False,
    ) -> DiagnosticPacketPackage:
        scenario = load_packet_scenario(self.project_root, task_id, scenario_id)
        destination = output_root / f"{task_id}-{scenario_id}"
        if destination.exists():
            if not replace:
                raise ConfigurationError(f"Packet workspace already exists: {destination}")
            shutil.rmtree(destination)
        destination.mkdir(parents=True)
        task_root = self.project_root / "tasks" / "diagnostic_decision_v0"
        for source in sorted(path for path in task_root.rglob("*") if path.is_file()):
            target = destination / source.relative_to(task_root)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        if expert_playbook:
            shutil.copyfile(
                self.project_root / "tasks" / "EXPERT_PLAYBOOK.md",
                destination / "EXPERT_PLAYBOOK.md",
            )
        packet = {
            "schema_version": "0.1",
            "task_id": task_id,
            "scenario_id": scenario_id,
            "decision_policy": _read_object(
                self.project_root / "configs" / "diagnostic_packets.json"
            )["decision_policy"],
            "scoring_policy": _read_object(
                self.project_root / "configs" / "diagnostic_packets.json"
            )["scoring_policy"],
            **scenario["packet"],
        }
        (destination / "packet.json").write_text(
            json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (destination / "submission").mkdir()
        rows = [
            {
                "path": path.relative_to(destination).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in sorted(
                candidate for candidate in destination.rglob("*") if candidate.is_file()
            )
        ]
        digest = canonical_sha256(rows)
        (destination / "START_STATE.json").write_text(
            json.dumps(
                {
                    "schema_version": "0.1",
                    "task_id": task_id,
                    "scenario_id": scenario_id,
                    "package_digest": digest,
                    "private_rubric_visible": False,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return DiagnosticPacketPackage(task_id, scenario_id, destination, digest)


class DiagnosticPacketEnvironment:
    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root.resolve()
        self.submission: dict[str, Any] | None = None

    def submit_packet(self, submission_path: str) -> str:
        if self.submission is not None:
            raise ContractError("submit_packet may be called only once")
        relative = Path(submission_path)
        if relative.is_absolute():
            raise ContractError("submission_path must be relative")
        path = (self.workspace_root / relative).resolve()
        if self.workspace_root not in path.parents or not path.is_file():
            raise ContractError("Submission is missing or outside the workspace")
        value = _read_object(path)
        schema = _read_object(self.workspace_root / "schemas" / "final_submission.schema.json")
        from jsonschema import Draft202012Validator
        from jsonschema.exceptions import ValidationError

        try:
            Draft202012Validator(schema).validate(value)
        except ValidationError as exc:
            location = ".".join(str(part) for part in exc.absolute_path)
            suffix = f" at {location}" if location else ""
            raise ContractError(
                f"Submission violates public schema{suffix}: {exc.message}"
            ) from exc
        packet = _read_object(self.workspace_root / "packet.json")
        allowed_evidence = set(str(item) for item in packet.get("evidence_ids", []))
        invented = sorted(set(value["evidence_ids"]) - allowed_evidence)
        if invented:
            raise ContractError(f"Submission cites unknown evidence IDs: {invented}")
        self.submission = value
        return json.dumps({"submitted": True}, sort_keys=True)


def grade_diagnostic_packet(
    submission: dict[str, Any] | None,
    rubric: dict[str, Any],
) -> DiagnosticPacketGrade:
    if submission is None:
        return DiagnosticPacketGrade(
            score=0.0,
            contract_valid=False,
            decision_correct=False,
            component_scores={
                "decision": 0.0,
                "diagnosis": 0.0,
                "next_action": 0.0,
                "required_evidence_recall": 0.0,
            },
            checks={"submitted": False},
        )
    expected_codes = set(str(item) for item in rubric["expected_diagnostic_codes"])
    submitted_codes = set(str(item) for item in submission["diagnostic_codes"])
    required_evidence = set(str(item) for item in rubric["required_evidence_ids"])
    submitted_evidence = set(str(item) for item in submission["evidence_ids"])
    decision_correct = submission["decision"] == rubric["expected_decision"]
    diagnosis = _set_f1(expected_codes, submitted_codes)
    citation = _set_recall(required_evidence, submitted_evidence)
    submitted_action = ACTION_ALIASES.get(
        submission["next_action_type"], submission["next_action_type"]
    )
    expected_action = ACTION_ALIASES.get(
        rubric["expected_next_action_type"], rubric["expected_next_action_type"]
    )
    legacy_actions = set(str(item) for item in rubric.get("accepted_legacy_next_action_types", []))
    action_correct = (
        submitted_action == expected_action or submission["next_action_type"] in legacy_actions
    )
    confidence = float(submission["confidence"])
    lower, upper = (float(item) for item in rubric["confidence_range"])
    confidence_correct = decision_correct and lower <= confidence <= upper
    components = {
        "decision": 100.0 * decision_correct,
        "diagnosis": diagnosis,
        "next_action": 100.0 * action_correct,
        "required_evidence_recall": citation,
    }
    score = (
        PACKET_COMPONENT_WEIGHTS["decision"] * components["decision"]
        + PACKET_COMPONENT_WEIGHTS["diagnosis"] * components["diagnosis"]
        + PACKET_COMPONENT_WEIGHTS["next_action"] * components["next_action"]
        + PACKET_COMPONENT_WEIGHTS["required_evidence_recall"]
        * components["required_evidence_recall"]
    )
    if not decision_correct:
        score = min(score, 59.0)
    return DiagnosticPacketGrade(
        score=score,
        contract_valid=True,
        decision_correct=decision_correct,
        component_scores=components,
        checks={
            "submitted": True,
            "diagnostic_codes_exact": submitted_codes == expected_codes,
            "next_action_correct": action_correct,
            "required_evidence_recalled": required_evidence <= submitted_evidence,
            "confidence_in_range": confidence_correct,
        },
    )

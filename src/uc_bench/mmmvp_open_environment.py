"""Condition-blind, flexible-order environment over the existing five conditions."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from uc_bench.docker_runtime import DockerWorkspace
from uc_bench.errors import ConfigurationError
from uc_bench.mmmvp_open_interventions import RC_PRIVATE_ROOT, execute_x31_resource
from uc_bench.mmmvp_open_schema import (
    AGENT_VISIBLE_CONTRACT,
    validate_final_submission,
    validate_followup_plan,
    validate_validation_plan,
)
from uc_bench.v07_cases import PRIVATE_ROOT, PUBLIC_ROOT, load_truth

_README = """# Predictor evidence package

The files in this directory are the supplied evidence for the stated intended use.
Sponsor statements are unverified assertions. Preserve derived evidence under work/.
"""

_SPONSOR = """# Sponsor statements

The sponsor states that the locked predictor and archived evidence may support the
intended use described in intended_use.json. This statement has not been adjudicated.
"""

_VALIDATION_MANIFEST = {
    "commitment_required_before_reveal": True,
    "outcomes_sealed": True,
    "predictions_locked": True,
}

_DEVELOPMENT_ACTION_CONTRACT = {
    "schema_version": "mmmvp-development-actions-1",
    "commitment_timing": (
        "Decision criteria and thresholds must be committed before validation outcomes are "
        "revealed and must be applied without post-hoc movement."
    ),
    "actions": {
        "CONTINUE": (
            "Proceed only to a bounded next development stage when all precommitted material "
            "criteria for that step are satisfied."
        ),
        "PAUSE": (
            "Do not progress while at least one precommitted material criterion or concrete "
            "decision gate remains unresolved; identify the evidence needed to resolve it."
        ),
        "STOP": (
            "End the investigated development path when valid evidence shows that the intended "
            "path is not supportable."
        ),
        "INSUFFICIENT_EVIDENCE": (
            "Make no directional progression claim when the available evidence cannot resolve "
            "the precommitted decision criteria."
        ),
    },
    "scope_rule": (
        "Allowed use and claims must remain no broader than the evidence actually calculated; "
        "research continuation is not clinical deployment."
    ),
}

_NEUTRAL_RESOURCE_CATALOG = {
    "maximum_purchases": 1,
    "resources": [
        {
            "resource_id": "X17",
            "title": "Source-record reconciliation package",
            "cost_units": 1,
            "delay_days": 4,
            "returns": ["source-key crosswalk", "visit chronology", "unresolved-record list"],
            "scope_limitations": ["existing records only", "no new outcome observations"],
        },
        {
            "resource_id": "X24",
            "title": "Endpoint evidence package",
            "cost_units": 2,
            "delay_days": 9,
            "returns": ["dual-reviewer labels", "source excerpts", "adjudication log"],
            "scope_limitations": ["existing source records only", "no new cohort"],
        },
        {
            "resource_id": "X31",
            "title": "Pipeline execution package",
            "cost_units": 1,
            "delay_days": 5,
            "returns": ["replay predictions", "fit-input hashes", "execution lineage"],
            "scope_limitations": ["supplied pipeline only", "no new cohort or label review"],
        },
        {
            "resource_id": "X46",
            "title": "Matched external evidence package",
            "cost_units": 3,
            "delay_days": 21,
            "returns": ["matched predictions and outcomes", "context fields", "action table"],
            "scope_limitations": ["new package only", "original records are unchanged"],
        },
        {
            "resource_id": "X58",
            "title": "Larger sample package",
            "cost_units": 3,
            "delay_days": 45,
            "returns": ["additional records", "updated sampling information"],
            "scope_limitations": ["same collection process", "no independent record review"],
        },
        {
            "resource_id": "X63",
            "title": "Expert review package",
            "cost_units": 1,
            "delay_days": 3,
            "returns": ["review memo based on available files", "analysis recommendations"],
            "scope_limitations": ["advisory output only", "no new empirical observations"],
        },
        {
            "resource_id": "none",
            "title": "Purchase nothing",
            "cost_units": 0,
            "delay_days": 0,
            "returns": ["no new evidence"],
            "scope_limitations": ["available evidence remains unchanged"],
        },
    ],
}

OPEN_TOOL_SPECS: tuple[dict[str, Any], ...] = (
    {
        "name": "inspect_workspace",
        "description": "List files visible inside the workspace.",
        "parameters": {
            "type": "object",
            "properties": {"relative_path": {"type": "string", "default": "."}},
        },
    },
    {
        "name": "read_file",
        "description": "Read one visible UTF-8 workspace file.",
        "parameters": {
            "type": "object",
            "properties": {"relative_path": {"type": "string"}},
            "required": ["relative_path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write a UTF-8 analysis artifact inside the visible workspace.",
        "parameters": {
            "type": "object",
            "properties": {
                "relative_path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["relative_path", "content"],
        },
    },
    {
        "name": "run_command",
        "description": "Run an analysis command inside the sealed workspace container.",
        "parameters": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    },
    {
        "name": "commit_validation_plan",
        "description": "Irreversibly commit an agent-chosen plan before outcomes are available.",
        "parameters": {
            "type": "object",
            "properties": {"payload_json": {"type": "string"}},
            "required": ["payload_json"],
        },
    },
    {
        "name": "reveal_validation",
        "description": "Reveal sealed outcomes after the validation plan has been committed.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "commit_followup_plan",
        "description": "Commit a resource choice and result-contingent actions before purchase.",
        "parameters": {
            "type": "object",
            "properties": {"payload_json": {"type": "string"}},
            "required": ["payload_json"],
        },
    },
    {
        "name": "purchase_resource",
        "description": "Irreversibly purchase one catalogue resource, including none.",
        "parameters": {
            "type": "object",
            "properties": {"resource_id": {"type": "string"}},
            "required": ["resource_id"],
        },
    },
    {
        "name": "submit",
        "description": "Submit the evidence-linked final recommendation after the resource action.",
        "parameters": {
            "type": "object",
            "properties": {"payload_json": {"type": "string"}},
            "required": ["payload_json"],
        },
    },
)


def _neutral_intended_use(source: Path) -> dict[str, Any]:
    value = json.loads(source.read_text(encoding="utf-8"))
    return {
        "population": value["population"],
        "input_time": value["input_time"],
        "endpoint": value["endpoint"],
        "predictor_output": value["claim"],
        "action_threshold": value["threshold"],
        "development_decision": "whether evidence supports the next bounded development stage",
    }


class OpenProtocolError(RuntimeError):
    """A disclosed irreversible action or workspace boundary was violated."""


@dataclass(slots=True)
class OpenEpisodeState:
    phase: str = "investigate"
    validation_plan_hash: str | None = None
    followup_plan_hash: str | None = None
    final_submission_hash: str | None = None
    selected_resource: str | None = None
    spent_units: int = 0
    completion_accepted: bool = False
    terminal_reason: str | None = None
    tool_calls: int = 0
    event_log: list[dict[str, Any]] = field(default_factory=list)


def _digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _json_digest(value: dict[str, Any]) -> str:
    return _digest_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def _decode(payload_json: str) -> dict[str, Any]:
    try:
        value = json.loads(payload_json)
    except (TypeError, json.JSONDecodeError) as exc:
        raise OpenProtocolError("payload_json must contain a JSON object") from exc
    if not isinstance(value, dict):
        raise OpenProtocolError("payload_json must contain a JSON object")
    return value


class OpenMMMVPEnvironment:
    """Expose evidence and irreversible actions without prescribing an analysis."""

    def __init__(
        self,
        project_root: Path,
        case_id: str,
        run_root: Path,
        *,
        mechanism: str = "default",
        maximum_tool_calls: int = 80,
    ) -> None:
        self.project_root = project_root.resolve()
        self.case_id = case_id
        self.mechanism = mechanism
        self.run_root = run_root.resolve()
        self.records_root = (
            self.run_root.parent / ".mmmvp_host_records" / self.run_root.name
        ).resolve()
        self.maximum_tool_calls = maximum_tool_calls
        truth = load_truth(self.project_root, case_id)
        if mechanism not in set(truth["mechanisms"]):
            raise ConfigurationError("Private mechanism is not configured for this evidence set")
        if self.run_root.exists():
            raise FileExistsError(f"Episode directory already exists: {self.run_root}")
        if self.records_root.exists():
            raise FileExistsError(f"Host record directory already exists: {self.records_root}")
        shutil.copytree(self.project_root / PUBLIC_ROOT / case_id, self.run_root)
        self._neutralise_public_descriptions()
        (self.run_root / "work").mkdir()
        self.records_root.mkdir(parents=True)
        self.state = OpenEpisodeState()
        self._protected_evidence_hashes = self._workspace_hashes()
        self._start_hashes = dict(self._protected_evidence_hashes)
        self._validation_input_hashes: dict[str, str] = {}
        self._record("reset", visible_file_count=len(self._start_hashes))

    def _neutralise_public_descriptions(self) -> None:
        intended_use_path = self.run_root / "intended_use.json"
        intended_use = _neutral_intended_use(intended_use_path)
        intended_use_path.write_text(
            json.dumps(intended_use, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (self.run_root / "README.md").write_text(_README, encoding="utf-8")
        sponsor = self.run_root / "sponsor/assertions.md"
        sponsor.write_text(_SPONSOR, encoding="utf-8")
        (self.run_root / "validation_manifest.json").write_text(
            json.dumps(_VALIDATION_MANIFEST, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        catalogue = {**_NEUTRAL_RESOURCE_CATALOG, "budget_units": 3}
        (self.run_root / "followup_catalog.json").write_text(
            json.dumps(catalogue, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (self.run_root / "submission_contract.json").write_text(
            json.dumps(AGENT_VISIBLE_CONTRACT, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (self.run_root / "development_action_contract.json").write_text(
            json.dumps(_DEVELOPMENT_ACTION_CONTRACT, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _record(self, event: str, **details: Any) -> None:
        self.state.event_log.append(
            {
                "sequence": len(self.state.event_log) + 1,
                "time": datetime.now(UTC).isoformat(),
                "event": event,
                **details,
            }
        )

    def _count_tool(self) -> None:
        if self.state.phase == "terminal":
            raise OpenProtocolError("Episode is terminal")
        self.state.tool_calls += 1
        if self.state.tool_calls > self.maximum_tool_calls:
            self.state.phase = "terminal"
            self.state.terminal_reason = "tool_budget_exhausted"
            raise OpenProtocolError("Tool-call budget exhausted")

    def _workspace_hashes(self) -> dict[str, str]:
        # Only agent-created work is mutable. Public source evidence, revealed
        # outcomes and purchased returns are all protected once they exist.
        excluded = {"work"}
        return {
            path.relative_to(self.run_root).as_posix(): _digest_bytes(path.read_bytes())
            for path in sorted(self.run_root.rglob("*"))
            if path.is_file()
            and not any(part in excluded for part in path.relative_to(self.run_root).parts)
        }

    def _assert_untampered(self) -> None:
        if self._workspace_hashes() != self._protected_evidence_hashes:
            self.state.phase = "terminal"
            self.state.terminal_reason = "start_state_tampering"
            self._record("integrity_rejection", reason="start_state_tampering")
            raise OpenProtocolError("Supplied evidence was modified")

    def _safe_visible_path(self, relative_path: str) -> Path:
        posix = PurePosixPath(relative_path)
        if posix.is_absolute() or ".." in posix.parts:
            raise OpenProtocolError("Path must remain inside the visible workspace")
        if any(part.startswith("grader_private") for part in posix.parts):
            raise OpenProtocolError("Path is not agent-visible")
        resolved = (self.run_root / Path(*posix.parts)).resolve()
        if resolved != self.run_root and self.run_root not in resolved.parents:
            raise OpenProtocolError("Path escapes the visible workspace")
        return resolved

    def record_workspace_tool(
        self,
        tool_name: str,
        *,
        success: bool,
        relative_path: str | None = None,
        command: str | None = None,
        error_type: str | None = None,
    ) -> None:
        details: dict[str, Any] = {"tool_name": tool_name, "success": success}
        if relative_path is not None:
            details["relative_path"] = relative_path
        if command is not None:
            details["command_sha256"] = _digest_bytes(command.encode())
        if error_type is not None:
            details["error_type"] = error_type
        self._record(f"tool_{tool_name}", **details)

    def commit_validation_plan(self, payload_json: str) -> dict[str, Any]:
        """Irreversibly commit an agent-chosen plan before outcomes are available."""

        self._count_tool()
        self._assert_untampered()
        if self.state.phase != "investigate":
            raise OpenProtocolError("Validation plan can be committed exactly once before reveal")
        payload = _decode(payload_json)
        result = validate_validation_plan(payload)
        if not result.valid:
            self._record(
                "validation_plan_rejected", schema_issues=[row.to_dict() for row in result.issues]
            )
            return {"accepted": False, "schema_issues": [row.to_dict() for row in result.issues]}
        committed_paths = {
            str(path)
            for analysis in payload["planned_analyses"]
            for path in analysis["input_paths"]
        } | {str(path) for path in payload["evidence_refs"]}
        invalid_paths: list[str] = []
        input_hashes: dict[str, str] = {}
        for relative_path in sorted(committed_paths):
            if relative_path.startswith(("revealed/", "purchased/")):
                invalid_paths.append(relative_path)
                continue
            try:
                path = self._safe_visible_path(relative_path)
            except OpenProtocolError:
                invalid_paths.append(relative_path)
                continue
            if not path.is_file():
                invalid_paths.append(relative_path)
                continue
            input_hashes[relative_path] = _digest_bytes(path.read_bytes())
        if invalid_paths:
            issues = [
                {
                    "path": "planned_analyses.input_paths",
                    "code": "pre_reveal_file_required",
                    "message": (
                        "Every committed input and evidence path must name an existing "
                        "agent-visible file before reveal"
                    ),
                    "invalid_paths": invalid_paths,
                }
            ]
            self._record("validation_plan_rejected", schema_issues=issues)
            return {"accepted": False, "schema_issues": issues}
        path = self.records_root / "validation_plan.json"
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (self.records_root / "validation_input_hashes.json").write_text(
            json.dumps(input_hashes, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        self._validation_input_hashes = input_hashes
        self.state.validation_plan_hash = _json_digest(payload)
        self.state.phase = "committed"
        self._record("commit_validation_plan", digest=self.state.validation_plan_hash)
        return {"accepted": True, "committed_plan_hash": self.state.validation_plan_hash}

    def reveal_validation(self) -> list[str]:
        """Reveal sealed outcomes after the validation plan has been committed."""

        self._count_tool()
        self._assert_untampered()
        if self.state.phase != "committed":
            raise OpenProtocolError("Outcome reveal requires the committed validation plan")
        source = self.project_root / PRIVATE_ROOT / self.case_id / "sealed"
        target = self.run_root / "revealed"
        shutil.copytree(source, target)
        self._protected_evidence_hashes = self._workspace_hashes()
        self.state.phase = "revealed"
        files = sorted(
            path.relative_to(self.run_root).as_posix()
            for path in target.rglob("*")
            if path.is_file()
        )
        self._record(
            "reveal_validation", committed_plan_hash=self.state.validation_plan_hash, files=files
        )
        return files

    def commit_followup_plan(self, payload_json: str) -> dict[str, Any]:
        """Commit a resource choice and result-contingent actions before purchase."""

        self._count_tool()
        self._assert_untampered()
        if self.state.phase != "revealed":
            raise OpenProtocolError(
                "Follow-up plan must be committed after reveal and before purchase"
            )
        payload = _decode(payload_json)
        result = validate_followup_plan(payload)
        if not result.valid:
            self._record(
                "followup_plan_rejected", schema_issues=[row.to_dict() for row in result.issues]
            )
            return {"accepted": False, "schema_issues": [row.to_dict() for row in result.issues]}
        validation = json.loads(
            (self.records_root / "validation_plan.json").read_text(encoding="utf-8")
        )
        expected_beliefs = {row["hypothesis_id"]: row["belief"] for row in validation["hypotheses"]}
        if payload["beliefs_before"] != expected_beliefs:
            issues = [
                {
                    "path": "beliefs_before",
                    "code": "commitment_mismatch",
                    "message": "Must preserve validation-plan hypothesis IDs and values",
                }
            ]
            self._record("followup_plan_rejected", schema_issues=issues)
            return {"accepted": False, "schema_issues": issues}
        path = self.records_root / "followup_plan.json"
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        self.state.followup_plan_hash = _json_digest(payload)
        self.state.phase = "followup_committed"
        self._record("commit_followup_plan", digest=self.state.followup_plan_hash)
        return {"accepted": True, "committed_followup_hash": self.state.followup_plan_hash}

    def purchase_resource(self, resource_id: str) -> list[str]:
        """Irreversibly purchase one catalogue resource, including none."""

        self._count_tool()
        self._assert_untampered()
        if self.state.phase != "followup_committed":
            raise OpenProtocolError("Purchase requires a committed follow-up plan")
        plan = json.loads((self.records_root / "followup_plan.json").read_text(encoding="utf-8"))
        if resource_id != plan["chosen_resource"]:
            raise OpenProtocolError("Purchase must match the committed resource ID")
        by_id = {row["resource_id"]: row for row in _NEUTRAL_RESOURCE_CATALOG["resources"]}
        if resource_id not in by_id:
            raise OpenProtocolError("Unknown resource ID")
        cost = int(by_id[resource_id]["cost_units"])
        budget = int(
            json.loads((self.run_root / "followup_catalog.json").read_text())["budget_units"]
        )
        if cost > budget:
            raise OpenProtocolError("Selected resource exceeds the disclosed budget")
        target = self.run_root / "purchased" / resource_id
        target.mkdir(parents=True)
        if resource_id == "none":
            (target / "no_new_evidence.json").write_text(
                '{"new_evidence":false}\n', encoding="utf-8"
            )
        elif self.case_id == "case_03" and resource_id == "X31":
            execute_x31_resource(self.project_root, self.mechanism, target)
        elif self.case_id == "case_02" and resource_id == "X17":
            source = self.project_root / RC_PRIVATE_ROOT / "case_02/X17"
            if not source.is_dir():
                raise ConfigurationError("The private X17 adjudication package is missing")
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            source = (
                self.project_root / PRIVATE_ROOT / self.case_id / "resource_returns" / resource_id
            )
            shutil.copytree(source, target, dirs_exist_ok=True)
        self._protected_evidence_hashes = self._workspace_hashes()
        self.state.selected_resource = resource_id
        self.state.spent_units = cost
        self.state.phase = "purchased"
        files = sorted(
            path.relative_to(self.run_root).as_posix()
            for path in target.rglob("*")
            if path.is_file()
        )
        self._record("purchase_resource", resource_id=resource_id, cost_units=cost, files=files)
        return files

    def submit(self, payload_json: str) -> dict[str, Any]:
        """Submit the evidence-linked final recommendation after the resource action."""

        self._count_tool()
        self._assert_untampered()
        if self.state.phase != "purchased":
            raise OpenProtocolError("Final submission requires a completed resource action")
        payload = _decode(payload_json)
        result = validate_final_submission(payload)
        if not result.valid:
            self._record("submit_rejected", schema_issues=[row.to_dict() for row in result.issues])
            return {"accepted": False, "schema_issues": [row.to_dict() for row in result.issues]}
        path = self.records_root / "final_submission.json"
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        self.state.final_submission_hash = _json_digest(payload)
        self.state.completion_accepted = True
        self.state.phase = "terminal"
        self.state.terminal_reason = "submitted"
        self._record(
            "submit",
            validation_plan_hash=self.state.validation_plan_hash,
            followup_plan_hash=self.state.followup_plan_hash,
            final_submission_hash=self.state.final_submission_hash,
        )
        return {"accepted": True, "terminal": True}

    def export_submission(self) -> dict[str, Any]:
        records = self.records_root

        def load(name: str) -> dict[str, Any] | None:
            path = records / name
            return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None

        return {
            "interface_version": "mmmvp-open-rc1-2",
            "host_record_locator": self.records_root.as_posix(),
            "case_id": self.case_id,
            "mechanism": self.mechanism,
            "protected_evidence_hashes": dict(self._protected_evidence_hashes),
            "validation_plan": load("validation_plan.json"),
            "validation_input_hashes": dict(self._validation_input_hashes),
            "followup_plan": load("followup_plan.json"),
            "final_submission": load("final_submission.json"),
            "event_log": list(self.state.event_log),
            "state": asdict(self.state),
        }

    def state_dict(self) -> dict[str, Any]:
        """Expose a JSON-safe host snapshot for durable trajectory persistence."""

        return {
            "case_id": self.case_id,
            "mechanism": self.mechanism,
            **asdict(self.state),
        }

    def integrity_status(self) -> dict[str, Any]:
        return {
            "start_state_untampered": all(
                self._workspace_hashes().get(path) == digest
                for path, digest in self._start_hashes.items()
            ),
            "protected_evidence_untampered": (
                self._workspace_hashes() == self._protected_evidence_hashes
            ),
            "completion_accepted": self.state.completion_accepted,
            "terminal_reason": self.state.terminal_reason,
        }


def mmmvp_open_tool_functions(
    docker: DockerWorkspace,
    core: OpenMMMVPEnvironment,
) -> list[Any]:
    """Expose shared neutral tools with host-side action recording."""

    def inspect_workspace(relative_path: str = ".") -> str:
        """List files visible inside the workspace."""
        try:
            result = docker.inspect_workspace(relative_path)
        except Exception as exc:
            core.record_workspace_tool(
                "inspect_workspace",
                success=False,
                relative_path=relative_path,
                error_type=type(exc).__name__,
            )
            raise
        core.record_workspace_tool("inspect_workspace", success=True, relative_path=relative_path)
        return result

    def read_file(relative_path: str) -> str:
        """Read one visible UTF-8 workspace file."""
        try:
            result = docker.read_file(relative_path)
        except Exception as exc:
            core.record_workspace_tool(
                "read_file",
                success=False,
                relative_path=relative_path,
                error_type=type(exc).__name__,
            )
            raise
        core.record_workspace_tool("read_file", success=True, relative_path=relative_path)
        return result

    def write_file(relative_path: str, content: str) -> str:
        """Write a UTF-8 analysis artifact inside the visible workspace."""
        try:
            result = docker.write_file(relative_path, content)
        except Exception as exc:
            core.record_workspace_tool(
                "write_file",
                success=False,
                relative_path=relative_path,
                error_type=type(exc).__name__,
            )
            raise
        core.record_workspace_tool("write_file", success=True, relative_path=relative_path)
        return result

    def run_command(command: str) -> str:
        """Run an analysis command inside the sealed workspace container."""
        try:
            result = docker.run_command(command)
        except Exception as exc:
            core.record_workspace_tool(
                "run_command", success=False, command=command, error_type=type(exc).__name__
            )
            raise
        core.record_workspace_tool("run_command", success=True, command=command)
        return result

    return [
        inspect_workspace,
        read_file,
        write_file,
        run_command,
        core.commit_validation_plan,
        core.reveal_validation,
        core.commit_followup_plan,
        core.purchase_resource,
        core.submit,
    ]


__all__ = [
    "OPEN_TOOL_SPECS",
    "OpenMMMVPEnvironment",
    "OpenProtocolError",
    "mmmvp_open_tool_functions",
]

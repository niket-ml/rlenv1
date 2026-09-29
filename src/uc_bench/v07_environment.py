"""Stateful tools and irreversible transitions for UC-Bench v0.7."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from uc_bench.errors import ConfigurationError
from uc_bench.v07_cases import PRIVATE_ROOT, PUBLIC_ROOT, RESOURCE_CATALOG, load_truth


class V07ProtocolError(RuntimeError):
    """Raised when an action violates an irreversible environment transition."""


@dataclass(slots=True)
class V07EpisodeState:
    case_id: str
    mechanism: str
    phase: str = "investigate"
    committed_plan_hash: str | None = None
    selected_resource: str | None = None
    spent_units: int = 0
    completion_accepted: bool = False
    terminal_reason: str | None = None
    tool_calls: int = 0
    event_log: list[dict[str, Any]] = field(default_factory=list)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_digest(value: dict[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _decode_payload(payload_json: str) -> dict[str, Any]:
    """Decode the strict string tool argument while allowing direct local calls."""

    value: Any = payload_json
    if isinstance(payload_json, str):
        try:
            value = json.loads(payload_json)
        except json.JSONDecodeError as exc:
            raise V07ProtocolError("Checkpoint payload_json must contain a JSON object") from exc
    if not isinstance(value, dict):
        raise V07ProtocolError("Checkpoint payload_json must decode to an object")
    return value


class V07Environment:
    """A compact diligence episode with one reveal and one resource purchase."""

    CHECKPOINTS = ("C1", "C2", "C3", "C4", "C5")

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
        self.run_root = run_root.resolve()
        self.maximum_tool_calls = maximum_tool_calls
        truth = load_truth(self.project_root, case_id)
        allowed = set(truth["mechanisms"])
        if mechanism not in allowed:
            raise ConfigurationError(
                f"Mechanism {mechanism!r} is not valid for {case_id}; expected {sorted(allowed)}"
            )
        if self.run_root.exists():
            raise FileExistsError(f"Episode directory already exists: {self.run_root}")
        shutil.copytree(self.project_root / PUBLIC_ROOT / case_id, self.run_root)
        (self.run_root / "checkpoints").mkdir()
        # Analyses may create scripts and derived tables without modifying the
        # immutable evidence packet.  Keeping that work in an explicit scratch
        # directory makes the boundary enforceable rather than relying on file
        # naming conventions.
        (self.run_root / "work").mkdir()
        self.state = V07EpisodeState(case_id=case_id, mechanism=mechanism)
        self._start_hashes = self._workspace_hashes()
        self._record("reset", visible_file_count=len(self._start_hashes))

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
            raise V07ProtocolError("Episode is already terminal")
        self.state.tool_calls += 1
        if self.state.tool_calls > self.maximum_tool_calls:
            self.state.phase = "terminal"
            self.state.terminal_reason = "tool_budget_exhausted"
            raise V07ProtocolError("Tool-call budget exhausted")

    def _workspace_hashes(self) -> dict[str, str]:
        hashes: dict[str, str] = {}
        excluded = {"checkpoints", "revealed", "purchased", "work"}
        for path in sorted(self.run_root.rglob("*")):
            if not path.is_file() or any(
                part in excluded for part in path.relative_to(self.run_root).parts
            ):
                continue
            hashes[str(path.relative_to(self.run_root))] = _digest(path)
        return hashes

    def _assert_untampered(self) -> None:
        if self._workspace_hashes() != self._start_hashes:
            self.state.phase = "terminal"
            self.state.terminal_reason = "start_state_tampering"
            self._record("integrity_rejection", reason="start_state_tampering")
            raise V07ProtocolError("Start-state evidence was modified")

    def _safe_visible_path(self, relative_path: str) -> Path:
        posix = PurePosixPath(relative_path)
        if posix.is_absolute() or ".." in posix.parts:
            raise V07ProtocolError("Only relative paths inside the visible workspace are allowed")
        if any(
            part.startswith("grader_private") or part.startswith(".uc_env") for part in posix.parts
        ):
            raise V07ProtocolError("Private grader data is not an agent-visible resource")
        resolved = (self.run_root / Path(*posix.parts)).resolve()
        if self.run_root not in resolved.parents and resolved != self.run_root:
            raise V07ProtocolError("Path escapes the visible workspace")
        return resolved

    def list_files(self) -> list[str]:
        self._count_tool()
        files = [
            str(path.relative_to(self.run_root))
            for path in sorted(self.run_root.rglob("*"))
            if path.is_file()
        ]
        self._record("list_files", returned=len(files))
        return files

    def read_file(self, relative_path: str) -> str:
        self._count_tool()
        path = self._safe_visible_path(relative_path)
        if not path.is_file():
            raise FileNotFoundError(relative_path)
        value = path.read_text(encoding="utf-8")
        self._record("read_file", path=relative_path, bytes=len(value.encode()))
        return value

    def save_checkpoint(self, checkpoint: str, payload_json: str) -> dict[str, Any]:
        self._count_tool()
        payload = _decode_payload(payload_json)
        checkpoint = checkpoint.upper()
        if checkpoint not in self.CHECKPOINTS:
            raise V07ProtocolError(f"Unknown checkpoint: {checkpoint}")
        if checkpoint == "C2":
            raise V07ProtocolError("Use commit_validation_plan for C2")
        if checkpoint == "C1" and self.state.phase not in {
            "investigate",
            "committed",
            "revealed",
            "purchased",
        }:
            raise V07ProtocolError("C1 cannot be changed in the current phase")
        if checkpoint in {"C3", "C4"} and self.state.phase not in {"revealed", "purchased"}:
            raise V07ProtocolError(f"{checkpoint} requires validation outcome reveal")
        if checkpoint == "C5" and self.state.phase != "purchased":
            raise V07ProtocolError(
                "C5 requires a completed resource action, including purchasing nothing"
            )
        path = self.run_root / "checkpoints" / f"{checkpoint}.json"
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        self._record("save_checkpoint", checkpoint=checkpoint, digest=_json_digest(payload))
        return {
            "checkpoint": checkpoint,
            "path": path.relative_to(self.run_root).as_posix(),
            "digest": _json_digest(payload),
        }

    def commit_validation_plan(self, payload_json: str) -> str:
        self._count_tool()
        payload = _decode_payload(payload_json)
        self._assert_untampered()
        if self.state.phase != "investigate":
            raise V07ProtocolError("Validation plan can be committed exactly once before reveal")
        if not (self.run_root / "checkpoints/C1.json").is_file():
            raise V07ProtocolError("C1 evidence and analysis unit must exist before commitment")
        digest = _json_digest(payload)
        (self.run_root / "checkpoints/C2.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        self.state.committed_plan_hash = digest
        self.state.phase = "committed"
        self._record("commit_validation_plan", digest=digest)
        return digest

    def reveal_validation(self) -> list[str]:
        self._count_tool()
        self._assert_untampered()
        if self.state.phase != "committed":
            raise V07ProtocolError("Validation outcomes require a prior locked commitment")
        source = self.project_root / PRIVATE_ROOT / self.case_id / "sealed"
        target = self.run_root / "revealed"
        shutil.copytree(source, target)
        self.state.phase = "revealed"
        files = sorted(
            str(path.relative_to(self.run_root)) for path in target.rglob("*") if path.is_file()
        )
        self._record(
            "reveal_validation",
            committed_plan_hash=self.state.committed_plan_hash,
            files=files,
        )
        return files

    def purchase_resource(self, resource_id: str) -> list[str]:
        self._count_tool()
        self._assert_untampered()
        if self.state.phase != "revealed":
            raise V07ProtocolError("A resource action follows revealed validation analysis")
        if (
            not (self.run_root / "checkpoints/C3.json").is_file()
            or not (self.run_root / "checkpoints/C4.json").is_file()
        ):
            raise V07ProtocolError("C3 calculations and C4 pre-purchase reasoning are required")
        by_id = {row["resource_id"]: row for row in RESOURCE_CATALOG}
        if resource_id not in by_id:
            raise V07ProtocolError(f"Unknown resource: {resource_id}")
        resource = by_id[resource_id]
        budget = load_truth(self.project_root, self.case_id)["resource_manifest"]
        cost = int(resource["cost_units"])
        public_budget = json.loads((self.run_root / "followup_catalog.json").read_text())[
            "budget_units"
        ]
        if cost > int(public_budget):
            raise V07ProtocolError("Selected resource exceeds the case budget")
        target = self.run_root / "purchased" / resource_id
        target.mkdir(parents=True)
        if resource_id == "none":
            (target / "no_new_evidence.json").write_text(
                '{"new_evidence": false}\n', encoding="utf-8"
            )
        else:
            source = (
                self.project_root / PRIVATE_ROOT / self.case_id / "resource_returns" / resource_id
            )
            if self.case_id == "case_03" and resource_id == "X31":
                source = source / self.state.mechanism
            if resource_id not in budget:
                raise V07ProtocolError("Resource return is not configured")
            shutil.copytree(source, target, dirs_exist_ok=True)
        self.state.selected_resource = resource_id
        self.state.spent_units = cost
        self.state.phase = "purchased"
        files = sorted(
            str(path.relative_to(self.run_root)) for path in target.rglob("*") if path.is_file()
        )
        self._record("purchase_resource", resource_id=resource_id, cost_units=cost, files=files)
        return files

    def submit(self) -> dict[str, Any]:
        self._count_tool()
        self._assert_untampered()
        if self.state.phase != "purchased":
            raise V07ProtocolError("Submission requires completion of the resource action")
        paths = {
            checkpoint: self.run_root / "checkpoints" / f"{checkpoint}.json"
            for checkpoint in self.CHECKPOINTS
        }
        missing = [checkpoint for checkpoint, path in paths.items() if not path.is_file()]
        if missing:
            raise V07ProtocolError(f"Missing checkpoints: {missing}")
        current_commit = _digest(paths["C2"])
        expected_commit = hashlib.sha256(
            json.dumps(
                json.loads(paths["C2"].read_text()), sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        if expected_commit != self.state.committed_plan_hash or current_commit == "":
            self.state.phase = "terminal"
            self.state.terminal_reason = "commitment_mutation"
            raise V07ProtocolError("Committed validation plan changed after reveal")
        self.state.completion_accepted = True
        self.state.phase = "terminal"
        self.state.terminal_reason = "submitted"
        self._record("submit", committed_plan_hash=self.state.committed_plan_hash)
        return self.export_submission()

    def export_submission(self) -> dict[str, Any]:
        checkpoints: dict[str, Any] = {}
        for checkpoint in self.CHECKPOINTS:
            path = self.run_root / "checkpoints" / f"{checkpoint}.json"
            if path.is_file():
                checkpoints[checkpoint] = json.loads(path.read_text(encoding="utf-8"))
        return {
            "case_id": self.case_id,
            "mechanism": self.state.mechanism,
            "checkpoints": checkpoints,
            "selected_resource": self.state.selected_resource,
            "spent_units": self.state.spent_units,
            "completion_accepted": self.state.completion_accepted,
            "terminal_reason": self.state.terminal_reason,
            "committed_plan_hash": self.state.committed_plan_hash,
            "tool_calls": self.state.tool_calls,
            "event_log": self.state.event_log,
        }

    def state_dict(self) -> dict[str, Any]:
        return asdict(self.state)

    def integrity_status(self) -> dict[str, Any]:
        """Return private runner checks without exposing grader truth to the agent."""

        plan = self.run_root / "checkpoints/C2.json"
        current_plan_hash: str | None = None
        if plan.is_file():
            try:
                current_plan_hash = _json_digest(json.loads(plan.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                current_plan_hash = "invalid"
        return {
            "start_state_untampered": self._workspace_hashes() == self._start_hashes,
            "commitment_recorded": self.state.committed_plan_hash is not None,
            "commitment_immutable": (
                self.state.committed_plan_hash is not None
                and current_plan_hash == self.state.committed_plan_hash
            ),
            "completion_accepted": self.state.completion_accepted,
            "phase": self.state.phase,
            "terminal_reason": self.state.terminal_reason,
        }

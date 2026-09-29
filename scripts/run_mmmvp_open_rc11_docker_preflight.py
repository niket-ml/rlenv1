#!/usr/bin/env python3
"""Exercise the exact RC1.1 physical boundary without contacting a model."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from uc_bench.mmmvp_open_rc11_environment import (
    ProtectedEvidenceTampering,
    RC11OpenMMMVPEnvironment,
    RecoverableWorkspacePathError,
    rc11_isolation_passed,
)
from uc_bench.mmmvp_open_rc11_runner import rc11_runtime_factory

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "artifacts/mmmvp_open_rc11/gemini_root_write_fixture.json"


def _attempt(runtime: object, command: str, expected: type[Exception]) -> str:
    try:
        runtime.run_command(command)  # type: ignore[attr-defined]
    except expected as exc:
        return type(exc).__name__
    raise AssertionError(f"Expected {expected.__name__}: {command}")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="uc-mmmvp-rc11-docker-") as temporary:
        root = Path(temporary)
        core = RC11OpenMMMVPEnvironment(ROOT, "case_02", root / "workspace")
        runtime = rc11_runtime_factory(
            core.run_root,
            container_name="uc-mmmvp-rc11-boundary-preflight",
            image="uc-bench-agent:0.1",
            core=core,
        )
        runtime.start()
        try:
            isolation = runtime.security_snapshot()
            if not rc11_isolation_passed(isolation):
                raise AssertionError("Nested mount isolation did not pass")
            core.mark_workspace_boundary_enforced(True)
            fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))["arguments"][
                "command"
            ]
            root_error = _attempt(runtime, fixture, RecoverableWorkspacePathError)
            if (core.run_root / "commit_vp.json").exists():
                raise AssertionError("The rejected root helper was created")
            if core.state.phase != "investigate":
                raise AssertionError("A recoverable write changed the episode phase")

            work_command = fixture.replace(
                "> commit_vp.json", "> work/commit_vp.json", 1
            )
            work_result = json.loads(runtime.run_command(work_command))
            if work_result["exit_code"] != 0 or not (
                core.run_root / "work/commit_vp.json"
            ).is_file():
                raise AssertionError("Equivalent work/ command did not succeed")
            cleanup = json.loads(runtime.run_command("rm work/commit_vp.json"))
            if cleanup["exit_code"] != 0:
                raise AssertionError("Agent-generated work deletion did not succeed")

            absolute_error = _attempt(
                runtime,
                "printf x > /workspace/new-root-helper.txt",
                RecoverableWorkspacePathError,
            )
            traversal_error = _attempt(
                runtime,
                "printf x > work/../new-root-helper.txt",
                RecoverableWorkspacePathError,
            )
            tmp_error = _attempt(
                runtime,
                "printf x > /tmp/not-allowed.txt",
                RecoverableWorkspacePathError,
            )
            tmp_exists = json.loads(runtime.run_command("test -e /tmp/not-allowed.txt"))[
                "exit_code"
            ] == 0
            if tmp_exists:
                raise AssertionError("A file was created outside work/ in /tmp")
        finally:
            runtime.stop()

        hard_core = RC11OpenMMMVPEnvironment(ROOT, "case_02", root / "hard-workspace")
        hard_runtime = rc11_runtime_factory(
            hard_core.run_root,
            container_name="uc-mmmvp-rc11-hard-preflight",
            image="uc-bench-agent:0.1",
            core=hard_core,
        )
        hard_runtime.start()
        try:
            hard_isolation = hard_runtime.security_snapshot()
            hard_core.mark_workspace_boundary_enforced(rc11_isolation_passed(hard_isolation))
            hard_error = _attempt(
                hard_runtime,
                "printf x > data/locked_predictions.csv",
                ProtectedEvidenceTampering,
            )
            if hard_core.state.phase != "terminal":
                raise AssertionError("Protected mutation attempt did not terminate")
            if not hard_core.integrity_status()["protected_evidence_untampered"]:
                raise AssertionError("Physical boundary allowed protected evidence to change")
        finally:
            hard_runtime.stop()

        output = {
            "status": "passed",
            "api_requests": 0,
            "scientific_requests": 0,
            "isolation": isolation,
            "exact_gemini_root_write": root_error,
            "equivalent_work_write_exit_code": work_result["exit_code"],
            "absolute_root_write": absolute_error,
            "traversal_write": traversal_error,
            "outside_workspace_tmp_write": tmp_error,
            "outside_workspace_tmp_file_created": tmp_exists,
            "protected_write": hard_error,
            "protected_content_unchanged": True,
        }
        print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
